#!/usr/bin/env python3
"""Export the scope-coded seed list as unreviewed discovery candidates.

Input:  registry/seed/scope_coding.csv            scope decision per record (docs/scope.md)
        registry/seed/intergenerational_dataset.enriched.csv   Crossref/OpenAlex matches
Output: registry/seed-list.jsonl                  one candidate per line, read by
                                                  scripts/publish_pilot_discovery.py

Guardrails (see CLAUDE.md):
  * Every record is review_status=pending, evidence_level=metadata_only. Scope coding is a
    screening decision, not an editorial endorsement; nothing here writes content/papers/.
  * Only records coded `core` are exported; adjacent/out stay in scope_coding.csv.
  * A record without an https link (e.g. pre-DOI AER articles) is held back, never guessed.
  * No deduplication here: publish_pilot_discovery.combine() merges by DOI, then by exact
    title + first-author surname, against curated, pilot and historical records.

Standard library only. Usage: python scripts/export_seed_list.py
"""
from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'registry' / 'seed'
OUT = ROOT / 'registry' / 'seed-list.jsonl'

# Scope channels (docs/scope.md section 4) -> discovery-index subject labels. Reuses the
# index's existing labels where they mean the same thing.
CHANNEL_TOPICS = {
    'A': 'Intergenerational mobility',
    'B1': 'Wealth and inheritance',
    'B2': 'Childhood and education',
    'B3': 'Genes, health and endowments',
    'B4': 'Networks and occupations',
    'B5': 'Place and opportunity',
    'B6': 'Family structure',
    'B7': 'Preferences and norms',
    'C': 'Institutions and policy',
    'D': 'Data, methods and theory',
}
WP_NOTE = 'only_working_paper_version_found'


def clean_title(*candidates: str) -> str:
    """First candidate that is not ALL CAPS; strip footnote stars and stray whitespace."""
    cleaned = [re.sub(r'\s+', ' ', html.unescape(c or '')).strip().rstrip('*').strip() for c in candidates]
    cleaned = [c for c in cleaned if c]
    for c in cleaned:
        if not c.isupper():
            return c
    return cleaned[0].title() if cleaned else ''


def clean_journal(name: str) -> str:
    name = html.unescape(name or '').strip()
    return re.sub(r'^The (?=(Quarterly|Review|Journal|Economic|American|Scandinavian))', '', name)


def https(url: str) -> str:
    return url if isinstance(url, str) and url.startswith('https://') else ''


def export_rows(coding: list[dict], enriched: dict[str, dict]) -> tuple[list[dict], list[str]]:
    rows, held = [], []
    for c in coding:
        if c['scope_tier'] != 'core':
            continue
        e = enriched[c['seed_id']]
        status = e['match_status']
        doi = e.get('doi', '').lower() if status in ('matched', 'probable') else ''
        is_wp = WP_NOTE in e['review_notes']
        if doi:
            url, provider = f'https://doi.org/{doi}', 'crossref'
        elif status == 'matched_url' and https(e.get('landing_url', '')):
            # Hand-verified catalogue page from corrections.csv (set_url), e.g. RePEc for pre-DOI AER.
            url, provider = e['landing_url'], 'repec' if 'repec.org' in e['landing_url'] else 'seedlist'
        elif e.get('openalex_id'):
            landing = https(e.get('landing_url', ''))
            article_page = landing and re.search(r'repec\.org/(a/|article/)', landing)
            url, provider = (landing if article_page else f"https://openalex.org/{e['openalex_id']}"), 'openalex'
        else:
            held.append(c['seed_id'])
            continue
        use_matched = bool(doi) and not is_wp
        wrong_journal = use_matched and 'journal_differs' in e['review_notes'] and e['record_type'] != 'chapter'
        topics = list(dict.fromkeys(CHANNEL_TOPICS[ch] for ch in c['channels'].split(';')))
        rows.append({
            'id': 'seedlist:' + c['seed_id'],
            'title': clean_title(e.get('cr_title') if doi else '', e.get('oa_title'), e['title']),
            'authors': [a.strip() for a in (e.get('oa_authors') or e.get('cr_authors') or e['authors']).split(';') if a.strip()],
            'year': int(e['cr_year']) if use_matched and e.get('cr_year') else int(e['year']),
            'source': clean_journal(e['cr_journal'] if wrong_journal else e['journal']),
            'doi': doi or None,
            'url': url,
            'provider': provider,
            'review_status': 'pending',
            'evidence_level': 'metadata_only',
            'collection': 'seedlist',
            'kind': 'book_chapter' if e['record_type'] == 'chapter' else 'journal_article',
            'topics': topics,
            # Provenance, kept in the JSONL for audit; not copied into the public index.
            'seed_id': c['seed_id'],
            'scope_tier': c['scope_tier'],
            'scope_rules': c['scope_rules'].split(';'),
            'scope_confidence': c['confidence'],
            'scope_coder': c['coder'],
            'codebook_version': c['codebook_version'],
            'match_status': status,
            'working_paper_doi': e.get('working_paper_doi') or None,
            'free_url': https(e.get('oa_url', '')) or None,
            'openalex_id': e.get('openalex_id') or None,
        })
    rows.sort(key=lambda r: r['id'])
    return rows, held


def main() -> int:
    enriched = {r['seed_id']: r for r in csv.DictReader((SEED / 'intergenerational_dataset.enriched.csv').open(encoding='utf-8-sig'))}
    coding = list(csv.DictReader((SEED / 'scope_coding.csv').open(encoding='utf-8-sig')))
    rows, held = export_rows(coding, enriched)
    OUT.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    core = sum(c['scope_tier'] == 'core' for c in coding)
    print(f'{len(coding)} coded records, {core} core; wrote {len(rows)} candidates to {OUT.relative_to(ROOT)}')
    print(f'Held back (no https link yet) {len(held)}: ' + ', '.join(held))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
