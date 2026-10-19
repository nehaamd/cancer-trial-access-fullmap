#!/bin/sh
# Refresh chain. It stops at the first stage that fails, and then publishes nothing (the classification audit, the validation and the release
# gate are stages): snapshot of the pull being replaced -> registry pull -> QC -> county metrics -> cancer types
#   -> road graph (rebuilt only when its rules changed) -> routing -> site routing -> tract/district metrics -> Tier 4 -> member list -> web payload
#   -> rural/urban layer -> burden-vs-access layer -> deaths-vs-access layer (mortality.js) -> oncologists-vs-trials layer (oncologists.js; the CMS/NPPES extract in data/ref is reused) -> ZIP-lookup data -> place names for the search box -> cosponsor pull (govinfo; set CONGRESS_API_KEY
#   for api.congress.gov) -> findings -> community pages -> what changed since the previous pull (changes.js) -> README headline numbers -> validation -> release gate.
# Reference data (Census tables, burden, covariates) are reused; re-run their scripts separately when those sources update.
# REFRESH_SKIP_FETCH=1 re-runs everything on the registry pull already in data/raw/ (used to test a change to the method without changing the data);
# no snapshot is taken then, and changes.js compares the pull with the same previous pull as when it was published.
set -e; cd "$(dirname "$0")"
if [ -z "$REFRESH_SKIP_FETCH" ]; then
  # Keep the pull about to be replaced, with the figures computed from it, in data/snapshots/<its date>/: diff_snapshots.py (the "Recent changes"
  # tab) and the release gate's drift checks compare the new pull with it. (Until October 2026 the workflow took this snapshot, so a refresh run
  # by hand compared with the pull before last.)
  python3 - <<'EOF'
import json, shutil, sys
from pathlib import Path
raw, snaps = Path("data/raw"), Path("data/snapshots")
if not (raw / "fetch_log.json").exists(): print("snapshot: no previous pull in data/raw/"); sys.exit(0)
ts = json.load(open(raw / "fetch_log.json"))["timestamp_utc"]
# The figures in out_adult55/ must be the ones computed from this pull. A refresh that stopped part-way leaves a newer pull in data/raw/ beside
# older figures (docs/data.js names the pull its figures came from); the pull those figures belong to was snapshotted before that refresh.
dj = Path("docs/data.js"); pub = json.loads(dj.read_text(encoding="utf-8").split("=", 1)[1].strip().rstrip(";"))["meta"].get("pull_utc", "") if dj.exists() else ""
if pub[:16] != ts[:16].replace("T", " "):
    print(f"snapshot: skipped - data/raw/ holds the pull of {ts[:16]} but the published figures are from {pub or 'an unknown pull'} (a refresh stopped part-way)"); sys.exit(0)
d = snaps / ts[:10]
if d.exists() and (not (d / "fetch_log.json").exists() or json.load(open(d / "fetch_log.json")).get("timestamp_utc") != ts):
    d = snaps / (ts[:10] + "T" + ts[11:13] + ts[14:16])   # a second pull on the same day: the first one's snapshot is kept
files = [raw / "trials.csv", raw / "us_sites.csv", raw / "fetch_log.json", raw / "trial_cancer_type.csv",
         Path("out_adult55/county_metrics.csv"), Path("out_adult55/national_metrics_v3.json"), Path("out_adult55/state_metrics_v3.csv")]
missing = [str(f) for f in files if not f.exists()]
if missing: sys.exit(f"snapshot: cannot keep the previous pull, missing {missing}")
d.mkdir(parents=True, exist_ok=True)
for f in files: shutil.copy2(f, d / f.name)
print(f"snapshot: the pull of {ts[:16]} and its figures -> {d}/")
EOF
  # each stage on its own line: under set -e a failure in the middle of an "a && b" list does not stop the script, so a failed registry
  # pull used to fall through to the rest of the chain, which then republished the previous pull as a new refresh
  python3 fetch_us.py
  python3 qc_us.py
else
  echo "REFRESH_SKIP_FETCH set: keeping the registry pull in data/raw/"; python3 qc_us.py --nci-only
fi
python3 metrics_us.py --min-max-age 55 --out out_adult55 && python3 classify_cancer_type.py && python3 audit_cancer_types.py \
 && python3 build_roads_us.py --if-stale \
 && python3 route_us.py && python3 route_sites_us.py && python3 tract_metrics_us.py && python3 tier4_covering.py && python3 fetch_legislators.py && python3 build_webapp_data_v3.py && python3 build_tract_context.py \
 && python3 build_rucc.py && python3 build_burden_access.py && python3 build_mortality.py && python3 build_oncologists.py && python3 build_find_data.py && python3 build_places.py && python3 fetch_cosponsors.py && python3 build_findings.py && python3 build_community.py \
 && python3 diff_snapshots.py && python3 build_readme.py && python3 validate_v3.py && python3 release_gate.py
