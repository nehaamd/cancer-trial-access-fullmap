/* Ask the map v3 — the pure half of the client (no DOM, no I/O), imported by docs/ask/ask.js and tested in Node by
   worker/tests/client.test.js. It validates the model's `map` request against the catalog and the page's own layer list,
   builds the view's query string, truncates tool results for the step protocol (rows, never bytes), sorts and formats table
   cells, and writes the answer card's HTML. Everything the model wrote passes through esc(); links come only from the engine's
   source list, and only when they are web addresses or site-relative paths. See ASK_CONTRACT.md §6–§7. */
import { MAP_LAYERS, MAP_PARAMS, STATES, SCOPE_TEXT, OTHER_TEXT, TABLES, UNIT_OF_TABLE, fieldFor, labelFor } from './catalog.js';

export const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const STATE_FIPS = { AL: '01', AK: '02', AZ: '04', AR: '05', CA: '06', CO: '08', CT: '09', DE: '10', DC: '11', FL: '12', GA: '13', HI: '15', ID: '16', IL: '17', IN: '18', IA: '19', KS: '20', KY: '21', LA: '22', ME: '23', MD: '24', MA: '25', MI: '26', MN: '27', MS: '28', MO: '29', MT: '30', NE: '31', NV: '32', NH: '33', NJ: '34', NM: '35', NY: '36', NC: '37', ND: '38', OH: '39', OK: '40', OR: '41', PA: '42', RI: '44', SC: '45', SD: '46', TN: '47', TX: '48', UT: '49', VT: '50', VA: '51', WA: '53', WV: '54', WI: '55', WY: '56' };
export const UNITS = ['county', 'district', 'state'];
export const NOUNS = { county: 'counties', district: 'districts', state: 'states' };
export const MAX_RESULT_BYTES = 24 * 1024;
export const TABLE_LIMIT = 100;
export const FOCUS_MAX = 400;
export const UNVERIFIED_NOTICE = 'The written summary could not be checked against the data, so only the data is shown.';
export const STANDING_NOTE = 'Figures are read from the map’s data files; the written summary was checked against them number by number. The box lists and ranks; it does not match patients to trials or give medical advice.';

// ---------- ids: the engine's (FIPS, "TX-34", USPS) and the map's (FIPS, 4-digit geoid, USPS) ----------
export const idKind = id => /^\d{5}$/.test(String(id)) ? 'county' : /^\d{4}$/.test(String(id)) ? 'district' : /^[A-Z]{2}$/i.test(String(id)) && STATES[String(id).toUpperCase()] ? 'state' : null;   // map ids
export function inferKind(id) { const s = String(id == null ? '' : id).trim(); if (/^\d{5}$/.test(s)) return 'county'; if (/^\d{4}$/.test(s) || /^[A-Z]{2}-\d{1,2}$/i.test(s)) return 'district'; if (/^[A-Z]{2}$/i.test(s) && STATES[s.toUpperCase()]) return 'state'; return null; }
// "TX-34" -> "4834"; at-large "WY-00" -> "5600"; the DC delegate "DC-00" -> "1198" (the map's id for it); a 4-digit geoid passes through
export function districtGeoid(id) { const s = String(id == null ? '' : id).trim().toUpperCase(); if (/^\d{4}$/.test(s)) return s; const m = s.match(/^([A-Z]{2})-(\d{1,2})$/); if (!m || !STATE_FIPS[m[1]]) return null; return STATE_FIPS[m[1]] + (m[1] === 'DC' ? '98' : m[2].padStart(2, '0')); }
export function toMapId(id, kind) { const s = String(id == null ? '' : id).trim(); if (!s) return null; const k = kind || inferKind(s);
  if (k === 'county') return /^\d{5}$/.test(s) ? s : null; if (k === 'district') return districtGeoid(s); if (k === 'state') { const u = s.toUpperCase(); return STATES[u] ? u : null; } return null; }
// engine ids -> distinct map ids; unitOf (the engine's) names the kind when it knows the id, inferKind otherwise
export function resolveIds(ids, unitOf) { const out = [], seen = new Set(); for (const id of Array.isArray(ids) ? ids : []) { let k = null; try { k = unitOf ? unitOf(String(id)) : null; } catch (e) { k = null; } const m = toMapId(id, k || inferKind(id)); if (m && !seen.has(m)) { seen.add(m); out.push(m); } } return out; }

