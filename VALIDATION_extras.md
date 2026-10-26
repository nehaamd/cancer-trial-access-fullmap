# Validation — v3.3 additions (rural/urban, cosponsors, burden vs access, ZIP lookup)

Checks re-run by `validate_extras.py` on 2026-10-26 (UTC).

| Check | Result | Pass | Context |
|---|---|---|---|
| RUCC: every county carries a code; 2013 fallback limited to Connecticut | 3143 coded, 0 missing; 2013 fallback: 8 (09001, 09003, 09005, 09007, 09009, 09011, 09013, 09015) | ✓ |  |
| RUCC: metro + nonmetro residents 55+ equal the national total; their weighted <20 / none shares reproduce the national figures | 100,019,672 vs 100,019,672; weighted <20 11.80% vs 11.8%; none 4.36% vs 4.3% | ✓ |  |
| RUCC: nonmetro '<20 within 60 road-mi' share recomputed independently from tract_access.csv | 42.6% vs rucc.js 42.6%; metro 6.0% (nonmetro / metro ratio 7.1×) | ✓ |  |
| RUCC: state metro + nonmetro populations equal state totals | 0 mismatches | ✓ |  |
| RUCC: exact residents 55+ with fewer than 20 / no trials within 60 road-mi (n_l20, n_z60) on every metro and nonmetro group, recounted from tract_access.csv | 101 groups, 0 differ; nation 11,830,618 short of trials (6,752,194 nonmetro + 5,078,424 metro) | ✓ |  |
| tract_county.bin: every tract maps back to its own county through meta.county_order | 84,397 of 84,397 tracts; 3143 counties in order list | ✓ |  |
| Cosponsors: every sponsor / cosponsor bioguide ID resolves to a current member of Congress | 33 members on 2 bills; unresolved: none | ✓ |  |
| Cosponsors: the tracked bills are the Clinical Trial Modernization Act only (Ruiz H.R. 3521, Scott S. 4440) | H.R. 3521 Raul Ruiz (30 cosponsors); S. 4440 Tim Scott (1 cosponsors) | ✓ |  |
| Cosponsors: TX-11 (Pfluger) is an original cosponsor of H.R. 3521, not its sponsor (corrects the v3.2 label) | role = original (2025-05-20) | ✓ |  |
| Cosponsors: district → member map covers every non-vacant House seat (+ DC delegate) | 434 mapped; 2 vacant in the payload; 436 district rows | ✓ |  |
| Cosponsors: 100 senators mapped to states | 100 senators across 50 states | ✓ |  |
| Cosponsors: House bills carry only representatives, Senate bills only senators | chambers consistent | ✓ |  |
| Cosponsors: freshness of the pull | fetched 2026-10-26 (0 days ago) from govinfo BILLSTATUS XML… | ✓ | re-run fetch_cosponsors.py before a Hill Day; the deployed page states the fetch date |
| Burden: county '<20 within 60 road-mi' shares recomputed from tract_access.csv; their population-weighted mean equals the national share | max |diff| 0.05 pts (rounding); weighted mean 11.83% vs national 11.8% | ✓ |  |
| Burden: national median and the high-burden/low-access cell recomputed independently | median 471.1 vs 471.1; cell 481 counties / 4,276,969 residents 55+ vs burden.js 481 / 4,276,969; 3130 classified | ✓ |  |
| Burden: the four cells partition the classified counties | 481 + 1041 + 816 + 792 = 3130 vs 3130 | ✓ |  |
| Burden: plausibility read of the largest high-burden/low-access counties by annual diagnoses | Leon (12); Lafayette (22); Butte (06); Harrison (28); Santa Rosa (12) | ✓ | same-session read; mid-sized metros without a trial hub within 60 road-miles — not independently reviewed |
| Burden: cancer-type-specific 'none within 60 road-mi' shares present for every named type | 20 types × 3143 counties | ✓ |  |
| ZIP lookup: site points match the payload one-to-one; ZCTAs cover the 50 states + DC | 2423 site points vs 2423 in DATA.SP; 33,640 ZCTAs, 51 states | ✓ |  |
| ZIP lookup: every ZCTA's county exists in the payload | 0 bad | ✓ |  |
| ZIP lookup: spot check — nearest site point to ZIP 77030 (Texas Medical Center) is in Harris County within ~2 miles | 0.2 mi; facilities there include ['Site-104', '014', '069'] | ✓ |  |
| ZIP lookup: spot check — El Paso ZIP 79901 finds site points within 60 estimated road-miles and no Houston sites | 7 site points within 60 est. road-mi | ✓ |  |
| ZIP lookup: large ZIP code areas measure from their residents (99701 Fairbanks, 99503 Anchorage, 83716 Boise each have a site point within 10 miles) | all three within 10 miles | ✓ | population-weighted ZCTA centers (build_zcta_centers.py: 23,884 of 33,640 from tract population centers, the rest Census internal points) |
| ZIP lookup: every population-weighted ZIP center lies within a mile of its own ZIP area and passes the coverage test; find_data.js uses those centers | 23,884 weighted centers: 0 outside their ZIP area (or not tested), 0 outside the coverage band; 0 of 33,640 finder ZIPs not at their center | ✓ |  |
| ZIP lookup page states its limits (information only; eligibility decided by the study team; ZIP stays in the browser; NCI 1-800-4-CANCER present) | all phrases present | ✓ |  |
| Map page loads the three new data files and states the burden view is a cross-tabulation, not a score | rucc.js, cosponsors.js, burden.js referenced; 'never a combined score' present | ✓ |  |
| community.js reproduces data.js / burden.js for every county, district and state | 3143 counties (0 differ), 436 districts (0 differ), 51 states (0 differ); nation 11.8% vs 11.8% | ✓ | built by build_community.py from the same files the map reads; the Your community and What could help pages read this file |
| community.js carries the tracked bills with the cosponsor fetch date | H.R. 3521: 30 cosponsors, S. 4440: 1 cosponsors; fetched 2026-10-26 | ✓ |  |
| Oncologists: every county has a row, and each county's category follows from its oncologist count and its trial count in data.js | 3,143 counties (0 missing, 0 extra); 0 categories disagree | ✓ |  |
| Oncologists: residents 55+ by category, recounted from tract_access.csv, equal oncologists.js (and the four shares sum to 100) | recounted {1: np.float64(78.3), 2: np.float64(11.1), 3: np.float64(0.7), 4: np.float64(9.9)} vs published {1: 78.3, 2: 11.1, 3: 0.7, 4: 9.9}; sum 100.0 | ✓ |  |
| Oncologists: state and district residents 55+ equal data.js | 51 states (0 differ), 436 districts (0 differ by more than 1) | ✓ |  |
| Oncologists: the ASCO-comparable count reproduces the published workforce study (14,547 in the March 2024 Care Compare file; oncologists in 45% of counties; 89% of residents 55+ in a county with one) | 15,670 clinicians in the 2026-10-02 file (+7.7%); counties 46.0% vs 45.0%; residents 55+ 89.4% vs 89.0% | ✓ | a newer file: ASCO reported growth of about 2% a year (12,267 in 2014 to 14,547 in 2024); the map's own count also excludes pediatric hematology-oncologists |
| Oncologists: the county of every adult NCI-designated center (by its ZIP, or its city) has oncologists listed | 67 centers, 67 placed; 0 without | ✓ |  |
| Oncologists: no CMS oncology specialty label is unmapped, and the only unplaced practice locations are outside the 50 states and DC | unmapped labels: none; 229 unplaced rows, e.g. ['PR', 'PR', 'PR', 'PR', 'PR', 'PR', 'PR', 'GU'] | ✓ |  |
| Oncologists: cross-check with NPPES — share of the map's oncologists whose registry entry carries an oncology or hematology taxonomy | 14,382 of 15,129 (95.1%); pediatric excluded: 541 | ✓ |  |
| Oncologists: the downloadable county table matches oncologists.js and data.js | 3,143 rows; 0 differ | ✓ |  |
| Map page loads oncologists.js and offers the layer | oncologists.js referenced; layer 'onc' defined | ✓ |  |
