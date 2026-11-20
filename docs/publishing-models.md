# Publishing-model evidence

The card's publishing model is separate from its Aalto APC support and reuse licence. **Gold OA** means a fully open-access journal; it does not mean publishing is free. **Diamond OA** additionally indicates no publication fees for authors. **Hybrid OA** means OA is optional per article. Green and Bronze describe the access route of an individual article and appear only in article-level checks.

Hover over, focus or tap the publishing-model value for a short explanation and its source. Escape or an outside click dismisses the help. Supplementary source links are available in Journal notes.

## Source precedence

Keep explicit Diamond information from JUFO and verified agreement models. Otherwise use an explicit JUFO model or positive OA/hybrid flags. Fill remaining gaps with the prepared supplement:

1. Publisher title lists identify Gold or Hybrid models by ISSN. The current sources cover Springer Nature, Wiley and the AIP Publishing title table in its public SURF agreement. That foreign agreement supplies model metadata only; it establishes no Aalto funding entitlement.
2. OpenAlex's public Sources snapshot supplies its journal-level full-OA flag. A positive flag or DOAJ membership supports Gold OA. A negative full-OA flag is labelled **Not fully OA**, with an explanation that optional OA has not been confirmed. It never becomes Hybrid automatically.
3. Missing or conflicting evidence remains unavailable. An absent fee, absent source or zero discount is never interpreted as Diamond OA or free publication.

The source observation and snapshot dates remain in the data. Publisher lists can change when journals switch models, so the supplement is a dated observation. It does not change the independently verified agreement eligibility, quota, expiry or licence data.

## Refresh

After downloading the public Sources snapshot with the quartile refresh, run:

```sh
python3.12 -B refresh_publishing_models.py --cache /absolute/path/publisher-sources --openalex-sources /absolute/path/openalex-sources/2026-10-14
```

Use the actual snapshot directory containing `manifest.json`. The script checks source-file sizes and counts, extracts publisher tables, validates ISSN checksums, excludes ambiguous joins and conflicting publisher labels, and writes `data/publishing-models.json.gz` only after the required sources pass their checks. The publisher cache refreshes on a later day. Review the configured list URLs when a new publisher edition is released.

Spreadsheet extraction uses Python's standard library. PDF extraction uses an existing `pdftotext` command, or macOS's installed Swift/PDFKit through the small bundled script. Raw files and any Swift module cache stay in the supplied execution artefact directory. The deployed application needs only the compiled JSON data, not these extraction tools.

Run the Python and client tests in the project guide before publication. No publisher pages or metric APIs are requested during ordinary journal search.
