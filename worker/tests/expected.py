#!/usr/bin/env python3
"""Independent expected values for worker/tests/engine.test.js.

Recomputes, from the raw files in docs/ (never through the engine), the data-dependent facts the engine tests assert, and
writes worker/tests/expected.json. Run with:  python3 -I worker/tests/expected.py
Only the standard library is used. Every helper here is ordinary arithmetic on the published rows; where the engine's
contract defines a rule (nulls last, ties by pop55 desc then name, 1-decimal means) the same rule is applied here by hand."""
import json
import os
import re
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
DOCS = os.path.join(ROOT, 'docs')


def read_json(rel):
    with open(os.path.join(DOCS, rel), encoding='utf-8') as fh:
        return json.load(fh)


def read_window(rel):
    """docs/x.js holds `window.X = {...};` — slice after the first '=' and drop the trailing semicolon."""
    with open(os.path.join(DOCS, rel), encoding='utf-8') as fh:
        text = fh.read()
    body = text[text.index('=') + 1:].strip()
    if body.endswith(';'):
        body = body[:-1]
    return json.loads(body)


def r1(x):
    return None if x is None else round(x + 0.0, 1)


def pop_name_key(row):
    """the contract's tie-break: pop55 desc, then name asc"""
    return (-(row.get('pop55') or 0), row['name'])


def order(rows, field_fn, desc=True):
    """sort rows by a value with nulls last; ties by pop55 desc then name"""
    with_val = [r for r in rows if field_fn(r) is not None]
    nulls = [r for r in rows if field_fn(r) is None]
    with_val.sort(key=lambda r: ((-field_fn(r)) if desc else field_fn(r), pop_name_key(r)))
    nulls.sort(key=pop_name_key)
    return with_val + nulls


def wmean(rows, field_fn, weight_fn):
    num = den = 0.0
    for r in rows:
        v, w = field_fn(r), weight_fn(r)
        if v is not None and w is not None and w > 0:
            num += v * w
            den += w
    return r1(num / den) if den > 0 else None


