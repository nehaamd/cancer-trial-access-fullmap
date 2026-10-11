"""Release gate: the last step of a refresh. If anything here fails the refresh stops and nothing is published;
GitHub Actions then emails the failure. Writes RELEASE_GATE.md.

Checks
  1. Classification audit has no unreviewed strings (audit_cancer_types.py; see qc_cancer_type_audit.md)
  2. The registry pull is complete (every study the registry counted was fetched) and newer than the previous snapshot; headline numbers
     are within plausible bounds, the population 55+ equals the ACS reference, and nothing jumped from the previous snapshot
     (a jump means the registry pull or a pipeline stage broke, not that access changed in a week)
  2b. The road network still routes short local trips sensibly and has not invented water crossings (route_us.py LOCAL_CHECKS),
      and few residents have a site nearby in a straight line but none by road (route_sites_us.py)
  2c. No site row is drawn at a county center when its stated city lies elsewhere (such rows are left unlocated), and no county's
      only located sites sit at the county center (route_sites_us.py)
  3. The published payload is internally consistent (trial count, county / district / state counts, no NaN in headline fields,
     every district's context block from tract tables, district case counts equal to the apportioned metrics file, and every page's
     data file built from this pull, changes.js included)
    python3 release_gate.py
"""
import gzip, json, os, subprocess, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
def find(name, required=True):
    for d in (ROOT, ROOT / "docs", ROOT / "out_adult55", ROOT / "data" / "raw", ROOT / "data" / "ref"):
        if (d / name).exists(): return d / name
    if required: sys.exit(f"release gate: missing input {name}")
    return None
rows = []
def check(name, detail, ok): rows.append((name, detail, ok)); print(("  PASS  " if ok else "  FAIL  ") + name + " — " + detail)

# 1. classification audit
r = subprocess.run([sys.executable, str(ROOT / "audit_cancer_types.py")], capture_output=True, text=True)
check("Classification audit: no unreviewed condition strings", (r.stdout.strip().splitlines()[0] if r.stdout.strip() else r.stderr.strip()[:200]), r.returncode == 0)

# 2. the registry pull: complete and new. fetch_us.py only warns when it fetched fewer studies than the registry counted; a lost last page
# (543 of 4,543 studies on 11 Oct 2026, about 12%) would pass every bound and drift tolerance below, so it is checked here.
skip_fetch = bool(os.environ.get("REFRESH_SKIP_FETCH"))   # run_refresh.sh re-running the method on the pull already in data/raw/
flog = json.load(open(find("fetch_log.json"))); tot, got = flog.get("api_total_count"), flog.get("studies_fetched")
if tot is not None and got is not None:
    check("Registry pull complete (studies fetched vs the registry's own count)", f"{got:,} of {tot:,} studies; {flog.get('duplicate_study_rows_dropped', 0)} repeated across pages dropped", abs(got - tot) <= max(5, 0.01 * tot))
else: check("Registry pull complete (studies fetched vs the registry's own count)", "fetch_log.json has no count (a pull reused from disk, or made before October 2026)", skip_fetch)

# 2. headline numbers: bounds and drift
nat = json.load(open(find("national_metrics_v3.json"))); D = json.loads(find("data.js").read_text().split("=", 1)[1].strip().rstrip(";")); meta = D["meta"]
check("Trial count plausible (2,000–8,000)", f"{meta['trials']:,} eligible trials", 2000 <= meta["trials"] <= 8000)
ref55 = int(pd.read_csv(find("county_pop55.csv"), dtype={"county_fips": str}).pop55.sum())   # was a 90-110 million band; the population is reference data and must not move
check("Population 55+ equals the ACS reference (data/ref/county_pop55.csv)", f"{nat['pop55']:,} vs {ref55:,}", nat["pop55"] == ref55 and 90e6 <= nat["pop55"] <= 110e6)
for k, lo, hi in (("pct_lt20_trials_within_60rdmi", 5, 30), ("pct_zero_trials_within_60rdmi", 1, 15), ("pct_gt60rdmi_broad_menu", 20, 60), ("pct_gt60rdmi_nci", 25, 65), ("median_road_mi_nci", 25, 90)):
    check(f"{k} within bounds [{lo}, {hi}]", str(nat[k]), lo <= nat[k] <= hi)
