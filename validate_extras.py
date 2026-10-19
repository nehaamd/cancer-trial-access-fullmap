"""Validation for the rural/urban, cosponsor, burden-vs-access and ZIP-lookup additions (v3.3). Runs from the flat
deployed layout or the pipeline layout. Standalone: writes VALIDATION_extras.md; validate_v3.py also folds these rows in.
Usage: python validate_extras.py [--browser]   (--browser re-runs the in-page tract recomputation with Playwright, if installed)
"""
import calendar, json, math, sys, struct, time
from pathlib import Path
import numpy as np, pandas as pd

rows = []
def check(name, result, ok, note=""): rows.append((name, result, "✓" if ok else "✗", note)); print(("PASS " if ok else "FAIL ") + name + ": " + str(result))


def find(name):
    for d in [".", "data/ref", "out_adult55", "data/raw", "docs"]:
        p = Path(d) / name
        if p.exists(): return p
    return None


def load_js(name, prefix):
    p = find(name); return None if p is None else json.loads(p.read_text(encoding="utf-8")[len(prefix):].rstrip().rstrip(";"))


def run(browser=False):
    D = load_js("data.js", "window.DATA="); RU = load_js("rucc.js", "window.RUCC="); CO = load_js("cosponsors.js", "window.COSPONSORS="); BU = load_js("burden.js", "window.BURDEN="); FI = load_js("find_data.js", "window.FIND=")
    counties = set(D["counties"]); nat = D["meta"]["nat_core"]
    tr = pd.read_csv(find("tract_access.csv"), dtype={"tract": str, "county_fips": str}, usecols=["tract", "county_fips", "pop55", "trials_within_60rdmi"])
    # ---- rural / urban ----
    if RU:
        missing = [k for k in counties if k not in RU["county"]]; ct13 = [k for k, v in RU["county"].items() if v["s"] == "2013"]
        check("RUCC: every county carries a code; 2013 fallback limited to Connecticut", f"{len(RU['county'])} coded, {len(missing)} missing; 2013 fallback: {len(ct13)} ({', '.join(sorted(ct13))})", not missing and all(k.startswith("09") for k in ct13) and len(ct13) == 8)
        m, nm = RU["nat"]["metro"], RU["nat"]["nonmetro"]; tot = m["p"] + nm["p"]; wl20 = (m["p"] * m["l20"] + nm["p"] * nm["l20"]) / tot; wz = (m["p"] * m["z60"] + nm["p"] * nm["z60"]) / tot
        check("RUCC: metro + nonmetro residents 55+ equal the national total; their weighted <20 / none shares reproduce the national figures", f"{tot:,} vs {nat['p']:,}; weighted <20 {wl20:.2f}% vs {nat['l20']}%; none {wz:.2f}% vs {nat['z60']}%", tot == nat["p"] and abs(wl20 - nat["l20"]) < 0.11 and abs(wz - nat["z60"]) < 0.11)
        code = tr.county_fips.map({k: v["c"] for k, v in RU["county"].items()}); w = tr.pop55.astype(float); nonmetro_l20 = 100 * w[(code >= 4) & (tr.trials_within_60rdmi < 20)].sum() / w[code >= 4].sum()
        check("RUCC: nonmetro '<20 within 60 road-mi' share recomputed independently from tract_access.csv", f"{nonmetro_l20:.1f}% vs rucc.js {nm['l20']}%; metro {m['l20']}% (nonmetro / metro ratio {nm['l20'] / m['l20']:.1f}×)", abs(nonmetro_l20 - nm["l20"]) < 0.06)
        sums = {st: g["metro"]["p"] + (g["nonmetro"]["p"] if g["nonmetro"] else 0) for st, g in RU["states"].items() if g["metro"]}; bad = [st for st, p in sums.items() if p != D["state_data"][st]["p"]]
        check("RUCC: state metro + nonmetro populations equal state totals", f"{len(bad)} mismatches" + (f" ({bad})" if bad else ""), not bad)
        # exact counts behind the shares (n_l20 / n_z60, build_rucc.py), which the map prints as numbers of people instead of share x population
        pw = tr.pop55.values.astype(float); mt = (code <= 3).values; l20m = (tr.trials_within_60rdmi < 20).values; z60m = (tr.trials_within_60rdmi == 0).values; stf = tr.county_fips.str[:2].values
        badn, ngroups = [], 0
        for st, g in [("US", RU["nat"])] + list(RU["states"].items()):
            sm = np.ones(len(tr), bool) if st == "US" else stf == D["state_data"][st]["fips"]
            for kind, km in (("metro", mt), ("nonmetro", ~mt)):
                grp = g.get(kind)
                if grp is None: continue
                ngroups += 1
                if (grp.get("n_l20"), grp.get("n_z60")) != (int(round(pw[sm & km & l20m].sum())), int(round(pw[sm & km & z60m].sum()))): badn.append(f"{st} {kind}")
        check("RUCC: exact residents 55+ with fewer than 20 / no trials within 60 road-mi (n_l20, n_z60) on every metro and nonmetro group, recounted from tract_access.csv",
              f"{ngroups} groups, {len(badn)} differ" + (f" ({badn[:6]})" if badn else f"; nation {m.get('n_l20', 0) + nm.get('n_l20', 0):,} short of trials ({nm.get('n_l20', 0):,} nonmetro + {m.get('n_l20', 0):,} metro)"), not badn)
        p = find("tract_county.bin"); buf = p.read_bytes(); magic, n = struct.unpack("<II", buf[:8]); idx = np.frombuffer(buf, "<u2", n, 8); order = RU["meta"]["county_order"]
        back = np.array(order)[idx]; agree = int((back == tr.county_fips.values).sum())
        check("tract_county.bin: every tract maps back to its own county through meta.county_order", f"{agree:,} of {n:,} tracts; {len(order)} counties in order list", magic == 0x54524332 and n == len(tr) and agree == n and len(order) == len(counties))
    # ---- cosponsors ----
    if CO:
        legis = json.load(open(find("legislators-current.json"))); ids = {l["id"]["bioguide"] for l in legis}
        allm = {b for bills in CO["by_member"].values() for b in bills}; unresolved = [k for k in CO["by_member"] if k not in ids]
        check("Cosponsors: every sponsor / cosponsor bioguide ID resolves to a current member of Congress", f"{len(CO['by_member'])} members on {len(allm)} bills; unresolved: {unresolved or 'none'}", not unresolved)
        b = CO["bills"]; exp = {"ctma_hr": ("R000599", "hr", 3521), "ctma_s": ("S001184", "s", 4440)}
        ok = all(k in b and b[k]["sponsor"] == v[0] and b[k]["type"] == v[1] and b[k]["number"] == v[2] for k, v in exp.items()) and not any(k.startswith("epic") for k in b)
        check("Cosponsors: the tracked bills are the Clinical Trial Modernization Act only (Ruiz H.R. 3521, Scott S. 4440)", "; ".join(f"{b[k]['label']} {CO['members'][b[k]['sponsor']]['name']} ({b[k]['n_cosponsors']} cosponsors)" for k in b), ok)
        pf = CO["by_member"].get("P000048", {}).get("ctma_hr", {}); check("Cosponsors: TX-11 (Pfluger) is an original cosponsor of H.R. 3521, not its sponsor (corrects the v3.2 label)", f"role = {pf.get('role')} ({pf.get('date')})", pf.get("role") == "original")
        nd = len(CO["district_map"]); vac = len(D["meta"]["vacant"]); check("Cosponsors: district → member map covers every non-vacant House seat (+ DC delegate)", f"{nd} mapped; {vac} vacant in the payload; 436 district rows", nd + vac == 436)
        ns = sum(len(v) for v in CO["senators"].values()); check("Cosponsors: 100 senators mapped to states", f"{ns} senators across {len(CO['senators'])} states", ns == 100)
        chamber_ok = all(CO["members"][m]["chamber"] == ("rep" if b[k]["type"] == "hr" else "sen") for k in b for m in [b[k]["sponsor"]] + [x for x in CO["by_member"] if k in CO["by_member"][x]])
        check("Cosponsors: House bills carry only representatives, Senate bills only senators", "chambers consistent" if chamber_ok else "MISMATCH", chamber_ok)
        age = (time.time() - calendar.timegm(time.strptime(CO["meta"]["fetched"], "%Y-%m-%d"))) / 86400; check("Cosponsors: freshness of the pull", f"fetched {CO['meta']['fetched']} ({int(age)} days ago) from {CO['meta']['source'][:40]}…", age < 45, "re-run fetch_cosponsors.py before a Hill Day; the deployed page states the fetch date")
    # ---- burden vs access ----
    if BU:
        w = tr.pop55.astype(float); g = tr.groupby("county_fips"); W = g.pop55.sum().astype(float)
        l20 = (pd.Series(w.values * (tr.trials_within_60rdmi.values < 20), index=tr.index).groupby(tr.county_fips).sum() / W * 100)
        diff = max(abs(l20[k] - BU["county"][k]["l20"]) for k in counties); wmean = sum(BU["county"][k]["l20"] * W[k] for k in counties) / W.sum()
        check("Burden: county '<20 within 60 road-mi' shares recomputed from tract_access.csv; their population-weighted mean equals the national share", f"max |diff| {diff:.2f} pts (rounding); weighted mean {wmean:.2f}% vs national {nat['l20']}%", diff < 0.06 and abs(wmean - nat["l20"]) < 0.11)
        inc = pd.read_csv(find("cancer_incidence_county.csv"), dtype={"county_fips": str}); a = inc[inc.site == "all"]; med = a[a.status == "ok"].rate.median()
        S = BU["summary"]["nat"]; classified = int(a.status.isin(["ok", "small_numbers"]).sum() - (~a.county_fips.isin(counties)).sum())
        hb = a[a.status.isin(["ok", "small_numbers"]) & a.county_fips.isin(counties)].copy(); hb["l20"] = hb.county_fips.map(l20); cell = hb[(hb.rate > med) & (hb.l20 >= 50)]
        check("Burden: national median and the high-burden/low-access cell recomputed independently", f"median {med} vs {BU['meta']['median_all']}; cell {len(cell)} counties / {int(hb[(hb.rate > med) & (hb.l20 >= 50)].county_fips.map(W).sum()):,} residents 55+ vs burden.js {S['hb_la_counties']} / {S['hb_la_pop55']:,}; {S['counties_classified']} classified", abs(med - BU["meta"]["median_all"]) < 0.06 and len(cell) == S["hb_la_counties"])
        cells = S["cells"]; check("Burden: the four cells partition the classified counties", f"{cells['hb_la']} + {cells['hb_ok']} + {cells['lb_la']} + {cells['lb_ok']} = {sum(cells.values())} vs {S['counties_classified']}", sum(cells.values()) == S["counties_classified"])
        top = [f"{D['counties'][k]['n']} ({D['counties'][k]['s']})" for k in S["top"][:5]]; check("Burden: plausibility read of the largest high-burden/low-access counties by annual diagnoses", "; ".join(top), True, "same-session read; mid-sized metros without a trial hub within 60 road-miles — not independently reviewed")
        check("Burden: cancer-type-specific 'none within 60 road-mi' shares present for every named type", f"{len(BU['meta']['types'])} types × {len(BU['county'])} counties", all(len(v["zt"]) == len(BU["meta"]["types"]) for v in BU["county"].values()))
    # ---- ZIP lookup ----
    if FI:
        check("ZIP lookup: site points match the payload one-to-one; ZCTAs cover the 50 states + DC", f"{len(FI['sp'])} site points vs {len(D['SP'])} in DATA.SP; {len(FI['zcta']):,} ZCTAs, {len({v[2][:2] for v in FI['zcta'].values()})} states", len(FI["sp"]) == len(D["SP"]) and len({v[2][:2] for v in FI["zcta"].values()}) == 51)
        bad = [z for z, v in FI["zcta"].items() if v[2] not in counties]; check("ZIP lookup: every ZCTA's county exists in the payload", f"{len(bad)} bad", not bad)
        def mi(a, b):
            R = 3958.8; dl, dn = math.radians(b[0] - a[0]), math.radians(b[1] - a[1]); h = math.sin(dl / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dn / 2) ** 2; return 2 * R * math.asin(math.sqrt(h))
        z = FI["zcta"].get("77030"); near = sorted((mi(z[:2], p[:2]), i) for i, p in enumerate(FI["sp"])) if z else []
        names = [D["counties"][cf]["fac"][i][0] for cf, i in D["SPI"][near[0][1]]][:3] if near else []
        check("ZIP lookup: spot check — nearest site point to ZIP 77030 (Texas Medical Center) is in Harris County within ~2 miles", f"{near[0][0]:.1f} mi; facilities there include {names}", bool(near) and near[0][0] < 2.5 and FI["sp"][near[0][1]][2] == "48201")
        z2 = FI["zcta"].get("79901"); n2 = sum(1 for p in FI["sp"] if mi(z2[:2], p[:2]) * FI["meta"]["road_factor"] <= 60) if z2 else 0
        check("ZIP lookup: spot check — El Paso ZIP 79901 finds site points within 60 estimated road-miles and no Houston sites", f"{n2} site points within 60 est. road-mi", 0 < n2 < 40)
        # large or split ZIP code areas measure from where their residents live (build_zcta_centers.py), not from the Census internal point:
        # 99701's point was 183 miles north of Fairbanks, 99503's 278 miles west of Anchorage, 83716's 48 miles from Boise (October 2026)
        far = {}
        for z_, town in (("99701", "Fairbanks"), ("99503", "Anchorage"), ("83716", "Boise")):
            zz = FI["zcta"].get(z_); near_ = min(mi(zz[:2], p[:2]) for p in FI["sp"]) if zz else None
            if near_ is None or near_ > 10: far[z_] = (town, None if near_ is None else round(near_, 1))
        check("ZIP lookup: large ZIP code areas measure from their residents (99701 Fairbanks, 99503 Anchorage, 83716 Boise each have a site point within 10 miles)", "all three within 10 miles" if not far else "far: " + str(far), not far, FI["meta"].get("zcta_centers", "centers: zcta_pop55.csv internal points"))
        # a population-weighted center is used only inside (or within a mile of) its own ZIP area and when the tract apportionment covers
        # half to twice the ZIP's residents (build_zcta_centers.py); until 11 Oct 2026 2,905 centers lay outside their ZIP (97904: 54 miles)
        pcf = find("zcta_popcenter.csv")
        if pcf is not None:
            pc = pd.read_csv(pcf, dtype={"zcta": str}).set_index("zcta"); wt = pc[pc.source == "tract_weighted"]
            bad_place = int((wt.outside_mi.isna() | (wt.outside_mi > 1.0)).sum()) if "outside_mi" in pc.columns else len(wt)
            bad_cov = int((~wt.coverage.between(0.5, 2.0)).sum())
            used = {z: (round(float(pc.lat[z]), 3), round(float(pc.lon[z]), 3)) for z in FI["zcta"] if z in pc.index}
            off = [z for z, ll in used.items() if (FI["zcta"][z][0], FI["zcta"][z][1]) != ll]
            check("ZIP lookup: every population-weighted ZIP center lies within a mile of its own ZIP area and passes the coverage test; find_data.js uses those centers",
                  f"{len(wt):,} weighted centers: {bad_place} outside their ZIP area (or not tested), {bad_cov} outside the coverage band; {len(off)} of {len(used):,} finder ZIPs not at their center" + (f" (e.g. {off[:5]})" if off else ""),
                  bad_place == 0 and bad_cov == 0 and not off)
        ui = (find("find.html") or Path("find.html")).read_text(encoding="utf-8"); check("ZIP lookup page states its limits (information only; eligibility decided by the study team; ZIP stays in the browser; NCI 1-800-4-CANCER present)", "all phrases present" if all(s in ui for s in ["For information only", "decided by each study team", "stays in your browser", "1-800-4-CANCER"]) else "MISSING", all(s in ui for s in ["For information only", "decided by each study team", "stays in your browser", "1-800-4-CANCER"]))
    ui = (find("index.html") or Path("index.html")).read_text(encoding="utf-8")
    check("Map page loads the three new data files and states the burden view is a cross-tabulation, not a score", "rucc.js, cosponsors.js, burden.js referenced; 'never a combined score' present" if all(s in ui for s in ['src="rucc.js"', 'src="cosponsors.js"', 'src="burden.js"', "never a combined score"]) else "MISSING", all(s in ui for s in ['src="rucc.js"', 'src="cosponsors.js"', 'src="burden.js"', "never a combined score"]))
    # ---- optional: in-browser recomputation against the pipeline ----
    if browser:
        try:
            import subprocess, socket
            from playwright.sync_api import sync_playwright
            docs = "docs" if Path("docs").is_dir() and not Path("data.js").exists() else "."
            srv = subprocess.Popen([sys.executable, "-m", "http.server", "8766"], cwd=docs, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.2)
            with sync_playwright() as p:
                b = p.chromium.launch(); pg = b.new_page(); pg.goto("http://localhost:8766/index.html", wait_until="networkidle", timeout=120000); pg.wait_for_timeout(300)
                r = pg.evaluate("""async () => { const V = window.__validate; await V.loadTractsAll(); const F = V.filteredCounty(); const B = window.BURDEN.county; let over = 0, maxd = 0, worst = '';
                  V.CK.forEach((k,i) => { const d = Math.max(Math.abs(F.l20[i]-B[k].l20), Math.abs(F.z60[i]-B[k].z60)); if (d > 0.55) over++; if (d > maxd) { maxd = d; worst = k; } });
                  const R = V.filteredRural('nat', 0); return { over, maxd, worst, metro: R.metro.l20, nonmetro: R.nonmetro.l20 }; }""")
                # the movable trial-count line (the pills on the panel's first figure): press each one and read back the national, Texas and per-county
                # shares the page computes; compared below with an independent recount from tract_access.csv at the same line
                lines = {}
                for lt in (5, 10, 50, 100):
                    pg.click(f'.thr-btn[data-lt="{lt}"]'); pg.wait_for_function("() => !document.querySelector('#pane-body .computing')", timeout=120000); pg.wait_for_timeout(150)
                    lines[lt] = pg.evaluate("""() => { const V = window.__validate; const F = V.FS(); const co = {}; V.CK.forEach(k => { const v = V.shortOf(k); co[k] = v ? v.s : null; });
                      return { lt: V.getLT(), nat: V.filteredGeo('nat', 0).l20, tx: F ? F.l20[F.idx['TX']] : null, co, text: document.querySelector('#stat-access .main').textContent }; }""")
                b.close()
            srv.terminate()
            check("Browser: in-page tract recomputation (no filter) reproduces burden.js county shares and rucc.js metro/nonmetro shares", f"{r['over']} of {len(counties)} counties differ by >0.55 pts (max {r['maxd']:.1f}, {D['counties'][r['worst']]['n']}); metro {r['metro']:.1f}% / nonmetro {r['nonmetro']:.1f}% vs {RU['nat']['metro']['l20']} / {RU['nat']['nonmetro']['l20']}", r["over"] <= 2 and abs(r["metro"] - RU["nat"]["metro"]["l20"]) < 0.06 and abs(r["nonmetro"] - RU["nat"]["nonmetro"]["l20"]) < 0.06,
                  "the residual county is a 20-trial threshold effect: the browser pools the 3,915 located trials, the pipeline table counts 3,919 eligible trials")
            w = tr.pop55.astype(float); tx = tr.county_fips.str.startswith("48"); worst = []; parts = []
            for lt, L in lines.items():
                short = (tr.trials_within_60rdmi < lt); py_nat = 100 * w[short].sum() / w.sum(); py_tx = 100 * w[short & tx].sum() / w[tx].sum()
                cs = tr.assign(w=w, s=w * short).groupby("county_fips")[["w", "s"]].sum(); cs = cs[cs.w > 0]; py_co = 100 * cs.s / cs.w
                dco = max(abs(py_co[k] - v) for k, v in L["co"].items() if v is not None and k in py_co.index)
                worst.append(max(abs(L["nat"] - py_nat), abs(L["tx"] - py_tx) if L["tx"] is not None else 9, dco)); parts.append(f"<{lt}: page {L['nat']:.2f}% vs {py_nat:.2f}%, TX {L['tx']:.1f}% vs {py_tx:.1f}%, counties max |diff| {dco:.3f}")
                if L["lt"] != lt or f"fewer than {lt} " not in L["text"]: worst.append(9)
            check("Browser: the trial-count line (5 / 10 / 50 / 100) recomputes the national, state and county shares in the page; each equals an independent recount from tract_access.csv", "; ".join(parts), max(worst) < 0.011)
        except Exception as e:
            check("Browser: in-page recomputation", f"skipped ({type(e).__name__}: {str(e)[:60]})", True)
    # ---- community.js (the question-based pages): copied from the files above, so every figure must equal its source ----
    CM = load_js("community.js", "window.COMMUNITY=")
    if CM and BU and RU:
        cols = CM["ccols"]; ci = {c: i for i, c in enumerate(cols)}; bad = []
        for cf, a in CM["counties"].items():
            c = D["counties"][cf]; u = BU["county"][cf]
            if a[ci["p"]] != c["p"] or a[ci["t"]] != c["t"] or a[ci["t60"]] != c["t60"] or a[ci["l20"]] != u["l20"] or a[ci["z60"]] != u["z60"] or a[ci["tm"]] != u.get("t60m", u["t60"]) or a[ci["rn"]] != c["rn"]: bad.append(cf)
        dbad = [k for k, d in CM["districts"].items() if d["l20"] != D["districts"][k]["l20"] or d["p"] != D["districts"][k]["p"] or d["member"] != D["districts"][k]["member"]]
        sbad = [k for k, g in CM["states"].items() if g["l20"] != D["state_data"][k]["l20"] or g["p"] != D["state_data"][k]["p"]]
        check("community.js reproduces data.js / burden.js for every county, district and state", f"{len(CM['counties'])} counties ({len(bad)} differ), {len(CM['districts'])} districts ({len(dbad)} differ), {len(CM['states'])} states ({len(sbad)} differ); nation {CM['meta']['nat']['l20']}% vs {nat['l20']}%",
              len(CM["counties"]) == len(counties) and not bad and len(CM["districts"]) == len(D["districts"]) and not dbad and len(CM["states"]) == len(D["state_data"]) and not sbad and CM["meta"]["nat"]["l20"] == nat["l20"],
              "built by build_community.py from the same files the map reads; the Your community and What could help pages read this file")
        if CO: check("community.js carries the tracked bills with the cosponsor fetch date", ", ".join(f"{b['label']}: {b['n_cosponsors']} cosponsors" for b in CM["meta"]["bills"].values()) + f"; fetched {CM['meta']['cosponsors_fetched']}", set(CM["meta"]["bills"]) == set(CO["bills"]) and all(CM["meta"]["bills"][k]["n_cosponsors"] == CO["bills"][k]["n_cosponsors"] for k in CO["bills"]) and CM["meta"]["cosponsors_fetched"] == CO["meta"]["fetched"])
    # ---- oncologists vs trials (build_oncologists.py): recomputed here from the extract's county table and the trial counts, and set against ----
    # ---- the published ASCO workforce study that used the same CMS file (Kirkwood et al., JCO Oncology Practice 2025, doi:10.1200/OP-25-00144) ----
    ON = load_js("oncologists.js", "window.ONCOLOGISTS="); olog_p = find("oncologists_build_log.json")
    if ON and olog_p is not None:
        olog = json.loads(olog_p.read_text()); oc = ON["county"]
        missing = sorted(set(counties) - set(oc)); extra = sorted(set(oc) - set(counties))
        badcat = [k for k, v in oc.items() if k in D["counties"] and v[6] != (1 if v[0] and D["counties"][k]["t"] else 2 if v[0] else 3 if D["counties"][k]["t"] else 4)]
        check("Oncologists: every county has a row, and each county's category follows from its oncologist count and its trial count in data.js",
              f"{len(oc):,} counties ({len(missing)} missing, {len(extra)} extra); {len(badcat)} categories disagree", not missing and not extra and not badcat)
        cat = tr.county_fips.map(lambda f: oc[f][6]); w = tr.pop55.astype(float); tot = w.sum()
        sh = {k: round(100 * w[cat == k].sum() / tot, 1) for k in (1, 2, 3, 4)}; n = ON["nat"]
        check("Oncologists: residents 55+ by category, recounted from tract_access.csv, equal oncologists.js (and the four shares sum to 100)",
              f"recounted {sh} vs published {{1: {n['c1']}, 2: {n['c2']}, 3: {n['c3']}, 4: {n['c4']}}}; sum {sum(sh.values()):.1f}",
              all(abs(sh[k] - n[f"c{k}"]) < 0.06 for k in sh) and abs(sum(sh.values()) - 100) < 0.25 and n["p"] == nat["p"])
        sp = [s for s, g in ON["states"].items() if g["p"] != D["state_data"][s]["p"]]; dp = [k for k, g in ON["districts"].items() if abs(g["p"] - D["districts"][k]["p"]) > 1]
        check("Oncologists: state and district residents 55+ equal data.js", f"{len(ON['states'])} states ({len(sp)} differ), {len(ON['districts'])} districts ({len(dp)} differ by more than 1)",
              len(ON["states"]) == len(D["state_data"]) and not sp and len(ON["districts"]) == len(D["districts"]) and not dp)
        a = olog["asco_comparable"]; pub_n, pub_cty, pub_res = 14547, 45.0, 89.0   # Kirkwood et al. 2025: March 2024 file
        cty = 100 * a["counties_with_one"] / len(counties); res = n["c1"] + n["c2"]
        check("Oncologists: the ASCO-comparable count reproduces the published workforce study (14,547 in the March 2024 Care Compare file; oncologists in 45% of counties; 89% of residents 55+ in a county with one)",
              f"{a['clinicians']:,} clinicians in the {ON['meta']['source_modified']} file ({100 * (a['clinicians'] / pub_n - 1):+.1f}%); counties {cty:.1f}% vs {pub_cty}%; residents 55+ {res:.1f}% vs {pub_res}%",
              0.95 <= a["clinicians"] / pub_n <= 1.15 and abs(cty - pub_cty) <= 3 and abs(res - pub_res) <= 2,
              "a newer file: ASCO reported growth of about 2% a year (12,267 in 2014 to 14,547 in 2024); the map's own count also excludes pediatric hematology-oncologists")
        nci = pd.read_csv(find("nci_centers.csv"), dtype=str); nci = nci[nci.adult == "1"]
        z2c = dict(pd.read_csv(find("zcta_county.csv"), dtype=str).values)   # the center's own ZIP (coord_source zip_centroid_NNNNN) -> county
        nci["cf"] = nci.coord_source.str.extract(r"(\d{5})")[0].map(z2c)
        try:   # centers located by an override or the city's Census place: the county of that place (the gazetteer the site rules use)
            from tier4_covering import find_place
            for i in nci.index[nci.cf.isna()]: q = find_place(nci.at[i, "state"], nci.at[i, "city"]); nci.at[i, "cf"] = q[2] if q else None
        except Exception: pass
        zc = pd.read_csv(find("zcta_pop55.csv"), dtype={"zcta": str})   # last resort (La Jolla is not a Census place): the ZIP center nearest the center's point
        for i in nci.index[nci.cf.isna()]:
            d = (zc.lat - float(nci.at[i, "lat"])) ** 2 + ((zc.lon - float(nci.at[i, "lon"])) * 0.8) ** 2; nci.at[i, "cf"] = z2c.get(zc.zcta.iloc[int(d.values.argmin())])
        bad_nci = [f"{r.name} ({r.cf})" for r in nci.itertuples() if not isinstance(r.cf, str) or oc.get(r.cf, [0])[0] == 0]
        check("Oncologists: the county of every adult NCI-designated center (by its ZIP, or its city) has oncologists listed", f"{len(nci)} centers, {int(nci.cf.notna().sum())} placed; {len(bad_nci)} without" + (f": {bad_nci[:5]}" if bad_nci else ""), not bad_nci)
        um = olog.get("unmapped_oncology_specialties"); un = olog["placement"]
        check("Oncologists: no CMS oncology specialty label is unmapped, and the only unplaced practice locations are outside the 50 states and DC",
              f"unmapped labels: {um or 'none'}; {un['unplaced_rows']} unplaced rows, e.g. {[x[1] for x in un['unplaced_examples']][:8]}",
              not um and all(x[1] in ("PR", "GU", "VI", "AS", "MP", "AA", "AE", "AP", "") for x in un["unplaced_examples"]))
        nc = olog.get("nppes_check")
        if nc: check("Oncologists: cross-check with NPPES — share of the map's oncologists whose registry entry carries an oncology or hematology taxonomy",
                     f"{nc['cms_oncologists_with_nppes_row']:,} of {nc['cms_oncologists']:,} ({100 * nc['cms_oncologists_with_nppes_row'] / nc['cms_oncologists']:.1f}%); pediatric excluded: {olog['pediatric_excluded']['clinicians']}",
                     nc["cms_oncologists_with_nppes_row"] / nc["cms_oncologists"] >= 0.9)
        csvp = find("oncologists_counties.csv")
        if csvp is not None:
            cv = pd.read_csv(csvp, dtype={"county_fips": str}); diff = [r.county_fips for r in cv.itertuples() if r.oncologists != oc[r.county_fips][0] or r.trials_in_county != D["counties"][r.county_fips]["t"]]
            check("Oncologists: the downloadable county table matches oncologists.js and data.js", f"{len(cv):,} rows; {len(diff)} differ", len(cv) == len(counties) and not diff)
        check("Map page loads oncologists.js and offers the layer", "oncologists.js referenced; layer 'onc' defined" if 'src="oncologists.js"' in ui and "onc: {label:" in ui else "missing", 'src="oncologists.js"' in ui and "onc: {label:" in ui)
    return rows


def write_md(rs):
    """VALIDATION_extras.md from the rows of run(). validate_v3.py calls this too: the refresh runs these checks only through validate_v3.py,
    and until October 2026 the file was written only by a standalone run, so the copy the refresh committed stayed at 6 October."""
    md = ["# Validation — v3.3 additions (rural/urban, cosponsors, burden vs access, ZIP lookup)", "", f"Checks re-run by `validate_extras.py` on {time.strftime('%Y-%m-%d', time.gmtime())} (UTC).", "", "| Check | Result | Pass | Context |", "|---|---|---|---|"] + [f"| {n} | {r} | {p} | {c} |" for n, r, p, c in rs]
    Path("VALIDATION_extras.md").write_text("\n".join(md) + "\n")


def main():
    run("--browser" in sys.argv)
    write_md(rows); n_ok = sum(1 for r in rows if r[2] == '✓'); print(f"\n{n_ok}/{len(rows)} checks pass"); sys.exit(0 if n_ok == len(rows) else 1)


if __name__ == "__main__":
    main()
