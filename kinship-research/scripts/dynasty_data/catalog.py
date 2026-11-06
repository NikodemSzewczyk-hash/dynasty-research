"""SQLite-backed source registry, import review queue, paper/version graph and Hugo export."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Any
from .identity import author_key, canonical_doi, clean_text, key, possible_match, safe_https, short_hash, slug, version_kind

def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def seed_sources(db: sqlite3.Connection, manifest_path: str | Path) -> int:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported source registry version")
    n = 0
    with db:
        for item in manifest["sources"]:
            if item["kind"] not in ("journal", "working_paper_series", "researcher"):
                raise ValueError(f"Invalid source kind {item['kind']}")
            if item["tier"] not in ("A", "B", "C"):
                raise ValueError(f"Invalid source tier {item['tier']}")
            if not item.get("id") or not item.get("name"):
                raise ValueError("Source missing id or name")
            result = db.execute(
                """INSERT OR IGNORE INTO sources(id,kind,name,area,tier,identifiers_json,retrieval_json,editorial_status)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (item["id"],item["kind"],item["name"],item.get("area",""),item["tier"],
                 encode(item.get("identifiers",{})),encode(item.get("retrieval",{})),item.get("editorial_status","candidate")))
            n += result.rowcount
    return n

def _author(db, name: str) -> str:
    normalized = key(name)
    if not normalized:
        raise ValueError("Empty author name")
    aid = "author:" + short_hash(normalized)
    db.execute("INSERT OR IGNORE INTO authors(id,name,name_key) VALUES(?,?,?)",(aid,clean_text(name),normalized))
    return aid

def _add_people_topics(db, work_id: str, authors: list[str], topics: list[str]) -> None:
    for position, name in enumerate(authors):
        aid = _author(db,name)
        db.execute("INSERT OR IGNORE INTO work_authors(work_id,author_id,position) VALUES(?,?,?)",(work_id,aid,position))
    for topic in topics:
        tid = "topic:" + slug(topic)
        db.execute("INSERT OR IGNORE INTO topics(id,name) VALUES(?,?)",(tid,topic))
        db.execute("INSERT OR IGNORE INTO work_topics(work_id,topic_id) VALUES(?,?)",(work_id,tid))

def _source_id(db, source_name: str | None) -> str | None:
    if not source_name:
        return None
    row = db.execute("SELECT id FROM sources WHERE lower(name)=lower(?) LIMIT 1",(source_name,)).fetchone()
    return row["id"] if row else None

