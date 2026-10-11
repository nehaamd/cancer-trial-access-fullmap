"""Population-weighted center of every ZIP code area (ZCTA) -> data/ref/zcta_popcenter.csv.

Why: the ZIP finder (find.html, data from build_find_data.py) measured from each ZCTA's Census internal point (zcta_pop55.csv), which
for a large or split ZCTA lies in open country, far from where its residents live. ZIP 99701 (Fairbanks) has its internal point
183 miles north of the city and showed no trial within 120 miles while the next ZIP showed 16; 99503 (Anchorage) has a detached part
in the Bethel Census Area that puts its point 274 miles west; 83716 (Boise) is 48 miles off. 247 ZIP points were more than 30 miles
from every populated tract center of their county.

Method: the Census 2020 ZCTA-to-tract relationship file gives, for every tract a ZCTA overlaps, the land area of the overlap. Each
tract's residents 55+ (data/ref/tracts_us.csv, ACS 2023 5-year) are split in proportion to the tract's land area inside the ZCTA
(the same apportionment build_geo_us.py uses for zcta_county_parts.csv), and the ZCTA's center is the mean of its tracts' population
centers weighted by the residents so attributed (a mean on the sphere, so the Aleutian ZCTAs across the 180th meridian are right).
For a ZCTA made of small urban tracts the result is within a mile of the internal point; for a ZCTA that is mostly empty land it
moves to the town.

The internal point is kept (source = internal_point) where the apportionment does not describe the ZCTA: when the residents
attributed from tracts are fewer than half or more than twice the ZCTA's own ACS count (zcta_pop55.csv). A village ZIP of 20 residents
inside one 5,000-square-mile tract gets a few people and the tract's point, 250 miles away (99747); a sparse ZIP inside a populous
tract gets several times its own population (97908: 75 attributed, 12 counted). Both keep the internal point, which lies inside the
ZCTA. ZCTAs outside the 50 states and DC have no tract rows and keep it too.

Columns: zcta, lat, lon, pop55_weighted (residents 55+ attributed from tracts; the ACS figure for the ZCTA itself stays in
zcta_pop55.csv), coverage (attributed / ACS), source (tract_weighted | internal_point), shift_mi (miles from the internal point, for audit).
    python3 build_zcta_centers.py [--rel path/to/tab20_zcta520_tract20_natl.txt]     (downloads the 24 MB file when --rel is absent)
Run after build_tracts_us.py and build_covariates.py (which write tracts_us.csv and zcta_pop55.csv); build_find_data.py reads the
result when it exists. Reference data: re-run only when those two files change (yearly), not on a weekly refresh.
"""
import io, json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np, pandas as pd

REF = Path("data/ref")
REL_URL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_tract20_natl.txt"


def main():
    rel_path = sys.argv[sys.argv.index("--rel") + 1] if "--rel" in sys.argv else None
    cols = ["GEOID_ZCTA5_20", "GEOID_TRACT_20", "AREALAND_TRACT_20", "AREALAND_PART"]
    if rel_path: rel = pd.read_csv(rel_path, sep="|", dtype=str, encoding="utf-8-sig", usecols=cols)
    else:
        import requests
        r = requests.get(REL_URL, timeout=600); r.raise_for_status(); rel = pd.read_csv(io.StringIO(r.content.decode("utf-8-sig")), sep="|", dtype=str, usecols=cols)
    rel = rel[rel.GEOID_ZCTA5_20.notna() & (rel.GEOID_ZCTA5_20 != "")]   # rows with no ZCTA are land outside every ZIP code
    tr = pd.read_csv(REF / "tracts_us.csv", dtype={"tract": str, "county_fips": str}).set_index("tract")
    zc = pd.read_csv(REF / "zcta_pop55.csv", dtype={"zcta": str}).drop_duplicates("zcta").set_index("zcta")
    m = rel[rel.GEOID_TRACT_20.isin(tr.index)].copy()
    share = m.AREALAND_PART.astype(float) / m.AREALAND_TRACT_20.astype(float).replace(0, np.nan)
    m["w"] = (share.fillna(0) * m.GEOID_TRACT_20.map(tr.pop55)).astype(float)
    la, lo = np.radians(m.GEOID_TRACT_20.map(tr.lat)), np.radians(m.GEOID_TRACT_20.map(tr.lon))   # weighted mean on the sphere (unit vectors)
    m["x"] = m.w * np.cos(la) * np.cos(lo); m["y"] = m.w * np.cos(la) * np.sin(lo); m["zz"] = m.w * np.sin(la)
    g = m.groupby("GEOID_ZCTA5_20")[["w", "x", "y", "zz"]].sum(); g = g[g.w > 0]
    g["lat"] = np.degrees(np.arctan2(g.zz, np.hypot(g.x, g.y))); g["lon"] = np.degrees(np.arctan2(g.y, g.x))
    out = zc[["lat", "lon", "pop55"]].rename(columns={"lat": "ilat", "lon": "ilon", "pop55": "acs"}).join(g[["lat", "lon", "w"]], how="left")
    out["coverage"] = (out.w / out.acs.replace(0, np.nan)).round(3)
    weighted = out.lat.notna() & out.coverage.between(0.5, 2.0)
    out["source"] = np.where(weighted, "tract_weighted", "internal_point")
    out["lat"] = out.lat.where(weighted, out.ilat); out["lon"] = out.lon.where(weighted, out.ilon)
    out["pop55_weighted"] = out.w.fillna(0).round().astype(int)
    a1, o1, a2, o2 = (np.radians(out[c]) for c in ("ilat", "ilon", "lat", "lon"))
    h = np.sin((a2 - a1) / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin((o2 - o1) / 2) ** 2; out["shift_mi"] = (2 * 3958.8 * np.arcsin(np.sqrt(h))).round(2)
    res = out.reset_index()[["zcta", "lat", "lon", "pop55_weighted", "coverage", "source", "shift_mi"]].sort_values("zcta")
    res["lat"] = res.lat.round(6); res["lon"] = res.lon.round(6)
    res.to_csv(REF / "zcta_popcenter.csv", index=False)
    w = res[res.source == "tract_weighted"]
    log = {"built_utc": datetime.now(timezone.utc).isoformat(timespec="minutes"), "relationship_file": rel_path or REL_URL, "zctas": int(len(res)), "tract_weighted": int(len(w)),
           "internal_point_kept": int((res.source == "internal_point").sum()), "internal_point_kept_coverage_outside_band": int(((res.source == "internal_point") & res.coverage.notna()).sum()),
           "shift_mi": {"median": float(w.shift_mi.median()), "p90": float(w.shift_mi.quantile(0.9)), "p99": float(w.shift_mi.quantile(0.99)), "max": float(w.shift_mi.max())},
           "moved_over_5_mi": int((w.shift_mi > 5).sum()), "moved_over_30_mi": int((w.shift_mi > 30).sum()),
           "largest_moves": [{"zcta": r.zcta, "shift_mi": r.shift_mi, "pop55_weighted": int(r.pop55_weighted)} for r in w.sort_values("shift_mi", ascending=False).head(8).itertuples()]}
    json.dump(log, open(REF / "zcta_popcenter_log.json", "w"), indent=1); print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
