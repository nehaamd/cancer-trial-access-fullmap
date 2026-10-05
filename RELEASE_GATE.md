# Release gate

**PASS** — 23/23 checks pass

| Check | Detail | Result |
|---|---|---|
| Classification audit: no unreviewed condition strings | 75 flagged strings, 0 new to review (out_adult55/qc_cancer_type_audit.md) | ✓ |
| Trial count plausible (2,000–8,000) | 3,910 eligible trials | ✓ |
| Population 55+ unchanged (ACS reference) | 98,596,429 | ✓ |
| pct_lt20_trials_within_60rdmi within bounds [5, 30] | 11.9 | ✓ |
| pct_zero_trials_within_60rdmi within bounds [1, 15] | 3.8 | ✓ |
| pct_gt60rdmi_broad_menu within bounds [20, 60] | 38.1 | ✓ |
| pct_gt60rdmi_nci within bounds [25, 65] | 43.7 | ✓ |
| median_road_mi_nci within bounds [25, 90] | 48.0 | ✓ |
| pct_lt20_trials_within_60rdmi moved less than 1.5 since 2026-10-01 | 11.8 -> 11.9 | ✓ |
| pct_zero_trials_within_60rdmi moved less than 1.0 since 2026-10-01 | 3.8 -> 3.8 | ✓ |
| pct_gt60rdmi_broad_menu moved less than 2.0 since 2026-10-01 | 38.1 -> 38.1 | ✓ |
| pct_gt60rdmi_nci moved less than 1.0 since 2026-10-01 | 43.7 -> 43.7 | ✓ |
| median_road_mi_nci moved less than 5 since 2026-10-01 | 48.0 -> 48.0 | ✓ |
| County trial-site total moved less than 15% since the previous pull | 38,458 -> 38,193 | ✓ |
| Local route checks (12 short trips, 11 water crossings; road_local_checks.csv) | 23/23 within tolerance | ✓ |
| Residents 55+ with a site within 20 straight-line miles but none within 60 road-miles (ceiling 100,000; water barriers explain the rest) | 22,196 in 22 tracts; largest: Clinton, New York 9,873, Island, Washington 6,827, Essex, New York 2,654, Tulare, California 1,690 | ✓ |
| Router vs published city-pair distances (mean difference below 5%, every pair routable) | 38 pairs, mean 3.1%, max 13.3%, unroutable 0 | ✓ |
| data.js trial list matches meta.trials | 3,910 vs 3,910 | ✓ |
| 436 districts and 51 states in the payload | 436 districts, 51 states | ✓ |
| 3,143 counties in the payload | 3,143 | ✓ |
| No district with a missing headline figure | 0 missing | ✓ |
| Vacant seats are few (member list loaded) | 2 districts without a member | ✓ |
| Every state has residents 55+ and a finite access share | 51 rows | ✓ |
