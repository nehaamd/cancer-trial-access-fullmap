"""Outside validation of the published figures, independent of the build scripts.

What it checks (each pass; sampled checks use --seed so that repeated passes draw different samples):
  1. Live registry: every listed trial in data.js is looked up on ClinicalTrials.gov today (API v2, batches of 100) and compared
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
Expected values are read from the files of the build under test (data/raw/fetch_log.json for the pull's dates and counts,
out_adult55/metrics_log.json, findings.js and the README's headline block for the published counts), never typed in, so a pass
on a later refresh compares that refresh's own figures.
Usage: python3 validate_outside.py --seed 1 [--out out_adult55/validation_outside_pass1.json] [--no-browser] [--skip-registry] [--sites 150] [--zips 30]
       [--port 8103] [--axe path/to/axe.min.js]
Needs: pandas, numpy, playwright (for 6-8), network access to clinicaltrials.gov, and a local server for docs/ (started by the script on
127.0.0.1:--port, or on a free port if that one is taken; the script checks that the server it reads is serving this checkout's docs/).
axe-core is looked for at --axe, $AXE_CORE_JS, then node_modules/axe-core/axe.min.js; without it the accessibility check is skipped (INFO).
"""
import argparse, csv, json, math, os, random, re, socket, subprocess, sys, time, urllib.parse, urllib.request
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; DOCS = ROOT / "docs"; OUT = ROOT / "out_adult55"; REF = ROOT / "data" / "ref"; RAW = ROOT / "data" / "raw"
API = "https://clinicaltrials.gov/api/v2/studies"
PAUSE = 0.6   # seconds between registry requests (another reviewer may be querying the registry at the same time)
R_EARTH = 3958.8
results = {}; notes = []
HOST = "127.0.0.1"; BASE = None   # set in run(): http://127.0.0.1:<port>
# the pull under test: its registry data date (ClinicalTrials.gov's snapshot) and the day it was fetched, from its own log
FETCH_LOG = json.loads((RAW / "fetch_log.json").read_text(encoding="utf-8"))
REG_DATE = FETCH_LOG["registry_data_timestamp"][:10]; FETCH_DATE = FETCH_LOG["timestamp_utc"][:10]
PULL = f"the pull (registry data of {REG_DATE}, fetched {FETCH_DATE})"

