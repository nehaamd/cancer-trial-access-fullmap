# Ask the map v3 — architecture and contract

This document is the single source of truth for the v3 question box. Every component (data catalog, engine, worker, client,
tests) is built against it. Where code and this document disagree, fix the code or update this document in the same change.

## 1. Why v3

v2 read questions with a hand-written regex parser that mapped each question onto one of nine fixed "shapes". Anything outside
those shapes was answered wrongly or not at all, and every new kind of question meant another regex. v3 inverts the design:

* **The model plans, the engine computes.** A Claude model is given *tools* that read the site's data (filter, rank, aggregate,
  look up, compare, resolve places, list trials, read the site's own methods text). It calls them, reads the results, and
  finishes by calling `final_answer`. It never computes a number itself.
* **Tools run in the browser (and in Node for tests), against the same data the map shows.** The map page already holds every
  layer in memory. The engine (`docs/ask/engine.js`) runs the tools over the published data API files plus the map's own data
  files, so a figure in an answer is the figure on the map, and every number carries the file it came from.
* **The worker is a stateless, signed, rate-limited model proxy with a verifier.** It holds the API key, builds the system prompt
  and tool definitions from the catalog, calls the model, verifies every number and place name in the final answer against the
  tool results, and signs what the model said so a client cannot forge assistant turns.
* **Not knowing is an answer.** The catalog tells the model exactly what exists and what does not; the engine rejects unknown
  fields with a list of what is available; the final answer carries `answerable: yes | partly | no` and `not_in_data`.

## 2. Components and files

| Path | Role | Runs in |
|---|---|---|
| `docs/ask/catalog.js` | The data dictionary: tables, fields (path, type, unit, meaning, nulls, source), enumerations, key-term definitions, what is NOT in the data, map layers per unit and which layer shows which field, `site_info` topics. ES module, no I/O. | browser, worker, Node |
| `docs/ask/engine.js` (+ `places.js`) | Loads the data (browser: `window.DATA/BURDEN/…` + fetched `api/*.json`; Node: files on disk), builds indexes, executes tools. Pure functions after load; never throws on well-formed input (returns `{error}` results). | browser, Node |
| `docs/ask/ask.js` | The client: drives the step protocol, executes tools with the engine, shows progress, renders the answer card and results list, applies the map view, follow-ups. | browser (map.html) |
| `worker/src/index.js` | HTTP: CORS, limits, `POST /ask` (step protocol), `/health`. | Cloudflare Worker |
| `worker/src/prompt.js` | System prompt + tool JSON schemas, generated from the catalog. | worker, Node |
| `worker/src/verify.js` | Final-answer verification (numbers, names, ids, style). | worker, Node |
| `worker/src/sign.js` | HMAC-SHA256 of assistant turns (Web Crypto). | worker, Node |
| `worker/src/loop.js` | `step(request, env, callModel)`: one protocol step incl. internal verification retries. Pure apart from `callModel`. | worker, Node |
| `worker/tests/` | `engine.test.js` (tool semantics vs independent Python), `loop.test.js` (protocol/verification with a scripted fake model), `eval.js` (live model evaluation, needs `ANTHROPIC_API_KEY`), `expected.py` (independent expected facts). | Node |
| `build_api.py` | Fixes to the published API (see §9). | Python |

Node 22, ESM, no package.json (syntax detection). No dependencies.

## 3. Step protocol (client ⇄ worker)

The client drives the loop; the worker keeps no state. Each HTTP call is one model step.

`POST {ASK_URL}` with JSON:

```json
{ "v": 3,
  "q": "which counties and districts in texas have oncologists but no clinical trials?",
  "turns": [ { "assistant": [ ...content blocks exactly as the worker returned them... ],
               "sig": "hex",
               "results": [ { "tool_use_id": "toolu_…", "content": "…JSON string…", "is_error": false } ] } ],
  "prior": [ { "q": "previous question", "answer": "its final answer text" } ],
  "client": { "page": "map", "unit": "county" } }
```

* `q`: 3–400 characters. `turns`: 0–8 earlier steps of *this* question. `prior`: up to 3 earlier (question, answer) pairs for
  follow-ups (the worker renders them as earlier user/assistant text turns). `client` is informational.
