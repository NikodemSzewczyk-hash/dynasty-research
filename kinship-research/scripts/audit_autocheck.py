#!/usr/bin/env python3
"""Automated metadata pre-check for the stratified audit sample (docs/metadata-audit.md).

Two steps, so that network access and judgement are separated and the run is auditable:

  fetch  Download, for each sample DOI, the doi.org handle record, the Crossref work (the
         publisher's own deposit), the OpenAlex work, an OpenAlex same-title search, and
         the author lists of same-title hits. Raw JSON is cached under --cache (keep it
         outside data/, which Hugo parses). Metadata only; no landing pages or full text.
  check  Offline. Compare each row against the cache, write an evidence JSON, and with
         --write fill metadata_verified, duplicate_version and reviewer_notes.

topically_relevant is never touched: relevance is an editorial judgement. Rows that an
editor has already filled (notes without the auto-check tag) are refused unless --force.

Lessons built in (2026-11-07 run): OpenAlex publication_year mirrors Crossref "created",
so it is not an independent year check; re-deposited working papers carry a recent
Crossref "published" date; online-first articles correctly use the issue/print year.
On python.org macOS builds without root certificates, set SSL_CERT_FILE=/etc/ssl/cert.pem.

  python scripts/audit_autocheck.py fetch --cache /tmp/dynasty-audit-cache
  python scripts/audit_autocheck.py check --cache /tmp/dynasty-audit-cache --write
"""
from __future__ import annotations
import argparse, csv, html, json, re, time, unicodedata
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
SAMPLE=ROOT/"registry/review-sample-v03.csv"
EVIDENCE=ROOT/"registry/review-sample-v03-autocheck.json"
UA="dynasty-research/0.2 (+https://dynastyecon.netlify.app/; metadata audit; noncommercial)"
VERSION_RELATIONS=("is-preprint-of","has-preprint","is-version-of","has-version","is-identical-to","is-same-as")
NOT_VERSIONS=("book-review","erratum","peer-review","paratext","retraction")

def tag(day: str) -> str:
    return f"[auto-check {day} by Claude vs DOI registry, Crossref, OpenAlex; editor to confirm]"

# ---------------------------------------------------------------- fetch

def _get(url: str) -> dict:
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers={"User-Agent":UA,"Accept":"application/json"}),timeout=40) as r:
                return {"status":r.status,"body":json.loads(r.read().decode("utf-8"))}
        except HTTPError as e:
            if e.code in (429,500,502,503,504) and attempt<2:
                time.sleep(3*(attempt+1)); continue
            return {"status":e.code,"body":None}
        except (URLError,TimeoutError,json.JSONDecodeError) as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                raise SystemExit("TLS verification failed; set SSL_CERT_FILE (see module docstring)")
            if attempt<2:
                time.sleep(3); continue
            return {"status":None,"error":str(e),"body":None}

def cache_name(doi: str) -> str:
    return re.sub(r"[^a-z0-9]+","_",doi.lower()).strip("_")+".json"

def sample_doi(row: dict) -> str:
    return row["doi"].lstrip("'").strip().lower()

def fetch(cache: Path, sample: Path=SAMPLE, pause: float=0.3) -> None:
    cache.mkdir(parents=True,exist_ok=True)
    rows=list(csv.DictReader(sample.open(encoding="utf-8")))
    for i,row in enumerate(rows):
        doi=sample_doi(row); dest=cache/cache_name(doi)
        if dest.exists(): continue
        title=row["title"].lstrip("'")
        search=urlencode({"filter":"title.search:"+re.sub(r"[,:|]"," ",title)[:200],
                          "select":"id,doi,display_name,publication_year,type,primary_location","per-page":"10"})
        rec={"doi":doi,
             "handle":_get("https://doi.org/api/handles/"+quote(doi,safe="/")),
             "crossref":_get("https://api.crossref.org/works/"+quote(doi,safe="/")),
             "openalex":_get("https://api.openalex.org/works/doi:"+quote(doi,safe="/")+
                             "?select=id,doi,display_name,publication_year,type,authorships,primary_location"),
             "openalex_title_search":_get("https://api.openalex.org/works?"+search)}
        # Author lists for exact same-title hits, so a version needs a shared author.
        rec["same_title_authors"]={}
        for w in (rec["openalex_title_search"].get("body") or {}).get("results") or []:
            if fold(w.get("display_name"))==fold(title) and (w.get("doi") or "").lower().removeprefix("https://doi.org/")!=doi:
                wid=(w.get("id") or "").rsplit("/",1)[-1]
                body=_get(f"https://api.openalex.org/works/{wid}?select=id,authorships").get("body") or {}
                rec["same_title_authors"][w.get("id")]=[(a.get("author") or {}).get("display_name","") for a in body.get("authorships") or []]
                time.sleep(pause)
        dest.write_text(json.dumps(rec),encoding="utf-8")
        print(i,doi,*(rec[k]["status"] for k in ("handle","crossref","openalex","openalex_title_search")),flush=True)
        time.sleep(pause)

