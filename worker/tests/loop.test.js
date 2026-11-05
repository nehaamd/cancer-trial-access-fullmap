#!/usr/bin/env node
// Offline tests of the v3 worker (ASK_CONTRACT.md §8): the step protocol with a scripted fake model, signatures, caps, forced
// final, verification accept / reject cases with the internal retry, limits, prompt and tool-schema validity. No network.
//   node worker/tests/loop.test.js            (exits 1 on any failure)
// When docs/ask/engine.js is present, one end-to-end test runs the fake model's tool calls through the real engine on disk.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import * as catalog from '../../docs/ask/catalog.js';
import { step, validateBody, buildMessages, MAX_STEPS, MAX_RESULT_BYTES, MAX_CALLS_PER_TURN, FINAL_NOTE, StepError } from '../src/loop.js';
import { sign, verifySig, canonical, constantTimeEqual, secretFor, sha256hex } from '../src/sign.js';
import { verify, numbersIn, numberWordsIn, capitalisedTokens, buildContext } from '../src/verify.js';
import { systemPrompt, toolDefinitions, catalogPaths, EXAMPLES, TOOL_NAMES } from '../src/prompt.js';
import { handle, checkLimits, resetLimits, makeCallModel, MAX_BODY_BYTES } from '../src/index.js';

const HERE = path.dirname(fileURLToPath(import.meta.url)); const ROOT = path.resolve(HERE, '..', '..');
let passed = 0, failed = 0; const failures = [];
async function test(name, fn) { try { await fn(); passed++; console.log(`ok   ${name}`); } catch (e) { failed++; failures.push(name); console.log(`FAIL ${name}\n     ${String(e && e.stack || e).split('\n').slice(0, 4).join('\n     ')}`); } }
const assert = (c, msg) => { if (!c) throw new Error(msg || 'assertion failed'); };
const eq = (a, b, msg) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${msg || 'not equal'}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); };
const includes = (arr, sub) => arr.some(s => String(s).includes(sub));
async function rejects(p, status, text) { try { await p; } catch (e) { if (status && e.status !== status) throw new Error(`expected status ${status}, got ${e.status}: ${e.message}`); if (text && !String(e.message).includes(text)) throw new Error(`expected "${text}" in "${e.message}"`); return e; } throw new Error('expected a rejection'); }

const ENV = { ANTHROPIC_API_KEY: 'sk-ant-test-key', MODEL: 'claude-sonnet-5-5', PER_MINUTE: '3', DAILY_CAP: '5', ALLOWED_ORIGINS: 'https://nehaamd.github.io,http://localhost:8080', SITE_BASE: 'https://example.test/' };
const SECRET = await secretFor(ENV);
let ids = 0; const tid = () => `toolu_${String(++ids).padStart(4, '0')}`;
const tu = (name, input, id = tid()) => ({ type: 'tool_use', id, name, input });
const txt = text => ({ type: 'text', text });

// a scripted model: each call pops the next canned reply; records every payload it was sent
function fakeModel(replies) {
  const calls = [];
  const fn = async payload => { calls.push(payload); if (!replies.length) throw new Error('fake model: no reply left'); const r = replies.shift(); const content = typeof r === 'function' ? r(payload) : r; return { content, stop_reason: 'tool_use', usage: { input_tokens: 100, output_tokens: 20, cache_read_input_tokens: 90 }, model: payload.model }; };
  fn.calls = calls; return fn;
}
// a client: runs the protocol to the end, executing tool calls with `exec(name, input) -> result object`
async function drive(q, model, exec, { prior, maxSteps = 12, env = ENV } = {}) {
  const turns = []; const responses = [];
  for (let i = 0; i < maxSteps; i++) {
    const r = await step({ v: 3, q, turns, prior }, env, model); responses.push(r);
    if (r.kind === 'answer') return { r, turns, responses };
    const results = [];
    for (const c of r.calls) { const out = c.name === 'final_answer' ? { ok: true, note: FINAL_NOTE } : await exec(c.name, c.input, c.id); results.push({ tool_use_id: c.id, content: typeof out === 'string' ? out : JSON.stringify(out), is_error: !!(out && out.error) }); }
    turns.push({ assistant: r.assistant, sig: r.sig, results });
  }
  throw new Error('drive: no answer after ' + maxSteps + ' steps');
}
const otherModel = () => fakeModel([[tu('final_answer', { answer: catalog.OTHER_TEXT, answerable: 'no', interpretation: 'Not a question about the map\'s data.', not_in_data: ['Not data.'] })]]);
// canned engine results
const COUNTY_ROWS = { table: 'counties', count: 38, in_scope: 254, returned: 3, columns: ['id', 'name', 'state', 'pop55', 'oncologists.count', 'trials_listed_here'], rows: [{ id: '48215', name: 'Hidalgo County, Texas', state: 'TX', pop55: 182206, 'oncologists.count': 41, 'trials_listed_here': 0 }, { id: '48479', name: 'Webb County, Texas', state: 'TX', pop55: 52310, 'oncologists.count': 12, 'trials_listed_here': 0 }, { id: '48061', name: 'Cameron County, Texas', state: 'TX', pop55: 98765, 'oncologists.count': 17, 'trials_listed_here': 0 }], nulls: {}, ids_truncated: false, sum_pop55_matching: 1180232, source: { file: 'api/all_counties.json', url: 'https://example.test/api/all_counties.json', as_of: '2026-11-03' } };
const DISTRICT_ROWS = { table: 'districts', count: 9, in_scope: 38, returned: 2, columns: ['id', 'name', 'state', 'pop55', 'oncologists.pct_pop55_in_counties_with_oncologists_no_trials'], rows: [{ id: 'TX-34', name: 'Texas 34th', state: 'TX', pop55: 201345, 'oncologists.pct_pop55_in_counties_with_oncologists_no_trials': 38.2 }, { id: 'TX-15', name: 'Texas 15th', state: 'TX', pop55: 190001, 'oncologists.pct_pop55_in_counties_with_oncologists_no_trials': 21.7 }], nulls: {}, ids_truncated: false, sum_pop55_matching: 1400000, source: { file: 'api/all_districts.json', url: '', as_of: '2026-11-03' } };
const exec = (name, input) => name === 'query' && input.table === 'districts' ? DISTRICT_ROWS : name === 'query' ? COUNTY_ROWS : name === 'find_places' ? { matches: [{ id: '48215', table: 'counties', kind: 'county', name: 'Hidalgo County, Texas', state: 'TX', pop55: 182206, how: 'exact' }], ambiguous: false } : { ok: true };
const GOOD = { answer: '38 of 254 Texas counties have at least one oncologist but no recruiting trial with a site in the county; 1,180,232 residents 55+ live in them. The largest are Hidalgo County, Texas (182,206 residents 55+, 41 oncologists), Cameron County, Texas (98,765, 17) and Webb County, Texas (52,310, 12). 9 Texas districts contain such counties; the largest share is Texas 34th at 38.2%.', answerable: 'yes', interpretation: 'Counties in Texas in oncologists-vs-trials class 2 (oncologists.class = 2).', alternatives: ['Which Texas counties have oncologists but no trial within 60 road-miles?'], not_in_data: [], caveats: ['An oncologist with practice locations in two counties is counted in both.'], map: { unit: 'county', layer: 'onc', params: {}, state: 'TX', highlight: { from_call: 'FIRST' }, highlight_label: 'Texas counties with oncologists but no recruiting trial' }, table: { from_call: 'FIRST' }, sources: ['counties', 'districts'], follow_ups: ['Which of these counties are rural?'] };
// the figures of GOOD as claims (ASK_CONTRACT §6 rule 6): FIRST = the county query, SECOND = the district query
GOOD.claims = [{ place: 'TX', field: 'count', value: 38, call: 'FIRST' }, { place: 'TX', field: 'in_scope', value: 254, call: 'FIRST' }, { place: 'TX', field: 'sum_pop55_matching', value: 1180232, call: 'FIRST' },
  { place: '48215', field: 'pop55', value: 182206, call: 'FIRST' }, { place: '48215', field: 'oncologists.count', value: 41, call: 'FIRST' }, { place: '48061', field: 'pop55', value: 98765, call: 'FIRST' }, { place: '48061', field: 'oncologists.count', value: 17, call: 'FIRST' },
  { place: '48479', field: 'pop55', value: 52310, call: 'FIRST' }, { place: '48479', field: 'oncologists.count', value: 12, call: 'FIRST' }, { place: 'TX', field: 'count', value: 9, call: 'SECOND' }, { place: 'TX-34', field: 'oncologists.pct_pop55_in_counties_with_oncologists_no_trials', value: 38.2, call: 'SECOND' }];