def readme_num(pattern, cast=float):
    """A number the README's headline block (rewritten by build_readme.py at every refresh) states; None if the sentence is gone."""
    s = (ROOT / "README.md").read_text(encoding="utf-8"); blk = s[s.index("headline:start"):s.index("headline:end")]
    m = re.search(pattern, blk)
    return None if not m else tuple(cast(g.replace(",", "")) for g in m.groups()) if len(m.groups()) > 1 else cast(m.group(1).replace(",", ""))
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
    # which registry snapshot answers today: ClinicalTrials.gov publishes a data timestamp. If it is the pull's own, every "today vs the
    # pull" comparison below re-reads the pull's snapshot (a reproduction of the pull), not drift since it.
    try:
        with urllib.request.urlopen(API.rsplit("/", 1)[0] + "/version", timeout=60) as r: ver = json.loads(r.read())
    except Exception as e: ver = {"dataTimestamp": f"unavailable ({type(e).__name__})"}
    same = ver.get("dataTimestamp") == FETCH_LOG["registry_data_timestamp"]
    rec("registry", "registry data the API serves today vs the pull's", f"{ver.get('dataTimestamp')} vs {FETCH_LOG['registry_data_timestamp']} (API {ver.get('apiVersion')})", None,
        "same snapshot: the checks below reproduce the pull from the registry, and drift since the pull is not measured" if same else "a later snapshot: differences below are registry changes since the pull (or errors in the pull)")
    fields = "NCTId,BriefTitle,OverallStatus,StudyType,DesignPrimaryPurpose,MinimumAge,MaximumAge,Phase,LeadSponsorClass,LastUpdatePostDate,LocationCity,LocationState,LocationZip,LocationCountry,LocationStatus,LocationFacility,Condition"
    live = {}
    for i in range(0, n, 100):
        batch = ids[i:i + 100]
        d = api({"filter.ids": ",".join(batch), "fields": fields, "pageSize": 100, "format": "json"})
        for s in d.get("studies", []):
            ps = s["protocolSection"]; live[ps["identificationModule"]["nctId"]] = ps
        time.sleep(PAUSE)
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
    rec("registry", f"payload (data.js) phase / sponsor class / minimum age equal {PULL} (trials.csv)", f"{len(pay_ph_mis)} / {len(pay_sp_mis)} / {len(pay_age_mis)} mismatches", not (pay_ph_mis or pay_sp_mis or pay_age_mis), str((pay_ph_mis + pay_sp_mis + pay_age_mis)[:10]) if (pay_ph_mis or pay_sp_mis or pay_age_mis) else None)
    min60 = []; upd = {}
    STATES = {}
    with open(REF / "county_centroids.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f): STATES[r["state_name"].lower()] = r["state_fips"]
    usps_of = {}
    with open(REF / "Ruralurbancontinuumcodes2023.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f): usps_of[r["FIPS"][:2]] = r["State"]
    for j, nct in enumerate(ids):
        ps = live.get(nct)
        if not ps: continue
        s = ps["statusModule"]["overallStatus"]; st[s] += 1; upd[nct] = (ps["statusModule"].get("lastUpdatePostDateStruct") or {}).get("date", "")
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
    # the payload's own count (data.js minimum age >= 60) against today's registry; a difference is drift only if the registry record
    # was updated on or after the registry data date (otherwise the payload disagrees with the record it was built from)
    pay60 = {nct for j, nct in enumerate(ids) if T["amin"][j] is not None and T["amin"][j] >= 60}; live60 = {a for a, b in min60}; d60 = sorted(pay60 ^ live60)
    expl60 = all(upd.get(x, "") >= REG_DATE for x in d60)
    rec("registry", "listed trials whose minimum age is 60 or more (open only to older adults; counted, not excluded): today vs the payload", f"{len(live60):,} today; {len(pay60):,} in the payload ({PULL})", True if not d60 else None if expl60 else False,
        (("differ (nct, in payload, minimum age today, last update posted): " + str([(x, x in pay60, next((b for a, b in min60 if a == x), None), upd.get(x)) for x in d60]) + (" — all updated on or after " + REG_DATE if expl60 else " — NOT explained by a registry update") + "; ") if d60 else "") + ", ".join(f"{a} ({b})" for a, b in min60[:60]))
    rec("registry", f"phase today vs the payload (differences are registry edits since {REG_DATE})", f"{len(phase_mis)} changed", None, "(nct, live, payload, last update posted): " + str([(a, b, c, upd.get(a)) for a, b, c in phase_mis[:12]]) if phase_mis else None)
    rec("registry", "sponsor class today vs the payload", f"{len(sp_mis)} changed", None, str([(a, b, c, upd.get(a)) for a, b, c in sp_mis[:12]]) if sp_mis else None)
    rec("registry", f"US sites listed as recruiting (city, state, ZIP) vs {PULL}", f"{site_same:,} unchanged, {site_added:,} added, {site_removed:,} removed, across {trials_changed_sites:,} trials with any change", None)
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
        time.sleep(PAUSE)
    # baseline: the pull = trials kept after the oncology screen (trials.csv) plus the rows that screen excluded (out/qc_excluded_non_oncology.csv)
    kept_ids = set(pull); exc = pd.read_csv(ROOT / "out" / "qc_excluded_non_oncology.csv", dtype=str) if (ROOT / "out" / "qc_excluded_non_oncology.csv").exists() else pd.DataFrame(columns=["nct_id"])
    raw_ids = kept_ids | set(exc.nct_id); log = FETCH_LOG
    rec("registry", "the pull reconstructed: trials.csv + screen exclusions = trials with a US recruiting site in fetch_log", f"{len(kept_ids):,} + {len(set(exc.nct_id)):,} = {len(raw_ids):,} vs {log.get('trials_with_us_recruiting_site')}", len(raw_ids) == log.get("trials_with_us_recruiting_site"))
    # the committed raw copy: qc_us.py rewrites it from a fresh pull (decided by content since 10 Oct 2026), but only on the machine that ran the pull
    raw_rows = list(csv.DictReader(open(RAW / "trials_raw.csv", newline="", encoding="utf-8"))) if (RAW / "trials_raw.csv").exists() else None
    stale = None if raw_rows is None else len(raw_rows); raw_upd = max((r.get("last_update_posted") or "" for r in raw_rows), default="") if raw_rows else ""
    rec("registry", f"data/raw/trials_raw.csv (the committed copy of the raw pull) has the row count of {PULL}", f"{stale} rows vs {log.get('trials_with_us_recruiting_site')} in fetch_log / qc_log", stale == log.get("trials_with_us_recruiting_site"), f"the committed trials_raw.csv is from an earlier pull (latest registry update in it: {raw_upd}); trials.csv and every published figure are from {PULL}" if stale != log.get("trials_with_us_recruiting_site") else None)
    new_ids = sorted(ids_live - raw_ids); gone = sorted(raw_ids - ids_live)
    # what the new studies are: fetched today (US recruiting site? ages? conditions)
    newinfo = {}
    for i in range(0, len(new_ids), 100):
        d = api({"filter.ids": ",".join(new_ids[i:i + 100]), "fields": "NCTId,BriefTitle,Condition,MinimumAge,MaximumAge,LocationCountry,LocationStatus,LocationState,StartDate,StudyFirstPostDate", "pageSize": 100, "format": "json"})
        for st_ in d.get("studies", []):
            ps = st_["protocolSection"]; locs = ps.get("contactsLocationsModule", {}).get("locations") or []
            us = sum(1 for l in locs if (l.get("country") or "") in ("United States", "") and l.get("status") in SITE_STATUS_KEEP and STATES.get((l.get("state") or "").strip().lower()))
            newinfo[ps["identificationModule"]["nctId"]] = {"title": ps["identificationModule"].get("briefTitle", ""), "cond": "; ".join(ps.get("conditionsModule", {}).get("conditions", []) or []), "us_recruiting_sites": us, "amax": (ps.get("eligibilityModule") or {}).get("maximumAge"), "first_posted": (ps.get("statusModule", {}).get("studyFirstPostDateStruct") or {}).get("date")}
        time.sleep(PAUSE)
    with_us = [k for k, v in newinfo.items() if v["us_recruiting_sites"] > 0]
    with_us_adult = [k for k in with_us if (age_years(newinfo[k]["amax"]) is None or age_years(newinfo[k]["amax"]) >= 55)]
    posted_after = [k for k in with_us_adult if (newinfo[k]["first_posted"] or "") > REG_DATE]
    rec("registry", "the site's registry query re-run today", f"{len(ids_live):,} studies (the pull: {log.get('api_total_count')}); not in the pull: {len(new_ids):,}, of which {len(with_us):,} have a US recruiting site today and {len(with_us_adult):,} of those also pass the age rule ({len(posted_after)} of those first posted after {REG_DATE}); in the pull but no longer returned: {len(gone):,}", None,
        "gone: " + ", ".join(gone[:40]) + "; would enter (US recruiting site, age rule): " + ", ".join(sorted(with_us_adult)[:60]))
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
            time.sleep(PAUSE)
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
           "nr": pct(tr.road_mi_broad >= 999), "nrn": pct(tr.road_mi_nci >= 999), "medn": round(wmed("road_mi_nci")), "medb": round(wmed("road_mi_broad")), "t60": round(float((tr.trials_within_60rdmi * w).sum() / W)), "t30": round(float((tr.trials_within_30rdmi * w).sum() / W)), "t120": round(float((tr.trials_within_120rdmi * w).sum() / W)),
           "own": round(float((tr.trials_in_own_county * w).sum() / W)),
           "people_l20": int(w[tr.trials_within_60rdmi < 20].sum()), "people_z60": int(w[tr.trials_within_60rdmi == 0].sum()), "people_g60n": int(w[tr.road_mi_nci > 60].sum()), "people_g60b": int(w[tr.road_mi_broad > 60].sum())}
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
    def grp(m):   # every figure findings.js publishes for metro / nonmetro (build_rucc.py), recomputed here from the tracts
        ww = w[m]; WW = ww.sum(); t = tr[m]; mn = wmed("road_mi_nci", t); mb = wmed("road_mi_broad", t); pc = lambda mask: round(100 * ww[mask].sum() / WW, 1)
        return {"p": int(WW), "n": int(t.county_fips.nunique()), "l20": pc(t.trials_within_60rdmi < 20), "z60": pc(t.trials_within_60rdmi == 0), "l100": pc(t.trials_within_60rdmi < 100),
                "t30": round(float((t.trials_within_30rdmi * ww).sum() / WW)), "t60": round(float((t.trials_within_60rdmi * ww).sum() / WW)), "t120": round(float((t.trials_within_120rdmi * ww).sum() / WW)),
                "g60n": pc(t.road_mi_nci > 60), "g120n": pc(t.road_mi_nci > 120), "g60b": pc(t.road_mi_broad > 60), "g120b": pc(t.road_mi_broad > 120),
                "medn": None if mn != mn else round(mn), "medb": None if mb != mb else round(mb), "nr": pc(t.road_mi_broad >= 999)}
    gm, gn = grp(metro), grp(nonm); R = FI["rural"]
    for g, name in ((gm, "metro"), (gn, "nonmetro")):
        for k, v in g.items(): rec("headline", f"{name} {k}: recomputed vs findings.js", f"{v} vs {R[name].get(k)}", R[name].get(k) == v)
    nm_share = 100 * gn['p'] / (gm['p'] + gn['p']); nm_readme = readme_num(r"Nonmetro counties hold ([\d.]+)% of residents 55\+")
    rec("headline", "nonmetro share of residents 55+", f"{nm_share:.1f}% (README says {nm_readme}%)", nm_readme is not None and abs(nm_share - nm_readme) < 0.05)
    rd_l20 = readme_num(r"([\d.]+)% of residents 55\+ in nonmetro counties \(codes 4–9\) have fewer than 20 recruiting trials within 60 road-miles, vs ([\d.]+)% in metro counties; ([\d.]+)% vs ([\d.]+)% have none; median road distance to an NCI-designated center (\d+) vs (\d+) miles")
    rec("headline", "README rural sentence (nonmetro / metro: fewer than 20, none, median to an NCI center) equals the recomputation", f"README {rd_l20} vs recomputed {(gn['l20'], gm['l20'], gn['z60'], gm['z60'], gn['medn'], gm['medn'])}", rd_l20 == (gn['l20'], gm['l20'], gn['z60'], gm['z60'], gn['medn'], gm['medn']))
    # counties and states from county_metrics, against the counts the build logs (metrics_log.json) and the README states
    cm = CM; broad = int((cm.trials_in_county >= 100).sum()); lim = int((cm.trials_in_county >= 20).sum()); anyt = int((cm.trials_in_county > 0).sum())
    st_of = cm.county_fips.str[:2]; st_broad = cm[cm.trials_in_county >= 100].county_fips.str[:2].unique(); usps = {}
    with open(REF / "Ruralurbancontinuumcodes2023.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f): usps[r["FIPS"][:2]] = r["State"]
    no_broad = sorted({usps.get(s, s) for s in st_of.unique()} - {usps.get(s, s) for s in st_broad})
    ML = json.loads((OUT / "metrics_log.json").read_text(encoding="utf-8")); rd_cnt = readme_num(r"([\d,]+) counties host at least a limited menu \(20 or more trials\), ([\d,]+) of them a broad menu", int)
    rec("headline", "broad-menu counties (100+), 20+ counties, counties with any trial", f"{broad}, {lim}, {anyt} (metrics_log: {ML.get('broad_menu_counties')}, {ML.get('limited_menu_counties')}, {ML.get('counties_with_any_trial')}; README: {rd_cnt[1] if rd_cnt else None} broad, {rd_cnt[0] if rd_cnt else None} limited)",
        (broad, lim, anyt) == (ML.get("broad_menu_counties"), ML.get("limited_menu_counties"), ML.get("counties_with_any_trial")) and rd_cnt == (lim, broad))
    CMJ = load_js(DOCS / "community.js", None); names = {k: v["name"] for k, v in CMJ["states"].items()}; rd_nb = readme_num(r"\*\*(\d+) states have no broad-menu county\*\*", int)
    rec("headline", "states with no broad-menu county", f"{len(no_broad)}: {', '.join(no_broad)} (findings.js: {FI.get('states_no_broad')}; README: {rd_nb})", len(no_broad) == FI.get("states_no_broad") == rd_nb and {names.get(x, x) for x in no_broad} == set(FI.get("states_no_broad_list", [])))
    # districts where every resident 55+ is beyond 60 road-miles of a broad menu
    rel = pd.read_csv(REF / "tract_cd119.csv", dtype={"tract": str, "cd_geoid": str}); rel["share"] = rel.share.astype(float)
    m = rel.merge(tr, on="tract", how="inner"); m["w"] = m.pop55 * m.share; m["far"] = m.w * (m.road_mi_broad > 60)
    g = m.groupby("cd_geoid").agg(w=("w", "sum"), far=("far", "sum")); g = g[g.w > 0]; n73 = int((g.far / g.w >= 0.9995).sum())
    fd = (FI.get("districts") or {}).get("all_beyond_60_broad"); rd_d = readme_num(r"(\d+) congressional districts have every resident 55\+ beyond 60 road-miles", int)
    rec("headline", "districts where every resident 55+ is beyond 60 road-miles of a broad menu", f"{n73} (findings.js: {fd}; README: {rd_d})", n73 == fd == rd_d)
    # README headline block
    readme = (ROOT / "README.md").read_text(encoding="utf-8"); blk = readme[readme.index("headline:start"):readme.index("headline:end")]
    want = {f"{got['l20']}% of Americans": True, f"{got['z60']}% have none": True, f"{got['zc']}% live in a county with no trial": True, f"{got['g60b']}% live more than 60 road-miles": True, f"{got['g120b']}% more than 120": True, f"{got['nr']}% (Alaska, Hawaii) have no road connection": True,
            f"{got['g60n']}% live more than 60 road-miles from an NCI": True, f"median resident 55+ is {got['medn']} road-miles": True, f"{got['g120n']}% are more than 120": True, f"{gn['l20']}% of residents 55+ in nonmetro": True, f"vs {gm['l20']}% in metro": True,
            f"{len(D['T']['id']):,} listed trials": True, f"({D['meta']['sitepoints']:,} distinct site locations)": True}
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
    rdr = readme_num(r"median ([\d.]+) \(10th–90th percentile ([\d.]+)–([\d.]+)\); the common ×1\.2 convention is too low for ([\d,]+) of ([\d,]+) counties")
    rec("roads", "road / straight-line ratio to the nearest broad menu", f"median {rb.median():.2f}, p10 {rb.quantile(.1):.2f}, p90 {rb.quantile(.9):.2f} (README: median {rdr[0] if rdr else None}, {rdr[1] if rdr else None}–{rdr[2] if rdr else None})", rdr is not None and abs(rb.median() - rdr[0]) < 0.02)
    # the README's own subset (route_us.py: every county with a road route and a nonzero distance) for its "×1.2 is too low for N of M counties"
    okr = (rd.road_mi_broad > 0) & (rd.road_mi_broad < 999); rr = rd.road_mi_broad[okr] / (rd.straightline_x1_2_broad[okr] / 1.2); n_low = int((rr > 1.2).sum())
    rd_txt = f"{int(rdr[3]):,} of {int(rdr[4]):,}; {rdr[0]}, {rdr[1]}–{rdr[2]}" if rdr else "sentence not found"
    rec("roads", "README: the ×1.2 convention is too low for N of M counties (road / straight-line > 1.2), recomputed from county_road_distances.csv", f"{n_low:,} of {int(okr.sum()):,}; median {rr.median():.2f}, p10 {rr.quantile(.1):.2f}, p90 {rr.quantile(.9):.2f} (README: {rd_txt})",
        rdr is not None and (n_low, int(okr.sum())) == (int(rdr[3]), int(rdr[4])) and (round(rr.median(), 2), round(rr.quantile(.1), 2), round(rr.quantile(.9), 2)) == rdr[:3])
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
    # every row (not a sample) whose county came from the ZIP's first three digits: the stated city must lie within 40 miles of that
    # county's population center. A row that fails was drawn at the county center by route_sites_us.py as a site that is not there
    # (Tuscola County MI, data of 5 Oct 2026: 31 trial rows for a Tawas City hospital listed with ZIP 48764). Since the refresh of
    # 11 Oct 2026 metrics_us.py lets a known city win (assign_method city_over_zip3), so a failure here is a new case.
    z3 = qc[qc.assign_method.isin(("zip3", "city_over_zip3"))]; z3_far = []; z3_judged = 0
    for r in z3.itertuples():
        cands = gaz.get((r.state, r.city.lower().strip())) or []; c = cm.loc[r.county_fips] if r.county_fips in cm.index else None
        if not cands or c is None: continue
        z3_judged += 1; d = min(miles(g, (c.lat, c.lon)) for g in cands)
        if d > 40: z3_far.append((r.nct_id, r.city, r.state, r.zip, r.county_fips, r.assign_method, round(d)))
    nm = Counter(z3.assign_method)
    rec("sites", "rows assigned by the ZIP's first three digits whose stated city lies within 40 miles of the assigned county (all such rows)", f"{z3_judged - len(z3_far)} of {z3_judged} judged ({len(z3) - z3_judged} without a gazetteer match; {nm.get('zip3', 0):,} by ZIP prefix, {nm.get('city_over_zip3', 0):,} by city over ZIP prefix)", len(z3_far) == 0, ("far: " + str(sorted(z3_far, key=lambda x: -x[-1])[:12])) if z3_far else None)
    # every row placed by its ZIP (not a sample): the ZIP's Census center against the stated city. In most such rows the ZIP is right and the
    # city loose ("Omaha" for a clinic in a small town); the ones that matter are counties whose whole trial count rests on such rows
    # (the link check of 5 Oct 2026 found seven: Chatham NC, Gage NE, Mitchell NC, Ashtabula OH, Brazos TX, Halifax NC, Skamania WA).
    # A row counts as far only if the stated city also lies outside the assigned county: a very large ZIP area (Fairbanks 99701, Cody 82414)
    # has its center far from its town although ZIP, city and county agree.
    zr = qc[qc.assign_method.isin(("zip", "zip_pop"))]; far25 = []; judged_all = 0; ok_rows = defaultdict(set); all_rows = defaultdict(set)
    for r in zr.itertuples():
        z = F["zcta"].get(r.zip[:5]); cands = gaz.get((r.state, r.city.lower().strip())) or []
        all_rows[r.county_fips].add(r.nct_id)
        if not z or not cands: ok_rows[r.county_fips].add(r.nct_id); continue
        judged_all += 1; d = min(miles((z[0], z[1]), g) for g in cands)
        c = cm.loc[r.county_fips] if r.county_fips in cm.index else None
        city_in = any(inside(r.county_fips, g) or (c is not None and miles(g, (c.lat, c.lon)) < 6) for g in cands)
        if d > 25 and not city_in: far25.append((r.nct_id, r.facility[:40], r.city, r.state, r.zip, r.county_fips, round(d)))
        else: ok_rows[r.county_fips].add(r.nct_id)
    for r in qc[~qc.assign_method.isin(("zip", "zip_pop", "virtual_site", "unassigned"))].itertuples(): all_rows[r.county_fips].add(r.nct_id); ok_rows[r.county_fips].add(r.nct_id)
    rest = sorted((f, cm.loc[f, "county_name"] if f in cm.index else "?", len(all_rows[f])) for f in all_rows if all_rows[f] and not ok_rows[f])
    rec("sites", "every row placed by its ZIP: ZIP center more than 25 miles from the stated city, which lies outside the assigned county; counties whose whole trial count rests on such rows", f"{len(far25):,} of {judged_all:,} rows (> 40 mi: {sum(1 for x in far25 if x[-1] > 40):,}); {len(rest)} counties rest entirely on them: " + ", ".join(f"{n} {f} ({k} trial{'s' if k != 1 else ''})" for f, n, k in rest), None,
        "rows behind those counties: " + str([x for x in far25 if x[5] in {f for f, _, _ in rest}][:20]))
    if (OUT / "site_geocode_qc.csv").exists():
        gq = pd.read_csv(OUT / "site_geocode_qc.csv", dtype=str).fillna(""); ncc = int((gq.geocode == "county_centroid_city_disagrees").sum())
        rsl = json.loads((OUT / "route_sites_log.json").read_text(encoding="utf-8")) if (OUT / "route_sites_log.json").exists() else {}
        cc = gq[gq.geocode == "county_centroid"]
        rec("sites", "site rows drawn at a county center although the stated city lies elsewhere (phantom sites)", f"{ncc} rows; {len(cc)} more at a county center because ZIP and city are both unknown; {rsl.get('unlocated_rows')} rows left unlocated (route_sites_log.json)", ncc == 0,
            (("phantom: " + str(gq.loc[gq.geocode == "county_centroid_city_disagrees", ["nct_id", "city", "state", "zip5", "county_fips"]].head(12).values.tolist()) + "; ") if ncc else "")
            + (("at a county center (ZIP and city unknown): " + str(cc[["nct_id", "facility", "city", "state", "zip5", "county_fips"]].values.tolist()[:12])) if len(cc) else ""))

# ---------------------------------------------------------------- 6. ZIP finder ----------------------------------------------------------------
def zip_finder(D, F, tr, seed, nzips, port, browser):
    T = D["T"]; SP = D["SP"]; rng = random.Random(seed)
    zc = [z for z in F["zcta"] if F["zcta"][z][2]]; sample = rng.sample(zc, nzips)
    cty = tr.groupby("county_fips").apply(lambda g: float((g.trials_within_60rdmi * g.pop55).sum() / max(g.pop55.sum(), 1)))
    # the road-network figure at the same place: the census tract (with residents 55+) whose population center is nearest the ZIP center, in the ZIP's county
    tl = pd.read_csv(OUT / "tract_access.csv", dtype={"tract": str, "county_fips": str}, usecols=["tract", "county_fips", "lat", "lon", "pop55", "trials_within_60rdmi"]); tl = tl[tl.pop55 > 0]
    tby = {k: g for k, g in tl.groupby("county_fips")}
    def nearest_tract(zz):
        g = tby.get(zz[2])
        if g is None: return None, None, None
        la, lo = np.radians(g.lat.values), np.radians(g.lon.values); la0, lo0 = math.radians(zz[0]), math.radians(zz[1])
        d = 2 * R_EARTH * np.arcsin(np.sqrt(np.sin((la - la0) / 2) ** 2 + np.cos(la0) * np.cos(la) * np.sin((lo - lo0) / 2) ** 2)); i = int(np.argmin(d))
        return g.tract.values[i], int(g.trials_within_60rdmi.values[i]), round(float(d[i]), 1)
    rows = []
    for z in sample:
        zz = F["zcta"][z]; near = [(s, math.floor(miles((zz[0], zz[1]), (p[0], p[1])) * F["meta"]["road_factor"] + 0.5)) for s, p in enumerate(F["sp"])]
        near = [(s, mi) for s, mi in near if mi <= 60]
        trials = set();
        for s, mi in near: trials.update(SP[s])
        tt, tv, td = nearest_tract(zz)
        rows.append({"zip": z, "county": zz[2], "python": len(trials), "county_road_t60": round(float(cty.get(zz[2], float("nan"))), 1), "tract": tt, "tract_road_t60": tv, "tract_mi": td})
    if browser:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 900})
            for r in rows:
                pg.goto(f"{BASE}/find.html?zip={r['zip']}", wait_until="networkidle"); pg.wait_for_timeout(600)
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
    rt = [(r["python"], r["tract_road_t60"]) for r in rows if r["tract_road_t60"] is not None]
    ratio_t = [a / b for a, b in rt if b > 0]; within = sum(1 for a, b in rt if abs(a - b) <= max(2, 0.1 * b))
    rec("zipfinder", "ZIP estimate (straight-line × 1.2) vs the road-network trials-within-60 of the census tract nearest the ZIP center (informational; same place, different distance methods)",
        (f"{within} of {len(rt)} ZIPs within 10% (or 2 trials); ratio median {np.median(ratio_t):.2f}, p10 {np.quantile(ratio_t, .1):.2f}, p90 {np.quantile(ratio_t, .9):.2f} over the {len(ratio_t)} with a tract figure above zero") if ratio_t else "n/a", None,
        "outside 10%: " + "; ".join(f"{r['zip']}:{r['python']}/{r['tract_road_t60']} (tract {r['tract']}, {r['tract_mi']} mi from the ZIP center)" for r in rows if r["tract_road_t60"] is not None and abs(r["python"] - r["tract_road_t60"]) > max(2, 0.1 * r["tract_road_t60"]))[:1500])
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
    # a county with no road route to an NCI center (the 999 sentinel in county_road_distances.csv) is shown with a sentence, not a number:
    # "No road connection from this county to any ... NCI ..." (index, community), "No road route to an NCI-designated center" (brief), or,
    # for a population center more than 30 miles from any road, "no road distance is reported" (index, community)
    # (an island county that does reach an NCI center, Honolulu, is "No road connection from this county to a broad menu of trials; the nearest
    # NCI-designated center is ..., 7 road-miles" on community.html: that number is read, and the sentence is not taken as "no route")
    noroute = lambda t: 999 if re.search(r"No road connection from this county to any (?:broad menu or NCI|NCI)|No road route to an NCI|no road distance is reported", t) else None
    def grab(pg, url, sel):
        pg.goto(f"{BASE}/{url}", wait_until="networkidle"); pg.wait_for_timeout(1500)
        return pg.inner_text(sel) if pg.locator(sel).count() else pg.inner_text("body")
    mism = []; checked = 0
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1440, "height": 900})
        for k in sample_c:
            exp = {"l20": float(cty_l20.get(k, float("nan"))), "t": int(cm.loc[k, "trials_in_county"]), "rn": rd.loc[k, "road_mi_nci"]}
            got = {}
            t = grab(pg, f"index.html?c={k}", "#pane"); m = re.search(r"(\d{1,3}\.\d)\s*%\s*of residents 55\+ in the county", t); got["index.l20"] = float(m.group(1)) if m else None
            m = re.search(r"(\d[\d,]*)\s*trials?\s*with a recruiting site in the county", t); got["index.t"] = int(m.group(1).replace(",", "")) if m else None
            m = re.search(r"(\d[\d,]*)\s*road-miles\s*from the county population center to the nearest NCI", t); got["index.rn"] = int(m.group(1).replace(",", "")) if m else noroute(t)
            t = grab(pg, f"community.html?c={k}", "main"); m = re.search(r"(\d{1,3}\.\d)\s*%\s*of residents 55 and older in", t); got["community.l20"] = float(m.group(1)) if m else None
            m = re.search(r"(\d[\d,]*)\s*trials?\s*(?:has|have|No listed trial has) a recruiting site in the county", t); got["community.t"] = int(m.group(1).replace(",", "")) if m else None
            m = re.search(r"(\d[\d,]*)\s*road-miles\s*from the county.s population center to the nearest NCI", t) or re.search(r"the nearest NCI-designated center is .+?, (\d[\d,]*) road-miles", t); got["community.rn"] = int(m.group(1).replace(",", "")) if m else noroute(t)
            t = grab(pg, f"brief.html?c={k}", "body")   # the county brief carries the trial count and the NCI distance, not the share
            m = re.search(r"(\d[\d,]*)\s*recruiting trials?\s*with a site in the county", t); got["brief.t"] = int(m.group(1).replace(",", "")) if m else None
            m = re.search(r"(\d[\d,]*)\s*road-mi\s*to the nearest NCI", t); got["brief.rn"] = int(m.group(1).replace(",", "")) if m else noroute(t)
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
def page_health(port, axe_path=None):
    from playwright.sync_api import sync_playwright
    axe = None; axe_ver = None
    for cand in [axe_path, os.environ.get("AXE_CORE_JS"), ROOT / "node_modules/axe-core/axe.min.js"]:
        if cand and Path(cand).exists():
            axe = Path(cand).read_text(encoding="utf-8"); m = re.search(r"axe v([\d.]+)", axe[:400]); axe_ver = m.group(1) if m else "?"; break
    pages = ["index.html", "findings.html", "community.html", "learn.html", "find.html", "act.html", "brief.html?s=KY", "trials.html?county=48215", "sites.html", "community.html?c=21227", "act.html?c=21227", "index.html?u=district&m=cos_ctma_hr", "index.html?c=48215", "index.html?s=KY&rural=1&guide=rural-urban"]
    errs_all = {}; viol = 0; hs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for vp, mob in (((1440, 900), False), ((390, 844), True)):
            ctx = b.new_context(viewport={"width": vp[0], "height": vp[1]}, is_mobile=mob, has_touch=mob)
            for u in pages:
                pg = ctx.new_page(); errs = []
                pg.on("pageerror", lambda ex, e=errs: e.append("pageerror: " + str(ex)))
                pg.on("console", lambda m, e=errs: e.append(m.text) if m.type == "error" and "cdnjs" not in m.text and "TUNNEL" not in m.text and "ERR_" not in m.text else None)
                pg.goto(f"{BASE}/{u}", wait_until="networkidle"); pg.wait_for_timeout(1500)
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
    rec("health", f"axe-core WCAG 2 A/AA violations (axe-core {axe_ver})" if axe else "axe-core WCAG 2 A/AA violations: NOT RUN (axe-core not found; pass --axe)", f"{viol}" if axe else "not run", viol == 0 if axe else None, str({k: v for k, v in errs_all.items() if k.startswith("axe")}) if viol else None)

