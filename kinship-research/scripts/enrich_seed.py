"""Match the cleaned seed list to DOIs (Crossref) and OpenAlex records.

Crossref (free, no key), up to three queries per record:
  1. title + first author;
  2. title only, if (1) is weak (author names in the seed list are sometimes misspelled
     or are a co-author's first name);
  3. title restricted to journal articles / chapters, if the best hit is a working-paper
     version (SSRN, NBER, IZA, IMF, World Bank, ...). The working-paper DOI is kept in
     `working_paper_doi`.
OpenAlex: batch lookup by DOI (50 per request, paged), then single lookups for DOIs the
batch did not return (OpenAlex sometimes merges a journal article with its working paper
under the working paper's DOI). Uses OPENALEX_API_KEY / OPENALEX_EMAIL if set.

All responses are cached under registry/seed/cache/ (git-ignored): re-runs are free and
reproducible. Output is a review file; nothing is written to data/papers.json.

Standard library only. Usage: python scripts/enrich_seed.py
Output: registry/seed/intergenerational_dataset.enriched.csv
"""
from __future__ import annotations

import csv
import difflib
import html
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'registry' / 'seed'
SRC = SEED / 'intergenerational_dataset.clean.csv'
CORRECTIONS = SEED / 'corrections.csv'  # hand-checked fixes: set_title, set_authors, set_doi, reject_match
OUT = SEED / 'intergenerational_dataset.enriched.csv'
CACHE = SEED / 'cache'
UA = 'KinshipResearchPrototype/0.1 (metadata research discovery; python-urllib)'
FINAL_TYPES = {'journal-article', 'book-chapter', 'book', 'reference-entry', 'monograph', 'edited-book'}
WP_DOI_PREFIXES = ('10.2139/', '10.3386/', '10.5089/', '10.1596/', '10.2307/j.ctt', '10.17863/', '10.1920/', '10.26481/')
WP_VENUES = re.compile(r'SSRN|Working Paper|Discussion Paper|IZA|NBER|CESifo|IMF', re.I)
JOURNAL_ALIASES = {'aejappliedeconomics': 'americaneconomicjournalappliedeconomics'}


def norm(s) -> str:
    s = html.unescape(re.sub(r'<[^>]+>', ' ', str(s or '')))
    s = unicodedata.normalize('NFKD', s.replace('ø', 'o').replace('Ø', 'O').replace('æ', 'ae'))
    return re.sub(r'[^a-z0-9]', '', s.encode('ascii', 'ignore').decode().lower())


def fetch_json(url: str, cache_file: Path, pause: float) -> dict:
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding='utf-8'))
    for attempt in range(5):
        try:
            with urlopen(Request(url, headers={'User-Agent': UA}), timeout=60) as r:
                payload = json.load(r)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            time.sleep(pause)
            return payload
        except HTTPError as e:
            if e.code == 404:
                payload = {'not_found': True}
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(payload), encoding='utf-8')
                return payload
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt * 2)
                continue
            raise
        except (URLError, TimeoutError):
            time.sleep(2 ** attempt * 2)
    raise RuntimeError(f'Giving up on {url}')


def main_title(s: str) -> str:
    """Title before the first colon/question mark: 'X: Evidence from Y' -> 'X'."""
    return norm(re.split(r'[:?]', html.unescape(re.sub(r'<[^>]+>', ' ', s or '')), maxsplit=1)[0])


def title_similarity(given: str, candidate: str, truncated: bool) -> float:
    g, c = norm(given), norm(candidate)
    if not g or not c:
        return 0.0
    if truncated and c.startswith(g):
        return 1.0
    full = difflib.SequenceMatcher(None, g, c).ratio()
    # A subtitle present on only one side ("Title" vs "Title: Evidence from X").
    shorter, longer = sorted((g, c), key=len)
    prefix = 0.95 if len(shorter) >= 12 and longer.startswith(shorter) else 0.0
    trimmed = difflib.SequenceMatcher(None, shorter, longer[:len(shorter)]).ratio() - 0.03 if len(shorter) >= 12 else 0.0
    return max(full, prefix, trimmed)


def same_work_title(a: str, b: str) -> bool:
    """Working paper and journal version often differ only in the subtitle."""
    ma, mb = main_title(a), main_title(b)
    return (title_similarity(a, b, False) >= 0.9
            or (len(ma) >= 15 and difflib.SequenceMatcher(None, ma, mb).ratio() >= 0.95))


