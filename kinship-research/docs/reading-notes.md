# Evidence-first reading notes

The knowledge layer is intentionally separate from the metadata archive. **A DOI, title, abstract, or Crossref record does not establish that a paper has been read.**

## Create an empty note

From kinship-research, after seeding the V0.2 database:

    python scripts/dynasty.py seed
    python scripts/notes.py init where-is-the-land-of-opportunity --output notes/where-is-the-land-of-opportunity.json
    python scripts/notes.py validate notes/where-is-the-land-of-opportunity.json

The output is a blank **draft template**, not a paper summary. It contains the work ID and known versions only.

## Progressively fill the evidence

1. Acquire a legally accessible full PDF and record the exact version and source URL.
2. Record its SHA256 hash and page count, then move status from draft to source_read.
3. Identify the motivating question separately from the **actual estimand** (treatment, outcome, population, timing, identifying variation, assumptions).
4. Record numerical estimates and authors' claims with exact PDF page numbers and table/figure references.
5. Check claims against the PDF before changing status to evidence_checked.
6. Add cross-paper links with explicit relation types and a rationale. Only after rechecking the underlying papers should a note become synthesis_ready.

The validator rejects missing PDF provenance for full-text review statuses and page-free claims for evidence_checked/synthesis_ready notes. This is a structural guardrail, **not a guarantee that an AI interpretation is correct**.

No full-text notes are published in V0.3 by default. The 30-paper deep-reading target is future work requiring PDF access and genuine evidence verification.
