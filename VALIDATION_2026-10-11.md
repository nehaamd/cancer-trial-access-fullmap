# Outside validation — 11 October 2026

One pass of `validate_outside.py` (seed 4; 102 checks) against the figures published by the registry refresh of 11 October 2026 (commit 190ac4a, registry data of 9 October 2026 09:00, fetched 11 October 02:41 UTC). This is the first refresh built with the pipeline rules of pull request #25. The script does not use the build pipeline's code: it re-derives the figures from the intermediate files, looks every listed trial up on ClinicalTrials.gov, and reads the pages in `docs/`, served locally, in a browser. Results: `out_adult55/validation_outside_pass4.json` (run 11 October 03:43–03:50 UTC; the start time is in its first entry). The script was changed for this pass so that it reads every expected value from the build under test instead of carrying the numbers of 5 October; section 9 lists the changes.

**Summary.** Every published headline figure reproduces exactly from the census-tract file, and so does every figure in the Key findings rural/urban table, which is now checked in full. ClinicalTrials.gov was still serving the same registry data as the pull (9 October 09:00), and the payload reproduces it exactly: 4,007 of 4,007 trials, with status, purpose, age limits, phase, sponsor class and 50,461 US site locations all identical. So this pass confirms the pull; it cannot measure drift since it. Pull request #25's site rules took effect. The two site-placement checks it added reported 58 rows on 10 October and report none now, and the 58 rows are in their stated city's county. Pages, ZIP finder and page health are clean: 13 places agree across four pages, 30 of 30 ZIP codes match the finder's method, and 14 pages at 2 screen sizes show no errors, no overflow and no accessibility violations. One check fails: the committed `data/raw/trials_raw.csv` is still the pull of 1 October. Three things a reader of CHANGES_v3 or the 9 October note should know:

- Tuscola County went from 31 trials to 2, not to 0. The 2 that remain are at Caro Cancer Center, which is in Tuscola.
- The seven counties from the 5 October link check are unchanged. The new city rule does not reach them.
- The registry figures in sections 1–2 of the 9 October note are from that day's first run, not from the re-runs saved in the result files.

## 1. Live registry (all 4,007 listed trials, looked up on 11 October)

