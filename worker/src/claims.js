/* Ask the map v3 — the per-place claim check (ASK_CONTRACT.md §6 rule 6).
   Rule 1 (verify.js) checks that every number in the answer appears in some tool result; it cannot tell that a correct number is
   written next to the wrong place ("Cameron County has 18 trials" when 18 is Hidalgo's). final_answer therefore lists its figures
   as claims {place, field, value, call}, and this file checks
   (a) each claim exactly against the result of the call it names (the row with that id, or the result itself for whole-result
       figures, a method's sub-result for "<id>.<n>"); a result the client truncated is checked only as far as it goes;
   (b) the answer text: every number is paired with the place named nearest before it in the same clause (or right after it,
       "33.1% in Montana"); a clause with no place continues the last place named in the sentence; a sentence with no place name
       carries scope figures. The number must equal (or be the written-precision rounding of) a claim value of THAT place.
   checkClaims(answer, ctx, issues) appends plain sentences the model can act on. Pure; no I/O. */
import { numbersIn, numbersWithPos, writtenMatches } from './verify.js';

export const MAX_CLAIMS = 40;
const PLACE_ID_RE = /^(\d{5}|[A-Z]{2}-\d{2}|[A-Z]{2}|US)$/;
const MONTHS = 'january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec';
const CLAUSE_SPLIT = /[;:,()—]|\s(?:and|but|while|whereas|against|versus|vs|compared (?:with|to)|than|or|with|ahead of|behind|followed by|next to|beside|unlike)\s/i;
const SCOPE_LEAD = /\b(?:of|out of|among|across|total of|in all|from)\s+(?:the\s+|all\s+|its\s+)?$/i;   // "38 of 254 …", "182,206 of the 1,180,232 …": a total, not the place's own figure
const STATE_WORDS = /\b(?:statewide|the state(?:'s|’s)?|state-wide|the whole state|the state as a whole)\b/gi;
const US_WORDS = /\b(?:nationally|nationwide|national|the nation(?:'s|’s)?|the country(?:'s|’s)?|countrywide|the United States|across the US)\b|\b(?:U\.S\.|US|America)(?![\w.])/g;
const ABBREV_DOTS = /\b(H\.R|U\.S|D\.C|St|Ste|Mt|Ft|Dr|Mr|Mrs|Ms|Jr|Sr|No|vs|e\.g|i\.e|approx|Inc|Co|S)\.(?=\s|$)/g;
const PH = i => String.fromCharCode(0xE000 + i);   // one private-use character per place mention (no digits, no periods)
const PH_RE = /[-]/g;

const isNum = v => typeof v === 'number' && Number.isFinite(v);
const toNum = v => isNum(v) ? v : typeof v === 'string' && v.trim() !== '' && !Number.isNaN(+v.replace(/,/g, '')) ? +v.replace(/,/g, '') : null;
const looseEq = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();
const short = (v, n = 60) => { const s = typeof v === 'string' ? v : JSON.stringify(v); return s && s.length > n ? s.slice(0, n - 1) + '…' : s; };

// ---------- the results of the question, parsed (cached on the context) ----------
function parsedCalls(ctx) {
  if (ctx._parsed) return ctx._parsed;
  const map = new Map();
  for (const t of ctx.turns || []) {
    const inputs = new Map(); for (const b of t.assistant || []) if (b && b.type === 'tool_use') inputs.set(b.id, { name: b.name, input: b.input && typeof b.input === 'object' ? b.input : {} });
    for (const r of t.results || []) {
      const meta = inputs.get(r.tool_use_id) || { name: null, input: {} };
      let result = null; const text = typeof r.content === 'string' ? r.content : JSON.stringify(r.content ?? '');
      try { const j = JSON.parse(text); if (j && typeof j === 'object' && !(j.truncated === true && typeof j.text === 'string')) result = j; } catch (e) { result = null; }
      const truncated = !result || /…\(truncated\)/.test(text);
      map.set(r.tool_use_id, { id: r.tool_use_id, name: meta.name, input: meta.input, result, truncated, error: !!r.is_error || !!(result && result.error) });
      if (meta.name === 'method' && result && Array.isArray(result.results)) for (const x of result.results) if (x && typeof x.call === 'string') map.set(x.call, { id: x.call, parent: r.tool_use_id, name: x.name, input: x.input || {}, result: x.result && typeof x.result === 'object' ? x.result : null, truncated: truncated || !!(x.result && x.result.truncated), error: !!(x.result && x.result.error) });
    }
  }
  ctx._parsed = map; return map;
}
// every object with an id under a result (rows, matches, reference, related rows), depth-limited
function objectsWithId(o, id, out = [], depth = 0) {
  if (!o || typeof o !== 'object' || depth > 7) return out;
  if (Array.isArray(o)) { for (const x of o) objectsWithId(x, id, out, depth + 1); return out; }
  if (o.id !== undefined && String(o.id) === id) out.push(o);
  for (const v of Object.values(o)) if (v && typeof v === 'object') objectsWithId(v, id, out, depth + 1);
  return out;
}
function namedObjects(o, out = [], depth = 0) {   // {id, name, state?} of every place-like object in a result
  if (!o || typeof o !== 'object' || depth > 7) return out;
  if (Array.isArray(o)) { for (const x of o) namedObjects(x, out, depth + 1); return out; }
  if ((typeof o.id === 'string' || typeof o.id === 'number') && typeof o.name === 'string' && o.name.trim().length >= 3) out.push({ id: String(o.id), name: o.name.trim(), state: typeof o.state === 'string' ? o.state : null });
  for (const v of Object.values(o)) if (v && typeof v === 'object') namedObjects(v, out, depth + 1);
  return out;
}

/** A dotted path into a result or row: keys may themselves contain dots ("oncologists.count", "oncologists.count:sum"), so at each
 *  level the longest key that prefixes the path wins; "[k=v]" picks the list element whose k is v, "[n]" by position, ".length"
 *  counts a list. Returns undefined when the path does not resolve. */
export function resolvePath(obj, path) {
  path = String(path ?? '').replace(/^\./, '');
  if (path === '') return obj;
  if (obj === null || typeof obj !== 'object') return undefined;
  if (Array.isArray(obj)) {
    if (path === 'length') return obj.length;
    let m = path.match(/^\[(\d+)\]\.?(.*)$/); if (m) return resolvePath(obj[+m[1]], m[2]);
    m = path.match(/^\[([^=\]]+)=([^\]]*)\]\.?(.*)$/); if (m) { const el = obj.find(e => e && typeof e === 'object' && e[m[1]] !== undefined && looseEq(e[m[1]], m[2].replace(/^["']|["']$/g, ''))); return el === undefined ? undefined : resolvePath(el, m[3]); }
    return undefined;
  }
  for (const k of Object.keys(obj).sort((a, b) => b.length - a.length)) {
    if (path === k) return obj[k];
    if (path.startsWith(k + '.') || path.startsWith(k + '[')) { const r = resolvePath(obj[k], path.slice(k.length + (path[k.length] === '.' ? 1 : 0))); if (r !== undefined) return r; }
  }
  return undefined;
}
// a claimed value against the result's value: numbers numerically (the claim may round the result to ≥ 2 significant digits),
// strings case-insensitively, a number against a list as its length
function valueMatches(claim, actual) {
  if (actual === undefined) return false;
  if (Array.isArray(actual)) { const c = toNum(claim); if (c !== null) return c === actual.length; return actual.some(x => looseEq(x, claim)) || looseEq(actual.join(', '), claim); }
  if (actual === null) return claim === null || /^(null|none|—|-)$/i.test(String(claim));
  if (typeof actual === 'object') return false;
  const a = toNum(actual), c = toNum(claim);
  if (a !== null && c !== null) { const n = numbersIn(String(claim).replace(/,/g, ''))[0]; return n ? writtenMatches({ ...n, value: c }, a) : a === c; }
  return looseEq(String(actual).trim(), String(claim).trim());
}

// ---------- the places a whole-result figure may be attributed to ----------
function scopePlaces(entry) {
  const out = new Set(); const inp = entry.input || {}; const r = entry.result || {};
  const where = Array.isArray(inp.where) ? inp.where : inp.where && typeof inp.where === 'object' ? [inp.where] : [];
  const walk = list => { for (const c of list) { if (!c || typeof c !== 'object') continue; if (Array.isArray(c.any_of)) { walk(c.any_of); continue; } const vals = Array.isArray(c.value) ? c.value : [c.value]; for (const v of vals) if (typeof v === 'string' || typeof v === 'number') { const s = normPlace(v); if (s) out.add(s); } } };
  walk(where);
  const stateConds = where.filter(c => c && (c.field === 'state' || (inp.table === 'states' && c.field === 'id')) && ['=', 'in'].includes(c.op));
  if (!stateConds.length) out.add('US');
  if (entry.name === 'trials' && r.scope) { if (r.scope.id) out.add(String(r.scope.id)); if (r.scope.state) out.add(String(r.scope.state)); }
  if (entry.name === 'trials' && inp.scope && typeof inp.scope === 'object') for (const v of Object.values(inp.scope)) if (typeof v === 'string') out.add(normPlace(v) || v);
  if (entry.name === 'profile' || entry.name === 'compare') { if (r.id) out.add(String(r.id)); if (inp.id) out.add(normPlace(inp.id) || String(inp.id)); for (const id of inp.ids || []) out.add(normPlace(id) || String(id)); }
  if (entry.name === 'site_info' || entry.name === 'aggregate' && inp.group_by === 'state') out.add('*');
  if (entry.name === 'find_places') out.add('*');
  return out;
}
function normPlace(v) {
  const s = String(v ?? '').trim(); if (!s) return null;
  if (/^(us|usa|u\.s\.?|national|nation|united states|the united states|nationwide)$/i.test(s)) return 'US';
  if (/^[a-z]{2}$/i.test(s) || /^[a-z]{2}-\d{1,2}$/i.test(s)) { const u = s.toUpperCase(); const m = u.match(/^([A-Z]{2})-(\d{1,2})$/); return m ? `${m[1]}-${m[2].padStart(2, '0')}` : u; }
  if (/^\d{4}$/.test(s)) return null;   // a district geoid or a FIPS without its leading zero: resolved against the result below
  return s;
}

// ---------- (a) each claim against its call's result ----------
function checkOneClaim(cl, i, ctx, C, known, issues) {
  const tag = `claims[${i}]`;
  if (!cl || typeof cl !== 'object' || Array.isArray(cl)) { issues.push(`${tag} must be {place, field, value, call}.`); return null; }
  const missing = ['place', 'field', 'value', 'call'].filter(k => cl[k] === undefined || cl[k] === '');
  if (missing.length) { issues.push(`${tag} needs ${missing.join(', ')} ({place, field, value, call}).`); return null; }
  if (typeof cl.value === 'object' && cl.value !== null) { issues.push(`${tag} value must be a number or a string as in the result, not an object; name a leaf field.`); return null; }
  const calls = parsedCalls(ctx); const callId = String(cl.call);
  let entry = calls.get(callId);
  if (!entry) {
    const base = callId.replace(/\.\d+$/, '');
    if (base !== callId && calls.get(base) && calls.get(base).name === 'method' && !calls.get(base).result) return { place: normPlace(cl.place) || String(cl.place), field: String(cl.field), value: cl.value, call: callId, unchecked: true };
    issues.push(`${tag} names call "${callId}", which is not a tool call of this question${calls.size ? ` (calls: ${[...calls.keys()].slice(0, 8).join(', ')})` : ''}; a method's figures use its sub-call ids ("<id>.1").`); return null;
  }
  let place = normPlace(cl.place) || String(cl.place).trim(); const field = String(cl.field).trim();
  if (entry.name === 'method' && entry.result && Array.isArray(entry.result.results)) {   // a method's own id: look in each sub-result
    for (const x of entry.result.results) { const sub = calls.get(x.call); if (!sub) continue; const r = locate(sub, place, field, known); if (r.found && valueMatches(cl.value, r.value)) return { place: r.place, field, value: cl.value, call: x.call }; }
    issues.push(`${tag} names the method call "${callId}"; name the sub-call that holds ${field} (${entry.result.results.map(x => `${x.call} = ${x.name}`).join(', ')}).`); return null;
  }
  if (entry.error) { issues.push(`${tag} names call "${callId}", whose result is an error; cite a call that returned the figure.`); return null; }
  if (!entry.result) return { place, field, value: cl.value, call: callId, unchecked: true };   // truncated beyond reading: only what is present can be checked
  const r = locate(entry, place, field, known);
  if (!r.found) {
    if (entry.truncated) return { place: r.place || place, field, value: cl.value, call: callId, unchecked: true };
    if (r.scopeError) { issues.push(`${tag}: ${field} of call ${callId} is a whole-result figure; its place must be the scope ${[...r.scopes].filter(x => x !== '*').map(x => `"${x}"`).join(' or ') || '"US"'}, not "${cl.place}".`); return null; }
    const row = r.rows[0];
    issues.push(row ? `${tag}: the row "${place}" of call ${callId} has no field "${field}"${Object.keys(row).length ? ` (it has ${Object.keys(row).filter(k => k !== 'id' && k !== 'name').slice(0, 10).join(', ')})` : ''}.` : `${tag}: no row "${cl.place}" in the result of call ${callId}, and "${field}" is not a key of the result; use the row's id as the result spells it, or a result key such as count.`);
    return null;
  }
  if (!valueMatches(cl.value, r.value)) { issues.push(`${tag}: ${r.place} ${field} is ${short(r.value)} in call ${callId}, not ${short(cl.value)}; copy the value from the result.`); return null; }
  return { place: r.place, field, value: cl.value, call: callId };
}
// finds the value a claim names: a row with the place's id (or name), else the result itself when the place is its scope
function locate(entry, place, field, known) {
  const res = entry.result; let rows = objectsWithId(res, place);
  if (!rows.length) {   // a name, a state name, a FIPS without its leading zero, a district geoid: resolve to the row id
    const byName = namedObjects(res).filter(o => looseEq(o.name, place) || looseEq(o.name.split(',')[0], place));
    if (byName.length) { place = byName[0].id; rows = objectsWithId(res, place); }
    else if (/^\d{4}$/.test(place)) { const pad = place.padStart(5, '0'); const hit = objectsWithId(res, pad); if (hit.length) { place = pad; rows = hit; } else { const g = namedObjects(res).find(o => { const x = objectsWithId(res, o.id)[0]; return x && String(x.geoid) === place; }); if (g) { place = g.id; rows = objectsWithId(res, place); } } }
    else { const st = known.stateByName.get(place.toLowerCase()); if (st) { place = st; rows = objectsWithId(res, place); } }
  }
  for (const o of rows) { const v = resolvePath(o, field); if (v !== undefined) return { found: true, value: v, place, rows }; }
  const top = resolvePath(res, field);
  if (top !== undefined) {
    const scopes = scopePlaces(entry);
    if (scopes.has('*') || scopes.has(place) || rows.some(o => o === res)) return { found: true, value: top, place, rows };
    return { found: false, scopeError: true, scopes, place, rows };
  }
  return { found: false, place, rows };
}

// numbers that are not figures of a place: years, dates (June 12, 2025-06-12), ZIP codes, phases, codes and classes, bill numbers
export function exemptReason(n, before, after) {
  if (n.mult === 1 && /^(19|20)\d\d$/.test(n.digits) && !/^\s*%/.test(after)) return 'year';
  if (new RegExp(`\\b(?:${MONTHS})\\.?\\s*$`, 'i').test(before) || /\d{4}-(?:\d{2}-)?$/.test(before) || /^-\d{2}(?:-\d{2})?\b/.test(after) && /^\d{4}$/.test(n.digits)) return 'date';
  if (/\b(?:ZIP|ZIP code|zip code|zip|phase|Phase|RUCC|code|codes|class|classes|tier|HR|H\.R\.|S\.|S|bill|NCT)\s*$/.test(before)) return 'label';
  if (/\b(?:RUCC|phase|codes?|class(?:es)?)\s+\d\s*[–-]\s*$/i.test(before)) return 'label';   // "RUCC 4–9", "phase 1-2"
  return null;
}

// ---------- (b) the answer text: which place each number is written next to ----------
function placeIndex(ctx, C, claims) {
  const names = new Map();   // id -> display name
  const states = new Map();  // id -> USPS
  for (const e of parsedCalls(ctx).values()) for (const o of namedObjects(e.result)) { if (!names.has(o.id)) names.set(o.id, o.name); if (o.state && !states.has(o.id)) states.set(o.id, o.state); }
  for (const [code, name] of Object.entries(C.STATES || {})) if (!names.has(code)) names.set(code, name);
  if (!names.has('US')) names.set('US', 'United States');
  const stateByName = new Map(Object.entries(C.STATES || {}).map(([k, v]) => [v.toLowerCase(), k]));
  // name variants -> ids (case-sensitive; the answer names places as the results do)
  const variants = new Map(); const add = (v, id) => { v = v.trim(); if (v.length < 3) return; if (!variants.has(v)) variants.set(v, new Set()); variants.get(v).add(id); };
  const stateNames = new Set(Object.values(C.STATES || {}));
  for (const [id, name] of names) {
    if (/^\d{5}$/.test(id)) {   // "Hidalgo County, Texas" -> "Hidalgo County, TX", "Hidalgo County", "Hidalgo"
      add(name, id); const base = name.replace(/,\s*[^,]+$/, ''); add(base, id); const st = states.get(id); if (st) add(`${base}, ${st}`, id);
      const core = base.replace(/\s+(County|Parish|Borough|Census Area|city|City|Municipality|City and Borough)$/, ''); if (core !== base && core.length >= 4 && !stateNames.has(core)) add(core, id);
    } else if (/^[A-Z]{2}-\d{2}$/.test(id)) {   // "Texas 34th" / "Wyoming at-large"
      add(name, id); add(id, id); const [st, nn] = id.split('-'); const sname = (C.STATES || {})[st] || st;
      if (nn === '00') for (const v of [`${sname}'s at-large`, `${sname}’s at-large`, `${sname} at large`, `${st}-AL`, `${sname}'s at-large district`, `${sname}’s at-large district`]) add(v, id);
      else { const o = ordinal(+nn); for (const v of [`${st} ${+nn}`, `${st}-${+nn}`, `${sname}'s ${o}`, `${sname}’s ${o}`, `${sname} ${o} district`, `${sname}'s ${o} district`, `${sname}’s ${o} district`, `${sname}'s ${o} congressional district`, `${sname}’s ${o} congressional district`, `${o} district of ${sname}`, `${o} congressional district of ${sname}`, `${o} district`, `${o} congressional district`, `${o} District`]) add(v, id); }
    } else if (/^[A-Z]{2}$/.test(id) && (C.STATES || {})[id]) {
      add(name, id); if (id === 'DC') for (const v of ['D.C.', 'Washington, D.C.', 'Washington, DC', 'the District']) add(v, id);
    } else if (id === 'US') { add('United States', 'US'); }
    else add(name, id);   // NCI centers, facilities, members, senators: names as the results spell them
  }
  for (const [dem, st] of Object.entries(C.DEMONYMS || {})) add(dem.replace(/\b\w/g, c => c.toUpperCase()), st);
  const claimPlaces = new Set(claims.map(c => c.place));
  return { names, states, variants, stateByName, claimPlaces };
}
function ordinal(n) { return n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'); }

// [{start, end, ids:Set, anchor?}] — longest match first, non-overlapping; a state name right after "<Unknown Name>, " is part of
// that name ("Bexar, Texas" in nearest_broad_menu), not a mention of the state
export function findMentions(text, ix) {
  const cands = [];
  const wordChar = ch => !!ch && /[\p{L}\p{N}]/u.test(ch);
  for (const [v, ids] of ix.variants) { let from = 0; for (;;) { const i = text.indexOf(v, from); if (i < 0) break; from = i + 1; if (wordChar(text[i - 1]) || (wordChar(text[i + v.length]) && !/^['’]s\b/.test(text.slice(i + v.length)))) continue; cands.push({ start: i, end: i + v.length, ids: new Set(ids) }); } }
  for (const [re, anchor] of [[US_WORDS, 'US'], [STATE_WORDS, 'STATE']]) { const r = new RegExp(re.source, re.flags); let m; while ((m = r.exec(text))) cands.push({ start: m.index, end: m.index + m[0].length, ids: new Set(anchor === 'US' ? ['US'] : []), anchor }); }
  cands.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));
  const out = []; let last = -1;
  for (const c of cands) { if (c.start < last) continue; out.push(c); last = c.end; }
  // a state name right after "<Capitalised word>, " that is not itself part of a mention ("Bexar, Texas") belongs to that name
  return out.filter((m, k) => {
    if (m.anchor || ![...m.ids].every(id => /^[A-Z]{2}$/.test(id))) return true;
    const before = text.slice(Math.max(0, m.start - 40), m.start);
    if (!/[A-Z][\p{L}.'’-]*,\s*$/u.test(before)) return true;
    const prev = out[k - 1];
    return !!(prev && /^,\s*$/.test(text.slice(prev.end, m.start)));
  });
}

// the claims of a set of place ids (the "the state" anchor resolves to the states among the claims and the inherited place's state)
const claimsOf = (byPlace, ids) => [...ids].flatMap(id => byPlace.get(id) || []);
const numClaims = list => list.filter(c => toNum(c.value) !== null);
const matchIn = (n, list) => numClaims(list).filter(c => writtenMatches(n, toNum(c.value)));

export function checkText(answer, ctx, claims, issues) {
  const C = ctx.C; const text = String(answer.answer || '');
  const ix = placeIndex(ctx, C, claims);
  const byPlace = new Map(); for (const c of claims) { if (!byPlace.has(c.place)) byPlace.set(c.place, []); byPlace.get(c.place).push(c); }
  const mentions = findMentions(text, ix);
  const mentioned = new Set(mentions.flatMap(m => [...m.ids]));
  const scopeClaims = claims.filter(c => !mentioned.has(c.place));   // figures of places the answer never names: the scope
  const display = id => ix.names.get(id) || id;
  // the masked text: one private-use character per mention, abbreviation dots removed (so sentences split cleanly)
  let masked = ''; let pos = 0; mentions.forEach((m, k) => { masked += text.slice(pos, m.start) + PH(k); pos = m.end; }); masked += text.slice(pos);
  masked = masked.replace(ABBREV_DOTS, m => m.replace(/\./g, ''));
  const sentences = masked.split(/(?<=[.!?])\s+/);
  let lastPlaceBefore = null;   // the last mention of the earlier sentences
  const statesOfClaims = new Set(claims.map(c => c.place).filter(p => /^[A-Z]{2}$/.test(p) && (C.STATES || {})[p]));
  const idsOf = (k, inheritedState) => { const m = mentions[k]; if (m.anchor === 'STATE') { const s = new Set(statesOfClaims); if (inheritedState) s.add(inheritedState); return s; } return m.ids; };
  const stateOfIds = ids => { for (const id of ids) { if (/^[A-Z]{2}$/.test(id)) return id; const st = ix.states.get(id) || (/^[A-Z]{2}-\d{2}$/.test(id) ? id.slice(0, 2) : null); if (st) return st; } return null; };
  for (const sent of sentences) {
    const sentMentions = [...sent.matchAll(PH_RE)].map(m => m[0].charCodeAt(0) - 0xE000);
    const respectively = /\brespectively\b/i.test(sent);
    const clauses = []; { const re = new RegExp(CLAUSE_SPLIT.source, 'gi'); let m, start = 0; while ((m = re.exec(sent))) { clauses.push({ text: sent.slice(start, m.index), off: start }); start = m.index + m[0].length; } clauses.push({ text: sent.slice(start), off: start }); }
    const clauseOf = idx => clauses.findIndex(c => idx >= c.off && idx <= c.off + c.text.length);
    const phPositions = [...sent.matchAll(PH_RE)].map(m => ({ k: m[0].charCodeAt(0) - 0xE000, at: m.index }));
    for (const n of numbersWithPos(sent.replace(PH_RE, '⁣'))) {   // the placeholder becomes an invisible separator for the number scan (positions kept)
      const before = sent.slice(Math.max(0, n.index - 24), n.index), after = sent.slice(n.end, n.end + 24);
      if (exemptReason(n, before.replace(PH_RE, ' '), after)) continue;
      const exempt = ctx.constants.has(n.digits) && n.mult === 1 || ctx.questionDigits.has(n.digits);
      const ci = clauseOf(n.index); const cl = clauses[ci] || { off: 0, text: sent };
      const inClause = phPositions.filter(p => p.at >= cl.off && p.at < cl.off + cl.text.length);
      const prevIn = inClause.filter(p => p.at < n.index).pop(), nextIn = inClause.find(p => p.at > n.index);
      const prevSent = phPositions.filter(p => p.at < cl.off).pop(), nextSent = phPositions.find(p => p.at >= cl.off + cl.text.length);
      let mode, k = null;
      if (prevIn) { mode = 'strict'; k = prevIn.k; } else if (nextIn) { mode = 'strict'; k = nextIn.k; }
      else if (prevSent) { mode = 'inherited'; k = prevSent.k; } else if (nextSent) { mode = 'inherited'; k = nextSent.k; }
      else mode = 'placeless';
      const inheritedState = lastPlaceBefore !== null ? stateOfIds(mentions[lastPlaceBefore].ids) : null;
      const ids = k !== null ? idsOf(k, stateOfIds(prevSent ? mentions[prevSent.k].ids : []) || inheritedState) : lastPlaceBefore !== null ? idsOf(lastPlaceBefore, null) : new Set();
      const own = claimsOf(byPlace, ids);
      const snippet = `"${n.raw}${(after.replace(PH_RE, '').match(/^\s*%?\s*[\p{L}+-]+/u) || [''])[0].replace(/^%/, '')}"`;
      const ownNames = [...ids].map(display).join(' / ');
      if (respectively) {   // "Wyoming and Montana have 87% and 33.1%, respectively": the figure must belong to a place of the sentence
        const all = claimsOf(byPlace, new Set(sentMentions.flatMap(j => [...idsOf(j, null)])));
        if (!exempt && !matchIn(n, [...all, ...scopeClaims]).length) issues.push(`${snippet} matches no claim of the places in its sentence; list it in claims, or write each figure next to its own place instead of "respectively".`);
        continue;
      }
      if (matchIn(n, own).length) continue;
      if (mode !== 'strict' && matchIn(n, scopeClaims).length) continue;
      if (mode === 'strict' && SCOPE_LEAD.test(before.replace(PH_RE, ' ')) && matchIn(n, scopeClaims).length) continue;
      const others = claims.filter(c => !ids.has(c.place));
      const elsewhere = matchIn(n, others);
      if (exempt) {   // a constant or a question number: rejected only when it is plainly another place's figure on a field this place also claims
        const sentIds = new Set(sentMentions.flatMap(j => [...idsOf(j, null)]));
        const swap = elsewhere.find(c => sentIds.has(c.place) && own.some(o => o.field === c.field) && Math.abs(toNum(c.value) - n.value) < 1e-9);
        if (!swap) continue;
      }
      if (mode === 'placeless') {
        if (elsewhere.length) issues.push(`${snippet} is in a sentence that names no place, but the claims give it to ${[...new Set(elsewhere.map(c => display(c.place)))].join(' and ')}; name the place in that sentence.`);
        else issues.push(`${snippet} in answer is not listed in claims; add {place, field, value, call} for it (a whole-result figure takes the scope as place, e.g. "${[...statesOfClaims][0] || 'US'}").`);
        continue;
      }
      const ownText = own.length ? numClaims(own).slice(0, 4).map(c => `${short(c.value, 20)} ${c.field}`).join(', ') : null;
      if (elsewhere.length) issues.push(`${snippet} is written next to ${ownNames}, but the claims give ${ownNames} ${ownText || 'no figure'} and ${[...new Set(elsewhere.map(c => display(c.place)))].join(' and ')} ${short(elsewhere[0].value, 20)} ${elsewhere[0].field}; write each figure next to its own place.`);
      else if (!own.length) issues.push(`${snippet} is written next to ${ownNames}, but no claim lists a figure for ${ownNames}; add the claim (place "${[...ids][0] || '?'}") or move the figure next to the place it belongs to.`);
      else issues.push(`${snippet} is written next to ${ownNames}, but the claims give ${ownNames} only ${ownText}; add the claim for this figure or correct it.`);
    }
    if (sentMentions.length) lastPlaceBefore = sentMentions[sentMentions.length - 1];
  }
}

// ---------- entry point ----------
/** Rule 6: claims are well-formed, each matches its call's result, and every figure in answer sits next to its own place. */
export function checkClaims(answer, ctx, issues) {
  const C = ctx.C; const text = String(answer.answer || '');
  const raw = answer.claims;
  if (raw !== undefined && raw !== null && !Array.isArray(raw)) { issues.push('claims must be a list of {place, field, value, call}.'); return; }
  const list = Array.isArray(raw) ? raw : [];
  if (list.length > MAX_CLAIMS) issues.push(`claims has ${list.length} entries; at most ${MAX_CLAIMS} (list the figures the answer writes, nothing more).`);
  const known = { stateByName: new Map(Object.entries(C.STATES || {}).map(([k, v]) => [v.toLowerCase(), k])) };
  const ok = []; list.slice(0, MAX_CLAIMS).forEach((cl, i) => { const r = checkOneClaim(cl, i, ctx, C, known, issues); if (r) ok.push(r); });
  // figures that need a claim: numbers outside years, dates, ZIPs, phases and codes, constants and the question's own numbers
  const figures = numbersWithPos(text).filter(n => !exemptReason(n, text.slice(Math.max(0, n.index - 24), n.index), text.slice(n.end, n.end + 24)) && !(ctx.constants.has(n.digits) && n.mult === 1) && !ctx.questionDigits.has(n.digits));
  if (!list.length) { if (figures.length) issues.push(`answer writes figures (${[...new Set(figures.map(n => n.raw))].slice(0, 6).join(', ')}) but final_answer.claims is empty: list each figure as {place, field, value, call} (see CLAIMS).`); return; }
  checkText(answer, ctx, ok, issues);
}
