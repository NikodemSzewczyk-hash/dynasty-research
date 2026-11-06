"""Canonical identifiers and conservative title/author matching."""
import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import unquote, urlparse

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", flags=re.I)

def clean_text(value: str | None) -> str:
    return " ".join(str(value or "").split())

def canonical_doi(value: str | None) -> str | None:
    if not value:
        return None
    v = unquote(str(value).strip()).lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if v.startswith(prefix):
            v = v[len(prefix):]
            break
    v = v.split("?")[0].split("#")[0].strip().rstrip(".,;")
    return v if DOI_RE.match(v) else None

def key(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", clean_text(value).casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()

def slug(value: str) -> str:
    return key(value).replace(" ", "-") or "untitled"

def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]

def author_key(name: str | None) -> str:
    parts = key(name).split()
    return parts[-1] if parts else ""

def external_nber_id(url_or_id: str | None) -> str | None:
    if not url_or_id:
        return None
    candidate = str(url_or_id).strip().lower()
    m = re.search(r"(?:nber\.org/papers/|^)(w\d{3,8})(?:$|[/?#])",candidate)
    return m.group(1) if m else None

def possible_match(db, title: str, authors: list[str], year: int | None):
    """Return likely version or duplicate; never silently merge on fuzzy text."""
    t = key(title)
    first = author_key(authors[0]) if authors else ""
    if not t or not first:
        return None
    candidates = db.execute("SELECT id,title_key,year,first_author_key FROM works WHERE first_author_key=?", (first,)).fetchall()
    best, score = None, 0.0
    for row in candidates:
        if row["year"] and year and abs(row["year"] - year) > 6:
            continue
        similarity = SequenceMatcher(None, t, row["title_key"]).ratio()
        if similarity >= 0.93 and similarity > score:
            best, score = row["id"], similarity
    return best

def version_kind(status: str | None, source: str | None = None) -> str:
    x = key(status)
    s = key(source)
    if "working" in x or "preprint" in x or "working" in s or "discussion paper" in s:
        return "working_paper"
    if "publish" in x or "journal" in x:
        return "journal_article"
    return "other"

def safe_https(url: str | None) -> str | None:
    if not url:
        return None
    url = str(url).strip()
    parsed = urlparse(url)
    return url if parsed.scheme == "https" and parsed.netloc and not parsed.username else None
