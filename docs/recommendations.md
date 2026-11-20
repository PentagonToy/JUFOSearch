# Journal recommendation strategy — peer alternatives first

Status: proposal, not implemented. This replaces the earlier topic-first design following the user's request on 20 November 2026. The two axes are research fit and proximity to the reference journal's standing. Citation indicators describe journals; they do not estimate manuscript quality or acceptance probability.

## Two entry paths

| Input | Purpose | Default ordering |
| --- | --- | --- |
| Journal title, ISSN or resolved initials, e.g. AECS | Find realistic alternatives to that journal. | Establish a comparable peer pool, then balance subject fit, metric proximity and useful subject variety. |
| Research keywords, e.g. `ML, PaSR, PDF` | Find venues for the research, including methodological neighbours. | Domain and method fit first, within the user's explicit filters. Do not silently choose a reference journal or infer one from browser history. |

Use one search box. Resolve ambiguous initials such as C&F before using a reference. A recognised journal title is not converted into topic keywords. When the user chooses Similar journals from keyword results, preserve both the chosen reference and the original research keywords.

## Comparable does not mean higher

Maintain separate provenance for each indicator: provider, edition, subject category and coverage. Compare JIF with JIF, SJR with SJR, and category percentiles with the same provider's percentiles. Do not average raw JIF and SJR, compare different editions silently, or choose each journal's best category to manufacture a match. Category percentile provides finer distance than Q1–Q4; use a genuinely shared relevant category first. A cross-category comparison uses the journals' relevant dominant categories and carries lower confidence.

The application currently holds JUFO levels and our own OpenAlex-derived quartiles and citation averages. It does not hold verified JIF or SJR values. The first free version can therefore use these available indicators as explicitly labelled proxies. The OpenAlex citation average is never labelled JIF, and its quartiles are never labelled JCR or SJR. Official JIF/SJR can be integrated later only with a verified reusable source; missing indicators are not fabricated.

For title-only recommendations, begin with these **provisional evaluation rules**, not a production formula:

1. Apply the user's JUFO, APC, licence and publishing-model constraints. Exclude the reference, duplicate identities, inactive records and non-journal sources. Persist the OpenAlex source type during refresh; the present topic snapshot does not retain it.
2. Require a credible subject connection. Build a wider pool from shared topics and their related subfields, rather than taking only the nearest six full-journal profiles. This allows computational-fluid and broader energy venues to be considered for AECS without hand-written journal lists.
3. For evaluated JUFO levels 1–3, start with the same level. A jump from level 1 to 3 does not belong in the default peer pool. Do not widen the band merely to fill twelve places.
4. Compare relevant subject quartiles/percentiles and the same-edition citation average. Test a same-or-adjacent-quartile band and a symmetric citation-ratio band of 2.5 as an initial diagnostic. These are starting hypotheses for validation, not established boundaries of journal quality. A true zero uses available category ranks instead of division; missing data never becomes zero or a confirmed peer match.
5. Within the eligible pool, prefer candidates that are both relevant and metrically close. Compare continuous proximity, not a bonus for a larger number. Evaluate topic-only ordering against a two-axis shortlist and remove near-duplicate subject profiles only where another relevant peer adds useful coverage. Do not fix numerical weights from this single combustion example.

For a reference without comparable standing data, offer clearly labelled topic matches rather than claiming equivalent quality. Keep incomplete cases distinct from the confirmed peer list. Levels 0 and unclassified are not interchangeable quality bands.

## AECS calibration examples

The following are observations from the shipped 2026 metric edition, OpenAlex snapshot 2026-10-14. Values are our OpenAlex citation averages and derived quartiles, **not JIF/SJR**. Ranges show all retained relevant categories rather than the best category alone.

