#!/usr/bin/env python3
"""Reproducible, stratified manual quality audit of dynasty_ imported metadata."""
from __future__ import annotations
import argparse
import csv
import json
import random
from pathlib import Path
from v03_bootstrap import relevance_score

ROOT=Path(__file__).resolve().parents[1]
FIELDS=["title","authors","year","source","doi","url","provider","relevance_score",
        "stratum","metadata_verified","topically_relevant","duplicate_version","reviewer_notes"]

def sample(records: list[dict], n: int=100, seed: int=20261107) -> list[dict]:
    if not 1<=n<=1000:
        raise ValueError("n must be 1..1000")
    rng=random.Random(seed)
    pools={"high":[],"medium":[],"low":[]}
    for r in records:
        score=relevance_score(r.get("title",""),r.get("source_name",""))
        bucket="high" if score>=10 else ("medium" if score>=5 else "low")
        pools[bucket].append((r,score))
    for pool in pools.values():
        pool.sort(key=lambda x:(x[0].get("provider",""),x[0].get("provider_id","")))
        rng.shuffle(pool)
    targets={"high":round(n*0.4),"medium":round(n*0.3),"low":n-round(n*0.4)-round(n*0.3)}
    selected=[]
    for bucket,target in targets.items():
        selected.extend((r,score,bucket) for r,score in pools[bucket][:target])
        pools[bucket]=pools[bucket][target:]
    remaining=n-len(selected)
    if remaining>0:
        extra=[(r,score,bucket) for bucket,pool in pools.items() for r,score in pool]
        rng.shuffle(extra)
        selected.extend(extra[:remaining])
    return [{"title":r.get("title",""),"authors":", ".join(r.get("authors",[])),
             "year":r.get("year"),"source":r.get("source_name",""),"doi":r.get("doi"),
             "url":r.get("url"),"provider":r.get("provider"),"relevance_score":score,
             "stratum":bucket,"metadata_verified":"","topically_relevant":"",
             "duplicate_version":"","reviewer_notes":""}
            for r,score,bucket in selected]

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="Generate a 100-paper stratified metadata review sample")
    p.add_argument("--input",type=Path,default=ROOT/"registry"/"candidates-v03.jsonl")
    p.add_argument("--output",type=Path,default=ROOT/"registry"/"review-sample-v03.csv")
    p.add_argument("--n",type=int,default=100)
    p.add_argument("--seed",type=int,default=20261107)
    args=p.parse_args(argv)
    with args.input.open(encoding="utf-8") as f:
        records=[json.loads(line) for line in f if line.strip()]
    selected=sample(records,args.n,args.seed)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        for row in selected:
            # Prevent spreadsheet formulas in untrusted provider metadata.
            for k,v in row.items():
                if isinstance(v,str) and v.lstrip().startswith(("=","+","-","@")):
                    row[k]="'"+v
            writer.writerow(row)
    print(json.dumps({"total_corpus":len(records),"audit_sample":len(selected),
                      "output":str(args.output),"note":"All reviewer decision fields are blank."}))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