snaps = sorted((ROOT / "data" / "snapshots").glob("*/national_metrics_v3.json")) if (ROOT / "data" / "snapshots").exists() else []
if snaps:
    prev = json.load(open(snaps[-1])); plog = json.load(open(snaps[-1].parent / "fetch_log.json")) if (snaps[-1].parent / "fetch_log.json").exists() else {}
    pt = plog.get("timestamp_utc", snaps[-1].parent.name)[:10]
    # a refresh publishes a new pull: the same or an older one means the fetch did not happen (until October 2026 a failed fetch fell through
    # run_refresh.sh and the chain republished the previous pull)
    newer = flog.get("timestamp_utc", "") > plog.get("timestamp_utc", "") and (flog.get("registry_data_timestamp") or "") >= (plog.get("registry_data_timestamp") or "")
    check(f"The pull is newer than the previous snapshot ({pt})", f"pulled {flog.get('timestamp_utc', '?')[:16]} (registry data {(flog.get('registry_data_timestamp') or '?')[:10]}) after {plog.get('timestamp_utc', '?')[:16]} (registry data {(plog.get('registry_data_timestamp') or '?')[:10]})", newer or skip_fetch)
    mv_prev, mv_now = int(prev.get("method_version", 1)), int(nat.get("method_version", 1))
    if mv_prev != mv_now:
        # the previous pull was calculated with an earlier method (config.METHOD_CHANGES): a step between the two is expected and is not drift
        check(f"Drift vs the pull of {pt}", f"skipped once: the method changed (version {mv_prev} -> {mv_now}); the bounds above still apply", True)
    else:
        for k, tol in (("pct_lt20_trials_within_60rdmi", 1.5), ("pct_zero_trials_within_60rdmi", 1.0), ("pct_gt60rdmi_broad_menu", 2.0), ("pct_gt60rdmi_nci", 1.0), ("median_road_mi_nci", 5)):
            check(f"{k} moved less than {tol} since {pt}", f"{prev[k]} -> {nat[k]}", abs(nat[k] - prev[k]) <= tol)
        pcsv = snaps[-1].parent / "trials.csv"   # the trial count's own drift (the 2,000-8,000 band above would pass a pull that lost a third of its trials)
        if pcsv.exists():
            tp = pd.read_csv(pcsv, dtype=str, keep_default_na=False, usecols=lambda c: c in ("nct_id", "excludes_55plus")); n_prev = int((tp.excludes_55plus == "0").sum()) if "excludes_55plus" in tp.columns else len(tp)
            check(f"Eligible trial count moved less than 10% since {pt}", f"{n_prev:,} -> {meta['trials']:,}", abs(meta["trials"] - n_prev) <= 0.10 * n_prev)
    pc = (ROOT / "data" / "snapshots" / snaps[-1].parent.name / "county_metrics.csv")
    if pc.exists():
        a = pd.read_csv(pc, dtype={"county_fips": str}); b = pd.read_csv(find("county_metrics.csv"), dtype={"county_fips": str})
        ta, tb = a.trials_in_county.sum(), b.trials_in_county.sum()
        check("County trial-site total moved less than 15% since the previous pull", f"{ta:,} -> {tb:,}", abs(tb - ta) <= 0.15 * max(ta, 1))
else:
    check("Drift vs previous snapshot", "no previous snapshot yet (first run) — skipped", True)

