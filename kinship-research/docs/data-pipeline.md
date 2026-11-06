# dynasty_ V0.2 — research metadata infrastructure

**Status:** feature branch prototype. The public Hugo site and its 12 existing curated papers remain unchanged until an explicitly approved export. This pipeline is Python 3.12+ and SQLite with **no third-party Python dependencies**.

## What is installed

- `registry/source_manifest.json` — 128 stable, source-typed local IDs (53 journals, 33 working-paper series, 42 researchers) with retrieval plans.
- `scripts/dynasty_data/schema.py` — SQLite tables for sources, works, versions, authors, topics, candidates, editorial decisions, and ingestion runs.
- `scripts/dynasty_data/identity.py` — DOI normalization and conservative title/author/year possible-match detection.
- `scripts/dynasty_data/providers.py` — bounded OpenAlex and Crossref metadata clients.
- `scripts/dynasty_data/catalog.py` — registry/seed imports, review queue, version linking, Hugo export.
- `scripts/dynasty.py` — command-line interface.
- `tests/test_pipeline.py` — offline fixture tests (no Internet needed).
- `.github/workflows/metadata-discovery.yml` — optional manually triggered, non-publishing metadata retrieval; stores a short-lived review artifact.

## Quick start

From `kinship-research/`:

```bash
python scripts/dynasty.py init
python scripts/dynasty.py seed
python scripts/dynasty.py stats
python scripts/dynasty.py sources list --kind journal --limit 10
python -m unittest discover -s tests -v
```

By default, the DB is `data/dynasty.sqlite`, a local **gitignored** file. Re-running `seed` doesn't create duplicate papers or source IDs. Do not commit the SQLite DB. The legacy `data/papers.json` remains the authoritative list for the 12 existing Hugo seed pages until the editorial migration is approved.

## Historical metadata imports

Search a **bounded** historical date interval (no paper is automatically published):

```bash
python scripts/dynasty.py ingest openalex --query "inheritance inequality" --from-date 2000-01-01 --to-date 2026-11-06 --max-records 100
python scripts/dynasty.py ingest crossref --query "intergenerational mobility" --from-date 2000-01-01 --to-date 2026-11-06 --max-records 100
python scripts/dynasty.py review list --status pending --limit 30
```

Set `DYNASTY_CONTACT_EMAIL` for polite API identification. For larger OpenAlex requests, supply `OPENALEX_API_KEY` as an environment variable. The current importer uses bounded **page** pagination; do not assume unlimited free cursor access. Both services can change limits or returned metadata. The Crossref importer searches DOI-bearing works; OpenAlex additionally returns works without DOIs. The importers store metadata and provenance, not copyrighted full texts.

The GitHub Actions **Manual dynasty_ metadata discovery** workflow can execute one run and publish its unreviewed SQLite database as a downloadable workflow artifact. It does **not** update the master DB, make persistent incremental changes, edit the website, or run on a schedule. To combine batches, use a **local persistent database**. Artifacts expire.

## External identifiers — verification gate

The 128 registry IDs are **local slugs**, NOT genuine Crossref ISSNs or OpenAlex author IDs. They start with `retrieval.enabled = false`. Do not enable them by guessing. Verify an ISSN at a journal's website or Crossref; verify an author identity at OpenAlex.

Example after manual verification:

```bash
python scripts/dynasty.py sources verify journal:american-economic-review --key issn --value 0002-8282 --verified-by "Your name"
python scripts/dynasty.py ingest crossref --source-id journal:american-economic-review --from-date 2020-01-01 --to-date 2026-11-06 --max-records 100
```

The example demonstrates syntax, not blanket verification of the registry. For authors, verify `openalex_author_id` and use `ingest openalex --source-id researcher:...`. Institutional working-paper sources still need independently verified feeds and dedicated connectors; they are **not** monitored yet. Source validation is recorded locally in SQLite only; for deployment, review and version-control a verified configuration.

## Review, deduplication, and version linking

The unit of the curated archive is an **intellectual work**, with multiple **versions** (working paper and journal publication). A separate **candidate** row tracks what each provider returned. The importer never writes to `content/papers`.

- Identical canonical DOI or existing provider ID: flagged as **exact**; the reviewer may accept and attach metadata to the existing work.
- Similar title, same first-author surname and nearby year: flagged as **possible**; an explicit `--merge-into` or `--force-new` is required. Fuzzy matching NEVER triggers automatic merge.
- Unmatched: a reviewer must enter an original, human-authored takeaway and at least one topic to publish a **new** work.

```bash
python scripts/dynasty.py review show 1
python scripts/dynasty.py review approve 1 --reviewer "Editor" --takeaway "Why this changes the literature" --topics "Wealth and inheritance,Intergenerational mobility" --method "Difference-in-differences"
python scripts/dynasty.py review approve 2 --reviewer "Editor" --merge-into existing-work-id
python scripts/dynasty.py review reject 3 --reviewer "Editor" --notes "Out of scope"
python scripts/dynasty.py review defer 4 --reviewer "Editor" --notes "Need to examine full paper"
```

Decisions are recorded in `review_decisions`; approved records form the public export. Provider summaries are never silently promoted to editorial conclusions.

## Export as Hugo research archive

```bash
python scripts/dynasty.py export
```

The command writes approved/curated work pages to `content/papers/*.md` and a lightweight search metadata file to `static/data/research-index.json`. The existing Hugo archive supports client-side title, author, source, topic, and year filtering. The JSON index prepares future full-archive indexing as the collection expands.

**Important:** Export into a disposable directory first to review output:

```bash
python scripts/dynasty.py export --site-root /tmp/dynasty-hugo-test
```

Do not export to the live project and commit the pages until you intentionally switch from the legacy JSON seed workflow. The current build CI still checks `scripts/build_content.py` to protect the existing 12 pages. The exporter never deletes existing pages, but it **overwrites any page with the same work ID**. Keep the master database backed up before editing it.

## Scope and limitations

This is a **working foundation**, not a complete historical archive. It has no live automatic feed for all sources, no verified matching of all 128 source names to external provider IDs, and no AI-generated credibility ratings. The current search UI renders Hugo paper entries and is suited to the seed/early archive; as the collection grows above several hundred items, add pagination or a Pagefind index. API metadata can be incomplete or incorrect. The DOI linker and fuzzy detector should be reviewed on real-world edge cases before doing large imports.

## Next engineering stages

1. Verify real identifiers for A-tier journals and researchers, prioritizing accuracy over coverage.
2. Build and test NBER/CEPR/IZA adapters from official structured feeds or licensed APIs.
3. Add incremental ingestion checkpoints, recurring monitored queries, persistent storage/backup, and confidence metrics.
4. Introduce Pagefind (or another static index) and archive pagination before exporting thousands of cards.
5. Build a reviewer UI over the current auditable CLI after the candidate volume warrants it.

## Identifier suggestion and safe matching updates

Run `python scripts/dynasty.py sources suggest journal:quarterly-journal-of-economics` (or a `researcher:` identifier) to examine unverified OpenAlex identity suggestions. These do **not** enable any source. After checking identities, use `sources verify`. Persist your verified local source configuration with `sources dump --output registry/source_manifest.json`, review the Git diff, and commit it if appropriate.

The import cap counts all API records processed, including malformed or incomplete records. Exact matching recognizes canonical DOIs, OpenAlex/provider IDs and known NBER working-paper URLs. Metadata with only similar title/author/year values still requires an explicit editorial merge decision. The existing 12 seed works contain 16 known versions, including four distinct NBER preprint links.
