"""Tier 4 (candidate universe, STAND-IN) — every US facility that has hosted an interventional oncology treatment trial started
2016 or later (any status except withdrawn / terminated / unknown), from ClinicalTrials.gov.

This is a stand-in for the intended universe (Commission on Cancer-accredited programs + NCORP affiliates), used because those
domains were not reachable from the build environment. It is a "demonstrated capacity" list: each facility has actually run an
oncology treatment trial in the last decade. Its bias is that it can only contain places already in the registry, so it will
miss CoC-accredited hospitals that have not (yet) hosted a registered trial. Replace it with fetch_candidates_coc_ncorp.py output
when those sources are reachable; tier4_covering.py accepts either file.

Output: data/ref/candidates_registry.csv  (name, city, state, zip, county_fips, n_trials_hosted_2016plus, n_recruiting_now, source)
"""
import csv, json, re, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd, requests
import config
from fetch_us import STATES, dig

RAW, REF, OUT = Path("data/raw"), Path("data/ref"), Path("out_adult55")
FIELDS = "NCTId,OverallStatus,StartDate,LocationFacility,LocationCity,LocationState,LocationZip,LocationCountry"
STATUSES = "COMPLETED,ACTIVE_NOT_RECRUITING,RECRUITING,ENROLLING_BY_INVITATION,NOT_YET_RECRUITING,SUSPENDED"
SITECODE = re.compile(r"\(?\s*(site|study site|local institution|investigative site|clinical site|id|site id|site number|site #)\s*[-#:]?\s*\d+[a-z]?\s*\)?|\(\s*\d{3,6}\s*\)|/\s*id#?\s*\d+|\bsite\s+\d{2,6}\b", re.I)
def norm(x):
    y = SITECODE.sub(" ", str(x)); y = re.sub(r"[^a-z0-9 ]", " ", y.lower()); return re.sub(r"\s+", " ", y).strip()


def main():
    params = {"query.cond": config.CONDITION_QUERY, "query.locn": "United States", "filter.overallStatus": STATUSES,
              "filter.advanced": "AREA[StudyType]INTERVENTIONAL AND AREA[DesignPrimaryPurpose]TREATMENT AND AREA[StartDate]RANGE[2016-01-01,MAX]",
              "fields": FIELDS, "pageSize": 1000, "countTotal": "true", "format": "json"}
    s = requests.Session(); s.headers["User-Agent"] = "us-trial-access-map/3.0 (research)"; tok, total, n, rows = None, None, 0, []
    while True:
        p = dict(params); p.update({"pageToken": tok} if tok else {})
        j = s.get(config.CTGOV_BASE, params=p, timeout=300).json(); total = total or j.get("totalCount")
        for st in j.get("studies", []):
            ps = st["protocolSection"]; nct = dig(ps, "identificationModule", "nctId"); status = dig(ps, "statusModule", "overallStatus")
            for loc in dig(ps, "contactsLocationsModule", "locations", default=[]) or []:
                if (loc.get("country") or "") not in ("United States", ""): continue
                stt = STATES.get((loc.get("state") or "").strip().lower())
                if not stt or stt[0] == "72": continue
                rows.append({"nct_id": nct, "status": status, "facility": loc.get("facility") or "", "city": loc.get("city") or "", "state_fips": stt[0], "state": stt[1], "zip": (loc.get("zip") or "").strip()[:5]})
            n += 1
        print(f"  {n}/{total}", flush=True); tok = j.get("nextPageToken")
        if not tok: break
        time.sleep(config.REQUEST_SLEEP_SEC)
    df = pd.DataFrame(rows); df["fac"] = df.facility.map(norm)
    # county by ZIP (state-checked), then ZIP3, as in metrics_us.py; city-gazetteer fallback omitted here (rare, and candidates without a county are dropped)
    z2c = dict(pd.read_csv(REF / "zcta_county.csv", dtype=str).values); z3 = dict(pd.read_csv(REF / "zip3_county.csv", dtype=str).values)
    def county(r):
        c = z2c.get(r.zip) if r.zip.isdigit() and len(r.zip) == 5 else None
        if c and c[:2] == r.state_fips: return c
        c3 = z3.get(r.zip[:3]) if len(r.zip) >= 3 and r.zip[:3].isdigit() else None
        return c3 if c3 and c3[:2] == r.state_fips else None
    df["county_fips"] = [county(r) for r in df.itertuples()]
    df = df[df.county_fips.notna() & (df.fac != "")]
    g = df.groupby(["county_fips", "fac"]).agg(name=("facility", lambda s: s.value_counts().index[0]), city=("city", lambda s: s.value_counts().index[0]), state=("state", "first"),
                                               zip=("zip", lambda s: s[s.str.len() == 5].value_counts().index[0] if (s.str.len() == 5).any() else ""),
                                               n_trials_hosted_2016plus=("nct_id", "nunique"), n_recruiting_now=("nct_id", lambda s: df.loc[s.index].loc[df.loc[s.index].status == "RECRUITING", "nct_id"].nunique())).reset_index()
    g["source"] = "registry_stand_in"; g["name"] = g.name.map(lambda x: re.sub(r"\s+", " ", SITECODE.sub("", x)).strip(" -(),") or x)
    g = g[~g.fac.isin(["research site", "local institution", "study site", "clinical site", "investigational site", "site"])]  # anonymous placeholders cannot be located
    g[["name", "city", "state", "zip", "county_fips", "n_trials_hosted_2016plus", "n_recruiting_now", "source"]].to_csv(REF / "candidates_registry.csv", index=False)
    log = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "api_total_count": total, "studies_read": n, "site_rows": len(rows), "facilities": len(g), "statuses": STATUSES, "start_date_from": "2016-01-01"}
    json.dump(log, open(REF / "candidates_registry_log.json", "w"), indent=2); print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
