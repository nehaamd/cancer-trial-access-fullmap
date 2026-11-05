#!/usr/bin/env node
/* Tests for the pure half of the "Ask the map" client (docs/ask/render.js): map validation, the view's query string, result truncation
   for the step protocol, table sorting and formatting, and the answer card's HTML (escaping, the unverified notice, the scope card).
   No DOM, no network, no model.   node worker/tests/client.test.js   (Node 22, ESM; exits 1 on any failure) */
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const R = await import(pathToFileURL(path.resolve(HERE, '..', '..', 'docs', 'ask', 'render.js')).href);
const CAT = await import(pathToFileURL(path.resolve(HERE, '..', '..', 'docs', 'ask', 'catalog.js')).href);

let pass = 0, fail = 0;
const test = (name, fn) => { try { fn(); pass++; console.log(`PASS ${name}`); } catch (e) { fail++; console.log(`FAIL ${name}\n     ${String(e && e.message || e).split('\n').join('\n     ')}`); } };
const PAGE_LAYERS = { county: ['short', 'shortt', 't', 'rn', 'rb', 'inc', 'acs', 'bva', 'mva', 'onc'], district: ['l20', 'z60', 'g60b', 'g60n', 'medn', 'ginc', 'gacs', 'cos_ctma_hr'], state: ['l20', 'z60', 'g60b', 'g60n', 'medn', 'ginc', 'gacs'] };
const unitOf = id => /^\d{5}$/.test(id) ? 'county' : /^[A-Z]{2}-\d{2}$/.test(id) ? 'district' : /^[A-Z]{2}$/.test(id) && CAT.STATES[id] ? 'state' : null;   // a stand-in for engine.unitOf

// ---------- ids ----------
test('district ids become the map geoid', () => { assert.equal(R.districtGeoid('TX-34'), '4834'); assert.equal(R.districtGeoid('WY-00'), '5600'); assert.equal(R.districtGeoid('DC-00'), '1198'); assert.equal(R.districtGeoid('4834'), '4834'); assert.equal(R.districtGeoid('ZZ-01'), null); assert.equal(R.districtGeoid('tx-7'), '4807'); });
test('toMapId / resolveIds keep only real place ids, once', () => {
  assert.equal(R.toMapId('48215', 'county'), '48215'); assert.equal(R.toMapId('tx', 'state'), 'TX'); assert.equal(R.toMapId('nci:3'), null); assert.equal(R.toMapId('fac:12', 'county'), null);
  assert.deepEqual(R.resolveIds(['48215', 'TX-34', 'TX-34', 'tx', 'nci:3', 'fac:12', '', null, '4834'], unitOf), ['48215', '4834', 'TX']); });

// ---------- validateMap ----------
test('validateMap drops bad layers, params and ids but keeps the unit and highlight', () => {
  const mv = R.validateMap({ unit: 'county', layer: 'nope', params: { site: 'lung', bogus: 'x', thr: '99' }, state: 'Texas', place: 'nci:3', highlight: { from_call: 'toolu_1' }, highlight_label: ' Counties with oncologists but no trial ' }, PAGE_LAYERS, unitOf);
  assert.equal(mv.unit, 'county'); assert.equal(mv.layer, null); assert.deepEqual(mv.params, { site: 'lung' }); assert.equal(mv.state, null); assert.equal(mv.place, null);
  assert.deepEqual(mv.highlight, { from_call: 'toolu_1' }); assert.equal(mv.highlight_label, 'Counties with oncologists but no trial');
  assert.ok(mv.dropped.some(d => /layer "nope"/.test(d))); assert.ok(mv.dropped.some(d => /bogus=x/.test(d))); assert.ok(mv.dropped.some(d => /thr=99/.test(d))); assert.ok(mv.dropped.some(d => /state "Texas"/.test(d))); assert.ok(mv.dropped.some(d => /place "nci:3"/.test(d))); });
