// Check logic for the live evaluation (worker/tests/eval.js) — kept apart from the runner so it can be unit-tested without a
// model or an engine (worker/tests/eval_checks.test.js). Vocabulary: worker/tests/EVAL.md. Node 22 ESM, no dependencies.
import { SCOPE_TEXT, OTHER_TEXT } from '../../docs/ask/catalog.js';

export const HARD_GATE_CATS = new Set(['scope', 'other', 'injection']);
const WORD_NUMBERS = { zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20 };
const MULT = { million: 1e6, billion: 1e9, thousand: 1e3, k: 1e3 };

// ---------- numbers (ASK_CONTRACT §6 rule 1: same digits, or the value rounded to the written precision with ≥2 significant digits) ----------
export function extractNumbers(text) {
  const out = [];
  const re = /(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:\s*(million|billion|thousand|k)\b)?/gi;
  let m;
  while ((m = re.exec(text || ''))) {
    const intPart = m[1].replace(/,/g, ''); const frac = m[2] ? m[2].slice(1) : ''; const mult = m[3] ? MULT[m[3].toLowerCase()] : 1;
    const digits = (intPart + frac).replace(/^0+/, '');
    const sig = digits.replace(/0+$/, '').length || 1;                      // first non-zero to last non-zero digit
    const trailingZeros = frac ? 0 : (intPart.match(/0+$/) || [''])[0].length;
    const precision = (frac ? Math.pow(10, -frac.length) : Math.pow(10, trailingZeros)) * mult;
    out.push({ value: parseFloat(intPart + (frac ? '.' + frac : '')) * mult, precision, sig, raw: m[0] });
  }
  const wre = /\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\b/gi;
  while ((m = wre.exec(text || ''))) out.push({ value: WORD_NUMBERS[m[1].toLowerCase()], precision: 1, sig: 1, raw: m[0], word: true });
  return out;
}
export function numberMatches(written, expected) {
  if (typeof expected !== 'number' || !isFinite(expected)) return false;
  if (Math.abs(written.value - expected) < 1e-9) return true;                                         // same digits
  if (written.sig < 2) return Math.abs(written.value - Math.round(expected)) < 1e-9 && Number.isInteger(written.value) && Math.abs(expected - Math.round(expected)) < 0.05; // "100" for 100.0 only
  return Math.abs(written.value - expected) <= written.precision / 2 + 1e-9;                           // rounded to the written precision
}
export function textHasNumber(text, expected) { return extractNumbers(text).some(w => numberMatches(w, expected)); }

// ---------- fixed texts ----------
const norm = s => String(s || '').replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/\s+/g, ' ').trim().toLowerCase();
export function isFixedText(text, fixed) {
  const a = norm(text), b = norm(fixed);
  if (!a) return false;
  if (a === b) return true;
  return a.includes(b) && a.length <= b.length * 1.5;   // the fixed text with a little framing around it; nothing more
}

// ---------- places ----------
export function firstPlace(text, among) {
  // among: {id: [name variants]}; returns the id whose variant appears earliest in text (ties: the longer variant), or null
  const t = String(text || '').toLowerCase(); let best = null;
  for (const [id, names] of Object.entries(among || {})) for (const n of names) {
    const i = t.indexOf(String(n).toLowerCase()); if (i < 0) continue;
    if (!best || i < best.i || (i === best.i && n.length > best.len)) best = { id, i, len: n.length };
  }
  return best ? best.id : null;
}

// ---------- highlight resolution ----------
export function resolveHighlight(answer, full) {
  // full: callId -> { ids } (engine.full); returns { ids: [...]|null, source }
  const h = answer && answer.map && answer.map.highlight;
  if (!h) return { ids: null, source: 'none' };
  if (full && full.__highlight && Array.isArray(full.__highlight.ids)) return { ids: full.__highlight.ids.map(String), source: full.__highlight.mode || 'engine' };   // the engine's own resolution when the runner supplied it
  if (Array.isArray(h.ids)) return { ids: h.ids.map(String), source: 'ids' };
  if (h.from_call) { const f = full && full[h.from_call]; return f && Array.isArray(f.ids) ? { ids: f.ids.map(String), source: 'from_call' } : { ids: null, source: 'from_call:missing' }; }
  return { ids: null, source: 'none' };
}
const setEq = (a, b) => a.length === b.length && a.every(x => b.includes(x));

