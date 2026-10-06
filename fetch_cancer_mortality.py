"""County cancer death rates from NCI/CDC State Cancer Profiles (National Vital Statistics System; age-adjusted; 2020-2024 in the
current release). The companion of fetch_cancer_burden.py (incidence): same 20 sites, same statuses, same reconciliation.

One request per cancer site (all US counties in one response), one more for the state table. Every row gets an explicit status:
  ok                      rate published
  small_numbers           rate published but average annual deaths < 16 (our reliability threshold; shown with a caution, never hidden)
  suppressed_source       source suppressed the rate ("*": 3 or fewer deaths a year on average)
  not_available_state     source carries the row but no data (none in the death table: NVSS data are released for every state)
  not_available_county    county in our geography but absent from the source: Alaska's 2019 Chugach / Copper River split (the source
                          still reports the former Valdez-Cordova Census Area, 02261)
The source reports Bedford County, Virginia under the combined code 51917 (county + the former independent city, merged in 2013);
that row is carried as 51019.
Outputs: data/ref/cancer_mortality_county.csv (long), data/ref/cancer_mortality_state.csv, data/ref/cancer_mortality_log.json
Re-run when State Cancer Profiles moves to a new five-year window (the title line carries the years); the refresh reuses the CSVs.
"""
import io, json, re, time
from pathlib import Path
import numpy as np, pandas as pd, requests

REF = Path("data/ref")
URL = "https://statecancerprofiles.cancer.gov/deathrates/index.php?stateFIPS=00&areatype={area}&cancer={c}&race=00&sex={sex}&age=001&year=0&type=death&output=1"
SITES = [("001", 0, "all"), ("055", 2, "breast"), ("020", 0, "colorectal"), ("047", 0, "lung"), ("066", 1, "prostate"), ("053", 0, "melanoma_skin"),
         ("086", 0, "lymphoma"), ("090", 0, "leukemia"), ("040", 0, "pancreatic"), ("035", 0, "liver_biliary"), ("071", 0, "bladder_urothelial"),
         ("072", 0, "kidney"), ("076", 0, "brain_cns"), ("061", 2, "gynecologic_ovary"), ("058", 2, "gynecologic_uterus"), ("057", 2, "gynecologic_cervix"),
         ("003", 0, "head_neck"), ("080", 0, "thyroid"), ("017", 0, "esophagus"), ("018", 0, "stomach")]
SMALL = 16
REMAP = {"51917": "51019"}   # source code -> our geography
s = requests.Session(); s.headers["User-Agent"] = "us-trial-access-map/3.0 (research)"


def pull(code, sex, area):
    for attempt in range(3):
        try:
            r = s.get(URL.format(area=area, c=code, sex=sex), timeout=120); r.raise_for_status(); txt = r.text
            if "County,FIPS" in txt or "State,FIPS" in txt: return txt
        except Exception as e: print("  retry", code, e)
        time.sleep(3)
    raise SystemExit(f"could not fetch site {code}")


def parse(txt):
    lines = txt.splitlines(); title = lines[2].strip('"'); who = lines[4].strip('"') if len(lines) > 4 else ""
    hdr = next(i for i, l in enumerate(lines) if l.startswith(("County,FIPS", "State,FIPS")))
    body = [l for l in lines[hdr:] if re.match(r'^"?[^"]*"?,\d{5},', l)]
    df = pd.read_csv(io.StringIO("\n".join([lines[hdr]] + body)), dtype=str)
    df.columns = [c.strip() for c in df.columns]
    rate_col = next(c for c in df.columns if c.startswith("Age-Adjusted")); lo, hi = df.columns[df.columns.get_loc(rate_col) + 1], df.columns[df.columns.get_loc(rate_col) + 2]
    out = pd.DataFrame({"fips": df.FIPS.str.strip(), "name": df.iloc[:, 0].str.replace(r"\(\d+\)$", "", regex=True).str.strip(), "rate_raw": df[rate_col].str.strip(),
                        "ci_lo": pd.to_numeric(df[lo].str.strip(), errors="coerce"), "ci_hi": pd.to_numeric(df[hi].str.strip(), errors="coerce"), "count_raw": df["Average Annual Count"].str.strip(),
                        "trend": df["Recent Trend"].str.strip() if "Recent Trend" in df else ""})
    out["rate"] = pd.to_numeric(out.rate_raw, errors="coerce"); out["avg_annual_count"] = pd.to_numeric(out.count_raw, errors="coerce")
    def status(r):
        if r.rate_raw.startswith("[P1"): return "not_available_state"
        if r.rate_raw == "*" or r.rate_raw.startswith("[") or pd.isna(r.rate): return "suppressed_source"
        if pd.isna(r.avg_annual_count) or r.avg_annual_count < SMALL: return "small_numbers"
        return "ok"
    out["status"] = out.apply(status, axis=1); out["title"] = title; out["who"] = who
    m = re.search(r"(\d{4})-(\d{4})", title); out["period"] = m.group(0) if m else ""
    return out


