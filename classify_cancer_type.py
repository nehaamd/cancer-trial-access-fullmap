"""Tier 2.3 — classify each trial into one major cancer category, or an explicit multi-cancer / basket bucket.

Input:  data/raw/trials.csv (conditions, keywords, brief_title, official_title)
Output: data/raw/trial_cancer_type.csv   (nct_id, cancer_type, multi_subtype, categories_matched, generic_listed, source)
        out_adult55/cancer_type_summary.json
        out_adult55/qc_cancer_type_sample_200.csv   (random sample for hand check; see VALIDATION note on self-checks)

Rules (applied to each registry condition string separately, then combined):
  S = set of named categories matched across condition strings; G = a generic/basket term was listed.
  |S| >= 2                      -> multi  ("multiple named cancers")
  |S| == 1, not G               -> that category
  |S| == 1, G, title is generic -> multi  ("basket with a named cohort")   [title mentions solid tumours etc. but not the category]
  |S| == 1, G, otherwise        -> that category (generic term treated as registry boilerplate; flagged generic_listed=1)
  |S| == 0, G                   -> multi  ("unspecified solid / haematologic")
  |S| == 0, not G               -> fall back to title + keywords; 1 hit -> that category; >=2 -> multi; 0 -> other_unclassified
"""
import json, re, random
from pathlib import Path
import pandas as pd

RAW, OUT = Path("data/raw"), Path("out_adult55")
I = re.I

