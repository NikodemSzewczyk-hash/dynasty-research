"""Fetch abstracts from OpenAlex for the enriched seed list, for internal scope coding.

Abstracts are often under publisher copyright: they are stored only in the git-ignored
cache (registry/seed/cache/abstracts.json) and are never written into site content.

Standard library only. Usage: python scripts/fetch_abstracts.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import urlencode

from enrich_seed import CACHE, OUT as ENRICHED, fetch_json, openalex_params

DEST = CACHE / 'abstracts.json'


def rebuild(inverted: dict | None) -> str:
    if not inverted:
        return ''
    positions = [(pos, word) for word, poss in inverted.items() for pos in poss]
    return ' '.join(word for _, word in sorted(positions))


def main() -> None:
    rows = list(csv.DictReader(ENRICHED.open(encoding='utf-8-sig')))
    ids = sorted({r['openalex_id'] for r in rows if r.get('openalex_id')})
    abstracts: dict[str, str] = {}
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        params = openalex_params({'filter': 'openalex:' + '|'.join(batch), 'per-page': 50})
        params['select'] = 'id,abstract_inverted_index'
        payload = fetch_json('https://api.openalex.org/works?' + urlencode(params),
                             CACHE / 'openalex' / f'abstracts-{i // 50:03d}-{len(batch)}.json', pause=1.0)
        for w in payload.get('results', []):
            abstracts[w['id'].replace('https://openalex.org/', '')] = rebuild(w.get('abstract_inverted_index'))
    by_seed = {r['seed_id']: abstracts.get(r.get('openalex_id', ''), '') for r in rows}
    DEST.write_text(json.dumps(by_seed, ensure_ascii=False, indent=0), encoding='utf-8')
    have = sum(bool(v) for v in by_seed.values())
    print(f'Abstracts for {have}/{len(rows)} records -> {DEST.relative_to(Path(__file__).resolve().parents[1])}')


if __name__ == '__main__':
    main()
