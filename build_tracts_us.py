"""Tier 2.2 (part 1) — national census-tract reference: population 55+ (ACS 2023 5-yr B01001), internal-point
centroids (2024 Gazetteer), and the Census 2020 tract -> 119th Congressional District relationship file.

Outputs
  data/ref/tracts_us.csv       tract (11-digit 2020 GEOID, legacy-county form for Connecticut), county_fips, lat, lon, pop55
  data/ref/tract_cd119.csv     tract, cd_geoid, share (land-area share of the tract inside the district; ZZ = unassigned water dropped)
  data/ref/county_pop55.csv    rewritten: Connecticut's 8 legacy counties now = sum of ACS 2023 tract pop 55+ (was 2021 PEP)
  data/ref/tract_ref_log.json

Connecticut: ACS 2023 and the 2024 gazetteer key CT tracts by planning region (county codes 091xx); the 2020 relationship
file keys them by legacy county (090xx). The 6-digit tract code is unchanged, so tracts are re-keyed to the legacy form
through the relationship file (the mapping is checked to be one-to-one before use).
"""
import io, json, zipfile
from pathlib import Path
import numpy as np, pandas as pd, requests

REF = Path("data/ref")
ACS = "https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-b01001.dat"
GAZ = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_tracts_national.zip"
REL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/cd-sld/tab20_cd11920_tract20_natl.txt"
AGE55 = [f"B01001_E{i:03d}" for i in list(range(17, 26)) + list(range(41, 50))]
KEEP = {f"{i:02d}" for i in range(1, 57)} - {"03", "07", "14", "43", "52"}
s = requests.Session()