test('validateMap: a layer must be in the catalog AND on the page; params must fit the layer', () => {
  assert.equal(R.validateMap({ unit: 'county', layer: 'onc' }, { county: ['t'] }, unitOf).layer, null);   // catalog yes, page no
  assert.equal(R.validateMap({ unit: 'county', layer: 'onc' }, PAGE_LAYERS, unitOf).layer, 'onc');
  const mv = R.validateMap({ unit: 'county', layer: 'onc', params: { site: 'lung' } }, PAGE_LAYERS, unitOf); assert.deepEqual(mv.params, {}); assert.ok(mv.dropped.some(d => /does not apply to the onc layer/.test(d)));
  const bva = R.validateMap({ unit: 'county', layer: 'bva', params: { crit: 'z60', thr: 75, site: 'breast', lt: '10' } }, PAGE_LAYERS, unitOf); assert.deepEqual(bva.params, { crit: 'z60', thr: '75', site: 'breast' }); });
test('validateMap: no usable unit -> null; highlight ids pass as strings; place resolves to a map id', () => {
  assert.equal(R.validateMap({ layer: 't' }, PAGE_LAYERS, unitOf), null); assert.equal(R.validateMap(null, PAGE_LAYERS, unitOf), null); assert.equal(R.validateMap({ unit: 'tract' }, PAGE_LAYERS, unitOf), null);
  const mv = R.validateMap({ unit: 'district', layer: 'cos_ctma_hr', highlight: { ids: ['OH-02', 'OH-04'] }, place: 'OH-02', state: 'oh' }, PAGE_LAYERS, unitOf);
  assert.deepEqual(mv.highlight, { ids: ['OH-02', 'OH-04'] }); assert.equal(mv.place, '3902'); assert.equal(mv.placeKind, 'district'); assert.equal(mv.state, 'OH'); });

// ---------- query string ----------
test('buildQS: county view with params and a state focus', () => {
  const mv = R.validateMap({ unit: 'county', layer: 'onc', state: 'TX', highlight: { ids: ['48215', '48201'] } }, PAGE_LAYERS, unitOf);
  const ids = R.resolveIds(mv.highlight.ids, unitOf); const pp = R.placeParamFor(ids, mv, id => 'TX');
  assert.deepEqual(pp, ['s', 'TX']); assert.equal(R.buildQS(mv, pp), 'm=onc&s=TX'); });
test('buildQS: district view, the layer params in catalog order, a single district selected', () => {
  const mv = R.validateMap({ unit: 'district', layer: 'l20', params: { lt: '10', type: 'lung' }, highlight: { ids: ['TX-34'] } }, PAGE_LAYERS, unitOf);
  const ids = R.resolveIds(mv.highlight.ids, unitOf); assert.deepEqual(ids, ['4834']);
  const pp = R.placeParamFor(ids, mv, null); assert.deepEqual(pp, ['d', '4834']); assert.equal(R.buildQS(mv, pp), 'u=district&m=l20&type=lung&lt=10&d=4834'); });
test('buildQS: state view, no layer (default), many states -> national view; the model\'s place wins over the list', () => {
  const mv = R.validateMap({ unit: 'state', highlight: { ids: ['TX', 'OH', 'CA'] } }, PAGE_LAYERS, unitOf);
  const ids = R.resolveIds(mv.highlight.ids, unitOf); assert.equal(R.placeParamFor(ids, mv, null), null); assert.equal(R.buildQS(mv, null), 'u=state');
  const mv2 = R.validateMap({ unit: 'state', layer: 'z60', place: 'OH', highlight: { ids: ['TX', 'OH'] } }, PAGE_LAYERS, unitOf);
  assert.equal(R.buildQS(mv2, R.placeParamFor(['TX', 'OH'], mv2, null)), 'u=state&m=z60&s=OH'); });
test('placeParamFor: counties in one state frame the state; across states the nation; a single county opens it', () => {
  const mv = R.validateMap({ unit: 'county', layer: 't' }, PAGE_LAYERS, unitOf); const st = { 48215: 'TX', 48201: 'TX', 39001: 'OH' };
  assert.deepEqual(R.placeParamFor(['48215', '48201'], mv, id => st[id]), ['s', 'TX']); assert.equal(R.placeParamFor(['48215', '39001'], mv, id => st[id]), null); assert.deepEqual(R.placeParamFor(['48215'], mv, id => st[id]), ['c', '48215']);
  assert.deepEqual(R.placeParamFor(['4834', '4815'], mv, id => 'TX'), null, 'ids of another unit do not frame the view'); });

