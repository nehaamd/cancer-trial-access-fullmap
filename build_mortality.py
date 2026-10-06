"""Cancer deaths versus trial access: county cancer death rates (State Cancer Profiles, NVSS) set against the same county access
shares the burden-vs-access view uses. A cross-tabulation, never a combined score.

Classes (the page lets the reader change the access side; the mortality side is fixed):
  high mortality = all-sites age-adjusted death rate in the top third of counties with a published rate (status ok); counties
                   flagged "small numbers" (fewer than 16 deaths a year on average) are classified but hatched; suppressed /
                   not available = no data
  low access     = at least half of residents 55+ have fewer than 20 recruiting trials within 60 road-miles (from burden.js,
                   population-weighted over census tracts; the page recomputes it when filters are on)
Four cells: high mortality & low access ("hh"), high mortality only, low access only, neither.

Reads data/ref/cancer_mortality_county.csv (fetch_cancer_mortality.py), docs/burden.js (access shares) and docs/data.js
(residents 55+, names, the counties touching each district). Writes docs/mortality.js (window.MORTALITY): per-county arrays in the
site order of data.js's burden sites, the tertile cut-offs and medians per site, and national / state / district summaries of
the default definition. Runs in run_refresh.sh after build_burden_access.py.
"""
import json, re
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd

FIPS2USPS = {"01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
             "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
             "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY"}
BSTAT = {"ok": 0, "small_numbers": 1, "suppressed_source": 2, "not_available_state": 3, "not_available_county": 4}
THRESHOLD_PCT = 50


def docs_dir():
    return Path("docs") if Path("docs").is_dir() and not Path("data.js").exists() else Path(".")


def read_js(path, prefix):
    s = Path(path).read_text(encoding="utf-8").strip(); assert s.startswith(prefix), path
    return json.loads(s[len(prefix):].rstrip(";"))


