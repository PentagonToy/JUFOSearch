# Comparable journal suggestions

The first implementation compares a selected journal with related venues of similar recorded standing. It does not predict manuscript acceptance or replace checking a journal's scope. Keyword discovery remains in the main search results.

## Interface

**Similar journals** is a disclosure inside each journal card, alongside JUFO history and OpenAlex quartiles. Opening it loads suggestions without blocking the original search. It shows at most six cards. **Show 6 more** reveals up to twelve in total, and **Show fewer** returns to six. Closing and reopening the disclosure preserves its loaded list.

Current filters apply within the prepared twelve suggestions and may leave fewer matches; they do not refill the candidate pool beyond twelve.

Each suggestion shows its title, JUFO level, a compact range of OpenAlex-derived subject quartiles, the listed APC when known, Aalto support or a verification link, and one shared-topic explanation. Aalto support opens the existing agreement details. Missing prices and support are not interpreted as zero charges or funding entitlement. Clicking the journal title opens its lookup in JUFOSearch.

## Standing and subject fit

Eligible candidates are active journals with an OpenAlex quartile record and a topic profile. The quartile preparation population contains verified journal sources. Exclude the reference and duplicate identities. Require the same evaluated JUFO level, 1–3. An unclassified reference receives no claim of comparable standing.

The provisional peer band allows at most one quartile of mean distance across shared categories. When categories are disjoint, compare the retained-category means with lower interpretive confidence. Positive citation averages must be within a symmetric factor of 2.5. Two genuine zero averages may match without division. Missing indicators never become zero. All metric comparisons use the same prepared OpenAlex edition and source population, not a mixture of JIF, SJR and OpenAlex values.

Topic profiles are normalised retained topic counts. Require weighted Jaccard overlap of at least 0.04. Order eligible candidates in successive nondominated fronts of topic overlap and citation proximity, so a candidate cannot precede another that is better on both axes. Within a front, the provisional tie-break is `0.6 * sqrt(topic_overlap) + 0.4 * citation_proximity`, with a small penalty for repeating an already selected topic profile. These are implementation choices awaiting researcher review, not validated quality measurements.

For the shipped AECS example, CST and CTM appear within six and Computers and Fluids within twelve. JFM and Combustion and Flame are excluded through the standing rules, without a journal blacklist. Energy and AI lies outside the title-only citation band but remains a candidate in relevant keyword discovery. Example journals are regression cases, not a hard-coded recommendation list.

## Keyword discovery and evidence

The main search accepts titles, ISSNs, initials and research keywords in one field. Ambiguous initials such as C&F preserve all matching identities. Exact titles take priority over topic interpretation.

For `ML, PaSR, PDF`, PDF expands to probability density function only with a fluid/combustion context. PaSR and other recognised domain anchors remain required in the profile evidence, so a generic ML/PDF match from an unrelated field does not replace the requested domain. SGS/LES matching accepts direct topic-keyword support as well as heading evidence. Broader hints remain distinct from proof that methods occur together in one article.

The optional Crossref check searches article titles only. It neither requests nor matches abstracts. The peer recommender makes no Crossref or OpenCitations request and introduces no paid service.

## Preparation and verification

`prepare_search.py` prepares title/topic postings and normalised peer profiles from the tracked source snapshots. A read-only SQLite store supplies only the journal records required by a response. Source hashes reject stale indices. The complete source catalogue and topic exports remain available for refresh and validation.

Tests check identity, bounded output, same-level standing, citation/quartile bounds, genuine zero and missing values, title-only evidence and contextual PDF interpretation. Twelve reference cases across combustion, fluids, energy, general science and medicine have been checked against the technical constraints. This does not establish researcher-assessed relevance or acceptance difficulty; broader relevance review remains necessary before treating the ranking as calibrated.

APC prices are dated list-price observations from OpenAlex's public Sources snapshot, stored separately from Aalto agreement terms. They are not reported historical payments, discounted invoices or guarantees of current charges. See the [project guide](guide.md) for refresh commands and the [metric method](metrics.md) for the comparison population.
