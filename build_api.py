#!/usr/bin/env python3
"""Public data files ("the data API"): one small JSON file per county, congressional district and state, plus a national file and an index,
under docs/api/. They are plain static files served by GitHub Pages at predictable addresses, so anyone can pull a place's figures into
their own page, dashboard or analysis without reading the map's internal payload.

    docs/api/index.json              what is here, the field definitions, data date, license, citation
    docs/api/national.json
    docs/api/state/TX.json           one per state and DC (USPS code)
    docs/api/district/TX-34.json     one per congressional district (USPS-number; at-large districts are XX-00)
    docs/api/county/48215.json       one per county (5-digit FIPS)
    docs/api/all_counties.json, all_districts.json, all_states.json   the same figures as one table each

Every file carries the same core fields (see FIELDS) so a consumer can treat the three levels alike. Sources: out_adult55/*.csv and the
national JSON from tract_metrics_us.py (district and state shares), the tract table (county shares, computed here by population weighting),
docs/data.js (names, trial counts, context) and docs/cosponsors.js (members and cosponsorship). Run after build_findings.py in run_refresh.sh.
"""
import json, csv, datetime, sys, math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "api"
SITE = "https://cancertrialaccess.org/"   # the published address (custom domain; docs/CNAME); change it here and in docs/ask/catalog.js, worker/wrangler.toml and make_sitemap.py
LICENSE = {"data": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/",
           "attribution": "Agrawal N. Cancer Clinical Trial Access Map (beta). " + SITE}

