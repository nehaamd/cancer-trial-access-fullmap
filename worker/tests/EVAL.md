# Ask the map v3 — live evaluation

`eval_questions.json` holds 110 questions a visitor might type (patient, caregiver, clinician, advocate, journalist, policy
staffer); `eval_expected.py` computes, from the raw published files and never from the engine, the facts the checks refer to
(`eval_expected.json`); `eval.js` drives the ASK_CONTRACT §3 step protocol through the real model and the real engine and
applies the checks; `eval_checks.js` is the check logic, unit-tested by `eval_checks.test.js`.

```
python3 -I worker/tests/eval_expected.py                        # regenerate expectations after a data refresh
node worker/tests/eval_checks.test.js                           # the check logic itself (no model, no engine)
ANTHROPIC_API_KEY=… node worker/tests/eval.js                   # in-process: loop.js + engine.js in Node
node worker/tests/eval.js --worker https://…workers.dev/ask     # against a deployed worker (tools still run locally)
options: --max N  --only substr (id, category or question)  --model NAME  --verbose  --json out.json  --md summary.md
```

Exit code 1 when the pass rate is below 90 % or when any `scope`, `other` or `injection` case fails (hard gates). Three
questions run at a time; each has 120 s. The `--json` file carries the full transcript of every question (each step's
assistant blocks, tool calls, engine results, the final answer, verification, usage) for reading afterwards.

## Question entry

```json
{ "id": "O01", "cat": "oncologists", "q": "which counties and districts in texas have oncologists, but no access to clinical trials?",
  "prior": [ { "q": "…", "answer": "…" } ],          // optional: earlier pairs, sent as `prior` (follow-up questions)
  "note": "why the case is ambiguous or unanswerable", // optional, for the reader
  "checks": { … } }
```

Categories (`cat`) group the report; `scope`, `other` and `injection` are hard gates.

## Expected record (eval_expected.json → questions[id])

Free-form per question; the checks name its keys. Conventions: `ids` / `*_ids` are lists of county FIPS, district ids
(`TX-34`) or USPS codes; `numbers` is a map of named values (`count`, `top_value`, …); `place_first` is
`{first: [ids that may be named first], among: {id: [name variants]}}`; `states` is a list of state names (namesakes).
Rankings follow the query tool's tie rule (value, then residents 55+ descending, then name; nulls last). Where a question has
two honest readings both are stored (e.g. `ids_center` / `ids_median`) and the check says `any_of`.

## Checks vocabulary

| check | meaning |
|---|---|
| `answerable` | `final_answer.answerable` must be the value, or one of the list (`["yes","partly"]`). |
| `verified` | default true: `verification.ok` must be true (the client would not show an unverified answer). `false` skips it. |
| `unit` | `map.unit` must be the value / one of the list. |
| `layer` | `map.layer` must be one of the list (keys of `MAP_LAYERS[unit]`). |
| `params` | each key/value must appear in `map.params` (e.g. `{"site":"breast"}`). |
| `highlight` | `{mode, ids_key}`: the highlighted ids (`map.highlight.ids`, or `engine.full(from_call).ids`) against `expected[ids_key]`. Modes: `exact` (same set), `superset` (answer ⊇ expected), `subset` (non-empty and ⊆ expected), `nonempty`, `none`, `exact_if_present` (exact when a highlight exists, nothing required otherwise), `subset_or_none`. |
| `place_or_highlight` | `{ids_key}`: `map.place` is one of the expected ids, or the highlight is a non-empty subset of them (single-place lookups). |
| `numbers_present` | list; each entry is a key into `expected.numbers`, a literal number, or `{any_of: [keys]}`. The number must appear in the answer text under the §6 rounding rule: same digits (thousands separators ignored), or the expected value rounded to the written precision with at least 2 significant digits (`11.8 million` for 11,802,321; `43%` for 42.7; not `40`), `million/billion/thousand/k` handled; the words one–twenty count as numbers. |
| `numbers_absent` | the same, but the numbers must not appear. |
| `text_must_match` / `text_must_not_match` | case-insensitive regexes on the answer text. |
| `any_text_must_match` | regexes on the answer, interpretation, alternatives, not_in_data, caveats and highlight label together. |
| `place_first` | `{key}`: of all candidate place names in `expected[key].among`, the one that appears earliest in the answer must be in `expected[key].first` (ties in the data give several acceptable firsts). |
| `scope_text` / `other_text` / `fixed_text` | the answer equals `SCOPE_TEXT` / `OTHER_TEXT` / either (whitespace and quote style normalised; the fixed text with at most a little framing passes, anything longer fails). |
| `ambiguous_offers` | `{key, min}`: at least `min` of the state names in `expected[key]` are offered somewhere in the answer, alternatives or caveats. |
| `not_in_data_nonempty` | `final_answer.not_in_data` has at least one entry. |
| `max_steps` | the question took at most this many model steps. |
| `table_from_call_matches_highlight` | when both `table.from_call` and `map.highlight.from_call` are set they name the same call or the same id set. |
| `any_of` | a list of check sets; at least one must pass in full (sibling checks still apply). |
| `pairs` | a key into the expected record (usually `"pairs"`): a list of `[[name variants], value]`, one per place the question names. Each place must be written with its own figure in one clause of the answer: place names are masked first (so the comma in "Hidalgo County, Texas" does not split), clauses split at `; ,` and the comparison words (against, compared with, than, while, whereas, versus, and, but, with, to, from); a clause with no place takes the nearest place of its sentence; the figure (§6 rounding rule) must have this place as its nearest place in the clause. "Wyoming at 87%, against 33.1% in Montana" pairs both; the swapped figures, or "87% and 33.1%, respectively", do not. |

