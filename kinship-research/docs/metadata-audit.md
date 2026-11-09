# Bibliographic quality audit

The historical corpus contains unreviewed records, including some false positives. Use a reproducible, stratified sample to estimate metadata correctness and topical relevance before calling the corpus curated.

From kinship-research:

    python scripts/audit_sample.py --input registry/candidates-v03.jsonl --output registry/review-sample-v03.csv --n 100 --seed 20261107

The sample deliberately includes high-, medium-, and low-relevance titles so the false-positive rate can be measured rather than hidden. It does **not** automatically mark any paper verified.

For each row, check the DOI landing page or an authoritative publisher/working-paper record and fill:
- metadata_verified: yes/no
- topically_relevant: yes/no
- duplicate_version: yes/no
- reviewer_notes: reason for uncertainty or correction

Only after reviewing the sample should the lexical threshold and source coverage be calibrated. Separately review any paper before promoting it to the curated archive. A checked DOI alone does not establish that its empirical conclusions have been read.

## Automated metadata pre-check (2026-11-07)

The `metadata_verified`, `duplicate_version` and `reviewer_notes` columns of
`registry/review-sample-v03.csv` were pre-filled automatically by Claude, and every note
is tagged `[auto-check ...]`. `topically_relevant` is left blank for the editor. The raw
values compared for each row are in `registry/review-sample-v03-autocheck.json`.

**Method.** Each of the 100 DOIs was checked against three sources:
- the doi.org handle registry, to confirm the DOI is registered;
- Crossref `/works/{doi}`, which is the publisher's own deposit;
- OpenAlex, for its work record and a search for other records with the same title.

The checks compared title, author surnames and order, venue, year and record type. A
possible version was flagged only when another DOI had an identical normalized title and
shared at least one author; book reviews were excluded. Publisher landing pages were not
fetched, because many publishers block automated requests.

OpenAlex's `publication_year` turned out to match Crossref's `created` date (the first DOI
deposit), so it is not an independent check on the year.

**Results.**

| Outcome | Rows |
|---|---|
| Consistent with the publisher's Crossref deposit (`yes`) | 76 |
| `ERROR`: a field is demonstrably wrong | 7 |
| `UNCERTAIN`: dates conflict; check the landing page | 17 |
| Likely another version under a different DOI (`duplicate_version = yes`) | 13 |

- **Systematic year bug for IFS working papers.** All 7 errors are IFS working papers
  (`10.1920/wp.ifs.*`) whose year is the date IFS re-registered them in 2025–2026; the DOI
  encodes the real year (1995–2017). The importer takes Crossref's `published` date. All 47
  IFS records in `candidates-v03.jsonl` are affected, and 9 of them appear in the public
  discovery index with a 2025 or 2026 year. One IFS deposit also has a malformed author
  (given name missing for Harmon).
- **Online-first versus print.** Many journal articles were posted online one or two years
  before appearing in an issue. The corpus correctly uses the issue/print year. This also
  explains why the sample clusters at 2010 and 2020: online-first papers from 2009 and 2019
  fell into the next era's query window.
- **Uncertain years.** These are mostly journals or book platforms that re-deposited old
  content. For example, JAOS volume 135 (2015) is dated 2021.
- **Not research papers.** Three records are two Crossref "dataset" items and one IUPAC
  glossary entry.

This pre-check confirms only that the metadata matches the registry. It does not establish
topical relevance or that anyone has read the papers. An editor should confirm the
`ERROR` and `UNCERTAIN` rows and fill in `topically_relevant` before the sample is used to
calibrate the title filter.

### Re-running the pre-check

    SSL_CERT_FILE=/etc/ssl/cert.pem python scripts/audit_autocheck.py fetch --cache /tmp/dynasty-audit-cache
    python scripts/audit_autocheck.py check --cache /tmp/dynasty-audit-cache --write

`fetch` is the only step that uses the network. It is polite but slow, because
unauthenticated OpenAlex requests are throttled after a few hundred calls. `check` runs
offline and refuses to overwrite rows that already contain editor notes unless you pass
`--force`. It never writes `topically_relevant`. Set `SSL_CERT_FILE` only on a Python build
that lacks root certificates, such as the python.org macOS installer; do not disable
verification.

### IFS year repair

`dynasty_data.providers.doi_convention_year` now supplies the issue year for IFS DOIs of the
form `10.1920/wp.ifs.YYYY.[w]YYNN`, and only when both encodings agree. For example,
`wp.ifs.1995.9520` is working paper W95/20. Both the Crossref and the OpenAlex
normalizers use it, so new imports are correct.

The rule was cross-checked against RePEc IDEAS citation dates for W95/20 (1995), W10/16
(2010), W05/05 (2005) and W17/11 (2017). IFS's own site returns HTTP 403 to automated
clients, and that was respected.

`scripts/repair_doi_years.py` applied the rule to the committed data: 46 records in
`candidates-v03.jsonl` and 9 rows in the public discovery index, which was then regenerated
with `publish_pilot_discovery.py`. Only `year` values and the year-based ordering changed.
The script is a dry run by default and is idempotent.

Still open:
- `10.1920/wp.ifs.2017.0194` is a briefing note (BN194) with a different numbering
  scheme, so it was deliberately left at 2026. Confirm its year by hand; it is probably
  2017.
- The `year` column in `review-sample-v03.csv` keeps the pre-repair values, because it
  records what was audited.