def main():
    counties = read_json('api/all_counties.json')
    districts = read_json('api/all_districts.json')
    states = read_json('api/all_states.json')
    national = read_json('api/national.json')
    zips = read_json('zip_county.json')
    places = read_json('places.json')['places']
    DATA = read_window('data.js')
    BURDEN = read_window('burden.js')
    MORTALITY = read_window('mortality.js')
    RUCC = read_window('rucc.js')
    COSPONSORS = read_window('cosponsors.js')
    FINDINGS = read_window('findings.js')
    CHANGES = read_window('changes.js')
    T = DATA['T']
    E = {}

    E['counts'] = {'counties': len(counties), 'districts': len(districts), 'states': len(states),
                   'facilities': sum(len(c.get('fac', [])) for c in DATA['counties'].values()),
                   'facilities_unresolved': sum(1 for c in DATA['counties'].values() for fa in c.get('fac', []) if fa[5]),
                   'nci': len(DATA['nci']), 'senators': sum(len(s.get('senators') or []) for s in states),
                   'cosponsor_rows': sum(len(v) for v in COSPONSORS['by_member'].values()),
                   'trials': len(T['id']), 'history': len(CHANGES['history'])}

    # --- query: TX counties with oncologists but no trial in the county ---
    tx = [c for c in counties if c['state'] == 'TX']
    hit = [c for c in tx if (c.get('oncologists') or {}).get('count') is not None and c['oncologists']['count'] > 0 and c.get('trials_listed_here') == 0]
    hit.sort(key=pop_name_key)
    E['tx_onc_no_trials'] = {'count': len(hit), 'in_scope': len(tx), 'ids': [c['id'] for c in hit], 'sum_pop55': sum(c['pop55'] for c in hit),
                             'first3': [c['id'] for c in hit[:3]], 'class2_count': sum(1 for c in tx if (c.get('oncologists') or {}).get('class') == 2)}

    # --- order_by with nulls: TX counties by mortality.all desc ---
    mort = lambda c: (c.get('mortality') or {}).get('all')
    ordered = order(tx, mort, desc=True)
    E['tx_top5_mortality'] = {'ids': [c['id'] for c in ordered[:5]], 'values': [mort(c) for c in ordered[:5]], 'nulls': sum(1 for c in tx if mort(c) is None)}
    medn = lambda c: c.get('median_road_mi_nci')
    all_by_medn = order(counties, medn, desc=True)
    E['medn_nulls_last'] = {'top_id': all_by_medn[0]['id'], 'top_value': medn(all_by_medn[0]), 'nulls': sum(1 for c in counties if medn(c) is None),
                            'last_ids_are_null': all([medn(c) is None for c in all_by_medn[-5:]]), 'tail5_ids': [c['id'] for c in all_by_medn[-5:]]}
    # ties: counties with pct_lt20 == 100 and trials_listed_here == 0, ordered by pct_lt20 desc → first is the most populous of them
    tied = [c for c in counties if c.get('pct_lt20_trials_within_60rdmi') == 100.0]
    tied.sort(key=pop_name_key)
    E['tie_break'] = {'n': len(tied), 'first3': [c['id'] for c in tied[:3]]}

    # --- ops ---
    E['ops'] = {
        'no_route_null': sum(1 for c in counties if c.get('no_road_route_reason') is None),
        'no_route_island': sum(1 for c in counties if c.get('no_road_route_reason') == 'island'),
        'no_route_not_null': sum(1 for c in counties if c.get('no_road_route_reason') is not None),
        'tx_pct_between_40_60': sum(1 for c in tx if c.get('pct_lt20_trials_within_60rdmi') is not None and 40 <= c['pct_lt20_trials_within_60rdmi'] <= 60),
        'name_contains_hidalgo': sum(1 for c in counties if 'hidalgo' in c['name'].lower()),
        'tx34_counties': sorted(next(d for d in districts if d['id'] == 'TX-34')['counties']),
        'districts_intersect_48215': sorted(d['id'] for d in districts if '48215' in d.get('counties', [])),
        'tx_any_of_class2_or_broad': sum(1 for c in tx if (c.get('oncologists') or {}).get('class') == 2 or (c.get('trials_listed_here') or 0) >= 100),
        'center_gt_wmean': sum(1 for c in counties if c.get('trials_within_60rdmi_of_center') is not None and c.get('wmean_trials_within_60rdmi') is not None and c['trials_within_60rdmi_of_center'] > c['wmean_trials_within_60rdmi']),
        'tx_metro_false': sum(1 for c in tx if c.get('metro') is False),
        'states_in_tx_ok': sorted(s['id'] for s in states if s['id'] in ('TX', 'OK')),
        'tx_rucc_in_8_9': sum(1 for c in tx if c.get('rucc') in (8, 9)),
        'tx_rucc_not_in_1_2_3': sum(1 for c in tx if c.get('rucc') is not None and c['rucc'] not in (1, 2, 3)),
        'tx_incidence_ne_ok': sum(1 for c in tx if (c.get('incidence') or {}).get('status') is not None and c['incidence']['status'] != 'ok'),
        'tx_pct_ge_50': sum(1 for c in tx if c.get('pct_lt20_trials_within_60rdmi') is not None and c['pct_lt20_trials_within_60rdmi'] >= 50),
        'tx_pct_lt_1': sum(1 for c in tx if c.get('pct_lt20_trials_within_60rdmi') is not None and c['pct_lt20_trials_within_60rdmi'] < 1),
        'tx_pct_le_0': sum(1 for c in tx if c.get('pct_lt20_trials_within_60rdmi') is not None and c['pct_lt20_trials_within_60rdmi'] <= 0),
        'tx_trials_gt_100': sum(1 for c in tx if (c.get('trials_listed_here') or 0) > 100),
    }

    # --- aggregate ---
    oh = [c for c in counties if c['state'] == 'OH']
    pct = lambda c: c.get('pct_lt20_trials_within_60rdmi')
    nonmetro = [c for c in oh if c.get('metro') is False]
    metro = [c for c in oh if c.get('metro') is True]
    E['oh_by_metro'] = {'nonmetro': {'n': len(nonmetro), 'sum_pop55': sum(c['pop55'] for c in nonmetro), 'wmean_pct_lt20': wmean(nonmetro, pct, lambda c: c['pop55']),
                                     'mean_pct_lt20': r1(sum(pct(c) for c in nonmetro) / len(nonmetro))},
                        'metro': {'n': len(metro), 'sum_pop55': sum(c['pop55'] for c in metro), 'wmean_pct_lt20': wmean(metro, pct, lambda c: c['pop55'])}}
    mt = [c for c in counties if c['state'] == 'MT']
    mt_vals = [medn(c) for c in mt if medn(c) is not None]
    E['mt_medn'] = {'n': len(mt), 'median': statistics.median(mt_vals), 'count_not_null': len(mt_vals), 'min': min(mt_vals), 'max': max(mt_vals), 'sum': sum(mt_vals)}
    inc_ok = [c for c in tx if (c.get('incidence') or {}).get('all') is not None]
    E['tx_agg'] = {'count': len(tx), 'sum_pop55': sum(c['pop55'] for c in tx), 'count_not_null_incidence': len(inc_ok),
                   'mean_incidence': r1(sum(c['incidence']['all'] for c in inc_ok) / len(inc_ok)),
                   'share_metro_true': r1(100.0 * sum(1 for c in tx if c.get('metro') is True) / sum(1 for c in tx if c.get('metro') is not None)),
                   'share_class_eq_2': r1(100.0 * sum(1 for c in tx if (c.get('oncologists') or {}).get('class') == 2) / sum(1 for c in tx if (c.get('oncologists') or {}).get('class') is not None)),
                   'max_pop55': max(c['pop55'] for c in tx), 'min_pop55': min(c['pop55'] for c in tx)}
    by_rucc = {}
    for c in counties:
        by_rucc.setdefault(str(c.get('rucc')) if c.get('rucc') is not None else 'null', 0)
        by_rucc[str(c.get('rucc')) if c.get('rucc') is not None else 'null'] += 1
    E['counties_by_rucc'] = by_rucc
    parties = {}
    for d in districts:
        p = (d.get('member') or {}).get('party')
        parties[str(p) if p is not None else 'null'] = parties.get(str(p) if p is not None else 'null', 0) + 1
    E['districts_by_party'] = parties

    # --- districts / members ---
    E['districts'] = {'not_cosponsor': sum(1 for d in districts if (d.get('member') or {}).get('ctma_hr3521') == 'none'),
                      'not_cosponsor_seated': sum(1 for d in districts if (d.get('member') or {}).get('ctma_hr3521') == 'none' and (d.get('member') or {}).get('name')),
                      'vacant': [d['id'] for d in districts if not (d.get('member') or {}).get('name')],
                      'cosponsoring': sum(1 for d in districts if (d.get('member') or {}).get('ctma_hr3521') not in (None, 'none')),
                      'tx34_bioguide': COSPONSORS['district_map'].get('4834'),
                      'ruiz': next(d['id'] for d in districts if (d.get('member') or {}).get('name') == 'Raul Ruiz'),
                      'ruiz_date': COSPONSORS['by_member']['R000599']['ctma_hr']['date'],
                      'tx34_deaths_vs_access': MORTALITY['summary']['districts']['4834'],
                      'tx34_county_names': [next(c['name'] for c in counties if c['id'] == f).rsplit(', ', 1)[0] for f in next(d for d in districts if d['id'] == 'TX-34')['counties']]}

    # --- Hidalgo County specifics ---
    hid = next(c for c in counties if c['id'] == '48215')
    types = BURDEN['meta']['types']
    lung_idx = [t[0] for t in T['types']].index('lung')
    tr = DATA['counties']['48215']['tr']
    nb60 = set()
    for sp in DATA['counties']['48215']['nb']:
        nb60.update(DATA['SP'][sp])
    E['hidalgo'] = {'districts': sorted(d['id'] for d in districts if '48215' in d['counties']),
                    'zt_lung': BURDEN['county']['48215']['zt'][types.index('lung')],
                    'per_100k': r1(hid['oncologists']['count'] / hid['pop55'] * 100000),
                    'menu': 'broad' if hid['trials_listed_here'] >= 100 else 'limited' if hid['trials_listed_here'] >= 20 else 'few' if hid['trials_listed_here'] >= 1 else 'none',
                    'trials': len(set(tr)), 'trials_lung': sum(1 for j in set(tr) if lung_idx in T['cats'][j]), 'trials_within_60': len(nb60), 't60_api': hid['trials_within_60rdmi_of_center'],
                    'trials_phase3': sum(1 for j in set(tr) if T['phases'][T['ph'][j]] == '3'),
                    'trials_industry': sum(1 for j in set(tr) if T['sponsors'][T['sp'][j]][0] == 'industry'),
                    'facilities': len(DATA['counties']['48215']['fac']), 'pop55': hid['pop55'],
                    'high_incidence_low_access': None if hid.get('incidence_above_county_median') is None else (hid['incidence_above_county_median'] and hid['pct_lt20_trials_within_60rdmi'] >= 50),
                    'nm_namesake_pop55': next(c['pop55'] for c in counties if c['id'] == '35023'),
                    'namesake_ratio_ge_20': hid['pop55'] >= 20 * next(c['pop55'] for c in counties if c['id'] == '35023')}
    # trials in Texas: union over counties; national: all
    tx_fips = next(s['fips'] for s in states if s['id'] == 'TX')
    tx_tr = set()
    for f, c in DATA['counties'].items():
        if f.startswith(tx_fips):
            tx_tr.update(c.get('tr', []))
    E['trials'] = {'tx_distinct': len(tx_tr), 'tx_state_data': DATA['state_data']['TX']['trials'], 'national': len(T['id']),
                   'national_phase3': sum(1 for j in range(len(T['id'])) if T['phases'][T['ph'][j]] == '3'),
                   'national_lung': sum(1 for j in range(len(T['id'])) if lung_idx in T['cats'][j]),
                   'tx_keyword_pembrolizumab': sum(1 for j in tx_tr if 'pembrolizumab' in (T['title'][j] + ' ' + T['iv'][j] + ' ' + T['kw'][j]).lower()),
                   'national_min_age_at_most_18': sum(1 for j in range(len(T['id'])) if T['amin'][j] is None or T['amin'][j] <= 18)}

    # --- states ---
    sc = next(s for s in states if s['id'] == 'SC')
    va = next(s for s in states if s['id'] == 'VA')
    txs = next(s for s in states if s['id'] == 'TX')
    E['states'] = {'sc_cosponsoring': sum(1 for x in sc['senators'] if x.get('s4440') not in (None, 'none')),
                   'va_cosponsoring': sum(1 for x in va['senators'] if x.get('s4440') not in (None, 'none')),
                   'sc_senator_names': [x['name'] for x in sc['senators']], 'sc_s4440': [x['s4440'] for x in sc['senators']],
                   'ca_nci': sum(1 for c in DATA['nci'] if c['st'] == 'CA'), 'sc_nci': sum(1 for c in DATA['nci'] if c['st'] == 'SC'),
                   'tx_trials_distinct': DATA['state_data']['TX']['trials'], 'tx_counties': DATA['state_data']['TX']['counties'],
                   'tx_counties_with_trials': DATA['state_data']['TX']['counties_with_trials'], 'tx_broad': DATA['state_data']['TX']['broad'], 'tx_limited': DATA['state_data']['TX']['limited'],
                   'tx_by_rucc_1_pct_lt20': RUCC['states']['TX']['codes']['1']['l20'], 'tx_by_rucc_1_pop55': RUCC['states']['TX']['codes']['1']['p'],
                   'dc_by_rucc_9_missing': '9' not in RUCC['states']['DC']['codes'],
                   'tx_need': BURDEN['summary']['states']['TX'], 'tx_deaths': MORTALITY['summary']['states']['TX'],
                   'tx_pct_lt20': txs['pct_lt20_trials_within_60rdmi'], 'tx_metro_pct_lt20': txs['metro']['pct_lt20_trials_within_60rdmi'],
                   'tx_metro_people_lt20': txs['metro']['people_lt20_trials_within_60rdmi'], 'tx_nonmetro_pct_lt100': txs['nonmetro']['pct_lt100_trials_within_60rdmi'],
                   'top3_pct_lt20': [s['id'] for s in order(states, lambda s: s.get('pct_lt20_trials_within_60rdmi'), desc=True)[:3]],
                   'states_with_2_cosponsoring': [s['id'] for s in states if sum(1 for x in (s.get('senators') or []) if x.get('s4440') not in (None, 'none')) == 2],
                   'n_with_1_cosponsoring': sum(1 for s in states if sum(1 for x in (s.get('senators') or []) if x.get('s4440') not in (None, 'none')) == 1),
                   'tx_sum_county_pop55': sum(c['pop55'] for c in tx)}

    # --- national ---
    E['national'] = {'pct_lt20': national['pct_lt20_trials_within_60rdmi'], 'pop55': national['pop55'], 'trials_listed_here': national['trials_listed_here'],
                     'mortality_lung': MORTALITY['meta']['us']['lung'], 'mortality_all': MORTALITY['meta']['us']['all'],
                     'need': BURDEN['summary']['nat'], 'deaths': MORTALITY['summary']['nat'], 'by_rucc_9_pct_lt20': RUCC['nat']['codes']['9']['l20'],
                     'states_no_broad': FINDINGS['states_no_broad'], 'states_no_broad_list': FINDINGS['states_no_broad_list'],
                     'history_first': CHANGES['history'][0], 'history_len': len(CHANGES['history']), 'metro_pct_lt20': national['metro']['pct_lt20_trials_within_60rdmi'],
                     'counties_by_class_2': national['oncologists']['counties_by_class']['2']}

    # --- places ---
    zip_to_county = {}
    for fips, zs in zips.items():
        for z in zs:
            zip_to_county.setdefault(str(z), fips)
    mcallen = [(st, f) for st, arr in places.items() for n, f, p in arr if n == 'McAllen']
    houston = sorted([(p, st, f) for st, arr in places.items() for n, f, p in arr if n == 'Houston'], reverse=True)
    E['places'] = {'zip_78501': zip_to_county.get('78501'), 'zip_77030': zip_to_county.get('77030'), 'mcallen': mcallen, 'houston_top': houston[0][2],
                   'houston_counties': sorted(c['id'] for c in counties if c['name'].startswith('Houston County')),
                   'washington_counties': sum(1 for c in counties if re.match(r'^Washington (County|Parish|Borough|Census Area|Municipality),', c['name'])),
                   'orange_counties': sorted(c['id'] for c in counties if c['name'].startswith('Orange County')),
                   'gonzalez_districts': sorted(d['id'] for d in districts if ((d.get('member') or {}).get('name') or '').split(' ')[-1].lower() == 'gonzalez'),
                   'tim_scott_state': next(s['id'] for s in states for x in (s.get('senators') or []) if x['name'] == 'Tim Scott'),
                   'cornyn_state': next(s['id'] for s in states for x in (s.get('senators') or []) if x['name'] == 'John Cornyn'),
                   'md_anderson': next(f'nci:{i}' for i, c in enumerate(DATA['nci']) if c['n'] == 'MD Anderson'),
                   'mayo_count': sum(1 for c in DATA['nci'] if c['n'].startswith('Mayo Clinic')),
                   'wy_at_large': next(d['id'] for d in districts if d['state'] == 'WY'), 'tx34_geoid': next(d['geoid'] for d in districts if d['id'] == 'TX-34')}

    # --- senators / cosponsors tables ---
    E['senators'] = {'sponsor_s4440': [x['bioguide'] for s in states for x in (s.get('senators') or []) if x.get('s4440') == 'sponsor'],
                     'n_not_none': sum(1 for s in states for x in (s.get('senators') or []) if x.get('s4440') not in (None, 'none')),
                     'tim_scott_date': COSPONSORS['by_member']['S001184']['ctma_s']['date']}
    E['cosponsors'] = {'n_house': sum(1 for bio, bills in COSPONSORS['by_member'].items() for b in bills if COSPONSORS['members'].get(bio, {}).get('chamber') != 'sen'),
                       'n_senate': sum(1 for bio, bills in COSPONSORS['by_member'].items() for b in bills if COSPONSORS['members'].get(bio, {}).get('chamber') == 'sen'),
                       'ruiz_row': 'R000599:ctma_hr', 'ruiz_district_id': 'CA-%02d' % COSPONSORS['members']['R000599']['district'],
                       'hr_n_cosponsors': COSPONSORS['bills']['ctma_hr']['n_cosponsors'], 's_introduced': COSPONSORS['bills']['ctma_s']['introduced'],
                       'roles': sorted({r['role'] for bills in COSPONSORS['by_member'].values() for r in bills.values()})}

    out = os.path.join(HERE, 'expected.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(E, fh, indent=1, sort_keys=True)
    print(f'wrote {out}: {sum(len(v) if isinstance(v, dict) else 1 for v in E.values())} expectations in {len(E)} groups')


if __name__ == '__main__':
    main()