def author_hit(seed_authors: list[str], item_authors: list[dict]) -> bool:
    """True if any seed author name fuzzily matches any family or given name in the item."""
    seed_tokens = {norm(tok) for a in seed_authors for tok in re.split(r'[\s\-]+', a) if len(norm(tok)) > 2}
    seed_tokens |= {norm(a) for a in seed_authors}  # multi-word surnames: "De Nardi" -> "denardi"
    names = {norm(x) for a in item_authors for x in (a.get('family', ''), a.get('given', ''), a.get('name', '')) if x}
    names |= {norm(tok) for a in item_authors for tok in re.split(r'[\s\-]+', a.get('family', '')) if len(norm(tok)) > 2}
    for s in seed_tokens:
        for n in names:
            if s and n and (s == n or (len(s) > 3 and (s in n or n in s)) or difflib.SequenceMatcher(None, s, n).ratio() >= 0.8):
                return True
    return False


def is_working_paper(c: dict) -> bool:
    return (c['cr_type'] in ('posted-content', 'report', 'report-component', 'other')
            or c['doi'].startswith(WP_DOI_PREFIXES) or bool(WP_VENUES.search(c['cr_journal'])))


def crossref_candidates(rec: dict, mode: str, query_title: str | None = None) -> list[dict]:
    authors = [a for a in rec['authors'].split('; ') if a]
    params = {'query.bibliographic': query_title or rec['title'], 'rows': 5,
              'select': 'DOI,title,container-title,issued,author,type'}
    if mode == 'author' and authors:
        params['query.author'] = authors[0]
    if mode == 'final':
        params['filter'] = 'type:book-chapter' if rec['record_type'] == 'chapter' else 'type:journal-article'
        params['rows'] = 10
        if authors:
            params['query.author'] = authors[0]
    if os.getenv('CROSSREF_MAILTO'):
        params['mailto'] = os.environ['CROSSREF_MAILTO']
    suffix = '' if mode == 'author' else f'.{mode}2' if mode == 'final' else f'.{mode}'
    if rec.get('corrected'):
        suffix += '.corrected'
    payload = fetch_json('https://api.crossref.org/works?' + urlencode(params),
                         CACHE / 'crossref' / f"{rec['seed_id']}{suffix}.json", pause=0.3)
    truncated = 'title_truncated' in rec['flags']
    out = []
    for item in payload.get('message', {}).get('items', []):
        title = html.unescape(re.sub(r'<[^>]+>', '', (item.get('title') or [''])[0]))
        year = ((item.get('issued') or {}).get('date-parts') or [[None]])[0][0]
        c = {
            'doi': item.get('DOI', '').lower(), 'cr_title': re.sub(r'\s+', ' ', title).strip(), 'cr_year': year,
            'cr_journal': html.unescape((item.get('container-title') or [''])[0]), 'cr_type': item.get('type', ''),
            'cr_authors': '; '.join(f"{a.get('given', '')} {a.get('family', '')}".strip() or a.get('name', '')
                                    for a in item.get('author', [])),
            'title_sim': round(title_similarity(rec['title'], title, truncated), 3),
            'author_hit': author_hit(authors, item.get('author', [])),
            'year_diff': abs(year - int(rec['year'])) if year else 99,
        }
        out.append(c)
    return out


def classify(c: dict | None) -> str:
    if c is None:
        return 'unmatched'
    if c['title_sim'] >= 0.92 and c['author_hit'] and c['year_diff'] <= 3:
        return 'matched'
    if c['title_sim'] >= 0.85 and (c['author_hit'] or c['year_diff'] <= 1):
        return 'probable'
    return 'unmatched'


def best_of(cands: list[dict], prefer_final: bool = True) -> dict | None:
    def key(c):
        return (c['title_sim'] >= 0.85, c['author_hit'], prefer_final and not is_working_paper(c),
                c['title_sim'] >= 0.92, -min(c['year_diff'], 10), c['title_sim'])
    return max(cands, key=key) if cands else None


def crossref_match(rec: dict) -> dict:
    best = best_of(crossref_candidates(rec, 'author'))
    if classify(best) != 'matched':
        alt = best_of(crossref_candidates(rec, 'title'))
        rank = {'matched': 2, 'probable': 1, 'unmatched': 0}
        if alt and (rank[classify(alt)], alt['title_sim']) > (rank[classify(best)], best['title_sim'] if best else 0):
            best = alt
    wp_doi = ''
    if best and classify(best) != 'unmatched' and is_working_paper(best):
        # Search with the working paper's full title (the seed title may be truncated),
        # and accept a journal version whose main title matches, by an overlapping author.
        finals = [c for c in crossref_candidates(rec, 'final', best['cr_title'])
                  if not is_working_paper(c) and c['author_hit'] and same_work_title(best['cr_title'], c['cr_title'])]
        if finals:
            final = min(finals, key=lambda c: (c['year_diff'], -c['title_sim']))
            final['title_sim'] = max(final['title_sim'], best['title_sim'] - 0.01)
            wp_doi, best = best['doi'], final
    status = classify(best)
    if status == 'unmatched':
        return {'match_status': status, **{f'candidate_{k}': v for k, v in (best or {}).items()}}
    return {'match_status': status, **best, 'working_paper_doi': wp_doi}


