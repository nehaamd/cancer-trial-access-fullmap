#!/usr/bin/env node
// Live evaluation of "Ask the map" v3 (ASK_CONTRACT.md §8): the questions in eval_questions.json through the real model and the
// real engine, checked against facts computed independently by eval_expected.py (eval_expected.json). Vocabulary: EVAL.md.
//
//   node worker/tests/eval.js [--max N] [--only substr] [--worker URL] [--model NAME] [--verbose] [--json out.json] [--md summary.md]
//                             [--concurrency 3] [--timeout 120] [--origin https://nehaamd.github.io]
//
// In-process (default): needs ANTHROPIC_API_KEY; imports step() from worker/src/loop.js and runs the tools with docs/ask/engine.js.
// Over HTTP (--worker URL): posts each step to a deployed worker; the tools still run locally with the same engine.
// Exit 1 when the pass rate is below 90 % or any scope/other/injection case fails (hard gates). Node 22 ESM, no dependencies.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { AsyncLocalStorage } from 'node:async_hooks';
import { runChecks, HARD_GATE_CATS } from './eval_checks.js';

const HERE = path.dirname(fileURLToPath(import.meta.url)); const ROOT = path.resolve(HERE, '..', '..');
const argv = process.argv.slice(2);
const opt = (name, dflt = null) => { const i = argv.indexOf(name); return i >= 0 && i + 1 < argv.length ? argv[i + 1] : dflt; };
const flag = name => argv.includes(name);
const MAX = parseInt(opt('--max', '0')) || Infinity, ONLY = (opt('--only', '') || '').toLowerCase(), WORKER = opt('--worker'), MODEL = opt('--model') || process.env.MODEL || 'claude-sonnet-5-5';
const VERBOSE = flag('--verbose'), JSON_OUT = opt('--json'), MD_OUT = opt('--md'), CONC = Math.max(1, parseInt(opt('--concurrency', '3')) || 3), TIMEOUT_MS = (parseInt(opt('--timeout', '120')) || 120) * 1000;
const MAX_TURNS = 8, RESULT_CAP = 24 * 1024, MIN_PASS = 0.9;
const die = (msg, code = 2) => { console.error(`eval: ${msg}`); process.exit(code); };
const exists = p => fs.existsSync(p);
const short = (v, n = 160) => { const s = typeof v === 'string' ? v : JSON.stringify(v); return s && s.length > n ? s.slice(0, n - 1) + '…' : s; };

// ---------- inputs ----------
const catalog = await import(pathToFileURL(path.join(ROOT, 'docs/ask/catalog.js')).href);
const qfile = path.join(HERE, 'eval_questions.json'), efile = path.join(HERE, 'eval_expected.json');
if (!exists(qfile)) die(`${qfile} missing`);
if (!exists(efile)) die(`${efile} missing — run: python3 -I worker/tests/eval_expected.py`);
let questions = JSON.parse(fs.readFileSync(qfile, 'utf8')).questions; const expected = JSON.parse(fs.readFileSync(efile, 'utf8'));
if (expected.data_as_of && expected.data_as_of !== JSON.parse(fs.readFileSync(path.join(ROOT, 'docs/api/index.json'), 'utf8')).data_as_of) console.error(`eval: warning — eval_expected.json is from data_as_of ${expected.data_as_of}, the API is newer; re-run eval_expected.py`);
questions = questions.filter(q => !ONLY || q.id.toLowerCase() === ONLY || q.id.toLowerCase().includes(ONLY) || (q.cat || '').toLowerCase().includes(ONLY) || q.q.toLowerCase().includes(ONLY)).slice(0, MAX);
if (!questions.length) die('no questions selected');

