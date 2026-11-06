"""Bounded historical OpenAlex and Crossref metadata importers.

These functions do not publish papers. The caller enqueues normalized candidates
for human review. No automatic bulk scraping or unbounded cursor traversal.
"""
from __future__ import annotations
import json
import os
import re
import time
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from typing import Callable, Iterator
from .identity import canonical_doi, clean_text, safe_https, version_kind

Fetch = Callable[[str], dict]
USER_AGENT="dynasty-research/0.2 (+https://dynastyecon.netlify.app/; metadata discovery; noncommercial)"

def fetch_json(url: str) -> dict:
    """Light retries for transient failures; no secrets embedded in the URL logs."""
    email=os.getenv("DYNASTY_CONTACT_EMAIL","").strip()
    headers={"User-Agent":USER_AGENT+(f" mailto:{email}" if email else ""),"Accept":"application/json"}
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers=headers),timeout=40) as res:
                return json.load(res)
        except HTTPError as ex:
            if ex.code==401 and "api.openalex.org" in url:
                raise RuntimeError("OpenAlex requires an API key for this request; configure OPENALEX_API_KEY") from ex
            if ex.code not in (429,500,502,503,504) or attempt==2:
                raise
            time.sleep(2**attempt)
        except (URLError,TimeoutError):
            if attempt==2:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("Request failed")

def validate_dates(from_date: str, to_date: str) -> None:
    a,b=date.fromisoformat(from_date),date.fromisoformat(to_date)
    if a>b:
        raise ValueError("Start date must not be after end date")

def _year_openalex(work: dict) -> int | None:
    value=work.get("publication_year")
    return int(value) if value and str(value).isdigit() else None

def normalize_openalex(work: dict) -> dict | None:
    title=clean_text(work.get("title") or work.get("display_name"))
    identity=work.get("id") or ""
    if not title or not identity.startswith("https://openalex.org/"):
        return None
    authors=[clean_text((a.get("author") or {}).get("display_name")) for a in (work.get("authorships") or [])]
    authors=[a for a in authors if a]
    loc=work.get("primary_location") or {}
    source=loc.get("source") or {}
    doi=canonical_doi(work.get("doi"))
    url=safe_https(work.get("doi")) or safe_https(loc.get("landing_page_url")) or identity
    dtype=work.get("type","")
    kind="working_paper" if dtype in ("preprint","posted-content") else ("journal_article" if dtype=="article" else "other")
    return {"provider":"openalex","provider_id":identity,"doi":doi,"title":title,
            "authors":authors,"year":_year_openalex(work),"date":work.get("publication_date"),
            "source_name":clean_text(source.get("display_name")),"url":url,"kind":kind}

def _year_crossref(work: dict) -> int | None:
    for field in ("published","published-online","published-print","issued","created"):
        entry=work.get(field) or {}
        parts=entry.get("date-parts") or []
        if parts and parts[0] and isinstance(parts[0][0],int):
            return parts[0][0]
    return None

def normalize_crossref(work: dict) -> dict | None:
    doi=canonical_doi(work.get("DOI"))
    raw_title=work.get("title") or []
    title=clean_text(raw_title[0] if isinstance(raw_title,list) and raw_title else raw_title if isinstance(raw_title,str) else "")
    if not doi or not title:
        return None
    people=[]
    for p in work.get("author",[]) or []:
        name=clean_text(" ".join(filter(None,[p.get("given",""),p.get("family","")]))) or clean_text(p.get("name"))
        if name:
            people.append(name)
    venue=work.get("container-title") or []
    source=clean_text(venue[0] if isinstance(venue,list) and venue else venue if isinstance(venue,str) else "")
    wt=work.get("type","")
    kind="journal_article" if wt=="journal-article" else ("working_paper" if wt in ("posted-content","working-paper") else "other")
    url=safe_https(work.get("URL")) or "https://doi.org/"+doi
    return {"provider":"crossref","provider_id":doi,"doi":doi,"title":title,
            "authors":people,"year":_year_crossref(work),"date":None,
            "source_name":source,"url":url,"kind":kind}

