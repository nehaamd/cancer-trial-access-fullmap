"""Tier 3 — county cancer incidence from NCI/CDC State Cancer Profiles (NPCR + SEER, age-adjusted, 2018-2022 in the current release).

One request per cancer site (parameterised URL, all US counties in one response). Every row gets an explicit status:
  ok                      rate published
  small_numbers           rate published but average annual count < 16 (our reliability threshold; shown with a caution, never hidden)
  suppressed_source       source suppressed the rate ("*": fewer than 16 records in the 5-year period)
  not_available_state     source carries the row but no data ("[P1 note]": state law prohibits county-level release) — Kansas
  not_available_county    county in our geography but absent from the source (e.g. Alaska's 2019 Chugach / Copper River split)
Outputs: data/ref/cancer_incidence_county.csv (long), data/ref/cancer_incidence_state.csv, data/ref/cancer_burden_log.json
"""
import io, json, re, time
from pathlib import Path
import numpy as np, pandas as pd, requests

REF = Path("data/ref"); URL = "https://statecancerprofiles.cancer.gov/incidencerates/index.php?age=001&areatype={area}&cancer={c}&race=00&sex={sex}&stage=999&stateFIPS=00&type=incd&year=0&output=1"
SITES = [("001", 0, "all"), ("055", 2, "breast"), ("020", 0, "colorectal"), ("047", 0, "lung"), ("066", 1, "prostate"), ("053", 0, "melanoma_skin"),
         ("086", 0, "lymphoma"), ("090", 0, "leukemia"), ("040", 0, "pancreatic"), ("035", 0, "liver_biliary"), ("071", 0, "bladder_urothelial"),
         ("072", 0, "kidney"), ("076", 0, "brain_cns"), ("061", 2, "gynecologic_ovary"), ("058", 2, "gynecologic_uterus"), ("057", 2, "gynecologic_cervix"),
         ("003", 0, "head_neck"), ("080", 0, "thyroid"), ("017", 0, "esophagus"), ("018", 0, "stomach")]
SMALL = 16
s = requests.Session(); s.headers["User-Agent"] = "us-trial-access-map/3.0 (research)"


def pull(code, sex, area):
    for attempt in range(3):
        try:
            r = s.get(URL.format(area=area, c=code, sex=sex), timeout=120); r.raise_for_status(); txt = r.text
            if "County,FIPS" in txt or "State,FIPS" in txt: return txt
        except Exception as e: print("  retry", code, e)
        time.sleep(3)
    raise SystemExit(f"could not fetch site {code}")


def parse(txt, area):
    lines = txt.splitlines(); title = lines[2].strip('"'); hdr = next(i for i, l in enumerate(lines) if l.startswith(("County,FIPS", "State,FIPS")))
    body = [l for l in lines[hdr:] if re.match(r'^"?[^"]*"?,\d{5},', l)]
    df = pd.read_csv(io.StringIO("\n".join([lines[hdr]] + body)), dtype=str)
    df.columns = [c.strip() for c in df.columns]
    rate_col = next(c for c in df.columns if c.startswith("Age-Adjusted")); lo, hi = df.columns[df.columns.get_loc(rate_col) + 1], df.columns[df.columns.get_loc(rate_col) + 2]
    cnt_col = "Average Annual Count"
    out = pd.DataFrame({"fips": df.FIPS.str.strip(), "name": df.iloc[:, 0].str.replace(r"\(\d+\)$", "", regex=True).str.strip(), "rate_raw": df[rate_col].str.strip(),
                        "ci_lo": pd.to_numeric(df[lo], errors="coerce"), "ci_hi": pd.to_numeric(df[hi], errors="coerce"), "count_raw": df[cnt_col].str.strip(),
                        "trend": df["Recent Trend"].str.strip() if "Recent Trend" in df else ""})
    out["rate"] = pd.to_numeric(out.rate_raw, errors="coerce"); out["avg_annual_count"] = pd.to_numeric(out.count_raw, errors="coerce")
    def status(r):
        if r.rate_raw.startswith("[P1"): return "not_available_state"
        if r.rate_raw == "*" or r.rate_raw.startswith("[") or pd.isna(r.rate): return "suppressed_source"
        if pd.isna(r.avg_annual_count) or r.avg_annual_count < SMALL: return "small_numbers"
        return "ok"
    out["status"] = out.apply(status, axis=1); out["title"] = title
    return out