def main():
    cent = pd.read_csv(REF / "county_centroids.csv", dtype=str); allf = set(cent.county_fips); log = {"sites": {}, "pulled": time.strftime("%Y-%m-%d"), "source": "NCI/CDC State Cancer Profiles, death rates (NVSS), age-adjusted, all ages"}
    rows, srows = [], []
    for code, sex, key in SITES:
        c = parse(pull(code, sex, "county")); st = parse(pull(code, sex, "state"))
        c["fips"] = c.fips.replace(REMAP)
        us = c[c.fips == "00000"]; c = c[(c.fips != "00000") & (c.fips.str[:2] != "72")]
        c["site"] = key; c["site_code"] = code; c["sex"] = {0: "both", 1: "male", 2: "female"}[sex]
        extra = sorted(set(c.fips) - allf); c = c[c.fips.isin(allf)]
        present = set(c.fips); missing = sorted(allf - present)
        for f in missing:
            r = cent[cent.county_fips == f].iloc[0]
            c = pd.concat([c, pd.DataFrame([{"fips": f, "name": f"{r.county_name}, {r.state_name}", "rate_raw": "", "rate": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "count_raw": "", "avg_annual_count": np.nan,
                                              "trend": "", "status": "not_available_county", "title": c.title.iat[0], "who": c.who.iat[0], "period": c.period.iat[0], "site": key, "site_code": code, "sex": c.sex.iat[0]}])], ignore_index=True)
        rows.append(c); st["site"] = key; st["site_code"] = code; srows.append(st[st.fips != "00000"])
        # reconciliation: sum of published county counts vs the state-level published count, per state; and vs the source's own US line
        cs = c[c.status.isin(["ok", "small_numbers"])].groupby(c.fips.str[:2]).avg_annual_count.sum()
        stt = st[st.fips != "00000"].assign(s2=lambda d: d.fips.str[:2]).set_index("s2").avg_annual_count
        rec = pd.DataFrame({"county_sum": cs, "state_pub": stt}).dropna(); rec["pct_diff"] = 100 * (rec.county_sum - rec.state_pub) / rec.state_pub
        log["sites"][key] = {"title": c.title.iat[0], "who": c.who.iat[0], "period": c.period.iat[0], "status_counts": c.status.value_counts().to_dict(), "rows_not_in_geography": extra,
                             "us_avg_annual_count": float(us.avg_annual_count.iat[0]) if len(us) else None, "us_rate": float(us.rate.iat[0]) if len(us) else None, "county_sum_published": float(cs.sum()),
                             "state_reconciliation": {"states": int(len(rec)), "median_abs_pct_diff": round(float(rec.pct_diff.abs().median()), 2), "max_abs_pct_diff": round(float(rec.pct_diff.abs().max()), 2), "worst": rec.pct_diff.abs().idxmax() if len(rec) else None}}
        print(key, c.period.iat[0], log["sites"][key]["status_counts"], "| US rate", log["sites"][key]["us_rate"], "| state recon median|max %:", log["sites"][key]["state_reconciliation"]["median_abs_pct_diff"], log["sites"][key]["state_reconciliation"]["max_abs_pct_diff"], flush=True)
        time.sleep(1)
    df = pd.concat(rows, ignore_index=True).rename(columns={"fips": "county_fips"})
    df[["county_fips", "site", "site_code", "sex", "title", "period", "rate", "ci_lo", "ci_hi", "avg_annual_count", "count_raw", "trend", "status"]].to_csv(REF / "cancer_mortality_county.csv", index=False)
    pd.concat(srows, ignore_index=True).rename(columns={"fips": "state_fips"})[["state_fips", "name", "site", "site_code", "title", "period", "rate", "ci_lo", "ci_hi", "avg_annual_count", "trend", "status"]].to_csv(REF / "cancer_mortality_state.csv", index=False)
    log["small_numbers_threshold_avg_annual_deaths"] = SMALL; log["remap"] = REMAP
    log["counties_not_available"] = sorted(df[(df.site == "all") & (df.status == "not_available_county")].county_fips.tolist())
    log["periods"] = sorted(df.period.unique().tolist())
    json.dump(log, open(REF / "cancer_mortality_log.json", "w"), indent=1)
    a = log["sites"]["all"]
    print(f"\nall sites {a['period']}: US rate {a['us_rate']} per 100,000, {a['us_avg_annual_count']:,.0f} deaths a year; county sum of published counts {a['county_sum_published']:,.0f}; "
          f"counties {sum(a['status_counts'].values())}: {a['status_counts']}; not available: {log['counties_not_available']}")


if __name__ == "__main__":
    main()
