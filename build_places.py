"""Build docs/places.json: the cities, towns and other Census places the map's search box understands, each with the county
it sits in. Choosing a place in the search box opens that county.

Inputs (all in the repository or downloaded by the refresh): data/ref/gazetteer_places.csv (Census Gazetteer places, written by
build_geo_us.py), the Census county boundary files in data/geo/ (the same ones the web payload uses), data/ref/tracts_us.csv (to
estimate each place's size), and docs/data.js for the list of counties the map carries. Run after build_webapp_data_v3.py:
    python3 build_places.py

A place is assigned to the county that contains its Census internal point, so a city that spans county lines opens the county
its centre is in. The short list of extra names below covers what people type that the Gazetteer does not carry under that name.
"""
import json
from datetime import date
from pathlib import Path
import geopandas as gpd, numpy as np, pandas as pd
from scipy.spatial import cKDTree

REF, DOCS = Path("data/ref"), Path("docs")
# (state, name people type) -> county FIPS. New York City's boroughs are counties under other names; consolidated city-counties
# are listed in the Gazetteer under their legal names ("Nashville-Davidson", "Urban Honolulu").
EXTRA = [("NY", "New York City", "36061"), ("NY", "Manhattan", "36061"), ("NY", "Brooklyn", "36047"), ("NY", "Queens", "36081"), ("NY", "The Bronx", "36005"), ("NY", "Bronx", "36005"), ("NY", "Staten Island", "36085"),
         ("DC", "Washington DC", "11001"), ("DC", "Washington, D.C.", "11001")]
# A city spread over several counties opens the county people mean by its name, not the one its geometric centre falls in.
CENTRE = {("NY", "New York"): "36061"}
SHORT = {("TN", "Nashville-Davidson"): "Nashville", ("KY", "Louisville/Jefferson County"): "Louisville", ("KY", "Lexington-Fayette"): "Lexington", ("HI", "Urban Honolulu"): "Honolulu",
         ("ID", "Boise City"): "Boise", ("CA", "San Buenaventura (Ventura)"): "Ventura", ("IN", "Indianapolis city"): "Indianapolis", ("GA", "Athens-Clarke County"): "Athens",
         ("GA", "Augusta-Richmond County"): "Augusta", ("GA", "Macon-Bibb County"): "Macon", ("MT", "Butte-Silver Bow"): "Butte", ("MT", "Anaconda-Deer Lodge County"): "Anaconda"}


def main():
    D = json.loads((DOCS / "data.js").read_text(encoding="utf-8").split("=", 1)[1].strip().rstrip(";")); have = set(D["counties"])
    gaz = pd.read_csv(REF / "gazetteer_places.csv", dtype={"state": str, "place": str, "geoid": str})
    if "name" not in gaz.columns: gaz["name"] = gaz.place.str.title()   # an older reference file: lower-case names only
    counties = gpd.read_file("zip://data/geo/cb.zip")[["STATEFP", "GEOID", "geometry"]]
    ct2021 = gpd.read_file("zip://data/geo/cb500_2021.zip"); ct2021 = ct2021[ct2021.STATEFP == "09"][["STATEFP", "GEOID", "geometry"]].to_crs(counties.crs)   # Connecticut: the eight legacy counties, as everywhere else in the pipeline
    counties = gpd.GeoDataFrame(pd.concat([counties[counties.STATEFP != "09"], ct2021], ignore_index=True), geometry="geometry", crs=ct2021.crs)[["GEOID", "geometry"]].to_crs(4326)
    pts = gpd.GeoDataFrame(gaz, geometry=gpd.points_from_xy(gaz.lon, gaz.lat), crs=4326)
    j = gpd.sjoin(pts, counties, how="left", predicate="within"); j = j[~j.index.duplicated(keep="first")]
    j = j[j.GEOID.isin(have)]
    # Size of each place, for ranking search results: residents 55+ in the census tracts centred within the place's radius
    # (the radius of a circle of the place's land area, at least one mile). The search box shows the larger place first.
    tr = pd.read_csv(REF / "tracts_us.csv", dtype={"tract": str, "county_fips": str})
    txy = np.column_stack([g.values for g in (lambda p: (p.x, p.y))(gpd.GeoSeries(gpd.points_from_xy(tr.lon, tr.lat), crs=4326).to_crs(5070))])
    pxy = np.column_stack([g.values for g in (lambda p: (p.x, p.y))(gpd.GeoSeries(gpd.points_from_xy(j.lon, j.lat), crs=4326).to_crs(5070))])
    area = j.aland_sqmi.fillna(0).values if "aland_sqmi" in j.columns else np.zeros(len(j))
    radius = np.maximum(1609.344, np.sqrt(area * 2.59e6 / np.pi)); tree = cKDTree(txy); pop = tr.pop55.values
    size = np.array([pop[ix].sum() if len(ix) else 0 for ix in tree.query_ball_point(pxy, radius)], dtype=float)
    nearest = pop[tree.query(pxy)[1]]; size = np.where(size > 0, size, np.minimum(nearest, 500))   # a hamlet smaller than its tract
    rows = {}
    def put(st, nm, f, sz): rows[(st, nm, f)] = max(rows.get((st, nm, f), 0), sz)
    for st, nm, f, sz in zip(j.state, j["name"], j.GEOID, size):
        f = CENTRE.get((st, nm), f); put(st, nm, f, sz)
        if (st, nm) in SHORT: put(st, SHORT[(st, nm)], f, sz)
    cpop = {k: v["p"] for k, v in D["counties"].items()}
    for st, nm, f in EXTRA:
        if f in have: put(st, nm, f, cpop[f])
    by_state = {}
    for (st, nm, f), sz in sorted(rows.items()): by_state.setdefault(st, []).append([nm, f, round(float(np.log10(sz + 1)), 1)])
    out = {"built": str(date.today()), "n": len(rows), "source": "Census Gazetteer places; county = the county containing the place's internal point", "format": "places[state] = [name, county FIPS, log10 of residents 55+ nearby]", "places": by_state}
    s = json.dumps(out, separators=(",", ":"), ensure_ascii=False); (DOCS / "places.json").write_text(s, encoding="utf-8")
    print("places.json KB:", len(s.encode()) // 1024, "| places", len(rows), "| states", len(by_state), "| not in a mapped county (dropped):", len(gaz) - len(j))


if __name__ == "__main__":
    main()
