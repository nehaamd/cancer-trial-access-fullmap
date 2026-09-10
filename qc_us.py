"""National QC pass: NCI treating centers with coordinates, rule-based non-oncology exclusion,
three-way oral route classification, age caps. Rewrites data/raw/trials.csv (keeps trials_raw.csv)."""
import csv, json, re, shutil
from pathlib import Path
import pandas as pd
import config

RAW, REF, OUT = Path("data/raw"), Path("data/ref"), Path("out")

# --- NCI-designated treating centers (Comprehensive + Clinical), cancer.gov list updated 2026-06-10 ---
NCI = [
 ("O'Neal Comprehensive Cancer Center (UAB)", "birmingham", "AL", "Comprehensive"),
 ("University of Arizona Cancer Center", "tucson", "AZ", "Comprehensive"), ("Mayo Clinic Cancer Center – Phoenix", "phoenix", "AZ", "Comprehensive"),
 ("Chao Family Comprehensive Cancer Center (UC Irvine)", "orange", "CA", "Comprehensive"), ("City of Hope", "duarte", "CA", "Comprehensive"),
 ("Jonsson Comprehensive Cancer Center (UCLA)", "los angeles", "CA", "Comprehensive"), ("Stanford Cancer Institute", "stanford", "CA", "Comprehensive"),
 ("UC Davis Comprehensive Cancer Center", "sacramento", "CA", "Comprehensive"), ("Moores Comprehensive Cancer Center (UCSD)", "la jolla", "CA", "Comprehensive"),
 ("UCSF Helen Diller Family Comprehensive Cancer Center", "san francisco", "CA", "Comprehensive"), ("USC Norris Comprehensive Cancer Center", "los angeles", "CA", "Comprehensive"),
 ("University of Colorado Cancer Center", "aurora", "CO", "Comprehensive"), ("Yale Cancer Center", "new haven", "CT", "Comprehensive"),
 ("Georgetown Lombardi Comprehensive Cancer Center", "washington", "DC", "Comprehensive"),
 ("Mayo Clinic Cancer Center – Jacksonville", "jacksonville", "FL", "Comprehensive"), ("Sylvester Comprehensive Cancer Center (Miami)", "miami", "FL", "Clinical"),
 ("Moffitt Cancer Center", "tampa", "FL", "Comprehensive"), ("University of Florida Health Cancer Institute", "gainesville", "FL", "Clinical"),
 ("Winship Cancer Institute (Emory)", "atlanta", "GA", "Comprehensive"), ("University of Hawai'i Cancer Center", "urban honolulu", "HI", "Clinical"),
 ("Robert H. Lurie Comprehensive Cancer Center (Northwestern)", "chicago", "IL", "Comprehensive"), ("University of Chicago Comprehensive Cancer Center", "chicago", "IL", "Comprehensive"),
 ("IU Simon Comprehensive Cancer Center", "indianapolis city", "IN", "Comprehensive"), ("Holden Comprehensive Cancer Center (Iowa)", "iowa city", "IA", "Comprehensive"),
 ("University of Kansas Cancer Center", "kansas city", "KS", "Comprehensive"), ("Markey Cancer Center (Kentucky)", "lexington-fayette", "KY", "Comprehensive"),
 ("Sidney Kimmel Comprehensive Cancer Center (Johns Hopkins)", "baltimore", "MD", "Comprehensive"), ("UM Greenebaum Comprehensive Cancer Center", "baltimore", "MD", "Comprehensive"),
 ("Dana-Farber/Harvard Cancer Center", "boston", "MA", "Comprehensive"),
 ("Karmanos Cancer Institute (Wayne State)", "detroit", "MI", "Comprehensive"), ("University of Michigan Rogel Cancer Center", "ann arbor", "MI", "Comprehensive"),
 ("Masonic Cancer Center (Minnesota)", "minneapolis", "MN", "Comprehensive"), ("Mayo Clinic Cancer Center – Rochester", "rochester", "MN", "Comprehensive"),
 ("Siteman Cancer Center (WashU)", "st. louis", "MO", "Comprehensive"), ("Fred & Pamela Buffett Cancer Center (UNMC)", "omaha", "NE", "Clinical"),
 ("Dartmouth Cancer Center", "lebanon", "NH", "Comprehensive"), ("Rutgers Cancer Institute of New Jersey", "new brunswick", "NJ", "Comprehensive"),
 ("UNM Comprehensive Cancer Center", "albuquerque", "NM", "Comprehensive"),
 ("Montefiore Einstein Cancer Center", "bronx", "NY", "Comprehensive"), ("Herbert Irving Comprehensive Cancer Center (Columbia)", "manhattan", "NY", "Comprehensive"),
 ("Perlmutter Cancer Center (NYU Langone)", "manhattan", "NY", "Comprehensive"), ("Memorial Sloan Kettering Cancer Center", "manhattan", "NY", "Comprehensive"),
 ("Roswell Park Comprehensive Cancer Center", "buffalo", "NY", "Comprehensive"), ("Mount Sinai Tisch Cancer Center", "manhattan", "NY", "Clinical"),
 ("Wilmot Cancer Institute (Rochester)", "rochester", "NY", "Clinical"),
 ("Duke Cancer Institute", "durham", "NC", "Comprehensive"), ("UNC Lineberger Comprehensive Cancer Center", "chapel hill", "NC", "Comprehensive"),
 ("Wake Forest Baptist Comprehensive Cancer Center", "winston-salem", "NC", "Comprehensive"),
 ("Case Comprehensive Cancer Center", "cleveland", "OH", "Comprehensive"), ("OSU Comprehensive Cancer Center – James", "columbus", "OH", "Comprehensive"),
 ("Stephenson Cancer Center (Oklahoma)", "oklahoma city", "OK", "Clinical"), ("Knight Cancer Institute (OHSU)", "portland", "OR", "Comprehensive"),
 ("Abramson Cancer Center (Penn)", "philadelphia", "PA", "Comprehensive"), ("Fox Chase Cancer Center", "philadelphia", "PA", "Comprehensive"),
 ("Sidney Kimmel Cancer Center (Jefferson)", "philadelphia", "PA", "Comprehensive"), ("UPMC Hillman Cancer Center", "pittsburgh", "PA", "Comprehensive"),
 ("Hollings Cancer Center (MUSC)", "charleston", "SC", "Clinical"),
 ("St. Jude Children's Research Hospital", "memphis", "TN", "Comprehensive"), ("Vanderbilt-Ingram Cancer Center", "nashville-davidson", "TN", "Comprehensive"),
 ("Dan L Duncan Comprehensive Cancer Center (Baylor)", "houston", "TX", "Comprehensive"), ("Harold C. Simmons Comprehensive Cancer Center (UTSW)", "dallas", "TX", "Comprehensive"),
 ("Mays Cancer Center (UT Health San Antonio)", "san antonio", "TX", "Clinical"), ("MD Anderson Cancer Center", "houston", "TX", "Comprehensive"),
 ("Huntsman Cancer Institute (Utah)", "salt lake city", "UT", "Comprehensive"),
 ("VCU Massey Comprehensive Cancer Center", "richmond", "VA", "Comprehensive"), ("University of Virginia Cancer Center", "charlottesville", "VA", "Comprehensive"),
 ("Fred Hutch/UW/Seattle Children's Cancer Consortium", "seattle", "WA", "Comprehensive"), ("UW Carbone Cancer Center", "madison", "WI", "Comprehensive"),
]
# Places that are not Census places or where a campus-level point is clearly better than the city centroid.
NCI_OVERRIDE = {"la jolla": (32.875, -117.236), "bronx": (40.880, -73.879), "manhattan": (40.770, -73.960), "stanford": (37.433, -122.175),
                "urban honolulu": (21.300, -157.850), "san francisco": (37.763, -122.458), "nashville-davidson": (36.144, -86.803), "lexington-fayette": (38.032, -84.508)}

