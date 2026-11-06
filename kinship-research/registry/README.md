# Source policy (v0.1)

The **single editable source registry** currently lives at `data/sources.json`, which is rendered by Hugo on `/sources/`.

Tiers mean:
- **A**: monitor all metadata routinely; surface only relevant papers.
- **B**: monitor selectively with topic filters.
- **C**: discovery and historical backfill, not an editorial quality endorsement.

Before implementing ingestion, add stable source IDs, official URLs, feed/API endpoints, licensing constraints, last checked timestamp, and parser health tests. Researcher homepages should be verified one-by-one rather than inferred from names. Track distinct works and their versions; do not interpret a repost as a new study.

We intentionally separate source prestige from a paper's relevance, identification quality and substantive contribution.