const withCall = (a, id, id2 = 'SECOND') => JSON.parse(JSON.stringify(a).replace(/"FIRST"/g, JSON.stringify(id)).replace(/"SECOND"/g, JSON.stringify(id2)));
const Q = 'which counties and districts in texas have oncologists but no access to clinical trials?';
// the canonical script: two queries in turn 1, then a final whose from_call is the county query
function canonicalScript(finalInput = GOOD, { extraFinals = [] } = {}) {
  const qid = tid(), did = tid();
  return fakeModel([[tu('query', { table: 'counties', where: [{ field: 'state', op: '=', value: 'TX' }, { field: 'oncologists.class', op: '=', value: 2 }] }, qid), tu('query', { table: 'districts', where: [{ field: 'state', op: '=', value: 'TX' }] }, did)], [tu('final_answer', withCall(finalInput, qid, did))], ...extraFinals.map(f => [tu('final_answer', withCall(f, qid, did))])]);
}

// ---------- sign.js ----------
await test('sign: canonical JSON is key-order independent and signatures round-trip', async () => {
  const a = [{ type: 'tool_use', id: 'toolu_1', name: 'query', input: { table: 'counties', where: [{ field: 'state', op: '=', value: 'TX' }] } }];
  const b = [{ input: { where: [{ value: 'TX', op: '=', field: 'state' }], table: 'counties' }, name: 'query', id: 'toolu_1', type: 'tool_use' }];
  eq(canonical(a), canonical(b), 'canonical differs');
  const sig = await sign(a, SECRET); assert(/^[0-9a-f]{64}$/.test(sig), 'hex sig');
  assert(await verifySig(b, sig, SECRET), 'reordered keys must verify');
  assert(!(await verifySig(a, sig, SECRET + 'x')), 'other secret must fail');
  assert(!(await verifySig(a, 'zz', SECRET)), 'malformed sig must fail');
  assert(constantTimeEqual('abc', 'abc') && !constantTimeEqual('abc', 'abd') && !constantTimeEqual('abc', 'ab'), 'constant-time compare');
});
await test('sign: secret is ASK_SIGNING_SECRET or the SHA-256 of the API key, never the key itself', async () => {
  eq(await secretFor({ ASK_SIGNING_SECRET: 'abc', ANTHROPIC_API_KEY: 'k' }), 'abc');
  const s = await secretFor({ ANTHROPIC_API_KEY: 'k' }); eq(s, await sha256hex('k')); assert(s !== 'k');
  await rejects(secretFor({}), undefined, 'neither');
});

// ---------- prompt.js ----------
await test('prompt: the system prompt has every required section in order and the fixed texts verbatim', () => {
  const p = systemPrompt(catalog);
  const order = ['OUT OF SCOPE', 'SCOPE_TEXT: ' + catalog.SCOPE_TEXT, 'OTHER_TEXT: ' + catalog.OTHER_TEXT, 'HOW TO WORK', 'INTERPRETATION RULES', 'WRITING THE ANSWER', 'THE MAP', 'TABLES.', 'DEFINITIONS', 'NOT IN THE DATA', 'MAP LAYERS', 'ENUMERATIONS', 'DATA VINTAGES', 'WORKED EXAMPLES', 'Example 3'];
  let pos = p.indexOf('HOW TO WORK') - 1; for (const s of order) { const i = p.indexOf(s, s.startsWith('OUT OF SCOPE') || s.startsWith('SCOPE_TEXT') || s.startsWith('OTHER_TEXT') ? 0 : pos); assert(i > (s.startsWith('OUT OF SCOPE') || s.startsWith('SCOPE_TEXT') || s.startsWith('OTHER_TEXT') ? -1 : pos), `section "${s}" missing or out of order`); if (!(s.startsWith('OUT OF SCOPE') || s.startsWith('SCOPE_TEXT') || s.startsWith('OTHER_TEXT'))) pos = i; }
  for (const s of catalog.NOT_IN_DATA) assert(p.includes(s), 'NOT_IN_DATA entry missing: ' + s.slice(0, 40));
  for (const k of Object.keys(catalog.DEFINITIONS)) assert(p.includes(`  ${k}: `), 'definition missing: ' + k);
  for (const k of Object.keys(catalog.STATES)) assert(p.includes(' ' + k), 'state missing ' + k);
  assert(p.includes(EXAMPLES[0].q), 'canonical example missing');
  const tokens = Math.round(p.length / 4); assert(tokens > 5000 && tokens < 16000, 'prompt size out of range: ' + tokens);
});
await test('prompt: every field path rendered in the catalog section exists in the catalog', () => {
  const paths = catalogPaths(catalog); assert(paths.length > 150, 'too few paths: ' + paths.length);
  for (const { table, path: pth } of paths) assert(catalog.fieldFor(table, pth.replace(/<[a-z]+>/g, m => ({ '<site>': 'lung', '<type>': 'breast', '<code>': '1', '<measure>': 'pct_lt20', '<class>': '1' }[m]))), `path ${pth} not in ${table}`);
  const text = systemPrompt(catalog);
  for (const t of Object.keys(catalog.TABLES)) for (const fd of catalog.TABLES[t].fields) if (!/^(metro|nonmetro)\./.test(fd.path)) assert(text.includes(fd.path), `field ${fd.path} of ${t} not rendered`);
});
await test('prompt: the worked examples use only real tables, fields, ops, layers and params', () => {
  const ops = toolDefinitions(catalog).find(t => t.name === 'query').input_schema.properties.where.items.anyOf[0].properties.op.enum;
  for (const ex of EXAMPLES) for (const t of ex.turns) for (const c of t.calls) {
    assert(TOOL_NAMES.includes(c.name), 'tool ' + c.name);
    if (c.name === 'query' || c.name === 'aggregate') { assert(catalog.TABLES[c.input.table], 'table ' + c.input.table); for (const w of c.input.where || []) { assert(ops.includes(w.op), 'op ' + w.op); assert(catalog.fieldFor(c.input.table, w.field), `field ${w.field} in ${c.input.table}`); } for (const o of c.input.order_by || []) assert(catalog.fieldFor(c.input.table, o.field), 'order field ' + o.field); for (const col of c.input.columns || []) assert(catalog.fieldFor(c.input.table, col), 'column ' + col); }
    if (c.name === 'site_info') assert(catalog.SITE_INFO[c.input.topic], 'topic');
    if (c.name === 'final_answer') { const m = c.input.map; if (m) { assert(catalog.MAP_LAYERS[m.unit] && catalog.MAP_LAYERS[m.unit][m.layer], `layer ${m.layer} for ${m.unit}`); for (const [k, v] of Object.entries(m.params || {})) { assert(catalog.MAP_LAYERS[m.unit][m.layer].params.includes(k), `param ${k} on ${m.layer}`); assert(catalog.MAP_PARAMS[k].includes(v), `param value ${v}`); } } for (const s of c.input.sources || []) assert(catalog.TABLES[s] || s === 'trials' || s === 'site_info', 'source ' + s); }
  }
});
await test('prompt: tool schemas are valid JSON-schema objects with tight enums and additionalProperties:false', () => {
  const tools = toolDefinitions(catalog); eq(tools.map(t => t.name), TOOL_NAMES);
  const walk = (s, where) => { assert(s && typeof s === 'object', where + ' not an object'); if (s.anyOf) { s.anyOf.forEach((x, i) => walk(x, `${where}.anyOf[${i}]`)); return; } if (s.type === 'object') { assert(s.properties, where + ' no properties'); assert(s.additionalProperties === false, where + ' must set additionalProperties:false'); for (const r of s.required || []) assert(s.properties[r], `${where}.required ${r} not a property`); for (const [k, v] of Object.entries(s.properties)) walk(v, `${where}.${k}`); } else if (s.type === 'array') { assert(s.items, where + ' array without items'); walk(s.items, where + '[]'); } if (s.enum) { assert(Array.isArray(s.enum) && s.enum.length > 0 && new Set(s.enum).size === s.enum.length, where + ' bad enum'); } };
  for (const t of tools) { assert(/^[a-z_]+$/.test(t.name) && t.description && t.input_schema && t.input_schema.type === 'object', 'tool shape ' + t.name); walk(t.input_schema, t.name); JSON.parse(JSON.stringify(t)); }
  eq(tools[tools.length - 1].cache_control, { type: 'ephemeral' }, 'last tool carries cache_control'); assert(!tools[0].cache_control, 'only the last tool');
  const q = tools.find(t => t.name === 'query').input_schema; eq(q.properties.table.enum, Object.keys(catalog.TABLES));
  const fa = tools.find(t => t.name === 'final_answer').input_schema; eq(fa.properties.answerable.enum, ['yes', 'partly', 'no']); eq(fa.properties.map.properties.unit.enum, ['county', 'district', 'state']);
  for (const u of ['county', 'district', 'state']) for (const k of Object.keys(catalog.MAP_LAYERS[u])) assert(fa.properties.map.properties.layer.enum.includes(k), 'layer ' + k);
  for (const [k, vals] of Object.entries(catalog.MAP_PARAMS)) eq(fa.properties.map.properties.params.properties[k].enum, vals, 'param ' + k);
  eq(tools.find(t => t.name === 'site_info').input_schema.properties.topic.enum, Object.keys(catalog.SITE_INFO));
  eq(tools.find(t => t.name === 'trials').input_schema.properties.phase.enum, catalog.PHASES);
  eq(tools.find(t => t.name === 'find_places').input_schema.properties.kind.enum, ['county', 'district', 'state', 'zip', 'town', 'member', 'senator', 'nci_center']);
  const ag = tools.find(t => t.name === 'aggregate').input_schema; eq(ag.properties.measures.items.properties.stat.enum, ['count', 'count_not_null', 'sum', 'mean', 'weighted_mean', 'median', 'min', 'max', 'share_true', 'share_eq']);
  for (const g of ag.properties.group_by.enum) assert(Object.keys(catalog.TABLES).some(t => catalog.groupableFields(t).includes(g)), 'groupable ' + g);
});

