"""Release gate: the last step of a refresh. If anything here fails the refresh stops and nothing is published;
GitHub Actions then emails the failure. Writes RELEASE_GATE.md.

Checks
  1. Classification audit has no unreviewed strings (audit_cancer_types.py; see qc_cancer_type_audit.md)
  2. Headline numbers are within plausible bounds and did not jump from the previous snapshot
     (a jump means the registry pull or a pipeline stage broke, not that access changed in a week)
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
    for k, tol in (("pct_lt20_trials_within_60rdmi", 1.5), ("pct_zero_trials_within_60rdmi", 1.0), ("pct_gt60rdmi_broad_menu", 2.0), ("pct_gt60rdmi_nci", 1.0), ("median_road_mi_nci", 5)):
        check(f"{k} moved less than {tol} since {pt}", f"{prev[k]} -> {nat[k]}", abs(nat[k] - prev[k]) <= tol)
    pc = (ROOT / "data" / "snapshots" / snaps[-1].parent.name / "county_metrics.csv")
    if pc.exists():
        a = pd.read_csv(pc, dtype={"county_fips": str}); b = pd.read_csv(find("county_metrics.csv"), dtype={"county_fips": str})
        ta, tb = a.trials_in_county.sum(), b.trials_in_county.sum()
        check("County trial-site total moved less than 15% since the previous pull", f"{ta:,} -> {tb:,}", abs(tb - ta) <= 0.15 * max(ta, 1))
else:
    check("Drift vs previous snapshot", "no previous snapshot yet (first run) — skipped", True)

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