// ---------- truncation ----------
test('truncateResult leaves small results alone and keeps big ones valid JSON under 24 KB, cut by rows', () => {
  const small = { count: 3, rows: [{ id: '1' }] }; assert.equal(R.truncateResult(small), JSON.stringify(small));
  const big = { table: 'counties', count: 3143, in_scope: 3143, columns: ['id', 'name', 'pop55', 'pct'], rows: Array.from({ length: 3143 }, (_, i) => ({ id: String(10000 + i), name: `County number ${i}, Somewhere`, pop55: i * 37, pct: i % 7 ? i / 3 : null })), source: { file: 'api/all_counties.json' } };
  const s = R.truncateResult(big); const bytes = new TextEncoder().encode(s).length; assert.ok(bytes <= 24 * 1024, `bytes ${bytes}`);
  const j = JSON.parse(s); assert.equal(j.count, 3143); assert.equal(j.table, 'counties'); assert.ok(j.rows.length > 0 && j.rows.length < 3143); assert.match(j.truncated, /^…\(truncated\): rows cut to \d+ of 3143$/); assert.deepEqual(j.rows[0], big.rows[0]); });
test('truncateResult with nothing to cut by rows keeps a JSON string with the marker', () => {
  const s = R.truncateResult({ text: 'x'.repeat(40000) }); assert.ok(new TextEncoder().encode(s).length <= 24 * 1024); const j = JSON.parse(s); assert.equal(j.truncated, true); assert.ok(j.text.endsWith('…(truncated)')); });

// ---------- sorting and cells ----------
test('sortRows: nulls last both ways, numbers numeric, stable', () => {
  const rows = [{ n: 'a', v: 3 }, { n: 'b', v: null }, { n: 'c', v: 1 }, { n: 'd' }, { n: 'e', v: 2 }, { n: 'f', v: 3 }];
  assert.deepEqual(R.sortRows(rows, 'v', 'asc').map(r => r.n), ['c', 'e', 'a', 'f', 'b', 'd']); assert.deepEqual(R.sortRows(rows, 'v', 'desc').map(r => r.n), ['a', 'f', 'e', 'c', 'b', 'd']);
  assert.deepEqual(R.sortRows([{ s: 'TX-10' }, { s: 'TX-2' }, { s: null }], 's', 'asc').map(r => r.s), ['TX-2', 'TX-10', null]);
  assert.deepEqual(R.sortRows([{ b: false }, { b: true }, { b: null }], 'b', 'asc').map(r => r.b), [true, false, null]); });
test('sortRows reads dotted paths from nested rows or flat dotted keys', () => {
  assert.deepEqual(R.sortRows([{ oncologists: { count: 5 } }, { 'oncologists.count': 2 }, { oncologists: { count: 9 } }], 'oncologists.count', 'desc').map(r => R.getPath(r, 'oncologists.count')), [9, 5, 2]); });
test('fmtCell: thousands separators, one-decimal rates kept, yes/no, em dash for null, arrays joined', () => {
  assert.equal(R.fmtCell(1080228), '1,080,228'); assert.equal(R.fmtCell(52.8), '52.8'); assert.equal(R.fmtCell(0), '0'); assert.equal(R.fmtCell(true), 'yes'); assert.equal(R.fmtCell(false), 'no'); assert.equal(R.fmtCell(null), '—'); assert.equal(R.fmtCell(undefined), '—'); assert.equal(R.fmtCell(['TX-15', 'TX-34']), 'TX-15, TX-34'); assert.equal(R.fmtCell(NaN), '—'); });

