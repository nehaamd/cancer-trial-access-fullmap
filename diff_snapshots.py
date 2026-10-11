"""What changed since the previous refresh? Compares two registry snapshots (data/snapshots/<date>/ vs data/raw/).

Usage: python diff_snapshots.py [previous_dir] [current_dir] [--no-county-movement]   (defaults: latest data/snapshots/* vs data/raw)
Reports, for the trial universe the pipeline keeps (eligible 55+ after QC):
  trials newly listed / no longer listed, status changes, phase changes, age-cap changes, recruiting sites newly listed / no longer listed,
  and how the county counts moved. Writes out_adult55/refresh_diff.json and docs/changes.js (window.CHANGES) for the web page.
The county movement re-assigns both pulls with metrics_us.assign_sites, which needs geopandas and the Census county files
data/geo/cb.zip and data/geo/cb500_2021.zip (not in the repository; the refresh workflow downloads them). Without them the script
stops instead of writing a page that would say no county changed; --no-county-movement writes the rest without that list.
Each pull's method version is config.method_of(its stamp, its date), so a method registered after the pull that first used it
(config.METHOD_CHANGES "first_pull") still marks the rows before it.
"""
import json, sys
from pathlib import Path
import pandas as pd
import config

RAW, OUT, DOCS = Path("data/raw"), Path("out_adult55"), Path("docs")


