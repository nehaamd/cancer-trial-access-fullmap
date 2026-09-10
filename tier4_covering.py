"""Tier 4 — "Of these existing facilities, which would close the largest coverage gap?" (maximal covering location problem).

Usage: python tier4_covering.py [--candidates data/ref/candidates_registry.csv] [--label "registry stand-in"]

METHODOLOGY (this text is reproduced verbatim in the output and the web page):
  Candidate universe. Existing facilities capable of hosting a trial, from the supplied candidates file (intended: Commission on
  Cancer-accredited programs plus NCORP affiliates; the stand-in used when those were unreachable is every US facility that hosted an
  interventional oncology treatment trial started 2016 or later on ClinicalTrials.gov). Candidates are excluded if (a) their county
  already hosts a limited menu (20 or more eligible recruiting trials) or (b) the facility itself already hosts an eligible recruiting
  trial today. Candidates are located by ZIP-code centroid (city centroid as fallback) and joined to the highway network like every
  other point in this project.
  Objective (primary). Residents aged 55+ who today have no eligible recruiting cancer treatment trial within 60 road-miles of their
  census tract's population center, and who would have one if a trial opened at the candidate (i.e. the candidate is within 60
  road-miles of their tract). Secondary view: the same, for residents who today have fewer than 20 such trials within 60 road-miles.
  Output. Every candidate ranked by the population 55+ it would newly cover (primary objective), and a greedy sequence: the best
  candidate is chosen, the residents it covers are removed, and the next best is chosen, for up to 25 steps, with the cumulative
  coverage curve. Marginal population is measured on the same road graph and tract data as the rest of the map.
  This is not a recommendation to build anything. It identifies which existing, trial-capable facilities sit nearest to the largest
  currently uncovered older populations.
"""
import argparse, json, re, time
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from scipy import sparse
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import dijkstra, connected_components

REF, OUT, ROADS, DOCS = Path("data/ref"), Path("out_adult55"), Path("data/roads"), Path("docs")
M2MI = 1 / 1609.344; SPEED_ACCESS = 35.0; MAX_ACCESS_MI = 30.0; BAND = 60.0; GREEDY_STEPS = 25
METHOD = re.sub(r"\s+", " ", __doc__.split("METHODOLOGY")[1].split("\n", 1)[1]).strip()
for _h in ("Objective (primary).", "Output.", "This is not a recommendation"): METHOD = METHOD.replace(" " + _h, "\n\n" + _h)
SITECODE = re.compile(r"\(?\s*(site|study site|local institution|investigative site|clinical site|id|site id|site number|site #)\s*[-#:]?\s*\d+[a-z]?\s*\)?|\(\s*\d{3,6}\s*\)|/\s*id#?\s*\d+|\bsite\s+\d{2,6}\b", re.I)
def norm(x):
    y = SITECODE.sub(" ", str(x)); y = re.sub(r"[^a-z0-9 ]", " ", y.lower()); return re.sub(r"\s+", " ", y).strip()
def to5070(lon, lat):
    p = gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs=4326).to_crs(5070); return np.column_stack([p.x.values, p.y.values])