// ---------- tables ----------
const FULL = { ids: ['48215', '48201'], unit: 'county', columns: ['id', 'name', 'state', 'pop55', 'oncologists.count', 'trials_listed_here', 'metro'], rows: [{ id: '48215', name: 'Hidalgo County, Texas', state: 'TX', pop55: 182206, 'oncologists.count': 31, trials_listed_here: 0, metro: true }, { id: '48201', name: 'Harris County, Texas', state: 'TX', pop55: 1080228, 'oncologists.count': 500, trials_listed_here: 1063, metro: true }] };
const RES = { table: 'counties', count: 2, in_scope: 254, returned: 2, columns: FULL.columns, rows: FULL.rows, sum_pop55_matching: 1262434, source: { file: 'api/all_counties.json' } };
test('prepareTable from the engine\'s full result carries count / in scope / residents; place cells are buttons; id is not a column', () => {
  const t = R.prepareTable({ from_call: 'toolu_1' }, FULL, RES); assert.equal(t.count, 2); assert.equal(t.in_scope, 254); assert.equal(t.sum_pop55, 1262434); assert.equal(t.unit, 'county'); assert.equal(t.table, 'counties');
  const html = R.tableHTML(t, { placeIdOf: r => R.rowMapId(r, 'county') }); assert.ok(html.includes('data-pl="48215"')); assert.ok(html.includes('>Hidalgo County, Texas<')); assert.ok(!/<th[^>]*>id</.test(html)); assert.ok(html.includes('class="n">1,080,228<')); assert.ok(html.includes('>yes<'));
  assert.ok(html.includes('title="oncologists.count — Oncologists (CMS'), 'the tooltip carries the field path and the catalog description'); assert.ok(/<button[^>]*data-col="oncologists.count"[^>]*>oncologists</.test(html), 'the header shows the short human label');
  assert.equal(R.summaryHTML(t), '<p class="ask-sum"><b>2</b> counties match · of <b>254</b> in scope · <b>1,262,434</b> residents 55+ in the matching places</p>'); });
test('tableHTML: 100 rows then "Show all N"; sorting marks the header; a model-written inline table is escaped', () => {
  const rows = Array.from({ length: 250 }, (_, i) => ({ id: String(10000 + i), name: `C${i}`, v: 250 - i })); const t = { columns: ['id', 'name', 'v'], rows, table: null, unit: 'county' };
  const h = R.tableHTML(t); assert.equal((h.match(/<tr>/g) || []).length - 1, 100); assert.ok(h.includes('Show all 250')); assert.equal((R.tableHTML(t, { showAll: true }).match(/<tr>/g) || []).length - 1, 250);
  const hs = R.tableHTML(t, { sortKey: 'v', sortDir: 'asc' }); assert.ok(hs.includes('aria-sort="ascending"')); assert.ok(/<tbody><tr><td>C249<\/td>/.test(hs));
  const inline = R.prepareTable({ columns: ['place', 'figure'], rows: [['<img src=x onerror=alert(1)>', 12], ['ok', null]] }, null, null); assert.equal(inline.inline, true);
  const hi = R.tableHTML(inline); assert.ok(!hi.includes('<img')); assert.ok(hi.includes('&lt;img src=x onerror=alert(1)&gt;')); assert.ok(hi.includes('>—<')); });

// ---------- the card ----------
const ANSWER = { answer: 'Two Texas counties have oncologists but no recruiting trial: Hidalgo County (31 oncologists) and <script>alert("x")</script>.', answerable: 'yes', interpretation: 'Counties in Texas with oncologists.count > 0 and trials_listed_here = 0 <b>bold</b>.', alternatives: ['Which Texas districts have oncologists but no trials?', '<i>x</i>'], not_in_data: ['Districts have no county-level trial sites of their own.'], caveats: ['Oncologists are counted at every practice location.'], map: { unit: 'county', layer: 'onc', state: 'TX', highlight: { from_call: 'toolu_1' }, highlight_label: 'Counties with oncologists but no trial' }, table: { from_call: 'toolu_1' }, sources: ['counties'], follow_ups: ['How many residents 55+ live there?'] };
const ctxBase = () => ({ q: 'Texas counties with oncologists but no trials <script>', answer: ANSWER, verification: { ok: true, issues: [] }, table: R.prepareTable(ANSWER.table, FULL, RES), sources: [{ table: 'counties', title: 'Counties', file: 'api/all_counties.json', url: 'https://nehaamd.github.io/cancer-trial-access-fullmap/api/all_counties.json', as_of: '2026-11-03' }, { table: 'x', title: 'Bad', file: 'bad.js', url: 'javascript:alert(1)' }], vintages: { data_as_of: '2026-11-03', incidence_period: '2019-2023' }, mapShows: 'Oncologists vs trials in the county · by county · Texas', hl: { label: 'Counties with oncologists but no trial', count: 2 }, focus: { on: true, show: true }, log: [{ call: 'Counties where oncologists.count > 0 and trials_listed_here = 0 in TX', result: '2 match; showing 2', error: false }], model: 'claude-sonnet-5-5', steps: 2, dropped: [], placeIdOf: r => R.rowMapId(r, 'county') });
test('cardHTML escapes everything the model wrote and has every section in order', () => {
  const h = R.cardHTML(ctxBase());
  assert.ok(!h.includes('<script>'), 'no raw script tag'); assert.ok(h.includes('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;')); assert.ok(!h.includes('<b>bold</b>')); assert.ok(h.includes('&lt;b&gt;bold&lt;/b&gt;')); assert.ok(h.includes('data-q="&lt;i&gt;x&lt;/i&gt;"'));
  const order = ['class="ask-q"', 'class="ask-a"', 'How this was read', 'Or ask:', 'Not in the data', 'class="ask-tbl"', 'class="ask-sum"', 'class="ask-cav"', 'Map now shows:', '(2 outlined)', 'id="ask-focus" checked', 'Read from:', 'How this was answered', 'Follow up:', 'New question', 'does not match patients to trials'];
  let at = -1; for (const s of order) { const i = h.indexOf(s); assert.ok(i > at, `${s} in order (found at ${i}, after ${at})`); at = i; }
  assert.ok(h.includes('href="https://nehaamd.github.io/cancer-trial-access-fullmap/api/all_counties.json"')); assert.ok(!h.includes('javascript:'), 'a bad source url is not a link'); assert.ok(h.includes('as of Nov 3, 2026')); assert.ok(h.includes('incidence 2019–2023'));
  assert.ok(h.includes('model claude-sonnet-5-5')); assert.ok(h.includes('2 model steps')); });
