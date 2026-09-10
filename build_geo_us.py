"""National reference geography for the US trial access snapshot (all states + DC)."""
import csv, io, json, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests

REF = Path("data/ref"); REF.mkdir(parents=True, exist_ok=True)
U = {
 "zcta": "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt",
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


def main():
    s = requests.Session(); log = {"timestamp_utc": datetime.now(timezone.utc).isoformat()}

    r = s.get(U["zcta"], timeout=300); r.raise_for_status()
    best, zip3 = {}, defaultdict(Counter)
    for row in csv.DictReader(io.StringIO(r.text), delimiter="|"):
        c, z = row.get("GEOID_COUNTY_20") or "", row.get("GEOID_ZCTA5_20") or ""
        if not z or c[:2] not in KEEP_STATES: continue
        a = float(row.get("AREALAND_PART") or 0)
        if z not in best or a > best[z][1]: best[z] = (c, a)
    for z, (c, _) in best.items(): zip3[z[:3]][c] += 1
    w(REF / "zcta_county.csv", [{"zcta": z, "county_fips": c} for z, (c, _) in sorted(best.items())])
    w(REF / "zip3_county.csv", [{"zip3": k, "county_fips": v.most_common(1)[0][0]} for k, v in sorted(zip3.items())])
    log["zcta_rows"] = len(best)

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

    r = s.get(U["gaz"], timeout=300); r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content)); name = [n for n in zf.namelist() if n.endswith(".txt")][0]
    gaz = []
    for row in csv.DictReader(io.StringIO(zf.read(name).decode("utf-8-sig")), delimiter="\t"):
        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        nm = row["NAME"].lower()
        for suf in (" city", " town", " village", " cdp", " borough", " municipality", " (balance)", " consolidated government", " metro government", " urban county", " unified government", " metropolitan government"):
            if nm.endswith(suf): nm = nm[: -len(suf)]
        gaz.append({"state": row["USPS"], "place": nm, "geoid": row["GEOID"], "lat": float(row["INTPTLAT"]), "lon": float(row["INTPTLONG"])})
    w(REF / "gazetteer_places.csv", gaz); log["gazetteer_places"] = len(gaz)
    json.dump(log, open(REF / "ref_log.json", "w"), indent=2); print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
