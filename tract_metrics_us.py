"""Tier 2.2 — tract-level access on the road network, and population-55+-weighted district / state / national metrics.

Reads data/roads/route_cache.npz (from route_us.py), data/ref/tracts_us.csv, data/ref/tract_cd119.csv, site assignments and trial table.
Writes out_adult55/tract_access.csv, district_metrics_v3.csv, state_metrics_v3.csv, national_metrics_v3.json, tract_metrics_log.json.

District weights: each tract-district record carries weight = tract pop 55+ x land-area share of the tract inside the district
(Census 2020 tract->CD119 relationship file). Tracts wholly inside one district (the vast majority) have share 1.
A tract with no road route to a target is treated as beyond every distance threshold and counted in pct_no_road_route_*.
"""
import json
from pathlib import Path
import numpy as np, pandas as pd
from scipy import sparse

REF, OUT, ROADS, RAW = Path("data/ref"), Path("out_adult55"), Path("data/roads"), Path("data/raw")
NOROAD = 999.0
PHASE_MAP = {"PHASE1": "1", "EARLY_PHASE1": "1", "PHASE1;PHASE2": "1-2", "PHASE2": "2", "PHASE2;PHASE3": "2-3", "PHASE3": "3", "PHASE4": "4", "": "NA", "NA": "NA"}
SPONSOR_MAP = {"INDUSTRY": "industry", "NIH": "nih_federal", "FED": "nih_federal", "OTHER": "academic_other", "OTHER_GOV": "academic_other", "NETWORK": "academic_other", "INDIV": "academic_other", "UNKNOWN": "academic_other"}


def load_trials():
    t = pd.read_csv(RAW / "trials.csv", dtype=str, keep_default_na=False)  # keep_default_na: the registry phase "NA" (not applicable) is real data
    t = t[pd.to_numeric(t.max_age_years, errors="coerce").fillna(999) >= 55].copy()
    ct = pd.read_csv(RAW / "trial_cancer_type.csv", dtype=str).set_index("nct_id")
    t["cancer_type"] = t.nct_id.map(ct.cancer_type).fillna("other_unclassified")
    t["phase"] = t.phases.map(lambda p: PHASE_MAP.get(p, "NA")); t["sponsor"] = t.lead_sponsor_class.map(lambda s: SPONSOR_MAP.get(s, "academic_other"))
    return t.reset_index(drop=True)


