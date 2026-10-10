"""Outside validation of the published figures, independent of the build scripts.

What it checks (each pass; sampled checks use --seed so that repeated passes draw different samples):
  1. Live registry: every one of the 4,001 listed trials is looked up on ClinicalTrials.gov today (API v2, batches of 100) and compared
     with the payload: status, study type and purpose, age limits (still accepting some adults 55+), phase, sponsor class, and the set
     of US sites listed as recruiting. The site's own registry query is re-run and its ID set compared with the raw pull.
  2. Coverage probe: a broader registry search (the MeSH-expanded condition "neoplasms", same filters) is compared with the site's
     keyword search; a seeded sample of the studies only the broader search returns is printed for review.
  3. Headline figures recomputed from out_adult55/tract_access.csv (population-weighted over census tracts) with the USDA rural-urban
     codes joined from data/ref, and compared with data.js, findings.js, community.js and the README's headline block; medians are over residents with a road route.
  4. Physical constraints on road distances: road miles to the nearest NCI center and broad menu must be at least the straight-line
     distance (never shorter); the road / straight-line ratio distribution.
  5. Site locations: a seeded sample of registry site rows; the ZIP's Census center must fall in the assigned county's polygon (or
     within a short distance of it, since the polygons are simplified) and within 40 miles of the registry's stated city.
  6. ZIP finder: for a seeded sample of ZIP codes, the finder's method (straight-line x 1.2 between ZIP centers and site points) is
     recomputed from find_data.js and compared with what find.html shows in a browser; both are set against the county's road-network
     figure as an informational comparison.
  7. Cross-page agreement: for a seeded sample of counties, districts and states, the figures shown by index.html, community.html,
     brief.html and act.html are read in a browser and compared with each other and with the tract recomputation.
  8. Page health on the deployed files: JavaScript errors, horizontal overflow and axe-core (WCAG 2 A/AA) on every page at 1440 and 390 px.
Usage: python3 validate_outside.py --seed 1 [--out out_adult55/validation_outside_pass1.json] [--no-browser] [--sites 150] [--zips 30]
Needs: pandas, numpy, playwright (for 6-8), network access to clinicaltrials.gov, and a local server for docs/ (started by the script).
"""
import argparse, csv, json, math, random, re, socket, subprocess, sys, time, urllib.parse, urllib.request
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; DOCS = ROOT / "docs"; OUT = ROOT / "out_adult55"; REF = ROOT / "data" / "ref"; RAW = ROOT / "data" / "raw"
API = "https://clinicaltrials.gov/api/v2/studies"
R_EARTH = 3958.8
results = {}; notes = []
def rec(section, name, value, ok=None, detail=None):
    ok = None if ok is None else bool(ok)   # numpy booleans would otherwise be written as the strings "True" / "False"
    results.setdefault(section, []).append({"check": name, "value": value, "ok": ok, "detail": detail})
    flag = "PASS" if ok is True else "FAIL" if ok is False else "INFO"
    print(f"[{flag}] {section} · {name}: {value}" + (f" — {detail}" if detail else ""), flush=True)

def load_js(path, prefix):
    s = Path(path).read_text(encoding="utf-8"); i = s.index("=") + 1 if prefix is None else len(prefix)
    return json.loads(s[i:].rstrip().rstrip(";"))

def miles(a, b):
    dlat = math.radians(b[0] - a[0]); dlon = math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))

def api(params, retries=4):
    url = API + "?" + urllib.parse.urlencode(params)
    for k in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r: return json.loads(r.read())
        except Exception as e:
            if k == retries - 1: raise
            time.sleep(2 + 3 * k)

def age_years(s):
    if not s: return None
    m = re.match(r"\s*([\d.]+)\s*(Year|Month|Week|Day|Hour|Minute)", s, re.I)
    if not m: return None
    v = float(m.group(1)); u = m.group(2).lower()
    return v if u == "year" else v / 12 if u == "month" else v / 52 if u == "week" else v / 365 if u == "day" else 0.0

PHASE_MAP = {("PHASE1",): "1", ("PHASE1", "PHASE2"): "1-2", ("PHASE2",): "2", ("PHASE2", "PHASE3"): "2-3", ("PHASE3",): "3", ("PHASE4",): "4", ("NA",): "NA", (): "NA", ("EARLY_PHASE1",): "1"}
SPONSOR_MAP = lambda c: "industry" if c == "INDUSTRY" else "nih_federal" if c in ("NIH", "FED") else "academic_other"
SITE_STATUS_KEEP = {"RECRUITING", None, ""}
STATE_NAMES = None

