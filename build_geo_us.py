"""National reference geography for the US trial access snapshot (all states + DC)."""
import csv, io, json, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests

REF = Path("data/ref"); REF.mkdir(parents=True, exist_ok=True)
U = {
 "zcta": "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt",
 "zcta_tract": "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_tract20_natl.txt",
 "cenpop": "https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt",
 "acs": "https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-b01001.dat",
 "cd": "https://www2.census.gov/geo/docs/maps-data/data/rel2020/cd-sld/tab20_cd11920_county20_natl.txt",
 "gaz": "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_place_national.zip",
}
ACS_55 = [f"B01001_E{i:03d}" for i in list(range(17, 26)) + list(range(41, 50))]
KEEP_STATES = {f"{i:02d}" for i in range(1, 57)} - {"03", "07", "14", "43", "52"}  # 50 states + DC


def w(path, rows):
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)


# legal suffixes stripped from Census place names, compound ones first: "Juneau city and borough" -> Juneau (not "Juneau city and"),
# "Indianapolis city (balance)" -> Indianapolis, "Nashville-Davidson metropolitan government (balance)" -> Nashville-Davidson
PLACE_SUFFIXES = (" city and borough", " municipality and borough", " city (balance)", " city", " town", " village", " cdp", " borough", " municipality", " (balance)", " consolidated government", " metro government", " urban county", " unified government", " metropolitan government")


def build_gazetteer(s=None):
    """Census Gazetteer places -> data/ref/gazetteer_places.csv. `place` is the lower-case matching key (used to place registry sites
    by city name); `name` is the same name as the Census writes it, for display in the map's search box; `aland_sqmi` (land area)
    lets build_places.py estimate how big a place is. The legal suffix ("city", "town", "CDP", ...) is removed from both names."""
    s = s or requests.Session(); r = s.get(U["gaz"], timeout=300); r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content)); name = [n for n in zf.namelist() if n.endswith(".txt")][0]
    gaz = []
    for row in csv.DictReader(io.StringIO(zf.read(name).decode("utf-8-sig")), delimiter="\t"):
        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        disp = row["NAME"]; nm = disp.lower()
        for suf in PLACE_SUFFIXES:   # in order, each at most once: a compound suffix is listed before its parts
            if nm.endswith(suf): nm = nm[: -len(suf)]; disp = disp[: len(nm)]
        gaz.append({"state": row["USPS"], "place": nm, "geoid": row["GEOID"], "lat": float(row["INTPTLAT"]), "lon": float(row["INTPTLONG"]), "name": disp, "aland_sqmi": float(row.get("ALAND_SQMI") or 0)})
    w(REF / "gazetteer_places.csv", gaz); return len(gaz)


def build_zcta_county(s=None):
    """Census 2020 ZCTA-county relationship file -> zcta_county.csv (each ZIP's county = the one holding most of its land area)
    and zip3_county.csv, both unchanged in format, plus zcta_land_area.csv (square miles of each ZIP) and zcta_county_parts.csv
    for the ZIPs that span more than one county: every county the ZIP touches with its share of the ZIP's land area and of its
    residents 55+.

    The resident share comes from the Census 2020 ZCTA-tract relationship file: each tract's residents 55+ (tracts_us.csv, written
    by build_tracts_us.py) are split in proportion to the tract's land area inside the ZIP. Land area alone picks the wrong county
    where a town sits on the edge of a large rural ZIP (ZIP 49684 is 61% Leelanau County by land, but two-thirds of its older
    residents - and the hospital - are in Traverse City, Grand Traverse County; ZIP 99701 is 97% Yukon-Koyukuk by land and
    100% Fairbanks by residents). metrics_us.py and build_find_data.py read the parts file. Run again with --zcta-only after
    build_tracts_us.py if tracts_us.csv did not exist yet (the resident share is left blank without it)."""
    s = s or requests.Session(); r = s.get(U["zcta"], timeout=300); r.raise_for_status()
    best, zip3, parts, zarea = {}, defaultdict(Counter), defaultdict(dict), {}
    for row in csv.DictReader(io.StringIO(r.text), delimiter="|"):
        c, z = row.get("GEOID_COUNTY_20") or "", row.get("GEOID_ZCTA5_20") or ""
        if not z or c[:2] not in KEEP_STATES: continue
        a = float(row.get("AREALAND_PART") or 0); parts[z][c] = parts[z].get(c, 0.0) + a
        zarea[z] = float(row.get("AREALAND_ZCTA5_20") or 0) / 2589988.11
        if z not in best or a > best[z][1]: best[z] = (c, a)
    for z, (c, _) in best.items(): zip3[z[:3]][c] += 1
    w(REF / "zcta_land_area.csv", [{"zcta": z, "land_sqmi": round(a, 2)} for z, a in sorted(zarea.items())])   # used by tier4_covering.SiteLocator
    w(REF / "zcta_county.csv", [{"zcta": z, "county_fips": c} for z, (c, _) in sorted(best.items())])
    w(REF / "zip3_county.csv", [{"zip3": k, "county_fips": v.most_common(1)[0][0]} for k, v in sorted(zip3.items())])
    pop = defaultdict(dict)                                                  # zcta -> county -> residents 55+ (areal share of each tract)
    if (REF / "tracts_us.csv").exists():
        tpop = {row["tract"]: float(row["pop55"] or 0) for row in csv.DictReader(open(REF / "tracts_us.csv"))}
        r = s.get(U["zcta_tract"], timeout=600); r.raise_for_status()
        for row in csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter="|"):
            z, t = row.get("GEOID_ZCTA5_20") or "", row.get("GEOID_TRACT_20") or ""
            at = float(row.get("AREALAND_TRACT_20") or 0)
            if not z or t[:2] not in KEEP_STATES or at <= 0 or t not in tpop: continue
            pop[z][t[:5]] = pop[z].get(t[:5], 0.0) + tpop[t] * float(row.get("AREALAND_PART") or 0) / at
    multi, n_diff = [], 0
    for z, d in sorted(parts.items()):
        tot = sum(d.values()); ptot = sum(pop[z].values()) if z in pop else 0
        if len(d) < 2 or tot <= 0: continue
        rows = [{"zcta": z, "county_fips": c, "land_share": round(a / tot, 4), "pop55_share": (round(pop[z].get(c, 0.0) / ptot, 4) if ptot > 0 else "")} for c, a in sorted(d.items(), key=lambda x: -x[1])]
        rows = [x for x in rows if x["land_share"] >= 0.005 or (x["pop55_share"] != "" and x["pop55_share"] >= 0.005)]
        if ptot > 0 and max(rows, key=lambda x: x["pop55_share"])["county_fips"] != best[z][0]: n_diff += 1
        multi += rows
    w(REF / "zcta_county_parts.csv", multi)
    return {"zcta_rows": len(best), "zcta_multi_county": len({m["zcta"] for m in multi}), "zcta_resident_majority_differs_from_land_majority": n_diff,
            "zcta_resident_share_source": "Census 2020 ZCTA-tract relationship file x tracts_us.csv pop55" if pop else "not computed (tracts_us.csv missing)"}


