#!/usr/bin/env python3
"""dynasty_ metadata CLI. Safe by default: imports are queued, never published."""
from __future__ import annotations
import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path
from dynasty_data.catalog import (
    seed_sources,seed_curated,enqueue,queue,decide,stats,export_hugo
)
from dynasty_data.providers import iter_openalex,iter_crossref,lookup_source
from dynasty_data.resolution import suggest_identifiers
from dynasty_data.schema import connect,initialize

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DB=ROOT/"data"/"dynasty.sqlite"

def say(value):
    print(json.dumps(value,indent=2,ensure_ascii=False))

def set_source(db, source_id: str, key: str, value: str, verified_by: str) -> None:
    row=db.execute("SELECT * FROM sources WHERE id=?",(source_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown source ID; run 'seed' first")
    expected={"journal":("issn",r"\d{4}-[\dXx]{4}"),
              "researcher":("openalex_author_id",r"A\d{4,12}")}
    if row["kind"] not in expected:
        raise ValueError("Working-paper series need a separately implemented, verified feed")
    name,pattern=expected[row["kind"]]
    if key!=name or not re.fullmatch(pattern,value):
        raise ValueError(f"Expected {name} matching {pattern}")
    if not verified_by.strip():
        raise ValueError("A verifier name is required to enable a source")
    ids=json.loads(row["identifiers_json"])
    retrieval=json.loads(row["retrieval_json"])
    ids[key]=value
    retrieval.update({"enabled":True,"verification":"manual","verified_by":verified_by.strip(),
                     "verified_on":date.today().isoformat()})
    with db:
        db.execute("UPDATE sources SET identifiers_json=?,retrieval_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                   (json.dumps(ids,sort_keys=True),json.dumps(retrieval,sort_keys=True),source_id))

def parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="dynasty_ V0.2 research-data workflow")
    p.add_argument("--db",type=Path,default=DEFAULT_DB,help="SQLite database (default: data/dynasty.sqlite)")
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("init",help="Initialize local SQLite database")
    sub.add_parser("seed",help="Import candidate source registry and 12 curated seed papers")
    sub.add_parser("stats",help="Inspect database counts")

    src=sub.add_parser("sources",help="List or configure source registry")
    ss=src.add_subparsers(dest="source_command",required=True)
    ls=ss.add_parser("list")
    ls.add_argument("--kind",choices=["journal","working_paper_series","researcher"])
    ls.add_argument("--limit",type=int,default=150)
    sv=ss.add_parser("verify",help="Enable a source after manually checking external ID")
    sv.add_argument("id");sv.add_argument("--key",required=True,choices=["issn","openalex_author_id"])
    sv.add_argument("--value",required=True);sv.add_argument("--verified-by",required=True)
    sj=ss.add_parser("suggest",help="Search possible external identifiers WITHOUT enabling them")
    sj.add_argument("id");sj.add_argument("--limit",type=int,default=5)
    sd=ss.add_parser("dump",help="Export current verified registry to a reviewable JSON manifest")
    sd.add_argument("--output",type=Path,required=True)

    imp=sub.add_parser("ingest",help="Bounded OpenAlex/Crossref metadata ingestion into review queue")
    imp.add_argument("provider",choices=["openalex","crossref"])
    imp.add_argument("--query",default="",help="Search keyword or bibliographic phrase")
    imp.add_argument("--source-id",help="Verified registry source, instead of or alongside keyword")
    imp.add_argument("--from-date",default="2000-01-01")
    imp.add_argument("--to-date",default=date.today().isoformat())
    imp.add_argument("--max-records",type=int,default=100,help="Fetch at most N candidate records (1..10000)")

    rev=sub.add_parser("review",help="Read and decide the editorial review queue")
    rv=rev.add_subparsers(dest="review_command",required=True)
    q=rv.add_parser("list");q.add_argument("--status",choices=["pending","accepted","rejected","deferred","all"],default="pending")
    q.add_argument("--limit",type=int,default=30)
    qcsv=rv.add_parser("export",help="Export candidate triage list to CSV; does not approve papers")
    qcsv.add_argument("--status",choices=["pending","accepted","rejected","deferred","all"],default="pending")
    qcsv.add_argument("--limit",type=int,default=1000)
    qcsv.add_argument("--output",type=Path,required=True)
    detail=rv.add_parser("show");detail.add_argument("id",type=int)
    for action in ("approve","reject","defer"):
        d=rv.add_parser(action)
        d.add_argument("id",type=int)
        d.add_argument("--reviewer",required=True)
        d.add_argument("--notes",default="")
        if action=="approve":
            d.add_argument("--takeaway",default="",help="Required for a new publication; human-authored")
            d.add_argument("--topics",default="",help="Comma-separated editorial topics")
            d.add_argument("--method",default="")
            d.add_argument("--description",default="")
            d.add_argument("--merge-into",help="Explicitly attach to existing work ID")
            d.add_argument("--force-new",action="store_true",help="Override a fuzzy possible-match warning")
    exp=sub.add_parser("export",help="Export published records as Hugo pages and search JSON")
    exp.add_argument("--site-root",type=Path,default=ROOT)
    return p

def main(argv=None) -> int:
    args=parser().parse_args(argv)
    db=connect(args.db)
    try:
        initialize(db)
        if args.command=="init":
            say({"db":str(args.db),"schema":"v1"})
        elif args.command=="seed":
            a=seed_sources(db,ROOT/"registry"/"source_manifest.json")
            b=seed_curated(db,ROOT/"data"/"papers.json")
            say({"sources_created":a,"papers_created":b,**stats(db)})
        elif args.command=="stats":
            say(stats(db))
        elif args.command=="sources":
            if args.source_command=="list":
                if not 1<=args.limit<=10000:
                    raise ValueError("--limit must be 1..10000")
                sql="SELECT id,kind,name,tier,identifiers_json,retrieval_json FROM sources"
                params=()
                if args.kind:
                    sql+=" WHERE kind=?";params=(args.kind,)
                sql+=" ORDER BY kind,tier,name LIMIT ?"
                rows=[dict(r) for r in db.execute(sql,params+(args.limit,))]
                for row in rows:
                    row["identifiers"]=json.loads(row.pop("identifiers_json"))
                    row["retrieval"]=json.loads(row.pop("retrieval_json"))
                say(rows)
            elif args.source_command=="verify":
                set_source(db,args.id,args.key,args.value,args.verified_by)
                say({"source_id":args.id,"retrieval_enabled":True,"verified_by":args.verified_by})
            elif args.source_command=="suggest":
                say(suggest_identifiers(db,args.id,args.limit))
            elif args.source_command=="dump":
                rows=db.execute("SELECT * FROM sources ORDER BY kind,id").fetchall()
                records=[]
                for row in rows:
                    records.append({"id":row["id"],"kind":row["kind"],"name":row["name"],"area":row["area"],
                                    "tier":row["tier"],"identifiers":json.loads(row["identifiers_json"]),
                                    "retrieval":json.loads(row["retrieval_json"]),"editorial_status":row["editorial_status"]})
                manifest={"schema_version":1,"generated_from":"SQLite editorial registry",
                          "notes":"Public, explicitly reviewed identifiers; local source IDs remain stable.",
                          "sources":records}
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
                say({"written":str(args.output),"sources":len(records)})
        elif args.command=="ingest":
            if not args.query and not args.source_id:
                raise ValueError("Provide --query or --source-id")
            opts=lookup_source(db,args.source_id,args.provider) if args.source_id else {}
            query=args.query.strip()
            db.execute("INSERT INTO ingestion_runs(provider,query,from_date,to_date) VALUES(?,?,?,?)",
                       (args.provider,args.source_id or query,args.from_date,args.to_date))
            run_id=db.execute("SELECT last_insert_rowid() n").fetchone()["n"];db.commit()
            if args.provider=="openalex":
                stream=iter_openalex(query,args.from_date,args.to_date,args.max_records,**opts)
            else:
                stream=iter_crossref(query,args.from_date,args.to_date,args.max_records,**opts)
            fetched=queued=0
            try:
                for record in stream:
                    fetched+=1
                    was_new,_=enqueue(db,record)
                    queued+=int(was_new)
            finally:
                db.execute("UPDATE ingestion_runs SET fetched=?,queued=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
                           (fetched,queued,run_id));db.commit()
            say({"provider":args.provider,"fetched":fetched,"new_in_queue":queued,"run_id":run_id,
                 "note":"All new candidates are unreviewed. Nothing was published."})
        elif args.command=="review":
            if args.review_command=="list":
                say(queue(db,args.status,args.limit))
            elif args.review_command=="export":
                if not 1<=args.limit<=10000:
                    raise ValueError("Queue export limit must be 1..10000")
                fields=["id","title","authors","year","source_name","provider","doi","match_type","possible_work_id","url","status"]
                sql="SELECT * FROM candidates"
                par=()
                if args.status!="all":
                    sql+=" WHERE status=?"
                    par=(args.status,)
                sql+=" ORDER BY id DESC LIMIT ?"
                rows=db.execute(sql,par+(args.limit,)).fetchall()
                args.output.parent.mkdir(parents=True,exist_ok=True)
                with args.output.open("w",encoding="utf-8",newline="") as output:
                    writer=csv.DictWriter(output,fieldnames=fields)
                    writer.writeheader()
                    for row in rows:
                        item={k:row[k] for k in fields if k not in ("authors",)}
                        item["authors"]=", ".join(json.loads(row["authors_json"]))
                        # Defang spreadsheet formulas from untrusted provider metadata.
                        for k,value in item.items():
                            if isinstance(value,str) and value.lstrip().startswith(("=","+","-","@")):
                                item[k]="'"+value
                        writer.writerow(item)
                say({"written":str(args.output),"rows":len(rows),"status":args.status})
            elif args.review_command=="show":
                row=db.execute("SELECT * FROM candidates WHERE id=?",(args.id,)).fetchone()
                if not row:
                    raise ValueError("Candidate not found")
                say(dict(row))
            else:
                topics=[x.strip() for x in getattr(args,"topics","").split(",") if x.strip()]
                work_id=decide(db,args.id,args.review_command,reviewer=args.reviewer,
                               takeaway=getattr(args,"takeaway",""),topics=topics,
                               method=getattr(args,"method",""),description=getattr(args,"description",""),
                               merge_into=getattr(args,"merge_into",None),force_new=getattr(args,"force_new",False),
                               notes=args.notes)
                say({"candidate":args.id,"decision":args.review_command,"work_id":work_id})
        elif args.command=="export":
            say(export_hugo(db,args.site_root))
        return 0
    except (ValueError,sqlite3.Error,RuntimeError) as exc:
        print(f"Error: {exc}",file=sys.stderr)
        return 2
    finally:
        db.close()

if __name__=="__main__":
    raise SystemExit(main())
