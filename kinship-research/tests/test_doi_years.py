"""Offline tests for DOI-convention issue years (IFS re-deposit bug, 2026-11-07 audit)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SITE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SITE/"scripts"))
from dynasty_data.providers import doi_convention_year,normalize_crossref,normalize_openalex
from repair_doi_years import repair_jsonl,repair_json_list

def crossref_ifs(doi,published=2026,created=2017):
    return {"DOI":doi,"title":["Intergenerational mobility in Britain"],"type":"report",
            "author":[{"given":"Lorraine","family":"Dearden"}],
            "published":{"date-parts":[[published,3,11]]},"issued":{"date-parts":[[published,3,11]]},
            "created":{"date-parts":[[created,8,10]]},"URL":"https://doi.org/"+doi}

class DoiConventionYearTests(unittest.TestCase):
    def test_ifs_year_needs_both_encodings_to_agree(self):
        self.assertEqual(doi_convention_year("10.1920/wp.ifs.1995.9520"),1995)
        self.assertEqual(doi_convention_year("10.1920/wp.ifs.2017.w1711"),2017)
        self.assertEqual(doi_convention_year("10.1920/WP.IFS.2010.1016"),2010)
        self.assertEqual(doi_convention_year("10.1920/wp.ifs.2025.2225"),2025)  # newer NN/YY order
        self.assertEqual(doi_convention_year("10.1920/wp.ifs.2020.220"),2020)   # single-digit N/YY
        self.assertIsNone(doi_convention_year("10.1920/wp.ifs.2000.9710"))      # W97/10 under a 2000 DOI
        self.assertIsNone(doi_convention_year("10.1920/wp.ifs.2013.1604"))   # inconsistent
        self.assertIsNone(doi_convention_year("10.1920/wp.ifs.20256.6126"))  # malformed DOI
        self.assertIsNone(doi_convention_year("10.1016/j.jpubeco.2018.04.001"))
        self.assertIsNone(doi_convention_year(None))

    def test_crossref_redeposit_date_is_not_used_for_ifs(self):
        self.assertEqual(normalize_crossref(crossref_ifs("10.1920/wp.ifs.1995.9520",2025))["year"],1995)

    def test_other_crossref_years_unchanged(self):
        rec=crossref_ifs("10.1016/j.example.2020.01.001",2020,2018)
        self.assertEqual(normalize_crossref(rec)["year"],2020)

    def test_openalex_year_uses_convention(self):
        work={"id":"https://openalex.org/W2023628960","display_name":"Explaining the gradient",
              "doi":"https://doi.org/10.1920/wp.ifs.2010.1016","publication_year":2017,"authorships":[]}
        self.assertEqual(normalize_openalex(work)["year"],2010)

    def test_repair_rewrites_only_affected_lines(self):
        good={"doi":"10.1086/722084","title":"Kept","year":2024}
        bad={"doi":"10.1920/wp.ifs.2005.0505","title":"Fixed","year":2026}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"c.jsonl"
            original_good=json.dumps(good)
            p.write_text(original_good+"\n"+json.dumps(bad)+"\n",encoding="utf-8")
            changes=repair_jsonl(p,write=True)
            lines=p.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0],original_good)
            self.assertEqual(json.loads(lines[1])["year"],2005)
            self.assertEqual(changes,[("10.1920/wp.ifs.2005.0505",2026,2005)])
            self.assertEqual(repair_jsonl(p,write=True),[])  # idempotent

    def test_repair_json_list(self):
        rows=[{"doi":"10.1920/wp.ifs.2017.w1725","year":2026},{"doi":None,"year":2020}]
        self.assertEqual(repair_json_list(rows),[("10.1920/wp.ifs.2017.w1725",2026,2017)])
        self.assertEqual(rows[0]["year"],2017)
        self.assertEqual(rows[1]["year"],2020)

if __name__=="__main__":
    unittest.main()