| Check | Result | |
|---|---|---|
| Registry data the API serves today (`/api/v2/version`) vs the pull's | 2026-10-09T09:00:05 vs 2026-10-09T09:00:05: the same snapshot (ClinicalTrials.gov had not published a newer one by 03:43 UTC on 11 October) | info |
| Listed trials found on ClinicalTrials.gov | 4,007 of 4,007 | ✓ |
| Still interventional with primary purpose Treatment | 4,007 of 4,007 | ✓ |
| Age limits still admit some adults 55+ (maximum age ≥ 55 or none, the site's rule) | 4,007 of 4,007 | ✓ |
| Trials whose minimum age is 60 or more (open only to older adults; counted, not excluded) | 39 in the registry, 39 in the payload, the same trials | ✓ |
| Payload (data.js) phase, sponsor class and minimum age equal the pull (trials.csv) | 0 / 0 / 0 mismatches | ✓ |
| Overall status today | 4,007 Recruiting | info |
| US sites listed as recruiting (city, state, ZIP) vs the pull | 50,461 unchanged, 0 added, 0 removed | info |
| Phase or sponsor class edited since the pull | 0 / 0 | info |
| Trials that would leave the set at a refresh today | 0 | info |
| The site's registry query re-run today | 4,543 studies, the pull's `api_total_count`; 62 not in the pull, none with a US site listed as recruiting (the pull keeps the 4,481 that have one); 0 in the pull no longer returned | info |
| The pull reconstructed: trials.csv (4,265) + the oncology screen's exclusions (216) | 4,481 = `trials_with_us_recruiting_site` in fetch_log.json | ✓ |
| `data/raw/trials_raw.csv` is the pull | **✗ 4,294 rows, the latest registry update in them 30 September: it is the pull of 1 October (registry data of 30 September).** `qc_us.py` rewrites the file from each fresh pull (since 10 October it decides by content whether `trials.csv` is fresh), but the refresh workflow commits `trials.csv`, `us_sites.csv`, `fetch_log.json` and `trial_cancer_type.csv`, not `trials_raw.csv` or `us_sites_raw.csv` (58,240 rows; this pull had 59,599). No published figure reads either file. | ✗ |

What this means: on 11 October the registry was still serving the data of Friday 9 October, so "today" and "the pull" are the same snapshot, and every row above re-reads the pull with independent code. They agree to the trial, the field and the site. Drift since the pull is zero by construction and will first show after ClinicalTrials.gov's next update. The 9 October passes measured the drift over the four days from the registry data of 5 October to that of 9 October: 0.4% of listed trials left and about 1% of US site rows changed. That is the scale to expect a few days after a refresh.

**What the refresh changed in the listed set, against the 9 October prediction.** The 9 October result files were re-run on 10 October at 03:46–03:57 UTC, when the registry was already serving the data of 9 October (the same snapshot as this refresh). They said 17 listed trials would leave and 25 new studies had a US recruiting site, 23 of which passed the age rule. The refresh matches: 17 left and 23 entered (4,001 − 17 + 23 = 4,007), though the 23 that entered are not quite the 23 predicted.

- **The 17 that left** are the 17 of the result files: the 15 named in the 9 October note, plus NCT07283900 and NCT07333261.
- **Of the 23 predicted to enter, 22 entered.** The refresh's pull, read from the same snapshot, holds the same counts: 25 studies not in the 5 October pull with a US recruiting site, 23 of them passing the age rule. All 22 were last updated 6–9 October. 21 are cancer treatment trials; the 22nd is NCT07694726, the lymphoedema-prevention study filed as Treatment, which the 9 October note said would be kept. The one that did not enter, NCT07729137, a corneal-oedema study, was excluded by the oncology screen, correctly.
- **The 23rd trial to enter**, NCT07814352 (SX-682 with proton craniospinal irradiation for leptomeningeal disease), was in the 5 October pull but excluded by the screen. It returned because pull request #25 made the screen recognise leptomeningeal disease, so it entered by a method change, not a registry change.

The tables in sections 1 and 2 of `VALIDATION_2026-10-09.md` give the first run of 9 October, 06:13 UTC, on an earlier registry snapshot. That run found 4,538 studies, 15 leaving and 17 new with a US site, 15 of them passing the age rule, and its full-text probe returned 4,856 studies. The committed result files are the re-runs and say 4,543, 17, 25, 23 and 4,860. The shares in that note are unaffected.

## 2. What the registry search can and cannot see

| Check | Result |
|---|---|
| Registry condition search for "neoplasms" (the registry's own synonym and MeSH expansion), same filters | 4,224 studies; **0** that the site's keyword search does not return |
| Condition search for "oncology", same filters | 4,224; 0 not returned |
| Full-text search for nine cancer words anywhere in the record (cancer, tumor, carcinoma, lymphoma, leukemia, myeloma, sarcoma, melanoma, malignant), same filters | 4,860; 396 not returned by the keyword search (the same counts as the 9 October result files, which read the same registry snapshot) |
| 30 studies from those 396, reviewed by hand (24 not reviewed on 9 October) | None is a cancer treatment trial: atopic dermatitis, Crohn's disease and ulcerative colitis, lupus CAR-T, ANCA vasculitis, alopecia, two graft-versus-host prophylaxis trials, transplants for inborn errors of immunity and metabolic disease, GM1 gangliosidosis, familial platelet disorder, diabetes, cognitive decline, early psychosis, respiratory infections (parainfluenza and COVID-19 in immunocompromised patients, two pneumonia trials), atrial fibrillation, transthyretin amyloidosis, NASH, lung-transplant rejection, corneal epithelial defect, neurogenic bladder, knee arthrofibrosis, radiation wounds, vaping cessation. One is borderline: NCT07284485, nadunolimab as immunoprevention for high-risk lung nodules in current or former smokers, a premalignant condition filed as Treatment. Like NCT05753748 (Barrett's dysplasia), it would be doubtful even if the search found it. |

With the 84 reviewed on 9 October, 108 distinct studies from the 396 have now been read. One is a cancer treatment trial the condition search cannot find: NCT05709782, spinal radiosurgery for spinal metastases, whose condition field says only "Spinal Disease". On 11 October it was still Recruiting and still absent from the pull. The conclusion of 9 October stands. The keyword search returns everything the registry's own neoplasm search returns. What it misses are records whose condition field names no cancer: a handful nationally, not dozens.

## 3. Headline figures recomputed from the census-tract file

Population-weighted over 84,396 tracts in `out_adult55/tract_access.csv`, with the USDA rural-urban codes joined from `data/ref` (Connecticut's eight legacy counties from the 2013 file). Each figure is compared with data.js, findings.js, metrics_log.json and the README's headline block. Expected counts are now read from those files, not typed into the script. The last column gives the figures published from the data of 5 October, as checked on 9 October.

| Figure | Recomputed | Published | | 5 Oct data |
|---|---|---|---|---|
| Residents 55+ | 98,596,429 | 98,596,429 | ✓ | 98,596,429 |
| Fewer than 20 trials within 60 road-miles | 12.0% (11,879,390 people) | 12.0% (11,879,390) | ✓ | 12.0% (11,847,214) |
| None within 60 road-miles | 4.3% (4,232,394) | 4.3% (4,232,394) | ✓ | 4.2% (4,155,856) |
| Fewer than 100 within 60 · in a county with no trial | 34.2% · 21.1% | 34.2% · 21.1% | ✓ | 34.2% · 21.0% |
| More than 60 / 120 road-miles from a broad menu | 38.1% (37,587,924) / 18.4% | same | ✓ | 38.1% / 18.4% |
| More than 60 road-miles from a limited menu | 14.0% | 14.0% | ✓ | 14.1% |
| More than 60 / 120 road-miles from an NCI center | 43.7% (43,130,974) / 20.8% | same | ✓ | 43.7% / 20.8% |
| No road route to a broad menu · to an NCI center | 0.7% · 0.4% | 0.7% · 0.4% | ✓ | 0.7% · — |
| Average trials within 30 / 60 / 120 road-miles · in the home county | 220 / 355 / 576 · 127 | same | ✓ | 220 / 354 / 575 · — |
| Median road-miles to an NCI center · broad menu · limited menu | 48 · 36 · 0 | 48 · 36 · 0 | ✓ | 48 · 36 · — |
| Metro: fewer than 20 · none · >60 from NCI · >60 from broad · median NCI | 6.2% · 1.3% · 35.2% · 28.8% · 35 (82,859,109 residents, 1,186 counties) | same | ✓ | 6.1% · 1.2% · 35.2% · 28.8% · 35 |
| Nonmetro: same | 43.0% · 20.2% · 88.9% · 87.3% · 115 (15,737,320, 1,957 counties) | same | ✓ | 43.1% · 20.0% · 88.9% · 87.3% · 115 |
| Metro / nonmetro, the rest of findings.js's table: fewer than 100; average within 30 / 60 / 120; >120 from NCI; >120 from broad; median to broad; no road route to broad | 24.8% / 83.6%; 260 / 411 / 631 and 10 / 60 / 288; 15.7% / 47.8%; 13.6% / 43.4%; 25 / 109; 0.6% / 1.1% | same | ✓ | not checked |
| Nonmetro share of residents 55+ | 16.0% | 16.0% (README) | ✓ | 16.0% |
| Broad-menu counties · 20+ counties · counties with any trial | 82 · 380 · 832 | 82 · 380 · 832 (metrics_log; README for the first two) | ✓ | 83 · 377 · 838 |
| States with no broad-menu county | 15: AK, AR, DE, HI, ID, LA, ME, MS, ND, NH, NM, NV, VT, WV, WY | 15, same list (findings.js, README) | ✓ | 15, same |
| Districts where every resident 55+ is beyond 60 road-miles of a broad menu | 73 | 73 (findings.js, README) | ✓ | 73 |
| README headline block | carries every recomputed figure it states (13 phrases, now including "4,007 listed trials" and "2,438 distinct site locations"); its rural sentence (fewer than 20, none, median to an NCI center, nonmetro and metro) equals the recomputation | | ✓ | ✓ |
| Medians published for the nation, 51 states and 436 districts (NCI center, broad menu, limited menu) equal the one rule recomputed from tracts | 0 differences | | ✓ | 0 |

**Why the county counts moved.** These were traced row by row against the build of 10 October (`site_assignment_qc.csv` at 6d4b74d, which used the 5 October data).

- **Broad menu, 83 to 82.** Washington County, Oregon fell from 107 trials to 83. This is a registry change. On about 30 trials updated 6–9 October, Providence St. Vincent and Providence Portland are no longer listed as recruiting. On NCT03739814, both Providence sites and all but one of its other Oregon sites are now Suspended; the exception, Oregon Health and Science University, is Active, not recruiting.
- **Limited menu, 377 to 380.** Gained: Iosco MI (0 → 31), Hudson NJ (19 → 20, a Jersey City row) and Pueblo CO (19 → 20), all by pull request #25's city rule, and Whatcom WA (19 → 20, a new Bellingham row in the registry). Lost: Tuscola MI (31 → 2), by the city rule.
- **Counties with any trial, 838 to 832.** Ten of the eleven counties that lost their only trials lost them to the city rule, which moved rows from the ZIP-prefix county to the stated city's county: Morton KS → Seward (Liberal), Carteret NC → Craven (New Bern), Lincoln NE → Douglas (Omaha), and DeKalb AL, Breckinridge KY, Conejos CO, Somerset PA, Giles VA, Cass TX and Grant IN. The eleventh, Leavenworth KS, is a registry change. All five gains are the city rule: Iosco, Seward, Craven, Martinsville VA and Howard IN (Kokomo).

The national "none within 60 road-miles" moved from 4.2% to 4.3%, as pull request #25's dry run predicted. This pass cannot separate the share due to the new rules from the share due to the new registry data.

## 4. Road distances: physical constraints

| Check | Result | |
|---|---|---|
| County → nearest NCI center: road miles shorter than straight-line (impossible) | 0 of the 3,085 counties with a route and more than 3 straight-line miles from the center (3% tolerance) | ✓ |
| County → nearest broad menu: road miles shorter than straight-line | 0 of 3,024, same conditions | ✓ |
| Road / straight-line ratio to the nearest NCI center | median 1.17, 10th–90th percentile 1.09–1.32; three counties above 2.5, all on Puget Sound (Island, Jefferson, Kitsap, WA: ferry crossings) | info |
| Road / straight-line ratio to the nearest broad menu, and the README's "the common ×1.2 convention is too low for 1,271 of 3,026 counties" | median 1.18, 1.09–1.34; ratio above 1.2 for 1,271 of the 3,026 counties with a route (recomputed with the README's own subset) | ✓ |
| Counties with no road route to a broad menu | 35, all in Alaska and Hawaii | info |

## 5. Site placement

**Sample of 150 registry site rows.** For 147 of 147 rows, the ZIP code's Census center lies in the assigned county (by the county's simplified polygon, within 6 miles of its population center, or by the Census ZCTA→county table). Rows located by city are judged by the city's point. Three rows placed by ZIP prefix have no ZIP center and were skipped (Duke University, Durham, 27710, twice; Saint Vincent Hospital, Erie, 16544). For 131 of 131 rows with a gazetteer match, the ZIP center is within 40 miles of the stated city. ✓

