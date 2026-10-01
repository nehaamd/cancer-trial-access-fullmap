"""Build docs/findings.js: the few numbers the Key findings page needs, taken from the pipeline outputs so the page
stays current after a refresh without loading the 7 MB map payload.

Inputs (repository root or the pipeline folders): data.js, national_metrics_v3.json, state_metrics_v3.csv, rucc.js,
burden.js, cosponsors.js. Run after build_webapp_data_v3.py / build_rucc.py / build_burden_access.py / fetch_cosponsors.py:
    python3 build_findings.py
"""
import json, sys, datetime
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent

def find(name):
    for d in (ROOT, ROOT / "docs", ROOT / "out_adult55", ROOT / "data" / "ref"):
        if (d / name).exists(): return d / name
    sys.exit(f"missing input: {name}")

def load_js(name):
    s = find(name).read_text(); return json.loads(s.split("=", 1)[1].strip().rstrip(";"))

D = load_js("data.js"); RU = load_js("rucc.js"); BU = load_js("burden.js"); CO = load_js("cosponsors.js")
nat = json.load(open(find("national_metrics_v3.json")))
st = pd.read_csv(find("state_metrics_v3.csv"), dtype={"state_fips": str})

FIPS2USPS = {"01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE","11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA","20":"KS","21":"KY","22":"LA","23":"ME","24":"MD","25":"MA","26":"MI","27":"MN","28":"MS","29":"MO","30":"MT","31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM","36":"NY","37":"NC","38":"ND","39":"OH","40":"OK","41":"OR","42":"PA","44":"RI","45":"SC","46":"SD","47":"TN","48":"TX","49":"UT","50":"VT","51":"VA","53":"WA","54":"WV","55":"WI","56":"WY"}
SD = D["state_data"]; DI = D["districts"]; meta = D["meta"]; core = meta["nat_core"]

def none_if_noroad(v): return None if v is None or v >= 999 else int(v)

states = []
for _, r in st.iterrows():
    usps = FIPS2USPS.get(r.state_fips)
    if not usps or usps not in SD: continue
    s = SD[usps]; ru = RU["states"].get(usps) or {}
    nm = ru.get("nonmetro"); m = ru.get("metro")
    states.append({"usps": usps, "name": s["name"], "pop55": int(r.pop55), "l20": float(r.pct_lt20_trials_within_60rdmi), "z60": float(r.pct_zero_trials_within_60rdmi),
                   "g60b": float(r.pct_gt60rdmi_broad_menu), "g60n": float(r.pct_gt60rdmi_nci), "medn": none_if_noroad(r.median_road_mi_nci), "t60": int(r.wmean_trials_within_60rdmi),
                   "counties": s["counties"], "broad": s["broad"], "limited": s["limited"], "trials": s["trials"], "ndist": s["ndist"],
                   "nonmetro_pct": round(100 * nm["p"] / (nm["p"] + m["p"]), 1) if nm and m and (nm["p"] + m["p"]) else None,
                   "nonmetro_l20": round(nm["l20"], 1) if nm else None, "metro_l20": round(m["l20"], 1) if m else None})
states.sort(key=lambda x: -x["l20"])

worst_d = sorted(DI.items(), key=lambda kv: -kv[1]["l20"])[:10]
districts = {"n": len(DI), "all_beyond_60_broad": sum(1 for d in DI.values() if d["g60b"] >= 99.95), "half_lt20": sum(1 for d in DI.values() if d["l20"] >= 50),
             "worst": [{"k": k, "label": f"{d['st']}-{'AL' if d['cd'] in ('0', '98') else d['cd']}", "member": d.get("member"), "party": d.get("party"), "l20": d["l20"], "z60": d["z60"], "medn": d.get("medn"), "pop55": d["p"]} for k, d in worst_d]}

bills = []
for k, b in CO["bills"].items():
    sp = CO["members"][b["sponsor"]]
    bills.append({"key": k, "label": b["label"], "short": b["short"], "chamber": "House" if b["type"] == "hr" else "Senate", "url": b.get("url"), "introduced": b["introduced"],
                  "sponsor": f"{sp['name']} ({sp['party']}-{sp['state']})", "n_cosponsors": b["n_cosponsors"], "parties": b["parties"], "latest_action": b["latest_action"], "topic": b.get("topic")})

out = {
    "built": datetime.date.today().isoformat(),
    "meta": {"pull": meta["pull"], "registry_data_timestamp": meta.get("registry_data_timestamp"), "trials": meta["trials"], "facilities": meta["facilities"], "sitepoints": meta["sitepoints"],
             "plan": meta["plan"], "incidence_period": meta["burden"]["period"], "members_pull": meta["members_pull"].split(" ")[0], "cosponsors_fetched": CO["meta"]["fetched"], "router": meta["router"], "n_tracts": core["nt"], "n_nci": len(D["nci"])},
    "nat": {**{k: core[k] for k in ("p", "l20", "z60", "l100", "zc", "g60b", "g120b", "g60l", "g60n", "g120n", "nr", "medb", "medn", "medl", "t30", "t60", "t120", "own")},
            "people_l20": int(round(core["p"] * core["l20"] / 100)), "people_z60": int(round(core["p"] * core["z60"] / 100)), "people_g60n": int(round(core["p"] * core["g60n"] / 100)), "people_g60b": int(round(core["p"] * core["g60b"] / 100))},
    "rural": {"metro": RU["nat"]["metro"], "nonmetro": RU["nat"]["nonmetro"]},
    "states": states, "states_no_broad": sum(1 for s in states if s["broad"] == 0), "states_no_broad_list": [s["name"] for s in sorted(states, key=lambda x: x["name"]) if s["broad"] == 0],
    "districts": districts,
    "burden": {k: BU["summary"]["nat"][k] for k in ("hb_la_counties", "hb_la_pop55", "hb_la_cases", "counties_classified")},
    "bills": bills, "topics": CO["meta"].get("topics", {}),
}
DOCS = ROOT / "docs" if (ROOT / "docs").is_dir() and not (ROOT / "data.js").exists() else ROOT
Path(DOCS / "findings.js").write_text("window.FINDINGS=" + json.dumps(out, separators=(",", ":")) + ";")
print("findings.js written:", len(states), "states;", out["states_no_broad"], "states with no broad-menu county;", districts["all_beyond_60_broad"], "districts fully beyond 60 mi of a broad menu;", [(b["label"], b["n_cosponsors"]) for b in bills])
