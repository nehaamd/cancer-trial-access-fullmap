#!/usr/bin/env node
// The per-place claim check (worker/src/claims.js; ASK_CONTRACT.md §6 rule 6) against REAL engine results.
//   node worker/tests/claims.test.js            (exits 1 on any failure; no network, no model)
// Part 1: realistic CORRECT answers, written the way the model writes them, from the results the engine returns for the calls the
// model makes; every one must verify (a false rejection hides a correct answer: the worst failure). The figures are read from the
// results at run time, so the cases follow a data refresh. Part 2: wrong attributions (a correct number next to the wrong place,
// a swapped pair, a state figure written as the nation's, a claim that does not match its row, …) that must be rejected, with an
// issue that names the figure and the place. Part 3: unit tests of resolvePath / findMentions.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as catalog from '../../docs/ask/catalog.js';
import { createEngine } from '../../docs/ask/engine.js';
import { truncateResult } from '../../docs/ask/render.js';
import { verify, buildContext } from '../src/verify.js';
import { resolvePath } from '../src/claims.js';

const HERE = path.dirname(fileURLToPath(import.meta.url)); const ROOT = path.resolve(HERE, '..', '..');
let passed = 0, failed = 0; const failures = [];
const test = async (name, fn) => { try { await fn(); passed++; console.log(`ok   ${name}`); } catch (e) { failed++; failures.push(name); console.log(`FAIL ${name}\n     ${String(e && e.message || e).split('\n').slice(0, 6).join('\n     ')}`); } };
const assert = (c, m) => { if (!c) throw new Error(m || 'assertion failed'); };

const engine = createEngine({ root: ROOT }); await engine.load();
const f = n => Number(n).toLocaleString('en-US');
let seq = 0;
// one model turn: the calls, run through the real engine; results as the client sends them (truncated to 24 KB by rows)
async function scenario(q, calls) {
  const blocks = calls.map(c => ({ type: 'tool_use', id: `toolu_c${String(++seq).padStart(3, '0')}`, name: c.name, input: c.input }));
  const R = {}; const results = [];
  for (const b of blocks) { const r = await engine.run(b.name, b.input, b.id); assert(!r.error, `${b.name} failed: ${JSON.stringify(r).slice(0, 200)}`); R[b.id] = r; results.push({ tool_use_id: b.id, content: truncateResult(r) }); }
  return { q, turns: [{ assistant: blocks, results }], R, id: blocks.map(b => b.id) };
}
const claim = (place, field, value, call) => ({ place, field, value, call });
const run = (sc, answer, claims) => verify({ answer, answerable: 'yes', interpretation: 'Read from the tool results.', claims }, buildContext({ question: sc.q, turns: sc.turns, catalog }));
const correct = []; const wrong = [];
const ok = (name, sc, answer, claims) => correct.push({ name, sc, answer, claims });
const bad = (name, sc, answer, claims, expect) => wrong.push({ name, sc, answer, claims, expect });

