"""Build the v3 web-app payload: docs/data.js (window.DATA) and docs/geo.js (window.GEO). Static; no backend.

Facility definition (Tier 1.1): a distinct recruiting facility = distinct (normalised facility name, county). Registry facility
names are free text, so two spellings of one hospital can count twice and one name can cover two campuses; the count is
therefore approximate and is labelled as "facilities (registry-listed, deduplicated by name)".
"""
import json, re
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import mapping
from tract_metrics_us import load_trials, PHASE_MAP, SPONSOR_MAP
from classify_cancer_type import LABEL as CT_LABEL

REF, OUT, RAW, DOCS = Path("data/ref"), Path("out_adult55"), Path("data/raw"), Path("docs"); DOCS.mkdir(exist_ok=True)
STFIPS = {"AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
          "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
          "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56"}
INV = {v: k for k, v in STFIPS.items()}
NOROAD = 999.0
SITECODE = re.compile(r"\(?\s*(site|study site|local institution|investigative site|clinical site|id|site id|site number|site #)\s*[-#:]?\s*\d+[a-z]?\s*\)?|\(\s*\d{3,6}\s*\)|/\s*id#?\s*\d+|\bsite\s+\d{2,6}\b", re.I)
def norm(x):
    """Facility key: lower-case, sponsor site codes removed ("( Site 0087)", "Local Institution - 0012", "/ID# 12345"), punctuation dropped."""
    y = SITECODE.sub(" ", str(x)); y = re.sub(r"[^a-z0-9 ]", " ", y.lower()); return re.sub(r"\s+", " ", y).strip()


