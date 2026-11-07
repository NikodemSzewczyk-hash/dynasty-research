#!/usr/bin/env python3
"""23 verified-source pilot: bounded metadata-only ingestion and durable JSONL.

No paper is approved, summarized, downloaded or added to Hugo. Weekly runs
write to a review PR, never directly to the published site.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date,timedelta
import json
from pathlib import Path
import re
from dynasty_data.catalog import enqueue,seed_sources,seed_curated
from dynasty_data.providers import iter_crossref,iter_openalex
from dynasty_data.repec import iter_repec
from dynasty_data.schema import connect,initialize

ROOT=Path(__file__).resolve().parents[1]
VERIFICATION=ROOT/"registry"/"pilot23-verification.json"
MANIFEST=ROOT/"registry"/"source_manifest.json"
DEFAULT_SNAPSHOT=ROOT/"registry"/"pilot23-candidates.jsonl"
DEFAULT_STATE=ROOT/"registry"/"pilot23-state.json"
DEFAULT_REPORT=ROOT/"data"/"pilot23-report.json"
SMOKE_IDS={"journal:american-economic-review","researcher:jan-stuhler",
           "working_paper_series:iza-discussion-papers"}
ADAPTERS={"journal":"crossref_journal","researcher":"openalex_author",
          "working_paper_series":"repec_series_listing"}

def sources_for_pilot(manifest_path=MANIFEST,verification_path=VERIFICATION):
    manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    verification=json.loads(Path(verification_path).read_text(encoding="utf-8"))
    wanted={x["source_id"] for x in verification["evidence"]}
    if len(wanted)!=23:raise ValueError("Expected exactly 23 unique verified pilot IDs")
    sources=[s for s in manifest["sources"] if s["id"] in wanted]
    if len(sources)!=23:raise ValueError("Pilot sources missing from registry")
    for s in sources:
        r=s.get("retrieval") or {}
        ids=s.get("identifiers") or {}
        if not r.get("enabled") or r.get("adapter")!=ADAPTERS[s["kind"]] or not r.get("evidence_url"):
            raise ValueError("Source not verified/enabled: "+s["id"])
        key={"journal":"issn","researcher":"openalex_author_id",
             "working_paper_series":"repec_series_handle"}[s["kind"]]
        if not ids.get(key):raise ValueError("Missing external ID: "+s["id"])
    return sources

def read_snapshot(path):
    rows={}
    if not Path(path).exists():return rows
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():continue
            r=json.loads(line)
            if r.get("review_status","pending")!="pending":
                raise ValueError("Refusing to rebuild reviewed candidates without audit database")
            key=(r["provider"],r["provider_id"])
            if key in rows:raise ValueError("Duplicate provider identity in snapshot")
            rows[key]=r
    return rows

def read_state(path):
    if not Path(path).exists():return {"schema_version":1,"sources":{}}
    state=json.loads(Path(path).read_text(encoding="utf-8"))
    if state.get("schema_version")!=1:raise ValueError("Unsupported checkpoint version")
    return state

def merge_candidate(records,record,source_id,today):
    if not record.get("title") or not record.get("provider_id"):return False
    key=(record["provider"],record["provider_id"])
    existing=records.get(key)
    if existing:
        ids=set(existing.get("pilot_source_ids",[]))
        ids.add(source_id)
        existing["pilot_source_ids"]=sorted(ids)
        return False
    item=dict(record)
    item["pilot_source_ids"]=[source_id]
    item["pilot_first_seen"]=today
    item["review_status"]="pending"
    item["evidence_level"]="metadata_only"
    records[key]=item
    return True

def records_for_source(source,start,end,cap):
    adapter=source["retrieval"]["adapter"]
    ids=source["identifiers"]
    if adapter=="crossref_journal":
        stream=iter_crossref("",start,end,cap,journal_issn=ids["issn"])
        for rec in stream:
            if rec["kind"]=="journal_article":
                yield rec
    elif adapter=="openalex_author":
        yield from iter_openalex("",start,end,cap,author_id=ids["openalex_author_id"])
    elif adapter=="repec_series_listing":
        stream=iter_repec(ids["repec_series_handle"],source["name"],cap)
        for rec in stream:
            if rec["year"] is None or int(start[:4])<=rec["year"]<=int(end[:4]):
                yield rec
    else:
        raise ValueError("Unknown adapter: "+str(adapter))

def _write_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    tmp.replace(path)

def _write_snapshot(path,records):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8") as f:
        for k in sorted(records):
            f.write(json.dumps(records[k],sort_keys=True,ensure_ascii=False)+"\n")
    tmp.replace(path)

def run(sources,records,state,start,end,cap,today,collector=records_for_source,strict=True):
    if not 1<=cap<=500:raise ValueError("Per-source cap must be 1..500")
    report={"date":today,"start_date":start,"end_date":end,
            "source_count":len(sources),"sources_succeeded":0,"sources_failed":0,
            "fetched":0,"new_candidates":0,"errors":[],"per_source":[],
            "publication_status":"unreviewed_metadata_only"}
    # Do not mutate persistent state on a partial failed run.
    newrecords={k:dict(v) for k,v in records.items()}
    newstate=json.loads(json.dumps(state))
    for s in sources:
        sid=s["id"]
        result={"source_id":sid,"adapter":s["retrieval"]["adapter"],"fetched":0,"new":0}
        try:
            for record in collector(s,start,end,cap):
                result["fetched"]+=1
                if merge_candidate(newrecords,record,sid,today):result["new"]+=1
            report["sources_succeeded"]+=1
            result["possibly_truncated"]=result["fetched"]>=cap
            # A saturated cap must not advance the checkpoint: data may be missing.
            if not result["possibly_truncated"]:
                newstate["sources"][sid]={"last_successful_end":end,"last_run":today}
        except Exception as e:
            report["sources_failed"]+=1
            result["error"]=str(e)[:220]
            report["errors"].append({"source_id":sid,"error":result["error"]})
        report["fetched"]+=result["fetched"]
        report["new_candidates"]+=result["new"]
        report["per_source"].append(result)
    report["candidate_total"]=len(newrecords)
    doi_counts=Counter(x["doi"] for x in newrecords.values() if x.get("doi"))
    report["cross_provider_duplicate_dois"]=sum(1 for n in doi_counts.values() if n>1)
    report["sources_at_cap"]=sum(x.get("possibly_truncated",False) for x in report["per_source"])
    if strict and report["sources_failed"]:
        raise RuntimeError("Source failures; no snapshot or checkpoint written: "+
                           json.dumps(report["errors"],ensure_ascii=False))
    return newrecords,newstate,report

def main(argv=None):
    p=argparse.ArgumentParser(description="23-source pilot, metadata only")
    p.add_argument("--mode",choices=["smoke","weekly","backfill"],default="smoke")
    p.add_argument("--max-per-source",type=int,default=3)
    p.add_argument("--from-date")
    p.add_argument("--to-date")
    p.add_argument("--snapshot",type=Path,default=DEFAULT_SNAPSHOT)
    p.add_argument("--state",type=Path,default=DEFAULT_STATE)
    p.add_argument("--report",type=Path,default=DEFAULT_REPORT)
    p.add_argument("--db",type=Path,default=ROOT/"data"/"pilot23.sqlite")
    args=p.parse_args(argv)
    today=date.today()
    end=args.to_date or today.isoformat()
    if args.from_date:
        start=args.from_date
    elif args.mode=="backfill":
        start="2000-01-01"
    elif args.mode=="smoke":
        start=(today-timedelta(days=730)).isoformat()
    else:
        start=(today-timedelta(days=45)).isoformat()
    if date.fromisoformat(start)>date.fromisoformat(end):
        p.error("from-date must not be after to-date")
    sources=sources_for_pilot()
    if args.mode=="smoke":
        sources=[s for s in sources if s["id"] in SMOKE_IDS]
    records=read_snapshot(args.snapshot)
    state=read_state(args.state)
    # For weekly runs, catch up from prior successful checkpoint with overlap.
    if args.mode=="weekly" and not args.from_date:
        checkpoints=[date.fromisoformat(state["sources"][s["id"]]["last_successful_end"])
                     for s in sources if s["id"] in state["sources"]]
        if checkpoints:
            start=min(start,(min(checkpoints)-timedelta(days=45)).isoformat())
    updated,checkpoint,report=run(sources,records,state,start,end,args.max_per_source,today.isoformat())
    db=connect(args.db)
    try:
        initialize(db)
        seed_sources(db,MANIFEST)
        seed_curated(db,ROOT/"data"/"papers.json")
        for record in updated.values():enqueue(db,record)
        report["sqlite_candidate_rows"]=db.execute("SELECT count(*) FROM candidates").fetchone()[0]
    finally:
        db.close()
    _write_snapshot(args.snapshot,updated)
    _write_json(args.state,checkpoint)
    _write_json(args.report,report)
    print(json.dumps(report,indent=2,ensure_ascii=False))
    if report["sources_at_cap"]:
        print("WARNING: One or more sources reached their cap; increase it or narrow dates before claiming completeness.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