// ---------- verify.js units ----------
await test('verify: number extraction handles separators, decimals, money, phones, NCT ids, ordinals, years, negatives, k/million', () => {
  const n = numbersIn('1,234,567 residents; 11.8 million; $2,000; 1-800-4-CANCER; 1-800-227-2345; NCT01234567; 38.2%; -3; the 3rd and the 34th; in 2024; TX-34; 55+; per 100,000; 5k; 2019–2023; 2020-2024; H.R. 3521');
  eq(n.map(x => x.raw), ['1,234,567', '11.8 million', '$2,000', '38.2%', '-3', '2024', '55', '100,000', '5k', '2019', '2023', '2020', '2024', '3521']);
  eq(n.find(x => x.raw === '11.8 million').value, 11800000); eq(n.find(x => x.raw === '11.8 million').sig, 3); eq(n.find(x => x.raw === '5k').value, 5000); eq(n.find(x => x.raw === '-3').value, -3);
  eq(numberWordsIn('twenty counties, a million people, two hundred, eleven, half of them, twenty-three').map(x => x.value), [20, 1000000, 200, 11, 23]);
  eq(numberWordsIn('11.8 million people and 2 thousand').length, 0, 'words after digits are multipliers, not words');
  eq(capitalisedTokens('Hidalgo County, Texas has the most. St. Louis City and Miami-Dade County; NCI-designated centers.'), ['Hidalgo', 'County', 'Texas', 'Louis', 'City', 'Miami-Dade', 'County', 'NCI-designated']);
});
const ctxOf = (turns, question = Q) => buildContext({ question, turns, catalog });
const TX_ONLY = [{ field: 'state', op: '=', value: 'TX' }];
const TURNS = [{ assistant: [tu('query', { table: 'counties', where: TX_ONLY }, 'toolu_c'), tu('query', { table: 'districts', where: TX_ONLY }, 'toolu_d')], results: [{ tool_use_id: 'toolu_c', content: JSON.stringify(COUNTY_ROWS) }, { tool_use_id: 'toolu_d', content: JSON.stringify(DISTRICT_ROWS) }] }];
const good = withCall(GOOD, 'toolu_c', 'toolu_d');
await test('verify: the good answer passes; every §6 rule rejects with a specific message', () => {
  eq(verify(good, ctxOf(TURNS)), { ok: true, issues: [] });
  const bad = (patch, sub) => { const r = verify({ ...good, ...patch }, ctxOf(TURNS)); assert(!r.ok, 'should fail: ' + sub); assert(includes(r.issues, sub), `expected "${sub}" in ${JSON.stringify(r.issues)}`); return r; };
  bad({ answer: good.answer.replace('38 of 254', '39 of 254') }, 'number 39');                                            // invented
  bad({ answer: good.answer.replace('38.2%', '38.7%') }, 'closest: 38.2');                                                 // invented decimal, closest named
  bad({ answer: good.answer.replace('Hidalgo County, Texas', 'Starr County, Texas') }, '"Starr"');                       // re-attributed place
  { const noHidalgo = JSON.parse(JSON.stringify(TURNS)); noHidalgo[0].results[0].content = noHidalgo[0].results[0].content.replace(/Hidalgo/g, 'Starr'); const r = verify({ ...good, answer: good.answer.replace('Cameron County, Texas (98,765, 17) and Webb County, Texas (52,310, 12)', 'Starr County, Texas (98,765, 17)') }, ctxOf(noHidalgo)); assert(!r.ok && includes(r.issues, '"Hidalgo"'), 'a name that only appears as an example in the catalog is not vocabulary: ' + JSON.stringify(r.issues)); }
  bad({ map: { ...good.map, highlight: { ids: ['48215', '48999'] } } }, '48999');                                          // unknown id
  bad({ map: { ...good.map, layer: 'l20' } }, 'map.layer "l20" is not a county layer');                                   // bad layer
  bad({ map: { ...good.map, params: { site: 'lung' } } }, 'map.params.site is not accepted by layer onc');               // param not for layer
  bad({ map: { ...good.map, layer: 'inc', params: { site: 'liver' } } }, 'map.params.site = "liver"');                   // bad param value
  bad({ map: { ...good.map, state: 'ZZ' } }, 'map.state');
  bad({ map: { ...good.map, place: '48999' } }, 'map.place');
  bad({ map: { ...good.map, highlight: { from_call: 'toolu_nope' } } }, 'map.highlight.from_call');                       // unknown call
  bad({ table: { from_call: 'toolu_c' }, map: { ...good.map, highlight: { from_call: 'toolu_c' } }, sources: ['nowhere'] }, 'sources entry');
  bad({ answer: '**38** of 254 Texas counties.' }, 'markdown');
  bad({ answer: '38 of 254 Texas counties. See https://example.com for more.' }, 'URL');
  bad({ answer: '38 of 254 Texas counties. Patients should consult their oncologist.' }, 'advice');
  bad({ answer: '38 of 254 Texas counties. These trials are available to you.' }, 'available to');
  bad({ answer: 'I found 38 of 254 Texas counties.' }, 'first person');
  bad({ answerable: 'no', not_in_data: [] }, 'answerable "no" requires not_in_data');
  bad({ answerable: 'maybe' }, 'answerable must be');
  bad({ interpretation: '' }, 'interpretation is required');
  bad({ caveats: ['a', 'b', 'c', 'd', 'e', 'f'] }, 'caveats has 6');
  bad({ answer: good.answer + ' Thousands more are affected.' }, 'vague quantity');
  bad({ answer: good.answer + ' Twenty-seven of them are rural.' }, 'number Twenty-seven');
  bad({ caveats: ['Only 14 of 38 counties are shown.'] }, 'number 14 in caveats');
  bad({ answer: good.answer + ' TX-99 is also affected.' }, 'district id TX-99');
});
await test('verify: rounding, million form, question numbers, constants, vintages and number words one–ten are accepted', () => {
  const ok = (answer, question) => { const r = verify({ ...good, answer }, ctxOf(TURNS, question)); assert(r.ok, `${answer} -> ${JSON.stringify(r.issues)}`); };
  ok('About 1.2 million residents 55+ live in the 38 counties.');                 // 1,180,232 -> 1.2 million (2 sig)
  ok('About 1.18 million residents 55+ live in the 38 counties.');                // 3 sig
  ok('1,180,000 residents 55+ live in the 38 counties, led by Hidalgo County, Texas; Texas 34th is at 38%.');   // 38.2 -> 38
  ok('Texas 34th has 38.2% of residents 55+ in such counties; Hidalgo County, Texas has about 180,000 residents 55+.');   // 182,206 -> 180,000 (2 sig)
  ok('Of the 254 counties, 38 match; the data covers residents 55+ within 60 road-miles and trials of 100 or more.');     // constants
  ok('Incidence rates cover 2019–2023 and death rates 2020–2024; the registry pull was 2026-11-03.');                     // vintages + result date
  ok('Three of the top five counties are on the border; 38 counties match in all.', 'top 5 counties in texas with oncologists but no trials');   // small words, question numbers
  ok('The 20 counties you asked about: 38 match.', 'which 20 texas counties have oncologists but no trials');
  const r = verify({ ...good, answer: '1.3 million residents 55+ live in the 38 counties.' }, ctxOf(TURNS)); assert(!r.ok && includes(r.issues, 'number 1.3 million'), 'wrong rounding must fail');
  const r2 = verify({ ...good, answer: 'About 40 of 254 Texas counties match.' }, ctxOf(TURNS)); assert(!r2.ok, '1-significant-digit rounding (40 for 38) is not accepted');
  // trailing zeros are ambiguous: a round figure is accepted when it is the result rounded to 2 or more digits
  const nat = [{ assistant: [tu('profile', { table: 'national', id: 'US' }, 'toolu_n')], results: [{ tool_use_id: 'toolu_n', content: JSON.stringify({ row: { pop55: 100019672, people_lt20_trials_within_60rdmi: 11802321, pct_lt20_trials_within_60rdmi: 11.8, people_zero_trials_within_60rdmi: 4300846, trials_listed_here: 4035, x: 19876 } }) }] }];
  const natClaims = Object.entries(JSON.parse(nat[0].results[0].content).row).map(([k, v]) => ({ place: 'US', field: 'row.' + k, value: v, call: 'toolu_n' }));
  const okN = (answer, q = 'how many people') => { const r = verify({ ...good, map: undefined, table: undefined, claims: natClaims, answer }, ctxOf(nat, q)); assert(r.ok, `${answer} -> ${JSON.stringify(r.issues)}`); };
  okN('The data covers 100 million residents 55+.'); okN('About 12 million residents 55+ are short of trials.'); okN('About 20,000 live there.'); okN('4,300,000 have none within 60 road-miles.'); okN('4,035 trials, roughly 4,000 trials.');
  okN('Residents aged 55–64 are a separate ACS band; the data has 3,143 counties and 436 districts.');                     // 64, 3,143 and 436 are constants
  okN('Fifteen thousand people, give or take, is not what the data says; it says twelve million are short of trials.', 'does fifteen thousand people sound right');   // question words
  for (const [a, sub] of [['About 100.5 million residents 55+.', 'number 100.5 million'], ['About 4,400,000 have none.', 'number 4,400,000'], ['About 13 million are short.', 'number 13 million'], ['Fifteen hundred trials are listed.', 'number Fifteen hundred'], ['Three thousand trials are listed.', 'number Three thousand'], ['Thirteen trials.', 'number Thirteen'], ['Half a million people.', 'number Half a million'], ['Several hundred trials.', 'vague quantity']]) {
    const r = verify({ ...good, map: undefined, table: undefined, claims: natClaims, answer: a }, ctxOf(nat, 'how many people')); assert(!r.ok && includes(r.issues, sub), `${a} should fail with "${sub}": ${JSON.stringify(r.issues)}`);
  }
});
await test('verify: style catches unicode bullets, bare domains, "dot com" and advice synonyms; common sentence starters pass', () => {
  const bad = (answer, sub) => { const r = verify({ ...good, answer }, ctxOf(TURNS)); assert(!r.ok && includes(r.issues, sub), `${answer} should fail with "${sub}": ${JSON.stringify(r.issues)}`); };
  bad('38 of 254 Texas counties:\n– Hidalgo County, Texas\n– Webb County, Texas', 'markdown'); bad('38 counties.\n‣ Hidalgo County, Texas', 'markdown'); bad('Hidalgo County, Texas is *fully* short of trials.', 'markdown');
  bad('38 of 254 Texas counties; see example.com for more.', 'URL'); bad('38 of 254 Texas counties; see example dot com.', 'URL'); bad('38 of 254 Texas counties; see nehaamd.github.io.', 'URL');
  bad('38 of 254 Texas counties. It is advisable to talk to a doctor.', 'advice'); bad('38 of 254 Texas counties. Patients ought to speak with a doctor.', 'advice'); bad('38 of 254 Texas counties. It would be wise to check with your oncologist.', 'advice');
  const ok = answer => { const r = verify({ ...good, answer }, ctxOf(TURNS)); assert(r.ok, `${answer} -> ${JSON.stringify(r.issues)}`); };
  ok('Therefore 38 of 254 Texas counties match. Currently 9 districts contain such counties. Counting only those, Hidalgo County, Texas leads. Approximately 38% of Texas 34th lives in them. Ovarian cancer is a type key, as listed on ClinicalTrials.gov and refreshed from congress.gov.');
});
await test('verify: SCOPE_TEXT and OTHER_TEXT answers pass with answerable "no" and a not_in_data sentence', () => {
  eq(verify({ answer: catalog.SCOPE_TEXT, answerable: 'no', interpretation: 'Out of scope: a question about a person\'s care.', not_in_data: ['The data lists trials; it does not match people to them.'] }, ctxOf([], 'which trial is right for my mother with stage 3 lung cancer?')), { ok: true, issues: [] });
  eq(verify({ answer: catalog.OTHER_TEXT, answerable: 'no', interpretation: 'Not a question about the map\'s data.', not_in_data: ['Jokes are not in the data.'] }, ctxOf([], 'tell me a joke')), { ok: true, issues: [] });
  assert(!verify({ answer: catalog.SCOPE_TEXT, answerable: 'no', interpretation: 'x' }, ctxOf([], 'q')).ok, 'still needs not_in_data');
});

