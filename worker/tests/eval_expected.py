"""Expected facts for the live evaluation (worker/tests/eval.js), computed from the raw published files and never from the engine.

    python3 -I worker/tests/eval_expected.py          -> writes worker/tests/eval_expected.json

(The engine unit tests have their own worker/tests/expected.py -> expected.json; this file is deliberately named differently.)

Every value follows the catalog's definitions (docs/ask/catalog.js): "short of trials" = pct_lt20_trials_within_60rdmi >= 50
at the default line; rural = metro false (RUCC 4-9); "oncologists but no trials" = oncologists.class == 2; high incidence x low
access = incidence_above_county_median AND pct_lt20 >= 50; high deaths x low access = mortality_top_third AND pct_lt20 >= 50;
rankings break ties by residents 55+ descending then name, nulls last (the query tool's order_by rule). Where a question has two
honest readings both are computed and the question's check says any_of.

Output: {"built", "data_as_of", "questions": {id: {"ids": [...], "numbers": {...}, "place_first": {...}, ...}}}. Keys are
referred to by name from eval_questions.json (ids_key, numbers_present entries, place_first.key, ambiguous_offers.key).
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

def load_json(p): return json.load(open(p, encoding="utf-8"))
def load_js(p):   # docs/*.js are `window.X={...}` single-line files
    s = open(p, encoding="utf-8").read(); return json.loads(s.split("=", 1)[1].strip().rstrip(";"))

C = load_json(DOCS / "api/all_counties.json"); D = load_json(DOCS / "api/all_districts.json"); S = load_json(DOCS / "api/all_states.json"); N = load_json(DOCS / "api/national.json")
IDX = load_json(DOCS / "api/index.json")
DATA = load_js(DOCS / "data.js"); BURDEN = load_js(DOCS / "burden.js"); MORT = load_js(DOCS / "mortality.js"); ONC = load_js(DOCS / "oncologists.js"); RUCC = load_js(DOCS / "rucc.js"); COS = load_js(DOCS / "cosponsors.js"); FIND = load_js(DOCS / "findings.js")
PLACES = load_json(DOCS / "places.json"); ZIPS = load_json(DOCS / "zip_county.json")

STATE_NAMES = dict(DATA["states"])
county = {c["id"]: c for c in C}; district = {d["id"]: d for d in D}; state = {s["id"]: s for s in S}
geoid2id = {d["geoid"]: d["id"] for d in D}
T = DATA["T"]; TYPE_KEYS = [t[0] for t in T["types"]]; PHASES = T["phases"]; SPONSORS = [s[0] for s in T["sponsors"]]
ZIP2COUNTY = {}
for fips, zs in ZIPS.items():
    for z in zs: ZIP2COUNTY.setdefault(z, []).append(fips)

def short(c): return c["name"].split(",")[0]                       # "Hidalgo County"
def get(row, path):
    cur = row
    for k in path.split("."):
        if cur is None: return None
        cur = cur.get(k) if isinstance(cur, dict) else None
    return cur
def rows_in(table, st=None):
    rows = {"counties": C, "districts": D, "states": S}[table]
    return [r for r in rows if st is None or r["state"] == st]
def ranked(rows, path, desc=True, n=None):
    """order_by rule: nulls last; ties by pop55 desc then name asc"""
    def key(r):
        v = get(r, path)
        return (1 if v is None else 0, (-v if desc else v) if v is not None else 0, -(r.get("pop55") or 0), r["name"])
    out = sorted(rows, key=key)
    return out if n is None else out[:n]
def ids(rows): return [r["id"] for r in rows]

def ordinal(n):
    n = int(n); return "%d%s" % (n, "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))
def variants(row):
    """How an answer may name a place; used by the place_first check (earliest match wins)."""
    lvl = row.get("level")
    if lvl == "county": return [short(row)]
    if lvl == "state": return [row["name"]] + (["D.C.", "Washington, DC", "Washington DC"] if row["id"] == "DC" else [])
    if lvl == "district":
        st, nn = row["id"].split("-"); sname = STATE_NAMES.get(st, st)
        if nn == "00": return [row["name"], f"{st}-00", f"{st}-AL", f"{sname}'s at-large", f"{sname} at-large", f"{sname} at large"]
        o = ordinal(nn)
        return [row["name"], f"{st}-{nn}", f"{st}-{int(nn)}", f"{st}{nn}", f"{sname}'s {o}", f"{sname}’s {o}", f"{o} district of {sname}", f"{sname} {o} district", f"{o} congressional district of {sname}", f"{o} district", f"{o} congressional district"]
    return [row["name"]]
def place_first(first_rows, among_rows):
    return {"first": [r["id"] for r in first_rows], "among": {r["id"]: variants(r) for r in among_rows}}

def district_trials(d):   # ASK_CONTRACT §9.1: distinct recruiting trials with a site in any overlapping county
    u = set()
    for f in d["counties"]: u |= set(DATA["counties"][f]["tr"])
    return len(u)
def trials_in_county(f): return list(DATA["counties"][f]["tr"])
def trials_within_60(f):
    u = set()
    for i in DATA["counties"][f].get("nb", []): u |= set(DATA["SP"][i])
    return sorted(u)
def trials_in_state(st):
    fips = state[st]["fips"]; u = set()
    for f, cc in DATA["counties"].items():
        if f.startswith(fips): u |= set(cc["tr"])
    return sorted(u)
def has_type(i, key, by="cats"):
    ti = TYPE_KEYS.index(key)
    return (ti in T["cats"][i]) if by == "cats" else (T["ct"][i] == ti)

E = {}
def put(qid, **kw): E[qid] = kw

# ---------------- rankings ----------------
tx = rows_in("counties", "TX")
tied = [c for c in tx if c["pct_lt20_trials_within_60rdmi"] == max(x["pct_lt20_trials_within_60rdmi"] for x in tx)]
put("R01", tx_lt20_max_ids=ids(tied), tx_ids=ids(tx), place_first=place_first(tied, tx),
    tx_zero_top50_ids=ids(ranked(tx, "pct_zero_trials_within_60rdmi", True, 50)), tx_medn_top50_ids=ids(ranked(tx, "median_road_mi_nci", True, 50)),
    numbers={"tx_counties": len(tx), "tied_at_max": len(tied)})
top5 = ranked(D, "pct_lt20_trials_within_60rdmi", True, 5); mx = top5[0]["pct_lt20_trials_within_60rdmi"]
put("R02", ids=ids(top5), scope_ids=ids(D), place_first=place_first([d for d in top5 if d["pct_lt20_trials_within_60rdmi"] == mx], D),
    numbers={"fourth_value": top5[3]["pct_lt20_trials_within_60rdmi"], "top_value": mx, "values": [d["pct_lt20_trials_within_60rdmi"] for d in top5]})
mn = min(s["pct_lt20_trials_within_60rdmi"] for s in S); low = [s for s in S if s["pct_lt20_trials_within_60rdmi"] == mn]
put("R03", ids=ids(low), place_first=place_first(low, S), numbers={"value": mn})
oh = rows_in("counties", "OH"); top = ranked(oh, "trials_listed_here", True, 10)
put("R04", ids=ids(top), scope_ids=ids(oh), place_first=place_first(top[:1], oh), numbers={"top_value": top[0]["trials_listed_here"], "tenth_value": top[9]["trials_listed_here"], "eleventh_value": ranked(oh, "trials_listed_here", True, 11)[10]["trials_listed_here"]})
top = ranked(S, "pct_zero_trials_within_60rdmi", True, 5)
put("R05", ids=ids(top), scope_ids=ids(S), place_first=place_first(top[:1], S), numbers={"top_value": top[0]["pct_zero_trials_within_60rdmi"], "values": [s["pct_zero_trials_within_60rdmi"] for s in top]})
mt = rows_in("counties", "MT"); a = ranked(mt, "median_road_mi_nci", True, 1)[0]; b = ranked(mt, "road_mi_nci_from_center", True, 1)[0]
put("R06", mt_ids=ids(mt), place_first=place_first(list({a["id"]: a, b["id"]: b}.values()), mt), numbers={"top_median": a["median_road_mi_nci"], "top_center": b["road_mi_nci_from_center"]})
ga = rows_in("districts", "GA"); mn = min(d["pct_lt20_trials_within_60rdmi"] for d in ga); best = [d for d in ga if d["pct_lt20_trials_within_60rdmi"] == mn]; wm = ranked(ga, "wmean_trials_within_60rdmi", True, 1)
put("R07", place_first=place_first(list({d["id"]: d for d in best + wm}.values()), ga), numbers={"min_lt20": mn, "max_wmean": wm[0]["wmean_trials_within_60rdmi"]})
low = ranked(S, "oncologists.oncologists_per_100k_pop55", False, 1)
put("R08", ids=ids(low), place_first=place_first(low, S), numbers={"value": low[0]["oncologists"]["oncologists_per_100k_pop55"]})
top = ranked(D, "people_lt20_trials_within_60rdmi", True, 1)
put("R09", ids=ids(top), place_first=place_first(top, D), numbers={"value": top[0]["people_lt20_trials_within_60rdmi"]})
top = ranked(C, "trials_listed_here", True, 1)
put("R10", ids=ids(top), place_first=place_first(top, C), numbers={"value": top[0]["trials_listed_here"]})
ky = rows_in("counties", "KY"); top = ranked(ky, "mortality.all", True, 3)
put("R11", ids=ids(top), scope_ids=ids(ky), place_first=place_first(top[:1], ky), numbers={"top_value": top[0]["mortality"]["all"], "values": [c["mortality"]["all"] for c in top]})

# ---------------- counts ----------------
put("C01", ids=ids([c for c in tx if c["trials_listed_here"] == 0]), numbers={"count": sum(1 for c in tx if c["trials_listed_here"] == 0)})
put("C02", ids=ids([d for d in D if d["pct_gt60rdmi_broad_menu"] == 100.0]), numbers={"count": sum(1 for d in D if d["pct_gt60rdmi_broad_menu"] == 100.0), "findings_says": FIND["districts"]["all_beyond_60_broad"]})
nb = [st for st, sd in DATA["state_data"].items() if sd["broad"] == 0]
put("C03", ids=sorted(nb), numbers={"count": len(nb), "findings_says": FIND["states_no_broad"]})
put("C04", numbers={"count_gt": sum(1 for c in ky if c["pct_lt20_trials_within_60rdmi"] > 50), "count_ge": sum(1 for c in ky if c["pct_lt20_trials_within_60rdmi"] >= 50), "ky_counties": len(ky)})
put("C05", names=[n["full"] for n in DATA["nci"] if n["st"] == "TX"], numbers={"count": sum(1 for n in DATA["nci"] if n["st"] == "TX")})
hr = COS["bills"]["ctma_hr"]
put("C06", numbers={"cosponsors": hr["n_cosponsors"], "with_sponsor": hr["n_cosponsors"] + 1})
put("C07", numbers={"count": hr["parties"]["R"], "d": hr["parties"]["D"]})
put("C08", numbers={"count": N["oncologists"]["counties_by_class"]["2"], "sum_check": sum(1 for c in C if c["oncologists"]["class"] == 2)})

# ---------------- thresholds ----------------
al = rows_in("counties", "AL"); m = [c for c in al if c["pct_lt20_trials_within_60rdmi"] > 50]
put("T01", ids=ids(m), numbers={"count": len(m), "count_ge": sum(1 for c in al if c["pct_lt20_trials_within_60rdmi"] >= 50)})
mc = [c for c in tx if (c["road_mi_nci_from_center"] or 0) > 100]; mm = [c for c in tx if (c["median_road_mi_nci"] or 0) > 100]
put("T02", ids_center=ids(mc), ids_median=ids(mm), numbers={"count_center": len(mc), "count_median": len(mm)})
m = [d for d in D if d["pct_zero_trials_within_60rdmi"] > 30]
put("T04", ids=ids(m), numbers={"count": len(m)})
m = [s for s in S if s["context"]["uninsured_55_64"] > 10]
put("T05", ids=ids(m), numbers={"count": len(m)})
ms = rows_in("counties", "MS"); m = [c for c in ms if (c["mortality"]["all"] or 0) >= 200]
put("T06", ids=ids(m), numbers={"count": len(m)})
m = [c for c in ky if (c["drive_hours_nci"] or 0) >= 2]
put("T07", ids=ids(m), numbers={"count": len(m), "nulls": sum(1 for c in ky if c["drive_hours_nci"] is None)})

# ---------------- lookups ----------------
h = county["48215"]
put("L01", ids=["48215"], numbers={"trials": h["trials_listed_here"], "pop55": h["pop55"], "wmean": h["wmean_trials_within_60rdmi"], "people_lt20": h["people_lt20_trials_within_60rdmi"], "lt20": h["pct_lt20_trials_within_60rdmi"]})
lub = [p for p in PLACES["places"]["TX"] if p[0] == "Lubbock"][0][1]; c = county[lub]
put("L02", ids=[lub], numbers={"center": c["road_mi_nci_from_center"], "median": c["median_road_mi_nci"], "hours": c["drive_hours_nci"]}, nearest=c["nearest_nci"])
f = ZIP2COUNTY["40601"]; assert len(f) == 1; c = county[f[0]]
put("L03", ids=f, numbers={"center": c["trials_within_60rdmi_of_center"], "wmean": c["wmean_trials_within_60rdmi"]}, name=c["name"])
d = [d for d in D if d["member"].get("name") == "Raul Ruiz"][0]
put("L04", ids=[d["id"]], numbers={"lt20": d["pct_lt20_trials_within_60rdmi"], "zero": d["pct_zero_trials_within_60rdmi"], "medn": d["median_road_mi_nci"], "people_lt20": d["people_lt20_trials_within_60rdmi"]})
d = district["TX-34"]
put("L05", ids=["TX-34"], numbers={"people_lt20": d["people_lt20_trials_within_60rdmi"], "lt20": d["pct_lt20_trials_within_60rdmi"]})
put("L06", ids=["TX-34"], member=d["member"]["name"], role=d["member"]["ctma_hr3521"])
d = district["FL-02"]
put("L07", ids=["FL-02"], member=d["member"]["name"], numbers={"people_lt20": d["people_lt20_trials_within_60rdmi"], "medn": d["median_road_mi_nci"], "zero": d["pct_zero_trials_within_60rdmi"], "lt20": d["pct_lt20_trials_within_60rdmi"]})
d = district["WY-00"]
put("L08", ids=["WY-00"], member=d["member"]["name"], numbers={"lt20": d["pct_lt20_trials_within_60rdmi"], "zero": d["pct_zero_trials_within_60rdmi"], "people_lt20": d["people_lt20_trials_within_60rdmi"]})

# ---------------- comparisons ----------------
cam = county["48061"]
put("X01", ids=["48215", "48061"], numbers={"hidalgo_trials": h["trials_listed_here"], "cameron_trials": cam["trials_listed_here"], "hidalgo_pop55": h["pop55"], "cameron_pop55": cam["pop55"], "hidalgo_lt20": h["pct_lt20_trials_within_60rdmi"], "cameron_lt20": cam["pct_lt20_trials_within_60rdmi"]})
put("X02", numbers={"ky": state["KY"]["pct_lt20_trials_within_60rdmi"], "us": N["pct_lt20_trials_within_60rdmi"]})
put("X03", numbers={"nonmetro_lt20": state["KY"]["nonmetro"]["pct_lt20"], "metro_lt20": state["KY"]["metro"]["pct_lt20"], "nonmetro_zero": state["KY"]["nonmetro"]["pct_zero"], "metro_zero": state["KY"]["metro"]["pct_zero"]})
worse = max((state["MT"], state["WY"]), key=lambda s: s["pct_lt20_trials_within_60rdmi"])
put("X04", ids=["MT", "WY"], place_first=place_first([worse], [state["MT"], state["WY"]]), numbers={"wy": state["WY"]["pct_lt20_trials_within_60rdmi"], "mt": state["MT"]["pct_lt20_trials_within_60rdmi"]})

# ---------------- attribution: each named place with its own figure (check "pairs") ----------------
def pv(row):   # name variants for the pairs check: the full name too ("Hidalgo County, Texas"), then the short forms
    return ([row["name"]] if row.get("level") == "county" else []) + variants(row)
def pairs(rows, path): return [[pv(r), get(r, path)] for r in rows]
def strict_top(rows, path, n, desc=True):
    # the top n, keeping only places whose value is strictly ahead of the (n+1)th (a tie at the cut-off may be listed either way)
    r = ranked([x for x in rows if get(x, path) is not None], path, desc)
    if len(r) <= n: return r
    cut = get(r[n], path)
    return [x for x in r[:n] if (get(x, path) > cut if desc else get(x, path) < cut)]
two = [state["WY"], state["MT"]]
put("AT01", ids=["WY", "MT"], pairs=pairs(two, "pct_lt20_trials_within_60rdmi"), place_first=place_first([max(two, key=lambda s: s["pct_lt20_trials_within_60rdmi"])], two))
put("AT02", ids=["48215", "48061"], pairs=pairs([county["48215"], county["48061"]], "trials_listed_here"))
put("AT03", ids=["KY", "OH", "WV"], pairs=pairs([state["KY"], state["OH"], state["WV"]], "pct_lt20_trials_within_60rdmi"))
ak_mt = [state["AK"], state["MT"]]
put("AT04", ids=["AK", "MT"], pairs=pairs(ak_mt, "pct_zero_trials_within_60rdmi"), place_first=place_first([max(ak_mt, key=lambda s: s["pct_zero_trials_within_60rdmi"])], ak_mt))
top_onc = strict_top(rows_in("counties", "TX"), "oncologists.count", 3)
put("AT05", ids=ids(ranked(rows_in("counties", "TX"), "oncologists.count", True, 3)), pairs=pairs(top_onc, "oncologists.count"))
d2 = [district["TX-34"], district["TX-15"]]
put("AT06", ids=["TX-34", "TX-15"], pairs=pairs(d2, "median_road_mi_nci"), place_first=place_first([max(d2, key=lambda d: d["median_road_mi_nci"])], d2))
put("AT07", ids=["ME", "VT", "NH"], pairs=pairs([state["ME"], state["VT"], state["NH"]], "median_road_mi_nci"))
top_b = strict_top(S, "median_road_mi_nci", 4)
put("AT08", ids=ids(ranked(S, "median_road_mi_nci", True, 4)), pairs=pairs(top_b, "median_road_mi_nci"))
put("AT09", ids=["48479", "48061"], pairs=pairs([county["48479"], county["48061"]], "people_lt20_trials_within_60rdmi"))
d3 = [district["FL-02"], district["GA-08"], district["AL-05"]]
put("AT10", ids=ids(d3), pairs=pairs(d3, "wmean_trials_within_60rdmi"), place_first=place_first([max(d3, key=lambda d: d["wmean_trials_within_60rdmi"])], d3))

# ---------------- need vs access, deaths vs access ----------------
def hila(c): return c.get("incidence_above_county_median") is True and c["pct_lt20_trials_within_60rdmi"] >= 50
def hdla(c): return c.get("mortality_top_third") is True and c["pct_lt20_trials_within_60rdmi"] >= 50
m = [c for c in tx if hila(c)]
put("N01", ids=ids(m), numbers={"count": len(m), "burden_says": BURDEN["summary"]["states"]["TX"]["hb_la_counties"]})
put("N02", numbers={"count": MORT["summary"]["nat"]["hh_counties"], "sum_check": sum(1 for c in C if hdla(c))})
m = [c for c in rows_in("counties", "GA") if hdla(c)]
put("N03", ids=ids(m), numbers={"count": len(m), "mortality_says": MORT["summary"]["states"]["GA"]["hh_counties"]})
m = [c for c in tx if hila(c)]
put("N04", numbers={"pop55": sum(c["pop55"] for c in m), "burden_says": BURDEN["summary"]["states"]["TX"]["hb_la_pop55"], "counties": len(m)})
txd = rows_in("districts", "TX"); dv = {d["id"]: len(MORT["summary"]["districts"][d["geoid"]]["hh"]) for d in txd}
mxv = max(dv.values()); best = [district[k] for k, v in dv.items() if v == mxv]
put("N05", place_first=place_first(best, txd), numbers={"value": mxv}, vacant=[d["id"] for d in best if not d["member"].get("name")])

# ---------------- cancer type ----------------
w60 = trials_within_60(h["id"])
put("Y01", numbers={"count": sum(1 for i in w60 if has_type(i, "lung")), "count_ct": sum(1 for i in w60 if has_type(i, "lung", "ct")), "all_within_60": len(w60)})
top = ranked(oh, "incidence.by_site.breast", True, 5)
put("Y02", place_first=place_first(top[:1], oh), numbers={"top_value": top[0]["incidence"]["by_site"]["breast"]})
put("Y03", numbers={"us_pancreatic_rate": MORT["meta"]["us"]["pancreatic"]["rate"]})
low = ranked(txd, "trials_within_60rdmi_by_cancer_type.lung", False, 5); mnv = low[0]["trials_within_60rdmi_by_cancer_type"]["lung"]
put("Y04", place_first=place_first([d for d in low if d["trials_within_60rdmi_by_cancer_type"]["lung"] == mnv], txd), numbers={"top_value": mnv})
bi = BURDEN["meta"]["types"].index("breast"); m = [c for c in mt if BURDEN["county"][c["id"]]["zt"][bi] == 100.0]
put("Y05", ids=ids(m), numbers={"count": len(m), "mt_counties": len(mt)})
hou = trials_in_county("48201"); p3 = [i for i in hou if PHASES[T["ph"][i]] == "3"]
put("Y06", numbers={"count_cats": sum(1 for i in p3 if has_type(i, "lung")), "count_ct": sum(1 for i in p3 if has_type(i, "lung", "ct")), "lung_all_phases": sum(1 for i in hou if has_type(i, "lung"))})

# ---------------- oncologists ----------------
c2 = [c for c in tx if c["oncologists"]["class"] == 2]; d2 = [d for d in txd if d["oncologists"]["counties_with_oncologists_no_trials"]]
put("O01", county_ids=ids(c2), district_ids=ids(d2), numbers={"county_count": len(c2), "district_count": len(d2), "state_says": state["TX"]["oncologists"]["counties_with_oncologists_no_trials"], "pct_pop55": state["TX"]["oncologists"]["pct_pop55_in_counties_with_oncologists_no_trials"]})
m = [c for c in rows_in("counties", "PA") if c["oncologists"]["class"] == 3]
put("O02", ids=ids(m), names=[short(c) for c in m])
top = ranked(S, "oncologists.oncologists_per_100k_pop55", True, 2)
put("O03", place_first=place_first(top, S), numbers={"dc": top[0]["oncologists"]["oncologists_per_100k_pop55"], "ma": top[1]["oncologists"]["oncologists_per_100k_pop55"]})
put("O04", numbers={"count": h["oncologists"]["within_60rdmi"]})

# ---------------- cosponsors ----------------
mem = COS["members"]
def hr_rows(st=None): return [(m, mem[m]) for m, v in COS["by_member"].items() if "ctma_hr" in v and (st is None or mem[m]["state"] == st)]
def did(m): return f"{m['state']}-{int(m['district']):02d}"
fl = hr_rows("FL"); put("S01", ids=[did(m) for _, m in fl], names=[m["name"] for _, m in fl])
va = [(mem[m]["name"], (COS["by_member"].get(m) or {}).get("ctma_s", {}).get("role", "none")) for m in COS["senators"]["VA"]]
put("S02", senators=va)
put("S03", sponsor=mem[COS["bills"]["ctma_s"]["sponsor"]]["name"])
txh = hr_rows("TX"); put("S04", ids=[did(m) for _, m in txh], names=[m["name"] for _, m in txh])
ds = [d for d in D if "48215" in d["counties"]]
put("S05", ids=ids(ds), members=[(d["id"], d["member"].get("name"), d["member"]["ctma_hr3521"]) for d in ds])
sen = [(mem[m]["name"], v["ctma_s"]["role"]) for m, v in COS["by_member"].items() if "ctma_s" in v]
put("S06", senators=sen)
m = [d for d in rows_in("districts", "CA") if d["member"].get("party") == "D" and d["member"]["ctma_hr3521"] == "none"]
put("S07", ids=ids(m), numbers={"count": len(m)})

# ---------------- rural ----------------
put("U01", numbers={"value": N["nonmetro_pct"]})
m = [c for c in tx if c["metro"] is False and c["pct_zero_trials_within_60rdmi"] >= 50]
put("U02", ids=ids(m), numbers={"count": len(m)})
r9 = RUCC["nat"]["codes"]["9"]
put("U03", numbers={"counties": r9["n"], "pct_lt20": r9["l20"], "pct_zero": r9["z60"], "count_check": sum(1 for c in C if c["rucc"] == 9)})
top = ranked(S, "nonmetro_pct", True, 5); mxv = top[0]["nonmetro_pct"]
put("U04", top5_ids=ids(top), place_first=place_first([s for s in top if s["nonmetro_pct"] == mxv], S), numbers={"top_value": mxv})

# ---------------- household ----------------
nm = rows_in("counties", "NM"); top = ranked(nm, "context.poverty", True, 5); mxv = top[0]["context"]["poverty"]
put("H01", place_first=place_first([c for c in top if c["context"]["poverty"] == mxv], nm), numbers={"top_value": mxv})
top = ranked(txd, "context.no_vehicle", True, 5); mxv = top[0]["context"]["no_vehicle"]
put("H02", place_first=place_first([d for d in top if d["context"]["no_vehicle"] == mxv], txd), numbers={"top_value": mxv})

# ---------------- NCI centers ----------------
flc = [n for n in DATA["nci"] if n["st"] == "FL" and n["tier"] == "Comprehensive"]
put("I01", names=[n["full"] for n in flc], numbers={"count": len(flc)}, trap=[n["full"] for n in DATA["nci"] if n["st"] == "FL" and n["tier"] != "Comprehensive"])
have = {n["st"] for n in DATA["nci"]}; none = sorted(s["id"] for s in S if s["id"] not in have)
put("I04", ids=none, numbers={"count": len(none)})

# ---------------- facilities and trials ----------------
put("F01", numbers={"count": county["48201"]["trials_listed_here"], "data_js": len(DATA["counties"]["48201"]["tr"])})
ohT = trials_in_state("OH"); ii = SPONSORS.index("industry")
put("F02", numbers={"count": sum(1 for i in ohT if T["sp"][i] == ii), "oh_trials": len(ohT)})
fac = sorted(DATA["counties"]["48215"]["fac"], key=lambda x: -len(x[3]))
put("F03", top=[[x[0], x[1], len(x[3])] for x in fac[:3]], numbers={"top_value": len(fac[0][3])})
mi = TYPE_KEYS.index("multi"); nmulti = sum(1 for x in T["ct"] if x == mi)
put("F04", numbers={"count": nmulti, "pct": round(100 * nmulti / len(T["id"]), 1), "trials": len(T["id"])})

# ---------------- how many people ----------------
put("P01", numbers={"people": N["people_zero_trials_within_60rdmi"], "pct": N["pct_zero_trials_within_60rdmi"]})
txs = state["TX"]
put("P02", numbers={"share": txs["pct_gt60rdmi_nci"], "derived_people": round(txs["pop55"] * txs["pct_gt60rdmi_nci"] / 100), "pop55": txs["pop55"]})

# ---------------- namesakes and typos ----------------
w = [c for c in C if short(c) == "Washington County"]
put("A01", ids=ids(w), states=sorted({STATE_NAMES[c["state"]] for c in w}), numbers={"count": len(w)})
l = [c for c in C if short(c) == "Lincoln County"]
put("A02", ids=ids(l), states=sorted({STATE_NAMES[c["state"]] for c in l}), numbers={"count": len(l)})
hh = sorted([c for c in C if short(c) == "Hidalgo County"], key=lambda c: -c["pop55"])
put("A03", ids=[hh[0]["id"]], others=[(c["id"], STATE_NAMES[c["state"]], c["pop55"]) for c in hh[1:]], numbers={"center": h["road_mi_nci_from_center"], "median": h["median_road_mi_nci"], "hours": h["drive_hours_nci"]}, nearest=h["nearest_nci"])
put("A04", ids=["48215"], numbers=E["L01"]["numbers"])
top = ranked(tx, "trials_listed_here", True, 1)
put("A05", place_first=place_first(top, tx), numbers={"top_value": top[0]["trials_listed_here"]})

# ---------------- territory, unanswerable, scope, other, methods: nothing numeric ----------------
for qid in ["Z01", "Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07", "Q08", "G01", "G02", "G03", "J01", "J02", "J03", "J04", "M01", "M02", "M03", "M04"]:
    put(qid, numbers={})
E["Q01"]["numbers"] = {"tx34_counties_with_rate": MORT["summary"]["districts"]["4834"]["classified"]}
E["Q06"]["numbers"] = {"center": county[lub]["road_mi_nci_from_center"]}
E["Q08"]["numbers"] = {"history_pulls": len(load_js(DOCS / "changes.js")["history"])}

# ---------------- follow-ups ----------------
m = [c for c in c2 if c["metro"] is False]
put("W01", ids=ids(m), numbers={"count": len(m), "class2": len(c2)})
put("W02", ids=ids(ds), members=[d["member"].get("name") for d in ds], senators=[s["name"] for s in txs["senators"]])

out = {"built": IDX["built"], "data_as_of": IDX["data_as_of"], "n": len(E), "questions": E}
qfile = Path(__file__).with_name("eval_questions.json")
if qfile.exists():
    qids = [q["id"] for q in load_json(qfile)["questions"]]
    missing = [q for q in qids if q not in E]; extra = [q for q in E if q not in qids]
    if missing or extra: sys.exit(f"eval_expected.py: questions without expectations {missing}; expectations without questions {extra}")
Path(__file__).with_name("eval_expected.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote eval_expected.json: {len(E)} questions, data as of {out['data_as_of']}")
