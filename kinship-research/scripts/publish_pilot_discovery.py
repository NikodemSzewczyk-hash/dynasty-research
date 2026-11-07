#!/usr/bin/env python3
"""Publish a clearly labelled discovery preview from verified-source metadata.

Only title-keyword screening is used; no abstract/full-text claims are made.
This exporter does not change the 12 curated paper records or the source
registry. It is deliberately deterministic for PR review and audit.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"registry/source_manifest.json"
PAPERS=ROOT/"data/papers.json"
SNAPSHOT=ROOT/"registry/pilot23-candidates.jsonl"
INDEX=ROOT/"static/data/discovery-index.json"
CATALOG=ROOT/"data/source-catalog.json"
REPORT=ROOT/"data/discovery-pilot-report.json"

# High-precision, title-only screening. These categories are discovery
# hypotheses, not human-assessed relevance or paper-level findings.
RULES={
    "Intergenerational mobility":[
        r"\binter[\s-]?generational\b",r"\bmulti[\s-]?generational\b",
        r"\bsocial mobility\b",r"\beconomic mobility\b",r"\bincome mobility\b",
        r"\beducational mobility\b",r"\bwealth mobility\b",
        r"\bparental (income|education|occupation|background|status)\b",
        r"\bintergenerational (persistence|transmission|inequality)\b",
    ],
    "Wealth and inheritance":[
        r"\binherit(?:ance|ed|ing)\b",r"\bbequest",r"\binter[\s-]?vivos\b",
        r"\bwealth transfers?\b",r"\bwealth transmission\b",
        r"\bparental wealth\b",r"\bfamily wealth\b",r"\bdynastic wealth\b",
        r"\bwealth inequality\b",r"\bwealth concentration\b",
        r"\bgift tax\b",r"\bestate tax\b",r"\binheritance tax\b",
        r"\bintergenerational gifts?\b",r"\bparental gifts?\b",
        r"\bwealth (shock|transfer|mobility)\b",
    ],
    "Family structure":[
        r"\bstepfamil",r"\bstep[\s-]?(?:parent|father|mother|child|sibling)",
        r"\bdivorc",r"\bparental separ",r"\bsingle[\s-]?parent",
        r"\bbirth order\b",r"\bsibling",r"\bfamily structure\b",
        r"\bfamily background\b",r"\bparental support\b",
        r"\bparent[\s-]?child (?:transfer|relationship|investment)",
        r"\bparental investment",r"\bchildhood family\b",
    ],
    "Place and opportunity":[
        r"\bneighbou?rhood effects?\b",r"\bneighbou?rhood mobility\b",
        r"\bchildhood exposure\b",r"\bgeography of (?:mobility|opportunity)\b",
        r"\bplace[- ]based (?:opportunity|mobility)\b",
        r"\bschool quality and (?:inequality|mobility)\b",
        r"\bsocial capital and (?:mobility|opportunity)\b",
    ],
    "Institutions and policy":[
        r"\bchild benefits? and (?:inequality|mobility)\b",
        r"\bfamily policy and (?:inequality|mobility)\b",
        r"\bredistribution and (?:mobility|inequality)\b",
        r"\bintergenerational redistribution\b",
    ],
    "Research designs":[
        r"\blottery (?:winnings?|wins?|wealth|shocks?)\b",
        r"\bparental (?:wealth|income) shocks?\b",
        r"\bwealth shocks? and (?:children|families|households)\b",
    ],
}
COMPILED={name:[re.compile(p,re.I) for p in pats] for name,pats in RULES.items()}
ORDER=list(RULES)

def classify(title):
    text=" ".join(str(title or "").split())
    matches=[topic for topic,patterns in COMPILED.items() if any(p.search(text) for p in patterns)]
    return matches

def valid_https(url):
    if not isinstance(url,str):return None
    try:
        u=urlsplit(url)
        return url if u.scheme=="https" and u.netloc and not u.username and not u.password else None
    except ValueError:return None

def doi_key(value):
    if not value:return ""
    v=str(value).strip().lower()
    for prefix in ("https://doi.org/","http://doi.org/","doi:"):
        if v.startswith(prefix):v=v[len(prefix):]
    return v if v.startswith("10.") and "/" in v else ""

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def catalog_from_manifest(manifest):
    out={"journals":[],"repositories":[],"researchers":[]}
    kinds={"journal":"journals","working_paper_series":"repositories","researcher":"researchers"}
    for s in manifest["sources"]:
        r=s.get("retrieval") or {}
        active=bool(r.get("enabled") and r.get("evidence_url"))
        out[kinds[s["kind"]]].append({
            "id":s["id"],"name":s["name"],"tier":s["tier"],"area":s.get("area",""),
            "active":active,"provider":r.get("adapter","") if active else "",
            "evidence_url":valid_https(r.get("evidence_url")) if active else None,
        })
    for rows in out.values():rows.sort(key=lambda x:("ABC".find(x["tier"]),x["name"].casefold()))
    all_sources=sum(len(v) for v in out.values())
    active=sum(s["active"] for v in out.values() for s in v)
    out["summary"]={"registered":all_sources,"verified_active":active,"planned":all_sources-active,
                    "scope":"Metadata collection configured; not a claim of comprehensive coverage"}
    return out

def base_records(existing):
    # Retain the historical V0.3 preview, not a previous export's pilot or
    # curated records. This keeps reruns deterministic as the snapshot grows.
    result=[]
    for r in existing:
        if r.get("collection") not in (None,"historical"):continue
        if r.get("review_status")!="pending" or r.get("evidence_level")!="metadata_only":continue
        if not isinstance(r.get("title"),str) or not r["title"].strip():continue
        x=dict(r)
        x["collection"]="historical"
        x["topics"]=r.get("topics") or classify(r["title"])
        x["source_ids"]=r.get("source_ids") or []
        result.append(x)
    return result

def pilot_records(snapshot,manifest):
    names={s["id"]:s["name"] for s in manifest["sources"]}
    active={s["id"] for s in manifest["sources"] if (s.get("retrieval") or {}).get("enabled")}
    rows=[];screened=0;total=0;unrecognized=0
    for line in Path(snapshot).read_text(encoding="utf-8").splitlines():
        if not line.strip():continue
        total+=1
        r=json.loads(line)
        if r.get("review_status")!="pending" or r.get("evidence_level")!="metadata_only":
            raise ValueError("Pilot snapshot contains non-pending or non-metadata record")
        ids=sorted(set(r.get("pilot_source_ids") or []))
        if not ids or any(s not in active for s in ids):
            unrecognized+=1;continue
        title=r.get("title","")
        topics=classify(title)
        if not topics:continue
        if not isinstance(r.get("authors"),list):continue
        url=valid_https(r.get("url"))
        if not url:continue
        yr=r.get("year")
        if not isinstance(yr,int) or not 1900<=yr<=date.today().year+1:continue
        screened+=1
        source=r.get("source_name") or names[ids[0]]
        rows.append({
            "id":str(r["provider"])+":"+str(r["provider_id"]),
            "title":title,"authors":r["authors"][:25],"year":yr,
            "source":source,"doi":doi_key(r.get("doi")) or None,"url":url,
            "provider":r["provider"],"review_status":"pending",
            "evidence_level":"metadata_only","collection":"pilot23",
            "topics":topics,"source_ids":ids,
            "score":12+len(topics)*2,"match_type":"none",
        })
    return rows,{"raw_candidates":total,"title_screened_candidates":screened,
                 "unrecognized_source_rows":unrecognized}

def curated_records(papers):
    result=[]
    for p in papers:
        result.append({
            "id":"curated:"+p["id"],"title":p["title"],
            "authors":p["authors"],"year":p["year"],
            "source":p["source"],"doi":doi_key(p.get("doi")) or None,
            "url":valid_https(p["paper_url"]),"curated_url":"/papers/"+p["id"]+"/",
            "provider":"curated","review_status":"curated",
            "evidence_level":"editorial_summary","collection":"curated",
            "topics":p.get("topics") or classify(p["title"]),
            "source_ids":[],"score":100,"match_type":"curated",
        })
    return result

def combine(records):
    # DOI identity only: do not conflate similar titles, working papers and
    # journal versions without a verified identifier.
    bykey={}
    rank={"historical":1,"pilot23":2,"curated":3}
    for r in records:
        doi=doi_key(r.get("doi"))
        key="doi:"+doi if doi else "record:"+str(r["id"])
        if key not in bykey:
            bykey[key]=dict(r);continue
        prev=bykey[key]
        merged_sources=sorted(set(prev.get("source_ids",[]))|set(r.get("source_ids",[])))
        merged_topics=list(dict.fromkeys(prev.get("topics",[])+r.get("topics",[])))
        if rank[r["collection"]]>rank[prev["collection"]]:
            bykey[key]=dict(r)
        bykey[key]["source_ids"]=merged_sources
        bykey[key]["topics"]=merged_topics
    return sorted(bykey.values(),key=lambda r:(
        0 if r["review_status"]=="curated" else 1,
        -(r.get("score") or 0),-(r.get("year") or 0),r["title"].casefold()))

def build(manifest,papers,existing,snapshot):
    cat=catalog_from_manifest(manifest)
    pilot,stats=pilot_records(snapshot,manifest)
    legacy=base_records(existing)
    curated=curated_records(papers)
    merged=combine(legacy+pilot+curated)
    counts=Counter(r["collection"] for r in merged)
    stats.update({
        "schema_version":1,"generated_on":date.today().isoformat(),
        "total_displayed":len(merged),"historical_displayed":counts["historical"],
        "pilot_displayed":counts["pilot23"],"curated_displayed":counts["curated"],
        "pilot_source_count":cat["summary"]["verified_active"],
        "scope":"Title-screened bibliographic candidates; not editorial endorsements",
        "deduplication":"Exact DOI only; distinct versions without DOI may remain",
    })
    return cat,merged,stats

def write_json(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",type=Path,default=SNAPSHOT)
    p.add_argument("--index",type=Path,default=INDEX)
    p.add_argument("--catalog",type=Path,default=CATALOG)
    p.add_argument("--report",type=Path,default=REPORT)
    args=p.parse_args(argv)
    if not args.snapshot.exists():p.error("Pilot snapshot missing: run ingestion first")
    manifest=load_json(MANIFEST);papers=load_json(PAPERS)
    existing=load_json(args.index) if args.index.exists() else []
    cat,index,report=build(manifest,papers,existing,args.snapshot)
    if report["pilot_displayed"]==0:
        p.error("No title-screened pilot records; refusing to publish empty pilot")
    if report["curated_displayed"]!=len(papers):
        p.error("Curated DOI collision or missing record; investigate before publishing")
    write_json(args.index,index)
    write_json(args.catalog,cat)
    write_json(args.report,report)
    print(json.dumps(report,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
