"""Offline regression tests for dynasty_ V0.2: no API calls or external packages."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SITE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SITE/"scripts"))
from dynasty_data.schema import connect,initialize
from dynasty_data.identity import canonical_doi,key,author_key,possible_match,external_nber_id
from dynasty_data.catalog import seed_sources,seed_curated,enqueue,decide,queue,stats,export_hugo,export_records
from dynasty_data.providers import normalize_openalex,normalize_crossref,iter_openalex,iter_crossref,lookup_source
from dynasty import set_source, main as dynasty_main
from dynasty_data.resolution import suggest_identifiers
from backfill_plan import build_jobs, main as backfill_main
from dynasty_data.nber import normalize_nber,iter_nber_tsv
import csv
import os
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO

def candidate(provider="openalex",doi=None,title="Family Wealth and Opportunity",authors=None,provider_id=None,year=2024):
    return {"provider":provider,"provider_id":provider_id or "https://openalex.org/W123456789",
            "doi":doi,"title":title,"authors":authors if authors is not None else ["Jane Smith","John Doe"],
            "year":year,"date":"2024-05-01","source_name":"Test Working Papers",
            "url":"https://example.org/paper", "kind":"working_paper"}

class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=connect(Path(self.tmp.name)/"research.sqlite")
        initialize(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def seed(self):
        seed_sources(self.db,SITE/"registry"/"source_manifest.json")
        seed_curated(self.db,SITE/"data"/"papers.json")

    def test_schema_and_source_registry(self):
        n=seed_sources(self.db,SITE/"registry"/"source_manifest.json")
        self.assertEqual(n,128)
        self.assertEqual(seed_sources(self.db,SITE/"registry"/"source_manifest.json"),0)
        self.assertEqual(stats(self.db)["sources"],128)
        all_rows=self.db.execute("SELECT id,retrieval_json FROM sources").fetchall()
        self.assertTrue(all(not json.loads(r["retrieval_json"])["enabled"] for r in all_rows))
        self.assertEqual(len({x["id"] for x in all_rows}),128)

    def test_manual_source_verification(self):
        seed_sources(self.db,SITE/"registry"/"source_manifest.json")
        sid="journal:american-economic-review"
        with self.assertRaisesRegex(ValueError,"disabled"):
            lookup_source(self.db,sid,"crossref")
        with self.assertRaisesRegex(ValueError,"Expected"):
            set_source(self.db,sid,"issn","fake","editor")
        set_source(self.db,sid,"issn","0002-8282","editor")
        self.assertEqual(lookup_source(self.db,sid,"crossref"),{"journal_issn":"0002-8282"})
        with self.assertRaisesRegex(ValueError,"Working-paper"):
            set_source(self.db,"working_paper_series:nber-working-papers","issn","0002-8282","editor")

    def test_seed_and_export_idempotent(self):
        self.seed()
        self.assertEqual(stats(self.db)["works"],12)
        self.assertEqual(stats(self.db)["versions"],16)
        self.assertEqual(stats(self.db)["published"],12)
        seed_curated(self.db,SITE/"data"/"papers.json")
        self.assertEqual(stats(self.db)["works"],12)
        self.assertEqual(stats(self.db)["versions"],16)
        folder=Path(self.tmp.name)/"hugo"
        report=export_hugo(self.db,folder)
        self.assertEqual(report["papers"],12)
        self.assertEqual(len(list((folder/"content"/"papers").glob("*.md"))),12)
        search=json.loads((folder/"static"/"data"/"research-index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(search),12)
        self.assertIn("authors",search[0])
        self.assertIn("paper_url",search[0])
        has_wp=[p for p in search if p.get("working_paper_url")]
        self.assertEqual(len(has_wp),4)
        self.assertTrue(all(p["version_count"]>=2 for p in has_wp))
        page=(folder/"content"/"papers"/"bequests-wealth-inequality.md").read_text(encoding="utf-8")
        self.assertIn("working_paper_url:",page)

    def test_doi_normalization(self):
        self.assertEqual(canonical_doi("HTTPS://DOI.ORG/10.3386/W22549?x=y"),"10.3386/w22549")
        self.assertEqual(canonical_doi("doi:10.1000/ABCD"),"10.1000/abcd")
        self.assertIsNone(canonical_doi("not-an-identifier"))
        self.assertEqual(author_key("Ana García"),"garcia")
        self.assertEqual(external_nber_id("https://www.nber.org/papers/w22549"),"w22549")
        self.assertEqual(key("Family   Wealth: A Test"),"family wealth a test")

    def test_exact_version_merging_across_providers(self):
        self.seed()
        doi="10.3386/w22549"
        rec=candidate(doi="https://doi.org/"+doi,title="Different title doesn't override editorial content",authors=["X Person"])
        ok,cid=enqueue(self.db,rec)
        self.assertTrue(ok)
        row=self.db.execute("SELECT match_type FROM candidates WHERE id=?",(cid,)).fetchone()
        self.assertEqual(row["match_type"],"exact")
        existing=self.db.execute("SELECT work_id FROM versions WHERE doi=?",(doi,)).fetchone()["work_id"]
        self.assertEqual(decide(self.db,cid,"approve",reviewer="tester"),existing)
        self.assertEqual(stats(self.db)["versions"],16)
        self.assertEqual(stats(self.db)["works"],12)
        self.assertEqual(self.db.execute("SELECT status FROM candidates WHERE id=?",(cid,)).fetchone()["status"],"accepted")
        self.assertEqual(self.db.execute("SELECT openalex_id FROM versions WHERE doi=?",(doi,)).fetchone()["openalex_id"],rec["provider_id"])

    def test_new_work_requires_editorial_content(self):
        ok,cid=enqueue(self.db,candidate())
        self.assertTrue(ok)
        self.assertEqual(queue(self.db)[0]["match_type"],"none")
        self.assertEqual(enqueue(self.db,candidate()),(False,cid))
        with self.assertRaisesRegex(ValueError,"takeaway"):
            decide(self.db,cid,"approve",reviewer="tester")
        self.assertEqual(stats(self.db)["works"],0)
        wid=decide(self.db,cid,"approve",reviewer="tester",takeaway="Family resources shape adult opportunity.",
                   topics=["Wealth and inheritance","Intergenerational mobility"],method="Register-based study")
        self.assertTrue(wid.startswith("family-wealth-and-opportunity"))
        self.assertEqual(stats(self.db)["published"],1)
        self.assertEqual(stats(self.db)["topics"],2)
        self.assertEqual(stats(self.db)["review_decisions"],1)
        with self.assertRaisesRegex(ValueError,"already"):
            decide(self.db,cid,"approve",reviewer="tester")
        search=export_records(self.db)
        self.assertEqual(len(search),1)
        self.assertEqual(search[0]["authors"],["Jane Smith","John Doe"])

    def test_fuzzy_match_blocks_accidental_merge(self):
        self.seed()
        base=self.db.execute("SELECT * FROM works LIMIT 1").fetchone()
        people=self.db.execute("""SELECT a.name FROM work_authors wa JOIN authors a ON a.id=wa.author_id
                                  WHERE wa.work_id=? ORDER BY wa.position""",(base["id"],)).fetchall()
        doc=candidate(title=base["title"],authors=[people[0]["name"]],year=base["year"]+2,provider_id="https://openalex.org/W555555")
        _,cid=enqueue(self.db,doc)
        record=self.db.execute("SELECT match_type,possible_work_id FROM candidates WHERE id=?",(cid,)).fetchone()
        self.assertEqual(record["match_type"],"possible")
        self.assertEqual(record["possible_work_id"],base["id"])
        with self.assertRaisesRegex(ValueError,"Possible existing"):
            decide(self.db,cid,"approve",reviewer="editor",takeaway="Test",topics=["Mobility"])
        self.assertEqual(decide(self.db,cid,"approve",reviewer="editor",merge_into=base["id"]),base["id"])
        self.assertEqual(stats(self.db)["versions"],17)
        self.assertEqual(self.db.execute("SELECT count(*) FROM works").fetchone()[0],12)

    def test_review_reject_defer_and_unreviewed_export(self):
        a=enqueue(self.db,candidate())[1]
        b=enqueue(self.db,candidate(provider="crossref",provider_id="10.1234/testing",doi="10.1234/testing"))[1]
        self.assertEqual(export_hugo(self.db,Path(self.tmp.name)/"site")["papers"],0)
        decide(self.db,a,"reject",reviewer="editor",notes="Out of scope")
        decide(self.db,b,"defer",reviewer="editor")
        self.assertEqual(stats(self.db)["queue_status"],{"deferred":1,"rejected":1})
        self.assertEqual(len(queue(self.db,"pending")),0)
        self.assertEqual(stats(self.db)["review_decisions"],2)

    def test_unsafe_candidate_urls_rejected(self):
        record=candidate()
        record["url"]="javascript:alert(1)"
        with self.assertRaisesRegex(ValueError,"HTTPS"):
            enqueue(self.db,record)

    def test_normalize_openalex(self):
        example={"id":"https://openalex.org/W123456789","title":"How Families Matter",
                 "doi":"https://doi.org/10.1234/example","publication_year":2023,
                 "publication_date":"2023-04-01","authorships":[{"author":{"display_name":"Jane Smith"}}],
                 "primary_location":{"source":{"display_name":"Journal of Economics"},"landing_page_url":"https://journal.example.com"},
                 "type":"article"}
        result=normalize_openalex(example)
        self.assertEqual(result["doi"],"10.1234/example")
        self.assertEqual(result["authors"],["Jane Smith"])
        self.assertEqual(result["kind"],"journal_article")
        self.assertEqual(result["provider_id"],example["id"])

    def test_normalize_crossref(self):
        example={"DOI":"10.1234/ABC","title":["A Good Research Paper"],"author":[{"given":"A.","family":"Smith"}],
                 "container-title":["Economic Journal"],"type":"journal-article",
                 "published":{"date-parts":[[2021,6,1]]},"URL":"https://doi.org/10.1234/ABC"}
        result=normalize_crossref(example)
        self.assertEqual(result["doi"],"10.1234/abc")
        self.assertEqual(result["authors"],["A. Smith"])
        self.assertEqual(result["year"],2021)
        self.assertEqual(result["source_name"],"Economic Journal")

    def test_bounded_openalex_queries(self):
        calls=[]
        example={"id":"https://openalex.org/W123456789","title":"Sample","doi":None,
                 "publication_year":2020,"authorships":[],"primary_location":{}}
        def fake(url):
            calls.append(url)
            return {"results":[example]}
        got=list(iter_openalex("intergenerational mobility","2000-01-01","2025-12-31",max_records=5,fetcher=fake))
        self.assertEqual(len(got),1)
        self.assertEqual(len(calls),1)
        self.assertIn("per_page=5",calls[0])
        self.assertIn("from_publication_date",calls[0])
        with self.assertRaisesRegex(ValueError,"1..10000"):
            list(iter_openalex("mobility","2020-01-01","2021-01-01",max_records=10001,fetcher=fake))

    def test_bounded_crossref_queries(self):
        calls=[]
        example={"DOI":"10.1000/test","title":["Sample study"],"author":[{"given":"A","family":"B"}],
                 "published":{"date-parts":[[2010]]},"type":"journal-article"}
        def fake(url):
            calls.append(url)
            return {"message":{"items":[example],"next-cursor":"NEXT"}}
        got=list(iter_crossref("wealth mobility","2000-01-01","2016-12-31",max_records=2,fetcher=fake))
        self.assertEqual(len(got),1)
        self.assertEqual(len(calls),1)
        self.assertIn("from-pub-date",calls[0])
        self.assertIn("query.bibliographic",calls[0])
        with self.assertRaises(ValueError):
            list(iter_crossref("","2023-01-01","2022-01-01",fetcher=fake))


    def test_source_identifier_suggestions_not_autoverified(self):
        seed_sources(self.db,SITE/"registry"/"source_manifest.json")
        sid="journal:quarterly-journal-of-economics"
        called=[]
        def fake(url):
            called.append(url)
            return {"results":[{"id":"https://openalex.org/S101","display_name":"Quarterly Journal of Economics",
                                "issn":["0033-5533"],"issn_l":"0033-5533","works_count":1234}]}
        result=suggest_identifiers(self.db,sid,limit=3,fetcher=fake)
        self.assertIn("UNVERIFIED",result["note"])
        self.assertEqual(result["suggestions"][0]["issn_candidates"],["0033-5533"])
        self.assertTrue(result["suggestions"][0]["name_exact"])
        self.assertIn("/sources?",called[0])
        db_source=self.db.execute("SELECT retrieval_json FROM sources WHERE id=?",(sid,)).fetchone()
        self.assertFalse(json.loads(db_source["retrieval_json"])["enabled"])

    def test_source_registry_dump_roundtrip(self):
        seed_sources(self.db,SITE/"registry"/"source_manifest.json")
        out=Path(self.tmp.name)/"verified-registry.json"
        with redirect_stdout(StringIO()):
            self.assertEqual(dynasty_main(["--db",str(Path(self.tmp.name)/"research.sqlite"),
                  "sources","dump","--output",str(out)]),0)
        data=json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"],1)
        self.assertEqual(len(data["sources"]),128)

    def test_importer_caps_include_malformed_records(self):
        fake_oa_calls=[]
        def oa(url):
            fake_oa_calls.append(url)
            return {"results":[{"id":"invalid","title":"Bad metadata"},{"id":"invalid2","title":"Bad metadata"}]}
        rows=list(iter_openalex("mobility","2010-01-01","2020-01-01",max_records=2,fetcher=oa))
        self.assertEqual(rows,[])
        self.assertEqual(len(fake_oa_calls),1)
        fake_cr_calls=[]
        def cr(url):
            fake_cr_calls.append(url)
            return {"message":{"items":[{"title":["No DOI"]},{"title":["Also no DOI"]}],"next-cursor":"MORE"}}
        rows=list(iter_crossref("mobility","2010-01-01","2020-01-01",max_records=2,fetcher=cr))
        self.assertEqual(rows,[])
        self.assertEqual(len(fake_cr_calls),1)


    def test_nber_preprint_link_matches_without_doi(self):
        self.seed()
        original=self.db.execute("SELECT work_id FROM versions WHERE provider_id='w21896'").fetchone()
        self.assertIsNotNone(original)
        rec=candidate(provider_id="https://openalex.org/W777000123",doi=None,
                      title="Different title for an old preprint",authors=["Unrelated Person"])
        rec["url"]="https://www.nber.org/papers/w21896"
        _,cid=enqueue(self.db,rec)
        row=self.db.execute("SELECT match_type,possible_work_id FROM candidates WHERE id=?",(cid,)).fetchone()
        self.assertEqual(row["match_type"],"exact")
        self.assertEqual(row["possible_work_id"],original["work_id"])
        self.assertEqual(decide(self.db,cid,"approve",reviewer="editor"),original["work_id"])
        self.assertEqual(stats(self.db)["versions"],16)
        linked=self.db.execute("SELECT openalex_id FROM versions WHERE provider_id='w21896'").fetchone()
        self.assertEqual(linked["openalex_id"],"https://openalex.org/W777000123")


    def test_historical_query_plan(self):
        plan=json.loads((SITE/"registry"/"discovery_plan.json").read_text(encoding="utf-8"))
        jobs=build_jobs(plan)
        self.assertEqual(len(jobs),36)
        selected=build_jobs(plan,provider="crossref",selected={"family-steps"})
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]["query"],"stepfamilies child outcomes")
        with self.assertRaisesRegex(ValueError,"do not exist"):
            build_jobs(plan,selected={"totally-unknown"})

    def test_backfill_dry_run_does_not_create_database(self):
        path=Path(self.tmp.name)/"not-created.sqlite"
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(backfill_main(["--db",str(path),"--max-jobs","2"]),0)
        report=json.loads(output.getvalue())
        self.assertEqual(report["mode"],"dry_run")
        self.assertEqual(len(report["jobs"]),2)
        self.assertFalse(path.exists())

    def test_review_csv_export_and_formula_escape(self):
        record=candidate(title='=HYPERLINK("https://example.com","click")')
        enqueue(self.db,record)
        path=Path(self.tmp.name)/"review.csv"
        with redirect_stdout(StringIO()):
            code=dynasty_main(["--db",str(Path(self.tmp.name)/"research.sqlite"),
                               "review","export","--output",str(path)])
        self.assertEqual(code,0)
        with path.open(encoding="utf-8",newline="") as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]["title"].startswith("'=HYPERLINK"))
        self.assertEqual(rows[0]["status"],"pending")


    def test_official_nber_tsv_import_and_version_match(self):
        self.seed()
        ref=Path(self.tmp.name)/"ref.tsv"
        ref.write_text(
            "paper\tauthor\ttitle\tissue_date\tdoi\n"
            "w21896\tA. Author and B. Author\tOld preprint test\t2016-05-01\t10.3386/w21896\n"
            "w543210\tJane Smith; John Doe\tNew NBER research\t2025-06-01\t\n"
            "c12345\tBook Author\tNot a working paper\t2020-01-01\t\n",
            encoding="utf-8")
        items=list(iter_nber_tsv(ref,from_year=2015,to_year=2026,max_records=10))
        self.assertEqual(len(items),2)
        self.assertEqual(items[0]["provider"],"nber")
        self.assertEqual(items[0]["authors"],["A. Author","B. Author"])
        self.assertEqual(items[0]["url"],"https://www.nber.org/papers/w21896")
        original=self.db.execute("SELECT work_id FROM versions WHERE provider_id='w21896'").fetchone()
        _,cid=enqueue(self.db,items[0])
        match=self.db.execute("SELECT match_type,possible_work_id FROM candidates WHERE id=?",(cid,)).fetchone()
        self.assertEqual(match["match_type"],"exact")
        self.assertEqual(match["possible_work_id"],original["work_id"])
        self.assertEqual(decide(self.db,cid,"approve",reviewer="editor"),original["work_id"])
        self.assertEqual(stats(self.db)["versions"],16)
        _,new_id=enqueue(self.db,items[1])
        self.assertEqual(self.db.execute("SELECT match_type FROM candidates WHERE id=?",(new_id,)).fetchone()[0],"none")
        self.assertEqual(stats(self.db)["queue_status"]["pending"],1)

    def test_nber_tsv_rejects_unrelated_files(self):
        path=Path(self.tmp.name)/"wrong.tsv"
        path.write_text("paper\ttitle\nw1234\tSample\n",encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"needs"):
            list(iter_nber_tsv(path))


    def test_api_key_not_embedded_in_search_urls(self):
        seen=[]
        example={"id":"https://openalex.org/W12345678","title":"Research","authorships":[],"primary_location":{}}
        def fake(url):
            seen.append(url)
            return {"results":[example]}
        with patch.dict(os.environ,{"OPENALEX_API_KEY":"top-secret-test-key"}):
            list(iter_openalex("mobility","2010-01-01","2020-01-01",max_records=2,fetcher=fake))
            source_rows=seed_sources(self.db,SITE/"registry"/"source_manifest.json")
            from dynasty_data.resolution import suggest_identifiers
            suggest_identifiers(self.db,"researcher:jan-stuhler",fetcher=lambda url: (seen.append(url) or {"results":[]}))
        self.assertTrue(seen)
        self.assertTrue(all("top-secret-test-key" not in url for url in seen))

if __name__=="__main__":
    unittest.main()
