"""Non-mutating candidate identifier suggestions from the OpenAlex source/author API.

A name lookup is never proof of identity; an editor must verify and explicitly
enable the selected ISSN or author ID using the CLI.
"""
from __future__ import annotations
import os
from urllib.parse import urlencode
from .providers import fetch_json
from .identity import key

def suggest_identifiers(db, source_id: str, limit: int = 5, fetcher=fetch_json) -> dict:
    if not 1<=limit<=10:
        raise ValueError("Limit must be 1..10")
    source=db.execute("SELECT id,kind,name FROM sources WHERE id=?",(source_id,)).fetchone()
    if source is None:
        raise ValueError("Unknown source ID; seed the registry first")
    kind=source["kind"]
    if kind=="working_paper_series":
        return {"source_id":source_id,"query":source["name"],"suggestions":[],
                "note":"Working-paper feeds must be identified and checked manually; no generic repository resolver is available."}
    collection="sources" if kind=="journal" else "authors"
    fields=("id,display_name,issn,issn_l,works_count" if kind=="journal"
            else "id,display_name,orcid,works_count,last_known_institutions")
    params={"search":source["name"],"per_page":limit,"select":fields}
    email=os.getenv("DYNASTY_CONTACT_EMAIL","").strip()
    if email:params["mailto"]=email
    result=fetcher("https://api.openalex.org/"+collection+"?"+urlencode(params))
    suggestions=[]
    for candidate in (result.get("results") or [])[:limit]:
        display=candidate.get("display_name","")
        raw_id=candidate.get("id","")
        identifier=raw_id.rsplit("/",1)[-1] if raw_id else ""
        if kind=="journal":
            issns=candidate.get("issn") or []
            if candidate.get("issn_l") and candidate["issn_l"] not in issns:
                issns=[candidate["issn_l"]]+issns
            suggestions.append({"name":display,"openalex_source_id":identifier,
                                "issn_candidates":issns,"works_count":candidate.get("works_count"),
                                "name_exact":key(display)==key(source["name"])})
        else:
            institution_names=[r.get("display_name","") for r in (candidate.get("last_known_institutions") or [])]
            suggestions.append({"name":display,"openalex_author_id":identifier,
                                "orcid":candidate.get("orcid"),
                                "last_known_institutions":institution_names,
                                "works_count":candidate.get("works_count"),
                                "name_exact":key(display)==key(source["name"])})
    return {"source_id":source_id,"query":source["name"],"suggestions":suggestions,
            "note":"Suggestions are UNVERIFIED. Confirm identities/ISSNs against official profiles before using 'sources verify'."}
