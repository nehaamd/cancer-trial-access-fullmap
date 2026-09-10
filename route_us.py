"""Tier 2.1 (part 2) — routing on the national highway graph.

For every county population center (2020 Census) and every census-tract internal point:
  * road miles (and indicative drive hours along the same shortest-mile route) to the nearest broad-menu county (>=100 trials),
    limited-menu county (>=20 trials) and NCI-designated treating center;
  * the set of trial-hosting counties within 120 road-miles (used for "trials within 30/60/120 road-miles" pools).
Also: 30 published city-pair driving distances re-computed on the graph (router validation).

Points are joined to the graph by a straight-line "access" edge to the nearest road node (35 mph), exactly as in the Texas build.
Counties and NCI centers get their own graph node (so they can be Dijkstra sources); tracts are leaves (distance = nearest
road node's distance + access length), which is numerically identical to giving them a node.

Outputs: out_adult55/county_road_distances.csv, out_adult55/road_validation.csv, out_adult55/county_pairs_within_120rdmi.csv,
         data/roads/route_cache.npz (tract-level arrays), out_adult55/route_log.json
"""
import json, time
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from scipy import sparse
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import dijkstra
import config

REF, OUT, ROADS = Path("data/ref"), Path("out_adult55"), Path("data/roads")
SPEED_ACCESS = 35.0; M2MI = 1 / 1609.344; NOROAD = 999.0  # 999 = no road connection (island / disconnected network); never a real distance
LIM, BRD = config.MENU_THRESHOLDS["limited"], config.MENU_THRESHOLDS["broad"]

# Published driving distances, city centre to city centre, approximate Google Maps / AAA values (rounded). Chosen to span flat
# (Plains, Florida), mountainous (Rockies, Appalachians, Sierra) and sparse (Dakotas, Wyoming, Alaska) terrain.
VALIDATION = [
 ("Los Angeles", "06037", "San Francisco", "06075", 382), ("Los Angeles", "06037", "Las Vegas", "32003", 270), ("Los Angeles", "06037", "Phoenix", "04013", 373),
 ("Phoenix", "04013", "Albuquerque", "35001", 420), ("Denver", "08031", "Salt Lake City", "49035", 520), ("Denver", "08031", "Kansas City MO", "29095", 605),
 ("Seattle", "53033", "Portland", "41051", 174), ("Seattle", "53033", "Spokane", "53063", 280), ("Portland", "41051", "Boise", "16001", 430),
 ("Salt Lake City", "49035", "Boise", "16001", 340), ("Chicago", "17031", "Minneapolis", "27053", 408), ("Chicago", "17031", "St. Louis", "29510", 297),
 ("Chicago", "17031", "Detroit", "26163", 283), ("Minneapolis", "27053", "Fargo", "38017", 234), ("Billings", "30111", "Bismarck", "38015", 414),
 ("Atlanta", "13121", "Nashville", "47037", 250), ("Atlanta", "13121", "Charlotte", "37119", 245), ("Atlanta", "13121", "Jacksonville", "12031", 346),
 ("New York", "36061", "Boston", "25025", 215), ("New York", "36061", "Washington DC", "11001", 226), ("Washington DC", "11001", "Pittsburgh", "42003", 245),
 ("Miami", "12086", "Orlando", "12095", 236), ("Miami", "12086", "Tampa", "12057", 280), ("Memphis", "47157", "Nashville", "47037", 212),
 ("New Orleans", "22071", "Houston", "48201", 350), ("Oklahoma City", "40109", "Kansas City MO", "29095", 350), ("Omaha", "31055", "Denver", "08031", 540),
 ("Las Vegas", "32003", "Salt Lake City", "49035", 420), ("Rapid City", "46103", "Sioux Falls", "46099", 348), ("Cheyenne", "56021", "Casper", "56025", 178),
 ("Little Rock", "05119", "Memphis", "47157", 137), ("Reno", "32031", "Sacramento", "06067", 132), ("Bangor", "23019", "Boston", "25025", 236),
 ("Missoula", "30063", "Billings", "30111", 344), ("Charleston WV", "54039", "Pittsburgh", "42003", 227), ("Anchorage", "02020", "Fairbanks", "02090", 358),
 ("El Paso", "48141", "San Antonio", "48029", 552), ("Amarillo", "48375", "Oklahoma City", "40109", 260),
]


