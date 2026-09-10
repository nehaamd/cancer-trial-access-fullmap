"""Tier 2.1 (part 1) — build the national highway graph from Census TIGER primary/secondary roads, all 50 states + DC.

Method is the Texas v2 method (tx_v2_road_network_template/build_roads.py) unchanged:
  * TIGER 2025 PRISECROADS, classes S1100 (interstates/freeways) and S1200 (US/state highways), projected to EPSG:5070
  * lines simplified to 30 m, then noded so every crossing becomes a graph node (done one state at a time to bound memory)
  * nodes keyed on a 1 m grid; nodes of different roads within 500 m joined by short "connector" edges (TIGER omits ramps)
  * speeds for the indicative drive time: S1100 65 mph, S1200 50 mph, connectors 25 mph, access edges 35 mph
What changed vs Texas: the graph is stored as numpy edge arrays + a scipy.sparse CSR matrix instead of a networkx Graph, because
a networkx graph at ~10x the Texas node count does not fit in the 3 GB available here. Routing results are identical for the same edges.

Outputs: data/roads/seg_<state>.npz (per-state noded segments), data/roads/graph_us.npz (nodes, edges), data/roads/graph_stats.json
"""
import gc, io, json, sys, time, zipfile
from pathlib import Path
import numpy as np, pandas as pd, requests
import geopandas as gpd, shapely
from scipy.spatial import cKDTree
from scipy import sparse
from scipy.sparse.csgraph import connected_components

ROADS = Path("data/roads"); ROADS.mkdir(parents=True, exist_ok=True)
STATES = [f"{i:02d}" for i in range(1, 57) if f"{i:02d}" not in ("03", "07", "14", "43", "52")]  # 50 states + DC
SPEED = {"S1100": 65.0, "S1200": 50.0, "connector": 25.0, "access": 35.0}
KIND = {"S1100": 0, "S1200": 1, "connector": 2, "access": 3}
M2MI = 1 / 1609.344
TIGER = "https://www2.census.gov/geo/tiger/TIGER2025/PRISECROADS/tl_2025_{st}_prisecroads.zip"


def download(st):
    p = ROADS / f"tl_2025_{st}_prisecroads.zip"
    if p.exists() and p.stat().st_size > 1000: return p
    for attempt in range(3):
        try:
            r = requests.get(TIGER.format(st=st) + (f"?v={attempt+1}" if attempt else ""), timeout=300); r.raise_for_status()  # ?v= busts a stale CDN rejection page
            want = int(r.headers.get("Content-Length") or 0)
            if (want and len(r.content) != want) or not zipfile.is_zipfile(io.BytesIO(r.content)): raise IOError(f"bad download ({len(r.content)} of {want} bytes)")
            p.write_bytes(r.content); return p
        except Exception as e:
            print(f"  download {st} failed ({e}); retry", flush=True); time.sleep(5)
    raise SystemExit(f"could not download roads for state {st}")


def node_state(st):
    """Noded segments for one state -> arrays (x0,y0,x1,y1,len_m,kind). Cached in seg_<st>.npz."""
    out = ROADS / f"seg_{st}.npz"
    if out.exists(): return
    g = gpd.read_file(f"zip://{download(st)}")[["MTFCC", "geometry"]]
    g = g[g.MTFCC.isin(["S1100", "S1200"])].to_crs(5070).explode(index_parts=False, ignore_index=True)
    g["geometry"] = g.geometry.simplify(30, preserve_topology=True)
    noded = shapely.node(shapely.multilinestrings(list(g.geometry)))
    segs = gpd.GeoDataFrame(geometry=list(shapely.get_parts(noded)), crs=5070); del noded
    segs = segs[segs.geometry.length > 0].reset_index(drop=True)
    mids = gpd.GeoDataFrame(geometry=segs.geometry.interpolate(0.5, normalized=True), crs=5070)
    j = gpd.sjoin_nearest(mids, g[["MTFCC", "geometry"]], how="left", max_distance=60); j = j[~j.index.duplicated(keep="first")]
    cls = j.MTFCC.reindex(segs.index).fillna("S1200").map(KIND).values.astype(np.int8)
    coords = shapely.get_coordinates(segs.geometry)  # all vertices in order
    counts = shapely.get_num_coordinates(segs.geometry); ends = np.cumsum(counts); starts = ends - counts
    x0, y0 = coords[starts, 0], coords[starts, 1]; x1, y1 = coords[ends - 1, 0], coords[ends - 1, 1]
    length = segs.geometry.length.values
    np.savez_compressed(out, x0=x0, y0=y0, x1=x1, y1=y1, len_m=length, kind=cls, n_tiger=len(g))
    print(f"  state {st}: {len(g)} TIGER lines -> {len(segs)} noded segments", flush=True)
    del g, segs, mids, j, coords; gc.collect()


