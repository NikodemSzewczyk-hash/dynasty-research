"""Offline 23-source activation tests: no external network calls."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from dynasty_data.repec import listing_url,parse_listing,iter_repec
from dynasty_data.providers import iter_crossref,iter_openalex
from dynasty_data.schema import connect,initialize
from dynasty_data.catalog import enqueue
from pilot23_ingest import (
    sources_for_pilot,read_snapshot,read_state,merge_candidate,run,
    _write_snapshot,_write_json,SMOKE_IDS
)

REPEC_HTML="""<!DOCTYPE html><html><h2>Content</h2>
<h3>2026</h3><ul class="list-group paperlist">
<li class="list-group-item downfree"><b>19056
<a href="/p/iza/izadps/dp19056.html">Life-Cycle Effects of Childcare</a></b><br><i>by</i> Jane Doe & John Smith
<li class="list-group-item downfree"><b>19055
<a href="/p/iza/izadps/dp19055.html">Wealth among Siblings</a></b><br><i>by</i> Anna A & B. C
</ul></html>"""

def record(provider_id="https://openalex.org/W123",doi=None):
    return {"provider":"openalex","provider_id":provider_id,"doi":doi,
            "title":"Parental Wealth and Child Outcomes","authors":["A. Scholar"],
            "year":2025,"date":"2025-01-01","source_name":"Journal",
            "url":"https://example.org/paper","kind":"journal_article"}

class PilotTest(unittest.TestCase):
    def test_verified_source_manifest(self):
        sources=sources_for_pilot()
        self.assertEqual(len(sources),23)
        self.assertEqual(sum(s["kind"]=="journal" for s in sources),10)
        self.assertEqual(sum(s["kind"]=="researcher" for s in sources),10)
        self.assertEqual(sum(s["kind"]=="working_paper_series" for s in sources),3)
        self.assertEqual(len(SMOKE_IDS),3)
        self.assertEqual(len(set(s["id"] for s in sources)),23)
        self.assertFalse(any(s["id"]=="researcher:sandra-e-black" for s in sources))

    def test_unverified_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest=json.loads((ROOT/"registry/source_manifest.json").read_text())
            source=next(s for s in manifest["sources"] if s["id"]=="journal:american-economic-review")
            source["retrieval"]["enabled"]=False
            p=Path(tmp)/"manifest.json"
            p.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"not verified"):
                sources_for_pilot(p)

    def test_source_polls_sort_recent_first(self):
        seen=[]
        def crossref(url):
            seen.append(url)
            return {"message":{"items":[]}}
        list(iter_crossref("","2025-01-01","2026-11-07",2,
                           fetcher=crossref,journal_issn="0002-8282"))
        self.assertIn("sort=published",seen[0])
        self.assertIn("order=desc",seen[0])
        seen.clear()
        def openalex(url):
            seen.append(url)
            return {"results":[]}
        list(iter_openalex("","2025-01-01","2026-11-07",2,
                           fetcher=openalex,author_id="A5071390181"))
        self.assertIn("sort=publication_date%3Adesc",seen[0])
        self.assertIn("authorships.author.id",seen[0])

    def test_repec_parses_title_authors_year_and_handle(self):
        rows=parse_listing(REPEC_HTML,"RePEc:iza:izadps","IZA Discussion Papers",100)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["provider_id"],"RePEc:iza:izadps:dp19056")
        self.assertEqual(rows[0]["authors"],["Jane Doe","John Smith"])
        self.assertEqual(rows[0]["year"],2026)
        self.assertEqual(rows[1]["url"],"https://ideas.repec.org/p/iza/izadps/dp19055.html")
        self.assertEqual(rows[0]["kind"],"working_paper")

    def test_repec_fail_closed(self):
        with self.assertRaises(ValueError):
            listing_url("RePEc:unverified:series")
        with self.assertRaisesRegex(ValueError,"layout"):
            parse_listing("<html>no papers</html>","RePEc:iza:izadps","IZA",10)
        with self.assertRaises(ValueError):
            parse_listing(REPEC_HTML,"RePEc:iza:izadps","IZA",501)

    def test_repec_fetcher_injection(self):
        items=list(iter_repec("RePEc:iza:izadps","IZA",1,fetcher=lambda url: REPEC_HTML))
        self.assertEqual(len(items),1)

    def test_candidate_provenance_and_idempotence(self):
        rows={}
        a=record()
        self.assertTrue(merge_candidate(rows,a,"researcher:jan-stuhler","2026-11-07"))
        self.assertFalse(merge_candidate(rows,a,"researcher:jan-stuhler","2026-11-08"))
        self.assertFalse(merge_candidate(rows,a,"journal:american-economic-review","2026-11-08"))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[("openalex",a["provider_id"])]["pilot_first_seen"],"2026-11-07")
        self.assertEqual(len(rows[("openalex",a["provider_id"])]["pilot_source_ids"]),2)

    def test_checkpoint_does_not_advance_at_cap(self):
        source=sources_for_pilot()[0]
        records,state,report=run([source],{},{"schema_version":1,"sources":{}},
            "2026-01-01","2026-11-07",2,"2026-11-07",
            collector=lambda s,a,b,c: iter([record("https://openalex.org/W1"),
                                              record("https://openalex.org/W2")]))
        self.assertEqual(report["new_candidates"],2)
        self.assertEqual(report["sources_at_cap"],1)
        self.assertNotIn(source["id"],state["sources"])

    def test_failure_rolls_back_state_and_snapshot(self):
        source=sources_for_pilot()[0]
        existing=record()
        original={("openalex",existing["provider_id"]):existing}
        state={"schema_version":1,"sources":{}}
        def broken(*args):
            yield record("https://openalex.org/W2")
            raise RuntimeError("simulated outage")
        with self.assertRaisesRegex(RuntimeError,"no snapshot"):
            run([source],original,state,"2026-01-01","2026-11-07",3,"2026-11-07",collector=broken)
        self.assertEqual(len(original),1)
        self.assertEqual(state["sources"],{})

    def test_snapshot_roundtrip_and_review_gate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"candidate.jsonl"
            r=record()
            merge_candidate(rows:={},r,"researcher:jan-stuhler","2026-11-07")
            _write_snapshot(p,rows)
            self.assertEqual(len(read_snapshot(p)),1)
            _write_snapshot(p,{("openalex",r["provider_id"]):{**r,"review_status":"accepted"}})
            with self.assertRaisesRegex(ValueError,"reviewed"):
                read_snapshot(p)

    def test_repec_candidate_accepted_into_sqlite(self):
        with tempfile.TemporaryDirectory() as d:
            db=connect(Path(d)/"test.sqlite")
            try:
                initialize(db)
                rec=parse_listing(REPEC_HTML,"RePEc:iza:izadps","IZA",1)[0]
                self.assertTrue(enqueue(db,rec)[0])
                self.assertFalse(enqueue(db,rec)[0])
                self.assertEqual(db.execute("SELECT count(*) FROM candidates").fetchone()[0],1)
            finally:
                db.close()

if __name__=="__main__":
    unittest.main()