def main():
    docs = docs_dir()
    D = read_js(docs / "data.js", "window.DATA="); BU = read_js(docs / "burden.js", "window.BURDEN=")
    sites = D["meta"]["burden"]["sites"]                       # [[key, label], ...] — the page's BSITE order
    mo = pd.read_csv("data/ref/cancer_mortality_county.csv", dtype={"county_fips": str})
    log = json.load(open("data/ref/cancer_mortality_log.json"))
    C = D["counties"]; CK = sorted(C)
    period = sorted(mo.period.dropna().unique().tolist())[-1]
    # per-site cut-offs over counties with a published, reliable rate (status ok)
    tert, med, us = {}, {}, {}
    for key, _ in sites:
        g = mo[(mo.site == key) & (mo.status == "ok")].rate
        tert[key] = [round(float(g.quantile(1 / 3)), 1), round(float(g.quantile(2 / 3)), 1)] if len(g) >= 30 else None
        med[key] = round(float(g.median()), 1) if len(g) else None
        us[key] = {"rate": log["sites"][key]["us_rate"], "deaths": log["sites"][key]["us_avg_annual_count"]}
    # per-county arrays: all sites [rate, lo, hi, deaths, status]; other sites [rate, deaths, status]
    by = {key: mo[mo.site == key].set_index("county_fips") for key, _ in sites}
    def arr(key, f):
        g = by[key]
        if f not in g.index: return [None, None, None, None, 4] if key == "all" else [None, None, 4]
        r = g.loc[f]; st = BSTAT[r.status]; rate = None if pd.isna(r.rate) else round(float(r.rate), 1); n = None if pd.isna(r.avg_annual_count) else int(r.avg_annual_count)
        if key == "all": return [rate, None if pd.isna(r.ci_lo) else float(r.ci_lo), None if pd.isna(r.ci_hi) else float(r.ci_hi), n, st]
        return [rate, n, st]
    county = {f: [arr(key, f) for key, _ in sites] for f in CK}
    # default classification: all sites, top third, low access = at least THRESHOLD_PCT% of residents 55+ with fewer than 20 trials within 60 road-miles
    t2 = tert["all"][1]
    rows = []
    for f in CK:
        a = county[f][0]; u = BU["county"].get(f)
        if a[4] > 1 or a[0] is None or not u or u.get("l20") is None: continue
        rows.append({"f": f, "st": FIPS2USPS.get(C[f]["s"], ""), "p": int(C[f]["p"]), "rate": a[0], "deaths": a[3] or 0, "small": a[4] == 1, "low": u["l20"] >= THRESHOLD_PCT, "high": a[0] >= t2,
                     "tert": 3 if a[0] >= t2 else 2 if a[0] >= tert["all"][0] else 1, "l20": u["l20"]})
    df = pd.DataFrame(rows)
    def summ(d):
        cell = d[d.high & d.low]
        return {"counties_classified": int(len(d)), "hh_counties": int(len(cell)), "hh_pop55": int(cell.p.sum()), "hh_deaths": int(cell.deaths.sum()), "hh_small": int(cell.small.sum()),
                "cells": {"hh": int((d.high & d.low).sum()), "h_only": int((d.high & ~d.low).sum()), "l_only": int((~d.high & d.low).sum()), "neither": int((~d.high & ~d.low).sum())},
                "tertile_low_access": {str(t): int(((d.tert == t) & d.low).sum()) for t in (1, 2, 3)}, "tertile_counties": {str(t): int((d.tert == t).sum()) for t in (1, 2, 3)},
                "pop55_classified": int(d.p.sum()), "top": [{"f": r.f, "name": C[r.f]["nl"], "st": r.st, "p": int(r.p), "rate": r.rate, "deaths": int(r.deaths), "small": bool(r.small), "l20": r.l20} for r in cell.sort_values("p", ascending=False).head(10).itertuples()]}
    nat = summ(df); states = {st: summ(d) for st, d in df.groupby("st")}
    hh = set(df[df.high & df.low].f)
    districts = {}
    for k, dd in D["districts"].items():
        ks = dd.get("counties") or []; cl = [f for f in ks if f in df.f.values]
        districts[k] = {"n": len(ks), "classified": len(cl), "hh": [f for f in ks if f in hh]}
    meta = {"built": str(date.today()), "pulled": log["pulled"], "period": period, "source": "NCI/CDC State Cancer Profiles death rates (National Vital Statistics System), age-adjusted, all ages, " + period,
            "sites": sites, "small_threshold": log["small_numbers_threshold_avg_annual_deaths"], "tertiles": tert, "medians": med, "us": us, "threshold_pct": THRESHOLD_PCT, "menu_threshold": 20,
            "definition": {"high_mortality": f"all-sites age-adjusted cancer death rate in the top third of counties with a published rate (at least {t2} per 100,000)",
                           "low_access": f"at least {THRESHOLD_PCT}% of residents 55+ have fewer than 20 recruiting trials within 60 road-miles (with a cancer type selected: no trial for that cancer within 60 road-miles)"},
            "status_counts_all": log["sites"]["all"]["status_counts"], "not_available": log.get("counties_not_available", []), "remap": log.get("remap", {}),
            "note": "County death rates are five-year age-adjusted rates per 100,000 from State Cancer Profiles (" + period + "); access shares are population-weighted over census tracts (burden.js). The two measures are cross-tabulated, never combined into a score."}
    out = {"meta": meta, "county": county, "summary": {"nat": nat, "states": states, "districts": districts}}
    s = json.dumps(out, separators=(",", ":")); (docs / "mortality.js").write_text("window.MORTALITY=" + s + ";", encoding="utf-8")
    print(f"all-sites death rate {period}: tertile cut-offs {tert['all']} per 100,000 (median {med['all']}, US {us['all']['rate']}) | classified counties {nat['counties_classified']} | "
          f"high mortality & low access: {nat['hh_counties']} counties, {nat['hh_pop55']:,} residents 55+, {nat['hh_deaths']:,} cancer deaths a year ({nat['hh_small']} small-numbers)")
    print("cells", nat["cells"], "| low-access counties by mortality tertile", nat["tertile_low_access"], "| top by residents 55+:", [t["name"] + ", " + t["st"] for t in nat["top"][:5]])
    print("mortality.js KB", len(s) // 1024)
    json.dump({"built": meta["built"], "period": period, "tertiles_all": tert["all"], "national": nat}, open("mortality_log.json", "w"), indent=1)


if __name__ == "__main__":
    main()
