"""Offline tests of the V0.3 historical discovery and metadata-only preview."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

SITE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SITE/"scripts"))
from dynasty_data.schema import connect,initialize
from dynasty_data.catalog import seed_sources,seed_curated,enqueue
from v03_bootstrap import relevance_score,export_discovery
from dynasty_data.providers import normalize_crossref
from backfill_plan import build_jobs
from rebuild_candidates import load_candidates

class V03Test(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=connect(Path(self.tmp.name)/"test.sqlite")
        initialize(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_relevance_heuristic_is_transparent(self):
        self.assertGreater(relevance_score("Intergenerational Wealth Mobility"),relevance_score("Quantum chemistry in liquids"))
        self.assertEqual(relevance_score("Quantum chemistry in liquids"),0)

    def test_biomedical_and_software_false_positives_excluded(self):
        self.assertEqual(relevance_score("Autosomal dominant inheritance of prostate cancer"),0)
        self.assertEqual(relevance_score("Inheritance graph construction in software systems"),0)
        self.assertEqual(relevance_score("International capital mobility: panel evidence"),0)
        self.assertEqual(relevance_score("Limited joint mobility in children with diabetes"),0)
        self.assertGreater(relevance_score("Parental Wealth and Adult Children's Earnings","Journal of Labor Economics"),8)

    def test_crossref_html_entities_are_decoded(self):
        rec={"DOI":"10.1234/test","title":["Wealth &amp; Inequality"],"container-title":["Economics &amp; Society"],
             "author":[{"given":"A","family":"B"}],"type":"journal-article"}
        normalized=normalize_crossref(rec)
        self.assertEqual(normalized["title"],"Wealth & Inequality")
        self.assertEqual(normalized["source_name"],"Economics & Society")

    def test_plan_jobs_are_bounded(self):
        plan=json.loads((SITE/"registry"/"discovery_plan.json").read_text(encoding="utf-8"))
        jobs=build_jobs(plan,provider="crossref")
        self.assertEqual(len(jobs),18)
        self.assertTrue(all(job["provider"]=="crossref" for job in jobs))

    def test_export_never_promotes_unreviewed_candidates(self):
        seed_sources(self.db,SITE/"registry"/"source_manifest.json")
        seed_curated(self.db,SITE/"data"/"papers.json")
        record={"provider":"crossref","provider_id":"10.1234/metadata-only",
                "doi":"10.1234/metadata-only","title":"Intergenerational Wealth Mobility in Families",
                "authors":["A. Scholar"],"year":2023,"date":None,
                "source_name":"Test Journal","url":"https://doi.org/10.1234/metadata-only",
                "kind":"journal_article"}
        created,cid=enqueue(self.db,record)
        self.assertTrue(created)
        result=export_discovery(self.db,Path(self.tmp.name)/"export",max_public=20,min_score=3)
        self.assertEqual(result["metadata_only_public_records"],1)
        public=json.loads((Path(self.tmp.name)/"export"/"discovery-index.json").read_text())
        self.assertEqual(public[0]["evidence_level"],"metadata_only")
        self.assertEqual(public[0]["review_status"],"pending")
        self.assertNotIn("takeaway",public[0])
        self.assertEqual(self.db.execute("SELECT count(*) FROM works").fetchone()[0],12)

    def test_exact_curated_matches_are_not_duplicated_in_public_preview(self):
        seed_curated(self.db,SITE/"data"/"papers.json")
        seed=self.db.execute("SELECT title,year,doi FROM versions WHERE doi IS NOT NULL LIMIT 1").fetchone()
        record={"provider":"crossref","provider_id":seed["doi"],"doi":seed["doi"],
                "title":seed["title"],"authors":["A. Scholar"],"year":seed["year"],
                "source_name":"Journal","url":"https://doi.org/"+seed["doi"],
                "kind":"journal_article"}
        enqueue(self.db,record)
        result=export_discovery(self.db,Path(self.tmp.name)/"export",max_public=20,min_score=0)
        self.assertEqual(result["metadata_only_public_records"],0)

    def test_version_controlled_jsonl_can_rebuild_unreviewed_queue(self):
        rec={"provider":"crossref","provider_id":"10.1234/rebuild","doi":"10.1234/rebuild",
             "title":"Intergenerational Wealth Mobility","authors":["Jane Scholar"],
             "year":2020,"source_name":"Economics Journal",
             "url":"https://doi.org/10.1234/rebuild","kind":"journal_article"}
        enqueue(self.db,rec)
        out=Path(self.tmp.name)/"export"
        export_discovery(self.db,out)
        archive=out/"all-candidates.jsonl"
        self.assertTrue(archive.is_file())
        new_db=connect(Path(self.tmp.name)/"rebuild.sqlite")
        try:
            initialize(new_db)
            result=load_candidates(new_db,archive)
            self.assertEqual(result["read"],1)
            self.assertEqual(result["new"],1)
            self.assertEqual(load_candidates(new_db,archive)["new"],0)
        finally:
            new_db.close()

    def test_title_only_exclusion_keeps_record_in_review_queue(self):
        rec={"provider":"crossref","provider_id":"10.5465/amj.2017.0769",
             "doi":"10.5465/amj.2017.0769",
             "title":"Intergenerational Wealth Mobility","authors":["A. Scholar"],
             "year":2020,"source_name":"Economics",
             "url":"https://doi.org/10.5465/amj.2017.0769","kind":"journal_article"}
        enqueue(self.db,rec)
        result=export_discovery(self.db,Path(self.tmp.name)/"export",min_score=0)
        self.assertEqual(result["metadata_only_public_records"],0)
        self.assertEqual(result["total_candidate_rows"],1)

    def test_spreadsheet_formula_injection_defanged(self):
        rec={"provider":"crossref","provider_id":"10.1234/safe",
             "doi":"10.1234/safe","title":"=1+1","authors":["@author"],
             "year":2022,"source_name":"-journal","url":"https://doi.org/10.1234/safe",
             "kind":"journal_article"}
        enqueue(self.db,rec)
        export_discovery(self.db,Path(self.tmp.name)/"export",min_score=0)
        with (Path(self.tmp.name)/"export"/"review-queue.csv").open(encoding="utf-8",newline="") as f:
            row=next(csv.DictReader(f))
        self.assertEqual(row["title"],"'=1+1")
        self.assertEqual(row["authors"],"'@author")
        self.assertEqual(row["source"],"'-journal")

if __name__=="__main__":
    unittest.main()
