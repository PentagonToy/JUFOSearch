# Related-journal recommendation strategy

Status: design only. Implement and verify the OpenAlex quartile display first. No related-journal recommendation action is added in this change.

## Intended behaviour

Help a researcher find another suitable publication venue using a reference journal **and the research keywords already entered**. Similarity to an entire journal is useful evidence, but it should not dominate the user's particular topic. JUFO level, citation quartile and publisher reputation do not receive automatic ranking bonuses.

The first version should add one contextual action, **Similar journals**, and reuse the existing results, filters and page controls. Each suggested journal gets one short explanation identifying the connection. Keep six initial suggestions varied enough to include both close subject neighbours and relevant methodological neighbours. Do not expose a similarity percentage, acceptance estimate or scoring controls.

## Candidate and ranking pipeline

1. Resolve the reference journal by JUFO ID. An ambiguous acronym must not silently choose one of its journals.
2. Form the candidate union from nearby journal-topic profiles and the existing keyword-discovery results. Match identities by ISSN, retain active candidates and exclude the reference itself. Do not maintain a hand-written list of recommended journals.
3. Apply the user's explicit JUFO, APC and other selected constraints. Missing data remains unknown and must not become a favourable score.
4. Prioritise coverage of the original research concepts. Distinguish direct phrase or method evidence from broader subject hints. Use similarity to the reference journal as supporting evidence, with topic proportions rather than raw publication volume.
5. Diversify the short list across the strongest relevant connections. Avoid returning six nearly identical combustion profiles when an energy-and-ML candidate has a credible connection. A diverse candidate still needs relevance; do not fill a category merely to balance the display.
6. Offer the existing optional paper check for specific methods. Journal-level topic overlap must never be presented as proof that PaSR and ML occur together in one paper. A failed live check should not erase the prepared candidates.

Start with explicit ordering by concept coverage and evidence strength before tuning a blended score. Freeze a small evaluation set first; add numerical weights only if they improve held-out cases. Keep all expensive profile preparation outside the visitor's request.

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
