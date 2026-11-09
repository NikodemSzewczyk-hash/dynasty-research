"""RePEc ReDIF metadata adapter: the standard RePEc access method (no website scraping).

RePEc asks data users to read the ReDIF files that each publisher archive exposes, as
listed in the archive templates at ftp://all.repec.org/RePEc/all/, or a RePEc mirror. It
strongly discourages scraping IDEAS pages: https://ideas.repec.org/getdata.html

Only an allowlist of bibliographic fields is kept. Author e-mail addresses, workplaces,
abstracts and file links are dropped: RePEc never releases e-mails, and abstracts may carry
rights. Only *.rdf/*.redif files are fetched; PDFs in the same directories are ignored.
"""
from __future__ import annotations
from html import unescape
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from .identity import clean_text

USER_AGENT="dynasty-research/0.6 (+https://dynastyecon.netlify.app/; RePEc ReDIF metadata; noncommercial)"
MAX_FILE_BYTES=40_000_000
KEEP={"template-type","handle","title","author-name","creation-date","number",
      "classification-jel","publication-status"}
MULTI={"author-name"}
REDIF_FILE=re.compile(r"^[A-Za-z0-9._-]+\.(?:rdf|redif)$",re.I)

def decode_redif(raw: bytes) -> str:
    """ReDIF has no declared encoding: CEPR files are UTF-8, IZA files mix Windows-1252
    and UTF-8, sometimes within one file. Decode line by line, preferring UTF-8."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    lines=[]
    for line in raw.split(b"\n"):
        try:
            lines.append(line.decode("utf-8"))
        except UnicodeDecodeError:
            lines.append(line.decode("cp1252",errors="replace"))
    return "\n".join(lines).lstrip("\ufeff")

def parse_redif(text: str) -> list[dict]:
    """Split ReDIF text into templates holding allowlisted fields only.

    Field lines look like "Name: value"; indented lines continue the previous value.
    """
    templates,current,last=[],None,None
    for line in text.replace("\r\n","\n").replace("\r","\n").split("\n"):
        if line[:1] in (" ","\t") and current is not None and last:
            if last in current and line.strip():
                if last in MULTI:
                    current[last][-1]+=" "+line.strip()
                else:
                    current[last]+=" "+line.strip()
            continue
        m=re.match(r"^([A-Za-z][A-Za-z0-9-]*):\s?(.*)$",line)
        if not m:
            continue
        name,value=m.group(1).lower(),m.group(2).strip()
        if name=="template-type":
            if current is not None:
                templates.append(current)
            current={"template-type":value}
            last=name
            continue
        if current is None:
            continue
        last=name
        if name not in KEEP:
            continue
        if name in MULTI:
            current.setdefault(name,[]).append(value)
        elif name not in current:
            current[name]=value
    if current is not None:
        templates.append(current)
    return templates

def _year(creation_date: str | None) -> int | None:
    m=re.match(r"^\s*((?:18|19|20)\d{2})",creation_date or "")
    return int(m.group(1)) if m else None

def ideas_url(handle: str) -> str:
    """Canonical IDEAS landing page for a RePEc paper handle (a link, not a fetch)."""
    parts=handle.split(":")
    if len(parts)!=4 or parts[0].lower()!="repec":
        raise ValueError("Unexpected RePEc paper handle: "+handle)
    return f"https://ideas.repec.org/p/{parts[1]}/{parts[2]}/{parts[3]}.html"

def normalize_redif_paper(t: dict, series_handle: str, source_name: str) -> dict | None:
    """Map a ReDIF-Paper template of the verified series onto the pipeline record shape."""
    if not t.get("template-type","").lower().startswith("redif-paper"):
        return None
    handle=(t.get("handle") or "").strip()
    if not handle.lower().startswith(series_handle.lower()+":"):
        return None
    title=clean_text(unescape(t.get("title") or ""))
    if not title:
        return None
    authors=[clean_text(a) for a in t.get("author-name",[]) if clean_text(a)]
    rec={"provider":"repec","provider_id":handle,"doi":None,"title":title,"authors":authors[:30],
         "year":_year(t.get("creation-date")),"date":None,"source_name":source_name,
         "url":ideas_url(handle),"kind":"working_paper","repec_series_handle":series_handle}
    if t.get("number"):
        rec["series_number"]=t["number"]
    if t.get("classification-jel"):
        rec["jel"]=[c for c in re.split(r"[;,\s]+",t["classification-jel"]) if c][:12]
    if t.get("publication-status"):
        rec["publication_status"]=clean_text(t["publication-status"])[:300]
    return rec

def _fetch_bytes(url: str) -> bytes:
    req=Request(url,headers={"User-Agent":USER_AGENT})
    with urlopen(req,timeout=90) as res:
        body=res.read(MAX_FILE_BYTES+1)
    if len(body)>MAX_FILE_BYTES:
        raise ValueError("ReDIF resource exceeds safe size bound: "+url)
    return body

def list_redif_files(directory_url: str, fetch=_fetch_bytes) -> list[str]:
    """Names of ReDIF files in an archive directory (HTTP index page or FTP listing)."""
    listing=fetch(directory_url).decode("utf-8",errors="replace")
    if urlsplit(directory_url).scheme=="ftp":
        names=[line.split()[-1] for line in listing.splitlines() if line.strip()]
    else:
        names=[urlsplit(h).path.rsplit("/",1)[-1] for h in re.findall(r'href="([^"]+)"',listing,re.I)]
    files=sorted({n for n in names if REDIF_FILE.match(n)})
    if not files:
        raise ValueError("No ReDIF files listed at "+directory_url+"; refusing empty success")
    return files

def file_year(name: str) -> int | None:
    m=re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)",name)
    return int(m.group(1)) if m else None

def iter_redif_series(directory_url: str, series_handle: str, source_name: str,
                      start_year: int, end_year: int, max_records: int=100000,
                      fetch=_fetch_bytes, stats: dict | None=None):
    """Yield normalized papers from a series' ReDIF files within the year window.

    Files named by year outside the window are skipped; files without a year are always read.
    stats receives files read, templates seen ("available") and records yielded ("raw").
    """
    if not 1<=max_records<=200000:
        raise ValueError("Bounded ReDIF runs must request 1..200000 records")
    if not directory_url.endswith("/"):
        directory_url+="/"
    stats=stats if stats is not None else {}
    stats.update(files=0,available=0,raw=0)
    for name in list_redif_files(directory_url,fetch):
        fy=file_year(name)
        # A paper dated late in year Y can sit in the Y+1 file, so keep one year of slack.
        if fy is not None and not (start_year-1<=fy<=end_year+1):
            continue
        stats["files"]+=1
        for t in parse_redif(decode_redif(fetch(urljoin(directory_url,name)))):
            rec=normalize_redif_paper(t,series_handle,source_name)
            if rec is None:
                continue
            if rec["year"] is not None and not start_year<=rec["year"]<=end_year:
                continue
            stats["available"]+=1
            if stats["raw"]>=max_records:
                continue
            stats["raw"]+=1
            yield rec