# ---------------------------------------------------------------- 1. live registry ----------------------------------------------------------------
def live_registry(D, seed):
    T = D["T"]; ids = T["id"]; n = len(ids)
    fields = "NCTId,BriefTitle,OverallStatus,StudyType,DesignPrimaryPurpose,MinimumAge,MaximumAge,Phase,LeadSponsorClass,LastUpdatePostDate,LocationCity,LocationState,LocationZip,LocationCountry,LocationStatus,LocationFacility,Condition"
    live = {}
    for i in range(0, n, 100):
        batch = ids[i:i + 100]
        d = api({"filter.ids": ",".join(batch), "fields": fields, "pageSize": 100, "format": "json"})
        for s in d.get("studies", []):
            ps = s["protocolSection"]; live[ps["identificationModule"]["nctId"]] = ps
        time.sleep(0.3)
    rec("registry", "listed trials found on ClinicalTrials.gov today", f"{len(live):,} of {n:,}", len(live) == n, "missing: " + ", ".join(x for x in ids if x not in live) if len(live) < n else None)
    # per-trial comparison
    st = Counter(); not_rec = []; not_int = []; age_bad = []; phase_mis = []; sp_mis = []; no_us_site = []; site_added = site_removed = site_same = 0; trials_changed_sites = 0
    us_sites = defaultdict(set)
    with open(RAW / "us_sites.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f): us_sites[r["nct_id"]].add(((r["city"] or "").strip().lower(), r["state"], (r["zip"] or "")[:5]))
    ph_names = T["phases"]; sp_names = [x[0] for x in T["sponsors"]]
    pull = {r["nct_id"]: r for r in csv.DictReader(open(RAW / "trials.csv", newline="", encoding="utf-8"))}
    pull_phase = lambda r: PHASE_MAP.get(tuple(x for x in r["phases"].split(";") if x), "?")
    pay_ph_mis = [(nct, pull_phase(pull[nct]), ph_names[T["ph"][j]]) for j, nct in enumerate(ids) if nct in pull and pull_phase(pull[nct]) != ph_names[T["ph"][j]]]
    pay_sp_mis = [(nct, SPONSOR_MAP(pull[nct]["lead_sponsor_class"]), sp_names[T["sp"][j]]) for j, nct in enumerate(ids) if nct in pull and SPONSOR_MAP(pull[nct]["lead_sponsor_class"]) != sp_names[T["sp"][j]]]
    r1 = lambda v: None if v is None else round(v, 1)   # the payload keeps one decimal (30 days → 0.1)
    pay_age_mis = [(nct, pull[nct]["minimum_age"], T["amin"][j]) for j, nct in enumerate(ids) if nct in pull and r1(age_years(pull[nct]["minimum_age"]) or None) != r1(T["amin"][j] or None)]
    rec("registry", "payload (data.js) phase / sponsor class / minimum age equal the Oct 5 pull (trials.csv)", f"{len(pay_ph_mis)} / {len(pay_sp_mis)} / {len(pay_age_mis)} mismatches", not (pay_ph_mis or pay_sp_mis or pay_age_mis), str((pay_ph_mis + pay_sp_mis + pay_age_mis)[:10]) if (pay_ph_mis or pay_sp_mis or pay_age_mis) else None)
    min60 = []
    STATES = {}
    with open(REF / "county_centroids.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f): STATES[r["state_name"].lower()] = r["state_fips"]
    usps_of = {}
    with open(REF / "Ruralurbancontinuumcodes2023.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f): usps_of[r["FIPS"][:2]] = r["State"]
    for j, nct in enumerate(ids):
        ps = live.get(nct)
        if not ps: continue
        s = ps["statusModule"]["overallStatus"]; st[s] += 1
        if s != "RECRUITING": not_rec.append((nct, s))
        dm = ps.get("designModule", {});
        if dm.get("studyType") != "INTERVENTIONAL" or (dm.get("designInfo") or {}).get("primaryPurpose") != "TREATMENT": not_int.append((nct, dm.get("studyType"), (dm.get("designInfo") or {}).get("primaryPurpose")))
        el = ps.get("eligibilityModule", {}); amin = age_years(el.get("minimumAge")); amax = age_years(el.get("maximumAge"))
        if amax is not None and amax < 55: age_bad.append((nct, el.get("minimumAge"), el.get("maximumAge")))   # the site's rule: accepts some adults aged 55 or older
        if amin is not None and amin >= 60: min60.append((nct, el.get("minimumAge")))
        ph = PHASE_MAP.get(tuple(dm.get("phases") or []), "?")
        if ph != ph_names[T["ph"][j]]: phase_mis.append((nct, ph, ph_names[T["ph"][j]]))
        spc = SPONSOR_MAP((ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor") or {}).get("class"))
        if spc != sp_names[T["sp"][j]]: sp_mis.append((nct, spc, sp_names[T["sp"][j]]))
        locs = set()
        for loc in (ps.get("contactsLocationsModule", {}).get("locations") or []):
            if (loc.get("country") or "") not in ("United States", ""): continue
            stf = STATES.get((loc.get("state") or "").strip().lower())
            if not stf: continue
            if loc.get("status") not in SITE_STATUS_KEEP: continue
            locs.add(((loc.get("city") or "").strip().lower(), usps_of.get(stf, ""), (loc.get("zip") or "").strip()[:5]))
        if not locs: no_us_site.append(nct)
        old = us_sites.get(nct, set()); a = len(locs - old); rm = len(old - locs); site_added += a; site_removed += rm; site_same += len(old & locs)
        if a or rm: trials_changed_sites += 1
    rec("registry", "overall status today", dict(st), None, f"{len(not_rec)} no longer Recruiting: " + ", ".join(f"{a} ({b})" for a, b in not_rec[:40]) + (" …" if len(not_rec) > 40 else ""))
    rec("registry", "still interventional with primary purpose Treatment", f"{n - len(not_int):,} of {n:,}", len(not_int) == 0, str(not_int[:10]) if not_int else None)
    rec("registry", "age limits today still admit some adults 55+ (maximum age ≥ 55 or none — the site's rule)", f"{n - len(age_bad):,} of {n:,}", len(age_bad) == 0, str(age_bad[:10]) if age_bad else None)
    rec("registry", "listed trials whose minimum age is 60 or more (open only to older adults; counted, not excluded)", f"{len(min60):,} (CHANGES_v3 of 5 Oct: 39)", len(min60) == 39, ", ".join(f"{a} ({b})" for a, b in min60[:40]))
    rec("registry", "phase today vs the payload (differences are registry edits since Oct 5)", f"{len(phase_mis)} changed", None, "(nct, live, payload): " + str(phase_mis[:12]) if phase_mis else None)
    rec("registry", "sponsor class today vs the payload", f"{len(sp_mis)} changed", None, str(sp_mis[:12]) if sp_mis else None)
    rec("registry", "US sites listed as recruiting (city, state, ZIP) vs the Oct 5 pull", f"{site_same:,} unchanged, {site_added:,} added, {site_removed:,} removed, across {trials_changed_sites:,} trials with any change", None)
    rec("registry", "listed trials with no US recruiting site today", f"{len(no_us_site):,}", None, ", ".join(no_us_site[:30]))
    would_drop = sorted(set([a for a, b in not_rec] + no_us_site + [a for a, *_ in age_bad] + [a for a, *_ in not_int]))
    rec("registry", "trials that would leave the set at a refresh today (status, sites, age or type)", f"{len(would_drop):,} of {n:,} ({100 * len(would_drop) / n:.1f}%)", None)
    # the site's own query, re-run today
    params = json.load(open(RAW / "fetch_log.json"))["params"]; p = {k: v for k, v in params.items()}; p["fields"] = "NCTId"; p["pageSize"] = 1000; p["countTotal"] = "true"
    ids_live = set(); tok = None
    while True:
        if tok: p["pageToken"] = tok
        d = api(p); ids_live.update(s["protocolSection"]["identificationModule"]["nctId"] for s in d.get("studies", [])); tok = d.get("nextPageToken")
        if not tok: break
        time.sleep(0.4)
    # baseline: the Oct 5 pull = trials kept after the oncology screen (trials.csv) plus the rows that screen excluded (out/qc_excluded_non_oncology.csv)
    kept_ids = set(pull); exc = pd.read_csv(ROOT / "out" / "qc_excluded_non_oncology.csv", dtype=str) if (ROOT / "out" / "qc_excluded_non_oncology.csv").exists() else pd.DataFrame(columns=["nct_id"])
    raw_ids = kept_ids | set(exc.nct_id); log = json.load(open(RAW / "fetch_log.json"))
    rec("registry", "Oct 5 pull reconstructed: trials.csv + screen exclusions = trials with a US recruiting site in fetch_log", f"{len(kept_ids):,} + {len(set(exc.nct_id)):,} = {len(raw_ids):,} vs {log.get('trials_with_us_recruiting_site')}", len(raw_ids) == log.get("trials_with_us_recruiting_site"))
    stale = sum(1 for _ in open(RAW / "trials_raw.csv", encoding="utf-8")) - 1 if (RAW / "trials_raw.csv").exists() else None
    rec("registry", "data/raw/trials_raw.csv row count equals the Oct 5 pull (qc_us.py refreshes it by file date, which git does not keep)", f"{stale} rows vs {log.get('trials_with_us_recruiting_site')} in fetch_log / qc_log", stale == log.get("trials_with_us_recruiting_site"), "the committed trials_raw.csv is from an earlier pull; trials.csv and every published figure are from the Oct 5 pull" if stale != log.get("trials_with_us_recruiting_site") else None)
    new_ids = sorted(ids_live - raw_ids); gone = sorted(raw_ids - ids_live)
    # what the new studies are: fetched today (US recruiting site? ages? conditions)
    newinfo = {}
    for i in range(0, len(new_ids), 100):
        d = api({"filter.ids": ",".join(new_ids[i:i + 100]), "fields": "NCTId,BriefTitle,Condition,MinimumAge,MaximumAge,LocationCountry,LocationStatus,LocationState,StartDate,StudyFirstPostDate", "pageSize": 100, "format": "json"})
        for st_ in d.get("studies", []):
            ps = st_["protocolSection"]; locs = ps.get("contactsLocationsModule", {}).get("locations") or []
            us = sum(1 for l in locs if (l.get("country") or "") in ("United States", "") and l.get("status") in SITE_STATUS_KEEP and STATES.get((l.get("state") or "").strip().lower()))
            newinfo[ps["identificationModule"]["nctId"]] = {"title": ps["identificationModule"].get("briefTitle", ""), "cond": "; ".join(ps.get("conditionsModule", {}).get("conditions", []) or []), "us_recruiting_sites": us, "amax": (ps.get("eligibilityModule") or {}).get("maximumAge"), "first_posted": (ps.get("statusModule", {}).get("studyFirstPostDateStruct") or {}).get("date")}
        time.sleep(0.3)
    with_us = [k for k, v in newinfo.items() if v["us_recruiting_sites"] > 0]
    with_us_adult = [k for k in with_us if (age_years(newinfo[k]["amax"]) is None or age_years(newinfo[k]["amax"]) >= 55)]
    posted_after = [k for k, v in newinfo.items() if (v["first_posted"] or "") > "2026-10-05"]
    rec("registry", "the site's registry query re-run today", f"{len(ids_live):,} studies (Oct 5: {log.get('api_total_count')}); not in the Oct 5 pull: {len(new_ids):,}, of which {len(with_us):,} have a US recruiting site today and {len(with_us_adult):,} of those also pass the age rule ({len(posted_after)} first posted after Oct 5); in the Oct 5 pull but no longer returned: {len(gone):,}", None,
        "gone: " + ", ".join(gone[:20]))
    rng = random.Random(seed); samp = rng.sample(with_us, min(25, len(with_us)))
    rec("registry", f"seeded sample of {len(samp)} studies that would enter at a refresh today (for review: cancer treatment trials?)", "\n    " + "\n    ".join(f"{k} | {newinfo[k]['title'][:100]} | {newinfo[k]['cond'][:100]} | US recruiting sites {newinfo[k]['us_recruiting_sites']} | max age {newinfo[k]['amax']} | posted {newinfo[k]['first_posted']}" for k in samp), None)
    return live, ids_live, raw_ids

# ---------------------------------------------------------------- 2. coverage probe ----------------------------------------------------------------
def coverage_probe(ids_live, raw_ids, D, seed, nsample=30):
    base = json.load(open(RAW / "fetch_log.json"))["params"]
    found = {}
    for label, key, cond in [("condition 'neoplasms' (MeSH tree)", "query.cond", "neoplasms"), ("condition 'oncology'", "query.cond", "oncology"), ("full text 'cancer OR tumor OR carcinoma OR lymphoma OR leukemia OR myeloma OR sarcoma OR melanoma OR malignant'", "query.term", "cancer OR tumor OR carcinoma OR lymphoma OR leukemia OR myeloma OR sarcoma OR melanoma OR malignant")]:
        p = {k: v for k, v in base.items() if k != "query.cond"}; p[key] = cond; p["fields"] = "NCTId,BriefTitle,Condition,MinimumAge,MaximumAge"; p["pageSize"] = 1000; p["countTotal"] = "true"
        got = {}; tok = None
        while True:
            if tok: p["pageToken"] = tok
            d = api(p)
            for s in d.get("studies", []):
                ps = s["protocolSection"]; got[ps["identificationModule"]["nctId"]] = (ps["identificationModule"].get("briefTitle", ""), "; ".join(ps.get("conditionsModule", {}).get("conditions", []) or []), (ps.get("eligibilityModule") or {}).get("minimumAge"), (ps.get("eligibilityModule") or {}).get("maximumAge"))
            tok = d.get("nextPageToken")
            if not tok: break
            time.sleep(0.4)
        extra = {k: v for k, v in got.items() if k not in ids_live}
        found[label] = extra
        rec("coverage", f"broader search '{label}' with the same filters", f"{len(got):,} studies; {len(extra):,} not returned by the site's keyword search", None)
    listed = set(D["T"]["id"]); pool = sorted(set().union(*[set(v) for v in found.values()]))
    rng = random.Random(seed); sample = rng.sample(pool, min(nsample, len(pool)))
    lines = []
    for k in sample:
        for v in found.values():
            if k in v: t, c, a1, a2 = v[k]; break
        lines.append(f"{k} | {t[:110]} | {c[:120]} | ages {a1}–{a2}")
    rec("coverage", f"seeded sample of {len(sample)} studies only the broader searches return (for review: are any cancer treatment trials?)", "\n    " + "\n    ".join(lines), None)
    return found

# ---------------------------------------------------------------- 3. headline recompute ----------------------------------------------------------------
def headline_recompute(D, FI, CM):
    tr = pd.read_csv(OUT / "tract_access.csv", dtype={"tract": str, "county_fips": str}, usecols=["tract", "county_fips", "pop55", "trials_within_60rdmi", "trials_within_30rdmi", "trials_within_120rdmi", "road_mi_broad", "road_mi_nci", "road_mi_lim", "trials_in_own_county"])
    w = tr.pop55.astype(float); W = w.sum()
    pct = lambda m: round(100 * w[m].sum() / W, 1)
    def wmed(c, frame=None):   # population-weighted median over tracts with a road route (the site excludes the 999 no-route sentinel)
        f = (tr if frame is None else frame); f = f[f[c] < 999]
        if not len(f) or f.pop55.sum() == 0: return float("nan")
        s = f.sort_values(c); cw = s.pop55.cumsum(); return float(s.loc[cw >= cw.iloc[-1] / 2, c].iloc[0])
    got = {"p": int(W), "l20": pct(tr.trials_within_60rdmi < 20), "z60": pct(tr.trials_within_60rdmi == 0), "l100": pct(tr.trials_within_60rdmi < 100), "zc": pct(tr.trials_in_own_county == 0),
           "g60b": pct(tr.road_mi_broad > 60), "g120b": pct(tr.road_mi_broad > 120), "g60l": pct(tr.road_mi_lim > 60), "g60n": pct(tr.road_mi_nci > 60), "g120n": pct(tr.road_mi_nci > 120),
           "nr": pct(tr.road_mi_broad >= 999), "medn": round(wmed("road_mi_nci")), "medb": round(wmed("road_mi_broad")), "t60": round(float((tr.trials_within_60rdmi * w).sum() / W)), "t30": round(float((tr.trials_within_30rdmi * w).sum() / W)), "t120": round(float((tr.trials_within_120rdmi * w).sum() / W)),
           "people_l20": int(w[tr.trials_within_60rdmi < 20].sum()), "people_z60": int(w[tr.trials_within_60rdmi == 0].sum())}
    nat = D["meta"]["nat_core"]; fn = FI["nat"]
    for k, v in got.items():
        a = nat.get(k); b = fn.get(k)
        ok = (a is None or a == v) and (b is None or b == v)
        rec("headline", f"{k}: recomputed from tracts vs data.js / findings.js", f"{v} vs {a} / {b}", ok)
    # rural / urban from the USDA file
    ru = pd.read_csv(REF / "Ruralurbancontinuumcodes2023.csv", dtype=str); ru = ru[ru.Attribute == "RUCC_2023"]; code = dict(zip(ru.FIPS, ru.Value.astype(int)))
    ru13 = pd.read_csv(REF / "ruralurbancodes2013.csv", dtype=str, encoding="latin-1") if (REF / "ruralurbancodes2013.csv").exists() else None
    tr["rucc"] = tr.county_fips.map(code)
    missing = tr.loc[tr.rucc.isna(), "county_fips"].unique()
    if ru13 is not None and len(missing):
        col = [c for c in ru13.columns if "RUCC" in c.upper()][0]; fcol = [c for c in ru13.columns if "FIPS" in c.upper()][0]
        code13 = dict(zip(ru13[fcol].str.zfill(5), pd.to_numeric(ru13[col], errors="coerce")))
        tr["rucc"] = tr.rucc.fillna(tr.county_fips.map(code13))
    # medians published for the nation, every state and every district must equal the rule used everywhere since 9 October 2026:
    # population-weighted over residents with a road route; "no route" only when no resident has one (build_rucc.py and tract_metrics_us.py agree)
    diffs = []
    fips_of = {}
    with open(REF / "Ruralurbancontinuumcodes2023.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f): fips_of[r["State"]] = r["FIPS"][:2]
    for c, lab in (("road_mi_nci", "medn"), ("road_mi_broad", "medb"), ("road_mi_lim", "medl")):
        v = wmed(c); exp = None if v != v else round(v)
        if nat.get(lab) != exp: diffs.append(f"nation {lab}: published {nat.get(lab)}, rule gives {exp}")
        for usps, g in D["state_data"].items():
            t = tr[tr.county_fips.str[:2] == fips_of.get(usps, "??")]
            if not len(t): continue
            v = wmed(c, t); exp = None if v != v else round(v)
            if g.get(lab) != exp: diffs.append(f"state {usps} {lab}: published {g.get(lab)}, rule gives {exp}")
    reld = pd.read_csv(REF / "tract_cd119.csv", dtype={"tract": str, "cd_geoid": str}); reld["share"] = reld.share.astype(float)
    md = reld.merge(tr, on="tract", how="inner"); md["pop55"] = md.pop55 * md.share
    for c, lab in (("road_mi_nci", "medn"), ("road_mi_broad", "medb"), ("road_mi_lim", "medl")):
        for cd, g in md.groupby("cd_geoid"):
            if cd not in D["districts"] or g.pop55.sum() == 0: continue
            v = wmed(c, g); exp = None if v != v else round(v)
            if D["districts"][cd].get(lab) != exp: diffs.append(f"district {cd} {lab}: published {D['districts'][cd].get(lab)}, rule gives {exp}")
    rec("headline", "medians published for the nation, 51 states and 436 districts equal the one rule (over residents with a road route) recomputed from tracts", f"{len(diffs)} differences", len(diffs) == 0, "; ".join(diffs[:20]))
    rec("headline", "counties without a 2023 rural-urban code (2013 fallback)", f"{len(missing)}: {', '.join(sorted(missing)[:12])}", None)
    metro = tr.rucc <= 3; nonm = tr.rucc >= 4
    def grp(m):
        ww = w[m]; WW = ww.sum(); t = tr[m]; med = wmed("road_mi_nci", t)
        return {"p": int(WW), "l20": round(100 * ww[t.trials_within_60rdmi < 20].sum() / WW, 1), "z60": round(100 * ww[t.trials_within_60rdmi == 0].sum() / WW, 1), "g60n": round(100 * ww[t.road_mi_nci > 60].sum() / WW, 1), "g60b": round(100 * ww[t.road_mi_broad > 60].sum() / WW, 1), "medn": round(med)}
    gm, gn = grp(metro), grp(nonm); R = FI["rural"]
    for g, name in ((gm, "metro"), (gn, "nonmetro")):
        for k, v in g.items(): rec("headline", f"{name} {k}: recomputed vs findings.js", f"{v} vs {R[name].get(k)}", R[name].get(k) == v)
    rec("headline", "nonmetro share of residents 55+", f"{100 * gn['p'] / (gm['p'] + gn['p']):.1f}% (README says 16.0%)", abs(100 * gn['p'] / (gm['p'] + gn['p']) - 16.0) < 0.05)
    # counties and states from county_metrics
    cm = CM; broad = int((cm.trials_in_county >= 100).sum()); lim = int((cm.trials_in_county >= 20).sum()); anyt = int((cm.trials_in_county > 0).sum())
    st_of = cm.county_fips.str[:2]; st_broad = cm[cm.trials_in_county >= 100].county_fips.str[:2].unique(); usps = {}
    with open(REF / "Ruralurbancontinuumcodes2023.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f): usps[r["FIPS"][:2]] = r["State"]
    no_broad = sorted({usps.get(s, s) for s in st_of.unique()} - {usps.get(s, s) for s in st_broad})
    rec("headline", "broad-menu counties (100+), 20+ counties, counties with any trial", f"{broad}, {lim}, {anyt} (README: 83, 377; metrics_log: 838 with any)", broad == 83 and lim == 377)
    CMJ = load_js(DOCS / "community.js", None); names = {k: v["name"] for k, v in CMJ["states"].items()}
    rec("headline", "states with no broad-menu county", f"{len(no_broad)}: {', '.join(no_broad)} (findings.js: {FI.get('states_no_broad')})", len(no_broad) == FI.get("states_no_broad") and {names.get(x, x) for x in no_broad} == set(FI.get("states_no_broad_list", [])))
    # districts where every resident 55+ is beyond 60 road-miles of a broad menu
    rel = pd.read_csv(REF / "tract_cd119.csv", dtype={"tract": str, "cd_geoid": str}); rel["share"] = rel.share.astype(float)
    m = rel.merge(tr, on="tract", how="inner"); m["w"] = m.pop55 * m.share; m["far"] = m.w * (m.road_mi_broad > 60)
    g = m.groupby("cd_geoid").agg(w=("w", "sum"), far=("far", "sum")); g = g[g.w > 0]; n73 = int((g.far / g.w >= 0.9995).sum())
    rec("headline", "districts where every resident 55+ is beyond 60 road-miles of a broad menu", f"{n73} (README: 73)", n73 == 73)
    # README headline block
    readme = (ROOT / "README.md").read_text(encoding="utf-8"); blk = readme[readme.index("headline:start"):readme.index("headline:end")]
    want = {f"{got['l20']}% of Americans": True, f"{got['z60']}% have none": True, f"{got['g60b']}% live more than 60 road-miles": True, f"{got['g60n']}% live more than 60 road-miles from an NCI": True, f"median resident 55+ is {got['medn']} road-miles": True, f"{gn['l20']}% of residents 55+ in nonmetro": True, f"vs {gm['l20']}% in metro": True}
    miss = [k for k in want if k not in blk]
    rec("headline", "README headline block carries the recomputed figures", "all present" if not miss else f"missing: {miss}", not miss)
    return got, tr

# ---------------------------------------------------------------- 4. road distance constraints ----------------------------------------------------------------
def road_constraints(D):
    rd = pd.read_csv(OUT / "county_road_distances.csv", dtype={"county_fips": str})
    nci = {n["full"]: (n["lat"], n["lon"]) for n in D["nci"]}
    cm = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str})
    rd = rd.merge(cm[["county_fips", "lat", "lon"]], on="county_fips", how="left")
    ok = rd.road_mi_nci < 999
    sl = [miles((r.lat, r.lon), nci[r.nearest_nci]) if r.nearest_nci in nci else np.nan for r in rd.itertuples()]
    rd["sl_nci"] = sl; sub = rd[ok & rd.sl_nci.notna() & (rd.sl_nci > 3)]
    ratio = sub.road_mi_nci / sub.sl_nci
    short = sub[ratio < 0.97]
    rec("roads", "county → nearest NCI center: road miles shorter than straight-line (impossible; 3% tolerance for rounding/centroids)", f"{len(short)} of {len(sub):,} counties", len(short) == 0, str(short[["county_fips", "county_name", "nearest_nci", "road_mi_nci", "sl_nci"]].head(12).to_dict("records")) if len(short) else None)
    rec("roads", "road / straight-line ratio to the nearest NCI center", f"median {ratio.median():.2f}, p10 {ratio.quantile(.1):.2f}, p90 {ratio.quantile(.9):.2f}, max {ratio.max():.2f}", None, f"{int((ratio > 2.5).sum())} counties above 2.5: " + ", ".join(sub.loc[ratio > 2.5, "county_name"].head(10)))
    okb = rd.road_mi_broad < 999; slb = rd.straightline_x1_2_broad / 1.2; subb = rd[okb & (slb > 3)]; rb = subb.road_mi_broad / (subb.straightline_x1_2_broad / 1.2)
    rec("roads", "county → nearest broad menu: road miles shorter than straight-line", f"{int((rb < 0.97).sum())} of {len(subb):,}", int((rb < 0.97).sum()) == 0, str(subb.loc[rb < 0.97, ["county_fips", "county_name", "nearest_broad", "road_mi_broad", "straightline_x1_2_broad"]].head(12).to_dict("records")) if (rb < 0.97).any() else None)
    rec("roads", "road / straight-line ratio to the nearest broad menu", f"median {rb.median():.2f}, p10 {rb.quantile(.1):.2f}, p90 {rb.quantile(.9):.2f} (README: median 1.18, 1.09–1.34)", abs(rb.median() - 1.18) < 0.02)
    noroad = rd[rd.road_mi_broad >= 999]
    rec("roads", "counties with no road route to a broad menu", f"{len(noroad)}: " + ", ".join(sorted(set(noroad.state_fips.astype(str)))), None, "states (FIPS): " + ", ".join(sorted(set(noroad.state_fips.astype(str).str.zfill(2)))))

# ---------------------------------------------------------------- 5. site locations ----------------------------------------------------------------
def point_in_poly(pt, poly):
    x, y = pt[1], pt[0]; inside = False
    for ring_i, ring in enumerate(poly):
        n = len(ring); j = n - 1; hit = False
        for i in range(n):
            xi, yi = ring[i]; xj, yj = ring[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi): hit = not hit
            j = i
        if ring_i == 0: inside = hit
        elif hit: inside = False
    return inside

def site_locations(D, GEO, F, seed, nsample):
    qc = pd.read_csv(OUT / "site_assignment_qc.csv", dtype=str).fillna("")
    qc = qc[qc.county_fips != ""]; rng = random.Random(seed); idx = rng.sample(range(len(qc)), min(nsample, len(qc))); s = qc.iloc[idx]
    polys = {}
    for f in GEO["counties"]["features"]:
        g = f["geometry"]; polys[f["properties"]["id"]] = g["coordinates"] if g["type"] == "Polygon" else None
        if g["type"] == "MultiPolygon": polys[f["properties"]["id"]] = g["coordinates"]
    def inside(fips, pt):
        p = polys.get(fips)
        if p is None: return None
        if p and isinstance(p[0][0][0], (int, float)): return point_in_poly(pt, p)
        return any(point_in_poly(pt, q) for q in p)
    gaz = defaultdict(list)   # a name can occur more than once in a state (Plantation, FL is a city in Broward and a CDP in Sarasota): keep every match
    with open(REF / "gazetteer_places.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f): gaz[(r["state"], r["place"])].append((float(r["lat"]), float(r["lon"])))
    cm = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str}).set_index("county_fips")
    out_poly = []; far_city = []; no_zcta = 0; checked = 0; city_checked = 0
    for r in s.itertuples():
        z = F["zcta"].get(r.zip[:5]) if r.zip else None
        cands = gaz.get((r.state, re.sub(r"[^a-z]", "", r.city.lower()))) or gaz.get((r.state, r.city.lower())) or []
        if r.assign_method in ("city_gazetteer", "zip_typo_corrected"):   # the pipeline set the ZIP aside (wrong state, or a typing error): judge the city instead
            c = cm.loc[r.county_fips] if r.county_fips in cm.index else None
            g = min(cands, key=lambda q: miles(q, (c.lat, c.lon))) if (cands and c is not None) else None
            if g is None: no_zcta += 1; continue
            checked += 1
            if not inside(r.county_fips, g) and miles(g, (c.lat, c.lon)) >= 6: out_poly.append((r.nct_id, r.facility[:40], r.city, r.state, r.zip, r.county_fips, r.assign_method, "city point", round(miles(g, (c.lat, c.lon)))))
            continue
        if not z: no_zcta += 1; continue
        pt = (z[0], z[1]); checked += 1
        ins = inside(r.county_fips, pt)
        if ins is False:
            c = cm.loc[r.county_fips] if r.county_fips in cm.index else None
            d = miles(pt, (c.lat, c.lon)) if c is not None else None
            # simplified polygons: accept a point that is within 6 miles of the assigned county's population center or whose ZCTA's own county (Census) matches
            if z[2] != r.county_fips and not (d is not None and d < 6): out_poly.append((r.nct_id, r.facility[:40], r.city, r.state, r.zip, r.county_fips, r.assign_method, z[2], round(d or -1)))
        if cands:
            city_checked += 1; d = min(miles(pt, g) for g in cands)
            if d > 40: far_city.append((r.nct_id, r.facility[:40], r.city, r.state, r.zip, round(d), r.assign_method))
    rec("sites", f"sampled site rows whose ZIP center lies in the assigned county (or the Census ZCTA→county agrees)", f"{checked - len(out_poly)} of {checked} ({no_zcta} rows without a ZCTA center skipped)", len(out_poly) == 0, "outside: " + str(out_poly[:10]) if out_poly else None)
    rec("sites", "sampled site rows whose ZIP center is within 40 miles of the registry's stated city", f"{city_checked - len(far_city)} of {city_checked} with a gazetteer match", len(far_city) == 0, "far: " + str(far_city[:10]) if far_city else None)

# ---------------------------------------------------------------- 6. ZIP finder ----------------------------------------------------------------
def zip_finder(D, F, tr, seed, nzips, port, browser):
    T = D["T"]; SP = D["SP"]; rng = random.Random(seed)
    zc = [z for z in F["zcta"] if F["zcta"][z][2]]; sample = rng.sample(zc, nzips)
    cty = tr.groupby("county_fips").apply(lambda g: float((g.trials_within_60rdmi * g.pop55).sum() / max(g.pop55.sum(), 1)))
    rows = []
    for z in sample:
        zz = F["zcta"][z]; near = [(s, math.floor(miles((zz[0], zz[1]), (p[0], p[1])) * F["meta"]["road_factor"] + 0.5)) for s, p in enumerate(F["sp"])]
        near = [(s, mi) for s, mi in near if mi <= 60]
        trials = set();
        for s, mi in near: trials.update(SP[s])
        rows.append({"zip": z, "county": zz[2], "python": len(trials), "county_road_t60": round(float(cty.get(zz[2], float("nan"))), 1)})
    if browser:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            for r in rows:
                pg.goto(f"http://localhost:{port}/find.html?zip={r['zip']}", wait_until="networkidle"); pg.wait_for_timeout(600)
                try:
                    pg.fill("#zip", r["zip"]); pg.click("button.btn[type=submit], form.f .btn"); pg.wait_for_timeout(900)
                except Exception: pass
                txt = pg.inner_text("#out") if pg.locator("#out").count() else pg.inner_text("body")
                m = re.search(r"([\d,]+) recruiting .*?trial", txt); r["page"] = int(m.group(1).replace(",", "")) if m else ("none" if "No matching" in txt else None)
            b.close()
        bad = [r for r in rows if r["page"] not in (r["python"], ("none" if r["python"] == 0 else r["python"]))]
        rec("zipfinder", f"find.html result equals the method recomputed in Python for {len(rows)} ZIP codes", f"{len(rows) - len(bad)} of {len(rows)} agree", len(bad) == 0, str(bad[:10]) if bad else None)
    ratio = [r["python"] / r["county_road_t60"] for r in rows if r["county_road_t60"] and r["county_road_t60"] > 0]
    rec("zipfinder", "ZIP estimate (straight-line × 1.2) vs the county's road-network trials-within-60 (informational; different methods)", f"ratio median {np.median(ratio):.2f}, p10 {np.quantile(ratio, .1):.2f}, p90 {np.quantile(ratio, .9):.2f} over {len(ratio)} ZIPs" if ratio else "n/a", None, "; ".join(f"{r['zip']}:{r['python']}/{r['county_road_t60']}" for r in rows[:12]))
    return rows

# ---------------------------------------------------------------- 7. cross-page agreement ----------------------------------------------------------------
def cross_page(D, CO, FI, tr, seed, port, ncounty=8, ndist=3, nstate=2):
    from playwright.sync_api import sync_playwright
    rng = random.Random(seed); cnt = D["counties"]; keys = [k for k in cnt if cnt[k]["p"] > 0]
    sample_c = rng.sample(keys, ncounty); sample_d = rng.sample(list(D["districts"].keys()), ndist); sample_s = rng.sample([s for s in D["state_data"]], nstate)
    cty_l20 = tr.groupby("county_fips").apply(lambda g: round(100 * float(g.loc[g.trials_within_60rdmi < 20, "pop55"].sum() / max(g.pop55.sum(), 1)), 1))
    rd = pd.read_csv(OUT / "county_road_distances.csv", dtype={"county_fips": str}).set_index("county_fips")
    rel = pd.read_csv(REF / "tract_cd119.csv", dtype={"tract": str, "cd_geoid": str}); rel["share"] = rel.share.astype(float)
    mm = rel.merge(tr, on="tract", how="inner"); mm["w"] = mm.pop55 * mm.share; mm["short"] = mm.w * (mm.trials_within_60rdmi < 20)
    gd = mm.groupby("cd_geoid").agg(w=("w", "sum"), s=("short", "sum")); dist_l20 = (100 * gd.s / gd.w).round(1)
    st = tr.assign(st=tr.county_fips.str[:2], short=tr.pop55 * (tr.trials_within_60rdmi < 20)).groupby("st").agg(w=("pop55", "sum"), s=("short", "sum")); state_l20 = (100 * st.s / st.w).round(1)
    fips_of = {}
    with open(REF / "Ruralurbancontinuumcodes2023.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f): fips_of[r["State"]] = r["FIPS"][:2]
    cm = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str}).set_index("county_fips")
    pct_re = re.compile(r"(\d{1,3}\.\d)\s*%")
    def grab(pg, url, sel):
        pg.goto(f"http://localhost:{port}/{url}", wait_until="networkidle"); pg.wait_for_timeout(1500)
        return pg.inner_text(sel) if pg.locator(sel).count() else pg.inner_text("body")
    mism = []; checked = 0
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1440, "height": 900})
        for k in sample_c:
            exp = {"l20": float(cty_l20.get(k, float("nan"))), "t": int(cm.loc[k, "trials_in_county"]), "rn": rd.loc[k, "road_mi_nci"]}
            got = {}
            t = grab(pg, f"index.html?c={k}", "#pane"); m = re.search(r"(\d{1,3}\.\d)\s*%\s*of residents 55\+ in the county", t); got["index.l20"] = float(m.group(1)) if m else None
            m = re.search(r"(\d[\d,]*)\s*trials?\s*with a recruiting site in the county", t); got["index.t"] = int(m.group(1).replace(",", "")) if m else None
            m = re.search(r"(\d[\d,]*)\s*road-miles\s*from the county population center to the nearest NCI", t); got["index.rn"] = int(m.group(1).replace(",", "")) if m else None
            t = grab(pg, f"community.html?c={k}", "main"); m = re.search(r"(\d{1,3}\.\d)\s*%\s*of residents 55 and older in", t); got["community.l20"] = float(m.group(1)) if m else None
            m = re.search(r"(\d[\d,]*)\s*trials?\s*(?:has|have|No listed trial has) a recruiting site in the county", t); got["community.t"] = int(m.group(1).replace(",", "")) if m else None
            m = re.search(r"(\d[\d,]*)\s*road-miles\s*from the county.s population center to the nearest NCI", t); got["community.rn"] = int(m.group(1).replace(",", "")) if m else None
            t = grab(pg, f"brief.html?c={k}", "body")   # the county brief carries the trial count and the NCI distance, not the share
            m = re.search(r"(\d[\d,]*)\s*recruiting trials?\s*with a site in the county", t); got["brief.t"] = int(m.group(1).replace(",", "")) if m else None
            m = re.search(r"(\d[\d,]*)\s*road-mi\s*to the nearest NCI", t); got["brief.rn"] = int(m.group(1).replace(",", "")) if m else None
            t = grab(pg, f"act.html?c={k}", "main"); m = re.search(r"(\d{1,3}\.\d)\s*%\s*of residents 55", t); got["act.l20"] = float(m.group(1)) if m else None
            checked += 1
            for key, v in got.items():
                base = key.split(".")[1]; e = exp[base]
                if v is None: mism.append((k, key, "not found on page", e)); continue
                tol = 0.051 if base == "l20" else 0.5
                if not (abs(v - e) <= tol): mism.append((k, key, v, e))
        for k in sample_d:
            t = grab(pg, f"index.html?d={k}", "#pane"); m = re.search(r"(\d{1,3}\.\d)\s*%\s*of residents 55\+ have fewer than 20", t); a = float(m.group(1)) if m else None
            t2 = grab(pg, f"community.html?d={k}", "main"); m = re.search(r"(\d{1,3}\.\d)\s*%\s*of residents 55 and older in", t2); bb = float(m.group(1)) if m else None
            t3 = grab(pg, f"brief.html?d={k}", "body"); m = re.search(r"(\d{1,3}\.\d)\s*%\s*of residents 55\+ have fewer than 20", t3); c = float(m.group(1)) if m else None
            e = float(dist_l20.get(k, float("nan"))); checked += 1
            for name, v in (("index", a), ("community", bb), ("brief", c)):
                if v is None or e is None or abs(v - e) > 0.051: mism.append((k, name + ".l20", v, e))
        for k in sample_s:
            t = grab(pg, f"index.html?s={k}", "#pane"); m = re.search(r"(\d{1,3}\.\d)\s*%\s*of residents 55\+ have fewer than 20", t); a = float(m.group(1)) if m else None
            t2 = grab(pg, f"community.html?s={k}", "main"); m = re.search(r"(\d{1,3}\.\d)\s*%\s*of residents 55 and older in", t2); bb = float(m.group(1)) if m else None
            t3 = grab(pg, f"brief.html?s={k}", "body"); m = re.search(r"(\d{1,3}\.\d)\s*%\s*of residents 55\+ have fewer than 20", t3); c = float(m.group(1)) if m else None
            e = float(state_l20.get(fips_of.get(k), float("nan"))); checked += 1
            for name, v in (("index", a), ("community", bb), ("brief", c)):
                if v is None or e is None or abs(v - e) > 0.051: mism.append((k, name + ".l20", v, e))
        b.close()
    rec("pages", f"figures agree across index / community / brief / act and with the tract recomputation ({ncounty} counties, {ndist} districts, {nstate} states: {', '.join(sample_c + sample_d + sample_s)})", f"{checked} places; {len(mism)} disagreements", len(mism) == 0, str(mism[:20]) if mism else None)

# ---------------------------------------------------------------- 8. page health ----------------------------------------------------------------
def page_health(port):
    from playwright.sync_api import sync_playwright
    axe = None
    for cand in [ROOT / "node_modules/axe-core/axe.min.js", Path("/tmp/claude-0/-home-claude/899c4b1b-0618-5030-972f-7bffc89832ff/scratchpad/node_modules/axe-core/axe.min.js"), Path("/tmp/claude-0/-home-claude-cancer-trial-access-fullmap/899c4b1b-0618-5030-972f-7bffc89832ff/scratchpad/node_modules/axe-core/axe.min.js")]:
        if cand.exists(): axe = cand.read_text(); break
    pages = ["index.html", "findings.html", "community.html", "learn.html", "find.html", "act.html", "brief.html?s=KY", "trials.html?county=48215", "community.html?c=21227", "act.html?c=21227", "index.html?u=district&m=cos_ctma_hr", "index.html?c=48215", "index.html?s=KY&rural=1&guide=rural-urban"]
    errs_all = {}; viol = 0; hs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for vp, mob in (((1440, 900), False), ((390, 844), True)):
            ctx = b.new_context(viewport={"width": vp[0], "height": vp[1]}, is_mobile=mob, has_touch=mob)
            for u in pages:
                pg = ctx.new_page(); errs = []
                pg.on("pageerror", lambda ex, e=errs: e.append("pageerror: " + str(ex)))
                pg.on("console", lambda m, e=errs: e.append(m.text) if m.type == "error" and "cdnjs" not in m.text and "TUNNEL" not in m.text and "ERR_" not in m.text else None)
                pg.goto(f"http://localhost:{port}/{u}", wait_until="networkidle"); pg.wait_for_timeout(1500)
                sw = pg.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
                if sw[0] > sw[1]: hs.append((vp[0], u, sw))
                if axe:
                    pg.add_script_tag(content=axe)
                    v = pg.evaluate("axe.run(document,{runOnly:['wcag2a','wcag2aa']}).then(r=>r.violations.map(v=>[v.id,v.impact,v.nodes.length,v.nodes.slice(0,2).map(n=>n.target.join(' '))]))")
                    if v: viol += len(v); errs_all[f"axe {vp[0]} {u}"] = v
                if errs: errs_all[f"{vp[0]} {u}"] = errs[:5]
                pg.close()
            ctx.close()
        b.close()
    rec("health", f"{len(pages)} pages × 2 sizes: JavaScript errors", f"{sum(1 for k in errs_all if not k.startswith('axe'))} pages with errors", not any(not k.startswith("axe") for k in errs_all), str({k: v for k, v in errs_all.items() if not k.startswith("axe")}) if errs_all else None)
    rec("health", "horizontal overflow", f"{len(hs)} pages", len(hs) == 0, str(hs) if hs else None)
    rec("health", "axe-core WCAG 2 A/AA violations", f"{viol}", viol == 0 if axe else None, str({k: v for k, v in errs_all.items() if k.startswith("axe")}) if viol else None)

# ---------------------------------------------------------------- cosponsors (payload consistency) ----------------------------------------------------------------
def cosponsor_consistency(CO, FI):
    b = CO["bills"]
    for k in b:
        roles = Counter(bills[k]["role"] for m, bills in CO["by_member"].items() if k in bills)
        n = sum(v for r, v in roles.items() if r != "sponsor"); parties = Counter(CO["members"][m]["party"] for m, bills in CO["by_member"].items() if k in bills and bills[k]["role"] != "sponsor")
        fb = next((x for x in FI.get("bills", []) if x.get("key") == k), {})
        ok = fb.get("n_cosponsors") == n and all(fb.get("parties", {}).get(pp, 0) == parties.get(pp, 0) for pp in ("R", "D", "I"))
        rec("cosponsors", f"{b[k]['label']}: cosponsors in cosponsors.js vs findings.js", f"{n} ({dict(parties)}) vs {fb.get('n_cosponsors')} ({fb.get('parties')}); roles {dict(roles)}", ok, f"fetched {CO['meta'].get('fetched')} from {CO['meta'].get('source')}")

def run(args):
    port = args.port
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port)], cwd=DOCS, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) if not args.no_browser else None
    try:
        D = load_js(DOCS / "data.js", "window.DATA="); FI = load_js(DOCS / "findings.js", "window.FINDINGS="); CO = load_js(DOCS / "cosponsors.js", "window.COSPONSORS=")
        F = load_js(DOCS / "find_data.js", "window.FIND="); GEO = load_js(DOCS / "geo.js", "window.GEO="); CM = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str})
        rec("setup", "seed / data date", f"seed {args.seed}; registry data {D['meta']['registry_data_timestamp']}; run {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", None)
        n_raw = sum(1 for _ in open(RAW / "trials.csv", encoding="utf-8")) - 1
        mx = pd.to_numeric(pd.read_csv(RAW / "trials.csv", usecols=["max_age_years"]).max_age_years, errors="coerce")
        rec("setup", "trials.csv rows minus those with a maximum age under 55 equals the listed set", f"{n_raw} − {int((mx < 55).sum())} = {n_raw - int((mx < 55).sum())} vs {len(D['T']['id'])}", n_raw - int((mx < 55).sum()) == len(D["T"]["id"]))
        if not args.skip_registry:
            live, ids_live, raw_ids = live_registry(D, args.seed)
            coverage_probe(ids_live, raw_ids, D, args.seed)
        got, tr = headline_recompute(D, FI, CM)
        road_constraints(D)
        site_locations(D, GEO, F, args.seed, args.sites)
        cosponsor_consistency(CO, FI)
        if not args.no_browser:
            time.sleep(1.0)
            zip_finder(D, F, tr, args.seed, args.zips, port, True)
            cross_page(D, CO, FI, tr, args.seed, port)
            page_health(port)
        else:
            zip_finder(D, F, tr, args.seed, args.zips, port, False)
    finally:
        if srv: srv.terminate()
    out = Path(args.out or (OUT / f"validation_outside_pass{args.seed}.json")); out.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    fails = [(s, r["check"]) for s, rs in results.items() for r in rs if r["ok"] is False]
    print(f"\nwrote {out}; {sum(len(v) for v in results.values())} checks, {len(fails)} failed" + (": " + "; ".join(f"{s} · {c}" for s, c in fails) if fails else ""))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=1); ap.add_argument("--out"); ap.add_argument("--no-browser", action="store_true"); ap.add_argument("--skip-registry", action="store_true")
    ap.add_argument("--sites", type=int, default=150); ap.add_argument("--zips", type=int, default=30); ap.add_argument("--port", type=int, default=8791)
    run(ap.parse_args())
