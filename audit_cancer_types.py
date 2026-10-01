"""Classification audit: runs after classify_cancer_type.py and before anything is published.

Lists the condition strings that could pull a trial into the wrong cancer type, so a person reviews only what is new:
  1. a category matched by a stem that starts inside a longer word (the 'anorectal melanoma', 'gallbladder', 'paraganglioma' class of error)
  2. a category matched by a string that reads as non-neoplastic or supportive care (hypothyroidism, infection, lymphedema, ...)
  3. a string that names melanoma and still reaches another category
Every string already reviewed is listed in audit_allowlist.txt (one per line, "category<TAB>condition string"); the audit exits non-zero
when a string not on that list appears, which holds the weekly refresh until someone looks. Output: qc_cancer_type_audit.md.
    python3 audit_cancer_types.py            # audit; exit 1 if there is anything new to review
    python3 audit_cancer_types.py --accept   # add everything currently listed to the allowlist (after reviewing it)
"""
import re, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
def find(name):
    for d in (ROOT, ROOT / "data" / "raw", ROOT / "out_adult55", ROOT / "docs"):
        if (d / name).exists(): return d / name
    sys.exit(f"missing input: {name}")

src = (ROOT / "classify_cancer_type.py").read_text(); ns = {}
exec(src.split("def classify(")[0].replace('RAW, OUT = Path("data/raw"), Path("out_adult55")', ''), ns)
CATRX, cats_in = ns["CATRX"], ns["cats_in"]
NONNEO = re.compile(r"hypothyroid|hyperthyroid|thyroiditis|toxicit|mucositis|dermatitis|neuropath|cachexia|fatigue|\bpain\b|nausea|vomiting|infection|vaccin|survivor|quality of life|screening|prevention|hyperplasia|colitis|pneumonitis|lymphedema|anemia|depression|anxiety|insomnia|cognitive|hot flash|menopaus|fertility|nutrition|obesity|exercise|smoking|alcohol|caregiver|diversion|operations|healthy|donor|benign|premalignant|dysplasia|polyp|hepatitis|cirrhosis|diabetes|hypertension|cardio|renal (failure|insufficiency|impairment)|hepatic (failure|impairment)", re.I)

tr = pd.read_csv(find("trials.csv"), dtype=str).fillna("")
conds = {}
for _, r in tr.iterrows():
    for c in r.conditions.split(";"):
        c = c.strip()
        if c: conds.setdefault(c, set()).add(r.nct_id)
items = []  # (kind, category, condition, n_trials, example)
for c, ncts in sorted(conds.items()):
    cats = cats_in(c)
    if not cats: continue
    for k, rx in CATRX.items():
        if k not in cats: continue
        ms = list(rx.finditer(c))
        if ms and all(m.start() > 0 and c[m.start() - 1].isalpha() for m in ms):   # every match of this category's stems begins mid-word
            items.append(("inside a longer word", k, c, len(ncts), sorted(ncts)[0]))
    if NONNEO.search(c):
        for k in sorted(cats): items.append(("reads as non-neoplastic or supportive", k, c, len(ncts), sorted(ncts)[0]))
    if re.search(r"melanom", c, re.I) and not re.search(r"non-?melanoma", c, re.I) and cats - {"melanoma_skin"}:
        for k in sorted(cats - {"melanoma_skin"}): items.append(("melanoma string reaching another category", k, c, len(ncts), sorted(ncts)[0]))

allow_path = ROOT / "audit_allowlist.txt"; allow = set()
if allow_path.exists():
    for line in allow_path.read_text().splitlines():
        if "\t" in line: k, c = line.split("\t", 1); allow.add((k, c))
new = [x for x in items if (x[1], x[2]) not in allow]
md = ["# Cancer-type classification audit", "", f"{len(conds):,} distinct condition strings across {len(tr):,} eligible trials · {len(items)} strings flagged · **{len(new)} not yet reviewed**", ""]
for title, kind in (("Matched inside a longer word", "inside a longer word"), ("Reads as non-neoplastic or supportive care", "reads as non-neoplastic or supportive"), ("Names melanoma and reaches another category", "melanoma string reaching another category")):
    rows = [x for x in items if x[0] == kind]
    md += [f"## {title} ({len(rows)})", "", "| Reviewed | Category | Condition string | Trials | Example |", "|---|---|---|---|---|"]
    md += [f"| {'yes' if (x[1], x[2]) in allow else '**NEW**'} | {x[1]} | {x[2]} | {x[3]} | {x[4]} |" for x in rows] + [""]
md += ["A flagged string is not necessarily wrong (myelofibrosis reads as fibrosis but is an MPN). Review the NEW rows: fix the pattern in classify_cancer_type.py if the category is wrong, otherwise run `python3 audit_cancer_types.py --accept` to record that they were reviewed.", ""]
((ROOT / "out_adult55") if (ROOT / "out_adult55").is_dir() else ROOT).joinpath("qc_cancer_type_audit.md").write_text("\n".join(md))
if "--accept" in sys.argv:
    allow |= {(x[1], x[2]) for x in items}; allow_path.write_text("\n".join(f"{k}\t{c}" for k, c in sorted(allow)) + "\n"); print(f"allowlist now has {len(allow)} reviewed strings"); sys.exit(0)
print(f"{len(items)} flagged strings, {len(new)} new to review (out_adult55/qc_cancer_type_audit.md)")
for x in new[:40]: print(f"  NEW  [{x[0]}] {x[1]}: {x[2]}  ({x[3]} trial{'s' if x[3] != 1 else ''}, e.g. {x[4]})")
sys.exit(1 if new else 0)
