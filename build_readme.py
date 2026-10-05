"""Rewrite the "Headline results" block of README.md from the refreshed data, so the README never quotes last month's numbers.

Reads docs/findings.js (written by build_findings.py), out_adult55/metrics_log.json and out_adult55/route_log.json. Replaces only
the text between the two marker lines in README.md; everything else in the README is left alone. Runs in run_refresh.sh after
build_findings.py. Usage: python build_readme.py
"""
import json, sys
from datetime import date
from pathlib import Path

START = "<!-- headline:start — rewritten by build_readme.py on every refresh; edit the script, not this block -->"
END = "<!-- headline:end -->"


def nice(iso):
    d = date.fromisoformat(str(iso)[:10]); return f"{d.day} {d.strftime('%B %Y')}"


def main():
    F = json.loads(Path("docs/findings.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    m, n, ru, bu, di = F["meta"], F["nat"], F["rural"], F["burden"], F["districts"]
    ml = json.load(open("out_adult55/metrics_log.json")); rl = json.load(open("out_adult55/route_log.json")); rr = rl["road_over_straightline_ratio_broad"]
    met, non = ru["metro"], ru["nonmetro"]; nci = (f"{m['nci_centers']} centers at {m['n_nci']} locations" if m.get("nci_centers") else f"{m['n_nci']} locations")
    lines = [START,
        "## Headline results (residents 55+, trials accepting some adults aged 55 or older, road miles from each census tract's population center)",
        f"Registry data as of {nice(m.get('registry_data_timestamp') or m['pull'])}: {m['trials']:,} listed trials at about {round(m['facilities'], -2):,} registry-listed facilities ({m['sitepoints']:,} distinct site locations).",
        f"- **{n['l20']}% of Americans 55+ have fewer than 20 recruiting cancer treatment trials within 60 road-miles of home; {n['z60']}% have none.** ({n['zc']}% live in a county with no trial — a county-boundary statistic that overstates isolation and is not the lead number.)",
        f"- **{n['g60b']}% live more than 60 road-miles from a broad menu** (a county with 100 or more trials); {n['g120b']}% more than 120; {n['nr']}% (Alaska, Hawaii) have no road connection to one at all.",
        f"- **{n['g60n']}% live more than 60 road-miles from an NCI-designated cancer center that treats adults** ({nci}); the median resident 55+ is {n['medn']} road-miles from one; {n['g120n']}% are more than 120.",
        f"- {ml['limited_menu_counties']} counties host at least a limited menu (20 or more trials), {ml['broad_menu_counties']} of them a broad menu; **{F['states_no_broad']} states have no broad-menu county**; {di['all_beyond_60_broad']} congressional districts have every resident 55+ beyond 60 road-miles of one.",
        f"- Road distance / straight-line distance to the nearest broad menu: median {rr['median']:.2f} (10th–90th percentile {rr['p10']:.2f}–{rr['p90']:.2f}); the common ×1.2 convention is too low for {rr['counties_where_x1_2_underestimated']:,} of {rr['counties_compared']:,} counties.",
        f"- **Rural vs urban (USDA Rural-Urban Continuum Codes, 2023): {non['l20']}% of residents 55+ in nonmetro counties (codes 4–9) have fewer than 20 recruiting trials within 60 road-miles, vs {met['l20']}% in metro counties; {non['z60']}% vs {met['z60']}% have none; median road distance to an NCI-designated center {non['medn']} vs {met['medn']} miles.** Nonmetro counties hold {100 * non['p'] / (non['p'] + met['p']):.1f}% of residents 55+.",
        f"- **Need vs access: {bu['hb_la_counties']:,} counties ({bu['hb_la_pop55']:,} residents 55+, about {bu['hb_la_cases']:,} new cancer diagnoses a year) have above-median all-sites incidence AND at least half of residents 55+ with fewer than 20 trials within 60 road-miles** — a cross-tabulation of the two published measures, never a combined score (the page lets the reader change the cancer site, the access criterion and the threshold).",
        f"- Router check: {m['router']['pairs']} published city-pair driving distances, mean difference {m['router']['mean_pct']}%" + (f"; {m['router']['local']['pairs']} local routes (short in-town trips and water crossings), {m['router']['local']['note']}" if m["router"].get("local") else "") + ". Reference distances are approximate; see VALIDATION_v3.md.",
        END]
    p = Path("README.md"); s = p.read_text(encoding="utf-8")
    if START not in s or END not in s: sys.exit("README.md has no headline markers; nothing rewritten")
    a, b = s.index(START), s.index(END) + len(END); new = s[:a] + "\n".join(lines) + s[b:]
    if new != s: p.write_text(new, encoding="utf-8")
    print("README.md headline block", "updated" if new != s else "unchanged", f"({n['l20']}% <20 within 60 mi; {n['z60']}% none; {m['trials']:,} trials)")


if __name__ == "__main__":
    main()
