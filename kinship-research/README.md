# dynasty_

dynasty_ is a Hugo-powered research observatory on the origins and persistence of economic inequality, especially the role of families, kinship and intergenerational relationships.

**Status:** v0.1 prototype, with a verified historical seed collection. It is not yet a comprehensive archive or automated live newsletter.

## Quick start (Windows)

1. Install [Hugo](https://gohugo.io/installation/windows/) (standard edition is sufficient; e.g. `winget install -e --id Hugo.Hugo.Extended`).
2. Unzip this project, or clone its repository after uploading it to GitHub.
3. In PowerShell, navigate to this folder (`cd path\to\kinship-research`).
4. Run `hugo server -D`, then open <http://localhost:1313/>.
5. To build the site for publication, run `hugo --minify` (output is in `public/`).

### Where to edit

- **Design:** `static/css/site.css`, `layouts/`.
- **Editorial pages:** `content/about/index.md`, `content/briefs/`.
- **Paper metadata:** `data/papers.json`. Run `python scripts/build_content.py` to regenerate paper pages.
- **Journals, repositories, researcher watchlist:** `data/sources.json` (renders the Sources page).
- **Ingestion policy:** `registry/README.md`.

### Paper workflow

Paper records live in `data/papers.json`. Every record must have an ID, title, authors, year, source, URL, topical tags, and a brief editorial summary. The generator writes Markdown under `content/papers/` and never invents citations or research findings. Run `python scripts/validate.py` before adding records; reviewers should check every source link.

### Research discovery (optional, experimental)

`python scripts/ingest_openalex.py` creates an **unreviewed** candidate JSONL file (requires Internet). It does not edit curated paper records. Avoid running it unattended until validation, deduplication, rate limits and editorial review are in place.

### Deployment

Netlify: import a GitHub repository, select Hugo as the framework, use build command `hugo --minify` and publish directory `public`. The `netlify.toml` specifies a Hugo version but should be updated to a currently supported release before deployment. For a custom domain, change `baseURL` in `hugo.toml` to the domain's HTTPS URL.

Cloudflare Pages: build command `hugo --minify`, output directory `public`, set `HUGO_VERSION` in environment variables to a supported Hugo release. No domain purchase is required for a preview.

The website itself is entirely static, does not require an account, and contains no private user notes. Automatic ingestion/publication has **not** been enabled.

## Architecture

`data/papers.json` → `scripts/build_content.py` → `content/papers/*.md` → Hugo templates → `public/`.

Later: OpenAlex, Crossref, NBER/CEPR and institutional feeds → review queue → identifier matching → curated database → published site. Keep this data pipeline independent of the presentation layer.

## Rights

Paper metadata is linked to its original source. Editorial summaries in this prototype are brief paraphrases, not copied abstracts. Always check rights before republishing full abstracts or article text.


**Naming note:** The Hugo source folder is still named `kinship-research` to avoid breaking the current hosting configuration. The public-facing project name is **dynasty_**.

## dynasty_ V0.2 data pipeline (opt-in)

The optional research-data infrastructure is in `scripts/dynasty_data/`, documented in [docs/data-pipeline.md](docs/data-pipeline.md). The live Hugo site still builds from the current seed archive; unreviewed API metadata is never published automatically.

```bash
python scripts/dynasty.py seed
python scripts/dynasty.py stats
python scripts/backfill_plan.py --max-jobs 4
python -m unittest discover -s tests -v
```

The default backfill mode is dry run. Manually verified source IDs can be suggested, reviewed and saved; official NBER TSV metadata has a separate offline importer. See [identifier verification](docs/identifier-verification.md) and the data-pipeline guide for details.

## V0.3 historical discovery preview

The searchable /discovery/ section is explicitly **unreviewed bibliographic metadata**, separate from the 12-paper curated archive. Its complete 3,477-record candidate corpus is version-controlled in registry/candidates-v03.jsonl; the public preview shows only a title-screened subset. See docs/v03-milestone.md and docs/metadata-audit.md.

The proposed 30-paper reading queue in registry/reading_queue_v03.json contains **unread** papers, not full-text summaries. Use scripts/notes.py to create evidence-first note templates only after acquiring the relevant PDF.

## V0.6 source access

Each of the 24 verified sources now has a documented access path covering 1990 to the present, and every run checks how complete it is. The sources are:

- 10 journals, read from Crossref by ISSN
- NBER and IFS, read from Crossref by their own DOI prefixes
- CEPR and IZA, read from RePEc ReDIF archives
- 10 researchers, read from OpenAlex by author ID

The unreviewed snapshot (about 98k records) is stored as one file per source under `registry/snapshot/`. The Sources page shows coverage for each source. See [docs/source-access.md](docs/source-access.md).
