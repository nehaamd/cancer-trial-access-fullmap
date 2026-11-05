/* Ask the map v3 — the client (an ES module loaded by map.html after the map's own script; see ASK_CONTRACT.md §3, §6, §7, §11).
   It mounts the question box (SITE.mountAskBox), drives the step protocol against the worker (SITE.ASK_URL), runs every tool call
   the model makes through the engine in this browser (docs/ask/engine.js, over the same data the map shows), shows the progress
   line and the busy card, renders the answer card into the figures column, applies the answer's map view, keeps follow-ups, and
   restores an open answer on Back/Forward. The map page hands it a few hooks (window.__askHooks, set in map.html): applyURL,
   highlight, setFocus, placeName, selectPlace, setTab, stateOf, mapShows, layers, unit, tab, paneHost, layout.
   Nothing here computes a figure: the engine reads the files, the worker verifies the summary, this file only shows the result.
   Pure parts (validation, query string, truncation, sorting, formatting, the card's HTML) live in render.js and are tested in Node. */
import { TABLES } from './catalog.js';
import * as R from './render.js';
import { methodById } from './methods.js';

const SITE = window.SITE || {};
const H = () => window.__askHooks || {};
// local development only (localhost): localStorage askUrl / askEngineUrl point the box at a stub worker or engine (worker/tests/fixtures/)
const devOverride = key => { try { return ['localhost', '127.0.0.1'].includes(location.hostname) ? localStorage.getItem(key) || '' : ''; } catch (e) { return ''; } };
const ASK_URL = devOverride('askUrl') || SITE.ASK_URL || '';
const TIMEOUT_S = Number(SITE.ASK_TIMEOUT_S) || 90;
const FEEDBACK_URL = (() => { try { return ASK_URL ? new URL(ASK_URL, location.href).origin + '/feedback' : ''; } catch (e) { return ''; } })();   // the worker's /feedback route (ASK_CONTRACT §7)
const MAX_TURNS = 10;          // the worker forces final_answer at its 8th model call; this is the client's own stop
const PRIOR_MAX = 3;           // earlier (question, answer) pairs sent with a follow-up
const HISTORY_ROWS = 2000;     // table rows kept in the history entry (Back/Forward restores the card without the engine)
const PH_FOLLOW = 'Ask a follow-up, or a new question…';
const LOAD_TEXT = 'Loading the data files (first question only)…';
const FOCUS_KEY = 'askFocus';  // sessionStorage: the reader's own Focus choice, kept for the session
const ERR = {
  unavailable: 'The question box is unavailable right now; the map and its filters still work.',
  timeout: `No reply within ${TIMEOUT_S} seconds for this step; try again.`,
  network: 'The question box could not be reached; check the connection and try again. The map and its filters still work.',
  engine: 'The data files could not be loaded; check the connection and try again. The map and its filters still work.',
  steps: 'The question took too many steps to answer; try a narrower question.',
};

const ui = { form: null, input: null, btn: null, status: null, hint: null };
let engine = null, enginePromise = null, engineReady = false;
let gen = 0, ctrl = null, cooldownUntil = 0, cooldownTimer = null;
let prior = [];
let card = null;   // the render context of the open answer card (re-rendered on sort / show all / focus)