# ---------------------------------------------------------------- check

def fold(s) -> str:
    s=html.unescape(re.sub(r"<[^>]+>"," ",s or ""))
    s="".join(c for c in unicodedata.normalize("NFKD",s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+"," ",s.casefold()).strip()

def title_cmp(a: str, b: str) -> str:
    fa,fb=fold(a),fold(b)
    if not fb: return "missing"
    if fa==fb: return "match"
    if (fa.startswith(fb) or fb.startswith(fa)) and min(len(fa.split()),len(fb.split()))>=4: return "subtitle"
    return "differ"

def surname(name: str) -> str:
    parts=fold(name).split()
    return parts[-1] if parts else ""

def crossref_years(m: dict) -> dict:
    out={}
    for f in ("published","published-print","published-online","issued","created"):
        dp=(m.get(f) or {}).get("date-parts") or [[None]]
        if dp and dp[0] and dp[0][0]: out[f]=dp[0][0]
    return out

def doi_year(doi: str):
    m=re.search(r"(?<![0-9])(19[5-9][0-9]|20[0-2][0-9])(?![0-9])",doi)
    return int(m.group(1)) if m else None

def year_findings(year, m, dy) -> tuple[list,list]:
    """Return (issues, notes) about the sample year given Crossref dates and DOI year."""
    issues,notes=[],[]
    ys=crossref_years(m) if m else {}; ctype=(m or {}).get("type")
    print_y=ys.get("published-print"); created=ys.get("created"); official=print_y or ys.get("issued")
    hint=f"; DOI encodes {dy}" if dy else ""
    if year is None: issues.append("ERROR: year missing")
    elif ctype in ("report","posted-content","book-chapter","book-section","dataset","book") and dy and abs(dy-year)>1:
        issues.append(f"ERROR: year {year} is a re-deposit date; DOI encodes {dy}"+(f", first deposited {created}" if created else ""))
    elif ctype and ctype!="journal-article" and created and year-created>1:
        issues.append(f"UNCERTAIN year: listed {year}, but DOI first deposited {created} (likely platform re-issue)"+hint)
    elif ctype=="journal-article" and not print_y and created and year-created>1:
        issues.append(f"UNCERTAIN year: online-only date {year}, DOI first deposited {created}; check landing page"+hint)
    elif ctype=="journal-article" and print_y==year and created and year-created>2:
        issues.append(f"UNCERTAIN year: print {year} but DOI deposited {created} ({year-created}-year gap); check landing page"+hint)
    elif official and official!=year:
        issues.append(f"year {year} differs from Crossref issued/print {official}")
    elif created and created<year:
        notes.append(f"online-first {created}, issue/print {year} (citation year {year})")
    return issues,notes

def load_corpus(root: Path) -> list[tuple]:
    recs=[]
    files=[root/"registry/candidates-v03.jsonl"]+sorted((root/"registry/snapshot").glob("*.jsonl"))
    for path in files:
        for line in path.open(encoding="utf-8"):
            if line.strip():
                r=json.loads(line); recs.append((path.name,(r.get("doi") or "").lower(),r.get("title",""),r.get("authors") or [],r.get("year")))
    for p in json.loads((root/"data/papers.json").read_text(encoding="utf-8")):
        a=p.get("authors"); a=a if isinstance(a,list) else [x.strip() for x in str(a).split(",")]
        recs.append(("papers.json",(p.get("doi") or "").lower(),p.get("title",""),a,p.get("year")))
    return recs

def check_row(row: dict, rec: dict, corpus: list[tuple]) -> dict:
    doi=rec["doi"]; title=row["title"].lstrip("'")
    authors=[a.strip() for a in row["authors"].split(",") if a.strip()]
    year=int(row["year"]) if row["year"].strip().isdigit() else None
    issues,notes=[],[]
    ev={"doi":doi,"sample":{"title":title,"authors":authors,"year":year,"source":row["source"]}}
    ev["doi_registered"]=(rec["handle"].get("body") or {}).get("responseCode")==1
    if not ev["doi_registered"]: issues.append("DOI not registered at doi.org")
    m=(rec["crossref"].get("body") or {}).get("message") if rec["crossref"]["status"]==200 else None
    oa=rec["openalex"].get("body") if rec["openalex"]["status"]==200 else None
    if not m:
        issues.append(f"Crossref record unavailable (HTTP {rec['crossref']['status']})")
    else:
        crt=(m.get("title") or [""])[0]; tc=title_cmp(title,crt)
        ev.update(crossref_title=crt,title_check=tc)
        if tc=="differ": issues.append(f"title differs from Crossref: '{crt[:120]}'")
        elif tc=="subtitle": notes.append(f"Crossref title adds/drops subtitle: '{crt[:120]}'")
        elif tc=="missing": issues.append("Crossref has no title")
        people=m.get("author") or []
        fam=[a.get("family") or a.get("name") or "" for a in people]; ev["crossref_authors"]=fam
        if not fam: notes.append("Crossref lists no authors")
        else:
            ss=[surname(a) for a in authors]; cs=[surname(f) for f in fam]
            bad=[f"{a.get('given')} {a.get('family')}" for a in people
                 if a.get("family") and (a.get("given") or "").rstrip(",").strip()==a["family"].strip()]
            if bad: issues.append(f"ERROR: malformed author in Crossref deposit ('{bad[0]}', given name missing)")
            elif len(ss)!=len(cs): issues.append(f"author count {len(ss)} vs Crossref {len(cs)}")
            elif ss!=cs:
                if sorted(ss)==sorted(cs): issues.append("author order differs from Crossref")
                elif not all(any(c in fold(a) for a in authors) for c in cs):
                    issues.append(f"author names differ from Crossref ({', '.join(fam[:4])})")
        ev.update(crossref_years=crossref_years(m),crossref_type=m.get("type"),
                  crossref_container=(m.get("container-title") or [""])[0])
        if row["source"] and ev["crossref_container"] and fold(row["source"])!=fold(ev["crossref_container"]):
            notes.append(f"venue in Crossref: {ev['crossref_container']}")
        if m.get("type")!="journal-article": notes.append(f"Crossref type: {m.get('type')}")
        if m.get("type") in ("dataset","book-section","component"): notes.append("not a research paper record")
        ev["crossref_relations"]={k:[x.get("id") for x in v] for k,v in (m.get("relation") or {}).items() if k!="cites"}
    ev.update(openalex_year=oa.get("publication_year") if oa else None,openalex_id=oa.get("id") if oa else None)
    if not oa: notes.append(f"no OpenAlex record (HTTP {rec['openalex']['status']})")
    elif title_cmp(title,oa.get("display_name") or "")=="differ" and ev.get("title_check")!="differ":
        notes.append(f"OpenAlex title differs: '{(oa.get('display_name') or '')[:100]}'")
    ev["doi_embedded_year"]=dy=doi_year(doi)
    yi,yn=year_findings(year,m,dy); issues+=yi; notes+=yn
    # Versions: same normalized title elsewhere, sharing an author.
    ft=fold(title); first=surname(authors[0]) if authors else ""; mine={surname(a) for a in authors}
    dup=[f"in {src}: {d2 or 'no DOI'} ({y2})" for src,d2,t2,a2,y2 in corpus
         if d2!=doi and len(ft.split())>=4 and fold(t2)==ft and (not a2 or not first or surname(a2[0])==first)]
    ext=[]
    for w in ((rec.get("openalex_title_search") or {}).get("body") or {}).get("results") or []:
        d2=(w.get("doi") or "").lower().removeprefix("https://doi.org/")
        if not d2 or d2==doi or w.get("type") in NOT_VERSIONS or len(ft.split())<4 or fold(w.get("display_name"))!=ft:
            continue
        names=(rec.get("same_title_authors") or {}).get(w.get("id")) or []
        if any(surname(n) in mine for n in names):
            ext.append({"doi":d2,"year":w.get("publication_year"),"type":w.get("type"),"openalex_id":w.get("id"),
                        "venue":((w.get("primary_location") or {}).get("source") or {}).get("display_name")})
    for k,ids in ev.get("crossref_relations",{}).items():
        if k in VERSION_RELATIONS:
            notes.append(f"Crossref relation {k}: {', '.join(i for i in ids if i)[:120]}"); dup.append(f"Crossref {k}")
    if ext: notes.append("same title, other DOI: "+"; ".join(f"{e['doi']} ({e['year']}, {e['type']}, {e['venue'] or '?'})" for e in ext[:3])+" (shares an author)")
    if dup: notes.append("; ".join(dup[:3]))
    ev.update(corpus_duplicates=dup,openalex_same_title_other_doi=ext,issues=issues,notes=notes,
              metadata_verified="no" if issues else "yes",duplicate_version="yes" if dup or ext else "no")
    return ev

def check(cache: Path, write: bool=False, force: bool=False, day: str | None=None,
          sample: Path=SAMPLE, evidence_out: Path=EVIDENCE, root: Path=ROOT) -> list[dict]:
    day=day or date.today().isoformat(); marker=tag(day)
    rows=list(csv.DictReader(sample.open(encoding="utf-8"))); fields=list(rows[0].keys())
    if write and not force:
        edited=[i for i,r in enumerate(rows) if (r["reviewer_notes"] and not r["reviewer_notes"].startswith("[auto-check"))]
        if edited: raise SystemExit(f"rows {edited[:10]} have editor notes; refusing to overwrite (use --force)")
    corpus=load_corpus(root); evidence=[]
    for i,row in enumerate(rows):
        p=cache/cache_name(sample_doi(row))
        if not p.exists(): raise SystemExit(f"no cached metadata for row {i} ({sample_doi(row)}); run fetch first")
        ev=check_row(row,json.loads(p.read_text(encoding="utf-8")),corpus); ev["row"]=i; evidence.append(ev)
        if write:
            row.update(metadata_verified=ev["metadata_verified"],duplicate_version=ev["duplicate_version"],
                       reviewer_notes=(marker+" "+" | ".join(ev["issues"]+ev["notes"])).strip())
    evidence_out.write_text(json.dumps({"generated_on":day,"method":marker,"rows":evidence},ensure_ascii=False,indent=1),encoding="utf-8")
    if write:
        with sample.open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    return evidence

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="Automated metadata pre-check of the audit sample")
    sub=p.add_subparsers(dest="cmd",required=True)
    f=sub.add_parser("fetch"); f.add_argument("--cache",type=Path,required=True)
    c=sub.add_parser("check"); c.add_argument("--cache",type=Path,required=True)
    c.add_argument("--write",action="store_true"); c.add_argument("--force",action="store_true")
    c.add_argument("--date",help="date stamp for notes (default: today)")
    a=p.parse_args(argv)
    if a.cmd=="fetch":
        fetch(a.cache); return 0
    ev=check(a.cache,a.write,a.force,a.date)
    yes=sum(e["metadata_verified"]=="yes" for e in ev)
    print(json.dumps({"rows":len(ev),"metadata_verified_yes":yes,"metadata_verified_no":len(ev)-yes,
                      "error_rows":sum(any(x.startswith("ERROR") for x in e["issues"]) for e in ev),
                      "uncertain_rows":sum(any(x.startswith("UNCERTAIN") for x in e["issues"]) for e in ev),
                      "duplicate_version_yes":sum(e["duplicate_version"]=="yes" for e in ev),
                      "written":a.write},indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
