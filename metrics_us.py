"""National county / district / state access metrics. Same definitions as the Texas pipeline.
Usage: python metrics_us.py [--min-max-age 55] [--out out_adult55]"""
import argparse, json
from pathlib import Path
import geopandas as gpd, numpy as np, pandas as pd
import config

RAW, REF = Path("data/raw"), Path("data/ref")
R_MI = 3958.8


def hav_matrix(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1)[:, None], np.radians(lat2)[None, :]
    dphi = p2 - p1; dl = np.radians(lon2)[None, :] - np.radians(lon1)[:, None]
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R_MI * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def assign_sites(sites, cent):
    z2c = dict(pd.read_csv(REF / "zcta_county.csv", dtype=str).values)
    z3 = dict(pd.read_csv(REF / "zip3_county.csv", dtype=str).values)
    gaz = pd.read_csv(REF / "gazetteer_places.csv", dtype={"state": str, "place": str})
    counties = gpd.read_file("zip://data/geo/cb.zip")[["STATEFP", "GEOID", "geometry"]]
    # Connecticut: the 2023 cartographic file carries planning regions (091xx); ZIP/ACS/population files use the 8 legacy counties,
    # so splice in the 2021 county shapes for CT (same fix as the web-app geometry) so city-fallback sites get legacy codes.
    ct2021 = gpd.read_file("zip://data/geo/cb500_2021.zip"); ct2021 = ct2021[ct2021.STATEFP == "09"][["STATEFP", "GEOID", "geometry"]].to_crs(counties.crs)
    counties = pd.concat([counties[counties.STATEFP != "09"], ct2021], ignore_index=True)
    counties = gpd.GeoDataFrame(counties, geometry="geometry", crs=ct2021.crs)[["GEOID", "geometry"]].to_crs(4326)
    pts = gpd.GeoDataFrame(gaz, geometry=gpd.points_from_xy(gaz.lon, gaz.lat), crs=4326)
    gaz_county = gpd.sjoin(pts, counties, how="left", predicate="within")
    city2c = {(r.state, r.place): r.GEOID for r in gaz_county.dropna(subset=["GEOID"]).itertuples()}
    method, county = [], []
    for s in sites.itertuples():
        z = (s.zip or "")[:5]; st = s.state_fips
        c = z2c.get(z) if z.isdigit() and len(z) == 5 else None
        if c and c[:2] == st: method.append("zip"); county.append(c); continue
        c3 = z3.get(z[:3]) if len(z) >= 3 and z[:3].isdigit() else None
        if c3 and c3[:2] == st: method.append("zip3"); county.append(c3); continue
        city = (s.city or "").strip().lower()
        for cand in (city, city.replace("saint ", "st. "), city.replace("st ", "st. "), city.replace("ft. ", "fort ").replace("ft ", "fort ")):
            cc = city2c.get((s.state, cand))
            if cc: break
        if cc and cc[:2] == st: method.append("city_gazetteer"); county.append(cc); continue
        method.append("unassigned"); county.append(None)
    sites = sites.copy(); sites["county_fips"] = county; sites["assign_method"] = method
    return sites


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--min-max-age", type=float); ap.add_argument("--out", default="out")
    a = ap.parse_args(); OUT = Path(a.out); OUT.mkdir(exist_ok=True)
    trials = pd.read_csv(RAW / "trials.csv", dtype=str)
    sites = pd.read_csv(RAW / "us_sites.csv", dtype=str).fillna("")
    age_note = "all ages"
    if a.min_max_age is not None:
        mx = pd.to_numeric(trials.max_age_years, errors="coerce"); drop = set(trials.loc[mx < a.min_max_age, "nct_id"])
        trials = trials[~trials.nct_id.isin(drop)]; sites = sites[~sites.nct_id.isin(drop)]
        age_note = f"trials with maximum age < {a.min_max_age:g} excluded (n={len(drop)})"
    cent = pd.read_csv(REF / "county_centroids.csv", dtype={"county_fips": str, "state_fips": str})
    pop = pd.read_csv(REF / "county_pop55.csv", dtype={"county_fips": str})
    cd = pd.read_csv(REF / "county_cd.csv", dtype=str); cd["share"] = cd.share.astype(float)
    nci = pd.read_csv(REF / "nci_centers.csv")

    sites = assign_sites(sites, cent); sites.to_csv(OUT / "site_assignment_qc.csv", index=False)
    qc = sites.assign_method.value_counts().to_dict()
    oral = dict(zip(trials.nct_id, trials.oral_candidate.astype(int))); indet = dict(zip(trials.nct_id, trials.oral_indeterminate.astype(int)))
    ct = sites.dropna(subset=["county_fips"]).groupby("county_fips").nct_id.agg(set).to_dict()

    c = cent.merge(pop, on="county_fips", how="left"); c["pop55"] = c.pop55.fillna(0).astype(int)
    c["trials_in_county"] = c.county_fips.map(lambda f: len(ct.get(f, set())))
    c["oral_trials_in_county"] = c.county_fips.map(lambda f: sum(oral.get(n, 0) for n in ct.get(f, set())))
    c["oral_indeterminate_in_county"] = c.county_fips.map(lambda f: sum(indet.get(n, 0) for n in ct.get(f, set())))
    lat, lon = c.lat.values, c.lon.values
    D = hav_matrix(lat, lon, lat, lon) * config.ROAD_FACTOR
    lim_idx = np.where(c.trials_in_county.values >= config.MENU_THRESHOLDS["limited"])[0]
    brd_idx = np.where(c.trials_in_county.values >= config.MENU_THRESHOLDS["broad"])[0]
    c["dist_to_limited_mi"] = D[:, lim_idx].min(axis=1); c.loc[c.trials_in_county >= config.MENU_THRESHOLDS["limited"], "dist_to_limited_mi"] = 0
    c["dist_to_broad_mi"] = D[:, brd_idx].min(axis=1); c.loc[c.trials_in_county >= config.MENU_THRESHOLDS["broad"], "dist_to_broad_mi"] = 0
    Dn = hav_matrix(lat, lon, nci.lat.values, nci.lon.values) * config.ROAD_FACTOR
    c["dist_to_nci_mi"] = Dn.min(axis=1); c["nearest_nci"] = nci.name.values[Dn.argmin(axis=1)]
    fips = c.county_fips.values
    for band in config.DISTANCE_BANDS_MI:
        t, o, i = [], [], []
        for k in range(len(c)):
            pool = set().union(*[ct.get(fips[j], set()) for j in np.where(D[k] <= band)[0]])
            t.append(len(pool)); o.append(sum(oral.get(n, 0) for n in pool)); i.append(sum(indet.get(n, 0) for n in pool))
        c[f"trials_within_{band}mi"], c[f"oral_trials_within_{band}mi"], c[f"oral_indeterminate_within_{band}mi"] = t, o, i
    c.sort_values("trials_in_county", ascending=False).to_csv(OUT / "county_metrics.csv", index=False)

    m = cd.merge(c, on=["county_fips", "state_fips"], how="inner"); m["w"] = m.pop55 * m.share
    m["zero"] = (m.trials_in_county == 0).astype(int)
    for b in config.DISTANCE_BANDS_MI:
        m[f"b{b}_broad"] = (m.dist_to_broad_mi > b).astype(int); m[f"b{b}_lim"] = (m.dist_to_limited_mi > b).astype(int)

    def agg(g, keys):
        W = g.w.sum()
        def wm(col): return (g[col] * g.w).sum() / W if W else np.nan
        row = dict(keys); row.update({"pop55_weighted": int(round(W)), "n_counties_touched": g.county_fips.nunique(),
            "pct_pop55_in_counties_with_zero_trials": round(100 * wm("zero"), 1),
            "wmean_trials_in_own_county": round(wm("trials_in_county"), 0),
            "wmean_dist_to_broad_menu_mi": round(wm("dist_to_broad_mi"), 1), "wmean_dist_to_limited_menu_mi": round(wm("dist_to_limited_mi"), 1),
            "wmean_dist_to_nci_mi": round(wm("dist_to_nci_mi"), 1), "wmean_trials_within_60mi": round(wm("trials_within_60mi"), 0),
            "wmean_oral_trials_within_60mi": round(wm("oral_trials_within_60mi"), 0), "wmean_oral_indeterminate_within_60mi": round(wm("oral_indeterminate_within_60mi"), 0)})
        for b in config.DISTANCE_BANDS_MI:
            row[f"pct_pop55_beyond_{b}mi_of_broad_menu"] = round(100 * wm(f"b{b}_broad"), 1); row[f"pct_pop55_beyond_{b}mi_of_limited_menu"] = round(100 * wm(f"b{b}_lim"), 1)
        return row
    st_name = dict(zip(cent.state_fips, cent.state_name))
    dist = pd.DataFrame([agg(g, {"cd_geoid": k, "state_fips": k[:2], "state": st_name[k[:2]], "cd": k[2:]}) for k, g in m.groupby("cd_geoid")])
    dist.to_csv(OUT / "district_metrics.csv", index=False)
    # state summary uses full county populations (no shares)
    c["zero"] = (c.trials_in_county == 0).astype(int); c["w"] = c.pop55
    for b in config.DISTANCE_BANDS_MI:
        c[f"b{b}_broad"] = (c.dist_to_broad_mi > b).astype(int); c[f"b{b}_lim"] = (c.dist_to_limited_mi > b).astype(int)
    states = pd.DataFrame([agg(g, {"state_fips": k, "state": st_name[k]}) for k, g in c.groupby("state_fips")])
    states["n_counties"] = states.state_fips.map(c.groupby("state_fips").size()); states["n_counties_with_trials"] = states.state_fips.map(c[c.trials_in_county > 0].groupby("state_fips").size()).fillna(0).astype(int)
    states["n_districts"] = states.state_fips.map(dist.groupby("state_fips").size())
    states.to_csv(OUT / "state_metrics.csv", index=False)
    us = agg(c.assign(w=c.pop55), {"scope": "US (50 states + DC)"})
    log = {"age_filter": age_note, "site_rows": len(sites), "site_assignment": qc, "distinct_trials": int(trials.nct_id.nunique()),
           "counties": len(c), "counties_with_any_trial": int((c.trials_in_county > 0).sum()), "broad_menu_counties": int(len(brd_idx)), "limited_menu_counties": int(len(lim_idx)),
           "districts": len(dist), "us": us}
    json.dump(log, open(OUT / "metrics_log.json", "w"), indent=2); print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
