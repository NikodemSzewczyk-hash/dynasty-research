# Source access (V0.6)

Each verified source has one documented, reproducible access path. Each run measures
completeness: how many records we read versus how many the provider itself reports for the
same window. Collection covers **1990 to the present**. Everything collected is unreviewed
bibliographic metadata. Nothing is approved, summarized or published automatically, and no
full text is downloaded.

## Access path per source

| Sources | Adapter | Path | History |
|---|---|---|---|
| 10 journals | `crossref_journal` | Crossref `/journals/{ISSN}/works`, cursor-paged | 1990– (AEJ from 2009) |
| NBER Working Papers | `crossref_prefix` | Crossref `/prefixes/10.3386/works`, DOIs `10.3386/wNNNNN` only | 1990– |
| IFS Working Papers | `crossref_prefix` | Crossref `/prefixes/10.1920/works`, DOIs `10.1920/wp.ifs.*` only | 1990– |
| CEPR Discussion Papers | `repec_redif` | RePEc ReDIF mirror `ftp://ftp.repec.org/opt/ReDIF/RePEc/cpr/ceprdp/` | 1990– (series from 1984) |
| IZA Discussion Papers | `repec_redif` | Official IZA ReDIF archive `https://repec.iza.org/RePEc/iza/izadps/` | 1998– |
| 10 researchers | `openalex_author` | OpenAlex works by verified author ID, cursor-paged | 1990– |

Why these paths:

- **NBER and IFS register their own DOIs** at Crossref; the prefix owners were checked via
  `/prefixes`. This replaces the RePEc listing page for NBER, which only showed a recent
  window. NBER keeps original dates on old papers (w5000 is 1995).
- **IFS re-deposited its working papers in 2025–2026**, so the year is taken from the DOI
  convention (`providers.doi_convention_year`), only when both encodings agree. Both
  number orders occur: W95/20 is `1995.9520`, and WP 22/25 is `2025.2225`. See
  `docs/metadata-audit.md`.
- **RePEc's standard method is ReDIF, not its websites.** https://ideas.repec.org/getdata.html
  says users should read each publisher archive, which is listed in the archive templates at
  `ftp://all.repec.org/RePEc/all/`, and "strongly" discourages scraping IDEAS pages. The
  RePEc API is a courtesy for small lookups and is not needed. The earlier adapter
  scraped IDEAS listing pages; it has been removed, and a test keeps it from returning.
- **CEPR's own archive** (`repec.cepr.org`) returns HTTP 403 to automated clients, so CEPR is
  read from the RePEc central mirror, which RePEc documents and notes may lag the
  publisher. The `https://` form of that host fails hostname verification, so the
  documented `ftp://` address is used. Verification is never disabled.
- **ReDIF privacy and rights.** Only an allowlist of fields is kept: handle, title,
  authors, creation date, number, JEL codes and publication status. Author e-mails,
  workplaces, abstracts and file links are discarded. RePEc never releases e-mails.
  Directories also contain PDFs; only `*.rdf` files are read.
- **Encodings.** CEPR's files are UTF-8; IZA's are Windows-1252. The reader tries UTF-8 and
  falls back.

## Completeness

`scripts/pilot23_ingest.py` records, for every source:

- `provider_records_available`: Crossref `total-results`, OpenAlex `meta.count`, or the
  ReDIF papers in the window;
- `provider_records_read`;
- `coverage`.

A source that was not fully read is flagged `possibly_truncated`, and its checkpoint does
not advance. The widest window measured (the backfill) is kept per source in
`registry/pilot23-state.json`, where weekly runs do not overwrite it. That figure is shown
on the Sources page.

Coverage measures completeness against the provider's own records. A provider can still
be incomplete itself: for example, Crossref deposits for older journal issues, or OpenAlex
author profiles that are split or merged.

Measured on 2026-11-08 for the window 1990-01-01 to 2026-11-08. *Kept* excludes non-articles
(journals), other DOI series under the same prefix (NBER chapters, other IFS series) and
papers outside the series.

| Source | Read / available | Coverage | Kept | Known gap |
|---|---|---|---|---|
| AEJ: Applied Economics | 858 / 858 | 100% | 858 |  |
| AEJ: Economic Policy | 935 / 935 | 100% | 935 |  |
| American Economic Review | 5,687 / 5,687 | 100% | 5,657 | Crossref holds no AER records under this ISSN for 1990–1994 and only 178 for 1995–1999 |
| Econometrica | 3,217 / 3,217 | 100% | 3,194 |  |
| Journal of Human Resources | 1,684 / 1,684 | 100% | 1,684 |  |
| Journal of Labor Economics | 1,629 / 1,629 | 100% | 1,537 |  |
| Journal of Political Economy | 2,861 / 2,861 | 100% | 2,781 |  |
| Quarterly Journal of Economics | 1,848 / 1,848 | 100% | 1,801 |  |
| Review of Economic Studies | 2,259 / 2,259 | 100% | 2,238 |  |
| Review of Economics and Statistics | 3,349 / 3,349 | 100% | 3,301 |  |
| CEPR Discussion Papers | 21,296 / 21,296 | 100% | 21,296 | The RePEc mirror ends at DP21601 while CEPR has issued up to DP22115 (checked 2026-11-08), so the newest few months are missing |
| IFS Working Papers | 6,445 / 6,445 | 100% | 1,097 | Two records keep Crossref's re-deposit year because their DOI encodings disagree (wp.ifs.2000.9710, briefing note wp.ifs.2017.0194). |
| IZA Discussion Papers | 19,019 / 19,019 | 100% | 19,019 |  |
| NBER Working Papers | 33,146 / 33,146 | 100% | 32,754 |  |

**Researchers (10)** have not been backfilled yet. OpenAlex now requires an API key for
these queries (HTTP 401 without one). The key is a repository secret, so their 1990+
backfill runs in GitHub Actions (`pilot23-sync.yml`, mode `backfill`) once this change is on
main. Until then they keep the records collected in V0.4.

## Storage

Records are stored as `registry/snapshot/<source>.jsonl`, one shard per primary source (the
alphabetically first source that returned the record). This keeps every file well under
GitHub's 50 MB warning and makes diffs reviewable. The SQLite review queue is rebuilt from
the shards and is not committed.

## Running

From `kinship-research/`:

    # live check of one source per adapter type (scratch output)
    python scripts/pilot23_ingest.py --mode smoke --max-per-source 3 \
      --snapshot /tmp/s.jsonl --state /tmp/st.json --report /tmp/r.json --no-db
    # full 1990-present backfill into registry/snapshot (about 30 minutes)
    python scripts/pilot23_ingest.py --mode backfill --max-per-source 200000 \
      --report registry/pilot23-report.json --no-db
    # one source only
    python scripts/pilot23_ingest.py --mode backfill --max-per-source 200000 \
      --source working_paper_series:cepr-discussion-papers --report /tmp/r.json --no-db
    python scripts/publish_pilot_discovery.py

The weekly GitHub workflow (`pilot23-sync.yml`) reads a 45-day window with overlap and
opens a review PR. It never commits to main.

On a python.org macOS build without root certificates, set
`SSL_CERT_FILE=/etc/ssl/cert.pem`.
