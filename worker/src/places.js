/* Place resolution for "Ask the map": states, counties, congressional districts, ZIP codes, towns and members of Congress are
   recognised in the question text and resolved to ids that exist in the data files. Ids never come from the question or a model;
   they come from the rows. A county name that exists in several states (with no state named) is reported as an ambiguity. */
import { STATES, TERRITORIES, DEMONYMS } from './lexicon.js';

export const norm = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/&/g, ' and ').replace(/[’'`]/g, "'").replace(/[^a-z0-9',.\- ]+/g, ' ').replace(/\s+/g, ' ').trim();
export const key = s => norm(s).replace(/\bsaint\b/g, 'st').replace(/\bmount\b/g, 'mt').replace(/\bfort\b/g, 'ft').replace(/[^a-z0-9]/g, '');
const SUFFIX = /\s+(county|parish|borough|census area|city and borough|municipality|city)$/i;
const STATE_KEYS = Object.fromEntries(Object.entries(STATES).map(([u, n]) => [key(n), u]));
const TERR_KEYS = Object.fromEntries(Object.entries(TERRITORIES).map(([u, n]) => [key(n), u]));
const ORD = { first: 1, second: 2, third: 3, fourth: 4, fifth: 5, sixth: 6, seventh: 7, eighth: 8, ninth: 9, tenth: 10, eleventh: 11, twelfth: 12, thirteenth: 13, fourteenth: 14, fifteenth: 15, sixteenth: 16, seventeenth: 17, eighteenth: 18, nineteenth: 19, twentieth: 20 };

const cache = new WeakMap(); const byRefs = [];   // the index is rebuilt only when a file object changes: a warm isolate keeps the parsed files and the index
const KEYS = ['counties', 'county_names', 'districts', 'states', 'zips', 'places'];
export function buildIndex(ctx) {
  if (!ctx) ctx = {};
  const sig = KEYS.map(k => ctx[k] ? (Array.isArray(ctx[k]) ? ctx[k].length : 1) : 0).join(',');   // files can be added to ctx after a first parse
  if (cache.has(ctx) && cache.get(ctx)._sig === sig) return cache.get(ctx);
  const refs = KEYS.map(k => ctx[k] || null); const same = byRefs.find(e => e.refs.every((r, i) => r === refs[i])); if (same) { cache.set(ctx, same.ix); return same.ix; }
  const ix = { _sig: sig, countyWords: new Set(), fuzzyBuckets: new Map(), counties: new Map(), countyById: new Map(), districts: new Map(), districtByGeoid: new Map(), byState: { county: new Map(), district: new Map() }, members: new Map(), memberFull: new Map(), senators: new Map(), senatorFull: new Map(), states: new Map(), zipToCounty: new Map(), places: new Map(), hasPlaces: false, hasZips: false, hasCounties: false, hasDistricts: false };
  const push = (m, k, v) => { if (!m.has(k)) m.set(k, []); m.get(k).push(v); };
  // the county-name index comes from county_names.json ([fips, name, state, pop55], ~150 KB) when present, else from the full table
  const countyList = Array.isArray(ctx.county_names) && ctx.county_names.length ? ctx.county_names.map(([id, name, state, pop55]) => ({ id, name, state, pop55 })) : (ctx.counties || []);
  for (const r of countyList) {
    ix.hasCounties = true; const base = r.name.replace(/,\s*[^,]+$/, ''); const m = base.match(SUFFIX); const suffix = m ? m[1].toLowerCase() : ''; const stem = base.replace(SUFFIX, '');
    const e = { id: r.id, name: r.name, state: r.state, base, stem, suffix, pop55: r.pop55 || 0 }; for (const w of norm(stem).split(/[\s-]+/)) ix.countyWords.add(w.replace(/[^a-z]/g, '')); if (suffix !== 'city') { const sk = key(stem); const b = sk[0] + ':' + sk.length; if (!ix.fuzzyBuckets.has(b)) ix.fuzzyBuckets.set(b, []); ix.fuzzyBuckets.get(b).push({ e, sk }); } ix.countyById.set(r.id, e); push(ix.byState.county, r.state, e);
    if (suffix === 'city') { push(ix.counties, key(stem + ' city'), e); push(ix.counties, key(stem), { ...e, weak: true }); }   // "Richmond city": the stem alone only when nothing else matches
    else { push(ix.counties, key(stem), e); if (suffix && suffix !== 'county') push(ix.counties, key(stem + ' ' + suffix), e); }
    if (/^(district of columbia|carson city)$/i.test(base)) push(ix.counties, key(base), e);
  }
  for (const r of ctx.districts || []) {
    ix.hasDistricts = true; const e = { id: r.id, geoid: r.geoid, name: r.name, state: r.state, member: r.member || null }; ix.districts.set(r.id, e); if (r.geoid) ix.districtByGeoid.set(r.geoid, e); push(ix.byState.district, r.state, e);
    const n = r.member && r.member.name; if (n) { const parts = norm(n).replace(/[.,]/g, '').split(' ').filter(p => !/^(jr|sr|ii|iii|iv|md|phd|dr)$/.test(p)); ix.memberFull.set(parts.join(''), e); if (parts.length > 1) ix.memberFull.set(parts[0] + parts[parts.length - 1], e); push(ix.members, parts[parts.length - 1], e); }
  }
  ix.fipsState = new Map();
  for (const r of ctx.states || []) { ix.states.set(r.id, r); if (r.fips) ix.fipsState.set(String(r.fips), r.id); for (const s of r.senators || []) { if (!s || !s.name) continue; const parts = norm(s.name).replace(/[.,]/g, '').split(' ').filter(p => !/^(jr|sr|ii|iii|iv)$/.test(p)); const e = { state: r.id, name: s.name, party: s.party || '', s4440: s.s4440 || 'none' }; ix.senatorFull.set(parts.join(''), e); if (parts.length > 1) ix.senatorFull.set(parts[0] + parts[parts.length - 1], e); push(ix.senators, parts[parts.length - 1], e); } }
  if (ctx.zips && typeof ctx.zips === 'object') { ix.hasZips = true; for (const [fips, zs] of Object.entries(ctx.zips)) { if (!Array.isArray(zs)) continue; for (const z of zs) if (!ix.zipToCounty.has(z)) ix.zipToCounty.set(String(z), fips); } }
  const pl = ctx.places && ctx.places.places; if (pl && typeof pl === 'object') { ix.hasPlaces = true; for (const [usps, arr] of Object.entries(pl)) { if (!Array.isArray(arr)) continue; for (const [n, fips, pop] of arr) push(ix.places, key(n), { name: n, fips, pop: +pop || 0, state: usps }); } }   // Gazetteer names carry no "city"/"town" suffix; "Kansas City" is the whole name
  cache.set(ctx, ix); byRefs.push({ refs, ix }); if (byRefs.length > 4) byRefs.shift(); return ix;
}

// ---- states ----
// Returns [{usps, start, end, form}] for every state mention; two-letter codes only when upper-case in the original or after a comma / in a district code.
export function findStates(q) {
  const out = []; const n = norm(q); const seen = new Set();
  const add = (usps, start, end, form) => { if (!usps || seen.has(start)) return; seen.add(start); out.push({ usps, start, end, form }); };
  // full names (longest first so "west virginia" beats "virginia", "washington state" is read before "washington")
  const names = Object.entries(STATES).map(([u, nm]) => [u, norm(nm)]).sort((a, b) => b[1].length - a[1].length);
  const taken = []; const free = (s, e) => taken.every(([a, b]) => e <= a || s >= b);
  const dc = /\b(washington,? d\.?c\.?|d\.?c\.?(?=[\s,.?!']|$)|district of columbia)/g; let m;
  while ((m = dc.exec(n))) { if (free(m.index, m.index + m[0].length)) { taken.push([m.index, m.index + m[0].length]); add('DC', m.index, m.index + m[0].length, 'name'); } }
  for (const [u, nm] of names) { if (u === 'DC') continue; const re = new RegExp(`\\b${nm.replace(/\s/g, '\\s+')}(?:'s|s)?(?=[\\s,.?!'-]|$)`, 'g'); while ((m = re.exec(n))) { if (!free(m.index, m.index + m[0].length)) continue; if (u === 'WA' && /^\s*(county|parish)\b/.test(n.slice(m.index + m[0].length))) continue; if (/^\s+(city|beach|springs|heights|falls)\b/.test(n.slice(m.index + m[0].length)) && !/\bstate\b/.test(n.slice(m.index, m.index + m[0].length + 12))) continue;   /* "Kansas City", "Virginia Beach": a town, not the state */ taken.push([m.index, m.index + m[0].length]); add(u, m.index, m.index + m[0].length, /\bstate\b/.test(n.slice(m.index + m[0].length, m.index + m[0].length + 7)) ? 'state-word' : 'name'); } }
  // two-letter codes: upper-case in the original, or after a comma, or in a district code like TX-34
  const re2 = /(^|[\s,(])([A-Za-z]{2})(?=$|[\s,.?!)'-]|\d)/g; const orig = q.normalize('NFD').replace(/[̀-ͯ]/g, '');
  const letters = orig.replace(/[^A-Za-z]/g, ''); const shouted = letters.length > 3 && letters === letters.toUpperCase();   // a question typed in all caps: two-letter words are not state codes
  while ((m = re2.exec(orig))) { const code = m[2].toUpperCase(); const at = m.index + m[1].length; if (!STATES[code] || !free(at, at + 2)) continue; const upper = m[2] === code; const afterComma = /,\s*$/.test(orig.slice(0, at)); const districtCode = /^-\d{1,2}(?!\d)/.test(orig.slice(at + 2)); const wordLike = /^(IN|OR|ME|HI|OK|DE|LA|CO|MA|MD|MO|PA|ID|WA|AL)$/.test(code);
    const prevWord = (orig.slice(0, at).match(/([A-Za-z]+)\s+$/) || [])[1] || '';
    let ok = afterComma || districtCode; if (!ok && upper && !shouted) ok = !wordLike || /^(in|for|of|near|around|to|from|about|and|vs|versus|compare|with|or)$/i.test(prevWord);   // "trials in OR", "compare TX and OK"; but not "counties IN Texas"
    if (!ok) continue; taken.push([at, at + 2]); add(code, at, at + 2, 'code'); }
  for (const [dem, u] of Object.entries(DEMONYMS)) { const re = new RegExp(`\\b${dem}s?\\b`, 'g'); while ((m = re.exec(n))) if (free(m.index, m.index + m[0].length)) { taken.push([m.index, m.index + m[0].length]); add(u, m.index, m.index + m[0].length, 'demonym'); } }
  for (const [k, u] of Object.entries(TERR_KEYS)) { const re = new RegExp(`\\b${norm(TERRITORIES[u]).replace(/^the /, '').replace(/\s/g, '\\s+')}\\b`); if (re.test(n) || new RegExp(`(^|[\\s,])${u}(?=$|[\\s,.?!])`).test(orig)) out.push({ usps: u, territory: true, start: 0, end: 0, form: 'name' }); }
  return out.sort((a, b) => a.start - b.start);
}

// ---- counties ----
// Finds "<name> County|Parish|Borough|Census Area|Municipality|city" phrases. Returns [{matches: [entry...], phrase, start, end}].
export function findCounties(q, ix, stateHint) {
  const out = []; if (!ix.hasCounties) return out; const n = norm(q); const toks = []; const re = /[a-z0-9][a-z0-9'.-]*/g; let m;
  let fuzzyCalls = 0;   // bounded: candidates are bucketed by first letter and length ±2, at most 3 fuzzy lookups per question
  const fuzzy = (phraseKey) => { if (phraseKey.length < 5 || phraseKey.length > 20 || fuzzyCalls >= 3) return []; fuzzyCalls++; const cands = []; for (let L = phraseKey.length - 2; L <= phraseKey.length + 2; L++) { const b = ix.fuzzyBuckets.get(phraseKey[0] + ':' + L); if (b) cands.push(...b); } const hits = cands.filter(c => (!stateHint || !stateHint.length || stateHint.includes(c.e.state)) && near(phraseKey, c.sk)).map(c => c.e); const names = new Set(hits.map(h => key(h.stem))); return names.size === 1 ? hits : []; };
  while ((m = re.exec(n))) toks.push({ t: m[0], s: m.index, e: m.index + m[0].length });
  const used = new Set();
  const tryAt = (i, suffixLen, suffixWord) => { for (let back = 4; back >= 1; back--) { const j = i - back; if (j < 0) continue; if (toks.slice(j, i).some((t, k) => k > 0 && /,/.test(n.slice(toks[j + k - 1].e, t.s)))) continue; const phrase = toks.slice(j, i).map(t => t.t).join(' '); const k = key(suffixWord === 'city' ? phrase + ' city' : phrase); let hits = ix.counties.get(k) || []; if (suffixWord !== 'county' && suffixWord !== 'city') { const k2 = key(phrase + ' ' + suffixWord); if (ix.counties.has(k2)) hits = ix.counties.get(k2); } hits = hits.filter(h => !h.weak); if (!hits.length && back === 1 && suffixWord !== 'city') { const fz = fuzzy(k); if (fz.length) { hits = fz; } } if (!hits.length) continue; if (/^(which|what|the|a|an|in|of|every|each|this|that|my|our|your|same|any|how|for|from|to|by|and|or|about|top|worst|best|is|are|does|do|per|compare|with|vs|versus|than)$/.test(toks[j].t)) continue; return { matches: hits, phrase: n.slice(toks[j].s, toks[i + suffixLen - 1].e), start: toks[j].s, end: toks[i + suffixLen - 1].e }; } return null; };
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i].t; let r = null;
    if (/^(county|parish|borough|municipality)$/.test(t)) r = tryAt(i, 1, t);
    else if (t === 'census' && toks[i + 1] && toks[i + 1].t === 'area') r = tryAt(i, 2, 'census area');
    else if (t === 'city' && toks[i + 1] && toks[i + 1].t === 'and' && toks[i + 2] && toks[i + 2].t === 'borough') r = tryAt(i, 3, 'city and borough');
    else if (t === 'city') r = tryAt(i, 1, 'city');
    if (r && !used.has(r.start)) { used.add(r.start); out.push(r); }
  }
  // county-equivalents without a suffix in the data: District of Columbia, Carson City
  for (const nm of ['carson city']) {   /* "District of Columbia" is read as the state DC (its state file covers the one county) */ const i = n.indexOf(nm); if (i >= 0 && !out.some(o => o.start <= i && i < o.end) && ix.counties.has(key(nm))) out.push({ matches: ix.counties.get(key(nm)), phrase: nm, start: i, end: i + nm.length }); }
  return out.sort((a, b) => a.start - b.start);
}

// A county named without its suffix ("Hidalgo, Texas", "how does Hidalgo in Texas do"): only with a state and only an exact stem match.
export function findBareCounty(q, ix, usps) {
  if (!ix.hasCounties || !usps) return null; const n = norm(q); const toks = n.split(/[\s,]+/).filter(Boolean); const rows = ix.byState.county.get(usps) || [];
  for (let len = 3; len >= 1; len--) for (let i = 0; i + len <= toks.length; i++) { const k = key(toks.slice(i, i + len).join(' ')); if (k.length < 4) continue; const hit = rows.filter(e => key(e.stem) === k && e.suffix !== 'city'); if (hit.length === 1) return hit[0]; }
  return null;
}

// ---- congressional districts ----
export function findDistricts(q, ix, states) {
  const out = []; if (!ix.hasDistricts) return out; const orig = q; const n = norm(q); let m;
  const add = (usps, num, start, end) => { const id = `${usps}-${String(num).padStart(2, '0')}`; const e = ix.districts.get(id); if (e && !out.some(o => o.id === id)) out.push({ ...e, start, end }); else if (!e && usps) out.push({ id, unknown: true, state: usps, start, end }); };
  // TX-34, TX34, tx-34, "TX 34"
  const re1 = /(^|[\s,(])([A-Za-z]{2})[-\s]?(\d{1,2})(?=$|[\s,.?!)])/g; while ((m = re1.exec(orig))) { const u = m[2].toUpperCase(); if (!STATES[u]) continue; if (m[2] !== u && !/-/.test(m[0])) continue; add(u, +m[3], m.index, m.index + m[0].length); }
  const re1b = /(^|[\s,(])([A-Z]{2})-(AL|00)(?=$|[\s,.?!)])/g; while ((m = re1b.exec(orig))) { const u = m[2]; if (STATES[u]) add(u, 0, m.index, m.index + m[0].length); }   // DE-AL, VT-AL: at-large
  const stName = '(' + Object.values(STATES).map(norm).sort((a, b) => b.length - a.length).join('|') + ')';
  // "Texas 34th", "Texas's 34th district", "Texas district 34", "Texas 34th congressional district", "Texas at-large"
  const re2 = new RegExp(`\\b${stName}(?:'s|s)?\\s+(?:(?:congressional\\s+)?district\\s+)?(\\d{1,2})(?:st|nd|rd|th)?\\b(?:\\s+(?:congressional\\s+)?district)?`, 'g');
  while ((m = re2.exec(n))) { const u = STATE_KEYS[key(m[1])]; if (u) add(u, +m[2], m.index, m.index + m[0].length); }
  const re2b = new RegExp(`\\b${stName}(?:'s|s)?\\s+(${Object.keys(ORD).join('|')})\\s+(?:congressional\\s+)?district\\b`, 'g');
  while ((m = re2b.exec(n))) { const u = STATE_KEYS[key(m[1])]; if (u) add(u, ORD[m[2]], m.index, m.index + m[0].length); }
  // "34th district of Texas", "district 34 in Texas", "the 34th in Texas"
  const re3 = new RegExp(`\\b(?:the\\s+)?(?:(?:congressional\\s+)?district\\s+(\\d{1,2})|(\\d{1,2})(?:st|nd|rd|th)(?:\\s+(?:congressional\\s+)?district)?)\\s+(?:of|in)\\s+${stName}\\b`, 'g');
  while ((m = re3.exec(n))) { const u = STATE_KEYS[key(m[3])]; if (u) add(u, +(m[1] || m[2]), m.index, m.index + m[0].length); }
  // at-large
  const re4 = new RegExp(`\\b${stName}(?:'s|s)?\\s+at[-\\s]large\\b|\\bat[-\\s]large\\s+(?:district\\s+)?(?:of|in|for)\\s+${stName}\\b`, 'g');
  while ((m = re4.exec(n))) { const u = STATE_KEYS[key(m[1] || m[2])]; if (u) add(u, 0, m.index, m.index + m[0].length); }
  // "district 34" / "the 34th district" with one state elsewhere in the question
  if (!out.length && states && states.length === 1) { const re5 = /\b(?:(?:congressional\s+)?district\s+(\d{1,2})|(\d{1,2})(?:st|nd|rd|th)\s+(?:congressional\s+)?district)\b/g; while ((m = re5.exec(n))) add(states[0], +(m[1] || m[2]), m.index, m.index + m[0].length); }
  return out;
}

// ---- ZIP codes ----
export function findZips(q, ix) { const out = []; const re = /(^|[^\d-])(\d{5})(?![\d-])/g; let m; while ((m = re.exec(q))) { const z = m[2]; const start = m.index + m[1].length; out.push({ zip: z, fips: ix.zipToCounty.get(z) || null, start, end: start + 5 }); } return out; }

// ---- towns and cities (docs/places.json) ----
const CITY_STOP = new Set('which what where who how many much does do is are the a an in of for at near nearby around from to with without and or vs versus compare compared than trials trial cancer county counties district districts state states national nationally us america american access worst best most least fewest lowest highest top bottom show tell me about list rank ranking people residents short fewer less more than within miles mile road nci center centers broad menu median average mean share percent rural urban metro nonmetro oncologist oncologists deaths death mortality incidence rate rates cases new poverty uninsured broadband vehicle car household households member members representative represents cosponsor cosponsors sponsor bill house senate senator senators congress congressional find search looking need needs cases diagnoses hospital hospitals site sites facility facilities type types by all any every no not none zero live living far close closest nearest furthest farthest drive driving hours hour lung breast colon colorectal prostate melanoma skin lymphoma leukemia pancreatic pancreas liver bladder kidney brain ovarian uterine cervical head neck thyroid esophageal esophagus gastric stomach myeloma sarcoma gist mds mpn please can you could would i my we our this that these those there here it its hr s h r act modernization clinical trial'.split(' '));
const COMMON_WORDS = new Set('ages age single between among within without about above below after before again against along around because been being both during each either else even ever every first last least less lesser more most much must near need never next none nothing often only other others over own part per place plan rate rates ready real reason rest right rise road rural same second seven several share short should since small some still such sure than that their then there these they thing this those three through time times today top total toward under union unity until upon very want week well were what when where which while white whole will with within without word work world worst would year years young zero one two four five six eight nine ten hundred thousand million mean median average center centre access deal paul north south east west home house senate congress trial trials cancer county district state member members bill act version metro rural urban island people residents live living far close drive miles half quarter third many few fewer best better worse'.split(' '));
export function findCities(q, ix, states, takenSpans, excludeKeys) {
  const out = []; if (!ix.hasPlaces) return out; const n = norm(q); const toks = []; const re = /[a-z0-9][a-z0-9'.-]*/g; let m; while ((m = re.exec(n))) toks.push({ t: m[0], s: m.index, e: m.index + m[0].length });
  const orig = q.normalize('NFD').replace(/[̀-ͯ]/g, ''); const free = (s, e) => (takenSpans || []).every(([a, b]) => e <= a || s >= b);
  const capital = (s, e) => { const words = orig.slice(s, e).split(/\s+/); return words.every(w => /^[A-Z]/.test(w) || /^(of|the|de|la|le|du|des|and)$/i.test(w)); };
  const stateSet = new Set((states || []).map(s => s.usps));
  for (let len = 3; len >= 1; len--) for (let i = 0; i + len <= toks.length; i++) {
    const span = toks.slice(i, i + len); const s = span[0].s, e = span[len - 1].e; if (!free(s, e)) continue; if (span.some(t => CITY_STOP.has(t.t))) continue; if (/,/.test(n.slice(s, e))) continue;
    const k = key(span.map(t => t.t).join(' ')); if (k.length < 3) continue; if (excludeKeys && span.some(t => excludeKeys.has(t.t))) continue; let hits = ix.places.get(k); if (!hits) continue;
    hits = hits.filter(h => h.name.split(/[\s-]+/).length === len); if (!hits.length) continue;   // "DE-AL" is not Deal, NJ
    const after = n.slice(e, e + 40); const commaState = after.match(/^,?\s*([a-z. ]+)/); const prev = n.slice(Math.max(0, s - 12), s);
    let stAfter = (states || []).find(st => st.start >= e && st.start <= e + 4 && /^,?\s*$/.test(n.slice(e, st.start)));
    if (!stAfter) { const cm = n.slice(e).match(/^,?\s+([a-z]{2})(?=$|[\s,.?!])/); const code = cm && cm[1].toUpperCase(); if (code && STATES[code] && hits.some(h => h.state === code)) stAfter = { usps: code, start: e + cm[0].length - 2, end: e + cm[0].length, form: 'code-after-city' }; }   // "Meadville PA", "meadville pa": the code binds when the town exists in that state
    if (stAfter) hits = hits.filter(h => h.state === stAfter.usps); else if (stateSet.size) { const inState = hits.filter(h => stateSet.has(h.state)); if (inState.length) hits = inState; }
    if (!hits.length) continue;
    const cap = capital(s, e); const cue = /\b(in|near|around|at|from|for|of|to|about)\s*$/.test(prev) || !!stAfter || !!commaState;
    if (!cap && !cue) continue;
    if (!stAfter && len === 1 && COMMON_WORDS.has(span[0].t)) continue;   // "ages", "between", "single": English words that are also town names need a state after them
    if (!cap && !stAfter && !stateSet.size) { const sorted = hits.slice().sort((a, b) => b.pop - a.pop); if (sorted.length > 1 && sorted[0].pop - sorted[1].pop < 1) continue; }   // lowercase "springfield" with no state: too ambiguous to guess
    if (!cap && !stAfter && len === 1 && COMMON_WORDS.has(span[0].t)) continue;
    hits = hits.slice().sort((a, b) => b.pop - a.pop); const top = hits[0]; const rivals = hits.filter(h => h.state !== top.state && top.pop - h.pop < 0.8);
    out.push({ phrase: n.slice(s, e), start: s, end: e, hits, best: top, ambiguous: !stAfter && !stateSet.size && rivals.length > 0, state: stAfter ? stAfter.usps : null });
    i += len - 1;
  }
  // keep the longest, non-overlapping matches
  out.sort((a, b) => (b.end - b.start) - (a.end - a.start)); const kept = []; for (const c of out) if (kept.every(k => c.end <= k.start || c.start >= k.end)) kept.push(c);
  return kept.sort((a, b) => a.start - b.start);
}

// ---- members of Congress ----
export function findMembers(q, ix, context, skipTokens) {
  const out = []; if (!ix.hasDistricts && !ix.senatorFull.size) return out; const n = norm(q).replace(/'s\b/g, '').replace(/[.,]/g, ''); const toks = n.split(/\s+/).filter(Boolean); const skip = skipTokens || new Set();
  const title = /\b(rep|representative|congressman|congresswoman|congressmember|senator|sen|mr|ms|mrs|dr)$/;
  for (let i = 0; i < toks.length; i++) {
    for (const len of [3, 2]) { const k = toks.slice(i, i + len).join(''); const h = ix.memberFull.get(k); const s = ix.senatorFull.get(k); if (h || s) { out.push({ kind: h ? 'house' : 'senate', full: true, entries: [h || s], surname: toks[i + len - 1], tokens: toks.slice(i, i + len) }); i += len - 1; break; } }
    if (out.length && out[out.length - 1].surname === toks[i]) continue;
    const t = toks[i]; if (skip.has(t)) continue; const hs = ix.members.get(t) || [], ss = ix.senators.get(t) || []; if (!hs.length && !ss.length) continue;
    const titled = title.test(toks.slice(Math.max(0, i - 1), i).join(' ')); const strong = /\b(represent|represents|cosponsor|cosponsors|cosponsored|sponsor|sponsors)\b/.test(n);
    const common = /^(green|young|hill|moore|brown|king|price|rose|bishop|mills|case|self|wild|good|strong|bell|cole|long|west|stone|fox|may|day|little|love|house|cross|sharp|paul|francis|page|park|fields|banks|wells|ray|grant|hunt|mason|bush|miles|graves|ward|powers|hale|holt|mack|carter|turner|walker|cook|baker|fisher|hunter|porter|mann|norman|lee|neal|ross|scott|kelly|murphy|ryan|craig|dean|mast|golden|crane|flood|kim|fry|cline|barr|nunn|comer|gooden|issa|baird|rouzer|webster|ogles|kean|lawler)$/.test(t);
    if (!titled && !context) continue; if (!titled && t.length < 4) continue; if (!titled && common && !strong) continue;   // a common word or a short surname needs a title (Rep. Green) or a strong cue (cosponsor, represents)
    out.push({ kind: hs.length ? 'house' : 'senate', full: false, entries: hs.length ? hs : ss, surname: t, tokens: [t], alsoSenate: hs.length && ss.length ? ss : null });
  }
  return out;
}

// Damerau-Levenshtein distance (insertions, deletions, substitutions, adjacent transpositions), capped
export function editDistance(a, b, cap = 2) { if (a === b) return 0; const la = a.length, lb = b.length; if (Math.abs(la - lb) > cap) return cap + 1; const d = []; for (let i = 0; i <= la; i++) { d[i] = [i]; } for (let j = 1; j <= lb; j++) d[0][j] = j;
  for (let i = 1; i <= la; i++) for (let j = 1; j <= lb; j++) { const c = a[i - 1] === b[j - 1] ? 0 : 1; d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c); if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1); }
  return d[la][lb]; }
export function edit1(a, b) { return editDistance(a, b, 1) <= 1; }
export function near(a, b) { return editDistance(a, b, 2) <= (Math.min(a.length, b.length) >= 6 ? 2 : 1); }   // two edits for longer names, one for short ones
const STATE_WORDS = Object.values(STATES).map(norm);
// "Texs" -> TX: a capitalised token of 4+ letters one edit from a one-word state name, when it is not itself a known word
export function fuzzyStates(q, ix, taken) {
  const out = []; const orig = q.normalize('NFD').replace(/[\u0300-\u036f]/g, ''); const re = /[A-Z][a-z]{3,19}/g; let m; let calls = 0;
  while ((m = re.exec(orig)) && calls < 3) { calls++; const t = m[0].toLowerCase(); if (STATE_KEYS[t] || (ix.counties && ix.counties.has(key(t))) || (ix.places && ix.places.has(key(t))) || (ix.members && ix.members.has(t)) || COMMON_WORDS.has(t)) continue; if ((taken || []).some(([a, b]) => m.index < b && m.index + t.length > a)) continue; const hit = STATE_WORDS.filter(w => !w.includes(' ') && w.length >= 4 && edit1(t, w)); if (hit.length === 1) out.push({ usps: STATE_KEYS[key(hit[0])], start: m.index, end: m.index + t.length, form: 'fuzzy', word: m[0] }); }
  return out;
}
export function stateOf(usps) { return STATES[usps] || null; }
export function stateFromName(name) { return STATE_KEYS[key(name)] || (/^[A-Za-z]{2}$/.test(name || '') && STATES[name.toUpperCase()] ? name.toUpperCase() : null); }