// ---------- the engine (tools run locally in both modes) ----------
const enginePath = path.join(ROOT, 'docs/ask/engine.js');
if (!exists(enginePath)) die('docs/ask/engine.js is not there yet (ASK_CONTRACT §11); the evaluation runs the tools with it. Nothing to evaluate until it lands.');
const { createEngine } = await import(pathToFileURL(enginePath).href);
if (typeof createEngine !== 'function') die('docs/ask/engine.js does not export createEngine({root})');
const engine = createEngine({ root: ROOT, onProgress: t => { if (VERBOSE) console.error(`  engine: ${t}`); } });
const t0load = Date.now(); await engine.load(); console.error(`engine loaded in ${Date.now() - t0load} ms${engine.loaded ? ' (' + Object.entries(engine.loaded.optional || {}).filter(([, v]) => !v).map(([k]) => k + ' not loaded').join(', ') + ')' : ''}`.replace(' ()', ''));
let truncateResult = r => { let s = JSON.stringify(r === undefined ? null : r); if (Buffer.byteLength(s) <= RESULT_CAP) return s; const key = Object.keys(r || {}).find(k => Array.isArray(r[k]) && r[k].length); if (key) { let n = r[key].length; while (n > 1) { n = Math.floor(n / 2); s = JSON.stringify({ ...r, [key]: r[key].slice(0, n), truncated: `…(truncated): ${key} cut to ${n}` }); if (Buffer.byteLength(s) <= RESULT_CAP) return s; } } return s.slice(0, RESULT_CAP - 20) + '…(truncated)'; };
try { const R = await import(pathToFileURL(path.join(ROOT, 'docs/ask/render.js')).href); if (typeof R.truncateResult === 'function') truncateResult = R.truncateResult; } catch (e) { /* the client's helper is optional here */ }

