# Validation — v3.3 additions (rural/urban, cosponsors, burden vs access, ZIP lookup)

Checks re-run by `validate_extras.py` on 2026-10-06.

| Check | Result | Pass | Context |
|---|---|---|---|
| RUCC: every county carries a code; 2013 fallback limited to Connecticut | 3143 coded, 0 missing; 2013 fallback: 8 (09001, 09003, 09005, 09007, 09009, 09011, 09013, 09015) | ✓ |  |
| RUCC: metro + nonmetro residents 55+ equal the national total; their weighted <20 / none shares reproduce the national figures | 98,596,429 vs 98,596,429; weighted <20 12.01% vs 12.0%; none 4.20% vs 4.2% | ✓ |  |
| RUCC: nonmetro '<20 within 60 road-mi' share recomputed independently from tract_access.csv | 43.1% vs rucc.js 43.1%; metro 6.1% (nonmetro / metro ratio 7.1×) | ✓ |  |
| RUCC: state metro + nonmetro populations equal state totals | 0 mismatches | ✓ |  |
| tract_county.bin: every tract maps back to its own county through meta.county_order | 84,396 of 84,396 tracts; 3143 counties in order list | ✓ |  |
| Cosponsors: every sponsor / cosponsor bioguide ID resolves to a current member of Congress | 27 members on 2 bills; unresolved: none | ✓ |  |
| Cosponsors: the tracked bills are the Clinical Trial Modernization Act only (Ruiz H.R. 3521, Scott S. 4440) | H.R. 3521 Raul Ruiz (24 cosponsors); S. 4440 Tim Scott (1 cosponsors) | ✓ |  |
| Cosponsors: TX-11 (Pfluger) is an original cosponsor of H.R. 3521, not its sponsor (corrects the v3.2 label) | role = original (2025-05-20) | ✓ |  |
| Cosponsors: district → member map covers every non-vacant House seat (+ DC delegate) | 434 mapped; 2 vacant in the payload; 436 district rows | ✓ |  |
| Cosponsors: 100 senators mapped to states | 100 senators across 50 states | ✓ |  |
| Cosponsors: House bills carry only representatives, Senate bills only senators | chambers consistent | ✓ |  |
| Cosponsors: freshness of the pull | fetched 2026-10-05 (2 days ago) from govinfo BILLSTATUS XML… | ✓ | re-run fetch_cosponsors.py before a Hill Day; the deployed page states the fetch date |
| Burden: county '<20 within 60 road-mi' shares recomputed from tract_access.csv; their population-weighted mean equals the national share | max |diff| 0.05 pts (rounding); weighted mean 12.01% vs national 12.0% | ✓ |  |
| Burden: national median and the high-burden/low-access cell recomputed independently | median 466.5 vs 466.5; cell 497 counties / 4,341,298 residents 55+ vs burden.js 497 / 4,341,298; 3026 classified | ✓ |  |
| Burden: the four cells partition the classified counties | 497 + 984 + 769 + 776 = 3026 vs 3026 | ✓ |  |
| Burden: plausibility read of the largest high-burden/low-access counties by annual diagnoses | Leon (12); Lafayette (22); Butte (06); Harrison (28); Bay (12) | ✓ | same-session read; mid-sized metros without a trial hub within 60 road-miles — not independently reviewed |
| Burden: cancer-type-specific 'none within 60 road-mi' shares present for every named type | 20 types × 3143 counties | ✓ |  |
| ZIP lookup: site points match the payload one-to-one; ZCTAs cover the 50 states + DC | 2450 site points vs 2450 in DATA.SP; 33,640 ZCTAs, 51 states | ✓ |  |
| ZIP lookup: every ZCTA's county exists in the payload | 0 bad | ✓ |  |
| ZIP lookup: spot check — nearest site point to ZIP 77030 (Texas Medical Center) is in Harris County within ~2 miles | 0.0 mi; facilities there include ['Site 0103', '014', '069'] | ✓ |  |
| ZIP lookup: spot check — El Paso ZIP 79901 finds site points within 60 estimated road-miles and no Houston sites | 7 site points within 60 est. road-mi | ✓ |  |
| ZIP lookup page states its limits (information only; eligibility decided by the study team; ZIP stays in the browser; NCI 1-800-4-CANCER present) | all phrases present | ✓ |  |
| Map page loads the three new data files and states the burden view is a cross-tabulation, not a score | rucc.js, cosponsors.js, burden.js referenced; 'never a combined score' present | ✓ |  |
