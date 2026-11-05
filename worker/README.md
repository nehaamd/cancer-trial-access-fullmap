# "Ask the map" helper

A small Cloudflare Worker behind the question box on the map and the homepage. It holds the Anthropic API key (the site's
code never sees it), reads the same published data files as the Data API (`docs/api/*.json`, `docs/places.json`,
`docs/zip_county.json` on the live site), and returns an answer whose every number is read from those files. The site moves
the map to `view` and outlines the places in `view.hl`.

## Parser first, models second

```
question
  │
  ├─ parseQuestion(q, ctx)      deterministic: fixed vocabulary + place indexes built from the data files   ──► plan
  │     └─ null (not confident) ─► planWithModel(q) (Haiku) ─► checkPlan(q, plan, ctx): the question text overrides the model
  │
  ├─ load the files the plan needs (parsed JSON and the place indexes memoised in the isolate for an hour, then the edge cache):
  │   county names resolve from api/county_names.json (~150 KB); a single county comes from api/county/<FIPS>.json;
  │   county-wide rankings, counts, thresholds and need-vs-access read the compact api/ask/counties.json (1.1 MB, ~6 ms to parse)
  │   plus api/ask/county_sites.json (650 KB) only for site-specific incidence / death-rate questions; all_counties.json (9 MB,
  │   ~35 ms to parse) is never fetched by the worker
  ├─ execute(plan, data)        pure arithmetic: filter, sort, count, sum ──► table, rows, view, sources, caveats
  ├─ composeAnswer(plan, result) deterministic sentences from the table (the fallback and the reference)
  ├─ writer model (Sonnet, 15 s limit) rewrites the draft from the table and summary ─► verifyAnswer(text, table, [summary]):
  │   every number in the text must be in the table or summary with the same rounding; number words ("one million", "half") only
  │   if the table has them; every capitalised name must be a place, centre or member in the table (no re-attributed figures);
  │   the first row's place and one of its figures must appear; at least one table number; no URLs, no "I", no advice, no
  │   markdown ─► otherwise the draft is used (deterministic: true). The planner has an 8 s limit; a slow or failing model never
  │   produces a 502, only the fixed reply or the composed answer
  └─ respond
```

The models never compute a number, never see anything but the question, the table and the draft, and nothing they write
becomes a URL, an id or code: ids come only from the data files; the finder's keyword must be a word of the question itself.

### Honest measures

A measure asked at a level where it is not published is never swapped silently: by-site incidence and death rates and
deaths per year exist for counties only, oncologists per 100,000 for states. The answer moves to the level that has the
measure ("Lung & bronchus cancer death rate is published for counties only, not states; here are the counties instead"),
or to a state / national lookup, and says so in the first sentence and in `caveats` (`plan.level_note`). A county question
about one cancer type's trials ranks all-cancer trials within 60 road-miles and says so (`plan.flags.type_fallback`).

### What the parser reads

- **Places**: state names and codes ("Washington state" vs "Washington County" vs DC; demonyms such as "Texans"), county names
  with or without County / Parish / Borough / Census Area / independent "city" (St./Saint, DeKalb/De Kalb, Doña Ana), district
  forms (TX-34, TX34, DE-AL, "Texas 34th", "34th district of Texas", "Texas's 34th", at-large), ZIP codes (via zip_county.json),
  towns (via places.json; "Houston, TX"), members of Congress by full name or surname (surnames need a title or a cosponsor /
  represents cue), senators. One or two edits are tolerated in county and state names ("Hildago County Texas", "Texs") and in
  keywords ("distrcits", "acess").
- **Ambiguity**: a county name that exists in several states with no state given ("Washington County", "Lincoln County") is
  returned as `ambiguity: {kind, options}` with an answer that asks which one; the map does not move. When there are only two
  or three namesakes and one has at least 20× the residents 55+ of each other ("Hidalgo County": Texas 182,206 vs New Mexico
  1,539), the largest is assumed and a caveat names the others. Territories get an honest
  out-of-scope reply; unknown places are said to be unknown.
- **Metric phrases** for every layer and API field (see the table below), the incidence / death-rate site, the ACS variable,
  the cancer type (synonyms: NSCLC → lung, CRC → colorectal, ovarian → gynecologic, AML → leukemia, glioblastoma → brain_cns, …).
- **Ordering**: "worst / best" are quality words; "most / highest / fewest / lowest / furthest / closest" are magnitudes mapped
  through the measure's own sign (`worse: high|low` in `METRICS`, applied to the final metric): "most trials" = best, "most people
  short" = worst, "most" always puts the maximum first; "20 or more trials" inverts. A cancer word bound to an incidence or
  death-rate site sets `site=`, never the trial-type filter; `type=` is set only for questions about trials of that type.
