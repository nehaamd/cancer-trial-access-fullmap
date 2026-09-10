"""Connecticut fix for the ACS context layers: county_covariates.csv (from build_covariates.py) is keyed on ACS 2023 county rows,
which for Connecticut are the nine planning regions (091xx). The map, ZIP and population files use the eight legacy counties, so
the four household layers were silently missing for all of Connecticut. This aggregates the tract-level ACS 2023 5-year tables
(B17001 poverty, B27001 insurance, B28002 internet, B08201 vehicles) to legacy counties via the 6-digit tract code (see build_tracts_us.py)
and replaces the CT rows. Median household income is not summable and is left blank for CT (not used in the web app)."""
import json
from pathlib import Path
import numpy as np, pandas as pd, requests

REF = Path("data/ref"); BASE = "https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-{}.dat"
tr = pd.read_csv(REF / "tracts_us.csv", dtype={"tract": str, "county_fips": str}); ct = tr[tr.county_fips.str[:2] == "09"]
legacy_of = dict(zip(ct.tract.str[5:], ct.county_fips))  # 6-digit tract code -> legacy county
WANT = {"b17001": {"pov_universe": ["B17001_E001"], "pov_below": ["B17001_E002"]},
        "b27001": {"ins_universe": ["B27001_E001"], "uninsured": [f"B27001_E{i:03d}" for i in (5, 8, 11, 14, 17, 20, 23, 26, 29, 33, 36, 39, 42, 45, 48, 51, 54, 57)], "uninsured_55_64": ["B27001_E023", "B27001_E051"], "universe_55_64": ["B27001_E021", "B27001_E049"]},
        "b28002": {"hh_total": ["B28002_E001"], "hh_no_internet": ["B28002_E013"], "hh_broadband": ["B28002_E004"]},
        "b08201": {"hh_total_veh": ["B08201_E001"], "hh_no_vehicle": ["B08201_E002"]}}
s = requests.Session(); agg = {}
for table, want in WANT.items():
    hdr = None; n = 0
    with s.get(BASE.format(table), stream=True, timeout=1800) as r:
        r.raise_for_status(); r.encoding = "utf-8"
        for line in r.iter_lines(decode_unicode=True):
            if not line: continue
            if hdr is None: hdr = line.split("|"); idx = {h: i for i, h in enumerate(hdr)}; continue
            if not line.startswith("1400000US09"): continue
            p = line.split("|"); leg = legacy_of.get(p[0][-6:])
            if not leg: continue
            d = agg.setdefault(leg, {})
            for name, cols in want.items():
                v = 0.0
                for c in cols:
                    x = p[idx[c]]
                    if x not in ("", "-666666666", "-999999999", "-888888888", "-222222222", "-333333333"): v += float(x)
                d[name] = d.get(name, 0.0) + v
            n += 1
    print(table, "CT tract rows:", n, flush=True)
cov = pd.read_csv(REF / "county_covariates.csv", dtype={"county_fips": str})
old = cov[cov.county_fips.str[:2] == "09"]; print("CT rows before (planning regions):", old.county_fips.tolist())
cov = cov[cov.county_fips.str[:2] != "09"]
rows = []
for f, d in sorted(agg.items()):
    d = dict(d); d["county_fips"] = f; d["median_hh_income"] = np.nan
    d["poverty_rate"] = 100 * d["pov_below"] / d["pov_universe"]; d["uninsured_rate"] = 100 * d["uninsured"] / d["ins_universe"]; d["uninsured_rate_55_64"] = 100 * d["uninsured_55_64"] / d["universe_55_64"]
    d["pct_hh_no_internet"] = 100 * d["hh_no_internet"] / d["hh_total"]; d["pct_hh_no_vehicle"] = 100 * d["hh_no_vehicle"] / d["hh_total_veh"]; rows.append(d)
new = pd.DataFrame(rows); cov = pd.concat([cov, new], ignore_index=True).sort_values("county_fips"); cov.to_csv(REF / "county_covariates.csv", index=False)
print("CT legacy counties written:", new.county_fips.tolist()); print(new[["county_fips", "poverty_rate", "uninsured_rate", "pct_hh_no_internet", "pct_hh_no_vehicle"]].round(1).to_string(index=False))
json.dump({"ct_legacy_counties": new.county_fips.tolist(), "source": "ACS 2023 5-yr tract tables aggregated to legacy counties", "planning_regions_replaced": old.county_fips.tolist()}, open(REF / "ct_covariates_log.json", "w"), indent=2)