* Each `turns[i].assistant` must verify against `turns[i].sig` (HMAC over the canonical JSON of the blocks with the worker's
  secret); otherwise 400 `{error:"bad transcript"}`. Each `tool_use` block in a turn must have exactly one result; a result's
  `content` is capped at 24 KB (the client truncates with `"…(truncated)"` before sending; the engine already caps rows).

Responses (always JSON, `cache-control: no-store`):

```json
{ "v": 3, "kind": "tools", "step": 2, "assistant": [ blocks ], "sig": "hex",
  "calls": [ { "id": "toolu_…", "name": "query", "input": { … } } ] }
```
```json
{ "v": 3, "kind": "answer", "step": 3, "assistant": [ blocks ], "sig": "hex",
  "answer": { …the final_answer tool input, see §6… },
  "verification": { "ok": true, "issues": [], "retries": 0 },
  "model": "claude-sonnet-5-5" }
```

* `kind:"tools"`: the client runs every call with the engine (in parallel is fine), appends `{assistant, sig, results}` to `turns`,
  and posts again. The worker calls the model with `tool_choice: {type:"any"}`, so every step ends in tool calls; a text-only
  reply is returned as `kind:"answer"` with `answer:{answer:<text>, answerable:"partly"}` and verified like any other.
* `kind:"answer"`: the loop ends. If `verification.ok` is false the client MUST NOT show `answer.answer`; it shows the results
  (table / highlights) with the notice in §7 instead. The worker has already retried verification failures internally
  (up to 2 extra model calls, each fed the failure as a `tool_result` error for the `final_answer` call), so `ok:false` is rare.
* Errors: `400 {error}` (bad request / transcript), `403 {error}` (origin), `429 {error, retry_after_s}` (per-visitor minute
  limit or the daily cap; only step 0 of a question counts toward limits, later steps of the same question are free),
  `502 {error, detail}` (model or internal failure), `504 {error}` (model timed out). Error texts are plain sentences the client
  shows as-is.
* Limits: `MAX_STEPS = 8` model calls per question (the 8th is forced to `final_answer` with `tool_choice:{type:"tool",
  name:"final_answer"}`), `max_tokens` 1200 per call, model timeout 25 s per call. A single HTTP step may contain up to 3 model
  calls (verification retries), so the client waits up to 90 s per step with a visible progress line.
* Model calls: `POST https://api.anthropic.com/v1/messages`, `anthropic-version: 2023-06-01`, body
  `{model, max_tokens, system:[{type:"text", text, cache_control:{type:"ephemeral"}}], tools:[…, last tool with cache_control],
  tool_choice, messages}`. No `temperature` (current models reject it). `MODEL` comes from `env.MODEL` (default
  `claude-sonnet-5-5`); `env.MODEL_FAST` may name a cheaper model for steps whose only output is tool calls when set.

## 4. Tables (what `query`, `aggregate`, `profile`, `compare` read)

All field paths are dotted. `id`, `name`, `state` and (where present) `pop55` are always returned.

| table | rows | source | id | notes |
|---|---|---|---|---|
| `counties` | 3,143 | `api/all_counties.json` + map files | 5-digit FIPS | + `districts` (array of district ids that overlap the county, from the districts table), `zero_trial_share_by_type.<type>` (BURDEN.county.zt: % of residents 55+ with no recruiting trial of that type within 60 road-miles), `oncologists.per_100k_pop55` (computed) |
| `districts` | 436 | `api/all_districts.json` + map files | `TX-34` (also `geoid` 4-digit for the map) | + `member.bioguide`, `member.cosponsor_date`, `county_names`, `deaths_vs_access` {counties_classified, high_death_low_access_counties, ids} (MORTALITY.summary.districts) |
| `states` | 51 | `api/all_states.json` + map files | USPS | + `mortality` {rate_all_sites? no: state-level published death rates are not in the map data; present: high_death_low_access_counties, pop55, deaths_per_year (MORTALITY.summary.states hh_*)}, `nci_centers_count`, `trials_distinct` (DATA.state_data.trials), `broad_menu_counties`, `limited_menu_counties`, `counties_with_trials`, `rucc_codes` (per-code access from RUCC.states) |
| `national` | 1 | `api/national.json` + map files | `US` | + `mortality` (MORTALITY.meta.us by site), `history` (CHANGES.history), `rucc_codes` |
| `nci_centers` | 67 | DATA.nci | `nci:<index>` | name, full_name, state, tier (Comprehensive / Clinical), lat, lon |
| `facilities` | 9,655 | DATA.counties[*].fac | `fac:<site_id>` | name, city, zip, county_id, county_name, state, trials (count), unresolved (bool) |
| `senators` | 100 | states.senators + COSPONSORS | bioguide | name, party, state, s4440 (sponsor/original/cosponsor/none), cosponsor_date |
| `cosponsors` | ~33 | COSPONSORS.by_member | `<bioguide>:<bill>` | name, party, state, chamber, district_id, bill (ctma_hr/ctma_s), bill_label, role, date |

