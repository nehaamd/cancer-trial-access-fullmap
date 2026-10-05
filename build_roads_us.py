"""Tier 2.1 (part 1) — build the national highway graph from Census TIGER primary/secondary roads, all 50 states + DC.

Source and speeds are the Texas v2 method (tx_v2_road_network_template/build_roads.py):
  * TIGER 2025 PRISECROADS, classes S1100 (interstates/freeways) and S1200 (US/state highways), projected to EPSG:5070
  * lines simplified to 30 m, then noded so every crossing becomes a graph node (done one state at a time to bound memory)
  * nodes keyed on a 1 m grid
  * speeds for the indicative drive time: S1100 65 mph, S1200 50 mph, connectors 25 mph, access edges 35 mph

How the graph is stitched (revised October 2026 — see "Why" below):
  1. DENSIFY. Every noded segment is cut into equal pieces no longer than DENSIFY_M (400 m), so there is a node at least every
     400 m along every road. A place therefore joins the network at the nearest point of the nearest road, not at whatever
     crossing or line end happens to be nearest.
  2. JUNCTION CONNECTORS. TIGER omits ramps, so nodes of different roads within CONNECTOR_M (500 m) are joined by a short
     "connector" edge — but only where both nodes are junction nodes (crossings or line ends, i.e. the nodes the original build
     had) or one of them is the end of a line. Two mid-road points of roads that merely pass near each other are never joined:
     that would link the two banks of every river with a highway along each side. Nor are the two ends of one stretch of road
     (the road already joins them; a straight link would cut off its bends).
  3. LAND GUARD. A connector longer than GUARD_OVER_M (250 m) is kept only if the straight link lies wholly inside one county
     polygon of the Census cartographic boundary file (which is clipped to the shoreline). County lines follow the large rivers,
     lakes and sounds, so a kept link crosses neither a county line nor coastal water.
  4. DEAD-END BRIDGES. A highway designation often stops a little short of the next highway (the pavement carries on as a city
     street that is not in this file), which leaves a dead end. Each end of TIGER linework is linked to the nearest node within
     BRIDGE_M (5 km) that it cannot already reach by a route shorter than 3 x 1.2 x the straight-line gap + 0.5 mi, provided the
     link passes the land guard. A bridge is a connector edge (25 mph) whose length is the gap x 1.2, the same straight-line
     inflation used elsewhere in the project.

Why: the first national build had nodes only at crossings and line ends and joined every pair of nodes within 500 m. Places
then attached to far-away or dangling nodes. Example: a south-Tucson tract attached to the dead end of a 33-mile one-way
carriageway of I-19 and was scored 296 road-miles from a hospital 7 miles away; Kalispell, Spokane, Pueblo and Duluth had the
same fault. route_us.py re-checks a table of such local trips (and of water crossings that must stay long) on every run.

The graph is stored as numpy edge arrays + a scipy.sparse CSR matrix (a networkx graph of this size does not fit in memory).

Outputs: data/roads/seg_<state>.npz (per-state noded, densified segments), data/roads/graph_us.npz (nodes, edges),
         data/roads/graph_stats.json
"""
import gc, heapq, io, json, sys, time, zipfile
from pathlib import Path
import numpy as np, pandas as pd, requests
import geopandas as gpd, shapely
from scipy.spatial import cKDTree
from scipy import sparse
from scipy.sparse.csgraph import connected_components

ROADS = Path("data/roads"); ROADS.mkdir(parents=True, exist_ok=True)
GEO = Path("data/geo")
STATES = [f"{i:02d}" for i in range(1, 57) if f"{i:02d}" not in ("03", "07", "14", "43", "52")]  # 50 states + DC
SPEED = {"S1100": 65.0, "S1200": 50.0, "connector": 25.0, "access": 35.0}
KIND = {"S1100": 0, "S1200": 1, "connector": 2, "access": 3}
M2MI = 1 / 1609.344
TIGER = "https://www2.census.gov/geo/tiger/TIGER2025/PRISECROADS/tl_2025_{st}_prisecroads.zip"
COUNTIES = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"   # same file the refresh workflow keeps in data/geo/cb.zip

