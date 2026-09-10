"""Reference data for the methods review: ZCTA centroids and pop 55+, county covariates."""
import csv, io, json, zipfile
from pathlib import Path
import pandas as pd, requests

REF = Path("data/ref"); BASE = "https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-{}.dat"
s = requests.Session()


def stream(table, prefixes, want, out_cols):
    """Stream an ACS table; keep rows whose GEO_ID starts with any prefix; return dict geoid -> {col: int}."""
    hdr, rows = None, {}
    with s.get(BASE.format(table), stream=True, timeout=900) as r:
        r.raise_for_status(); r.encoding = "utf-8"
        for line in r.iter_lines(decode_unicode=True):
            if not line: continue
            if hdr is None: hdr = line.split("|"); idx = {h: i for i, h in enumerate(hdr)}; continue
            if not line.startswith(prefixes): continue
            p = line.split("|"); g = p[0]
            vals = {}
            for name, cols in want.items():
                v = 0
                for c in cols:
                    x = p[idx[c]]
                    if x in ("", "-666666666", "-999999999", "-888888888", "-222222222", "-333333333"): x = None
                    if x is not None: v += float(x)
                vals[name] = v
            rows[g] = vals
    return rows


# --- ZCTA centroids (gazetteer) and pop 55+ ---
z = zipfile.ZipFile(io.BytesIO(s.get("https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip", timeout=300).content))
gz = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), sep="\t", dtype={"GEOID": str}); gz.columns = [c.strip() for c in gz.columns]
gz = gz.rename(columns={"GEOID": "zcta", "INTPTLAT": "lat", "INTPTLONG": "lon"})[["zcta", "lat", "lon"]]
age55 = [f"B01001_E{i:03d}" for i in list(range(17, 26)) + list(range(41, 50))]
zp = stream("b01001", ("860Z200US",), {"pop55": age55, "pop_total": ["B01001_E001"]}, None)
zdf = pd.DataFrame([{"zcta": k[-5:], **v} for k, v in zp.items()])
zdf = gz.merge(zdf, on="zcta", how="inner"); zdf.to_csv(REF / "zcta_pop55.csv", index=False)
print("ZCTAs with centroid+pop:", len(zdf), "| pop55 total:", int(zdf.pop55.sum()))

# --- county covariates ---
C = ("0500000US",)
cov = {}
cov.update({k: {"median_hh_income": v["median_hh_income"]} for k, v in stream("b19013", C, {"median_hh_income": ["B19013_E001"]}, None).items()})
for k, v in stream("b17001", C, {"pov_universe": ["B17001_E001"], "pov_below": ["B17001_E002"]}, None).items(): cov.setdefault(k, {}).update(v)
# B27001: uninsured by age; 55-64 = E024 (M) + E052 (F) no-insurance; 65-74 E027/E055; 75+ E030/E058 ; universes: M 55-64 E022, 65-74 E025, 75+ E028; F 55-64 E050, 65-74 E053, 75+ E056
for k, v in stream("b27001", C, {"ins_universe": ["B27001_E001"], "uninsured": [f"B27001_E{i:03d}" for i in (5, 8, 11, 14, 17, 20, 23, 26, 29, 33, 36, 39, 42, 45, 48, 51, 54, 57)],
                                  "uninsured_55_64": ["B27001_E023", "B27001_E051"], "universe_55_64": ["B27001_E021", "B27001_E049"]}, None).items(): cov.setdefault(k, {}).update(v)
for k, v in stream("b28002", C, {"hh_total": ["B28002_E001"], "hh_no_internet": ["B28002_E013"], "hh_broadband": ["B28002_E004"]}, None).items(): cov.setdefault(k, {}).update(v)
for k, v in stream("b08201", C, {"hh_total_veh": ["B08201_E001"], "hh_no_vehicle": ["B08201_E002"]}, None).items(): cov.setdefault(k, {}).update(v)
for k, v in stream("b03002", C, {"race_total": ["B03002_E001"], "white_nh": ["B03002_E003"], "black_nh": ["B03002_E004"], "aian_nh": ["B03002_E005"], "hispanic": ["B03002_E012"]}, None).items(): cov.setdefault(k, {}).update(v)
cdf = pd.DataFrame([{"county_fips": k[-5:], **v} for k, v in cov.items()])

# 2020 urban/rural shares by county
ua = pd.read_excel(io.BytesIO(s.get("https://www2.census.gov/geo/docs/reference/ua/2020_UA_COUNTY.xlsx", timeout=300).content), dtype=str)
ua.columns = [c.strip() for c in ua.columns]
statecol = [c for c in ua.columns if c.upper().startswith("STATE")][0]; countycol = [c for c in ua.columns if c.upper().startswith("COUNTY")][0]
rur = [c for c in ua.columns if "RUR" in c.upper() and "POP" in c.upper()]; tot = [c for c in ua.columns if c.upper() in ("POP_COU", "POP_TOTAL", "POP", "TOTAL_POP")] or [c for c in ua.columns if "POP" in c.upper()]
print("urban/rural columns:", list(ua.columns)[:12])
ua["county_fips"] = ua[statecol].str.zfill(2) + ua[countycol].str.zfill(3)
ua["pct_rural_2020"] = 100 * pd.to_numeric(ua[rur[0]], errors="coerce") / pd.to_numeric(ua[tot[0]], errors="coerce")
cdf = cdf.merge(ua[["county_fips", "pct_rural_2020"]], on="county_fips", how="left")
cdf["poverty_rate"] = 100 * cdf.pov_below / cdf.pov_universe; cdf["uninsured_rate"] = 100 * cdf.uninsured / cdf.ins_universe
cdf["uninsured_rate_55_64"] = 100 * cdf.uninsured_55_64 / cdf.universe_55_64; cdf["pct_hh_no_internet"] = 100 * cdf.hh_no_internet / cdf.hh_total
cdf["pct_hh_no_vehicle"] = 100 * cdf.hh_no_vehicle / cdf.hh_total_veh; cdf["pct_black_nh"] = 100 * cdf.black_nh / cdf.race_total
cdf["pct_hispanic"] = 100 * cdf.hispanic / cdf.race_total; cdf["pct_aian_nh"] = 100 * cdf.aian_nh / cdf.race_total
cdf.to_csv(REF / "county_covariates.csv", index=False)
print("counties with covariates:", len(cdf), "| median income median:", cdf.median_hh_income.median(), "| rural share available:", cdf.pct_rural_2020.notna().sum())
