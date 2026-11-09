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
import unicodedata
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"registry/source_manifest.json"
PAPERS=ROOT/"data/papers.json"
SNAPSHOT=ROOT/"registry/snapshot"
INDEX=ROOT/"static/data/discovery-index.json"
CATALOG=ROOT/"data/source-catalog.json"
REPORT=ROOT/"data/discovery-pilot-report.json"
STATE=ROOT/"registry/pilot23-state.json"
SEEDLIST=ROOT/"registry/seed-list.jsonl"

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

ACCESS_LABELS={"crossref_journal":"Crossref, journal ISSN","crossref_prefix":"Crossref, publisher DOI prefix",
               "openalex_author":"OpenAlex, author ID","repec_redif":"RePEc ReDIF archive"}

def coverage_for(source_id,adapter,state):
    c=((state or {}).get("sources",{}).get(source_id) or {}).get("coverage")
    if not c or not isinstance(c.get("available"),int):return None
    return {"read":c["read"],"available":c["available"],"since":c["start_date"][:4],
            "measured_on":c.get("measured_on"),"incomplete":not c.get("complete",False),
            "access":ACCESS_LABELS.get(adapter,adapter)}

def catalog_from_manifest(manifest,state=None):
    out={"journals":[],"repositories":[],"researchers":[]}
    kinds={"journal":"journals","working_paper_series":"repositories","researcher":"researchers"}
    for s in manifest["sources"]:
        r=s.get("retrieval") or {}
        active=bool(r.get("enabled") and r.get("evidence_url"))
        out[kinds[s["kind"]]].append({
            "id":s["id"],"name":s["name"],"tier":s["tier"],"area":s.get("area",""),
            "active":active,"provider":r.get("adapter","") if active else "",
            "evidence_url":valid_https(r.get("evidence_url")) if active else None,
            "coverage":coverage_for(s["id"],r.get("adapter"),state) if active else None,
            "coverage_note":r.get("coverage_note") if active else None,
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

NONPAPER=re.compile(
    r"^\s*(?:replication (?:data|code)|replication package|data and code for|"
    r"replication files? for|supplementary (?:data|materials?)|"
    r"corrigendum|erratum|correction to:|dataset for:)\b",re.I)

def repair_encoding(value):
    """Repair obvious UTF-8/Latin-1 mojibake in public RePEc titles only."""
    text=str(value or "")
    if any(mark in text for mark in ("â€™","â€œ","â€","Ã©","Ã¼")):
        try:return text.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError,UnicodeDecodeError):return text
    return text

def snapshot_lines(snapshot):
    """Lines of a single snapshot JSONL file or of every shard in a snapshot directory."""
    path=Path(snapshot)
    files=sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    for f in files:
        yield from f.read_text(encoding="utf-8").splitlines()

def pilot_records(snapshot,manifest):
    names={s["id"]:s["name"] for s in manifest["sources"]}
    active={s["id"] for s in manifest["sources"] if (s.get("retrieval") or {}).get("enabled")}
    rows=[];screened=0;total=0;unrecognized=0
    for line in snapshot_lines(snapshot):
        if not line.strip():continue
        total+=1
        r=json.loads(line)
        if r.get("review_status")!="pending" or r.get("evidence_level")!="metadata_only":
            raise ValueError("Pilot snapshot contains non-pending or non-metadata record")
        if r.get("kind") not in ("journal_article","working_paper"):
            continue  # Do not present book chapters, datasets or other records as papers.
        ids=sorted(set(r.get("pilot_source_ids") or []))
        if not ids or any(s not in active for s in ids):
            unrecognized+=1;continue
        title=repair_encoding(r.get("title",""))
        if NONPAPER.search(title):continue
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
            "title":title,"authors":[repair_encoding(a) for a in r["authors"][:25]],"year":yr,
            "source":source,"doi":doi_key(r.get("doi")) or None,"url":url,
            "provider":r["provider"],"review_status":"pending",
            "evidence_level":"metadata_only","collection":"pilot23",
            "topics":topics,"source_ids":ids,
            "score":12+len(topics)*2,"match_type":"none","kind":r.get("kind",""),
        })
    return rows,{"raw_candidates":total,"title_screened_candidates":screened,
                 "unrecognized_source_rows":unrecognized}

def seed_records(path):
    """Unreviewed candidates from the hand-compiled seed list (scripts/export_seed_list.py).

    Only scope-coded `core` rows with an https link and a plausible year are shown. Scope
    coding is screening, not review: rows stay pending/metadata_only like pilot rows.
    """
    rows=[]
    if not path or not Path(path).exists():return rows
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():continue
        r=json.loads(line)
        if r.get("review_status")!="pending" or r.get("evidence_level")!="metadata_only":
            raise ValueError("Seed list contains non-pending or non-metadata record")
        if r.get("scope_tier")!="core":continue
        url=valid_https(r.get("url"))
        if not url:continue
        yr=r.get("year")
        if not isinstance(yr,int) or not 1900<=yr<=date.today().year+1:continue
        topics=[t for t in (r.get("topics") or []) if isinstance(t,str)]
        if not topics or not isinstance(r.get("authors"),list):continue
        rows.append({
            "id":str(r["id"]),"title":str(r["title"]),"authors":r["authors"][:25],"year":yr,
            "source":r.get("source") or "","doi":doi_key(r.get("doi")) or None,"url":url,
            "provider":r.get("provider") or "seedlist","review_status":"pending",
            "evidence_level":"metadata_only","collection":"seedlist",
            "topics":topics,"source_ids":[],
            "score":14+len(topics)*2,"match_type":"none","kind":r.get("kind",""),
        })
    return rows

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

