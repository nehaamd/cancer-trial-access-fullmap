# Release gate

**PASS** — 20/20 checks pass

| Check | Detail | Result |
|---|---|---|
| Classification audit: no unreviewed condition strings | 75 flagged strings, 0 new to review (out_adult55/qc_cancer_type_audit.md) | ✓ |
| Trial count plausible (2,000–8,000) | 3,917 eligible trials | ✓ |
| Population 55+ unchanged (ACS reference) | 98,596,429 | ✓ |
| pct_lt20_trials_within_60rdmi within bounds [5, 30] | 12.7 | ✓ |
| pct_zero_trials_within_60rdmi within bounds [1, 15] | 4.4 | ✓ |
| pct_gt60rdmi_broad_menu within bounds [20, 60] | 38.8 | ✓ |
| pct_gt60rdmi_nci within bounds [25, 65] | 44.2 | ✓ |
| median_road_mi_nci within bounds [25, 90] | 50.0 | ✓ |
| pct_lt20_trials_within_60rdmi moved less than 1.5 since 2026-09-09 | 12.8 -> 12.7 | ✓ |
| pct_zero_trials_within_60rdmi moved less than 1.0 since 2026-09-09 | 4.6 -> 4.4 | ✓ |
| pct_gt60rdmi_broad_menu moved less than 2.0 since 2026-09-09 | 38.8 -> 38.8 | ✓ |
| pct_gt60rdmi_nci moved less than 1.0 since 2026-09-09 | 44.2 -> 44.2 | ✓ |
| median_road_mi_nci moved less than 5 since 2026-09-09 | 50.0 -> 50.0 | ✓ |
| County trial-site total moved less than 15% since the previous pull | 38,059 -> 38,440 | ✓ |
| data.js trial list matches meta.trials | 3,917 vs 3,917 | ✓ |
| 436 districts and 51 states in the payload | 436 districts, 51 states | ✓ |
| 3,143 counties in the payload | 3,143 | ✓ |
| No district with a missing headline figure | 0 missing | ✓ |
| Vacant seats are few (member list loaded) | 2 districts without a member | ✓ |
| Every state has residents 55+ and a finite access share | 51 rows | ✓ |
