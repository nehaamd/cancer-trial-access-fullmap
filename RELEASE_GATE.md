# Release gate

**PASS** — 28/28 checks pass

| Check | Detail | Result |
|---|---|---|
| Classification audit: no unreviewed condition strings | 64 flagged strings, 0 new to review (out_adult55/qc_cancer_type_audit.md) | ✓ |
| Registry pull complete (studies fetched vs the registry's own count) | 4,547 of 4,547 studies; 0 repeated across pages dropped | ✓ |
| Trial count plausible (2,000–8,000) | 4,013 eligible trials | ✓ |
| Population 55+ equals the ACS reference (data/ref/county_pop55.csv) | 100,019,672 vs 100,019,672 | ✓ |
| pct_lt20_trials_within_60rdmi within bounds [5, 30] | 12.0 | ✓ |
| pct_zero_trials_within_60rdmi within bounds [1, 15] | 4.3 | ✓ |
| pct_gt60rdmi_broad_menu within bounds [20, 60] | 38.0 | ✓ |
| pct_gt60rdmi_nci within bounds [25, 65] | 43.7 | ✓ |
| median_road_mi_nci within bounds [25, 90] | 48.0 | ✓ |
| The pull is newer than the previous snapshot (2026-10-11) | pulled 2026-10-11T18:42 (registry data 2026-10-09) after 2026-10-11T02:41 (registry data 2026-10-09) | ✓ |
| Drift vs the pull of 2026-10-11 | skipped once: the method changed (version 4 -> 6); the bounds above still apply | ✓ |
| County trial-site total moved less than 15% since the previous pull | 38,672 -> 38,705 | ✓ |
| Local route checks (12 short trips, 11 water crossings; road_local_checks.csv) | 23/23 within tolerance | ✓ |
| Residents 55+ with a site within 20 straight-line miles but none within 60 road-miles (ceiling 100,000; water barriers explain the rest) | 20,970 in 21 tracts; largest: Clinton, New York 10,361, Island, Washington 6,719, Essex, New York 2,692, Knox, Maine 1,064 | ✓ |
| Router vs published city-pair distances (mean difference below 5%, every pair routable) | 38 pairs, mean 3.1%, max 13.3%, unroutable 0 | ✓ |
| No site row drawn at a county center when its stated city lies elsewhere | 0 rows left unlocated and dropped; county-center placements: 9 | ✓ |
| No county whose only located sites sit at the county center (ZIP and city both unknown) | 9 such rows; counties with nothing else: 0 | ✓ |
| data.js trial list matches meta.trials | 4,013 vs 4,013 | ✓ |
| 436 districts and 51 states in the payload | 436 districts, 51 states | ✓ |
| 3,143 counties in the payload | 3,143 | ✓ |
| No district with a missing headline figure | 0 missing | ✓ |
| Vacant seats are few (member list loaded) | 2 districts without a member | ✓ |
| Every state has residents 55+ and a finite access share | 51 rows | ✓ |
| Every district's household and incidence figures come from tract tables (build_tract_context.py ran) | 436/436 districts marked ctx_src = tract | ✓ |
| Published district cancer-case counts equal the apportioned counts in district_metrics_v3.csv | 0 districts differ | ✓ |
| Every page's data file is from this pull (data.js, changes.js, findings.js, community.js, find_data.js) | pull 2026-10-11 18:42 UTC; all agree; changes.js compares with the pull of 2026-10-11 | ✓ |
| Compressed tract files (tracts60.bin.gz, tract_county.bin.gz) decompress to the plain files, whose lengths match data.js and rucc.js | both match | ✓ |
| Newer yearly sources (information only) | ACS 2024 5-year is the newest; incidence 2019-2023 is the newest | ✓ |
