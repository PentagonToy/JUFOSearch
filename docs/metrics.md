# OpenAlex-derived quartiles

These are JUFOSearch calculations from a public OpenAlex Sources snapshot. They are not JCR/JIF quartiles, SJR quartiles or official OpenAlex-issued rankings. The displayed source date and edition belong to the metric snapshot, independently of the JUFO and topic-search snapshots.

## Calculation

For edition `Y`, use OpenAlex's `summary_stats.2yr_mean_citedness`: citations in `Y−1` to publications in `Y−3` and `Y−2`, divided according to OpenAlex's source metric definition. For the 2026 edition, these are 2025 citations and 2023–2024 publications. The score is an average citation measure, not a measure of manuscript quality or acceptance probability. [OpenAlex source attributes](https://help.openalex.org/data/sources/attributes/)

The comparison population comes from **all globally eligible CWTS Core journals in the same public Sources snapshot**, not just journals linked to JUFO. Eligible records have source type `journal`, OpenAlex's `is_core=true`, a finite non-negative citation score, and at least ten OpenAlex works published in the two-year publication window. CWTS Core provides a defined research-journal reference set rather than mixing every source labelled a journal into the comparison. It is not Web of Science Core Collection membership. Journals outside this reference set, missing scores, insufficient publication history and non-journal sources receive no quartile. A real zero citation score remains valid. [OpenAlex's `is_core` definition](https://help.openalex.org/data/sources/attributes/)

Assign subject areas using the source's retained OpenAlex topics across its available publication history, rather than a new classification of the two-year publication window. Aggregate topic counts by subfield, then retain at most the three largest subfields, each accounting for at least 10% of those topic counts. These are topic-profile weights, not percentages of unique papers. This rule limits incidental subject assignments; it is different from assigning every subfield touched by any publication.

Within each subfield, rank eligible sources by descending citation score. Rank is `1 + number of sources with a strictly greater score`, so tied scores receive the same rank. For population size `N`, assign `Q = 1 + floor(4 × (rank−1) / N)`, capped at four. Ties crossing a boundary receive the better quartile together, so groups need not contain exactly 25% of journals. A subfield needs at least twenty eligible sources and more than one distinct score; otherwise it receives no quartile.

Match the results to JUFO records by ISSN. Ambiguous joins are excluded. A journal with no eligible match shows no comparable data; it is not assigned Q4 or level zero. The displayed rank is specific to the named subject area. Differences from JournalMetrics or other OpenAlex-based services are expected when populations, subject assignments, source dates or tie rules differ.

## Refresh

Run this from the repository root, using the designated Python interpreter and an execution artefact directory outside the source tree:

```sh
python3.12 -B -m scripts.refresh_quartiles --cache /absolute/path/openalex-sources
```

The script downloads only the public Sources snapshot, checks file sizes and record counts against its manifest, calculates the global comparison groups, and saves the matched results to `data/quartiles.json.gz`. Raw source parts remain in the execution artefact directory. The compiled result is loaded locally by the search Function; a visitor's search makes no metric API request. No account, API key or paid service is required for the public snapshot. [Public snapshot documentation](https://help.openalex.org/access/snapshot/)

Run the Python and client checks in the project guide before publishing the updated data. The manifest records the compiled file's size and checksum. Subject quartiles are displayed in a collapsed table; they do not change the default search order.