def assemble():
    xs, ys, xe, ye, L, K, ntig = [], [], [], [], [], [], 0
    for st in STATES:
        z = np.load(ROADS / f"seg_{st}.npz")
        xs.append(z["x0"]); ys.append(z["y0"]); xe.append(z["x1"]); ye.append(z["y1"]); L.append(z["len_m"]); K.append(z["kind"]); ntig += int(z["n_tiger"])
    x0, y0, x1, y1 = (np.concatenate(a) for a in (xs, ys, xe, ye)); L = np.concatenate(L); K = np.concatenate(K); del xs, ys, xe, ye
    # node keys on a 1 m grid (same as the Texas build's round(x), round(y))
    kx = np.concatenate([np.round(x0), np.round(x1)]).astype(np.int64); ky = np.concatenate([np.round(y0), np.round(y1)]).astype(np.int64)
    key = kx * 10_000_000 + ky  # y span in EPSG:5070 is < 1e7 m
    uniq, inv = np.unique(key, return_inverse=True)
    n_seg = len(L); u, v = inv[:n_seg], inv[n_seg:]
    nodes = np.stack([(uniq // 10_000_000).astype(np.float64), (uniq % 10_000_000).astype(np.float64)], axis=1)
    mi = L * M2MI
    e = pd.DataFrame({"u": np.minimum(u, v), "v": np.maximum(u, v), "mi": mi, "kind": K})
    e = e[e.u != e.v]
    e = e.sort_values("mi").drop_duplicates(["u", "v"], keep="first").reset_index(drop=True)  # parallel edges: keep shortest
    # connectors: nodes within 500 m that are not already adjacent
    tree = cKDTree(nodes); pairs = tree.query_pairs(r=500.0, output_type="ndarray")
    pu, pv = np.minimum(pairs[:, 0], pairs[:, 1]), np.maximum(pairs[:, 0], pairs[:, 1])
    have = set(zip(e.u.values.tolist(), e.v.values.tolist()))
    keep = np.fromiter((not ((a, b) in have) for a, b in zip(pu.tolist(), pv.tolist())), dtype=bool, count=len(pu))
    pu, pv = pu[keep], pv[keep]
    cmi = np.hypot(nodes[pu, 0] - nodes[pv, 0], nodes[pu, 1] - nodes[pv, 1]) * M2MI
    conn = pd.DataFrame({"u": pu, "v": pv, "mi": cmi, "kind": np.full(len(pu), KIND["connector"], np.int8)})
    e = pd.concat([e, conn], ignore_index=True); del have, pairs, conn
    speed = np.array([SPEED["S1100"], SPEED["S1200"], SPEED["connector"], SPEED["access"]])
    e["hr"] = e.mi.values / speed[e.kind.values]
    n = len(nodes)
    A = sparse.coo_matrix((e.mi.values, (e.u.values, e.v.values)), shape=(n, n)).tocsr()
    ncomp, lab = connected_components(A, directed=False)
    sizes = np.bincount(lab); big = sizes.argmax()
    stats = {"states": len(STATES), "edges_from_tiger": int(ntig), "noded_segments": int(n_seg), "nodes": int(n), "edges": int(len(e)),
             "connector_edges": int((e.kind == KIND["connector"]).sum()), "components": int(ncomp),
             "largest_component_share": round(float(sizes[big]) / n, 4), "components_over_1000_nodes": int((sizes > 1000).sum()),
             "speeds_mph": SPEED, "connector_radius_m": 500, "node_grid_m": 1, "simplify_m": 30, "source": "TIGER2025 PRISECROADS S1100+S1200"}
    np.savez_compressed(ROADS / "graph_us.npz", nodes=nodes, u=e.u.values.astype(np.int32), v=e.v.values.astype(np.int32),
                        mi=e.mi.values.astype(np.float32), hr=e.hr.values.astype(np.float32), kind=e.kind.values.astype(np.int8), comp=lab.astype(np.int32))
    json.dump(stats, open(ROADS / "graph_stats.json", "w"), indent=2); print(json.dumps(stats, indent=1), flush=True)


def load_graph():
    z = np.load(ROADS / "graph_us.npz"); n = len(z["nodes"])
    u, v = z["u"], z["v"]
    A_mi = sparse.coo_matrix((np.concatenate([z["mi"], z["mi"]]).astype(np.float64), (np.concatenate([u, v]), np.concatenate([v, u]))), shape=(n, n)).tocsr()
    A_hr = sparse.coo_matrix((np.concatenate([z["hr"], z["hr"]]).astype(np.float64), (np.concatenate([u, v]), np.concatenate([v, u]))), shape=(n, n)).tocsr()
    return z["nodes"], A_mi, A_hr, z["comp"]


if __name__ == "__main__":
    t0 = time.time()
    for st in STATES:
        node_state(st); print(f"    [{st} done, {time.time()-t0:.0f}s]", flush=True)
    assemble(); print(f"graph built in {time.time()-t0:.0f}s", flush=True)