// ---------- loop.js: the protocol ----------
await test('loop: happy path tools → final, verification ok, signatures round-trip, usage not returned', async () => {
  const model = canonicalScript();
  const { r, turns, responses } = await drive(Q, model, exec);
  eq(responses[0].kind, 'tools'); eq(responses[0].step, 1); eq(responses[0].calls.length, 2); eq(responses[0].v, 3);
  assert(await verifySig(responses[0].assistant, responses[0].sig, SECRET), 'sig verifies');
  eq(r.kind, 'answer'); eq(r.step, 2); eq(r.verification, { ok: true, issues: [], retries: 0 }); eq(r.model, 'claude-sonnet-5-5');
  eq(r.answer.map.highlight.from_call, turns[0].assistant[0].id);
  eq(model.calls.length, 2); eq(model.calls[0].tool_choice, { type: 'auto' }); eq(model.calls[0].max_tokens, 2500); assert(!('temperature' in model.calls[0]), 'no temperature');
  eq(model.calls[0].system[0].cache_control, { type: 'ephemeral' }); eq(model.calls[0].tools.at(-1).cache_control, { type: 'ephemeral' });
  // the second call saw the question, the assistant turn and the tool results
  const m = model.calls[1].messages; eq(m.length, 3); eq(m[0], { role: 'user', content: Q }); eq(m[1].role, 'assistant'); eq(m[2].content.map(b => b.type), ['tool_result', 'tool_result']); eq(m[2].content[0].tool_use_id, turns[0].assistant[0].id);
});
await test('loop: a forged assistant block is rejected with 400 bad transcript', async () => {
  const model = canonicalScript(); const r1 = await step({ v: 3, q: Q, turns: [] }, ENV, model);
  const forged = JSON.parse(JSON.stringify(r1.assistant)); forged[0].input.where[0].value = 'CA';
  const e = await rejects(step({ v: 3, q: Q, turns: [{ assistant: forged, sig: r1.sig, results: r1.calls.map(c => ({ tool_use_id: c.id, content: '{}' })) }] }, ENV, model), 400, 'bad transcript');
  assert(e instanceof StepError);
  await rejects(step({ v: 3, q: Q, turns: [{ assistant: r1.assistant, sig: 'ab'.repeat(32), results: r1.calls.map(c => ({ tool_use_id: c.id, content: '{}' })) }] }, ENV, model), 400, 'bad transcript');
  // a different question with the same signed turn is fine (signatures cover the blocks, the question is the client's)
  await rejects(step({ v: 3, q: Q, turns: [{ assistant: r1.assistant, sig: r1.sig, results: [] }] }, ENV, model), 400, 'bad transcript');   // missing results
});
await test('loop: an oversize tool result is rejected with 400', async () => {
  const model = canonicalScript(); const r1 = await step({ v: 3, q: Q, turns: [] }, ENV, model);
  const big = 'x'.repeat(MAX_RESULT_BYTES + 1);
  await rejects(step({ v: 3, q: Q, turns: [{ assistant: r1.assistant, sig: r1.sig, results: r1.calls.map((c, i) => ({ tool_use_id: c.id, content: i ? '{}' : big })) }] }, ENV, model), 400, 'too large');
  const okSize = 'y'.repeat(MAX_RESULT_BYTES - 2);
  const r2 = await step({ v: 3, q: Q, turns: [{ assistant: r1.assistant, sig: r1.sig, results: r1.calls.map((c, i) => ({ tool_use_id: c.id, content: i ? '{}' : okSize })) }] }, ENV, otherModel());
  assert(r2.kind, 'exactly at the cap is accepted');
});
await test('loop: a turn with more than 8 tool calls is rejected with 400, even when correctly signed', async () => {
  const blocks = Array.from({ length: MAX_CALLS_PER_TURN + 1 }, () => tu('query', { table: 'states' }));
  const sig = await sign(blocks, SECRET);
  await rejects(step({ v: 3, q: Q, turns: [{ assistant: blocks, sig, results: blocks.map(b => ({ tool_use_id: b.id, content: '{}' })) }] }, ENV, fakeModel([])), 400, 'bad transcript');
  const eight = blocks.slice(0, MAX_CALLS_PER_TURN); const sig8 = await sign(eight, SECRET);
  const r = await step({ v: 3, q: Q, turns: [{ assistant: eight, sig: sig8, results: eight.map(b => ({ tool_use_id: b.id, content: '{"count":51}' })) }] }, ENV, fakeModel([[tu('final_answer', { answer: 'There are 51 states in the data.', answerable: 'yes', interpretation: 'x' })]]));
  eq(r.kind, 'answer'); eq(r.verification.ok, true);
});
await test('loop: when the model itself returns more than 8 calls it is told so and retried', async () => {
  const many = Array.from({ length: 9 }, () => tu('query', { table: 'states' }));
  const model = fakeModel([many, [tu('query', { table: 'states' })]]);
  const r = await step({ v: 3, q: Q, turns: [] }, ENV, model);
  eq(r.kind, 'tools'); eq(r.calls.length, 1);
  const m = model.calls[1].messages; eq(m[2].content.length, 9); assert(m[2].content.every(b => b.is_error && b.content.includes('Too many tool calls')), 'errors for every call');
});
await test('loop: body validation (q length, protocol version, prior, result bookkeeping)', async () => {
  await rejects(step({ v: 3, q: 'hi', turns: [] }, ENV, fakeModel([])), 400, 'few words');
  await rejects(step({ v: 3, q: 'x'.repeat(401), turns: [] }, ENV, fakeModel([])), 400, 'too long');
  await rejects(step({ v: 2, q: 'how many counties', turns: [] }, ENV, fakeModel([])), 400, 'protocol version');
  await rejects(step(null, ENV, fakeModel([])), 400, 'not understood');
  await rejects(step({ v: 3, q: Q, turns: 'nope' }, ENV, fakeModel([])), 400, 'bad transcript');
  await rejects(step({ v: 3, q: Q, turns: Array.from({ length: 9 }, () => ({ assistant: [], sig: '', results: [] })) }, ENV, fakeModel([])), 400, 'bad transcript');
  const model = canonicalScript(); const r1 = await step({ v: 3, q: Q, turns: [] }, ENV, model);
  const dup = [{ tool_use_id: r1.calls[0].id, content: '{}' }, { tool_use_id: r1.calls[0].id, content: '{}' }];
  await rejects(step({ v: 3, q: Q, turns: [{ assistant: r1.assistant, sig: r1.sig, results: dup }] }, ENV, model), 400, 'bad transcript');
  await rejects(step({ v: 3, q: Q, turns: [{ assistant: r1.assistant, sig: r1.sig, results: r1.calls.map(c => ({ tool_use_id: c.id, content: { not: 'a string' } })) }] }, ENV, model), 400, 'bad transcript');
  const v = validateBody({ q: '  how   many counties  ', prior: [{ q: 'a', answer: 'b' }, { q: '', answer: 'x' }, { q: 'c', answer: 'd' }, { q: 'e', answer: 'f' }, { q: 'g', answer: 'h' }], client: { page: 'map', unit: 'county' } });
  eq(v.q, 'how many counties'); eq(v.prior.length, 3); eq(v.prior[0].q, 'c'); eq(v.client, { page: 'map', unit: 'county' });
});
await test('loop: MAX_STEPS forces final_answer with a user instruction (tool_choice stays auto: current models reject any/tool)', async () => {
  // seven signed earlier turns, each one query with an empty result
  const turns = [];
  for (let i = 0; i < MAX_STEPS - 1; i++) { const b = [tu('query', { table: 'states' })]; turns.push({ assistant: b, sig: await sign(b, SECRET), results: [{ tool_use_id: b[0].id, content: JSON.stringify({ count: 51 }) }] }); }
  const model = fakeModel([p => { eq(p.tool_choice, { type: 'auto' }, 'auto'); assert(JSON.stringify(p.messages[p.messages.length - 1]).includes('Call final_answer now'), 'forced final in words'); return [tu('final_answer', { answer: 'The data covers 51 states.', answerable: 'partly', interpretation: 'x' })]; }]);
  const r = await step({ v: 3, q: Q, turns }, ENV, model);
  eq(r.kind, 'answer'); eq(r.step, MAX_STEPS); eq(r.verification.ok, true);
  // at step 7 it is still free to call tools; env.MAX_STEPS overrides
  const model2 = fakeModel([p => { eq(p.tool_choice, { type: 'auto' }); assert(!JSON.stringify(p.messages).includes('Call final_answer now')); return [tu('query', { table: 'states' })]; }]);
  const r2 = await step({ v: 3, q: Q, turns: turns.slice(0, MAX_STEPS - 2) }, ENV, model2); eq(r2.kind, 'tools');
  const model3 = fakeModel([p => { eq(p.tool_choice, { type: 'auto' }); assert(JSON.stringify(p.messages[p.messages.length - 1]).includes('Call final_answer now')); return [tu('final_answer', { answer: 'The data covers 51 states.', answerable: 'partly', interpretation: 'x' })]; }]);
  await step({ v: 3, q: Q, turns: turns.slice(0, 2) }, { ...ENV, MAX_STEPS: '3' }, model3);
});
await test('loop: a verification failure is fed back as a tool_result error and the retry passes', async () => {
  const wrong = { ...GOOD, answer: GOOD.answer.replace('38 of 254', '39 of 254').replace('Hidalgo County, Texas', 'Starr County, Texas') };
  const model = canonicalScript(wrong, { extraFinals: [GOOD] });
  const { r } = await drive(Q, model, exec);
  eq(r.kind, 'answer'); eq(r.verification.ok, true); eq(r.verification.retries, 1); eq(r.answer.answer, GOOD.answer);
  eq(model.calls.length, 3);
  const m = model.calls[2].messages; eq(m.length, 5); eq(m[3].role, 'assistant'); eq(m[4].content[0].type, 'tool_result'); assert(m[4].content[0].is_error, 'is_error'); eq(m[4].content[0].tool_use_id, m[3].content[0].id);
  assert(m[4].content[0].content.startsWith('Verification failed: number 39'), m[4].content[0].content); assert(m[4].content[0].content.includes('"Starr"'), 'names the place');
  assert(await verifySig(r.assistant, r.sig, SECRET), 'the returned turn is the retried one, signed');
});
await test('loop: after two failed retries the last attempt is returned with verification.ok false', async () => {
  const wrong = { ...GOOD, answer: GOOD.answer.replace('38 of 254', '39 of 254') };
  const model = canonicalScript(wrong, { extraFinals: [wrong, wrong] });
  const { r } = await drive(Q, model, exec);
  eq(r.kind, 'answer'); eq(r.verification.ok, false); eq(r.verification.retries, 2); assert(includes(r.verification.issues, 'number 39'), 'issue kept'); eq(model.calls.length, 4);
});
await test('loop: each rejected style/number case triggers a retry and the corrected answer passes', async () => {
  const cases = [
    ['rounded number accepted (no retry)', { ...GOOD, answer: GOOD.answer.replace('1,180,232', '1.2 million') }, 0],
    ['million form accepted (no retry)', { ...GOOD, answer: GOOD.answer.replace('1,180,232 residents 55+', '1.18 million residents 55+') }, 0],
    ['invented number', { ...GOOD, answer: GOOD.answer.replace('41 oncologists', '42 oncologists') }, 1],
    ['re-attributed place', { ...GOOD, answer: GOOD.answer.replace('Webb County, Texas', 'Zapata County, Texas') }, 1],
    ['unknown id', { ...GOOD, map: { ...GOOD.map, highlight: { ids: ['48215', '99999'] } } }, 1],
    ['bad layer', { ...GOOD, map: { ...GOOD.map, layer: 'cos_ctma_hr' } }, 1],
    ['markdown', { ...GOOD, answer: '# Result\n' + GOOD.answer }, 1],
    ['advice', { ...GOOD, answer: GOOD.answer + ' Residents should ask their doctor about trials.' }, 1],
    ['answerable no without not_in_data', { ...GOOD, answerable: 'no', not_in_data: [] }, 1],
  ];
  for (const [name, first, retries] of cases) {
    const model = canonicalScript(first, { extraFinals: retries ? [GOOD] : [] });
    const { r } = await drive(Q, model, exec);
    assert(r.verification.ok, `${name}: final should pass: ${JSON.stringify(r.verification.issues)}`); eq(r.verification.retries, retries, name + ' retries');
  }
});
await test('loop: a text-only reply becomes kind:"answer" with answerable "partly" and is verified', async () => {
  const model = fakeModel([[txt('There are 254 counties in Texas.')], [txt('There are 254 counties in Texas.')], [txt('There are 254 counties in Texas.')]]);
  const r = await step({ v: 3, q: 'how many counties are in texas', turns: [] }, ENV, model);
  // two nudges back to the tools, then the third text reply is taken as the answer and verified (it fails: no result holds 254)
  eq(r.kind, 'answer'); eq(r.answer.answerable, 'partly'); eq(r.answer.answer, 'There are 254 counties in Texas.'); eq(r.verification.ok, false); eq(r.verification.retries, 2); assert(includes(r.verification.issues, 'number 254'), 'no result holds 254');
  eq(model.calls.length, 3); assert(String(model.calls[1].messages[2].content).includes('Text replies are not shown'), 'the nudge is a plain user message');
  // the retry for a text-only reply is a plain user message; a final_answer that then follows is accepted
  const model2 = fakeModel([[txt('Hello there.')], [tu('final_answer', { answer: catalog.OTHER_TEXT, answerable: 'no', interpretation: 'Not a question about the map\'s data.', not_in_data: ['Greetings are not data.'] })]]);
  const r2 = await step({ v: 3, q: 'hey you', turns: [] }, ENV, model2);
  eq(r2.kind, 'answer'); eq(r2.verification.retries, 1); assert(r2.verification.ok); eq(model2.calls[1].messages[2].role, 'user'); assert(typeof model2.calls[1].messages[2].content === 'string' && model2.calls[1].messages[2].content.includes('Text replies are not shown'));
  // a text-only reply whose every token checks out passes as it is (after the two nudges)
  const model3 = fakeModel([[txt('The data covers 254 counties in Texas.')], [txt('The data covers 254 counties in Texas.')], [txt('The data covers 254 counties in Texas.')]]);
  // a text reply cannot carry claims (ASK_CONTRACT §6 rule 6): one that writes a figure is not shown; one with no figure passes as it is
  const b = [tu('query', { table: 'counties' })]; const turns = [{ assistant: b, sig: await sign(b, SECRET), results: [{ tool_use_id: b[0].id, content: '{"in_scope":254}' }] }];
  const r3 = await step({ v: 3, q: 'how many counties in texas', turns }, ENV, model3); eq(r3.kind, 'answer'); eq(r3.verification.ok, false); eq(r3.answer.answerable, 'partly'); assert(includes(r3.verification.issues, 'claims is empty'), JSON.stringify(r3.verification.issues));
  const model4 = fakeModel([[txt('The data covers every county in Texas.')], [txt('The data covers every county in Texas.')], [txt('The data covers every county in Texas.')]]);
  const r4 = await step({ v: 3, q: 'how many counties in texas', turns }, ENV, model4); eq(r4.kind, 'answer'); eq(r4.verification.ok, true, JSON.stringify(r4.verification.issues));
});
await test('loop: SCOPE_TEXT answer passes verification without any tool call', async () => {
  const model = fakeModel([[tu('final_answer', { answer: catalog.SCOPE_TEXT, answerable: 'no', interpretation: 'Out of scope: a question about a person\'s care.', not_in_data: ['The data lists trials; it does not match people to them.'] })]]);
  const r = await step({ v: 3, q: 'which trial is right for my mother with stage 3 lung cancer?', turns: [] }, ENV, model);
  eq(r.kind, 'answer'); eq(r.step, 1); eq(r.verification, { ok: true, issues: [], retries: 0 }); eq(r.answer.answer, catalog.SCOPE_TEXT);
});
await test('loop: final_answer alongside other calls is returned as kind:"tools" with ALL calls and a note', async () => {
  const fid = tid();
  const model = fakeModel([[tu('query', { table: 'counties', where: TX_ONLY }), tu('final_answer', { answer: 'x', answerable: 'yes', interpretation: 'y' }, fid)], [tu('final_answer', withCall(GOOD, 'FIRST'))]]);
  const r1 = await step({ v: 3, q: Q, turns: [] }, ENV, model);
  eq(r1.kind, 'tools'); eq(r1.calls.map(c => c.name), ['query', 'final_answer']); assert(r1.note && r1.note.includes(FINAL_NOTE), 'note tells the client what to answer');
  // the client answers the final_answer call with {ok:true, note} and the model is called again with both results
  const results = r1.calls.map(c => ({ tool_use_id: c.id, content: JSON.stringify(c.name === 'final_answer' ? { ok: true, note: FINAL_NOTE } : COUNTY_ROWS) }));
  const fix = JSON.parse(JSON.stringify(withCall(GOOD, r1.calls[0].id))); fix.answer = '38 of 254 Texas counties match; the largest is Hidalgo County, Texas with 41 oncologists.'; fix.sources = ['counties']; fix.claims = fix.claims.filter(c => c.call === r1.calls[0].id && ['count', 'in_scope', 'oncologists.count'].includes(c.field) && ['TX', '48215'].includes(c.place));
  model.calls.length = 0; const model2 = fakeModel([[tu('final_answer', fix)]]);
  const r2 = await step({ v: 3, q: Q, turns: [{ assistant: r1.assistant, sig: r1.sig, results }] }, ENV, model2);
  eq(r2.kind, 'answer'); assert(r2.verification.ok, JSON.stringify(r2.verification.issues)); eq(model2.calls[0].messages[2].content.length, 2);
});
await test('loop: prior Q/A pairs are rendered as plain user/assistant turns before the question', async () => {
  const wrong = [tu('final_answer', { answer: 'There are 254 counties in the data for Texas.', answerable: 'partly', interpretation: 'x' })];
  const model = fakeModel([p => { const m = p.messages; eq(m.slice(0, 5), [{ role: 'user', content: 'how many counties in texas' }, { role: 'assistant', content: 'Texas has 254 counties.' }, { role: 'user', content: 'and in ohio' }, { role: 'assistant', content: 'Ohio has 88 counties.' }, { role: 'user', content: 'which of them are rural' }]); return wrong; }, wrong, wrong]);
  const r = await step({ v: 3, q: 'which of them are rural', turns: [], prior: [{ q: 'how many counties in texas', answer: 'Texas has 254 counties.' }, { q: 'and in ohio', answer: 'Ohio has 88 counties.' }] }, ENV, model);
  eq(r.kind, 'answer'); assert(!r.verification.ok, 'prior answers are not tool results: 254 is unverified'); eq(r.verification.retries, 2);
  eq(buildMessages({ q: 'q1', prior: [], turns: [] }), [{ role: 'user', content: 'q1' }]);
});
await test('loop: unknown env (no key, no secret) fails with a 5xx-mapped error, env.MODEL is used, MODEL_FAST ignored', async () => {
  await rejects(step({ v: 3, q: Q, turns: [] }, {}, fakeModel([])), undefined, 'neither');
  const model = fakeModel([[tu('final_answer', { answer: catalog.OTHER_TEXT, answerable: 'no', interpretation: 'x', not_in_data: ['y'] })]]);
  const r = await step({ v: 3, q: 'hello', turns: [] }, { ...ENV, MODEL: 'claude-test-9', MODEL_FAST: 'claude-fast-1' }, model);
  eq(r.model, 'claude-test-9'); eq(model.calls[0].model, 'claude-test-9');
});

