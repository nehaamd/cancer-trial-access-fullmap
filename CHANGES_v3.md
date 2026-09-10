# What changed from the national version 2 to version 3, and why

Version 2 (5 September 2026) covered all 50 states + DC with straight-line ×1.2 distances between county population centers and land-area weights for districts. Version 3 (9 September 2026) keeps the parts that were already right — the registry pull and QC, site-to-county assignment, NCI center list, member data, the Connecticut fix — and replaces the two coarse methods with the ones the Texas version had already proved, then adds the features below.

## Method changes

| Weakness in v2 | Fix in v3 | Effect |
|---|---|---|
| Straight-line ×1.2 as distance | Shortest routes on the Census TIGER 2025 primary/secondary road network, all 51 states, 1.09 M nodes (same method as Texas v2, stored as sparse arrays to fit in 3 GB); validated on 38 city pairs, mean error 3.1% | Road / straight-line ratio to the nearest broad menu: median 1.20, 10th–90th pct 1.10–1.38; the ×1.2 rule was too low for 1,481 of 3,025 counties. National % beyond 60 miles of a broad menu 37.0 → 38.8 |
| District weights by land area | Tract population 55+ weights (84,396 tracts, 89,397 tract–district records) | Mean absolute change in "% beyond 60 mi of a broad menu" 3.5 points across 436 districts; median 0; 42 districts move >10 points. Largest: CA-25 7.3 → 100.0, CA-23 2.4 → 87.7, CA-41 0 → 53.9, WA-6 29.3 → 72.5, FL-8 21.6 → 62.4 — all districts holding the far half of a big metro county whose *centroid* is near the menu (Riverside and San Bernardino counties each host ~55 trials, so Coachella Valley residents are ~100 road-miles from Orange County's population center, not 0) |
| "% in a zero-trial county" as lead metric | "% with fewer than 20 (or 0) trials within 60 road-miles" | 20.9% → 12.7% (<20) and 4.4% (none): the county-boundary statistic overstated isolation, as the ZCTA analysis had suggested |
| Alaska / Hawaii scored with straight-line distances to the mainland | Labelled "no road connection"; counted in a separate no-road percentage | 35 counties, 0.7% of residents 55+; no longer produce 1,700-mile "distances" |
| Connecticut: one site row dropped via a planning-region code; no ACS household data | City-fallback layer uses 2021 county shapes; covariates rebuilt from tract tables on legacy counties; county pop 55+ now ACS 2023 tract sums (was 2021 PEP) | Every CT number is now on the same geography and vintage as every other state |
| Tract population not reconciled | Reconciled exactly to all 3,143 counties; Suffolk and Ulster NY raked (ACS 2023 publishes 371 of Suffolk's 385 2020 tracts) | 98,596,429 residents 55+ at tract, county, state and national level |

## New features

| Item | What it does | Where |
|---|---|---|
| 1.1 Trials vs facilities | Every trial count is paired with the number of distinct registry-listed facilities (names deduplicated after removing sponsor site codes): 3,919 trials at 9,491 facilities | county pane, tooltip, national pane |
| 1.2 Trial list per county | `trials.html?county=<fips>`: NCT ID (linked to ClinicalTrials.gov), title, phase, lead sponsor class, assigned cancer type, facilities in the county; eligibility criteria are linked, not embedded | linked from every county pane |
| 1.3 / 1.4 Phase and sponsor filters | Recount county trials, facilities and the 60-road-mile pool client-side; the filter bar states how many trials the counts reflect; district figures are labelled as unfiltered | filter bar |
| 1.5 ACS context layers | Households without a vehicle (B08201), with broadband (B28002), uninsured all ages and 55–64 (B27001), poverty (B17001) — four separate map layers and county-pane rows, never blended | "Household context" map layer |
| 2.3 Cancer-type filter | 20 named categories plus an always-visible multi-cancer / basket bucket (28.7% of trials; sub-reasons reported) and an unclassified bucket (1.1%); district panes show reachable trials by type | filter bar, district pane |
| 3.1 Cancer-incidence layer | Age-adjusted rate per 100,000 (2018–2022, NPCR + SEER) for 20 sites, with 95% CI and average annual cases; counties under 16 cases a year hatched "small numbers"; source-suppressed, Kansas (state law) and three counties absent from the source each carry their own label; trials-per-100-diagnoses shown only above the reliability threshold | "Cancer incidence rate" map layer, county pane |
| Road-based county pane | Road miles and indicative hours to the nearest NCI center, broad menu and limited menu, with the v2 straight-line figure alongside for comparison | county pane |
| v2 → v3 comparison | Each district pane shows its v2 and v3 figures | district pane |
| Tier 4 "where would an additional site help" (research prototype) | Maximal covering location problem on the road graph: 1,809 trial-capable facilities with no eligible recruiting trial in counties below the limited-menu threshold, ranked by residents 55+ who have no eligible trial within 60 road-miles today and would gain one; greedy 25-pick sequence with its coverage curve (22.4% of the 4.35 M uncovered after 25 picks). Runs on a registry-derived stand-in universe until the CoC + NCORP lists are pulled; methodology fixed and shown verbatim | `sites.html`, `tier4_*.csv` |
| Validation | 31 automated checks re-run by one script, including 25 live registry re-fetches, router validation, invariants, reconciliation, knife-edge audit and a payload null-vs-zero audit; written fresh-eyes review | `VALIDATION_v3.md` |

## Things the build found that the spec did not expect
- **Indiana is present** in State Cancer Profiles 2018–2022; **Kansas** is the state that does not release county data. The source also suppresses 9 counties with fewer than 16 cases in the period.
- ACS 2023 publishes fewer tracts for Suffolk County NY than the 2020 geography; 18,235 residents 55+ are in no tract row. Raked to the county total (factor 1.038, logged).
- The registry's explicit phase value "NA" is read as missing by pandas' defaults; 255 eligible trials are "not phased" (device, surgery, radiation), now labelled as such.
- Roughly a dozen supportive-care / non-oncology trials survive the inherited rule screen (surfaced by the classifier's unclassified bucket); left in for comparability and listed for review.

## Deferred, with reasons
- **Tier 4 with the intended candidate universe.** `www.facs.org` and `ncorp.cancer.gov` were added to the sandbox allowlist but the running container did not pick the change up, so the CoC + NCORP crawl (`fetch_candidates_coc_ncorp.py`) is written as a contract and plan, not run. The full computation is built and tested on the registry stand-in; substituting the intended list is one command.
- **Oral-agent classification** — explicitly out of scope; fields remain in `trials.csv`, unused.
- **Independent (blind) check of the cancer-type classifier** — the 200-trial sample with classifier output is left for a reader who did not build it.

## Independent review, round 2 (external session)

Four points raised, all verified against the code before responding:

| Point raised | Verified? | Action |
|---|---|---|
| Own-county trials get zero distance regardless of county size, overstating access in large counties | Confirmed in `route_us.py` | First response only quantified site counts (and mis-described a Boston-ZIP row the pipeline had in fact handled correctly). **Now fixed** by routing to facility locations — see round 3 below. |
| Cancer-type filters excluded relevant basket/multi-cancer trials (29% of trials are in that bucket) | Confirmed: 153 basket trials named colorectal specifically and were invisible to the Colorectal filter | **Fixed.** Every trial now carries its full set of matched categories; filters (map, county pane, trials.html) match on set membership, so a basket trial naming colorectal now appears under "Colorectal," with an "also names" note. |
| Filtered vs. unfiltered figures weren't visually distinct enough | Confirmed: the caveat was a small explanatory note, easy to miss next to a prominently filtered number | **Fixed.** Every unfiltered statistic (district and national panes) now carries an inline "ALL CANCER TYPES" tag directly on the number when a cancer-type filter is active, plus a callout showing the filtered figure for that district up front. |
| The 3.1% routing validation figure was presented more confidently than the underlying evidence supports | Confirmed: the 38 reference distances are approximate published values, not independently re-fetched using the router's own coordinates | **First response claimed the homepage/footer wording had been corrected; it had not** (caught in the critical re-review). Now corrected in `index.html`, and `validate_v3.py` checks the deployed HTML for the qualifying phrase. Not re-measured — no routing-service API is reachable from the build environment. |

## Round 3: critical re-review of round 2, facility-level routing, and redesign

| Change | Why |
|---|---|
| **Facility-level routing** (`route_sites_us.py`): pools count recruiting sites within the road-mile band of the resident's tract or county center; sites located at ZIP centroid (state-checked, 96%), city centroid (must agree with the assigned county), else county center | Closes review point R1 properly. 1.21 M residents 55+ were being scored 0 miles from trials that are >60 road-miles away; 30 districts move >5 points, in both directions. |
| Multi-label cancer type applied consistently: filters, county counts (with a named-only / basket split) and district breakdowns | The round-2 fix had left district breakdowns on primary labels, so a filtered county count and the district figure disagreed. |
| Router-accuracy wording actually corrected in the page; validator now greps the HTML for it | The round-2 report claimed this was done; it was not. |
| Validation report: the fresh-eyes and round-2 sections live in `VALIDATION_review.md`, which the generator appends | The round-2 section had been overwritten by regenerating the report. |
| Redesign: card-based pane, one "Color the map by" control, filter badge and Reset, **shareable URLs** (`?d=4816&type=colorectal`), "Copy link to this view", start-here actions, methods in a collapsible section; `trials.html` and `sites.html` on the same visual system; the county → trial-list link carries the active cancer-type filter | Usability for hand-off to congressional offices: a specific district view can be sent as a link. |

## Round 4: state statistics, context at every level, live filtering of aggregates

Feedback: state-level statistics were missing (only national and district), road-distance / household / incidence figures appeared only for counties, and the tumor-type and phase filters did not change the national, state or district figures.

| Change | Detail |
|---|---|
| **State panes** | Every state now shows the same statistics as districts and the nation: access figures, road distances (median to NCI center, broad and limited menu; shares beyond 60/120), breakdowns by cancer type / phase / sponsor, cancer incidence (state-published rate), household context, district list with least-access ranking. These had been computed in `state_metrics_v3.csv` all along but never displayed. |
| **Household context and incidence at national, state and district level** | Residents-55+-weighted means of county values (tract → county inheritance), with the share of residents covered shown when below 100% (Kansas incidence: "not available"). `tract_metrics_us.py` |
| **Filters now change the access figure for the nation, states and districts** | On first use with a filter on, the page loads `tracts60.bin` (84,396 tracts × recruiting sites within 60 road-miles, 2.64 M pairs, 6.3 MB) and recomputes the share of residents 55+ with fewer than 20 / none / fewer than 100 matching trials and the typical count, at census-tract level, in about 0.3 s. The all-trials figure is shown alongside. Distance-to-menu / NCI figures and the breakdown lists depend on all trials and stay tagged. `validate_v3.py` confirms the browser method reproduces the pipeline exactly with no filter. |
| Copy updated | Filter-bar note and methods text describe what is and is not recomputed. |

## Round 5: map by county, district or state; filters restored in full

| Change | Detail |
|---|---|
| **"Map by" control: counties / congressional districts / states** | District and state polygons are now colored by: share of residents 55+ with fewer than 20 (or no) trials within 60 road-miles, share beyond 60 road-miles of a broad menu or an NCI center, median road-miles to an NCI center, all-sites cancer incidence, or an ACS household variable. Hover shows the geography's figures; click selects it. State outlines are drawn in district mode. |
| **Filters recolor district and state maps** | With any phase / sponsor / cancer-type filter on, the two access metrics are recomputed for all 436 districts and 51 states in one pass over the tract file (~0.4 s) and the map repaints; the legend says "(filtered)". Distance metrics are structural and unchanged. |
| **Cancer-type filter includes the basket bucket again** | "Multiple cancer types / basket or umbrella" (1,124 trials) and "Other / unclassified" are selectable as buckets (matching on the primary label); a named cancer still includes basket trials that name it. Same rule in `trials.html`. |
| Filters always visible | The filter row is no longer collapsible; the toolbar shows the count of active filters and a Reset button. |
| Shareable URLs carry the map unit and metric | e.g. `?u=district&m=l20&type=colorectal`. |
| Data-currency note | NCI-designated centers are the inherited list of 68 treating centers (pipeline QC). Designations change — e.g. the Medical College of Wisconsin Cancer Center was seeking designation as of mid-2025 — so the list should be refreshed from cancer.gov before citing state-level NCI-distance figures. |

## Round 6: reviewer's feature list — trials and sites tables, exports, synchronized filters, refresh diff, brief

Registry re-pulled 2026-09-10 with extended fields (lead sponsor name, last registry update, central contact, collaborators) and the registry's own data timestamp recorded; the 2026-09-09 pull is kept as a snapshot. Headline numbers moved slightly with the day's registry changes (3,919 → 3,915 eligible trials).

| Requested | Status | Where / how |
|---|---|---|
| Persistent state/county cards: unique trials, distinct sites, annual cases, incidence, travel access | **Done** (cards for county, district, state, nation); annual cases and incidence rate shown as separate rows | pane cards |
| Visible "Trials" tab: search by NCT / title / intervention / institution; sortable; expandable sites | **Done**; also shows lead sponsor, interventions, min/max age, registry update date, central contact; sites expand with city, ZIP, county, site ID, distance (nearby mode) | Trials tab |
| "Sites" tab: one row per location, institution, city/ZIP, matching trials, "view trials" | **Done** with stable site IDs (S00000…), a reviewed-alias mechanism (`data/ref/site_aliases.csv`, empty starter) and candidate duplicates for review (`out_adult55/site_alias_candidates.csv`); anonymous placeholders flagged "unresolved" (340 of 9,494) rather than merged | Sites tab |
| Clickable counts; CSV download with NCT links and site info | **Done**: every trial/site count on the cards opens the exact list; CSV of the current trial or site selection (NCT, URL, phase, sponsor, cancers named, interventions, ages, dates, sites, site IDs, nearest distance, contact) | cards, Trials/Sites tabs |
| Shared filters across map, cards, tables, links, exports | **Done** (phase, sponsor, cancer type incl. basket bucket, patient age) — one filter state drives all views; share links carry it | filter bar |
| "In this county" / "Nearby" with a road-distance threshold, across state lines; nearby offered when local is zero | **Done**: 30 / 60 / 120 road-miles from the county population center to actual site locations (county→site distances precomputed); empty states offer the next radius; county card names the nearest site with a matching trial and its road distance | Trials/Sites tabs, county card |
| County comparison table within a state; select two to compare | **Done**: sortable by trials (filtered), sites, trials within 60, road-miles to NCI / broad menu, incidence (selected site), annual cases, poverty; two-county side-by-side; CSV | Compare counties tab |
| Printable district/county brief | **Done**: `brief.html?d=…` / `?c=…` / `?s=…` — statistics, locator map, definitions, sources, dates; print stylesheet | "Printable brief" links |
| Annual cases and incidence rate shown separately; state totals deduplicated by NCT; published state incidence rates | **Done** (state trial counts are distinct NCTs across the state's counties; state incidence uses the state-published rate) | state cards |
| Site identity: consistent IDs, reviewed alias list, campuses preserved, anonymous flagged | **Partly**: IDs, alias mechanism and candidate list exist; the human review of aliases has not been done, so no aliases are applied yet | `sites_registry.csv`, `site_alias_candidates.csv` |
| Extra trial fields: intervention, sponsor name, local site status, city/ZIP, contact, last update | **Done** except local site status: every surviving site row in this pull is "RECRUITING" (the query keeps recruiting-or-unreported sites; none were unreported), so the label "listed as recruiting" is shown and the distinction will appear automatically if unreported rows occur | Trials tab |
| Immediate updates on filter change; colorectal filter offers colorectal burden; phase/sponsor leave incidence unchanged | **Done**: choosing a cancer type auto-selects the matching incidence site (colorectal → Colon & Rectum, gynecologic → ovary, neuroendocrine → thyroid, gastric/esophageal → stomach); phase/sponsor/age do not touch incidence | filter bar, cards |
| Scheduled refresh with the registry's data timestamp displayed | **Partly**: `run_refresh.sh` chains the pipeline; `.github/workflows/refresh.yml` runs it weekly and publishes — written, **not executed from this environment**; the registry data timestamp (`/api/v2/version`) is recorded at pull time and shown in the header | header stamp, workflow |
| Cancer burden and Census keep their own reference periods | **Done**: every card and the brief say 2018–2022 and ACS 2023 explicitly | everywhere |
| Distance to the nearest site offering a matching trial | **Partly**: county-level (from the county population center) is live; tract-weighted district/state versions would need the per-tract site distances kept in the browser and are deferred | county card, Sites tab |
| Age selector using actual eligibility ages | **Done** with a stated limit: the dataset contains only trials open to at least one 55-year-old, so ages under 55 filter within that set and the population base stays 55+ | filter bar |
| "What changed since the previous refresh" | **Done** on real data: new / dropped trials, field changes, sites added or removed at continuing trials, county count changes; menu-threshold crossings counted | What changed tab, `diff_snapshots.py` |

Bug found during the refresh: the inherited `qc_us.py` only copied the fresh pull to `trials_raw.csv` if that file was absent, so a second run silently QC'd the *previous* pull. Fixed (copies whenever the pull is newer).