def openalex_record(w: dict) -> dict:
    return {
        'openalex_id': (w.get('id') or '').replace('https://openalex.org/', ''),
        'openalex_doi': (w.get('doi') or '').replace('https://doi.org/', '').lower(),
        'oa_title': w.get('display_name', ''), 'oa_year': w.get('publication_year', ''),
        'oa_authors': '; '.join(a['author']['display_name'] for a in w.get('authorships', []) if a.get('author')),
        'oa_cited_by_count': w.get('cited_by_count', ''), 'oa_type': w.get('type', ''),
        'oa_is_oa': (w.get('open_access') or {}).get('is_oa', ''),
        'oa_url': (w.get('open_access') or {}).get('oa_url') or '',
    }


def openalex_params(extra: dict) -> dict:
    p = dict(extra, select='id,doi,display_name,publication_year,cited_by_count,authorships,open_access,type')
    if os.getenv('OPENALEX_API_KEY'):
        p['api_key'] = os.environ['OPENALEX_API_KEY']
    if os.getenv('OPENALEX_EMAIL'):
        p['mailto'] = os.environ['OPENALEX_EMAIL']
    return p


def crossref_by_doi(rec: dict, doi: str) -> dict:
    payload = fetch_json(f'https://api.crossref.org/works/{quote(doi, safe="/")}',
                         CACHE / 'crossref' / f"{rec['seed_id']}.doi.json", pause=0.3)
    item = payload.get('message', {})
    title = html.unescape(re.sub(r'<[^>]+>', '', (item.get('title') or [''])[0]))
    year = ((item.get('issued') or {}).get('date-parts') or [[None]])[0][0]
    return {'match_status': 'matched', 'doi': doi.lower(), 'cr_title': title, 'cr_year': year,
            'cr_journal': html.unescape((item.get('container-title') or [''])[0]), 'cr_type': item.get('type', ''),
            'cr_authors': '; '.join(f"{a.get('given', '')} {a.get('family', '')}".strip() for a in item.get('author', [])),
            'title_sim': round(title_similarity(rec['title'], title, False), 3),
            'author_hit': author_hit(rec['authors'].split('; '), item.get('author', [])),
            'year_diff': abs(year - int(rec['year'])) if year else 99, 'working_paper_doi': ''}


def openalex_title_search(rec: dict) -> dict:
    """Fallback for papers with no Crossref DOI (e.g. pre-1999 AER articles on JSTOR)."""
    y = int(rec['year'])
    title = re.sub(r'[,:;?!|()]', ' ', rec['title'])
    params = openalex_params({'filter': f'title.search:{title},publication_year:{y - 2}-{y + 2}', 'per-page': 5})
    params['select'] += ',primary_location'
    payload = fetch_json('https://api.openalex.org/works?' + urlencode(params),
                         CACHE / 'openalex' / f"title-{rec['seed_id']}{'.corrected' if rec.get('corrected') else ''}.json", pause=1.0)
    seed_authors = [a for a in rec['authors'].split('; ') if a]
    for w in payload.get('results', []):
        names = [{'family': a['author']['display_name']} for a in w.get('authorships', []) if a.get('author')]
        sim = title_similarity(rec['title'], w.get('display_name', ''), 'title_truncated' in rec['flags'])
        if sim >= 0.92 and author_hit(seed_authors, names):
            out = openalex_record(w)
            out['landing_url'] = ((w.get('primary_location') or {}).get('landing_page_url') or '')
            return {'match_status': 'matched_openalex_only', 'title_sim': round(sim, 3), **out}
    return {}