## Attribution questions (`attribution`, AT01–AT10)

Comparisons of two or three named places with different values ("which is higher, X or Y"), and rankings where each place must
carry its own figure. They exercise the worker's per-place claim check (ASK_CONTRACT §6 rule 6) from the outside: the `pairs`
check fails an answer that writes a correct number next to the wrong place. For rankings, only places strictly ahead of the
cut-off are paired (a tie at the cut-off may be listed either way).

## Honest cases kept on purpose

* Ties: 139 Texas counties at 100 % short (R01), three districts at 100 % (R02), four states at 0 % (R03), Vermont/Wyoming at
  70.3 % nonmetro (U04), Socorro/McKinley at 33.2 % poverty (H01), six Georgia districts at 0 % (R07). The checks accept any
  tied first place.
* Two readings: "more than 100 road-miles from an NCI center" by county center (178 counties) or by residents' median (183),
  T02; "furthest" by median or by center (R06); cosponsor count with or without the sponsor (C06); lung trials counted by any
  listed cancer type (4) or by primary category (3) near Hidalgo County (Y01); DC first or Massachusetts first for oncologists
  per 100,000 (O03).
* Not in the data: state death rates by site (Y03), district death rates (Q01), race (Q02), tracts (Q03), enrolment (Q04),
  results (Q05), travel cost (Q06), Commission on Cancer sites (Q07), a five-year trend (Q08), Puerto Rico (Z01). The answer
  must say so (`answerable` no/partly, `not_in_data` non-empty) and may offer what exists instead.
* Derived counts: "how many Texans 55+ live more than 60 road-miles from an NCI center" has no published people count (P02);
  the share (42.7 %) or pop55 × share is accepted.
* Namesakes: Washington County (30 states) and Lincoln County (23) must be asked back; Hidalgo County is assumed to be Texas
  (182,206 vs 1,539 residents 55+) with New Mexico mentioned (A03).
* Traps: Sylvester "Comprehensive" Cancer Center carries the Clinical tier in the data (I01); TX-23, the district with the
  most high-deaths-low-access counties, is a vacant seat (N05); ZIP 78501 sits in a county split between two districts (S05).
* District `trials_listed_here` in the published API is still the tract count until build_api.py's §9 fix lands; the
  expectations use the §9 definition (distinct trials in overlapping counties) where it matters.
* "Houston" resolves as ambiguous in find_places (the city plus Houston Counties in GA, AL, TX…); Y06 still expects the city
  (Harris County), the only reading a visitor means.
* F04 expects the site's own figure for basket trials (1,137 = 28.2 %, trials whose primary category is `multi`, as the finder
  and the Limits text count them); the engine's trials tool with `cancer_type: "multi"` currently counts trials that list
  `multi` among their categories (469), so a failure here points at the engine, not the model.
