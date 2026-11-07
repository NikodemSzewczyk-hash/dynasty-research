#!/usr/bin/env python3
"""Rebuild a local unreviewed SQLite queue from version-controlled JSONL metadata.

Review decisions are NOT reconstructed; never use this for replacing a database
with completed editorial decisions. Back up the original SQLite database.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from dynasty_data.schema import connect,initialize
from dynasty_data.catalog import seed_sources,seed_curated,enqueue,stats

ROOT=Path(__file__).resolve().parents[1]

def load_candidates(db, path: Path, max_rows: int=100000) -> dict:
    if not 1<=max_rows<=1000000:
        raise ValueError("max_rows out of range")
    read=inserted=0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            read+=1
            if read>max_rows:
                raise ValueError("Too many rows")
            record=json.loads(line)
            if record.get("review_status","pending")!="pending":
                raise ValueError("Reviewed records require the original audit database, not this rebuild")
            new,_=enqueue(db,record)
            inserted+=int(new)
    return {"read":read,"new":inserted}

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="Rebuild unreviewed dynasty_ metadata candidates")
    p.add_argument("--input",type=Path,default=ROOT/"registry"/"candidates-v03.jsonl")
    p.add_argument("--db",type=Path,default=ROOT/"data"/"dynasty.sqlite")
    a=p.parse_args(argv)
    db=connect(a.db)
    try:
        initialize(db)
        seed_sources(db,ROOT/"registry"/"source_manifest.json")
        seed_curated(db,ROOT/"data"/"papers.json")
        report=load_candidates(db,a.input)
        print(json.dumps({**report,"database":stats(db)},indent=2))
        return 0
    finally:
        db.close()

if __name__=="__main__":
    raise SystemExit(main())
