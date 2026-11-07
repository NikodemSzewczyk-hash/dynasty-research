#!/usr/bin/env python3
"""Import a bounded, title-relevant subset of NBER's official public-use metadata.

Source: https://www.nber.org/research/data/nber-working-papers-and-chapters-metadata
This downloads only the official ref.tsv bibliographic file, NEVER paper PDFs.
"""
from __future__ import annotations
import argparse
import csv
import json
import tempfile
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

from dynasty_data.nber import normalize_nber
from dynasty_data.schema import connect,initialize
from dynasty_data.catalog import enqueue,stats
from v03_bootstrap import relevance_score,export_discovery

ROOT=Path(__file__).resolve().parents[1]
NBER_URL="https://data.nber.org/nber_paper_chapter_metadata/tsv/ref.tsv"
MAX_BYTES=30*1024*1024

def fetch_nber_metadata(url: str = NBER_URL) -> bytes:
    if url != NBER_URL:
        raise ValueError("Only the official NBER metadata endpoint is allowed")
    req=urllib.request.Request(url,headers={"User-Agent":"dynasty-research/0.3 (noncommercial research metadata; https://dynastyecon.netlify.app/)"})
    with urllib.request.urlopen(req,timeout=90) as response:
        content=response.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES:
        raise ValueError("NBER metadata exceeds safety size cap")
    if not content.startswith(b"paper\t"):
        raise ValueError("Unexpected NBER metadata header")
    return content

def choose_nber_rows(content: bytes, max_per_era: int=600, min_score: int=8) -> tuple[list[dict],dict]:
    """Balance selection across eras and prioritize title-level family/inequality evidence."""
    if not 1<=max_per_era<=2000:
        raise ValueError("max_per_era must be 1..2000")
    text=content.decode("utf-8-sig",errors="replace").splitlines()
    reader=csv.DictReader(text,delimiter="\t")
    if not reader.fieldnames or not {"paper","author","title","issue_date"}.issubset(reader.fieldnames):
        raise ValueError("Unexpected NBER TSV columns")
    eras={(2000,2009):[],(2010,2019):[],(2020,2100):[]}
    scanned=0
    for row in reader:
        scanned+=1
        if scanned>100000:
            raise ValueError("Unexpectedly large NBER metadata file")
        rec=normalize_nber(row)
        if not rec or not rec["year"] or rec["year"]<2000 or rec["year"]>date.today().year:
            continue
        score=relevance_score(rec["title"],"NBER Working Papers")
        if score<min_score:
            continue
        for (lo,hi),bucket in eras.items():
            if lo<=rec["year"]<=hi:
                bucket.append((score,rec))
                break
    selected=[]
    by_era={}
    for (lo,hi),bucket in eras.items():
        bucket.sort(key=lambda item:(-item[0],-(item[1]["year"] or 0),item[1]["title"]))
        picks=[r for _,r in bucket[:max_per_era]]
        selected.extend(picks)
        by_era[f"{lo}-{hi}"]={"eligible":len(bucket),"selected":len(picks)}
    return selected,{"scanned_rows":scanned,"by_era":by_era,"selected_total":len(selected)}

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="Official NBER metadata import; all records remain unreviewed")
    p.add_argument("--db",type=Path,default=ROOT/"data"/"v03.sqlite")
    p.add_argument("--output-dir",type=Path,default=ROOT/"data"/"v03-export")
    p.add_argument("--max-per-era",type=int,default=600)
    p.add_argument("--min-score",type=int,default=8)
    p.add_argument("--max-public",type=int,default=400)
    p.add_argument("--file",type=Path,help="Optional local official ref.tsv (offline testing)")
    a=p.parse_args(argv)
    content=a.file.read_bytes() if a.file else fetch_nber_metadata()
    selected,summary=choose_nber_rows(content,a.max_per_era,a.min_score)
    db=connect(a.db)
    try:
        initialize(db)
        new=0
        for rec in selected:
            try:
                inserted,_=enqueue(db,rec)
                new+=int(inserted)
            except ValueError:
                continue
        a.output_dir.mkdir(parents=True,exist_ok=True)
        report_file=a.output_dir/"report.json"
        report=json.loads(report_file.read_text(encoding="utf-8")) if report_file.exists() else {"schema_version":1}
        report["nber"]={**summary,"new_candidates":new,
                        "source":"NBER official public-use ref.tsv; metadata only"}
        report["discovery"]=export_discovery(db,a.output_dir,a.max_public,a.min_score)
        report["database"]=stats(db)
        report_file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print("NBER_SUMMARY "+json.dumps(report["nber"],ensure_ascii=False),flush=True)
        print("COMBINED_CANDIDATES "+str(report["discovery"]["total_candidate_rows"]),flush=True)
        return 0
    finally:
        db.close()

if __name__=="__main__":
    raise SystemExit(main())
