#!/usr/bin/env python3
"""Run a small, auditable historical metadata search plan. DRY RUN by default.

Every discovered paper goes to the existing UNREVIEWED SQLite queue. Nothing is
automatically added to the Hugo website.
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
import time
from datetime import date
from pathlib import Path
from dynasty import main as dynasty_cli
from dynasty_data.schema import connect

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_PLAN=ROOT/"registry"/"discovery_plan.json"

def build_jobs(plan: dict, provider: str = "all", selected: set[str] | None = None) -> list[dict]:
    if plan.get("schema_version")!=1:
        raise ValueError("Unsupported discovery plan version")
    date.fromisoformat(plan.get("from_date","2000-01-01"))
    ids=set()
    jobs=[]
    for row in plan.get("queries",[]):
        ident=row.get("id","")
        phrase=row.get("query","")
        if not re.fullmatch(r"[a-z0-9-]{3,80}",ident) or ident in ids:
            raise ValueError("Query IDs must be unique lowercase slugs")
        if not isinstance(phrase,str) or not 3<=len(phrase.strip())<=200:
            raise ValueError("Search terms must be 3..200 characters")
        ids.add(ident)
        for p in row.get("providers",[]):
            if p not in ("openalex","crossref"):
                raise ValueError("Unknown provider in discovery plan")
            if provider!="all" and p!=provider:
                continue
            if selected is not None and ident not in selected:
                continue
            jobs.append({"id":ident,"theme":row.get("theme",""),"provider":p,"query":phrase.strip()})
    if selected is not None and not selected.issubset(ids):
        raise ValueError("Some requested --query-id values do not exist")
    return jobs

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="Manual bounded historical discovery plan for dynasty_")
    p.add_argument("--plan",type=Path,default=DEFAULT_PLAN)
    p.add_argument("--db",type=Path,default=ROOT/"data"/"dynasty.sqlite")
    p.add_argument("--provider",choices=["openalex","crossref","all"],default="all")
    p.add_argument("--query-id",action="append",default=[],help="Repeat to select a subset of plan queries")
    p.add_argument("--from-date",default=None)
    p.add_argument("--to-date",default=date.today().isoformat())
    p.add_argument("--max-jobs",type=int,default=4,help="Hard limit on number of jobs per invocation")
    p.add_argument("--max-records-per-job",type=int,default=50,help="Raw API record cap for each job")
    p.add_argument("--pause",type=float,default=1.0,help="Polite delay in seconds between jobs")
    p.add_argument("--force",action="store_true",help="Repeat completed matching historical queries")
    p.add_argument("--execute",action="store_true",help="Actually contact APIs; default prints plan only")
    a=p.parse_args(argv)
    if not 1<=a.max_jobs<=50 or not 1<=a.max_records_per_job<=1000 or not 0<=a.pause<=30:
        p.error("Limits: jobs 1..50, records per job 1..1000, pause 0..30 seconds")
    plan=json.loads(a.plan.read_text(encoding="utf-8"))
    start=a.from_date or plan.get("from_date","2000-01-01")
    date.fromisoformat(start);date.fromisoformat(a.to_date)
    if start>a.to_date:
        p.error("from-date after to-date")
    selected=set(a.query_id) if a.query_id else None
    jobs=build_jobs(plan,a.provider,selected)
    done=set()
    if a.db.exists():
        db=connect(a.db)
        try:
            for row in db.execute("""SELECT provider,query,from_date,to_date FROM ingestion_runs
                    WHERE finished_at IS NOT NULL AND fetched>0""").fetchall():
                done.add((row["provider"],row["query"],row["from_date"],row["to_date"]))
        except sqlite3.OperationalError:
            pass  # Database exists but schema was not yet seeded.
        finally:
            db.close()
    pending=[]
    skipped=[]
    for job in jobs:
        token=(job["provider"],job["query"],start,a.to_date)
        if token in done and not a.force:
            skipped.append(job["id"]+" / "+job["provider"])
        else:
            pending.append(job)
    pending=pending[:a.max_jobs]
    report={"mode":"execute" if a.execute else "dry_run","from_date":start,"to_date":a.to_date,
            "max_records_per_job":a.max_records_per_job,"jobs":pending,
            "already_completed_skipped":skipped,
            "warning":"All data remains unreviewed; nothing is auto-published."}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not a.execute or not pending:
        return 0
    result=dynasty_cli(["--db",str(a.db),"seed"])
    if result:
        return result
    for index,job in enumerate(pending):
        print(f"\nDISCOVERY {index+1}/{len(pending)}: {job['id']} / {job['provider']}",flush=True)
        args=["--db",str(a.db),"ingest",job["provider"],"--query",job["query"],
              "--from-date",start,"--to-date",a.to_date,"--max-records",str(a.max_records_per_job)]
        result=dynasty_cli(args)
        if result:
            print("A query failed; correct the problem and re-run (previous rows are idempotent).",flush=True)
            return result
        if index+1<len(pending) and a.pause:
            time.sleep(a.pause)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