The catalog (`catalog.js`) lists every field of every table with: `type` (number / integer / string / boolean / array / object),
`unit`, `desc`, `nulls` (what null means), `enum` (allowed values when categorical), `source` (key into `SOURCES`, which carries
the file/URL and vintage), `computed` (true when the engine derives it from published fields, with the formula in `desc`), and
`layer` (which map layer shows it, per unit). Fields that exist only when a map file is loaded are marked `optional`; the engine
reports them as `not loaded` (not null) when absent.

`trials` are not a table (columnar, 4,035 rows, 22 columns in `DATA.T`); they are reached through the `trials` tool.

## 5. Tools

Every tool returns JSON. Errors are returned as `{error: "…", hint: "…"}` (never thrown); e.g. an unknown field returns
`{error:"unknown field 'oncologist_count' in table 'counties'", hint:"did you mean oncologists.count? Fields: …"}`.
Every result that reads a table carries `source: {file, url, as_of}`; aggregates carry `note` saying they are computed by the
engine from the rows (not published figures).

### `find_places`
`{query: string, kind?: "county"|"district"|"state"|"zip"|"town"|"member"|"senator"|"nci_center", state?: USPS, limit?: ≤10}`
→ `{matches: [{id, table, kind, name, state, pop55?, how: "exact"|"fuzzy"|"zip"|"town"|"member"|"senator"|"namesake", note?}],
ambiguous: boolean, hint?}`. Resolves county names (with/without County/Parish/Borough/Census Area; 1–2 edit typos; namesakes
across states listed with pop55 so the model can ask), district codes in every form (`TX-34`, `Texas 34th`, `34th district of
Texas`, `TX 34`, at-large), states (name, USPS, demonym), 5-digit ZIPs → county (`zip_county.json`), towns → county
(`places.json`), House members → district, senators → state, NCI centers by name. A ZIP/town/member/senator match carries
`via` text ("ZIP 78501 is in Hidalgo County, Texas").

### `query`
```
{ table, where?: [cond | {any_of:[cond…]}], order_by?: [{field, dir:"asc"|"desc"}], limit?: 1–50 (default 20), columns?: [path…] }
cond = { field, op: "="|"!="|">"|">="|"<"|"<="|"in"|"not_in"|"is_null"|"not_null"|"contains"|"includes"|"intersects"|"between", value }
```
* Conditions at the top level are ANDed; `any_of` ORs its members. `value` may be `{field: "other.path"}` to compare two fields.
  `contains` = case-insensitive substring on strings; `includes` = array field contains value; `intersects` = array field shares
  any value with the list; `between` takes `[lo, hi]` inclusive.
* Rows whose compared field is null never match `<`, `>`, `=`, etc. (only `is_null`). The result reports how many rows in scope
  had a null for each filtered/ordered field (`nulls`).
* `order_by` puts nulls last. Ties are broken by `pop55` desc then `name`.
* Result: `{table, count, in_scope, returned, columns, rows:[{id,name,state,pop55,…}], nulls:{path:n}, ids_truncated: boolean,
  sum_pop55_matching, source}`. `count` = rows matching; `in_scope` = rows in the table (after any `state` filter in `where`).
  The engine keeps the full list of matching ids under the call's id for `highlight.from_call` / `table.from_call`.
* Default columns per table are the short "headline" set in the catalog (`DEFAULT_COLUMNS`), plus every field named in `where`
  and `order_by`.