def prepare_graph():
    """Same graph preparation as route_us.py: attachable components (mainland + AK/HI >=100 nodes), fragments >=50 nodes bridged within 5 km."""
    z = np.load(ROADS / "graph_us.npz"); nodes = z["nodes"]; n = len(nodes); comp = z["comp"]
    eu, ev, emi = z["u"].astype(np.int64), z["v"].astype(np.int64), z["mi"].astype(np.float64)
    sizes = np.bincount(comp); main = int(sizes.argmax())
    lonlat = gpd.GeoSeries(gpd.points_from_xy(nodes[:, 0], nodes[:, 1]), crs=5070).to_crs(4326)
    cx = pd.DataFrame({"comp": comp, "lon": lonlat.x.values, "lat": lonlat.y.values}).groupby("comp").mean(); akhi = (cx.lon < -130) | (cx.lat < 23)
    eligible = np.zeros(len(sizes), bool); eligible[main] = True; eligible[(sizes >= 100) & akhi.reindex(range(len(sizes))).fillna(False).values] = True
    etree = cKDTree(nodes[eligible[comp]]); eidx = np.where(eligible[comp])[0]; bu, bv, bmi = [], [], []
    for c in np.where((~eligible) & (sizes >= 50))[0]:
        members = np.where(comp == c)[0]; d, i = etree.query(nodes[members]); k = int(d.argmin())
        if d[k] <= 5000: bu.append(int(members[k])); bv.append(int(eidx[i[k]])); bmi.append(float(d[k]) * M2MI); eligible[c] = True
    eu = np.concatenate([eu, np.array(bu, np.int64)]); ev = np.concatenate([ev, np.array(bv, np.int64)]); emi = np.concatenate([emi, np.array(bmi)])
    A = sparse.coo_matrix((np.concatenate([emi, emi]), (np.concatenate([eu, ev]), np.concatenate([ev, eu]))), shape=(n, n)).tocsr()
    attach_ok = eligible[comp]; tree = cKDTree(nodes[attach_ok]); aidx = np.where(attach_ok)[0]
    return nodes, A, tree, aidx


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--candidates", default="data/ref/candidates_registry.csv"); ap.add_argument("--label", default="registry stand-in (facilities that hosted an oncology treatment trial started 2016+)")
    a = ap.parse_args(); t0 = time.time(); log = {"candidates_file": a.candidates, "universe_label": a.label, "method": METHOD}
    nodes, A, tree, aidx = prepare_graph(); print(f"graph ready {time.time()-t0:.0f}s", flush=True)
    tr = pd.read_csv(OUT / "tract_access.csv", dtype={"tract": str, "county_fips": str})
    txy = to5070(tr.lon.values, tr.lat.values); td, ti = tree.query(txy); ti = aidx[ti]; t_acc = td * M2MI; t_acc[t_acc > MAX_ACCESS_MI] = np.inf
    pop = tr.pop55.values.astype(np.int64); zero = (tr.trials_within_60rdmi.values == 0); lt20 = (tr.trials_within_60rdmi.values < 20)
    log["uncovered_pop55"] = {"zero_trials_within_60rdmi": int(pop[zero].sum()), "lt20_trials_within_60rdmi": int(pop[lt20].sum())}
    # ---- candidates ----
    cand = pd.read_csv(a.candidates, dtype={"county_fips": str, "zip": str}).fillna(""); cand["fac"] = cand.name.map(norm); log["candidates_read"] = len(cand)
    cm = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str}).set_index("county_fips")
    sites = pd.read_csv(OUT / "site_assignment_qc.csv", dtype=str).fillna(""); sites = sites[sites.county_fips != ""]; sites["fac"] = sites.facility.map(norm)
    hosting = sites.groupby(["county_fips", "fac"]).nct_id.nunique()
    cand["county_trials"] = cand.county_fips.map(cm.trials_in_county).fillna(0).astype(int)
    cand["eligible_trials_at_facility"] = [int(hosting.get((r.county_fips, r.fac), 0)) for r in cand.itertuples()]
    excl_a = cand.county_trials >= 20; excl_b = cand.eligible_trials_at_facility > 0
    log["excluded_county_has_limited_menu"] = int(excl_a.sum()); log["excluded_facility_already_recruiting"] = int((~excl_a & excl_b).sum())
    cand = cand[~excl_a & ~excl_b].copy()
    # geocode: ZIP centroid, then city gazetteer
    zc = pd.read_csv(REF / "zcta_pop55.csv", dtype={"zcta": str}).set_index("zcta"); gz = pd.read_csv(REF / "gazetteer_places.csv", dtype={"state": str, "place": str}).drop_duplicates(["state", "place"]).set_index(["state", "place"])
    lat, lon, how = [], [], []
    for r in cand.itertuples():
        if r.zip in zc.index: lat.append(zc.loc[r.zip, "lat"]); lon.append(zc.loc[r.zip, "lon"]); how.append("zip"); continue
        key = (r.state, str(r.city).strip().lower())
        if key in gz.index: lat.append(gz.loc[key, "lat"]); lon.append(gz.loc[key, "lon"]); how.append("city"); continue
        lat.append(np.nan); lon.append(np.nan); how.append("none")
    cand["lat"], cand["lon"], cand["geocode"] = lat, lon, how; log["geocode"] = cand.geocode.value_counts().to_dict(); cand = cand[cand.geocode != "none"].copy()
    cxy = to5070(cand.lon.values, cand.lat.values); cd, ci = tree.query(cxy); ci = aidx[ci]; c_acc = cd * M2MI
    cand = cand[c_acc <= MAX_ACCESS_MI].copy(); ci = ci[c_acc <= MAX_ACCESS_MI]; cxy = cxy[c_acc <= MAX_ACCESS_MI]; c_acc = c_acc[c_acc <= MAX_ACCESS_MI]
    # prefilter: only candidates within 70 straight-line miles of some under-served tract (secondary objective superset)
    ut = cKDTree(txy[lt20]); dmin, _ = ut.query(cxy); keep = dmin * M2MI <= 70
    cand = cand[keep].reset_index(drop=True); ci, c_acc = ci[keep], c_acc[keep]; log["candidates_evaluated"] = len(cand); print(f"candidates to evaluate: {len(cand)}", flush=True)
    # ---- one bounded Dijkstra per candidate ----
    cutoff = BAND + float(np.nanmax(t_acc[np.isfinite(t_acc)])) + float(c_acc.max()) + 0.01
    prim, sec, ntr, cover_zero = np.zeros(len(cand), np.int64), np.zeros(len(cand), np.int64), np.zeros(len(cand), np.int32), []
    B = 10
    for b0 in range(0, len(cand), B):
        idx = np.arange(b0, min(b0 + B, len(cand)))
        D = dijkstra(A, directed=False, indices=ci[idx], min_only=False, limit=cutoff)
        for k, i in enumerate(idx):
            dt = D[k, ti] + t_acc + c_acc[i]; cov = dt <= BAND
            prim[i] = pop[cov & zero].sum(); sec[i] = pop[cov & lt20].sum(); ntr[i] = cov.sum(); cover_zero.append(np.where(cov & zero)[0].astype(np.int32))
        if (b0 // B) % 25 == 0: print(f"  {b0+len(idx)}/{len(cand)} {time.time()-t0:.0f}s", flush=True)
    cand["pop55_newly_covered_zero"] = prim; cand["pop55_newly_covered_lt20"] = sec; cand["tracts_within_60rdmi"] = ntr; cand["access_mi"] = np.round(c_acc, 1)
    cand["state_name"] = cand.county_fips.map(cm.state_name); cand["county_name"] = cand.county_fips.map(cm.county_name)
    PLACEHOLDER = re.compile(r"recruiting site|investigative site|investigational site|research site|clinical site|study site|trial site|^site\b|site \d+$", re.I)
    cand["name_is_placeholder"] = [int(bool(PLACEHOLDER.search(str(n))) or norm(n) == norm(c) or norm(n) == "") for n, c in zip(cand.name, cand.city)]  # sponsor placeholder or bare city name: location real, facility not identified
    ranked = cand.sort_values(["pop55_newly_covered_zero", "pop55_newly_covered_lt20"], ascending=False).reset_index(drop=True); ranked["rank_zero"] = np.arange(1, len(ranked) + 1)
    ranked["rank_lt20"] = ranked.pop55_newly_covered_lt20.rank(ascending=False, method="first").astype(int)
    cols = ["rank_zero", "rank_lt20", "name", "name_is_placeholder", "city", "state", "zip", "county_name", "county_fips", "pop55_newly_covered_zero", "pop55_newly_covered_lt20", "tracts_within_60rdmi", "county_trials", "n_trials_hosted_2016plus", "geocode", "access_mi", "lat", "lon", "source"]
    cols = [c for c in cols if c in ranked.columns]; ranked[cols].to_csv(OUT / "tier4_candidates_ranked.csv", index=False)
    # ---- greedy sequence on the primary objective ----
    remaining = zero.copy(); seq = []; total_zero = int(pop[zero].sum()); cum = 0
    for step in range(GREEDY_STEPS):
        gains = np.array([int(pop[cz[remaining[cz]]].sum()) for cz in cover_zero]) if len(cover_zero) else np.array([])
        if not len(gains) or gains.max() == 0: break
        i = int(gains.argmax()); cz = cover_zero[i]; newly = cz[remaining[cz]]; cum += int(pop[newly].sum()); remaining[newly] = False
        r = cand.iloc[i]; seq.append({"step": step + 1, "name": r["name"], "placeholder": int(r.name_is_placeholder), "city": r.city, "state": r.state, "county": f"{r.county_name}, {r.state_name}", "pop55_newly_covered": int(pop[newly].sum()), "cumulative_pop55_covered": cum,
                                      "pct_of_uncovered_pop55": round(100 * cum / total_zero, 1), "lat": round(float(r.lat), 4), "lon": round(float(r.lon), 4)})
    pd.DataFrame(seq).to_csv(OUT / "tier4_greedy_sequence.csv", index=False)
    log["greedy"] = seq; log["top10_single"] = ranked.head(10)[["name", "city", "state", "county_name", "pop55_newly_covered_zero", "pop55_newly_covered_lt20"]].to_dict("records")
    log["seconds"] = round(time.time() - t0); json.dump(log, open(OUT / "tier4_log.json", "w"), indent=2)
    # web payload (top 200 ranked + greedy + method)
    top = ranked.head(200)[["rank_zero", "name", "name_is_placeholder", "city", "state", "county_name", "pop55_newly_covered_zero", "pop55_newly_covered_lt20", "tracts_within_60rdmi", "county_trials", "lat", "lon"]]
    web = {"label": a.label, "method": METHOD, "generated": time.strftime("%Y-%m-%d"), "uncovered": log["uncovered_pop55"], "counts": {k: log[k] for k in ("candidates_read", "excluded_county_has_limited_menu", "excluded_facility_already_recruiting", "candidates_evaluated")},
           "ranked": [[int(r.rank_zero), r.name, int(r.name_is_placeholder), r.city, r.state, r.county_name, int(r.pop55_newly_covered_zero), int(r.pop55_newly_covered_lt20), int(r.tracts_within_60rdmi), int(r.county_trials), round(float(r.lat), 3), round(float(r.lon), 3)] for r in top.itertuples()], "greedy": seq}
    (DOCS / "tier4.js").write_text("window.TIER4=" + json.dumps(web, separators=(",", ":"), ensure_ascii=False) + ";", encoding="utf-8")
    pd.set_option("display.width", 220); print(pd.DataFrame(seq)[["step", "name", "city", "state", "pop55_newly_covered", "cumulative_pop55_covered", "pct_of_uncovered_pop55"]].to_string(index=False)); print(json.dumps({k: log[k] for k in ("uncovered_pop55", "candidates_read", "excluded_county_has_limited_menu", "excluded_facility_already_recruiting", "geocode", "candidates_evaluated", "seconds")}, indent=1))


if __name__ == "__main__":
    main()
