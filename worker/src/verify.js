/* Ask the map v3 — verification of the model's final_answer against the tool results of the question (ASK_CONTRACT.md §6).
   verify(answer, context) -> {ok, issues:[plain sentences the model can act on]}
   context: { question, turns, catalog? } where turns are the protocol turns ({assistant blocks, results}) of this question.
   Rules: (1) every number in answer / interpretation / caveats / not_in_data is in a tool result (same digits), or a tool-result
   number rounded to the written precision (≥ 2 significant digits; million / thousand / k handled), or in the question, or a
   definitional constant / data vintage; number words above ten likewise. (2) Every capitalised token in `answer` outside the
   stoplist (sentence words, the site's vocabulary, state names, the catalog text, the question) appears in a tool result.
   (3) ids, from_call, unit / layer / params / state / sources are valid. (4) Style: no URLs, markdown, first person, advice,
   "available to" claims; ≤ 1,200 characters. (5) answerable "no" needs not_in_data. Pure function; no I/O. */
import * as DEFAULT_CATALOG from '../../docs/ask/catalog.js';
import { catalogText, CALL_TOOLS_WITH_IDS, UNITS } from './prompt.js';
import { checkClaims } from './claims.js';

export const MAX_ANSWER_CHARS = 1200;
const LIMITS = { alternatives: 3, not_in_data: 4, caveats: 5, follow_ups: 3 };
const EXTRA_CONSTANTS = ['100000', '100,000', '0', '1', '2', '3', '4', '9'];   // "per 100,000"; zero; classes 1–4 and RUCC 1–9 are definitional codes

// ---------- numbers ----------
const PHONE_RE = /\b1-8\d\d-(?:\d-?[A-Z]{2,}|\d{3}-\d{4})\b|\b\d{3}-\d{3}-\d{4}\b/gi;
const NCT_RE = /\bNCT\d{6,}\b/g;
const DISTRICT_ID_RE = /\b[A-Z]{2}-\d{2}\b/g;
const NUM_RE = /(?<![\w.])(-?)\$?(\d[\d,]*(?:\.\d+)?)(?:\s*(million|billion|thousand|percent|k)\b|%)?(?![\w])/gi;
const MULT = { million: 1e6, billion: 1e9, thousand: 1e3, k: 1e3 };
const SMALL_WORDS = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, zero: 0 };
const WORDS = { eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90, hundred: 100, thousand: 1000, million: 1e6, billion: 1e9, dozen: 12 };
const VAGUE_RE = /\b(hundreds|thousands|millions|billions|dozens|tens of thousands|countless|numerous|(?:a few|several|many) (?:hundred|thousand|million))\b/gi;
// a number word, optionally compounded ("twenty-three") and scaled ("fifteen hundred", "half a million", "a thousand")
const WORD_RE = new RegExp(`\\b(a|an|half a|half|${Object.keys(SMALL_WORDS).join('|')}|${Object.keys(WORDS).join('|')})(?:[-\\s](one|two|three|four|five|six|seven|eight|nine))?(?:\\s+(hundred|thousand|million|billion))?\\b`, 'gi');

