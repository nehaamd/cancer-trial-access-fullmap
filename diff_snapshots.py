"""What changed since the previous refresh? Compares two registry snapshots (data/snapshots/<date>/ vs data/raw/).

Usage: python diff_snapshots.py [previous_dir] [current_dir]   (defaults: latest data/snapshots/* vs data/raw)
Reports, for the trial universe the pipeline keeps (eligible 55+ after QC):
  trials newly listed / no longer listed, status changes, phase changes, age-cap changes, recruiting sites newly listed / no longer listed,
  and how the county counts moved. Writes out_adult55/refresh_diff.json and docs/changes.js (window.CHANGES) for the web page.
"""
import json, sys
from pathlib import Path
import pandas as pd

RAW, OUT, DOCS = Path("data/raw"), Path("out_adult55"), Path("docs")


def load(d):
    t = pd.read_csv(Path(d) / "trials.csv", dtype=str, keep_default_na=False)
    if "excludes_55plus" in t.columns: t = t[t.excludes_55plus == "0"]
    s = pd.read_csv(Path(d) / "us_sites.csv", dtype=str, keep_default_na=False); s = s[s.nct_id.isin(t.nct_id)]
    log = json.load(open(Path(d) / "fetch_log.json")); return t.set_index("nct_id"), s, log


def main():
    prev_dir = sys.argv[1] if len(sys.argv) > 1 else sorted(Path("data/snapshots").glob("*"))[-1]
    cur_dir = sys.argv[2] if len(sys.argv) > 2 else RAW
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
    # county movement (needs the current county metrics and the previous site assignment; approximate via ZIP->county of both site sets if available)
    try:
        cmc = pd.read_csv(OUT / "county_metrics.csv", dtype={"county_fips": str}); prev_cm = Path(prev_dir) / "county_metrics.csv"
        if prev_cm.exists():
            cmp_ = pd.read_csv(prev_cm, dtype={"county_fips": str}).set_index("county_fips").trials_in_county; cur_ = cmc.set_index("county_fips").trials_in_county
            d = (cur_ - cmp_.reindex(cur_.index).fillna(0)); mv = d[d != 0]; names = cmc.set_index("county_fips")
            detail["county_changes"] = [{"county": f"{names.loc[f, 'county_name']}, {names.loc[f, 'state_name']}", "from": int(cmp_.get(f, 0)), "to": int(cur_[f])} for f in mv.abs().sort_values(ascending=False).index[:60]]
            summ["counties_with_changed_trial_count"] = int(len(mv)); summ["counties_crossing_a_menu_threshold"] = int(((cmp_.reindex(cur_.index).fillna(0) >= 20) != (cur_ >= 20)).sum() + ((cmp_.reindex(cur_.index).fillna(0) >= 100) != (cur_ >= 100)).sum())
    except Exception as e: summ["county_change_note"] = f"county movement not computed: {e}"
    # refresh history: one row per archived pull (data/snapshots/<date>/national_metrics_v3.json, kept since the first refresh) plus the current pull
    hist = []
    for d in sorted(Path("data/snapshots").glob("*")):
        nm, fl = d / "national_metrics_v3.json", d / "fetch_log.json"
        if nm.exists():
            n = json.load(open(nm)); f = json.load(open(fl)) if fl.exists() else {}
            tcount = None
            if (d / "trials.csv").exists():
                tt = pd.read_csv(d / "trials.csv", dtype=str, keep_default_na=False); tcount = int((tt.excludes_55plus == "0").sum()) if "excludes_55plus" in tt.columns else int(len(tt))
            hist.append({"pull": f.get("timestamp_utc", d.name)[:10], "registry_data": (f.get("registry_data_timestamp") or "")[:10] or None, "trials": tcount,
                         "l20": n["pct_lt20_trials_within_60rdmi"], "z60": n["pct_zero_trials_within_60rdmi"], "g60b": n["pct_gt60rdmi_broad_menu"], "g60n": n["pct_gt60rdmi_nci"], "medn": n["median_road_mi_nci"]})
    ncur = json.load(open(OUT / "national_metrics_v3.json"))
    hist.append({"pull": lc["timestamp_utc"][:10], "registry_data": (lc.get("registry_data_timestamp") or "")[:10] or None, "trials": int(len(tc)), "l20": ncur["pct_lt20_trials_within_60rdmi"], "z60": ncur["pct_zero_trials_within_60rdmi"],
                 "g60b": ncur["pct_gt60rdmi_broad_menu"], "g60n": ncur["pct_gt60rdmi_nci"], "medn": ncur["median_road_mi_nci"], "current": True})
    out = {"summary": summ, "history": hist, **detail}; json.dump(out, open(OUT / "refresh_diff.json", "w"), indent=2)
    (DOCS / "changes.js").write_text("window.CHANGES=" + json.dumps(out, separators=(",", ":"), ensure_ascii=False) + ";", encoding="utf-8")
    print(json.dumps(summ, indent=1)); print("examples of field changes:", changes[:5])


if __name__ == "__main__":
    main()