def main():
    s = requests.Session(); log = {"timestamp_utc": datetime.now(timezone.utc).isoformat()}

    log.update(build_zcta_county(s))

    r = s.get(U["cenpop"], timeout=120); r.raise_for_status()
    rows = [{"county_fips": f"{x['STATEFP']}{x['COUNTYFP']}", "state_fips": x["STATEFP"], "county_name": x["COUNAME"], "state_name": x["STNAME"],
             "lat": float(x["LATITUDE"]), "lon": float(x["LONGITUDE"]), "pop2020": int(x["POPULATION"])}
            for x in csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))) if x["STATEFP"] in KEEP_STATES]
    w(REF / "county_centroids.csv", rows); log["counties"] = len(rows)

    out, hdr = [], None
    with s.get(U["acs"], stream=True, timeout=900) as r:
        r.raise_for_status(); r.encoding = "utf-8"
        for line in r.iter_lines(decode_unicode=True):
            if not line: continue
            if hdr is None: hdr = line.split("|"); idx = {h: i for i, h in enumerate(hdr)}; continue
            if not line.startswith("0500000US"): continue
            row = line.split("|"); fips = row[0][-5:]
            if fips[:2] not in KEEP_STATES: continue
            out.append({"county_fips": fips, "pop55": sum(int(row[idx[v]] or 0) for v in ACS_55)})
    w(REF / "county_pop55.csv", sorted(out, key=lambda d: d["county_fips"])); log["county_pop55"] = len(out)

    r = s.get(U["cd"], timeout=300); r.raise_for_status()
    parts = defaultdict(lambda: defaultdict(float))
    rows_ = list(csv.DictReader(io.StringIO(r.text), delimiter="|"))
    cdk = next(k for k in rows_[0] if k.startswith("GEOID_CD"))
    for row in rows_:
        c = row.get("GEOID_COUNTY_20") or ""
        if c[:2] not in KEEP_STATES: continue
        cd = row.get(cdk) or ""
        if not cd or cd.endswith("ZZ"): continue
        parts[c][cd] += float(row.get("AREALAND_PART") or 0)
    cdrows = []
    for c, d in parts.items():
        tot = sum(d.values()) or 1
        for cd, a in d.items():
            cdrows.append({"county_fips": c, "cd_geoid": cd, "state_fips": cd[:2], "cd": cd[2:], "share": round(a / tot, 4)})
    w(REF / "county_cd.csv", cdrows); log["county_cd_rows"] = len(cdrows); log["cd_source"] = "census_area_overlap_proxy_cd119"

    log["gazetteer_places"] = build_gazetteer(s)
    json.dump(log, open(REF / "ref_log.json", "w"), indent=2); print(json.dumps(log, indent=2))


if __name__ == "__main__":
    import sys
    if "--gazetteer-only" in sys.argv: print("gazetteer places:", build_gazetteer())       # refresh one reference file without the rest
    elif "--zcta-only" in sys.argv: print(build_zcta_county())
    else: main()
