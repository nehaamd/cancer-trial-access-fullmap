"""Tract-level household context and apportioned cancer cases for districts, states and the nation.

Why: the district, state and national "household context" figures used to be residents-55+-weighted means of COUNTY values, and a
district's "average annual new cancer cases" was the sum of every county it touches. For a district inside one big county (TX-9 in
Harris County) that meant the district showed the whole county's figures: 23,274 cases a year and Harris County's poverty rate.

What this does:
  1. Streams four ACS 2023 5-year tables at census-tract level (same tables and cells as build_covariates.py):
       B08201 households without a vehicle, B28002 households with broadband, B27001 uninsured (all ages and 55-64), B17001 poverty.
  2. District / state / national rates = (sum of tract numerators) / (sum of tract denominators), with tracts split by a district
     boundary counted by their tract_cd119.csv share. Tracts without ACS values fall back to their county's rate (counted in *_cov).
  3. Average annual cancer cases = each county's State Cancer Profiles count x (that county's residents 55+ inside the area /
     county residents 55+). An estimate, labelled as one: incidence is only published down to counties.
  4. The all-sites incidence RATE stays a residents-55+-weighted mean of county rates (no sub-county rates exist); the page says so.
  5. Rewrites the ctx blocks in data.js (nat_ctx, state_data[*].ctx, districts[*].ctx) and writes tract_covariates.csv and
     district_context_v3.csv for audit. Adds "ctx_src": "tract" so the page can label the figures.

Run after build_webapp_data_v3.py:  python3 build_tract_context.py   (about 5-10 minutes; the ACS files are streamed, not stored)
Inputs are looked for in the repository root first, then in data/ref, out_adult55 and docs (the pipeline layout).
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, requests

ROOT = Path(__file__).resolve().parent
BASE = "https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-{}.dat"
BAD = {"", "-666666666", "-999999999", "-888888888", "-222222222", "-333333333", "-555555555"}


def find(name):
    for d in (ROOT, ROOT / "data" / "ref", ROOT / "out_adult55", ROOT / "docs", ROOT / "data" / "raw"):
        if (d / name).exists(): return d / name
    sys.exit(f"missing input: {name}")


def stream(table, want):
    """Stream an ACS table-based summary file; keep tract rows; return DataFrame indexed by 11-digit tract GEOID."""
    hdr, rows = None, {}
    with requests.get(BASE.format(table), stream=True, timeout=1800) as r:
        r.raise_for_status(); r.encoding = "utf-8"
        for line in r.iter_lines(decode_unicode=True):
            if not line: continue
            if hdr is None: hdr = line.split("|"); idx = {h: i for i, h in enumerate(hdr)}; continue
            if not line.startswith("1400000US"): continue
            p = line.split("|"); vals = {}
            for name, cols in want.items():
                xs = [p[idx[c]] for c in cols]
                vals[name] = np.nan if any(x in BAD for x in xs) else sum(float(x) for x in xs)
            rows[p[0][-11:]] = vals
    print(f"  {table}: {len(rows):,} tracts", flush=True)
    return pd.DataFrame.from_dict(rows, orient="index")


def tract_acs():
    cache = ROOT / "tract_covariates.csv"
    if cache.exists() and "--refetch" not in sys.argv:
        return pd.read_csv(cache, dtype={"tract": str}).set_index("tract")
    print("streaming ACS 2023 5-year tract tables ...", flush=True)
    parts = [
        stream("b08201", {"veh_den": ["B08201_E001"], "veh_num": ["B08201_E002"]}),
        stream("b28002", {"bb_den": ["B28002_E001"], "bb_num": ["B28002_E004"]}),
        stream("b27001", {"unins_den": ["B27001_E001"],
                          "unins_num": [f"B27001_E{i:03d}" for i in (5, 8, 11, 14, 17, 20, 23, 26, 29, 33, 36, 39, 42, 45, 48, 51, 54, 57)],
                          "unins55_den": ["B27001_E021", "B27001_E049"], "unins55_num": ["B27001_E023", "B27001_E051"]}),
        stream("b17001", {"pov_den": ["B17001_E001"], "pov_num": ["B17001_E002"]}),
    ]
    t = pd.concat(parts, axis=1); t.index.name = "tract"
    t.reset_index().to_csv(cache, index=False)
    return t


def main():
    tr = pd.read_csv(find("tract_access.csv"), dtype={"tract": str, "county_fips": str}, usecols=["tract", "county_fips", "pop55"])
    rel = pd.read_csv(find("tract_cd119.csv"), dtype={"tract": str, "cd_geoid": str}); rel["share"] = rel.share.astype(float)
    cov = pd.read_csv(find("county_covariates.csv"), dtype={"county_fips": str}).set_index("county_fips")
    inc = pd.read_csv(find("cancer_incidence_county.csv"), dtype={"county_fips": str}); inc = inc[inc.site == "all"].set_index("county_fips")
    acs = tract_acs()

    # Connecticut: the map keys tracts on the eight legacy counties; ACS 2023 keys them on planning regions. Tract codes (last six
    # digits) were kept in the 2022 change, so match CT on state + tract code.
    ct_map = {g[:2] + g[-6:]: g for g in acs.index if g.startswith("09")}
    tr["acs_key"] = np.where(tr.tract.str.startswith("09"), (tr.tract.str[:2] + tr.tract.str[-6:]).map(ct_map), tr.tract)
    tr = tr.join(acs, on="acs_key")
    measures = {"veh": ("veh_num", "veh_den", "pct_hh_no_vehicle"), "bb": ("bb_num", "bb_den", None), "unins": ("unins_num", "unins_den", "uninsured_rate"),
                "unins55": ("unins55_num", "unins55_den", "uninsured_rate_55_64"), "pov": ("pov_num", "pov_den", "poverty_rate")}
    matched = tr.veh_den.notna()
    print(f"tracts matched to ACS: {matched.sum():,} of {len(tr):,} ({100 * tr.pop55[matched].sum() / tr.pop55.sum():.2f}% of residents 55+)")
    # fallback: a tract with no ACS row (or a suppressed cell) gets its county's rate on the tract's own denominator proxy (pop55)
    cbb = 100 * cov.hh_broadband / cov.hh_total.replace(0, np.nan)
    for k, (num, den, ccol) in measures.items():
        crate = (cbb if k == "bb" else cov[ccol]).reindex(tr.county_fips).values / 100
        miss = tr[num].isna() | tr[den].isna() | (tr[den] <= 0)
        tr[f"{k}_fb"] = miss
        tr.loc[miss, den] = tr.loc[miss, "pop55"]; tr.loc[miss, num] = tr.loc[miss, "pop55"] * crate[miss.values]
    # apportioned cases: county cases x tract share of county residents 55+
    cpop = tr.groupby("county_fips").pop55.sum()
    ccases = inc.avg_annual_count.where(inc.status.isin(["ok", "small_numbers"]))
    tr["cases_share"] = (tr.county_fips.map(ccases) * tr.pop55 / tr.county_fips.map(cpop).replace(0, np.nan))
    tr["inc_rate"] = tr.county_fips.map(inc.rate.where(inc.status.isin(["ok", "small_numbers"])))

    def ctx(g, w):
        out = {}
        for k, (num, den, _) in measures.items():
            nn = (g[num] * w).sum(); dd = (g[den] * w).sum()
            out[k] = None if dd <= 0 or not np.isfinite(nn) else round(float(100 * nn / dd), 1)
        P = (g.pop55 * w).sum()
        out["acs_cov"] = round(float(100 * (g.pop55 * w)[~g.veh_fb].sum() / P), 1) if P > 0 else None   # share of residents 55+ on tract-level values
        m = g.inc_rate.notna(); Pm = (g.pop55 * w)[m].sum()
        out["inc"] = round(float((g.inc_rate * g.pop55 * w)[m].sum() / Pm), 1) if Pm > 0 else None
        out["inc_cov"] = round(float(100 * Pm / P), 1) if P > 0 else None
        c = (g.cases_share * w)
        out["cases"] = int(round(float(c.sum()))) if c.notna().any() else None
        out["ctx_src"] = "tract"
        return out

    m = rel.merge(tr, on="tract", how="inner")
    dist = {k: ctx(g, g.share) for k, g in m.groupby("cd_geoid")}
    tr["state_fips"] = tr.county_fips.str[:2]
    one = pd.Series(1.0, index=tr.index)
    states = {k: ctx(g, one.loc[g.index]) for k, g in tr.groupby("state_fips")}
    nat = ctx(tr, one)

    audit = pd.DataFrame.from_dict(dist, orient="index"); audit.index.name = "cd_geoid"; audit.reset_index().to_csv(ROOT / "district_context_v3.csv", index=False)

    # rewrite data.js
    djs = find("data.js"); s = djs.read_text()
    pre, body = s.split("=", 1); D = json.loads(body.strip().rstrip(";"))
    old9 = D["districts"].get("4809", {}).get("ctx")
    D["meta"]["nat_ctx"] = {**D["meta"].get("nat_ctx", {}), **nat}
    for k, v in dist.items():
        if k in D["districts"]: D["districts"][k]["ctx"] = {**D["districts"][k].get("ctx", {}), **v}
    for usps, rec in D["state_data"].items():
        f = rec.get("fips")
        if f in states: rec["ctx"] = {**rec.get("ctx", {}), **states[f]}
    D["meta"]["ctx_method"] = ("Household figures: ACS 2023 5-year census-tract tables summed over the area (tracts split by a district boundary "
                               "counted by share). Cases: county averages apportioned by residents 55+. Incidence rate: county rates weighted by residents 55+.")
    djs.write_text(pre + "=" + json.dumps(D, separators=(",", ":")) + ";")
    print("TX-9 before:", old9); print("TX-9 after: ", D["districts"]["4809"]["ctx"]); print("TX-11 after:", D["districts"]["4811"]["ctx"])
    tot = sum(v["cases"] or 0 for v in dist.values())
    print(f"district cases sum {tot:,} vs national {nat['cases']:,} (should match within rounding; districts sum to the nation)")


if __name__ == "__main__":
    main()
