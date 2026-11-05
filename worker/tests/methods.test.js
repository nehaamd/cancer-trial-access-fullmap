#!/usr/bin/env node
// The standard-method library (docs/ask/methods.js) through the engine's `method` tool (docs/ask/engine.js).
//   node worker/tests/methods.test.js            (exits 1 on any failure; no network, no model)
// For every method: run it for a sample state / place and check each sub-result equals the result of the equivalent free-tool
// call, written out here by hand from the method's rule text (so a change to a method's calls that the rule does not describe
// fails here); the results carry no error; sub-call ids "<id>.<n>" are kept for engine.full(); the method's own id stands for
// its primary call; parameters are validated; the review fields are well formed; the review sheet is current.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createEngine } from '../../docs/ask/engine.js';
import { METHODS, methodById, MEASURES, isReviewed } from '../../docs/ask/methods.js';
import { reviewSheet } from './methods_doc.js';

const HERE = path.dirname(fileURLToPath(import.meta.url)); const ROOT = path.resolve(HERE, '..', '..');
let passed = 0, failed = 0; const failures = [];
const test = async (name, fn) => { try { await fn(); passed++; console.log(`ok   ${name}`); } catch (e) { failed++; failures.push(name); console.log(`FAIL ${name}\n     ${String(e && e.message || e).split('\n').slice(0, 5).join('\n     ')}`); } };
const assert = (c, m) => { if (!c) throw new Error(m || 'assertion failed'); };
const engine = createEngine({ root: ROOT }); await engine.load();

