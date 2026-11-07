# dynasty_ V0.3 — staged historical corpus

This milestone separates **bibliographic discovery**, **editorial verification**, and **full-text knowledge notes**. An API search does not mean a paper was read or endorsed.

## Real historical import

The new GitHub Actions workflow runs a bounded Crossref search across 18 research queries, up to 90 raw records per query (maximum 1,620). It creates a SQLite database, a CSV review queue, a provenance report, and a capped discovery JSON index. The workflow stores the full database and review CSV as a 30-day Actions artifact. Only metadata-only preview JSON and the provenance report are committed to the feature branch.

From the kinship-research folder, first dry-run:

    python scripts/v03_bootstrap.py --provider crossref

Then execute a bounded import:

    python scripts/v03_bootstrap.py --execute --provider crossref --max-jobs 18 --per-query 90

OpenAlex can be run separately if its API access is available; use an environment variable OPENALEX_API_KEY. Neither importer writes editorial conclusions.

## Review and release gates

1. Read data/discovery-report.json: verify how many queries succeeded, total unique candidates, and the fraction passing the lexical filter.
2. Download the dynasty-v03-historical-review Actions artifact. Inspect the full CSV and SQLite database.
3. Verify a random sample of at least 100 records against DOI landing pages: titles, authors, years, versions, and topical relevance.
4. Resolve DOI and working-paper/version duplicates before promoting records.
5. Approve individual papers in the V0.2 editorial queue, supplying human-authored takeaways and topics. The separate discovery page labels all records as unreviewed metadata.
6. Only write detailed notes after accessing and reading full papers. Cite page/table evidence and distinguish author claims from what the empirical design identifies.

## Targets versus achieved work

The V0.3 goals are 1,000+ imported candidate records, 100–200 bibliographically verified papers, and 30 deeply analyzed papers. The import may reach the first target. The latter two require deliberate verification and full-text reading, and are not automatically completed by the import.

The site remains on the current production version until the stacked V0.2 and V0.3 pull requests are reviewed and merged.

## Quality-control iteration

The first 18-query Crossref backfill returned 945 distinct candidate records, but title-level inspection revealed many irrelevant medical and engineering matches. We therefore split queries across three publication eras (2000–2009, 2010–2019, 2020–present), use title-focused search, and add a transparent domain-sensitive lexical gate. The 54-query Crossref run returned 3,477 candidates, of which only 82 passed the stronger gate; those 82 are still unreviewed.

To improve coverage of economics working papers without scraping copyrighted PDFs, the pipeline also attempts to download the NBER's **official public-use bibliographic ref.tsv** from https://data.nber.org/nber_paper_chapter_metadata/tsv/ref.tsv, selects a bounded set of likely relevant titles across eras, and queues them as unreviewed records. This official metadata endpoint may be unavailable at times; the workflow treats the supplement as optional and reports its outcome. The website's discovery index never represents imported records as read or endorsed.

The separate notes CLI creates empty drafts with source-version provenance and validates page references before a note can claim evidence-checked status. It does not generate 30 notes automatically.

## NBER access limitation observed on 2026-11-07

The official public-use NBER ref.tsv endpoint returned HTTP 403 from the GitHub Actions runner. We did not attempt to bypass this access control. The official TSV parser and bounded selector are implemented and tested, but the automated runner does not import NBER records. An authorized researcher may download the TSV through the NBER site and run:

    python scripts/v03_nber.py --file /path/to/ref.tsv --db data/v03.sqlite --output-dir data/v03-export

The CI report explicitly records NBER as not imported. Do not describe Crossref candidates as NBER-verified or source-verified.

## Initial title-only quality triage

A manual inspection of the 65 records passing the stricter lexical gate identified 13 obviously off-topic items (e.g. technical-professional mobility, firm innovation, and an unrelated book review). Their DOIs are listed with reasons in registry/discovery_exclusions.json. They remain in the complete research-universe JSONL and review database, but are excluded from the public metadata preview. This is a **title-only** triage, not DOI verification or full-text reading.

The workflow also generates data/review-sample-v03.csv, a deterministic 100-record stratified sample with blank reviewer fields. Use docs/metadata-audit.md to record verification results.

## Hugo data-directory compatibility

The complete normalized corpus is stored under registry/candidates-v03.jsonl, not the Hugo data/ folder. Hugo attempts to parse every file under data/ and does not support JSONL. To rebuild the local database, run:

    python scripts/rebuild_candidates.py --input registry/candidates-v03.jsonl --db data/dynasty.sqlite

This metadata archive is version-controlled; the SQLite review audit remains in the workflow artifact until durable reviewed-state storage is added.
