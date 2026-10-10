"""Automated validation for v3 -> VALIDATION_v3.md. Re-runs the checks that can be re-run and reads the logs of stages already run.
Usage: python validate_v3.py [--no-registry]   (registry re-check needs clinicaltrials.gov)
Exits 1 when a check fails, so run_refresh.sh stops before the release gate; a failure marked known=True (a documented limitation,
e.g. the Tier 4 candidate universe) is reported but does not stop the refresh.
"""
import json, random, re, sys, time
from pathlib import Path
import numpy as np, pandas as pd, requests
import config

REF, OUT, RAW, ROADS = Path("data/ref"), Path("out_adult55"), Path("data/raw"), Path("data/roads")
rows = []; KNOWN = set()   # names of checks whose failure is a documented limitation, not a reason to stop a refresh
def check(name, result, ok, note="", known=False):
    rows.append((name, result, "✓" if ok else "✗", note)); print(("PASS " if ok else "FAIL ") + name + ": " + str(result))
    if known: KNOWN.add(name)


def age_years(s):
    m = re.match(r"([\d.]+)\s*(Year|Month|Week|Day)", s or "", re.I)
    return None if not m else float(m.group(1)) / {"year": 1, "month": 12, "week": 52, "day": 365}[m.group(2).lower()]


def main():
    tlog = json.load(open(REF / "tract_ref_log.json")); mlog = json.load(open(OUT / "tract_metrics_log.json")); rlog = json.load(open(OUT / "route_log.json"))
    flog = json.load(open(RAW / "fetch_log.json")); glog = json.load(open(ROADS / "graph_stats.json")); blog = json.load(open(REF / "cancer_burden_log.json")); qlog = json.load(open("out/qc_log.json")); cts = json.load(open(OUT / "cancer_type_summary.json"))
    tr = pd.read_csv(OUT / "tract_access.csv", dtype={"tract": str, "county_fips": str}); cm = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str}); rd = pd.read_csv(OUT / "county_road_distances.csv", dtype={"county_fips": str})
    dm = pd.read_csv(OUT / "district_metrics_v3.csv", dtype={"cd_geoid": str}).set_index("cd_geoid", drop=False); cp = pd.read_csv(REF / "county_pop55.csv", dtype={"county_fips": str}); sm = pd.read_csv(OUT / "state_metrics_v3.csv", dtype={"state_fips": str}).set_index("state_fips", drop=False)
    # 1 population reconciliation
    cs = tr.groupby("county_fips").pop55.sum().reindex(cp.county_fips).fillna(0).values; mism = int((cs != cp.pop55.values).sum())
    check("Tract pop 55+ sums equal county ACS totals (3,143 counties)", f"{mism} mismatches; tract total {int(tr.pop55.sum()):,} = county total {int(cp.pop55.sum()):,}", mism == 0 and int(tr.pop55.sum()) == int(cp.pop55.sum()),
          f"Exact after raking Suffolk NY (×{tlog['raking_factors'].get('36103')}) and Ulster NY (×{tlog['raking_factors'].get('36111')}): ACS 2023 publishes 371 of Suffolk's 385 2020-geography tracts; the absent tracts' 18,235 residents are in no tract row. Connecticut counties are ACS-2023 tract sums on legacy counties (replaces 2021 PEP).")
    ss = tr.assign(s=tr.county_fips.str[:2]).groupby("s").pop55.sum(); sp = cp.assign(s=cp.county_fips.str[:2]).groupby("s").pop55.sum()
    check("State tract sums equal state county sums (51)", f"{int((ss != sp).sum())} mismatches", int((ss != sp).sum()) == 0)
    check("District pop 55+ total vs tract total", f"{int(dm.pop55.sum()):,} vs {int(tr.pop55.sum()):,} (difference {int(dm.pop55.sum()) - int(tr.pop55.sum()):+d})", abs(int(dm.pop55.sum()) - int(tr.pop55.sum())) <= 5, "per-district integer rounding; 3 zero-population water tracts have no district row")
    # 2 shares
    rel = pd.read_csv(REF / "tract_cd119.csv", dtype={"tract": str}); sh = rel.groupby("tract").share.sum(); bad = int(((sh - 1).abs() > 1e-6).sum())
    check("Every tract's district shares sum to 1.000", f"{bad} of {len(sh):,} tracts off", bad == 0)
    ccd = pd.read_csv(REF / "county_cd.csv", dtype=str); ccd["share"] = ccd.share.astype(float); s2 = ccd.groupby("county_fips").share.sum(); bad2 = int(((s2 - 1).abs() > 1e-3).sum())
    check("Every county's district shares sum to 1.000 (legacy area shares, kept for v2 comparison)", f"{bad2} of {len(s2):,} off by >0.001", bad2 == 0)
    # 3 invariants
    inv = mlog["invariants"]
    check("Menu counties at zero road distance to their own menu (tracts)", f"{inv['tract_in_menu_county_nonzero_violations']} violations", inv["tract_in_menu_county_nonzero_violations"] == 0)
    v = int(((rd.trials_in_county >= 100) & (rd.road_mi_broad != 0)).sum() + ((rd.trials_in_county >= 20) & (rd.road_mi_limited != 0)).sum())
    check("Menu counties at zero road distance to their own menu (counties)", f"{v} violations", v == 0)
    v = int((rd.road_mi_broad < rd.road_mi_limited - 1e-6).sum()); check("Road distance to broad menu ≥ to limited menu (counties)", f"{v} violations", v == 0)
    check("Road distance to broad menu ≥ to limited menu (tracts)", f"{inv['tract_broad_ge_limited_violations']} violations", inv["tract_broad_ge_limited_violations"] == 0)
    check("Trial pools monotone in distance band 30 ≤ 60 ≤ 120 road-mi (tracts)", f"{inv['tract_pool_monotone_violations']} violations", inv["tract_pool_monotone_violations"] == 0)
    check("Own-county trials ≤ 60-mile pool (tracts) — retired", f"{inv['tracts_where_own_county_trials_exceed_60mi_pool']:,} tracts where own-county trials exceed the 60-mile pool", True, "no longer an invariant: with facility-level routing a large county's trials can legitimately be >60 road-miles from some of its own tracts (this was the review's point R1)")
    check("District % beyond 120 ≤ % beyond 60 road-mi of a broad menu", f"{inv['district_pct120_le_pct60_violations']} violations in {len(dm)} districts", inv["district_pct120_le_pct60_violations"] == 0)
    v = int((dm.pct_gt120rdmi_nci > dm.pct_gt60rdmi_nci + 1e-9).sum()); check("District % beyond 120 ≤ % beyond 60 road-mi of an NCI center", f"{v} violations", v == 0)
    v = int(((dm.pct_zero_trials_within_60rdmi > dm.pct_lt20_trials_within_60rdmi + 1e-9) | (dm.pct_lt20_trials_within_60rdmi > dm.pct_lt100_trials_within_60rdmi + 1e-9)).sum())
    check("District % with 0 ≤ % with <20 ≤ % with <100 trials within 60 road-mi", f"{v} violations", v == 0)
    # 4 connectivity
    check("Road-graph nodes in the largest connected component (target ≥ 95%)", f"{100*glog['largest_component_share']:.1f}% of {glog['nodes']:,} nodes; {rlog['fragments_bridged']['n']} fragments bridged, attachable share {100*rlog['attachable_nodes_share']:.1f}%", glog["largest_component_share"] >= 0.95)
    nr = rlog["counties_no_road_route"]; ak = sum(1 for x in nr["list"] if "(02)" in x); hi = sum(1 for x in nr["list"] if "(15)" in x)
    check("Counties with no road route to any broad menu explained", f"{nr['n']} counties: {ak} Alaska boroughs, {hi} Hawaii counties, {nr['n']-ak-hi} elsewhere", nr["n"] - ak - hi == 0, "Alaska and the Hawaiian islands have no road connection to any broad-menu county; Honolulu routes to its own NCI center. Labelled 'no road connection' in the UI, never scored as a distance.")
    off = rlog["tracts_off_road_network_gt30mi"]; check("Tracts >30 straight-line miles from any primary/secondary road", f"{off['n']} tracts, {off['pop55']:,} residents 55+ ({off['of_which_alaska']} in Alaska)", True, "treated as no road distance, counted in pct_no_road_route")
    # 5 router
    rv = rlog["router_validation"]; val = pd.read_csv(OUT / "road_validation.csv")
    check("Router vs published city-pair driving distances (target mean < 5%)", f"{rv['pairs']} pairs, mean |error| {rv['mean_abs_pct_diff']}%, max {rv['max_abs_pct_diff']}% ({val.loc[val.pct_diff.abs().idxmax(), 'from']}–{val.loc[val.pct_diff.abs().idxmax(), 'to']})", rv["mean_abs_pct_diff"] < 5,
          "routes run between county population centers, published values are city center to city center; the tails (Miami–Tampa, DC–Pittsburgh, Atlanta–Jacksonville) are pairs where the centroid sits well outside downtown")
    lc = rlog.get("local_checks")
    if lc:
        loc = pd.read_csv(OUT / "road_local_checks.csv"); worst = loc[loc.kind == "land"].assign(r=lambda d: d.network_mi / d.approx_driving_mi).sort_values("r").iloc[-1]
        check("Router on local trips and water crossings (road_local_checks.csv)", f"{lc['routes'] - lc['failed']}/{lc['routes']} within tolerance: {lc['land']} short or regional trips (at most 2x the driving distance + 5 mi; longest relative to the drive: {worst.route}, {worst.network_mi} vs about {worst.approx_driving_mi} mi) and {lc['water']} water crossings (at least 0.6x the drive around, i.e. no invented crossing)",
              lc["failed"] == 0, "added October 2026: the first national graph routed several in-town trips 60-300 miles (Tucson, Kalispell, Spokane, Pueblo, Duluth); the city-pair check above could not see it. Driving distances are approximate map values, used only as a coarse screen")
    if (OUT / "route_sites_log.json").exists():
        sc = json.load(open(OUT / "route_sites_log.json")).get("screen_site_near_in_straight_line_far_by_road")
        if sc: check("Residents 55+ with a recruiting site within 20 straight-line miles but none within 60 road-miles (contiguous states)", f"{sc['pop55']:,} residents in {sc['tracts']:,} tracts ({sc['pct_of_pop55']}% of residents 55+); largest: " + "; ".join(f"{c['county']} {c['pop55']:,}" for c in sc["largest_counties"][:6]),
                     sc["pop55"] <= 100_000, "what remains should be places cut off by water with no bridge (islands, peninsulas, lake shores); ferries are not modelled. About 194,000 before the October 2026 graph repair")
    # 6 registry spot-check
    if "--no-registry" not in sys.argv:
        t = pd.read_csv(RAW / "trials.csv", dtype=str, keep_default_na=False); t = t[pd.to_numeric(t.max_age_years, errors="coerce").fillna(999) >= 55]
        sites = pd.read_csv(RAW / "us_sites.csv", dtype=str).fillna("")
        random.seed(20260909); samp = t.sample(25, random_state=20260909)
        res = []; s = requests.Session()
        for r in samp.itertuples():
            j = s.get(f"https://clinicaltrials.gov/api/v2/studies/{r.nct_id}", params={"fields": "NCTId,OverallStatus,DesignPrimaryPurpose,Phase,MaximumAge,LocationCountry,LocationState,LocationStatus"}, timeout=60).json()["protocolSection"]
            live_sites = [l for l in j.get("contactsLocationsModule", {}).get("locations", []) if (l.get("country") in ("United States", None)) and (l.get("status") in ("RECRUITING", None, ""))]
            live_us = sum(1 for l in live_sites if l.get("state"))
            live = {"status": j["statusModule"]["overallStatus"], "purpose": j["designModule"].get("designInfo", {}).get("primaryPurpose"), "phase": ";".join(j["designModule"].get("phases", [])),
                    "max_age": age_years(j.get("eligibilityModule", {}).get("maximumAge")), "n_us_sites": live_us}
            stored = {"status": r.overall_status, "purpose": r.primary_purpose, "phase": r.phases, "max_age": age_years(r.maximum_age), "n_us_sites": int(r.n_us_sites)}
            eq = lambda a, b: (a in (None, "") or (isinstance(a, float) and np.isnan(a))) and (b in (None, "") or (isinstance(b, float) and np.isnan(b))) or a == b
            match = all(eq(live[k], stored[k]) for k in ("status", "purpose", "phase", "n_us_sites")) and (eq(live["max_age"], stored["max_age"]) or (live["max_age"] is not None and stored["max_age"] is not None and abs(live["max_age"] - stored["max_age"]) < 0.01))
            res.append({"nct_id": r.nct_id, **{f"stored_{k}": v for k, v in stored.items()}, **{f"live_{k}": v for k, v in live.items()}, "match": match}); time.sleep(0.4)
        rdf = pd.DataFrame(res); rdf.to_csv(OUT / "qc_spotcheck_25_trials_v3.csv", index=False); n_ok = int(rdf.match.sum())
        mism = rdf[~rdf.match]; note = "; ".join(f"{r.nct_id}: " + ", ".join(f"{k} {getattr(r, 'stored_'+k)}→{getattr(r, 'live_'+k)}" for k in ("status", "purpose", "phase", "max_age", "n_us_sites") if getattr(r, 'stored_'+k) != getattr(r, 'live_'+k)) for r in mism.itertuples())
        check("Registry re-check: 25 random trials re-fetched individually (status, purpose, phase, max age, US recruiting-site count)", f"{n_ok}/25 match", n_ok >= 24, note or f"re-fetched {time.strftime('%Y-%m-%d')}, pull was {json.load(open(RAW/'fetch_log.json'))['timestamp_utc'][:10]}")
    # 7 cancer-type classification
    hc = pd.read_csv(OUT / "qc_cancer_type_selfcheck_50.csv") if (OUT / "qc_cancer_type_selfcheck_50.csv").exists() else None
    if hc is not None:
        agree = int((hc.agree == 1).sum()); check("Cancer-type classifier: same-session self-consistency read of 50 sampled trials (NOT independent validation)", f"{agree}/{len(hc)} agree", agree / len(hc) >= 0.9, "The builder re-read titles/conditions; this checks the rules were applied as intended, not that the rules are right. The 200-trial file qc_cancer_type_sample_200.csv is left for a blind hand check.")
    check("Cancer-type classifier: multi-cancer bucket and unclassified share reported", f"{cts['pct_multi_55plus']}% multi/basket ({cts['multi_subtypes_55plus']}); {cts['pct_unclassified_55plus']}% unclassified", True)
    # 8 burden
    a = blog["sites"]["all"]; check("Cancer burden: county counts vs state-published counts (all sites, 50 states)", f"median |diff| {a['state_reconciliation']['median_abs_pct_diff']}%, max {a['state_reconciliation']['max_abs_pct_diff']}% (state {a['state_reconciliation']['worst']})", a["state_reconciliation"]["max_abs_pct_diff"] < 2,
          "Alaska's max reflects the 2019 Chugach/Copper River split not in the registry file")
    check("Cancer burden: county sum vs source's own US line (all sites)", f"{a['county_sum_published']:,.0f} of {a['us_avg_annual_count']:,.0f} avg annual cases ({100*a['county_sum_published']/a['us_avg_annual_count']:.1f}%)", a["county_sum_published"] / a["us_avg_annual_count"] > 0.98, "shortfall = Kansas (no county release) + 9 suppressed counties. External headline: CDC USCS reports about 1.8 M new cases per year (2021: ~1.78 M) — consistent in magnitude; cdc.gov was not reachable to fetch the exact figure")
    check("Cancer burden: 'not available for this state' vs small-number flag kept distinct", f"KS = not_available_state ({a['status_counts'].get('not_available_state')} counties); small numbers {a['status_counts'].get('small_numbers')}; source-suppressed {a['status_counts'].get('suppressed_source')}; absent from source {a['status_counts'].get('not_available_county')}", True, "Indiana IS present in this release (the prompt expected it absent)")
    # 8b deaths vs access (mortality.js from data/ref/cancer_mortality_*.csv; the layer is optional, the checks run when the file exists)
    DOCS = Path("docs"); mpath = DOCS / "mortality.js"
    if mpath.exists() and (REF / "cancer_mortality_log.json").exists():
        mlog = json.load(open(REF / "cancer_mortality_log.json")); ma = mlog["sites"]["all"]; MO = json.loads(mpath.read_text(encoding="utf-8")[len("window.MORTALITY="):].rstrip(";"))
        check("Cancer deaths: county counts vs state-published counts (all sites)", f"median |diff| {ma['state_reconciliation']['median_abs_pct_diff']}%, max {ma['state_reconciliation']['max_abs_pct_diff']}% (state {ma['state_reconciliation']['worst']})", ma["state_reconciliation"]["max_abs_pct_diff"] < 5, "Alaska's max reflects the 2019 Chugach/Copper River split")
        check("Cancer deaths: county sum vs source's own US line (all sites)", f"{ma['county_sum_published']:,.0f} of {ma['us_avg_annual_count']:,.0f} avg annual deaths ({100*ma['county_sum_published']/ma['us_avg_annual_count']:.1f}%)", ma["county_sum_published"] / ma["us_avg_annual_count"] > 0.98)
        BUj = json.loads((DOCS / "burden.js").read_text(encoding="utf-8")[len("window.BURDEN="):].rstrip(";")); t2 = MO["meta"]["tertiles"]["all"][1]
        hh = [f for f, a in MO["county"].items() if a[0][4] <= 1 and a[0][0] is not None and a[0][0] >= t2 and BUj["county"].get(f, {}).get("l20", -1) >= MO["meta"]["threshold_pct"]]
        check("Cancer deaths: every county has a record; the high-mortality & low-access count matches a recount", f"{len(MO['county'])} counties; recount {len(hh)} vs summary {MO['summary']['nat']['hh_counties']}; cut-off {t2} per 100,000 ({MO['meta']['period']})", len(MO["county"]) == len(BUj["county"]) and len(hh) == MO["summary"]["nat"]["hh_counties"])
    # 9 knife-edge thresholds
    k20 = cm[cm.trials_in_county.between(17, 23)]; k100 = cm[cm.trials_in_county.between(97, 103)].sort_values("trials_in_county")
    check("Counties within ±3 trials of a menu threshold (knife-edge audit)", f"limited menu (20): {int((k20.trials_in_county < 20).sum())} counties at 17–19, {int((k20.trials_in_county >= 20).sum())} at 20–23; broad menu (100): " + "; ".join(f"{r.county_name} {r.state_name} {r.trials_in_county}" for r in k100.itertuples()), True,
          "these classifications are the most likely to flip on a re-pull; a state's 'no broad-menu county' claim rests on them (full list: county_metrics.csv)")
    # 10 no-data vs zero audit in the payload
    D = json.loads(open("docs/data.js").read()[len("window.DATA="):-1]); Cc = D["counties"]
    n_null = sum(1 for c in Cc.values() if c["rb"] is None); n_b = sum(1 for c in Cc.values() if c["b"] is None); n_acs = sum(1 for c in Cc.values() if c["acs"] is None)
    check("Payload: 'no road' is null (not 0/999); burden/ACS absent is null (not 0)", f"{n_null} counties with null road distance to a broad menu (expected {nr['n']}; Honolulu keeps its own NCI center), {n_b} with no burden record, {n_acs} with no ACS household record", n_null == nr["n"] and n_b == 0 and n_acs == 0, "Connecticut ACS rows rebuilt from tract tables on legacy counties (fix_ct_covariates.py)" if n_acs == 0 else "")
    for k in ("ok", "no ACS"): pass
    z = sum(1 for c in Cc.values() if c["t"] == 0 and len(c["tr"]) == 0); nz = sum(1 for c in Cc.values() if c["t"] > 0 and c["t"] != len(c["tr"]))
    check("Payload: county trial count equals length of its trial list", f"{nz} mismatches; {z} counties with a true zero", nz == 0)
    D_ = json.loads(open("docs/data.js").read()[len("window.DATA="):-1]); T = D_["T"]
    named = set(T["named_types"]); has_cats = sum(1 for c in T["cats"] if c)
    crc_i = next(i for i, t in enumerate(T["types"]) if t[0] == "colorectal")
    crc_via_multi = sum(1 for j, c in enumerate(T["cats"]) if crc_i in c and T["ct"][j] != crc_i)
    check("Payload: multi-label 'cats' present for every trial with a matched category, basket trials reachable by single-cancer filters", f"{has_cats} of {len(T['id'])} trials carry a category list; {crc_via_multi} trials reach the Colorectal filter via a non-colorectal primary label", has_cats > 0.9 * len(T["id"]) and crc_via_multi > 100)
    rec = sum(1 for c in Cc.values() if c["t"] != int(cm.set_index("county_fips").loc[[k for k, v in Cc.items() if v is c][0], "trials_in_county"]) ) if False else 0
    # 10b facility-level routing (review round 2)
    if (OUT / "route_sites_log.json").exists():
        rs = json.load(open(OUT / "route_sites_log.json")); g = rs["geocode"]
        nz = g.get("zip_centroid", 0); ncity = sum(v for k, v in g.items() if k.startswith("city_centroid")); nlarge = g.get("city_centroid_large_zip", 0)
        check("Facility-level routing: recruiting sites located below county level", f"{nz:,} ZIP-centroid + {ncity:,} city-centroid ({nlarge:,} of them because the ZIP is larger than 100 sq mi) of {rs['site_rows']:,} site rows ({100*(nz+ncity)/rs['site_rows']:.1f}%); {g.get('county_centroid_city_disagrees',0)+g.get('county_centroid',0)} fell back to the county center; {rs['site_points']:,} distinct locations", (nz+ncity)/rs['site_rows'] > 0.95, "city fallback rejected when >40 mi from the assigned county's center (e.g. a registry row with city Dallas but a Cass County ZIP)")
        check("Facility-level routing: residents whose own county's trials are >60 road-miles away are no longer scored at 0 mi", f"{inv['tracts_where_own_county_trials_exceed_60mi_pool']:,} tracts, {inv['pop55_in_those_tracts']:,} residents 55+", True, "this population was previously counted as having every trial in its county at zero distance")
    ui = open("docs/index.html").read()
    check("UI text matches validation evidence: router accuracy is qualified in the deployed page (guard against claiming a fix that was not made)", "phrase 'not yet against an independent routing engine' present in index.html" if "independent routing engine" in ui else "MISSING", "independent routing engine" in ui and "approximate" in ui)
    # 10c live-filter data file: the browser's tract-level recount must reproduce the pipeline exactly when every trial passes
    if Path("docs/tracts60.bin").exists():
        import struct
        buf = open("docs/tracts60.bin", "rb").read(); magic, n, ns, npairs, nst = struct.unpack("<IIIII", buf[:20]); o = 20
        pop = np.frombuffer(buf, "<u4", n, o); o += n * 4; st_ = np.frombuffer(buf, "u1", n, o); o += n + ((4 - n % 4) % 4); di = np.frombuffer(buf, "<u2", n, o); o += n * 2 + ((4 - (n * 2) % 4) % 4)
        split = [struct.unpack("<IHH", buf[o + 8 * i:o + 8 * i + 8]) for i in range(ns)]; o += 8 * ns; off = np.frombuffer(buf, "<u4", n + 1, o); o += (n + 1) * 4; ids = np.frombuffer(buf, "<u2", npairs, o)
        Dj = json.loads(open("docs/data.js").read()[len("window.DATA="):-1]); SP = Dj["SP"]; order = Dj["meta"]["state_order"]; dkeys = Dj["district_keys"]
        cnt = np.array([len(set().union(*[SP[x] for x in ids[off[i]:off[i + 1]]])) if off[i + 1] > off[i] else 0 for i in range(n)])
        def agg_(mask_w):
            idx, w = mask_w; W = w.sum(); return (round(100 * w[cnt[idx] < 20].sum() / W, 1), round(100 * w[cnt[idx] == 0].sum() / W, 1), round((w * cnt[idx]).sum() / W))
        tx = order.index("48"); m = np.where(st_ == tx)[0]; got = agg_((m, pop[m].astype(float)))
        want = (float(sm.loc["48", "pct_lt20_trials_within_60rdmi"]), float(sm.loc["48", "pct_zero_trials_within_60rdmi"]), int(sm.loc["48", "wmean_trials_within_60rdmi"]))
        k = dkeys.index("4816"); m = np.where(di == k)[0]; ws = [(t, sh / 10000) for t, d, sh in split if d == k]; idx = np.concatenate([m, np.array([t for t, _ in ws], int)]); w = np.concatenate([pop[m].astype(float), np.array([pop[t] * sh for t, sh in ws])])
        got_d = agg_((idx, w)); want_d = (float(dm.loc["4816", "pct_lt20_trials_within_60rdmi"]), float(dm.loc["4816", "pct_zero_trials_within_60rdmi"]), int(dm.loc["4816", "wmean_trials_within_60rdmi"]))
        check("Live-filter tract file reproduces pipeline figures with no filter (Texas; TX-16)", f"TX: browser method {got} vs pipeline {want}; TX-16: {got_d} vs {want_d}", got == want and got_d == want_d, "same tract pools, same weights; guarantees filtered and unfiltered figures are comparable")
    # 10d payload integrity for the trial / site tables and the refresh diff
    Dj2 = json.loads(open("docs/data.js").read()[len("window.DATA="):-1]); T2 = Dj2["T"]; N2 = len(T2["id"]); bad_idx = 0; nbd_unsorted = 0; sp_bad = 0
    for k_, c_ in Dj2["counties"].items():
        for fa_ in c_["fac"]:
            if any(j >= N2 for j in fa_[3]): bad_idx += 1
        if any(c_["nbd"][i][1] > c_["nbd"][i + 1][1] for i in range(len(c_["nbd"]) - 1)): nbd_unsorted += 1
    for sp_ in Dj2["SPI"]:
        for cf_, i_ in sp_:
            if i_ >= len(Dj2["counties"][cf_]["fac"]): sp_bad += 1
    # every trial at every location carries the ZIP of its own registry row (SPX), and the per-location lists add up to the facility's list
    if "SPX" in Dj2:
        SPX_ = Dj2["SPX"]; shape_ok = len(SPX_) == len(Dj2["SPI"]) and all(len(a) == len(b) for a, b in zip(SPX_, Dj2["SPI"])); union = {}; outside = 0
        for s_i, (ents, refs) in enumerate(zip(SPX_, Dj2["SPI"])):
            here = set(Dj2["SP"][s_i])
            for ent_, (cf_, i_) in zip(ents, refs): tr_ = ent_[1]; union.setdefault((cf_, i_), set()).update(tr_); outside += len(set(tr_) - here)
        mism = sum(1 for (cf_, i_), u_ in union.items() if u_ != set(Dj2["counties"][cf_]["fac"][i_][3]))
        sgq = pd.read_csv(OUT / "site_geocode_qc.csv", dtype=str).fillna(""); sgq = sgq[sgq.geocode.isin(["zip_centroid", "city_centroid_large_zip", "city_centroid_zip_spans_counties"])]
        shown = {(s_i, T2["id"][j_]): e_[0] for s_i, ents in enumerate(SPX_) for e_ in ents for j_ in e_[1] if e_[0]}   # one facility is enough: all rows at a ZIP-located point share the ZIP unless two large ZIPs share a city
        samp = sgq.sample(min(4000, len(sgq)), random_state=11); wrong = sum(1 for r_ in samp.itertuples() if (int(r_.sp), r_.nct_id) in shown and r_.zip5 not in {e_[0] for e_ in SPX_[int(r_.sp)] if T2["id"].index(r_.nct_id) in e_[1]}) if len(samp) else 0
        check("Payload: each trial is listed at a location with the ZIP of its own registry row", f"{len(samp):,} registry rows sampled, {wrong} shown under a different ZIP; {mism} facilities whose per-location trial lists do not add up to their list; {outside} trial entries outside their location's pool", shape_ok and wrong == 0 and mism == 0 and outside == 0,
              "a facility is a name in a county and one name is often listed at several ZIP codes; before October 2026 the pages printed the facility's most common ZIP for every trial (4.8% of trial-location rows)")
        # the city printed with each location is one the registry itself gives for a trial at that location (third item of an SPX entry)
        if any(len(e_) > 2 for ents in SPX_ for e_ in ents):
            allq = pd.read_csv(OUT / "site_geocode_qc.csv", dtype=str).fillna(""); jx = {n_: j_ for j_, n_ in enumerate(T2["id"])}
            said = {}
            for r_ in allq.itertuples(): said.setdefault((int(r_.sp), jx.get(r_.nct_id)), set()).add(r_.city.strip())
            ents_n = 0; city_bad = 0
            for s_i, ents in enumerate(SPX_):
                for e_ in ents:
                    ents_n += 1
                    if not all(e_[2] in said.get((s_i, j_), ()) for j_ in e_[1]): city_bad += 1
            check("Payload: each trial is listed at a location with the city of its own registry row", f"{ents_n:,} facility-location entries, {city_bad} naming a city that is not the registry's for one of their trials", city_bad == 0,
                  "before October 2026 the pages printed a facility's most common city next to each row's own ZIP (2.7% of first lines in the ZIP finder named a different town)")
    # registry rows that are not places (telemedicine services) and rows whose ZIP is a typing error
    sa_ = pd.read_csv(OUT / "site_assignment_qc.csv", dtype=str).fillna("")
    if "assign_method" in sa_.columns:
        import re as _re
        vrx = _re.compile(config.VIRTUAL_SITE_PATTERN, _re.I); is_v = sa_.facility.map(lambda x: bool(vrx.search(x)))
        located = int((is_v & (sa_.county_fips != "")).sum()); n_v = int(is_v.sum()); tele = Dj2["T"].get("tele", {})
        if not config.VIRTUAL_SITES_ARE_LOCATIONS:
            want = {n_ for n_ in sa_[is_v].nct_id if n_ in set(T2["id"])}
            check("Telemedicine / virtual registry rows are not mapped as sites", f"{n_v} rows in {sa_[is_v].nct_id.nunique()} trials; {located} of them assigned to a county; {len(tele)} trial(s) listed for the ZIP finder's telemedicine section", located == 0 and {T2['id'][int(k_)] for k_ in tele} == want,
                  "a fully decentralized study lists one telemedicine row per city; counted as sites, the rows of one such study (NCT06906562) were the only trial within 60 road-miles for about 346,000 residents 55+")
        ty = sa_[sa_.assign_method == "zip_typo_corrected"]
        if len(ty):
            gq_ = pd.read_csv(OUT / "site_geocode_qc.csv", dtype=str).fillna(""); k_ = set(zip(ty.nct_id, ty.facility, ty.zip.str[:5]))
            at_zip = sum(1 for r_ in gq_.itertuples() if (r_.nct_id, r_.facility, r_.zip5) in k_ and r_.geocode in ("zip_centroid", "city_centroid_large_zip", "city_centroid_zip_spans_counties"))
            check("Registry rows with a mistyped ZIP are located where the registry lists that facility", f"{len(ty)} rows (" + "; ".join(f"{r_.facility[:28]}, {r_.city} {r_.zip[:5]}" for r_ in ty.head(4).itertuples()) + ("; ..." if len(ty) > 4 else "") + f"); {at_zip} still drawn at the ZIP", at_zip == 0,
                  "judged a typing error only when the same named facility is listed repeatedly near the stated city and never near the ZIP (metrics_us.zip_typos)")
    check("Payload: trial/site tables are internally consistent (facility→trial indices, sitepoint→facility index, nearby lists sorted)", f"{bad_idx} bad facility trial indices; {sp_bad} bad sitepoint→facility refs; {nbd_unsorted} unsorted nearby lists; sponsor names {sum(1 for x in T2['spn'] if x):,}/{N2:,}, last-update dates {sum(1 for x in T2['upd'] if x):,}/{N2:,}", bad_idx == 0 and sp_bad == 0 and nbd_unsorted == 0 and sum(1 for x in T2['spn'] if x) == N2)
    if (OUT / "refresh_diff.json").exists():
        rd_ = json.load(open(OUT / "refresh_diff.json"))["summary"]
        check("Refresh diff: previous and current pulls compared", f"{rd_['previous_pull'][:10]} → {rd_['current_pull'][:10]}: {rd_['trials_previous']:,} → {rd_['trials_current']:,} trials; {rd_['trials_new']} new, {rd_['trials_no_longer_listed']} no longer listed, {rd_['sites_new_at_existing_trials']} sites added / {rd_['sites_removed_at_existing_trials']} removed at continuing trials; {rd_.get('counties_with_changed_trial_count', 0)} counties changed count", rd_["trials_current"] > 0, "registry data timestamp " + str(rd_.get("current_registry_data")))
    # 11 Tier 4 prototype
    if (OUT / "tier4_log.json").exists():
        t4 = json.load(open(OUT / "tier4_log.json")); rk = pd.read_csv(OUT / "tier4_candidates_ranked.csv"); gs = pd.read_csv(OUT / "tier4_greedy_sequence.csv")
        v = int((rk.county_trials >= 20).sum()); check("Tier 4: no evaluated candidate sits in a county with a limited menu", f"{v} of {len(rk)} candidates in a county with ≥20 trials", v == 0)
        mono = bool((gs.pop55_newly_covered.diff().dropna() <= 0).all()); check("Tier 4: greedy marginal gains are non-increasing", f"{len(gs)} picks; first {int(gs.pop55_newly_covered.iloc[0]):,}, last {int(gs.pop55_newly_covered.iloc[-1]):,}; {gs.pct_of_uncovered_pop55.iloc[-1]}% of uncovered reached", mono)
        check("Tier 4: candidate universe is the intended one (CoC + NCORP)", f"universe = {t4['universe_label']}", "stand-in" not in t4["universe_label"], "registry-derived stand-in used because www.facs.org / ncorp.cancer.gov were not reachable; results are labelled a research prototype in the UI until the intended universe is substituted", known=True)
        check("Tier 4: plausibility read of top picks", "; ".join(f"{g['city']} {g['state']}" for g in t4["greedy"][:10]), True, "same-session read: all known rural/remote gaps; not independently reviewed")
    # 12 v3.3 additions (rural/urban codes, cosponsors, burden vs access, ZIP lookup) — see validate_extras.py
    if Path("validate_extras.py").exists():
        try:
            from validate_extras import run as extras; rows.extend(extras("--browser" in sys.argv))
        except Exception as e: check("v3.3 extras", f"validate_extras.py failed: {type(e).__name__} {e}", False)
    # write report
    md = ["# Validation — National Cancer Trial Access Map v3", "", f"Registry pull {flog['timestamp_utc'][:10]}" + (f" (registry data of {flog['registry_data_timestamp'][:10]})" if flog.get("registry_data_timestamp") else "") + f"; road graph TIGER 2025 (graph version {glog.get('graph_version', 1)}); ACS 2023 5-year; State Cancer Profiles 2018–2022. Checks re-run by `validate_v3.py` on {time.strftime('%Y-%m-%d')}.", "",
          "| Check | Result | Pass | Context |", "|---|---|---|---|"] + [f"| {n} | {r} | {p} | {c} |" for n, r, p, c in rows]
    text = "\n".join(md) + "\n" + (("\n" + Path("VALIDATION_review.md").read_text()) if Path("VALIDATION_review.md").exists() else "")
    (OUT / "VALIDATION_v3.md").write_text(text); Path("VALIDATION_v3.md").write_text(text)
    failed = [n for n, _, p, _ in rows if p == "✗" and n not in KNOWN]
    print(f"\n{sum(1 for r in rows if r[2]=='✓')}/{len(rows)} checks pass" + (f"; {len(failed)} unexpected failure(s): " + "; ".join(failed) if failed else ""))
    return failed


if __name__ == "__main__":
    # a failing check stops the refresh (run_refresh.sh runs the stages with &&); a documented limitation (known=True) does not
    sys.exit(1 if main() else 0)
