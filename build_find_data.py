"""Data for find.html (ZIP-code lookup): ZCTA centroids with their county, and the coordinates of every recruiting-site
location ("site point") in the web payload. Nothing here is personal data; the page does all matching in the browser.

Sources: zcta_pop55.csv (Census ZCTA population centers, ACS 2023), zcta_county.csv (ZCTA -> county, the same file the
pipeline uses to assign sites to counties), sitepoints.csv (site-point coordinates from route_sites_us.py; order = DATA.SP).

Writes docs/find_data.js (window.FIND): {zcta: {"77030": [lat, lon, "48201"], ...}, sp: [[lat, lon, "48201"], ...], meta},
and docs/zip_county.json ({county: [its ZIP codes]}), which the map's search box loads the first time a ZIP code is typed.
Distances on the page are straight-line from the ZCTA center to the site point, multiplied by 1.20 — a rounded factor; the median
road / straight-line ratio measured on this project's highway network is 1.18 (10th–90th percentile 1.09–1.34), and the page quotes
the measured figure from route_log.json — and labelled as estimates.
"""
import json
from datetime import date
from pathlib import Path
import pandas as pd


def find(name):
    for d in [".", "data/ref", "out_adult55", "data/raw", "docs"]:
        p = Path(d) / name
        if p.exists(): return p
    raise FileNotFoundError(name)


def docs_dir():
    return Path("docs") if Path("docs").is_dir() and not Path("data.js").exists() else Path(".")


def main():
    D = json.loads(open(docs_dir() / "data.js", encoding="utf-8").read()[len("window.DATA="):].rstrip().rstrip(";"))
    counties = set(D["counties"])
    z = pd.read_csv(find("zcta_pop55.csv"), dtype={"zcta": str}); zc = pd.read_csv(find("zcta_county.csv"), dtype=str).drop_duplicates("zcta").set_index("zcta").county_fips
    # A ZIP that spans counties is labelled with the county where most of its residents 55+ live (zcta_county_parts.csv), not
    # the one holding most of its land: someone typing 49684 is far more likely in Traverse City than in rural Leelanau County.
    if Path(find("zcta_county.csv")).with_name("zcta_county_parts.csv").exists():
        pp = pd.read_csv(Path(find("zcta_county.csv")).with_name("zcta_county_parts.csv"), dtype={"zcta": str, "county_fips": str}); pp = pp[pp.pop55_share.notna()]
        zc = zc.copy(); zc.update(pp.sort_values("pop55_share", ascending=False).drop_duplicates("zcta").set_index("zcta").county_fips)
    # the map's search box uses the same ZIP -> county table (docs/zip_county.json: county -> its ZIP codes)
    by_county = {}
    for zip5, cf in sorted(zc.items()):
        if cf in counties: by_county.setdefault(cf, []).append(zip5)
    (docs_dir() / "zip_county.json").write_text(json.dumps(dict(sorted(by_county.items())), separators=(",", ":")), encoding="utf-8")
    z["county"] = z.zcta.map(zc); z = z[z.county.isin(counties) & z.lat.notna()]
    zcta = {r.zcta: [round(float(r.lat), 3), round(float(r.lon), 3), r.county] for r in z.itertuples()}
    sp = pd.read_csv(find("sitepoints.csv"), dtype={"county_fips": str}).sort_values("sp")
    assert list(sp.sp) == list(range(len(sp))) and len(sp) == len(D["SP"]), "sitepoints.csv must match DATA.SP one-to-one, in order"
    pts = [[round(float(r.lat), 3), round(float(r.lon), 3), r.county_fips] for r in sp.itertuples()]
    road_note = "median road-mile / straight-line ratio on this project's highway network"
    try:
        rr = json.load(open(find("route_log.json")))["road_over_straightline_ratio_broad"]; road_note += f" is {rr['median']:.2f}; 10th-90th percentile {rr['p10']:.2f}-{rr['p90']:.2f}"
    except Exception: pass
    out = {"meta": {"built": str(date.today()), "zctas": len(zcta), "sitepoints": len(pts), "road_factor": 1.2, "road_factor_note": road_note,
                    "registry_pull": D["meta"]["pull"], "trials": D["meta"]["trials"]}, "zcta": zcta, "sp": pts}
    s = json.dumps(out, separators=(",", ":")); (docs_dir() / "find_data.js").write_text("window.FIND=" + s + ";", encoding="utf-8")
    print("find_data.js KB", len(s) // 1024, "| ZCTAs", len(zcta), "| site points", len(pts))


if __name__ == "__main__":
    main()
