#!/usr/bin/env python3
"""Read-only official API identity probe for 23 source pilot."""
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
JOURNALS=[
 ("journal:american-economic-review","0002-8282"),
 ("journal:quarterly-journal-of-economics","0033-5533"),
 ("journal:journal-of-political-economy","0022-3808"),
 ("journal:econometrica","0012-9682"),
 ("journal:review-of-economic-studies","0034-6527"),
 ("journal:aej-applied-economics","1945-7782"),
 ("journal:aej-economic-policy","1945-7731"),
 ("journal:review-of-economics-and-statistics","0034-6535"),
 ("journal:journal-of-labor-economics","0734-306X"),
 ("journal:journal-of-human-resources","0022-166X")
]
SERIES=[
 "working_paper_series:nber-working-papers",
 "working_paper_series:cepr-discussion-papers",
 "working_paper_series:iza-discussion-papers"
]
RESEARCHERS=[
 "researcher:jan-stuhler","researcher:martin-nybom",
 "researcher:katrine-v-l-ken","researcher:aline-butikofer",
 "researcher:kjell-g-salvanes","researcher:magne-mogstad",
 "researcher:raj-chetty","researcher:alessandra-voena",
 "researcher:corina-mommaerts","researcher:wojciech-kopczuk"
]
def fetch(url):
    headers={"User-Agent":"dynasty-research/0.4 (+https://dynastyecon.netlify.app/; source identity verification)",
             "Accept":"application/json"}
    if url.startswith("https://api.openalex.org/") and os.environ.get("OPENALEX_API_KEY"):
        headers["Authorization"]="Bearer "+os.environ["OPENALEX_API_KEY"]
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers=headers),timeout=25) as response:
                return json.load(response)
        except (HTTPError,URLError,TimeoutError) as e:
            if isinstance(e,HTTPError) and e.code not in (429,500,502,503,504):
                raise
            if attempt==2: raise
            time.sleep(1+attempt*2)
def get(url,errors,label):
    try: return fetch(url)
    except Exception as e:
        errors.append({"item":label,"error":str(e)[:160]})
        return {}
def main():
    manifest=json.loads((ROOT/"registry/source_manifest.json").read_text())
    byid={x["id"]:x for x in manifest["sources"]}
    out={"journals":[],"researchers":[],"series":[],"errors":[]}
    for sid,issn in JOURNALS:
        j=get("https://api.crossref.org/journals/"+issn,out["errors"],sid)
        m=j.get("message") or {}
        out["journals"].append({"source_id":sid,"expected_name":byid[sid]["name"],
                                "issn":issn,"returned_title":m.get("title"),
                                "returned_issns":m.get("ISSN")})
    for sid in SERIES+RESEARCHERS:
        item=byid[sid]
        kind="sources" if sid in SERIES else "authors"
        select=("id,display_name,issn,issn_l,works_count,homepage_url"
                if kind=="sources" else
                "id,display_name,orcid,works_count,last_known_institutions")
        params=urlencode({"search":item["name"],"per_page":5,"select":select})
        res=get("https://api.openalex.org/"+kind+"?"+params,out["errors"],sid)
        found=[]
        for a in (res.get("results") or [])[:5]:
            found.append({
                "id":a.get("id"),"name":a.get("display_name"),
                "works_count":a.get("works_count"),"issn":a.get("issn"),
                "orcid":a.get("orcid"),"homepage_url":a.get("homepage_url"),
                "institutions":[i.get("display_name") for i in (a.get("last_known_institutions") or [])]})
        out["series" if kind=="sources" else "researchers"].append({
            "source_id":sid,"expected_name":item["name"],"candidates":found})
    path=ROOT/"registry"/"pilot23-probe.json"
    path.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(out,indent=2,ensure_ascii=False))
    print("WROTE",path)
    return 0
if __name__=="__main__":
    raise SystemExit(main())
