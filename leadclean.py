#!/usr/bin/env python3
"""lead-list-cleaner: clean and de-duplicate a CSV lead list.

Standard library only. Works offline. Syntax-level checks only: it does not
verify that a mailbox exists or that a website is live.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from collections import Counter
from pathlib import Path

__version__ = "0.1.0"


class CleanError(Exception):
    """A problem the user can fix (bad path, missing column, ...)."""


LEGAL_SUFFIXES = {
    "inc", "inc.", "llc", "l.l.c.", "ltd", "ltd.", "limited", "corp", "corp.",
    "corporation", "co", "co.", "gmbh", "ag", "sa", "s.a.", "bv", "b.v.",
    "plc", "pty", "pvt", "llp", "lp",
}

ROLE_LOCALPARTS = {
    "info", "admin", "administrator", "sales", "support", "contact", "hello",
    "help", "office", "team", "mail", "enquiries", "inquiries", "marketing",
    "billing", "accounts", "hr", "jobs", "careers", "press", "media",
    "webmaster", "postmaster", "noreply", "no-reply", "donotreply",
    "do-not-reply",
}

FREE_PROVIDERS = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "live.com", "icloud.com", "aol.com", "proton.me", "protonmail.com",
    "gmx.com", "mail.com", "yandex.com",
}

# Small sample list, not exhaustive.
DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "temp-mail.org", "yopmail.com", "trashmail.com", "throwawaymail.com",
    "sharklasers.com", "getnada.com", "dispostable.com", "maildrop.cc",
}

DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
EMAIL_RE = re.compile(
    r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)

COMPANY_NAMES = {"company", "company name", "organization", "organisation",
                 "account name", "business name", "employer", "account"}
DOMAIN_NAMES = {"website", "domain", "url", "company website", "web", "site",
                "company domain", "website url"}
EMAIL_NAMES = {"email", "e mail", "email address", "work email", "e mail address"}

BLOCKING_FLAGS = {"invalid_email", "disposable_email", "invalid_domain"}
REVIEW_FLAGS = {"role_email", "free_provider_email", "missing_email", "missing_domain"}

CLEAN_COLS = ["clean_company", "clean_domain", "clean_email",
              "clean_status", "clean_flags", "clean_duplicate_of"]


def clean_whitespace(value) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def strip_legal_suffix(name: str) -> str:
    parts = name.split(" ")
    while len(parts) > 1 and parts[-1].lower().strip(",") in LEGAL_SUFFIXES:
        parts.pop()
    return " ".join(parts).rstrip(",").strip()


def normalize_domain(value):
    """Return (domain, flag). flag is '' when the domain looks valid."""
    v = clean_whitespace(value).lower()
    if not v:
        return "", "missing_domain"
    v = re.sub(r"^[a-z][a-z0-9+.-]*://", "", v)
    v = v.split("/")[0].split("?")[0].split("#")[0]
    v = v.split("@")[-1]
    v = v.split(":")[0]
    v = v.strip(".")
    if v.startswith("www."):
        v = v[4:]
    try:
        v = v.encode("idna").decode("ascii")
    except UnicodeError:
        return v, "invalid_domain"
    if not DOMAIN_RE.match(v):
        return v, "invalid_domain"
    return v, ""


def check_email(value):
    """Return (email, [flags]) using syntax-level checks only."""
    v = clean_whitespace(value).lower()
    if v.startswith("mailto:"):
        v = v[len("mailto:"):]
    m = re.search(r"<([^>]+)>", v)
    if m:
        v = m.group(1).strip()
    if not v:
        return "", ["missing_email"]
    if not EMAIL_RE.match(v):
        return v, ["invalid_email"]
    local, domain = v.rsplit("@", 1)
    if (len(local) > 64 or local.startswith(".") or local.endswith(".")
            or ".." in local):
        return v, ["invalid_email"]
    flags = []
    if local.split("+")[0] in ROLE_LOCALPARTS:
        flags.append("role_email")
    if domain in DISPOSABLE:
        flags.append("disposable_email")
    if domain in FREE_PROVIDERS:
        flags.append("free_provider_email")
    return v, flags


def detect_columns(headers, company_col=None, domain_col=None, email_col=None):
    norm = {h: re.sub(r"[\s_\-]+", " ", h.strip().lower()) for h in headers}

    def find(explicit, names):
        if explicit:
            if explicit not in headers:
                raise CleanError(f"column not found: {explicit!r}. Headers: {headers}")
            return explicit
        for h in headers:
            if norm[h] in names:
                return h
        return None

    return (find(company_col, COMPANY_NAMES),
            find(domain_col, DOMAIN_NAMES),
            find(email_col, EMAIL_NAMES))


def process(rows, company_col, domain_col, email_col):
    seen = {}
    out = []
    for idx, row in enumerate(rows, start=1):
        flags = []
        company = clean_whitespace(row.get(company_col, "")) if company_col else ""
        company_clean = strip_legal_suffix(company)

        email_clean, email_flags = "", []
        if email_col:
            email_clean, email_flags = check_email(row.get(email_col, ""))
            flags += email_flags

        domain_clean = ""
        if domain_col:
            domain_clean, dflag = normalize_domain(row.get(domain_col, ""))
            if dflag:
                flags.append(dflag)
        elif (email_clean and "invalid_email" not in email_flags
              and "free_provider_email" not in email_flags):
            domain_clean = email_clean.rsplit("@", 1)[1]

        key = None
        if email_clean and "invalid_email" not in email_flags:
            key = ("email", email_clean)
        elif domain_clean and "invalid_domain" not in flags:
            key = ("domain", domain_clean)
        elif company_clean:
            key = ("company", company_clean.lower())

        dup_of = ""
        if key is not None:
            if key in seen:
                dup_of = seen[key]
                flags.append("duplicate")
            else:
                seen[key] = idx

        if "duplicate" in flags:
            status = "duplicate"
        elif any(f in BLOCKING_FLAGS for f in flags):
            status = "invalid"
        elif any(f in REVIEW_FLAGS for f in flags):
            status = "review"
        else:
            status = "ok"

        new = dict(row)
        new.update({
            "clean_company": company_clean,
            "clean_domain": domain_clean,
            "clean_email": email_clean,
            "clean_status": status,
            "clean_flags": ";".join(flags),
            "clean_duplicate_of": dup_of,
        })
        out.append(new)
    return out


def read_rows(path: Path):
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise CleanError(f"file not found: {path}")
    except UnicodeDecodeError:
        raise CleanError("file is not UTF-8. Re-save it as 'CSV UTF-8' and try again.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect)
    if not reader.fieldnames:
        raise CleanError("the file is empty or has no header row")
    return reader.fieldnames, list(reader)


def run(args) -> int:
    src = Path(args.input)
    dest = Path(args.output) if args.output else src.with_name(src.stem + ".cleaned.csv")
    if dest.resolve() == src.resolve():
        raise CleanError("output path is the same as the input file")
    if dest.exists() and not args.force:
        raise CleanError(f"{dest} already exists (use --force to overwrite)")

    headers, rows = read_rows(src)
    company_col, domain_col, email_col = detect_columns(
        headers, args.company_col, args.domain_col, args.email_col)
    if not (company_col or domain_col or email_col):
        raise CleanError("could not find a company, website or email column. "
                         f"Headers: {headers}. Use --company-col/--domain-col/--email-col.")

    processed = process(rows, company_col, domain_col, email_col)
    statuses = Counter(r["clean_status"] for r in processed)
    flag_counts = Counter(f for r in processed for f in r["clean_flags"].split(";") if f)

    keep = None
    if args.only:
        keep = {s.strip() for s in args.only.split(",") if s.strip()}
        valid = {"ok", "review", "invalid", "duplicate"}
        if not keep <= valid:
            raise CleanError(f"--only accepts: {', '.join(sorted(valid))}")
        processed = [r for r in processed if r["clean_status"] in keep]

    fieldnames = [h for h in headers if h not in CLEAN_COLS] + CLEAN_COLS
    with dest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(processed)

    print(f"Read {len(rows)} rows from {src}", file=sys.stderr)
    for s in ("ok", "review", "invalid", "duplicate"):
        print(f"  {s}: {statuses.get(s, 0)}", file=sys.stderr)
    if flag_counts:
        print("Flags: " + ", ".join(f"{k}={v}" for k, v in sorted(flag_counts.items())),
              file=sys.stderr)
    print(f"Wrote {len(processed)} rows to {dest}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="leadclean",
        description="Clean and de-duplicate a CSV lead list (offline, syntax-level checks).")
    p.add_argument("input", help="CSV file with a header row")
    p.add_argument("-o", "--output", help="output CSV (default: <input>.cleaned.csv)")
    p.add_argument("--company-col", help="company column name (auto-detected if omitted)")
    p.add_argument("--domain-col", help="website/domain column name (auto-detected)")
    p.add_argument("--email-col", help="email column name (auto-detected)")
    p.add_argument("--only", help="keep only these statuses, e.g. ok or ok,review")
    p.add_argument("--force", action="store_true", help="overwrite the output file")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)
    try:
        return run(args)
    except CleanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