**The two checks pull request #25 added, which read every row (not a sample):**

| Check | 10 October build (data of 5 Oct, old rules) | This refresh | |
|---|---|---|---|
| Rows whose county came from the ZIP's first three digits: stated city within 40 miles of the assigned county | 58 of 1,940 judged rows far | 1,945 of 1,945 judged (25 without a gazetteer match; 1,780 by ZIP prefix, 190 by the city over the ZIP prefix) | ✓ |
| Rows drawn at a county center although the stated city lies elsewhere ("phantom" sites) | 58 rows | 0; `route_sites_log.json` records 0 rows left unlocated | ✓ |
| Rows at a county center because neither ZIP nor city is known | 26 | 9 | info |

The 58 rows of 10 October are all in this refresh's data, and all are now assigned to the stated city's county (`city_over_zip3`). They are Tawas City → Iosco County MI (31 rows; Tuscola before), Albemarle → Stanly NC (7), Liberal → Seward KS (4), Omaha → Douglas NE (2), and 14 single rows (Birmingham, Cleveland, two Dallas, Louisville, Martinsville, Newport Beach, Pittsburgh, Pueblo, Rochester MN, Salisbury MD, San Diego, Seattle, West Palm Beach).

CHANGES_v3's dry-run predictions for these moves held for Iosco (0 → 31 trials) and Pueblo (19 → 20), and for the national 4.2% → 4.3%. **They did not hold for Tuscola: 31 → 2, not 31 → 0.** Two of the 31 trials also list Caro Cancer Center (Caro, ZIP 48723, in Tuscola County). Those two remain, correctly, and Tuscola is no longer a limited-menu county, as predicted.

