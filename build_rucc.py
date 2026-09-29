"""Rural / urban classification layer: USDA ERS Rural-Urban Continuum Codes (RUCC) joined to every county, and tract-weighted
access figures for residents 55+ by metro / nonmetro status and by each of the nine codes, nationally and per state.

Writes docs/rucc.js (window.RUCC) and docs/tract_county.bin (one u16 per census tract = index of its county in the web
payload's county order), which the page uses to recompute the metro / nonmetro split live when trial filters are on.

Sources
  Ruralurbancontinuumcodes2023.csv  USDA ERS, 2023 Rural-Urban Continuum Codes (long format: FIPS, State, County_Name,
                                    Attribute, Value). Codes 1-3 = metro, 4-9 = nonmetro. Connecticut is coded on its nine
                                    2022 planning regions, which this project does not use.
  ruralurbancodes2013.csv           USDA ERS, 2013 codes — used ONLY for Connecticut's eight legacy counties, which the 2023
                                    release no longer lists. Flagged in the output (meta.ct_note; county code source "2013").
  tract_access.csv, tracts_us.csv   this project's tract-level access table (population 55+, trials within 60 road-miles,
                                    road miles to NCI centers / menus), tract order = tracts_us.csv order.
  tract_cd119.csv                   Census tract -> 119th Congressional District relationship (shares), for district
                                    metro / nonmetro population shares.

Definitions (same as the rest of the site): "fewer than 20 trials within 60 road-miles" and "none within 60 road-miles" are
shares of residents 55+, weighted by census-tract population; medians are population-weighted; NOROAD (999) distances are
excluded from medians and counted in the "no road route" share.

Run from the repository root (flat layout) or the pipeline root (data/ref, out_adult55, docs). ~20 s.
"""
import json, sys, struct
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd

NOROAD = 999.0
CODE_LABEL = {1: "Metro, 1 million or more", 2: "Metro, 250,000 to 1 million", 3: "Metro, under 250,000",
              4: "Nonmetro, urban population 20,000+, adjacent to a metro area", 5: "Nonmetro, urban population 20,000+, not adjacent",
              6: "Nonmetro, urban population 5,000–20,000, adjacent to a metro area", 7: "Nonmetro, urban population 5,000–20,000, not adjacent",
              8: "Nonmetro, urban population under 5,000, adjacent to a metro area", 9: "Nonmetro, urban population under 5,000, not adjacent"}
FIPS2USPS = {"01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
             "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
             "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY"}


def find(name):
    for d in [".", "data/ref", "out_adult55", "data/raw", "docs"]:
        p = Path(d) / name
        if p.exists(): return p
    raise FileNotFoundError(name)


def docs_dir():
    return Path("docs") if Path("docs").is_dir() and not Path("data.js").exists() else Path(".")


def load_rucc():
    raw = pd.read_csv(find("Ruralurbancontinuumcodes2023.csv"), dtype=str, encoding="latin-1")
    r23 = raw[raw.Attribute == "RUCC_2023"].set_index("FIPS").Value.dropna().astype(int)
    r13 = pd.read_csv(find("ruralurbancodes2013.csv"), dtype=str)
    r13["FIPS"] = r13.FIPS.str.zfill(5); r13 = r13.set_index("FIPS").RUCC2013.astype(int)
    return r23, r13


def wmedian(vals, w):
    if len(vals) == 0: return None
    o = np.argsort(vals); v, ww = np.asarray(vals)[o], np.asarray(w, float)[o]
    c = np.cumsum(ww); return float(v[np.searchsorted(c, c[-1] / 2)])


def group_stats(t):
    """t: tract rows. Returns the site's standard access figures for the residents 55+ in those tracts."""
    w = t.pop55.values.astype(float); W = w.sum()
    if W == 0: return None
    m60 = t.trials_within_60rdmi.values
    nci = t.road_mi_nci.values; brd = t.road_mi_broad.values
    okn, okb = nci < NOROAD, brd < NOROAD
    return {"p": int(W), "n": int(t.county_fips.nunique()),
            "z60": round(100 * w[m60 == 0].sum() / W, 1), "l20": round(100 * w[m60 < 20].sum() / W, 1), "l100": round(100 * w[m60 < 100].sum() / W, 1),
            "t60": int(round((w * m60).sum() / W)), "t30": int(round((w * t.trials_within_30rdmi.values).sum() / W)), "t120": int(round((w * t.trials_within_120rdmi.values).sum() / W)),
            "g60n": round(100 * (w[okn & (nci > 60)].sum() + w[~okn].sum()) / W, 1), "g120n": round(100 * (w[okn & (nci > 120)].sum() + w[~okn].sum()) / W, 1),
            "g60b": round(100 * (w[okb & (brd > 60)].sum() + w[~okb].sum()) / W, 1), "g120b": round(100 * (w[okb & (brd > 120)].sum() + w[~okb].sum()) / W, 1),
            "medn": None if okn.sum() == 0 else int(round(wmedian(nci[okn], w[okn]))), "medb": None if okb.sum() == 0 else int(round(wmedian(brd[okb], w[okb]))),
            "nr": round(100 * w[~okb].sum() / W, 1)}