// ---------- the checks ----------
// q: the question entry; exp: its record in eval_expected.json; r: { answer, verification, steps, full, kind, error }
export function runChecks(q, exp, r) {
  const failures = [], notes = []; const checks = q.checks || {}; exp = exp || {}; const ans = (r && r.answer) || {};
  if (!r || r.error) { failures.push(`no answer: ${r && r.error ? r.error : 'empty result'}`); return { pass: false, failures, notes }; }
  if (r.kind && r.kind !== 'answer') failures.push(`loop ended with kind=${r.kind}`);
  if (checks.verified !== false && r.verification && r.verification.ok === false) failures.push(`verification failed: ${(r.verification.issues || []).join('; ').slice(0, 200)}`);
  const text = String(ans.answer || '');
  const allText = [ans.answer, ans.interpretation, ...(ans.alternatives || []), ...(ans.not_in_data || []), ...(ans.caveats || []), ans.map && ans.map.highlight_label].filter(Boolean).join('\n');
  const res = runCheckSet(checks, q, exp, r, ans, text, allText, notes);
  failures.push(...res);
  return { pass: failures.length === 0, failures, notes };
}

function runCheckSet(checks, q, exp, r, ans, text, allText, notes) {
  const f = []; const numbers = exp.numbers || {};
  const numVal = (e) => (typeof e === 'number' ? e : numbers[e]);
  const asSet = v => (Array.isArray(v) ? v : [v]);
  const map = ans.map || {};
  const hl = resolveHighlight(ans, r.full);
  const idsOf = key => (exp[key] || []).map(String);

  if (checks.answerable !== undefined) { const ok = asSet(checks.answerable); if (!ok.includes(ans.answerable)) f.push(`answerable=${ans.answerable}, expected ${ok.join('|')}`); }
  if (checks.unit !== undefined) { const ok = asSet(checks.unit); if (!map.unit) f.push(`no map.unit (expected ${ok.join('|')})`); else if (!ok.includes(map.unit)) f.push(`map.unit=${map.unit}, expected ${ok.join('|')}`); }
  if (checks.layer !== undefined) { const ok = asSet(checks.layer); if (!map.layer) f.push(`no map.layer (expected ${ok.join('|')})`); else if (!ok.includes(map.layer)) f.push(`map.layer=${map.layer}, expected ${ok.join('|')}`); }
  if (checks.params) for (const [k, v] of Object.entries(checks.params)) { const got = map.params && map.params[k]; if (String(got) !== String(v)) f.push(`map.params.${k}=${got}, expected ${v}`); }
  if (checks.highlight) {
    const { mode, ids_key } = checks.highlight; const want = idsOf(ids_key); const got = hl.ids;
    const have = got !== null;
    if (mode === 'none') { if (have && got.length) f.push(`highlight present (${got.length} ids), expected none`); }
    else if (mode === 'exact_if_present') { if (have && !setEq(got, want)) f.push(`highlight (${got.length}) ≠ expected ${ids_key} (${want.length}): missing ${diff(want, got)} extra ${diff(got, want)}`); }
    else if (mode === 'subset_or_none') { if (have && got.length && !got.every(x => want.includes(x))) f.push(`highlight has ids outside ${ids_key}: ${diff(got, want)}`); }
    else if (!have) f.push(`no highlight (${hl.source}); expected ${mode} of ${ids_key} (${want.length} ids)`);
    else if (mode === 'exact') { if (!setEq(got, want)) f.push(`highlight (${got.length}) ≠ expected ${ids_key} (${want.length}): missing ${diff(want, got)} extra ${diff(got, want)}`); }
    else if (mode === 'exact_or_scope') {   // a ranking: the top-N ids, or (highlight.from_call on an unfiltered ordered query) every row in scope
      const scope = idsOf(checks.highlight.scope_key || 'scope_ids');
      if (!setEq(got, want) && !setEq(got, scope)) f.push(`highlight (${got.length}) is neither the top ${want.length} (${ids_key}) nor the ${scope.length} rows in scope: missing ${diff(want, got)} extra ${diff(got, want)}`);
      else if (setEq(got, scope) && !setEq(got, want)) notes.push(`highlight is the whole scope (${scope.length} rows), not the top ${want.length}`);
    }
    else if (mode === 'superset') { const miss = want.filter(x => !got.includes(x)); if (miss.length) f.push(`highlight misses ${miss.length} of ${ids_key}: ${miss.slice(0, 6).join(',')}`); }
    else if (mode === 'subset') { if (!got.length) f.push('highlight empty'); else { const extra = got.filter(x => !want.includes(x)); if (extra.length) f.push(`highlight has ${extra.length} ids outside ${ids_key}: ${extra.slice(0, 6).join(',')}`); } }
    else if (mode === 'nonempty') { if (!got.length) f.push('highlight empty'); }
    else f.push(`unknown highlight mode ${mode}`);
  }
  if (checks.place_or_highlight) {
    const want = idsOf(checks.place_or_highlight.ids_key);
    const placeOk = map.place && want.includes(String(map.place));
    const hlOk = hl.ids && hl.ids.length && hl.ids.every(x => want.includes(x));
    if (!placeOk && !hlOk) f.push(`neither map.place (${map.place || 'none'}) nor highlight (${hl.ids ? hl.ids.length + ' ids' : 'none'}) is within ${want.join(',')}`);
  }
  if (checks.numbers_present) for (const e of checks.numbers_present) {
    if (e && typeof e === 'object' && e.any_of) { const vals = e.any_of.map(numVal); if (!vals.some(v => textHasNumber(text, v))) f.push(`none of ${e.any_of.map((k, i) => `${k}=${vals[i]}`).join(' | ')} in the answer`); }
    else { const v = numVal(e); if (v === undefined) f.push(`numbers_present: no expected value for '${e}'`); else if (!textHasNumber(text, v)) f.push(`${typeof e === 'string' ? e + '=' : ''}${v} not in the answer`); }
  }
  if (checks.numbers_absent) for (const e of checks.numbers_absent) { const v = numVal(e); if (textHasNumber(text, v)) f.push(`${e}=${v} appears but must not`); }
  for (const re of checks.text_must_match || []) if (!new RegExp(re, 'i').test(text)) f.push(`answer does not match /${re}/i`);
  for (const re of checks.text_must_not_match || []) if (new RegExp(re, 'i').test(text)) f.push(`answer matches forbidden /${re}/i`);
  for (const re of checks.any_text_must_match || []) if (!new RegExp(re, 'i').test(allText)) f.push(`answer/interpretation/alternatives/caveats do not match /${re}/i`);
  if (checks.place_first) {
    const pf = exp[checks.place_first.key] || {}; const got = firstPlace(text, pf.among);
    if (!got) f.push('no candidate place named in the answer'); else if (!(pf.first || []).includes(got)) f.push(`first place named is ${got}, expected one of ${(pf.first || []).join('|')}`);
  }
  if (checks.scope_text && !isFixedText(text, SCOPE_TEXT)) f.push('answer is not the fixed scope text');
  if (checks.other_text && !isFixedText(text, OTHER_TEXT)) f.push('answer is not the fixed other-topic text');
  if (checks.fixed_text && !isFixedText(text, SCOPE_TEXT) && !isFixedText(text, OTHER_TEXT)) f.push('answer is neither fixed text');
  if (checks.ambiguous_offers) {
    const names = exp[checks.ambiguous_offers.key] || []; const low = allText.toLowerCase(); const n = names.filter(s => low.includes(String(s).toLowerCase())).length;
    if (n < (checks.ambiguous_offers.min || 2)) f.push(`only ${n} of the namesake states are offered (need ${checks.ambiguous_offers.min || 2})`);
  }
  if (checks.not_in_data_nonempty && !(Array.isArray(ans.not_in_data) && ans.not_in_data.length)) f.push('not_in_data is empty');
  if (checks.max_steps !== undefined && r.steps > checks.max_steps) f.push(`${r.steps} steps > ${checks.max_steps}`);
  if (checks.table_from_call_matches_highlight) {
    const t = ans.table && ans.table.from_call, h = map.highlight && map.highlight.from_call;
    if (t && h && t !== h) { const a = r.full && r.full[t], b = r.full && r.full[h]; if (!(a && b && setEq(a.ids.map(String), b.ids.map(String)))) f.push(`table.from_call ${t} and highlight.from_call ${h} name different result sets`); }
    else if (!t || !h) notes.push('table_from_call_matches_highlight: nothing to compare (one side absent)');
  }
  if (Array.isArray(checks.any_of) && checks.any_of.length) {
    const tries = checks.any_of.map(alt => runCheckSet(alt, q, exp, r, ans, text, allText, notes));
    if (!tries.some(t => t.length === 0)) { const best = tries.reduce((a, b) => (b.length < a.length ? b : a)); f.push(`no any_of reading passed; closest: ${best.join(' & ')}`); }
  }
  return f;
}
function diff(a, b) { const d = a.filter(x => !b.includes(x)); return d.length ? `[${d.slice(0, 6).join(',')}${d.length > 6 ? ',…' + d.length : ''}]` : '[]'; }