def main():
    cent = pd.read_csv(REF / "county_centroids.csv", dtype=str); allf = set(cent.county_fips); log = {"sites": {}, "pulled": time.strftime("%Y-%m-%d")}
    rows, srows = [], []
    for code, sex, key in SITES:
        c = parse(pull(code, sex, "county"), "county"); st = parse(pull(code, sex, "state"), "state")
        us = c[c.fips == "00000"]; c = c[c.fips.isin(allf) | (c.fips.str[:2] != "72")]
        c = c[c.fips != "00000"]; c["site"] = key; c["site_code"] = code; c["sex"] = {0: "both", 1: "male", 2: "female"}[sex]
        present = set(c.fips); missing = sorted(allf - present)
        for f in missing:
            r = cent[cent.county_fips == f].iloc[0]
            c = pd.concat([c, pd.DataFrame([{"fips": f, "name": f"{r.county_name}, {r.state_name}", "rate_raw": "", "rate": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "count_raw": "", "avg_annual_count": np.nan,
                                              "trend": "", "status": "not_available_county", "title": c.title.iat[0], "site": key, "site_code": code, "sex": c.sex.iat[0]}])], ignore_index=True)
        c = c[c.fips.isin(allf)]; rows.append(c)
        st["site"] = key; st["site_code"] = code; srows.append(st[st.fips != "00000"])
        # reconciliation: sum of published county counts vs state-level published count, per state
        cs = c[c.status.isin(["ok", "small_numbers"])].groupby(c.fips.str[:2]).avg_annual_count.sum()
        stt = st[st.fips != "00000"].assign(s2=lambda d: d.fips.str[:2]).set_index("s2").avg_annual_count
        rec = pd.DataFrame({"county_sum": cs, "state_pub": stt}).dropna(); rec["pct_diff"] = 100 * (rec.county_sum - rec.state_pub) / rec.state_pub
        log["sites"][key] = {"title": c.title.iat[0], "status_counts": c.status.value_counts().to_dict(), "us_avg_annual_count": float(us.avg_annual_count.iat[0]) if len(us) else None,
                             "us_rate": float(us.rate.iat[0]) if len(us) else None, "county_sum_published": float(cs.sum()), "state_reconciliation": {"states": int(len(rec)), "median_abs_pct_diff": round(float(rec.pct_diff.abs().median()), 2), "max_abs_pct_diff": round(float(rec.pct_diff.abs().max()), 2), "worst": rec.pct_diff.abs().idxmax() if len(rec) else None}}
        print(key, log["sites"][key]["status_counts"], "| state recon median|max %:", log["sites"][key]["state_reconciliation"]["median_abs_pct_diff"], log["sites"][key]["state_reconciliation"]["max_abs_pct_diff"], flush=True)
        time.sleep(1)
    df = pd.concat(rows, ignore_index=True).rename(columns={"fips": "county_fips"})
    df[["county_fips", "site", "site_code", "sex", "title", "rate", "ci_lo", "ci_hi", "avg_annual_count", "count_raw", "trend", "status"]].to_csv(REF / "cancer_incidence_county.csv", index=False)
    pd.concat(srows, ignore_index=True).rename(columns={"fips": "state_fips"}).to_csv(REF / "cancer_incidence_state.csv", index=False)
    log["small_numbers_threshold_avg_annual_cases"] = SMALL
    log["states_not_available"] = sorted(df[df.status == "not_available_state"].county_fips.str[:2].unique().tolist())
    log["counties_not_in_source_all_sites"] = df[(df.site == "all") & (df.status == "not_available_county")].county_fips.tolist()
    json.dump(log, open(REF / "cancer_burden_log.json", "w"), indent=2); print(json.dumps({k: v for k, v in log.items() if k != "sites"}, indent=1))


if __name__ == "__main__":
    main()
