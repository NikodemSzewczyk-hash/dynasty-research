"""Offline sanity checks for curated paper and source records.

Usage: python scripts/validate.py
"""
import json
from pathlib import Path
from urllib.parse import urlparse
ROOT = Path(__file__).resolve().parents[1]
papers = json.loads((ROOT/'data/papers.json').read_text(encoding='utf8'))
sources = json.loads((ROOT/'data/sources.json').read_text(encoding='utf8'))
ids, dois = set(), set()
for p in papers:
    for k in ['id','title','authors','year','source','status','paper_url','topics','takeaway','description','method']:
        assert p.get(k), f'{p.get("id", "unknown")}: missing {k}'
    assert p['id'] not in ids, f'duplicate id {p["id"]}'
    ids.add(p['id'])
    assert p['year'] >= 1950 and p['year'] <= 2026, f'invalid year {p["id"]}'
    assert p['paper_url'].startswith('https://'), f'invalid URL {p["id"]}'
    if p.get('doi'):
        doi=p['doi'].lower()
        assert doi not in dois, f'duplicate DOI {doi}'
        dois.add(doi)
for family in ['journals','repositories','researchers']:
    names=set()
    for source in sources[family]:
        assert source['name'] not in names
        assert source['tier'] in ['A','B','C']
        names.add(source['name'])
print(f'OK: {len(papers)} papers, {sum(len(x) for x in sources.values())} source candidates, no duplicate paper IDs or DOIs.')
