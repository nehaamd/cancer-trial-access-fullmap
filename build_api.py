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
import json, csv, datetime, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "api"
SITE = "https://nehaamd.github.io/cancer-trial-access-fullmap/"   # the published address; change in one place if the site gets a domain
LICENSE = {"data": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/",
           "attribution": "Agrawal N. Cancer Trial Access Map. " + SITE}

FIELDS = {
    "id": "Place identifier: 5-digit county FIPS, USPS-number for a district (XX-00 is at-large), USPS code for a state, US for the nation.",
    "level": "county, district, state or national.",
    "name": "Place name. Districts: 'Texas 34th'; counties: 'Hidalgo County, Texas'.",
    "state": "USPS code of the state.",
    "pop55": "Residents aged 55 and older (ACS 5-year, summed from census tracts).",
    "pct_lt20_trials_within_60rdmi": "Share (%) of residents 55+ with fewer than 20 recruiting cancer treatment trials within 60 road-miles of home. The site's headline 'short of trials' measure.",
    "people_lt20_trials_within_60rdmi": "The same, as a count of people.",
    "pct_zero_trials_within_60rdmi": "Share (%) with no recruiting trial within 60 road-miles.",
    "pct_lt100_trials_within_60rdmi": "Share (%) with fewer than 100 trials within 60 road-miles.",
    "pct_gt60rdmi_broad_menu": "Share (%) living more than 60 road-miles from a county with 100 or more recruiting trials (a 'broad menu').",
    "pct_gt60rdmi_nci": "Share (%) living more than 60 road-miles from an NCI-designated cancer center.",
    "median_road_mi_nci": "Median road miles from home to the nearest NCI-designated center (residents with a road route).",
    "median_road_mi_broad_menu": "Median road miles to the nearest broad-menu county.",
    "wmean_trials_within_60rdmi": "Population-weighted mean number of recruiting trials within 60 road-miles.",
    "trials_listed_here": "Recruiting trials with at least one site in the place (county: in the county; district and state: in any county of it).",
    "nearest_nci": "The NCI-designated center nearest to most residents.",
    "nearest_broad_menu": "The broad-menu county nearest to most residents.",
    "trials_within_60rdmi_by_cancer_type": "Population-weighted mean trials within 60 road-miles, by cancer type (district and state only).",
    "context": "ACS context: no_vehicle, broadband, uninsured, uninsured_55_64, poverty, all in %, population-weighted.",
    "member": "Districts only: the House member, party, and cosponsorship of the Clinical Trial Modernization Act (H.R. 3521): sponsor, original, cosponsor, or none.",
    "counties": "Districts only: the FIPS codes of counties that overlap the district.",
    "links": "map: the map opened on this place; brief: the printable brief for it.",
    "data_as_of": "Registry data date of the ClinicalTrials.gov pull these figures come from.",
}

def load_js(name):
    s = (ROOT / "docs" / name).read_text(encoding="utf-8")
    return json.loads(s.split("=", 1)[1].strip().rstrip(";"))

def fnum(v, nd=1):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f >= 999: return None   # NaN or the "no road route" sentinel
    return round(f, nd) if nd else int(round(f))

def read_csv(p):
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))

