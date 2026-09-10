"""Disease setting ("stage") per trial, from registry title, official title and conditions.

Extent-of-disease terms:
  E (early / localized): neoadjuvant, adjuvant, early-stage, resectable (not "unresectable"), stage I–III, localized, non-metastatic, in situ
  A (advanced / metastatic / relapsed-refractory): metastatic, stage IV, unresectable, advanced (incl. locally advanced), recurrent, relapsed, refractory, castration-resistant
  N (line of therapy only): newly diagnosed, previously untreated, treatment-naive, first-line
Rules:  A and not E -> advanced;  E and not A -> early;  E and A -> multiple settings;  only N -> newly diagnosed (extent not stated);  none -> not stated.
Output: data/raw/trial_setting.csv (nct_id, setting, terms), out_adult55/setting_summary.json, out_adult55/qc_setting_sample_100.csv
"""
import json, random, re
from pathlib import Path
import pandas as pd

RAW, OUT = Path("data/raw"), Path("out_adult55")
E = re.compile(r"neoadjuvant|(?<!neo)adjuvant|early[- ]stage|early breast|(?<!un)resectable|\bstage (i{1,3}|[123])[abc]?\b(?!v)|stage (i|ii|1|2)\s*[/-]\s*(ii|iii|2|3)\b|localized|localised|non-?metastatic|in situ|\bdcis\b|high[- ]risk localized|organ[- ]confined|clinically localized", re.I)
A = re.compile(r"metasta|\bstage (iv|4)\b|unresectable|\badvanced\b|recurrent|relapsed|refractory|castration[- ]resistant|\bmcrpc\b|\bmcrc\b|\bmbc\b|\bmnsclc\b|\bcrpc\b|extensive[- ]stage|\bes-sclc\b|leptomening|oligometasta", re.I)
N = re.compile(r"newly diagnosed|previously untreated|treatment[- ]na[iï]ve|first[- ]line|\b1l\b|untreated", re.I)
LABEL = {"early": "Early-stage / localized (incl. neoadjuvant, adjuvant)", "advanced": "Advanced, metastatic, or relapsed / refractory", "multiple": "Multiple settings stated", "newdx": "Newly diagnosed, extent not stated", "not_stated": "Setting not stated"}


def classify(text):
    e, a, n = bool(E.search(text)), bool(A.search(text)), bool(N.search(text))
    if e and a: return "multiple"
    if a: return "advanced"
    if e: return "early"
    if n: return "newdx"
    return "not_stated"


def main():
    t = pd.read_csv(RAW / "trials.csv", dtype=str, keep_default_na=False)
    txt = t.brief_title + " ; " + t.official_title + " ; " + t.conditions
    t["setting"] = txt.map(classify); t["setting_terms"] = txt.map(lambda x: ";".join(sorted({m.group(0).lower() for rx in (E, A, N) for m in rx.finditer(x)})[:6]))
    t[["nct_id", "setting", "setting_terms"]].to_csv(RAW / "trial_setting.csv", index=False)
    d55 = t[pd.to_numeric(t.max_age_years, errors="coerce").fillna(999) >= 55]
    summ = {"labels": LABEL, "counts_55plus": d55.setting.map(LABEL).value_counts().to_dict(), "pct_not_stated_55plus": round(100 * (d55.setting == "not_stated").mean(), 1)}
    json.dump(summ, open(OUT / "setting_summary.json", "w"), indent=2); print(json.dumps(summ, indent=1))
    random.seed(20260910); samp = d55.iloc[sorted(random.sample(range(len(d55)), 100))][["nct_id", "brief_title", "conditions", "setting", "setting_terms"]].copy(); samp["hand_check"] = ""; samp["agree"] = ""
    samp.to_csv(OUT / "qc_setting_sample_100.csv", index=False)
    pd.set_option("display.width", 220); print(samp.head(24)[["setting", "brief_title"]].to_string(index=False, max_colwidth=100))


if __name__ == "__main__":
    main()
