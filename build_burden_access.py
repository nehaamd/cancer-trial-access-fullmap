"""Burden-versus-access view: county-level cancer incidence set against county-level trial access, as a cross-tabulation
(a view, not an index — the two measures are never combined into a score).

For every county this computes, from the tract table, the share of residents 55+ with fewer than 20 / no recruiting trials
within 60 road-miles (population-weighted over the county's census tracts — the county pane's own count is the number of
trials within 60 road-miles of the county *population center*, which is a different, unweighted quantity), plus the same
"none within 60 road-miles" share for each named cancer type (multi-label rule: a basket trial counts under every cancer
it names, as everywhere else on the site).

Default classification (the page lets the reader change the access criterion):
  high burden  = all-sites age-adjusted incidence above the median of counties with a published rate (status ok);
                 counties flagged "small numbers" are classified but hatched; suppressed / not available = no data
  low access   = at least half of residents 55+ have fewer than 20 recruiting trials within 60 road-miles
                 (when a cancer type is selected on the page: at least half have NO trial for that cancer within 60 road-miles)

Writes docs/burden.js (window.BURDEN): per-county shares (all trials and by cancer type), the incidence medians per site,
and national / state summaries of the high-burden, low-access cell for the default definition.
"""
import json
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd

FIPS2USPS = {"01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
             "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
             "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY"}
# incidence site -> the site's cancer-type filter category (same mapping as the page's TYPE2SITE, inverted; several sites share a category)
SITE2TYPE = {"breast": "breast", "colorectal": "colorectal", "lung": "lung", "prostate": "prostate", "melanoma_skin": "melanoma_skin", "lymphoma": "lymphoma", "leukemia": "leukemia", "pancreatic": "pancreatic",
             "liver_biliary": "liver_biliary", "bladder_urothelial": "bladder_urothelial", "kidney": "kidney", "brain_cns": "brain_cns", "head_neck": "head_neck", "thyroid": "neuroendocrine_endocrine",
             "gynecologic_ovary": "gynecologic", "gynecologic_uterus": "gynecologic", "gynecologic_cervix": "gynecologic", "esophagus": "gastric_esophageal", "stomach": "gastric_esophageal"}


def find(name):
    for d in [".", "data/ref", "out_adult55", "data/raw", "docs"]:
        p = Path(d) / name
        if p.exists(): return p
    raise FileNotFoundError(name)


def docs_dir():
    return Path("docs") if Path("docs").is_dir() and not Path("data.js").exists() else Path(".")


def main():
    tr = pd.read_csv(find("tract_access.csv"), dtype={"tract": str, "county_fips": str})
    tcols = [c for c in tr.columns if c.startswith("t60_cancer_type_") and not c.endswith(("_multi", "_other_unclassified"))]
    types = [c.replace("t60_cancer_type_", "") for c in tcols]
    w = tr.pop55.values.astype(float)
    g = tr.groupby("county_fips")
    W = g.pop55.sum().astype(float)
    def share(mask): return (pd.Series(w * mask, index=tr.index).groupby(tr.county_fips).sum() / W * 100).round(1)
    l20 = share(tr.trials_within_60rdmi.values < 20); z60 = share(tr.trials_within_60rdmi.values == 0)
    t60 = (pd.Series(w * tr.trials_within_60rdmi.values, index=tr.index).groupby(tr.county_fips).sum() / W).round().astype(int)
    zt = {t: share(tr[c].values == 0) for t, c in zip(types, tcols)}
    county = {f: {"l20": float(l20[f]), "z60": float(z60[f]), "t60": int(t60[f]), "zt": [float(zt[t][f]) for t in types]} for f in W.index}
    # incidence, from the same file the payload uses
    inc = pd.read_csv(find("cancer_incidence_county.csv"), dtype={"county_fips": str})
    medians = {s: (round(float(gg[gg.status == "ok"].rate.median()), 1) if (gg.status == "ok").any() else None) for s, gg in inc.groupby("site")}
    # national / state summary for the default definition (all sites, <20 within 60 road-miles for >= 50% of residents 55+)
    a = inc[inc.site == "all"].set_index("county_fips"); med = medians["all"]
    rows = []
    for f in W.index:
        if f not in a.index or a.loc[f, "status"] not in ("ok", "small_numbers"): continue
        rows.append({"f": f, "st": FIPS2USPS.get(f[:2], ""), "p": int(W[f]), "rate": float(a.loc[f, "rate"]), "cases": int(a.loc[f, "avg_annual_count"]) if not pd.isna(a.loc[f, "avg_annual_count"]) else 0,
                     "small": a.loc[f, "status"] == "small_numbers", "low": l20[f] >= 50, "high": float(a.loc[f, "rate"]) > med})
    df = pd.DataFrame(rows)
    def summ(d):
        cell = d[d.high & d.low]
        return {"counties_classified": int(len(d)), "hb_la_counties": int(len(cell)), "hb_la_pop55": int(cell.p.sum()), "hb_la_cases": int(cell.cases.sum()), "hb_la_small_numbers": int(cell.small.sum()),
                "cells": {"hb_la": int((d.high & d.low).sum()), "hb_ok": int((d.high & ~d.low).sum()), "lb_la": int((~d.high & d.low).sum()), "lb_ok": int((~d.high & ~d.low).sum())},
                "top": cell.sort_values("cases", ascending=False).head(10).f.tolist()}
    summary = {"nat": summ(df), "states": {st: summ(d) for st, d in df.groupby("st")}}
    meta = {"built": str(date.today()), "types": types, "medians": medians, "median_all": med, "definition": {"high_burden": "all-sites age-adjusted incidence above the median of counties with a published rate",
            "low_access": "at least 50% of residents 55+ have fewer than 20 recruiting trials within 60 road-miles (with a cancer type selected: no trial for that cancer within 60 road-miles)", "threshold_pct": 50, "menu_threshold": 20},
            "site2type": SITE2TYPE, "note": "County shares are population-weighted over census tracts; incidence is NCI/CDC State Cancer Profiles 2018-2022. The two measures are cross-tabulated, never combined into a score."}
    out = {"meta": meta, "county": county, "summary": summary}
    s = json.dumps(out, separators=(",", ":")); (docs_dir() / "burden.js").write_text("window.BURDEN=" + s + ";", encoding="utf-8")
    n = summary["nat"]
    print(f"median all-sites incidence (published counties): {med} | classified counties {n['counties_classified']} | high-burden & low-access: {n['hb_la_counties']} counties, {n['hb_la_pop55']:,} residents 55+, {n['hb_la_cases']:,} annual diagnoses ({n['hb_la_small_numbers']} small-numbers)")
    print("cells", n["cells"], "| top by cases:", n["top"][:5]); print("burden.js KB", len(s) // 1024)
    json.dump({"built": meta["built"], "median_all": med, "national": n, "types": types}, open("burden_log.json", "w"), indent=1)


if __name__ == "__main__":
    main()