def load(d):
    t = pd.read_csv(Path(d) / "trials.csv", dtype=str, keep_default_na=False)
    if "excludes_55plus" in t.columns: t = t[t.excludes_55plus == "0"]
    s = pd.read_csv(Path(d) / "us_sites.csv", dtype=str, keep_default_na=False); s = s[s.nct_id.isin(t.nct_id)]
    log = json.load(open(Path(d) / "fetch_log.json")); return t.set_index("nct_id"), s, log


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]; no_counties = "--no-county-movement" in sys.argv[1:]
    prev_dir = args[0] if len(args) > 0 else sorted(Path("data/snapshots").glob("*"))[-1]
    cur_dir = args[1] if len(args) > 1 else RAW
    tp, sp, lp = load(prev_dir); tc, sc, lc = load(cur_dir)
    new = sorted(set(tc.index) - set(tp.index)); gone = sorted(set(tp.index) - set(tc.index)); both = sorted(set(tc.index) & set(tp.index))
    changes = []
    for n in both:
        for col, lab in (("overall_status", "status"), ("phases", "phase"), ("maximum_age", "maximum age"), ("minimum_age", "minimum age"), ("brief_title", "title")):
            if col in tp.columns and col in tc.columns and tp.loc[n, col] != tc.loc[n, col]: changes.append({"nct_id": n, "field": lab, "from": tp.loc[n, col], "to": tc.loc[n, col]})
    key = lambda df: set(zip(df.nct_id, df.facility.str.lower().str.strip(), df.city.str.lower().str.strip(), df.state))
    kp, kc = key(sp), key(sc); sites_new = sorted(kc - kp); sites_gone = sorted(kp - kc)
    # sites at trials that exist in both pulls (i.e. a trial added/removed a location), vs sites of new/removed trials
    both_set = set(both); sites_new_existing = [x for x in sites_new if x[0] in both_set]; sites_gone_existing = [x for x in sites_gone if x[0] in both_set]
    summ = {"previous_pull": lp["timestamp_utc"][:19] + "Z", "current_pull": lc["timestamp_utc"][:19] + "Z", "previous_registry_data": lp.get("registry_data_timestamp"), "current_registry_data": lc.get("registry_data_timestamp"),
            "trials_previous": int(len(tp)), "trials_current": int(len(tc)), "trials_new": len(new), "trials_no_longer_listed": len(gone), "field_changes": len(changes),
            "recruiting_sites_previous": int(len(sp)), "recruiting_sites_current": int(len(sc)), "sites_new_at_existing_trials": len(sites_new_existing), "sites_removed_at_existing_trials": len(sites_gone_existing),
            "sites_of_new_trials": len(sites_new) - len(sites_new_existing), "sites_of_removed_trials": len(sites_gone) - len(sites_gone_existing)}
    detail = {"new_trials": [{"nct_id": n, "title": tc.loc[n, "brief_title"], "phase": tc.loc[n, "phases"], "sponsor": tc.loc[n, "lead_sponsor"] if "lead_sponsor" in tc.columns else "", "n_us_sites": int(tc.loc[n, "n_us_sites"])} for n in new],
              "no_longer_listed": [{"nct_id": n, "title": tp.loc[n, "brief_title"], "last_status": tp.loc[n, "overall_status"], "note": "not returned by the recruiting/treatment/oncology query today (status may have changed to a non-recruiting value, or the record was withdrawn)"} for n in gone],
              "field_changes": changes, "sites_new_at_existing_trials": [{"nct_id": a, "facility": b, "city": c, "state": d} for a, b, c, d in sites_new_existing][:500],
              "sites_removed_at_existing_trials": [{"nct_id": a, "facility": b, "city": c, "state": d} for a, b, c, d in sites_gone_existing][:500]}
    # county movement. Both pulls are assigned to counties here, with the current rules (metrics_us.assign_sites), so the list
    # shows what the registry changed and nothing else: a change in how sites are assigned to counties never appears as movement.
    try:
        from metrics_us import assign_sites
        cmc = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str}); names = cmc.set_index("county_fips")
        count = lambda sites: assign_sites(sites, None).dropna(subset=["county_fips"]).groupby("county_fips").nct_id.nunique().reindex(names.index).fillna(0).astype(int)
        cmp_, cur_ = count(sp), count(sc)
        if not (cur_ == names.trials_in_county).all(): summ["county_change_note"] = "county recount differs from county_metrics.csv; check the trial universe"
        d = cur_ - cmp_; mv = d[d != 0]
        # labels: the Census Bureau's full name of the county equivalent from data.js ("St. Louis city" and "St. Louis County", "Baltimore city",
        # "Fairfax County" and "Fairfax city"), the state once ("District of Columbia", not twice), and the FIPS code for a page that wants to link it
        nl = {}
        if (DOCS / "data.js").exists():
            s_ = (DOCS / "data.js").read_text(encoding="utf-8"); nl = {k: v.get("nl") for k, v in json.loads(s_[s_.index("=") + 1:].strip().rstrip(";"))["counties"].items()}
        def label(f):
            n, st = nl.get(f) or names.loc[f, "county_name"], names.loc[f, "state_name"]
            return n if n == st else f"{n}, {st}"
        detail["county_changes"] = [{"county": label(f), "fips": f, "from": int(cmp_[f]), "to": int(cur_[f])} for f in mv.abs().sort_values(ascending=False, kind="stable").index[:60]]
        summ["counties_with_changed_trial_count"] = int(len(mv)); summ["counties_crossing_a_menu_threshold"] = int(((cmp_ >= 20) != (cur_ >= 20)).sum() + ((cmp_ >= 100) != (cur_ >= 100)).sum())
    except Exception as e:
        # the page prints "0 counties changed their trial count" when the count is missing, so never publish that silently
        if not no_counties: sys.exit(f"diff_snapshots.py: county movement not computed ({type(e).__name__}: {e}). It needs geopandas and data/geo/cb.zip + "
                                     "data/geo/cb500_2021.zip (see the refresh workflow); run with --no-county-movement to write the comparison without it.")
        summ["county_change_note"] = f"county movement not computed: {e}"; summ["counties_with_changed_trial_count"] = None
    # refresh history: one row per archived pull (data/snapshots/<date>/national_metrics_v3.json, kept since the first refresh) plus the current pull
    hist = []
    for d in sorted(Path("data/snapshots").glob("*")):
        nm, fl = d / "national_metrics_v3.json", d / "fetch_log.json"
        if nm.exists():
            n = json.load(open(nm)); f = json.load(open(fl)) if fl.exists() else {}
            tcount = None
            if (d / "trials.csv").exists():
                tt = pd.read_csv(d / "trials.csv", dtype=str, keep_default_na=False); tcount = int((tt.excludes_55plus == "0").sum()) if "excludes_55plus" in tt.columns else int(len(tt))
            pull = f.get("timestamp_utc", d.name)[:10]
            hist.append({"pull": pull, "registry_data": (f.get("registry_data_timestamp") or "")[:10] or None, "trials": tcount, "method": config.method_of(n.get("method_version", 1), pull),
                         "l20": n["pct_lt20_trials_within_60rdmi"], "z60": n["pct_zero_trials_within_60rdmi"], "g60b": n["pct_gt60rdmi_broad_menu"], "g60n": n["pct_gt60rdmi_nci"], "medn": n["median_road_mi_nci"]})
    ncur = json.load(open(OUT / "national_metrics_v3.json"))
    hist.append({"pull": lc["timestamp_utc"][:10], "registry_data": (lc.get("registry_data_timestamp") or "")[:10] or None, "trials": int(len(tc)), "method": config.method_of(ncur.get("method_version", 1), lc["timestamp_utc"]), "l20": ncur["pct_lt20_trials_within_60rdmi"], "z60": ncur["pct_zero_trials_within_60rdmi"],
                 "g60b": ncur["pct_gt60rdmi_broad_menu"], "g60n": ncur["pct_gt60rdmi_nci"], "medn": ncur["median_road_mi_nci"], "current": True})
    # method changes that fall inside the history shown (config.METHOD_CHANGES): rows on either side are not directly comparable
    seen = {h["method"] for h in hist}; summ["method_version"] = hist[-1]["method"]
    # the method of the previous pull compared above (when it is an archived pull): if it differs, the comparison straddles a method change
    pm = [h["method"] for h in hist[:-1] if h["pull"] == lp["timestamp_utc"][:10]]
    if pm: summ["previous_method_version"] = pm[-1]
    methods = [m for m in config.METHOD_CHANGES if m["version"] > min(seen) and m["version"] <= max(seen)]
    out = {"summary": summ, "history": hist, "method_changes": methods, **detail}; json.dump(out, open(OUT / "refresh_diff.json", "w"), indent=2)
    (DOCS / "changes.js").write_text("window.CHANGES=" + json.dumps(out, separators=(",", ":"), ensure_ascii=False) + ";", encoding="utf-8")
    print(json.dumps(summ, indent=1)); print("examples of field changes:", changes[:5]); print("method changes shown:", [m["version"] for m in methods])


if __name__ == "__main__":
    main()
