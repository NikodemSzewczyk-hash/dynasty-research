# dynasty_

A static research observatory on how economic advantage and inequality are created and
transmitted across generations (families, kinship, mobility, wealth and inheritance,
human capital, policy). Hugo site + a stdlib-only Python/SQLite metadata pipeline,
deployed on Netlify.

The Hugo root is `kinship-research/` (legacy name, kept so hosting config doesn't break).
**Run every command below from `kinship-research/`.**

## Commands

```bash
python scripts/validate.py                    # check curated records (data/papers.json)
python -m unittest discover -s tests -v       # offline tests, no network
python scripts/build_content.py               # regenerate the 12 curated paper pages
hugo server -D                                # local preview at http://localhost:1313/
hugo --minify                                 # production build into public/

python scripts/dynasty.py seed                # build local SQLite (data/dynasty.sqlite, gitignored)
python scripts/dynasty.py review list --status pending
python scripts/dynasty.py export --site-root /tmp/dynasty-hugo-test   # always export to a scratch dir first
python scripts/pilot23_ingest.py --mode smoke --snapshot /tmp/s.jsonl --state /tmp/st.json --report /tmp/r.json --no-db
python scripts/pilot23_ingest.py --mode backfill --max-per-source 200000 --report registry/pilot23-report.json
python scripts/publish_pilot_discovery.py     # rebuild discovery index and source catalog from registry/snapshot
python scripts/repair_doi_years.py            # dry run; --write fixes stored years that contradict DOI conventions
python scripts/audit_autocheck.py check --cache DIR   # offline metadata pre-check of the audit sample (fetch first)

# Hand-compiled seed list (registry/seed/README.md); cached, so re-runs make no API calls
python scripts/import_seed.py                 # workbook -> registry/seed/*.clean.csv
python scripts/enrich_seed.py                 # Crossref + OpenAlex matching (+ corrections.csv)
python scripts/export_seed_list.py            # core records -> registry/seed-list.jsonl, then run publish_pilot_discovery.py
```

CI (`.github/workflows/build.yml`) runs on Python 3.12 and Hugo 0.159.2. It runs the
validator and tests, smoke-tests seed and export (expects exactly 12 records),
regenerates pages, fails if `content/papers/` changed (`git diff --exit-code`), then
builds Hugo and checks the HTML.

## Layout

| Path | Role |
|---|---|
| `data/papers.json` | The 12 curated papers, the source for `content/papers/*.md` |
| `data/sources.json`, `data/source-catalog.json` | Sources page |
| `registry/source_manifest.json` | 128 local source IDs. Only the verified sources listed in `registry/pilot23-verification.json` (24) are enabled |
| `registry/snapshot/*.jsonl` | Unreviewed metadata from the verified sources, one shard per primary source (1990–present) |
| `registry/pilot23-*.json` | Verification provenance, checkpoints and per-source coverage, last ingestion report |
| `registry/candidates-v03.jsonl` | 3,477-record unreviewed historical Crossref corpus |
| `registry/seed/`, `registry/seed-list.jsonl` | Hand-compiled 403-paper seed list, its Crossref/OpenAlex matches and scope coding; core records exported as unreviewed candidates |
| `docs/scope.md` | Scope codebook: what counts as research on how advantage passes between generations (tiers, rule IDs, hard cases) |
| `static/data/discovery-index.json` | Public index (curated, pilot, seed-list and historical rows) |
| `scripts/dynasty.py`, `scripts/dynasty_data/` | Pipeline CLI and package (schema, identity/dedup, providers, redif, nber, catalog, notes) |
| `scripts/pilot23_ingest.py` | Bounded ingestion from the verified sources (smoke/weekly/backfill from 1990), with per-source completeness checks |
| `layouts/`, `static/css/site.css`, `static/js/` | Site design and the client-side discovery explorer |
| `docs/` | Per-stage docs: read the relevant one before changing that stage |

The weekly `pilot23-sync.yml` job (Monday 09:20 UTC) pushes `bot/pilot23-weekly` and opens a
**review PR**. It never commits to main. Secrets: `OPENALEX_API_KEY`; repo variable
`DYNASTY_CONTACT_EMAIL`.

## Editorial guardrails (do not weaken)

- Never invent citations, findings, summaries, citation counts or ratings. Takeaways
  must be written by a person. Never promote a provider's abstract to an editorial conclusion.
- Discovery ≠ endorsement ≠ reading. Imported metadata is always labelled *unreviewed*.
  A reading note reaches `evidence_checked` only with PDF provenance and claims cited by
  page (`scripts/notes.py`).
- Importers never write `content/papers/`. No auto-publish, no auto-merge, and fuzzy matches
  need an explicit `--merge-into` or `--force-new`. The archive tracks an intellectual
  *work* with multiple *versions* (working paper and journal article).
- Never enable a source from a guessed identifier. Verify ISSNs at Crossref or the publisher,
  and OpenAlex authors by affiliation or ORCID (e.g. Sandra E. Black was excluded because
  the top match was a different person).
- Respect access controls and rights: no workarounds for HTTP 403s (NBER TSV and CEPR
  listings from CI), no PDF scraping, no republishing full text or abstracts, and never
  print or commit API keys.
- Use each provider's documented bulk route, never its website. RePEc asks users not to
  scrape IDEAS pages, so CEPR and IZA come from ReDIF archives (`dynasty_data/redif.py`).
  ReDIF author e-mails, workplaces and abstracts are dropped, and PDFs are never fetched.
  See `kinship-research/docs/source-access.md`.
- Report coverage honestly: a network failure does not mean "zero new papers", a cap that
  is hit is flagged, and a bounded window is not a full backfill.

## Gotchas

- Hugo parses every file in `data/` and can't read JSONL, so keep corpora in `registry/`.
  Keep API caches outside `data/` as well.
- On a Python build without root certificates (e.g. the python.org macOS installer), HTTPS
  calls fail with `CERTIFICATE_VERIFY_FAILED`. Run with `SSL_CERT_FILE=/etc/ssl/cert.pem`;
  never disable verification.
- Crossref `published` can be a publisher's re-deposit date. IFS working papers showed
  2025–2026 for papers from 1995–2017. `doi_convention_year()` in `providers.py` corrects
  IFS DOIs. OpenAlex `publication_year` mirrors Crossref `created`, so it is not an
  independent check on the year. See `docs/metadata-audit.md`.
- Templates need `index` lookups for hyphenated data keys (e.g. `discovery-pilot-report`).
- HTML smoke checks must tolerate Hugo's minified attributes.
- Some workflows fire only on specific branches (e.g. `feat/discovery-pilot-live`).
  Feature work goes on `feat/*`, `design/*` or `fix/*` branches and is merged by PR.
- `dynasty.py export` overwrites pages with the same work ID. Don't export into the live
  tree until the move from the legacy JSON workflow has been approved.
