# Kinship Research

A Hugo-powered research observatory on the origins and persistence of economic inequality, especially the role of families, kinship and intergenerational relationships.

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
