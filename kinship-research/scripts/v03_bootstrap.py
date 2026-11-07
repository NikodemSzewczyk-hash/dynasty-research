#!/usr/bin/env python3
"""V0.3 bounded historical metadata backfill and *unreviewed* discovery export.

Nothing here approves a paper, writes an editorial summary, or downloads a PDF.
The public-facing metadata index is explicitly labelled as unreviewed.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

from backfill_plan import build_jobs
from dynasty_data.schema import connect, initialize
from dynasty_data.catalog import seed_sources, seed_curated, enqueue, stats
from dynasty_data.providers import iter_crossref, iter_openalex
from dynasty_data.identity import key

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "registry" / "discovery_plan.json"
# Topic-aware lexical gate. This is an *inclusion heuristic*, not a claim of relevance.
ECON_WORDS = {"income","wealth","inequality","mobility","earnings","education","school",
              "schooling","bequest","inheritance","financial","labor","labour","poverty",
              "transfer","transfers","gifts","estate","taxation","economic","economics",
              "housing","employment","wages","occupation","capital","redistribution",
              "social","class","opportunity"}
FAMILY_WORDS = {"intergenerational","multigenerational","parent","parents","parental",
                "children","child","family","families","sibling","siblings","divorce",
                "stepfamily","stepfamilies","grandparents","grandparent","inheritance",
                "bequest","bequests","mobility","neighborhood","neighbourhood"}
STRONG_PHRASES = {
    "intergenerational mobility","intergenerational wealth","intergenerational income",
    "wealth mobility","income mobility","educational mobility","social mobility",
    "wealth inequality","income inequality","intergenerational transmission",
    "parental wealth","parental income","family wealth","parental transfers",
    "inter vivos","bequest motives","inheritance tax","estate tax",
    "family structure","birth order","neighborhood effects","neighbourhood effects",
    "economic opportunity","social capital","parental divorce","adult children",
    "intergenerational transfers","multigenerational mobility",
}
NEGATIVE_WORDS = {
    "genetic","autosomal","mitochondrial","chromosome","diabetes","protein","cell",
    "clinical","mutation","patients","cancer","syndrome","immunodeficiency",
    "electrons","semiconductor","crystal","quantum","materials","alloy",
    "software","algorithm","programming","compiler","molecular","bacteria",
    "trout","carp","soil","leachate","flow liquefaction",
}
VENUE_TERMS = {"economic","economics","finance","sociology","sociological","demography",
               "population","labor","labour","education","social science",
               "social policy","public economics","inequality","development"}
def relevance_score(title: str, source: str = "") -> int:
    """Lexical triage with a subject-domain gate; never substitute for reading."""
    norm = key(title)
    words = set(norm.split())
    strong = sum(1 for phrase in STRONG_PHRASES if phrase in norm)
    economic = len(words & ECON_WORDS)
    family = len(words & FAMILY_WORDS)
    family_specific = bool(words & {"intergenerational","multigenerational","parental","parent",
        "parents","family","families","child","children","sibling","siblings",
        "stepfamily","stepfamilies","grandparents","grandparent","bequest","bequests","inheritance"})
    if strong == 0 and (economic < 1 or not family_specific):
        return 0
    negative = len(words & NEGATIVE_WORDS)
    if negative and not (strong >= 1 and economic >= 2):
        return 0
    venue = key(source)
    venue_bonus = 2 if any(v in venue.split() for v in VENUE_TERMS) else 0
    return strong*5 + min(economic,4)*2 + min(family,4)*2 + venue_bonus - negative*4

def normalize_for_public(row: sqlite3.Row) -> dict:
    authors = json.loads(row["authors_json"])
    score = relevance_score(row["title"],row["source_name"])
    return {
        "id": f"{row['provider']}:{row['provider_id']}",
        "title": row["title"],
        "authors": authors[:12],
        "year": row["year"],
        "source": row["source_name"],
        "doi": row["doi"],
        "url": row["url"],
        "provider": row["provider"],
        "match_type": row["match_type"],
        "possible_work_id": row["possible_work_id"],
        "review_status": row["status"],
        "score": score,
        "evidence_level": "metadata_only",
    }

def export_discovery(db: sqlite3.Connection, outdir: Path, max_public: int = 400, min_score: int = 4) -> dict:
    if not 1 <= max_public <= 5000:
        raise ValueError("max_public out of range")
    outdir.mkdir(parents=True, exist_ok=True)
    rows = db.execute("SELECT * FROM candidates ORDER BY id").fetchall()
    records = [normalize_for_public(r) for r in rows]
    # Persist all normalized candidate metadata, not just the public preview.
    with (outdir/"all-candidates.jsonl").open("w",encoding="utf-8") as archive:
        for row in rows:
            item=json.loads(row["payload_json"])
            item["review_status"]=row["status"]
            item["match_type"]=row["match_type"]
            item["possible_work_id"]=row["possible_work_id"]
            archive.write(json.dumps(item,ensure_ascii=False,sort_keys=True)+"\n")
    # Never show an unreviewed record as if it were a curated paper.
    # Exact matches to already curated papers are already represented on /papers/.
    exclusions_path=ROOT/"registry"/"discovery_exclusions.json"
    excluded_dois=set()
    if exclusions_path.exists():
        exclusions=json.loads(exclusions_path.read_text(encoding="utf-8"))
        if exclusions.get("schema_version")!=1:
            raise ValueError("Unsupported discovery exclusion list")
        excluded_dois={r["doi"] for r in exclusions.get("records",[])}
    eligible = [r for r in records if r["score"] >= min_score
                and r["match_type"] != "exact" and r["doi"] not in excluded_dois]
    eligible.sort(key=lambda r: (-r["score"], -(r["year"] or 0), r["title"].casefold()))
    # Collapse only exact DOI and exact normalized title+first-author+year
    # in the PREVIEW, never in the underlying review database.
    distinct=[]
    seen_dois=set()
    seen_title_author_year=set()
    for rec in eligible:
        doi=rec["doi"]
        authors=rec["authors"]
        title_identity=(key(rec["title"]),key(authors[0]) if authors else "",rec["year"])
        if (doi and doi in seen_dois) or (authors and title_identity in seen_title_author_year):
            continue
        distinct.append(rec)
        if doi:
            seen_dois.add(doi)
        if authors:
            seen_title_author_year.add(title_identity)
    selected = distinct[:max_public]
    (outdir/"discovery-index.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (outdir/"review-queue.csv").open("w", newline="", encoding="utf-8") as handle:
        columns=["id","title","authors","year","source","doi","url","provider","score","match_type","possible_work_id","review_status"]
        writer=csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for r in sorted(records,key=lambda x:(-x["score"],x["title"].casefold())):
            item={k:r.get(k) for k in columns}
            item["authors"]=", ".join(r["authors"])
            for k,v in item.items():
                if isinstance(v,str) and v.lstrip().startswith(("=","+","-","@")):
                    item[k]="'"+v
            writer.writerow(item)
    return {"total_candidate_rows":len(records),"eligible_after_title_exclusions":len(eligible),
            "title_only_exclusions":len(excluded_dois),
            "after_exact_preview_dedup":len(distinct),
            "metadata_only_public_records":len(selected),"min_score":min_score,
            "max_public":max_public,"by_provider":{
                provider:sum(1 for r in records if r["provider"]==provider)
                for provider in ("crossref","openalex")},
            "review_queue":str(outdir/"review-queue.csv")}

def run(db, jobs: list[dict], per_query: int, pause: float) -> list[dict]:
    reports=[]
    for i,job in enumerate(jobs):
        provider=job["provider"]
        if provider=="crossref":
            stream=iter_crossref(job["query"],job["from_date"],job["to_date"],
                                 max_records=per_query,query_mode="title")
        else:
            stream=iter_openalex(job["query"],job["from_date"],job["to_date"],
                                 max_records=per_query)
        fetched=queued=0
        failure=None
        db.execute("INSERT INTO ingestion_runs(provider,query,from_date,to_date) VALUES(?,?,?,?)",
                   (provider,job["query"],job["from_date"],job["to_date"]))
        run_id=db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        db.commit()
        try:
            for record in stream:
                fetched+=1
                try:
                    was_new,_=enqueue(db,record)
                    queued+=int(was_new)
                except (ValueError,sqlite3.IntegrityError):
                    # Malformed provider records are not grounds to abort the batch.
                    continue
        except Exception as exc:
            # Continue other queries/providers, but report failures rather than claiming success.
            failure=f"{type(exc).__name__}: {exc}"
        finally:
            db.execute("UPDATE ingestion_runs SET fetched=?,queued=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
                       (fetched,queued,run_id))
            db.commit()
        result={"query_id":job["id"],"provider":provider,"period":job["from_date"][:4]+"–"+job["to_date"][:4],"fetched_normalized":fetched,
                "new_candidates":queued,"error":failure}
        reports.append(result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
        if pause and i<len(jobs)-1:
            time.sleep(pause)
    return reports

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="Bounded dynasty_ historical import; no automatic editorial approval")
    p.add_argument("--db",type=Path,default=ROOT/"data"/"dynasty-v03.sqlite")
    p.add_argument("--plan",type=Path,default=PLAN)
    p.add_argument("--output-dir",type=Path,default=ROOT/"data"/"v03-export")
    p.add_argument("--provider",choices=["crossref","openalex","all"],default="crossref")
    p.add_argument("--max-jobs",type=int,default=54)
    p.add_argument("--per-query",type=int,default=90)
    p.add_argument("--max-public",type=int,default=400)
    p.add_argument("--min-score",type=int,default=8)
    p.add_argument("--from-date",default="2000-01-01")
    p.add_argument("--to-date",default=date.today().isoformat())
    p.add_argument("--pause",type=float,default=0.6)
    p.add_argument("--execute",action="store_true",help="Contact the external APIs; default is dry run")
    a=p.parse_args(argv)
    if not 1<=a.max_jobs<=108 or not 1<=a.per_query<=100 or not 0<=a.pause<=30:
        p.error("Limits: 1..108 jobs, 1..100 records per query, pause 0..30 seconds")
    date.fromisoformat(a.from_date);date.fromisoformat(a.to_date)
    if a.from_date>a.to_date:
        p.error("Start date is after end date")
    plan=json.loads(a.plan.read_text(encoding="utf-8"))
    # Sample all eras; a single 2000–2026 Crossref query heavily overrepresents early years.
    periods=[("2000-01-01","2009-12-31"),("2010-01-01","2019-12-31"),
             ("2020-01-01",a.to_date)]
    jobs=[]
    for original in build_jobs(plan,provider=a.provider):
        for start,end in periods:
            start=max(start,a.from_date)
            end=min(end,a.to_date)
            if start<=end:
                jobs.append({**original,"from_date":start,"to_date":end})
    jobs=jobs[:a.max_jobs]
    print(json.dumps({"mode":"execute" if a.execute else "dry_run",
                      "jobs":len(jobs),"per_query":a.per_query,"provider":a.provider,
                      "maximum_raw_records":len(jobs)*a.per_query,
                      "no_automatic_editorial_approval":True},indent=2),flush=True)
    if not a.execute:
        return 0
    db=connect(a.db)
    try:
        initialize(db)
        seed_sources(db,ROOT/"registry"/"source_manifest.json")
        seed_curated(db,ROOT/"data"/"papers.json")
        reports=run(db,jobs,a.per_query,a.pause)
        export=export_discovery(db,a.output_dir,a.max_public,a.min_score)
        result={"schema_version":1,"run_date":date.today().isoformat(),
                "scope":"Metadata-only, unreviewed candidates; NOT editorial recommendations",
                "queries_attempted":len(reports),
                "queries_succeeded":sum(not r["error"] for r in reports),
                "queries_failed":sum(bool(r["error"]) for r in reports),
                "queries":reports,"database":stats(db),"discovery":export}
        (a.output_dir/"report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print("V03_SUMMARY "+json.dumps({k:v for k,v in result.items() if k not in ("queries","database")},ensure_ascii=False),flush=True)
        return 0 if result["queries_succeeded"] else 2
    finally:
        db.close()

if __name__=="__main__":
    raise SystemExit(main())
