#!/usr/bin/env node
/* A stand-in for the "Ask the map" worker (ASK_CONTRACT.md §3) for exercising the client (docs/ask/ask.js) locally, without a model.
   It plays a fixed script: step 1 asks the client to run one `query` (and, to test the rule, a `final_answer` alongside it); step 2
   returns a verified final answer whose map and table point at that query. Questions that contain certain words take other paths:
     "unverified"  -> the answer comes back with verification.ok = false      "scope"  -> the fixed SCOPE_TEXT, no map
     "limit"       -> 429 with retry_after_s                                   "fail"   -> 502 with a detail
     "slow"        -> no reply for 100 s (the client's 90 s timeout)           "text"   -> a text-only answer (no map, no table)
     "method"      -> a standard-method call, then an answer whose table comes from its sub-call (the card's method label)
   POST /feedback is logged to the console and answered {ok:true}.
   Run:  node worker/tests/fixtures/stub_worker.js [port=8766]   then on the map page (served on localhost):
         localStorage.setItem('askUrl', 'http://localhost:8766/ask'); localStorage.setItem('askEngineUrl', '/worker/tests/fixtures/engine.stub.js')
   (with the repository root served: python3 -m http.server 8765 -> http://localhost:8765/docs/map.html). Signatures are not checked here. */
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const CAT = await import(pathToFileURL(path.resolve(HERE, '..', '..', '..', 'docs', 'ask', 'catalog.js')).href);
const port = parseInt(process.argv[2]) || 8766;
const json = (res, status, body, extra = {}) => { res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store', 'access-control-allow-origin': '*', 'access-control-allow-headers': 'content-type', ...extra }); res.end(JSON.stringify(body)); };
const QUERY = { table: 'counties', where: [{ field: 'state', op: '=', value: 'TX' }, { field: 'oncologists.count', op: '>', value: 0 }, { field: 'trials_listed_here', op: '=', value: 0 }], order_by: [{ field: 'pop55', dir: 'desc' }], limit: 50 };
http.createServer((req, res) => {
  if (req.method === 'OPTIONS') return json(res, 204, {});
  if (req.method !== 'POST') return json(res, 405, { error: 'POST only' });
  if (req.url.startsWith('/feedback')) { let raw = ''; req.on('data', d => { raw += d; }); req.on('end', () => { console.log('feedback ' + raw.slice(0, 300)); json(res, 200, { ok: true }); }); return; }
  let raw = ''; req.on('data', d => { raw += d; }); req.on('end', () => {
    let b; try { b = JSON.parse(raw); } catch (e) { return json(res, 400, { error: 'bad JSON' }); }
    const q = String(b.q || ''), turns = Array.isArray(b.turns) ? b.turns : [], low = q.toLowerCase();
    console.log(`step ${turns.length + 1}  q="${q.slice(0, 60)}"  prior=${(b.prior || []).length}  unit=${b.client && b.client.unit}${turns.length ? '  results=' + turns[turns.length - 1].results.map(r => r.tool_use_id + ':' + r.content.length + 'B' + (r.is_error ? ' err' : '')).join(',') : ''}`);
    if (/\blimit\b/.test(low)) return json(res, 429, { error: 'Too many questions from this address in a minute.', retry_after_s: 8 });
    if (/\bfail\b/.test(low)) return json(res, 502, { error: 'The model did not answer.', detail: 'upstream 529 overloaded' });
    if (/\bslow\b/.test(low)) return;   // never answers
    if (/\bscope\b/.test(low)) return json(res, 200, { v: 3, kind: 'answer', step: 1, assistant: [], sig: 'stub', answer: { answer: CAT.SCOPE_TEXT, answerable: 'no', not_in_data: ['Eligibility is not in the data.'] }, verification: { ok: true, issues: [], retries: 0 }, model: 'stub' });
    if (/\btext\b/.test(low)) return json(res, 200, { v: 3, kind: 'answer', step: 1, assistant: [], sig: 'stub', answer: { answer: 'The data covers 3,143 counties, 436 districts and 51 states.', answerable: 'partly' }, verification: { ok: true, issues: [], retries: 0 }, model: 'stub' });
    if (/\bmethod\b/.test(low)) {   // a standard method: the card shows "Standard method: <title>"
      const M = { id: 'oncologists_no_trials_counties', params: { state: 'TX' } };
      if (turns.length === 0) return json(res, 200, { v: 3, kind: 'tools', step: 1, assistant: [{ type: 'tool_use', id: 'toolu_m', name: 'method', input: M }], sig: 'stub', calls: [{ id: 'toolu_m', name: 'method', input: M }] });
      const answer = { answer: 'Texas counties with oncologists but no recruiting trial, by the standard method.', answerable: 'yes', interpretation: 'The standard method for counties with oncologists but no trials.', map: { unit: 'county', layer: 'onc', state: 'TX', highlight: { from_call: 'toolu_m' }, highlight_label: 'Counties with oncologists but no recruiting trial' }, table: { from_call: 'toolu_m.1' }, sources: ['counties'] };
      return json(res, 200, { v: 3, kind: 'answer', step: 2, assistant: [], sig: 'stub', answer, verification: { ok: true, issues: [], retries: 0 }, model: 'stub-model' });
    }
    if (turns.length === 0) return json(res, 200, { v: 3, kind: 'tools', step: 1, assistant: [{ type: 'tool_use', id: 'toolu_1', name: 'query', input: QUERY }, { type: 'tool_use', id: 'toolu_2', name: 'final_answer', input: {} }], sig: 'stub', calls: [{ id: 'toolu_1', name: 'query', input: QUERY }, { id: 'toolu_2', name: 'final_answer', input: {} }] });
    const r1 = turns[turns.length - 1].results.find(r => r.tool_use_id === 'toolu_1'); let count = '?'; try { count = JSON.parse(r1.content).count; } catch (e) { /* keep ? */ }
    const unverified = /\bunverified\b/.test(low);
    const answer = { answer: `${count} Texas counties have oncologists with a Medicare practice location but no recruiting trial with a site in the county; Hidalgo County is the largest, with 31 oncologists.`, answerable: 'yes',
      interpretation: 'Counties in Texas with at least one oncologist (oncologists.count > 0) and no recruiting trial with a site in the county (trials_listed_here = 0), largest first by residents 55+.',
      alternatives: ['Which Texas districts have the most residents in counties with oncologists but no trials?', 'Which Texas counties have no trial within 60 road-miles?'],
      not_in_data: unverified ? [] : ['Whether those oncologists refer patients to trials elsewhere is not in the data.'],
      caveats: ['An oncologist with locations in two counties is counted in both.', 'A county figure can turn on a single trial.'],
      map: { unit: 'county', layer: 'onc', params: { site: 'lung' }, state: 'TX', highlight: { from_call: 'toolu_1' }, highlight_label: 'Counties with oncologists but no recruiting trial' },
      table: { from_call: 'toolu_1' }, sources: ['counties'], follow_ups: ['How many residents 55+ live in those counties?', 'Which of them are rural?', 'Who represents Hidalgo County?'] };
    return json(res, 200, { v: 3, kind: 'answer', step: turns.length + 1, assistant: [{ type: 'tool_use', id: 'toolu_3', name: 'final_answer', input: answer }], sig: 'stub', answer, verification: unverified ? { ok: false, issues: ['number 31 is not in any tool result'], retries: 2 } : { ok: true, issues: [], retries: 0 }, model: 'stub-model' });
  });
}).listen(port, () => console.log(`stub worker on http://localhost:${port}/ask`));
