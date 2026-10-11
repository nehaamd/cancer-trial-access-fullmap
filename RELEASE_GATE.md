# Release gate

**PASS** — 31/31 checks pass

| Check | Detail | Result |
|---|---|---|
| Classification audit: no unreviewed condition strings | 61 flagged strings, 0 new to review (out_adult55/qc_cancer_type_audit.md) | ✓ |
| Registry pull complete (studies fetched vs the registry's own count) | 4,543 of 4,543 studies; 0 repeated across pages dropped | ✓ |
| Trial count plausible (2,000–8,000) | 4,007 eligible trials | ✓ |
| Population 55+ equals the ACS reference (data/ref/county_pop55.csv) | 98,596,429 vs 98,596,429 | ✓ |
| pct_lt20_trials_within_60rdmi within bounds [5, 30] | 12.0 | ✓ |
| pct_zero_trials_within_60rdmi within bounds [1, 15] | 4.3 | ✓ |
| pct_gt60rdmi_broad_menu within bounds [20, 60] | 38.1 | ✓ |
| pct_gt60rdmi_nci within bounds [25, 65] | 43.7 | ✓ |
| median_road_mi_nci within bounds [25, 90] | 48.0 | ✓ |
| The pull is newer than the previous snapshot (2026-10-05) | pulled 2026-10-11T02:41 (registry data 2026-10-09) after 2026-10-05T15:09 (registry data 2026-10-05) | ✓ |
| pct_lt20_trials_within_60rdmi moved less than 1.5 since 2026-10-05 | 12.0 -> 12.0 | ✓ |
| pct_zero_trials_within_60rdmi moved less than 1.0 since 2026-10-05 | 4.2 -> 4.3 | ✓ |
| pct_gt60rdmi_broad_menu moved less than 2.0 since 2026-10-05 | 38.1 -> 38.1 | ✓ |
| pct_gt60rdmi_nci moved less than 1.0 since 2026-10-05 | 43.7 -> 43.7 | ✓ |
| median_road_mi_nci moved less than 5 since 2026-10-05 | 48.0 -> 48.0 | ✓ |
| Eligible trial count moved less than 10% since 2026-10-05 | 4,001 -> 4,007 | ✓ |
| County trial-site total moved less than 15% since the previous pull | 38,554 -> 38,672 | ✓ |
| Local route checks (12 short trips, 11 water crossings; road_local_checks.csv) | 23/23 within tolerance | ✓ |
| Residents 55+ with a site within 20 straight-line miles but none within 60 road-miles (ceiling 100,000; water barriers explain the rest) | 22,196 in 22 tracts; largest: Clinton, New York 9,873, Island, Washington 6,827, Essex, New York 2,654, Tulare, California 1,690 | ✓ |
| Router vs published city-pair distances (mean difference below 5%, every pair routable) | 38 pairs, mean 3.1%, max 13.3%, unroutable 0 | ✓ |
| No site row drawn at a county center when its stated city lies elsewhere | 0 rows left unlocated and dropped; county-center placements: 9 | ✓ |
| No county whose only located sites sit at the county center (ZIP and city both unknown) | 9 such rows; counties with nothing else: 0 | ✓ |
| data.js trial list matches meta.trials | 4,007 vs 4,007 | ✓ |
| 436 districts and 51 states in the payload | 436 districts, 51 states | ✓ |
| 3,143 counties in the payload | 3,143 | ✓ |
| No district with a missing headline figure | 0 missing | ✓ |
| Vacant seats are few (member list loaded) | 2 districts without a member | ✓ |
| Every state has residents 55+ and a finite access share | 51 rows | ✓ |
| Every district's household and incidence figures come from tract tables (build_tract_context.py ran) | 436/436 districts marked ctx_src = tract | ✓ |
| Published district cancer-case counts equal the apportioned counts in district_metrics_v3.csv | 0 districts differ | ✓ |
| Every page's data file is from this pull (data.js, changes.js, findings.js, community.js, find_data.js) | pull 2026-10-11 02:41 UTC; all agree; changes.js compares with the pull of 2026-10-05 | ✓ |
