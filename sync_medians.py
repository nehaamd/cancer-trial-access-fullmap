"""Copy the district, state and national medians, and the "most often" nearest-target labels, from the v3 metrics files into docs/data.js.

Used once, on 9 October 2026, after tract_metrics_us.py changed its median rule (medians over residents with a road route, as
build_rucc.py already did) and was re-run with --from-tract-access. build_webapp_data_v3.py would do the same as part of a full
build, but needs the Census shapefiles under data/geo, which are not in the repository. Every other value in data.js is left as
it is; the script prints each value it changes and stops if anything but a median would change.
    python3 sync_medians.py
"""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent; DOCS = ROOT / "docs"; OUT = ROOT / "out_adult55"; NOROAD = 999.0
COLS = {"medn": "median_road_mi_nci", "medb": "median_road_mi_broad_menu", "medl": "median_road_mi_limited_menu", "mnci": "modal_nearest_nci", "mbroad": "modal_nearest_broad"}
conv = lambda v: v if isinstance(v, str) else None if v >= NOROAD else int(v)

s = (DOCS / "data.js").read_text(encoding="utf-8"); D = json.loads(s[len("window.DATA="):].rstrip().rstrip(";"))
dm = pd.read_csv(OUT / "district_metrics_v3.csv", dtype={"cd_geoid": str}).set_index("cd_geoid")
sm = pd.read_csv(OUT / "state_metrics_v3.csv", dtype={"state_fips": str}).set_index("state_fips")
nat = json.load(open(OUT / "national_metrics_v3.json"))
fips_of = {k: v["st"] for k, v in D["districts"].items()}; usps_fips = {}
for k, v in D["districts"].items(): usps_fips[v["st"]] = k[:2]
changes = []
for k, d in D["districts"].items():
    for key, col in COLS.items():
        new = conv(dm.loc[k, col])
        if d.get(key) != new: changes.append(("district", k, key, d.get(key), new)); d[key] = new
for usps, g in D["state_data"].items():
    f = usps_fips.get(usps)
    if f is None or f not in sm.index: continue
    for key, col in COLS.items():
        new = conv(sm.loc[f, col])
        if g.get(key) != new: changes.append(("state", usps, key, g.get(key), new)); g[key] = new
for key, col in COLS.items():
    new = conv(nat[col])
    if D["meta"]["nat_core"].get(key) != new: changes.append(("nation", "US", key, D["meta"]["nat_core"].get(key), new)); D["meta"]["nat_core"][key] = new
for c in changes: print("%-8s %-5s %s: %s -> %s" % c)
# every other published value must still equal the metrics files (a different run would show up here)
core = {"l20": "pct_lt20_trials_within_60rdmi", "z60": "pct_zero_trials_within_60rdmi", "g60b": "pct_gt60rdmi_broad_menu", "g60n": "pct_gt60rdmi_nci", "nr": "pct_no_road_route_broad", "nrn": "pct_no_road_route_nci", "t60": "wmean_trials_within_60rdmi"}
bad = [(k, key) for k, d in D["districts"].items() for key, col in core.items() if abs(float(d[key]) - float(dm.loc[k, col])) > 1e-9]
bad += [("US", key) for key, col in core.items() if abs(float(D["meta"]["nat_core"][key]) - float(nat[col])) > 1e-9]
if bad: raise SystemExit(f"data.js and the metrics files disagree on more than medians and labels: {bad[:10]}")
(DOCS / "data.js").write_text("window.DATA=" + json.dumps(D, separators=(",", ":"), ensure_ascii=False) + ";", encoding="utf-8")
print(f"{len(changes)} values changed in docs/data.js (medians and 'most often' labels); every other checked value unchanged")