# ---------------------------------------------------------------- cosponsors (payload consistency) ----------------------------------------------------------------
def cosponsor_consistency(CO, FI):
    b = CO["bills"]
    for k in b:
        roles = Counter(bills[k]["role"] for m, bills in CO["by_member"].items() if k in bills)
        n = sum(v for r, v in roles.items() if r != "sponsor"); parties = Counter(CO["members"][m]["party"] for m, bills in CO["by_member"].items() if k in bills and bills[k]["role"] != "sponsor")
        fb = next((x for x in FI.get("bills", []) if x.get("key") == k), {})
        ok = fb.get("n_cosponsors") == n and all(fb.get("parties", {}).get(pp, 0) == parties.get(pp, 0) for pp in ("R", "D", "I"))
        rec("cosponsors", f"{b[k]['label']}: cosponsors in cosponsors.js vs findings.js", f"{n} ({dict(parties)}) vs {fb.get('n_cosponsors')} ({fb.get('parties')}); roles {dict(roles)}", ok, f"fetched {CO['meta'].get('fetched')} from {CO['meta'].get('source')}")

def port_free(port):   # as http.server binds (SO_REUSEADDR): only a listening socket makes the port taken, not one left in TIME_WAIT by an earlier run
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: s.bind((HOST, port)); return True
        except OSError: return False

