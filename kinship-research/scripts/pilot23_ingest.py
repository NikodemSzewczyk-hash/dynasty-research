#!/usr/bin/env python3
"""Verified-source ingestion: bounded, metadata-only, with per-source completeness checks.

(The file keeps its historical "pilot23" name; the verified set is defined by
registry/pilot23-verification.json and is no longer fixed at 23 sources.)

Access paths (see docs/source-access.md):
  crossref_journal  Crossref works by verified journal ISSN, cursor-paged
  crossref_prefix   Crossref works by verified DOI prefix plus DOI pattern (NBER, IFS)
  openalex_author   OpenAlex works by verified author ID, cursor-paged
  repec_redif       RePEc ReDIF files from the publisher archive or a RePEc mirror (CEPR, IZA)

No paper is approved, summarized, downloaded or added to Hugo. Weekly runs write to a
review PR, never directly to the published site.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date,timedelta
import inspect
import json
from pathlib import Path
import re
from dynasty_data.catalog import enqueue,seed_sources,seed_curated
from dynasty_data.providers import iter_crossref,iter_openalex,MAX_BOUNDED_RECORDS
from dynasty_data.redif import iter_redif_series
from dynasty_data.schema import connect,initialize

ROOT=Path(__file__).resolve().parents[1]
VERIFICATION=ROOT/"registry"/"pilot23-verification.json"
MANIFEST=ROOT/"registry"/"source_manifest.json"
DEFAULT_SNAPSHOT=ROOT/"registry"/"snapshot"
LEGACY_SNAPSHOT=ROOT/"registry"/"pilot23-candidates.jsonl"
DEFAULT_STATE=ROOT/"registry"/"pilot23-state.json"
DEFAULT_REPORT=ROOT/"data"/"pilot23-report.json"
BACKFILL_START="1990-01-01"
SMOKE_IDS={"journal:american-economic-review","researcher:jan-stuhler",
           "working_paper_series:nber-working-papers",
           "working_paper_series:iza-discussion-papers",
           "working_paper_series:cepr-discussion-papers"}
ADAPTER_IDENTIFIER={"crossref_journal":"issn","openalex_author":"openalex_author_id",
                    "crossref_prefix":"crossref_prefix","repec_redif":"redif_url"}
KIND_ADAPTERS={"journal":{"crossref_journal"},"researcher":{"openalex_author"},
               "working_paper_series":{"crossref_prefix","repec_redif"}}

def sources_for_pilot(manifest_path=MANIFEST,verification_path=VERIFICATION):
    """Enabled sources whose identifiers are recorded in the verification evidence."""
    manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    verification=json.loads(Path(verification_path).read_text(encoding="utf-8"))
    wanted={x["source_id"] for x in verification["evidence"]}
    if len(wanted)!=len(verification["evidence"]) or len(wanted)!=verification.get("source_count"):
        raise ValueError("Verification evidence must list each source once and match source_count")
    sources=[s for s in manifest["sources"] if s["id"] in wanted]
    if len(sources)!=len(wanted):raise ValueError("Verified sources missing from registry")
    for s in sources:
        r=s.get("retrieval") or {}
        ids=s.get("identifiers") or {}
        adapter=r.get("adapter")
        if not r.get("enabled") or adapter not in KIND_ADAPTERS.get(s["kind"],()) or not r.get("evidence_url"):
            raise ValueError("Source not verified/enabled: "+s["id"])
        if not ids.get(ADAPTER_IDENTIFIER[adapter]):raise ValueError("Missing external ID: "+s["id"])
        if adapter=="crossref_prefix" and not ids.get("doi_pattern"):
            raise ValueError("DOI-prefix source needs a doi_pattern: "+s["id"])
        if adapter=="repec_redif" and not ids.get("repec_series_handle"):
            raise ValueError("ReDIF source needs its RePEc series handle: "+s["id"])
    return sources

# ------------------------------------------------------------------ snapshot storage

def shard_name(source_id: str) -> str:
    """Windows-safe file name for a source shard."""
    return re.sub(r"[^a-z0-9_-]+","_",source_id.lower().replace(":","__"))+".jsonl"

def _read_jsonl(path,rows):
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():continue
            r=json.loads(line)
            if r.get("review_status","pending")!="pending":
                raise ValueError("Refusing to rebuild reviewed candidates without audit database")
            key=(r["provider"],r["provider_id"])
            if key in rows:raise ValueError("Duplicate provider identity in snapshot")
            rows[key]=r

def read_snapshot(path):
    """Read a single JSONL file or a directory of per-source shards."""
    rows={}
    path=Path(path)
    if path.is_dir():
        for shard in sorted(path.glob("*.jsonl")):_read_jsonl(shard,rows)
    elif path.exists():
        _read_jsonl(path,rows)
    return rows

def _write_jsonl(path,records,keys):
    tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8") as f:
        for k in keys:
            f.write(json.dumps(records[k],sort_keys=True,ensure_ascii=False)+"\n")
    tmp.replace(path)

def _write_snapshot(path,records):
    """A path ending in .jsonl gets one file; otherwise one shard per primary source.

    The primary source is the alphabetically first source that returned the record, so
    shard placement is deterministic. Shards for sources with no records are removed.
    """
    path=Path(path)
    if path.suffix==".jsonl":
        path.parent.mkdir(parents=True,exist_ok=True)
        _write_jsonl(path,records,sorted(records))
        return
    path.mkdir(parents=True,exist_ok=True)
    shards={}
    for k,r in records.items():
        shards.setdefault(shard_name(sorted(r["pilot_source_ids"])[0]),[]).append(k)
    for name,keys in shards.items():
        _write_jsonl(path/name,records,sorted(keys))
    for stale in path.glob("*.jsonl"):
        if stale.name not in shards:stale.unlink()

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

# ------------------------------------------------------------------ collection

def records_for_source(source,start,end,cap,stats=None):
    adapter=source["retrieval"]["adapter"]
    ids=source["identifiers"]
    stats=stats if stats is not None else {}
    if adapter=="crossref_journal":
        for rec in iter_crossref("",start,end,cap,journal_issn=ids["issn"],stats=stats):
            if rec["kind"]=="journal_article":
                yield rec
    elif adapter=="crossref_prefix":
        pattern=re.compile(ids["doi_pattern"],re.I)
        for rec in iter_crossref("",start,end,cap,prefix=ids["crossref_prefix"],stats=stats):
            if rec.get("doi") and pattern.search(rec["doi"]):
                rec["kind"]="working_paper"
                rec["source_name"]=rec.get("source_name") or source["name"]
                yield rec
    elif adapter=="openalex_author":
        yield from iter_openalex("",start,end,cap,author_id=ids["openalex_author_id"],stats=stats)
    elif adapter=="repec_redif":
        yield from iter_redif_series(ids["redif_url"],ids["repec_series_handle"],source["name"],
                                     int(start[:4]),int(end[:4]),cap,stats=stats)
    else:
        raise ValueError("Unknown adapter: "+str(adapter))

def _accepts_stats(fn) -> bool:
    try:
        return "stats" in inspect.signature(fn).parameters
    except (TypeError,ValueError):
        return False

def run(sources,records,state,start,end,cap,today,collector=records_for_source,strict=True):
    if not 1<=cap<=MAX_BOUNDED_RECORDS:raise ValueError(f"Per-source cap must be 1..{MAX_BOUNDED_RECORDS}")
    report={"date":today,"start_date":start,"end_date":end,
            "source_count":len(sources),"sources_succeeded":0,"sources_failed":0,
            "fetched":0,"new_candidates":0,"errors":[],"per_source":[],
            "publication_status":"unreviewed_metadata_only"}
    # Do not mutate persistent state on a partial failed run.
    newrecords={k:dict(v) for k,v in records.items()}
    newstate=json.loads(json.dumps(state))
    with_stats=_accepts_stats(collector)
    for s in sources:
        sid=s["id"]
        stats={}
        result={"source_id":sid,"adapter":s["retrieval"]["adapter"],"fetched":0,"new":0}
        try:
            stream=collector(s,start,end,cap,stats=stats) if with_stats else collector(s,start,end,cap)
            for record in stream:
                result["fetched"]+=1
                if merge_candidate(newrecords,record,sid,today):result["new"]+=1
            report["sources_succeeded"]+=1
            raw=stats.get("raw",result["fetched"])
            available=stats.get("available")
            result["provider_records_read"]=raw
            if available is not None:
                result["provider_records_available"]=available
                result["coverage"]=round(raw/available,4) if available else 1.0
                result["possibly_truncated"]=raw<available
            else:
                result["possibly_truncated"]=result["fetched"]>=cap
            if "files" in stats:result["files_read"]=stats["files"]
            entry=newstate["sources"].setdefault(sid,{})
            # Keep coverage for the widest window measured (the backfill); a weekly
            # 45-day run must not replace it with a narrow-window figure.
            previous=entry.get("coverage") or {}
            prev_start=previous.get("start_date","9999-12-31")
            # Same window: never let an incomplete (capped) read replace a complete one.
            wider=start<prev_start
            same_not_worse=start==prev_start and (not result["possibly_truncated"] or not previous.get("complete"))
            if available is not None and (wider or same_not_worse or not previous):
                entry["coverage"]={"start_date":start,"end_date":end,"measured_on":today,
                                   "read":raw,"available":available,"complete":not result["possibly_truncated"]}
            # An incomplete read must not advance the checkpoint: data may be missing.
            if not result["possibly_truncated"]:
                entry.update(last_successful_end=end,last_run=today)
            if not entry:
                del newstate["sources"][sid]
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

def _write_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    tmp.replace(path)

def rebuild_review_db(path,records):
    """Rebuild the disposable SQLite review queue from the snapshot (fast, unsafe pragmas)."""
    db=connect(path)
    try:
        db.execute("PRAGMA synchronous=OFF")
        db.execute("PRAGMA journal_mode=MEMORY")
        initialize(db)
        seed_sources(db,MANIFEST)
        seed_curated(db,ROOT/"data"/"papers.json")
        for record in records.values():enqueue(db,record)
        return db.execute("SELECT count(*) FROM candidates").fetchone()[0]
    finally:
        db.close()

def main(argv=None):
    p=argparse.ArgumentParser(description="Verified-source ingestion, metadata only")
    p.add_argument("--mode",choices=["smoke","weekly","backfill"],default="smoke")
    p.add_argument("--max-per-source",type=int,default=3)
    p.add_argument("--from-date")
    p.add_argument("--to-date")
    p.add_argument("--source",action="append",help="limit to these source IDs (repeatable)")
    p.add_argument("--snapshot",type=Path,default=DEFAULT_SNAPSHOT,
                   help="directory of per-source shards, or a single .jsonl file")
    p.add_argument("--state",type=Path,default=DEFAULT_STATE)
    p.add_argument("--report",type=Path,default=DEFAULT_REPORT)
    p.add_argument("--db",type=Path,default=ROOT/"data"/"pilot23.sqlite")
    p.add_argument("--no-db",action="store_true",help="skip rebuilding the SQLite review queue")
    args=p.parse_args(argv)
    today=date.today()
    end=args.to_date or today.isoformat()
    if args.from_date:
        start=args.from_date
    elif args.mode=="backfill":
        start=BACKFILL_START
    elif args.mode=="smoke":
        start=(today-timedelta(days=730)).isoformat()
    else:
        start=(today-timedelta(days=45)).isoformat()
    if date.fromisoformat(start)>date.fromisoformat(end):
        p.error("from-date must not be after to-date")
    sources=sources_for_pilot()
    if args.mode=="smoke":
        sources=[s for s in sources if s["id"] in SMOKE_IDS]
    if args.source:
        unknown=set(args.source)-{s["id"] for s in sources}
        if unknown:p.error("Unknown or unverified source: "+", ".join(sorted(unknown)))
        sources=[s for s in sources if s["id"] in set(args.source)]
    snapshot=args.snapshot
    records=read_snapshot(snapshot)
    if not records and snapshot==DEFAULT_SNAPSHOT and LEGACY_SNAPSHOT.exists():
        records=read_snapshot(LEGACY_SNAPSHOT)  # one-time migration to shards
    state=read_state(args.state)
    # For weekly runs, catch up from prior successful checkpoint with overlap.
    if args.mode=="weekly" and not args.from_date:
        checkpoints=[date.fromisoformat(state["sources"][s["id"]]["last_successful_end"])
                     for s in sources if "last_successful_end" in state["sources"].get(s["id"],{})]
        if checkpoints:
            start=min(start,(min(checkpoints)-timedelta(days=45)).isoformat())
    updated,checkpoint,report=run(sources,records,state,start,end,args.max_per_source,today.isoformat())
    if not args.no_db:
        report["sqlite_candidate_rows"]=rebuild_review_db(args.db,updated)
    _write_snapshot(snapshot,updated)
    _write_json(args.state,checkpoint)
    _write_json(args.report,report)
    print(json.dumps({k:v for k,v in report.items() if k!="per_source"},indent=2,ensure_ascii=False))
    for r in report["per_source"]:
        cov=f"{r['coverage']:.1%}" if "coverage" in r else "n/a"
        print(f"  {r['source_id']:55} read={r.get('provider_records_read','-'):>6} "
              f"available={r.get('provider_records_available','?'):>6} coverage={cov:>7} kept={r['fetched']}")
    if report["sources_at_cap"]:
        print("WARNING: One or more sources were not fully read; increase the cap or narrow dates before claiming completeness.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
