"""Oncologists and trials: where cancer specialists practise, set against where trials recruit (docs/oncologists.js).

The question it answers for a county: is there no trial because there is no oncologist, or are there oncologists and no trial? The second
group of counties is where a research program (an NCORP affiliate, a network site, a decentralized-trial partner) could open trials with
specialists already in place.

Source (fetch_oncologists.py, data/ref/oncologists_cms.csv): the CMS Doctors and Clinicians national file (Care Compare), one row per
clinician x practice location for clinicians enrolled in Medicare. The NPPES extract (data/ref/oncologists_nppes.csv) is the cross-check
and the taxonomy behind each CMS specialty.

Rules (each is reported in oncologists_log.json):
  Specialty   the clinician's CMS primary specialty decides the group. The headline group, "oncologists", is medical oncology,
              hematology/oncology and hematology: the definition of the ASCO workforce study that used the same file (Kirkwood et al., JCO
              Oncology Practice 2025: 14,547 in the March 2024 file), so the national figures can be checked against a published count.
              Radiation, gynecologic and surgical oncologists are counted separately and shown; a clinician whose oncology specialty is only
              secondary is logged, not counted.
  Location    every practice location is placed in a county by the rules used for trial sites (metrics_us.assign_sites: ZIP area, then
              where most of a ZIP's residents 55+ live, the city when the ZIP has no Census area). A clinician counts once in each county
              where CMS lists a location for them ("practising in the county"); nationally each clinician counts once.
  Pediatric   CMS files pediatric hematology-oncology under hematology/oncology; a clinician whose only oncology taxonomy in NPPES is
              pediatric (2080P0207X) is not counted.
  Shared      a county where every listed oncologist also lists a location in another county (a part-time or outreach clinic, likely).
  Trials      a county "has trials" when at least one trial on the map recruits at a site in it (data.js county t >= 1).
  Reach       oncologists within 60 road-miles: distinct clinicians with a location in any county whose center is within 60 road-miles
              (out_adult55/county_pairs_within_120rdmi.csv, the county-center road distances the map already uses).
Categories (county): 1 oncologists and trials, 2 oncologists but no trials, 3 trials but no oncologist listed, 4 neither.
Residents 55+ by category are summed from tracts (tract_access.csv) for the nation, states and districts (tract_cd119.csv shares).
Outputs: docs/oncologists.js (window.ONCOLOGISTS=), docs/oncologists_counties.csv (one row per county, for download), oncologists_build_log.json
"""
import json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; REF = ROOT / "data" / "ref"; OUT = ROOT / "out_adult55"; DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT))
from tier4_covering import USPS          # state FIPS -> USPS
from metrics_us import assign_sites      # the trial sites' county rules

GROUPS = {   # CMS primary specialty (upper case) -> group
    "MEDICAL ONCOLOGY": "onc", "HEMATOLOGY/ONCOLOGY": "onc", "HEMATOLOGY-ONCOLOGY": "onc", "HEMATOLOGY ONCOLOGY": "onc", "HEMATOLOGY": "onc",
    "HEMATOPOIETIC CELL TRANSPLANTATION AND CELLULAR THERAPY": "onc",   # a CMS specialty added in 2024 (transplant and CAR-T physicians)
    "RADIATION ONCOLOGY": "rad", "GYNECOLOGICAL ONCOLOGY": "gyn", "GYNECOLOGIC ONCOLOGY": "gyn", "SURGICAL ONCOLOGY": "surg",
}
SUBGROUP = {"MEDICAL ONCOLOGY": "medical", "HEMATOLOGY/ONCOLOGY": "hem_onc", "HEMATOLOGY-ONCOLOGY": "hem_onc", "HEMATOLOGY ONCOLOGY": "hem_onc", "HEMATOLOGY": "hematology", "HEMATOPOIETIC CELL TRANSPLANTATION AND CELLULAR THERAPY": "transplant"}
CAT_LABEL = {1: "Oncologists and trials", 2: "Oncologists, no trials", 3: "Trials, no oncologist listed", 4: "Neither"}
REACH_MI = 60.0


