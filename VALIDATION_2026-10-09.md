# Outside validation — 9 October 2026

Three passes of `validate_outside.py` (seeds 1, 2 and 3; 73 checks each, all three from the same revision of the script) against the figures published from the registry data of 5 October 2026. The script does not use the build pipeline's code: it re-derives the figures from the intermediate files, looks every listed trial up on ClinicalTrials.gov on the day of the run, and reads the pages in `docs/` at HEAD, served locally, in a browser. The sampled checks (registry studies for review, site rows, ZIP codes, places) draw a different sample in each pass; the 65 deterministic checks were compared across the three passes and agree on every value. Results: `out_adult55/validation_outside_pass{1,2,3}.json` (the run times are in each file's first entry). A reviewer who had not seen the work checked a draft of this note against the result files and the script; its corrections are folded in.

**Summary.** Every published headline figure but one reproduces exactly from the census-tract file (the exception is a median that is one mile off under the site's own documented rule); the figures read from four pages for 38 sampled places agree with each other and with the tract file; the ZIP finder's page computes what its text says for 90 sampled ZIP codes; 422 sampled site rows are where the registry puts them; the registry search returns everything the registry's condition search for "neoplasms" returns; and the listed set has drifted by 0.4% in the four days since the pull. Three things to fix, none of which changes a published national share: a median rule applied two ways, a stale raw file, and a note on the kinds of trial a condition-field search cannot see.

## 1. Live registry (all 4,001 listed trials, looked up today)

| Check | Result | |
|---|---|---|
| Listed trials found on ClinicalTrials.gov | 4,001 of 4,001 | ✓ |
| Still interventional with primary purpose Treatment | 4,001 of 4,001 | ✓ |
| Age limits still admit some adults 55+ (maximum age ≥ 55 or none, the site's rule) | 4,001 of 4,001 | ✓ |
| Trials whose minimum age is 60 or more (open only to older adults; counted, not excluded) | 39 — the number CHANGES_v3 gives for 5 October | ✓ |
| Payload (data.js) phase, sponsor class and minimum age equal the 5 October pull (trials.csv) | 0 / 0 / 0 mismatches (the payload keeps one decimal of age: 30 days → 0.1) | ✓ |
| Overall status today | 3,986 Recruiting; 11 Active-not-recruiting, 1 Suspended, 1 Enrolling by invitation, 1 Terminated, 1 Completed | drift |
| US sites listed as recruiting (city, state, ZIP) vs the pull | 50,225 unchanged, 226 added, 123 removed (0.7% of rows), across 132 trials | drift |
| Listed trials with no US recruiting site today | 0 | info |
| Trials that would leave the set at a refresh today | 15 of 4,001 (0.4%): NCT03824652, NCT04145622, NCT04712851, NCT04870762, NCT05185505, NCT05336383, NCT05394337, NCT05482516, NCT05663710, NCT05787561, NCT05918783, NCT06389591, NCT06568692, NCT06624085, NCT07429110 | drift |
| Registry edits since the pull | 1 trial's phase changed (NCT06080061, Phase 1 → N/A); 0 sponsor classes changed | drift |
| The site's registry query re-run today | 4,538 studies, the same count as on 5 October; 79 not in the pull, of which 17 have a US recruiting site today and 15 of those also pass the age rule (1 first posted after 5 October); 15 in the pull no longer returned (the 15 above) | info |
| The 17 that would enter at a refresh, reviewed by hand | 16 are cancer treatment trials (breast, CLL, NSCLC, three brain — glioblastoma, brain neoplasm, DIPG — pancreas, two AML, follicular lymphoma, RCC, colorectal, gastric, oropharyngeal, two solid-tumour); two of these (DIPG, a paediatric solid-tumour trial) have a maximum age of 25 and 20 and would be removed by the age rule; the 17th (NCT07694726, lymphedema prevention after head-and-neck surgery) is supportive care registered as Treatment and, since its condition field names a cancer, would be kept | reviewed |
| 5 October pull reconstructed: trials.csv (4,257) + the oncology screen's exclusions (217) | 4,474 = `trials_with_us_recruiting_site` in fetch_log.json | ✓ |
| `data/raw/trials_raw.csv` is the 5 October pull | **✗ 4,294 rows; the pull had 4,474.** The committed file is from an earlier pull. `qc_us.py` refreshes it only when `fetch_log.json` is newer by file date, which git does not keep, so on a checkout where the dates come out the other way it keeps and screens the old file. No published figure reads this file: `trials.csv` is correct and reconciles above. | ✗ |

What the drift means: a reader on 9 October sees figures from 5 October; 15 trials have since stopped recruiting and about 15 have started, or gained a US recruiting site, so the listed count would barely move. Site lists moved on 132 trials. The pages state the data date; this is the scale of staleness a four-day-old page carries.

## 2. What the registry search can and cannot see

| Check | Result |
|---|---|
| Registry condition search for "neoplasms" (the registry's own synonym and MeSH expansion), same filters | 4,219 studies; **0** that the site's keyword search does not return |
| Condition search for "oncology", same filters | 4,219; 0 not returned |
| Full-text search for nine cancer words anywhere in the record (cancer, tumor, carcinoma, lymphoma, leukemia, myeloma, sarcoma, melanoma, malignant), same filters | 4,856; 396 not returned by the keyword search |
| 84 distinct studies from those 396, reviewed by hand (30 per pass, with some overlap) | 83 are not cancer treatment trials: smoking and vaping cessation, chronic GVHD, cirrhosis, heart failure, depression, osteoarthritis, HIV, aplastic anaemia, hemophilia, and supportive care in cancer patients (anaemia during chemotherapy, scalp cooling, checkpoint-inhibitor colitis, chemotherapy neuropathy, palliative demoralisation). **One** is a cancer treatment trial the condition search cannot find: NCT05709782, spinal stereotactic radiosurgery on an MR-LINAC for spinal metastases, whose condition field says only "Spinal Disease"; its summary and eligibility text do use cancer terms, which is why the full-text probe found it. |

So the keyword search is a superset of the registry's own condition search for neoplasms, and what it misses are records whose condition field does not name a cancer. One in 84 reviewed is a small sample: the rate among the 396 could be anywhere from near zero to several percent, which is a handful of trials nationally, not dozens. Supportive-care trials in cancer patients are not returned when their condition field names the symptom rather than the cancer (and are, by the site's definition, not cancer treatment trials); a few whose condition field does name a cancer are returned and kept, as the README's note on supportive-care survivors says. If the author wants to close the gap, a full-text probe like this one plus the oncology screen over the ~400 extra records would do it.

## 3. Headline figures recomputed from the census-tract file

Population-weighted over 84,396 tracts in `out_adult55/tract_access.csv`, with the USDA rural-urban codes joined from `data/ref` (Connecticut's eight legacy counties from the 2013 file), compared with data.js, findings.js and the README's headline block (shares and medians parsed from the README text; the county, state and district counts typed into the script from the README and metrics_log.json).

| Figure | Recomputed | Published | |
|---|---|---|---|
| Residents 55+ | 98,596,429 | 98,596,429 | ✓ |
| Fewer than 20 trials within 60 road-miles | 12.0% (11,847,214 people) | 12.0% (11,847,214) | ✓ |
| None within 60 road-miles | 4.2% (4,155,856) | 4.2% (4,155,856) | ✓ |
| Fewer than 100 within 60 · in a county with no trial | 34.2% · 21.0% | 34.2% · 21.0% | ✓ |
| More than 60 / 120 road-miles from a broad menu | 38.1% / 18.4% | 38.1% / 18.4% | ✓ |
| More than 60 road-miles from a limited menu | 14.1% | 14.1% | ✓ |
| More than 60 / 120 road-miles from an NCI center | 43.7% / 20.8% | 43.7% / 20.8% | ✓ |
| No road route to a broad menu | 0.7% | 0.7% | ✓ |
| Average trials within 30 / 60 / 120 road-miles | 220 / 354 / 575 | 220 / 354 / 575 | ✓ |
| Median road-miles to an NCI center | 48 | 48 | ✓ |
| Median road-miles to a broad menu | **36** (excluding tracts with no route) | 37 | ✗ see below |
| Metro: fewer than 20 · none · >60 from NCI · >60 from broad · median NCI | 6.1% · 1.2% · 35.2% · 28.8% · 35 (82,859,109 residents) | same | ✓ |
| Nonmetro: same | 43.1% · 20.0% · 88.9% · 87.3% · 115 (15,737,320) | same | ✓ |
| Nonmetro share of residents 55+ | 16.0% | 16.0% | ✓ |
| Broad-menu counties · 20+ counties · counties with any trial | 83 · 377 · 838 | 83 · 377 · 838 | ✓ |
| States with no broad-menu county | 15: AK, AR, DE, HI, ID, LA, ME, MS, ND, NH, NM, NV, VT, WV, WY | 15, same list | ✓ |
| Districts where every resident 55+ is beyond 60 road-miles of a broad menu | 73 | 73 | ✓ |
| README headline block | carries every recomputed figure | | ✓ |

**Two median rules.** `build_rucc.py` excludes tracts with no road route (the 999 sentinel) from medians and reports them as the "no road route" share; the metro and nonmetro medians follow that rule. `tract_metrics_us.py`, which produces the national, state and district medians, includes those tracts at 999 miles (its docstring says so: "treated as beyond every distance threshold"), which pushes a median up wherever no-route residents exist. Each file documents its own rule; the site needs one. The two rules disagree in 13 places: the national median to a broad menu (36 vs the published 37); Hawaii's median to an NCI center (10 vs the published 16 — a third of Hawaii's residents 55+ have no road route to the center on Oahu, and counting them as 999 miles moves the median); HI-2's median to an NCI center (15 miles among the third of residents with a route; published as "no route" because two-thirds have none); Maine's median to a broad menu (155 vs 156); ME-2's median to an NCI center (211 vs 212); AZ-9's median to a broad menu (166 vs 171, from one Mohave County tract with no road route); and seven cases — Alaska and AK-at-large for both targets, Hawaii, HI-1 and HI-2 for the broad menu — where the median resident has no route under either rule and the page already says so. Either rule is defensible. Recommendation: make `wmed` in `tract_metrics_us.py` exclude distances ≥ 999, as `build_rucc.py` does, and say under the figure that medians are over residents with a road route.

## 4. Road distances: physical constraints

| Check | Result | |
|---|---|---|
| County → nearest NCI center: road miles shorter than straight-line (impossible) | 0 of the 3,085 counties with a route and more than 3 straight-line miles from the center (3% tolerance for rounding and centroids) | ✓ |
| County → nearest broad menu: road miles shorter than straight-line | 0 of 3,023, same conditions | ✓ |
| Road / straight-line ratio to the nearest NCI center | median 1.17, 10th–90th percentile 1.09–1.32; three counties above 2.5, all on Puget Sound (Island, Jefferson, Kitsap, WA — ferry crossings) | info |
| Road / straight-line ratio to the nearest broad menu | median 1.18, 1.09–1.34 — the README's figures | ✓ |
| Counties with no road route to a broad menu | 35, all in Alaska and Hawaii | info |

## 5. Site locations (three samples of 150 registry site rows, 450 in all)

| Check | Pass 1 | Pass 2 | Pass 3 |
|---|---|---|---|
| The ZIP's Census center lies in the assigned county's (simplified) polygon, or is within 6 miles of the county's population center, or the Census ZCTA→county table agrees; rows the pipeline located by city (ZIP in the wrong state, or a corrected typing error) are judged by the city's gazetteer point | 140 of 140 | 139 of 139 | 143 of 143 |
| The ZIP center is within 40 miles of the registry's stated city (a name shared by several places in a state is matched to the nearest) | 126 of 126 | 124 of 124 | 132 of 132 |

Rows skipped: 10, 11 and 7 whose ZIP has no Census ZCTA center — all of them rows the pipeline placed by three-digit ZIP prefix (`zip3`), which are institutional "unique" ZIPs such as 27710 (Duke), 94143 (UCSF) and 44195 (Cleveland Clinic); and 14, 15 and 11 that did not reach the 40-mile city check (no gazetteer match for the city, or already judged by the city). So this check says nothing about the 1,965 `zip3`-placed rows in the pipeline (see Not checked). Pass 2's sample included a registry row for the University of Colorado Hospital in Aurora, CO with ZIP 88045 (a New Mexico ZIP); the pipeline had set the ZIP aside and placed the site by its city, in Arapahoe County, correctly.

## 6. ZIP finder (three samples of 30 ZIP codes)

| Check | Result | |
|---|---|---|
| find.html's result equals its method recomputed in Python (straight-line × 1.2 between ZIP-code centers and site points, within 60 miles) | 90 of 90 ZIP codes agree | ✓ |
| ZIP estimate vs the county's road-network trials-within-60 (85 ZIPs whose county figure is above zero) | ratio median 1.00, 1.00 and 1.02 in the three passes; 10th–90th percentiles 0.69–1.34, 0.66–2.93 and 0.89–2.27. The two methods agree for the typical ZIP; at the edges the ZIP estimate can be a third of, or three times, the county's figure, because a ZIP near a county line or a metro edge is not its county's average. The finder's note already says the two are different measures. | info |

## 7. Pages agree with each other and with the tract file

For 38 distinct places (24 counties, 8 districts, 6 states; one district was drawn twice), the share of residents 55+ short of trials, the trials-in-county count and the road miles to the nearest NCI center were read from index.html, community.html, brief.html and act.html in a browser and compared with each other and with the tract recomputation: 39 place-checks, 0 disagreements. Cosponsor counts (H.R. 3521: 24, 9 R / 15 D; S. 4440: 1) agree between cosponsors.js and findings.js, which the pages render; the brief and district panel were read by hand earlier and show the same counts. A live check against congress.gov was not possible from the validation environment (see Not checked).

## 8. Page health (13 pages × 2 screen sizes, each pass)

0 JavaScript errors (console errors from the sandbox's blocked CDN requests excluded; d3 falls back to the local copy), 0 pages with horizontal overflow, 0 axe-core WCAG 2 A/AA violations.

## 9. The repository's own checks, re-run on 9 October

`validate_extras.py`: 25 of 25 pass (its output file `VALIDATION_extras.md` was left as committed, so its own date line still reads 6 October). `release_gate.py`: PASS, 19 of 19 (`RELEASE_GATE.md` unchanged).

## Not checked

- Cosponsor counts against congress.gov on the day (the environment could not reach congress.gov or govinfo); cosponsors.js is from the govinfo feed of 5 October and is internally consistent.
- Site rows placed by three-digit ZIP prefix (1,965 rows): the sample check skips them because their ZIPs have no Census center.
- The cancer-type classification of individual trials beyond the registry's own category (the repository's `qc_cancer_type_sample_200.csv` covers this).
- Routed distances against an independent router (`VALIDATION_v3.md` covers 38 city pairs and 23 local routes).
- Cancer words beyond the nine probed (glioma, neoplasm, metastatic, MDS and the like appear in the site's own query but were not probed in full text).

## To do

1. `tract_metrics_us.py`: exclude no-route tracts from medians, matching `build_rucc.py`. Changes: national broad-menu median 37 → 36; Hawaii's NCI median 16 → 10; HI-2's NCI median from "no route" to 15; Maine's broad-menu median 156 → 155; ME-2's NCI median 212 → 211; AZ-9's broad-menu median 171 → 166. No share changes.
2. Refresh `data/raw/trials_raw.csv` from the current pull, or make `qc_us.py` compare the file against `fetch_log.json` by content rather than by file date.
3. At the next refresh, expect 15 trials out and about 15 in; nothing in this note changes any published share.
