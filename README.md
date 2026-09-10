# US Cancer Trial Access by County and Congressional District — version 3

**What this is.** For every US county (3,143), congressional district (435 + DC) and state: how many recruiting cancer treatment trials are within reach of residents aged 55+, how far they must drive to a broad menu of trials or to an NCI-designated cancer center, which trials those are, how many people are diagnosed with cancer there, and what household barriers (vehicle, broadband, insurance, poverty) sit alongside the distance. Version 3 brings the national map up to the rigour of the Texas road-network version: shortest highway routes instead of straight-line ×1.2, census-tract population weights instead of land-area weights, and adds trial lists, filters, a cancer-incidence layer and household context. Registry pulled 9 September 2026.

Web app: `docs/` (static, deployable to GitHub Pages as-is; `index.html` map, `trials.html` per-county trial lists, `sites.html` the Tier 4 research prototype, plus `data.js`, `geo.js`, `tier4.js`; d3 loads from cdnjs with a local fallback).

## Headline results (residents 55+, trials open to a 55-year-old, road miles from each census tract's population center)
- **12.8% of Americans 55+ have fewer than 20 recruiting cancer treatment trials within 60 road-miles of home; 4.6% have none.** (20.9% live in a county with no trial — a county-boundary statistic that overstates isolation and is no longer the lead number.)
- **38.8% live more than 60 road-miles from a broad menu** (a county with ≥100 trials); 19.0% more than 120; 0.7% (Alaska, Hawaii) have no road connection to one at all. Version 2 (straight-line ×1.2, area weights) gave 37.0%.
- **44.2% live more than 60 road-miles from an NCI-designated cancer center**; the median resident 55+ is 50 road-miles from one; 20.6% are more than 120.
- 3,919 eligible trials at ~9,500 registry-listed facilities; 83 counties host a broad menu, 380 a limited menu; **15 states have no broad-menu county**; 72 districts have 100% of residents 55+ beyond 60 road-miles of one (79 in version 2).
- Road distance / straight-line distance to the nearest broad menu: median 1.20 (10th–90th percentile 1.10–1.38) — the old ×1.2 convention was right on average and too low for 1,481 of 3,025 counties.