The shared city-spelling rule took effect for the Lexington KY (10), Nashville TN (3), St Louis MO (3) and Washington DC (1) rows that were drawn at a county center on 10 October. Those 17 rows are now placed at their city's center. The 9 rows still at a county center are all in Connecticut, in the right county, about 4 to 9 miles from where the site is (positions approximate):

- University of Connecticut Health Center, Farmington, ZIP 06030: 7 rows; the hospital is about 4 miles from Hartford County's population center.
- Smilow Cancer Hospital, Trumbull, ZIP 06835: 1 row; Trumbull is about 9 miles from Fairfield County's.
- A row typed "New Have", ZIP 06520 (Yale): 1 row; central New Haven is about 6 miles from New Haven County's.

Farmington and Trumbull are Connecticut towns, which the Census places file does not list; the third city is mistyped; and none of the three ZIP codes has a Census ZIP area.

**Every row placed by its ZIP (new check, all rows).** In 268 of 47,137 judged rows, the ZIP center is more than 25 miles from the stated city and the city lies outside the assigned county (62 rows over 40 miles). In most of these the ZIP is right and the city loose. Seven counties rest entirely on such rows, each showing 1 trial, and they are exactly the seven of the 5 October link check:

- Gage NE: "Omaha" 68310
- Chatham NC: Wake Forest University, "Winston-Salem" 27517
- Halifax NC: "Greenville" 27843
- Mitchell NC: "Charlotte" 28777
- Ashtabula OH: "Akron" 44032
- Brazos TX: Baylor Scott & White, "Round Rock" 77845
- Skamania WA: "Vancouver" 98648

