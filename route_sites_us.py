"""Facility-level routing (review round 2, point 1) — replaces the county-population-center stand-in for trial locations.

Previously every trial was placed at its county's population center, and a resident's own county's trials were 0 miles away
regardless of county size. Now each recruiting site is located at its ZIP-code centroid (ZCTA), with the same state check the
county assignment uses (a ZIP whose state disagrees with the site's stated state is rejected — e.g. a Los Angeles site listed with
a Boston ZIP falls through to the city gazetteer, exactly as it did for county assignment), then the city centroid, then — only
if nothing else is available — the county population center (flagged).

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
from tier4_covering import prepare_graph, norm, to5070

REF, OUT, ROADS, RAW = Path("data/ref"), Path("out_adult55"), Path("data/roads"), Path("data/raw")
M2MI = 1 / 1609.344; SPEED_ACCESS = 35.0; MAX_ACCESS_MI = 30.0; BAND_MAX = 120.0


def main():
    t0 = time.time(); log = {}
    nodes, A, tree, aidx = prepare_graph(); n = len(nodes); print(f"graph ready {time.time()-t0:.0f}s", flush=True)
    trials = pd.read_csv(RAW / "trials.csv", dtype=str, keep_default_na=False); trials = trials[pd.to_numeric(trials.max_age_years, errors="coerce").fillna(999) >= 55].reset_index(drop=True)
    j_of = {nct: j for j, nct in enumerate(trials.nct_id)}
    sites = pd.read_csv(OUT / "site_assignment_qc.csv", dtype=str).fillna(""); sites = sites[(sites.county_fips != "") & sites.nct_id.isin(j_of)].copy()
    sites["zip5"] = sites.zip.str.extract(r"(\d{5})", expand=False).fillna("")
    zc = pd.read_csv(REF / "zcta_pop55.csv", dtype={"zcta": str}).set_index("zcta"); z2c = dict(pd.read_csv(REF / "zcta_county.csv", dtype=str).values)
    gz = pd.read_csv(REF / "gazetteer_places.csv", dtype={"state": str, "place": str}).drop_duplicates(["state", "place"]).set_index(["state", "place"])
    cent = pd.read_csv(REF / "county_centroids.csv", dtype={"county_fips": str, "state_fips": str}).set_index("county_fips")
    lat, lon, how = [], [], []
    for r in sites.itertuples():
        zcty = z2c.get(r.zip5)
        if r.zip5 in zc.index and zcty and zcty[:2] == r.county_fips[:2]:
            lat.append(zc.loc[r.zip5, "lat"]); lon.append(zc.loc[r.zip5, "lon"]); how.append("zip_centroid"); continue
        key = (r.state, str(r.city).strip().lower()); c = cent.loc[r.county_fips]
        if key in gz.index:
            glat, glon = gz.loc[key, "lat"], gz.loc[key, "lon"]
            # the city name must agree with the assigned county: a registry row like city "Dallas" + ZIP 75521 (Atlanta, TX) was
            # assigned to Cass County by ZIP, and must not be drawn 180 miles away in Dallas. 40 mi ~ the radius of a large county.
            if np.hypot((glat - c.lat) * 69.0, (glon - c.lon) * 69.0 * np.cos(np.radians(c.lat))) <= 40:
                lat.append(glat); lon.append(glon); how.append("city_centroid"); continue
            lat.append(c.lat); lon.append(c.lon); how.append("county_centroid_city_disagrees"); continue
        lat.append(c.lat); lon.append(c.lon); how.append("county_centroid")
    sites["lat"], sites["lon"], sites["geocode"] = lat, lon, how
    log["site_rows"] = len(sites); log["geocode"] = sites.geocode.value_counts().to_dict()
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
    np.savez_compressed(ROADS / "route_cache_sites.npz", tract=tr.tract.values.astype(str), county_fips=cent.index.values.astype(str),
                        sp_lat=pts.lat.values, sp_lon=pts.lon.values, sp_county=pts.county_fips.values.astype(str), sp_n_facilities=pts.n_facilities.values,
                        S_indptr=S.indptr, S_indices=S.indices, S_shape=np.array(S.shape), trial_ids=trials.nct_id.values.astype(str),
                        pt_src=pt_src, pt_t=pt_t, pt_mi=pt_mi, pc_src=pc_src, pc_c=pc_c, pc_mi=pc_mi)
    pts[["sp", "lat", "lon", "county_fips", "geocode", "n_trials", "n_facilities"]].to_csv(OUT / "sitepoints.csv", index=False)
    sites[["nct_id", "facility", "city", "state", "zip5", "county_fips", "geocode", "sp"]].to_csv(OUT / "site_geocode_qc.csv", index=False)
    log["seconds"] = round(time.time() - t0); json.dump(log, open(OUT / "route_sites_log.json", "w"), indent=2); print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