test('an unverified answer omits the answer text and shows the notice, but keeps the table and the map line', () => {
  const ctx = ctxBase(); ctx.verification = { ok: false, issues: ['number 99 not in any tool result'] }; const h = R.cardHTML(ctx);
  assert.ok(!h.includes('Two Texas counties have oncologists')); assert.ok(h.includes(R.UNVERIFIED_NOTICE)); assert.ok(h.includes('class="ask-tbl"')); assert.ok(h.includes('Map now shows:')); assert.ok(h.includes('verification failed: number 99 not in any tool result'));
  assert.equal(R.priorText(ANSWER, ctx.verification), ANSWER.interpretation, 'the follow-up context falls back to the interpretation'); assert.equal(R.priorText(ANSWER, { ok: true }), ANSWER.answer); });
test('SCOPE_TEXT and OTHER_TEXT render as a plain card: no table, no map line, no sources, no follow-ups', () => {
  for (const text of [CAT.SCOPE_TEXT, CAT.OTHER_TEXT]) { const ctx = ctxBase(); ctx.answer = { answer: text, answerable: 'no', not_in_data: ['x'], follow_ups: ['y'] }; const h = R.cardHTML(ctx);
    assert.ok(R.isPlainAnswer(ctx.answer)); assert.ok(h.includes('class="ask-card plain"')); assert.ok(h.includes(R.esc(text).slice(0, 60))); assert.ok(!h.includes('ask-tbl')); assert.ok(!h.includes('Map now shows')); assert.ok(!h.includes('Read from')); assert.ok(!h.includes('Follow up')); assert.ok(!h.includes('Not in the data')); assert.ok(h.includes('does not match patients to trials')); } });
test('answerable partly / no show a tag; a dropped map part is reported; no map -> no map line', () => {
  const ctx = ctxBase(); ctx.answer = { ...ANSWER, answerable: 'no' }; ctx.dropped = ['layer "zzz" is not a county layer on this page']; ctx.mapShows = null; const h = R.cardHTML(ctx);
  assert.ok(h.includes('Not in the data</span>')); assert.ok(h.includes('Not applied to the map: layer &quot;zzz&quot;')); assert.ok(!h.includes('Map now shows'));
  assert.ok(R.cardHTML({ ...ctxBase(), answer: { ...ANSWER, answerable: 'partly' } }).includes('Answered in part')); });
test('the standing note claims a number-by-number check only when the summary passed it; the plain card claims no figures', () => {
  assert.ok(R.cardHTML(ctxBase()).includes('checked against them number by number'));
  const un = ctxBase(); un.verification = { ok: false, issues: ['x'] }; const h = R.cardHTML(un); assert.ok(!h.includes('number by number')); assert.ok(h.includes(R.STANDING_NOTE_UNCHECKED));
  const pl = ctxBase(); pl.answer = { answer: CAT.SCOPE_TEXT, answerable: 'no' }; const hp = R.cardHTML(pl); assert.ok(!hp.includes('Figures are read')); assert.ok(hp.includes('does not match patients to trials')); });