## Files
| File | What |
|---|---|
| `docs/index.html`, `docs/trials.html`, `docs/sites.html` | The web app (map + panes; per-county trial list linked from the county pane, `trials.html?county=<fips>`; "where would an additional site help" research prototype) |
| `out_adult55/tier4_candidates_ranked.csv`, `tier4_greedy_sequence.csv`, `tier4_log.json` | Tier 4: every evaluated candidate facility ranked by residents 55+ newly covered; the greedy 25-pick sequence; the methodology text and counts |
| `docs/data.js`, `docs/geo.js` | Data payload (4.4 MB) and simplified geometry (2.3 MB) |
| `out_adult55/district_metrics_v3.csv` | 436 districts: tract-weighted, road-based metrics, breakdowns by cancer type / phase / sponsor |
| `out_adult55/state_metrics_v3.csv`, `national_metrics_v3.json` | Same for states and the US |
| `out_adult55/county_road_distances.csv` | Per county: road miles and hours to nearest broad menu, limited menu, NCI center; straight-line comparison; no-road flags |
| `out_adult55/tract_access.csv` | 84,396 tracts: trials within 30/60/120 road-miles (and by cancer type/phase/sponsor at 60), road miles to menus and NCI centers |
| `out_adult55/county_pairs_within_120rdmi.csv` | Which trial-hosting counties are within 120 road-miles of each county (feeds the web app's filtered pools) |
| `out_adult55/county_metrics.csv`, `site_assignment_qc.csv` | County counts and site→county assignment audit (unchanged method) |
| `data/raw/trial_cancer_type.csv`, `out_adult55/cancer_type_summary.json` | Cancer-type classification per trial, with the multi-cancer bucket share |
| `data/ref/cancer_incidence_county.csv`, `cancer_incidence_state.csv` | State Cancer Profiles incidence, 20 sites, with an explicit status per row |
| `data/ref/county_covariates.csv` | ACS household context (Connecticut rebuilt on legacy counties) |
| `VALIDATION_v3.md`, `out_adult55/road_validation.csv`, `qc_spotcheck_25_trials_v3.csv`, `qc_cancer_type_sample_200.csv`, `qc_cancer_type_selfcheck_50.csv`, `qc_cancer_type_unclassified.csv` | Validation |
| `CHANGES_v3.md` | What changed from version 2 and why |

## Method in plain language
1. **Trials.** Ask ClinicalTrials.gov for every interventional study that is recruiting, has treatment as its purpose, matches an oncology condition, and lists a US site. Drop the non-cancer studies the broad search lets in (rule-based screen with a keep-list) and the trials that cannot enroll anyone 55 or older. Result: 3,919 trials.
2. **Where the trials are.** Put each recruiting site in a county by ZIP code (3-digit ZIP, then city name as fallbacks; Connecticut on its eight legacy counties). A trial "is in" a county if it has a recruiting site there; a facility is a distinct registry facility name in a county after removing sponsor site codes. ≥100 trials = *broad menu*, ≥20 = *limited menu* (ASCO's 2024 thresholds).
3. **What the trials are.** Each trial is assigned one *primary* cancer category from its registry condition text, or the explicit "multiple cancer types / basket" bucket when it names several cancers or only generic terms (28.7% of trials). Filtering by a named cancer type also returns basket/multi-cancer trials that name that cancer among others (151 trials reach the Colorectal filter this way, for example) — the filter checks every category a trial's conditions name, not just its primary label. Phase and lead-sponsor class come from the registry's structured fields.
4. **Where the people are.** Population 55+ for each of 84,396 census tracts (ACS 2023 5-year) and each tract's population center; tract sums reconcile exactly to every county.
5. **Roads.** Build a highway network from the Census Bureau's primary and secondary roads for all 50 states + DC (1.09 million nodes), split at every crossing, and compute shortest routes. Validated against 38 published city-pair driving distances (mean error 3.1%).
6. **Access.** Each recruiting site is located at its ZIP centroid (state-checked; city centroid or county center as fallbacks). For each tract and county: distinct trials with a recruiting site within 30/60/120 road-miles of the population center; road miles (and indicative hours) to the nearest broad menu, limited menu and NCI-designated treating center (68 centers). Alaska and the Hawaiian islands have no road connection to a broad menu and are labelled, not scored.
7. **Districts.** Average tract values within each 119th-Congress district, weighting by population 55+ (tracts split by a boundary apportioned by land area).
8. **Cancer burden.** Age-adjusted incidence, 95% CI and average annual cases by county and cancer site from NCI/CDC State Cancer Profiles (NPCR + SEER, 2018–2022), with every county labelled published / small numbers (<16 cases a year) / suppressed by the source / not available (Kansas, by state law).
9. **Household context.** Households without a vehicle, with broadband, uninsured, and poverty rate from ACS 2023 5-year tables, shown as four separate layers — never combined into an index.
10. **Where would an additional site help (research prototype).** Take existing trial-capable facilities that host no eligible recruiting trial today and whose county has fewer than 20; for each, count the residents 55+ who have no eligible trial within 60 road-miles today but would if a trial opened there; rank them, and pick greedily (each pick removes the people it covers). The intended candidate universe is Commission on Cancer-accredited programs plus NCORP affiliates; until those lists are pulled, the prototype runs on a stand-in (every US facility that hosted an oncology treatment trial started 2016 or later) and is labelled as such.

## Replicate it (about 30 minutes on a 1-CPU, 3 GB machine; Linux/macOS with Python 3.10+)
```
pip install -r requirements.txt
python fetch_us.py                              # 1. ClinicalTrials.gov pull -> data/raw/  (check api_total_count in data/raw/fetch_log.json)
python build_geo_us.py                          # 2. Census reference files -> data/ref/ (ZCTA-county, centroids, county-CD, gazetteer, county pop 55+)
#    also download three boundary files into data/geo/: cb_2023_us_county_500k.zip -> cb.zip, cb_2021_us_county_500k.zip -> cb500_2021.zip,
#    cb_2024_us_cd119_500k.zip -> cd119.zip (from www2.census.gov/geo/tiger/GENZ20xx/shp/), and legislators-current.json
#    (raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages/) into data/ref/
python qc_us.py                                 # 3. non-oncology screen, age caps, NCI centers
python build_tracts_us.py                       # 4. tract centroids + pop 55+, tract->CD119 shares, Connecticut re-key, reconciliation (rewrites county_pop55.csv)
python metrics_us.py --min-max-age 55 --out out_adult55   # 5. county counts, site assignment, straight-line baseline (needed as input)
python classify_cancer_type.py                  # 6. cancer-type classification + 200-trial hand-check sample
python build_roads_us.py                        # 7. download TIGER roads (51 files, ~300 MB), node them, build the graph (~2 min)
python route_us.py                              # 8. routing: menus, NCI centers, city-pair validation (~1 min)
python route_sites_us.py                        # 8b. facility-level routing: every recruiting site located by ZIP, tracts/counties to sites within 120 road-mi (~1 min)
python tract_metrics_us.py                      # 9. tract access + district / state / national metrics (uses 8b when present)
python fetch_cancer_burden.py                   # 10. State Cancer Profiles, 20 sites, with reconciliation to state totals
python build_covariates.py && python fix_ct_covariates.py   # 11. ACS household context (the fix rebuilds Connecticut on legacy counties)
python build_webapp_data_v3.py                  # 12. docs/data.js + docs/geo.js
python fetch_candidates_registry.py             # 13. Tier 4 stand-in candidate universe from the registry (any-status oncology trials, 2016+)
python tier4_covering.py                        # 14. Tier 4 ranking + greedy sequence -> out_adult55/tier4_*.csv, docs/tier4.js  (~1 min)
#    when www.facs.org and ncorp.cancer.gov are reachable: python fetch_candidates_coc_ncorp.py (see its docstring; not yet run), then
#    python tier4_covering.py --candidates data/ref/candidates_coc_ncorp.csv --label "CoC-accredited programs + NCORP affiliates"
python validate_v3.py                           # 15. re-runs every check (incl. 25 live registry re-fetches) -> VALIDATION_v3.md
```
Then open `docs/index.html` (or push `docs/` to GitHub Pages).

To verify by hand: pick any row of `out_adult55/county_road_distances.csv` and check the road miles against a mapping site (expect within ~10%); open a few NCT IDs from `data/raw/trials.csv` on ClinicalTrials.gov and confirm status, purpose and a US site; compare `tract_access.csv` pop55 sums to `data/ref/county_pop55.csv`; pick rows from `out_adult55/qc_cancer_type_sample_200.csv` and judge the assigned cancer type from the title and conditions.

## Weaknesses that remain
- **Site locations are ZIP-code centroids**, not street addresses (96% of site rows); a few registry rows carry a ZIP that disagrees with the stated city and follow the ZIP. Menu distances (nearest county with 20+/100+ trials) remain county-level by definition.
- **Router validation uses approximate published reference distances, not an independently-fetched routing benchmark.** The 3.1% mean difference is a real computation but the 38 comparison distances are approximate reference values, not re-fetched from a routing service using the router's own coordinates (no routing API is reachable from the build environment). The page says so; treat the figure as directional, not certified.
- **Trials, not eligibility.** Counts pool all cancer types unless filtered; the cancer-type filter is regex-based and 28.7% of trials sit in the multi-cancer bucket by design. Filters apply to county counts and lists; district figures are unfiltered (with one-dimension breakdowns).
- **Highway-only network.** Local roads are not in the graph; the last mile is a straight-line access edge (median 0.8 mi for tracts) and drive-times use fixed per-class speeds, so hours are indicative. Grade-separated crossings without interchanges may create false connections (small effect on long routes).
- **County population centers stand in for trial sites** when pooling trials within a distance band (as in ASCO's method and the Texas build).
- **Registry limits.** "Recruiting" lags real enrollment; facility names are free text; ~12 supportive-care / non-oncology trials survive the rule screen (listed for review).
- **Districts are the 119th Congress (2021 maps).** Several states have redrawn for 2026; the Census has not published 120th-Congress relationship files.
- **Cancer burden** is a different period (2018–2022) and geography vintage than the registry; Kansas is absent by state law; small counties are flagged, not hidden.
- **Snapshot.** One day's registry and one day's member list; re-pull before distributing.
- **Tier 4 is a research prototype.** It runs on a registry-derived stand-in candidate universe, so it can only name places already in ClinicalTrials.gov; 185 of 1,809 candidates carry sponsor placeholder names (flagged †). The intended CoC + NCORP universe needs `fetch_candidates_coc_ncorp.py` to be run once those domains resolve; `validate_v3.py` keeps one check failing until then.
- **Not in this version** (explicitly out of scope): oral-agent classification (fields present in `trials.csv`, unused), real-time enrollment, eligibility matching, trend-over-time.