// ---------- the model's map request, checked against the catalog and the page ----------
// pageLayers: the map page's UNIT_METRICS ({county: [...], district: [...], state: [...]}); a layer must be in both lists.
// Returns null when there is no usable unit; otherwise {unit, layer|null, params, state|null, place|null (a map id), placeKind,
// highlight ({from_call} | {ids} | null), highlight_label, dropped: [what was ignored and why]}.
export function validateMap(map, pageLayers, unitOf) {
  if (!map || typeof map !== 'object' || Array.isArray(map)) return null;
  const dropped = [];
  const unit = UNITS.includes(map.unit) ? map.unit : null; if (!unit) return null;
  const cat = MAP_LAYERS[unit] || {}, page = (pageLayers && Array.isArray(pageLayers[unit])) ? pageLayers[unit] : [];
  const layer = typeof map.layer === 'string' && cat[map.layer] && page.includes(map.layer) ? map.layer : null;
  if (map.layer != null && !layer) dropped.push(`layer "${String(map.layer).slice(0, 40)}" is not a ${unit} layer on this page`);
  const allowed = layer ? (cat[layer].params || []) : Object.keys(MAP_PARAMS);
  const params = {};
  if (map.params && typeof map.params === 'object' && !Array.isArray(map.params)) for (const [k, v] of Object.entries(map.params)) {
    if (v === null || v === undefined || v === '') continue; const sv = String(v);
    if (!MAP_PARAMS[k] || !MAP_PARAMS[k].includes(sv)) { dropped.push(`${String(k).slice(0, 20)}=${sv.slice(0, 40)} is not a map parameter`); continue; }
    if (!allowed.includes(k)) { dropped.push(`${k}=${sv} does not apply to the ${layer} layer`); continue; }
    params[k] = sv; }
  const state = typeof map.state === 'string' && STATES[map.state.trim().toUpperCase()] ? map.state.trim().toUpperCase() : null;
  if (map.state != null && map.state !== '' && !state) dropped.push(`state "${String(map.state).slice(0, 20)}" is not a state`);
  let place = null, placeKind = null;
  if (map.place != null && map.place !== '') { let k = null; try { k = unitOf ? unitOf(String(map.place)) : null; } catch (e) { k = null; } placeKind = k || inferKind(map.place); place = placeKind ? toMapId(map.place, placeKind) : null; if (!place) { placeKind = null; dropped.push(`place "${String(map.place).slice(0, 20)}" is not a place id`); } }
  let highlight = null; const h = map.highlight;
  if (h && typeof h === 'object') { if (typeof h.from_call === 'string' && h.from_call) highlight = { from_call: h.from_call }; else if (Array.isArray(h.ids)) highlight = { ids: h.ids.map(String).slice(0, 5000) }; }
  const highlight_label = typeof map.highlight_label === 'string' ? map.highlight_label.trim().slice(0, 160) : '';
  return { unit, layer, params, state, place, placeKind, highlight, highlight_label, dropped };
}

// the place the view opens on: the model's `place`; else the one outlined place of the view's unit; else the state focus; else the
// one state every outlined place is in (stateOf: map id -> USPS). Returns ['c'|'d'|'s', id] or null (the national view).
export function placeParamFor(ids, mv, stateOf) {
  if (!mv) return null; const key = k => k === 'county' ? 'c' : k === 'district' ? 'd' : 's';
  if (mv.place) return [key(mv.placeKind), mv.place];
  const own = (ids || []).filter(id => idKind(id) === mv.unit);
  if (own.length === 1) return [key(mv.unit), own[0]];
  if (mv.state) return ['s', mv.state];
  if (own.length > 1 && mv.unit !== 'state' && typeof stateOf === 'function') { const st = new Set(own.map(id => { try { return stateOf(id); } catch (e) { return null; } }).filter(Boolean)); if (st.size === 1) return ['s', [...st][0]]; }
  return null;
}

// the view's address: u (unless county), m, the layer's parameters in the catalog's order, then the place (c / d / s)
export function buildQS(mv, placeParam) {
  const p = new URLSearchParams(); if (!mv) { if (placeParam) p.set(placeParam[0], placeParam[1]); return p.toString(); }
  if (mv.unit !== 'county') p.set('u', mv.unit); if (mv.layer) p.set('m', mv.layer);
  for (const k of Object.keys(MAP_PARAMS)) if (mv.params && mv.params[k] != null) p.set(k, mv.params[k]);
  if (placeParam) p.set(placeParam[0], placeParam[1]); else if (mv.state) p.set('s', mv.state);
  return p.toString();
}

