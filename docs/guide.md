# JUFOSearch guide

[Open JUFOSearch](https://jufosearch.vercel.app/)

## Run locally

Use Python 3.12 and macOS's built-in curl. From the repository directory, run the following command and open [JUFOSearch](http://127.0.0.1:8765/).

```sh
python3.12 server.py
```

On the Workspace MacBook, use `/Volumes/PentagonToy/Workspace/Agents/Environment/m5/bin/python` in place of `python3.12`. Use the corresponding `m1pro` path on the M1 Pro. Pass `--port 8766` if port 8765 is in use, then open the matching address. Press Ctrl+C to stop the server.

## Search for journals

| Search mode | Example | What it returns |
| --- | --- | --- |
| Journal title or ISSN | `Results in Physics` or `2211-3797` | Up to 30 journal and series records from the CSC JUFO API. [CSC API documentation](https://wiki.eduuni.fi/spaces/cscvirtajtp/pages/578257375/v2.x) |
| Research topic | `turbulent combustion` | Journals with matching article titles. Each result can show up to two articles with DOI links. [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) |

In journal mode, if a title search returns no matches, JUFOSearch tries individual title words and ranks candidates by word overlap. For example, `application in engineering combustion jufo` finds *Applications in Energy and Combustion Science*. The app also searches an acronym index generated from active scientific journals in the [CSC bulk export](https://wiki.eduuni.fi/spaces/cscvirtajtp/pages/48922203/Julkaisukanavatietokannan%2BREST-rajapinta). It derives forms from title initials and conjunctions, so `C&F` and `CNF` can return both *Combustion and Flame* and *Computers and Fluids*. Each candidate is checked against the live JUFO record. Run `python3.12 refresh_acronyms.py` to rebuild the index from the latest export.

The main search box recognises `physics` (including `physcis`), `ml` and `cfd` as topic shortcuts. These topics begin with selected journals whose records are checked in JUFO. Topic search examines a limited set of recent Crossref article titles, groups matches by journal and checks their ISSNs against active JUFO records. For the three shortcut topics, it also screens article-derived results against relevant JUFO disciplines. Use the results to identify candidates for further review.

## Interpret the results

Select a journal title to open its publisher page when a website is available. Use the separate Aalto SciFree link to check publishing support. Filter results by JUFO level, publisher, APC support, licence or publishing model. Select the APC status to see available contract terms, article types, quota information and sources. **Journal notes** contains subject areas and self-archiving information. Each card distinguishes an Aalto agreement licence from the licence reported by JUFO. [Aalto SciFree](https://search.scifree.se/aalto)

For eligible Elsevier journals, JUFOSearch matches ISSNs against the official FinELib title list and caches the list for one hour. This lookup covers the agreement through 31 December 2026. The app also includes dated SciFree records for selected Wiley, Springer and IOP titles. For journals without a verified match, expired terms or unavailable title data, the card points to SciFree. Check your eligibility, article type and any quota before submission. [FinELib Elsevier agreement](https://finelib.fi/open-access-publishing-in-elsevier-journals/) · [Aalto publishing agreements](https://www.aalto.fi/en/services/open-access-agreements)

## Verify search changes

Run `python3.12 -B -m unittest -v` from the repository directory. The tests exercise title ranking, ISSN normalisation, acronym collisions and agreement matching without network access.

## Hosting on Vercel

Import the GitHub repository as a Vercel project with the root directory left at the repository root. The configuration serves the interface from `public/` and runs `api/search.py` as a Python Function. The Function uses the same search handler as the local server. [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python)
