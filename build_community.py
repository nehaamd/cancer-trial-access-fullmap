"""Build docs/community.js: one compact record per county, congressional district and state for the "Your community",
"What could help" and "Understand clinical trials" pages, so they load a few hundred kilobytes instead of data.js (7.7 MB).

Every figure is copied from the files the map itself reads (data.js, burden.js, rucc.js, mortality.js, cosponsors.js), so the
pages cannot disagree with the map. Runs in run_refresh.sh after build_findings.py. Nothing is computed here except the
county -> district index (inverted from each district's county list).
"""
import json
from datetime import date
from pathlib import Path

DOCS = Path("docs")


def load(name):
    s = (DOCS / name).read_text(encoding="utf-8")
    return json.loads(s[s.index("=") + 1:].strip().rstrip(";"))


def main():
    D = load("data.js"); BU = load("burden.js"); RU = load("rucc.js"); MO = load("mortality.js"); CO = load("cosponsors.js")
    C, DI, SD, meta = D["counties"], D["districts"], D["state_data"], D["meta"]
    types = D["T"]["types"]; type_keys = [t[0] for t in types]; btypes = BU["meta"]["types"]
    bsites = [s[0] for s in meta["burden"]["sites"]]; msites = [s[0] for s in MO["meta"]["sites"]]
    name_of = {bid: m["name"] for bid, m in CO["members"].items()}
    roles = {bid: {b: r["role"] for b, r in v.items()} for bid, v in CO["by_member"].items()}
    # county -> districts (a county can touch several)
    cd_of = {}
    for k, d in DI.items():
        for cf in d.get("counties", []): cd_of.setdefault(cf, []).append(k)
    inc_i = bsites.index("all"); mort_i = msites.index("all"); usps = {g["fips"]: st for st, g in SD.items()}
    counties = {}
    for cf, c in C.items():
        u = BU["county"].get(cf) or {}; r = RU["county"].get(cf); b = (c.get("b") or [None] * 20)[inc_i]; m = (MO["county"].get(cf) or [None] * 20)[mort_i]
        counties[cf] = {"n": c.get("nl") or c["n"], "st": usps.get(c["s"], c["s"]), "p": c["p"], "t": c["t"], "f": c["f"], "t60": c["t60"], "f60": c.get("f60"),
                        "l20": u.get("l20"), "z60": u.get("z60"), "tm": u.get("t60m", u.get("t60")), "zt": u.get("zt"),
                        "rn": c["rn"], "nn": c["nn"], "rb": c["rb"], "nbm": c["nbm"], "noroad": c.get("noroad") or "",
                        "ru": r["c"] if r else None, "inc": [b[0], b[3], b[4]] if b else None, "mort": [m[0], m[3], m[4]] if m else None, "d": cd_of.get(cf, [])}
    districts = {}
    for k, d in DI.items():
        bid = CO["district_map"].get(k); ru = RU["districts"].get(k) or {}
        districts[k] = {"st": d["st"], "cd": d["cd"], "p": d["p"], "l20": d["l20"], "z60": d["z60"], "t60": d["t60"], "g60n": d["g60n"], "g60b": d["g60b"], "medn": d["medn"], "medb": d["medb"],
                        "nr": d.get("nr", 0), "member": d["member"], "party": d["party"], "bio": bid, "nm": ru.get("nonmetro_pct"), "ct": (d.get("bd") or {}).get("ct"), "counties": d.get("counties", []),
                        "mnci": d.get("mnci"), "mbroad": d.get("mbroad")}
    states = {}
    for st, g in SD.items():
        ru = RU["states"].get(st) or {}; bs = BU["summary"]["states"].get(st) or {}; ms = (MO.get("summary") or {}).get("states", {}).get(st) or {}
        met, non = ru.get("metro") or {}, ru.get("nonmetro") or {}
        states[st] = {"name": g["name"], "fips": g["fips"], "p": g["p"], "l20": g["l20"], "z60": g["z60"], "t60": g["t60"], "g60n": g["g60n"], "g60b": g["g60b"], "medn": g["medn"], "medb": g["medb"], "nr": g.get("nr", 0),
                      "ndist": g["ndist"], "counties": g["counties"], "cwt": g["counties_with_trials"], "broad": g["broad"], "limited": g["limited"], "trials": g["trials"], "mnci": g.get("mnci"),
                      "ct": (g.get("bd") or {}).get("ct"), "rural": {"metro": [met.get("p"), met.get("l20"), met.get("z60")], "nonmetro": [non.get("p"), non.get("l20"), non.get("z60")]},
                      "burden": [bs.get("hb_la_counties"), bs.get("hb_la_pop55"), bs.get("counties_classified")], "mort": [ms.get("hh_counties"), ms.get("hh_pop55"), ms.get("hh_deaths")],
                      "senators": [{"name": name_of.get(b, b), "party": CO["members"][b]["party"], "bio": b} for b in CO["senators"].get(st, []) if b in CO["members"]]}
    bills = {k: {**{f: b.get(f) for f in ("congress", "type", "number", "label", "short", "title", "introduced", "latest_action", "n_cosponsors", "n_original", "parties", "url", "cosponsors_url", "topic")}, "sponsor": name_of.get(b.get("sponsor"), b.get("sponsor")), "sponsor_bio": b.get("sponsor")} for k, b in CO["bills"].items()}
    nat = {**{k: meta["nat_core"][k] for k in ("p", "nt", "l20", "z60", "t60", "g60n", "g60b", "medn", "medb", "nr", "mnci", "mbroad")}, "ct": meta["nat_core"]["bd"]["ct"],
           "rural": {"metro": [RU["nat"]["metro"]["p"], RU["nat"]["metro"]["l20"], RU["nat"]["metro"]["z60"]], "nonmetro": [RU["nat"]["nonmetro"]["p"], RU["nat"]["nonmetro"]["l20"], RU["nat"]["nonmetro"]["z60"]]},
           "burden": [BU["summary"]["nat"]["hb_la_counties"], BU["summary"]["nat"]["hb_la_pop55"], BU["summary"]["nat"]["counties_classified"]],
           "mort": [MO["summary"]["nat"]["hh_counties"], MO["summary"]["nat"]["hh_pop55"], MO["summary"]["nat"]["hh_deaths"]]}
    CCOLS = ["n", "st", "p", "t", "f", "t60", "f60", "l20", "z60", "tm", "zt", "rn", "nn", "rb", "nbm", "noroad", "ru", "inc", "mort", "d"]
    counties = {cf: [c[k] for k in CCOLS] for cf, c in counties.items()}
    for d in districts.values(): d["ct"] = [d["ct"].get(t) for t in type_keys] if d["ct"] else None
    for g in states.values(): g["ct"] = [g["ct"].get(t) for t in type_keys] if g["ct"] else None
    nat["ct"] = [nat["ct"].get(t) for t in type_keys]
    FI = load("findings.js")
    if FI.get("meta", {}).get("pull") == meta.get("pull"): nat["people_l20"], nat["people_z60"] = FI["nat"].get("people_l20"), FI["nat"].get("people_z60")   # same tract sums the map's national card shows
    out = {"ccols": CCOLS, "meta": {"built": str(date.today()), "registry_data_timestamp": meta.get("registry_data_timestamp"), "pull": meta.get("pull"), "plan": meta.get("plan"), "trials": meta.get("trials"), "members_pull": meta.get("members_pull"),
                    "cosponsors_fetched": CO["meta"].get("fetched"), "cosponsors_note": CO["meta"].get("note"), "topics": CO["meta"].get("topics"), "inc_period": meta["burden"]["period"], "mort_period": MO["meta"]["period"],
                    "inc_median": BU["meta"]["median_all"], "mort_tertile": (MO["meta"].get("tertiles") or {}).get("all"), "types": types, "btypes": btypes, "nat": nat, "bills": bills, "roles": roles, "rucc_labels": RU["meta"]["labels"]},
           "counties": counties, "districts": districts, "states": states}
    s = "window.COMMUNITY=" + json.dumps(out, separators=(",", ":"), ensure_ascii=False)
    (DOCS / "community.js").write_text(s, encoding="utf-8")
    print(f"community.js KB {len(s.encode()) // 1024} | counties {len(counties)} districts {len(districts)} states {len(states)} | bills {list(bills)}")


if __name__ == "__main__":
    main()
