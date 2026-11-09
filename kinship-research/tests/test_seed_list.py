"""Offline checks for the hand-compiled seed list and its discovery export."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from publish_pilot_discovery import seed_records,curated_records,combine
from export_seed_list import export_rows,collect_all,CHANNEL_TOPICS

SEED=ROOT/"registry/seed"

def seed_row(id="seedlist:a-2020-x",doi="10.1000/seed",title="Intergenerational wealth mobility",**kw):
    row={"id":id,"title":title,"authors":["Ann Author"],"year":2020,"source":"Economic Journal",
         "doi":doi,"url":"https://doi.org/"+doi if doi else "https://openalex.org/W1",
         "provider":"crossref","review_status":"pending","evidence_level":"metadata_only",
         "collection":"seedlist","kind":"journal_article","topics":["Wealth and inheritance"],
         "scope_tier":"core"}
    row.update(kw)
    return row

def write_jsonl(rows):
    d=tempfile.mkdtemp()
    p=Path(d)/"seed-list.jsonl"
    p.write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf-8")
    return p

class SeedRecordTests(unittest.TestCase):
    def test_only_core_rows_with_https_links_are_shown(self):
        rows=seed_records(write_jsonl([
            seed_row(),
            seed_row(id="seedlist:adj",doi="10.1000/adj",scope_tier="adjacent"),
            seed_row(id="seedlist:http",doi=None,url="http://example.org/paper"),
            seed_row(id="seedlist:old",doi="10.1000/old",year=1850),
            seed_row(id="seedlist:notopic",doi="10.1000/nt",topics=[]),
        ]))
        self.assertEqual([r["id"] for r in rows],["seedlist:a-2020-x"])

    def test_rows_stay_unreviewed_metadata(self):
        (row,)=seed_records(write_jsonl([seed_row()]))
        self.assertEqual(row["review_status"],"pending")
        self.assertEqual(row["evidence_level"],"metadata_only")
        self.assertEqual(row["collection"],"seedlist")
        self.assertNotIn("scope_rules",row)  # provenance stays in the JSONL, not the public index

    def test_reviewed_or_upgraded_rows_are_rejected(self):
        with self.assertRaises(ValueError):
            seed_records(write_jsonl([seed_row(review_status="curated")]))
        with self.assertRaises(ValueError):
            seed_records(write_jsonl([seed_row(evidence_level="editorial_summary")]))

    def test_missing_file_is_skipped(self):
        self.assertEqual(seed_records(Path(tempfile.mkdtemp())/"absent.jsonl"),[])
        self.assertEqual(seed_records(None),[])

    def test_curated_record_absorbs_seed_duplicate(self):
        papers=[{"id":"x","title":"Intergenerational wealth mobility","authors":["Ann Author"],
                 "year":2020,"source":"Economic Journal","doi":"10.1000/seed",
                 "paper_url":"https://doi.org/10.1000/seed","topics":["Wealth and inheritance"]}]
        merged=combine(seed_records(write_jsonl([seed_row()]))+curated_records(papers))
        self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]["review_status"],"curated")

class SeedExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.coding=list(csv.DictReader((SEED/"scope_coding.csv").open(encoding="utf-8-sig")))
        cls.enriched={r["seed_id"]:r for r in csv.DictReader(
            (SEED/"intergenerational_dataset.enriched.csv").open(encoding="utf-8-sig"))}
        cls.rows,cls.held=export_rows(cls.coding,cls.enriched)

    def test_every_coding_row_uses_known_channels(self):
        for c in self.coding:
            for ch in c["channels"].split(";"):
                self.assertIn(ch,CHANNEL_TOPICS,c["seed_id"])

    def test_export_contains_only_core_pending_https_records(self):
        core={c["seed_id"] for c in self.coding if c["scope_tier"]=="core"}
        self.assertEqual(len(self.rows)+len(self.held),len(core))
        for r in self.rows:
            self.assertIn(r["seed_id"],core)
            self.assertEqual((r["review_status"],r["evidence_level"]),("pending","metadata_only"))
            self.assertTrue(r["url"].startswith("https://"),r["id"])

    def test_committed_jsonl_matches_inputs(self):
        committed=[json.loads(l) for l in (ROOT/"registry/seed-list.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        rows,_,_=collect_all()
        self.assertEqual(committed,json.loads(json.dumps(rows,ensure_ascii=False)))

    def test_sources_are_tagged_and_ids_unique(self):
        rows,_,_=collect_all()
        self.assertEqual(len({r["id"] for r in rows}),len(rows))
        self.assertTrue({r["seed_source"] for r in rows}<={"spreadsheet","inheritance-library"})
        self.assertTrue(all(r["review_status"]=="pending" for r in rows))

if __name__=="__main__":
    unittest.main()