const st = v => [{ field: 'state', op: '=', value: v }];
const one = (table, id, columns) => ({ name: 'query', input: { table, where: [{ field: 'id', op: '=', value: id }], columns } });
const NAT = columns => ({ name: 'query', input: { table: 'national', columns } });
const rank = (table, where, field, dir, limit, extra) => ({ name: 'query', input: { table, where, order_by: [{ field, dir }], limit, columns: [field, ...extra] } });
// method id -> [params, the equivalent free-tool calls]
const CASES = {
  counties_worst_access: [{ state: 'TX', n: 5 }, [rank('counties', st('TX'), 'pct_lt20_trials_within_60rdmi', 'desc', 5, ['people_lt20_trials_within_60rdmi'])]],
  counties_best_access: [{ state: 'TX', measure: 'trials_near', n: 5 }, [rank('counties', st('TX'), 'wmean_trials_within_60rdmi', 'desc', 5, ['pct_lt20_trials_within_60rdmi'])]],
  districts_worst_access: [{ state: 'GA', measure: 'median_nci' }, [rank('districts', st('GA'), 'median_road_mi_nci', 'desc', 10, ['nearest_nci'])]],
  districts_best_access: [{ measure: 'none', n: 3 }, [rank('districts', [], 'pct_zero_trials_within_60rdmi', 'asc', 3, ['people_zero_trials_within_60rdmi'])]],
  states_worst_access: [{ measure: 'far_broad', n: 5 }, [rank('states', [], 'pct_gt60rdmi_broad_menu', 'desc', 5, ['median_road_mi_broad_menu'])]],
  states_best_access: [{ measure: 'far_nci' }, [rank('states', [], 'pct_gt60rdmi_nci', 'asc', 10, ['median_road_mi_nci'])]],
  counties_short_of_trials: [{ state: 'KY' }, [{ name: 'query', input: { table: 'counties', where: [...st('KY'), { field: 'pct_lt20_trials_within_60rdmi', op: '>=', value: 50 }], order_by: [{ field: 'pop55', dir: 'desc' }], limit: 20, columns: ['pct_lt20_trials_within_60rdmi', 'people_lt20_trials_within_60rdmi'] } }, one('states', 'KY', ['pct_lt20_trials_within_60rdmi', 'people_lt20_trials_within_60rdmi'])]],
  people_short_of_trials_state: [{ state: 'OH' }, [one('states', 'OH', ['pct_lt20_trials_within_60rdmi', 'people_lt20_trials_within_60rdmi', 'pct_zero_trials_within_60rdmi', 'people_zero_trials_within_60rdmi']), NAT(['pct_lt20_trials_within_60rdmi', 'people_lt20_trials_within_60rdmi', 'pct_zero_trials_within_60rdmi', 'people_zero_trials_within_60rdmi'])]],
  counties_no_trial_within_60: [{ state: 'MT' }, [{ name: 'query', input: { table: 'counties', where: [...st('MT'), { field: 'trials_within_60rdmi_of_center', op: '=', value: 0 }], order_by: [{ field: 'pop55', dir: 'desc' }], limit: 20, columns: ['trials_within_60rdmi_of_center', 'pct_zero_trials_within_60rdmi'] } }, one('states', 'MT', ['pct_zero_trials_within_60rdmi', 'people_zero_trials_within_60rdmi'])]],
  oncologists_no_trials_counties: [{ state: 'TX' }, [{ name: 'query', input: { table: 'counties', where: [...st('TX'), { field: 'oncologists.class', op: '=', value: 2 }], order_by: [{ field: 'pop55', dir: 'desc' }], limit: 25, columns: ['oncologists.count', 'trials_listed_here', 'pct_lt20_trials_within_60rdmi'] } }]],
  oncologists_no_trials_districts: [{ state: 'TX' }, [{ name: 'query', input: { table: 'districts', where: [...st('TX'), { field: 'oncologists.pct_pop55_in_counties_with_oncologists_no_trials', op: '>', value: 0 }], order_by: [{ field: 'oncologists.pct_pop55_in_counties_with_oncologists_no_trials', dir: 'desc' }], limit: 25, columns: ['oncologists.pct_pop55_in_counties_with_oncologists_no_trials', 'oncologists.counties_with_oncologists_no_trials', 'member.name'] } }]],
  need_vs_access_state: [{ state: 'GA' }, [{ name: 'query', input: { table: 'counties', where: [...st('GA'), { field: 'high_incidence_low_access', op: '=', value: true }], order_by: [{ field: 'pop55', dir: 'desc' }], limit: 20, columns: ['incidence.all', 'pct_lt20_trials_within_60rdmi'] } }, one('states', 'GA', ['need_vs_access.counties_classified', 'need_vs_access.high_incidence_low_access_counties', 'need_vs_access.pop55', 'need_vs_access.cases_per_year'])]],
  deaths_vs_access_state: [{ state: 'MS' }, [{ name: 'query', input: { table: 'counties', where: [...st('MS'), { field: 'high_deaths_low_access', op: '=', value: true }], order_by: [{ field: 'pop55', dir: 'desc' }], limit: 20, columns: ['mortality.all', 'pct_lt20_trials_within_60rdmi'] } }, one('states', 'MS', ['deaths_vs_access.counties_classified', 'deaths_vs_access.high_death_low_access_counties', 'deaths_vs_access.pop55', 'deaths_vs_access.deaths_per_year'])]],
  hr3521_cosponsors_state: [{ state: 'TX' }, [{ name: 'query', input: { table: 'cosponsors', where: [{ field: 'bill', op: '=', value: 'ctma_hr' }, ...st('TX')], order_by: [{ field: 'date', dir: 'asc' }], limit: 50, columns: ['party', 'district_id', 'role', 'date'] } }, { name: 'query', input: { table: 'districts', where: st('TX'), order_by: [{ field: 'id', dir: 'asc' }], limit: 50, columns: ['member.name', 'member.party', 'member.ctma_hr3521'] } }]],
  hr3521_cosponsors_all: [{}, [{ name: 'query', input: { table: 'cosponsors', where: [{ field: 'bill', op: '=', value: 'ctma_hr' }], order_by: [{ field: 'date', dir: 'asc' }], limit: 50, columns: ['party', 'district_id', 'role', 'date'] } }, { name: 'aggregate', input: { table: 'cosponsors', where: [{ field: 'bill', op: '=', value: 'ctma_hr' }], group_by: 'party', measures: [{ field: 'id', stat: 'count' }] } }]],
  s4440_senators: [{ state: 'TX' }, [{ name: 'query', input: { table: 'senators', where: st('TX'), columns: ['party', 's4440', 'cosponsor_date'] } }]],
  my_representative: [{ query: '78501' }, [{ name: 'find_places', input: { query: '78501', limit: 5 } }, { name: 'profile', input: { table: 'counties', id: '48215' } }]],
  place_profile: [{ place: 'TX-34' }, [{ name: 'profile', input: { table: 'districts', id: 'TX-34' } }]],
  state_vs_nation: [{ state: 'KY' }, (c => [one('states', 'KY', c), NAT(c)])(['pct_lt20_trials_within_60rdmi', 'people_lt20_trials_within_60rdmi', 'pct_zero_trials_within_60rdmi', 'pct_gt60rdmi_nci', 'pct_gt60rdmi_broad_menu', 'median_road_mi_nci', 'wmean_trials_within_60rdmi', 'nonmetro_pct'])],
  rural_vs_metro_state: [{ state: 'KY' }, (c => [one('states', 'KY', c), NAT(c)])(['nonmetro_pct', 'metro.pop55', 'nonmetro.pop55', 'metro.pct_lt20', 'nonmetro.pct_lt20', 'metro.pct_zero', 'nonmetro.pct_zero', 'metro.median_road_mi_nci', 'nonmetro.median_road_mi_nci'])],
  rural_vs_metro_nation: [{}, [NAT(['nonmetro_pct', 'metro.pop55', 'nonmetro.pop55', 'metro.pct_lt20', 'nonmetro.pct_lt20', 'metro.pct_zero', 'nonmetro.pct_zero', 'metro.median_road_mi_nci', 'nonmetro.median_road_mi_nci'])]],
  nci_centers_state: [{ state: 'OH' }, [{ name: 'query', input: { table: 'nci_centers', where: st('OH'), order_by: [{ field: 'name', dir: 'asc' }], limit: 50, columns: ['full_name', 'tier'] } }, one('states', 'OH', ['median_road_mi_nci', 'pct_gt60rdmi_nci', 'nearest_nci'])]],
  nearest_nci_county: [{ county: '48215' }, [one('counties', '48215', ['nearest_nci', 'road_mi_nci_from_center', 'drive_hours_nci', 'median_road_mi_nci', 'pct_gt60rdmi_nci'])]],
  counties_far_from_nci_state: [{ state: 'NE', n: 5 }, [{ name: 'query', input: { table: 'counties', where: [...st('NE'), { field: 'road_mi_nci_from_center', op: '>', value: 100 }], order_by: [{ field: 'road_mi_nci_from_center', dir: 'desc' }], limit: 5, columns: ['road_mi_nci_from_center', 'nearest_nci', 'drive_hours_nci'] } }]],
  trials_in_county: [{ county: '48215', cancer_type: 'breast' }, [{ name: 'trials', input: { scope: { county_id: '48215' }, cancer_type: 'breast', limit: 10 } }]],
  trials_near_county: [{ county: '48061', phase: '3' }, [{ name: 'trials', input: { scope: { within_60_of_county_id: '48061' }, phase: '3', limit: 10 } }]],
  trials_in_state: [{ state: 'OH', cancer_type: 'breast' }, [{ name: 'trials', input: { scope: { state: 'OH' }, cancer_type: 'breast', limit: 10 } }, one('states', 'OH', ['trials_distinct', 'counties', 'counties_with_trials'])]],
  district_counties: [{ district: 'TX-34' }, [{ name: 'query', input: { table: 'counties', where: [{ field: 'districts', op: 'includes', value: 'TX-34' }], order_by: [{ field: 'pop55', dir: 'desc' }], limit: 50, columns: ['pct_lt20_trials_within_60rdmi', 'trials_listed_here', 'oncologists.count'] } }, one('districts', 'TX-34', ['pct_lt20_trials_within_60rdmi', 'trials_listed_here', 'member.name', 'member.party', 'member.ctma_hr3521'])]],
  trial_type_access_state: [{ state: 'TX', cancer_type: 'breast', n: 5 }, [{ name: 'query', input: { table: 'counties', where: st('TX'), order_by: [{ field: 'zero_trial_share_by_type.breast', dir: 'desc' }], limit: 5, columns: ['zero_trial_share_by_type.breast'] } }, one('states', 'TX', ['trials_within_60rdmi_by_cancer_type.breast'])]],
  incidence_rank_counties: [{ state: 'KY', site: 'lung', n: 5 }, [{ name: 'query', input: { table: 'counties', where: [...st('KY'), { field: 'incidence.by_site.lung', op: 'not_null' }], order_by: [{ field: 'incidence.by_site.lung', dir: 'desc' }], limit: 5, columns: ['incidence.by_site.lung', 'incidence.small_numbers', 'pct_lt20_trials_within_60rdmi'] } }]],
  death_rate_rank_counties: [{ state: 'WV' }, [{ name: 'query', input: { table: 'counties', where: [...st('WV'), { field: 'mortality.all', op: 'not_null' }], order_by: [{ field: 'mortality.all', dir: 'desc' }], limit: 10, columns: ['mortality.all', 'mortality.small_numbers', 'pct_lt20_trials_within_60rdmi'] } }]],
  oncologists_per_capita_states: [{ n: 5 }, [{ name: 'query', input: { table: 'states', order_by: [{ field: 'oncologists.oncologists_per_100k_pop55', dir: 'desc' }], limit: 5, columns: ['oncologists.oncologists_per_100k_pop55', 'oncologists.count'] } }]],
};