def start_server(port):
    """Serve this checkout's docs/ on 127.0.0.1 only. A port another process holds (other reviewers' servers, other checkouts) is never
    read from: the next free port is taken instead, and the pages are read only once this script's own server process is up and answering
    (a server that failed to bind exits at once) with this checkout's data.js."""
    if not port_free(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s: s.bind((HOST, 0)); new = s.getsockname()[1]
        print(f"port {port} is in use; serving {DOCS} on free port {new} instead", flush=True); port = new
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", HOST, "--directory", str(DOCS)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})); want = (DOCS / "data.js").stat().st_size
    for _ in range(60):
        time.sleep(0.25)
        if srv.poll() is not None: raise SystemExit(f"http.server on port {port} exited at start (code {srv.returncode}): port taken?")
        try:
            with opener.open(urllib.request.Request(f"http://{HOST}:{port}/data.js", method="HEAD"), timeout=5) as r: got = int(r.headers.get("Content-Length", -1))
        except Exception: continue
        time.sleep(0.3)
        if srv.poll() is not None: raise SystemExit(f"http.server on port {port} exited at start (code {srv.returncode}): port taken?")
        if got != want: srv.terminate(); raise SystemExit(f"the server on port {port} is not serving {DOCS} (data.js {got} bytes, expected {want})")
        return srv, port
    srv.terminate(); raise SystemExit(f"http.server on port {port} did not answer")

def run(args):
    global BASE
    srv, port = start_server(args.port) if not args.no_browser else (None, args.port)
    BASE = f"http://{HOST}:{port}"
    try:
        D = load_js(DOCS / "data.js", "window.DATA="); FI = load_js(DOCS / "findings.js", "window.FINDINGS="); CO = load_js(DOCS / "cosponsors.js", "window.COSPONSORS=")
        F = load_js(DOCS / "find_data.js", "window.FIND="); GEO = load_js(DOCS / "geo.js", "window.GEO="); CM = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str})
        rec("setup", "seed / data date", f"seed {args.seed}; registry data {D['meta']['registry_data_timestamp']} (fetch_log: {FETCH_LOG['registry_data_timestamp']}, fetched {FETCH_LOG['timestamp_utc'][:16]} UTC; data.js pull {D['meta'].get('pull_utc')}); {len(D['T']['id']):,} listed trials; run {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}" + (f"; pages served from {BASE}" if srv else ""), None)
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
            zip_finder(D, F, tr, args.seed, args.zips, port, True)
            cross_page(D, CO, FI, tr, args.seed, port)
            page_health(port, args.axe)
        else:
            zip_finder(D, F, tr, args.seed, args.zips, port, False)
    finally:
        if srv:
            srv.terminate()
            try: srv.wait(timeout=10)
            except subprocess.TimeoutExpired: srv.kill()
    out = Path(args.out or (OUT / f"validation_outside_pass{args.seed}.json")); out.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    fails = [(s, r["check"]) for s, rs in results.items() for r in rs if r["ok"] is False]
    print(f"\nwrote {out}; {sum(len(v) for v in results.values())} checks, {len(fails)} failed" + (": " + "; ".join(f"{s} · {c}" for s, c in fails) if fails else ""))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=1); ap.add_argument("--out"); ap.add_argument("--no-browser", action="store_true"); ap.add_argument("--skip-registry", action="store_true")
    ap.add_argument("--sites", type=int, default=150); ap.add_argument("--zips", type=int, default=30); ap.add_argument("--port", type=int, default=8103)
    ap.add_argument("--axe", help="path to axe-core's axe.min.js (else $AXE_CORE_JS, else node_modules/axe-core/axe.min.js)")
    run(ap.parse_args())
