#!/usr/bin/env python3
"""Import NBER public bibliographic metadata into the UNREVIEWED dynasty_ queue."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from dynasty_data.schema import connect,initialize
from dynasty_data.catalog import enqueue
from dynasty_data.nber import iter_nber_tsv

ROOT=Path(__file__).resolve().parents[1]

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="Bounded NBER official ref.tsv metadata importer (no automatic publication)")
    p.add_argument("--file",required=True,type=Path,help="Downloaded NBER ref.tsv")
    p.add_argument("--db",type=Path,default=ROOT/"data"/"dynasty.sqlite")
    p.add_argument("--from-year",type=int,default=2000)
    p.add_argument("--to-year",type=int,default=2100)
    p.add_argument("--max-records",type=int,default=500)
    p.add_argument("--max-rows",type=int,default=100000)
    a=p.parse_args(argv)
    db=connect(a.db)
    try:
        initialize(db)
        cursor=db.execute("""INSERT INTO ingestion_runs(provider,query,from_date,to_date)
                             VALUES ('nber',?,?,?)""",
                          (a.file.name,str(a.from_year),str(a.to_year)))
        run_id=cursor.lastrowid;db.commit()
        fetched=queued=0
        try:
            for record in iter_nber_tsv(a.file,a.from_year,a.to_year,a.max_records,a.max_rows):
                fetched+=1
                new,_=enqueue(db,record)
                queued+=int(new)
        finally:
            db.execute("UPDATE ingestion_runs SET fetched=?,queued=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
                       (fetched,queued,run_id))
            db.commit()
        print(json.dumps({"provider":"nber","fetched":fetched,"new_in_queue":queued,
                          "note":"Metadata only. All new records are UNREVIEWED."},indent=2))
        return 0
    except (ValueError,OSError) as e:
        print(f"Error: {e}",file=sys.stderr)
        return 2
    finally:
        db.close()

if __name__=="__main__":
    raise SystemExit(main())
