"""Optional metadata-only candidate discovery, not automatic publication.

Uses the public OpenAlex API and generates data/candidates.jsonl for manual review.
Set OPENALEX_EMAIL to identify yourself politely. Requires Internet access.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'candidates.jsonl'
QUERIES = ['intergenerational mobility', 'inheritance wealth inequality', 'parental transfers']
seen = set()
records = []
for query in QUERIES:
    params = {'search': query, 'per-page': 25, 'filter': 'from_publication_date:2025-01-01', 'select': 'id,doi,title,publication_year,publication_date,authorships,primary_location,ids'}
    if os.getenv('OPENALEX_EMAIL'):
        params['mailto'] = os.getenv('OPENALEX_EMAIL')
    req = Request('https://api.openalex.org/works?' + urlencode(params), headers={'User-Agent':'KinshipResearchPrototype/0.1 (metadata research discovery)'})
    with urlopen(req, timeout=30) as response:
        payload = json.load(response)
    for work in payload.get('results',[]):
        uid = work.get('doi') or work.get('id')
        if not uid or uid in seen:
            continue
        seen.add(uid)
        records.append({'source_query': query, 'openalex_id':work.get('id'), 'doi':work.get('doi'), 'title':work.get('title'), 'year':work.get('publication_year'), 'date':work.get('publication_date'), 'authors':[x.get('author',{}).get('display_name') for x in work.get('authorships',[])], 'venue':(work.get('primary_location') or {}).get('source',{}), 'review_status':'UNREVIEWED'})
OUT.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in records),encoding='utf8')
print(f'Wrote {len(records)} unreviewed candidates to {OUT}. Do not auto-publish.')