DENSIFY_M = 400.0        # a node at least this often along every road
CONNECTOR_M = 500.0      # junction nodes of different roads closer than this are joined (TIGER has no ramps)
GUARD_OVER_M = 250.0     # connectors longer than this must stay inside one county polygon
BRIDGE_M = 5000.0        # a dead end is linked to another road at most this far away
BRIDGE_FACTOR = 1.2      # bridge length = straight-line gap x this (config.ROAD_FACTOR)
BRIDGE_DETOUR = 3.0      # ... only if the existing route is longer than DETOUR x FACTOR x gap + SLACK
BRIDGE_SLACK_MI = 0.5
GRAPH_VERSION = 2        # bump when the stitching rules change; the refresh workflow's cache key carries the same number


def _get(url, path, what):
    """Download with a size / zip check and three attempts (?v= busts a stale CDN rejection page)."""
    if path.exists() and path.stat().st_size > 1000 and zipfile.is_zipfile(path): return path
    for attempt in range(3):
        try:
            r = requests.get(url + (f"?v={attempt+1}" if attempt else ""), timeout=300); r.raise_for_status()
            want = int(r.headers.get("Content-Length") or 0)
            if (want and len(r.content) != want) or not zipfile.is_zipfile(io.BytesIO(r.content)): raise IOError(f"bad download ({len(r.content)} of {want} bytes)")
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(r.content); return path
        except Exception as e:
            print(f"  download of {what} failed ({e}); retry", flush=True); time.sleep(5)
    raise SystemExit(f"could not download {what}")


def download(st):
    return _get(TIGER.format(st=st), ROADS / f"tl_2025_{st}_prisecroads.zip", f"roads for state {st}")


def node_state(st):
    """Noded, densified segments for one state -> arrays (x0,y0,x1,y1,len_m,kind,o0,o1). Cached in seg_<st>.npz.
    o0 / o1 flag the segment ends that are junction nodes (a crossing or a line end) rather than points added by densifying."""
    out = ROADS / f"seg_{st}.npz"
    if out.exists():
        z = np.load(out)
        if "o0" in z.files and float(z["densify_m"]) == DENSIFY_M: return
    g = gpd.read_file(f"zip://{download(st)}")[["MTFCC", "geometry"]]
    g = g[g.MTFCC.isin(["S1100", "S1200"])].to_crs(5070).explode(index_parts=False, ignore_index=True)
    g["geometry"] = g.geometry.simplify(30, preserve_topology=True)
    noded = shapely.node(shapely.multilinestrings(list(g.geometry)))
    segs = gpd.GeoDataFrame(geometry=list(shapely.get_parts(noded)), crs=5070); del noded
    segs = segs[segs.geometry.length > 0].reset_index(drop=True)
    mids = gpd.GeoDataFrame(geometry=segs.geometry.interpolate(0.5, normalized=True), crs=5070)
    j = gpd.sjoin_nearest(mids, g[["MTFCC", "geometry"]], how="left", max_distance=60); j = j[~j.index.duplicated(keep="first")]
    cls = j.MTFCC.reindex(segs.index).fillna("S1200").map(KIND).values.astype(np.int8)
    geom = segs.geometry.values; length = shapely.length(geom)
    k = np.maximum(1, np.ceil(length / DENSIFY_M)).astype(np.int64)                 # pieces per segment
    rep = np.repeat(np.arange(len(geom)), k); i_in = np.arange(len(rep)) - np.repeat(np.cumsum(k) - k, k)
    p0 = shapely.get_coordinates(shapely.line_interpolate_point(geom[rep], i_in / k[rep], normalized=True))
    p1 = shapely.get_coordinates(shapely.line_interpolate_point(geom[rep], (i_in + 1) / k[rep], normalized=True))
    np.savez_compressed(out, x0=p0[:, 0], y0=p0[:, 1], x1=p1[:, 0], y1=p1[:, 1], len_m=(length / k)[rep], kind=cls[rep], n_tiger=len(g), n_noded=len(segs),
                        o0=(i_in == 0), o1=(i_in == k[rep] - 1), densify_m=DENSIFY_M)
    print(f"  state {st}: {len(g)} TIGER lines -> {len(segs)} noded segments -> {len(rep)} pieces of <= {DENSIFY_M:.0f} m", flush=True)
    del g, segs, mids, j, geom; gc.collect()


def county_polygons():
    """County polygons (EPSG:5070) from the Census cartographic boundary file, prepared for fast containment tests."""
    g = gpd.read_file(f"zip://{_get(COUNTIES, GEO / 'cb.zip', 'county boundaries')}")[["GEOID", "geometry"]].to_crs(5070).reset_index(drop=True)
    polys = g.geometry.values
    for q in polys: shapely.prepare(q)
    return g, polys