// ======================= the scenarios =======================
const TX = [{ field: 'state', op: '=', value: 'TX' }];
{ // 1. a ranking of five counties with two figures each
  const sc = await scenario('Which Texas counties have the worst trial access?', [{ name: 'query', input: { table: 'counties', where: TX, order_by: [{ field: 'pct_lt20_trials_within_60rdmi', dir: 'desc' }], limit: 5, columns: ['people_lt20_trials_within_60rdmi'] } }]);
  const [id] = sc.id; const r = sc.R[id]; const rows = r.rows;
  const answer = `Of ${r.in_scope} Texas counties, the five with the largest share of residents 55+ short of trials (fewer than 20 within 60 road-miles) are ${rows.slice(0, 4).map(x => `${x.name} (${x.pct_lt20_trials_within_60rdmi}%, ${f(x.pop55)} residents 55+)`).join(', ')} and ${rows[4].name} (${rows[4].pct_lt20_trials_within_60rdmi}%, ${f(rows[4].pop55)}). Ties at the same share are listed by residents 55+.`;
  const claims = [claim('TX', 'in_scope', r.in_scope, id), ...rows.flatMap(x => [claim(x.id, 'pct_lt20_trials_within_60rdmi', x.pct_lt20_trials_within_60rdmi, id), claim(x.id, 'pop55', x.pop55, id)])];
  ok('ranking: five Texas counties with share and residents', sc, answer, claims);
  // wrong: the residents of the first two swapped inside the parentheses
  const sw = answer.replace(f(rows[0].pop55), '§').replace(f(rows[1].pop55), f(rows[0].pop55)).replace('§', f(rows[1].pop55));
  bad('ranking: residents 55+ of two counties swapped in the parentheses', sc, sw, claims, rows[1].name);
}
{ // 2. a national ranking of five districts with the member
  const sc = await scenario('Which 5 congressional districts have the largest share of residents 55+ short of trials?', [{ name: 'query', input: { table: 'districts', order_by: [{ field: 'pct_lt20_trials_within_60rdmi', dir: 'desc' }], limit: 5, columns: ['member.name'] } }]);
  const [id] = sc.id; const rows = sc.R[id].rows;
  const answer = `The five districts with the largest share of residents 55+ short of trials are ${rows.map(x => `${x.name} (${x['member.name']}), at ${x.pct_lt20_trials_within_60rdmi}%`).join('; ')}. Shares are of residents 55+ with fewer than 20 recruiting trials within 60 road-miles.`;
  ok('ranking: five districts nationally with members and shares', sc, answer, rows.map(x => claim(x.id, 'pct_lt20_trials_within_60rdmi', x.pct_lt20_trials_within_60rdmi, id)));
}
{ // 3. two states compared, with the national reference row
  const sc = await scenario('Compare Wyoming and Montana on trial access', [{ name: 'compare', input: { table: 'states', ids: ['WY', 'MT'] } }]);
  const [id] = sc.id; const r = sc.R[id]; const wy = r.rows.find(x => x.id === 'WY'), mt = r.rows.find(x => x.id === 'MT'), us = r.reference.find(x => x.id === 'US');
  const claims = [claim('WY', 'pct_lt20_trials_within_60rdmi', wy.pct_lt20_trials_within_60rdmi, id), claim('MT', 'pct_lt20_trials_within_60rdmi', mt.pct_lt20_trials_within_60rdmi, id), claim('US', 'pct_lt20_trials_within_60rdmi', us.pct_lt20_trials_within_60rdmi, id), claim('WY', 'median_road_mi_nci', wy.median_road_mi_nci, id), claim('MT', 'median_road_mi_nci', mt.median_road_mi_nci, id)];
  const answer = `Wyoming has ${wy.pct_lt20_trials_within_60rdmi}% of residents 55+ short of trials, against ${mt.pct_lt20_trials_within_60rdmi}% in Montana and ${us.pct_lt20_trials_within_60rdmi}% nationally. The median distance to an NCI-designated center is ${wy.median_road_mi_nci} road-miles in Wyoming and ${mt.median_road_mi_nci} in Montana.`;
  ok('comparison: Wyoming against Montana and the nation', sc, answer, claims);
  ok('comparison: "Wyoming at X%, against Y% in Montana" (number before its place)', sc, `Wyoming is at ${wy.pct_lt20_trials_within_60rdmi}%, against ${mt.pct_lt20_trials_within_60rdmi}% in Montana.`, claims);
  ok('comparison: "With X%, Wyoming …" (number before the place, in its own clause)', sc, `With ${wy.pct_lt20_trials_within_60rdmi}%, Wyoming has the larger share of residents 55+ short of trials; Montana has ${mt.pct_lt20_trials_within_60rdmi}%.`, claims);
  ok('comparison: "respectively" form', sc, `Wyoming and Montana have ${wy.pct_lt20_trials_within_60rdmi}% and ${mt.pct_lt20_trials_within_60rdmi}% of residents 55+ short of trials, respectively.`, claims);
  ok('comparison: "higher than" form with possessives', sc, `Wyoming's share of residents 55+ short of trials, ${wy.pct_lt20_trials_within_60rdmi}%, is higher than Montana's ${mt.pct_lt20_trials_within_60rdmi}%; the national share is ${us.pct_lt20_trials_within_60rdmi}%.`, claims);
  bad('comparison: the two states\' shares swapped', sc, `Wyoming has ${mt.pct_lt20_trials_within_60rdmi}% of residents 55+ short of trials, against ${wy.pct_lt20_trials_within_60rdmi}% in Montana.`, claims, 'Wyoming');
  bad('comparison: the national share written as Wyoming\'s', sc, `Wyoming has ${us.pct_lt20_trials_within_60rdmi}% of residents 55+ short of trials, against ${wy.pct_lt20_trials_within_60rdmi}% nationally.`, claims, 'Wyoming');
  bad('comparison: Montana\'s median distance written as Wyoming\'s in a "with" clause', sc, `With ${mt.median_road_mi_nci} road-miles to the nearest NCI center, Wyoming is farther than Montana.`, claims, 'Wyoming');
}
{ // 4. which is higher: the nonmetro share of two states
  const sc = await scenario('Which is more rural, Wyoming or Montana?', [{ name: 'query', input: { table: 'states', where: [{ field: 'id', op: 'in', value: ['WY', 'MT'] }], columns: ['nonmetro_pct'] } }]);
  const [id] = sc.id; const rows = sc.R[id].rows; const wy = rows.find(x => x.id === 'WY'), mt = rows.find(x => x.id === 'MT'); const [hi, lo] = wy.nonmetro_pct >= mt.nonmetro_pct ? [wy, mt] : [mt, wy];
  ok('which is higher: nonmetro share of two states', sc, `${hi.name} is more rural: ${hi.nonmetro_pct}% of its residents 55+ live in nonmetro counties, compared with ${lo.nonmetro_pct}% in ${lo.name}.`, [claim(hi.id, 'nonmetro_pct', hi.nonmetro_pct, id), claim(lo.id, 'nonmetro_pct', lo.nonmetro_pct, id)]);
}
{ // 5. ZIP → county → districts (find_places + profile)
  const sc = await scenario('Who represents ZIP 78501 and how is trial access there?', [{ name: 'find_places', input: { query: '78501' } }, { name: 'profile', input: { table: 'counties', id: '48215' } }]);
  const [, pid] = sc.id; const p = sc.R[pid]; const [d1, d2] = p.related.districts;
  const answer = `ZIP 78501 is in ${p.name}, which overlaps two congressional districts: ${d1.name}, represented by ${d1.member} (${d1.party}), and ${d2.name}, represented by ${d2.member} (${d2.party}). In ${p.name.split(',')[0]}, ${p.row.pct_lt20_trials_within_60rdmi}% of residents 55+ are short of trials and ${p.row.trials_listed_here} recruiting trials have a site in the county. The data cannot say which of the two districts a single address is in.`;
  ok('ZIP → county → districts with two figures', sc, answer, [claim('48215', 'pct_lt20_trials_within_60rdmi', p.row.pct_lt20_trials_within_60rdmi, pid), claim('48215', 'trials_listed_here', p.row.trials_listed_here, pid)]);
}
{ // 6. a count with the sum of residents and the largest place
  const sc = await scenario('Which counties in Texas have oncologists but no clinical trials?', [{ name: 'query', input: { table: 'counties', where: [...TX, { field: 'oncologists.class', op: '=', value: 2 }], order_by: [{ field: 'pop55', dir: 'desc' }], limit: 50, columns: ['oncologists.count', 'trials_listed_here'] } }]);
  const [id] = sc.id; const r = sc.R[id]; const [a, b, c] = r.rows;
  const claims = [claim('TX', 'count', r.count, id), claim('TX', 'in_scope', r.in_scope, id), claim('TX', 'sum_pop55_matching', r.sum_pop55_matching, id), ...[a, b, c].flatMap(x => [claim(x.id, 'pop55', x.pop55, id), claim(x.id, 'oncologists.count', x['oncologists.count'], id)])];
  const answer = `${r.count} of ${r.in_scope} Texas counties have at least one oncologist but no recruiting trial with a site in the county; ${f(r.sum_pop55_matching)} residents 55+ live in them. The largest are ${a.name} (${f(a.pop55)} residents 55+, ${a['oncologists.count']} oncologists), ${b.name} (${f(b.pop55)}, ${b['oncologists.count']}) and ${c.name} (${f(c.pop55)}, ${c['oncologists.count']}).`;
  ok('count with sum of residents and the three largest', sc, answer, claims);
  ok('count with the sum rounded to millions / thousands', sc, `${r.count} Texas counties have oncologists but no trial site; about ${(r.sum_pop55_matching / 1e6).toPrecision(2)} million residents 55+ live in them, the most in ${a.name} with about ${f(Math.round(a.pop55 / 1000) * 1000)}.`, claims);
  ok('count, then a sentence with no place name carrying the scope figure', sc, `The largest such county is ${a.name}, with ${a['oncologists.count']} oncologists. In all, ${f(r.sum_pop55_matching)} residents 55+ live in the ${r.count} counties.`, claims);
  bad('count: a county\'s residents written next to another county', sc, `The largest are ${a.name} (${f(b.pop55)} residents 55+) and ${b.name} (${f(a.pop55)}).`, claims, a.name);
  bad('count: the oncologists of the second county given to the first in a following sentence', sc, `The largest is ${a.name}. ${b.name} follows. It has ${a['oncologists.count']} oncologists.`, claims, b.name);
  bad('count: figures written but no claims at all', sc, answer, [], 'claims is empty');
  bad('count: a claim whose value does not match its row', sc, answer, claims.map(x => x.place === a.id && x.field === 'oncologists.count' ? { ...x, value: x.value + 3 } : x), 'copy the value');
  bad('count: a whole-result figure claimed for the nation on a Texas query', sc, answer, claims.map(x => x.field === 'count' ? { ...x, place: 'US' } : x), 'whole-result figure');
  bad('count: a claim naming a call that does not exist', sc, answer, claims.map((x, i) => i === 0 ? { ...x, call: 'toolu_nope' } : x), 'not a tool call');
}
{ // 7. a profile with eight figures, the related state and national rows
  const sc = await scenario('Tell me about Hidalgo County, Texas', [{ name: 'find_places', input: { query: 'Hidalgo County, Texas' } }, { name: 'profile', input: { table: 'counties', id: '48215' } }]);
  const [, id] = sc.id; const p = sc.R[id]; const r = p.row; const st = p.related.state_row_headline, us = p.related.national_headline;
  const claims = [claim('48215', 'pop55', r.pop55, id), claim('48215', 'pct_lt20_trials_within_60rdmi', r.pct_lt20_trials_within_60rdmi, id), claim('48215', 'median_road_mi_nci', r.median_road_mi_nci, id), claim('48215', 'trials_listed_here', r.trials_listed_here, id), claim('48215', 'wmean_trials_within_60rdmi', r.wmean_trials_within_60rdmi, id), claim('48215', 'oncologists.count', r.oncologists.count, id), claim('48215', 'context.uninsured', r.context.uninsured, id), claim('48215', 'context.poverty', r.context.poverty, id), claim('TX', 'pct_lt20_trials_within_60rdmi', st.pct_lt20_trials_within_60rdmi, id), claim('US', 'pct_lt20_trials_within_60rdmi', us.pct_lt20_trials_within_60rdmi, id), claim('US', 'median_road_mi_nci', us.median_road_mi_nci, id)];
  const answer = `${p.name} has ${f(r.pop55)} residents 55+, and ${r.pct_lt20_trials_within_60rdmi}% of them are short of trials, against ${st.pct_lt20_trials_within_60rdmi}% statewide and ${us.pct_lt20_trials_within_60rdmi}% nationally. Their median distance to an NCI-designated center is ${r.median_road_mi_nci} road-miles; the nearest is ${r.nearest_nci}. ${r.trials_listed_here} recruiting trials have a site in the county, and residents have ${r.wmean_trials_within_60rdmi} on average within 60 road-miles. The county has ${r.oncologists.count} oncologists; ${r.context.uninsured}% of residents are uninsured and ${r.context.poverty}% live in poverty.`;
  ok('profile: eight county figures with the state and national shares', sc, answer, claims);
  ok('profile: the nearest broad menu named as "Bexar, Texas" next to a county figure', sc, `${p.name} is ${r.road_mi_broad_menu_from_center} road-miles by road from its nearest broad trial menu, ${r.nearest_broad_menu}, and ${r.pct_lt20_trials_within_60rdmi}% of its residents 55+ are short of trials.`, [...claims, claim('48215', 'road_mi_broad_menu_from_center', r.road_mi_broad_menu_from_center, id)]);
  ok('profile: an aside in parentheses naming the districts, then the county\'s figure', sc, `${p.name} (${p.related.districts.map(d => d.name).join(' and ')}) has ${r.trials_listed_here} recruiting trials with a site in the county and ${r.oncologists.count} oncologists.`, claims);
  bad('profile: the national median distance written as the county\'s', sc, `${p.name} has a median of ${us.median_road_mi_nci} road-miles to an NCI-designated center, against ${r.median_road_mi_nci} nationally.`, claims, p.name);
}
{ // 8. a state and its national comparison (two queries)
  const sc = await scenario('How does Kentucky compare with the national average on the share of residents short of trials?', [{ name: 'query', input: { table: 'states', where: [{ field: 'id', op: '=', value: 'KY' }], columns: ['pct_lt20_trials_within_60rdmi', 'median_road_mi_nci'] } }, { name: 'query', input: { table: 'national', columns: ['pct_lt20_trials_within_60rdmi', 'median_road_mi_nci'] } }]);
  const [a, b] = sc.id; const ky = sc.R[a].rows[0], us = sc.R[b].rows[0];
  const claims = [claim('KY', 'pct_lt20_trials_within_60rdmi', ky.pct_lt20_trials_within_60rdmi, a), claim('KY', 'median_road_mi_nci', ky.median_road_mi_nci, a), claim('US', 'pct_lt20_trials_within_60rdmi', us.pct_lt20_trials_within_60rdmi, b), claim('US', 'median_road_mi_nci', us.median_road_mi_nci, b)];
  ok('state against the nation', sc, `In Kentucky, ${ky.pct_lt20_trials_within_60rdmi}% of residents 55+ are short of trials, against ${us.pct_lt20_trials_within_60rdmi}% nationally. The median distance to an NCI-designated center is ${ky.median_road_mi_nci} road-miles in Kentucky and ${us.median_road_mi_nci} in the United States.`, claims);
  ok('state against the nation, the national figure in its own sentence', sc, `Kentucky has ${ky.pct_lt20_trials_within_60rdmi}% of residents 55+ short of trials. Across the United States the share is ${us.pct_lt20_trials_within_60rdmi}%.`, claims);
  bad('state against the nation: swapped', sc, `In Kentucky, ${us.pct_lt20_trials_within_60rdmi}% of residents 55+ are short of trials, against ${ky.pct_lt20_trials_within_60rdmi}% nationally.`, claims, 'Kentucky');
}
{ // 9. an aggregate by metro / nonmetro in one state
  const sc = await scenario('In Kentucky, how does trial access in rural counties compare with metro counties?', [{ name: 'aggregate', input: { table: 'counties', where: [{ field: 'state', op: '=', value: 'KY' }], group_by: 'metro', measures: [{ field: 'pct_lt20_trials_within_60rdmi', stat: 'weighted_mean' }] } }]);
  const [id] = sc.id; const r = sc.R[id]; const non = r.groups.find(g => g.group === false), met = r.groups.find(g => g.group === true); const K = 'pct_lt20_trials_within_60rdmi:weighted_mean';
  const claims = [claim('KY', 'count', r.count, id), claim('KY', 'groups[group=false].n', non.n, id), claim('KY', 'groups[group=true].n', met.n, id), claim('KY', `groups[group=false].measures.${K}`, non.measures[K], id), claim('KY', `groups[group=true].measures.${K}`, met.measures[K], id)];
  ok('aggregate: metro against nonmetro in a state', sc, `Across Kentucky's ${r.count} counties, residents 55+ of nonmetro (rural) counties are short of trials at a weighted ${non.measures[K]}%, against ${met.measures[K]}% in metro counties. There are ${non.n} nonmetro and ${met.n} metro counties.`, claims);
  bad('aggregate: the Kentucky figure written as Ohio\'s', sc, `In Ohio, residents 55+ of nonmetro counties are short of trials at a weighted ${non.measures[K]}%.`, claims, 'Ohio');
}
{ // 10. trials in a county by phase and sponsor
  const sc = await scenario('What phases are the trials in Hidalgo County, Texas?', [{ name: 'trials', input: { scope: { county_id: '48215' } } }]);
  const [id] = sc.id; const r = sc.R[id]; const ph = Object.entries(r.by_phase).filter(([, v]) => v > 0).sort((x, y) => y[1] - x[1]);
  const claims = [claim('48215', 'count', r.count, id), ...ph.map(([k, v]) => claim('48215', `by_phase.${k}`, v, id)), claim('48215', 'by_sponsor_type.industry', r.by_sponsor_type.industry, id)];
  ok('trials by phase in a county', sc, `Hidalgo County, Texas has ${r.count} recruiting trials with a site in the county: ${ph.map(([k, v]) => `${v} phase ${k}`).join(', ')}. ${r.by_sponsor_type.industry} are sponsored by industry.`, claims);
}
{ // 11. three counties compared on trials listed
  const sc = await scenario('Compare Hidalgo, Cameron and Webb counties in Texas on trials', [{ name: 'compare', input: { table: 'counties', ids: ['48215', '48061', '48479'], columns: ['trials_listed_here'] } }]);
  const [id] = sc.id; const r = sc.R[id]; const [h, c, w] = ['48215', '48061', '48479'].map(x => r.rows.find(y => y.id === x));
  const claims = [h, c, w].map(x => claim(x.id, 'trials_listed_here', x.trials_listed_here, id));
  ok('three counties compared on trials', sc, `${h.name} lists ${h.trials_listed_here} recruiting trials with a site in the county, ${c.name} ${c.trials_listed_here} and ${w.name} ${w.trials_listed_here}.`, claims);
  ok('three counties: a range "from X in A to Y in B"', sc, `Trials with a site in the county range from ${w.trials_listed_here} in ${w.name} to ${h.trials_listed_here} in ${h.name}; ${c.name} has ${c.trials_listed_here}.`, claims);
  ok('three counties compared, short names', sc, `Hidalgo County has ${h.trials_listed_here} trials, Cameron County ${c.trials_listed_here} and Webb County ${w.trials_listed_here}.`, claims);
  bad('three counties: the first two counts swapped', sc, `${c.name} lists ${h.trials_listed_here} recruiting trials, ${h.name} ${c.trials_listed_here} and ${w.name} ${w.trials_listed_here}.`, claims, c.name);
}
{ // 12. a definition and a no-figure answer (no claims needed)
  const sc = await scenario('What does short of trials mean?', [{ name: 'site_info', input: { topic: 'definitions' } }]);
  ok('definition: constants only, no claims', sc, 'Short of trials means fewer than 20 recruiting trials within 60 road-miles of where a resident aged 55 or older lives.', undefined);
  const sc2 = await scenario('Have the Texas senators signed on to S. 4440?', [{ name: 'query', input: { table: 'senators', where: TX, columns: ['party', 's4440'] } }]);
  const rows = sc2.R[sc2.id[0]].rows;
  ok('senators: names and positions, no figures', sc2, `Neither Texas senator cosponsors S. 4440: ${rows[0].name} (${rows[0].party}) and ${rows[1].name} (${rows[1].party}) are both listed as not cosponsoring.`, undefined);
}
{ // 13. cosponsors by party (aggregate, national scope)
  const sc = await scenario('How many Democrats and Republicans cosponsor H.R. 3521?', [{ name: 'aggregate', input: { table: 'cosponsors', where: [{ field: 'bill', op: '=', value: 'ctma_hr' }], group_by: 'party', measures: [{ field: 'id', stat: 'count' }] } }]);
  const [id] = sc.id; const r = sc.R[id]; const D = r.groups.find(g => g.group === 'D'), Rr = r.groups.find(g => g.group === 'R');
  ok('cosponsors by party (whole-result figures, scope US)', sc, `H.R. 3521 has ${r.count} sponsor and cosponsor records: ${D.n} Democrats and ${Rr.n} Republicans.`, [claim('US', 'count', r.count, id), claim('US', 'groups[group=D].n', D.n, id), claim('US', 'groups[group=R].n', Rr.n, id)]);
}
{ // 14. a standard method: the three states with the worst access (claims on the sub-call)
  const sc = await scenario('Which 3 states have the worst trial access?', [{ name: 'method', input: { id: 'states_worst_access', params: { n: 3 } } }]);
  const [id] = sc.id; const sub = sc.R[id].results[0]; const rows = sub.result.rows;
  ok('method: three states, claims on the method sub-call', sc, `The states with the largest share of residents 55+ short of trials are ${rows[0].name} at ${rows[0].pct_lt20_trials_within_60rdmi}%, ${rows[1].name} at ${rows[1].pct_lt20_trials_within_60rdmi}% and ${rows[2].name} at ${rows[2].pct_lt20_trials_within_60rdmi}%.`, rows.map(x => claim(x.id, 'pct_lt20_trials_within_60rdmi', x.pct_lt20_trials_within_60rdmi, sub.call)));
  bad('method: a claim on the method id with a wrong value', sc, `${rows[0].name} has ${rows[0].pct_lt20_trials_within_60rdmi}% of residents 55+ short of trials.`, [claim(rows[0].id, 'pct_lt20_trials_within_60rdmi', rows[1].pct_lt20_trials_within_60rdmi === rows[0].pct_lt20_trials_within_60rdmi ? 1 : rows[1].pct_lt20_trials_within_60rdmi, id)], 'sub-call');
}
{ // 15. a district profile
  const sc = await scenario('Tell me about Texas 34th', [{ name: 'find_places', input: { query: 'TX-34' } }, { name: 'profile', input: { table: 'districts', id: 'TX-34' } }]);
  const [, id] = sc.id; const p = sc.R[id]; const r = p.row; const n = p.related.counties.length;
  ok('district profile with member, residents and county count', sc, `${p.name}, represented by ${r.member.name} (${r.member.party}), has ${f(r.pop55)} residents 55+ in ${n} counties; ${r.pct_lt20_trials_within_60rdmi}% of them are short of trials and the median distance to an NCI-designated center is ${r.median_road_mi_nci} road-miles.`, [claim('TX-34', 'pop55', r.pop55, id), claim('TX-34', 'related.counties.length', n, id), claim('TX-34', 'pct_lt20_trials_within_60rdmi', r.pct_lt20_trials_within_60rdmi, id), claim('TX-34', 'median_road_mi_nci', r.median_road_mi_nci, id)]);
}
{ // 16. rural against metro from the published state split
  const sc = await scenario('Is trial access worse in rural Texas?', [{ name: 'query', input: { table: 'states', where: [{ field: 'id', op: '=', value: 'TX' }], columns: ['metro.pct_lt20', 'nonmetro.pct_lt20', 'nonmetro_pct'] } }]);
  const [id] = sc.id; const r = sc.R[id].rows[0];
  ok('rural against metro in a state (published split)', sc, `In Texas, ${r['nonmetro.pct_lt20']}% of nonmetro residents 55+ are short of trials, against ${r['metro.pct_lt20']}% of metro residents; ${r.nonmetro_pct}% of the state's residents 55+ live in nonmetro counties.`, [claim('TX', 'metro.pct_lt20', r['metro.pct_lt20'], id), claim('TX', 'nonmetro.pct_lt20', r['nonmetro.pct_lt20'], id), claim('TX', 'nonmetro_pct', r.nonmetro_pct, id)]);
}
{ // 17. need vs access in a state (state row) and the national figure in millions
  const sc = await scenario('Where in Texas is cancer incidence high and trial access low?', [{ name: 'query', input: { table: 'states', where: [{ field: 'id', op: '=', value: 'TX' }], columns: ['need_vs_access.high_incidence_low_access_counties', 'need_vs_access.pop55', 'need_vs_access.cases_per_year'] } }, { name: 'query', input: { table: 'national', columns: ['people_lt20_trials_within_60rdmi', 'pct_lt20_trials_within_60rdmi'] } }]);
  const [a, b] = sc.id; const r = sc.R[a].rows[0], us = sc.R[b].rows[0];
  ok('need vs access state row, and a national figure in millions', sc, `In Texas, ${r['need_vs_access.high_incidence_low_access_counties']} counties have high cancer incidence and low trial access; ${f(r['need_vs_access.pop55'])} residents 55+ live in them, with about ${f(r['need_vs_access.cases_per_year'])} new cases a year. Nationally, ${(us.people_lt20_trials_within_60rdmi / 1e6).toFixed(1)} million residents 55+ (${us.pct_lt20_trials_within_60rdmi}%) are short of trials.`, [claim('TX', 'need_vs_access.high_incidence_low_access_counties', r['need_vs_access.high_incidence_low_access_counties'], a), claim('TX', 'need_vs_access.pop55', r['need_vs_access.pop55'], a), claim('TX', 'need_vs_access.cases_per_year', r['need_vs_access.cases_per_year'], a), claim('US', 'people_lt20_trials_within_60rdmi', us.people_lt20_trials_within_60rdmi, b), claim('US', 'pct_lt20_trials_within_60rdmi', us.pct_lt20_trials_within_60rdmi, b)]);
}
{ // 18. death rates in the counties of a district (scope = the district named in the where condition)
  const sc = await scenario('lung cancer death rate for TX-34', [{ name: 'find_places', input: { query: 'TX-34', kind: 'district' } }, { name: 'query', input: { table: 'counties', where: [{ field: 'districts', op: 'includes', value: 'TX-34' }, { field: 'mortality.by_site.lung', op: 'not_null' }], order_by: [{ field: 'mortality.by_site.lung', dir: 'desc' }], limit: 50, columns: ['mortality.by_site.lung'] } }]);
  const [, id] = sc.id; const r = sc.R[id]; const rows = r.rows.slice(0, 3);
  ok('death rates for the counties of a district', sc, `Death rates are published for counties, not for congressional districts, so there is no lung cancer death rate for Texas 34th. ${r.count} counties overlapping the district have a published rate (age-adjusted deaths per 100,000, 2020–2024): ${rows.map(x => `${x.name} ${x['mortality.by_site.lung']}`).join(', ')}.`, [claim('TX-34', 'count', r.count, id), ...rows.map(x => claim(x.id, 'mortality.by_site.lung', x['mortality.by_site.lung'], id))]);
}
{ // 19. trials in a state, all and of one type
  const sc = await scenario('How many breast cancer trials are recruiting in Ohio?', [{ name: 'trials', input: { scope: { state: 'OH' } } }, { name: 'trials', input: { scope: { state: 'OH' }, cancer_type: 'breast' } }]);
  const [a, b] = sc.id;
  ok('trials in a state, all and breast', sc, `Ohio has ${f(sc.R[a].count)} recruiting trials with a site in the state; ${sc.R[b].count} of them are breast cancer trials.`, [claim('OH', 'count', sc.R[a].count, a), claim('OH', 'count', sc.R[b].count, b)]);
}
{ // 20. the representative from a ZIP through the standard method (dependent steps)
  const sc = await scenario('Who is my representative? I live in 78501.', [{ name: 'method', input: { id: 'my_representative', params: { query: '78501' } } }]);
  const [id] = sc.id; const res = sc.R[id].results; const p = res[1].result; const [d1, d2] = p.related.districts;
  ok('method my_representative: names only, then one figure on the profile sub-call', sc, `ZIP 78501 is in ${p.name}, split between ${d1.name} (${d1.member}, ${d1.party}) and ${d2.name} (${d2.member}, ${d2.party}). ${p.row.pct_lt20_trials_within_60rdmi}% of the county's residents 55+ are short of trials.`, [claim('48215', 'pct_lt20_trials_within_60rdmi', p.row.pct_lt20_trials_within_60rdmi, res[1].call)]);
}
{ // 21. counties far from an NCI center, ranked, with drive hours
  const sc = await scenario('Which Nebraska counties are farthest from an NCI cancer center?', [{ name: 'query', input: { table: 'counties', where: [{ field: 'state', op: '=', value: 'NE' }], order_by: [{ field: 'road_mi_nci_from_center', dir: 'desc' }], limit: 3, columns: ['road_mi_nci_from_center', 'drive_hours_nci'] } }]);
  const [id] = sc.id; const rows = sc.R[id].rows;
  ok('ranking: road-miles and drive hours for three counties', sc, `${rows[0].name} is the farthest, ${rows[0].road_mi_nci_from_center} road-miles (${rows[0].drive_hours_nci} hours by road) from the nearest NCI-designated center; next are ${rows[1].name} at ${rows[1].road_mi_nci_from_center} road-miles and ${rows[2].name} at ${rows[2].road_mi_nci_from_center}.`, rows.flatMap(x => [claim(x.id, 'road_mi_nci_from_center', x.road_mi_nci_from_center, id), claim(x.id, 'drive_hours_nci', x.drive_hours_nci, id)]));
}
{ // 22. a district comparison where one figure belongs to each of two districts of one county
  const sc = await scenario('Compare Texas 15th and Texas 34th', [{ name: 'compare', input: { table: 'districts', ids: ['TX-15', 'TX-34'], columns: ['wmean_trials_within_60rdmi'] } }]);
  const [id] = sc.id; const r = sc.R[id]; const a = r.rows.find(x => x.id === 'TX-15'), b = r.rows.find(x => x.id === 'TX-34');
  const claims = [claim('TX-15', 'wmean_trials_within_60rdmi', a.wmean_trials_within_60rdmi, id), claim('TX-34', 'wmean_trials_within_60rdmi', b.wmean_trials_within_60rdmi, id), claim('TX-15', 'pop55', a.pop55, id), claim('TX-34', 'pop55', b.pop55, id)];
  ok('two districts compared (ids TX-15 / TX-34 written in the text)', sc, `Residents 55+ of Texas 15th (TX-15) have ${a.wmean_trials_within_60rdmi} recruiting trials within 60 road-miles on average, against ${b.wmean_trials_within_60rdmi} in Texas 34th; the districts have ${f(a.pop55)} and ${f(b.pop55)} residents 55+, respectively.`, claims);
  if (a.wmean_trials_within_60rdmi !== b.wmean_trials_within_60rdmi) bad('two districts: average trials swapped', sc, `Residents 55+ of Texas 15th have ${b.wmean_trials_within_60rdmi} recruiting trials within 60 road-miles on average, against ${a.wmean_trials_within_60rdmi} in Texas 34th.`, claims, 'Texas 15th');
}

