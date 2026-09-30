# Release gate

**PASS** — 15/15 checks pass

| Check | Detail | Result |
|---|---|---|
| Classification audit: no unreviewed condition strings | 76 flagged strings, 0 new to review (qc_cancer_type_audit.md) | ✓ |
| Trial count plausible (2,000–8,000) | 3,915 eligible trials | ✓ |
| Population 55+ unchanged (ACS reference) | 98,596,429 | ✓ |
| pct_lt20_trials_within_60rdmi within bounds [5, 30] | 12.8 | ✓ |
| pct_zero_trials_within_60rdmi within bounds [1, 15] | 4.6 | ✓ |
| pct_gt60rdmi_broad_menu within bounds [20, 60] | 38.8 | ✓ |
| pct_gt60rdmi_nci within bounds [25, 65] | 44.2 | ✓ |
| median_road_mi_nci within bounds [25, 90] | 50.0 | ✓ |
| Drift vs previous snapshot | no previous snapshot yet (first run) — skipped | ✓ |
| data.js trial list matches meta.trials | 3,915 vs 3,915 | ✓ |
| 436 districts and 51 states in the payload | 436 districts, 51 states | ✓ |
| 3,143 counties in the payload | 3,143 | ✓ |
| No district with a missing headline figure | 0 missing | ✓ |
| Vacant seats are few (member list loaded) | 2 districts without a member | ✓ |
| Every state has residents 55+ and a finite access share | 51 rows | ✓ |
