"""Import the hand-compiled intergenerational paper list (Excel) into a clean CSV.

The Excel file is the untouched original. This script only fixes mechanical problems
(whitespace, Unicode normalization, journal-name spelling, known garbled names, exact
duplicate rows) and *flags* everything else for the enrichment step or a reviewer.
It never invents titles, authors or identifiers.

Standard library only. Usage:
    python scripts/import_seed.py [path/to/intergenerational_dataset.xlsx]
Output: registry/seed/intergenerational_dataset.clean.csv (UTF-8 with BOM, opens in Excel)
"""
from __future__ import annotations

import csv
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / 'registry' / 'seed' / 'intergenerational_dataset.xlsx'
OUT = ROOT / 'registry' / 'seed' / 'intergenerational_dataset.clean.csv'
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}

# Spelling variants and abbreviations -> one canonical name (matches data/sources.json where possible).
JOURNALS = {
    'AER': 'American Economic Review',
    'QJE': 'Quarterly Journal of Economics',
    'JPE': 'Journal of Political Economy',
    'REStat': 'Review of Economics and Statistics',
    'REStud': 'Review of Economic Studies',
    'JEP': 'Journal of Economic Perspectives',
    'JEL': 'Journal of Economic Literature',
    'JLE': 'Journal of Labor Economics',  # Becker & Tomes 1986 is J. Labor Econ., not J. Law & Econ.
    'The Economic Journal': 'Economic Journal',
    'The European Economic Review': 'European Economic Review',
    'The Scandinavian Journal of Economics': 'Scandinavian Journal of Economics',
    'Scandinavian Joournal of Economics': 'Scandinavian Journal of Economics',
    'The Journal of Economic Inequality': 'Journal of Economic Inequality',
    'The Journal of Development Studies': 'Journal of Development Studies',
    'The B.E Journal of Economic Analysis and Policy': 'B.E. Journal of Economic Analysis & Policy',
    'The B.E. Journal of Economic Analysis & Policy': 'B.E. Journal of Economic Analysis & Policy',
    'The B.E Journal of Economic Analysis': 'B.E. Journal of Economic Analysis & Policy',
    'Journal of Economic Analysis and Policy': 'B.E. Journal of Economic Analysis & Policy',
    'Economics&Human Biology': 'Economics & Human Biology',
    'Journal of Economics Behavior & Organization': 'Journal of Economic Behavior & Organization',
}
# Outlets that are books or handbook chapters rather than journal articles.
CHAPTER_OUTLETS = re.compile(r'Handbook|Dynamics of Inequality and Poverty|Schools and the Equal Opportunity Problem|Research in Labor Economics')
# Garbled author names verified by inspection of the original file.
NAME_FIXES = {'Kostl': 'Kostøl', 'RodrÌguez': 'Rodríguez'}
# Titles visibly cut off in the original; the enrichment step recovers the full title.
TRUNCATED = re.compile(r'(\b(from|in|of|the|and|for|to|on|with|by)|[:,\-])$', re.I)
KNOWN_TRUNCATED = {'the intergenerational transmission'}


def read_xlsx(path: Path) -> list[list[str | None]]:
    z = zipfile.ZipFile(path)
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS):
            shared.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    first = wb.find('m:sheets', NS)[0]
    sheet_path = 'xl/' + rels[first.get('{%s}id' % NS['r'])].lstrip('/').replace('xl/', '')
    rows = []
    for row in ET.fromstring(z.read(sheet_path)).iter('{%s}row' % NS['m']):
        vals = {}
        for c in row.findall('m:c', NS):
            col = 0
            for ch in re.match(r'[A-Z]+', c.get('r')).group():
                col = col * 26 + ord(ch) - 64
            v = c.find('m:v', NS)
            if c.get('t') == 's' and v is not None:
                val = shared[int(v.text)]
            elif c.get('t') == 'inlineStr':
                val = ''.join(x.text or '' for x in c.iter('{%s}t' % NS['m']))
            else:
                val = v.text if v is not None else None
            vals[col - 1] = val
        if vals:
            rows.append([vals.get(i) for i in range(max(vals) + 1)])
    return rows


