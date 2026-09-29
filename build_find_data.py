"""Data for find.html (ZIP-code lookup): ZCTA centroids with their county, and the coordinates of every recruiting-site
location ("site point") in the web payload. Nothing here is personal data; the page does all matching in the browser.

Sources: zcta_pop55.csv (Census ZCTA population centers, ACS 2023), zcta_county.csv (ZCTA -> county, the same file the
pipeline uses to assign sites to counties), sitepoints.csv (site-point coordinates from route_sites_us.py; order = DATA.SP).

Writes docs/find_data.js (window.FIND): {zcta: {"77030": [lat, lon, "48201"], ...}, sp: [[lat, lon, "48201"], ...], meta}.
Distances on the page are straight-line from the ZCTA center to the site point, multiplied by 1.20 — the median road /
straight-line ratio measured on this project's highway network (10th–90th percentile 1.10–1.38) — and labelled as estimates.
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
    z["county"] = z.zcta.map(zc); z = z[z.county.isin(counties) & z.lat.notna()]
    zcta = {r.zcta: [round(float(r.lat), 3), round(float(r.lon), 3), r.county] for r in z.itertuples()}
    sp = pd.read_csv(find("sitepoints.csv"), dtype={"county_fips": str}).sort_values("sp")
    assert list(sp.sp) == list(range(len(sp))) and len(sp) == len(D["SP"]), "sitepoints.csv must match DATA.SP one-to-one, in order"
    pts = [[round(float(r.lat), 3), round(float(r.lon), 3), r.county_fips] for r in sp.itertuples()]
    out = {"meta": {"built": str(date.today()), "zctas": len(zcta), "sitepoints": len(pts), "road_factor": 1.2, "road_factor_note": "median road-mile / straight-line ratio on this project's highway network; 10th-90th percentile 1.10-1.38",
                    "registry_pull": D["meta"]["pull"], "trials": D["meta"]["trials"]}, "zcta": zcta, "sp": pts}
    s = json.dumps(out, separators=(",", ":")); (docs_dir() / "find_data.js").write_text("window.FIND=" + s + ";", encoding="utf-8")
    print("find_data.js KB", len(s) // 1024, "| ZCTAs", len(zcta), "| site points", len(pts))


if __name__ == "__main__":
    main()
