#!/usr/bin/env node
/* Offline tests for docs/ask/engine.js (ASK_CONTRACT.md §4, §5, §11).  node worker/tests/engine.test.js [--verbose]
   Every data-dependent expectation is read from worker/tests/expected.json, which python3 -I worker/tests/expected.py recomputes
   from the raw files without the engine. Exits 1 on any failure. Node 22, ESM, no dependencies. */
import { readFileSync, mkdtempSync, mkdirSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createEngine } from '../../docs/ask/engine.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const VERBOSE = process.argv.includes('--verbose');
const E = JSON.parse(readFileSync(path.join(HERE, 'expected.json'), 'utf8'));

let passed = 0, failed = 0;
const fails = [];
// one assertion: a condition with a name and a detail for the failure line
function check(name, cond, detail) {
  if (cond) { passed++; if (VERBOSE) console.log('  ok   ' + name); }
  else { failed++; fails.push(name + (detail !== undefined ? '  →  ' + JSON.stringify(detail) : '')); console.log('  FAIL ' + name + (detail !== undefined ? '  →  ' + JSON.stringify(detail).slice(0, 300) : '')); }
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const eq = (name, got, want) => check(name, same(got, want), { got, want });
const setEq = (name, got, want) => eq(name, [...got].slice().sort(), [...want].slice().sort());
const section = t => console.log('\n' + t);

// ---------------------------------------------------------------- load
section('load');
const engine = createEngine({ root: ROOT });
const t0 = Date.now();
await engine.load();
const loadMs = Date.now() - t0;
console.log(`  load(): ${loadMs} ms`);
check('loaded flags', engine.loaded && engine.loaded.counties && engine.loaded.districts && engine.loaded.states && engine.loaded.national, engine.loaded);
check('optional files loaded', Object.values(engine.loaded.optional).every(Boolean), engine.loaded.optional);
const before = await engine.run('query', { table: 'counties', limit: 1 });
await engine.load();   // idempotent
check('load() is idempotent', !before.error && same(await engine.run('query', { table: 'counties', limit: 1 }), before));
eq('table sizes', [engine.table('counties').length, engine.table('districts').length, engine.table('states').length, engine.table('national').length, engine.table('nci_centers').length, engine.table('facilities').length, engine.table('senators').length, engine.table('cosponsors').length],
  [E.counts.counties, E.counts.districts, E.counts.states, 1, E.counts.nci, E.counts.facilities, E.counts.senators, E.counts.cosponsor_rows]);

// ---------------------------------------------------------------- query
section('query');
const Q = (input, id) => engine.run('query', input, id);
const txOnc = await Q({ table: 'counties', where: [{ field: 'state', op: '=', value: 'TX' }, { field: 'oncologists.count', op: '>', value: 0 }, { field: 'trials_listed_here', op: '=', value: 0 }], order_by: [{ field: 'pop55', dir: 'desc' }] }, 'call-tx');
eq('TX oncologists-no-trials count', txOnc.count, E.tx_onc_no_trials.count);
eq('in_scope = TX counties', txOnc.in_scope, E.tx_onc_no_trials.in_scope);
eq('default limit 20', txOnc.returned, Math.min(20, E.tx_onc_no_trials.count));
eq('first three by pop55', txOnc.rows.slice(0, 3).map(r => r.id), E.tx_onc_no_trials.first3);
eq('sum_pop55_matching', txOnc.sum_pop55_matching, E.tx_onc_no_trials.sum_pop55);
check('ids_truncated when count > returned', txOnc.ids_truncated === (txOnc.count > txOnc.returned));
check('rows carry id/name/state/pop55 and dotted keys', txOnc.rows.every(r => 'id' in r && 'name' in r && 'state' in r && 'pop55' in r && 'oncologists.count' in r), txOnc.rows[0]);
check('default columns + filtered fields', ['pct_lt20_trials_within_60rdmi', 'trials_listed_here', 'oncologists.count'].every(c => txOnc.columns.includes(c)), txOnc.columns);
eq('nulls reported per filtered field', Object.keys(txOnc.nulls).sort(), ['oncologists.count', 'pop55', 'state', 'trials_listed_here']);
eq('source file', txOnc.source.file, 'api/all_counties.json');
const fullTx = engine.full('call-tx');
eq('full(callId).ids = all matching ids', fullTx.ids, E.tx_onc_no_trials.ids);
eq('full(callId).unit', fullTx.unit, 'county');
eq('full(callId).rows length = count', fullTx.rows.length, E.tx_onc_no_trials.count);
eq('class 2 equals the two-condition rule', (await Q({ table: 'counties', where: [{ field: 'state', op: '=', value: 'TX' }, { field: 'oncologists.class', op: '=', value: 2 }] })).count, E.tx_onc_no_trials.class2_count);
// state-name normalisation
for (const v of ['Texas', 'texas', 'Texans', 'tx']) eq(`state value "${v}" → TX`, (await Q({ table: 'counties', where: [{ field: 'state', op: '=', value: v }] })).count, E.tx_onc_no_trials.in_scope);
eq('states table: id in [Texas, Oklahoma]', (await Q({ table: 'states', where: [{ field: 'id', op: 'in', value: ['Texas', 'Oklahoma'] }] })).rows.map(r => r.id).sort(), E.ops.states_in_tx_ok);
// ordering
const mort = await Q({ table: 'counties', where: [{ field: 'state', op: '=', value: 'TX' }], order_by: [{ field: 'mortality.all', dir: 'desc' }], limit: 5 });
eq('top-5 TX by mortality.all', mort.rows.map(r => r.id), E.tx_top5_mortality.ids);
eq('their values', mort.rows.map(r => r['mortality.all']), E.tx_top5_mortality.values);
eq('nulls of mortality.all in scope', mort.nulls['mortality.all'], E.tx_top5_mortality.nulls);
const medn = await Q({ table: 'counties', order_by: [{ field: 'median_road_mi_nci', dir: 'desc' }], limit: 50 }, 'call-medn');
eq('nulls-last: top id', medn.rows[0].id, E.medn_nulls_last.top_id);
eq('nulls-last: top value', medn.rows[0].median_road_mi_nci, E.medn_nulls_last.top_value);
const medRows = engine.full('call-medn').rows;
check('nulls-last: the tail rows are the nulls', medRows.slice(-E.medn_nulls_last.nulls).every(r => r.median_road_mi_nci === null) && medRows[medRows.length - E.medn_nulls_last.nulls - 1].median_road_mi_nci !== null);
eq('nulls-last: tail ordered by pop55 desc, name', medRows.slice(-5).map(r => r.id), E.medn_nulls_last.tail5_ids);
const asc = await Q({ table: 'counties', where: [{ field: 'state', op: '=', value: 'MT' }], order_by: [{ field: 'median_road_mi_nci', dir: 'asc' }], limit: 1 });
eq('asc ordering gives the minimum', asc.rows[0].median_road_mi_nci, E.mt_medn.min);
const tie = await Q({ table: 'counties', where: [{ field: 'pct_lt20_trials_within_60rdmi', op: '=', value: 100 }], order_by: [{ field: 'pct_lt20_trials_within_60rdmi', dir: 'desc' }], limit: 3 });
eq('tie-break by pop55 desc then name', tie.rows.map(r => r.id), E.tie_break.first3);
eq('tie count', tie.count, E.tie_break.n);
// ops
const TX = { field: 'state', op: '=', value: 'TX' };
const cnt = async (where, table = 'counties') => (await Q({ table, where })).count;
eq('is_null', await cnt([{ field: 'no_road_route_reason', op: 'is_null' }]), E.ops.no_route_null);
eq('not_null', await cnt([{ field: 'no_road_route_reason', op: 'not_null' }]), E.ops.no_route_not_null);
eq('= string', await cnt([{ field: 'no_road_route_reason', op: '=', value: 'island' }]), E.ops.no_route_island);
eq('!= string skips nulls', await cnt([TX, { field: 'incidence.status', op: '!=', value: 'ok' }]), E.ops.tx_incidence_ne_ok);
eq('>=', await cnt([TX, { field: 'pct_lt20_trials_within_60rdmi', op: '>=', value: 50 }]), E.ops.tx_pct_ge_50);
eq('<', await cnt([TX, { field: 'pct_lt20_trials_within_60rdmi', op: '<', value: 1 }]), E.ops.tx_pct_lt_1);
eq('<=', await cnt([TX, { field: 'pct_lt20_trials_within_60rdmi', op: '<=', value: 0 }]), E.ops.tx_pct_le_0);
eq('>', await cnt([TX, { field: 'trials_listed_here', op: '>', value: 100 }]), E.ops.tx_trials_gt_100);
eq('between', await cnt([TX, { field: 'pct_lt20_trials_within_60rdmi', op: 'between', value: [40, 60] }]), E.ops.tx_pct_between_40_60);
eq('contains (case-insensitive)', await cnt([{ field: 'name', op: 'contains', value: 'HIDALGO' }]), E.ops.name_contains_hidalgo);
eq('includes on an array field', (await Q({ table: 'counties', where: [{ field: 'districts', op: 'includes', value: 'TX-34' }] })).rows.map(r => r.id).sort(), E.ops.tx34_counties);
eq('intersects', (await Q({ table: 'districts', where: [{ field: 'counties', op: 'intersects', value: ['48215'] }] })).rows.map(r => r.id).sort(), E.ops.districts_intersect_48215);
eq('any_of', await cnt([TX, { any_of: [{ field: 'oncologists.class', op: '=', value: 2 }, { field: 'trials_listed_here', op: '>=', value: 100 }] }]), E.ops.tx_any_of_class2_or_broad);
eq('{field} value compares two fields', await cnt([{ field: 'trials_within_60rdmi_of_center', op: '>', value: { field: 'wmean_trials_within_60rdmi' } }]), E.ops.center_gt_wmean);
eq('boolean = false', await cnt([TX, { field: 'metro', op: '=', value: false }]), E.ops.tx_metro_false);
eq('boolean given as "false"', await cnt([TX, { field: 'metro', op: '=', value: 'false' }]), E.ops.tx_metro_false);
eq('in (numbers)', await cnt([TX, { field: 'rucc', op: 'in', value: [8, 9] }]), E.ops.tx_rucc_in_8_9);
eq('not_in skips nulls', await cnt([TX, { field: 'rucc', op: 'not_in', value: [1, 2, 3] }]), E.ops.tx_rucc_not_in_1_2_3);
eq('number given as a string', await cnt([TX, { field: 'trials_listed_here', op: '>', value: '100' }]), E.ops.tx_trials_gt_100);
eq('national table has one row', (await Q({ table: 'national' })).count, 1);
eq('national pct_lt20', (await Q({ table: 'national' })).rows[0].pct_lt20_trials_within_60rdmi, E.national.pct_lt20);
// limits, columns, errors
eq('limit clamps to 50', (await Q({ table: 'counties', limit: 500 })).returned, 50);
eq('limit 0 → default 20', (await Q({ table: 'counties', limit: 0 })).returned, 20);
const cols = await Q({ table: 'counties', where: [TX], columns: ['incidence.by_site.lung', 'zero_trial_share_by_type.lung'], limit: 1 });
check('requested columns returned', 'incidence.by_site.lung' in cols.rows[0] && 'zero_trial_share_by_type.lung' in cols.rows[0], cols.rows[0]);
check('zero_trial_share_by_type.lung present (§4)', typeof cols.rows[0]['zero_trial_share_by_type.lung'] === 'number', cols.rows[0]);
const bad = await Q({ table: 'counties', where: [{ field: 'oncologist_count', op: '>', value: 0 }] });
check('unknown field → error with hint', bad.error && /unknown field 'oncologist_count'/.test(bad.error) && /oncologists\.count/.test(bad.hint), bad);
check('unknown table → error', (await Q({ table: 'cities' })).error, await Q({ table: 'cities' }));
check('unknown op → error', /unknown op/.test((await Q({ table: 'counties', where: [{ field: 'pop55', op: '~', value: 1 }] })).error || ''));
check('unknown column → error', /unknown field/.test((await Q({ table: 'counties', columns: ['bogus'] })).error || ''));
check('unknown order field → error', /unknown field/.test((await Q({ table: 'counties', order_by: [{ field: 'bogus' }] })).error || ''));
check('missing value → error', /needs a value/.test((await Q({ table: 'counties', where: [{ field: 'pop55', op: '>' }] })).error || ''));
check('enum warning for a wrong value', (await Q({ table: 'districts', where: [{ field: 'member.party', op: '=', value: 'Democrat' }] })).warnings, 'no warning');
check('where not an array → error', (await Q({ table: 'counties', where: 'bad' })).error);
eq('"= null" reads as is_null, "!= null" as not_null', [(await Q({ table: 'counties', where: [{ field: 'mortality.all', op: '=', value: null }] })).count, (await Q({ table: 'counties', where: [{ field: 'mortality.all', op: '!=', value: null }] })).count], [(await Q({ table: 'counties', where: [{ field: 'mortality.all', op: 'is_null' }] })).count, (await Q({ table: 'counties', where: [{ field: 'mortality.all', op: 'not_null' }] })).count]);
check('run never throws on null input', !!(await engine.run('query', null)).error);
check('unknown tool → error', /unknown tool/.test((await engine.run('nope', {})).error));
eq('final_answer is a no-op', await engine.run('final_answer', { answer: 'x' }), { ok: true });

// ---------------------------------------------------------------- aggregate
section('aggregate');
const A = (input, id) => engine.run('aggregate', input, id);
const oh = await A({ table: 'counties', where: [{ field: 'state', op: '=', value: 'Ohio' }], group_by: 'metro', measures: [{ field: 'pct_lt20_trials_within_60rdmi', stat: 'weighted_mean' }, { field: 'pct_lt20_trials_within_60rdmi', stat: 'mean' }, { stat: 'count' }] });
const g = v => oh.groups.find(x => x.group === v);
eq('OH nonmetro weighted mean pct_lt20', g(false).measures['pct_lt20_trials_within_60rdmi:weighted_mean'], E.oh_by_metro.nonmetro.wmean_pct_lt20);
eq('OH nonmetro plain mean', g(false).measures['pct_lt20_trials_within_60rdmi:mean'], E.oh_by_metro.nonmetro.mean_pct_lt20);
eq('OH metro weighted mean', g(true).measures['pct_lt20_trials_within_60rdmi:weighted_mean'], E.oh_by_metro.metro.wmean_pct_lt20);
eq('group n and sum_pop55', [g(false).n, g(false).sum_pop55, g(true).n, g(true).sum_pop55], [E.oh_by_metro.nonmetro.n, E.oh_by_metro.nonmetro.sum_pop55, E.oh_by_metro.metro.n, E.oh_by_metro.metro.sum_pop55]);
eq('count measure', g(false).measures['*:count'], E.oh_by_metro.nonmetro.n);
check('the fixed note', /Computed by the engine across the matching rows; a mean of county rates is not the published state rate/.test(oh.note));
const mt = await A({ table: 'counties', where: [{ field: 'state', op: '=', value: 'MT' }], measures: [{ field: 'median_road_mi_nci', stat: 'median' }, { field: 'median_road_mi_nci', stat: 'count_not_null' }, { field: 'median_road_mi_nci', stat: 'min' }, { field: 'median_road_mi_nci', stat: 'max' }, { field: 'median_road_mi_nci', stat: 'sum' }] });
const m = mt.groups[0].measures;
eq('median (exact) across MT counties', m['median_road_mi_nci:median'], E.mt_medn.median);
eq('count_not_null / min / max / sum', [m['median_road_mi_nci:count_not_null'], m['median_road_mi_nci:min'], m['median_road_mi_nci:max'], m['median_road_mi_nci:sum']], [E.mt_medn.count_not_null, E.mt_medn.min, E.mt_medn.max, E.mt_medn.sum]);
eq('ungrouped → one group with group null', [mt.groups.length, mt.groups[0].group, mt.groups[0].n], [1, null, E.mt_medn.n]);
const txa = await A({ table: 'counties', where: [TX], measures: [{ field: 'metro', stat: 'share_true' }, { field: 'oncologists.class', stat: 'share_eq', value: 2 }, { field: 'incidence.all', stat: 'mean' }, { field: 'incidence.all', stat: 'count_not_null' }, { field: 'pop55', stat: 'sum' }, { field: 'pop55', stat: 'max' }] });
const tm = txa.groups[0].measures;
eq('share_true', tm['metro:share_true'], E.tx_agg.share_metro_true);
eq('share_eq', tm['oncologists.class:share_eq'], E.tx_agg.share_class_eq_2);
eq('mean skips nulls', tm['incidence.all:mean'], E.tx_agg.mean_incidence);
eq('sum of pop55 (= state pop55)', tm['pop55:sum'], E.tx_agg.sum_pop55);
eq('max', tm['pop55:max'], E.tx_agg.max_pop55);
const byR = await A({ table: 'counties', group_by: 'rucc', measures: [{ stat: 'count' }] });
eq('group by rucc: counts per code', Object.fromEntries(byR.groups.map(x => [x.group === null ? 'null' : String(x.group), x.n])), E.counties_by_rucc);
check('groups sorted with null last', byR.groups.map(x => x.group).slice(0, -1).every((v, i, a) => i === 0 || a[i - 1] < v) && (byR.groups[byR.groups.length - 1].group === null || byR.groups.every(x => x.group !== null)));
const byP = await A({ table: 'districts', group_by: 'member.party', measures: [{ stat: 'count' }] });
eq('districts by party', Object.fromEntries(byP.groups.map(x => [x.group === null ? 'null' : x.group, x.n])), E.districts_by_party);
const notG = await A({ table: 'counties', group_by: 'name', measures: [{ stat: 'count' }] });
check('groupable enforcement', /not a groupable field/.test(notG.error || '') && /metro/.test(notG.hint || ''), notG);
check('unknown stat → error', /unknown stat/.test((await A({ table: 'counties', measures: [{ field: 'pop55', stat: 'avg' }] })).error || ''));
check('missing measures → error', (await A({ table: 'counties' })).error);
check('unknown measure field → error', /unknown field/.test((await A({ table: 'counties', measures: [{ field: 'nope', stat: 'mean' }] })).error || ''));
eq('aggregate count equals query count', (await A({ table: 'districts', where: [{ field: 'member.ctma_hr3521', op: '=', value: 'none' }], measures: [{ stat: 'count' }] })).count, E.districts.not_cosponsor);
eq('districts not cosponsoring (seated)', await cnt([{ field: 'member.ctma_hr3521', op: '=', value: 'none' }, { field: 'member.vacant', op: '=', value: false }], 'districts'), E.districts.not_cosponsor_seated);
eq('vacant seats', (await Q({ table: 'districts', where: [{ field: 'member.vacant', op: '=', value: true }] })).rows.map(r => r.id).sort(), E.districts.vacant);

// ---------------------------------------------------------------- profile
section('profile');
const P = (table, id, cid) => engine.run('profile', { table, id }, cid);
const hid = await P('counties', '48215', 'call-prof');
eq('Hidalgo districts (§4)', hid.row.districts, E.hidalgo.districts);
eq('zero_trial_share_by_type.lung', hid.row.zero_trial_share_by_type.lung, E.hidalgo.zt_lung);
eq('oncologists.per_100k_pop55 (1 decimal)', hid.row.oncologists.per_100k_pop55, E.hidalgo.per_100k);
eq('menu', hid.row.menu, E.hidalgo.menu);
eq('high_incidence_low_access', hid.row.high_incidence_low_access, E.hidalgo.high_incidence_low_access);
check('boilerplate stripped', !('links' in hid.row) && !('license' in hid.row) && !('cite' in hid.row) && !('source' in hid.row), Object.keys(hid.row));
eq('related.districts', hid.related.districts.map(d => d.id), E.hidalgo.districts);
check('related.districts carry member/party/ctma', hid.related.districts.every(d => 'member' in d && 'party' in d && 'ctma_hr3521' in d));
eq('related.senators', hid.related.senators.length, 2);
eq('related.state_row_headline', [hid.related.state_row_headline.id, hid.related.state_row_headline.pct_lt20_trials_within_60rdmi], ['TX', E.states.tx_pct_lt20]);
eq('related.national_headline', hid.related.national_headline.pct_lt20_trials_within_60rdmi, E.national.pct_lt20);
eq('full(profile call)', engine.full('call-prof').ids, ['48215']);
eq('profile accepts a FIPS without the leading zero', (await P('counties', 1001)).id, '01001');
const d34 = await P('districts', '4834');
eq('district by geoid', d34.id, 'TX-34');
eq('member.bioguide', d34.row.member.bioguide, E.districts.tx34_bioguide);
eq('member.cosponsor_date null for a non-cosponsor', d34.row.member.cosponsor_date, null);
eq('member.vacant false', d34.row.member.vacant, false);
eq('county_names', d34.row.county_names, E.districts.tx34_county_names);
eq('deaths_vs_access (district)', d34.row.deaths_vs_access, { counties_classified: E.districts.tx34_deaths_vs_access.classified, high_death_low_access_counties: E.districts.tx34_deaths_vs_access.hh.length, ids: E.districts.tx34_deaths_vs_access.hh });
eq('related.counties', d34.related.counties.length, 5);
check('related.member has cosponsor_date', 'cosponsor_date' in d34.related.member);
eq('vacant seat flagged', (await P('districts', E.districts.vacant[0])).row.member.vacant, true);
const ruiz = await P('districts', E.districts.ruiz);
eq('sponsor cosponsor_date', ruiz.row.member.cosponsor_date, E.districts.ruiz_date);
const sc = await P('states', 'SC');
eq('SC senators_cosponsoring_s4440 = 1 (§4)', sc.row.senators_cosponsoring_s4440, E.states.sc_cosponsoring);
eq('VA senators_cosponsoring_s4440 = 1 (§4)', (await P('states', 'Virginia')).row.senators_cosponsoring_s4440, E.states.va_cosponsoring);
eq('senator_names', sc.row.senator_names, E.states.sc_senator_names);
check('senators_s4440 text', sc.row.senators_s4440.includes(`${E.states.sc_senator_names[0]} (`) && sc.row.senators_s4440.includes(E.states.sc_s4440[0]), sc.row.senators_s4440);
eq('nci_centers_count SC', sc.row.nci_centers_count, E.states.sc_nci);
eq('nci_centers_count CA', (await P('states', 'CA')).row.nci_centers_count, E.states.ca_nci);
const txs = await P('states', 'TX');
eq('trials_distinct / counties / counties_with_trials / broad / limited', [txs.row.trials_distinct, txs.row.counties, txs.row.counties_with_trials, txs.row.broad_menu_counties, txs.row.limited_menu_counties], [E.states.tx_trials_distinct, E.states.tx_counties, E.states.tx_counties_with_trials, E.states.tx_broad, E.states.tx_limited]);
eq('by_rucc.1 mapped keys', [txs.row.by_rucc['1'].pct_lt20, txs.row.by_rucc['1'].pop55], [E.states.tx_by_rucc_1_pct_lt20, E.states.tx_by_rucc_1_pop55]);
eq('by_rucc code absent → null', (await P('states', 'DC')).row.by_rucc['9'], E.states.dc_by_rucc_9_missing ? null : 'present');
eq('need_vs_access (state)', txs.row.need_vs_access, { counties_classified: E.states.tx_need.counties_classified, high_incidence_low_access_counties: E.states.tx_need.hb_la_counties, pop55: E.states.tx_need.hb_la_pop55, cases_per_year: E.states.tx_need.hb_la_cases });
eq('deaths_vs_access (state)', txs.row.deaths_vs_access, { counties_classified: E.states.tx_deaths.counties_classified, high_death_low_access_counties: E.states.tx_deaths.hh_counties, pop55: E.states.tx_deaths.hh_pop55, deaths_per_year: E.states.tx_deaths.hh_deaths });
eq('metro short aliases', [txs.row.metro.pct_lt20, txs.row.metro.people_lt20, txs.row.nonmetro.pct_lt100], [E.states.tx_metro_pct_lt20, E.states.tx_metro_people_lt20, E.states.tx_nonmetro_pct_lt100]);
check('state related', txs.related.senators.length === 2 && Array.isArray(txs.related.nci_centers) && txs.related.metro_nonmetro.metro.pct_lt20 === E.states.tx_metro_pct_lt20, txs.related);
const us = await P('national', 'US');
check('national history length ≥ 5 (§4)', Array.isArray(us.row.history) && us.row.history.length >= 5 && us.row.history.length === E.national.history_len, us.row.history && us.row.history.length);
eq('history keys mapped', us.row.history[0], { pull: E.national.history_first.pull, trials: E.national.history_first.trials, pct_lt20: E.national.history_first.l20, pct_zero: E.national.history_first.z60, pct_gt60_broad: E.national.history_first.g60b, pct_gt60_nci: E.national.history_first.g60n, median_road_mi_nci: E.national.history_first.medn });
eq('mortality.by_site.lung', [us.row.mortality.by_site.lung.rate, us.row.mortality.by_site.lung.deaths], [E.national.mortality_lung.rate, E.national.mortality_lung.deaths]);
eq('states_with_no_broad_menu_county as USPS', us.row.states_with_no_broad_menu_county.length, E.national.states_no_broad);
check('…codes not names', us.row.states_with_no_broad_menu_county.every(s => /^[A-Z]{2}$/.test(s)), us.row.states_with_no_broad_menu_county);
eq('national need_vs_access', us.row.need_vs_access.high_incidence_low_access_counties, E.national.need.hb_la_counties);
eq('national deaths_vs_access', us.row.deaths_vs_access.deaths_per_year, E.national.deaths.hh_deaths);
eq('national by_rucc.9.pct_lt20', us.row.by_rucc['9'].pct_lt20, E.national.by_rucc_9_pct_lt20);
eq('national counties_by_class.2', us.row.oncologists.counties_by_class['2'], E.national.counties_by_class_2);
check('profile unknown id → error', /no row/.test((await P('counties', '99999')).error || ''));
eq('profile facility', (await P('facilities', engine.table('facilities')[0].id)).row.id, engine.table('facilities')[0].id);
eq('profile senator by bioguide', (await P('senators', E.senators.sponsor_s4440[0])).row.s4440, 'sponsor');

// ---------------------------------------------------------------- compare
section('compare');
const cmp = await engine.run('compare', { table: 'counties', ids: ['48215', '48061'] }, 'call-cmp');
eq('compare rows', cmp.rows.map(r => r.id), ['48215', '48061']);
eq('reference: the state and the nation', cmp.reference.map(r => r.id), ['TX', 'US']);
eq('reference state value', cmp.reference[0].pct_lt20_trials_within_60rdmi, E.states.tx_pct_lt20);
eq('reference national value', cmp.reference[1].pct_lt20_trials_within_60rdmi, E.national.pct_lt20);
check('reference rows carry the same columns (where they exist)', cmp.columns.filter(c => c !== 'metro' && c !== 'state').every(c => c in cmp.reference[1]), cmp.reference[1]);
eq('full(compare)', engine.full('call-cmp').ids, ['48215', '48061']);
const cmpS = await engine.run('compare', { table: 'states', ids: ['TX', 'Oklahoma', 'NM'], columns: ['nonmetro.pct_lt20'] });
eq('compare states → national reference only', cmpS.reference.map(r => r.id), ['US']);
check('compare extra column', cmpS.rows.every(r => 'nonmetro.pct_lt20' in r), cmpS.rows[0]);
check('compare needs 2–6 ids', /2 to 6/.test((await engine.run('compare', { table: 'counties', ids: ['48215'] })).error || ''));
check('compare unknown id → error', /unknown id/.test((await engine.run('compare', { table: 'counties', ids: ['48215', '00000'] })).error || ''));
const cmpD = await engine.run('compare', { table: 'districts', ids: ['TX-34', '4815'] });
eq('compare districts by id and geoid', cmpD.rows.map(r => r.id), ['TX-34', 'TX-15']);

// ---------------------------------------------------------------- trials
section('trials');
const TR = input => engine.run('trials', input);
const th = await TR({ scope: { county_id: '48215' } });
eq('trials in Hidalgo County', th.count, E.hidalgo.trials);
eq('…lung', (await TR({ scope: { county_id: '48215' }, cancer_type: 'lung' })).count, E.hidalgo.trials_lung);
eq('…phase 3', (await TR({ scope: { county_id: '48215' }, phase: '3' })).count, E.hidalgo.trials_phase3);
eq('…industry', (await TR({ scope: { county_id: '48215' }, sponsor_type: 'industry' })).count, E.hidalgo.trials_industry);
eq('within 60 road-miles of the center', (await TR({ scope: { within_60_of_county_id: '48215' } })).count, E.hidalgo.trials_within_60);
eq('…equals the API t60', E.hidalgo.trials_within_60, E.hidalgo.t60_api);
eq('state scope (name)', (await TR({ scope: { state: 'Texas' } })).count, E.trials.tx_distinct);
eq('state scope = DATA.state_data trials', E.trials.tx_distinct, E.trials.tx_state_data);
eq('national scope', (await TR({ scope: { national: true } })).count, E.trials.national);
eq('national phase 3', (await TR({ scope: { national: true }, phase: '3' })).count, E.trials.national_phase3);
eq('national lung', (await TR({ scope: { national: true }, cancer_type: 'lung' })).count, E.trials.national_lung);
eq('keyword', (await TR({ scope: { state: 'TX' }, keyword: 'Pembrolizumab' })).count, E.trials.tx_keyword_pembrolizumab);
eq('min_age_at_most', (await TR({ scope: { national: true }, min_age_at_most: 18 })).count, E.trials.national_min_age_at_most_18);
check('by_phase sums to count', Object.values(th.by_phase).reduce((a, b) => a + b, 0) === th.count);
check('by_sponsor_type sums to count', Object.values(th.by_sponsor_type).reduce((a, b) => a + b, 0) === th.count);
check('by_cancer_type ≤ 10, labelled', th.by_cancer_type.length <= 10 && th.by_cancer_type.every(x => x.label && x.count > 0));
eq('by_cancer_type top for a lung filter is lung', (await TR({ scope: { county_id: '48215' }, cancer_type: 'lung' })).by_cancer_type[0].type, 'lung');
const samp = await TR({ scope: { state: 'TX' }, limit: 5 });
check('sample limited and most recently updated first', samp.sample.length === 5 && samp.sample.every((s, i, a) => i === 0 || a[i - 1].last_update >= s.last_update), samp.sample.map(s => s.last_update));
check('sample rows have the documented keys', ['nct', 'title', 'phase', 'sponsor', 'sponsor_type', 'cancer_types', 'start', 'last_update'].every(k => k in samp.sample[0]));
check('sample limit clamps to 25', (await TR({ scope: { national: true }, limit: 100 })).sample.length === 25);
check('county link', th.link.endsWith('trials.html?county=48215'), th.link);
check('state link with type', (await TR({ scope: { state: 'TX' }, cancer_type: 'lung' })).link.endsWith('find.html?type=lung'));
check('the note says listed, not available', /not matched|available to a particular person/.test(th.note));
check('unknown cancer_type → error', /unknown cancer_type/.test((await TR({ scope: { national: true }, cancer_type: 'toe' })).error || ''));
check('unknown phase → error', /unknown phase/.test((await TR({ scope: { national: true }, phase: '7' })).error || ''));
eq('type, phase and sponsor keys are case-insensitive ("Lung", "Phase 3", "Industry", "na")', (r => [r.filters, r.count === (0 + r.count)])(await TR({ scope: { county_id: '48201' }, cancer_type: 'Lung', phase: 'Phase 3', sponsor_type: 'Industry' })), [{ cancer_type: 'lung', phase: '3', sponsor_type: 'industry' }, true]);
eq('phase "na" → NA', (await TR({ scope: { national: true }, phase: 'na' })).filters.phase, 'NA');
check('bad scope → error', (await TR({ scope: { planet: 'mars' } })).error);
check('unknown county in scope → error', /unknown county/.test((await TR({ scope: { county_id: '00000' } })).error || ''));

// ---------------------------------------------------------------- site_info
section('site_info');
const SI = topic => engine.run('site_info', { topic });
const bills = await SI('bills');
check('bills text + url', bills.text.length > 100 && /act\.html/.test(bills.url));
eq('bills numbers: H.R. 3521 cosponsors', bills.numbers.bills.ctma_hr.n_cosponsors, E.cosponsors.hr_n_cosponsors);
eq('bills numbers: S. 4440 introduced', bills.numbers.bills.ctma_s.introduced, E.cosponsors.s_introduced);
check('bills numbers: latest_action + url', bills.numbers.bills.ctma_hr.latest_action.text && bills.numbers.bills.ctma_hr.url);
eq('findings numbers', (await SI('findings')).numbers.states_no_broad, E.national.states_no_broad);
check('findings districts numbers', (await SI('findings')).numbers.districts.all_beyond_60_broad > 0);
eq('history numbers', (await SI('history')).numbers.history.length, E.national.history_len);
check('changes numbers', typeof (await SI('changes')).numbers.summary.trials_current === 'number');
eq('rural numbers', (await SI('rural')).numbers.metro.pct_lt20, E.national.metro_pct_lt20);
eq('need_vs_access numbers', (await SI('need_vs_access')).numbers.nat.hb_la_counties, E.national.need.hb_la_counties);
eq('deaths_vs_access numbers', (await SI('deaths_vs_access')).numbers.nat.hh_counties, E.national.deaths.hh_counties);
check('oncologists numbers', (await SI('oncologists')).numbers.nat.onc > 0);
eq('sources numbers carry vintages', (await SI('sources')).numbers.vintages.data_as_of, engine.vintages().data_as_of);
for (const t of ['methods', 'definitions', 'limits', 'how_to_act', 'about', 'finder']) check(`site_info ${t} has text`, (await SI(t)).text.length > 50);
check('unknown topic → error', /unknown topic/.test((await SI('weather')).error || ''));

// ---------------------------------------------------------------- find_places
section('find_places');
const FP = input => engine.run('find_places', typeof input === 'string' ? { query: input } : input);
const one = async (q, id, how) => { const r = await FP(q); const m = r.matches && r.matches[0]; eq(`"${typeof q === 'string' ? q : q.query}" → ${id}`, m && m.id, id); if (how) eq(`  …how ${how}`, m && m.how, how); check('  …not ambiguous', r.ambiguous === false && r.matches.length === 1, r); return r; };
await one('Hidalgo County, Texas', '48215', 'exact');
await one('Hidalgo, TX', '48215', 'exact');
await one('hidalgo county texas', '48215', 'exact');
await one('Hidalgo County, New Mexico', '35023', 'exact');
await one('Hidago County', '48215', 'fuzzy');
await one('Hudspth County', '48229', 'fuzzy');
const nmsk = await FP('Hidalgo County');
check('dominant namesake flagged', E.hidalgo.namesake_ratio_ge_20 ? (nmsk.matches.length === 1 && nmsk.matches[0].id === '48215' && nmsk.matches[0].how === 'namesake' && /New Mexico/.test(nmsk.matches[0].note) && nmsk.ambiguous === false) : nmsk.ambiguous === true, nmsk);
const orange = await FP({ query: 'Orange County', limit: 10 });
check('namesakes without a dominant one → ambiguous', orange.ambiguous === true && orange.hint, orange);
setEq('…all candidates listed', orange.matches.map(m => m.id), E.places.orange_counties);
check('…sorted by pop55 desc', orange.matches.every((m, i, a) => i === 0 || a[i - 1].pop55 >= m.pop55));
const wash = await FP({ query: 'Washington', kind: 'county', limit: 3 });
check('limit respected and hint counts all', wash.matches.length === 3 && wash.ambiguous && new RegExp(`${E.places.washington_counties} places`).test(wash.hint), wash.hint);
await one('Washington', 'WA', 'exact');
const z = await one('78501', E.places.zip_78501, 'zip');
check('ZIP via text', /ZIP 78501 is in Hidalgo County, Texas/.test(z.matches[0].via), z.matches[0]);
await one('77030', E.places.zip_77030, 'zip');
const fipsAsZip = await FP('48215');
check('a 5-digit string is a ZIP first, with the FIPS noted', fipsAsZip.matches[0].how === 'zip' && /FIPS code of Hidalgo County/.test(fipsAsZip.hint), fipsAsZip);
eq('…kind:"county" reads it as FIPS', (await FP({ query: '48215', kind: 'county' })).matches[0].id, '48215');
const town = await one('McAllen', E.places.mcallen[0][1], 'town');
check('town via text', /McAllen, TX is in Hidalgo County, Texas/.test(town.matches[0].via));
const houston = await FP('Houston');
check('Houston: the city wins (5x the residents 55+ of every namesake county) and the counties are listed as others', !houston.ambiguous && houston.matches.length === 1 && houston.matches[0].id === E.places.houston_top && houston.matches[0].how === 'town' && E.places.houston_counties.every(id => (houston.others || []).some(m => m.id === id)), houston.matches.map(m => m.id));
const gz = await FP('Gonzalez');
eq('member surname → district', gz.matches[0].id, E.places.gonzalez_districts[0]);
eq('…how member', gz.matches[0].how, 'member');
check('…via names the member', /Rep\. Vicente Gonzalez/.test(gz.matches[0].via));
await one('Rep. Vicente Gonzalez', 'TX-34', 'member');
await one("Gonzalez's district", 'TX-34', 'member');
await one('Vicente Gonzales', 'TX-34', 'fuzzy');
await one('Raul Ruiz', E.districts.ruiz, 'member');
const ts = await one('Tim Scott', E.places.tim_scott_state, 'senator');
check('senator via text', /Senator Tim Scott/.test(ts.matches[0].via) && /sponsor/.test(ts.matches[0].via), ts.matches[0]);
await one('Senator Cornyn', E.places.cornyn_state, 'senator');
const scott = await FP('Scott');
check('shared surname → ambiguous', scott.ambiguous && scott.matches.length >= 3, scott.matches.length);
for (const q of ['TX-34', 'tx-34', 'TX 34', 'TX34', 'Texas 34th', 'Texas 34', "Texas's 34th district", 'Texas 34th congressional district', '34th district of Texas', 'district 34 of Texas', 'Texas district 34', E.places.tx34_geoid]) await one(q, 'TX-34', 'exact');
eq('district with the state param', (await FP({ query: 'district 34', state: 'TX' })).matches[0].id, 'TX-34');
for (const q of ['Wyoming at-large', 'WY-AL', 'WY-00', 'at-large district of Wyoming', 'Wyoming 1st']) await one(q, E.places.wy_at_large, 'exact');
await one('Delaware at large', 'DE-00', 'exact');
await one('Texans', 'TX', 'exact');
await one('texan', 'TX', 'exact');
await one('Hoosiers', 'IN', 'exact');
await one('texas', 'TX', 'exact');
await one('TX', 'TX', 'exact');
await one('New York', 'NY', 'exact');
await one('MD Anderson', E.places.md_anderson, 'exact');
await one('Moffitt', 'nci:16', 'exact');
const mayo = await FP('Mayo Clinic');
check('NCI centres with one name → ambiguous list', mayo.ambiguous && mayo.matches.length === E.places.mayo_count && mayo.matches.every(m => m.kind === 'nci_center'), mayo);
eq('…narrowed by state', (await FP({ query: 'Mayo Clinic', state: 'MN' })).matches.length, 1);
eq('kind + state narrow', (await FP({ query: 'Hidalgo', kind: 'county', state: 'NM' })).matches[0].id, '35023');
eq('state as a name', (await FP({ query: 'Springfield', state: 'Illinois' })).matches[0].id, '17167');
check('Springfield alone is ambiguous', (await FP('Springfield')).ambiguous);
await one('Carson City', '32510', 'exact');
await one('Richmond city', '51760', 'exact');
await one('Kansas City, MO', '29095', 'town');
await one('District of Columbia', 'DC', 'exact');
await one('United States', 'US', 'exact');
check('no match → empty with hint', (r => r.matches.length === 0 && r.ambiguous === false && /No county/.test(r.hint))(await FP('Nowheresville Qzx')));
check('empty query → error', (await FP('')).error);
check('unknown kind → error', /unknown kind/.test((await FP({ query: 'x', kind: 'planet' })).error || ''));
eq('kind narrows: Hidalgo as town', (await FP({ query: 'Hidalgo', kind: 'town', state: 'TX' })).matches[0].how, 'town');
eq('a state hint beats a state\'s own name: Washington in OR is the county', (await FP({ query: 'Washington', state: 'OR' })).matches.map(m => m.id), ['41067']);
eq('a state hint that matches keeps the state', (await FP({ query: 'Washington', state: 'WA' })).matches.map(m => m.id), ['WA']);
eq('Texas with state OK is Texas County, Oklahoma', (await FP({ query: 'Texas', state: 'OK' })).matches.map(m => m.id), ['40139']);
eq('"Sainte" folds like "Saint"', (await FP('Sainte Genevieve County')).matches.map(m => m.id), ['29186']);
const fpFull = await engine.run('find_places', { query: 'Orange County' }, 'call-fp');
eq('full(find_places)', engine.full('call-fp').ids.length, Math.min(10, E.places.orange_counties.length));

// ---------------------------------------------------------------- descriptions, names, sources, vintages
section('describe / names / sources');
const dq = engine.describeCall('query', { table: 'counties', where: [{ field: 'state', op: '=', value: 'TX' }, { field: 'oncologists.count', op: '>', value: 0 }, { field: 'trials_listed_here', op: '=', value: 0 }], order_by: [{ field: 'pop55', dir: 'desc' }] });
eq('describeCall(query)', dq, 'Counties in TX where oncologists.count > 0 and trials_listed_here = 0, ordered by pop55 desc (first 20)');
eq('describeCall(aggregate)', engine.describeCall('aggregate', { table: 'counties', where: [{ field: 'state', op: '=', value: 'Texas' }], group_by: 'metro', measures: [{ stat: 'count' }, { field: 'pct_lt20_trials_within_60rdmi', stat: 'mean' }] }), 'Count and mean of pct_lt20_trials_within_60rdmi across counties in TX grouped by metro');
eq('describeCall(find_places)', engine.describeCall('find_places', { query: 'Hidalgo county' }), 'Looking up "Hidalgo county"');
check('describeCall(trials)', /^Trials with a site in Hidalgo County, Texas \(lung/.test(engine.describeCall('trials', { scope: { county_id: '48215' }, cancer_type: 'lung' })), engine.describeCall('trials', { scope: { county_id: '48215' }, cancer_type: 'lung' }));
for (const [n, i] of [['profile', { table: 'districts', id: 'TX-34' }], ['compare', { table: 'states', ids: ['TX', 'OK'] }], ['site_info', { topic: 'bills' }], ['final_answer', {}], ['query', {}], ['aggregate', {}], ['trials', {}], ['find_places', {}]]) check(`describeCall(${n}) non-empty`, typeof engine.describeCall(n, i) === 'string' && engine.describeCall(n, i).length > 3, engine.describeCall(n, i));
eq('describeResult(query)', engine.describeResult('query', {}, txOnc), `${E.tx_onc_no_trials.count} match; showing ${Math.min(20, E.tx_onc_no_trials.count)}`);
eq('describeResult(find_places single)', engine.describeResult('find_places', {}, await FP('Hidalgo County, Texas')), '1 place found');
eq('describeResult(find_places ambiguous)', engine.describeResult('find_places', {}, orange), `${E.places.orange_counties.length} candidates (ambiguous)`);
eq('describeResult(trials)', engine.describeResult('trials', {}, th), `${E.hidalgo.trials} trials`);
check('describeResult(error)', /^error: /.test(engine.describeResult('query', {}, bad)));
eq('placeName', [engine.placeName('48215'), engine.placeName('TX-34'), engine.placeName('4834'), engine.placeName('TX'), engine.placeName('US')], ['Hidalgo County, Texas', 'Texas 34th', 'Texas 34th', 'Texas', 'United States']);
eq('unitOf', [engine.unitOf('48215'), engine.unitOf('TX-34'), engine.unitOf('4834'), engine.unitOf('TX'), engine.unitOf('nci:1'), engine.unitOf('zzz')], ['county', 'district', 'district', 'state', null, null]);
const src = engine.sourcesFor(['counties', 'districts', 'cosponsors', 'bogus']);
check('sourcesFor', src.length === 3 && src[0].file === 'api/all_counties.json' && /^https:/.test(src[0].url) && src[0].as_of && src[2].table === 'cosponsors', src);
check('source.url of composite files is the first file (senators, cosponsors)', [engine.sourcesFor(['senators'])[0].url, engine.sourcesFor(['cosponsors'])[0].url].every(u => /^https:\/\/\S+\.(json|js)$/.test(u)), [engine.sourcesFor(['senators'])[0].url, engine.sourcesFor(['cosponsors'])[0].url]);
const v = engine.vintages();
check('vintages', v.data_as_of && v.incidence_period && v.mortality_period && v.oncologists_pulled && v.cosponsors_fetched && v.acs, v);
eq('full(unknown) → null', engine.full('nope'), null);
await engine.run('aggregate', { table: 'counties', measures: [{ stat: 'count' }] }, 'call-agg');
eq('full(aggregate call) → null (contract §11)', engine.full('call-agg'), null);
await engine.run('site_info', { topic: 'bills' }, 'call-si');
eq('full(site_info call) → null', engine.full('call-si'), null);

// ---------------------------------------------------------------- the API files alone: optional fields report "not loaded"
section('API files only (map files absent)');
const tmp = mkdtempSync(path.join(tmpdir(), 'ask-api-only-'));
mkdirSync(path.join(tmp, 'docs'));
symlinkSync(path.join(ROOT, 'docs', 'api'), path.join(tmp, 'docs', 'api'));
const lean = createEngine({ root: tmp });
await lean.load();
check('optional flags false', Object.values(lean.loaded.optional).every(x => x === false) && lean.loaded.places === false && lean.loaded.counties === true, lean.loaded);
const leanRow = (await lean.run('query', { table: 'counties', where: [{ field: 'id', op: '=', value: '48215' }], columns: ['zero_trial_share_by_type.lung', 'districts', 'menu'] })).rows[0];
eq('optional field → "not loaded"', leanRow['zero_trial_share_by_type.lung'], 'not loaded');
eq('districts still computed from the district lists', leanRow.districts, E.hidalgo.districts);
eq('computed fields still present', leanRow.menu, E.hidalgo.menu);
check('trials tool reports the missing file', /not loaded/.test((await lean.run('trials', { scope: { county_id: '48215' } })).error || ''));
check('profile lists not_loaded fields', (await lean.run('profile', { table: 'states', id: 'TX' })).not_loaded.includes('by_rucc.<code>.<measure>'));
check('find_places still resolves counties and districts', (await lean.run('find_places', { query: 'Hidalgo County, Texas' })).matches[0].id === '48215' && (await lean.run('find_places', { query: 'TX-34' })).matches[0].id === 'TX-34');
check('…but not ZIPs', (await lean.run('find_places', { query: '78501' })).matches.length === 0);
eq('senators cosponsor_date → "not loaded" without cosponsors.js', (await lean.run('query', { table: 'senators', where: [{ field: 'state', op: '=', value: 'SC' }] })).rows[0].cosponsor_date, 'not loaded');

// ---------------------------------------------------------------- other tables
section('other tables');
eq('nci_centers in CA', await cnt([{ field: 'state', op: '=', value: 'California' }], 'nci_centers'), E.states.ca_nci);
eq('facilities unresolved', await cnt([{ field: 'unresolved', op: '=', value: true }], 'facilities'), E.counts.facilities_unresolved);
eq('facilities in Hidalgo', await cnt([{ field: 'county_id', op: '=', value: '48215' }], 'facilities'), E.hidalgo.facilities);
eq('senators sponsoring S. 4440', (await Q({ table: 'senators', where: [{ field: 's4440', op: '=', value: 'sponsor' }] })).rows.map(r => r.id), E.senators.sponsor_s4440);
eq('senators not none', await cnt([{ field: 's4440', op: '!=', value: 'none' }], 'senators'), E.senators.n_not_none);
eq('senator cosponsor_date', (await Q({ table: 'senators', where: [{ field: 'id', op: '=', value: E.senators.sponsor_s4440[0] }] })).rows[0].cosponsor_date, E.senators.tim_scott_date);
eq('cosponsors by chamber', [await cnt([{ field: 'chamber', op: '=', value: 'house' }], 'cosponsors'), await cnt([{ field: 'chamber', op: '=', value: 'senate' }], 'cosponsors')], [E.cosponsors.n_house, E.cosponsors.n_senate]);
const ruizRow = (await Q({ table: 'cosponsors', where: [{ field: 'id', op: '=', value: E.cosponsors.ruiz_row }] })).rows[0];
eq('cosponsor district_id in TX-11 form', ruizRow.district_id, E.cosponsors.ruiz_district_id);
eq('cosponsor roles', (await A({ table: 'cosponsors', group_by: 'role', measures: [{ stat: 'count' }] })).groups.map(g => g.group), E.cosponsors.roles);
eq('states with one senator cosponsoring', await cnt([{ field: 'senators_cosponsoring_s4440', op: '=', value: 1 }], 'states'), E.states.n_with_1_cosponsoring);
eq('top-3 states by pct_lt20', (await Q({ table: 'states', order_by: [{ field: 'pct_lt20_trials_within_60rdmi', dir: 'desc' }], limit: 3 })).rows.map(r => r.id), E.states.top3_pct_lt20);

// ---------------------------------------------------------------- summary
console.log(`\n${passed} passed, ${failed} failed  (load ${loadMs} ms)`);
if (failed) { console.log('\nFailures:\n  ' + fails.join('\n  ')); process.exit(1); }