- **Shapes**: ranking (`n` from "top 5", "worst 3 districts", "which single county"), lookup (one place, ZIP, town, member,
  state, nation), compare (2–4 places; "vs", "compare", "Montana or Wyoming", "against the national average"), count ("how many
  counties …"), threshold ("counties where more than half …"), who-represents / cosponsor (H.R. 3521 House, S. 4440 Senate;
  "have not cosponsored"), need-vs-access (high incidence or deaths AND low access, with the map's rule), by cancer type,
  search (trials near ZIP / town, keyword, age, radius), scope (medical / eligibility), other (definitions, off-topic, injection).

### Metric coverage (question phrase → field → map layer)

| Question phrase | Field | county `m=` | district / state `m=` |
|---|---|---|---|
| short of trials, fewer than 20, access, 20 or more (inverted) | `pct_lt20_trials_within_60rdmi` | `short` | `l20` |
| how many people / residents short | `people_lt20_trials_within_60rdmi` | `short` | `l20` |
| no trial within 60 | `pct_zero_trials_within_60rdmi` | `short` | `z60` |
| most people / residents with no trial within 60 | `people_zero_trials_within_60rdmi` | `short` | `z60` |
| most people / residents beyond 60 miles of an NCI center (broad menu) | computed: `pop55 × pct_gt60rdmi_nci ÷ 100` (`…broad_menu`), rule stated in the table | `rn` / `rb` | `g60n` / `g60b` |
| fewer than 100 trials | `pct_lt100_trials_within_60rdmi` | `short&lt=100` | `l20&lt=100` |
| beyond / more than 60 miles from an NCI center | `pct_gt60rdmi_nci` | `rn` | `g60n` |
| beyond 60 miles of a broad menu / county with 100+ trials | `pct_gt60rdmi_broad_menu` | `rb` | `g60b` |
| how far / median miles to NCI center, furthest, closest | `median_road_mi_nci` | `rn` | `medn` |
| median miles to a broad-menu county | `median_road_mi_broad_menu` | `rb` | `g60b` |
| nearest NCI center (name) | `nearest_nci` | `rn` | `medn` |
| nearest broad-menu county (name) | `nearest_broad_menu` | `rb` | `g60b` |
| average trials within 60 miles / nearby | `wmean_trials_within_60rdmi` | `short` | `l20` |
| trials in the county / with a site / listed, most trials | `trials_listed_here` | `t` | `l20` |
| facilities, trial sites | `facilities` | `t` | — (county, national) |
| <cancer type> trials | `trials_within_60rdmi_by_cancer_type[type]` | `short&type=` (caveat: county has no by-type field) | `l20&type=` |
| no vehicle / broadband / uninsured / uninsured 55–64 / poverty | `context.*` | `acs&acs=veh|bb|unins|unins55|pov` | `gacs&acs=` |
| rural, nonmetro, most rural | `rucc`, `metro` (county); `nonmetro_pct` (district, state) | `short&rural=1` | `l20&rural=1` |
| metro vs rural within a state / nationally | `metro.*`, `nonmetro.*` (state, national) | — | `l20&rural=1` |
| miles from the county center to NCI / broad / limited menu | `road_mi_*_from_center` | `rn` / `rb` | — |
| drive hours, longest drive | `drive_hours_nci`, `drive_hours_broad_menu` | `rn` / `rb` | — |
| trials / sites within 60 miles of the county center | `trials_within_60rdmi_of_center`, `facilities_within_60rdmi_of_center` | `short` / `t` | — |
| incidence, new cases, diagnoses (+ site: breast, lung, … stomach) | `incidence.all` / `incidence.by_site[site]`, `incidence_all_sites` | `inc&site=` | `ginc` |
| cases per year | `incidence.cases_per_year`, `incidence_all_sites_cases_per_year` | `inc` | `ginc` |
| deaths, mortality, death rate (+ site) | `mortality.all` / `mortality.by_site[site]` | `mva&site=` | — |
| deaths per year | `mortality.deaths_per_year` | `mva` | — |
| oncologists; oncologists within 60; oncologists per 100,000 | `oncologists.count`, `.within_60rdmi`, `.oncologists_per_100k_pop55` | `onc` | `l20` |
| oncologists but no trials | `oncologists.class == 2` (county filter); `oncologists.pct_pop55_in_counties_with_oncologists_no_trials` | `onc` | `l20` |
| residents 55 and older | `pop55` | `short` | `l20` |
| no road route (NCI / broad menu) | `median_road_mi_nci` / `median_road_mi_broad_menu` is null (`no_road_route_reason` only describes why) | `rn` / `rb` | — |
| cosponsor H.R. 3521 / S. 4440, who represents | `member.ctma_hr3521`, `senators[].s4440`, `counties` | — | `cos_ctma_hr` (district) / `l20` (state) |
| high incidence (deaths) and low access | `incidence_above_county_median` / `mortality_top_third` × `pct_lt20` or `pct_zero` ≥ thr | `bva` / `mva` + `tab=burden&crit=&thr=&site=` | — |

A field that is missing from a row is "not in the data" — never guessed. Counts and sums are computed in code and the rule is
stated in the table ("counties in Texas where every resident 55+ has no trial within 60 road-miles").

## Response

`POST /ask` with `{"q": "..."}` returns

```
{ q, route: "search"|"data"|"scope"|"other", answer, summary: {rule, counts: {label: value}} | null, table: [{column: value, ...}], rows: [{id, level, name, geoid, state}],
  sources: [{title, url}], view: {page: "map"|"find", qs, hl: [ids], unit, layer} | null, data_as_of, caveats: [..],
  plan: {route, shape, level, state, metric, site, acs, cancer_type, order, n, cosponsor, bill, rural, places, ...},
  deterministic: true|false, ambiguity?: {kind, options: [{name, id, state}]}, note }
```

`view.qs` uses only the map's own parameters (`u`, `m`, `site`, `acs`, `crit`, `thr`, `type`, `rural`, `lt`, `tab`, `c`, `d`, `s`;
`zip`, `type`, `q`, `age`, `mi` for the finder). `view.hl` ids match the unit (county FIPS, district geoid, state USPS).
`summary` carries the rule a ranking, count, threshold, need-vs-access or cosponsor answer used and its totals (places in scope,
matches, residents 55+ sums, seats filled / vacant, ties at the top); `table` holds place rows only, every row with the same
columns. `rows[i]` is the id of `table[i]`; `rows` and `view.hl` are one list in one order (rank order for rankings; highest
values first for thresholds and counts; highest rate for need-vs-access; largest share short for cosponsor lists), capped at
400 with a caveat; the counts in `summary` and the answer stay exact.
`caveats` carry: the assumed namesake, by-type answers at county level, small-numbers incidence / death rates, no-road-route medians, vacant seats,
the district plan (119th Congress), fields not published yet, the rule assumed when a question gave no cut-off.