// ---------- index.js: HTTP ----------
const realLog = console.log; const quiet = async fn => { console.log = (...a) => { if (!(typeof a[0] === 'string' && a[0].startsWith('{"q"'))) realLog(...a); }; try { return await fn(); } finally { console.log = realLog; } };
const req = (body, { origin = 'https://nehaamd.github.io', ip = '1.2.3.4', method = 'POST', path = '/ask' } = {}) => new Request('https://worker.test' + path, { method, headers: { 'content-type': 'application/json', ...(origin ? { Origin: origin } : {}), 'CF-Connecting-IP': ip }, body: method === 'POST' ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined });
await test('http: CORS preflight, /health, origin check, bad JSON, 404', () => quiet(async () => {
  resetLimits();
  const pre = await handle(req(null, { method: 'OPTIONS' }), ENV, fakeModel([])); eq(pre.status, 204); eq(pre.headers.get('Access-Control-Allow-Origin'), 'https://nehaamd.github.io');
  const h = await handle(req(null, { method: 'GET', path: '/health' }), ENV, fakeModel([])); eq(h.status, 200); const hj = await h.json(); eq(hj.ok, true); eq(hj.v, 3); eq(h.headers.get('cache-control'), 'no-store');
  const bad = await handle(req({ v: 3, q: Q }, { origin: 'https://evil.test' }), ENV, fakeModel([])); eq(bad.status, 403); eq(bad.headers.get('Access-Control-Allow-Origin'), 'null');
  const nojson = await handle(req('{not json'), ENV, fakeModel([])); eq(nojson.status, 400);
  const nf = await handle(req(null, { method: 'GET', path: '/ask' }), ENV, fakeModel([])); eq(nf.status, 404);
  const noOrigin = await handle(req({ v: 3, q: 'hello' }, { origin: '' }), ENV, fakeModel([[tu('final_answer', { answer: catalog.OTHER_TEXT, answerable: 'no', interpretation: 'x', not_in_data: ['y'] })]])); eq(noOrigin.status, 200);   // curl / same-origin
}));
await test('http: a full step over HTTP, status codes for bad transcript, model failure and timeout', () => quiet(async () => {
  resetLimits();
  const model = canonicalScript();
  const r1 = await handle(req({ v: 3, q: Q, turns: [] }), ENV, model); eq(r1.status, 200); const j1 = await r1.json(); eq(j1.kind, 'tools'); assert(!('usage' in j1) && !('retries' in j1), 'usage and retries stay in the log');
  const forged = JSON.parse(JSON.stringify(j1.assistant)); forged[0].input.table = 'states';
  const r2 = await handle(req({ v: 3, q: Q, turns: [{ assistant: forged, sig: j1.sig, results: j1.calls.map(c => ({ tool_use_id: c.id, content: '{}' })) }] }), ENV, model); eq(r2.status, 400); eq(await r2.json(), { error: 'bad transcript' });
  const r3 = await handle(req({ v: 3, q: Q, turns: [{ assistant: j1.assistant, sig: j1.sig, results: j1.calls.map(c => ({ tool_use_id: c.id, content: JSON.stringify(exec(c.name, c.input)) })) }] }), ENV, model); eq(r3.status, 200); const j3 = await r3.json(); eq(j3.kind, 'answer'); eq(j3.verification.ok, true);
  const boom = await handle(req({ v: 3, q: Q, turns: [] }, { ip: '9.9.9.9' }), ENV, async () => { throw new Error('model claude: HTTP 500 oops'); }); eq(boom.status, 502); const bj = await boom.json(); assert(bj.error.includes('unavailable') && bj.detail.includes('HTTP 500'));
  const slow = await handle(req({ v: 3, q: Q, turns: [] }, { ip: '9.9.9.8' }), ENV, async () => { const e = new Error('x'); e.name = 'TimeoutError'; throw e; }); eq(slow.status, 504);
  const unknownTool = await handle(req({ v: 3, q: Q, turns: [] }, { ip: '9.9.9.7' }), ENV, fakeModel([[tu('explode', {})]])); eq(unknownTool.status, 502);
}));
await test('http: rate limits count questions (turns.length === 0) and, separately, continuation steps; 429 carries retry_after_s', () => quiet(async () => {
  resetLimits(); const final = () => fakeModel([[tu('final_answer', { answer: catalog.OTHER_TEXT, answerable: 'no', interpretation: 'x', not_in_data: ['y'] })]]);
  for (let i = 0; i < 3; i++) eq((await handle(req({ v: 3, q: 'hello', turns: [] }, { ip: '5.5.5.5' }), ENV, final())).status, 200, 'first three pass');
  const r = await handle(req({ v: 3, q: 'hello', turns: [] }, { ip: '5.5.5.5' }), ENV, final()); eq(r.status, 429); const j = await r.json(); assert(j.retry_after_s >= 1 && j.retry_after_s <= 60, 'retry_after_s'); assert(j.error.includes('minute')); eq(r.headers.get('retry-after'), String(j.retry_after_s));
  // later steps of a question are free even for a throttled visitor
  const model = canonicalScript(); const t0 = await step({ v: 3, q: Q, turns: [] }, ENV, model);
  const r2 = await handle(req({ v: 3, q: Q, turns: [{ assistant: t0.assistant, sig: t0.sig, results: t0.calls.map(c => ({ tool_use_id: c.id, content: JSON.stringify(exec(c.name, c.input)) })) }] }, { ip: '5.5.5.5' }), ENV, model); eq(r2.status, 200); eq((await r2.json()).verification.ok, true);
  // the daily cap (5 in this env) across visitors
  resetLimits(); let last;
  for (let i = 0; i < 5; i++) last = await handle(req({ v: 3, q: 'hello', turns: [] }, { ip: '7.7.7.' + i }), ENV, final()); eq(last.status, 200);
  const capped = await handle(req({ v: 3, q: 'hello', turns: [] }, { ip: '7.7.7.9' }), ENV, final()); eq(capped.status, 429); assert((await capped.json()).error.includes("today's limit"));
  // checkLimits directly: per-minute window slides
  resetLimits(); const now = Date.now(); for (let i = 0; i < 3; i++) eq(checkLimits('a', ENV, now + i).ok, true); eq(checkLimits('a', ENV, now + 10).ok, false); eq(checkLimits('a', ENV, now + 60001).ok, true); eq(checkLimits('b', ENV, now).ok, true);
  // continuation steps have their own budget of MAX_STEPS × the question limits: a replayed signed turn cannot buy unlimited model calls
  resetLimits(); for (let i = 0; i < 3 * MAX_STEPS; i++) eq(checkLimits('c', ENV, now, true).ok, true, 'continuation ' + i); eq(checkLimits('c', ENV, now, true).ok, false, 'continuation budget exhausted'); eq(checkLimits('c', ENV, now).ok, true, 'questions still have their own budget');
  resetLimits(); const replay = { v: 3, q: Q, turns: [{ assistant: t0.assistant, sig: t0.sig, results: t0.calls.map(c => ({ tool_use_id: c.id, content: JSON.stringify(exec(c.name, c.input)) })) }] };
  let status = 200; for (let i = 0; i < 3 * MAX_STEPS + 1 && status === 200; i++) status = (await handle(req(replay, { ip: '6.6.6.6' }), ENV, canonicalScript())).status;
  eq(status, 429, 'the replayed turn is throttled after MAX_STEPS × PER_MINUTE continuation steps');
}));
await test('http: a request body over MAX_BODY_BYTES is refused with 413 before parsing', () => quiet(async () => {
  resetLimits();
  const huge = JSON.stringify({ v: 3, q: Q, turns: [], pad: 'x'.repeat(MAX_BODY_BYTES + 10) });
  const r = await handle(req(huge, { ip: '8.8.8.8' }), ENV, fakeModel([])); eq(r.status, 413); assert((await r.json()).error.includes('too large'));
  const r2 = await handle(new Request('https://worker.test/ask', { method: 'POST', headers: { 'content-type': 'application/json', Origin: 'https://nehaamd.github.io', 'content-length': String(MAX_BODY_BYTES + 1) }, body: '{}' }), ENV, fakeModel([])); eq(r2.status, 413);
}));
await test('http: makeCallModel posts the §3 shape, retries once on 529, maps timeouts', async () => {
  const seen = [];
  const fetchOk = async (url, init) => { seen.push({ url, init }); return new Response(JSON.stringify({ content: [txt('hi')], stop_reason: 'end_turn', usage: { input_tokens: 1 }, model: 'm' }), { status: 200 }); };
  const call = makeCallModel({ ANTHROPIC_API_KEY: 'sk-x' }, fetchOk);
  const out = await call({ model: 'm', max_tokens: 2500, system: [], tools: [], tool_choice: { type: 'auto' }, messages: [] });
  eq(out.content, [txt('hi')]); eq(seen[0].url, 'https://api.anthropic.com/v1/messages'); eq(seen[0].init.headers['x-api-key'], 'sk-x'); eq(seen[0].init.headers['anthropic-version'], '2023-06-01'); eq(seen[0].init.method, 'POST'); assert(seen[0].init.signal, 'abort signal'); assert(!JSON.parse(seen[0].init.body).temperature, 'no temperature');
  let n = 0; const flaky = async () => { n++; return n === 1 ? new Response('overloaded', { status: 529 }) : new Response(JSON.stringify({ content: [] }), { status: 200 }); };
  const t0 = Date.now(); await makeCallModel({ ANTHROPIC_API_KEY: 'k' }, flaky)({ model: 'm', messages: [] }); eq(n, 2); assert(Date.now() - t0 >= 1400, 'waited 1.5 s');
  await rejects(makeCallModel({ ANTHROPIC_API_KEY: 'k' }, async () => new Response('bad', { status: 400 }))({ model: 'm', messages: [] }), undefined, 'HTTP 400');
  const e = await rejects(makeCallModel({ ANTHROPIC_API_KEY: 'k' }, async () => { const x = new Error('t'); x.name = 'TimeoutError'; throw x; })({ model: 'm', messages: [] })); eq(e.code, 'timeout');
  await rejects(makeCallModel({}, fetchOk)({ model: 'm', messages: [] }), undefined, 'ANTHROPIC_API_KEY');
});

