"""Population-weighted center of every ZIP code area (ZCTA) -> data/ref/zcta_popcenter.csv.

Why: the ZIP finder (find.html, data from build_find_data.py) measured from each ZCTA's Census internal point (zcta_pop55.csv), which
for a large or split ZCTA lies in open country, far from where its residents live. ZIP 99701 (Fairbanks) has its internal point
183 miles north of the city and showed no trial within 120 miles while the next ZIP showed 16; 99503 (Anchorage) has a detached part
in the Bethel Census Area that puts its point 274 miles west; 83716 (Boise) is 48 miles off. 247 ZIP points were more than 30 miles
from every populated tract center of their county.

Method: the Census 2020 ZCTA-to-tract relationship file gives, for every tract a ZCTA overlaps, the land area of the overlap. Each
tract's residents 55+ (data/ref/tracts_us.csv, ACS 5-year (config.ACS_YEAR)) are split in proportion to the tract's land area inside the ZCTA
(the same apportionment build_geo_us.py uses for zcta_county_parts.csv), and the ZCTA's center is the mean of its tracts' population
centers weighted by the residents so attributed (a mean on the sphere, so the Aleutian ZCTAs across the 180th meridian are right).
For a ZCTA made of small urban tracts the result is within a mile of the internal point; for a ZCTA that is mostly empty land it
moves to the town.

The weighted center is used only when two tests agree that it describes the ZCTA; otherwise the Census internal point is kept
(source = internal_point):
  1. coverage: the residents attributed from tracts are at least half and at most twice the ZCTA's own ACS count (zcta_pop55.csv).
     A village ZIP of 20 residents inside one 5,000-square-mile tract gets a few people and the tract's point, 250 miles away (99747);
     a sparse ZIP inside a populous tract gets several times its own population (97908: 75 attributed, 12 counted).
  2. place: the center lies inside its own ZCTA, or within a mile of it (the Census cartographic boundary file, generalised to
     1:500,000, so a center on the line can fall just outside). A ZCTA that holds a sliver of a large tract takes that tract's point,
     which the coverage test does not catch: until 11 October 2026 only test 1 was applied, and 2,905 centers lay more than a mile
     outside their own ZIP area (683 more than 5 miles); 97904 (Harney County OR) moved 54 miles out of its ZIP and its nearest
     site went from about 86 to about 147 estimated road-miles.
Checked against an independent reference, the 2020 Census block-group centers of population averaged inside each ZCTA polygon
(26,381 ZCTAs that contain one): the internal points are a median 1.30 miles from it, 487 more than 10 miles; these centers 0.94
miles, 297 more than 10 miles. Where test 1 fails but the center is inside the ZIP, the internal point is the closer of the two in
62% of ZCTAs, and where test 2 fails in 92%, so both tests are kept. ZCTAs outside the 50 states and DC have no tract rows and keep
the internal point too.

Columns: zcta, lat, lon, pop55_weighted (residents 55+ attributed from tracts; the ACS figure for the ZCTA itself stays in
zcta_pop55.csv), coverage (attributed / ACS), outside_mi (miles from the tract-weighted center to its own ZCTA polygon, 0 inside),
source (tract_weighted | internal_point), shift_mi (miles from the internal point to the center used, for audit).
    python3 build_zcta_centers.py [--rel path/to/tab20_zcta520_tract20_natl.txt] [--shp path/to/cb_2020_us_zcta520_500k.zip]
    (each file is downloaded from www2.census.gov when its option is absent: 24 MB and 66 MB)
Run after build_tracts_us.py and build_covariates.py (which write tracts_us.csv and zcta_pop55.csv); build_find_data.py reads the
result when it exists. Reference data: re-run only when those two files change (yearly), not on a weekly refresh.
"""
import io, json, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np, pandas as pd

REF = Path("data/ref")
REL_URL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_tract20_natl.txt"
SHP_URL = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"
MAX_OUTSIDE_MI = 1.0
# distances to a polygon are measured in an equal-area projection for the region (Alaska, Hawaii, the rest)
REGION_CRS = {"02": "EPSG:3338", "15": "ESRI:102007"}; DEFAULT_CRS = "EPSG:5070"


