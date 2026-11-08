"""Offline tests for the audit-sample metadata pre-check (no network)."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

SITE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SITE/"scripts"))
from audit_autocheck import cache_name,check,check_row,year_findings

FIELDS=["title","authors","year","source","doi","url","provider","relevance_score","stratum",
        "metadata_verified","topically_relevant","duplicate_version","reviewer_notes"]

def crossref(type_="journal-article",**dates):
    m={"title":["Intergenerational mobility in Britain"],"type":type_,
       "author":[{"given":"Lorraine","family":"Dearden"},{"given":"Stephen","family":"Machin"}],
       "container-title":[]}
    for k,v in dates.items(): m[k.replace("_","-")]={"date-parts":[[v]]}
    return m

def cached(doi,m):
    return {"doi":doi,"handle":{"status":200,"body":{"responseCode":1}},
            "crossref":{"status":200,"body":{"message":m}},
            "openalex":{"status":200,"body":{"id":"https://openalex.org/W1","publication_year":2017,
                                              "display_name":"Intergenerational mobility in Britain"}},
            "openalex_title_search":{"status":200,"body":{"results":[]}},"same_title_authors":{}}

def row(doi,year,notes=""):
    r=dict.fromkeys(FIELDS,"")
    r.update(title="Intergenerational mobility in Britain",authors="Lorraine Dearden, Stephen Machin",
             year=str(year),doi=doi,reviewer_notes=notes)
    return r

class AuditAutocheckTests(unittest.TestCase):
    def test_redeposited_working_paper_is_an_error(self):
        issues,_=year_findings(2025,crossref("report",published=2025,created=2017),1995)
        self.assertTrue(issues[0].startswith("ERROR: year 2025 is a re-deposit date; DOI encodes 1995"))

    def test_online_first_print_year_is_accepted(self):
        issues,notes=year_findings(2010,crossref(published_print=2010,issued=2010,created=2009),None)
        self.assertEqual(issues,[])
        self.assertIn("online-first 2009, issue/print 2010",notes[0])

    def test_online_only_year_far_after_deposit_is_uncertain(self):
        issues,_=year_findings(2021,crossref(published_online=2021,issued=2021,created=2015),None)
        self.assertTrue(issues[0].startswith("UNCERTAIN"))

    def test_malformed_author_is_flagged(self):
        m=crossref(published_print=2010,issued=2010)
        m["author"][1]={"given":"Machin,","family":"Machin"}
        ev=check_row(row("10.1/x",2010),cached("10.1/x",m),[])
        self.assertEqual(ev["metadata_verified"],"no")
        self.assertIn("malformed author",ev["issues"][0])

    def test_same_title_in_corpus_is_a_version(self):
        corpus=[("candidates-v03.jsonl","10.1/other","Intergenerational Mobility in Britain",["Lorraine Dearden"],1997)]
        ev=check_row(row("10.1/x",2010),cached("10.1/x",crossref(published_print=2010,issued=2010)),corpus)
        self.assertEqual(ev["duplicate_version"],"yes")

    def _sample(self,tmp,notes=""):
        tmp=Path(tmp); sample=tmp/"s.csv"; cache=tmp/"cache"; cache.mkdir()
        with sample.open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerow(row("10.1/x",2010,notes))
        (cache/cache_name("10.1/x")).write_text(json.dumps(cached("10.1/x",crossref(published_print=2010,issued=2010))))
        root=tmp/"site"; (root/"registry/snapshot").mkdir(parents=True); (root/"data").mkdir()
        (root/"registry/candidates-v03.jsonl").write_text("")
        (root/"data/papers.json").write_text("[]")
        return sample,cache,root

    def test_write_fills_columns_but_never_relevance(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample,cache,root=self._sample(tmp)
            check(cache,write=True,day="2026-11-07",sample=sample,evidence_out=Path(tmp)/"e.json",root=root)
            r=next(csv.DictReader(sample.open(encoding="utf-8")))
            self.assertEqual(r["metadata_verified"],"yes")
            self.assertEqual(r["topically_relevant"],"")
            self.assertTrue(r["reviewer_notes"].startswith("[auto-check 2026-11-07"))

    def test_refuses_to_overwrite_editor_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample,cache,root=self._sample(tmp,notes="Checked landing page myself")
            with self.assertRaises(SystemExit):
                check(cache,write=True,sample=sample,evidence_out=Path(tmp)/"e.json",root=root)

if __name__=="__main__":
    unittest.main()
