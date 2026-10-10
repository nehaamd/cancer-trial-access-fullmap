"""Facility-level routing (review round 2, point 1) — replaces the county-population-center stand-in for trial locations.

Previously every trial was placed at its county's population center, and a resident's own county's trials were 0 miles away
regardless of county size. Now each recruiting site is located at its ZIP-code centroid (ZCTA), with the same state check the
county assignment uses (a ZIP whose state disagrees with the site's stated state is rejected — e.g. a Los Angeles site listed with
a Boston ZIP falls through to the city gazetteer, exactly as it did for county assignment), then the city centroid, then — only
if nothing else is available — the county population center (flagged). Two exceptions put a site at its city although its ZIP
is known: a ZIP larger than 100 square miles, whose centroid is in open country (tier4_covering.SiteLocator), and a ZIP that
spans counties when the site was assigned to the county where the ZIP's residents live (metrics_us.assign_sites). A row
whose ZIP is a typing error is placed at the ZIP where the registry's other rows list that facility (metrics_us.zip_typos),
and a row that is not a place at all - a telemedicine "site" - has no county and never reaches this script
(config.VIRTUAL_SITE_PATTERN).

Sites at the same location are merged into "site points". For every tract and county population center: road miles to every
site point within 120 road-miles. "Trials within X road-miles" then means trials with at least one recruiting site within X
road-miles of where the resident actually is, including sites in their own county at their real distance.

Menu distances (nearest county with >=20 / >=100 trials) are county-level concepts by definition and are unchanged.

Outputs: data/roads/route_cache_sites.npz, out_adult55/sitepoints.csv, out_adult55/route_sites_log.json
"""
import json, re, time
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from scipy import sparse
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import dijkstra
from tier4_covering import prepare_graph, norm, to5070, SiteLocator

REF, OUT, ROADS, RAW = Path("data/ref"), Path("out_adult55"), Path("data/roads"), Path("data/raw")
M2MI = 1 / 1609.344; SPEED_ACCESS = 35.0; MAX_ACCESS_MI = 30.0; BAND_MAX = 120.0