CATS = {  # order matters only for display
 "breast":        r"breast|\btnbc\b|\bhr\+?/her2|mammary|ductal carcinoma in situ|\bdcis\b|lobular carcinom",
 "lung":          r"lung|\bnsclc\b|\bsclc\b|mesotheliom|bronch|thymom|thymic|pleural|pulmonary (neoplasm|cancer|carcinom|nodule)",
 "colorectal":    r"colorectal|\bcolon\b|colonic|rectal|rectum|\bcrc\b|\bmcrc\b",
 "prostate":      r"prostat|\bcrpc\b|\bmcrpc\b|\bmhspc\b|\bcspc\b|\bhspc\b",
 "melanoma_skin": r"melanom|merkel|basal cell carcinom|cutaneous squamous|\bcscc\b|skin (cancer|neoplasm|carcinom)|nonmelanoma|non-melanoma",
 "lymphoma":      r"lymphom|hodgkin|waldenstr|\bdlbcl\b|\bctcl\b|\bptcl\b|mycosis fungoides|sezary|\bnhl\b|\bmcl\b|\bpmbcl\b|richter|lymphoproliferative|castleman",
 "leukemia":      r"leuk|\baml\b|\bcll\b|\bcml\b|\bsll\b|\bapl\b|hairy cell|blastic plasmacytoid",
 "myeloma":       r"myelom|plasma cell|plasmacytom|amyloidosis|\bmgus\b|smoldering|light chain",
 "mds_mpn":       r"myelodysplas|\bmds\b|myelofibrosis|polycythemia|thrombocythemia|myeloproliferative|\bmpn\b|\bcmml\b|mastocytosis",
 "pancreatic":    r"pancrea|\bpdac\b",
 "liver_biliary": r"hepatocellular|\bhcc\b|liver (cancer|neoplasm|carcinom|tumou?r)|hepatobiliary|cholangio|biliary|gallbladder|bile duct|hepatoblastom|fibrolamellar",
 "gastric_esophageal": r"gastric|stomach|esophag|oesophag|gastroesophageal|gastro-esophageal|\bgej\b|\bgea\b",
 "gynecologic":   r"ovar|endometri|cervical (cancer|carcinom|neoplasm|squamous|adenocarcinom|intraepithelial)|cervix|uterine|uterus|fallopian|primary peritoneal|vulva|vagina|gynecolog|trophoblast|leiomyosarcom",
 "bladder_urothelial": r"bladder|urothel|\bnmibc\b|\bmibc\b|upper (urinary )?tract|urinary tract|ureter",
 "kidney":        r"kidney|renal cell|renal (cancer|carcinom|neoplasm|tumou?r)|\brcc\b|\bccrcc\b|wilms|nephroblastom",
 "brain_cns":     r"glio|\bgbm\b|astrocytom|brain (tumou?r|cancer|neoplasm|stem)|cns (tumou?r|neoplasm|cancer)|meningiom|ependymom|medulloblastom|oligodendro|central nervous system (tumou?r|neoplasm|cancer)|diffuse midline|\bdipg\b|craniopharyngiom|pituitary|neuro-?oncolog|\bhgg\b|\blgg\b",
 "head_neck":     r"head and neck|head & neck|\bhnscc\b|\bscchn\b|oral cavity|oropharyn|laryn|pharyn|nasopharyn|hypopharyn|salivary|tongue|sinonasal|oral (cancer|squamous|carcinom)|tonsil|lip cancer|adenoid cystic",
 "sarcoma":       r"sarcom|\bgist\b|gastrointestinal stromal|desmoid|osteosarcom|ewing|rhabdomyo|liposarcom|chondrosarcom|chordom|synovial|fibromatosis|nerve sheath|\bmpnst\b|giant cell tumou?r of bone|bone (cancer|tumou?r)",
 "neuroendocrine_endocrine": r"thyroid|adrenocortical|adrenal (cancer|carcinom|cortical)|pheochromocytom|paragangliom|neuroendocrin|\bnet\b|\bnets\b|carcinoid|parathyroid",
 "other_named":   r"testic|germ cell|seminom|penile|neuroblastom|retinoblastom|anal (cancer|carcinom|canal|squamous)|appendi|small bowel|small intestin|unknown primary|kaposi|uveal|ocular|eye (cancer|neoplasm)|urethral|peritoneal mesotheliom|histiocyt|langerhans|erdheim|nut carcinom|nut midline",
}
# per-string precedence: if the left regex matches a condition string, only the listed categories are kept for that string
PRECEDENCE = [
 (r"small lymphocytic lymphoma|\bsll\b", {"leukemia"}),                   # CLL/SLL is one disease
 (r"myelomonocytic|atypical chronic myeloid", {"mds_mpn"}),                                         # CMML/JMML are MDS/MPN overlap entities, not "leukemia" for this purpose
 (r"plasma cell leukemia", {"myeloma"}),                                   # a plasma-cell disorder
 (r"gliosarcom", {"brain_cns"}),                                           # a glioblastoma variant, not a sarcoma
 (r"leiomyosarcom", {"sarcoma"}),                                          # uterine leiomyosarcoma is a sarcoma
 (r"neck.*unknown primary|unknown primary.*neck", {"head_neck"}),
 (r"lymphoblastic lymphoma", {"lymphoma", "leukemia"}),                   # keep both; combined trials are genuinely two entities
 (r"neuroendocrin|carcinoid", {"neuroendocrine_endocrine"}),               # pancreatic/lung NET -> NET, not the organ
 (r"cutaneous t-cell|cutaneous b-cell|cutaneous lymphom", {"lymphoma"}),
 (r"primary cns lymphom|cns lymphom|central nervous system lymphom", {"lymphoma"}),
 (r"uveal|ocular melanom|conjunctival melanom", {"melanoma_skin"}),
 (r"lung metasta|pulmonary metasta|brain metasta|cns metasta|leptomening|liver metasta|hepatic metasta|bone metasta|peritoneal metasta|carcinomatosis|spinal metasta|metastatic disease to", set()),  # metastatic *site*, not a primary
]
GENERIC = re.compile(r"solid tumou?r|solid neoplasm|solid malignan|advanced cancer|advanced malignan|metastatic cancer|metastatic malignan|^cancers?$|^neoplasms?$|^tumou?rs?$|^malignan(t|cy|cies)|malignan(t|cy|cies)$|"
                     r"hematologic(al)? (malignan|cancer|neoplasm)|blood cancer|^carcinoma$|^adenocarcinoma$|^metasta(tic|sis|ses)$|refractory cancer|recurrent cancer|rare (cancer|tumou?r|disease)|"
                     r"^(advanced|metastatic|recurrent|refractory|relapsed|unresectable|locally advanced)( or [a-z]+)? (cancer|carcinoma|neoplasm|malignan|disease|tumou?r)s?$|"
                     r"multiple (cancer|tumou?r)|various (cancer|tumou?r)|pan-?cancer|tumor agnostic|tumou?r-agnostic|any cancer|all cancer|different cancer|"
                     r"lung metasta|brain metasta|liver metasta|bone metasta|peritoneal metasta|spinal metasta|neoplasm metasta|carcinomatosis|leptomening|oligometasta|hematopoietic and lymphoid|gastrointestinal (neoplasm|cancer|tumou?r|malignan|carcinom)|genitourinary (neoplasm|cancer|tumou?r|malignan)|thoracic (neoplasm|cancer|tumou?r|malignan)|gynecologic(al)? (neoplasm|cancer|tumou?r|malignan)|"
                     r"^(cancer|malignan|neoplasm|tumou?r)[a-z]* (of|in) (the )?(elderly|adult|child|older)", I)
CATRX = {k: re.compile(v, I) for k, v in CATS.items()}
PRERX = [(re.compile(p, I), keep) for p, keep in PRECEDENCE]
CASE_SENS = {"leukemia": re.compile(r"\bB-ALL\b|\bT-ALL\b|\bALL\b(?![a-z])"), "lymphoma": re.compile(r"\bHL\b|\bFL\b|\bMZL\b"),
             "myeloma": re.compile(r"\bMM\b"), "kidney": re.compile(r"\bRCC\b"), "gynecologic": re.compile(r"\bOC\b"), "neuroendocrine_endocrine": re.compile(r"\bNET\b")}