def seed_curated(db: sqlite3.Connection, papers_path: str | Path) -> int:
    papers = json.loads(Path(papers_path).read_text(encoding="utf-8"))
    created = 0
    with db:
        for p in papers:
            url = safe_https(p["paper_url"])
            if not url:
                raise ValueError(f"{p['id']}: unsafe paper URL")
            doi = canonical_doi(p.get("doi"))
            if p.get("doi") and not doi:
                raise ValueError(f"{p['id']}: malformed DOI")
            wid = slug(p["id"])
            if wid != p["id"]:
                raise ValueError(f"Unsafe curated work ID: {p['id']}")
            existing = db.execute("SELECT id FROM works WHERE id=?",(wid,)).fetchone()
            if existing is None:
                db.execute("""INSERT INTO works(id,title,title_key,year,first_author_key,takeaway,description,method,status)
                              VALUES(?,?,?,?,?,?,?,?,?)""",
                           (wid,p["title"],key(p["title"]),p["year"],author_key(p["authors"][0]) if p["authors"] else "",
                            p["takeaway"],p.get("description",""),p.get("method",""),"curated"))
                created += 1
            else:
                db.execute("""UPDATE works SET title=?,title_key=?,year=?,first_author_key=?,takeaway=?,description=?,method=?,status='curated',updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                           (p["title"],key(p["title"]),p["year"],author_key(p["authors"][0]) if p["authors"] else "",
                            p["takeaway"],p.get("description",""),p.get("method",""),wid))
            _add_people_topics(db,wid,p.get("authors",[]),p.get("topics",[]))
            version_id = "seed:" + wid
            db.execute("""INSERT INTO versions(id,work_id,kind,title,year,doi,source_name,source_id,url,metadata_json)
                          VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                          kind=excluded.kind,title=excluded.title,year=excluded.year,doi=excluded.doi,
                          source_name=excluded.source_name,source_id=excluded.source_id,url=excluded.url""",
                       (version_id,wid,version_kind(p.get("status"),p.get("source")),p["title"],p["year"],
                        doi,p["source"],_source_id(db,p["source"]),url,encode({"status":p.get("status","Published"),"working_paper_url":p.get("working_paper_url")})))
    return created

def find_match(db, doi: str | None, title: str, authors: list[str], year: int | None, provider: str = "", provider_id: str = "") -> tuple[str,str | None]:
    doi = canonical_doi(doi)
    if doi:
        row = db.execute("SELECT work_id FROM versions WHERE doi=? LIMIT 1",(doi,)).fetchone()
        if row:
            return "exact",row["work_id"]
    if provider_id:
        row = db.execute("SELECT work_id FROM versions WHERE (provider=? AND provider_id=?) OR (openalex_id=? AND ?='openalex') LIMIT 1",
                         (provider,provider_id,provider_id,provider)).fetchone()
        if row:
            return "exact",row["work_id"]
    probable = possible_match(db,title,authors,year)
    return ("possible",probable) if probable else ("none",None)

def enqueue(db, record: dict) -> tuple[bool,int]:
    """Store one normalized API record; never publish it or merge fuzzy matches."""
    provider = str(record["provider"]).lower()
    if provider not in ("openalex","crossref"):
        raise ValueError(f"Unsupported provider {provider}")
    title = clean_text(record.get("title"))
    authors = [clean_text(x) for x in record.get("authors",[]) if clean_text(x)]
    doi = canonical_doi(record.get("doi"))
    if record.get("doi") and doi is None:
        raise ValueError("Invalid DOI supplied by provider")
    provider_id = str(record.get("provider_id") or doi or "").strip()
    if not title or not provider_id:
        raise ValueError("Candidate needs title and provider id")
    url = safe_https(record.get("url"))
    if not url:
        raise ValueError("Candidate needs an HTTPS source URL")
    year = record.get("year")
    if year is not None and (not isinstance(year,int) or year<1800 or year>2100):
        raise ValueError("Invalid publication year")
    existing = db.execute("SELECT id FROM candidates WHERE provider=? AND provider_id=?",(provider,provider_id)).fetchone()
    if existing:
        return False,existing["id"]
    match_type, probable_id = find_match(db,doi,title,authors,year,provider,provider_id)
    with db:
        cursor = db.execute("""INSERT INTO candidates(provider,provider_id,doi,title,title_key,year,first_author_key,
             authors_json,source_name,url,kind,date,payload_json,match_type,possible_work_id)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (provider,provider_id,doi,title,key(title),year,author_key(authors[0]) if authors else "",
              encode(authors),clean_text(record.get("source_name")),url,record.get("kind","other"),
              record.get("date"),encode(record),match_type,probable_id))
        return True,int(cursor.lastrowid)

def queue(db, status: str = "pending", limit: int = 50) -> list[dict]:
    if status not in ("pending","accepted","rejected","deferred","all"):
        raise ValueError("Invalid review status")
    if limit<1 or limit>10000:
        raise ValueError("Queue limit must be 1..10000")
    sql = "SELECT id,provider,doi,title,year,authors_json,match_type,possible_work_id,status,discovered_at FROM candidates"
    params: tuple = ()
    if status != "all":
        sql += " WHERE status=?"
        params=(status,)
    sql += " ORDER BY id DESC LIMIT ?"
    return [dict(r) for r in db.execute(sql,params+(limit,)).fetchall()]