def main():
    t0 = time.time(); log = {}
    nodes, A, tree, aidx = prepare_graph(); n = len(nodes); print(f"graph ready {time.time()-t0:.0f}s", flush=True)
    trials = pd.read_csv(RAW / "trials.csv", dtype=str, keep_default_na=False); trials = trials[pd.to_numeric(trials.max_age_years, errors="coerce").fillna(999) >= 55].reset_index(drop=True)
    j_of = {nct: j for j, nct in enumerate(trials.nct_id)}
    sites = pd.read_csv(OUT / "site_assignment_qc.csv", dtype=str).fillna(""); sites = sites[(sites.county_fips != "") & sites.nct_id.isin(j_of)].copy()
    sites["zip5"] = sites.zip.str.extract(r"(\d{5})", expand=False).fillna("")
    z2c = dict(pd.read_csv(REF / "zcta_county.csv", dtype=str).values); loc = SiteLocator()
    cent = pd.read_csv(REF / "county_centroids.csv", dtype={"county_fips": str, "state_fips": str}).set_index("county_fips")
    clat, clon = cent.lat.to_dict(), cent.lon.to_dict()
    lat, lon, how = [], [], []
    for r in sites.itertuples():
        # the ZIP is a typing error (metrics_us.zip_typos): the row is located at the ZIP where the registry's other rows put that facility
        fix = getattr(r, "zip_fix", "") if getattr(r, "assign_method", "") == "zip_typo_corrected" else ""
        zf = loc.by_zip(fix, r.state, r.city) if fix else None
        if zf: lat.append(zf[0]); lon.append(zf[1]); how.append("zip_typo_corrected"); continue
        zcty = z2c.get(r.zip5); z = loc.by_zip(r.zip5, r.state, r.city) if (zcty and zcty[:2] == r.county_fips[:2] and not fix) else None
        c = loc.city(r.state, r.city); la0, lo0 = clat[r.county_fips], clon[r.county_fips]
        # the city name must agree with the assigned county: a registry row like city "Dallas" + ZIP 75521 (Atlanta, TX) was
        # assigned to Cass County by ZIP, and must not be drawn 180 miles away in Dallas. 40 mi ~ the radius of a large county.
        city_ok = bool(c) and np.hypot((c[0] - la0) * 69.0, (c[1] - lo0) * 69.0 * np.cos(np.radians(la0))) <= 40
        # A site assigned to the county where its ZIP's residents live rather than where its land is ("zip_pop", metrics_us.py)
        # is placed at its city: the ZIP centroid is in the other county.
        if z and getattr(r, "assign_method", "") == "zip_pop" and city_ok and z[2] == "zip_centroid": z = (c[0], c[1], "city_centroid_zip_spans_counties")
        if z: lat.append(z[0]); lon.append(z[1]); how.append(z[2]); continue
        if c:
            if city_ok: lat.append(c[0]); lon.append(c[1]); how.append("city_centroid"); continue
            # the city lies far from the assigned county: the row is not located (a point at the county center would be a phantom site)
            lat.append(np.nan); lon.append(np.nan); how.append("unlocated_city_disagrees"); continue
        lat.append(la0); lon.append(lo0); how.append("county_centroid")
    sites["lat"], sites["lon"], sites["geocode"] = lat, lon, how
    log["site_rows"] = len(sites); log["geocode"] = sites.geocode.value_counts().to_dict()
    unloc = sites.lat.isna(); log["unlocated_rows"] = int(unloc.sum()); sites = sites[~unloc].copy()   # rows with no defensible location carry no site point
    # merge coincident locations into site points
    sites["pt"] = (sites.lat.round(4).astype(str) + "," + sites.lon.round(4).astype(str))
    pts = sites.groupby("pt").agg(lat=("lat", "first"), lon=("lon", "first"), county_fips=("county_fips", "first"), geocode=("geocode", "first"),
                                  n_trials=("nct_id", "nunique"), n_facilities=("facility", lambda s: s.map(norm).nunique())).reset_index()
    pts["sp"] = np.arange(len(pts)); sp_of = dict(zip(pts.pt, pts.sp)); sites["sp"] = sites.pt.map(sp_of)
    log["site_points"] = len(pts); print(f"{len(sites)} site rows -> {len(pts)} site points", flush=True)
    # site point x trial membership
    S = sparse.coo_matrix((np.ones(len(sites), bool), (sites.sp.values, sites.nct_id.map(j_of).values)), shape=(len(pts), len(trials))).tocsr(); S.data[:] = True; S.sum_duplicates()
    # attach site points as graph nodes (so their access edge is part of the route), tracts and counties as leaves
    pxy = to5070(pts.lon.values, pts.lat.values); pd_, pi = tree.query(pxy); pi = aidx[pi]; p_acc = pd_ * M2MI
    p_off = p_acc > MAX_ACCESS_MI; log["site_points_off_network_gt30mi"] = int(p_off.sum())
    p_node = np.arange(n, n + len(pts)); N = n + len(pts)
    coo = A.tocoo(); au = np.concatenate([coo.row, p_node, pi]); av = np.concatenate([coo.col, pi, p_node])
    ami = np.concatenate([coo.data, np.where(p_off, 1e9, p_acc), np.where(p_off, 1e9, p_acc)])
    A2 = sparse.coo_matrix((ami, (au, av)), shape=(N, N)).tocsr()
    tr = pd.read_csv(REF / "tracts_us.csv", dtype={"tract": str, "county_fips": str})
    txy = to5070(tr.lon.values, tr.lat.values); td, ti = tree.query(txy); ti = aidx[ti]; t_acc = td * M2MI; t_acc[t_acc > MAX_ACCESS_MI] = np.inf
    cxy = to5070(cent.lon.values, cent.lat.values); cd, ci = tree.query(cxy); ci = aidx[ci]; c_acc = cd * M2MI; c_acc[c_acc > MAX_ACCESS_MI] = np.inf
    cutoff = BAND_MAX + float(np.nanmax(t_acc[np.isfinite(t_acc)])) + 0.01
    B = 16; pt_src, pt_t, pt_mi, pc_src, pc_c, pc_mi = [], [], [], [], [], []
    for b0 in range(0, len(pts), B):
        idx = np.arange(b0, min(b0 + B, len(pts)))
        D = dijkstra(A2, directed=False, indices=p_node[idx], min_only=False, limit=cutoff)
        dt = (D[:, ti] + t_acc[None, :]).astype(np.float32); ok = dt <= BAND_MAX; s_i, t_i = np.where(ok)
        pt_src.append(idx[s_i].astype(np.int32)); pt_t.append(t_i.astype(np.int32)); pt_mi.append(dt[ok])
        dc = (D[:, ci] + c_acc[None, :]).astype(np.float32); ok = dc <= BAND_MAX; s_i, c_i = np.where(ok)
        pc_src.append(idx[s_i].astype(np.int32)); pc_c.append(c_i.astype(np.int32)); pc_mi.append(dc[ok]); del D
        if (b0 // B) % 40 == 0: print(f"  {b0+len(idx)}/{len(pts)} {time.time()-t0:.0f}s", flush=True)
    pt_src, pt_t, pt_mi = (np.concatenate(x) for x in (pt_src, pt_t, pt_mi)); pc_src, pc_c, pc_mi = (np.concatenate(x) for x in (pc_src, pc_c, pc_mi))
    # a site point inside a resident's own tract can still be a few miles away by road; nothing is forced to zero any more
    log["tract_sitepoint_pairs_within_120"] = int(len(pt_src)); log["county_sitepoint_pairs_within_120"] = int(len(pc_src))
    # --- screen: residents with a recruiting site close by in a straight line but none within 60 miles by road. A real water
    #     barrier produces a few of these (Whidbey Island, the Bolivar Peninsula, the New York shore of Lake Champlain); a fault in
    #     the road graph produces many (the first national graph: about 194,000 residents 55+). release_gate.py puts a ceiling on it. ---
    near_road = np.full(len(tr), np.inf); np.minimum.at(near_road, pt_t, pt_mi)
    sl = cKDTree(pxy[~p_off]).query(txy)[0] * M2MI
    lower48 = ~tr.county_fips.str[:2].isin(["02", "15"]).values; flag = lower48 & (sl <= 20.0) & (near_road > 60.0)
    pop55 = tr.pop55.values; by_c = pd.Series(pop55[flag], index=tr.county_fips.values[flag]).groupby(level=0).sum().sort_values(ascending=False)
    log["screen_site_near_in_straight_line_far_by_road"] = {"rule": "contiguous states; nearest site point within 20 straight-line miles, none within 60 road-miles",
        "tracts": int(flag.sum()), "pop55": int(pop55[flag].sum()), "pct_of_pop55": round(100 * float(pop55[flag].sum()) / float(pop55.sum()), 3),
        "largest_counties": [{"county": f"{cent.county_name.get(f, f)}, {cent.state_name.get(f, '')}", "pop55": int(v)} for f, v in by_c.head(12).items()]}
    np.savez_compressed(ROADS / "route_cache_sites.npz", tract=tr.tract.values.astype(str), county_fips=cent.index.values.astype(str),
                        sp_lat=pts.lat.values, sp_lon=pts.lon.values, sp_county=pts.county_fips.values.astype(str), sp_n_facilities=pts.n_facilities.values,
                        S_indptr=S.indptr, S_indices=S.indices, S_shape=np.array(S.shape), trial_ids=trials.nct_id.values.astype(str),
                        pt_src=pt_src, pt_t=pt_t, pt_mi=pt_mi, pc_src=pc_src, pc_c=pc_c, pc_mi=pc_mi)
    pts[["sp", "lat", "lon", "county_fips", "geocode", "n_trials", "n_facilities"]].to_csv(OUT / "sitepoints.csv", index=False)
    sites[["nct_id", "facility", "city", "state", "zip5", "county_fips", "geocode", "sp"]].to_csv(OUT / "site_geocode_qc.csv", index=False)
    log["seconds"] = round(time.time() - t0); json.dump(log, open(OUT / "route_sites_log.json", "w"), indent=2); print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