FIELDS = {
    "id": "Place identifier: 5-digit county FIPS, USPS-number for a district (XX-00 is at-large), USPS code for a state, US for the nation.",
    "level": "county, district, state or national.",
    "name": "Place name. Districts: 'Texas 34th'; counties: 'Hidalgo County, Texas'.",
    "state": "USPS code of the state.",
    "pop55": "Residents aged 55 and older (ACS 5-year, summed from census tracts).",
    "pct_lt20_trials_within_60rdmi": "Share (%) of residents 55+ with fewer than 20 recruiting cancer treatment trials within 60 road-miles of home. The site's headline 'short of trials' measure.",
    "people_lt20_trials_within_60rdmi": "The same, as a count of people.",
    "pct_zero_trials_within_60rdmi": "Share (%) with no recruiting trial within 60 road-miles.",
    "people_zero_trials_within_60rdmi": "The same, as a count of people (pop55 x share, rounded; the rule used for people_lt20_trials_within_60rdmi).",
    "pct_lt100_trials_within_60rdmi": "Share (%) with fewer than 100 trials within 60 road-miles.",
    "pct_gt60rdmi_broad_menu": "Share (%) living more than 60 road-miles from a county with 100 or more recruiting trials (a 'broad menu').",
    "pct_gt60rdmi_nci": "Share (%) living more than 60 road-miles from an NCI-designated cancer center.",
    "median_road_mi_nci": "Median road miles from home to the nearest NCI-designated center (residents with a road route).",
    "median_road_mi_broad_menu": "Median road miles to the nearest broad-menu county.",
    "wmean_trials_within_60rdmi": "Population-weighted mean number of recruiting trials within 60 road-miles.",
    "trials_listed_here": "Recruiting trials with at least one site in the place, each trial counted once. County: trials with a site in the county. District: distinct trials with a site in any county that overlaps the district (a trial in a county shared by two districts counts for both, so district figures do not add up to the state's). State: distinct trials with a site in the state. National: all recruiting trials in the pull.",
    "nearest_nci": "The NCI-designated center nearest to most residents.",
    "nearest_broad_menu": "The broad-menu county nearest to most residents.",
    "trials_within_60rdmi_by_cancer_type": "Population-weighted mean trials within 60 road-miles, by cancer type (district and state only).",
    "context": "ACS context: no_vehicle, broadband, uninsured, uninsured_55_64, poverty, all in %, population-weighted.",
    "member": "Districts only: the House member, party, and cosponsorship of the Clinical Trial Modernization Act (H.R. 3521): sponsor, original, cosponsor, or none.",
    "counties": "Districts only: the FIPS codes of counties that overlap the district.",
    "districts": "Counties only: the ids of the congressional districts that overlap the county, in the district file's form (TX-15, XX-00 for at-large), sorted; the inverse of the districts' counties lists. A county split between districts lists each of them.",
    "links": "map: the map opened on this place; brief: the printable brief for it.",
    "data_as_of": "Registry data date of the ClinicalTrials.gov pull these figures come from.",
    # ---- the data behind the map's other layers (county rows) ----
    "rucc": "Counties only: USDA ERS Rural-Urban Continuum Code, 1 (metro, 1 million+) to 9 (nonmetro, urban under 5,000, not adjacent); 2023 release (2013 for Connecticut's legacy counties). null where no code is published.",
    "rucc_label": "Counties only: the USDA label for the code.",
    "metro": "Counties: true when the RUCC is 1-3 (metro), false for 4-9 (nonmetro), null when unknown. States and the nation: the access figures for residents of metro counties (see nonmetro).",
    "nonmetro": "States and the nation: the access figures for residents of nonmetro counties (RUCC 4-9), with metro holding the same for RUCC 1-3: pop55, counties, pct_lt20 (share with fewer than 20 trials within 60 road-miles), people_lt20, pct_zero, people_zero, pct_lt100, mean_trials_60 (average trials within 60 road-miles), pct_gt60rdmi_nci, pct_gt60rdmi_broad_menu, median_road_mi_nci, median_road_mi_broad_menu. null where the state has no county of that kind (DC has no nonmetro county).",
    "road_mi_nci_from_center": "Counties only: road miles from the county population center to the nearest NCI-designated cancer center (the map's 'road-miles to an NCI center' layer). null = no road route.",
    "road_mi_broad_menu_from_center": "Counties only: road miles from the population center to the nearest county with 100 or more recruiting trials; 0 when the county itself hosts a broad menu. null = no road route.",
    "road_mi_limited_menu_from_center": "Counties only: road miles from the population center to the nearest county with 20 or more recruiting trials; 0 when the county hosts one. null = no road route.",
    "no_road_route_reason": "Counties only: null when road distances exist; 'island' when the county has no road connection to a broad menu or NCI center (island or disconnected network); 'off' when the population center is more than 30 miles from any primary or secondary road, so no road distance is reported.",
    "drive_hours_nci": "Counties only: estimated driving time in hours from the population center to the nearest NCI-designated center (one decimal). null = no road route.",
    "drive_hours_broad_menu": "Counties only: estimated driving time in hours to the nearest broad-menu county (one decimal). null = no road route.",
    "trials_within_60rdmi_of_center": "Counties only: recruiting trials with a site within 60 road-miles of the county population center (the county-level count the map's county card shows; the pop-weighted tract figure is wmean_trials_within_60rdmi).",
    "facilities_within_60rdmi_of_center": "Counties only: recruiting trial sites within 60 road-miles of the county population center.",
    "incidence": "Counties only: cancer incidence from NCI State Cancer Profiles, age-adjusted per 100,000, all ages, for the period given. all = all-sites rate (null unless status is ok); cases_per_year = average annual new cases, all sites; small_numbers = true when fewer than 16 average annual cases (interpret with caution); status = ok | suppressed (fewer than 16 cases in the period) | no data; status_text = the wording the map prints; by_site = rate per site key (null where not published; site labels are in index.json thresholds.site_labels).",
    "mortality": "Counties only: cancer death rates from NCI/CDC State Cancer Profiles (National Vital Statistics System), age-adjusted per 100,000, all ages, for the period given. all = all-sites death rate; deaths_per_year = average annual cancer deaths, all sites; small_numbers = fewer than 16 deaths a year on average; status, status_text and by_site as for incidence.",
    "oncologists": "County: count = oncologists (CMS Care Compare primary specialty medical oncology, hematology/oncology or hematology) with a Medicare practice location in the county; radiation, gynecologic, surgical = the same for those specialties; within_60rdmi = oncologists within 60 road-miles of the population center; class 1-4 and class_label = the map's 'oncologists vs trials' category (1 Oncologists and trials, 2 Oncologists, no trials, 3 Trials, no oncologist listed, 4 Neither); all_also_elsewhere = true when every oncologist counted also lists a location in another county (likely a part-time or outreach clinic). District, state, national: count = oncologists practising in the place (district: in counties touching it); oncologists_per_100k_pop55 (state, national); pct_pop55_in_counties_with_oncologists_no_trials, pct_pop55_in_counties_with_both, pct_pop55_in_counties_with_neither = shares of residents 55+ by county category; counties_with_oncologists_no_trials = how many such counties (district: their FIPS codes).",
    "incidence_above_county_median": "Counties only: true when the all-sites incidence rate is above the median of US counties with a published rate (the 'high incidence' half of the map's incidence-vs-access layer; the median is in index.json thresholds). null when the rate is not published.",
    "mortality_top_third": "Counties only: true when the all-sites cancer death rate is in the top third of US counties with a published rate (the 'high mortality' part of the deaths-vs-access layer; the cut is in index.json thresholds). null when the rate is not published.",
    # ---- district, state and national rows ----
    "nonmetro_pct": "Districts and states: share (%) of residents 55+ living in nonmetro counties (RUCC 4-9).",
    "incidence_all_sites": "Districts, states and the nation: all-sites age-adjusted incidence per 100,000, as the map's incidence layer paints it: the residents-55+-weighted mean of county rates (incidence_all_sites_cases_per_year = the matching annual cases, county counts shared out by residents 55+).",
    "incidence_all_sites_cases_per_year": "Districts, states and the nation: average annual new cases, all sites, behind incidence_all_sites (county counts shared out by residents 55+, so 'about').",
    "incidence_published": "States and the nation: the published state/national rates from State Cancer Profiles, all = all-sites rate, cases_per_year, by_site = rate per site key (the figure the state card leads with; districts have only the county-weighted mean).",
    "senators": "States only: the two senators (name, party) and, as s4440, each one's position on the Senate Clinical Trial Modernization Act (S. 4440): sponsor, original (original cosponsor), cosponsor, or none; bill and bill_url name the bill. Empty for DC.",
}