LABEL = {"breast": "Breast", "lung": "Lung & thoracic", "colorectal": "Colorectal", "prostate": "Prostate", "melanoma_skin": "Melanoma & skin",
         "lymphoma": "Lymphoma", "leukemia": "Leukemia", "myeloma": "Myeloma & plasma cell", "mds_mpn": "MDS & MPN", "pancreatic": "Pancreatic",
         "liver_biliary": "Liver & biliary", "gastric_esophageal": "Gastric & esophageal", "gynecologic": "Gynecologic (ovarian, uterine, cervical)",
         "bladder_urothelial": "Bladder & urothelial", "kidney": "Kidney", "brain_cns": "Brain & CNS", "head_neck": "Head & neck", "sarcoma": "Sarcoma",
         "neuroendocrine_endocrine": "Neuroendocrine & endocrine", "other_named": "Other named cancer",
         "multi": "Multiple cancer types / basket or umbrella", "other_unclassified": "Other / unclassified"}


def cats_in(s):
    s = s.strip()
    if not s: return set()
    found = {k for k, rx in CATRX.items() if rx.search(s)} | {k for k, rx in CASE_SENS.items() if rx.search(s)}
    for rx, keep in PRERX:
        if rx.search(s): found &= keep; break
    return found


def classify(conds, keywords, title, otitle):
    strings = [x for x in conds.split(";")]
    S, G = set(), False
    for s in strings:
        S |= cats_in(s); G = G or bool(GENERIC.search(s.strip()))
    src = "conditions"
    if len(S) >= 2: return "multi", "multiple named cancers", S, G, src
    if len(S) == 1:
        c = next(iter(S)); t = f"{title} {otitle}"
        if G and GENERIC.search(t) and not (CATRX[c].search(t) or (c in CASE_SENS and CASE_SENS[c].search(t))):
            return "multi", "basket with a named cohort", S, G, "conditions+title"
        extra = cats_in(title) - S
        if G and extra: return "multi", "title names additional cancers", S | extra, G, "conditions+title"
        return c, "", S, G, src
    if G: return "multi", "unspecified solid / hematologic", S, G, src
    T = set()
    for s in [title, otitle] + keywords.split(";"): T |= cats_in(s)
    if len(T) == 1: return next(iter(T)), "", T, G, "title/keywords"
    if len(T) >= 2: return "multi", "multiple named cancers (title/keywords)", T, G, "title/keywords"
    if GENERIC.search(f"{title} {otitle}"): return "multi", "unspecified (title)", T, True, "title"
    return "other_unclassified", "", set(), G, "none"


def main():
    t = pd.read_csv(RAW / "trials.csv", dtype=str, keep_default_na=False)
    rows = []
    for r in t.itertuples():
        c, sub, S, G, src = classify(r.conditions, getattr(r, "keywords", ""), r.brief_title, getattr(r, "official_title", ""))
        rows.append({"nct_id": r.nct_id, "cancer_type": c, "cancer_type_label": LABEL[c], "multi_subtype": sub,
                     "categories_matched": ";".join(sorted(S)), "generic_listed": int(G), "source": src})
    df = pd.DataFrame(rows); df.to_csv(RAW / "trial_cancer_type.csv", index=False)
    elig = t[pd.to_numeric(t.max_age_years, errors="coerce").fillna(999) >= 55].nct_id
    d55 = df[df.nct_id.isin(elig)]
    summ = {"trials_all": len(df), "trials_55plus": len(d55),
            "counts_55plus": d55.cancer_type_label.value_counts().to_dict(),
            "pct_multi_55plus": round(100 * (d55.cancer_type == "multi").mean(), 1),
            "pct_unclassified_55plus": round(100 * (d55.cancer_type == "other_unclassified").mean(), 1),
            "multi_subtypes_55plus": d55[d55.cancer_type == "multi"].multi_subtype.value_counts().to_dict(),
            "source_55plus": d55.source.value_counts().to_dict()}
    OUT.mkdir(exist_ok=True); json.dump(summ, open(OUT / "cancer_type_summary.json", "w"), indent=2)
    print(json.dumps(summ, indent=1))
    # hand-check sample (fixed seed so the file is reproducible)
    random.seed(20260909)
    samp = d55.merge(t[["nct_id", "brief_title", "conditions"]], on="nct_id")
    samp = samp.iloc[sorted(random.sample(range(len(samp)), 200))]
    samp["hand_check_category"] = ""; samp["agree"] = ""
    samp[["nct_id", "brief_title", "conditions", "cancer_type_label", "multi_subtype", "categories_matched", "hand_check_category", "agree"]].to_csv(OUT / "qc_cancer_type_sample_200.csv", index=False)
    unc = d55[d55.cancer_type == "other_unclassified"].merge(t[["nct_id", "brief_title", "conditions"]], on="nct_id")
    unc.to_csv(OUT / "qc_cancer_type_unclassified.csv", index=False)
    print("\nunclassified examples:"); print(unc[["nct_id", "brief_title", "conditions"]].head(25).to_string(index=False, max_colwidth=70))


if __name__ == "__main__":
    main()
