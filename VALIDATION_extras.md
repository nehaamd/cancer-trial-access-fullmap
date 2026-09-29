# Validation — v3.3 additions (rural/urban, cosponsors, burden vs access, ZIP lookup)

Checks re-run by `validate_extras.py` on 2026-09-29.

| Check | Result | Pass | Context |
|---|---|---|---|
| RUCC: every county carries a code; 2013 fallback limited to Connecticut | 3143 coded, 0 missing; 2013 fallback: 8 (09001, 09003, 09005, 09007, 09009, 09011, 09013, 09015) | ✓ |  |
| RUCC: metro + nonmetro residents 55+ equal the national total; their weighted <20 / none shares reproduce the national figures | 98,596,429 vs 98,596,429; weighted <20 12.76% vs 12.8%; none 4.59% vs 4.6% | ✓ |  |
| RUCC: nonmetro '<20 within 60 road-mi' share recomputed independently from tract_access.csv | 45.2% vs rucc.js 45.2%; metro 6.6% (nonmetro / metro ratio 6.8×) | ✓ |  |
| RUCC: state metro + nonmetro populations equal state totals | 0 mismatches | ✓ |  |
| tract_county.bin: every tract maps back to its own county through meta.county_order | 84,396 of 84,396 tracts; 3143 counties in order list | ✓ |  |
| Cosponsors: every sponsor / cosponsor bioguide ID resolves to a current member of Congress | 88 members on 4 bills; unresolved: none | ✓ |  |
| Cosponsors: bill numbers and sponsors as expected (Murphy H.R. 1492, Tillis S. 832, Ruiz H.R. 3521, Scott S. 4440) | H.R. 1492 Gregory F. Murphy (68 cosponsors); S. 832 Thom Tillis (7 cosponsors); H.R. 3521 Raul Ruiz (12 cosponsors); S. 4440 Tim Scott (1 cosponsors) | ✓ |  |
| Cosponsors: TX-11 (Pfluger) is an original cosponsor of H.R. 3521, not its sponsor (corrects the v3.2 label) | role = original (2025-05-20) | ✓ |  |
| Cosponsors: district → member map covers every non-vacant House seat (+ DC delegate) | 434 mapped; 2 vacant in the payload; 436 district rows | ✓ |  |
| Cosponsors: 100 senators mapped to states | 100 senators across 50 states | ✓ |  |
| Cosponsors: House bills carry only representatives, Senate bills only senators | chambers consistent | ✓ |  |
| Cosponsors: freshness of the pull | fetched 2026-09-29 (1 days ago) from govinfo.gov bulk data BILLSTATUS XML (ht… | ✓ | re-run fetch_cosponsors.py before a Hill Day; the deployed page states the fetch date |
| Burden: county '<20 within 60 road-mi' shares recomputed from tract_access.csv; their population-weighted mean equals the national share | max |diff| 0.05 pts (rounding); weighted mean 12.76% vs national 12.8% | ✓ |  |
| Burden: national median and the high-burden/low-access cell recomputed independently | median 466.5 vs 466.5; cell 514 counties / 4,383,276 residents 55+ vs burden.js 514 / 4,383,276; 3026 classified | ✓ |  |
| Burden: the four cells partition the classified counties | 514 + 967 + 798 + 747 = 3026 vs 3026 | ✓ |  |
| Burden: plausibility read of the largest high-burden/low-access counties by annual diagnoses | Leon (12); Lafayette (22); Butte (06); Harrison (28); Bay (12) | ✓ | same-session read; mid-sized metros without a trial hub within 60 road-miles — not independently reviewed |
| Burden: cancer-type-specific 'none within 60 road-mi' shares present for every named type | 20 types × 3143 counties | ✓ |  |
| ZIP lookup: site points match the payload one-to-one; ZCTAs cover the 50 states + DC | 2464 site points vs 2464 in DATA.SP; 33,640 ZCTAs, 51 states | ✓ |  |
| ZIP lookup: every ZCTA's county exists in the payload | 0 bad | ✓ |  |
| ZIP lookup: spot check — nearest site point to ZIP 77030 (Texas Medical Center) is in Harris County within ~2 miles | 0.0 mi; facilities there include ['Investigative Site #129', '014', '069'] | ✓ |  |
| ZIP lookup: spot check — El Paso ZIP 79901 finds site points within 60 estimated road-miles and no Houston sites | 7 site points within 60 est. road-mi | ✓ |  |
| ZIP lookup page states its limits (information only; eligibility decided by the study team; ZIP stays in the browser; NCI 1-800-4-CANCER present) | all phrases present | ✓ |  |
| Map page loads the three new data files and states the burden view is a cross-tabulation, not a score | rucc.js, cosponsors.js, burden.js referenced; 'never a combined score' present | ✓ |  |
| Browser: in-page tract recomputation (no filter) reproduces burden.js county shares and rucc.js metro/nonmetro shares | 1 of 3143 counties differ by >0.55 pts (max 8.7, Bennington); metro 6.6% / nonmetro 45.2% vs 6.6 / 45.2 | ✓ | the residual county is a 20-trial threshold effect: the browser pools the 3,915 located trials, the pipeline table counts 3,919 eligible trials |