test('a restored table capped at the history limit says how many rows were kept', () => {
  const rows = Array.from({ length: 120 }, (_, i) => ({ id: String(10000 + i), name: `C${i}`, v: i })); const t = { columns: ['id', 'name', 'v'], rows, table: null, unit: 'county', count: 3143, rows_capped: true };
  assert.ok(R.tableHTML(t).includes('100 of 3,143 rows shown'), 'the total is the real count');
  assert.ok(R.tableHTML(t, { showAll: true }).includes('120 of 3,143 rows were kept for this restored view'));
  assert.ok(!R.tableHTML({ ...t, rows_capped: false }, { showAll: true }).includes('were kept'), 'a full table says nothing'); });
test('busy and error cards escape the question and the detail', () => {
  const b = R.busyHTML('<x>', [{ call: 'Counties where a > 1', result: null }, { call: 'c', result: 'r <y>', error: true }]); assert.ok(b.includes('&lt;x&gt;')); assert.ok(b.includes('aria-busy="true"')); assert.ok(b.includes('→ r &lt;y&gt;')); assert.ok(b.includes('<li class="err">'));
  const e = R.errorHTML('<x>', 'The question box is unavailable right now; the map and its filters still work.', '<detail>'); assert.ok(e.includes('class="ask-card err"')); assert.ok(e.includes('&lt;detail&gt;')); });

// ---------- the standard-method label and feedback (ASK_CONTRACT §7) ----------
const M = await import(pathToFileURL(path.resolve(HERE, '..', '..', 'docs', 'ask', 'methods.js')).href);
test('methodFor: a table or highlight from a method call (or one of its sub-calls) names the method; other answers none', () => {
  const calls = { toolu_m: { name: 'method', input: { id: 'oncologists_no_trials_counties', params: { state: 'TX' } } }, toolu_q: { name: 'query', input: { table: 'counties' } } };
  const m = R.methodFor({ table: { from_call: 'toolu_m.1' } }, calls, M.methodById); assert.equal(m.id, 'oncologists_no_trials_counties'); assert.equal(m.title, M.methodById('oncologists_no_trials_counties').title); assert.equal(m.reviewed_by, '');
  assert.equal(R.methodFor({ map: { highlight: { from_call: 'toolu_m' } } }, calls, M.methodById).id, 'oncologists_no_trials_counties');
  assert.equal(R.methodFor({ table: { from_call: 'toolu_q' } }, calls, M.methodById), null); assert.equal(R.methodFor({}, calls, M.methodById), null); assert.equal(R.methodFor({ table: { from_call: 'toolu_x' } }, calls, M.methodById), null); });
test('methodHTML: "Standard method" with the rule; "Reviewed method · name, date" only when both are set; escaped', () => {
  const base = { id: 'x', title: 'Counties <b>with</b> oncologists', rule: 'Class 2 "only"', reviewed_by: '', reviewed_on: '' };
  const h = R.methodHTML(base); assert.ok(h.includes('Standard method:')); assert.ok(h.includes('Counties &lt;b&gt;with&lt;/b&gt; oncologists')); assert.ok(h.includes('title="Class 2 &quot;only&quot;"')); assert.ok(!h.includes('Reviewed'));
  assert.ok(!R.methodHTML({ ...base, reviewed_by: 'Neha Agrawal' }).includes('Reviewed'), 'a name without a date is not a review');
  const r = R.methodHTML({ ...base, reviewed_by: 'Neha Agrawal', reviewed_on: '2026-11-20' }); assert.ok(r.includes('Reviewed method · Neha Agrawal, Nov 20, 2026')); assert.ok(!r.includes('Standard method'));
  assert.equal(R.methodHTML(null), '');
  const card = R.cardHTML({ ...ctxBase(), method: base }); assert.ok(card.indexOf('Standard method:') > card.indexOf('class="ask-a"') && card.indexOf('Standard method:') < card.indexOf('How this was read'), 'the label sits under the answer');
  assert.ok(!card.includes('computed for this question')); assert.ok(R.cardHTML(ctxBase()).includes('computed for this question'), 'an answer without a method says so in the details'); });