# 2b. road network: a fault in the graph shows up as short trips routed the long way round, or as water crossed where there is no bridge
rl = json.load(open(find("route_log.json"))); lc = rl.get("local_checks")
if lc: check(f"Local route checks ({lc['land']} short trips, {lc['water']} water crossings; road_local_checks.csv)", f"{lc['routes'] - lc['failed']}/{lc['routes']} within tolerance" + ("; outside: " + "; ".join(lc["failed_routes"]) if lc["failed"] else ""), lc["failed"] == 0)
else: check("Local route checks", "route_log.json has no local_checks (route_us.py not re-run?)", False)
sl = json.load(open(find("route_sites_log.json"))).get("screen_site_near_in_straight_line_far_by_road")
if sl: check("Residents 55+ with a site within 20 straight-line miles but none within 60 road-miles (ceiling 100,000; water barriers explain the rest)", f"{sl['pop55']:,} in {sl['tracts']:,} tracts; largest: " + ", ".join(f"{c['county']} {c['pop55']:,}" for c in sl["largest_counties"][:4]), sl["pop55"] <= 100_000)
else: check("Near-in-a-straight-line, far-by-road screen", "route_sites_log.json has no screen (route_sites_us.py not re-run?)", False)
rv = rl["router_validation"]; check("Router vs published city-pair distances (mean difference below 5%, every pair routable)", f"{rv['pairs']} pairs, mean {rv['mean_abs_pct_diff']}%, max {rv['max_abs_pct_diff']}%, unroutable {rv['unroutable_pairs']}", rv["mean_abs_pct_diff"] < 5 and rv["unroutable_pairs"] == 0)
# 2c. site placement: a row whose city lies far from the county its ZIP gave it is not located at all (route_sites_us.py); a point at the
# county center would be a phantom site that counts as "a trial within 60 road-miles" for residents who have none (Tuscola County MI, Oct 2026)
slog = json.load(open(find("route_sites_log.json"))); gc = slog.get("geocode", {})
if "unlocated_rows" in slog:
    check("No site row drawn at a county center when its stated city lies elsewhere", f"{slog['unlocated_rows']} rows left unlocated and dropped; county-center placements: {gc.get('county_centroid', 0)}", "county_centroid_city_disagrees" not in gc and slog["unlocated_rows"] <= 200)
else: check("No site row drawn at a county center when its stated city lies elsewhere", "route_sites_log.json predates this rule (route_sites_us.py not re-run?)", False)
gq = pd.read_csv(find("site_geocode_qc.csv"), dtype=str).fillna("")
only_cc = gq.groupby("county_fips").geocode.apply(lambda s: (s == "county_centroid").all()); only_cc = only_cc[only_cc].index.tolist()
check("No county whose only located sites sit at the county center (ZIP and city both unknown)", f"{int((gq.geocode == 'county_centroid').sum())} such rows; counties with nothing else: {len(only_cc)}" + (" (" + ", ".join(only_cc[:6]) + ")" if only_cc else ""), not only_cc and (gq.geocode == "county_centroid").sum() <= 100)