let k = 0;
const strip = r => { const o = JSON.parse(JSON.stringify(r)); delete o.truncated; return o; };
await test('every method in the library has a test case here, and every case names a method', () => {
  const missing = METHODS.filter(m => !CASES[m.id]).map(m => m.id), extra = Object.keys(CASES).filter(id => !methodById(id));
  assert(!missing.length && !extra.length, `missing cases: ${missing.join(', ')}; unknown: ${extra.join(', ')}`);
});
for (const m of METHODS) {
  const c = CASES[m.id]; if (!c) continue; const [params, free] = c;
  await test(`method ${m.id}: runs exactly the free-tool calls its rule describes`, async () => {
    const id = `toolu_mt${++k}`; const r = await engine.run('method', { id: m.id, params }, id);
    assert(!r.error, `error: ${JSON.stringify(r)}`); assert(r.method === m.id && r.title === m.title && r.rule === m.rule, 'title and rule come back');
    assert(r.reviewed === isReviewed(m) && (r.reviewed ? r.reviewed_by === m.reviewed_by && r.reviewed_on === m.reviewed_on : !('reviewed_by' in r)), 'the review fields come back as the library has them');
    assert(r.results.length === free.length, `${r.results.length} sub-calls, expected ${free.length}: ${JSON.stringify(r.results.map(x => [x.name, x.input]))}`);
    for (const [i, fc] of free.entries()) {
      const sub = r.results[i]; assert(sub.call === `${id}.${i + 1}`, `sub-call id ${sub.call}`); assert(sub.name === fc.name, `sub-call ${i + 1} is ${sub.name}, expected ${fc.name}`);
      assert(JSON.stringify(sub.input) === JSON.stringify(fc.input), `sub-call ${i + 1} input\n       got ${JSON.stringify(sub.input)}\n      want ${JSON.stringify(fc.input)}`);
      assert(!sub.result.error, `sub-call ${i + 1} error: ${JSON.stringify(sub.result)}`);
      const want = await engine.run(fc.name, fc.input, `toolu_free${k}_${i}`);
      if (!sub.result.truncated) assert(JSON.stringify(strip(sub.result)) === JSON.stringify(want), `sub-call ${i + 1} result differs from the free call`);
      else { assert(sub.result.count === want.count && JSON.stringify(sub.result.rows) === JSON.stringify(want.rows.slice(0, sub.result.rows.length)), `truncated sub-call ${i + 1} is not a prefix of the free result`); }
      const full = engine.full(sub.call); if (['query', 'compare', 'profile', 'find_places'].includes(fc.name)) assert(full && JSON.stringify(full.ids) === JSON.stringify(engine.full(`toolu_free${k}_${i}`).ids), `engine.full(${sub.call}) keeps every id`);
    }
    assert(JSON.stringify(r).length <= 24 * 1024, 'the combined result fits the 24 KB protocol cap');
    if (r.primary_call) assert(JSON.stringify(engine.full(id).ids) === JSON.stringify(engine.full(r.primary_call).ids), 'the method id stands for its primary call in engine.full');
    const hl = engine.highlightIds({ from_call: r.primary_call || id }); if (r.primary_call) assert(hl && Array.isArray(hl.ids), 'highlightIds works on the sub-call');
    assert(/^Standard method: /.test(engine.describeCall('method', { id: m.id, params })), 'describeCall');
  });
}
await test('every ranking measure names a field, a direction and a map layer for each unit', () => {
  for (const [key, ms] of Object.entries(MEASURES)) { assert(ms.field && ['asc', 'desc'].includes(ms.worst) && ms.words, key); for (const u of ['county', 'district', 'state']) assert(ms.layer[u], `${key} ${u}`); }
});
await test('parameters are validated: unknown method, unknown or missing parameter, bad state, bad id, out-of-range n, bad enum', async () => {
  const err = async (input, sub) => { const r = await engine.run('method', input, 'toolu_bad'); assert(r.error && (r.error + ' ' + (r.hint || '')).includes(sub), `${JSON.stringify(input)} -> ${JSON.stringify(r)}`); };
  await err({ id: 'nope' }, 'unknown method'); await err({ id: 'oncologists_no_trials_counties', params: {} }, 'needs state'); await err({ id: 'oncologists_no_trials_counties', params: { state: 'ZZ' } }, 'unknown state');
  await err({ id: 'oncologists_no_trials_counties', params: { state: 'TX', place: '48215' } }, "no parameter 'place'"); await err({ id: 'nearest_nci_county', params: { county: 'Hidalgo' } }, 'not a county FIPS');
  await err({ id: 'counties_worst_access', params: { n: 99 } }, 'n must be'); await err({ id: 'counties_worst_access', params: { measure: 'best' } }, 'unknown measure'); await err({ id: 'district_counties', params: { district: 'Texas' } }, 'not a district id');
  const ok = await engine.run('method', { id: 'oncologists_no_trials_counties', params: { state: 'Texas' } }, 'toolu_ok'); assert(!ok.error && ok.params.state === 'TX', 'a state name is accepted');
  const d = await engine.run('method', { id: 'district_counties', params: { district: 'tx 34' } }, 'toolu_ok2'); assert(!d.error && d.params.district === 'TX-34', 'district forms are normalised');
});
await test('reviewed_by / reviewed_on are both empty or both set (a name and a YYYY-MM-DD date); only the site owner sets them', () => {
  for (const m of METHODS) { const by = String(m.reviewed_by || ''), on = String(m.reviewed_on || ''); assert((by === '' && on === '') || (by.trim().length >= 2 && /^\d{4}-\d{2}-\d{2}$/.test(on)), `${m.id}: reviewed_by "${by}", reviewed_on "${on}"`); assert(isReviewed(m) === !!(by && on), m.id); }
  console.log(`     ${METHODS.filter(isReviewed).length} of ${METHODS.length} methods reviewed`);
});
await test('docs/ask/METHODS_REVIEW.md is the current output of node worker/tests/methods_doc.js', () => {
  const file = path.join(ROOT, 'docs/ask/METHODS_REVIEW.md'); assert(fs.existsSync(file), 'METHODS_REVIEW.md missing: run node worker/tests/methods_doc.js');
  assert(fs.readFileSync(file, 'utf8') === reviewSheet(), 'METHODS_REVIEW.md is stale: run node worker/tests/methods_doc.js');
});

console.log(`\n${passed} passed, ${failed} failed${failed ? ': ' + failures.join('; ') : ''}`);
process.exit(failed ? 1 : 0);