| Journal | JUFO | OpenAlex average | Derived Q | Role in evaluation |
| --- | --- | --- | --- | --- |
| AECS | 1 | 2.84 | Q2 | Reference |
| Computers and Fluids | 1 | 2.78 | Q2 | Computational-fluid peer candidate |
| Combustion Science and Technology | 1 | 1.32 | Q3 | Combustion peer candidate |
| Combustion Theory and Modelling | 1 | 1.46 | Q3 | Combustion/modelling peer candidate |
| International Journal of Energy Research | 1 | 4.33 | Q2–Q3 | Broader energy peer candidate |
| Journal of Fluid Mechanics | 3 | 4.37 | Q1 | Exclude from AECS's default peer pool |
| Combustion and Flame | 3 | 6.27 | Q1 | Exclude from AECS's default peer pool |
| Energy and AI | 1 | 8.57 | Q1 | Consider for relevant keyword discovery; not an unconditional title-only peer |

JFM and International Journal of Energy Research have almost the same OpenAlex average, but different JUFO levels. Conversely, Energy and AI shares AECS's JUFO level but has a substantially higher citation average. Neither one indicator nor quartile equality alone captures the requested notion of a comparable venue.

The initial same-JUFO/adjacent-Q probe excludes JFM and Combustion and Flame and ranks CST and CTM first and second. It still puts Computers and Fluids 54th and International Journal of Energy Research 46th when ordered only by full-profile overlap. This is evidence that peer filtering alone is insufficient: candidate generation and the subject-versus-proximity ordering need to be tested together. The user's four examples are calibration cases, not hard-coded winners or a promise that all four will occupy the first six positions.

## Keyword discovery: domain plus method

For `ML, PaSR, PDF`, treat PaSR as a turbulent-combustion domain/method anchor, ML as the computational approach, and PDF as probability density function when that combustion context supports it. Do not globally translate PDF into that meaning or search for document formats. Preserve the original concepts alongside aliases and broader hints.

Energy and AI can enter the pool through supported energy/modelling and ML connections even if its overall journal profile differs from AECS. Keyword-only discovery has no reference-specific citation-ratio band; explicit user filters still apply. Where a reference is also supplied, show its standing as context and allow method relevance to broaden discovery without calling the result an equivalent peer. No candidate receives a bonus merely for being Q1 or highly cited.

Distinguish full concept coverage from partial methodological fit. A journal profile containing neural-network topics does not establish that it publishes PaSR/PDF closure papers. Keep the reason short and traceable; the existing optional article check can strengthen that evidence. Do not require literal occurrence of all acronyms in a journal title, and do not present broad topic hints as proof of co-occurrence.

## Six results, twelve at most

Show at most six compact recommendation cards, with one short reason per card and the existing JUFO/quartile information. One **Show 6 more** control reveals the remaining eligible candidates, up to twelve total. Expansion uses the same ordered pool and constraints: it does not silently admit more prestigious, less relevant or unverified-quality journals. Return fewer when insufficient candidates qualify; omit expansion when nothing remains.

Keep one contextual Similar journals action and a Back to results action that restores the original query, filters, page and scroll. Do not add a separate search mode selector, scoring sliders or recommendation pagination. The main search retains its existing page-size controls.

## Verification before implementation

Freeze at least twelve reference-and-keyword cases across domains before tuning, with held-out cases. Assess research fit first, then peer comparability; record both judgements rather than concealing standing information throughout the review. Include the AECS examples, `ML, PaSR, PDF`, `ML, SGS`, an unrelated medical negative, ambiguous C&F, missing metrics, real zero scores and restrictive APC/JUFO filters.

Compare topic-only, peer-filtered and combined shortlists at six and twelve. Verify that JFM and Combustion and Flame are excluded from AECS title-only peers through general rules; Energy and AI remains eligible for relevant keyword discovery; expansion preserves filters and ordering; missing metadata cannot masquerade as low quality. Inspect candidates below rank twelve to detect useful peers lost by candidate generation. No unreviewed offline score constitutes a passed relevance assessment.

Repair SGS/LES topic mapping and add context-aware PDF disambiguation before enabling recommendations. Use prepared compact profiles, metric records and topic postings; the first version needs no LLM, vector database, paid API or live metric request. This proposal does not introduce a recommender UI or claim validated acceptance predictions.

Sources: [OpenAlex source attributes](https://help.openalex.org/data/sources/attributes/), [Clarivate category percentiles](https://supportcenter.clarivate.com/s/article/Journal-Citation-Reports-Quartile-rankings-and-other-metrics?language=en_US). The local data method is documented in [metrics.md](metrics.md).