def load_js(name, optional=False):
    p = ROOT / "docs" / name
    if optional and not p.exists(): return None
    s = p.read_text(encoding="utf-8")
    return json.loads(s.split("=", 1)[1].strip().rstrip(";"))

def clean(v):
    """A JSON-safe number: NaN -> null (the map's data files use null already; this guards the CSV-derived figures)."""
    return None if v is None or (isinstance(v, float) and v != v) else v

# the status codes of the incidence / mortality records (data.js county b[i][4], mortality.js county[fips][i][-1]) and the text the map prints for each
STATUS_KEY = {0: "ok", 1: "ok", 2: "suppressed", 3: "no data", 4: "no data"}
def status_text(code, small_threshold, noun):
    return {0: "published", 1: f"small numbers — interpret with caution (fewer than {small_threshold} average annual {noun})",
            2: f"suppressed by the source (fewer than 16 {noun} in the period)", 3: "not available for this state (state law prohibits county-level release)",
            4: "not available for this county in the source"}.get(code, "no data for this county")

def burden_record(recs, sites, period, small_threshold, noun):
    """The county's incidence or mortality block. recs: list of [rate, ci_lo, ci_hi, count, status] (the all-sites record; shorter site records are
    [rate, count, status]) in `sites` order, or None. A rate or count is carried only when the status is 0 (published) or 1 (small numbers), as the map prints it."""
    count_key = "cases_per_year" if noun == "cases" else "deaths_per_year"
    out = {"all": None, count_key: None, "small_numbers": False, "status": "no data", "status_text": "no data for this county", "period": period, "by_site": {}}
    if not recs: return out
    def parts(r):   # (rate, count, status) whatever the record length
        return (r[0], r[3], r[4]) if len(r) >= 5 else (r[0], r[1], r[2])
    for i, (key, _label) in enumerate(sites):
        r = recs[i] if i < len(recs) and recs[i] else None
        rate, n, st = parts(r) if r else (None, None, None)
        ok = st is not None and st <= 1 and rate is not None
        out["by_site"][key] = clean(rate) if ok else None
        if i == 0:
            out["all"] = clean(rate) if ok else None; out[count_key] = clean(n) if ok else None
            out["small_numbers"] = st == 1; out["status"] = STATUS_KEY.get(st, "no data") if st is not None else "no data"
            out["status_text"] = status_text(st, small_threshold, noun) if st is not None else "no data for this county"
    return out

def rucc_group(g):
    """One side of the metro / nonmetro split in rucc.js (nat or states[usps]), with the API's names. None when the state has no such county."""
    if not g: return None
    n_of = lambda k: g.get("n_" + k) if isinstance(g.get("n_" + k), (int, float)) else int(round(g["p"] * g[k] / 100))   # the tract count when rucc.js has it, as the map's grpN
    return {"pop55": g["p"], "counties": g["n"],
            "pct_lt20_trials_within_60rdmi": clean(g["l20"]), "people_lt20_trials_within_60rdmi": n_of("l20"),
            "pct_zero_trials_within_60rdmi": clean(g["z60"]), "people_zero_trials_within_60rdmi": n_of("z60"),
            "pct_lt100_trials_within_60rdmi": clean(g.get("l100")), "mean_trials_within_60rdmi": clean(g.get("t60")),
            "pct_gt60rdmi_nci": clean(g.get("g60n")), "pct_gt60rdmi_broad_menu": clean(g.get("g60b")),
            "median_road_mi_nci": clean(g.get("medn")), "median_road_mi_broad_menu": clean(g.get("medb")),
            # the contract's short names, for readers of the "Ask the map" worker
            "pct_lt20": clean(g["l20"]), "pct_zero": clean(g["z60"]), "mean_trials_60": clean(g.get("t60"))}

def onc_summary(o, level):
    """The oncologists block of a district, state or national row (oncologists.js districts / states / nat)."""
    if not o: return None
    c2c = o.get("c2_counties"); c2n = c2c if isinstance(c2c, list) else (o.get("counties", {}).get("2") if level == "national" else c2c)
    out = {"count": o.get("onc"), "pct_pop55_in_counties_with_oncologists_no_trials": clean(o.get("c2")),
           "pct_pop55_in_counties_with_both": clean(o.get("c1")), "pct_pop55_in_counties_with_trials_no_oncologist": clean(o.get("c3")),
           "pct_pop55_in_counties_with_neither": clean(o.get("c4")), "counties_with_oncologists_no_trials": c2n}
    if o.get("per100k") is not None: out["oncologists_per_100k_pop55"] = clean(o["per100k"])
    if level == "national": out["counties_by_class"] = {str(k): v for k, v in o.get("counties", {}).items()}
    for k in ("rad", "gyn", "surg"):
        if o.get(k) is not None: out[{"rad": "radiation", "gyn": "gynecologic", "surg": "surgical"}[k]] = o[k]
    return out

