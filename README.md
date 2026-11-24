# lead-list-cleaner

A small, free command-line tool that cleans and de-duplicates a CSV lead list before you use it for outreach. One Python file, standard library only, no network access, no API keys.

## What it does

- Reads a CSV (comma, semicolon or tab separated; UTF-8 with or without BOM).
- Finds the company, website and email columns by name, or you pass them with flags.
- Normalizes websites to a bare domain (`https://www.Acme.com/about` becomes `acme.com`).
- Lowercases and checks email syntax, and flags role addresses (`info@`, `sales@`), free providers (Gmail, Yahoo...), and a small sample list of disposable domains.
- Strips legal suffixes (Inc, LLC, Ltd, GmbH...) into a separate `clean_company` column. Your original columns are never changed.
- Marks duplicates by email, falling back to domain, then company name, and tells you which row they duplicate.

## What it does not do

- It does not check that a mailbox exists or that a website is live. These are syntax-level checks only, so a row marked `ok` can still bounce.
- The disposable-domain list is a short sample, not a complete one.
- It does not find or enrich leads. It only cleans a list you already have.

## Usage

```bash
python3 leadclean.py leads.csv                     # writes leads.cleaned.csv
python3 leadclean.py leads.csv -o clean.csv        # choose the output file
python3 leadclean.py leads.csv --only ok,review    # keep only these statuses
python3 leadclean.py leads.csv --email-col "Work Email"
```

Needs Python 3.8 or newer. It refuses to overwrite an existing output file unless you pass `--force`.

## Example

`sample_leads.csv` is included. Running the tool on it prints:

```
Read 9 rows from sample_leads.csv
  ok: 2
  review: 3
  invalid: 3
  duplicate: 1
Flags: disposable_email=1, duplicate=1, free_provider_email=1, invalid_domain=1, invalid_email=1, missing_email=1, role_email=1
Wrote 9 rows to sample.cleaned.csv
```

| Company | clean_status | clean_flags |
|---|---|---|
| Acme Inc. | ok | |
| ACME INC | duplicate | duplicate (of row 1) |
| Globex LLC | review | role_email |
| Initech | invalid | invalid_domain |
| Hooli Ltd | review | missing_email |
| Umbrella Corp | invalid | disposable_email |
| Stark Industries | review | free_provider_email |
| Wayne Co. | invalid | invalid_email |
| Wonka GmbH | ok | |

## Output columns

| Column | Meaning |
|---|---|
| `clean_company` | company name without the legal suffix |
| `clean_domain` | bare lowercase domain |
| `clean_email` | lowercase email with any `Name <...>` wrapper removed |
| `clean_status` | `ok`, `review` (worth a look), `invalid`, or `duplicate` |
| `clean_flags` | the reasons, separated by `;` |
| `clean_duplicate_of` | data row number this row duplicates |

## Tests

```bash
python3 -m unittest -v
```

## Want more?

This tool is the free, offline part. If you need more, the same author sells:

- **[Lead Enrichment & Cleanup MCP Server](https://payaion.com/m/dOYxSnIujENd)** ($19.99 USDC): an MCP server for Claude, Cursor or any MCP client that cleans a company list and adds AI-estimated industry, size band and contact role using your own Gemini API key. The AI fields are estimates, not verified data.
- **[Cold Email Personalizer](https://payaion.com/m/G5JzEGfU2ueG)** ($19.99 USDC): a Claude skill plus a Python helper that drafts personalized cold emails using only facts in each lead's row. It drafts only; nothing is sent.

Payments are in USDC and settle on-chain, so read the listing before you buy. More at the [DigitalSolutions site](https://throbbing-water-9fc1.digitalsolutionsmagic.workers.dev/).

## License

MIT. See `LICENSE`.