const blank = m => ' '.repeat(m.length);   // same-length masking keeps the positions of the numbers (numbersWithPos)
const stripIds = s => String(s || '').replace(PHONE_RE, blank).replace(NCT_RE, blank).replace(DISTRICT_ID_RE, blank);
/** Every number written in a text: [{raw, digits (no commas/sign), value (with sign and multiplier), sig, mult}]. */
export function numbersIn(text) { return numbersWithPos(text).map(({ index, end, ...n }) => n); }
/** numbersIn with the position of each number in the text: [{…, index, end}] (claims.js pairs numbers with place names). */
export function numbersWithPos(text) {
  const out = []; const t = stripIds(text); let m; const re = new RegExp(NUM_RE.source, 'gi');
  while ((m = re.exec(t))) {
    let digits = m[2].replace(/,/g, '').replace(/,+$/, ''); if (!/\d/.test(digits)) continue;
    const word = (m[3] || '').toLowerCase(); const mult = MULT[word] || 1;
    const value = parseFloat(digits) * (m[1] ? -1 : 1) * mult;
    const raw = m[0].trim().replace(/,+$/, ''); const index = m.index + (m[0].length - m[0].trimStart().length);
    out.push({ raw, digits, value, sig: sigDigits(digits), mult, word, index, end: index + raw.length });
  }
  return out;
}
function sigDigits(digits) { let d = digits.replace(/^0+/, ''); if (d.includes('.')) d = d.replace('.', '').replace(/^0+/, ''); else d = d.replace(/0+$/, ''); return d.length; }
// the digits a number occupies once written out (trailing zeros and the multiplier word included): "100 million" → 9, "20,000" → 5
function writtenDigits(n) { const v = Math.abs(n.value); if (Number.isInteger(v)) return String(v).replace(/^0+/, '').length; let d = String(n.digits).replace(/^0+/, ''); if (d.includes('.')) d = d.replace('.', '').replace(/^0+/, ''); return d.length; }
function sigRound(r, p) { if (r === 0) return 0; const e = Math.floor(Math.log10(Math.abs(r))); const f = Math.pow(10, p - 1 - e); return Math.round(r * f) / f; }
const near = (a, b) => Math.abs(a - b) <= Math.max(1e-9, Math.abs(b) * 1e-9);
/** Does a written number (from numbersIn) stand for the value v under rule 1 (same digits, or v rounded to the written precision)? */
export function writtenMatches(n, v) {
  if (typeof v !== 'number' || !Number.isFinite(v)) return false;
  if (near(v, n.value)) return true;
  const lo = Math.max(2, sigDigits(n.digits)), hi = Math.max(lo, writtenDigits(n));
  for (let p = lo; p <= hi; p++) if (near(sigRound(v, p), n.value)) return true;
  return false;
}

/** Number words above ten in a text (digits already removed): [{raw, value}]; one–ten are always allowed, but "fifteen hundred",
 *  "two thousand" and "half a million" are one number each (never "fifteen" and a constant "hundred"). */
export function numberWordsIn(text) {
  const t = String(text || '').replace(new RegExp(NUM_RE.source, 'gi'), ' ');   // "11.8 million" is a number, not a word
  const out = []; let m; const re = new RegExp(WORD_RE.source, 'gi');
  while ((m = re.exec(t))) {
    const w = m[1].toLowerCase(); const small = m[2] ? SMALL_WORDS[m[2].toLowerCase()] : 0; const scale = m[3] ? WORDS[m[3].toLowerCase()] : null;
    let v;
    if (w === 'a' || w === 'an') { if (!scale) continue; v = 1; }
    else if (w === 'half a' || w === 'half') { if (!scale) continue; v = 0.5; }
    else if (w in SMALL_WORDS) { if (!scale) continue; v = SMALL_WORDS[w] + small; }   // one–ten alone are allowed
    else v = WORDS[w] + small;
    out.push({ raw: m[0], value: scale ? v * scale : v });
  }
  return out;
}