def main():
    z = np.load(ROADS / "route_cache.npz", allow_pickle=True)
    tr = pd.read_csv(REF / "tracts_us.csv", dtype={"tract": str, "county_fips": str})
    assert (tr.tract.values == z["tract"]).all(), "route cache tract order does not match tracts_us.csv"
    fips = z["county_fips"]; k_of = {f: k for k, f in enumerate(fips)}
    trials = load_trials(); j_of = {n: j for j, n in enumerate(trials.nct_id)}
    sites = pd.read_csv(OUT / "site_assignment_qc.csv", dtype=str).fillna(""); sites = sites[(sites.county_fips != "") & sites.nct_id.isin(j_of)]
    # county x trial membership (sparse, bool)
    rows = sites.county_fips.map(k_of).values; cols = sites.nct_id.map(j_of).values
    M = sparse.coo_matrix((np.ones(len(rows), bool), (rows, cols)), shape=(len(fips), len(trials))).tocsr(); M.data[:] = True; M.sum_duplicates()
    cnt_county = np.asarray(M.sum(axis=1)).ravel()
    cm = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str}).set_index("county_fips")
    assert (cm.reindex(fips).trials_in_county.values == cnt_county).all(), "trial-per-county recount disagrees with metrics_us.py"
    # tract x site-point proximity (sparse) per band — facility-level routing (route_sites_us.py); falls back to county centers if absent
    nT = len(tr); zs = None
    if (ROADS / "route_cache_sites.npz").exists():
        zs = np.load(ROADS / "route_cache_sites.npz", allow_pickle=True); assert (zs["tract"] == tr.tract.values).all() and (zs["trial_ids"] == trials.nct_id.values).all()
        SM = sparse.csr_matrix((np.ones(len(zs["S_indices"]), np.int32), zs["S_indices"], zs["S_indptr"]), shape=tuple(zs["S_shape"]))  # site point x trial
        pt_src, pt_t, pt_mi, n_src, SRC = zs["pt_src"], zs["pt_t"], zs["pt_mi"], SM.shape[0], SM
        print("using facility-level routing:", SM.shape[0], "site points", flush=True)
    else:
        pt_src, pt_t, pt_mi, n_src, SRC = z["pt_src"], z["pt_t"], z["pt_mi"], len(fips), M.astype(np.int32)
    one_hot = {}
    ctypes = pd.read_csv(RAW / "trial_cancer_type.csv", dtype=str, keep_default_na=False).set_index("nct_id")
    for name, keyser in (("cancer_type", trials.cancer_type), ("phase", trials.phase), ("sponsor", trials.sponsor)):
        if name == "cancer_type":
            # multi-label: a trial counts under every named cancer its conditions name (so basket trials naming colorectal count under
            # colorectal), and additionally under "multi" (its primary bucket) so the basket share stays visible. Same rule as the web filter.
            named = sorted(c for c in keyser.unique() if c not in ("multi", "other_unclassified")); cats = named + ["multi", "other_unclassified"]; ci = {c: i for i, c in enumerate(cats)}
            rows_, cols_ = [], []
            for j, (nct, prim) in enumerate(zip(trials.nct_id, keyser)):
                m = [c for c in str(ctypes.categories_matched.get(nct, "")).split(";") if c in ci]
                for c in (m if m else ([] if prim == "other_unclassified" else [prim])): rows_.append(j); cols_.append(ci[c])
                if prim in ("multi", "other_unclassified"): rows_.append(j); cols_.append(ci[prim])
            C = sparse.coo_matrix((np.ones(len(rows_)), (rows_, cols_)), shape=(len(trials), len(cats))).tocsr(); C.data[:] = 1; C.sum_duplicates()
        else:
            cats = sorted(keyser.unique()); C = sparse.coo_matrix((np.ones(len(trials)), (np.arange(len(trials)), keyser.map({c: i for i, c in enumerate(cats)}).values)), shape=(len(trials), len(cats))).tocsr()
        one_hot[name] = (cats, C)
    out = {}
    for band in (30, 60, 120):
        ok = pt_mi <= band
        P = sparse.coo_matrix((np.ones(ok.sum(), bool), (pt_t[ok], pt_src[ok])), shape=(nT, n_src)).tocsr(); P.data[:] = True; P.sum_duplicates()
        pool = (P @ SRC); pool.data[:] = 1; pool = pool.astype(np.int32)   # tract x trial, 1 if a recruiting site is within the band
        out[f"trials_within_{band}rdmi"] = np.asarray(pool.sum(axis=1)).ravel()
        if band == 60:
            for name, (cats, C) in one_hot.items():
                counts = np.asarray((pool @ C).todense())
                for i, c in enumerate(cats): out[f"t60_{name}_{c}"] = counts[:, i].astype(int)
    for k, v in out.items(): tr[k] = v
    for lab in ("broad", "lim", "nci"):
        d = z[f"t_{lab}"]; h = z[f"t_{lab}_hr"]
        tr[f"road_mi_{lab}"] = np.where(np.isfinite(d), np.round(d, 1), NOROAD); tr[f"drive_hr_{lab}"] = np.where(np.isfinite(h), np.round(h, 2), NOROAD)
    cent = pd.read_csv(REF / "county_centroids.csv", dtype={"county_fips": str}); nci = pd.read_csv(REF / "nci_centers.csv")
    cname = (cent.county_name + ", " + cent.state_name).values
    tr["nearest_broad"] = np.where(z["t_broad_src"] >= 0, cname[np.clip(z["t_broad_src"], 0, None)], "NO ROAD CONNECTION")
    tr["nearest_nci"] = np.where(z["t_nci_src"] >= 0, nci.name.values[np.clip(z["t_nci_src"], 0, None)], "NO ROAD CONNECTION")
    tr.loc[tr.road_mi_broad == 0, "nearest_broad"] = cname[tr.loc[tr.road_mi_broad == 0, "county_fips"].map(k_of).values]
    tr["trials_in_own_county"] = cnt_county[tr.county_fips.map(k_of).values]
    tr["on_main_road_network"] = (z["t_component"] == int(z["main_component"])).astype(int)
    tr.to_csv(OUT / "tract_access.csv", index=False)

    # ---- district metrics ----
    rel = pd.read_csv(REF / "tract_cd119.csv", dtype={"tract": str, "cd_geoid": str}); rel["share"] = rel.share.astype(float)
    m = rel.merge(tr, on="tract", how="inner"); m["w"] = m.pop55 * m.share
    tcols = [c for c in tr.columns if c.startswith("t60_")]

    def agg(g):
        W = g.w.sum()
        if W == 0: return pd.Series({"pop55": 0})
        wm = lambda c: float((g[c] * g.w).sum() / W); pct = lambda mask: round(100 * float(g.loc[mask, "w"].sum() / W), 1)
        def wmed(c):
            s = g.sort_values(c); return float(s.loc[s.w.cumsum() >= W / 2, c].iloc[0])
        r = {"pop55": int(round(W)), "n_tracts": len(g),
             "pct_zero_trials_within_60rdmi": pct(g.trials_within_60rdmi == 0), "pct_lt20_trials_within_60rdmi": pct(g.trials_within_60rdmi < 20),
             "pct_lt100_trials_within_60rdmi": pct(g.trials_within_60rdmi < 100), "pct_in_zero_trial_county": pct(g.trials_in_own_county == 0),
             "pct_gt60rdmi_broad_menu": pct(g.road_mi_broad > 60), "pct_gt120rdmi_broad_menu": pct(g.road_mi_broad > 120),
             "pct_gt60rdmi_limited_menu": pct(g.road_mi_lim > 60), "pct_gt60rdmi_nci": pct(g.road_mi_nci > 60), "pct_gt120rdmi_nci": pct(g.road_mi_nci > 120),
             "pct_no_road_route_broad": pct(g.road_mi_broad >= NOROAD), "pct_no_road_route_nci": pct(g.road_mi_nci >= NOROAD),
             "median_road_mi_nci": round(wmed("road_mi_nci"), 0), "median_road_mi_broad_menu": round(wmed("road_mi_broad"), 0), "median_road_mi_limited_menu": round(wmed("road_mi_lim"), 0),
             "wmean_trials_within_60rdmi": round(wm("trials_within_60rdmi"), 0), "wmean_trials_within_30rdmi": round(wm("trials_within_30rdmi"), 0),
             "wmean_trials_within_120rdmi": round(wm("trials_within_120rdmi"), 0), "wmean_trials_in_own_county": round(wm("trials_in_own_county"), 0),
             "modal_nearest_nci": g.groupby("nearest_nci").w.sum().idxmax(), "modal_nearest_broad": g.groupby("nearest_broad").w.sum().idxmax()}
        for c in tcols: r["wmean_" + c] = round(wm(c), 0)
        return pd.Series(r)
    dist = m.groupby("cd_geoid").apply(agg, include_groups=False).reset_index()
    dist["state_fips"] = dist.cd_geoid.str[:2]; dist["cd"] = dist.cd_geoid.str[2:]
    dist.to_csv(OUT / "district_metrics_v3.csv", index=False)
    # share check: every tract's shares sum to 1
    ssum = rel.groupby("tract").share.sum(); share_bad = int(((ssum - 1).abs() > 1e-6).sum())
    # ---- state and national (whole tracts, no shares) ----
    tr["w"] = tr.pop55; tr["state_fips"] = tr.county_fips.str[:2]
    st = tr.groupby("state_fips").apply(agg, include_groups=False).reset_index(); st.to_csv(OUT / "state_metrics_v3.csv", index=False)
    nat = agg(tr); nat = {k: (int(v) if isinstance(v, (np.integer,)) else float(v) if isinstance(v, (np.floating,)) else v) for k, v in nat.items()}
    json.dump(nat, open(OUT / "national_metrics_v3.json", "w"), indent=2, default=str)
    # invariants
    inv = {"tract_pool_monotone_violations": int(((tr.trials_within_30rdmi > tr.trials_within_60rdmi) | (tr.trials_within_60rdmi > tr.trials_within_120rdmi)).sum()),
           "tract_broad_ge_limited_violations": int((tr.road_mi_broad < tr.road_mi_lim - 1e-6).sum()),
           "tract_in_menu_county_nonzero_violations": int(((tr.trials_in_own_county >= 100) & (tr.road_mi_broad > 0)).sum() + ((tr.trials_in_own_county >= 20) & (tr.road_mi_lim > 0)).sum()),
           "tracts_where_own_county_trials_exceed_60mi_pool": int((tr.trials_in_own_county > tr.trials_within_60rdmi).sum()),  # expected >0 with facility routing: a large county's trials can be >60 road-mi from some of its own tracts
           "pop55_in_those_tracts": int(tr.pop55[tr.trials_in_own_county > tr.trials_within_60rdmi].sum()),
           "district_pct120_le_pct60_violations": int((dist.pct_gt120rdmi_broad_menu > dist.pct_gt60rdmi_broad_menu + 1e-9).sum()),
           "tract_share_sum_not_1": share_bad, "districts": len(dist), "district_pop55_total": int(dist.pop55.sum()), "tract_pop55_total": int(tr.pop55.sum()),
           "tracts_with_no_district_row": int((~tr.tract.isin(set(rel.tract))).sum()), "pop55_in_tracts_with_no_district_row": int(tr.loc[~tr.tract.isin(set(rel.tract)), "pop55"].sum())}
    json.dump({"national": nat, "invariants": inv}, open(OUT / "tract_metrics_log.json", "w"), indent=2, default=str)
    print(json.dumps(inv, indent=1)); print({k: nat[k] for k in ("pop55", "pct_zero_trials_within_60rdmi", "pct_lt20_trials_within_60rdmi", "pct_in_zero_trial_county", "pct_gt60rdmi_broad_menu", "pct_gt120rdmi_broad_menu", "pct_gt60rdmi_nci", "median_road_mi_nci", "pct_no_road_route_broad")})


if __name__ == "__main__":
    main()
