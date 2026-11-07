"""Versioned SQLite schema and connection helpers."""
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1
DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('journal','working_paper_series','researcher')),
  name TEXT NOT NULL,
  area TEXT NOT NULL DEFAULT '',
  tier TEXT NOT NULL DEFAULT 'C',
  identifiers_json TEXT NOT NULL DEFAULT '{}',
  retrieval_json TEXT NOT NULL DEFAULT '{}',
  editorial_status TEXT NOT NULL DEFAULT 'candidate',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS sources_kind ON sources(kind);
CREATE TABLE IF NOT EXISTS works (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  title_key TEXT NOT NULL,
  year INTEGER,
  first_author_key TEXT NOT NULL DEFAULT '',
  takeaway TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  method TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK (status IN ('curated','approved')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS works_title_key ON works(title_key);
CREATE TABLE IF NOT EXISTS authors (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE,
  orcid TEXT UNIQUE, openalex_id TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS work_authors (
  work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
  author_id TEXT NOT NULL REFERENCES authors(id),
  position INTEGER NOT NULL,
  PRIMARY KEY (work_id, author_id),
  UNIQUE (work_id, position)
);
CREATE TABLE IF NOT EXISTS versions (
  id TEXT PRIMARY KEY,
  work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('journal_article','working_paper','other')),
  title TEXT NOT NULL,
  year INTEGER,
  publication_date TEXT,
  doi TEXT UNIQUE,
  openalex_id TEXT UNIQUE,
  provider TEXT,
  provider_id TEXT,
  source_name TEXT NOT NULL DEFAULT '',
  source_id TEXT REFERENCES sources(id),
  url TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS versions_work_id ON versions(work_id);
CREATE INDEX IF NOT EXISTS versions_provider ON versions(provider, provider_id);
CREATE TABLE IF NOT EXISTS topics (id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS work_topics (
  work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
  topic_id TEXT NOT NULL REFERENCES topics(id),
  PRIMARY KEY(work_id, topic_id)
);
CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  doi TEXT,
  title TEXT NOT NULL,
  title_key TEXT NOT NULL,
  year INTEGER,
  first_author_key TEXT NOT NULL DEFAULT '',
  authors_json TEXT NOT NULL,
  source_name TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'other',
  date TEXT,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','accepted','rejected','deferred')),
  match_type TEXT NOT NULL DEFAULT 'none'
    CHECK(match_type IN ('none','exact','possible')),
  possible_work_id TEXT REFERENCES works(id),
  reviewed_work_id TEXT REFERENCES works(id),
  reviewer TEXT,
  reviewed_at TEXT,
  notes TEXT NOT NULL DEFAULT '',
  discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (provider,provider_id)
);
CREATE INDEX IF NOT EXISTS candidates_status ON candidates(status,match_type);
CREATE INDEX IF NOT EXISTS candidates_doi ON candidates(doi);
CREATE TABLE IF NOT EXISTS review_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_id INTEGER NOT NULL REFERENCES candidates(id),
  action TEXT NOT NULL,
  work_id TEXT REFERENCES works(id),
  reviewer TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  query TEXT NOT NULL,
  from_date TEXT,
  to_date TEXT,
  fetched INTEGER NOT NULL DEFAULT 0,
  queued INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT
);
CREATE VIEW IF NOT EXISTS published_works AS
  SELECT * FROM works WHERE status IN ('curated','approved') AND length(takeaway)>0;
"""

def connect(path: str | Path) -> sqlite3.Connection:
    """Open a local SQLite database; caller owns the connection."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def initialize(db: sqlite3.Connection) -> None:
    db.executescript(DDL)
    current = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if current and int(current["value"]) != SCHEMA_VERSION:
        raise RuntimeError(f"Unsupported schema {current['value']} (expected {SCHEMA_VERSION}); migrate explicitly")
    db.execute("INSERT OR IGNORE INTO meta(key,value) VALUES ('schema_version',?)", (str(SCHEMA_VERSION),))
    db.commit()