The new city rule applies only when the ZIP code has no Census ZIP area, and these ZIPs have one, so the rule does not reach them. Their status is unchanged. Brazos's single trial is one of the 2 within 60 road-miles of its population center. The other six have 22 to 434 trials within 60 road-miles of theirs, so losing one would not take any of them below 20.

## 6. ZIP finder (30 ZIP codes)

| Check | Result | |
|---|---|---|
| find.html's result equals its method recomputed in Python (straight-line × 1.2 between ZIP-code centers and site points, within 60 miles) | 30 of 30 ZIP codes agree | ✓ |
| ZIP estimate vs the county's road-network trials-within-60 (29 ZIPs whose county figure is above zero) | ratio median 1.02, 10th–90th percentile 0.89–2.52. Example: ZIP 46932 (Cass County IN) has 66 by the finder against the county's 12.0. The census tract around that ZIP has 62 by road; the county's other ten tracts have 4 to 8 | info |
| ZIP estimate vs the road-network figure of the census tract nearest the ZIP center (new: same place, different distance method) | 23 of 30 within 10% (or 2 trials); ratio median 1.00, 10th–90th percentile 0.98–2.85 | info |

The seven ZIPs outside 10% of their nearest tract all have a cluster of sites just inside or just outside the 60-mile line, where a few miles of difference between straight-line × 1.2 and the routed road moves dozens of trials. ZIP 18370 (Monroe County PA) has 97 trials within 55 estimated miles and 324 within 60, against 114 by road. ZIP 50449 has 0 within 55 and 51 within 60, against 5 by road. ZIP 38650 goes the other way: 40 by the finder, 82 by road. The finder's note already says real driving distance can be shorter or longer.

## 7. Pages

**Pages agree with each other and with the tract file.** For 13 places (8 counties, 3 districts, 2 states), the share of residents 55+ short of trials, the trials-in-county count and the road miles to the nearest NCI center were read from index.html, community.html, brief.html and act.html in a browser and compared with each other and with the tract recomputation: 13 places, 0 disagreements ✓.

The sample included Aleutians West AK (02016), which has no road route to an NCI center. The pages say so in words: index.html "…more than 30 miles from any primary or secondary road; no road distance is reported", community.html "…, so no road distance is reported", brief.html "No road route to an NCI-designated center". The script's first run reported these as "not found on page", so it now reads those sentences as "no route". Checked on five Alaska and Hawaii counties, including Honolulu, which reaches an NCI center but no broad menu; community.html words that differently, and the script reads it.

**Cosponsors.** cosponsors.js and findings.js agree:

- H.R. 3521: 30 cosponsors, 11 R and 19 D (24 on 5 October).
- S. 4440: 1 cosponsor, D.