def decide(db, candidate_id: int, action: str, reviewer: str = "editor", takeaway: str = "",
           topics: list[str] | None = None, method: str = "", description: str = "",
           merge_into: str | None = None, force_new: bool = False, notes: str = "") -> str | None:
    """Explicit editorial decision; version matching is conservative and auditable."""
    if action not in ("approve","reject","defer"):
        raise ValueError("Action must be approve, reject, or defer")
    if merge_into and force_new:
        raise ValueError("Cannot merge and force new simultaneously")
    row = db.execute("SELECT * FROM candidates WHERE id=?",(candidate_id,)).fetchone()
    if not row:
        raise ValueError("Unknown candidate ID")
    if row["status"] not in ("pending","deferred"):
        raise ValueError("Candidate has already been reviewed")
    reviewer = clean_text(reviewer)
    if not reviewer:
        raise ValueError("Reviewer cannot be empty")
    result_work = None
    with db:
        if action=="approve":
            authors=json.loads(row["authors_json"])
            exact = db.execute("SELECT work_id,id FROM versions WHERE doi=?",(row["doi"],)).fetchone() if row["doi"] else None
            if exact:
                if merge_into and merge_into!=exact["work_id"]:
                    raise ValueError("DOI already belongs to another work")
                result_work=exact["work_id"]
                if row["provider"]=="openalex":
                    db.execute("UPDATE versions SET openalex_id=COALESCE(openalex_id,?) WHERE id=?",
                               (row["provider_id"],exact["id"]))
            elif merge_into:
                if not db.execute("SELECT 1 FROM works WHERE id=?",(merge_into,)).fetchone():
                    raise ValueError("Requested merge destination does not exist")
                result_work=merge_into
            elif row["match_type"]=="possible" and not force_new:
                raise ValueError(f"Possible existing version of {row['possible_work_id']}; use --merge-into or --force-new")
            else:
                if not clean_text(takeaway):
                    raise ValueError("An editorial takeaway is required before publishing a new work")
                if not topics:
                    raise ValueError("At least one editorial topic is required before publishing")
                result_work=slug(row["title"])[:72].rstrip("-")+"-"+short_hash(row["provider"]+":"+row["provider_id"])
                db.execute("""INSERT INTO works(id,title,title_key,year,first_author_key,takeaway,description,method,status)
                              VALUES(?,?,?,?,?,?,?,?,?)""",
                           (result_work,row["title"],row["title_key"],row["year"],row["first_author_key"],
                            clean_text(takeaway),clean_text(description) or "Research metadata reviewed by the dynasty_ editorial team.",
                            clean_text(method) or "See the original study.","approved"))
                _add_people_topics(db,result_work,authors,topics)
            version_exists=db.execute("SELECT id FROM versions WHERE provider=? AND provider_id=?",(row["provider"],row["provider_id"])).fetchone()
            if not exact and not version_exists:
                version_id="version:"+short_hash(row["provider"]+":"+row["provider_id"])
                db.execute("""INSERT INTO versions(id,work_id,kind,title,year,publication_date,doi,openalex_id,
                              provider,provider_id,source_name,source_id,url,metadata_json)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (version_id,result_work,row["kind"],row["title"],row["year"],row["date"],row["doi"],
                            row["provider_id"] if row["provider"]=="openalex" else None,row["provider"],
                            row["provider_id"],row["source_name"],_source_id(db,row["source_name"]),row["url"],
                            row["payload_json"]))
            status="accepted"
        else:
            status="rejected" if action=="reject" else "deferred"
        db.execute("""UPDATE candidates SET status=?,reviewer=?,reviewed_work_id=?,reviewed_at=CURRENT_TIMESTAMP,notes=?
                      WHERE id=?""",(status,reviewer,result_work,notes,candidate_id))
        db.execute("INSERT INTO review_decisions(candidate_id,action,work_id,reviewer,notes) VALUES(?,?,?,?,?)",
                   (candidate_id,action,result_work,reviewer,notes))
    return result_work

def stats(db) -> dict:
    counts={}
    for table in ("sources","works","authors","versions","topics","candidates","review_decisions","ingestion_runs"):
        counts[table]=db.execute("SELECT count(*) n FROM "+table).fetchone()["n"]
    counts["queue_status"]={r["status"]:r["n"] for r in db.execute("SELECT status,count(*) n FROM candidates GROUP BY status")}
    counts["published"] = db.execute("SELECT count(*) n FROM published_works").fetchone()["n"]
    return counts

def _authors_for(db, work_id: str) -> list[str]:
    return [r["name"] for r in db.execute(
      "SELECT a.name FROM work_authors wa JOIN authors a ON a.id=wa.author_id WHERE wa.work_id=? ORDER BY wa.position",(work_id,))]

def _topics_for(db, work_id: str) -> list[str]:
    return [r["name"] for r in db.execute(
      "SELECT t.name FROM work_topics wt JOIN topics t ON t.id=wt.topic_id WHERE wt.work_id=? ORDER BY t.name",(work_id,))]

def export_records(db) -> list[dict]:
    records=[]
    for w in db.execute("SELECT * FROM published_works ORDER BY year DESC,id"):
        v=db.execute("""SELECT * FROM versions WHERE work_id=?
            ORDER BY CASE kind WHEN 'journal_article' THEN 0 WHEN 'working_paper' THEN 1 ELSE 2 END,year DESC,id LIMIT 1""",(w["id"],)).fetchone()
        if not v:
            continue
        status="Published" if v["kind"]=="journal_article" else ("Working paper" if v["kind"]=="working_paper" else "Research")
        records.append({"id":w["id"],"title":w["title"],"authors":_authors_for(db,w["id"]),
            "topics":_topics_for(db,w["id"]),"year":w["year"],"source":v["source_name"] or "Research",
            "status":status,"doi":v["doi"],"paper_url":v["url"],"takeaway":w["takeaway"],
            "description":w["description"],"method":w["method"],"version_count":db.execute(
            "SELECT count(*) n FROM versions WHERE work_id=?",(w["id"],)).fetchone()["n"]})
    return records

def _yaml_str(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)

def render_markdown(record: dict) -> str:
    lines=["---",f"title: {_yaml_str(record['title'])}",f"year: {record['year']}",
           f"source: {_yaml_str(record['source'])}",f"status: {_yaml_str(record['status'])}",
           f"paper_url: {_yaml_str(record['paper_url'])}",f"takeaway: {_yaml_str(record['takeaway'])}",
           f"method: {_yaml_str(record['method'])}"]
    if record["doi"]:
        lines.append(f"doi: {_yaml_str(record['doi'])}")
    for field in ("authors","topics"):
        lines.append(field+":")
        lines.extend("  - "+_yaml_str(x) for x in record[field])
    lines+=["---","","## About this study","",record["description"],"",
            "## Editorial context","",record["takeaway"],"",
            "## Original source","",f"[Read at source]({record['paper_url']})",""]
    return "\n".join(lines)

def export_hugo(db, root: str | Path) -> dict:
    """Export only curated/explicitly approved works; no raw candidate publication."""
    root=Path(root)
    pages=root/"content"/"papers"
    index=root/"static"/"data"/"research-index.json"
    pages.mkdir(parents=True,exist_ok=True)
    index.parent.mkdir(parents=True,exist_ok=True)
    records=export_records(db)
    for record in records:
        if slug(record["id"])!=record["id"]:
            raise ValueError("Unsafe work ID")
        if not safe_https(record["paper_url"]):
            raise ValueError("Unsafe source URL")
        (pages/(record["id"]+".md")).write_text(render_markdown(record),encoding="utf-8")
    index.write_text(json.dumps(records,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"papers":len(records),"search_index":str(index),"pages":str(pages)}