def openalex_by_doi(dois: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for i in range(0, len(dois), 50):
        batch, page = dois[i:i + 50], 1
        while True:
            params = openalex_params({'filter': 'doi:' + '|'.join(batch), 'per-page': 50, 'page': page})
            payload = fetch_json('https://api.openalex.org/works?' + urlencode(params),
                                 CACHE / 'openalex' / f'doi-batch-{i // 50:03d}-{len(batch)}-p{page}.json', pause=1.0)
            for w in payload.get('results', []):
                doi = (w.get('doi') or '').replace('https://doi.org/', '').lower()
                if doi in batch:
                    found[doi] = openalex_record(w)
            if page * 50 >= payload.get('meta', {}).get('count', 0):
                break
            page += 1
    for doi in [d for d in dois if d not in found]:
        payload = fetch_json(f'https://api.openalex.org/works/doi:{quote(doi, safe="/")}?' + urlencode(openalex_params({})),
                             CACHE / 'openalex' / f"single-{re.sub(r'[^a-z0-9]+', '_', doi)}.json", pause=0.5)
        if not payload.get('not_found') and payload.get('id'):
            found[doi] = openalex_record(payload)
    return found


def main() -> None:
    records = list(csv.DictReader(SRC.open(encoding='utf-8-sig')))
    corrections: dict[str, list[dict]] = {}
    if CORRECTIONS.exists():
        for c in csv.DictReader(CORRECTIONS.open(encoding='utf-8-sig')):
            corrections.setdefault(c['seed_id'], []).append(c)
    unknown = set(corrections) - {r['seed_id'] for r in records}
    assert not unknown, f'corrections.csv refers to unknown seed_ids: {unknown}'
    for rec in records:
        for c in corrections.get(rec['seed_id'], []):
            if c['action'] in ('set_title', 'set_authors'):
                field = c['action'].removeprefix('set_')
                rec[f'seed_{field}'] = rec[field]
                rec[field], rec['corrected'] = c['value'], 'yes'

    print(f'Crossref: matching {len(records)} records (cached responses are reused)...', flush=True)
    for n, rec in enumerate(records, 1):
        acts = {c['action']: c['value'] for c in corrections.get(rec['seed_id'], [])}
        if 'set_doi' in acts:
            rec.update(crossref_by_doi(rec, acts['set_doi']))
        elif 'reject_match' in acts:
            rec['match_status'] = 'unmatched'
        else:
            rec.update(crossref_match(rec))
        if n % 50 == 0:
            print(f'  {n}/{len(records)}', flush=True)

    dois = sorted({r['doi'] for r in records if r['match_status'] != 'unmatched'})
    print(f'OpenAlex: looking up {len(dois)} DOIs...', flush=True)
    oa = openalex_by_doi(dois)
    unmatched = [r for r in records if r['match_status'] == 'unmatched']
    print(f'OpenAlex: title search for {len(unmatched)} records without a DOI match...', flush=True)
    for rec in unmatched:
        rec.update(openalex_title_search(rec))

    for rec in records:
        notes = []
        if rec['seed_id'] in corrections:
            notes.append('hand_corrected')
        if rec['match_status'] not in ('unmatched', 'matched_openalex_only'):
            rec.update(oa.get(rec['doi'], {}))
            if norm(rec['title']) != norm(rec['cr_title']):
                notes.append('title_differs')
            if is_working_paper(rec):
                notes.append('only_working_paper_version_found')
            if rec['year_diff'] not in (0, 99):
                notes.append('year_differs')
            j1, j2 = norm(rec['journal']).removeprefix('the'), norm(rec['cr_journal']).removeprefix('the')
            j1 = JOURNAL_ALIASES.get(j1, j1)
            if j2 and j1[:15] not in j2 and j2[:15] not in j1:
                notes.append('journal_differs')
            if not rec.get('openalex_id'):
                notes.append('not_in_openalex')
            elif rec.get('openalex_doi') and rec['openalex_doi'] != rec['doi']:
                notes.append('openalex_merged_with_other_version')
        rec['review_notes'] = ';'.join(notes)

    by_doi: dict[str, list[str]] = {}
    for rec in records:
        if rec.get('doi') and rec['match_status'] not in ('unmatched', 'matched_openalex_only'):
            by_doi.setdefault(rec['doi'], []).append(rec['seed_id'])
    for rec in records:
        others = [s for s in by_doi.get(rec.get('doi', ''), []) if s != rec['seed_id']] if rec['match_status'] not in ('unmatched', 'matched_openalex_only') else []
        if others:
            rec['review_notes'] = ';'.join(filter(None, [rec['review_notes'], 'same_doi_as:' + ','.join(others)]))

    fields: list[str] = []
    for rec in records:
        fields += [k for k in rec if k not in fields]
    with OUT.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(records)

    status = {s: sum(r['match_status'] == s for r in records) for s in ('matched', 'probable', 'matched_openalex_only', 'unmatched')}
    print(f'Wrote {OUT.relative_to(ROOT)}')
    print('Match status:', status)
    print('In OpenAlex:', sum(bool(r.get('openalex_id')) for r in records))
    print('Working-paper version replaced by journal version:', sum(bool(r.get('working_paper_doi')) for r in records))
    notes: dict[str, int] = {}
    for r in records:
        for x in filter(None, r['review_notes'].split(';')):
            x = x.split(':')[0]
            notes[x] = notes.get(x, 0) + 1
    print('Review notes:', notes)


if __name__ == '__main__':
    main()