// ---------- one protocol step: in-process (loop.js) or over HTTP ----------
const usageStore = new AsyncLocalStorage();   // per-question token tally, attributed through the async context even with concurrency
function tally(resp) { const u = usageStore.getStore(); if (!u || !resp || !resp.usage) return; u.input += resp.usage.input_tokens || 0; u.output += resp.usage.output_tokens || 0; u.cache_read += resp.usage.cache_read_input_tokens || 0; u.cache_write += resp.usage.cache_creation_input_tokens || 0; u.calls++; }
let doStep, modeLabel;
if (WORKER) {
  modeLabel = `worker ${WORKER}`; const ORIGIN = opt('--origin') || new URL(catalog.SITE_BASE).origin;
  doStep = async (body, signal) => {
    for (let attempt = 0; attempt < 5; attempt++) {
      const r = await fetch(WORKER, { method: 'POST', headers: { 'content-type': 'application/json', origin: ORIGIN }, body: JSON.stringify(body), signal });
      const j = await r.json().catch(() => ({}));
      if (r.status === 429) { const wait = Math.min(120, Math.max(2, Number(j.retry_after_s) || 10)); console.error(`  429: waiting ${wait} s`); await new Promise(res => setTimeout(res, wait * 1000)); continue; }
      if (!r.ok) { const e = new Error(`HTTP ${r.status}: ${j.error || ''} ${j.detail || ''}`.trim()); e.status = r.status; throw e; }
      if (j.usage) tally(j); return j;
    }
    throw new Error('rate limited five times in a row');
  };
} else {
  const FAKE = flag('--fake');   // smoke test of the runner with a scripted model (no key, no network): exercises loop.js, signing, the engine, verification and the checks
  if (!process.env.ANTHROPIC_API_KEY && !FAKE) die('ANTHROPIC_API_KEY is not set (or pass --worker URL to evaluate a deployed worker, or --fake to smoke-test the runner)');
  const loopPath = path.join(ROOT, 'worker/src/loop.js');
  if (!exists(loopPath)) die('worker/src/loop.js is not there yet (ASK_CONTRACT §3: step(body, env, callModel)); use --worker URL against a deployed worker, or wait for it.');
  const loop = await import(pathToFileURL(loopPath).href);
  if (typeof loop.step !== 'function') die('worker/src/loop.js does not export step(body, env, callModel)');
  const env = { ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY || (FAKE ? 'fake-key' : ''), MODEL, SITE_BASE: catalog.SITE_BASE, ALLOWED_ORIGINS: '', MAX_STEPS: '8' };
  if (process.env.MODEL_FAST) env.MODEL_FAST = process.env.MODEL_FAST;
  if (process.env.ASK_SIGNING_SECRET) env.ASK_SIGNING_SECRET = process.env.ASK_SIGNING_SECRET;
  // the model call: the worker's own when it exports one, else the fetch exactly as §3 describes it
  let base = null;
  if (FAKE) { base = fakeModel; modeLabel = 'in-process (FAKE scripted model — smoke test, results are not an evaluation)'; }
  else for (const [file, names] of [['worker/src/loop.js', ['callModel', 'defaultCallModel']], ['worker/src/model.js', ['callModel', 'default']]]) {
    const p = path.join(ROOT, file); if (!exists(p)) continue;
    try { const m = await import(pathToFileURL(p).href); const n = names.find(x => typeof m[x] === 'function'); if (n) { base = m[n]; modeLabel = `in-process (${file} ${n})`; break; } } catch (e) { /* try the next */ }
  }
  if (!base) {
    modeLabel = 'in-process (eval fetch)';
    base = async (payload, env2, extra) => {
      const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), 25000);
      try {
        const r = await fetch((process.env.ANTHROPIC_BASE_URL || 'https://api.anthropic.com').replace(/\/$/, '') + '/v1/messages', { method: 'POST', headers: { 'content-type': 'application/json', 'x-api-key': env2.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' }, body: JSON.stringify({ model: MODEL, ...payload }), signal: (extra && extra.signal) || ctrl.signal });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { const e = new Error(`model HTTP ${r.status}: ${short(JSON.stringify(j), 200)}`); e.status = r.status; throw e; }
        return j;
      } finally { clearTimeout(timer); }
    };
  }
  // whatever the argument order, find the request body and the env, call, and tally usage from the response
  const callModel = async (...args) => {
    const payload = args.find(a => a && typeof a === 'object' && Array.isArray(a.messages)); const e2 = args.find(a => a && typeof a === 'object' && a.ANTHROPIC_API_KEY) || env;
    const resp = await base(...(args.length ? args : [payload, e2]));
    tally(resp); return resp;
  };
  doStep = async (body) => {
    const r = await loop.step(body, env, callModel);
    if (r && typeof r.status === 'number' && r.body !== undefined) { const b = typeof r.body === 'string' ? JSON.parse(r.body) : r.body; if (r.status >= 400) { const e = new Error(`HTTP ${r.status}: ${b && b.error || ''} ${b && b.detail || ''}`.trim()); e.status = r.status; throw e; } return b; }
    if (r && typeof r.json === 'function') { const b = await r.json(); if (r.status >= 400) { const e = new Error(`HTTP ${r.status}: ${b && b.error || ''} ${b && b.detail || ''}`.trim()); e.status = r.status; throw e; } return b; }
    if (r && r.error && !r.kind) { const e = new Error(String(r.error) + (r.detail ? ' ' + r.detail : '')); e.status = r.status; throw e; }
    return r;
  };
}

// ---------- a scripted model for --fake: one query (or site_info), then a final_answer built from the result ----------
let fakeN = 0;
async function fakeModel(payload) {
  const msgs = payload.messages || []; const last = msgs[msgs.length - 1]; const q = String((msgs.find(m => m.role === 'user' && typeof m.content === 'string') || {}).content || '');
  const id = () => `toolu_fake_${++fakeN}`;
  const usage = { input_tokens: 1000, output_tokens: 100, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
  const mk = (name, input) => ({ id: id(), type: 'tool_use', name, input, content: [{ type: 'tool_use', id: `toolu_fake_${fakeN}`, name, input }], usage, stop_reason: 'tool_use' });
  if (payload.tool_choice && payload.tool_choice.type === 'tool') return mk('final_answer', { answer: 'No answer.', answerable: 'no', interpretation: 'forced', not_in_data: ['forced final'], map: null, sources: [] });
  const prevResults = last && Array.isArray(last.content) ? last.content.filter(b => b.type === 'tool_result') : [];
  if (!prevResults.length) {
    const st = Object.entries(catalog.STATES).find(([, nm]) => new RegExp('\\b' + nm + '\\b', 'i').test(q));
    if (/what is|how are|what does|what can i do/i.test(q) && !st) return mk('site_info', { topic: /3521|4440|act\b/i.test(q) ? 'bills' : /road-mile/i.test(q) ? 'methods' : /what can i do/i.test(q) ? 'how_to_act' : 'definitions' });
    return mk('query', { table: /district/i.test(q) ? 'districts' : /state/i.test(q) && !st ? 'states' : 'counties', where: st ? [{ field: 'state', op: '=', value: st[0] }] : [], order_by: [{ field: 'pct_lt20_trials_within_60rdmi', dir: 'desc' }], limit: 5 });
  }
  let r = {}; try { r = JSON.parse(prevResults[0].content); } catch (e) { /* keep {} */ }
  if (r.error) return mk('final_answer', { answer: 'The data does not have that.', answerable: 'no', interpretation: 'fake: the tool returned an error', not_in_data: [String(r.error).slice(0, 100)], sources: [] });
  if (r.text) return mk('final_answer', { answer: String(r.text).split(/(?<=\.)\s/).slice(0, 2).join(' ').slice(0, 600), answerable: 'yes', interpretation: 'fake: site text', sources: [], alternatives: [], not_in_data: [], caveats: [] });
  const row = (r.rows || [])[0]; const callId = prevResults[0].tool_use_id; const unit = { counties: 'county', districts: 'district', states: 'state' }[r.table] || 'county';
  return mk('final_answer', { answer: row ? `${row.name} leads with ${row.pct_lt20_trials_within_60rdmi}% of residents 55+ short of trials; ${r.count} places match.` : `${r.count} places match.`, answerable: 'yes', interpretation: 'fake: top rows by the headline measure', alternatives: [], not_in_data: [], caveats: [],
    map: { unit, layer: unit === 'county' ? 'short' : 'l20', highlight: { from_call: callId }, highlight_label: 'fake' }, table: { from_call: callId }, sources: [r.table], follow_ups: [] });
}

// ---------- one question ----------
async function askOne(q) {
  const started = Date.now(); const usage = { input: 0, output: 0, cache_read: 0, cache_write: 0, calls: 0 };
  const transcript = [], calls = {}, results = {}; let steps = 0, answer = null, verification = null, kind = null, model = null, error = null;
  const body = { v: 3, q: q.q, turns: [], prior: Array.isArray(q.prior) ? q.prior : [], client: { page: 'eval', unit: 'county' } };
  const work = usageStore.run(usage, async () => {
    for (let i = 0; i < MAX_TURNS + 1; i++) {
      const resp = await doStep(body);
      steps = Number.isFinite(resp.step) ? resp.step : i + 1; model = resp.model || model;
      if (resp.kind === 'tools' && Array.isArray(resp.calls)) {
        const many = resp.calls.length > 1; const entry = { step: steps, assistant: resp.assistant, calls: [] }; transcript.push(entry);
        const out = await Promise.all(resp.calls.map(async c => {
          const id = String(c.id || ''), name = String(c.name || ''), input = c.input && typeof c.input === 'object' ? c.input : {}; calls[id] = { name, input };
          if (name === 'final_answer') { entry.calls.push({ id, name, input, note: 'final_answer inside a tools step' }); return { tool_use_id: id, content: JSON.stringify(many ? { ok: true, note: 'call final_answer alone, after the other results' } : { ok: true, note: 'final_answer is read by the server' }), is_error: false }; }
          let r; try { r = await engine.run(name, input, id); } catch (e) { r = { error: 'engine failure: ' + (e && e.message || e) }; } if (r === undefined || r === null) r = { error: 'the tool returned nothing' };
          results[id] = r; const content = truncateResult(r);
          entry.calls.push({ id, name, input, described: safe(() => engine.describeCall(name, input)), result_summary: safe(() => engine.describeResult(name, input, r)), result: JSON.parse(content), is_error: !!r.error });
          return { tool_use_id: id, content, is_error: !!r.error };
        }));
        body.turns.push({ assistant: resp.assistant, sig: resp.sig, results: out }); continue;
      }
      if (resp.kind === 'answer') { kind = 'answer'; answer = resp.answer || {}; verification = resp.verification || null; transcript.push({ step: steps, assistant: resp.assistant, answer, verification }); return; }
      kind = resp.kind || 'unknown'; error = `unexpected reply: ${short(resp, 200)}`; return;
    }
    error = `no answer after ${MAX_TURNS} turns`;
  });
  try { await Promise.race([work, new Promise((_, rej) => setTimeout(() => rej(new Error(`timeout after ${TIMEOUT_MS / 1000} s`)), TIMEOUT_MS))]); }
  catch (e) { error = e && e.message || String(e); }
  const full = {}; for (const id of Object.keys(calls)) { const f = safe(() => engine.full(id)); if (f && Array.isArray(f.ids)) full[id] = { ids: f.ids, returned_ids: f.returned_ids, filtered: f.filtered, ordered: f.ordered, unit: f.unit, n: f.ids.length }; }
  // the ids the map would outline, by the engine's own rule (a ranking outlines the rows returned; a filter every match)
  const hl = answer && answer.map ? safe(() => engine.highlightIds(answer.map.highlight)) : null; if (hl) full.__highlight = hl;
  const res = { kind, answer, verification, steps, full, error };
  const check = runChecks(q, expected.questions[q.id], res);
  return { id: q.id, cat: q.cat, q: q.q, prior: q.prior || null, note: q.note || null, pass: check.pass, failures: check.failures, notes: check.notes, hard_gate: HARD_GATE_CATS.has(q.cat), steps, latency_ms: Date.now() - started, usage, model,
    answerable: answer && answer.answerable, interpretation: answer && answer.interpretation, answer_text: answer && answer.answer, map: answer && answer.map, verification, error, calls: Object.entries(calls).map(([id, c]) => ({ id, ...c, ids: full[id] ? full[id].n : undefined })), transcript };
}
function safe(fn) { try { return fn(); } catch (e) { return null; } }

// ---------- run with a little concurrency ----------
console.error(`eval: ${questions.length} questions, ${modeLabel}, model ${MODEL}, concurrency ${CONC}, ${TIMEOUT_MS / 1000} s each`);
const T_START = Date.now();
const out = new Array(questions.length); let next = 0;
async function worker() { while (next < questions.length) { const i = next++; const q = questions[i]; try { out[i] = await askOne(q); } catch (e) { out[i] = { id: q.id, cat: q.cat, q: q.q, pass: false, failures: [`runner error: ${e && e.message || e}`], hard_gate: HARD_GATE_CATS.has(q.cat), steps: 0, latency_ms: 0, usage: {}, transcript: [] }; } report(out[i]); } }
function report(r) {
  const reason = r.pass ? (r.notes && r.notes.length && VERBOSE ? ` (${r.notes.join('; ')})` : '') : ` — ${r.failures.join('; ')}`;
  console.log(`${r.pass ? 'PASS' : 'FAIL'} ${r.id} [${r.cat}${r.hard_gate ? ', hard gate' : ''}] ${r.steps} steps ${r.latency_ms} ms  ${r.q}${reason}`);
  if (VERBOSE) {
    if (r.interpretation) console.log(`      read as: ${r.interpretation}`);
    if (r.answer_text) console.log(`      answer: ${short(r.answer_text, 400)}`);
    if (r.map) console.log(`      map: ${short(r.map, 200)}`);
    for (const t of r.transcript || []) for (const c of t.calls || []) console.log(`      step ${t.step}: ${c.described || c.name + ' ' + short(c.input, 120)} → ${c.result_summary || short(c.result, 100)}`);
    if (r.verification && !r.verification.ok) console.log(`      verification: ${short(r.verification.issues, 300)}`);
  }
}
await Promise.all(Array.from({ length: Math.min(CONC, questions.length) }, worker));

// ---------- summary ----------
const n = out.length, passed = out.filter(r => r.pass).length, rate = passed / n;
const hardFails = out.filter(r => r.hard_gate && !r.pass);
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
const withSteps = out.filter(r => r.steps > 0);
const tok = out.reduce((a, r) => ({ input: a.input + (r.usage.input || 0), output: a.output + (r.usage.output || 0), cache_read: a.cache_read + (r.usage.cache_read || 0), cache_write: a.cache_write + (r.usage.cache_write || 0), calls: a.calls + (r.usage.calls || 0) }), { input: 0, output: 0, cache_read: 0, cache_write: 0, calls: 0 });
const byCat = {}; for (const r of out) { const c = byCat[r.cat] || (byCat[r.cat] = { n: 0, pass: 0 }); c.n++; if (r.pass) c.pass++; }
console.log('');
console.log(`${passed}/${n} pass (${(rate * 100).toFixed(1)} %); mean ${mean(withSteps.map(r => r.steps)).toFixed(1)} steps; mean ${Math.round(mean(out.map(r => r.latency_ms)))} ms; ${tok.calls ? `${tok.calls} model calls, ${tok.input.toLocaleString()} input + ${tok.output.toLocaleString()} output tokens (cache read ${tok.cache_read.toLocaleString()}, written ${tok.cache_write.toLocaleString()})` : 'token usage not returned'}`);
console.log('by category: ' + Object.entries(byCat).sort().map(([c, v]) => `${c} ${v.pass}/${v.n}`).join(', '));
if (hardFails.length) console.log(`HARD GATE FAILED: ${hardFails.map(r => r.id).join(', ')}`);
const ok = rate >= MIN_PASS && !hardFails.length;
console.log(ok ? `eval: PASS (≥ ${MIN_PASS * 100} % and every hard gate held)` : `eval: FAIL (${rate < MIN_PASS ? `pass rate ${(rate * 100).toFixed(1)} % < ${MIN_PASS * 100} %` : ''}${rate < MIN_PASS && hardFails.length ? '; ' : ''}${hardFails.length ? `${hardFails.length} hard-gate failure(s)` : ''})`);

const summary = { started: new Date(T_START).toISOString(), finished: new Date().toISOString(), wall_ms: Date.now() - T_START, mode: modeLabel, model: MODEL, n, passed, pass_rate: rate, mean_steps: mean(withSteps.map(r => r.steps)), mean_latency_ms: mean(out.map(r => r.latency_ms)), tokens: tok, by_category: byCat, hard_gate_failures: hardFails.map(r => r.id), ok, data_as_of: expected.data_as_of };
if (JSON_OUT) { fs.writeFileSync(JSON_OUT, JSON.stringify({ summary, results: out }, null, 1)); console.error(`eval: wrote ${JSON_OUT}`); }
if (MD_OUT) {
  const md = [`## Ask the map eval — ${ok ? 'PASS' : 'FAIL'}`, '', `${passed}/${n} pass (${(rate * 100).toFixed(1)} %), mean ${summary.mean_steps.toFixed(1)} steps, mean ${Math.round(summary.mean_latency_ms)} ms, model ${MODEL}, ${modeLabel}, data as of ${expected.data_as_of}${tok.calls ? `, ${tok.input.toLocaleString()} input + ${tok.output.toLocaleString()} output tokens` : ''}.`, hardFails.length ? `**Hard gates failed:** ${hardFails.map(r => r.id).join(', ')}` : 'Hard gates (scope / other / injection) held.', '',
    '| id | category | result | steps | ms | reason / interpretation |', '|---|---|---|---|---|---|',
    ...out.map(r => `| ${r.id} | ${r.cat} | ${r.pass ? 'PASS' : '**FAIL**'} | ${r.steps} | ${r.latency_ms} | ${(r.pass ? (r.interpretation || '') : r.failures.join('; ')).replace(/\|/g, '\\|').slice(0, 300)} |`), ''];
  fs.writeFileSync(MD_OUT, md.join('\n')); console.error(`eval: wrote ${MD_OUT}`);
}
process.exit(ok ? 0 : 1);
