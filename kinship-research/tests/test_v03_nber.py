"""Offline fixture tests for the official NBER metadata selector."""
import sys
import unittest
from pathlib import Path

SITE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SITE/"scripts"))
from v03_nber import choose_nber_rows,fetch_nber_metadata

class NberV03Test(unittest.TestCase):
    def test_era_balance_and_domain_filter(self):
        raw=("paper\tauthor\ttitle\tissue_date\tdoi\n"
             "w10000\tA. Author\tParental Wealth and Adult Children's Income\t2004\t10.3386/w10000\n"
             "w20000\tB. Author\tIntergenerational Wealth Mobility\t2014\t10.3386/w20000\n"
             "w30000\tC. Author\tInheritance and Wealth Inequality\t2023\t10.3386/w30000\n"
             "w40000\tD. Author\tGenetic Inheritance of Rare Diseases\t2024\t10.3386/w40000\n"
             "w50000\tE. Author\tParental Income and Educational Mobility\t2022\t10.3386/w50000\n").encode()
        selected,summary=choose_nber_rows(raw,max_per_era=1,min_score=8)
        self.assertEqual(len(selected),3)
        self.assertEqual({r["year"] for r in selected},{2004,2014,2022})
        self.assertEqual(summary["scanned_rows"],5)

    def test_bad_metadata_header(self):
        with self.assertRaises(ValueError):
            choose_nber_rows(b"foo\tbar\n1\t2\n")

    def test_only_official_source_allowed(self):
        with self.assertRaises(ValueError):
            fetch_nber_metadata("https://example.com/metadata.tsv")

if __name__=="__main__":
    unittest.main()