// ---------- end to end with the real engine, when it exists ----------
const enginePath = path.join(ROOT, 'docs/ask/engine.js');
if (fs.existsSync(enginePath)) {
  await test('end to end: the canonical question through the real engine (offline) and a verified final answer', async () => {
    const { createEngine } = await import(pathToFileURL(enginePath).href);
    const engine = createEngine({ root: ROOT }); await engine.load();
    assert(engine.loaded && engine.loaded.counties, 'engine loaded counties');
    const qid = tid(), did = tid(); const store = {};
    const model = fakeModel([
      [tu('query', { table: 'counties', where: [{ field: 'state', op: '=', value: 'TX' }, { field: 'oncologists.class', op: '=', value: 2 }], order_by: [{ field: 'pop55', dir: 'desc' }], limit: 50, columns: ['oncologists.count', 'trials_listed_here', 'pct_lt20_trials_within_60rdmi', 'districts'] }, qid),
       tu('query', { table: 'districts', where: [{ field: 'state', op: '=', value: 'TX' }, { field: 'oncologists.pct_pop55_in_counties_with_oncologists_no_trials', op: '>', value: 0 }], order_by: [{ field: 'oncologists.pct_pop55_in_counties_with_oncologists_no_trials', dir: 'desc' }], limit: 50 }, did)],
      () => { // write the final from the real results, as the model would
        const c = store[qid], d = store[did]; assert(c && !c.error, 'county query failed: ' + JSON.stringify(c).slice(0, 200)); assert(d && !d.error, 'district query failed: ' + JSON.stringify(d).slice(0, 200));
        const top = c.rows[0]; const topd = d.rows[0];
        const answer = `${c.count} of ${c.in_scope} Texas counties have at least one oncologist but no recruiting trial with a site in the county; ${c.sum_pop55_matching.toLocaleString('en-US')} residents 55+ live in them. The largest is ${top.name} (${top.pop55.toLocaleString('en-US')} residents 55+, ${top['oncologists.count']} oncologists). ${d.count} Texas districts contain such counties; the largest share of residents 55+ living in them is in ${topd.name} at ${topd['oncologists.pct_pop55_in_counties_with_oncologists_no_trials']}%.`;
        const claims = [{ place: 'TX', field: 'count', value: c.count, call: qid }, { place: 'TX', field: 'in_scope', value: c.in_scope, call: qid }, { place: 'TX', field: 'sum_pop55_matching', value: c.sum_pop55_matching, call: qid }, { place: top.id, field: 'pop55', value: top.pop55, call: qid }, { place: top.id, field: 'oncologists.count', value: top['oncologists.count'], call: qid }, { place: 'TX', field: 'count', value: d.count, call: did }, { place: topd.id, field: 'oncologists.pct_pop55_in_counties_with_oncologists_no_trials', value: topd['oncologists.pct_pop55_in_counties_with_oncologists_no_trials'], call: did }];
        return [tu('final_answer', { answer, claims, answerable: 'yes', interpretation: 'Counties in Texas in oncologists-vs-trials class 2; for districts, the share of residents 55+ living in such counties.', alternatives: ['Which Texas counties have oncologists but no trial within 60 road-miles?'], not_in_data: [], caveats: ['An oncologist with practice locations in two counties is counted in both.'], map: { unit: 'county', layer: 'onc', params: {}, state: 'TX', highlight: { from_call: qid }, highlight_label: 'Texas counties with oncologists but no recruiting trial' }, table: { from_call: qid }, sources: ['counties', 'districts'] })];
      },
    ]);
    const { r } = await drive(Q, model, async (name, input, id) => { const out = await engine.run(name, input, id); store[id] = out; return out; });
    eq(r.kind, 'answer'); assert(r.verification.ok, JSON.stringify(r.verification.issues)); assert(/^\d+ of 254 Texas counties/.test(r.answer.answer), r.answer.answer);
    const full = engine.full(qid); assert(full && full.unit === 'county' && full.ids.length === store[qid].count, 'engine.full gives every matching id');
    // a 24 KB cap check against a real wide result: the client truncates; the worker rejects anything larger
    assert(JSON.stringify(store[qid]).length < 60000, 'sanity');
  });
  await test('end to end: an error result from the engine (unknown field) is passed to the model as a tool result', async () => {
    const { createEngine } = await import(pathToFileURL(enginePath).href);
    const engine = createEngine({ root: ROOT }); await engine.load();
    const out = await engine.run('query', { table: 'counties', where: [{ field: 'oncologist_count', op: '>', value: 0 }] }, 'toolu_x');
    assert(out && out.error && /oncologist_count/.test(out.error), 'engine returns {error}: ' + JSON.stringify(out).slice(0, 200));
    const model = fakeModel([[tu('query', { table: 'counties', where: [{ field: 'oncologist_count', op: '>', value: 0 }] })], p => { const tr = p.messages[2].content[0]; assert(tr.is_error === true, 'is_error passed through'); assert(tr.content.includes('oncologist_count')); return [tu('final_answer', { answer: catalog.OTHER_TEXT, answerable: 'no', interpretation: 'x', not_in_data: ['y'] })]; }]);
    const { r } = await drive(Q, model, (name, input, id) => engine.run(name, input, id)); eq(r.kind, 'answer');
  });
} else console.log('skip end-to-end: docs/ask/engine.js not present');

console.log(`\n${passed} passed, ${failed} failed${failed ? ': ' + failures.join('; ') : ''}`);
process.exit(failed ? 1 : 0);
