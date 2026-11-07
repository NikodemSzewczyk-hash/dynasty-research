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
