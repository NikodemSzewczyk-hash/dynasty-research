# External identifiers: editorial verification protocol

All 128 source IDs in `registry/source_manifest.json` are **locally defined**. They do not prove the identity of a journal, working-paper feed or scholar at a public API.

## 1. Get candidates

```bash
python scripts/dynasty.py seed
python scripts/dynasty.py sources suggest journal:quarterly-journal-of-economics
python scripts/dynasty.py sources suggest researcher:jan-stuhler
```

This queries OpenAlex source or author search and returns up to five candidate records, showing journal ISSN possibilities or scholar ORCID/affiliation context. The tool **does not update the database**.

## 2. Independently verify

For journals, cross-check full title and ISSN in Crossref or at the publisher website. Be careful about title changes and multiple print/online ISSNs. For researchers, inspect OpenAlex publication lists, institution history, and where possible a personal ORCID/research page. Identical names are not sufficient identification.

For working-paper series, use the institution's documented metadata feed, endpoint, usage policy or licensing terms. No series has been enabled automatically.

## 3. Enable only confirmed identifiers

```bash
python scripts/dynasty.py sources verify journal:quarterly-journal-of-economics --key issn --value VERIFIED_ISSN --verified-by "Editor"
python scripts/dynasty.py sources verify researcher:jan-stuhler --key openalex_author_id --value VERIFIED_A_ID --verified-by "Editor"
```

Replace placeholders with checked values. The CLI validates identifier formats and records the review date and reviewer. It cannot independently authenticate that an identifier belongs to the intended journal or researcher.

## 4. Persist your manual work

```bash
python scripts/dynasty.py sources dump --output registry/source_manifest.json
```

This writes the **current** registry from SQLite into the tracked manifest. Review the resulting Git diff before committing it. Source IDs remain stable. The dump includes public reviewer labels and verification dates; avoid including private contact details.

**Never** enable retrieval automatically based on a name-search score or an unverified source suggestion.
