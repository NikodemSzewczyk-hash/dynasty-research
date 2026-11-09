# Seed list: hand-compiled intergenerational papers

This folder holds the import of `intergenerational_dataset.xlsx`, a list of 405 papers compiled by hand in 2025. The workbook in this folder is the untouched original.

Records reach the public discovery index only as **unreviewed metadata** (`review_status: pending`, `evidence_level: metadata_only`, `collection: seedlist`), like the verified-source pilot. Nothing here writes `content/papers/` or changes the 12 curated papers.

## Pipeline

Run from `kinship-research/`. Standard library only; API responses are cached in `cache/` (git-ignored), so re-runs are free and reproducible.

```
registry/seed/intergenerational_dataset.xlsx
  └─ python scripts/import_seed.py       → registry/seed/intergenerational_dataset.clean.csv
       └─ python scripts/enrich_seed.py      (+ corrections.csv)
                                         → registry/seed/intergenerational_dataset.enriched.csv
            └─ registry/seed/scope_coding.csv  (scope decision per record, docs/scope.md)
                 └─ python scripts/export_seed_list.py  → registry/seed-list.jsonl
                      └─ python scripts/publish_pilot_discovery.py → static/data/discovery-index.json
```

`scripts/fetch_abstracts.py` pulls OpenAlex abstracts into `cache/abstracts.json` for scope coding only. Abstracts are never committed or published.

## Files

| File | What it is |
|---|---|
| `intergenerational_dataset.clean.csv` | 403 records after mechanical cleaning. **What it fixes:** whitespace and Unicode, 2 exact duplicates dropped, journal names standardized, 3 garbled names fixed. **What it flags:** incomplete author lists, truncated titles, possible version duplicates. Has a stable `seed_id`. |
| `corrections.csv` | Hand-checked fixes applied before matching. Actions: `set_title`, `set_authors`, `set_doi`, `set_url` (verified https page for a work with no DOI), `reject_match`. Each row says why. Add a row here instead of editing the workbook or the outputs. |
| `intergenerational_dataset.enriched.csv` | Cleaned records plus Crossref and OpenAlex matches. Opens in Excel (UTF-8 with BOM). |
| `scope_coding.csv` | Scope decision for every record under [`docs/scope.md`](../../docs/scope.md) v0.1: tier, rule IDs, channels, generations, advantage, confidence and a one-line rationale. First pass by `model:claude-opus-5-5` from titles and OpenAlex abstracts (abstracts were available for 299 of 403). Reviewers fill `reviewed_by`, `review_decision` (`agree` / `change:<tier>`) and `review_note`. |
| `../seed-list.jsonl` | The `core` records with an https link, as discovery candidates. Provenance (scope rules, confidence, coder, codebook version) stays in this file; the public index carries only the standard metadata fields. |

## How matching works

1. **Crossref, title + first author.** If that is weak, retry with the title only, because seed author names are sometimes misspelled or a co-author's first name.
2. **Prefer the journal version.** If the best hit is a working paper (SSRN, NBER, IZA, IMF, World Bank…), search journal articles or chapters with the working paper's full title. Accept a hit whose main title matches and which shares an author. The working-paper DOI is kept in `working_paper_doi`.
3. **OpenAlex by DOI**, in batches of 50, with single lookups for DOIs the batch misses (OpenAlex sometimes merges a journal article with its working paper under the working paper's DOI).
4. **OpenAlex title search** for records with no DOI match (pre-1999 AER articles on JSTOR). These get the status `matched_openalex_only`.

`match_status`: `matched` (title ≥ 0.92 similar, shares an author, year within 3), `probable` (needs a look), `matched_openalex_only`, `unmatched`.

## Scope coding (403 records)

| Tier | Records | Shown in the index |
|---|---|---|
| Core | 367 | Yes, as unreviewed candidates (all with a link) |
| Adjacent | 34 | No |
| Out | 2 | No |

The first pass (363 / 37 / 3) was followed by a second model pass over the 53 flagged records; see the review columns of `scope_coding.csv`. It changed 5 tiers. This is not a human review: `reviewed_by` says so explicitly.

Deduplication against curated, pilot and historical records happens in `publish_pilot_discovery.combine()`: exact DOI first, then exact normalized title + first-author surname (labelled *possible* versions).

## Known open items

- **Pre-DOI AER papers** (Solon 1992, Zimmerman 1992, Loury 1981) have no Crossref record. They link to RePEc article pages set by `set_url` in `corrections.csv`, each checked against title, author, volume, issue and pages (`match_status: matched_url`).
- **`matched_openalex_only` to check:** Goldberger 1989 resolves to a Wisconsin working-paper page; Behrman & Taubman 1976 to a mirror site. Both are linked through their OpenAlex record.
- **Year or journal in the seed list differs** from the published record in about 75 cases, mostly online-first year vs print year, or working-paper year vs publication year. The export uses the matched values.
- **Scope coding has had two model passes but no human review.** Open questions for a human reviewer: whether crime transmission counts as disadvantage (H14; 4 papers would move to core), and whether Bütikofer et al. 2018 (school breakfast) reports effects by family background (H4).