def county_index(nodes, g):
    """Index of the county polygon containing each node; -1 = outside every polygon (e.g. on a bridge over coastal water)."""
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(nodes[:, 0], nodes[:, 1]), crs=5070)
    j = gpd.sjoin(pts, g[["geometry"]], how="left", predicate="within"); j = j[~j.index.duplicated(keep="first")]
    return j.index_right.reindex(range(len(nodes))).fillna(-1).astype(np.int32).values


def on_land(nodes, pu, pv, cidx, polys):
    """True where the straight link pu-pv lies wholly inside the county polygon of pu: it crosses neither a county line nor coastal water."""
    pu = np.asarray(pu); pv = np.asarray(pv); ok = np.zeros(len(pu), bool); cu = cidx[pu]; same = (cu >= 0) & (cu == cidx[pv])
    if not same.any(): return ok
    idx = np.where(same)[0]; lines = shapely.linestrings(np.stack([nodes[pu[idx]], nodes[pv[idx]]], axis=1))
    order = np.argsort(cu[idx], kind="stable"); ci = cu[idx][order]; bounds = np.flatnonzero(np.r_[True, ci[1:] != ci[:-1], True])
    for a, b in zip(bounds[:-1], bounds[1:]):
        sel = order[a:b]; ok[idx[sel]] = shapely.contains(polys[ci[a]], lines[sel])
    return ok


def bridge_dead_ends(nodes, e, cidx, polys):
    """Step 4 of the docstring. Returns (bridge edges as a DataFrame, number of dead ends with a candidate but no link that stays on land)."""
    n = len(nodes); tig = e.kind.values < KIND["connector"]
    A = sparse.coo_matrix((np.concatenate([e.mi.values, e.mi.values]), (np.concatenate([e.u.values, e.v.values]), np.concatenate([e.v.values, e.u.values]))), shape=(n, n)).tocsr()
    indptr, indices, data = A.indptr, A.indices, A.data
    ends = np.where(np.bincount(np.concatenate([e.u.values[tig], e.v.values[tig]]), minlength=n) == 1)[0]
    near_all = cKDTree(nodes).query_ball_point(nodes[ends], BRIDGE_M); add_u, add_v, add_mi, rejected = [], [], [], 0
    for u, near in zip(ends.tolist(), near_all):
        if len(near) <= 1 or cidx[u] < 0: continue
        near = np.array(near); near = near[(near != u) & (cidx[near] == cidx[u])]
        if not len(near): continue
        sl = np.hypot(nodes[near, 0] - nodes[u, 0], nodes[near, 1] - nodes[u, 1]) * M2MI; thr = BRIDGE_DETOUR * BRIDGE_FACTOR * sl + BRIDGE_SLACK_MI
        need = set(near.tolist()); lim = float(thr.max()); left = len(need)
        dist = {u: 0.0}; pq = [(0.0, u)]; done = set()          # Dijkstra from the dead end, stopped once every candidate is settled or out of range
        while pq and left:
            d, a = heapq.heappop(pq)
            if d > dist[a] or a in done: continue
            done.add(a)
            if a in need: left -= 1
            lo, hi = indptr[a], indptr[a + 1]
            for b, w in zip(indices[lo:hi].tolist(), data[lo:hi].tolist()):
                nd = d + w
                if nd <= lim and nd < dist.get(b, 1e18): dist[b] = nd; heapq.heappush(pq, (nd, b))
        net = np.array([dist[q] if q in done else 1e18 for q in near.tolist()]); far = np.where(net > thr)[0]
        if not len(far): continue
        far = far[np.argsort(sl[far], kind="stable")][:12]      # nearest candidates first; take the first whose link stays on land
        ok = on_land(nodes, np.full(len(far), u), near[far], cidx, polys)
        if not ok.any(): rejected += 1; continue
        k = far[np.argmax(ok)]; c = int(near[k]); add_u.append(min(u, c)); add_v.append(max(u, c)); add_mi.append(float(sl[k]) * BRIDGE_FACTOR)
    b = pd.DataFrame({"u": np.array(add_u, np.int64), "v": np.array(add_v, np.int64), "mi": np.array(add_mi, float), "kind": np.full(len(add_u), KIND["connector"], np.int8)}).drop_duplicates(["u", "v"])
    return b, len(ends), rejected


