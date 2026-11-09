"""Offline verified-source ingestion tests: no external network calls."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from dynasty_data.redif import (decode_redif,parse_redif,normalize_redif_paper,
                                list_redif_files,iter_redif_series,ideas_url)
from dynasty_data.providers import iter_crossref,iter_openalex,doi_convention_year
from dynasty_data.schema import connect,initialize
from dynasty_data.catalog import enqueue
from pilot23_ingest import (
    sources_for_pilot,read_snapshot,read_state,merge_candidate,run,
    _write_snapshot,_write_json,shard_name,SMOKE_IDS
)

REDIF=("Template-Type: ReDIF-Paper 1.0\n"
       "Author-Name: Doe, Jane\nAuthor-Email: jane@example.org\nAuthor-Workplace-Name: Univ\n"
       "Author-Name: Smith, John\n"
       "Title: Life-Cycle Effects of Childcare\n  and Parental Wealth\n"
       "Abstract: Copyrighted abstract text\n  continues here\n"
       "Classification-JEL: J13; D31\nCreation-Date: 202401\nNumber: 16706\n"
       "File-URL: https://example.org/dp16706.pdf\n"
       "Publication-Status: published in Journal of Things, 2025\n"
       "Handle: RePEc:iza:izadps:dp16706\n\n"
       "Template-Type: ReDIF-Paper 1.0\nTitle: Other series paper\nCreation-Date: 2024\n"
       "Handle: RePEc:iza:izarrs:rr1\n\n"
       "template-type: ReDIF-Paper 1.0\nTitle: Old paper\nCreation-Date: 1997-05\n"
       "Handle: RePEc:iza:izadps:dp1\n")

def record(provider_id="https://openalex.org/W123",doi=None):
    return {"provider":"openalex","provider_id":provider_id,"doi":doi,
            "title":"Parental Wealth and Child Outcomes","authors":["A. Scholar"],
            "year":2025,"date":"2025-01-01","source_name":"Journal",
            "url":"https://example.org/paper","kind":"journal_article"}

class VerifiedSourceTests(unittest.TestCase):
    def test_verified_source_manifest(self):
        sources=sources_for_pilot()
        self.assertEqual(len(sources),24)
        self.assertEqual(sum(s["kind"]=="journal" for s in sources),10)
        self.assertEqual(sum(s["kind"]=="researcher" for s in sources),10)
        self.assertEqual(sum(s["kind"]=="working_paper_series" for s in sources),4)
        adapters={s["id"]:s["retrieval"]["adapter"] for s in sources}
        self.assertEqual(adapters["working_paper_series:nber-working-papers"],"crossref_prefix")
        self.assertEqual(adapters["working_paper_series:ifs-working-papers"],"crossref_prefix")
        self.assertEqual(adapters["working_paper_series:cepr-discussion-papers"],"repec_redif")
        self.assertEqual(adapters["working_paper_series:iza-discussion-papers"],"repec_redif")
        self.assertTrue(SMOKE_IDS<=set(adapters))
        self.assertFalse(any(s["id"]=="researcher:sandra-e-black" for s in sources))

    def test_no_source_uses_website_scraping(self):
        # RePEc asks users not to scrape IDEAS pages (https://ideas.repec.org/getdata.html).
        manifest=json.loads((ROOT/"registry/source_manifest.json").read_text())
        adapters={(s.get("retrieval") or {}).get("adapter") for s in manifest["sources"]}
        self.assertNotIn("repec_series_listing",adapters)

    def test_unverified_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest=json.loads((ROOT/"registry/source_manifest.json").read_text())
            source=next(s for s in manifest["sources"] if s["id"]=="journal:american-economic-review")
            source["retrieval"]["enabled"]=False
            p=Path(tmp)/"manifest.json"
            p.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"not verified"):
                sources_for_pilot(p)

    def test_prefix_source_needs_doi_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest=json.loads((ROOT/"registry/source_manifest.json").read_text())
            source=next(s for s in manifest["sources"] if s["id"]=="working_paper_series:nber-working-papers")
            del source["identifiers"]["doi_pattern"]
            p=Path(tmp)/"manifest.json"
            p.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"doi_pattern"):
                sources_for_pilot(p)

class ProviderPagingTests(unittest.TestCase):
    def test_source_polls_sort_recent_first(self):
        seen=[]
        def crossref(url):
            seen.append(url)
            return {"message":{"items":[]}}
        list(iter_crossref("","2025-01-01","2026-11-07",2,
                           fetcher=crossref,journal_issn="0002-8282"))
        self.assertIn("from-pub-date",seen[0])
        self.assertIn("/journals/0002-8282/works",seen[0])
        seen.clear()
        def openalex(url):
            seen.append(url)
            return {"results":[]}
        list(iter_openalex("","2025-01-01","2026-11-07",2,
                           fetcher=openalex,author_id="A5071390181"))
        self.assertIn("sort=publication_date%3Adesc",seen[0])
        self.assertIn("authorships.author.id",seen[0])
        self.assertIn("cursor=%2A",seen[0])

    def test_crossref_prefix_cursor_and_stats(self):
        def item(i,prefix="w"):
            return {"DOI":f"10.3386/{prefix}{i}","title":[f"Paper {i}"],"type":"report","published":{"date-parts":[[1995]]}}
        pages=[{"message":{"total-results":1003,"next-cursor":"c2","items":[item(i) for i in range(1000)]}},
               {"message":{"total-results":1003,"next-cursor":"c3","items":[item(1000),item(1001,"c"),item(1002)]}}]
        seen=[]
        def fake(url):
            seen.append(url); return pages[len(seen)-1]
        stats={}
        got=list(iter_crossref("","1990-01-01","2026-11-08",5000,fetcher=fake,prefix="10.3386",stats=stats))
        self.assertIn("/prefixes/10.3386/works",seen[0])
        self.assertIn("rows=1000",seen[0])
        self.assertIn("cursor=c2",seen[1])
        self.assertEqual(len(seen),2)
        self.assertEqual(len(got),1003)
        self.assertEqual(stats,{"raw":1003,"available":1003})
        with self.assertRaises(ValueError):
            list(iter_crossref("","2020-01-01","2021-01-01",5,fetcher=fake,prefix="10.3386",journal_issn="0002-8282"))
        with self.assertRaises(ValueError):
            list(iter_crossref("","2020-01-01","2021-01-01",5,fetcher=fake,prefix="not-a-prefix"))

    def test_ifs_slash_variant_doi_year(self):
        self.assertEqual(doi_convention_year("10.1920/wp/ifs.2024.1924"),2024)

class RedifTests(unittest.TestCase):
    def test_parse_keeps_allowlisted_fields_only(self):
        t=parse_redif(REDIF)
        self.assertEqual(len(t),3)
        first=t[0]
        self.assertEqual(first["title"],"Life-Cycle Effects of Childcare and Parental Wealth")
        self.assertEqual(first["author-name"],["Doe, Jane","Smith, John"])
        for dropped in ("author-email","author-workplace-name","abstract","file-url"):
            self.assertNotIn(dropped,first)
        self.assertNotIn("jane@example.org",json.dumps(t))

    def test_normalize_series_filter_and_record_shape(self):
        t=parse_redif(REDIF)
        rec=normalize_redif_paper(t[0],"RePEc:iza:izadps","IZA Discussion Papers")
        self.assertEqual(rec["provider"],"repec")
        self.assertEqual(rec["provider_id"],"RePEc:iza:izadps:dp16706")
        self.assertEqual(rec["year"],2024)
        self.assertEqual(rec["url"],"https://ideas.repec.org/p/iza/izadps/dp16706.html")
        self.assertEqual(rec["jel"],["J13","D31"])
        self.assertEqual(rec["kind"],"working_paper")
        self.assertIsNone(normalize_redif_paper(t[1],"RePEc:iza:izadps","IZA"))  # other series
        with self.assertRaises(ValueError):
            ideas_url("not-a-handle")

    def test_decode_falls_back_to_cp1252(self):
        self.assertEqual(decode_redif("Orléans".encode("cp1252")),"Orléans")
        self.assertEqual(decode_redif("Orléans".encode("utf-8")),"Orléans")

    def test_decode_mixed_encodings_line_by_line(self):
        raw="Title: Today’s Children\n".encode("utf-8")+"Author-Name: Rault, Christophe (Orléans)\n".encode("cp1252")
        self.assertEqual(decode_redif(raw),"Title: Today’s Children\nAuthor-Name: Rault, Christophe (Orléans)\n")

    def test_listing_ignores_pdfs_and_fails_closed(self):
        http=b'<a href="izadp.2024.rdf">x</a><a href="izadp.2025.rdf">y</a><a href="dp1.pdf">z</a>'
        self.assertEqual(list_redif_files("https://x/izadps/",lambda u: http),["izadp.2024.rdf","izadp.2025.rdf"])
        ftp=b"-rw-r--r-- 1 1005 1005 793402 Dec 19 2018 DP0009.pdf\n-rw-r--r-- 1 1 1 9 Jan 1 2026 ceprdp.2026.cepr.rdf\n"
        self.assertEqual(list_redif_files("ftp://m/ceprdp/",lambda u: ftp),["ceprdp.2026.cepr.rdf"])
        with self.assertRaisesRegex(ValueError,"refusing empty"):
            list_redif_files("https://x/",lambda u: b"<html>nothing</html>")

    def test_iter_series_year_window_and_stats(self):
        files={"https://x/izadps/":b'<a href="izadp.1997.rdf"></a><a href="izadp.2024.rdf"></a><a href="izadp.2010.rdf"></a>',
               "https://x/izadps/izadp.2024.rdf":REDIF.encode("cp1252"),
               "https://x/izadps/izadp.1997.rdf":REDIF.encode("cp1252")}
        fetched=[]
        def fetch(url):
            fetched.append(url); return files[url]
        stats={}
        got=list(iter_redif_series("https://x/izadps/","RePEc:iza:izadps","IZA",2023,2026,stats=stats,fetch=fetch))
        self.assertEqual([r["provider_id"] for r in got],["RePEc:iza:izadps:dp16706"])
        self.assertNotIn("https://x/izadps/izadp.1997.rdf",fetched)  # outside window, not downloaded
        self.assertNotIn("https://x/izadps/izadp.2010.rdf",fetched)
        self.assertEqual(stats,{"files":1,"available":1,"raw":1})

    def test_redif_candidate_accepted_into_sqlite(self):
        with tempfile.TemporaryDirectory() as d:
            db=connect(Path(d)/"test.sqlite")
            try:
                initialize(db)
                rec=normalize_redif_paper(parse_redif(REDIF)[0],"RePEc:iza:izadps","IZA")
                self.assertTrue(enqueue(db,rec)[0])
                self.assertFalse(enqueue(db,rec)[0])
                self.assertEqual(db.execute("SELECT count(*) FROM candidates").fetchone()[0],1)
            finally:
                db.close()

class RunAndSnapshotTests(unittest.TestCase):
    def test_candidate_provenance_and_idempotence(self):
        rows={}
        a=record()
        self.assertTrue(merge_candidate(rows,a,"researcher:jan-stuhler","2026-11-07"))
        self.assertFalse(merge_candidate(rows,a,"researcher:jan-stuhler","2026-11-08"))
        self.assertFalse(merge_candidate(rows,a,"journal:american-economic-review","2026-11-08"))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[("openalex",a["provider_id"])]["pilot_first_seen"],"2026-11-07")
        self.assertEqual(len(rows[("openalex",a["provider_id"])]["pilot_source_ids"]),2)

    def test_checkpoint_does_not_advance_at_cap_without_provider_count(self):
        source=sources_for_pilot()[0]
        records,state,report=run([source],{},{"schema_version":1,"sources":{}},
            "2026-01-01","2026-11-07",2,"2026-11-07",
            collector=lambda s,a,b,c: iter([record("https://openalex.org/W1"),
                                              record("https://openalex.org/W2")]))
        self.assertEqual(report["new_candidates"],2)
        self.assertEqual(report["sources_at_cap"],1)
        self.assertNotIn(source["id"],state["sources"])

    def test_completeness_uses_provider_count(self):
        source=sources_for_pilot()[0]
        def partial(s,a,b,c,stats=None):
            stats.update(available=5,raw=2)
            yield record("https://openalex.org/W1")
        _,state,report=run([source],{},{"schema_version":1,"sources":{}},
                           "1990-01-01","2026-11-08",100,"2026-11-08",collector=partial)
        r=report["per_source"][0]
        self.assertEqual((r["provider_records_available"],r["provider_records_read"],r["coverage"]),(5,2,0.4))
        self.assertTrue(r["possibly_truncated"])
        entry=state["sources"][source["id"]]
        self.assertNotIn("last_successful_end",entry)  # no checkpoint for an incomplete read
        self.assertEqual(entry["coverage"]["read"],2)
        self.assertFalse(entry["coverage"]["complete"])
        def complete(s,a,b,c,stats=None):
            stats.update(available=1,raw=1)
            yield record("https://openalex.org/W1")
        _,state,report=run([source],{},{"schema_version":1,"sources":{}},
                           "1990-01-01","2026-11-08",100,"2026-11-08",collector=complete)
        self.assertEqual(report["per_source"][0]["coverage"],1.0)
        self.assertEqual(state["sources"][source["id"]]["last_successful_end"],"2026-11-08")

    def test_weekly_run_keeps_backfill_coverage(self):
        source=sources_for_pilot()[0]
        state={"schema_version":1,"sources":{source["id"]:{"last_successful_end":"2026-11-08",
               "coverage":{"start_date":"1990-01-01","read":5000,"available":5000,"complete":True}}}}
        def weekly(s,a,b,c,stats=None):
            stats.update(available=7,raw=7)
            yield record("https://openalex.org/W9")
        _,state,_=run([source],{},state,"2026-10-01","2026-11-15",100,"2026-11-15",collector=weekly)
        entry=state["sources"][source["id"]]
        self.assertEqual(entry["coverage"]["read"],5000)
        self.assertEqual(entry["last_successful_end"],"2026-11-15")

    def test_capped_rerun_does_not_replace_complete_coverage(self):
        source=sources_for_pilot()[0]
        state={"schema_version":1,"sources":{source["id"]:{
               "coverage":{"start_date":"1990-01-01","read":33146,"available":33146,"complete":True}}}}
        def capped(s,a,b,c,stats=None):
            stats.update(available=33146,raw=5000)
            yield record("https://openalex.org/W9")
        _,state,_=run([source],{},state,"1990-01-01","2026-11-15",5000,"2026-11-15",collector=capped)
        self.assertEqual(state["sources"][source["id"]]["coverage"]["read"],33146)

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

    def test_sharded_snapshot_per_primary_source(self):
        with tempfile.TemporaryDirectory() as d:
            shards=Path(d)/"snapshot"
            rows={}
            merge_candidate(rows,record("https://openalex.org/W1"),"researcher:jan-stuhler","2026-11-08")
            merge_candidate(rows,record("https://openalex.org/W2"),"researcher:raj-chetty","2026-11-08")
            merge_candidate(rows,record("https://openalex.org/W2"),"journal:american-economic-review","2026-11-08")
            _write_snapshot(shards,rows)
            names=sorted(p.name for p in shards.glob("*.jsonl"))
            self.assertEqual(names,[shard_name("journal:american-economic-review"),shard_name("researcher:jan-stuhler")])
            self.assertNotIn(":",names[0])
            self.assertEqual(read_snapshot(shards),rows)
            del rows[("openalex","https://openalex.org/W1")]
            _write_snapshot(shards,rows)
            self.assertEqual(len(list(shards.glob("*.jsonl"))),1)  # stale shard removed

if __name__=="__main__":
    unittest.main()
