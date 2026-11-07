"""Evidence-first paper notes. Drafts are never represented as full-text reviews."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

STATES={"draft","source_read","evidence_checked","synthesis_ready"}
CLAIM_TYPES={"author_claim","empirical_finding","identified_estimand","interpretation","limitation"}
RELATIONS={"supports","challenges","extends","different_estimand","methodological_comparison","context"}

def draft_note(work: dict, versions: list[dict]) -> dict:
    return {
        "schema_version":1,
        "paper_id":work["id"],
        "title":work["title"],
        "status":"draft",
        "reviewer":"",
        "source":{"versions":[{"doi":v.get("doi"),"url":v["url"],"kind":v["kind"]} for v in versions],
                  "pdf_sha256":None,"pdf_pages":None,"pdf_access_url":None},
        "motivating_question":"",
        "actual_estimand":{"treatment":"","outcome":"","population":"","timing":"",
                           "identifying_variation":"","assumptions":[]},
        "data_and_sample":"",
        "empirical_design":"",
        "results":[],
        "claims":[],
        "limitations":[],
        "connections":[],
        "open_questions":[],
        "review_log":[],
        "disclaimer":"DRAFT TEMPLATE — no paper has been read or verified."
    }

def hash_pdf(path: str | Path) -> str:
    path=Path(path)
    with path.open("rb") as f:
        if f.read(5)!=b"%PDF-":
            raise ValueError("Not a PDF")
        f.seek(0)
        digest=hashlib.sha256()
        for chunk in iter(lambda:f.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()

def validate_note(note: dict) -> list[str]:
    errors=[]
    if note.get("schema_version")!=1:
        errors.append("Unknown schema_version")
    if not isinstance(note.get("paper_id"),str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,150}",note.get("paper_id","")):
        errors.append("paper_id must be a stable work slug")
    status=note.get("status")
    if status not in STATES:
        errors.append("Invalid review status")
    source=note.get("source") or {}
    pages=source.get("pdf_pages")
    digest=source.get("pdf_sha256")
    if status in ("source_read","evidence_checked","synthesis_ready"):
        if not re.fullmatch(r"[0-9a-f]{64}",digest or ""):
            errors.append("A full-text review requires a PDF SHA256")
        if not isinstance(pages,int) or pages<1:
            errors.append("A full-text review requires a positive PDF page count")
        if not note.get("reviewer"):
            errors.append("A full-text review requires a named reviewer")
    for group in ("claims","results"):
        for i,item in enumerate(note.get(group,[])):
            if not isinstance(item,dict):
                errors.append(f"{group}[{i}] must be an object")
                continue
            if group=="claims" and item.get("kind") not in CLAIM_TYPES:
                errors.append(f"claims[{i}] has invalid kind")
            if not item.get("text"):
                errors.append(f"{group}[{i}] missing text")
            evidence=item.get("evidence") or []
            if status in ("evidence_checked","synthesis_ready") and not evidence:
                errors.append(f"{group}[{i}] needs page-level evidence")
            for e in evidence:
                if not isinstance(e,dict) or not isinstance(e.get("page"),int) or e["page"]<1:
                    errors.append(f"{group}[{i}] evidence must have a positive page number")
                elif isinstance(pages,int) and e["page"]>pages:
                    errors.append(f"{group}[{i}] cites a page beyond PDF length")
    for i,conn in enumerate(note.get("connections",[])):
        if not isinstance(conn,dict) or conn.get("relation") not in RELATIONS or not conn.get("other_paper_id"):
            errors.append(f"connections[{i}] needs other_paper_id and a valid relation")
        elif status=="synthesis_ready" and not conn.get("rationale"):
            errors.append(f"connections[{i}] requires an explicit rationale")
    if status=="synthesis_ready" and not note.get("claims"):
        errors.append("Synthesis-ready notes need evidence-checked claims")
    return errors

def load_and_validate(path: str | Path) -> list[str]:
    try:
        data=json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        return [f"Cannot read note: {exc}"]
    return validate_note(data)