test('no method in the library is marked reviewed by code: reviewed_by and reviewed_on start empty', () => {
  assert.ok(M.METHODS.length >= 28, 'about 30 methods: ' + M.METHODS.length);
  for (const m of M.METHODS) { assert.equal(m.reviewed_by, '', m.id); assert.equal(m.reviewed_on, '', m.id); assert.ok(!M.isReviewed(m)); assert.ok(m.title && m.rule && m.example && Array.isArray(m.params) && Array.isArray(m.steps), m.id); } });
test('feedbackHTML: Yes / No and the report link; after a vote the thanks replace the buttons', () => {
  const h = R.feedbackHTML(ctxBase()); assert.ok(h.includes('Was this right?')); assert.ok(h.includes('data-v="yes"') && h.includes('data-v="no"')); assert.ok(h.includes('class="ask-report" href="https://github.com/nehaamd/cancer-trial-access-fullmap/issues/new?title=')); assert.ok(h.includes('target="_blank" rel="noopener"'));
  const t = R.feedbackHTML({ ...ctxBase(), feedback: 'no' }); assert.ok(t.includes('Thanks — noted.')); assert.ok(!t.includes('ask-fb-b')); assert.ok(t.includes('Report a problem'));
  assert.ok(R.cardHTML(ctxBase()).includes('Was this right?')); const pl = ctxBase(); pl.answer = { answer: CAT.SCOPE_TEXT, answerable: 'no' }; assert.ok(R.cardHTML(pl).includes('Was this right?'), 'the plain card has it too'); });
test('feedbackPayload: the documented fields, capped, no visitor identifier, ≤ 20 KB', () => {
  const ctx = { ...ctxBase(), answer: { ...ANSWER, answer: 'x'.repeat(5000) }, calls: Array.from({ length: 40 }, (_, i) => ({ name: i % 2 ? 'query' : 'final_answer', input: { table: 'counties', pad: 'y'.repeat(2000) } })), vintages: { data_as_of: '2026-11-03' } };
  const p = R.feedbackPayload(ctx, 'no');
  assert.deepEqual(Object.keys(p).sort(), ['answer_text', 'data_as_of', 'interpretation', 'kind', 'method', 'model', 'q', 'steps', 'v', 'verdict', 'verified'].sort());
  assert.equal(p.v, 3); assert.equal(p.kind, 'feedback'); assert.equal(p.verdict, 'no'); assert.ok(p.answer_text.length <= 1500); assert.ok(p.steps.length <= 12 && p.steps.every(s => s.tool === 'query' && s.input.length <= 300)); assert.equal(p.data_as_of, '2026-11-03');
  assert.ok(new TextEncoder().encode(JSON.stringify(p)).length <= R.FEEDBACK_MAX_BYTES); assert.equal(R.feedbackPayload(ctx, 'maybe').verdict, 'no'); assert.equal(R.feedbackPayload(ctx, 'yes').verdict, 'yes'); });
test('issueURL: title and a body with the question, answer, reading, steps and data date; stays under 6,000 characters', () => {
  const ctx = { ...ctxBase(), calls: [{ name: 'query', input: { table: 'counties', where: [{ field: 'state', op: '=', value: 'TX' }] } }], vintages: { data_as_of: '2026-11-03' } };
  const u = R.issueURL(ctx); assert.ok(u.startsWith('https://github.com/nehaamd/cancer-trial-access-fullmap/issues/new?title=' + encodeURIComponent('Ask the map: problem with an answer') + '&body='));
  const body = decodeURIComponent(u.split('&body=')[1]); for (const s of ['**Question:** ' + ctx.q, '**Answer:** ' + ANSWER.answer, '**How it was read:** ' + ANSWER.interpretation, '- query {"table":"counties"', '**Data as of:** 2026-11-03']) assert.ok(body.includes(s), s);
  const big = R.issueURL({ ...ctx, answer: { ...ANSWER, answer: 'é'.repeat(1500), interpretation: 'ü'.repeat(600) }, calls: Array.from({ length: 12 }, () => ({ name: 'query', input: { pad: 'z'.repeat(400) } })) }); assert.ok(big.length <= R.ISSUE_URL_MAX, 'capped: ' + big.length); assert.ok(decodeURIComponent(big.split('&body=')[1]).includes('**Question:**'));
  const un = decodeURIComponent(R.issueURL({ ...ctx, verification: { ok: false, issues: ['x'] } }).split('&body=')[1]); assert.ok(un.includes('did not pass its check')); });

console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
