"""Offline metadata import from NBER's official public-use ref.tsv.

Official schema: paper,author,title,issue_date,doi. Download TSV yourself from
https://www.nber.org/research/data/nber-working-papers-and-chapters-metadata.
Never download copyrighted paper PDFs. This only parses bibliographic metadata.
"""
from __future__ import annotations
import csv
import re
from pathlib import Path
from typing import Iterator
from .identity import canonical_doi, clean_text, safe_https

NBER_ID=re.compile(r"^w\d{3,8}$",re.I)
YEAR_RE=re.compile(r"\b(?:19|20)\d{2}\b")

def normalize_nber(row: dict) -> dict | None:
    paper=clean_text(row.get("paper")).lower()
    if not NBER_ID.fullmatch(paper):
        return None  # book chapters and retired h/t series are intentionally out of scope
    title=clean_text(row.get("title"))
    if not title:
        return None
    raw_author=clean_text(row.get("author"))
    # The official ref.tsv may concatenate authors with ambiguous commas.
    # Split only unambiguous separators, never guess author identity from commas.
    authors=[clean_text(part) for part in re.split(r"\s*(?:;|\s+and\s+|\s+&\s+)\s*",raw_author) if clean_text(part)]
    issue_date=clean_text(row.get("issue_date"))
    found=YEAR_RE.search(issue_date)
    year=int(found.group(0)) if found else None
    doi=canonical_doi(row.get("doi"))
    return {"provider":"nber","provider_id":paper,"doi":doi,"title":title,"authors":authors,
            "year":year,"date":issue_date or None,"source_name":"NBER Working Papers",
            "url":"https://www.nber.org/papers/"+paper,"kind":"working_paper"}

def iter_nber_tsv(filename: str | Path, from_year: int=2000, to_year: int=2100,
                  max_records: int=500, max_rows: int=100000) -> Iterator[dict]:
    if from_year>to_year or not 1800<=from_year<=2100 or not 1800<=to_year<=2100:
        raise ValueError("Invalid year range")
    if not 1<=max_records<=10000 or not 1<=max_rows<=1000000:
        raise ValueError("Bounded NBER import limits exceeded")
    path=Path(filename)
    if not path.is_file():
        raise FileNotFoundError(f"TSV not found: {path}")
    with path.open("r",encoding="utf-8-sig",errors="replace",newline="") as handle:
        reader=csv.DictReader(handle,delimiter="\t")
        expected={"paper","author","title","issue_date"}
        if not reader.fieldnames or not expected.issubset(set(reader.fieldnames)):
            raise ValueError("NBER ref.tsv needs paper,author,title,issue_date columns")
        found=0
        for n,row in enumerate(reader):
            if n>=max_rows:
                break
            record=normalize_nber(row)
            if record is None or record["year"] is None:
                continue
            if not from_year<=record["year"]<=to_year:
                continue
            yield record
            found+=1
            if found>=max_records:
                break
