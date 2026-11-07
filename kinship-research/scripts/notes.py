#!/usr/bin/env python3
"""Create a blank, clearly labelled evidence note; validate notes before publishing."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from dynasty_data.schema import connect
from dynasty_data.notes import draft_note,load_and_validate

ROOT=Path(__file__).resolve().parents[1]

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="dynasty_ source-grounded research notes")
    sub=p.add_subparsers(dest="command",required=True)
    init=sub.add_parser("init",help="Create an EMPTY draft note for a known curated work")
    init.add_argument("work_id")
    init.add_argument("--db",type=Path,default=ROOT/"data"/"dynasty.sqlite")
    init.add_argument("--output",type=Path,required=True)
    val=sub.add_parser("validate",help="Validate note schema and evidence links")
    val.add_argument("paths",type=Path,nargs="+")
    args=p.parse_args(argv)
    if args.command=="init":
        if args.output.exists():
            print("Refusing to overwrite an existing note",file=sys.stderr)
            return 2
        if not args.db.exists():
            print("Database missing; run dynasty.py seed first",file=sys.stderr)
            return 2
        db=connect(args.db)
        try:
            work=db.execute("SELECT id,title FROM works WHERE id=?",(args.work_id,)).fetchone()
            if not work:
                print("Unknown curated work ID",file=sys.stderr)
                return 2
            versions=[dict(r) for r in db.execute("SELECT doi,url,kind FROM versions WHERE work_id=?",(args.work_id,))]
            note=draft_note(dict(work),versions)
        finally:
            db.close()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(note,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print("Created draft template only; NO full-text review has been performed:",args.output)
        return 0
    failures=0
    for path in args.paths:
        errors=load_and_validate(path)
        if errors:
            failures+=1
            print(path,":", "; ".join(errors),file=sys.stderr)
        else:
            print(path,": valid schema (NOT a guarantee that claims are true)")
    return 2 if failures else 0

if __name__=="__main__":
    raise SystemExit(main())
