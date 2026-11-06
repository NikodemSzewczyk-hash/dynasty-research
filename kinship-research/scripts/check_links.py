"""Print paper links for manual verification; no automated crawling.

Use this list to validate authoritative source URLs during editorial review.
"""
from pathlib import Path
import json
p=Path(__file__).resolve().parents[1]
for x in json.loads((p/'data/papers.json').read_text(encoding='utf8')):
    print(f'{x["id"]}\t{x["paper_url"]}')