def main():
    r23, r13 = load_rucc()
    tr = pd.read_csv(find("tract_access.csv"), dtype={"tract": str, "county_fips": str},
                     usecols=["tract", "county_fips", "pop55", "trials_within_30rdmi", "trials_within_60rdmi", "trials_within_120rdmi", "road_mi_nci", "road_mi_broad"])
    order = pd.read_csv(find("tracts_us.csv"), dtype={"tract": str}).tract
    assert (tr.tract.values == order.values).all(), "tract_access.csv order must equal tracts_us.csv order (the web payload's tract order)"
    counties = sorted(tr.county_fips.unique())
    code, src = {}, {}
    for f in counties:
        if f in r23.index: code[f], src[f] = int(r23[f]), "2023"
        elif f in r13.index: code[f], src[f] = int(r13[f]), "2013"
    missing = [f for f in counties if f not in code]
    assert not missing, f"counties without a RUCC code: {missing}"
    ct13 = sorted(f for f in counties if src[f] == "2013")
    assert all(f.startswith("09") for f in ct13), "only Connecticut should fall back to 2013 codes"
    tr["rucc"] = tr.county_fips.map(code); tr["metro"] = tr.rucc <= 3; tr["st"] = tr.county_fips.str[:2].map(FIPS2USPS)

    def groups(t):
        g = {"metro": group_stats(t[t.metro]), "nonmetro": group_stats(t[~t.metro]), "codes": {}}
        for c in range(1, 10):
            s = group_stats(t[t.rucc == c])
            if s: g["codes"][str(c)] = s
        return g
    nat = groups(tr); states = {st: groups(t) for st, t in tr.groupby("st")}
    # districts: share of residents 55+ living in nonmetro counties (tract shares apportion split tracts)
    rel = pd.read_csv(find("tract_cd119.csv"), dtype={"tract": str, "cd_geoid": str}); rel["share"] = rel.share.astype(float)
    rel = rel.merge(tr[["tract", "pop55", "rucc", "metro"]], on="tract", how="inner"); rel["w"] = rel.pop55 * rel.share
    dist = {}
    for k, g in rel.groupby("cd_geoid"):
        W = g.w.sum()
        if W == 0: continue
        by = g.groupby("rucc").w.sum().sort_values(ascending=False)
        dist[k] = {"nonmetro_pct": round(100 * g.w[~g.metro].sum() / W, 1), "modal": int(by.index[0]), "modal_pct": round(100 * by.iloc[0] / W, 1)}
    # county-level shares for the county pane and for validation
    cty = {}
    for f, g in tr.groupby("county_fips"):
        s = group_stats(g); cty[f] = {"c": code[f], "s": src[f], "z60": s["z60"], "l20": s["l20"], "t60": s["t60"]}
    # tract -> county index. The index refers to meta.county_order (sorted FIPS), NOT to Object.keys(DATA.counties): JavaScript
    # reorders integer-like keys numerically and leaves zero-padded ones in insertion order, so key order is not portable.
    D = json.loads(open(docs_dir() / "data.js", encoding="utf-8").read()[len("window.DATA="):].rstrip().rstrip(";"))
    ckeys = counties; cidx = {k: i for i, k in enumerate(ckeys)}
    assert set(D["counties"].keys()) == set(counties), "county sets differ between data.js and tract_access.csv"
    tidx = np.array([cidx[f] for f in tr.county_fips], np.uint16)
    assert D["meta"]["tracts_bin"]["tracts"] == len(tr)
    blob = struct.pack("<II", 0x54524332, len(tr)) + tidx.astype("<u2").tobytes()
    (docs_dir() / "tract_county.bin").write_bytes(blob)
    m, nm = nat["metro"], nat["nonmetro"]
    meta = {"source": "USDA ERS Rural-Urban Continuum Codes, 2023 release (counties); 2013 release for Connecticut's eight legacy counties only",
            "vintage": "2023", "labels": {str(k): v for k, v in CODE_LABEL.items()}, "metro_codes": [1, 2, 3], "nonmetro_codes": [4, 5, 6, 7, 8, 9],
            "ct_note": "Connecticut's 2023 codes are published for its nine planning regions; this site uses the eight legacy counties, so those carry their 2013 codes.",
            "ct_counties_2013": ct13, "built": str(date.today()), "n_counties": len(counties), "tract_county_bin": {"file": "tract_county.bin", "bytes": len(blob), "tracts": int(len(tr))}, "county_order": ckeys,
            "headline": {"nonmetro_pop_pct": round(100 * nm["p"] / (m["p"] + nm["p"]), 1), "l20_metro": m["l20"], "l20_nonmetro": nm["l20"], "z60_metro": m["z60"], "z60_nonmetro": nm["z60"],
                         "medn_metro": m["medn"], "medn_nonmetro": nm["medn"], "g60n_metro": m["g60n"], "g60n_nonmetro": nm["g60n"], "t60_metro": m["t60"], "t60_nonmetro": nm["t60"]}}
    out = {"meta": meta, "county": cty, "nat": nat, "states": states, "districts": dist}
    s = json.dumps(out, separators=(",", ":")); (docs_dir() / "rucc.js").write_text("window.RUCC=" + s + ";", encoding="utf-8")
    log = {"built": meta["built"], "counties": len(counties), "ct_2013_fallback": ct13, "code_counts": {str(c): int((pd.Series(code) == c).sum()) for c in range(1, 10)}, "headline": meta["headline"],
           "rucc_js_kb": len(s) // 1024, "tract_county_bin_bytes": len(blob)}
    (find("rucc_log.json") if Path("rucc_log.json").exists() else Path("rucc_log.json")).write_text(json.dumps(log, indent=1))
    print(json.dumps(log["headline"], indent=1)); print("rucc.js KB", len(s) // 1024, "| tract_county.bin bytes", len(blob), "| CT 2013 fallback", len(ct13))


if __name__ == "__main__":
    main()
