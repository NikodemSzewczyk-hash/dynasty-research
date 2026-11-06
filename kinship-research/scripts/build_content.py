"""Generate Hugo paper pages from the curated paper metadata JSON.

Do not edit generated `content/papers/*.md` directly; edit data/papers.json.
No external dependencies. Usage: python scripts/build_content.py
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'papers.json'
OUT = ROOT / 'content' / 'papers'


def yaml_string(x: str) -> str:
    return json.dumps(x, ensure_ascii=False)


def build() -> None:
    papers = json.loads(DATA.read_text(encoding='utf-8'))
    OUT.mkdir(parents=True, exist_ok=True)
    for p in papers:
        props = ['title', 'year', 'source', 'status', 'doi', 'paper_url', 'working_paper_url', 'takeaway', 'method']
        lines = ['---']
        for key in props:
            if key in p:
                value = p[key]
                lines.append(f'{key}: {value}' if isinstance(value, int) else f'{key}: {yaml_string(str(value))}')
        for arr in ['authors', 'topics']:
            lines.append(f'{arr}:')
            lines.extend(f'  - {yaml_string(v)}' for v in p[arr])
        lines.extend(['---', '', '## About this study', '', p['description'], '', '## Editorial context', '', p['takeaway'], '', '## Original source', '', f'[{p["source"]}]({p["paper_url"]})', ''])
        (OUT / (p['id'] + '.md')).write_text('\n'.join(lines), encoding='utf-8')
    print(f'Generated {len(papers)} paper pages in {OUT}')

if __name__ == '__main__':
    build()
