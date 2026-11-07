# dynasty_ 23-source activation pilot (V0.4)

**Status: review-only pull request.** No unreviewed paper is added to the curated site. The 12 existing curated papers and the V0.3 discovery preview remain unchanged. All source IDs have provenance in registry/pilot23-verification.json and enabled retrieval settings in registry/source_manifest.json.

## Sources and identity checks

- **10 journals (Crossref):** American Economic Review, Quarterly Journal of Economics, Journal of Political Economy, Econometrica, Review of Economic Studies, AEJ Applied Economics, AEJ Economic Policy, Review of Economics and Statistics, Journal of Labor Economics, Journal of Human Resources. Each ISSN was checked against the live Crossref journal registry, including returned title and registered ISSN list. The importer retrieves DOI-bearing journal articles by ISSN.
- **10 researchers (OpenAlex):** Jan Stuhler, Martin Nybom, Katrine V. Løken, Aline Bütikofer, Kjell G. Salvanes, Magne Mogstad, Alessandra Voena, Corina Mommaerts, Wojciech Kopczuk, Raj Chetty. Each author ID was checked against name, affiliation and ORCID when present. Kjell Salvanes also has a smaller OpenAlex profile sharing his ORCID, so author coverage is not guaranteed complete. Sandra E. Black was excluded because OpenAlex's top name match is a different person (a medical researcher).
- **3 working-paper series (RePEc):** NBER (RePEc:nbr:nberwo), CEPR (RePEc:cpr:ceprdp), IZA (RePEc:iza:izadps). We use one bounded public IDEAS/RePEc series listing per run, not a restricted RePEc API, a subscription site, or PDF scraping. NBER's direct TSV endpoint and CEPR's publisher listing returned HTTP 403 from GitHub Actions; no access-control workaround was attempted.

The RePEc adapter captures series handle, item identifier, title, available authors, listing year and canonical IDEAS link. A public RePEc listing is a **recent window**, not a full historical archive. RePEc's separate API requires approval; this pilot does not use it.

## Data flow and publication boundary

1. scripts/pilot23_ingest.py reads the exact 23-source verification list and refuses unknown, disabled or mismatched identifiers.
2. The three adapters fetch bounded metadata, normalize it and attach pilot_source_ids provenance. Same-provider IDs are idempotent. DOI collisions across providers are counted, not silently merged.
3. registry/pilot23-candidates.jsonl is a durable, reconstructable **unreviewed** snapshot. registry/pilot23-state.json records per-source successful checkpoints; a source that hits its cap does not advance its checkpoint. registry/pilot23-report.json records coverage warnings.
4. The SQLite queue is rebuilt from the snapshot for review. **No paper is approved**, no claim is extracted, and no Hugo content is modified.
5. The weekly pilot23-sync.yml workflow (Monday 09:20 UTC, only after merge to main) writes to bot/pilot23-weekly and attempts to open a **review PR**. It never commits to main or auto-merges. GitHub Actions must be permitted to create pull requests; if disabled, the data branch is still pushed and a warning is emitted. A failed provider run does not publish a partial snapshot.

## Run locally

From kinship-research/:

    python -m unittest discover -s tests -v
    python scripts/pilot23_ingest.py --mode smoke --max-per-source 3 \
      --snapshot /tmp/pilot23-smoke.jsonl --state /tmp/pilot23-smoke-state.json \
      --report /tmp/pilot23-smoke-report.json --db /tmp/pilot23-smoke.sqlite

For a bounded rolling collection of all 23:

    python scripts/pilot23_ingest.py --mode weekly --max-per-source 150

For a sample of older papers (not a full backfill):

    python scripts/pilot23_ingest.py --mode backfill --max-per-source 150

Crossref is publicly accessible without registration. OpenAlex has a free starter allowance and supports OPENALEX_API_KEY when available; API limits, prices and authentication can change. Set DYNASTY_CONTACT_EMAIL for polite provider identification. Never commit API keys. Network failures must be investigated; do not label them "zero new papers."

## Tests and limitations

- Offline tests cover source verification gating, RePEc HTML parsing, idempotent provenance, cap detection, checkpoint rollback and SQLite import.
- GitHub Actions live checks a journal, researcher and series, then all 23 sources with a two-record cap per source. This proves endpoint connectivity, not recall or historical completeness.
- Crossref journal deposits may omit papers; OpenAlex author profiles can be split or overmerged; RePEc listings may lag or change HTML markup.
- A saturated cap is explicitly flagged; a 45-day lookback is not a substitute for incremental pagination through all records.
- The V0.3 3,477 Crossref candidates are a separate corpus. The pilot's new snapshot is not merged into that corpus or the curated archive automatically.
- Exhaustive 2000–2026 coverage requires year/month-scoped pagination, completeness checks against official issue lists, full ReDIF archive ingestion or authorized provider feeds, and editorial review.
- External titles and author strings are untrusted metadata. No copyrighted full-text papers are downloaded by these workflows.