def main():
    trials = load_trials(); j_of = {n: j for j, n in enumerate(trials.nct_id)}
    ctype = pd.read_csv(RAW / "trial_cancer_type.csv", dtype=str).set_index("nct_id")
    sites = pd.read_csv(OUT / "site_assignment_qc.csv", dtype=str).fillna(""); sites = sites[(sites.county_fips != "") & sites.nct_id.isin(j_of)].copy()
    sites["fac"] = sites.facility.map(norm)
    fetch_log = json.load(open(RAW / "fetch_log.json")); pull_date = fetch_log["timestamp_utc"][:10]
    # ---- trial table (compact arrays) ----
    types = sorted(trials.cancer_type.unique(), key=lambda c: (c == "other_unclassified", c == "multi", CT_LABEL[c]))
    t_idx = {c: i for i, c in enumerate(types)}; phases = ["1", "1-2", "2", "2-3", "3", "4", "NA"]; sponsors = ["industry", "academic_other", "nih_federal"]
    named_types = [c for c in types if c not in ("multi", "other_unclassified")]
    catmatch = ctype.categories_matched.reindex(trials.nct_id).fillna("")
    def cats_for(nct, primary):
        # every category the trial's registry conditions actually name (from the classifier's own matched-set), so a basket
        # trial that names colorectal is still returned by the "Colorectal" filter, even though its PRIMARY label is "multi".
        m = [c for c in str(catmatch.get(nct, "")).split(";") if c in t_idx]
        if m: return sorted({t_idx[c] for c in m})
        return [] if primary == "other_unclassified" else [t_idx[primary]]
    def age_years(x):
        m = re.match(r"([\d.]+)\s*(Year|Month|Week|Day)", str(x or ""), re.I)
        return None if not m else round(float(m.group(1)) / {"year": 1, "month": 12, "week": 52, "day": 365}[m.group(2).lower()], 1)
    T = {"id": trials.nct_id.tolist(), "title": trials.brief_title.tolist(), "ph": [phases.index(p) for p in trials.phase], "sp": [sponsors.index(s) for s in trials.sponsor],
         "spn": trials.get("lead_sponsor", pd.Series([""] * len(trials))).fillna("").tolist(), "iv": [x[:160] for x in trials.intervention_names.fillna("")], "ivt": trials.intervention_types.fillna("").tolist(),
         "amin": [age_years(x) for x in trials.minimum_age], "amax": [age_years(x) for x in trials.maximum_age], "start": trials.start_date.fillna("").tolist(),
         "upd": trials.get("last_update_posted", pd.Series([""] * len(trials))).fillna("").tolist(), "cc": [x[:140] for x in trials.get("central_contact", pd.Series([""] * len(trials))).fillna("")],
         "ct": [t_idx[c] for c in trials.cancer_type], "cats": [cats_for(n, c) for n, c in zip(trials.nct_id, trials.cancer_type)],
         "multi": [ctype.multi_subtype.get(n, "") if ctype.cancer_type.get(n) == "multi" else "" for n in trials.nct_id],
         "types": [[c, CT_LABEL[c]] for c in types], "named_types": named_types, "phases": phases, "sponsors": [["industry", "Industry"], ["academic_other", "Academic / other"], ["nih_federal", "NIH / federal"]]}
    # ---- per-county trial index and facilities ----
    ct_trials = sites.groupby("county_fips").nct_id.agg(lambda s: sorted({j_of[n] for n in s})).to_dict()
    # Site identity: key = (county, normalised name after removing sponsor site codes), then a reviewed alias list (data/ref/site_aliases.csv:
    # county_fips, alias_norm, canonical_norm) merges spellings a human has confirmed are the same place. Anonymous placeholders
    # ("Research Site", "Local Institution") cannot be resolved to a physical site and are flagged, not merged across sponsors.
    ALIAS = {}
    if (REF / "site_aliases.csv").exists():
        for r_ in pd.read_csv(REF / "site_aliases.csv", dtype=str).fillna("").itertuples(): ALIAS[(r_.county_fips, r_.alias_norm)] = r_.canonical_norm
    sites["fac"] = [ALIAS.get((c, f), f) for c, f in zip(sites.county_fips, sites.fac)]
    PLACEHOLDER = re.compile(r"^(research site|local institution|study site|clinical site|investigational site|investigative site|site|clinical research site|research facility|central recruiting site|recruiting site)$|^\s*$", re.I)
    fac = sites.groupby(["county_fips", "fac"]).agg(name=("facility", lambda s: s.value_counts().index[0]), city=("city", lambda s: s.value_counts().index[0]), zip=("zip", lambda s: s[s.str.len() == 5].value_counts().index[0] if (s.str.len() == 5).any() else ""),
                                                   trials=("nct_id", lambda s: sorted({j_of[n] for n in s})), n_rows=("nct_id", "size")).reset_index()
    fac["name"] = fac.name.map(lambda x: re.sub(r"\s+", " ", SITECODE.sub("", x)).strip(" -(),") or x)
    fac["unresolved"] = fac.fac.map(lambda f: int(bool(PLACEHOLDER.match(f))))
    fac = fac.sort_values(["county_fips", "fac"]).reset_index(drop=True); fac["site_id"] = [f"S{i:05d}" for i in range(len(fac))]
    fac_idx = {}; ct_fac = {}
    for f, g in fac.groupby("county_fips"):
        ct_fac[f] = []
        for r in g.itertuples(): fac_idx[(f, r.fac)] = len(ct_fac[f]); ct_fac[f].append([r.name, r.city, r.zip, r.trials, r.site_id, int(r.unresolved)])
    # candidate duplicates for human review (same county + ZIP, one normalised name contains the other) — NOT applied
    cands = []
    for (f, z), g in fac[fac.zip != ""].groupby(["county_fips", "zip"]):
        names = g.fac.tolist()
        for i in range(len(names)):
            for k in range(len(names)):
                if i != k and len(names[i]) >= 8 and names[i] in names[k] and not PLACEHOLDER.match(names[i]): cands.append({"county_fips": f, "zip": z, "shorter": names[i], "longer": names[k], "suggested_canonical": names[k]})
    pd.DataFrame(cands).drop_duplicates().to_csv(OUT / "site_alias_candidates.csv", index=False)
    fac[["site_id", "county_fips", "name", "city", "zip", "n_rows", "unresolved"]].to_csv(OUT / "sites_registry.csv", index=False)
    # ---- county metrics ----
    cm = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str, "state_fips": str}).set_index("county_fips")
    rd = pd.read_csv(OUT / "county_road_distances.csv", dtype={"county_fips": str, "state_fips": str}).set_index("county_fips")
    cov = pd.read_csv(REF / "county_covariates.csv", dtype={"county_fips": str}).set_index("county_fips")
    # facility-level routing (route_sites_us.py): the county's 60-road-mile pool is every *recruiting site* within 60 road-miles
    # of the county population center — not every county whose center is within 60 miles. Site points are ZIP/city-level locations.
    zs = np.load("data/roads/route_cache_sites.npz", allow_pickle=True)
    assert (zs["trial_ids"] == trials.nct_id.values).all(), "site cache trial order differs from trials table"
    SM = __import__("scipy.sparse", fromlist=["csr_matrix"]).csr_matrix((np.ones(len(zs["S_indices"]), np.int32), zs["S_indices"], zs["S_indptr"]), shape=tuple(zs["S_shape"]))
    SP = [sorted(SM.indices[SM.indptr[i]:SM.indptr[i + 1]].tolist()) for i in range(SM.shape[0])]  # site point -> trial indices
    SPF = [int(x) for x in zs["sp_n_facilities"]]
    cfips = list(zs["county_fips"]); pc = pd.DataFrame({"c": zs["pc_c"], "sp": zs["pc_src"], "mi": zs["pc_mi"]})
    nb60 = {cfips[c]: sorted(g.sp.tolist()) for c, g in pc[pc.mi <= 60].groupby("c")}
    nbd = {cfips[c]: [[int(a), int(round(b))] for a, b in sorted(zip(g.sp.tolist(), g.mi.tolist()), key=lambda x: x[1])] for c, g in pc.groupby("c")}  # all site points within 120 road-mi, nearest first
    # sitepoint -> facilities: [county_fips, index into that county's fac list]
    sg = pd.read_csv(OUT / "site_geocode_qc.csv", dtype=str).fillna(""); sg["fac"] = sg.facility.map(norm); sg["fac"] = [ALIAS.get((c, f), f) for c, f in zip(sg.county_fips, sg.fac)]
    SPI = [[] for _ in range(int(zs["S_shape"][0]))]
    for (spi, cf, fc), _ in sg.groupby(["sp", "county_fips", "fac"]):
        if (cf, fc) in fac_idx: SPI[int(spi)].append([cf, fac_idx[(cf, fc)]])
    pool60 = {f: len(set().union(*[set(SP[i]) for i in nb60.get(f, [])])) if nb60.get(f) else 0 for f in cm.index}
    fac60 = {f: sum(SPF[i] for i in nb60.get(f, [])) for f in cm.index}
    burden = pd.read_csv(REF / "cancer_incidence_county.csv", dtype={"county_fips": str})
    bsites = ["all", "breast", "colorectal", "lung", "prostate", "melanoma_skin", "lymphoma", "leukemia", "pancreatic", "liver_biliary", "bladder_urothelial", "kidney", "brain_cns",
              "gynecologic_ovary", "gynecologic_uterus", "gynecologic_cervix", "head_neck", "thyroid", "esophagus", "stomach"]
    btitle = burden.drop_duplicates("site").set_index("site").title.to_dict()
    bstat = {"ok": 0, "small_numbers": 1, "suppressed_source": 2, "not_available_state": 3, "not_available_county": 4}
    B = {}
    for f, g in burden.groupby("county_fips"):
        g = g.set_index("site"); B[f] = [[(None if pd.isna(g.loc[s, "rate"]) else round(float(g.loc[s, "rate"]), 1)), (None if pd.isna(g.loc[s, "ci_lo"]) else round(float(g.loc[s, "ci_lo"]), 1)),
                                         (None if pd.isna(g.loc[s, "ci_hi"]) else round(float(g.loc[s, "ci_hi"]), 1)), (None if pd.isna(g.loc[s, "avg_annual_count"]) else int(g.loc[s, "avg_annual_count"])),
                                         bstat[g.loc[s, "status"]]] if s in g.index else [None, None, None, None, 4] for s in bsites]
    counties = {}
    for f in cm.index:
        c = cm.loc[f]; r = rd.loc[f]; v = cov.loc[f] if f in cov.index else None
        def road(lab):
            mi = float(r[f"road_mi_{lab}"]); return None if mi >= NOROAD else round(mi)
        counties[f] = {"n": c.county_name, "s": str(c.state_fips).zfill(2), "p": int(c.pop55), "t": int(c.trials_in_county), "f": len(ct_fac.get(f, [])),
                       "tr": ct_trials.get(f, []), "fac": ct_fac.get(f, []), "nb": nb60.get(f, []), "nbd": nbd.get(f, []), "t60": pool60[f], "f60": fac60[f],
                       "rb": road("broad"), "rl": road("limited"), "rn": road("nci"), "hb": None if r.road_mi_broad >= NOROAD else round(float(r.drive_hr_broad), 1),
                       "hn": None if r.road_mi_nci >= NOROAD else round(float(r.drive_hr_nci), 1), "nn": r.nearest_nci, "nbm": r.nearest_broad,
                       "noroad": ("off" if "OFF ROAD" in str(r.nearest_nci) else "island" if "NO ROAD" in str(r.nearest_nci) or "NO ROAD" in str(r.nearest_broad) else ""),
                       "sl": {"b": round(float(c.dist_to_broad_mi)), "n": round(float(c.dist_to_nci_mi))},
                       "acs": None if v is None else {"veh": None if pd.isna(v.pct_hh_no_vehicle) else round(float(v.pct_hh_no_vehicle), 1), "net": None if pd.isna(v.pct_hh_no_internet) else round(float(v.pct_hh_no_internet), 1),
                                                     "bb": None if pd.isna(v.hh_broadband) or pd.isna(v.hh_total) or v.hh_total == 0 else round(100 * float(v.hh_broadband) / float(v.hh_total), 1),
                                                     "unins": None if pd.isna(v.uninsured_rate) else round(float(v.uninsured_rate), 1), "unins55": None if pd.isna(v.uninsured_rate_55_64) else round(float(v.uninsured_rate_55_64), 1),
                                                     "pov": None if pd.isna(v.poverty_rate) else round(float(v.poverty_rate), 1)},
                       "b": B.get(f)}
    # ---- districts ----
    dm = pd.read_csv(OUT / "district_metrics_v3.csv", dtype={"cd_geoid": str, "state_fips": str, "cd": str}).set_index("cd_geoid")
    old = pd.read_csv(OUT / "district_metrics.csv", dtype={"cd_geoid": str}).set_index("cd_geoid")  # v2 method (area weights, straight-line) for the "what changed" comparison
    legis = json.load(open(REF / "legislators-current.json")); repmap = {}
    for l in legis:
        t = l["terms"][-1]
        if t["type"] != "rep": continue
        sf = STFIPS.get(t["state"]);
        if not sf: continue
        d = t.get("district") or 0; repmap[f"{sf}{d:02d}"] = {"name": l["name"].get("official_full") or f'{l["name"]["first"]} {l["name"]["last"]}', "party": {"Republican": "R", "Democrat": "D"}.get(t["party"], "I")}
    repmap["1198"] = repmap.pop("1100", repmap.get("1198"))  # DC delegate: relationship file codes DC as district 98
    lead_hr3521 = {"4811"}  # verified 5 Sep 2026 (prior version); recheck on congress.gov before use
    st_name = dict(zip(cm.state_fips.astype(str).str.zfill(2), pd.read_csv(REF / "county_centroids.csv", dtype=str).drop_duplicates("state_fips").set_index("state_fips").state_name.reindex(cm.state_fips.astype(str).str.zfill(2).unique())))
    cent = pd.read_csv(REF / "county_centroids.csv", dtype=str); st_name = dict(zip(cent.state_fips, cent.state_name))
    tcols = {"ct": [c for c in dm.columns if c.startswith("wmean_t60_cancer_type_")], "ph": [c for c in dm.columns if c.startswith("wmean_t60_phase_")], "sp": [c for c in dm.columns if c.startswith("wmean_t60_sponsor_")]}
    def nz(v): return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)
    def ctx_of(r):  # residents-55+-weighted means of county values; *_cov = share of residents 55+ whose county has the value
        return {"veh": nz(r.acs_no_vehicle), "bb": nz(r.acs_broadband), "unins": nz(r.acs_uninsured), "unins55": nz(r.acs_uninsured_55_64), "pov": nz(r.acs_poverty), "acs_cov": nz(r.acs_no_vehicle_pop_covered_pct),
                "inc": nz(r.inc_all_rate), "inc_cov": nz(r.inc_all_rate_pop_covered_pct), "cases": None if pd.isna(r.inc_all_cases_sum) else int(r.inc_all_cases_sum)}
    def core_of(r):
        return {"p": int(r.pop55), "nt": int(r.n_tracts), "z60": float(r.pct_zero_trials_within_60rdmi), "l20": float(r.pct_lt20_trials_within_60rdmi), "l100": float(r.pct_lt100_trials_within_60rdmi), "zc": float(r.pct_in_zero_trial_county),
                "g60b": float(r.pct_gt60rdmi_broad_menu), "g120b": float(r.pct_gt120rdmi_broad_menu), "g60l": float(r.pct_gt60rdmi_limited_menu), "g60n": float(r.pct_gt60rdmi_nci), "g120n": float(r.pct_gt120rdmi_nci),
                "nr": float(r.pct_no_road_route_broad), "nrn": float(r.pct_no_road_route_nci), "medb": None if r.median_road_mi_broad_menu >= NOROAD else int(r.median_road_mi_broad_menu), "medn": None if r.median_road_mi_nci >= NOROAD else int(r.median_road_mi_nci),
                "medl": None if r.median_road_mi_limited_menu >= NOROAD else int(r.median_road_mi_limited_menu), "t30": int(r.wmean_trials_within_30rdmi), "t60": int(r.wmean_trials_within_60rdmi), "t120": int(r.wmean_trials_within_120rdmi), "own": int(r.wmean_trials_in_own_county),
                "mnci": r.modal_nearest_nci, "mbroad": r.modal_nearest_broad,
                "bd": {"ct": {c.replace("wmean_t60_cancer_type_", ""): int(r[c]) for c in tcols["ct"]}, "ph": {c.replace("wmean_t60_phase_", ""): int(r[c]) for c in tcols["ph"]}, "sp": {c.replace("wmean_t60_sponsor_", ""): int(r[c]) for c in tcols["sp"]}}}
    # ---- states ----
    sm = pd.read_csv(OUT / "state_metrics_v3.csv", dtype={"state_fips": str}).set_index("state_fips")
    sinc = pd.read_csv(REF / "cancer_incidence_state.csv", dtype={"state_fips": str}); sinc["st"] = sinc.state_fips.str[:2]
    states_d = {}
    for sf, r in sm.iterrows():
        usps = INV.get(sf);
        if not usps: continue
        sc = cm[cm.state_fips.astype(str).str.zfill(2) == sf]
        si = sinc[sinc.st == sf].set_index("site")
        binc = {site: ([None if pd.isna(si.loc[site, "rate"]) else round(float(si.loc[site, "rate"]), 1), None if pd.isna(si.loc[site, "avg_annual_count"]) else int(si.loc[site, "avg_annual_count"]), si.loc[site, "status"]] if site in si.index else [None, None, "not_available_state"]) for site in bsites}
        states_d[usps] = {**core_of(r), "name": st_name[sf], "fips": sf, "ctx": ctx_of(r), "ndist": int((dm.state_fips == sf).sum()), "counties": int(len(sc)), "counties_with_trials": int((sc.trials_in_county > 0).sum()),
                          "broad": int((sc.trials_in_county >= 100).sum()), "limited": int(((sc.trials_in_county >= 20) & (sc.trials_in_county < 100)).sum()),
                          "trials": int(len({j for f in sc.index for j in ct_trials.get(f, [])})), "fac": int(sum(len(ct_fac.get(f, [])) for f in sc.index)), "binc": binc}
    ccd_ = pd.read_csv(REF / "county_cd.csv", dtype=str); ccd_["share"] = ccd_.share.astype(float); d_counties = {k: sorted(g.county_fips.tolist()) for k, g in ccd_[ccd_.share > 0.001].groupby("cd_geoid")}
    districts = {}
    for k, r in dm.iterrows():
        m = repmap.get(k); sf = k[:2]
        districts[k] = {"st": INV[sf], "stname": st_name[sf], "cd": r.cd.lstrip("0") or "0", "p": int(r.pop55), "nt": int(r.n_tracts),
                        "z60": float(r.pct_zero_trials_within_60rdmi), "l20": float(r.pct_lt20_trials_within_60rdmi), "l100": float(r.pct_lt100_trials_within_60rdmi), "zc": float(r.pct_in_zero_trial_county),
                        "g60b": float(r.pct_gt60rdmi_broad_menu), "g120b": float(r.pct_gt120rdmi_broad_menu), "g60l": float(r.pct_gt60rdmi_limited_menu), "g60n": float(r.pct_gt60rdmi_nci), "g120n": float(r.pct_gt120rdmi_nci),
                        "nr": float(r.pct_no_road_route_broad), "nrn": float(r.pct_no_road_route_nci), "medb": None if r.median_road_mi_broad_menu >= NOROAD else int(r.median_road_mi_broad_menu),
                        "medn": None if r.median_road_mi_nci >= NOROAD else int(r.median_road_mi_nci), "t30": int(r.wmean_trials_within_30rdmi), "t60": int(r.wmean_trials_within_60rdmi), "t120": int(r.wmean_trials_within_120rdmi),
                        "own": int(r.wmean_trials_in_own_county), "mnci": r.modal_nearest_nci, "mbroad": r.modal_nearest_broad,
                        "bd": {"ct": {c.replace("wmean_t60_cancer_type_", ""): int(r[c]) for c in tcols["ct"]}, "ph": {c.replace("wmean_t60_phase_", ""): int(r[c]) for c in tcols["ph"]}, "sp": {c.replace("wmean_t60_sponsor_", ""): int(r[c]) for c in tcols["sp"]}},
                        "v2": {"g60b": float(old.loc[k, "pct_pop55_beyond_60mi_of_broad_menu"]), "zc": float(old.loc[k, "pct_pop55_in_counties_with_zero_trials"])} if k in old.index else None,
                        "member": m["name"] if m else "", "party": m["party"] if m else "", "hr3521": "lead" if k in lead_hr3521 else "", "ctx": ctx_of(r), "counties": d_counties.get(k, [])}
    nci = pd.read_csv(REF / "nci_centers.csv"); short = lambda s: s.replace(" Comprehensive Cancer Center", "").replace(" Cancer Center", "")
    ncil = [{"n": short(r.name), "full": r.name, "lat": round(r.lat, 3), "lon": round(r.lon, 3), "st": r.state, "tier": r.tier} for r in nci.itertuples()]
    nat = json.load(open(OUT / "national_metrics_v3.json")); cts = json.load(open(OUT / "cancer_type_summary.json")); rlog = json.load(open(OUT / "route_log.json")); blog = json.load(open(REF / "cancer_burden_log.json"))
    nat_ctx = ctx_of(pd.Series(nat)); blog_sites = blog["sites"]
    nat_binc = {site: [blog_sites[site]["us_rate"], int(blog_sites[site]["us_avg_annual_count"]) if blog_sites[site]["us_avg_annual_count"] else None, "ok"] for site in bsites if site in blog_sites}
    nat_core = core_of(pd.Series(nat))
    meta = {"version": "3.2", "registry_data_timestamp": fetch_log.get("registry_data_timestamp"), "pull_utc": fetch_log["timestamp_utc"][:16].replace("T", " ") + " UTC", "sites_unresolved": int(fac.unresolved.sum()), "site_alias_rules": len(ALIAS), "nat_ctx": nat_ctx, "nat_binc": nat_binc, "nat_core": nat_core, "pull": pull_date, "trials": len(trials), "facilities": int(fac.shape[0]), "plan": "119th Congress (2021 maps)", "members_pull": "2026-09-09 (unitedstates/congress-legislators, gh-pages)",
            "router": {"pairs": rlog["router_validation"]["pairs"], "mean_pct": rlog["router_validation"]["mean_abs_pct_diff"], "max_pct": rlog["router_validation"]["max_abs_pct_diff"]},
            "burden": {"period": btitle["all"].split(", ")[-1], "pulled": blog["pulled"], "small_threshold": 16, "sites": [[s, btitle[s].split(" (All")[0]] for s in bsites], "not_available_states": ["KS"]},
            "sitepoints": int(SM.shape[0]), "pct_multi": cts["pct_multi_55plus"], "pct_unclassified": cts["pct_unclassified_55plus"], "national": {k: nat[k] for k in ("pop55", "pct_zero_trials_within_60rdmi", "pct_lt20_trials_within_60rdmi", "pct_in_zero_trial_county", "pct_gt60rdmi_broad_menu", "pct_gt120rdmi_broad_menu", "pct_gt60rdmi_nci", "median_road_mi_nci", "pct_no_road_route_broad")},
            "vacant": [k for k, v in districts.items() if not v["member"]]}
    statelist = sorted({(v["st"], v["stname"]) for v in districts.values()}, key=lambda x: x[1])
    meta["routing"] = "facility-level: every recruiting site located by ZIP centroid (state-checked), city centroid, or county center; pools count sites within the road-mile band of the resident's tract or county population center"
    data = {"meta": meta, "T": T, "SP": SP, "SPF": SPF, "SPI": SPI, "counties": counties, "districts": districts, "state_data": states_d, "nci": ncil, "states": statelist, "district_keys": list(districts.keys())}
    # ---- tract-level binary for live filtered aggregates (loaded on demand by the page) ----
    # layout (little-endian): u32 magic 0x54524331 ('TRC1'), u32 n_tracts, u32 n_split, u32 n_pairs, u32 n_states, then
    #   pop55 u32[n]; state_idx u8[n] (index into meta.state_order) padded to 4; dist_idx u16[n] (index into district_keys, 0xFFFF = split) padded to 4;
    #   split: tract u32, dist u16, share_x10000 u16 (n_split records); offsets u32[n+1]; sitepoint ids u16[n_pairs] (within 60 road-mi)
    import struct
    tr_ = pd.read_csv(REF / "tracts_us.csv", dtype={"tract": str, "county_fips": str}); assert (zs["tract"] == tr_.tract.values).all()
    rel = pd.read_csv(REF / "tract_cd119.csv", dtype={"tract": str, "cd_geoid": str}); rel["share"] = rel.share.astype(float)
    dkey = {k: i for i, k in enumerate(districts)}; rel = rel[rel.cd_geoid.isin(dkey)]
    t_idx = {t: i for i, t in enumerate(tr_.tract)}; grp = rel.groupby("tract")
    dist_idx = np.full(len(tr_), 0xFFFF, np.uint16); split = []
    for t, g in grp:
        i = t_idx.get(t)
        if i is None: continue
        if len(g) == 1: dist_idx[i] = dkey[g.cd_geoid.iat[0]]
        else:
            for r_ in g.itertuples(): split.append((i, dkey[r_.cd_geoid], int(round(r_.share * 10000))))
    state_order = sorted({c["s"] for c in counties.values()}); s_idx = {sf: i for i, sf in enumerate(state_order)}
    state_idx = np.array([s_idx[t[:2]] for t in tr_.tract], np.uint8)
    pm = zs["pt_mi"] <= 60; ps, pt_ = zs["pt_src"][pm], zs["pt_t"][pm]; order = np.lexsort((ps, pt_)); ps, pt_ = ps[order], pt_[order]
    counts = np.bincount(pt_, minlength=len(tr_)); offsets = np.zeros(len(tr_) + 1, np.uint32); offsets[1:] = np.cumsum(counts)
    def pad4(b): return b + b"\0" * ((4 - len(b) % 4) % 4)
    blob = struct.pack("<IIIII", 0x54524331, len(tr_), len(split), len(ps), len(state_order)) + tr_.pop55.values.astype("<u4").tobytes() + pad4(state_idx.tobytes()) + pad4(dist_idx.astype("<u2").tobytes())
    blob += b"".join(struct.pack("<IHH", a, b, c) for a, b, c in split) + offsets.astype("<u4").tobytes() + ps.astype("<u2").tobytes()
    (DOCS / "tracts60.bin").write_bytes(blob); meta["state_order"] = state_order; meta["tracts_bin"] = {"file": "tracts60.bin", "bytes": len(blob), "tracts": int(len(tr_)), "pairs": int(len(ps)), "split_records": len(split)}
    data["meta"] = meta
    print("tracts60.bin MB:", round(len(blob) / 1e6, 1), "| pairs", len(ps), "| split", len(split))
    s = json.dumps(data, separators=(",", ":"), ensure_ascii=False); (DOCS / "data.js").write_text("window.DATA=" + s + ";", encoding="utf-8")
    print("data.js KB:", len(s.encode()) // 1024, "| counties", len(counties), "| districts", len(districts), "| trials", len(trials), "| facilities", fac.shape[0], "| vacant", meta["vacant"])
    # ---- geometry (unchanged method from v2: CT 2021 county shapes spliced in) ----
    from shapely.geometry import Polygon, MultiPolygon
    from shapely.geometry.polygon import orient
    def clean(geom, tol):
        """Simplify, drop slivers (< 2e-5 deg^2, ~0.25 km^2) and enforce d3-geo winding (exterior clockwise, holes anticlockwise)."""
        geom = geom.simplify(tol, preserve_topology=True)
        parts = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
        keep = []
        for pg in parts:
            if pg.is_empty or pg.area < 2e-5: continue
            pg = Polygon([(round(x, 2), round(y, 2)) for x, y in pg.exterior.coords], [[(round(x, 2), round(y, 2)) for x, y in r.coords] for r in pg.interiors if Polygon(r).area >= 2e-5])
            if not pg.is_valid: pg = pg.buffer(0)
            if pg.is_empty or pg.area < 2e-5: continue
            for q in (list(pg.geoms) if isinstance(pg, MultiPolygon) else [pg]):
                if len(q.exterior.coords) >= 4 and q.area >= 2e-5: keep.append(orient(q, sign=-1.0))
        return MultiPolygon(keep) if len(keep) > 1 else (keep[0] if keep else None)
    def simp(g, tol, pid, pstate=None):
        g = g.to_crs(4326); feats = []; dropped = []
        for r in g.itertuples():
            geom = clean(r.geometry, tol)
            if geom is None: dropped.append(pid(r)); continue
            gj = mapping(geom); pr = {"id": pid(r)}
            if pstate: pr["s"] = pstate(r)
            feats.append({"type": "Feature", "properties": pr, "geometry": gj})
        if dropped: print("features dropped as empty after cleaning (must be empty):", dropped)
        return {"type": "FeatureCollection", "features": feats}
    gc = gpd.read_file("zip://data/geo/cb.zip"); ct21 = gpd.read_file("zip://data/geo/cb500_2021.zip"); ct21 = ct21[ct21.STATEFP == "09"]
    gc = gpd.GeoDataFrame(pd.concat([gc[gc.STATEFP != "09"], ct21], ignore_index=True), geometry="geometry", crs=ct21.crs); gc = gc[gc.GEOID.isin(counties)]
    missing = set(counties) - set(gc.GEOID); print("counties in data but without geometry (should be empty):", missing)
    gd = gpd.read_file("zip://data/geo/cd119.zip"); gd["cdid"] = gd.STATEFP.astype(str).str.zfill(2) + gd.CD119FP.astype(str).str.zfill(2); gd = gd[gd.cdid.isin(districts)]
    print("districts in data but without geometry (should be empty):", set(districts) - set(gd.cdid))
    gs = gpd.read_file("zip://data/geo/states.zip"); gs = gs[gs.STATEFP.isin(INV)]
    geo = {"counties": simp(gc, 0.012, lambda r: r.GEOID), "districts": simp(gd, 0.007, lambda r: r.cdid, lambda r: INV.get(r.STATEFP, "")), "states": simp(gs, 0.01, lambda r: INV[r.STATEFP])}
    s = json.dumps(geo, separators=(",", ":")); (DOCS / "geo.js").write_text("window.GEO=" + s + ";")
    print("geo.js KB:", len(s) // 1024, "| county features", len(geo["counties"]["features"]), "| district features", len(geo["districts"]["features"]))


if __name__ == "__main__":
    main()