# 3. payload consistency
T = D["T"]; check("data.js trial list matches meta.trials", f"{len(T['id']):,} vs {meta['trials']:,}", len(T["id"]) == meta["trials"])
check("436 districts and 51 states in the payload", f"{len(D['districts'])} districts, {len(D['state_data'])} states", len(D["districts"]) == 436 and len(D["state_data"]) == 51)
check("3,143 counties in the payload", f"{len(D['counties']):,}", len(D["counties"]) == 3143)
bad = [k for k, d in D["districts"].items() if any(d[f] is None or d[f] != d[f] for f in ("l20", "z60", "g60b", "g60n"))]
check("No district with a missing headline figure", f"{len(bad)} missing", not bad)
nm = sum(1 for d in D["districts"].values() if not d.get("member")); check("Vacant seats are few (member list loaded)", f"{nm} districts without a member", nm <= 8)
st = pd.read_csv(find("state_metrics_v3.csv")); check("Every state has residents 55+ and a finite access share", f"{len(st)} rows", len(st) == 51 and st.pct_lt20_trials_within_60rdmi.notna().all())
nt = sum(1 for d in D["districts"].values() if (d.get("ctx") or {}).get("ctx_src") == "tract")
check("Every district's household and incidence figures come from tract tables (build_tract_context.py ran)", f"{nt}/{len(D['districts'])} districts marked ctx_src = tract", nt == len(D["districts"]))
dm = pd.read_csv(find("district_metrics_v3.csv"), dtype={"cd_geoid": str}).set_index("cd_geoid")
off = [k for k, d in D["districts"].items() if k in dm.index and d["ctx"].get("cases") is not None and abs(d["ctx"]["cases"] - dm.loc[k, "inc_all_cases_sum"]) > 1]
check("Published district cancer-case counts equal the apportioned counts in district_metrics_v3.csv", f"{len(off)} districts differ" + (": " + ", ".join(off[:6]) if off else ""), not off)
# every page's data file is from this pull (a stage that silently kept an old file would leave one page on the previous refresh); changes.js
# ("Recent changes") must compare this pull with the previous one: until October 2026 it was built after this gate had already passed
def js(name): return json.loads(find(name).read_text(encoding="utf-8").split("=", 1)[1].strip().rstrip(";"))
pull_min = flog["timestamp_utc"][:16].replace("T", " "); CH = js("changes.js")["summary"]
pulls = {"data.js": meta.get("pull_utc", "")[:16], "changes.js": CH.get("current_pull", "")[:16].replace("T", " "), "findings.js": js("findings.js")["meta"].get("pull"),
         "community.js": js("community.js")["meta"].get("pull"), "find_data.js": js("find_data.js")["meta"].get("registry_pull")}
stale = {k: v for k, v in pulls.items() if v != (pull_min if len(v or "") > 10 else pull_min[:10])}
check("Every page's data file is from this pull (data.js, changes.js, findings.js, community.js, find_data.js)", f"pull {pull_min} UTC" + ("; from another pull: " + ", ".join(f"{k} {v}" for k, v in stale.items()) if stale else "; all agree") + f"; changes.js compares with the pull of {CH.get('previous_pull', '?')[:10]}", not stale and CH.get("trials_current") == meta["trials"])
# the map page fetches the gzipped tract files first and checks the decompressed length against data.js / rucc.js: each .gz must decompress
# to its .bin byte for byte, and each .bin must have the length the page expects (a stale .gz would serve the previous refresh's tracts)
gzn = []
for name, want in (("tracts60.bin", meta.get("tracts_bin", {}).get("bytes")), ("tract_county.bin", js("rucc.js")["meta"].get("tract_county_bin", {}).get("bytes"))):
    b_, g_ = find(name, required=False), find(name + ".gz", required=False)
    if b_ is None or g_ is None: gzn.append(f"{name}{'' if b_ else ' missing'}{'' if g_ else ': no .gz'}"); continue
    raw = b_.read_bytes()
    try: same = gzip.decompress(g_.read_bytes()) == raw
    except Exception: same = False
    if not same: gzn.append(f"{name}.gz does not decompress to {name}")
    if len(raw) != want: gzn.append(f"{name} is {len(raw):,} bytes, the payload says {want}")
check("Compressed tract files (tracts60.bin.gz, tract_county.bin.gz) decompress to the plain files, whose lengths match data.js and rucc.js", "; ".join(gzn) if gzn else "both match", not gzn)

ok = all(r[2] for r in rows)
md = ["# Release gate", "", f"**{'PASS' if ok else 'FAIL'}** — {sum(1 for r in rows if r[2])}/{len(rows)} checks pass", "", "| Check | Detail | Result |", "|---|---|---|"] + [f"| {n} | {d} | {'✓' if o else '✗'} |" for n, d, o in rows] + [""]
(ROOT / "RELEASE_GATE.md").write_text("\n".join(md)); print(f"\nrelease gate: {'PASS' if ok else 'FAIL — nothing will be published'}"); sys.exit(0 if ok else 1)