The Library of Congress bill-status XML on govinfo, read on 11 October through a web reader (the validation environment's shell cannot reach govinfo or congress.gov), lists the same 30 H.R. 3521 cosponsors with the same dates, none withdrawn (record updated 7 October). It lists Mark Warner (D-VA) as the one S. 4440 cosponsor. congress.gov itself refuses automated reading.

**Page health.** 14 pages × 2 screen sizes (1440 and 390 px; sites.html added this time). 0 JavaScript errors (the sandbox's blocked cdnjs requests excluded; d3 falls back to the local copy), 0 pages with horizontal overflow, 0 axe-core 4.10.2 WCAG 2 A/AA violations ✓.

## 8. The repository's own checks, re-run on 11 October

`validate_extras.py`: 25 of 25 pass. Its output file was restored afterwards. The committed `VALIDATION_extras.md` is still dated 6 October with the figures of the 5 October data (12.01%, 4.20%, nonmetro 43.1%), because the refresh runs these checks only inside `validate_v3.py`, whose `VALIDATION_v3.md` is current. `release_gate.py`: PASS, 27 of 27; `RELEASE_GATE.md` was rewritten identically.

## 9. Changes to `validate_outside.py` for this pass

- **Serving the pages.** The local server binds 127.0.0.1 on `--port` (default 8103, was 8791). If that port is taken, the script uses a free port instead. It reads pages only after its own server process is up and serving this checkout's `data.js`, so it can never read another checkout's server. The axe-core path is an option (`--axe`, or `$AXE_CORE_JS`), replacing two hard-coded paths from an earlier session's scratch directory.
- **Values read from the build, not typed in.**
  - The pull's dates come from `fetch_log.json`: "Oct 5" labels, and the "first posted after" date was the literal 2026-10-05.
  - The minimum-age-60 count is compared with the payload's own count, with the registry's last-update date shown for any difference (it was compared with the literal 39 of 5 October).
  - Broad / limited / any-trial county counts come from `metrics_log.json` and the README (they were 83 and 377).
  - States with no broad menu and fully beyond-60 districts are read from findings.js and the README (the districts were the literal 73).
  - The nonmetro share is read from the README (it was 16.0%).
  - The road/straight-line ratio is read from the README (it was 1.18).
- **New checks.**
  - The registry API's data date against the pull's.
  - The README's "×1.2 too low for N of M counties", its rural sentence, and six more phrases of the headline block.
  - findings.js's `nrn`, `own`, `people_g60n` and `people_g60b`, and the whole metro / nonmetro table (`n`, `l100`, `t30`, `t60`, `t120`, `g120n`, `g120b`, `medb`, `nr`).
  - Every ZIP-placed row's ZIP center against its stated city, with the counties that rest on such rows.
  - The ZIP finder against the nearest tract's road figure.
  - sites.html in page health.
- **Changed wording or rules.**
  - The two pull request #25 checks no longer say "clears at the next refresh" and now list the rows still at a county center.
  - The "first posted after" count now counts only studies that would enter.
  - A county with no road route to an NCI center is read from the page's sentence.
  - Registry requests are 0.6 s apart (was 0.3–0.4 s).

## What remains

1. `data/raw/trials_raw.csv` and `us_sites_raw.csv` in the repository are the pull of 1 October. Either the refresh workflow should commit them with the other raw files, or they should be removed from the repository. They cannot be re-screened without `studies_raw.jsonl`, which is not committed. If a stale copy is left in place, `qc_us.py` run without a fresh fetch reads it instead of the pull.
2. The seven counties whose single trial rests on a far-off ZIP (section 5) need a rule or a review by hand. Brazos TX matters most: its trial is 1 of the 2 within 60 road-miles of its population center.
3. CHANGES_v3's entry of 10 October says Tuscola County goes from 31 trials to 0; the refresh gives 2 (section 5).
4. Drift since the pull was not measured, because the registry had not updated. The next pass should run after ClinicalTrials.gov's next update.

**Not checked.**

- Cosponsors on congress.gov itself (the bill-status XML on govinfo was read instead).
- The exact location of the 1,780 rows placed by ZIP prefix, beyond their county (the full-file check above judges the county only).
- The cancer-type classification of individual trials beyond the registry's own category.
- Routed distances against an independent router (`VALIDATION_v3.md` covers 38 city pairs and 23 local routes).
- Cancer words beyond the nine probed in full text.
