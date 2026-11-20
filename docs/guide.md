# JUFOSearch guide

[Open JUFOSearch](https://jufosearch.vercel.app/)

## Run locally

From the repository directory, run `python3.12 -B server.py` and open [localhost](http://127.0.0.1:8765/). Use the designated Workspace agent interpreter when working on the shared MacBook. Pass `--port 8876` to choose another port. No package installation or frontend build is required.

## Search

Use the single box for a journal title, ISSN, initials or up to eight keywords separated by commas or semicolons. Examples include `Computers and fluids`, `0045-7930`, `C&F`, `ml, pasr` and `CFD, ML, SGS, TCI`. Space-separated recognised abbreviations also work. Exact titles and identifiers take priority. Initials can identify several journals; compare titles and ISSNs.

Title and topic searches use prepared metadata. Ordinary searches do not wait for Crossref, JUFO or FinELib requests. Filters apply to the complete returned set, including inactive and unclassified JUFO series records. Results show 50 journals per page by default, with options for 100 or 150.

**Related topics** explains a candidate using OpenAlex subject profiles. At least two concepts must be related for a multi-keyword candidate. Profiles describe a journal's subjects; they do not establish that the requested methods occur together in one paper. Broader discovery terms connect PaSR and TCI with turbulent combustion, and SGS with large-eddy simulation. These hints are not used as substitutes for the requested concepts when checking article evidence. A missing profile does not remove a journal from title or ISSN search.

Select **Find matching articles** to run the slower Crossref check. It searches titles and available abstracts, preserves the original keyword requirements, and provides DOI links. **Back to topic matches** restores discovery results. This is a sample, not an exhaustive literature search; incomplete metadata can hide genuine matches. External failures leave the prepared search available.

The five most recent searches stay in the current browser's local storage. **Clear history** removes them. Successful prepared responses are also kept in memory for five minutes, up to ten query pages; that cache is not shared between visitors.

## Read the results

**OpenAlex quartiles** opens a subject-area table with the edition and snapshot date. Hover over a quartile for its field-specific rank; assistive technology also receives the rank. These are JUFOSearch calculations from OpenAlex, not official JCR quartiles. Missing comparisons remain unavailable. See the [metric method and refresh procedure](metrics.md). They do not affect the default search order. The [related-journal strategy](recommendations.md) is a design proposal; that feature is not implemented yet.

The theme button follows the device preference initially and saves a manual light or dark choice only in this browser. JUFO and quartile badges share four colour tiers: JUFO 3/Q1 indigo, 2/Q2 blue, 1/Q3 ochre, and 0/unclassified/Q4 slate. The visible labels retain each metric's meaning; shared colour does not convert one classification into the other.

A journal title opens its publisher website when a usable URL is present. APC support links to dated agreement details or Aalto SciFree. Agreement licences and journal licences remain distinct. The footer gives the JUFO snapshot date; source dates and agreement expiry are retained in the data and agreement dialog. Eligibility, article types and quotas still require checking with Aalto.

The publishing-model value explains Gold, Diamond, Hybrid and uncertain status on hover, keyboard focus or tap. Publisher lists and OpenAlex supplement missing JUFO models across journals. **Not fully OA** does not confirm a Hybrid option, and OA status never establishes Aalto funding. See [publishing-model evidence and refresh](publishing-models.md).

The history graph shows the full available JUFO history, excluding years before publication began. The table shows the latest five years. Hover or focus a point for its year and level. Missing values use open markers and dashed links at the baseline; a recorded level zero stays distinct from missing data. Unclassified journals are not assigned level zero.

## Refresh the prepared data

Tracked files under `data/` are compressed public metadata, not a private database. Refresh them before a release when the source information needs updating; the app does not silently replace them during a visitor's search.

1. Download the official [CSC bulk export](https://jufo-rest.csc.fi/v1.1/massa.json.zip) into an execution artefact directory outside the source tree.
2. Run the following command from the repository root, replacing the two paths with that directory's paths.
3. Run the checks below, inspect the source dates and changed files, then commit the snapshots with the code that consumes them.

```sh
python3.12 -B refresh_catalogue.py --bulk /absolute/path/massa.json.zip --cache /absolute/path/source-cache
```

The script obtains full v2.1 series records and checks coverage against every series ID in the bulk export. It then retrieves OpenAlex topic descriptors and source profiles by registered ISSNs, plus the FinELib Elsevier list. Downloads are bounded and resumable within the same day; an older cache is refreshed. Each snapshot is replaced atomically after its preparation succeeds. A failed refresh exits with an error; do not publish an incomplete set of files.

JUFO retains its own levels, histories, licences and OA metadata. OpenAlex supplies topic profiles, publishing-model evidence and the inputs for our calculated quartiles, not JCR quartiles or SCIE status. Topic profiles use the API's retained topic counts across its available publication history, not a fixed-year article cohort; these counts are normalised for ranking and are not probabilities. Ambiguous ISSN joins are excluded. FinELib terms retain their agreement expiry, and the selected SciFree observations retain their original observation dates.

Sources: [CSC API](https://wiki.eduuni.fi/spaces/cscvirtajtp/pages/578257375/v2.x), [OpenAlex source attributes](https://help.openalex.org/data/sources/attributes/), [Aalto publishing agreements](https://www.aalto.fi/en/services/open-access-agreements-by-publisher), [FinELib Elsevier agreement](https://finelib.fi/open-access-publishing-in-elsevier-journals/).

## Verify and host

```sh
python3.12 -B -m unittest -q
node --test test_client.cjs test_theme.cjs
```

Tests cover prepared search without network access, complete pagination, initials, Unicode, missing levels, history, topic explanations, article evidence, agreement matching and compressed responses. The snapshot checks also exercise the shipped data.

Vercel serves `public/` and runs `api/search.py` using the shared handler. `data/**` must be included in the Function bundle. Prepared API results are returned in batches of at most 1,000 records; the client collects every batch before enabling filters. JSON responses support gzip. Complete successful responses are cached on the CDN for five minutes; source failures are not cached. Legacy journal pagination remains available, `mode=auto` and `mode=fast` use prepared discovery, and `mode=articles` explicitly requests live paper evidence.
