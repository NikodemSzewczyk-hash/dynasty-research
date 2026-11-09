"""Offline checks for the public, metadata-only discovery export."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from publish_pilot_discovery import (
    classify,valid_https,catalog_from_manifest,base_records,pilot_records,
    curated_records,combine,build,write_json,repair_encoding
)

def pilot(id="10.1000/abc",title="Inheritance and wealth inequality",doi=None):
    return {
        "provider":"crossref","provider_id":id,"title":title,
        "authors":["Researcher A"],"year":2025,"date":None,
        "source_name":"American Economic Review","url":"https://doi.org/"+id,
        "doi":doi,"kind":"journal_article",
        "pilot_source_ids":["journal:american-economic-review"],
        "review_status":"pending","evidence_level":"metadata_only"
    }

class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((ROOT/"registry/source_manifest.json").read_text())
        cls.papers=json.loads((ROOT/"data/papers.json").read_text())

    def test_title_screen_is_conservative(self):
        self.assertIn("Intergenerational mobility",classify("Intergenerational income mobility"))
        self.assertIn("Wealth and inheritance",classify("Inheritance and wealth inequality"))
        self.assertIn("Family structure",classify("Parental divorce and child outcomes"))
        self.assertEqual(classify("The Effect of Interest Rates on Asset Prices"),[])
        self.assertEqual(classify("Climate Change and Economic Growth"),[])
        self.assertEqual(classify("Financial Market Risk and Volatility"),[])

    def test_catalog_reports_verified_sources(self):
        c=catalog_from_manifest(self.manifest)
        self.assertEqual(c["summary"]["verified_active"],24)
        self.assertEqual(c["summary"]["registered"],128)
        self.assertEqual(c["summary"]["planned"],104)
        self.assertEqual(sum(x["active"] for x in c["journals"]),10)
        self.assertEqual(sum(x["active"] for x in c["repositories"]),4)
        self.assertEqual(sum(x["active"] for x in c["researchers"]),10)
        self.assertTrue(all(x["evidence_url"].startswith("https://") for rows in
            (c["journals"],c["repositories"],c["researchers"]) for x in rows if x["active"]))

    def test_screened_snapshot_excludes_irrelevant_and_unverified(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"snapshot.jsonl"
            bad=pilot("10.1000/bad","Unrelated quantum physics")
            good=pilot()
            unknown=pilot("10.1000/unknown")
            unknown["pilot_source_ids"]=["journal:unverified"]
            path.write_text("\n".join(json.dumps(x) for x in [bad,good,unknown])+"\n")
            records,stats=pilot_records(path,self.manifest)
            self.assertEqual(stats["raw_candidates"],3)
            self.assertEqual(stats["title_screened_candidates"],1)
            self.assertEqual(stats["unrecognized_source_rows"],1)
            self.assertEqual(records[0]["topics"],["Wealth and inheritance"])
            self.assertEqual(records[0]["source_ids"],["journal:american-economic-review"])

    def test_book_chapters_are_not_mislabelled_as_papers(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"snapshot.jsonl"
            chapter=pilot("10.1000/book","Intergenerational Income Mobility")
            chapter["kind"]="other"
            path.write_text(json.dumps(chapter)+"\n")
            records,stats=pilot_records(path,self.manifest)
            self.assertEqual(records,[])
            self.assertEqual(stats["title_screened_candidates"],0)

    def test_duplicate_doi_prefers_curated_and_retains_provenance(self):
        curated=curated_records(self.papers)[0]
        paper=pilot("10.1000/x","Intergenerational mobility",doi=curated["doi"])
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"snapshot.jsonl"
            path.write_text(json.dumps(paper)+"\n")
            new,_=pilot_records(path,self.manifest)
            merged=combine(new+[curated])
            self.assertEqual(len(merged),1)
            self.assertEqual(merged[0]["review_status"],"curated")
            self.assertIn("journal:american-economic-review",merged[0]["source_ids"])

    def test_exact_title_and_first_author_group_versions(self):
        a={"id":"a","title":"Educational Mobility Across Generations","authors":["Jan Stuhler"],
           "doi":"10.1234/working","url":"https://example.org/a","source":"SSRN",
           "provider":"openalex","review_status":"pending","collection":"pilot23",
           "source_ids":["researcher:jan-stuhler"],"topics":["Intergenerational mobility"],"score":14,"year":2025}
        b={**a,"id":"b","title":"Educational mobility across generations",
           "doi":"10.1234/journal","url":"https://example.org/b",
           "source":"Journal of Development Economics","year":2026}
        out=combine([a,b])
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["source"],"Journal of Development Economics")
        self.assertEqual(out[0]["version_count"],2)
        self.assertEqual(out[0]["match_type"],"possible")
        c={**b,"id":"c","authors":["Someone Else"],"doi":"10.1234/other"}
        self.assertEqual(len(combine([a,b,c])),2)

    def test_excludes_replication_packages_and_repairs_mojibake(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"snapshot.jsonl"
            replication=pilot("10.1000/rep","Replication Code for: Intergenerational Mobility")
            actual=pilot("10.1000/actual","Will Todayâ€™s Children Be Richer than Their Parents? Intergenerational Mobility")
            path.write_text("\n".join(json.dumps(x) for x in [replication,actual])+"\n")
            rows,stats=pilot_records(path,self.manifest)
            self.assertEqual(stats["title_screened_candidates"],1)
            self.assertIn("Today’s",rows[0]["title"])

    def test_baseline_does_not_duplicate_previous_exports(self):
        existing=[
            {"id":"crossref:1","title":"Intergenerational mobility",
             "review_status":"pending","evidence_level":"metadata_only"},
            {"id":"pilot:1","title":"Inheritance","collection":"pilot23",
             "review_status":"pending","evidence_level":"metadata_only"},
            {"id":"curated:1","title":"Mobility","collection":"curated",
             "review_status":"curated","evidence_level":"editorial_summary"},
        ]
        base=base_records(existing)
        self.assertEqual(len(base),1)
        self.assertEqual(base[0]["collection"],"historical")

    def test_reject_unsafe_urls(self):
        for url in ["javascript:alert(1)","http://example.com","https://user:pass@example.com","/path"]:
            self.assertIsNone(valid_https(url))
        self.assertEqual(valid_https("https://doi.org/10.1000/abc"),"https://doi.org/10.1000/abc")

    def test_build_reports_counts_and_does_not_upgrade_pending_status(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"snapshot.jsonl"
            path.write_text(json.dumps(pilot())+"\n")
            legacy=[{"id":"crossref:legacy","title":"Parental divorce and child outcomes",
                     "authors":[],"year":2020,"source":"Journal",
                     "review_status":"pending","evidence_level":"metadata_only",
                     "doi":None,"url":"https://example.org"}]
            cat,index,report=build(self.manifest,self.papers,legacy,path)
            self.assertEqual(report["pilot_displayed"],1)
            self.assertEqual(report["curated_displayed"],12)
            self.assertEqual(report["historical_displayed"],1)
            self.assertEqual(report["total_displayed"],14)
            self.assertEqual(len([x for x in index if x["review_status"]=="curated"]),12)
            self.assertEqual(len([x for x in index if x["review_status"]=="pending"]),2)
            self.assertEqual(cat["summary"]["verified_active"],24)

class SurnameKeyTests(unittest.TestCase):
    def test_repec_and_crossref_name_orders_match(self):
        from publish_pilot_discovery import _surname_key
        self.assertEqual(_surname_key("Snower, Dennis"),_surname_key("Dennis Snower"))
        self.assertEqual(_surname_key("Moraga-González, José-Luis"),_surname_key("José-Luis Moraga-González"))
        self.assertEqual(_surname_key("Sánchez de la Sierra, Raúl"),_surname_key("Raúl Sánchez de la Sierra"))
        self.assertNotEqual(_surname_key("Snower, Dennis"),_surname_key("Dennis Smith"))

if __name__=="__main__":
    unittest.main()
