# Related-journal recommendation strategy

Status: design only. Quartiles and publishing-model evidence were deployed on 20 November 2026. Recommendations are not implemented.

## Intended behaviour

Help a researcher find another suitable publication venue using a reference journal **and the research keywords already entered**. Similarity to an entire journal is useful evidence, but it should not dominate the user's particular topic. JUFO level, citation quartile and publisher reputation do not receive automatic ranking bonuses.

The first version should add one contextual action, **Similar journals**, and reuse the existing results, filters and page controls. Each suggested journal gets one short explanation identifying the connection. Keep six initial suggestions varied enough to include both close subject neighbours and relevant methodological neighbours. Do not expose a similarity percentage, acceptance estimate or scoring controls.

Carry the original research keywords when the action is chosen from keyword results. A title lookup alone supplies no research keywords: use the journal profile without inventing a manuscript topic. Show the reference and any carried keywords once above the results. **Back to results** restores the original query, filters, page and scroll position. Do not introduce a second search form or duplicate the journal cards.

## What the current data establishes

An offline diagnostic used 30,001 uniquely joined journal-topic profiles from the shipped snapshot. Topic-only neighbours were ordered by weighted Jaccard overlap of normalised retained topic counts, excluding inactive records and the reference itself. These are diagnostic ranks, not relevance judgements or production recommendations.

| Diagnostic | Observation | Consequence |
| --- | --- | --- |
| AECS profile only | Energy and AI ranks 174th; the nearest journals are primarily combustion venues. | Searching only the nearest journal profiles can miss methodological neighbours. |
| `energy, ml` discovery only | Energy and AI ranks 213th among 5,757 candidates; drug-design and materials venues occur near the top. | Keyword coverage alone is too permissive for a short recommendation list. |
| `ml, pasr` discovery | Energy and AI ranks 30th among 138 candidates. | The candidate pool contains it, but the profile does not prove PaSR publication evidence. |
| `ml, sgs` discovery | No candidates. The SGS hint requires a heading-word overlap that the relevant fluid-dynamics topic lacks, despite its LES keywords. | Repair and test method-to-topic mapping before shipping recommendations. Never translate this failure into “no suitable journals”. |

Energy and AI's largest retained topics include energy forecasting and smart grids; AECS's largest include combustion engines and flame dynamics. Energy and AI is therefore a plausible methodological neighbour when energy and ML are requested, not an unconditional alternative for every combustion manuscript. No proposed ranking has yet been validated by a researcher.

## Candidate and ranking pipeline

1. Resolve the reference journal by JUFO ID. An ambiguous acronym must not silently choose one of its journals.
2. Form the candidate union from nearby journal-topic profiles and the existing keyword-discovery results. Match identities by ISSN, retain active candidates and exclude the reference itself. Restrict recommendations to verified journal sources: the current JUFO series catalogue also contains book series and proceedings. Do not maintain a hand-written list of recommended journals.
3. Apply the user's explicit JUFO, APC and other selected constraints. Missing data remains unknown and must not become a favourable score.
4. Require a credible connection to the reference's research domain and prioritise coverage of the original research concepts. Distinguish a method found in a topic's name or keywords from one mentioned only in its description, and distinguish both from a broader discovery hint. Use similarity to the reference journal as supporting evidence, with topic proportions rather than raw publication volume. A broad term such as energy must not give a drug-design topic the same domain evidence as an energy-research topic.
5. Diversify the short list across the strongest relevant connections. Avoid returning six nearly identical combustion profiles when an energy-and-ML candidate has a credible connection. A diverse candidate still needs relevance; do not fill a category merely to balance the display.
6. Offer the existing optional paper check for specific methods. Journal-level topic overlap must never be presented as proof that PaSR and ML occur together in one paper. A failed live check should not erase the prepared candidates.

Start with explicit ordering by concept coverage and evidence strength before tuning a blended score. Freeze a small evaluation set first; add numerical weights only if they improve held-out cases. Keep all expensive profile preparation outside the visitor's request.

Use one eligible candidate pool. Select the strongest relevant candidate, then favour a different supported topic connection among candidates with equivalent concept coverage and evidence strength. Do not force a fixed number of subject and method slots, and do not relax filters to fill six places. Return fewer candidates when the evidence is weak. Keep JUFO and quartile values as comparison information or explicit filters; they are not proxies for manuscript acceptance difficulty.

Prepare compact normalised topic profiles and topic-to-journal postings with the existing data refresh. The current topic snapshot retains source IDs but not source types: retain the journal type from OpenAlex before enabling journal-only recommendations, rather than guessing from titles. Compare only the candidate union at request time. Reuse the current catalogue, filters and cards; the first version needs no LLM, vector database, paid API or live publisher lookup. Preserve profile provenance and the reason for each inclusion. A candidate with no verified profile cannot receive a fabricated similarity reason.

## Evaluation before implementation

| Case | Expected behaviour |
| --- | --- |
| AECS + combustion | Closely related combustion journals are prominent. |
| AECS + energy and ML | Methodological neighbours such as Energy and AI are considered when their profiles support the connection. |
| AECS + ML and PaSR | Distinguish broad energy/ML fit from actual PaSR paper evidence. Do not label Energy and AI as a proven PaSR venue without that evidence. |
| Computers & Fluids + ML and SGS | Include relevant computational-method venues, not just journals with “fluids” in their titles. |
| C&F as reference | Require identity resolution between Computers & Fluids and Combustion & Flame. |
| New journal or absent profile | Preserve title lookup and explain unavailable recommendation evidence. |

Use researcher-reviewed relevance judgements for these cases and unrelated negative cases. Check useful candidates in the first six results, diversity without relevance loss, reasons that trace to data, and the effect of each filter. Energy and AI is a diagnostic example, not a hard-coded promotion target. Adding a high quartile must not move an otherwise identical candidate upward.

## Implementation gates

1. Fix SGS/LES mapping and separate direct metadata evidence from broad hints. Add negative cases for medical drug design versus energy engineering and for generic neural-network mentions. Keep method synonym rules general; journal titles never belong in those rules.
2. Freeze at least 12 reference-and-keyword cases before tuning. Include the cases above, unrelated domains, short profiles, journal identity ambiguity and restrictive filters. Have the researcher label candidate fit as relevant, plausible or unrelated without showing JUFO or quartiles. Hold out part of the set from tuning.
3. Compare profile-only, keyword-only and combined candidates. Publish the first-six results and their reasons for review; proceed only if combined recommendations retain useful neighbours and reduce unrelated results on the held-out cases. An unreviewed offline score is not a passing relevance test.
4. Check invariants: no self-recommendations, duplicate identities, non-journal sources, inactive venues or filter violations; no promotion from higher JUFO/quartile values; no claim of method co-occurrence without paper evidence; no fabricated reason for missing metadata.
5. Verify the contextual action and back navigation, empty and partial results, keyboard/mobile access and response time against the deployed prepared-search baseline. A failed optional article check must leave the candidate list usable.

The next implementation step is the mapping repair and a reviewable candidate diagnostic, not a new recommendation interface. This keeps the present site small while testing whether the proposed recommendations are actually useful.
