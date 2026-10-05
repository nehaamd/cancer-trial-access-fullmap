"""Release gate: the last step of a refresh. If anything here fails the refresh stops and nothing is published;
GitHub Actions then emails the failure. Writes RELEASE_GATE.md.

Checks
  1. Classification audit has no unreviewed strings (audit_cancer_types.py; see qc_cancer_type_audit.md)
  2. Headline numbers are within plausible bounds and did not jump from the previous snapshot
     (a jump means the registry pull or a pipeline stage broke, not that access changed in a week)
  2b. The road network still routes short local trips sensibly and has not invented water crossings (route_us.py LOCAL_CHECKS),
      and few residents have a site nearby in a straight line but none by road (route_sites_us.py)
  3. The published payload is internally consistent (trial count, county / district / state counts, no NaN in headline fields)
    python3 release_gate.py
"""
import json, subprocess, sys
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

# 2. headline numbers: bounds and drift
nat = json.load(open(find("national_metrics_v3.json"))); D = json.loads(find("data.js").read_text().split("=", 1)[1].strip().rstrip(";")); meta = D["meta"]
check("Trial count plausible (2,000–8,000)", f"{meta['trials']:,} eligible trials", 2000 <= meta["trials"] <= 8000)
check("Population 55+ unchanged (ACS reference)", f"{nat['pop55']:,}", 90e6 <= nat["pop55"] <= 110e6)
for k, lo, hi in (("pct_lt20_trials_within_60rdmi", 5, 30), ("pct_zero_trials_within_60rdmi", 1, 15), ("pct_gt60rdmi_broad_menu", 20, 60), ("pct_gt60rdmi_nci", 25, 65), ("median_road_mi_nci", 25, 90)):
    check(f"{k} within bounds [{lo}, {hi}]", str(nat[k]), lo <= nat[k] <= hi)
snaps = sorted((ROOT / "data" / "snapshots").glob("*/national_metrics_v3.json")) if (ROOT / "data" / "snapshots").exists() else []
if snaps:
    prev = json.load(open(snaps[-1])); pt = json.load(open(snaps[-1].parent / "fetch_log.json")).get("timestamp_utc", "?")[:10] if (snaps[-1].parent / "fetch_log.json").exists() else snaps[-1].parent.name
    mv_prev, mv_now = int(prev.get("method_version", 1)), int(nat.get("method_version", 1))
    if mv_prev != mv_now:
        # the previous pull was calculated with an earlier method (config.METHOD_CHANGES): a step between the two is expected and is not drift
        check(f"Drift vs the pull of {pt}", f"skipped once: the method changed (version {mv_prev} -> {mv_now}); the bounds above still apply", True)
    else:
        for k, tol in (("pct_lt20_trials_within_60rdmi", 1.5), ("pct_zero_trials_within_60rdmi", 1.0), ("pct_gt60rdmi_broad_menu", 2.0), ("pct_gt60rdmi_nci", 1.0), ("median_road_mi_nci", 5)):
            check(f"{k} moved less than {tol} since {pt}", f"{prev[k]} -> {nat[k]}", abs(nat[k] - prev[k]) <= tol)
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

# 3. payload consistency
T = D["T"]; check("data.js trial list matches meta.trials", f"{len(T['id']):,} vs {meta['trials']:,}", len(T["id"]) == meta["trials"])
check("436 districts and 51 states in the payload", f"{len(D['districts'])} districts, {len(D['state_data'])} states", len(D["districts"]) == 436 and len(D["state_data"]) == 51)
check("3,143 counties in the payload", f"{len(D['counties']):,}", len(D["counties"]) == 3143)
bad = [k for k, d in D["districts"].items() if any(d[f] is None or d[f] != d[f] for f in ("l20", "z60", "g60b", "g60n"))]
check("No district with a missing headline figure", f"{len(bad)} missing", not bad)
nm = sum(1 for d in D["districts"].values() if not d.get("member")); check("Vacant seats are few (member list loaded)", f"{nm} districts without a member", nm <= 8)
st = pd.read_csv(find("state_metrics_v3.csv")); check("Every state has residents 55+ and a finite access share", f"{len(st)} rows", len(st) == 51 and st.pct_lt20_trials_within_60rdmi.notna().all())

ok = all(r[2] for r in rows)
md = ["# Release gate", "", f"**{'PASS' if ok else 'FAIL'}** — {sum(1 for r in rows if r[2])}/{len(rows)} checks pass", "", "| Check | Detail | Result |", "|---|---|---|"] + [f"| {n} | {d} | {'✓' if o else '✗'} |" for n, d, o in rows] + [""]
(ROOT / "RELEASE_GATE.md").write_text("\n".join(md)); print(f"\nrelease gate: {'PASS' if ok else 'FAIL — nothing will be published'}"); sys.exit(0 if ok else 1)
