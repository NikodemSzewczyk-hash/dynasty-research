#!/usr/bin/env python3
"""Correct stored years that contradict a known DOI issue-year convention (currently IFS).

Background: IFS re-deposited its working papers at Crossref in 2025-2026, so imports that
used Crossref's "published" date show 1995-2017 papers as new. See docs/metadata-audit.md.

Dry run by default. With --write, only the affected JSONL lines are rewritten, so diffs
stay reviewable. After repairing static/data/discovery-index.json, rerun
scripts/publish_pilot_discovery.py so ordering and counts are regenerated.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from dynasty_data.identity import canonical_doi
from dynasty_data.providers import doi_convention_year

ROOT=Path(__file__).resolve().parents[1]
JSONL=[ROOT/"registry/candidates-v03.jsonl"]+sorted((ROOT/"registry/snapshot").glob("*.jsonl"))
INDEX=ROOT/"static/data/discovery-index.json"

def _fix(rec: dict):
    doi=canonical_doi(rec.get("doi"))
    year=doi_convention_year(doi)
    if year and rec.get("year")!=year:
        change=(doi,rec.get("year"),year)
        rec["year"]=year
        return change
    return None

def repair_jsonl(path: Path, write: bool=False) -> list[tuple]:
    changes,out=[],[]
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            out.append(line); continue
        rec=json.loads(line)
        change=_fix(rec)
        if change:
            changes.append(change)
            sort_keys=list(rec)==sorted(rec)
            out.append(json.dumps(rec,ensure_ascii=False,sort_keys=sort_keys))
        else:
            out.append(line)
    if write and changes:
        path.write_text("\n".join(out)+"\n",encoding="utf-8")
    return changes

def repair_json_list(rows: list[dict]) -> list[tuple]:
    return [c for c in (_fix(r) for r in rows) if c]

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--write",action="store_true",help="apply changes (default: dry run)")
    args=p.parse_args(argv)
    report={}
    for path in JSONL:
        report[str(path.relative_to(ROOT))]=repair_jsonl(path,args.write)
    rows=json.loads(INDEX.read_text(encoding="utf-8"))
    report[str(INDEX.relative_to(ROOT))]=repair_json_list(rows)
    if args.write and report[str(INDEX.relative_to(ROOT))]:
        INDEX.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for name,changes in report.items():
        print(f"{name}: {len(changes)} year(s) {'corrected' if args.write else 'to correct'}")
        for doi,old,new in changes:
            print(f"  {doi}: {old} -> {new}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