ONC = re.compile(r"cancer|neoplas|carcinom|lymphom|leuk|myelom|sarcom|melanom|malignan|tumou?r|gliom|mesotheliom|blastom|adenoma|myelodysplas|metasta|oncolog|hodgkin|"
                 r"waldenstr|myelofibrosis|polycythemia|thrombocythemia|\bmds\b|\baml\b|\bcll\b|\bcml\b|nsclc|sclc|\bgist\b|\bmpn\b|\bhcc\b|\brcc\b|\bcrc\b|pdac|\bgbm\b|dlbcl|tnbc|"
                 r"meningiom|ependymom|germinom|craniopharyngiom|schwannom|neurofibrom|mycosis fungoides|sezary|amyloidosis|lymphoproliferative|mastocytosis|histiocyt|"
                 r"castleman|paragangliom|pheochromocytom|desmoid|chordom|thymom|wilms|trophoblastic|plasmacytom|macroglobulinemia|\bptld\b|graft.versus.host|gvhd|\bctcl\b|\bptcl\b|\b[bt]-all\b|plasma cell|\bmgus\b|smoldering|hairy cell", re.I)

INJ = {"bortezomib", "carfilzomib"}
ORAL_WORD = re.compile(r"\b(oral|orally|p\.?o\.?|by mouth|per os|tablet|tablets|capsule|capsules)\b", re.I)
ORAL_FALSE = re.compile(r"\boral(?:\s|-)?(cavity|cancer|carcinoma|squamous|mucositis|lesion|health|hygiene|care|tongue|examination|mucosa|contraceptive)", re.I)
NON_ORAL = re.compile(r"\b(intravenous(?:ly)?|i\.?v\.?|infusion|infused|injection|injected|subcutaneous(?:ly)?|s\.?c\.?|intramuscular|intrathecal|intratumoral(?:ly)?|intra-tumoral|"
                      r"intravesical|intraperitoneal|intranodal|topical(?:ly)?|inhaled|inhalation|transdermal|implant)\b", re.I)