def read_js(path, prefix=None):
    s = Path(path).read_text(encoding="utf-8"); return json.loads(s.split("=", 1)[1].strip().rstrip(";"))


def place(df, cent):
    """County of each (city, state, ZIP) row by the trial-site rules. Returns the frame with county_fips and assign_method."""
    s2f = {v: k for k, v in USPS.items()}
    loc = df[["city", "state", "zip5"]].drop_duplicates().reset_index(drop=True)
    sites = pd.DataFrame({"facility": "", "zip": loc.zip5.fillna(""), "state": loc.state, "state_fips": loc.state.map(s2f).fillna(""),
                          "city": loc.city.fillna(""), "nct_id": [f"L{i}" for i in range(len(loc))]})
    a = assign_sites(sites, cent)
    loc["county_fips"] = a.county_fips.values; loc["assign_method"] = a.assign_method.values
    return df.merge(loc, on=["city", "state", "zip5"], how="left")


def main():
    log = {"rules": {"specialty": "CMS primary specialty", "groups": GROUPS, "reach_road_mi": REACH_MI, "categories": CAT_LABEL}}
    src = json.loads((REF / "oncologists_log.json").read_text())
    log["source"] = {"cms_url": src["cms"]["url"], "cms_modified": src["cms"].get("modified"), "pulled": src.get("pulled"),
                     "nppes_url": (src.get("nppes") or {}).get("url")}
    D = read_js(DOCS / "data.js"); C = D["counties"]
    cent = pd.read_csv(REF / "county_centroids.csv", dtype={"county_fips": str, "state_fips": str})

    cms = pd.read_csv(REF / "oncologists_cms.csv", dtype=str, keep_default_na=False)
    cms["group"] = cms.pri_spec.map(GROUPS); cms["sub"] = cms.pri_spec.map(SUBGROUP)
    sec_only = cms[cms.group.isna()].drop_duplicates("npi")
    log["secondary_only"] = {"clinicians": int(len(sec_only)), "primary_specialties": sec_only.pri_spec.value_counts().head(15).to_dict(),
                             "note": "oncology or hematology is a secondary specialty only; not counted"}
    other = cms[cms.group.isna() & cms.pri_spec.str.contains("ONCOL|HEMATOL")].pri_spec.value_counts().to_dict()
    if other: log["unmapped_oncology_specialties"] = other   # a CMS label not in GROUPS: review and add (validate_extras.py fails on it)
    cms = cms[cms.group.notna()].copy()
    cms = place(cms, cent)
    rows = len(cms); un = cms[cms.county_fips.isna()]
    log["placement"] = {"location_rows": rows, "methods": cms.assign_method.value_counts().to_dict(), "unplaced_rows": int(len(un)),
                        "unplaced_clinicians_with_no_placed_location": int(len(set(un.npi) - set(cms[cms.county_fips.notna()].npi))),
                        "unplaced_examples": un[["city", "state", "zip5"]].drop_duplicates().head(15).values.tolist()}
    cms = cms[cms.county_fips.notna() & cms.county_fips.isin(C)]
    # Connecticut: data.js uses the 8 legacy counties; assign_sites returns them (zcta_county.csv is built on the legacy counties).
    # The ASCO-comparable count, before the pediatric rule below (Kirkwood et al. 2025 counted CMS hematology/oncology, medical oncology
    # and hematology without it): validate_extras.py compares this, and the share of counties with one, with the published figures.
    a = cms[cms.group == "onc"]; log["asco_comparable"] = {"clinicians": int(a.npi.nunique()), "counties_with_one": int(a.county_fips.nunique()),
        "excluding_transplant": int(a[a.pri_spec != "HEMATOPOIETIC CELL TRANSPLANTATION AND CELLULAR THERAPY"].npi.nunique())}
    # CMS files pediatric hematology-oncology under HEMATOLOGY/ONCOLOGY. A clinician whose only oncology or hematology taxonomy in NPPES is
    # pediatric (2080P0207X) treats children: not counted on a map of adults 55+ (544 in the October 2026 files).
    if (REF / "oncologists_nppes.csv").exists():
        npp = pd.read_csv(REF / "oncologists_nppes.csv", dtype=str, keep_default_na=False)
        adult = npp.codes.str.contains("207RX0202X|207RH0003X|207RH0000X"); peds = set(npp[npp.codes.str.contains("2080P0207X") & ~adult].npi)
        drop = cms.group.eq("onc") & cms.npi.isin(peds)
        log["pediatric_excluded"] = {"clinicians": int(cms[drop].npi.nunique()), "rule": "NPPES taxonomy 2080P0207X and no adult oncology/hematology taxonomy"}
        cms = cms[~drop]
        log["nppes_check"] = {"cms_oncologists_with_nppes_row": int(cms[cms.group == "onc"].drop_duplicates("npi").npi.isin(set(npp.npi)).sum()),
                              "cms_oncologists": int(cms[cms.group == "onc"].npi.nunique())}
    npi_group = cms.drop_duplicates("npi").set_index("npi").group
    log["clinicians"] = {g: int((npi_group == g).sum()) for g in ("onc", "rad", "gyn", "surg")}
    log["clinicians_onc_by_specialty"] = cms[cms.group == "onc"].drop_duplicates("npi").pri_spec.value_counts().to_dict()
    ncounties = cms.groupby("npi").county_fips.nunique()
    log["counties_per_clinician"] = {"median": float(ncounties.median()), "p90": float(ncounties.quantile(.9)), "max": int(ncounties.max()),
                                     "share_in_1_county": round(float((ncounties == 1).mean()), 3)}

    # A clinician listed in this county only, or also elsewhere. (NPPES's single practice address was tried as a "base county" and dropped:
    # for 17% of oncologists it is a county where CMS lists no location for them, often a group's head office, which marked Hawaii County,
    # with 13 oncologists, as served from Honolulu.)
    only_here = cms[cms.group == "onc"].groupby("npi").county_fips.nunique().eq(1)

    pres = cms.groupby(["county_fips", "group"]).npi.apply(set)
    onc_sets = {f: pres.get((f, "onc"), set()) for f in C}
    pairs = pd.read_csv(OUT / "county_pairs_within_120rdmi.csv", dtype={"trial_county_fips": str, "county_fips": str})
    pairs = pairs[pairs.road_mi <= REACH_MI]
    near = pairs.groupby("county_fips").trial_county_fips.apply(list).to_dict()

    county, rows_out = {}, []
    for f, c in C.items():
        on = onc_sets[f]; n_on = len(on)
        n_rad = len(pres.get((f, "rad"), set())); n_gyn = len(pres.get((f, "gyn"), set())); n_surg = len(pres.get((f, "surg"), set()))
        n_only = sum(1 for k in on if only_here.get(k, False))
        reach = set().union(*[onc_sets.get(g, set()) for g in near.get(f, [f])]) if near.get(f) else set(on)
        t = int(c["t"]); cat = 1 if n_on and t else 2 if n_on else 3 if t else 4
        shared = int(bool(n_on) and n_only == 0)   # every oncologist listed here also lists a location in another county
        county[f] = [n_on, n_only, n_rad, n_gyn, n_surg, len(reach), cat, shared]
        rows_out.append({"county_fips": f, "county": c["nl"], "state": USPS.get(c["s"], c["s"]), "residents_55plus": c["p"], "oncologists": n_on,
                         "oncologists_listed_only_here": n_only, "all_also_practise_elsewhere": shared, "radiation_oncologists": n_rad, "gynecologic_oncologists": n_gyn,
                         "surgical_oncologists": n_surg, "oncologists_within_60_road_mi": len(reach), "trials_in_county": t,
                         "trials_within_60_road_mi": int(c.get("t60", 0)), "category": CAT_LABEL[cat],
                         "residents_55plus_per_oncologist": round(c["p"] / n_on) if n_on else ""})
    ordr = {v: k for k, v in CAT_LABEL.items()}   # the map's order: oncologists and trials, oncologists but no trials, ...; largest counties first
    pd.DataFrame(rows_out).sort_values(["category", "residents_55plus"], key=lambda x: x.map(ordr) if x.name == "category" else x, ascending=[True, False]).to_csv(DOCS / "oncologists_counties.csv", index=False)

    # residents 55+ by category: tracts -> nation, states, districts
    tr = pd.read_csv(OUT / "tract_access.csv", dtype={"tract": str, "county_fips": str}, usecols=["tract", "county_fips", "pop55"])
    tr["cat"] = tr.county_fips.map(lambda f: county[f][6]); tr["vis"] = tr.county_fips.map(lambda f: county[f][7])
    tr["st"] = tr.county_fips.str[:2].map(USPS)

    def summ(g, w):
        p = float((g.pop55 * w).sum()); out = {"p": int(round(p))}
        for k in (1, 2, 3, 4): out[f"c{k}"] = round(100 * float((g.pop55 * w)[g.cat == k].sum()) / p, 1) if p else 0.0
        out["vis"] = round(100 * float((g.pop55 * w)[g.vis == 1].sum()) / p, 1) if p else 0.0
        return out
    one = pd.Series(1.0, index=tr.index)
    nat = summ(tr, one)
    nat.update({"onc": log["clinicians"]["onc"], "rad": log["clinicians"]["rad"], "gyn": log["clinicians"]["gyn"], "surg": log["clinicians"]["surg"],
                "per100k": round(100000 * log["clinicians"]["onc"] / nat["p"], 1),
                "counties": {str(k): sum(1 for v in county.values() if v[6] == k) for k in (1, 2, 3, 4)},
                "counties_with_onc": sum(1 for v in county.values() if v[0]), "counties_all_shared": sum(v[7] for v in county.values())})
    states = {}
    for st, g in tr.groupby("st"):
        s = summ(g, one.loc[g.index]); fs = [f for f in C if USPS.get(C[f]["s"]) == st]
        s["onc"] = len(set().union(*[onc_sets[f] for f in fs])); s["per100k"] = round(100000 * s["onc"] / s["p"], 1) if s["p"] else 0.0
        s["c2_counties"] = sum(1 for f in fs if county[f][6] == 2); states[st] = s
    rel = pd.read_csv(REF / "tract_cd119.csv", dtype={"tract": str, "cd_geoid": str}); rel["share"] = rel.share.astype(float)
    tm = rel.merge(tr, on="tract")
    districts = {}
    for cd, g in tm.groupby("cd_geoid"):
        s = summ(g, g.share); fs = sorted(set(g.county_fips))
        s["onc"] = len(set().union(*[onc_sets[f] for f in fs])) if fs else 0
        s["c2_counties"] = [f for f in fs if county[f][6] == 2]; districts[cd] = s
    out = {"meta": {"built": pd.Timestamp.now("UTC").strftime("%Y-%m-%d"), "source": "CMS Doctors and Clinicians national file (Care Compare)",
                    "source_modified": log["source"]["cms_modified"], "pulled": log["source"]["pulled"], "fields": ["onc", "onc_only_here", "rad", "gyn", "surg",
                    "onc_within_60rdmi", "cat", "all_also_elsewhere"], "categories": CAT_LABEL, "reach_road_mi": REACH_MI,
                    "definition": "Oncologists: CMS primary specialty medical oncology, hematology/oncology or hematology, at any Medicare practice location in the county."},
           "county": county, "nat": nat, "states": states, "districts": districts}
    (DOCS / "oncologists.js").write_text("window.ONCOLOGISTS=" + json.dumps(out, separators=(",", ":")) + ";", encoding="utf-8")
    log["nat"] = nat; (ROOT / "oncologists_build_log.json").write_text(json.dumps(log, indent=1))
    print(f"oncologists {nat['onc']:,} (rad {nat['rad']:,}, gyn {nat['gyn']:,}, surg {nat['surg']:,}); counties with one {nat['counties_with_onc']:,} of {len(C):,}; "
          f"residents 55+: both {nat['c1']}%, oncologists no trials {nat['c2']}%, trials no oncologist {nat['c3']}%, neither {nat['c4']}%; "
          f"counties by category {nat['counties']}; all oncologists also elsewhere {nat['counties_all_shared']}")


if __name__ == "__main__":
    main()