// ---------- tool results for the protocol: at most 24 KB each, cut by rows ----------
const byteLen = s => typeof TextEncoder !== 'undefined' ? new TextEncoder().encode(s).length : s.length;
const CUT_KEYS = ['rows', 'sample', 'matches', 'groups', 'reference', 'ids', 'county_names', 'counties'];
export function truncateResult(result, max = MAX_RESULT_BYTES) {
  let s = JSON.stringify(result === undefined ? null : result); if (byteLen(s) <= max) return s;
  if (result && typeof result === 'object' && !Array.isArray(result)) {
    const key = CUT_KEYS.find(k => Array.isArray(result[k]) && result[k].length) || Object.keys(result).find(k => Array.isArray(result[k]) && result[k].length);
    if (key) { const all = result[key]; let n = all.length;
      while (n > 0) { n = Math.floor(n / 2); s = JSON.stringify({ ...result, [key]: all.slice(0, n), truncated: `…(truncated): ${key} cut to ${n} of ${all.length}` }); if (byteLen(s) <= max) return s; } }
  }
  // nothing to cut row by row: the head of the text, as a JSON string
  let keep = Math.max(0, max - 80); for (;;) { const out = JSON.stringify({ truncated: true, text: s.slice(0, keep) + '…(truncated)' }); if (byteLen(out) <= max || keep === 0) return out; keep = Math.floor(keep * 0.8); }
}

// ---------- table cells, sorting ----------
export function getPath(row, path) { if (!row || typeof row !== 'object') return undefined; if (path in row) return row[path]; let v = row; for (const k of String(path).split('.')) { if (v === null || v === undefined || typeof v !== 'object') return undefined; v = v[k]; } return v; }
export const isNullish = v => v === null || v === undefined || v === '' || (typeof v === 'number' && Number.isNaN(v));
export function fmtCell(v) {
  if (v === null || v === undefined) return '—'; if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (typeof v === 'number') return Number.isFinite(v) ? v.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—';
  if (Array.isArray(v)) return v.length ? v.map(x => x !== null && typeof x === 'object' ? JSON.stringify(x) : String(x)).join(', ') : '—';
  if (typeof v === 'object') return JSON.stringify(v); return String(v); }
// stable sort on one column; nulls last in both directions; numbers numerically, booleans yes before no, strings by locale with numeric runs
export function sortRows(rows, key, dir = 'asc') {
  const cmp = (a, b) => { const va = getPath(a, key), vb = getPath(b, key); const na = isNullish(va), nb = isNullish(vb); if (na && nb) return 0; if (na) return 1; if (nb) return -1;
    let c; if (typeof va === 'number' && typeof vb === 'number') c = va - vb; else if (typeof va === 'boolean' && typeof vb === 'boolean') c = (vb ? 1 : 0) - (va ? 1 : 0); else c = String(va).localeCompare(String(vb), 'en', { numeric: true, sensitivity: 'base' });
    return dir === 'desc' ? -c : c; };
  return (rows || []).map((r, i) => [r, i]).sort((x, y) => cmp(x[0], y[0]) || x[1] - y[1]).map(x => x[0]);
}

// ---------- the results table ----------
// t: {columns, rows (objects keyed by column path), table (catalog table name | null), unit}; o: {sortKey, sortDir, showAll, limit,
// placeIdOf(row) -> map id | null}. The place column (name, else the first) is a button that selects the place on the map.
export function tableHTML(t, o = {}) {
  if (!t || !Array.isArray(t.rows) || !t.rows.length) return '';
  const cols = (Array.isArray(t.columns) && t.columns.length ? t.columns : Object.keys(t.rows[0])).map(String).filter(c => c !== 'id' && c !== 'geoid' && c !== 'level');
  if (!cols.length) return '';
  let rows = t.rows; if (o.sortKey) rows = sortRows(rows, o.sortKey, o.sortDir);
  const limit = o.limit || TABLE_LIMIT, shown = o.showAll ? rows : rows.slice(0, limit), placeCol = cols.includes('name') ? 'name' : cols[0];
  const head = cols.map(c => { const f = t.table && TABLES[t.table] ? fieldFor(t.table, c) : null; const on = o.sortKey === c, desc = on && o.sortDir === 'desc';
    return `<th scope="col" aria-sort="${on ? (desc ? 'descending' : 'ascending') : 'none'}"><button type="button" class="ask-sort" data-col="${esc(c)}"${` title="${esc(c + (f && f.desc ? ' — ' + f.desc : ''))}"`}>${esc(labelFor(c))}<span class="ask-arr" aria-hidden="true">${on ? (desc ? '▼' : '▲') : '↕'}</span></button></th>`; }).join('');
  const body = shown.map(r => { let pid = null; try { pid = o.placeIdOf ? o.placeIdOf(r) : null; } catch (e) { pid = null; }
    return '<tr>' + cols.map(c => { const v = getPath(r, c), txt = esc(fmtCell(v));
      if (c === placeCol && pid) return `<td><button type="button" class="ask-place" data-pl="${esc(pid)}">${txt}</button></td>`;
      return `<td${typeof v === 'number' ? ' class="n"' : ''}>${txt}</td>`; }).join('') + '</tr>'; }).join('');
  const more = rows.length > shown.length ? `<p class="ask-more-rows"><button type="button" class="ask-showall">Show all ${rows.length.toLocaleString('en-US')}</button><span>${shown.length} of ${rows.length.toLocaleString('en-US')} rows shown</span></p>` : '';
  return `<div class="ask-tbl"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>${more}`;
}

