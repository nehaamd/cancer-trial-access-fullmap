"""
National pull: recruiting interventional oncology TREATMENT trials with >=1 US site.
Writes data/raw/studies_raw.jsonl (page by page), trials.csv, us_sites.csv, fetch_log.json.
"""
import csv, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
import requests
import config

RAW = Path("data/raw"); RAW.mkdir(parents=True, exist_ok=True)
EXTRA = ["InterventionOtherName", "ArmGroupDescription", "BriefSummary", "MinimumAge", "MaximumAge", "Keyword", "OfficialTitle"]

STATES = {  # name/abbr -> (FIPS, USPS)
 "alabama":("01","AL"),"alaska":("02","AK"),"arizona":("04","AZ"),"arkansas":("05","AR"),"california":("06","CA"),"colorado":("08","CO"),
 "connecticut":("09","CT"),"delaware":("10","DE"),"district of columbia":("11","DC"),"florida":("12","FL"),"georgia":("13","GA"),"hawaii":("15","HI"),
 "idaho":("16","ID"),"illinois":("17","IL"),"indiana":("18","IN"),"iowa":("19","IA"),"kansas":("20","KS"),"kentucky":("21","KY"),"louisiana":("22","LA"),
 "maine":("23","ME"),"maryland":("24","MD"),"massachusetts":("25","MA"),"michigan":("26","MI"),"minnesota":("27","MN"),"mississippi":("28","MS"),
 "missouri":("29","MO"),"montana":("30","MT"),"nebraska":("31","NE"),"nevada":("32","NV"),"new hampshire":("33","NH"),"new jersey":("34","NJ"),
 "new mexico":("35","NM"),"new york":("36","NY"),"north carolina":("37","NC"),"north dakota":("38","ND"),"ohio":("39","OH"),"oklahoma":("40","OK"),
 "oregon":("41","OR"),"pennsylvania":("42","PA"),"rhode island":("44","RI"),"south carolina":("45","SC"),"south dakota":("46","SD"),"tennessee":("47","TN"),
 "texas":("48","TX"),"utah":("49","UT"),"vermont":("50","VT"),"virginia":("51","VA"),"washington":("53","WA"),"west virginia":("54","WV"),
 "wisconsin":("55","WI"),"wyoming":("56","WY"),"puerto rico":("72","PR"),
}
for k, (f, a) in list(STATES.items()):
    STATES[a.lower()] = (f, a)
STATES["washington, d.c."] = STATES["washington dc"] = STATES["d.c."] = STATES["district of columbia"]


def dig(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict): return default
        d = d.get(k)
        if d is None: return default
    return d


def fetch():
    params = {"query.cond": config.CONDITION_QUERY, "query.locn": "United States",
              "filter.overallStatus": ",".join(config.OVERALL_STATUS),
              "filter.advanced": f"AREA[StudyType]INTERVENTIONAL AND AREA[DesignPrimaryPurpose]{config.PRIMARY_PURPOSE}",
              "fields": ",".join(config.FIELDS + EXTRA), "pageSize": config.PAGE_SIZE, "countTotal": "true", "format": "json"}
    s = requests.Session(); s.headers.update({"User-Agent": "us-trial-access-snapshot/0.1 (research)"})
    tok, total, n = None, None, 0
    with open(RAW / "studies_raw.jsonl", "w") as f:
        while True:
            p = dict(params)
            if tok: p["pageToken"] = tok
            r = s.get(config.CTGOV_BASE, params=p, timeout=300); r.raise_for_status(); j = r.json()
            total = total or j.get("totalCount")
            for st in j.get("studies", []): f.write(json.dumps(st) + "\n"); n += 1
            f.flush(); print(f"  {n}/{total}", flush=True)
            tok = j.get("nextPageToken")
            if not tok: break
            time.sleep(config.REQUEST_SLEEP_SEC)
    return params, total, n


def flatten(ps):
    nct = dig(ps, "identificationModule", "nctId")
    ivs = dig(ps, "armsInterventionsModule", "interventions", default=[]) or []
    sites = []
    for loc in dig(ps, "contactsLocationsModule", "locations", default=[]) or []:
        if (loc.get("country") or "") not in ("United States", ""): continue
        st = STATES.get((loc.get("state") or "").strip().lower())
        if not st: continue
        if loc.get("status") not in config.SITE_STATUS_KEEP: continue
        sites.append({"nct_id": nct, "facility": loc.get("facility"), "city": loc.get("city"), "state_fips": st[0], "state": st[1],
                      "zip": (loc.get("zip") or "").strip(), "site_status": loc.get("status") or ""})
    elig = ps.get("eligibilityModule", {})
    trial = {"nct_id": nct, "brief_title": dig(ps, "identificationModule", "briefTitle"),
             "overall_status": dig(ps, "statusModule", "overallStatus"), "start_date": dig(ps, "statusModule", "startDateStruct", "date"),
             "phases": ";".join(dig(ps, "designModule", "phases", default=[]) or []),
             "primary_purpose": dig(ps, "designModule", "designInfo", "primaryPurpose"),
             "conditions": ";".join(dig(ps, "conditionsModule", "conditions", default=[]) or []),
             "keywords": ";".join(dig(ps, "conditionsModule", "keywords", default=[]) or []),
             "official_title": dig(ps, "identificationModule", "officialTitle") or "",
             "lead_sponsor_class": dig(ps, "sponsorCollaboratorsModule", "leadSponsor", "class"),
             "intervention_types": ";".join(sorted({(iv.get("type") or "") for iv in ivs})),
             "intervention_names": ";".join((iv.get("name") or "") for iv in ivs),
             "minimum_age": elig.get("minimumAge") or "", "maximum_age": elig.get("maximumAge") or "",
             "n_us_sites": len(sites), "n_states": len({s["state"] for s in sites})}
    return trial, sites


def main():
    if "--no-fetch" in sys.argv:
        params, total = {"note": "reused existing studies_raw.jsonl"}, None
    else:
        params, total, _ = fetch()
    trials, sites = [], []
    with open(RAW / "studies_raw.jsonl") as f:
        for line in f:
            t, sr = flatten(json.loads(line)["protocolSection"])
            if sr: trials.append(t); sites.extend(sr)
    with open(RAW / "trials.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(trials[0].keys())); w.writeheader(); w.writerows(trials)
    with open(RAW / "us_sites.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sites[0].keys())); w.writeheader(); w.writerows(sites)
    log = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "params": params, "api_total_count": total,
           "trials_with_us_recruiting_site": len(trials), "us_site_rows": len(sites)}
    json.dump(log, open(RAW / "fetch_log.json", "w"), indent=2); print(json.dumps({k: v for k, v in log.items() if k != "params"}, indent=2))


if __name__ == "__main__":
    main()