def main():
    log = {}
    # --- tract pop 55+ (stream the 200 MB national table, keep tract rows) ---
    if not (REF / "tract_pop55_us.csv").exists():
        rows, hdr = [], None
        with s.get(ACS, stream=True, timeout=1800) as r:
            r.raise_for_status(); r.encoding = "utf-8"
            for line in r.iter_lines(decode_unicode=True):
                if not line: continue
                if hdr is None: hdr = line.split("|"); idx = {h: i for i, h in enumerate(hdr)}; continue
                if not line.startswith("1400000US"): continue
                p = line.split("|"); g = p[0][-11:]
                if g[:2] not in KEEP: continue
                rows.append({"tract_acs": g, "pop55": sum(int(p[idx[v]] or 0) for v in AGE55)})
        pd.DataFrame(rows).to_csv(REF / "tract_pop55_us.csv", index=False)
    tp = pd.read_csv(REF / "tract_pop55_us.csv", dtype={"tract_acs": str})
    # --- centroids ---
    z = zipfile.ZipFile(io.BytesIO(s.get(GAZ, timeout=600).content)); name = [n for n in z.namelist() if n.endswith(".txt")][0]
    gz = pd.read_csv(io.BytesIO(z.read(name)), sep="\t", dtype={"GEOID": str}); gz.columns = [c.strip() for c in gz.columns]
    gz = gz.rename(columns={"GEOID": "tract_acs", "INTPTLAT": "lat", "INTPTLONG": "lon"})[["tract_acs", "lat", "lon"]]
    gz = gz[gz.tract_acs.str[:2].isin(KEEP)]
    # --- tract -> CD119 relationship (2020 tract GEOIDs) ---
    rel = pd.read_csv(io.StringIO(s.get(REL, timeout=600).text), sep="|", dtype=str, encoding="utf-8-sig")
    rel = rel[rel.GEOID_TRACT_20.str[:2].isin(KEEP)]
    rel = rel[~rel.GEOID_CD119_20.str.endswith("ZZ")].copy()
    rel["AREALAND_PART"] = rel.AREALAND_PART.astype(float); rel["AREALAND_TRACT_20"] = rel.AREALAND_TRACT_20.astype(float)
    # share = land-area part / total land of the tract *within assigned districts* (so shares sum to exactly 1 per tract)
    tot = rel.groupby("GEOID_TRACT_20").AREALAND_PART.transform("sum")
    rel["share"] = np.where(tot > 0, rel.AREALAND_PART / tot.replace(0, np.nan), np.nan)
    # zero-land tracts (all water): split equally among the districts listed
    nz = rel.groupby("GEOID_TRACT_20").GEOID_CD119_20.transform("count"); rel["share"] = rel.share.fillna(1.0 / nz)
    rel = rel.rename(columns={"GEOID_TRACT_20": "tract", "GEOID_CD119_20": "cd_geoid"})[["tract", "cd_geoid", "share"]]
    # --- Connecticut re-key: planning-region tract id -> legacy-county tract id via 6-digit tract code ---
    ct_rel = rel[rel.tract.str[:2] == "09"].tract.unique()
    m6 = pd.Series({t[5:]: t for t in ct_rel})
    assert m6.index.is_unique, "CT 6-digit tract codes are not unique statewide; need a different crosswalk"
    def rekey(t): return m6.get(t[5:], None) if t[:2] == "09" else t
    tp["tract"] = tp.tract_acs.map(rekey); gz["tract"] = gz.tract_acs.map(rekey)
    log["ct_tracts_acs"] = int((tp.tract_acs.str[:2] == "09").sum()); log["ct_tracts_rekeyed"] = int(tp[tp.tract_acs.str[:2] == "09"].tract.notna().sum())
    tp = tp.dropna(subset=["tract"]); gz = gz.dropna(subset=["tract"])
    tp = tp.drop_duplicates("tract"); gz = gz.drop_duplicates("tract")  # CT all-water tracts "990000" collapse to one legacy id (pop 0)
    tr = gz.merge(tp[["tract", "pop55"]], on="tract", how="inner"); tr["county_fips"] = tr.tract.str[:5]
    tr = tr[["tract", "county_fips", "lat", "lon", "pop55"]].sort_values("tract").reset_index(drop=True)
    rel[rel.tract.isin(set(tr.tract))].to_csv(REF / "tract_cd119.csv", index=False)
    log.update({"tracts_with_pop_and_centroid": len(tr), "tracts_acs_total": len(tp), "tracts_gazetteer": len(gz), "tract_pop55_total": int(tr.pop55.sum()),
                "tract_cd_rows": int(rel.tract.isin(set(tr.tract)).sum()), "tracts_without_cd_row": int((~tr.tract.isin(set(rel.tract))).sum()),
                "cd_count": int(rel.cd_geoid.nunique())})
    # --- county pop55: replace Connecticut with ACS-2023 tract sums on legacy counties ---
    cp = pd.read_csv(REF / "county_pop55.csv", dtype={"county_fips": str})
    ct_old = cp[cp.county_fips.str[:2] == "09"].set_index("county_fips").pop55.to_dict()
    ct_new = tr[tr.county_fips.str[:2] == "09"].groupby("county_fips").pop55.sum()
    cp = cp[cp.county_fips.str[:2] != "09"]
    cp = pd.concat([cp, pd.DataFrame({"county_fips": ct_new.index, "pop55": ct_new.values})], ignore_index=True).sort_values("county_fips")
    cp.to_csv(REF / "county_pop55.csv", index=False)
    log["connecticut_pop55_old_pep2021"] = ct_old; log["connecticut_pop55_new_acs2023_tract_sum"] = {k: int(v) for k, v in ct_new.items()}
    # --- reconciliation: tract sums vs county ACS (must be exact outside CT; CT is exact by construction) ---
    cs = tr.groupby("county_fips").pop55.sum(); cpi = cp.set_index("county_fips").pop55
    diff = (cs.reindex(cpi.index).fillna(0) - cpi)
    log["counties_with_tract_sum_mismatch_before_raking"] = int((diff != 0).sum())
    log["mismatch_before_raking"] = {k: {"tract_sum": int(cs.get(k, 0)), "county_acs": int(cpi[k]), "diff": int(v)} for k, v in diff[diff != 0].items()}
    # Known source inconsistency (ACS 2023 publishes fewer tracts than the 2020 geography in Suffolk and Ulster NY; the absent
    # tracts' residents are in no tract row). Rake those counties' tract populations to the county total so district weights
    # sum to the county ACS figure; assumes the unlocated residents are distributed like the located ones. Factor is logged.
    log["raking_factors"] = {}
    for k, v in diff[diff != 0].items():
        if cs.get(k, 0) > 0:
            f = cpi[k] / cs[k]; m = tr.county_fips == k
            raked = np.floor(tr.loc[m, "pop55"] * f).astype(int); short = int(cpi[k] - raked.sum())
            idx = raked.sort_values(ascending=False).index[:short]; raked.loc[idx] += 1  # largest-remainder fix so the sum is exact
            tr.loc[m, "pop55"] = raked; log["raking_factors"][k] = round(float(f), 5)
    tr.to_csv(REF / "tracts_us.csv", index=False)
    cs = tr.groupby("county_fips").pop55.sum(); diff = (cs.reindex(cpi.index).fillna(0) - cpi)
    log["counties_with_tract_sum_mismatch_after_raking"] = int((diff != 0).sum()); log["tract_pop55_total_after_raking"] = int(tr.pop55.sum())
    log["pop_of_tracts_without_cd_row"] = int(tr[~tr.tract.isin(set(rel.tract))].pop55.sum())
    json.dump(log, open(REF / "tract_ref_log.json", "w"), indent=2); print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