def outside_miles(centers, shp_path):
    """Miles from each center (index zcta; lat, lon) to its own ZCTA polygon: 0 inside, NaN when the ZCTA has no polygon."""
    import geopandas as gpd
    shp = gpd.read_file(shp_path, columns=["ZCTA5CE20"]).drop_duplicates("ZCTA5CE20").set_index("ZCTA5CE20")
    st = pd.read_csv(REF / "zcta_county.csv", dtype=str).drop_duplicates("zcta").set_index("zcta").county_fips.str[:2].reindex(centers.index)
    crs_of = st.map(REGION_CRS).fillna(DEFAULT_CRS); out = pd.Series(np.nan, index=centers.index)
    have = centers.index.isin(shp.index)
    for crs in crs_of[have].unique():
        c = centers[have & (crs_of == crs).values]
        pts = gpd.GeoSeries(gpd.points_from_xy(c.lon, c.lat), index=c.index, crs=shp.crs).to_crs(crs)
        out.loc[c.index] = pts.distance(shp.geometry.reindex(c.index).to_crs(crs), align=True).values / 1609.344
    return out


def main():
    rel_path = sys.argv[sys.argv.index("--rel") + 1] if "--rel" in sys.argv else None
    shp_path = sys.argv[sys.argv.index("--shp") + 1] if "--shp" in sys.argv else None
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
    has = out.lat.notna(); tmp = None
    if not shp_path:
        import requests
        tmp = tempfile.TemporaryDirectory(); shp_path = str(Path(tmp.name) / "zcta.zip")
        r = requests.get(SHP_URL, timeout=900); r.raise_for_status(); Path(shp_path).write_bytes(r.content)
    out["outside_mi"] = outside_miles(out.loc[has, ["lat", "lon"]], ("zip://" + shp_path) if shp_path.endswith(".zip") and "://" not in shp_path else shp_path).reindex(out.index).round(2)
    if tmp: tmp.cleanup()
    band = out.coverage.between(0.5, 2.0); placed = out.outside_mi <= MAX_OUTSIDE_MI   # NaN (no polygon) fails the test
    weighted = has & band & placed
    out["source"] = np.where(weighted, "tract_weighted", "internal_point")
    out["lat"] = out.lat.where(weighted, out.ilat); out["lon"] = out.lon.where(weighted, out.ilon)
    out["pop55_weighted"] = out.w.fillna(0).round().astype(int)
    a1, o1, a2, o2 = (np.radians(out[c]) for c in ("ilat", "ilon", "lat", "lon"))
    h = np.sin((a2 - a1) / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin((o2 - o1) / 2) ** 2; out["shift_mi"] = (2 * 3958.8 * np.arcsin(np.sqrt(h))).round(2)
    res = out.reset_index()[["zcta", "lat", "lon", "pop55_weighted", "coverage", "outside_mi", "source", "shift_mi"]].sort_values("zcta")
    res["lat"] = res.lat.round(6); res["lon"] = res.lon.round(6)
    res.to_csv(REF / "zcta_popcenter.csv", index=False)
    w = res[res.source == "tract_weighted"]
    log = {"built_utc": datetime.now(timezone.utc).isoformat(timespec="minutes"), "relationship_file": REL_URL, "zcta_polygons": SHP_URL,
           "read_from_local_copies": [k for k in ("--rel", "--shp") if k in sys.argv],
           "zctas": int(len(res)), "tract_weighted": int(len(w)), "internal_point_kept": int((res.source == "internal_point").sum()),
           "internal_point_kept_because": {"no_tract_rows": int((~has).sum()), "coverage_outside_0.5_2": int((has & ~band).sum()),
                                           f"center_more_than_{MAX_OUTSIDE_MI:g}_mi_outside_its_zcta": int((has & band & ~placed & out.outside_mi.notna()).sum()), "no_zcta_polygon": int((has & band & out.outside_mi.isna()).sum())},
           "centers_outside_their_zcta_before_the_place_test": {"over_1_mi": int((has & band & (out.outside_mi > 1)).sum()), "over_5_mi": int((has & band & (out.outside_mi > 5)).sum())},
           "shift_mi": {"median": float(w.shift_mi.median()), "p90": float(w.shift_mi.quantile(0.9)), "p99": float(w.shift_mi.quantile(0.99)), "max": float(w.shift_mi.max())},
           "moved_over_5_mi": int((w.shift_mi > 5).sum()), "moved_over_30_mi": int((w.shift_mi > 30).sum()),
           "largest_moves": [{"zcta": r.zcta, "shift_mi": r.shift_mi, "pop55_weighted": int(r.pop55_weighted)} for r in w.sort_values("shift_mi", ascending=False).head(8).itertuples()]}
    json.dump(log, open(REF / "zcta_popcenter_log.json", "w"), indent=1); print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