def iter_openalex(query: str, from_date: str, to_date: str,
                  max_records: int=100, fetcher: Fetch=fetch_json,
                  author_id: str | None=None) -> Iterator[dict]:
    validate_dates(from_date,to_date)
    if not 1<=max_records<=10000:
        raise ValueError("Bounded OpenAlex runs must request 1..10000 records")
    if not query and not author_id:
        raise ValueError("OpenAlex requires a query or verified author ID")
    if author_id and not re.fullmatch(r"A\d{4,12}",author_id):
        raise ValueError("Expected a verified OpenAlex author ID such as A1234567890")
    filter_value=f"from_publication_date:{from_date},to_publication_date:{to_date}"
    if author_id:
        filter_value+=",author.id:"+author_id
    processed=0  # Count ALL fetched records, even if metadata normalization rejects them.
    per_page=min(100,max_records)
    page=1
    while processed<max_records:
        params={"filter":filter_value,"per_page":min(per_page,max_records-processed),"page":page,
                "select":"id,doi,title,publication_year,publication_date,authorships,primary_location,type"}
        if query:
            params["search"]=query
        email=os.getenv("DYNASTY_CONTACT_EMAIL","").strip()
        if email:
            params["mailto"]=email
        api_key=os.getenv("OPENALEX_API_KEY","").strip()
        if api_key:
            params["api_key"]=api_key
        result=fetcher("https://api.openalex.org/works?"+urlencode(params))
        batch=result.get("results") or []
        if not batch:
            break
        for raw in batch:
            processed+=1
            normalized=normalize_openalex(raw)
            if normalized:
                yield normalized
            if processed>=max_records:
                break
        if len(batch)<params["per_page"]:
            break
        page+=1

def iter_crossref(query: str, from_date: str, to_date: str,
                  max_records: int=100, fetcher: Fetch=fetch_json,
                  journal_issn: str | None=None) -> Iterator[dict]:
    validate_dates(from_date,to_date)
    if not 1<=max_records<=10000:
        raise ValueError("Bounded Crossref runs must request 1..10000 records")
    if not query and not journal_issn:
        raise ValueError("Crossref requires a query or verified journal ISSN")
    if journal_issn and not re.fullmatch(r"\d{4}-[\dXx]{4}",journal_issn):
        raise ValueError("Journal ISSN must have the form 1234-567X")
    base=("https://api.crossref.org/journals/"+quote(journal_issn)+"/works"
          if journal_issn else "https://api.crossref.org/works")
    cursor="*"
    processed=0  # Raw API records, not just accepted metadata.
    page_size=min(100,max_records)
    while processed<max_records:
        params={"filter":f"from-pub-date:{from_date},until-pub-date:{to_date}",
                "rows":min(page_size,max_records-processed),"cursor":cursor}
        if query:
            params["query.bibliographic"]=query
        mailto=os.getenv("DYNASTY_CONTACT_EMAIL","").strip()
        if mailto:
            params["mailto"]=mailto
        response=fetcher(base+"?"+urlencode(params))
        message=response.get("message") or {}
        batch=message.get("items") or []
        if not batch:
            break
        for raw in batch:
            processed+=1
            normalized=normalize_crossref(raw)
            if normalized:
                yield normalized
            if processed>=max_records:
                break
        nxt=message.get("next-cursor")
        if len(batch)<params["rows"] or not nxt or nxt==cursor:
            break
        cursor=nxt

def lookup_source(db, source_id: str, provider: str) -> dict:
    """Explicit opt-in source collection; never invent or silently infer IDs."""
    row=db.execute("SELECT * FROM sources WHERE id=?",(source_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown source ID")
    ids=json.loads(row["identifiers_json"])
    retrieval=json.loads(row["retrieval_json"])
    if not retrieval.get("enabled"):
        raise ValueError(f"{source_id}: retrieval disabled until identifiers are verified")
    if provider=="crossref" and row["kind"]=="journal":
        issn=ids.get("issn")
        if not issn or not re.fullmatch(r"\d{4}-[\dXx]{4}",issn):
            raise ValueError(f"{source_id}: verified ISSN required")
        return {"journal_issn":issn}
    if provider=="openalex" and row["kind"]=="researcher":
        aid=ids.get("openalex_author_id")
        if not aid or not re.fullmatch(r"A\d{4,12}",aid):
            raise ValueError(f"{source_id}: verified OpenAlex author ID required")
        return {"author_id":aid}
    raise ValueError("Source kind not supported by this importer; use keyword query")