### `aggregate`
```
{ table, where?, group_by?: path (categorical fields only, listed in the catalog as `groupable`),
  measures: [{field, stat: "count"|"count_not_null"|"sum"|"mean"|"weighted_mean"|"median"|"min"|"max"|"share_true"|"share_eq", weight?: path (default pop55), value?: any (for share_eq)}] }
```
→ `{table, count, groups:[{group: value|null, n, sum_pop55, measures:{"<field>:<stat>": number|null}}], note, source}`.
Means and shares to 1 decimal; sums and counts integers. `note` always says: "Computed by the engine across the matching rows;
a mean of county rates is not the published state rate (use the states table for that)."

### `profile`
`{table, id}` → `{row: <full row, nested>, related: {…}, source}`. `related` for a county: `districts` [{id,name,member,party,
ctma_hr3521}], `senators`, `state_row_headline` {pct_lt20…, pct_zero…, median_road_mi_nci}, `national_headline`; for a district:
`counties` [{id,name,pop55}], `member` (+cosponsor_date), `senators`; for a state: `senators` (+dates), `nci_centers` [names],
`metro_nonmetro`; for national: nothing extra.

### `compare`
`{table, ids: [2–6], columns?}` → `{rows, reference: [state rows for the ids' states (counties/districts), the national row], source}`.

### `trials`
```
{ scope: {county_id} | {within_60_of_county_id} | {state} | {national: true},
  cancer_type?: key, phase?: "1"|"1-2"|"2"|"2-3"|"3"|"4"|"NA", sponsor_type?: "industry"|"academic_other"|"nih_federal",
  keyword?: string (matched in title, interventions and keywords, case-insensitive), min_age_at_most?: int, limit?: ≤25 }
```
→ `{count, by_phase, by_sponsor_type, by_cancer_type (top 10), sample:[{nct, title, phase, sponsor, sponsor_type, cancer_types,
start, last_update}], link (trials.html?county=… or find.html?…), note}`. Counts are distinct trials; `within_60_of_county_id`
uses the county's site points within 60 road-miles of its population center (the map's `t60`). This is "trials listed", never
"trials available to a person" (the note says so).

### `site_info`
`{topic: "bills"|"methods"|"definitions"|"sources"|"limits"|"how_to_act"|"findings"|"history"|"changes"|"about"|"finder"|"rural"|"need_vs_access"|"deaths_vs_access"|"oncologists"}`
→ `{topic, text, url, numbers?: {…}}`. Text is the site's own wording (curated in `catalog.js` `SITE_INFO`), numbers (where
relevant) are read from FINDINGS / COSPONSORS / CHANGES / MORTALITY / BURDEN / ONCOLOGISTS / RUCC at call time.

### `final_answer`
See §6.

## 6. `final_answer` (the model's last call)

```json
{ "answer": "Plain prose, 1–6 sentences. Every number is one that appeared in a tool result (same digits, or the result value rounded to the precision written: 11,802,321 may be written 11.8 million). No markdown, no URLs, no advice, no first person.",
  "answerable": "yes" | "partly" | "no",
  "interpretation": "One or two sentences: how the question was read and the exact rule applied, in words (e.g. 'Counties in Texas with at least one oncologist with a Medicare practice location in the county and no recruiting trial with a site in the county').",
  "alternatives": [ "Other reasonable readings, phrased as questions the reader could ask instead (≤3)" ],
  "not_in_data": [ "What was asked for that the data does not have, each as one sentence (≤4)" ],
  "caveats": [ "Small-numbers rates, ties, truncation, vacant seats, no-road-route places, different data periods … (≤5)" ],
  "map": { "unit": "county"|"district"|"state", "layer": "<key in MAP_LAYERS[unit]>", "params": {"site"?,"acs"?,"type"?,"lt"?,"rural"?,"crit"?,"thr"?},
           "state": "TX" (focus; optional), "place": "<id to select>" (optional, single-place answers),
           "highlight": { "from_call": "toolu_…" } | { "ids": ["48215", …] }, "highlight_label": "Counties with oncologists but no recruiting trial" },
  "table": { "from_call": "toolu_…" } | { "columns": ["…"], "rows": [[…]] },
  "sources": [ "counties", "districts" ],
  "follow_ups": [ "≤3 short follow-up questions" ] }
```