// ======================= run them =======================
await test(`at least 20 realistic correct answers (${correct.length}) and 10 wrong attributions (${wrong.length}) are defined`, () => { assert(correct.length >= 20 && wrong.length >= 10, `${correct.length} / ${wrong.length}`); });
for (const c of correct) await test(`correct: ${c.name}`, () => { const r = run(c.sc, c.answer, c.claims); assert(r.ok, `rejected: ${JSON.stringify(r.issues)}\n     answer: ${c.answer}`); });
for (const w of wrong) await test(`wrong:   ${w.name}`, () => { const r = run(w.sc, w.answer, w.claims); assert(!r.ok, `accepted: ${w.answer}`); assert(r.issues.some(i => i.includes(w.expect)), `no issue names "${w.expect}": ${JSON.stringify(r.issues)}`); });

// ======================= units =======================
await test('resolvePath: dotted keys, nested rows, selectors, positions and lengths', () => {
  const o = { rows: [{ id: '48215', 'oncologists.count': 41, metro: { pct_lt20: 13.1 } }], groups: [{ group: false, n: 81, measures: { 'pct_lt20_trials_within_60rdmi:weighted_mean': 62.6, 'oncologists.count:sum': 5 } }, { group: null, n: 2 }], by_phase: { '3': 12, '1-2': 4 }, related: { senators: [{ name: 'John Cornyn', party: 'R' }] } };
  const cases = [['rows[0].oncologists.count', 41], ['rows[id=48215].metro.pct_lt20', 13.1], ['groups[group=false].measures.pct_lt20_trials_within_60rdmi:weighted_mean', 62.6], ['groups[group=false].measures.oncologists.count:sum', 5], ['groups[group=null].n', 2], ['by_phase.3', 12], ['by_phase.1-2', 4], ['related.senators[name=John Cornyn].party', 'R'], ['related.senators.length', 1], ['rows[id=1].x', undefined], ['nope', undefined]];
  for (const [p, want] of cases) { const got = resolvePath(o, p); assert(got === want, `${p}: ${got} != ${want}`); }
});
await test('the "Texas" inside "Hidalgo County, Texas" is not a separate mention; "Bexar, Texas" is not Texas', async () => {
  const sc = await scenario('Hidalgo County', [{ name: 'profile', input: { table: 'counties', id: '48215' } }]);
  const [id] = sc.id; const r = sc.R[id].row;
  const res = run(sc, `Hidalgo County, Texas has ${r.trials_listed_here} trials with a site in the county.`, [claim('48215', 'trials_listed_here', r.trials_listed_here, id)]); assert(res.ok, JSON.stringify(res.issues));
});

console.log(`\n${passed} passed, ${failed} failed${failed ? ': ' + failures.join('; ') : ''}`);
console.log(`false-rejection check: ${correct.filter(c => run(c.sc, c.answer, c.claims).ok).length}/${correct.length} realistic correct answers verified; ${wrong.filter(w => !run(w.sc, w.answer, w.claims).ok).length}/${wrong.length} wrong attributions rejected`);
process.exit(failed ? 1 : 0);