## Exported interface (worker/src/index.js)

- `parseQuestion(q, ctx) -> plan | null` — ctx = `{counties, districts, states, national, index, places, zips}` (any subset).
- `planWithModel(q, env) -> plan` (Haiku), `checkPlan(q, plan, ctx) -> plan` — corrects the model's plan from the question text;
  a place name the resolver cannot find is reported, never guessed.
- `execute(plan, data) -> {route, shape, answer_facts, summary, table, rows, view, sources, data_as_of, caveats, ambiguity?}` — pure.
- `composeAnswer(plan, result) -> string`, `verifyAnswer(text, table, extraAllowed?) -> {ok, badNumbers}`.
- `answer(q, env, loader?) -> response object` — the pipeline (loader: `path -> Promise<json>`, defaults to the edge cache).
- `filesForText(q)`, `filesForPlan(plan)`, `expandCounties(compact, sites)` — which files are loaded when, and the compact table → rows.
Helpers live in `lexicon.js` (vocabulary, METRICS), `places.js` (indexes, resolution, fuzzy matching), `parse.js`, `execute.js`.

## Deploy

```
cd worker
npx wrangler login                       # or set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in the environment
npx wrangler deploy                      # prints the worker's address, e.g. https://trial-map-ask.<account>.workers.dev
npx wrangler secret put ANTHROPIC_API_KEY
```

Then set `ASK_URL` in `docs/site.js` to `https://trial-map-ask.<account>.workers.dev/ask`. While `ASK_URL` is empty the
question boxes stay hidden and the site works as before. `GET /health` on the worker returns `{ok:true}`. Without an API key
the worker still answers every question the parser understands (deterministic answers); only the model fallback and the
rewrite are off.

## Settings (`wrangler.toml`)

- `SITE_BASE`: where the data files are read from. Change it if the site moves to its own domain.
- `ALLOWED_ORIGINS`: the pages allowed to call the worker (the site plus localhost for testing). Add a new domain here.
- `MODEL_PLAN`, `MODEL_WRITE`: the two models. Most questions never reach the planner.
- `PER_MINUTE`: questions per visitor per minute (best effort, per worker instance). `DAILY_CAP`: questions per day in
  total across the site, after which the box answers with a "try tomorrow" message. Both protect the API bill.

Nothing about a visitor is stored. Each question is logged (question text, route, shape, whether the answer was deterministic,
view, first 300 characters of the answer; rejected model texts with the offending numbers) so wrong answers can be found and fixed.

## Testing

- `node tests/offline.js` — no network: loads the data files from `docs/`, runs every question in `tests/questions.json`
  through parseQuestion → execute → composeAnswer → verifyAnswer and checks routes, plans, views and one recomputed number per
  case, then property tests (rankings match a direct sort, hl ids exist, qs valid for the map, every county / state / district /
  ZIP resolves). `--only <substring> --verbose` for one case.
- `node tests/run.js https://trial-map-ask.<account>.workers.dev/ask` — live, after a deploy.