def _text_key(text):
    ascii_text=unicodedata.normalize("NFKD",str(text or ""))
    ascii_text="".join(c for c in ascii_text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+"," ",ascii_text.casefold()).strip()

def _surname_key(name):
    """Surname for "Last, First" (RePEc) and "First Last" (Crossref/OpenAlex) forms."""
    name=str(name or "")
    part=name.split(",",1)[0] if "," in name else name
    tokens=_text_key(part).split()
    # Final surname token in both orders: "First Last" cannot be split reliably otherwise.
    return tokens[-1] if tokens else ""

def _version(row):
    return {"doi":doi_key(row.get("doi")) or None,
            "url":row.get("url"),"source":row.get("source",""),
            "provider":row.get("provider","")}

def _priority(row):
    if row.get("collection")=="curated":return (4,0)
    if row.get("collection")=="historical":return (0,0)
    venue=(row.get("source") or "").casefold()
    is_journal=("journal" in venue or "review of" in venue or "econometrica" in venue)
    not_journal=any(t in venue for t in ("ssrn","arxiv","working paper","nber","cesifo"))
    return (3 if is_journal and not not_journal else 2, row.get("year") or 0)

def _merge_rows(old,new,possible):
    a,b=dict(old),dict(new)
    chosen=a if _priority(a)>=_priority(b) else b
    out=dict(chosen)
    out["source_ids"]=sorted(set(a.get("source_ids",[]))|set(b.get("source_ids",[])))
    out["topics"]=list(dict.fromkeys(a.get("topics",[])+b.get("topics",[])))
    versions=(a.get("versions") or [_version(a)])+(b.get("versions") or [_version(b)])
    dedup={}
    for v in versions:
        k=doi_key(v.get("doi")) or v.get("url")
        if k:dedup[k]=v
    out["versions"]=list(dedup.values())
    out["version_count"]=len(out["versions"])
    if possible or a.get("match_type")=="possible" or b.get("match_type")=="possible":
        out["match_type"]="possible"
    return out

def combine(records):
    # Two passes: exact DOI, then exact normalized title AND first-author surname.
    # The second pass is labelled as *possible* versions, not verified
    # equivalence. Do not fuzzy-match titles or people.
    bydoi={}
    for row in records:
        r=dict(row)
        doi=doi_key(r.get("doi"))
        key="doi:"+doi if doi else "record:"+str(r["id"])
        if key in bydoi:bydoi[key]=_merge_rows(bydoi[key],r,False)
        else:bydoi[key]=r
    bytitle={}
    for r in bydoi.values():
        title=_text_key(r.get("title"))
        authors=r.get("authors") or []
        first=_surname_key(authors[0]) if authors else ""
        key="title:"+title+":"+first if title and first else "record:"+str(r["id"])
        if key in bytitle:bytitle[key]=_merge_rows(bytitle[key],r,True)
        else:bytitle[key]=r
    return sorted(bytitle.values(),key=lambda r:(
        0 if r["review_status"]=="curated" else 1,
        -(r.get("score") or 0),-(r.get("year") or 0),r["title"].casefold()))

def build(manifest,papers,existing,snapshot,state=None,seed_list=None):
    cat=catalog_from_manifest(manifest,state)
    pilot,stats=pilot_records(snapshot,manifest)
    legacy=base_records(existing)
    seed=seed_records(seed_list)
    curated=curated_records(papers)
    merged=combine(legacy+pilot+seed+curated)
    counts=Counter(r["collection"] for r in merged)
    stats.update({
        "schema_version":1,"generated_on":date.today().isoformat(),
        "total_displayed":len(merged),"historical_displayed":counts["historical"],
        "pilot_displayed":counts["pilot23"],"curated_displayed":counts["curated"],
        "seed_candidates":len(seed),"seed_displayed":counts["seedlist"],
        "pilot_source_count":cat["summary"]["verified_active"],
        "scope":"Title-screened bibliographic candidates; not editorial endorsements",
        "deduplication":"Exact DOI, then exact normalized title + first-author surname (latter labelled possible versions)",
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
    p.add_argument("--seed-list",type=Path,default=SEEDLIST,
                   help="Scope-coded seed candidates (scripts/export_seed_list.py); skipped if missing")
    args=p.parse_args(argv)
    if not args.snapshot.exists():p.error("Pilot snapshot missing: run ingestion first")
    manifest=load_json(MANIFEST);papers=load_json(PAPERS)
    existing=load_json(args.index) if args.index.exists() else []
    state=load_json(STATE) if STATE.exists() else None
    cat,index,report=build(manifest,papers,existing,args.snapshot,state,args.seed_list)
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