export function summaryHTML(t) {
  if (!t) return ''; const parts = []; const noun = t.unit && NOUNS[t.unit] ? NOUNS[t.unit] : t.table && TABLES[t.table] ? TABLES[t.table].label : 'rows';
  if (Number.isFinite(t.count)) parts.push(`<b>${fmtCell(t.count)}</b> ${esc(noun)} match`);
  if (Number.isFinite(t.in_scope)) parts.push(`of <b>${fmtCell(t.in_scope)}</b> in scope`);
  if (Number.isFinite(t.sum_pop55) && t.sum_pop55 > 0) parts.push(`<b>${fmtCell(t.sum_pop55)}</b> residents 55+ in the matching places`);
  return parts.length ? `<p class="ask-sum">${parts.join(' · ')}</p>` : '';
}

// ---------- the card ----------
export const isPlainAnswer = answer => { const a = String(answer && answer.answer || '').trim(); return a === SCOPE_TEXT.trim() || a === OTHER_TEXT.trim(); };
export const answerable = answer => ['yes', 'partly', 'no'].includes(answer && answer.answerable) ? answer.answerable : 'yes';
// the text a follow-up refers back to: the verified answer, else the interpretation
export function priorText(answer, verification) { const ok = !!(verification && verification.ok); const a = String(answer && answer.answer || '').trim(), i = String(answer && answer.interpretation || '').trim(); return ok && a ? a : i; }
export function niceDate(iso) { if (!iso) return ''; const s = String(iso).slice(0, 10); const d = new Date(s + 'T12:00:00'); return isNaN(d) ? String(iso) : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); }
const safeUrl = u => { const s = String(u || '').trim(); if (!s || /[\s"'<>]/.test(s)) return null; if (/^https?:\/\//i.test(s)) return s; if (/^[a-z][a-z0-9+.-]*:/i.test(s)) return null; if (s.startsWith('//')) return null; return s; };   // a web address or a site-relative path; never javascript:, data: or a scheme-relative link
const strList = (a, n) => (Array.isArray(a) ? a : []).filter(x => typeof x === 'string' && x.trim()).slice(0, n);
const paras = text => String(text || '').split(/\n+/).map(x => x.trim()).filter(Boolean).map(x => `<p>${esc(x)}</p>`).join('');
export const chipsHTML = (qs, cls) => qs.map(q => `<button type="button" class="ask-pl ${cls}" data-q="${esc(q)}">${esc(q)}</button>`).join('');

export function stepsHTML(log) {
  return (log || []).map(e => `<li${e.error ? ' class="err"' : ''}><span class="ask-log-c">${esc(e.call)}</span>${e.result != null ? `<span class="ask-log-r">→ ${esc(e.result)}</span>` : ''}</li>`).join('');
}
export function busyHTML(q, log, lead) {
  return `<div class="ask-card busy" id="ask-card" role="region" aria-label="Answer" aria-busy="true" tabindex="-1"><button type="button" class="ask-x" aria-label="Close answer">×</button><p class="ask-q">${esc(q)}</p><div class="ask-a"><p>${esc(lead || 'Asking the map…')}</p></div><ol class="ask-steps">${stepsHTML(log)}</ol></div>`;
}
export function errorHTML(q, message, detail) {
  return `<div class="ask-card err" id="ask-card" role="region" aria-label="Answer" tabindex="-1"><button type="button" class="ask-x" aria-label="Close answer">×</button><p class="ask-q">${esc(q)}</p><div class="ask-a"><p>${esc(message)}</p>${detail ? `<p class="ask-detail">${esc(String(detail).slice(0, 400))}</p>` : ''}</div></div>`;
}

// the sources line: file links (only web addresses or site-relative paths, from the engine) with their dates, then the vintages
export function sourcesHTML(sources, vintages) {
  const items = (Array.isArray(sources) ? sources : []).filter(s => s && (s.file || s.title)).map(s => { const u = safeUrl(s.url); const lab = esc(s.file || s.title); return (u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${lab}</a>` : lab) + (s.as_of ? ` <span class="ask-asof">(as of ${esc(niceDate(s.as_of))})</span>` : ''); });
  const v = vintages && typeof vintages === 'object' ? vintages : {}; const tail = [];
  if (v.data_as_of) tail.push(`registry data as of ${esc(niceDate(v.data_as_of))}`); if (v.incidence_period) tail.push(`incidence ${esc(String(v.incidence_period).replace('-', '–'))}`); if (v.mortality_period) tail.push(`death rates ${esc(String(v.mortality_period).replace('-', '–'))}`); if (v.acs) tail.push(`ACS ${esc(String(v.acs).replace('-', '–'))}`);
  if (!items.length && !tail.length) return '';
  return `<p class="ask-src">${items.length ? '<span class="ask-lead">Read from:</span> ' + items.join(', ') : ''}${items.length && tail.length ? ' · ' : ''}${tail.join(' · ')}</p>`;
}

// ctx: { q, answer (the final_answer object), verification {ok, issues}, table (see tableHTML) | null, sort {key, dir}, showAll,
//        placeIdOf, sources, vintages, mapShows (the map's own line) | null, hl {label, count} | null, focus {on, show} | null,
//        log [{call, result, error}], model, steps, dropped [strings] }
export function cardHTML(ctx) {
  const a = ctx.answer && typeof ctx.answer === 'object' ? ctx.answer : {}; const ok = !!(ctx.verification && ctx.verification.ok); const plain = isPlainAnswer(a);
  const kind = answerable(a); const tag = kind === 'partly' ? '<span class="ask-tag">Answered in part</span>' : kind === 'no' ? '<span class="ask-tag ask-tag-no">Not in the data</span>' : '';
  const x = '<button type="button" class="ask-x" aria-label="Close answer">×</button>';
  const head = `<p class="ask-q">${esc(ctx.q)}</p>`;
  if (plain) return `<div class="ask-card plain" id="ask-card" role="region" aria-label="Answer" tabindex="-1">${x}${head}<div class="ask-a">${paras(a.answer)}</div><p class="ask-note">${esc(STANDING_NOTE)}</p></div>`;
  const body = ok && String(a.answer || '').trim() ? `<div class="ask-a">${tag}${paras(a.answer)}</div>` : `<p class="ask-unverified">${esc(UNVERIFIED_NOTICE)}</p>`;
  const alts = strList(a.alternatives, 3), nid = strList(a.not_in_data, 4), cav = strList(a.caveats, 5), fu = strList(a.follow_ups, 3), interp = String(a.interpretation || '').trim();
  const read = interp || alts.length ? `<section class="ask-sec ask-read"><h4>How this was read</h4>${interp ? `<p>${esc(interp)}</p>` : ''}${alts.length ? `<div class="ask-alts"><span class="ask-lead">Or ask:</span>${chipsHTML(alts, 'ask-alt')}</div>` : ''}</section>` : '';
  const notin = nid.length ? `<section class="ask-sec ask-nid"><h4>Not in the data</h4><ul>${nid.map(s => `<li>${esc(s)}</li>`).join('')}</ul></section>` : '';
  const table = ctx.table ? tableHTML(ctx.table, { sortKey: ctx.sort && ctx.sort.key, sortDir: ctx.sort && ctx.sort.dir, showAll: ctx.showAll, placeIdOf: ctx.placeIdOf }) : '';
  const sum = ctx.table && !ctx.table.inline ? summaryHTML(ctx.table) : '';
  const caveats = cav.length ? `<ul class="ask-cav">${cav.map(s => `<li>${esc(s)}</li>`).join('')}</ul>` : '';
  const dropped = Array.isArray(ctx.dropped) && ctx.dropped.length ? `<p class="ask-dropped">Not applied to the map: ${ctx.dropped.map(esc).join('; ')}.</p>` : '';
  const hl = ctx.hl && ctx.hl.count ? ` · <span class="ask-hl-lab">${esc(ctx.hl.label || 'Outlined')} <span class="ask-hl-n">(${Number(ctx.hl.count).toLocaleString('en-US')} outlined)</span></span>` : '';
  const focus = ctx.focus && ctx.focus.show ? ` <label class="ask-focus"><input type="checkbox" id="ask-focus"${ctx.focus.on ? ' checked' : ''}> Focus</label>` : '';
  const mapLine = ctx.mapShows != null ? `<p class="ask-map"><span class="ask-map-lead">Map now shows:</span> <b id="ask-map-shows">${esc(ctx.mapShows)}</b>${hl}${focus} · <a href="map.html" class="ask-reset">Reset map</a></p>` : '';
  const src = sourcesHTML(ctx.sources, ctx.vintages);
  const log = Array.isArray(ctx.log) && ctx.log.length ? `<details class="ask-log"><summary>How this was answered</summary><ol>${stepsHTML(ctx.log)}</ol><p class="ask-log-foot">${esc([ctx.steps ? `${ctx.steps} model step${ctx.steps === 1 ? '' : 's'}` : '', ctx.model ? `model ${ctx.model}` : '', ctx.verification ? (ok ? 'every number and place name in the summary was found in the tool results' : 'verification failed: ' + strList(ctx.verification.issues, 6).join('; ')) : ''].filter(Boolean).join(' · '))}</p></details>` : '';
  const follow = `<div class="ask-fu">${fu.length ? `<span class="ask-lead">Follow up:</span>${chipsHTML(fu, 'ask-fuq')}` : ''}<button type="button" class="ask-new">New question</button></div>`;
  return `<div class="ask-card" id="ask-card" role="region" aria-label="Answer" tabindex="-1">${x}${head}${body}${read}${notin}${table}${sum}${caveats}${dropped}${mapLine}${src}${log}${follow}<p class="ask-note">${esc(STANDING_NOTE)}</p></div>`;
}

// the table the card shows, from the engine's full result for table.from_call (full: engine.full(id); res: the result the model
// saw, for count / in_scope / sum_pop55_matching), or from the model's inline columns/rows. Rows are objects keyed by column path.
export function prepareTable(table, full, res) {
  if (!table || typeof table !== 'object') return null;
  if (typeof table.from_call === 'string') {
    const rows = full && Array.isArray(full.rows) && full.rows.length ? full.rows : res && Array.isArray(res.rows) && res.rows.length ? res.rows : null; if (!rows) return null;
    const columns = full && Array.isArray(full.columns) && full.columns.length ? full.columns : res && Array.isArray(res.columns) && res.columns.length ? res.columns : Object.keys(rows[0]);
    const tname = res && typeof res.table === 'string' && TABLES[res.table] ? res.table : null;
    const unit = full && UNITS.includes(full.unit) ? full.unit : tname ? UNIT_OF_TABLE[tname] || null : null;
    const sumPop = rows.reduce((s, r) => s + (Number.isFinite(r && r.pop55) ? r.pop55 : 0), 0);
    return { columns, rows, table: tname, unit, count: res && Number.isFinite(res.count) ? res.count : rows.length, in_scope: res && Number.isFinite(res.in_scope) ? res.in_scope : null, sum_pop55: res && Number.isFinite(res.sum_pop55_matching) ? res.sum_pop55_matching : sumPop > 0 ? sumPop : null, ids: full && Array.isArray(full.ids) ? full.ids : null };
  }
  if (Array.isArray(table.columns) && Array.isArray(table.rows) && table.columns.length) {
    const cols = table.columns.map(String).slice(0, 12); const rows = table.rows.filter(Array.isArray).slice(0, TABLE_LIMIT).map(r => Object.fromEntries(cols.map((c, i) => [c, r[i] === undefined ? null : r[i]])));
    return rows.length ? { columns: cols, rows, table: null, unit: null, inline: true } : null; }
  return null;
}
// the map id a table row stands for (district rows carry geoid; county and state rows their id)
export function rowMapId(row, unit) { if (!row || typeof row !== 'object') return null; if (row.geoid && /^\d{4}$/.test(String(row.geoid))) return String(row.geoid); return toMapId(row.id, unit || inferKind(row.id)); }
