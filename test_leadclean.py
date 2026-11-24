import csv
import tempfile
import unittest
from pathlib import Path

import leadclean as lc


def write(path: Path, text: str, encoding="utf-8"):
    path.write_bytes(text.encode(encoding))


def read(path: Path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


class UnitTests(unittest.TestCase):
    def test_domain(self):
        self.assertEqual(lc.normalize_domain("https://www.Acme.com/about?x=1"), ("acme.com", ""))
        self.assertEqual(lc.normalize_domain("acme.com:8080/"), ("acme.com", ""))
        self.assertEqual(lc.normalize_domain("not a domain")[1], "invalid_domain")
        self.assertEqual(lc.normalize_domain("localhost")[1], "invalid_domain")
        self.assertEqual(lc.normalize_domain(""), ("", "missing_domain"))

    def test_email(self):
        self.assertEqual(lc.check_email("  Jane.Doe@Acme.COM "), ("jane.doe@acme.com", []))
        self.assertEqual(lc.check_email("Jane Doe <jane@acme.com>"), ("jane@acme.com", []))
        self.assertIn("role_email", lc.check_email("info@acme.com")[1])
        self.assertIn("role_email", lc.check_email("sales+x@acme.com")[1])
        self.assertEqual(lc.check_email("jane@@acme.com")[1], ["invalid_email"])
        self.assertEqual(lc.check_email("jane@acme")[1], ["invalid_email"])
        self.assertEqual(lc.check_email(".jane@acme.com")[1], ["invalid_email"])
        self.assertIn("disposable_email", lc.check_email("a@mailinator.com")[1])
        self.assertIn("free_provider_email", lc.check_email("jane@gmail.com")[1])
        self.assertEqual(lc.check_email(""), ("", ["missing_email"]))

    def test_legal_suffix(self):
        self.assertEqual(lc.strip_legal_suffix("Acme, Inc."), "Acme")
        self.assertEqual(lc.strip_legal_suffix("Acme Holdings Ltd"), "Acme Holdings")
        self.assertEqual(lc.strip_legal_suffix("Inc"), "Inc")


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, text, *extra, name="in.csv", encoding="utf-8"):
        src = self.dir / name
        out = self.dir / "out.csv"
        write(src, text, encoding)
        code = lc.main([str(src), "-o", str(out), *extra])
        return code, out

    def test_mixed_list(self):
        csv_text = (
            "Company,Website,Email\n"
            "Acme Inc.,https://www.acme-example.com/,Jane@acme-example.com\n"
            "ACME INC,acme-example.com,jane@ACME-example.com\n"
            "Globex LLC,globex-example.com,info@globex-example.com\n"
            "Initech,not a domain,bob@initech-example.com\n"
            "Hooli,hooli-example.com,\n"
        )
        code, out = self.run_cli(csv_text)
        self.assertEqual(code, 0)
        rows = read(out)
        self.assertEqual([r["clean_status"] for r in rows],
                         ["ok", "duplicate", "review", "invalid", "review"])
        self.assertEqual(rows[0]["clean_company"], "Acme")
        self.assertEqual(rows[0]["clean_domain"], "acme-example.com")
        self.assertEqual(rows[1]["clean_duplicate_of"], "1")
        self.assertIn("role_email", rows[2]["clean_flags"])
        self.assertIn("invalid_domain", rows[3]["clean_flags"])
        self.assertIn("missing_email", rows[4]["clean_flags"])

    def test_dedupe_by_domain_without_email_column(self):
        code, out = self.run_cli("Company,Website\nAcme Inc,acme-example.com\nAcme,www.acme-example.com\n")
        self.assertEqual(code, 0)
        self.assertEqual([r["clean_status"] for r in read(out)], ["ok", "duplicate"])

    def test_semicolon_delimiter_and_bom(self):
        code, out = self.run_cli("Company;Email\nAcme;jane@acme-example.com\n",
                                 encoding="utf-8-sig")
        self.assertEqual(code, 0)
        self.assertEqual(read(out)[0]["clean_status"], "ok")

    def test_only_filter(self):
        csv_text = "Company,Email\nA,a@a-example.com\nB,not-an-email\n"
        code, out = self.run_cli(csv_text, "--only", "ok")
        self.assertEqual(code, 0)
        self.assertEqual(len(read(out)), 1)

    def test_refuses_overwrite_without_force(self):
        src = self.dir / "in.csv"
        out = self.dir / "out.csv"
        write(src, "Company,Email\nA,a@a-example.com\n")
        self.assertEqual(lc.main([str(src), "-o", str(out)]), 0)
        self.assertEqual(lc.main([str(src), "-o", str(out)]), 2)
        self.assertEqual(lc.main([str(src), "-o", str(out), "--force"]), 0)

    def test_errors(self):
        self.assertEqual(lc.main([str(self.dir / "missing.csv")]), 2)
        code, _ = self.run_cli("Foo,Bar\n1,2\n")
        self.assertEqual(code, 2)
        code, _ = self.run_cli("Company,Email\nA,a@a-example.com\n", "--only", "bogus")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