def assemble():
    t0 = time.time(); xs, ys, xe, ye, L, K, O0, O1, ntig, nnoded = [], [], [], [], [], [], [], [], 0, 0
    for st in STATES:
        z = np.load(ROADS / f"seg_{st}.npz")
        xs.append(z["x0"]); ys.append(z["y0"]); xe.append(z["x1"]); ye.append(z["y1"]); L.append(z["len_m"]); K.append(z["kind"]); O0.append(z["o0"]); O1.append(z["o1"])
        ntig += int(z["n_tiger"]); nnoded += int(z["n_noded"])
    x0, y0, x1, y1 = (np.concatenate(a) for a in (xs, ys, xe, ye)); L = np.concatenate(L); K = np.concatenate(K); O = np.concatenate([np.concatenate(O0), np.concatenate(O1)]); del xs, ys, xe, ye, O0, O1
    # node keys on a 1 m grid (same as the Texas build's round(x), round(y))
    kx = np.concatenate([np.round(x0), np.round(x1)]).astype(np.int64); ky = np.concatenate([np.round(y0), np.round(y1)]).astype(np.int64)
    key = kx * 10_000_000 + ky  # y span in EPSG:5070 is < 1e7 m
    uniq, inv = np.unique(key, return_inverse=True)
    n_seg = len(L); u, v = inv[:n_seg], inv[n_seg:]
    nodes = np.stack([(uniq // 10_000_000).astype(np.float64), (uniq % 10_000_000).astype(np.float64)], axis=1); n = len(nodes)
    junction = np.zeros(n, bool); junction[inv[O]] = True                            # crossings and line ends (the nodes of the first build)
    # The two ends of every noded segment: the first build joined them by the road itself, so they never got a connector. A segment
    # cut into pieces must not get one either, or a hairpin bend would be cut off by a straight link. (Pieces of a segment are stored
    # together and in order: its first piece carries o0, its last piece o1.)
    n0 = len(O) // 2; a0, a1 = u[O[:n0]].astype(np.int64), v[O[n0:]].astype(np.int64); same_seg = np.unique(np.minimum(a0, a1) * n + np.maximum(a0, a1)); del a0, a1
    e = pd.DataFrame({"u": np.minimum(u, v), "v": np.maximum(u, v), "mi": L * M2MI, "kind": K})
    e = e[e.u != e.v]
    e = e.sort_values("mi", kind="stable").drop_duplicates(["u", "v"], keep="first").reset_index(drop=True)  # parallel edges: keep shortest
    line_end = np.bincount(np.concatenate([e.u.values, e.v.values]), minlength=n) == 1
    print(f"  {n:,} nodes ({int(junction.sum()):,} junction nodes, {int(line_end.sum()):,} line ends), {len(e):,} road edges [{time.time()-t0:.0f}s]", flush=True)
    # 2. junction connectors
    pairs = cKDTree(nodes).query_pairs(r=CONNECTOR_M, output_type="ndarray")
    pu, pv = np.minimum(pairs[:, 0], pairs[:, 1]).astype(np.int64), np.maximum(pairs[:, 0], pairs[:, 1]).astype(np.int64); del pairs
    keep = ~np.isin(pu * n + pv, e.u.values.astype(np.int64) * n + e.v.values.astype(np.int64))     # not already adjacent
    keep &= ~np.isin(pu * n + pv, same_seg)                                                         # nor the two ends of one stretch of road
    keep &= (junction[pu] & junction[pv]) | line_end[pu] | line_end[pv]
    pu, pv = pu[keep], pv[keep]; cm_ = np.hypot(nodes[pu, 0] - nodes[pv, 0], nodes[pu, 1] - nodes[pv, 1])
    # 3. land guard on the longer connectors
    g, polys = county_polygons(); cidx = county_index(nodes, g)
    chk = np.where(cm_ > GUARD_OVER_M)[0]; ok = on_land(nodes, pu[chk], pv[chk], cidx, polys)
    drop = np.zeros(len(pu), bool); drop[chk[~ok]] = True; n_conn_all = len(pu)
    pu, pv, cm_ = pu[~drop], pv[~drop], cm_[~drop]
    print(f"  connectors {n_conn_all:,}; longer than {GUARD_OVER_M:.0f} m: {len(chk):,}; dropped by the land guard: {int(drop.sum()):,} [{time.time()-t0:.0f}s]", flush=True)
    e = pd.concat([e, pd.DataFrame({"u": pu, "v": pv, "mi": cm_ * M2MI, "kind": np.full(len(pu), KIND["connector"], np.int8)})], ignore_index=True)
    # 4. dead-end bridges
    bridges, n_ends, rejected = bridge_dead_ends(nodes, e, cidx, polys)
    gaps = bridges.mi.values / BRIDGE_FACTOR / M2MI
    print(f"  line ends examined {n_ends:,}; bridged {len(bridges):,} within {BRIDGE_M:.0f} m; no link on land for {rejected:,} [{time.time()-t0:.0f}s]", flush=True)
    e = pd.concat([e, bridges], ignore_index=True)
    speed = np.array([SPEED["S1100"], SPEED["S1200"], SPEED["connector"], SPEED["access"]])
    e["hr"] = e.mi.values / speed[e.kind.values]
    A = sparse.coo_matrix((e.mi.values, (e.u.values, e.v.values)), shape=(n, n)).tocsr()
    ncomp, lab = connected_components(A, directed=False)
    sizes = np.bincount(lab); big = sizes.argmax()
    stats = {"graph_version": GRAPH_VERSION, "states": len(STATES), "edges_from_tiger": int(ntig), "noded_segments": int(nnoded), "segment_pieces": int(n_seg), "nodes": int(n),
             "junction_nodes": int(junction.sum()), "edges": int(len(e)),
             "connector_edges": int(len(pu)), "connectors_dropped_by_land_guard": int(drop.sum()), "dead_end_bridges": int(len(bridges)), "dead_ends_examined": int(n_ends), "dead_ends_no_link_on_land": int(rejected),
             "bridge_gap_m": {"median": round(float(np.median(gaps))) if len(gaps) else None, "p90": round(float(np.percentile(gaps, 90))) if len(gaps) else None, "max": round(float(gaps.max())) if len(gaps) else None},
             "components": int(ncomp), "largest_component_share": round(float(sizes[big]) / n, 4), "components_over_1000_nodes": int((sizes > 1000).sum()),
             "speeds_mph": SPEED, "densify_m": DENSIFY_M, "connector_radius_m": CONNECTOR_M, "connector_rule": "junction-to-junction or line end only", "land_guard_over_m": GUARD_OVER_M,
             "land_guard_source": "Census cartographic boundary file, counties 1:500k (2023)", "bridge_radius_m": BRIDGE_M, "bridge_length_factor": BRIDGE_FACTOR,
             "bridge_rule": f"existing route longer than {BRIDGE_DETOUR:g} x {BRIDGE_FACTOR:g} x gap + {BRIDGE_SLACK_MI:g} mi",
             "node_grid_m": 1, "simplify_m": 30, "source": "TIGER2025 PRISECROADS S1100+S1200",
             "note": "a node at least every 400 m and at every crossing; junctions within 500 m joined; highway dead ends within 5 km of another road linked across the gap; no link crosses a county line or coastal water"}
    np.savez_compressed(ROADS / "graph_us.npz", nodes=nodes, u=e.u.values.astype(np.int32), v=e.v.values.astype(np.int32),
                        mi=e.mi.values.astype(np.float32), hr=e.hr.values.astype(np.float32), kind=e.kind.values.astype(np.int8), comp=lab.astype(np.int32), graph_version=GRAPH_VERSION)
    json.dump(stats, open(ROADS / "graph_stats.json", "w"), indent=2); print(json.dumps(stats, indent=1), flush=True)


def load_graph():
    z = np.load(ROADS / "graph_us.npz"); n = len(z["nodes"])
    u, v = z["u"], z["v"]
    A_mi = sparse.coo_matrix((np.concatenate([z["mi"], z["mi"]]).astype(np.float64), (np.concatenate([u, v]), np.concatenate([v, u]))), shape=(n, n)).tocsr()
    A_hr = sparse.coo_matrix((np.concatenate([z["hr"], z["hr"]]).astype(np.float64), (np.concatenate([u, v]), np.concatenate([v, u]))), shape=(n, n)).tocsr()
    return z["nodes"], A_mi, A_hr, z["comp"]


def is_current():
    """True if data/roads/graph_us.npz exists and was built by this version of the rules (used by the refresh workflow)."""
    p = ROADS / "graph_us.npz"
    if not p.exists(): return False
    try: return int(np.load(p)["graph_version"]) == GRAPH_VERSION
    except Exception: return False


if __name__ == "__main__":
    if "--if-stale" in sys.argv and is_current():
        print(f"road graph is current (version {GRAPH_VERSION}); nothing to do"); sys.exit(0)
    t0 = time.time()
    for st in STATES:
        node_state(st); print(f"    [{st} done, {time.time()-t0:.0f}s]", flush=True)
    assemble(); print(f"graph built in {time.time()-t0:.0f}s", flush=True)
