# Release gate

**PASS** — 38/38 checks pass

| Check | Detail | Result |
|---|---|---|
| Classification audit: no unreviewed condition strings | 66 flagged strings, 0 new to review (out_adult55/qc_cancer_type_audit.md) | ✓ |
| Registry pull complete (studies fetched vs the registry's own count) | 4,577 of 4,577 studies; 0 repeated across pages dropped | ✓ |
| Trial count plausible (2,000–8,000) | 4,033 eligible trials | ✓ |
| Population 55+ equals the ACS reference (data/ref/county_pop55.csv) | 100,019,672 vs 100,019,672 | ✓ |
| pct_lt20_trials_within_60rdmi within bounds [5, 30] | 11.8 | ✓ |
| pct_zero_trials_within_60rdmi within bounds [1, 15] | 4.3 | ✓ |
| pct_gt60rdmi_broad_menu within bounds [20, 60] | 38.0 | ✓ |
| pct_gt60rdmi_nci within bounds [25, 65] | 43.7 | ✓ |
| median_road_mi_nci within bounds [25, 90] | 48.0 | ✓ |
| The pull is newer than the previous snapshot (2026-11-17) | pulled 2026-11-18T01:22 (registry data 2026-11-17) after 2026-11-17T04:19 (registry data 2026-11-16) | ✓ |
| Drift vs the pull of 2026-11-17 | skipped once: the method changed (version 6 -> 8); the bounds above still apply | ✓ |
| County trial-site total moved less than 15% since the previous pull | 39,436 -> 39,445 | ✓ |
| Local route checks (12 short trips, 11 water crossings; road_local_checks.csv) | 23/23 within tolerance | ✓ |
| Residents 55+ with a site within 20 straight-line miles but none within 60 road-miles (ceiling 100,000; water barriers explain the rest) | 20,970 in 21 tracts; largest: Clinton, New York 10,361, Island, Washington 6,719, Essex, New York 2,692, Knox, Maine 1,064 | ✓ |
| Next-nearest NCI centers agree with the nearest (all-pairs ranking vs single-source routing) | first-ranked center differs for 0 counties; max miles difference 0.05; 3108 counties have a second center by road, 3108 a third | ✓ |
| Router vs published city-pair distances (mean difference below 5%, every pair routable) | 38 pairs, mean 3.1%, max 13.3%, unroutable 0 | ✓ |
| No site row drawn at a county center when its stated city lies elsewhere | 0 rows left unlocated and dropped; county-center placements: 10 | ✓ |
| No county whose only located sites sit at the county center (ZIP and city both unknown) | 10 such rows; counties with nothing else: 0 | ✓ |
| data.js trial list matches meta.trials | 4,033 vs 4,033 | ✓ |
| 436 districts and 51 states in the payload | 436 districts, 51 states | ✓ |
| 3,143 counties in the payload | 3,143 | ✓ |
| No district with a missing headline figure | 0 missing | ✓ |
| Vacant seats are few (member list loaded) | 2 districts without a member | ✓ |
| Every state has residents 55+ and a finite access share | 51 rows | ✓ |
| Every district's household and incidence figures come from tract tables (build_tract_context.py ran) | 436/436 districts marked ctx_src = tract | ✓ |
| Published district cancer-case counts equal the apportioned counts in district_metrics_v3.csv | 0 districts differ | ✓ |
| Every page's data file is from this pull (data.js, changes.js, findings.js, community.js, find_data.js) | pull 2026-11-18 01:22 UTC; all agree; changes.js compares with the pull of 2026-11-17 | ✓ |
| Compressed tract files (tracts60.bin.gz, tract_county.bin.gz) decompress to the plain files, whose lengths match data.js and rucc.js | both match | ✓ |
| Question-box eval expectations rebuilt from the refreshed files (eval_expected.py) | wrote eval_expected.json: 110 questions, data as of 2026-11-17 | ✓ |
| Question-box engine expectations rebuilt from the refreshed files (expected.py) | wrote /home/runner/work/cancer-trial-access-fullmap/cancer-trial-access-fullmap/worker/tests/expected.json: 166 expectations in 19 groups | ✓ |
| Question-box engine suite (worker/tests/engine.test.js) | 432 passed, 0 failed  (load 366 ms) | ✓ |
| Question-box loop suite (worker/tests/loop.test.js) | 37 passed, 0 failed | ✓ |
| Question-box claims (per-place attribution) suite (worker/tests/claims.test.js) | false-rejection check: 41/41 realistic correct answers verified; 16/16 wrong attributions rejected | ✓ |
| Question-box standard methods suite (worker/tests/methods.test.js) | 37 passed, 0 failed | ✓ |
| Question-box client suite (worker/tests/client.test.js) | 34 passed, 0 failed | ✓ |
| Question-box eval checks suite (worker/tests/eval_checks.test.js) | 108/108 eval_checks tests pass | ✓ |
| Key findings: the figures written into the page are this refresh's (prerender_findings.js --check) | prerender_findings: 15 figures in docs/index.html match docs/findings.js | ✓ |
| Newer yearly sources (information only) | ACS 2024 5-year is the newest; incidence 2019-2023 is the newest | ✓ |