def route(ps):
    aim = ps.get("armsInterventionsModule", {}); ivs = aim.get("interventions", []) or []
    drugs = [iv for iv in ivs if (iv.get("type") or "").upper() == "DRUG"]
    names = [iv.get("name") or "" for iv in drugs] + [o for iv in drugs for o in (iv.get("otherNames") or [])]
    for nm in names:
        for tok in [t.strip("()[],;") for t in nm.lower().replace("/", " ").split()]:
            if tok.endswith(config.ORAL_SUFFIXES) and len(tok) > 6 and tok not in INJ: return "oral", f"stem:{tok}"
    ivt = ORAL_FALSE.sub(" ", " ".join(iv.get("description") or "" for iv in drugs))
    armt = ORAL_FALSE.sub(" ", " ".join(a.get("description") or "" for a in aim.get("armGroups", []) or []))
    sumt = ORAL_FALSE.sub(" ", ps.get("descriptionModule", {}).get("briefSummary") or "")
    if ORAL_WORD.search(ivt): return "oral", "intervention_text"
    if ORAL_WORD.search(armt): return "oral", "arm_text"
    if drugs and ORAL_WORD.search(sumt): return "oral", "summary_text"
    if not drugs: return "non_oral", "no_drug_intervention"
    if NON_ORAL.search(ivt + " " + armt + " " + sumt): return "non_oral", "parenteral_or_topical_route_stated"
    return "indeterminate", "drug_listed_no_route_words"


def age_years(s):
    m = re.match(r"([\d.]+)\s*(Year|Month|Week|Day)", s or "", re.I)
    if not m: return None
    return float(m.group(1)) / {"year": 1, "month": 12, "week": 52, "day": 365}[m.group(2).lower()]


def main():
    OUT.mkdir(exist_ok=True)
    gaz = pd.read_csv(REF / "gazetteer_places.csv", dtype=str)
    gaz["lat"] = gaz.lat.astype(float); gaz["lon"] = gaz.lon.astype(float)
    rows = []
    for name, place, st, tier in NCI:
        if place in NCI_OVERRIDE: lat, lon = NCI_OVERRIDE[place]; src = "override"
        else:
            m = gaz[(gaz.state == st) & (gaz.place == place)]
            if m.empty: raise SystemExit(f"gazetteer miss: {place}, {st}")
            lat, lon, src = m.iloc[0].lat, m.iloc[0].lon, "gazetteer_place_centroid"
        rows.append({"name": name, "city": place, "state": st, "tier": tier, "lat": round(lat, 4), "lon": round(lon, 4), "coord_source": src})
    pd.DataFrame(rows).to_csv(REF / "nci_centers.csv", index=False)

    # fetch_us.py writes the raw pull to trials.csv / us_sites.csv; keep a *_raw copy of THIS pull (always refresh — an older copy
    # left over from a previous pull would silently be QC'd instead of the new data)
    if (RAW / "fetch_log.json").stat().st_mtime > (RAW / "trials_raw.csv").stat().st_mtime if (RAW / "trials_raw.csv").exists() else True:
        shutil.copy(RAW / "trials.csv", RAW / "trials_raw.csv"); shutil.copy(RAW / "us_sites.csv", RAW / "us_sites_raw.csv")
    raw = {}
    with open(RAW / "studies_raw.jsonl") as fh:
        for line in fh:
            ps = json.loads(line)["protocolSection"]; raw[ps["identificationModule"]["nctId"]] = ps
    trials = list(csv.DictReader(open(RAW / "trials_raw.csv")))
    kept, excluded, tally = [], [], {}
    for t in trials:
        if not (ONC.search(t["conditions"]) or ONC.search(t["brief_title"])):
            excluded.append({"nct_id": t["nct_id"], "brief_title": t["brief_title"], "conditions": t["conditions"], "n_us_sites": t["n_us_sites"]}); continue
        r, ev = route(raw[t["nct_id"]])
        mx = age_years(t.get("maximum_age"))
        t.update({"oral_route": r, "oral_evidence": ev, "oral_candidate": int(r == "oral"), "oral_indeterminate": int(r == "indeterminate"),
                  "max_age_years": "" if mx is None else round(mx, 1), "excludes_55plus": int(mx is not None and mx < 55)})
        tally[r] = tally.get(r, 0) + 1
        kept.append(t)
    keep = {t["nct_id"] for t in kept}
    sites = [s for s in csv.DictReader(open(RAW / "us_sites_raw.csv")) if s["nct_id"] in keep]
    for path, data in ((RAW / "trials.csv", kept), (RAW / "us_sites.csv", sites)):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys())); w.writeheader(); w.writerows(data)
    pd.DataFrame(excluded).to_csv(OUT / "qc_excluded_non_oncology.csv", index=False)
    log = {"trials_raw": len(trials), "excluded_non_oncology_rule": len(excluded), "trials_kept": len(kept), "site_rows_kept": len(sites),
           "route": tally, "excludes_55plus": sum(t["excludes_55plus"] for t in kept), "nci_treating_centers": len(rows)}
    json.dump(log, open(OUT / "qc_log.json", "w"), indent=2); print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