def main():
    D = load_js("data.js"); C = load_js("cosponsors.js")
    meta = D["meta"]; data_as_of = str(meta.get("registry_data_timestamp") or meta.get("pull"))[:10]
    usps_of_fips = {}
    # state FIPS -> USPS from state_data (each carries its fips)
    for usps, sd in D["state_data"].items():
        usps_of_fips[sd["fips"]] = usps
    state_name = {usps: sd["name"] for usps, sd in D["state_data"].items()}

    ctx_keys = {"veh": "no_vehicle", "bb": "broadband", "unins": "uninsured", "unins55": "uninsured_55_64", "pov": "poverty"}
    def ctx_of(c): return {v: c.get(k) for k, v in ctx_keys.items() if c and c.get(k) is not None} if c else {}

    common = {"data_as_of": data_as_of, "source": "ClinicalTrials.gov (registry), Census Bureau (tracts, ACS), NCI; see methods", "license": LICENSE["data"],
              "cite": LICENSE["attribution"], "methods": SITE + "map.html#methods"}

    def core(row, pop_key="pop55"):
        pop = int(float(row[pop_key]))
        l20 = fnum(row["pct_lt20_trials_within_60rdmi"])
        return {"pop55": pop,
                "pct_lt20_trials_within_60rdmi": l20,
                "people_lt20_trials_within_60rdmi": int(round(pop * l20 / 100)) if l20 is not None else None,
                "pct_zero_trials_within_60rdmi": fnum(row["pct_zero_trials_within_60rdmi"]),
                "pct_lt100_trials_within_60rdmi": fnum(row["pct_lt100_trials_within_60rdmi"]),
                "pct_gt60rdmi_broad_menu": fnum(row["pct_gt60rdmi_broad_menu"]),
                "pct_gt60rdmi_nci": fnum(row["pct_gt60rdmi_nci"]),
                "median_road_mi_nci": fnum(row["median_road_mi_nci"], 0),
                "median_road_mi_broad_menu": fnum(row["median_road_mi_broad_menu"], 0),
                "wmean_trials_within_60rdmi": fnum(row["wmean_trials_within_60rdmi"], 0),
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
    national = {"id": "US", "level": "national", "name": "United States", **core(nat_row),
                "trials_listed_here": meta["trials"], "facilities": meta["facilities"],
                "trials_within_60rdmi_by_cancer_type": by_type(nat_row), "context": ctx_of(meta.get("nat_ctx")),
                "links": {"map": SITE + "map.html", "findings": SITE + "findings.html"}, **common}

    # ---- states ----
    states = {}
    for r in read_csv(ROOT / "out_adult55" / "state_metrics_v3.csv"):
        fips = r["state_fips"].zfill(2); usps = usps_of_fips.get(fips)
        if not usps: continue
        sd = D["state_data"][usps]
        states[usps] = {"id": usps, "level": "state", "name": state_name[usps], "state": usps, "fips": fips, **core(r),
                        "trials_listed_here": sd.get("nt"), "trials_within_60rdmi_by_cancer_type": by_type(r), "context": ctx_of(sd.get("ctx")),
                        "links": {"map": SITE + f"map.html?s={usps}", "brief": SITE + f"brief.html?s={usps}", "community": SITE + f"community.html?s={usps}"}, **common}

    # ---- districts ----
    bill = C["bills"]["ctma_hr"]; by_member = C["by_member"]; dmap = C["district_map"]
    def role(key):
        bid = dmap.get(key); r = (by_member.get(bid, {}).get("ctma_hr") or {}).get("role") if bid else None
        return r or "none"
    districts = {}
    for r in read_csv(ROOT / "out_adult55" / "district_metrics_v3.csv"):
        key = r["cd_geoid"].zfill(4); dd = D["districts"].get(key)
        if not dd: continue
        usps = dd["st"]; cd = dd["cd"]; num = "00" if cd in ("0", "98", "At-large", "AL") or not str(cd).isdigit() else f"{int(cd):02d}"
        did = f"{usps}-{num}"
        ordinal = "at-large" if num == "00" else f"{int(num)}{'th' if 11 <= int(num) % 100 <= 13 else {1:'st',2:'nd',3:'rd'}.get(int(num) % 10, 'th')}"
        districts[did] = {"id": did, "level": "district", "name": f"{dd['stname']} {ordinal}", "state": usps, "geoid": key, "plan": meta.get("plan"), **core(r),
                          "trials_listed_here": dd.get("nt"), "trials_within_60rdmi_by_cancer_type": by_type(r), "context": ctx_of(dd.get("ctx")),
                          "member": {"name": dd.get("member") or None, "party": dd.get("party") or None, "ctma_hr3521": role(key),
                                     "bill": bill["label"], "bill_url": bill["url"]},
                          "counties": dd.get("counties", []),
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
            mb, mn = fnum(t["road_mi_broad"], 3), fnum(t["road_mi_nci"], 3)
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
                          "pct_zero_trials_within_60rdmi": pct("z60"), "pct_lt100_trials_within_60rdmi": pct("l100"),
                          "pct_gt60rdmi_broad_menu": round(100 * (a["gb60"] + a["nr_b"]) / a["pop"], 1) if a and a["pop"] else None,
                          "pct_gt60rdmi_nci": round(100 * (a["gn60"] + a["nr_n"]) / a["pop"], 1) if a and a["pop"] else None,
                          "median_road_mi_nci": wmedian(a["mi_n"]) if a else None,
                          "median_road_mi_broad_menu": wmedian(a["mi_b"]) if a else None,
                          "wmean_trials_within_60rdmi": int(round(a["t60w"] / a["pop"])) if a and a["pop"] else None,
                          "trials_listed_here": c.get("t", 0), "facilities": c.get("f", 0),
                          "nearest_nci": c.get("nn") or None, "nearest_broad_menu": c.get("nbm") or None,
                          "context": ctx_of(c.get("acs")),
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
    index = {"name": "Cancer Trial Access Map data API", "built": datetime.date.today().isoformat(), "data_as_of": data_as_of,
             "base_url": SITE + "api/", "docs": SITE + "api.html",
             "files": {"national": "national.json", "state": "state/{USPS}.json", "district": "district/{USPS}-{NN}.json (NN = 00 for at-large)",
                       "county": "county/{FIPS5}.json", "tables": ["all_states.json", "all_districts.json", "all_counties.json"]},
             "counts": {"states": len(states), "districts": len(districts), "counties": len(counties)},
             "fields": FIELDS, "definitions": SITE + "map.html#methods", "license": LICENSE,
             "ids": {"states": sorted(states), "districts": sorted(districts)}}
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"api: {len(states)} states, {len(districts)} districts, {len(counties)} counties -> {OUT}/ (data as of {data_as_of})")

if __name__ == "__main__":
    main()