Rules the worker enforces (`verify.js`):
1. Every number in `answer`, `interpretation`, `caveats`, `not_in_data` must be (a) present in some tool result of this question
   (digits equal after removing thousands separators), or (b) a tool-result number rounded to the written precision (≥2
   significant digits; `million`/`billion`/`thousand`/`k` multipliers handled), or (c) present in the question, or (d) one of the
   definitional constants (55, 60, 20, 100, 30, 120, 200, 3521, 4440, 119, 2000, 1-800-4-CANCER digits) or a year/period string
   present in the catalog vintages. Number words above ten are checked the same way; one–ten are allowed.
2. Every capitalised token in `answer` that is not in the stoplist (common sentence words, the site's own vocabulary) must appear
   in a tool result, in the question, or in the catalog text.
3. `map.highlight.ids`, `map.place` must appear in tool results; `map.highlight.from_call` / `table.from_call` must name a
   `query`, `compare`, `profile` or `find_places` call of this question; `map.layer` must be in `MAP_LAYERS[map.unit]`;
   `params` values must be in the catalog enumerations.
4. Style: no `http`, no markdown (`**`, `#`, backticks, bullets), no "I"/"as an AI", no advice verbs (should, recommend, consult,
   eligible…), no claim that a trial is "available to" a person. ≤ 1,200 characters in `answer`.
5. `answerable:"no"` requires `not_in_data` to be non-empty and `answer` to say what the data does have instead (may be short).
On failure the worker sends the model a `tool_result` error for the `final_answer` call listing the issues and retries (≤2).

## 7. Client behaviour (ask.js)

* Mount: the existing box (`SITE.mountAskBox`) on map.html and the homepage hero (homepage keeps the GET redirect to
  `map.html?ask=`). The box shows live progress per step in `#ask-status` and in the busy card: "Finding Texas counties with
  oncologists and no trials… (step 2 of up to 8)"; each executed tool call is described in plain words from its input
  (e.g. "Counties where oncologists.count > 0 and trials_listed_here = 0, in TX → 38 match").
* First question: load `api/all_counties.json`, `all_districts.json`, `all_states.json`, `national.json` (≈ 800 KB gzipped)
  with the status "Loading the data files (first question only)…"; the map's own globals are used as loaded.
* Answer card (right pane, as now) shows in order: the question; the answer (only if verified); "How this was read"
  (interpretation; alternatives as buttons that re-ask); "Not in the data" (distinct style); the results table from `table`
  (full engine result, sortable headers, up to 100 rows with "show all", place cells link/select on the map); summary counts
  (matching / in scope / residents 55+ in the matching places); caveats; "Map now shows: …" with the highlight label and a
  **Focus** toggle (non-highlighted features at reduced opacity, default on when ≤ 400 ids); "Read from" (files + vintages from
  `sources`); "How this was answered" (collapsed step log); follow-up chips; the standing note (not medical advice, lists not
  matches). An unverified answer shows the notice: "The written summary could not be checked against the data, so only the data
  is shown." and the table/map.
* Map: validate `map` against the catalog and the map's `UNIT_METRICS`; build the query string (`u`, `m`, params, `s`, `c/d`),
  `history.pushState`, `applyURL(false)`, `highlight(ids)`, focus dim; outlines survive repaint/zoom/unit change (existing
  `__askSync`). Ids of a unit other than the current are kept and drawn when the unit matches, as now.
* Follow-ups: the client keeps the last 3 (q, answer) pairs and sends them as `prior`; "Ask a follow-up" placeholder after an
  answer; "Clear" starts fresh.
* Errors: 429 → the worker's sentence + retry countdown; 502/504 → "The question box is unavailable right now; the map and its
  filters still work." + detail; network timeout per step 90 s.
* Everything the model wrote is HTML-escaped; links come only from the engine/catalog (never from model text).

## 8. Tests and evaluation

* `node worker/tests/engine.test.js`: tool semantics (filters, ops, nulls, ordering, aggregates, place resolution incl.
  namesakes/typos/ZIPs/towns/members, trials scope, profile/compare/related, error shapes), with expected values recomputed
  independently by `python3 -I worker/tests/expected.py` (writes `worker/tests/expected.json`) — never by the engine.
* `node worker/tests/loop.test.js`: the protocol with a scripted fake model: signatures, forged turns rejected, result caps,
  forced final at MAX_STEPS, verification accept/reject cases (rounded numbers, invented numbers, re-attributed places, bad ids,
  markdown, advice), internal retry, limits, prompt/tool schema validity (JSON-schema shape, every catalog field referenced
  exists in the engine).
* `node worker/tests/eval.js [--max N] [--worker URL]`: ~80 questions (`eval_questions.json`) through the real model: either
  in-process (`ANTHROPIC_API_KEY` in env, loop.js + engine.js in Node) or against a deployed worker (`--worker`). Each question
  carries machine checks written by `expected.py`: expected highlight set (exact / superset / subset), numbers that must appear,
  `answerable` expected, phrases that must/must not appear ("not in the data", no advice). Prints per-question PASS/FAIL and a
  pass rate; exits 1 below 90 %. Runs in `.github/workflows/ask-eval.yml` (workflow_dispatch) and after each worker deploy.
* `release_gate.py` gains: the two offline suites must pass.

## 9. Data fixes (build_api.py)

1. `trials_listed_here` for districts and states was the census-tract count (`nt`). Districts: distinct recruiting trials with a
   site in any county overlapping the district (union of `DATA.counties[f].tr` over `counties`); states: `DATA.state_data[st].trials`.
2. `wmean_trials_within_60rdmi` was null for 48 dense districts and New Jersey because `fnum()` treated any value ≥ 999 as the
   no-road-route sentinel. The sentinel applies to distance fields only.
3. County rows gain `districts` (ids of overlapping districts, from the district lists) — documented in `FIELDS` and api.html.
4. Every other value stays byte-identical (checked by a diff script in the change).

## 10. Non-goals and honesty rules

* No tract-level queries (the map draws tracts, but the engine answers at county, district, state and national level).
* No eligibility, prognosis, treatment or "which trial is right for me" answers: the system prompt routes these to the fixed
  scope text (`SCOPE_TEXT`), with the NCI Cancer Information Service number.
* No data below age 55, by race/ethnicity, by insurance type, trends beyond the weekly national history, travel cost, or
  enrolment status; the catalog's `NOT_IN_DATA` list names these and the model is told to say so.
* The model may not infer causes ("because rural areas lack…"); it reports what the data shows.

## 11. Engine interface (docs/ask/engine.js) — used by the client, the worker tests and the eval runner

```js
import { createEngine } from './engine.js';
const engine = createEngine({ sources });        // see below; no I/O in the constructor
await engine.load();                             // loads/parses everything it needs; idempotent; reports progress via options.onProgress(text)
engine.loaded                                    // { counties: true, districts: true, …, optional: { burden: true, mortality: false, … } }
const r = await engine.run(name, input, callId); // runs one tool; never throws; returns the JSON-able result object the model sees
engine.describeCall(name, input)                 // plain-English one-liner for progress ("Counties where oncologists.count > 0 and trials_listed_here = 0 in TX")
engine.describeResult(name, input, result)       // one-liner for the step log ("38 match; showing 20")
engine.full(callId)                              // { ids: [...all matching ids...], unit: 'county'|'district'|'state'|null, rows: [...all matching rows, trimmed to the returned columns...], columns } for query/compare/profile/find_places calls (for highlight.from_call / table.from_call); null otherwise
engine.sourcesFor(tables)                        // [{ table, title, file, url, as_of }] for the "Read from" line
engine.placeName(id) / engine.unitOf(id)         // "Hidalgo County, Texas" / 'county'
engine.vintages()                                // { data_as_of, incidence_period, mortality_period, oncologists_pulled, cosponsors_fetched, acs } where known
```

`sources` tells the engine where data comes from:
* Browser (map.html): `{ globals: window, fetchJSON: url => fetch(url).then(r => r.json()), base: '' }` — the engine reads `window.DATA`, `window.BURDEN`, `window.MORTALITY`, `window.ONCOLOGISTS`, `window.RUCC`, `window.COSPONSORS`, `window.FINDINGS`, `window.CHANGES` when present, and fetches `api/all_counties.json`, `api/all_districts.json`, `api/all_states.json`, `api/national.json`, `places.json`, `zip_county.json` relative to `base`.
* Node: `{ root: '/path/to/repo' }` — the engine reads the same files from `docs/` on disk (the `window.X=` files are parsed by stripping the assignment).

Missing optional files (a map file not loaded) make their fields report `"not loaded"` in results and `loaded.optional.<name> = false`; the engine still answers everything the API files cover.