def fnum(v, nd=1, dist=False):
    """A number from a CSV cell, rounded to nd decimals (nd=0: an int), or None when blank / NaN.
    dist=True marks a road-distance field (median_road_mi_*, road_mi_*), where 999 is the pipeline's "no road route" sentinel
    (NOROAD in route_us.py; never a real distance) and becomes null. Trial counts must NOT pass through that check: a dense district
    can have 1,000+ trials within 60 road-miles (CA-30: 1,090; New Jersey as a whole: 1,039), and treating those as the sentinel
    nulled wmean_trials_within_60rdmi for 48 districts and one state."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or (dist and f >= 999): return None   # NaN, or the "no road route" sentinel on a distance field
    return round(f, nd) if nd else int(round(f))

def read_csv(p):
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))

def main():
    D = load_js("data.js"); C = load_js("cosponsors.js")
    RU = load_js("rucc.js", True); MO = load_js("mortality.js", True); ON = load_js("oncologists.js", True); BU = load_js("burden.js", True)   # the map's other layers (each optional)
    meta = D["meta"]; data_as_of = str(meta.get("registry_data_timestamp") or meta.get("pull"))[:10]
    BSITES = meta["burden"]["sites"]; IPER = meta["burden"]["period"]; ISMALL = meta["burden"].get("small_threshold", 16)
    MSITES = MO["meta"]["sites"] if MO else BSITES; MPER = MO["meta"]["period"] if MO else None; MSMALL = MO["meta"].get("small_threshold", 16) if MO else 16
    inc_median = BU["meta"]["medians"]["all"] if BU else None                                   # "high incidence": rate above this (map: highOf, rate > median)
    mort_cut = (MO["meta"]["tertiles"].get("all") or [None, None])[1] if MO else None          # "high mortality": rate at or above the upper tertile (map: rate >= cut)
    onc_fields = ON["meta"]["fields"] if ON else []; onc_labels = ON["meta"]["categories"] if ON else {}
    rucc_labels = (RU["meta"].get("labels") or {}) if RU else {}

    def published_inc(binc):   # a state's / the nation's published State Cancer Profiles rates (data.js binc: site -> [rate, cases, status])
        if not binc: return None
        a = binc.get("all") or [None, None, None]
        return {"all": clean(a[0]), "cases_per_year": clean(a[1]), "period": IPER, "by_site": {k: clean((binc.get(k) or [None])[0]) for k, _ in BSITES}}
    def split_of(g):   # the metro / nonmetro halves of a state or the nation (rucc.js)
        return {"metro": rucc_group(g.get("metro")) if g else None, "nonmetro": rucc_group(g.get("nonmetro")) if g else None}
    def nonmetro_pct_of(g):
        if not g or not g.get("metro"): return None
        m = g["metro"]["p"]; nm = g["nonmetro"]["p"] if g.get("nonmetro") else 0
        return (math.floor(100 * nm / (m + nm) * 10 + 0.5) / 10) if m + nm else None   # the map's pct(): Math.round(v*10)/10
    usps_of_fips = {}
    # state FIPS -> USPS from state_data (each carries its fips)
    for usps, sd in D["state_data"].items():
        usps_of_fips[sd["fips"]] = usps
    state_name = {usps: sd["name"] for usps, sd in D["state_data"].items()}

    ctx_keys = {"veh": "no_vehicle", "bb": "broadband", "unins": "uninsured", "unins55": "uninsured_55_64", "pov": "poverty"}
    def ctx_of(c): return {v: c.get(k) for k, v in ctx_keys.items() if c and c.get(k) is not None} if c else {}

    common = {"data_as_of": data_as_of, "source": "ClinicalTrials.gov (registry), Census Bureau (tracts, ACS), NCI; see methods", "license": LICENSE["data"],
              "cite": LICENSE["attribution"], "methods": SITE + "methods.html#methods"}

    def core(row, pop_key="pop55"):
        pop = int(float(row[pop_key]))
        l20 = fnum(row["pct_lt20_trials_within_60rdmi"])
        return {"pop55": pop,
                "pct_lt20_trials_within_60rdmi": l20,
                "people_lt20_trials_within_60rdmi": int(round(pop * l20 / 100)) if l20 is not None else None,
                "pct_zero_trials_within_60rdmi": fnum(row["pct_zero_trials_within_60rdmi"]),
                "people_zero_trials_within_60rdmi": int(round(pop * fnum(row["pct_zero_trials_within_60rdmi"]) / 100)) if fnum(row["pct_zero_trials_within_60rdmi"]) is not None else None,
                "pct_lt100_trials_within_60rdmi": fnum(row["pct_lt100_trials_within_60rdmi"]),
                "pct_gt60rdmi_broad_menu": fnum(row["pct_gt60rdmi_broad_menu"]),
                "pct_gt60rdmi_nci": fnum(row["pct_gt60rdmi_nci"]),
                "median_road_mi_nci": fnum(row["median_road_mi_nci"], 0, dist=True),
                "median_road_mi_broad_menu": fnum(row["median_road_mi_broad_menu"], 0, dist=True),
                "wmean_trials_within_60rdmi": fnum(row["wmean_trials_within_60rdmi"], 0),   # a count: no sentinel (see fnum)
                "nearest_nci": row.get("modal_nearest_nci") or None,
                "nearest_broad_menu": row.get("modal_nearest_broad") or None}

    def by_type(row):
        out = {}
        for k, v in row.items():
            if k.startswith("wmean_t60_cancer_type_"):
                t = k[len("wmean_t60_cancer_type_"):]
                if t not in ("multi", "other_unclassified"): out[t] = fnum(v, 0)
        return out

    # ---- national ----
    nat = json.load(open(ROOT / "out_adult55" / "national_metrics_v3.json"))
    nat_row = {k: (v if not isinstance(v, (list, dict)) else json.dumps(v)) for k, v in nat.items()}
    nat_ctx = meta.get("nat_ctx") or {}
    national = {"id": "US", "level": "national", "name": "United States", **core(nat_row),
                "trials_listed_here": meta["trials"], "facilities": meta["facilities"],
                "trials_within_60rdmi_by_cancer_type": by_type(nat_row), "context": ctx_of(nat_ctx),
                "nonmetro_pct": nonmetro_pct_of(RU["nat"] if RU else None), **split_of(RU["nat"] if RU else None),
                "incidence_all_sites": clean(nat_ctx.get("inc")), "incidence_all_sites_cases_per_year": clean(nat_ctx.get("cases")),
                "incidence_published": published_inc(meta.get("nat_binc")),
                "oncologists": onc_summary(ON["nat"] if ON else None, "national"),
                "links": {"map": SITE + "map.html", "findings": SITE + "findings.html"}, **common}

    # ---- states ----
    # senators and the Senate bill (cosponsors.js: the tracked bill of type 's'; roles as the map's chips: sponsor, original cosponsor, cosponsor, none)
    sbills = [k for k, b in C["bills"].items() if b.get("type") == "s"]; sbill_key = sbills[0] if sbills else None; sbill = C["bills"][sbill_key] if sbill_key else None
    def senators_of(usps):
        out = []
        for bid in (C.get("senators") or {}).get(usps, []):
            m = C["members"].get(bid) or {}
            r = ((C["by_member"].get(bid) or {}).get(sbill_key) or {}).get("role") if sbill_key else None
            out.append({"name": m.get("name"), "party": m.get("party") or None, "bioguide": bid, "s4440": r or "none",
                        **({"bill": sbill["label"], "bill_url": sbill["url"]} if sbill else {})})
        return out
    states = {}
    for r in read_csv(ROOT / "out_adult55" / "state_metrics_v3.csv"):
        fips = r["state_fips"].zfill(2); usps = usps_of_fips.get(fips)
        if not usps: continue
        sd = D["state_data"][usps]; sctx = sd.get("ctx") or {}; ru = RU["states"].get(usps) if RU else None
        # trials_listed_here: state_data[usps].trials = distinct recruiting trials with a site in the state (the same figure as the union of
        # counties[f].tr over the state's counties; checked for all 51). `nt` is the state's census-tract count and was published here by mistake.
        states[usps] = {"id": usps, "level": "state", "name": state_name[usps], "state": usps, "fips": fips, **core(r),
                        "trials_listed_here": sd.get("trials"), "trials_within_60rdmi_by_cancer_type": by_type(r), "context": ctx_of(sd.get("ctx")),
                        "nonmetro_pct": nonmetro_pct_of(ru), **split_of(ru),
                        "incidence_all_sites": clean(sctx.get("inc")), "incidence_all_sites_cases_per_year": clean(sctx.get("cases")),
                        "incidence_published": published_inc(sd.get("binc")),
                        "oncologists": onc_summary(ON["states"].get(usps) if ON else None, "state"),
                        "senators": senators_of(usps),
                        "links": {"map": SITE + f"map.html?s={usps}", "brief": SITE + f"brief.html?s={usps}", "community": SITE + f"community.html?s={usps}"}, **common}

    # ---- districts ----
    bill = C["bills"]["ctma_hr"]; by_member = C["by_member"]; dmap = C["district_map"]
    def role(key):
        bid = dmap.get(key); r = (by_member.get(bid, {}).get("ctma_hr") or {}).get("role") if bid else None
        return r or "none"
    def district_trials(fips_list):
        """Distinct recruiting trials with a site in any county overlapping the district: the union of counties[f].tr (indices into the trial
        list, so the same trial in two of the district's counties is counted once). A county shared by two districts contributes its trials to
        both, so district figures do not add up to the state's. (D.districts[key].nt is the tract count and was published here by mistake.)"""
        seen = set()
        for f in fips_list:
            seen.update((D["counties"].get(f) or {}).get("tr") or [])
        return len(seen)
    districts = {}
    districts_of_county = defaultdict(list)   # FIPS -> API district ids (TX-15 form) that overlap it: the inverse of each district's `counties` list
    for r in read_csv(ROOT / "out_adult55" / "district_metrics_v3.csv"):
        key = r["cd_geoid"].zfill(4); dd = D["districts"].get(key)
        if not dd: continue
        usps = dd["st"]; cd = dd["cd"]; num = "00" if cd in ("0", "98", "At-large", "AL") or not str(cd).isdigit() else f"{int(cd):02d}"
        did = f"{usps}-{num}"
        ordinal = "at-large" if num == "00" else f"{int(num)}{'th' if 11 <= int(num) % 100 <= 13 else {1:'st',2:'nd',3:'rd'}.get(int(num) % 10, 'th')}"
        for f in dd.get("counties", []): districts_of_county[f].append(did)
        districts[did] = {"id": did, "level": "district", "name": f"{dd['stname']} {ordinal}", "state": usps, "geoid": key, "plan": meta.get("plan"), **core(r),
                          "trials_listed_here": district_trials(dd.get("counties", [])), "trials_within_60rdmi_by_cancer_type": by_type(r), "context": ctx_of(dd.get("ctx")),
                          "member": {"name": dd.get("member") or None, "party": dd.get("party") or None, "ctma_hr3521": role(key),
                                     "bill": bill["label"], "bill_url": bill["url"]},
                          "counties": dd.get("counties", []),
                          "nonmetro_pct": clean((RU["districts"].get(key) or {}).get("nonmetro_pct")) if RU else None,
                          "incidence_all_sites": clean((dd.get("ctx") or {}).get("inc")), "incidence_all_sites_cases_per_year": clean((dd.get("ctx") or {}).get("cases")),
                          "oncologists": onc_summary(ON["districts"].get(key) if ON else None, "district"),
                          "links": {"map": SITE + f"map.html?d={key}", "brief": SITE + f"brief.html?d={key}", "community": SITE + f"community.html?d={key}"}, **common}

    # ---- counties: shares from the tract table, population-weighted ----
    agg = defaultdict(lambda: {"pop": 0, "z60": 0, "l20": 0, "l100": 0, "gb60": 0, "gn60": 0, "nr_b": 0, "nr_n": 0, "t60w": 0.0, "mi_b": [], "mi_n": []})
    with open(ROOT / "out_adult55" / "tract_access.csv", newline="", encoding="utf-8") as fh:
        for t in csv.DictReader(fh):
            p = int(float(t["pop55"] or 0))
            if p <= 0: continue
            a = agg[t["county_fips"].zfill(5)]; n60 = int(float(t["trials_within_60rdmi"] or 0))
            a["pop"] += p; a["t60w"] += p * n60
            if n60 == 0: a["z60"] += p
            if n60 < 20: a["l20"] += p
            if n60 < 100: a["l100"] += p
            mb, mn = fnum(t["road_mi_broad"], 3, dist=True), fnum(t["road_mi_nci"], 3, dist=True)   # 999 = no road route -> counted in nr_b / nr_n
            if mb is None: a["nr_b"] += p
            else:
                a["mi_b"].append((mb, p))
                if mb > 60: a["gb60"] += p
            if mn is None: a["nr_n"] += p
            else:
                a["mi_n"].append((mn, p))
                if mn > 60: a["gn60"] += p
    def wmedian(pairs):
        if not pairs: return None
        pairs.sort(); tot = sum(w for _, w in pairs); acc = 0
        for v, w in pairs:
            acc += w
            if acc >= tot / 2: return int(round(v))
    def county_layers(fips, c):
        """The data behind the map's other county layers: rural code, road distances from the population center, incidence, deaths, oncologists."""
        ru = RU["county"].get(fips) if RU else None; code = ru.get("c") if ru else None
        inc = burden_record(c.get("b"), BSITES, IPER, ISMALL, "cases")
        mort = burden_record(MO["county"].get(fips) if MO else None, MSITES, MPER, MSMALL, "deaths")
        o = ON["county"].get(fips) if ON else None; orec = dict(zip(onc_fields, o)) if o else None
        # the map's oncCat: oncologists present? trials in the county? -> 1 both, 2 oncologists no trials, 3 trials no oncologist, 4 neither
        ocls = (1 if c.get("t") else 2) if orec and orec.get("onc") else (3 if c.get("t") else 4) if orec else None
        return {"rucc": code, "rucc_label": rucc_labels.get(str(code)) if code is not None else None, "metro": (code <= 3) if code is not None else None,
                "road_mi_nci_from_center": clean(c.get("rn")), "road_mi_broad_menu_from_center": clean(c.get("rb")), "road_mi_limited_menu_from_center": clean(c.get("rl")),
                "no_road_route_reason": c.get("noroad") or None,
                "drive_hours_nci": clean(c.get("hn")), "drive_hours_broad_menu": clean(c.get("hb")),
                "trials_within_60rdmi_of_center": c.get("t60"), "facilities_within_60rdmi_of_center": c.get("f60"),
                "incidence": inc, "mortality": mort,
                "oncologists": {"count": orec["onc"], "radiation": orec.get("rad"), "gynecologic": orec.get("gyn"), "surgical": orec.get("surg"),
                                "within_60rdmi": orec.get("onc_within_60rdmi"), "class": ocls, "class_label": onc_labels.get(str(ocls)),
                                "all_also_elsewhere": bool(orec.get("all_also_elsewhere"))} if orec else None,
                "incidence_above_county_median": (inc["all"] > inc_median) if inc["all"] is not None and inc_median is not None else None,
                "mortality_top_third": (mort["all"] >= mort_cut) if mort["all"] is not None and mort_cut is not None else None}

    counties = {}
    for fips, c in D["counties"].items():
        a = agg.get(fips); usps = usps_of_fips.get(c["s"])
        pop = a["pop"] if a else c.get("p", 0)
        pct = lambda k: round(100 * a[k] / a["pop"], 1) if a and a["pop"] else None
        l20 = pct("l20")
        counties[fips] = {"id": fips, "level": "county", "name": f"{c['nl']}, {state_name.get(usps, '')}".strip(", "), "state": usps,
                          "pop55": pop,
                          "pct_lt20_trials_within_60rdmi": l20,
                          "people_lt20_trials_within_60rdmi": int(round(pop * l20 / 100)) if l20 is not None else None,
                          "pct_zero_trials_within_60rdmi": pct("z60"),
                          "people_zero_trials_within_60rdmi": int(round(pop * pct("z60") / 100)) if pct("z60") is not None else None,
                          "pct_lt100_trials_within_60rdmi": pct("l100"),
                          "pct_gt60rdmi_broad_menu": round(100 * (a["gb60"] + a["nr_b"]) / a["pop"], 1) if a and a["pop"] else None,
                          "pct_gt60rdmi_nci": round(100 * (a["gn60"] + a["nr_n"]) / a["pop"], 1) if a and a["pop"] else None,
                          "median_road_mi_nci": wmedian(a["mi_n"]) if a else None,
                          "median_road_mi_broad_menu": wmedian(a["mi_b"]) if a else None,
                          "wmean_trials_within_60rdmi": int(round(a["t60w"] / a["pop"])) if a and a["pop"] else None,
                          "trials_listed_here": c.get("t", 0), "facilities": c.get("f", 0),
                          "nearest_nci": c.get("nn") or None, "nearest_broad_menu": c.get("nbm") or None,
                          "context": ctx_of(c.get("acs")),
                          "districts": sorted(districts_of_county.get(fips, [])),   # the districts whose `counties` list names this county
                          **county_layers(fips, c),
                          "links": {"map": SITE + f"map.html?c={fips}", "brief": SITE + f"brief.html?c={fips}", "community": SITE + f"community.html?c={fips}", "trials": SITE + f"trials.html?county={fips}"},
                          **common}

    # ---- write ----
    for sub in ("state", "district", "county"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    def dump(p, obj): p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    dump(OUT / "national.json", national)
    for k, v in states.items(): dump(OUT / "state" / f"{k}.json", v)
    for k, v in districts.items(): dump(OUT / "district" / f"{k}.json", v)
    for k, v in counties.items(): dump(OUT / "county" / f"{k}.json", v)
    dump(OUT / "all_states.json", list(states.values()))
    dump(OUT / "all_districts.json", list(districts.values()))
    dump(OUT / "all_counties.json", list(counties.values()))
    dump(OUT / "county_names.json", [[c["id"], c["name"], c["state"], c["pop55"]] for c in counties.values()])   # small: resolve a county name to its FIPS without the 9 MB table
    # ask/: compact tables for the "Ask the map" worker (a 10 ms CPU budget cannot parse the 9 MB table). counties.json holds every
    # county field the worker ranks or filters on, as one `cols` array and one array per county; by-site rates live in county_sites.json.
    (OUT / "ask").mkdir(parents=True, exist_ok=True)
    def nested(c, *path):
        cur = c
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
            if cur is None:
                return None
        return cur
    ASK_COLS = [("id", lambda c: c["id"]), ("name", lambda c: c["name"]), ("state", lambda c: c["state"]), ("pop55", lambda c: c["pop55"]),
                ("pct_lt20_trials_within_60rdmi", lambda c: c["pct_lt20_trials_within_60rdmi"]), ("people_lt20_trials_within_60rdmi", lambda c: c["people_lt20_trials_within_60rdmi"]),
                ("pct_zero_trials_within_60rdmi", lambda c: c["pct_zero_trials_within_60rdmi"]), ("people_zero_trials_within_60rdmi", lambda c: c["people_zero_trials_within_60rdmi"]),
                ("pct_lt100_trials_within_60rdmi", lambda c: c["pct_lt100_trials_within_60rdmi"]), ("pct_gt60rdmi_broad_menu", lambda c: c["pct_gt60rdmi_broad_menu"]), ("pct_gt60rdmi_nci", lambda c: c["pct_gt60rdmi_nci"]),
                ("median_road_mi_nci", lambda c: c["median_road_mi_nci"]), ("median_road_mi_broad_menu", lambda c: c["median_road_mi_broad_menu"]), ("wmean_trials_within_60rdmi", lambda c: c["wmean_trials_within_60rdmi"]),
                ("trials_listed_here", lambda c: c["trials_listed_here"]), ("facilities", lambda c: c["facilities"]), ("nearest_nci", lambda c: c["nearest_nci"]), ("nearest_broad_menu", lambda c: c["nearest_broad_menu"]),
                ("context.no_vehicle", lambda c: nested(c, "context", "no_vehicle")), ("context.broadband", lambda c: nested(c, "context", "broadband")), ("context.uninsured", lambda c: nested(c, "context", "uninsured")), ("context.uninsured_55_64", lambda c: nested(c, "context", "uninsured_55_64")), ("context.poverty", lambda c: nested(c, "context", "poverty")),
                ("rucc", lambda c: c.get("rucc")), ("rucc_label", lambda c: c.get("rucc_label")), ("metro", lambda c: c.get("metro")),
                ("road_mi_nci_from_center", lambda c: c.get("road_mi_nci_from_center")), ("road_mi_broad_menu_from_center", lambda c: c.get("road_mi_broad_menu_from_center")), ("road_mi_limited_menu_from_center", lambda c: c.get("road_mi_limited_menu_from_center")),
                ("drive_hours_nci", lambda c: c.get("drive_hours_nci")), ("drive_hours_broad_menu", lambda c: c.get("drive_hours_broad_menu")), ("trials_within_60rdmi_of_center", lambda c: c.get("trials_within_60rdmi_of_center")), ("facilities_within_60rdmi_of_center", lambda c: c.get("facilities_within_60rdmi_of_center")), ("no_road_route_reason", lambda c: c.get("no_road_route_reason")),
                ("incidence.all", lambda c: nested(c, "incidence", "all")), ("incidence.cases_per_year", lambda c: nested(c, "incidence", "cases_per_year")), ("incidence.small_numbers", lambda c: nested(c, "incidence", "small_numbers")), ("incidence.status", lambda c: nested(c, "incidence", "status")), ("incidence.period", lambda c: nested(c, "incidence", "period")),
                ("mortality.all", lambda c: nested(c, "mortality", "all")), ("mortality.deaths_per_year", lambda c: nested(c, "mortality", "deaths_per_year")), ("mortality.small_numbers", lambda c: nested(c, "mortality", "small_numbers")), ("mortality.status", lambda c: nested(c, "mortality", "status")), ("mortality.period", lambda c: nested(c, "mortality", "period")),
                ("oncologists.count", lambda c: nested(c, "oncologists", "count")), ("oncologists.within_60rdmi", lambda c: nested(c, "oncologists", "within_60rdmi")), ("oncologists.class", lambda c: nested(c, "oncologists", "class")), ("oncologists.class_label", lambda c: nested(c, "oncologists", "class_label")),
                ("incidence_above_county_median", lambda c: c.get("incidence_above_county_median")), ("mortality_top_third", lambda c: c.get("mortality_top_third")),
                ("districts", lambda c: c["districts"])]   # a list (the only non-scalar column); the worker's expandCounties copies any column value as is
    dump(OUT / "ask" / "counties.json", {"cols": [k for k, _ in ASK_COLS], "data_as_of": data_as_of, "rows": [[f(c) for _, f in ASK_COLS] for c in counties.values()]})
    site_keys = [k for k, _ in BSITES]
    dump(OUT / "ask" / "county_sites.json", {"sites": site_keys, "data_as_of": data_as_of,
                                             "rows": {fips: [[(nested(c, "incidence", "by_site") or {}).get(k) for k in site_keys], [(nested(c, "mortality", "by_site") or {}).get(k) for k in site_keys]] for fips, c in counties.items()}})   # [incidence rates, death rates] in `sites` order; null = not published
    index = {"name": "Cancer Clinical Trial Access Map data API", "built": datetime.date.today().isoformat(), "data_as_of": data_as_of,
             "base_url": SITE + "api/", "docs": SITE + "api.html",
             "files": {"national": "national.json", "state": "state/{USPS}.json", "district": "district/{USPS}-{NN}.json (NN = 00 for at-large)",
                       "county": "county/{FIPS5}.json", "county_names": "county_names.json (array of [FIPS5, name, state, pop55])", "ask": {"counties": "ask/counties.json (compact: cols + one array per county, every county field except the by-site rates; for the question box)", "county_sites": "ask/county_sites.json ({sites: [...], rows: {FIPS5: [[incidence rate per site], [death rate per site]]}})"}, "tables": ["all_states.json", "all_districts.json", "all_counties.json"]},
             "counts": {"states": len(states), "districts": len(districts), "counties": len(counties)},
             "fields": FIELDS, "definitions": SITE + "methods.html#terms", "license": LICENSE,
             "thresholds": {"incidence_county_median_all_sites": inc_median, "mortality_top_third_cut_all_sites": mort_cut,
                            "incidence_period": IPER, "mortality_period": MPER, "small_numbers_below_per_year": ISMALL,
                            "incidence_sites": [k for k, _ in BSITES], "site_labels": {k: v for k, v in BSITES},
                            "rucc_labels": rucc_labels, "oncologist_classes": onc_labels, "senate_bill": sbill["label"] if sbill else None},
             "ids": {"states": sorted(states), "districts": sorted(districts)}}
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"api: {len(states)} states, {len(districts)} districts, {len(counties)} counties -> {OUT}/ (data as of {data_as_of})")

if __name__ == "__main__":
    main()