def clean_text(s: str | None) -> str:
    s = unicodedata.normalize('NFC', s or '').replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def norm_key(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', s).lower())


TRANSLIT = str.maketrans({'ø': 'o', 'Ø': 'O', 'æ': 'ae', 'Æ': 'AE', 'ß': 'ss', 'ł': 'l', 'Ł': 'L'})


def slug(s: str) -> str:
    s = unicodedata.normalize('NFKD', s.translate(TRANSLIT)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    rows = read_xlsx(src)
    header, data = rows[0], rows[1:]
    expected = ['Journal', 'Authors', 'Citations', 'Year', 'Years_since_publication',
                'Citations_weighted', 'Title', 'Evidence', 'Data']
    assert [clean_text(h) for h in header] == expected, f'Unexpected columns: {header}'

    records, seen, dropped, ids = [], {}, [], set()
    for excel_row, r in enumerate(data, start=2):
        r = [clean_text(x) for x in r] + [''] * (9 - len(r))
        journal_raw, authors_raw, cites, year, _, cites_w, title, evidence, data_type = r[:9]
        authors = authors_raw
        for bad, good in NAME_FIXES.items():
            authors = authors.replace(bad, good)
        author_list = [a.strip() for a in authors.split(',') if a.strip()]
        flags = []
        if any('et al' in a for a in author_list):
            flags.append('authors_incomplete')
            author_list = [re.sub(r'\s*et\.? al\.*$', '', a).strip() for a in author_list]
            author_list = [a for a in author_list if a]
        if authors != authors_raw:
            flags.append('author_name_fixed')
        if TRUNCATED.search(title) or title.lower() in KNOWN_TRUNCATED:
            flags.append('title_truncated')
        journal = JOURNALS.get(journal_raw, journal_raw)
        record_type = 'chapter' if CHAPTER_OUTLETS.search(journal) else 'article'

        key = (norm_key(title), int(float(year)), norm_key(' '.join(sorted(author_list))))
        if key in seen:
            dropped.append((excel_row, seen[key], title))
            continue
        seen[key] = excel_row

        base = f"{slug(author_list[0].split()[-1]) if author_list else 'anon'}-{int(float(year))}-{'-'.join(slug(title).split('-')[:4])}"
        sid, n = base, 2
        while sid in ids:
            sid, n = f'{base}-{n}', n + 1
        ids.add(sid)
        records.append({
            'seed_id': sid, 'excel_row': excel_row, 'record_type': record_type,
            'title': title, 'authors': '; '.join(author_list), 'year': int(float(year)),
            'journal': journal, 'journal_raw': journal_raw,
            'evidence': evidence, 'data': data_type,
            'citations_2025': int(float(cites)), 'citations_weighted_2025': round(float(cites_w), 2),
            'flags': ';'.join(flags),
        })

    # Same title, different year/authors: likely versions of one work, resolved at enrichment.
    by_title: dict[str, list[dict]] = {}
    for rec in records:
        by_title.setdefault(norm_key(rec['title']), []).append(rec)
    for group in by_title.values():
        if len(group) > 1 and len({g['authors'] for g in group}) == 1 or (
                len(group) > 1 and len({frozenset(g['authors'].split('; ')) for g in group}) == 1):
            for g in group:
                g['flags'] = ';'.join(filter(None, [g['flags'], 'possible_version_duplicate']))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)

    print(f'Read {len(data)} rows from {src.name}; wrote {len(records)} records to {OUT.relative_to(ROOT)}')
    print(f'Dropped {len(dropped)} exact duplicates: ' + '; '.join(f'row {a} = row {b} ({t[:50]})' for a, b, t in dropped))
    counts: dict[str, int] = {}
    for rec in records:
        for fl in filter(None, rec['flags'].split(';')):
            counts[fl] = counts.get(fl, 0) + 1
    print('Flags:', counts)
    print('Record types:', {t: sum(r['record_type'] == t for r in records) for t in ('article', 'chapter')})


if __name__ == '__main__':
    main()