// ---------- small helpers ----------
const safe = fn => { try { return fn(); } catch (e) { return undefined; } };
const short = (o, n = 90) => { let s; try { s = typeof o === 'string' ? o : JSON.stringify(o); } catch (e) { s = String(o); } s = String(s == null ? '' : s); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
const reduceMotion = () => !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
const setStatus = t => { if (ui.status) ui.status.textContent = String(t == null ? '' : t); };
function setBusy(on) { if (!ui.form) return; ui.btn.disabled = on || Date.now() < cooldownUntil; ui.btn.textContent = on ? 'Asking…' : 'Ask'; if (on) ui.form.setAttribute('aria-busy', 'true'); else ui.form.removeAttribute('aria-busy'); if (ui.hint) ui.hint.hidden = on || Date.now() < cooldownUntil; if (!on && Date.now() >= cooldownUntil) setStatus(''); }
function setPlaceholder(follow) { if (!ui.input) return; const ph = follow ? PH_FOLLOW : (ui.input.dataset.ph0 || ''); ui.input.dataset.ph = ph; if (!/^Ask the map a question/.test(ui.input.placeholder)) ui.input.placeholder = ph; }   // the compact one-line box keeps its own placeholder (map.html layoutMap)
const focusPref = () => { try { const v = sessionStorage.getItem(FOCUS_KEY); return v === '1' ? true : v === '0' ? false : null; } catch (e) { return null; } };
const decideFocus = n => { const p = focusPref(); return p !== null ? p && n > 0 : n >= 1 && n <= R.FOCUS_MAX; };
const known = id => { const h = H(); return h.placeName ? !!safe(() => h.placeName(id)) : true; };
const placeIdOf = unit => row => { const id = R.rowMapId(row, unit); return id && known(id) ? id : null; };
const describeCall = (name, input) => safe(() => String(engine.describeCall(name, input))) || `${name} ${short(input)}`;
const describeResult = (name, input, r) => safe(() => String(engine.describeResult(name, input, r))) || (r && r.error ? `error: ${short(r.error, 120)}` : short(r, 100));

// ---------- the engine (created once; the data files load on the first question) ----------
async function ensureEngine() {
  if (engineReady) return engine;
  if (!enginePromise) enginePromise = (async () => {
    const url = new URL(devOverride('askEngineUrl') || './engine.js', import.meta.url).href;
    const mod = await import(url);
    engine = mod.createEngine({ globals: window, fetchJSON: u => fetch(u).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status} for ${u}`); return r.json(); }), base: '', onProgress: t => { if (ui.form && ui.form.hasAttribute('aria-busy')) setStatus(t); } });   // only while a question runs: the load goes on after a closed card, and its "Data loaded." must not stay in the box
    await engine.load(); engineReady = true; return engine;
  })().catch(e => { enginePromise = null; throw e; });
  return enginePromise;
}

// ---------- the worker ----------
async function postStep(body, signal) {
  const r = await fetch(ASK_URL, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), signal });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(typeof j.error === 'string' && j.error ? j.error : `HTTP ${r.status}`); e.status = r.status; e.detail = j.detail; e.retry_after_s = j.retry_after_s; throw e; }
  return j && typeof j === 'object' ? j : {};
}
function startCooldown(seconds) {
  cooldownUntil = Date.now() + seconds * 1000; if (cooldownTimer) clearInterval(cooldownTimer);
  const tick = () => { const left = Math.ceil((cooldownUntil - Date.now()) / 1000); if (left > 0) { setStatus(`Try again in ${left} s.`); if (ui.btn) ui.btn.disabled = true; if (ui.hint) ui.hint.hidden = true; return; }
    clearInterval(cooldownTimer); cooldownTimer = null; cooldownUntil = 0; if (ui.btn) ui.btn.disabled = false; if (ui.hint) ui.hint.hidden = false; setStatus(''); };
  tick(); cooldownTimer = setInterval(tick, 1000);
}
function handleError(q, e) {
  const st = e && e.status;
  if (e && e.name === 'AbortError') { renderError(q, ERR.timeout); return; }
  if (st === 429) { const n = Math.max(1, Math.min(600, Math.round(Number(e.retry_after_s) || 30))); renderError(q, `${e.message.replace(/\.?\s*$/, '.')} Try again in ${n} s.`); startCooldown(n); return; }
  if (st >= 400) { renderError(q, ERR.unavailable, e.detail || e.message); return; }
  renderError(q, ERR.network, e && e.message);
}

// ---------- the card in the figures column ----------
function removeCard() { const old = document.getElementById('ask-card'); if (old) old.remove(); const ag = document.getElementById('ask-again'); if (ag) ag.hidden = true; }
function sync() {   // after every repaint, tab change or unit change (map.html's __askSync calls this): the "Map now shows" line and the way back to the box
  const el = document.getElementById('ask-map-shows'); if (el && H().mapShows) el.textContent = safe(() => H().mapShows()) || '';
  const ag = document.getElementById('ask-again'); if (ag) { ag.hidden = (H().tab ? H().tab() : 'map') === 'map' || !document.getElementById('ask-card'); const sp = ag.querySelector('span'); if (sp) sp.hidden = !(H().hl && safe(() => H().hl().length)); }   // "the Map tab shows the outlined places" only when there are outlines
}
function mountCard(html, opts = {}) {
  removeCard(); const host = H().paneHost ? H().paneHost() : document.querySelector('#pane .tabs'); if (!host) return null;
  let ag = document.getElementById('ask-again');
  if (!ag) { host.insertAdjacentHTML('afterend', '<div class="ask-again" id="ask-again" hidden><button type="button" id="ask-again-b">Ask another question</button><span>The Map tab shows the outlined places.</span></div>'); ag = document.getElementById('ask-again');
    ag.querySelector('button').addEventListener('click', () => { if (H().setTab) H().setTab('map'); if (ui.input) { ui.input.focus(); ui.input.select(); } }); }
  ag.insertAdjacentHTML('afterend', html); const el = document.getElementById('ask-card'); if (!el) return null;
  el.querySelector('.ask-x').addEventListener('click', closeCard);
  el.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); closeCard(); } });
  sync();
  if (!opts.quiet) { const pane = document.getElementById('pane'); if (pane && !opts.keepScroll) pane.scrollTop = 0; if (opts.focus !== false) el.focus({ preventScroll: true });
    // stacked layout (a phone or a narrow window): the figures sit below the map, so bring the map and the answer under it into view
    if (!opts.busy && window.innerWidth <= 980) setTimeout(() => { const t = (H().tab ? H().tab() : 'map') === 'map' ? document.getElementById('map') : document.getElementById('ask-card'); if (t) t.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' }); }, 120); }
  return el;
}
function closeCard() {   // the × or Escape: the card, the outlines and the focus dimming go; a running question is dropped; the follow-up context stays
  if (document.querySelector('#ask-card.busy')) { gen++; if (ctrl) ctrl.abort(); setBusy(false); }
  removeCard(); if (H().highlight) H().highlight([]); if (H().setFocus) H().setFocus(false); window.__askState = null; card = null;
  try { history.replaceState(null, '', location.href); } catch (e) { /* file: pages */ }
  sync(); if (ui.input) ui.input.focus({ preventScroll: true });
}
function renderBusy(q, log, lead) { mountCard(R.busyHTML(q, log, lead), { busy: true, focus: false }); }
function renderSteps(log) { const ol = document.querySelector('#ask-card.busy .ask-steps'); if (ol) ol.innerHTML = R.stepsHTML(log); }
function setLead(text) { const p = document.querySelector('#ask-card.busy .ask-a p'); if (p) p.textContent = text; }
function renderError(q, message, detail) { window.__askState = null; card = null; mountCard(R.errorHTML(q, message, detail), { focus: true }); }
function renderAnswer(ctx, opts = {}) {
  card = ctx; const el = mountCard(R.cardHTML(ctx), opts); if (!el) return;
  el.addEventListener('click', e => {
    const t = e.target.closest('button, a'); if (!t) return;
    if (t.dataset.pl) { if (H().selectPlace) H().selectPlace(t.dataset.pl); return; }
    if ((t.classList.contains('ask-alt') || t.classList.contains('ask-fuq')) && t.dataset.q) { run(t.dataset.q); return; }
    if (t.classList.contains('ask-sort')) { toggleSort(t.dataset.col); return; }
    if (t.classList.contains('ask-showall')) { card.showAll = true; rerender({ focusSel: '.ask-tbl' }); return; }
    if (t.classList.contains('ask-new')) { newQuestion(); return; }
    if (t.classList.contains('ask-fb-b')) { sendFeedback(t.dataset.v); return; }
    if (t.classList.contains('ask-reset')) { e.preventDefault(); resetMap(); }
  });
  el.addEventListener('change', e => { if (e.target && e.target.id === 'ask-focus') setFocus(e.target.checked, true); });
}
function rerender(o = {}) { if (!card) return; const pane = document.getElementById('pane'), top = pane ? pane.scrollTop : 0; renderAnswer(card, { quiet: true }); if (pane) pane.scrollTop = top; if (o.focusSel) { const t = document.querySelector('#ask-card ' + o.focusSel); if (t && t.focus) t.focus({ preventScroll: true }); } }
function toggleSort(col) { if (!card || !col) return; const s = card.sort; card.sort = s && s.key === col ? (s.dir === 'asc' ? { key: col, dir: 'desc' } : null) : { key: col, dir: 'asc' }; rerender({ focusSel: `.ask-sort[data-col="${col.replace(/"/g, '\\"')}"]` }); }   // ascending, then descending, then the engine's order
// "Was this right?": one POST to the worker, never waited on and never shown as an error; the buttons give way to the thanks
function sendFeedback(verdict) {
  if (!card || card.feedback) return; card.feedback = verdict === 'yes' ? 'yes' : 'no';
  const st = window.__askState; if (st) st.feedback = card.feedback;
  rerender();
  if (!FEEDBACK_URL) return;
  try { fetch(FEEDBACK_URL, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(R.feedbackPayload(card, card.feedback)), keepalive: true }).catch(() => {}); } catch (e) { /* feedback is best effort */ }
}
function setFocus(on, byUser) { if (H().setFocus) H().setFocus(on); if (byUser) { try { sessionStorage.setItem(FOCUS_KEY, on ? '1' : '0'); } catch (e) { /* private mode */ } } if (card && card.focus) card.focus.on = on; if (window.__askState) window.__askState.focus = on; }
function resetMap() {   // the card's "Reset map": back to the default national view; the card stays, its outlines go
  if (H().highlight) H().highlight([]); if (H().setFocus) H().setFocus(false); window.__askState = null;
  history.pushState(null, '', 'map.html'); if (H().applyURL) H().applyURL(false);
  if (card) { card.hl = { label: '', count: 0 }; card.focus = { on: false, show: false }; rerender(); } sync();
}

// the render context of an answer: the stored snapshot (what the history entry keeps) plus live parts (the map's own line, the focus state)
function ctxOf(snap, table) {
  const t = table || snap.table || null; const ids = Array.isArray(snap.ids) ? snap.ids : [];
  return { q: snap.q, answer: snap.answer, verification: snap.verification, model: snap.model, steps: snap.steps, table: t, sources: snap.sources, vintages: snap.vintages, log: snap.log, dropped: snap.dropped, method: snap.method || null, calls: snap.calls || [], feedback: snap.feedback || null,
    mapShows: snap.hasMap ? (safe(() => H().mapShows()) || '') : null, hl: { label: snap.hlLabel || '', count: ids.length }, focus: { on: H().focus ? !!H().focus() : !!snap.focus, show: ids.length > 0 && snap.hasMap }, sort: null, showAll: false, placeIdOf: placeIdOf(t && t.unit) };
}
const cleanSources = list => (Array.isArray(list) ? list : []).filter(s => s && typeof s === 'object').map(s => ({ table: String(s.table || ''), title: String(s.title || ''), file: String(s.file || ''), url: s.url ? String(s.url) : '', as_of: s.as_of ? String(s.as_of) : '' })).slice(0, 12);
function sourcesFor(answer, calls) {
  const tables = new Set(); for (const s of Array.isArray(answer.sources) ? answer.sources : []) if (typeof s === 'string' && (TABLES[s] || s === 'trials')) tables.add(s);
  for (const c of Object.values(calls)) { if (c.input && typeof c.input.table === 'string' && TABLES[c.input.table]) tables.add(c.input.table); if (c.name === 'trials') tables.add('trials'); }
  return cleanSources(safe(() => engine.sourcesFor([...tables])));
}
const capTable = t => !t ? null : t.rows.length > HISTORY_ROWS ? { ...t, rows: t.rows.slice(0, HISTORY_ROWS), rows_capped: true } : t;

// ---------- the loop (one HTTP step per model call; the engine runs the calls here) ----------
async function run(q) {
  q = String(q || '').trim(); if (!q || !ui.form) return;
  if (q.length < 3) { setStatus('Ask a longer question.'); return; }
  if (Date.now() < cooldownUntil) { setStatus(`Please wait ${Math.ceil((cooldownUntil - Date.now()) / 1000)} s before the next question.`); return; }
  ui.input.value = q; ui.input.scrollTop = 0; ui.input.scrollLeft = 0; const g = ++gen; if (ctrl) ctrl.abort();   // the box shows the start of the question while it runs (a long one scrolls while typed)
  const log = [], results = {}, calls = {}; let step = 0;
  setBusy(true); renderBusy(q, log, engineReady ? 'Asking the map…' : LOAD_TEXT); if (!engineReady) setStatus(LOAD_TEXT); else setStatus('Asking the map…');
  try {
    try { await ensureEngine(); } catch (e) { if (g !== gen) return; renderError(q, ERR.engine, e && e.message); return; }
    if (g !== gen) return;
    const turns = [];
    for (let i = 0; i < MAX_TURNS; i++) {
      setLead(`Asking the map… (step ${Math.min(i + 1, 8)} of up to 8)`); setStatus(i === 0 ? 'Asking the map…' : `Step ${step + 1}: reading the results…`);
      const my = new AbortController(); ctrl = my; const timer = setTimeout(() => my.abort(), TIMEOUT_S * 1000); let resp;
      try { resp = await postStep({ v: 3, q, turns, prior, client: { page: 'map', unit: safe(() => H().unit()) || 'county' } }, my.signal); }
      catch (e) { if (g !== gen) return; handleError(q, e); return; }
      finally { clearTimeout(timer); if (ctrl === my) ctrl = null; }
      if (g !== gen) return;
      step = Number.isFinite(resp.step) ? resp.step : i + 1;
      if (resp.kind === 'tools' && Array.isArray(resp.calls)) {
        const many = resp.calls.length > 1;
        const out = await Promise.all(resp.calls.map(async c => {
          const id = String(c && c.id || ''), name = String(c && c.name || ''), input = c && c.input && typeof c.input === 'object' ? c.input : {};
          calls[id] = { name, input };
          if (name === 'final_answer') return { tool_use_id: id, content: JSON.stringify(many ? { ok: true, note: 'call final_answer alone, after the other results' } : { ok: true, note: 'final_answer is read by the server' }), is_error: false };
          const entry = { call: describeCall(name, input), result: null, error: false }; log.push(entry); renderSteps(log); setStatus(`Step ${step}: ${entry.call}`);
          let r; try { r = await engine.run(name, input, id); } catch (e) { r = { error: 'engine failure: ' + (e && e.message || e) }; } if (r === undefined || r === null) r = { error: 'the tool returned nothing' };
          results[id] = r; entry.error = !!(r && typeof r === 'object' && r.error); entry.result = describeResult(name, input, r); if (g === gen) { renderSteps(log); setStatus(`→ ${entry.result}`); }
          return { tool_use_id: id, content: R.truncateResult(r), is_error: entry.error };
        }));
        if (g !== gen) return;
        turns.push({ assistant: resp.assistant, sig: resp.sig, results: out }); continue;
      }
      if (resp.kind === 'answer') { finish(q, resp, log, results, calls, step); return; }
      renderError(q, ERR.unavailable, `unexpected reply (${short(resp.kind || resp.error || resp, 80)})`); return;
    }
    renderError(q, ERR.steps);
  } finally { if (g === gen) setBusy(false); }
}

// the answer: table from the engine's full result, the map view (validated), the outlines, the card, the follow-up context
function finish(q, resp, log, results, calls, steps) {
  const answer = resp.answer && typeof resp.answer === 'object' ? resp.answer : { answer: '', answerable: 'partly' };
  const verification = resp.verification && typeof resp.verification === 'object' ? { ok: !!resp.verification.ok, issues: Array.isArray(resp.verification.issues) ? resp.verification.issues.map(x => short(x, 200)) : [] } : { ok: false, issues: ['the reply carried no verification'] };
  const plain = R.isPlainAnswer(answer);
  const full = id => safe(() => engine.full(id)) || null;
  const fromCall = answer.table && typeof answer.table === 'object' && typeof answer.table.from_call === 'string' ? answer.table.from_call : null;
  const table = plain ? null : R.prepareTable(answer.table, fromCall ? full(fromCall) : null, fromCall ? results[fromCall] : null);
  const mv = plain ? null : R.validateMap(answer.map, safe(() => H().layers()) || {}, id => engine.unitOf(id));
  let ids = [];
  if (mv && mv.highlight) { const h = safe(() => engine.highlightIds(mv.highlight)); if (h) ids = R.resolveIds(h.ids || [], id => h.unit || engine.unitOf(id)); else if (mv.highlight.from_call) mv.dropped.push('the highlight named a call with no places'); }
  const before = ids.length; ids = ids.filter(known); if (mv && before && !ids.length) mv.dropped.push('none of the highlighted ids is on the map');
  const focusOn = decideFocus(ids.length);
  const snap = { v: 3, q, answer, verification, model: typeof resp.model === 'string' ? resp.model : null, steps, ids, focus: focusOn, hasMap: !!mv, hlLabel: mv ? mv.highlight_label : '', table: capTable(table), sources: plain ? [] : sourcesFor(answer, calls), vintages: plain ? { data_as_of: safe(() => engine.vintages().data_as_of) || '' } : (safe(() => engine.vintages()) || {}), log: log.map(e => ({ call: e.call, result: e.result, error: e.error })), dropped: mv ? mv.dropped : [],
    method: plain ? null : (safe(() => R.methodFor(answer, calls, methodById)) || null), calls: Object.values(calls).filter(c => c.name !== 'final_answer').slice(0, 12).map(c => ({ name: c.name, input: c.input })), feedback: null };
  if (plain) { window.__askState = null; if (H().highlight) H().highlight([]); if (H().setFocus) H().setFocus(false); renderAnswer(ctxOf(snap, null)); return; }
  window.__askState = snap;   // pushURL (map.html) copies it into every later history entry of this view
  if (H().highlight) H().highlight(ids); if (H().setFocus) H().setFocus(focusOn);   // the outlines first: the card's "Map now shows" line describes them
  if (mv) { const pp = R.placeParamFor(ids, mv, H().stateOf); const qs = R.buildQS(mv, pp); history.pushState({ ask: snap }, '', 'map.html' + (qs ? '?' + qs : '')); if (H().applyURL) H().applyURL(false); }
  else history.pushState({ ask: snap }, '', location.href);   // no view change: the entry still carries the card, so Back returns to the previous answer
  renderAnswer(ctxOf(snap, table));
  const pt = R.priorText(answer, verification); if (pt) { prior.push({ q, answer: pt }); prior = prior.slice(-PRIOR_MAX); setPlaceholder(true); }
}

// ---------- Back/Forward, clearing ----------
function restore(st) {
  if (st && typeof st === 'object' && st.v === 3 && st.answer) { window.__askState = st; if (H().highlight) H().highlight(st.ids || []); if (H().setFocus) H().setFocus(!!st.focus && (st.ids || []).length > 0); renderAnswer(ctxOf(st, null), { quiet: true }); }
  else { window.__askState = null; card = null; removeCard(); if (H().highlight) H().highlight([]); if (H().setFocus) H().setFocus(false); sync(); }
}
function newQuestion() { prior = []; setPlaceholder(false); if (ui.input) { ui.input.value = ''; ui.input.focus(); } }
function clear() { closeCard(); newQuestion(); setStatus(''); }

// ---------- mount ----------
function init() {
  if (!ASK_URL || !SITE.mountAskBox) return;
  const mount = (H().askMount && H().askMount()) || document.getElementById('ask-mount'); if (!mount) return;
  const link = document.createElement('link'); link.rel = 'stylesheet'; link.href = new URL('./ask.css', import.meta.url).href; document.head.appendChild(link);
  SITE.askStyles(); ui.form = SITE.mountAskBox(mount, { status: true }); ui.input = document.getElementById('askq'); ui.btn = document.getElementById('askb'); ui.status = document.getElementById('ask-status'); ui.hint = document.getElementById('ask-hint');
  ui.input.dataset.ph0 = ui.input.placeholder; ui.input.dataset.ph = ui.input.placeholder;
  if (H().layout) H().layout(); else document.body.classList.add('has-ask');   // the map is laid out around the box
  ui.form.addEventListener('submit', e => { e.preventDefault(); run(ui.input.value); });
  H().sync = sync; window.__askRestore = restore;
  window.ASK = { run, clear, restore, newQuestion, get engine() { return engine; }, version: 3 };
  const p = new URLSearchParams(location.search); const q0 = p.get('ask');
  if (q0) { p.delete('ask'); history.replaceState(history.state, '', 'map.html' + (p.toString() ? '?' + p : '')); run(q0); }   // a question carried in from the homepage box
  else if (history.state && history.state.ask) restore(history.state.ask);   // a reload of a view with an open answer
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