def to5070(lon, lat):
    p = gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs=4326).to_crs(5070); return np.column_stack([p.x.values, p.y.values])


def main():
    t0 = time.time(); log = {}
    z = np.load(ROADS / "graph_us.npz"); nodes = z["nodes"]; n = len(nodes); comp = z["comp"]
    eu, ev, emi, ehr = z["u"].astype(np.int64), z["v"].astype(np.int64), z["mi"].astype(np.float64), z["hr"].astype(np.float64)
    # --- which components may points attach to? The mainland network, plus Alaska / Hawaii components of >=100 nodes.
    #     Everything else is a stray fragment of TIGER linework (a topology break); fragments of >=50 nodes are bridged to the
    #     nearest attachable node with a connector if the gap is <= 5 km, otherwise ignored. ---
    sizes = np.bincount(comp); main = int(sizes.argmax())
    lonlat = gpd.GeoSeries(gpd.points_from_xy(nodes[:, 0], nodes[:, 1]), crs=5070).to_crs(4326)
    cx = pd.DataFrame({"comp": comp, "lon": lonlat.x.values, "lat": lonlat.y.values}).groupby("comp").mean()
    akhi = (cx.lon < -130) | (cx.lat < 23)
    eligible = np.zeros(len(sizes), bool); eligible[main] = True; eligible[(sizes >= 100) & akhi.reindex(range(len(sizes))).fillna(False).values] = True
    etree = cKDTree(nodes[eligible[comp]]); eidx = np.where(eligible[comp])[0]
    bridged, bu, bv, bmi = [], [], [], []
    for c in np.where((~eligible) & (sizes >= 50))[0]:
        members = np.where(comp == c)[0]; d, i = etree.query(nodes[members]); k = int(d.argmin())
        if d[k] <= 5000: bu.append(int(members[k])); bv.append(int(eidx[i[k]])); bmi.append(float(d[k]) * M2MI); bridged.append((int(c), int(sizes[c]), round(float(d[k]))))
    log["fragments_bridged"] = {"n": len(bridged), "detail(component,nodes,gap_m)": bridged[:40], "fragments_ge50_not_bridged": int(((~eligible) & (sizes >= 50)).sum() - len(bridged))}
    eu = np.concatenate([eu, np.array(bu, np.int64)]); ev = np.concatenate([ev, np.array(bv, np.int64)])
    emi = np.concatenate([emi, np.array(bmi)]); ehr = np.concatenate([ehr, np.array(bmi) / 25.0])
    for c, _, _ in bridged: eligible[c] = True
    attach_ok = eligible[comp]; tree = cKDTree(nodes[attach_ok]); aidx = np.where(attach_ok)[0]
    log["attachable_nodes_share"] = round(float(attach_ok.mean()), 4)
    MAX_ACCESS_MI = 30.0  # a point more than 30 straight-line miles from any primary/secondary road is "off the road network"
    cent = pd.read_csv(REF / "county_centroids.csv", dtype={"county_fips": str, "state_fips": str})
    cm = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str, "state_fips": str}).set_index("county_fips")
    nci = pd.read_csv(REF / "nci_centers.csv")
    tr = pd.read_csv(REF / "tracts_us.csv", dtype={"tract": str, "county_fips": str})
    # --- county and NCI nodes appended to the graph with access edges ---
    cxy = to5070(cent.lon.values, cent.lat.values); cd, ci = tree.query(cxy); ci = aidx[ci]
    nxy = to5070(nci.lon.values, nci.lat.values); nd, ni = tree.query(nxy); ni = aidx[ni]
    c_off = cd * M2MI > MAX_ACCESS_MI; cd = np.where(c_off, 1e9, cd)  # off-network county centres: access edge effectively infinite
    log["counties_off_road_network_gt30mi"] = [f"{r.county_name} ({r.state_fips})" for r, o in zip(cent.itertuples(), c_off) if o]
    nc, nn = len(cent), len(nci)
    c_node = np.arange(n, n + nc); n_node = np.arange(n + nc, n + nc + nn); N = n + nc + nn
    au = np.concatenate([eu, c_node, n_node]); av = np.concatenate([ev, ci, ni])
    ami = np.concatenate([emi, cd * M2MI, nd * M2MI]); ahr = np.concatenate([ehr, cd * M2MI / SPEED_ACCESS, nd * M2MI / SPEED_ACCESS])
    A = sparse.coo_matrix((np.concatenate([ami, ami]), (np.concatenate([au, av]), np.concatenate([av, au]))), shape=(N, N)).tocsr()
    H = sparse.coo_matrix((np.concatenate([ahr, ahr]), (np.concatenate([au, av]), np.concatenate([av, au]))), shape=(N, N)).tocsr()
    from scipy.sparse.csgraph import connected_components as _cc
    _, comp_ext = _cc(A, directed=False); comp = comp_ext[:n]
    log["county_access_mi"] = {"median": round(float(np.median(cd) * M2MI), 2), "p90": round(float(np.percentile(cd, 90) * M2MI), 2), "max": round(float(cd.max() * M2MI), 1)}
    # --- tracts as leaves ---
    txy = to5070(tr.lon.values, tr.lat.values); td, ti = tree.query(txy); ti = aidx[ti]; t_acc = td * M2MI
    t_off = t_acc > MAX_ACCESS_MI; t_acc = np.where(t_off, np.inf, t_acc)
    log["tracts_off_road_network_gt30mi"] = {"n": int(t_off.sum()), "pop55": int(tr.pop55.values[t_off].sum()), "of_which_alaska": int((t_off & (tr.county_fips.str[:2] == "02").values).sum())}
    log["tract_access_mi"] = {"median": round(float(np.median(t_acc)), 2), "p90": round(float(np.percentile(t_acc, 90)), 2), "max": round(float(t_acc.max()), 1)}
    fips = cent.county_fips.values; trials = cm.reindex(fips).trials_in_county.fillna(0).astype(int).values
    broad_src = c_node[trials >= BRD]; lim_src = c_node[trials >= LIM]; trial_src_mask = trials > 0

    def hours_along_tree(dist, pred, sources_idx):
        """Drive hours along the shortest-mile tree returned by dijkstra(min_only=True, return_predecessors=True)."""
        order = np.argsort(dist); order = order[np.isfinite(dist[order])]
        hr = np.full(N, np.inf); hr[sources_idx] = 0.0
        p = pred[order]; ok = p >= 0
        o, p = order[ok], p[ok]
        eh = np.asarray(H[p, o]).ravel()
        hr_list = hr  # sequential accumulation in distance order (a parent is always processed before its children)
        for k in range(len(o)):
            hr_list[o[k]] = hr_list[p[k]] + eh[k]
        return hr

    def nearest(sources, label):
        dist, pred, src = dijkstra(A, directed=False, indices=sources, min_only=True, return_predecessors=True)
        hr = hours_along_tree(dist, pred, sources)
        print(f"  {label}: {len(sources)} sources, {time.time()-t0:.0f}s", flush=True)
        return dist, hr, src

    Db, Hb, Sb = nearest(broad_src, "broad menu"); Dl, Hl, Sl = nearest(lim_src, "limited menu"); Dn, Hn, Sn = nearest(n_node, "NCI centers")
    cname = {c: f"{r.county_name}, {r.state_name}" for c, r in zip(c_node, cent.itertuples())}; nname = dict(zip(n_node, nci.name))

    def county_row(k):
        node = c_node[k]; f = fips[k]; r = {"county_fips": f, "county_name": cent.county_name.iat[k], "state_fips": cent.state_fips.iat[k], "trials_in_county": int(trials[k]),
                                          "access_mi": round(float(cd[k] * M2MI), 1) if not c_off[k] else NOROAD, "on_main_network": int(comp_ext[node] == np.bincount(comp).argmax())}
        for lab, D, Hh, S, thr, names in (("broad", Db, Hb, Sb, BRD, cname), ("limited", Dl, Hl, Sl, LIM, cname), ("nci", Dn, Hn, Sn, None, nname)):
            if thr is not None and trials[k] >= thr:
                r[f"nearest_{lab}"] = cname[node]; r[f"road_mi_{lab}"] = 0.0; r[f"drive_hr_{lab}"] = 0.0; continue
            d = D[node] if not c_off[k] else np.inf  # off-network centres have no road distance at all
            if np.isfinite(d): r[f"nearest_{lab}"] = names[int(S[node])]; r[f"road_mi_{lab}"] = round(float(d), 1); r[f"drive_hr_{lab}"] = round(float(Hh[node]), 2)
            else: r[f"nearest_{lab}"] = "OFF ROAD NETWORK (>30 mi from a primary/secondary road)" if c_off[k] else "NO ROAD CONNECTION (island / disconnected network)"; r[f"road_mi_{lab}"] = NOROAD; r[f"drive_hr_{lab}"] = NOROAD
        r["straightline_x1_2_broad"] = round(float(cm.loc[f, "dist_to_broad_mi"]), 1); r["straightline_x1_2_limited"] = round(float(cm.loc[f, "dist_to_limited_mi"]), 1)
        r["straightline_x1_2_nci"] = round(float(cm.loc[f, "dist_to_nci_mi"]), 1); r["straightline_nearest_nci"] = cm.loc[f, "nearest_nci"]
        return r
    rd = pd.DataFrame([county_row(k) for k in range(nc)]); rd.to_csv(OUT / "county_road_distances.csv", index=False)
    unr = rd[(rd.road_mi_broad >= NOROAD) | (rd.road_mi_limited >= NOROAD) | (rd.road_mi_nci >= NOROAD)]
    log["counties_no_road_route"] = {"n": len(unr), "broad": int((rd.road_mi_broad >= NOROAD).sum()), "limited": int((rd.road_mi_limited >= NOROAD).sum()), "nci": int((rd.road_mi_nci >= NOROAD).sum()),
                                     "list": [f"{r.county_name} ({r.state_fips})" for r in unr.itertuples()]}
    # --- tract-level nearest distances (leaf = nearest node + access) ---
    tb, tl, tn = Db[ti] + t_acc, Dl[ti] + t_acc, Dn[ti] + t_acc
    tb_hr, tl_hr, tn_hr = Hb[ti] + t_acc / SPEED_ACCESS, Hl[ti] + t_acc / SPEED_ACCESS, Hn[ti] + t_acc / SPEED_ACCESS
    t_own = cm.reindex(tr.county_fips).trials_in_county.fillna(0).astype(int).values
    tb[t_own >= BRD] = 0; tl[t_own >= LIM] = 0; tb_hr[t_own >= BRD] = 0; tl_hr[t_own >= LIM] = 0  # a tract in a menu county is at the menu
    tb_src = np.where(np.isfinite(tb), Sb[ti], -1); tl_src = np.where(np.isfinite(tl), Sl[ti], -1); tn_src = np.where(np.isfinite(tn), Sn[ti], -1)
    # --- per-trial-county limited Dijkstra: county-county and county-tract pairs within 120 road-miles ---
    src_idx = np.where(trial_src_mask)[0]; pairs_c, pairs_t = [], []
    B = 8; cutoff = 120.0 + float(t_acc[np.isfinite(t_acc)].max()) + 0.01; import resource, gc
    for b0 in range(0, len(src_idx), B):
        idx = src_idx[b0:b0 + B]
        D = dijkstra(A, directed=False, indices=c_node[idx], min_only=False, limit=cutoff)
        dc = D[:, c_node].astype(np.float32); dt = D[:, ti].astype(np.float32); del D; gc.collect()
        ok = dc <= 120.0; s_i, c_i = np.where(ok); pairs_c.append((idx[s_i].astype(np.int32), c_i.astype(np.int32), dc[ok]))
        dt += t_acc[None, :].astype(np.float32); ok = dt <= 120.0; s_i, t_i = np.where(ok); pairs_t.append((idx[s_i].astype(np.int32), t_i.astype(np.int32), dt[ok]))
        del dc, dt, ok
        if (b0 // B) % 10 == 0: print(f"  pools batch {b0//B+1}/{(len(src_idx)+B-1)//B}, {time.time()-t0:.0f}s, peak RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB", flush=True)
    pairs_c = np.column_stack([np.concatenate([p[i] for p in pairs_c]) for i in range(3)]); pairs_t = np.column_stack([np.concatenate([p[i] for p in pairs_t]) for i in range(3)])
    # a county is within 0 miles of itself
    pc = pd.DataFrame({"trial_county_fips": fips[pairs_c[:, 0].astype(int)], "county_fips": fips[pairs_c[:, 1].astype(int)], "road_mi": np.round(pairs_c[:, 2], 1)})
    pc.loc[pc.trial_county_fips == pc.county_fips, "road_mi"] = 0.0
    pc.to_csv(OUT / "county_pairs_within_120rdmi.csv", index=False)
    pt_src = pairs_t[:, 0].astype(np.int32); pt_t = pairs_t[:, 1].astype(np.int32); pt_mi = pairs_t[:, 2].astype(np.float32)
    own = t_own > 0; own_src = pd.Series(np.arange(nc), index=fips).reindex(tr.county_fips).values  # tract's own county index
    own_pairs = np.column_stack([own_src[own], np.where(own)[0], np.zeros(own.sum())])
    pt_src = np.concatenate([pt_src, own_pairs[:, 0].astype(np.int32)]); pt_t = np.concatenate([pt_t, own_pairs[:, 1].astype(np.int32)]); pt_mi = np.concatenate([pt_mi, own_pairs[:, 2].astype(np.float32)])
    np.savez_compressed(ROADS / "route_cache.npz", tract=tr.tract.values.astype(str), tract_county=tr.county_fips.values.astype(str), county_fips=fips.astype(str),
                        t_broad=tb, t_lim=tl, t_nci=tn, t_broad_hr=tb_hr, t_lim_hr=tl_hr, t_nci_hr=tn_hr,
                        t_broad_src=np.where(tb_src >= 0, tb_src - n, -1), t_lim_src=np.where(tl_src >= 0, tl_src - n, -1), t_nci_src=np.where(tn_src >= 0, tn_src - n - nc, -1),
                        t_component=comp_ext[ti], t_access_mi=np.where(np.isfinite(t_acc), t_acc, NOROAD), t_off_network=t_off, pt_src=pt_src, pt_t=pt_t, pt_mi=pt_mi, main_component=np.bincount(comp).argmax())
    log["tracts"] = len(tr); log["tract_no_road_route"] = {"broad": int((~np.isfinite(tb)).sum()), "limited": int((~np.isfinite(tl)).sum()), "nci": int((~np.isfinite(tn)).sum()),
                                                            "pop55_no_route_to_broad": int(tr.pop55.values[~np.isfinite(tb)].sum())}
    log["tract_pairs_within_120rdmi"] = int(len(pt_src)); log["county_pairs_within_120rdmi"] = int(len(pc))
    # --- router validation on published city pairs ---
    val = []; k_of = {f: k for k, f in enumerate(fips)}
    for a, fa, b, fb, pub in VALIDATION:
        D = dijkstra(A, directed=False, indices=[c_node[k_of[fa]]], min_only=True); mi = float(D[c_node[k_of[fb]]])
        val.append({"from": a, "to": b, "published_road_mi": pub, "network_mi": round(mi) if np.isfinite(mi) else None, "pct_diff": round(100 * (mi - pub) / pub, 1) if np.isfinite(mi) else None})
    vdf = pd.DataFrame(val); vdf.to_csv(OUT / "road_validation.csv", index=False)
    log["router_validation"] = {"pairs": len(vdf), "mean_abs_pct_diff": round(float(vdf.pct_diff.abs().mean()), 1), "max_abs_pct_diff": round(float(vdf.pct_diff.abs().max()), 1),
                                "unroutable_pairs": int(vdf.network_mi.isna().sum())}
    okm = (rd.road_mi_broad > 0) & (rd.road_mi_broad < NOROAD); ratio = rd.road_mi_broad[okm] / (rd.straightline_x1_2_broad[okm] / config.ROAD_FACTOR)
    log["road_over_straightline_ratio_broad"] = {"median": round(float(ratio.median()), 3), "p10": round(float(ratio.quantile(.1)), 3), "p90": round(float(ratio.quantile(.9)), 3),
                                                 "counties_where_x1_2_underestimated": int((ratio > config.ROAD_FACTOR).sum()), "counties_compared": int(okm.sum())}
    log["seconds"] = round(time.time() - t0)
    json.dump(log, open(OUT / "route_log.json", "w"), indent=2); print(json.dumps(log, indent=1)); print(vdf.to_string(index=False))


if __name__ == "__main__":
    main()