// ---------- the context built from the turns ----------
export function buildContext(ctx) {
  const C = ctx.catalog || DEFAULT_CATALOG;
  const turns = Array.isArray(ctx.turns) ? ctx.turns : [];
  const resultTexts = []; const callIds = new Map(); const queryResults = [];   // queryResults: truncated query results, to steer highlight.ids to from_call
  for (const t of turns) {
    for (const b of t.assistant || []) if (b && b.type === 'tool_use') callIds.set(b.id, b.name);
    for (const r of t.results || []) {
      const text = typeof r.content === 'string' ? r.content : JSON.stringify(r.content ?? ''); resultTexts.push(text);
      if (callIds.get(r.tool_use_id) === 'method') { try { const j = JSON.parse(text); for (const x of (j && Array.isArray(j.results) ? j.results : [])) if (x && typeof x.call === 'string') callIds.set(x.call, String(x.name || '')); } catch (e) { /* a truncated method result: its sub-call ids are accepted by their prefix */ } }
      if (callIds.get(r.tool_use_id) === 'query' && /"ids_truncated":\s*true/.test(text)) { try { const j = JSON.parse(text); if (j && Array.isArray(j.rows)) queryResults.push({ id: r.tool_use_id, count: j.count, returned: j.returned, rowIds: new Set(j.rows.map(x => String(x && x.id))) }); } catch (e) { /* a truncated or non-JSON result: nothing to steer */ } }
    }
  }
  const resultsText = resultTexts.join('\n'); const resultsLower = resultsText.toLowerCase();
  const resultNums = numbersIn(resultsText); const resultDigits = new Set(resultNums.map(n => n.digits)); const resultValues = [...new Set(resultNums.map(n => n.value))];
  const question = String(ctx.question || '');
  const questionDigits = new Set(numbersIn(question).map(n => n.digits)); const questionWords = new Set(numberWordsIn(question).map(n => n.value));
  const constants = new Set([...(C.CONSTANTS || []), ...EXTRA_CONSTANTS].map(s => String(s).replace(/,/g, '')));
  for (const s of Object.values(C.SOURCES || {})) for (const n of numbersIn(`${s.vintage || ''} ${s.label || ''}`)) constants.add(n.digits);
  const catText = ctx.catalogText || catalogText(C);
  const stop = new Set(FIXED_STOP);
  for (const [code, name] of Object.entries(C.STATES || {})) { stop.add(code.toLowerCase()); for (const w of name.toLowerCase().split(/[^a-z]+/)) if (w) stop.add(w); }
  for (const d of Object.keys(C.DEMONYMS || {})) for (const w of d.split(/\s+/)) { stop.add(w); stop.add(w + 's'); }   // Ohioans, Texans, New Yorkers
  for (const w of wordsOf(catText)) stop.add(w);
  for (const w of wordsOf(question)) stop.add(w);
  for (const w of wordsOf(C.SCOPE_TEXT + ' ' + C.OTHER_TEXT)) stop.add(w);
  for (const t of Object.values(C.SITE_INFO || {})) for (const w of wordsOf(`${t.title} ${t.text}`)) stop.add(w);
  for (const [phrase] of C.CANCER_WORDS || []) for (const w of wordsOf(phrase)) stop.add(w);   // "Ovarian", "Uterine", "Glioblastoma" at a sentence start
  // the catalog's quoted examples ("Hidalgo County, Texas", "Mays Cancer Center") are illustrations, not vocabulary: a place or
  // center named in an answer must still come from a result
  const keep = new Set(FIXED_STOP); for (const name of Object.values(C.STATES || {})) for (const w of name.toLowerCase().split(/[^a-z]+/)) keep.add(w);
  for (const T of Object.values(C.TABLES || {})) for (const m of `${T.name_desc || ''} ${T.id_desc || ''}`.match(/"[^"]+"/g) || []) for (const w of wordsOf(m)) if (!keep.has(w)) stop.delete(w);
  for (const fd of Object.values(C.TABLES || {}).flatMap(T => T.fields)) for (const m of String(fd.desc || '').match(/e\.g\. "[^"]+"/g) || []) for (const w of wordsOf(m)) if (!keep.has(w)) stop.delete(w);
  return { C, turns, question, resultsText, resultsLower, resultDigits, resultValues, questionDigits, questionWords, constants, stop, callIds, queryResults, scope: norm(C.SCOPE_TEXT), other: norm(C.OTHER_TEXT) };
}
const norm = s => String(s || '').replace(/\s+/g, ' ').trim();
const wordsOf = s => String(s || '').toLowerCase().split(/[^a-z0-9'’]+/).map(w => w.replace(/['’]s$/, '').replace(/['’]/g, '')).filter(Boolean);

const FIXED_STOP = new Set(`a an the and or but nor so yet if then than as of in on at by for with from to into onto over under above below between among across through within without about around roughly nearly almost just exactly only even again instead otherwise however although though while since until after before during per out up down off all any another other others such same both either neither several few fewer fewest many more most less least much half third quarter each every some none no not nothing yes it its they their them there here these those this that what which who whose whom why how when where whether because
is are was were be been being has have had do does did can could may might will would shall should must
one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion first second third fourth fifth last next
january february march april may june july august september october november december monday tuesday wednesday thursday friday saturday sunday
county counties parish parishes borough boroughs census area city town district districts state states united us america american americans nation national nationally nationwide statewide countrywide congress congressional house senate senator senators representative representatives rep sen member members delegate dr mr ms mrs jr sr
act bill bills nci acs cms usda ers rucc zip zips fips medicare medicaid comprehensive clinical trial trials modernization cancer cancers oncologist oncologists hematology recruiting residents share shares metro nonmetro rural urban road miles mile deaths death incidence mortality rate rates data vacant democrat democrats republican republicans independent phase industry nih federal academic hospital
north south east west new saint st fort mount lake san santa los las el la de du port point grand little big upper lower
map methods key findings sources limits about finder understand information service society blood center centers centre profiles bureau tiger clinicaltrials gov hodgkin non overall together nearby closest farthest furthest highest lowest largest smallest biggest worst best top bottom
texas texan texans hr clinicaltrials.gov u.s you your yours
also altogether anyway apart besides certainly clearly combined compared comparing conversely elsewhere equally especially essentially finally further furthermore generally hence however in-state indeed likewise meanwhile moreover mostly namely nationally naturally nevertheless nonetheless notably often once overall partly perhaps presumably previously rather regardless respectively roughly separately similarly simply specifically statewide still subsequently thus together typically ultimately unlike usually whereas within without
across against along alongside amid behind beneath beside beyond despite except excluding including inside near nearby outside past plus regarding round throughout toward towards unlike upon versus via
add added adds answer answered appear appears apply applies are based become becomes being bring brings call called calls come comes compare compares consider considered count counted counts cover covered covers describe describes draw drawn exclude excluded excludes exist exists fall falls find found follow follows get give given gives go goes hold holds include included includes keep keeps lack lacks lead leads leave leaves lie lies list listed lists live lives look looks make makes match matched matches mean means measure measured measures meet meets note noted notes offer offers place placed put puts rank ranked ranks read reads record records remain remains report reported reports represent represents rest results return returns run runs say says see seen show shown shows sit sits stand stands start starts stay stays take taken takes tell tells tend tends total totals treat treated turn turns use used uses vary varies
able available average averages certain clear close closer combined common current different direct distinct due early equal exact fair far farther few full further greater high higher large larger late later likely limited long longer low lower main major mean median minor missing modest much narrow near nearer net notable open other overall own partial particular poor possible present published rare recent relative remaining roughly short shorter similar single small smaller sole specific steady strong total true typical unclear unknown various very weak whole wide wider worse
figure figures number numbers value values total totals count counts share shares list lists table tables row rows result results answer answers question questions reading readings rule rules measure measures level levels place places area areas part parts rest remainder half third quarter majority minority range gap gaps line lines period periods year years month months week weeks day days time times source sources file files pull pulls note notes caveat caveats case cases site sites center centers people person resident residents household households home homes
therefore currently consequently additionally lastly today now somewhat nobody nowhere something anything everything sometimes always approximately precisely entirely largely mainly partially fully completely
counting using ranking rounding rounded sorted ordered ordering adding applying restricting limiting weighting weighted expressed tied tie ties
sum sums difference differences proportion fraction ratio threshold thresholds cutoff cut-off percent percentage points patient doctor doctors drug drugs gene genes tumor tumors tumour tumours
`.split(/\s+/));

// ---------- the checks ----------
export function verify(answer, context) {
  const issues = [];
  const ctx = context && context.resultsLower !== undefined ? context : buildContext(context || {});
  const C = ctx.C;
  if (!answer || typeof answer !== 'object') return { ok: false, issues: ['final_answer input must be an object with answer, answerable and interpretation.'] };
  const text = typeof answer.answer === 'string' ? answer.answer : '';
  if (!text.trim()) issues.push('answer is empty.');
  if (!['yes', 'partly', 'no'].includes(answer.answerable)) issues.push('answerable must be "yes", "partly" or "no".');
  if (typeof answer.interpretation !== 'string' || !answer.interpretation.trim()) issues.push('interpretation is required: one or two sentences on how the question was read.');
  for (const k of ['alternatives', 'not_in_data', 'caveats', 'follow_ups', 'sources']) {
    if (answer[k] === undefined) continue;
    if (!Array.isArray(answer[k]) || answer[k].some(x => typeof x !== 'string')) issues.push(`${k} must be a list of strings.`);
    else if (LIMITS[k] && answer[k].length > LIMITS[k]) issues.push(`${k} has ${answer[k].length} entries; at most ${LIMITS[k]}.`);
  }
  const fixed = norm(text) === ctx.scope || norm(text) === ctx.other;
  if (answer.answerable === 'no' && !(Array.isArray(answer.not_in_data) && answer.not_in_data.length)) issues.push('answerable "no" requires not_in_data to say what the data does not have (and answer to say briefly what it does have).');
  if (text.length > MAX_ANSWER_CHARS) issues.push(`answer is ${text.length} characters; at most ${MAX_ANSWER_CHARS}.`);

  // 4. style
  if (!fixed) {
    style(text, 'answer', issues, true);
    for (const k of ['interpretation', 'caveats', 'not_in_data', 'alternatives', 'follow_ups', 'highlight_label']) for (const s of listOf(k === 'highlight_label' ? answer.map && answer.map.highlight_label : answer[k])) style(s, k, issues, false);
  }
  // 1. numbers
  if (!fixed) for (const n of numbersIn(text)) checkNumber(n, 'answer', ctx, issues);
  for (const k of ['interpretation', 'caveats', 'not_in_data']) for (const s of listOf(answer[k])) for (const n of numbersIn(s)) checkNumber(n, k, ctx, issues);
  if (!fixed) { for (const w of numberWordsIn(text)) checkNumber({ raw: w.raw, digits: String(w.value), value: w.value, sig: 1, mult: 1 }, 'answer', ctx, issues, true); const vague = text.match(VAGUE_RE); if (vague) for (const v of new Set(vague.map(x => x.toLowerCase()))) if (!ctx.question.toLowerCase().includes(v)) issues.push(`"${v}" is a vague quantity; write the figure from the tool result instead.`); }
  // 2. capitalised tokens and district ids in the answer
  if (!fixed) {
    for (const tok of capitalisedTokens(text)) {
      const low = tok.toLowerCase(); const base = low.replace(/['’]s$/, ''); const nodots = base.replace(/\./g, '');
      if (ctx.stop.has(base) || ctx.stop.has(low) || ctx.stop.has(nodots)) continue;
      if (ctx.resultsLower.includes(base) || ctx.question.toLowerCase().includes(base)) continue;
      if (base.includes('-') && base.split('-').every(p => p.length < 3 || ctx.stop.has(p) || ctx.resultsLower.includes(p))) continue;
      issues.push(`"${tok}" does not appear in any tool result: name only places, people and centers from the results.`);
    }
    for (const id of new Set(text.match(DISTRICT_ID_RE) || [])) if (!ctx.resultsText.includes(id) && !ctx.question.includes(id)) issues.push(`district id ${id} does not appear in any tool result or in the question.`);
  }
  // 3. ids, calls, map, sources
  const map = answer.map;
  if (map !== undefined && map !== null) {
    if (typeof map !== 'object') issues.push('map must be an object.');
    else {
      if (!UNITS.includes(map.unit)) issues.push(`map.unit must be one of ${UNITS.join(', ')}.`);
      const layers = C.MAP_LAYERS[map.unit] || {};
      if (!map.layer || !layers[map.layer]) issues.push(`map.layer "${map.layer}" is not a ${map.unit || ''} layer; choose one of ${Object.keys(layers).join(', ') || 'the unit\'s layers'}.`);
      else if (map.params && typeof map.params === 'object') {
        for (const [k, v] of Object.entries(map.params)) {
          if (!layers[map.layer].params.includes(k)) issues.push(`map.params.${k} is not accepted by layer ${map.layer} (accepts: ${layers[map.layer].params.join(', ') || 'none'}).`);
          else if (!(C.MAP_PARAMS[k] || []).includes(String(v))) issues.push(`map.params.${k} = "${v}" is not one of ${C.MAP_PARAMS[k].join(', ')}.`);
        }
      }
      if (map.state !== undefined && !(map.state in C.STATES)) issues.push(`map.state "${map.state}" is not a USPS state code.`);
      if (map.place !== undefined && !idInResults(String(map.place), ctx)) issues.push(`map.place "${map.place}" does not appear in any tool result.`);
      if (map.highlight !== undefined && map.highlight !== null) {
        if (typeof map.highlight !== 'object') issues.push('map.highlight must be {from_call} or {ids}.');
        else {
          if (map.highlight.from_call !== undefined) checkCall(map.highlight.from_call, 'map.highlight.from_call', ctx, issues);
          if (map.highlight.ids !== undefined) { if (!Array.isArray(map.highlight.ids)) issues.push('map.highlight.ids must be a list of ids.'); else { const bad = map.highlight.ids.filter(id => !idInResults(String(id), ctx)); if (bad.length) issues.push(`map.highlight.ids not in any tool result: ${bad.slice(0, 5).join(', ')}${bad.length > 5 ? ` and ${bad.length - 5} more` : ''}; use highlight.from_call instead.`);
            // the returned rows of a truncated query are not "the matches": a filtered query outlines every matching row through from_call
            const ids = map.highlight.ids.map(String); const partial = ids.length && (ctx.queryResults || []).find(qr => qr.count > ids.length && ids.every(id => qr.rowIds.has(id)));
            if (partial) issues.push(`map.highlight.ids lists ${ids.length} of the ${partial.count} rows matched by call ${partial.id}; set map.highlight = {from_call: "${partial.id}"} (and table.from_call the same) so the map outlines all ${partial.count} and the table carries them; the answer may still name the first few.`); } }
        }
      }
    }
  }
  const table = answer.table;
  if (table !== undefined && table !== null) {
    if (typeof table !== 'object') issues.push('table must be {from_call} or {columns, rows}.');
    else {
      if (table.from_call !== undefined) checkCall(table.from_call, 'table.from_call', ctx, issues);
      if (table.rows !== undefined) { if (!Array.isArray(table.rows) || !Array.isArray(table.columns)) issues.push('table.columns and table.rows must be lists.'); else for (const row of table.rows) for (const cell of (Array.isArray(row) ? row : [])) if (typeof cell === 'number' || (typeof cell === 'string' && /\d/.test(cell))) for (const n of numbersIn(String(cell))) checkNumber(n, 'table.rows', ctx, issues); }
    }
  }
  // 6. claims: each figure paired with its place, checked against its call's result, and the text checked place by place (claims.js)
  if (!fixed) checkClaims(answer, ctx, issues);
  if (Array.isArray(answer.sources)) { const ok = new Set([...Object.keys(C.TABLES), 'trials', 'site_info']); for (const s of answer.sources) if (!ok.has(s)) issues.push(`sources entry "${s}" is not a table; use ${[...ok].join(', ')}.`); }
  return { ok: issues.length === 0, issues: [...new Set(issues)] };
}

const listOf = v => Array.isArray(v) ? v.filter(x => typeof x === 'string') : typeof v === 'string' ? [v] : [];
// bare domains are URLs too, except the registry and Congress sites the catalog itself names ("listed on ClinicalTrials.gov")
const DOMAIN_RE = /\b(?!clinicaltrials\.gov|congress\.gov|house\.gov|senate\.gov|govinfo\.gov)[\w-]+\.(?:com|org|net|io|edu|gov)\b|\b\w+ dot (?:com|org|net|gov)\b/i;
function style(s, field, issues, full) {
  if (/https?:\/\/|www\./i.test(s) || DOMAIN_RE.test(s)) issues.push(`${field} contains a URL; links come from the site, not from the answer.`);
  if (/\*\*|__|`|\*\S[^*\n]*\S\*|^\s*#|^\s*[-*•‣◦▪·–—]\s|^\s*\d+[.)]\s|\[[^\]]+\]\([^)]+\)|<\/?[a-z]+>/m.test(s)) issues.push(`${field} contains markdown or list formatting; write plain sentences.`);
  if (!full) return;
  if (/\bI\b(?![-)])|\bI'(?:m|ve|d|ll)\b|\b[Mm]y\b|\b[Mm]e\b|\b[Ww]e\b|\b[Ww]e're\b|\b[Oo]ur\b|\bus\b/.test(s) || /\bas an ai\b|\blanguage model\b/i.test(s)) issues.push(`${field} uses the first person; write about the data only.`);
  for (const sentence of s.split(/(?<=[.!?])\s+/)) {
    const neg = /\b(not|no|never|cannot|does not|do not|is not|are not)\b/i.test(sentence);
    const m = sentence.match(/\b(should|ought to|recommend\w*|consult\w*|advis(?:e|es|ed|ing|able)|talk to (?:your|a|an)|speak (?:to|with) (?:your|a|an)|check with (?:your|a|an)|reach out to|ask your|see your|contact your|you (?:may|might|can|could|need)|(?:it is|it's|it would be) (?:best|wise|worth|a good idea)|consider (?:enrolling|joining|asking|contacting|calling)|enrol(?:l)?(?:ing)? in|sign up for)\b/i);
    if (m) issues.push(`${field} gives advice ("${m[1]}"); report what the data shows, nothing more.`);
    const e = sentence.match(/\b(eligib\w*)\b|\b(?:you|she|he|they|patients?|people|someone|anyone|who)\s+(?:\w+\s+){0,2}(qualif\w*)\b/i); if (e && !neg) issues.push(`${field} speaks of eligibility ("${e[1] || e[2]}"); the data does not match people to trials.`);
    const a = sentence.match(/\bavailable (?:to|for) (?:you|her|him|them|your|anyone|a patient|patients|someone|people|residents|everyone)\b|\b(?:you|she|he|they|your \w+) (?:can|could|may|might) (?:join|enrol|enroll|take part|participate)\b|\bopen to (?:you|her|him|them|your)\b/i);
    if (a) issues.push(`${field} says a trial is available to someone ("${a[0]}"); trials are listed, never matched to a person.`);
  }
}
function checkNumber(n, field, ctx, issues, isWord = false) {
  if (ctx.resultDigits.has(n.digits) && n.mult === 1) return;
  if (ctx.resultValues.some(v => near(v, n.value))) return;
  if (ctx.questionDigits.has(n.digits) || (isWord && ctx.questionWords.has(n.value))) return;
  if (ctx.constants.has(n.digits) && n.mult === 1) return;
  // a result value rounded to p significant digits, for any p from the digits written up to the digits implied: trailing zeros are
  // ambiguous ("100 million" for 100,019,672, "20,000" for 19,876 are 2-digit roundings), but never fewer than 2 digits
  const lo = Math.max(2, sigDigits(n.digits)), hi = Math.max(lo, writtenDigits(n));
  for (let p = lo; p <= hi; p++) for (const v of ctx.resultValues) if (near(sigRound(v, p), n.value)) return;
  const closest = ctx.resultValues.length ? ctx.resultValues.reduce((best, v) => Math.abs(v - n.value) < Math.abs(best - n.value) ? v : best, ctx.resultValues[0]) : null;
  issues.push(`number ${n.raw} in ${field} is not in any tool result${closest !== null ? ` (closest: ${closest})` : ''}; use only figures from the results, rounded at most to the precision written, or call a tool to get it.`);
}
function checkCall(id, field, ctx, issues) {
  let name = ctx.callIds.get(String(id));
  if (!name && /\.\d+$/.test(String(id)) && ctx.callIds.get(String(id).replace(/\.\d+$/, '')) === 'method') name = 'method';   // a sub-call of a method whose result was cut
  if (!name) issues.push(`${field} "${id}" is not the id of a tool call of this question; use the id (toolu_…) of a query, compare, profile, find_places or method call (or a method's sub-call, toolu_….1).`);
  else if (!CALL_TOOLS_WITH_IDS.includes(name)) issues.push(`${field} names a ${name} call; it must be a query, compare, profile, find_places or method call.`);
}
function idInResults(id, ctx) {
  if (!id) return false;
  if (ctx.resultsText.includes(`"${id}"`)) return true;
  if (!/^\d+$/.test(id)) return ctx.resultsText.includes(id);
  return new RegExp(`(^|[^\\d.])${id}(?![\\d.])`).test(ctx.resultsText);
}
export function capitalisedTokens(text) {
  const out = []; const re = /(?<![\p{L}\d'’.-])([A-Z][\p{L}'’.-]*)/gu; let m;
  for (const seg of String(text).split(/\n+/)) while ((m = re.exec(seg))) { const tok = m[1].replace(/[.,;:'’-]+$/, ''); if (tok.length < 3) continue; out.push(tok); }
  return out;
}
