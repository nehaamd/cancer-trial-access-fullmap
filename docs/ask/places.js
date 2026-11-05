/* Ask the map v3 — place resolution for the `find_places` tool (ASK_CONTRACT.md §5).
   buildPlaceIndex(tables) indexes county names (with and without their suffix), states (name, USPS, demonym), district codes in
   every form, ZIPs → county, towns → county, House members → district, senators → state and NCI centers by name.
   findPlaces(ix, input) resolves one query to ids that exist in the data; ids never come from the query text itself.
   Namesakes across states are returned with pop55 so the model can ask; typos are tolerated only when nothing matches exactly. */
import { STATES, DEMONYMS } from './catalog.js';

// ---------- text normalisation ----------
// lower-case, accents stripped, "&" → "and", punctuation (except apostrophes, dots, hyphens, commas) → space
export const norm = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  .replace(/&/g, ' and ').replace(/[’'`]/g, "'").replace(/[^a-z0-9',.\- ]+/g, ' ').replace(/\s+/g, ' ').trim();
// a comparison key: norm + common abbreviations folded + nothing but letters and digits
export const key = s => norm(s).replace(/\bsaint\b/g, 'st').replace(/\bmount\b/g, 'mt').replace(/\bfort\b/g, 'ft').replace(/[^a-z0-9]/g, '');

const SUFFIX = /\s+(county|parish|borough|census area|city and borough|municipality|city)$/i;
const ORD = { first: 1, second: 2, third: 3, fourth: 4, fifth: 5, sixth: 6, seventh: 7, eighth: 8, ninth: 9, tenth: 10, eleventh: 11, twelfth: 12, thirteenth: 13, fourteenth: 14, fifteenth: 15, sixteenth: 16, seventeenth: 17, eighteenth: 18, nineteenth: 19, twentieth: 20 };
const TITLES = /^(rep|representative|congressman|congresswoman|congressmember|senator|sen|mr|ms|mrs|dr|hon)$/;
const NAME_SUFFIXES = /^(jr|sr|ii|iii|iv|md|phd)$/;
const STATE_BY_KEY = Object.fromEntries(Object.entries(STATES).map(([u, n]) => [key(n), u]));
const STATE_NAMES_RE = Object.values(STATES).map(n => norm(n).replace(/\s/g, '\\s+')).sort((a, b) => b.length - a.length).join('|');

// Damerau-Levenshtein distance (insert, delete, substitute, adjacent transposition), capped
export function editDistance(a, b, cap = 2) {
  if (a === b) return 0;
  const la = a.length, lb = b.length;
  if (Math.abs(la - lb) > cap) return cap + 1;
  const d = [];
  for (let i = 0; i <= la; i++) d[i] = [i];
  for (let j = 1; j <= lb; j++) d[0][j] = j;
  for (let i = 1; i <= la; i++) {
    for (let j = 1; j <= lb; j++) {
      const c = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[la][lb];
}
// typo tolerance: one edit for keys of five letters or fewer, two for longer ones
export function withinTypo(qk, k) { const cap = qk.length <= 5 ? 1 : 2; return editDistance(qk, k, cap) <= cap; }

// USPS code for a state given as a name, code or demonym (null when it is not one)
export function stateCode(s) {
  if (s === null || s === undefined) return null;
  const t = String(s).trim();
  if (/^[A-Za-z]{2}$/.test(t) && STATES[t.toUpperCase()]) return t.toUpperCase();
  const k = key(t);
  if (STATE_BY_KEY[k]) return STATE_BY_KEY[k];
  const dem = norm(t).replace(/s$/, '');
  return DEMONYMS[norm(t)] || DEMONYMS[dem] || null;
}

// name tokens of a person, titles and generational suffixes dropped
function personTokens(name) {
  return norm(name).replace(/[.,]/g, '').split(' ').filter(p => p && !NAME_SUFFIXES.test(p) && !TITLES.test(p));
}
// the same for a query, with the words around a name ("Gonzalez's district", "the seat of") dropped too
const QUERY_STOP = /^(district|seat|the|of|for|house|member|congress|congressional|us|u|s)$/;
function queryTokens(name) { return personTokens(String(name).replace(/'s\b/g, '')).filter(p => !QUERY_STOP.test(p)); }
const push = (m, k, v) => { if (!m.has(k)) m.set(k, []); m.get(k).push(v); };

// ---------- the index ----------
// tables: { counties, districts, states, nci, zips, places } — rows as the engine builds them; zips = {FIPS: [ZIP…]}; places = {USPS: [[name, FIPS, log10pop]]}
export function buildPlaceIndex(tables) {
  const ix = { counties: new Map(), countyList: [], countyById: new Map(), states: new Map(), stateRows: new Map(), districts: new Map(), districtByGeoid: new Map(),
    members: new Map(), memberFull: new Map(), senators: new Map(), senatorFull: new Map(), zipToCounty: new Map(), towns: new Map(), nci: [], hasZips: false, hasTowns: false };
  indexCounties(ix, tables.counties || []);
  indexStates(ix, tables.states || []);
  indexDistricts(ix, tables.districts || []);
  indexSenators(ix, tables.states || []);
  indexZips(ix, tables.zips);
  indexTowns(ix, tables.places);
  indexNci(ix, tables.nci || []);
  return ix;
}

// county names: "Hidalgo County, Texas" → stem "hidalgo", base "hidalgo county"; independent cities keep the stem weak
function indexCounties(ix, rows) {
  for (const r of rows) {
    const base = String(r.name).replace(/,\s*[^,]+$/, '');
    const m = base.match(SUFFIX);
    const suffix = m ? m[1].toLowerCase() : '';
    const stem = base.replace(SUFFIX, '');
    const e = { id: r.id, name: r.name, state: r.state, pop55: r.pop55 || 0, base, stem, suffix, sk: key(stem) };
    ix.countyList.push(e); ix.countyById.set(r.id, e);
    push(ix.counties, key(base), e);
    if (suffix === 'city') push(ix.counties, key(stem), { ...e, weak: true });
    else if (suffix) push(ix.counties, key(stem), e);
    else push(ix.counties, key(stem), e);
    if (suffix && suffix !== 'county' && suffix !== 'city') push(ix.counties, key(stem + ' county'), { ...e, weak: true });
  }
}
// states by name, USPS and demonym
function indexStates(ix, rows) {
  for (const r of rows) { ix.stateRows.set(r.id, { id: r.id, name: r.name, pop55: r.pop55 || 0 }); ix.states.set(key(r.name), r.id); ix.states.set(r.id.toLowerCase(), r.id); }
  for (const [dem, u] of Object.entries(DEMONYMS)) if (ix.stateRows.has(u)) ix.states.set(key(dem), u);
}
// districts by id and geoid; House members by full name, first+last and surname
function indexDistricts(ix, rows) {
  for (const r of rows) {
    const member = r.member || {};
    const e = { id: r.id, geoid: r.geoid, name: r.name, state: r.state, pop55: r.pop55 || 0, member: member.name || null, party: member.party || null, ctma_hr3521: member.ctma_hr3521 || 'none' };
    ix.districts.set(r.id, e);
    if (r.geoid) ix.districtByGeoid.set(String(r.geoid), e);
    if (!member.name) continue;
    const parts = personTokens(member.name);
    ix.memberFull.set(parts.join(''), e);
    if (parts.length > 1) ix.memberFull.set(parts[0] + parts[parts.length - 1], e);
    push(ix.members, parts[parts.length - 1], e);
  }
}
// senators by full name, first+last and surname
function indexSenators(ix, rows) {
  for (const r of rows) {
    for (const s of r.senators || []) {
      if (!s || !s.name) continue;
      const parts = personTokens(s.name);
      const e = { state: r.id, stateName: r.name, pop55: r.pop55 || 0, name: s.name, party: s.party || null, s4440: s.s4440 || 'none', bioguide: s.bioguide || null };
      ix.senatorFull.set(parts.join(''), e);
      if (parts.length > 1) ix.senatorFull.set(parts[0] + parts[parts.length - 1], e);
      push(ix.senators, parts[parts.length - 1], e);
    }
  }
}
// zip_county.json maps county FIPS → [ZIPs]; invert it (a ZIP that spans counties keeps its first county)
function indexZips(ix, zips) {
  if (!zips || typeof zips !== 'object') return;
  ix.hasZips = true;
  for (const [fips, list] of Object.entries(zips)) { if (!Array.isArray(list)) continue; for (const z of list) if (!ix.zipToCounty.has(String(z))) ix.zipToCounty.set(String(z), fips); }
}
// places.json: places[USPS] = [[name, county FIPS, log10 of residents 55+ nearby]]
function indexTowns(ix, places) {
  const pl = places && places.places ? places.places : places;
  if (!pl || typeof pl !== 'object') return;
  ix.hasTowns = true;
  for (const [usps, arr] of Object.entries(pl)) { if (!Array.isArray(arr)) continue; for (const [n, fips, lp] of arr) push(ix.towns, key(n), { name: n, fips, state: usps, pop: Math.round(10 ** (+lp || 0)) }); }
}
// NCI centers: normalised short and full names for substring matching
function indexNci(ix, rows) {
  for (const r of rows) ix.nci.push({ id: r.id, name: r.name, full_name: r.full_name, state: r.state, nk: norm(r.name), fk: norm(r.full_name), toks: new Set(norm(r.full_name + ' ' + r.name).split(/[\s.,()\-]+/).filter(t => t.length >= 2)) });
}

// ---------- the search ----------
const KINDS = ['county', 'district', 'state', 'zip', 'town', 'member', 'senator', 'nci_center'];
const HOW_RANK = { exact: 0, namesake: 0, zip: 1, town: 2, member: 3, senator: 3, fuzzy: 5 };
const DOMINANT = 20;   // a namesake at least this many times more populous than every other is taken without asking

// resolves input {query, kind?, state?, limit?} → {matches, ambiguous, hint?}
export function findPlaces(ix, input) {
  const q0 = String(input && input.query || '').trim();
  if (!q0) return { error: 'find_places needs a query', hint: 'e.g. {query: "Hidalgo County, Texas"}' };
  if (input.kind && !KINDS.includes(input.kind)) return { error: `unknown kind '${input.kind}'`, hint: 'kind is one of ' + KINDS.join(', ') };
  const limit = Math.max(1, Math.min(10, Math.floor(+input.limit) || 10));
  const kind = input.kind || null;
  const parsed = splitState(q0, kind);
  const stateHint = stateCode(input.state) || parsed.state;
  const want = k => !kind || kind === k;
  const notes = [];
  let found = [];
  if (want('state') && !parsed.state) found.push(...matchStates(ix, q0));
  const districtHits = want('district') ? matchDistricts(ix, q0, parsed, stateHint) : [];
  found.push(...districtHits);
  const zipHits = want('zip') ? matchZip(ix, parsed.name, stateHint, notes) : [];
  found.push(...zipHits);
  if (want('county')) found.push(...matchCounties(ix, parsed, stateHint, kind === 'county' || !zipHits.length));
  if (parsed.suffix === 'city' && (ix.counties.get(key(parsed.nameNoThe)) || []).some(e => !e.weak)) parsed.countyOnly = true;   // "Richmond city", "Carson City": a county equivalent's own name
  const people = !parsed.countyOnly && !districtHits.length;   // "TX-34" is not the town of Deal; "X County" is not a person
  if (want('town') && people) found.push(...matchTowns(ix, parsed.name, stateHint));
  if (want('member') && people) found.push(...matchMembers(ix, parsed.name, stateHint));
  if (want('senator') && people) found.push(...matchSenators(ix, parsed.name, stateHint));
  if (want('nci_center') && people) found.push(...matchNci(ix, parsed.name, stateHint));
  if (!found.length) found = fuzzyPass(ix, parsed, stateHint, kind);
  const result = rank(dedupe(found), limit, q0);
  if (notes.length) result.hint = (result.hint ? result.hint + ' ' : '') + notes.join(' ');
  if (!result.matches.length) { result.hint = `No county, district, state, ZIP, town, member, senator or NCI center matches "${q0}"` + (stateHint ? ` in ${STATES[stateHint] || stateHint}` : '') + '. Try the full name with the state, or a 5-digit ZIP.'; }
  return result;
}

// "Hidalgo County, Texas" / "Hidalgo, TX" / "Hidalgo Texas" → {name, state, suffix}; the state part is only taken when it is a state
function splitState(q, kind) {
  const out = { name: q, state: null, suffix: null };
  const m = q.match(/^(.*?)\s*,\s*([A-Za-z .]+)$/);
  if (m && stateCode(m[2]) && m[1].trim()) { out.name = m[1].trim(); out.state = stateCode(m[2]); }
  else if (kind !== 'district' && !stateCode(q)) {
    const words = q.split(/\s+/);
    for (let len = Math.min(3, words.length - 1); len >= 1 && !out.state; len--) {
      const tail = words.slice(-len).join(' '); const head = words.slice(0, -len).join(' ');
      const twoLetter = len === 1 && /^[A-Za-z]{2}$/.test(tail);
      if (twoLetter && tail !== tail.toUpperCase()) continue;   // "hidalgo tx" is accepted only as "Hidalgo TX" or after a comma
      if (!head || /^(the|of|in)$/i.test(head)) continue;
      if (/\b(at|district|congressional)\b/i.test(head) && !twoLetter) continue;   // "34th district of Texas" is a district form, not "<name> <state>"
      const sc = stateCode(tail);
      if (sc && !(len === 1 && /^(city|county|parish|borough)$/i.test(tail))) { out.name = head; out.state = sc; }
    }
  }
  const sm = out.name.match(SUFFIX);
  if (sm) out.suffix = sm[1].toLowerCase();
  out.countyOnly = !!out.suffix && out.suffix !== 'city';   // "X County" cannot be a town or a person; "X City" can be a town
  out.nameNoThe = out.name.replace(/^the\s+/i, '');
  out.stem = out.nameNoThe.replace(SUFFIX, '');
  return out;
}

// states by name, USPS or demonym; "United States" → the national row
function matchStates(ix, q) {
  const k = key(q).replace(/^(thestateof|stateof)/, '').replace(/state$/, '');
  if (/^(us|usa|unitedstates|nation|national|america|thenation|wholecountry)$/.test(k)) return [{ id: 'US', table: 'national', kind: 'national', name: 'United States', state: null, pop55: null, how: 'exact', score: 1e9 }];
  const u = ix.states.get(k) || ix.states.get(k.replace(/s$/, ''));
  if (!u) return [];
  const row = ix.stateRows.get(u);
  const m = { id: u, table: 'states', kind: 'state', name: row.name, state: u, pop55: row.pop55, how: 'exact', score: row.pop55 };
  if (DEMONYMS[norm(q)] || DEMONYMS[norm(q).replace(/s$/, '')]) m.via = `${q} → ${row.name}`;
  return [m];
}
// district codes in every form: TX-34, TX 34, Texas 34th, Texas's 34th district, 34th district of Texas, Texas at-large, geoid 4834
function matchDistricts(ix, q, parsed, stateHint) {
  const n = norm(q).replace(/[.,]/g, '').trim();
  const out = [];
  const add = (usps, num, how = 'exact') => {
    if (!usps || num === null || num === undefined || Number.isNaN(+num)) return;
    const e = ix.districts.get(`${usps}-${String(+num).padStart(2, '0')}`) || (+num === 1 && ix.districts.get(`${usps}-00`));
    if (e) out.push(districtMatch(e, how));
  };
  let m;
  if ((m = n.match(/^([a-z]{2})[\s-]?(\d{1,2})(?:st|nd|rd|th)?(?:\s+(?:congressional\s+)?district)?$/)) && STATES[m[1].toUpperCase()]) add(m[1].toUpperCase(), m[2]);
  if ((m = n.match(/^([a-z]{2})[\s-]?(al|00|at[\s-]?large)$/)) && STATES[m[1].toUpperCase()]) add(m[1].toUpperCase(), 0);
  if ((m = n.match(/^(\d{4})$/)) && ix.districtByGeoid.has(m[1])) out.push(districtMatch(ix.districtByGeoid.get(m[1]), 'exact'));
  const re1 = new RegExp(`^(?:the\\s+)?(${STATE_NAMES_RE})(?:'s|s)?\\s+(?:(?:congressional\\s+)?district\\s+)?(\\d{1,2})(?:st|nd|rd|th)?(?:\\s+(?:congressional\\s+)?district)?$`);
  if ((m = n.match(re1))) add(STATE_BY_KEY[key(m[1])], m[2]);
  const re2 = new RegExp(`^(?:the\\s+)?(${STATE_NAMES_RE})(?:'s|s)?\\s+(${Object.keys(ORD).join('|')})(?:\\s+(?:congressional\\s+)?district)?$`);
  if ((m = n.match(re2))) add(STATE_BY_KEY[key(m[1])], ORD[m[2]]);
  const re3 = new RegExp(`^(?:the\\s+)?(?:(?:congressional\\s+)?district\\s+(\\d{1,2})|(\\d{1,2})(?:st|nd|rd|th)(?:\\s+(?:congressional\\s+)?district)?)\\s+(?:of|in|for)\\s+(?:the\\s+state\\s+of\\s+)?(${STATE_NAMES_RE})$`);
  if ((m = n.match(re3))) add(STATE_BY_KEY[key(m[3])], m[1] || m[2]);
  const re4 = new RegExp(`^(?:the\\s+)?(${STATE_NAMES_RE})(?:'s|s)?\\s+at[\\s-]?large(?:\\s+(?:congressional\\s+)?district)?$|^(?:the\\s+)?at[\\s-]?large\\s+(?:(?:congressional\\s+)?district\\s+)?(?:of|in|for)\\s+(${STATE_NAMES_RE})$`);
  if ((m = n.match(re4))) add(STATE_BY_KEY[key(m[1] || m[2])], 0);
  if ((m = n.match(/^(?:the\s+)?(?:(?:congressional\s+)?district\s+(\d{1,2})|(\d{1,2})(?:st|nd|rd|th)(?:\s+(?:congressional\s+)?district)?)$/)) && stateHint) add(stateHint, m[1] || m[2]);
  if ((m = n.match(/^(?:the\s+)?at[\s-]?large(?:\s+(?:congressional\s+)?district)?$/)) && stateHint) add(stateHint, 0);
  if (/^[a-z]{2}-\d{2}$/.test(n) && ix.districts.has(n.toUpperCase())) out.push(districtMatch(ix.districts.get(n.toUpperCase()), 'exact'));
  return out;
}
function districtMatch(e, how, extra = {}) {
  return { id: e.id, table: 'districts', kind: 'district', name: e.name, state: e.state, geoid: e.geoid, pop55: e.pop55, member: e.member, party: e.party, ctma_hr3521: e.ctma_hr3521, how, score: e.pop55, ...extra };
}
// a 5-digit ZIP → its county; a 5-digit county FIPS is noted as the alternative
function matchZip(ix, name, stateHint, notes) {
  const z = name.trim();
  if (!/^\d{5}$/.test(z)) return [];
  const out = [];
  const fips = ix.zipToCounty.get(z);
  const c = fips ? ix.countyById.get(fips) : null;
  if (c && (!stateHint || c.state === stateHint)) out.push(countyMatch(c, 'zip', { via: `ZIP ${z} is in ${c.name}` }));
  const byId = ix.countyById.get(z);
  if (out.length && byId) notes.push(`${z} is also the FIPS code of ${byId.name}; use kind:"county" for that.`);
  if (!out.length && !c && !byId && ix.hasZips) notes.push(`ZIP ${z} is not in the ZIP-to-county file (territory, PO-box-only or not a US ZIP).`);
  return out;
}
function countyMatch(e, how, extra = {}) {
  return { id: e.id, table: 'counties', kind: 'county', name: e.name, state: e.state, pop55: e.pop55, how, score: e.pop55, ...extra };
}
// county names with or without the suffix; "X city" only by its full form unless nothing else matches
function matchCounties(ix, parsed, stateHint, allowFips) {
  const name = parsed.nameNoThe;
  const k = key(name);
  if (!k) return [];
  if (/^\d{5}$/.test(name)) return allowFips && ix.countyById.has(name) ? [countyMatch(ix.countyById.get(name), 'exact', { via: `${name} read as a county FIPS code` })] : [];
  let hits = (ix.counties.get(k) || []).slice();
  if (!parsed.suffix) for (const suf of ['county', 'parish', 'borough', 'censusarea', 'municipality', 'cityandborough']) hits.push(...(ix.counties.get(k + suf) || []));
  const strong = hits.filter(h => !h.weak);
  hits = strong.length ? strong : hits;
  if (stateHint) hits = hits.filter(h => h.state === stateHint);
  const seen = new Set();
  return hits.filter(h => !seen.has(h.id) && seen.add(h.id)).map(h => countyMatch(h, 'exact'));
}
// towns → their county (Census Gazetteer names carry no "city"/"town" word)
function matchTowns(ix, name, stateHint) {
  const bare = name.replace(/^the\s+/i, '');
  let hits = ix.towns.get(key(bare)) || [];
  if (!hits.length && /\s+(city|town|village)$/i.test(bare)) hits = ix.towns.get(key(bare.replace(/\s+(city|town|village)$/i, ''))) || [];
  if (stateHint) hits = hits.filter(h => h.state === stateHint);
  return hits.map(h => { const c = ix.countyById.get(h.fips); return c ? countyMatch(c, 'town', { via: `${h.name}, ${h.state} is in ${c.name}`, score: h.pop }) : null; }).filter(Boolean);
}
// House members by full name, first+last or surname (titles dropped)
function matchMembers(ix, name, stateHint) {
  const parts = queryTokens(name);
  if (!parts.length) return [];
  const full = ix.memberFull.get(parts.join('')) || (parts.length > 1 ? ix.memberFull.get(parts[0] + parts[parts.length - 1]) : null);
  let hits = full ? [full] : (parts.length === 1 ? (ix.members.get(parts[0]) || []) : []);
  if (!hits.length && parts.length > 1) hits = (ix.members.get(parts[parts.length - 1]) || []).filter(e => parts.every(p => personTokens(e.member).includes(p)));
  if (stateHint) hits = hits.filter(h => h.state === stateHint);
  return hits.map(e => districtMatch(e, 'member', { via: `Rep. ${e.member} (${e.party || '?'}) represents ${e.name} (${e.id})` }));
}
// senators by full name, first+last or surname
function matchSenators(ix, name, stateHint) {
  const parts = queryTokens(name);
  if (!parts.length) return [];
  const full = ix.senatorFull.get(parts.join('')) || (parts.length > 1 ? ix.senatorFull.get(parts[0] + parts[parts.length - 1]) : null);
  let hits = full ? [full] : (parts.length === 1 ? (ix.senators.get(parts[0]) || []) : []);
  if (!hits.length && parts.length > 1) hits = (ix.senators.get(parts[parts.length - 1]) || []).filter(e => parts.every(p => personTokens(e.name).includes(p)));
  if (stateHint) hits = hits.filter(h => h.state === stateHint);
  return hits.map(e => senatorMatch(e, 'senator'));
}
function senatorMatch(e, how, extra = {}) {
  return { id: e.state, table: 'states', kind: 'state', name: e.stateName, state: e.state, pop55: e.pop55, how, score: e.pop55, via: `Senator ${e.name} (${e.party || '?'}) represents ${e.stateName}; S. 4440: ${e.s4440}`, senator: e.name, bioguide: e.bioguide, ...extra };
}
// NCI centers: the query inside the name, or every query word in the name
function matchNci(ix, name, stateHint) {
  const n = norm(name).replace(/[.,]/g, '');
  if (n.length < 3) return [];
  const toks = n.split(/[\s\-()]+/).filter(t => t.length >= 2);
  const out = [];
  for (const c of ix.nci) {
    if (stateHint && c.state !== stateHint) continue;
    const hit = c.fk.includes(n) || c.nk.includes(n) || (toks.length && toks.every(t => c.toks.has(t)));
    if (hit) out.push(nciMatch(c, 'exact'));
  }
  return out;
}
function nciMatch(c, how, extra = {}) {
  return { id: c.id, table: 'nci_centers', kind: 'nci_center', name: c.name, full_name: c.full_name, state: c.state, pop55: null, how, score: 0, ...extra };
}

// typo tolerance, only when nothing matched exactly: counties, states, towns (with a state), surnames, NCI words; the closest wins
function fuzzyPass(ix, parsed, stateHint, kind) {
  const want = k => !kind || kind === k;
  const name = parsed.nameNoThe;
  const qk = key(parsed.stem);   // the typo is in the name, not in "County"
  const capFor = qk.length <= 5 ? 1 : 2;
  const cands = [];   // [distance, match]
  if (qk.length < 3) return [];
  if (want('county')) {
    for (const e of ix.countyList) {
      if (stateHint && e.state !== stateHint) continue;
      if (parsed.suffix ? e.suffix !== parsed.suffix : e.suffix === 'city') continue;
      const d = editDistance(qk, e.sk, capFor); if (d <= capFor) cands.push([d, countyMatch(e, 'fuzzy', { note: `"${name}" read as ${e.base}` })]);
    }
  }
  if (want('state') && !parsed.state && !parsed.countyOnly) {
    for (const [u, nm] of Object.entries(STATES)) {
      if (!ix.stateRows.has(u)) continue;
      const d = editDistance(qk, key(nm), capFor); if (d > capFor) continue;
      const row = ix.stateRows.get(u);
      cands.push([d, { id: u, table: 'states', kind: 'state', name: row.name, state: u, pop55: row.pop55, how: 'fuzzy', score: row.pop55, note: `"${name}" read as ${row.name}` }]);
    }
  }
  if (want('town') && !parsed.countyOnly && (stateHint || kind === 'town')) {
    for (const [k, list] of ix.towns) {
      const d = editDistance(qk, k, capFor); if (d > capFor) continue;
      for (const h of list) { if (stateHint && h.state !== stateHint) continue; const c = ix.countyById.get(h.fips); if (c) cands.push([d, countyMatch(c, 'fuzzy', { via: `${h.name}, ${h.state} is in ${c.name}`, note: `"${name}" read as ${h.name}`, score: h.pop })]); }
    }
  }
  const parts = queryTokens(name);
  const sur = parts.length ? parts[parts.length - 1] : '';
  if (!parsed.countyOnly && sur.length >= 4) {
    const scap = sur.length <= 5 ? 1 : 2;
    if (want('member')) {
      for (const [k, list] of ix.members) {
        const d = editDistance(sur, k, scap); if (d > scap) continue;
        for (const e of list) if (!stateHint || e.state === stateHint) cands.push([d, districtMatch(e, 'fuzzy', { via: `Rep. ${e.member} (${e.party || '?'}) represents ${e.name} (${e.id})`, note: `"${name}" read as ${e.member}` })]);
      }
    }
    if (want('senator')) {
      for (const [k, list] of ix.senators) {
        const d = editDistance(sur, k, scap); if (d > scap) continue;
        for (const e of list) if (!stateHint || e.state === stateHint) cands.push([d, senatorMatch(e, 'fuzzy', { note: `"${name}" read as ${e.name}` })]);
      }
    }
  }
  if (want('nci_center') && !parsed.countyOnly && qk.length >= 4) {
    for (const c of ix.nci) {
      if (stateHint && c.state !== stateHint) continue;
      let best = 9;
      for (const t of c.toks) if (t.length >= 4) best = Math.min(best, editDistance(qk, t, capFor));
      if (best <= capFor) cands.push([best, nciMatch(c, 'fuzzy', { note: `"${name}" read as ${c.name}` })]);
    }
  }
  if (!cands.length) return [];
  const min = Math.min(...cands.map(c => c[0]));
  return cands.filter(c => c[0] === min).map(c => c[1]);
}

// one entry per (table, id), keeping the strongest way it was found
function dedupe(found) {
  const best = new Map();
  for (const m of found) {
    const k = m.table + ':' + m.id;
    const cur = best.get(k);
    if (!cur || HOW_RANK[m.how] < HOW_RANK[cur.how] || (HOW_RANK[m.how] === HOW_RANK[cur.how] && (m.score || 0) > (cur.score || 0))) best.set(k, m);
  }
  return [...best.values()];
}
// order by population, decide ambiguity, apply the dominant-namesake rule, cap at limit
function rank(matches, limit, q) {
  matches.sort((a, b) => (b.score || 0) - (a.score || 0) || String(a.name).localeCompare(String(b.name)));
  const strip = m => { const o = { ...m }; delete o.score; return o; };
  if (matches.length <= 1) return { matches: matches.map(strip), ambiguous: false };
  const stateHit = matches.find(m => m.kind === 'state' && m.how === 'exact' && !m.via);
  if (stateHit) {   // a state's own name beats counties and towns called the same ("Washington", "New York", "Delaware")
    const others = matches.filter(m => m !== stateHit);
    const out = strip(stateHit);
    out.note = `Read as the state. Also ${describeOthers(others)}; ask with kind:"county" or kind:"town" for those.`;
    return { matches: [out], ambiguous: false, others: others.slice(0, limit).map(strip) };
  }
  const top = matches[0];
  const rest = matches.slice(1);
  const comparable = matches.every(m => m.kind !== 'nci_center');   // centers carry no population, so they never settle a tie
  // a big city beats small counties of the same name when nobody wrote "County" ("Houston", "Miami"): 5× the residents 55+ is enough
  const cityOverCounties = top.how === 'town' && (top.score || 0) > 0 && rest.every(m => (top.score || 0) >= 5 * (m.score || 0));
  const dominant = comparable && (top.score || 0) > 0 && (cityOverCounties || rest.every(m => (top.score || 0) >= DOMINANT * (m.score || 0)));
  if (dominant) {
    const out = strip(top);
    if (out.how === 'exact' && rest.every(m => m.kind === 'county' && m.how === 'exact')) out.how = 'namesake';
    out.note = `Taken as ${top.name} (the most populous); also ${describeOthers(rest)}. Add the state to pick another.`;
    return { matches: [out], ambiguous: false, others: rest.slice(0, limit).map(strip) };
  }
  return { matches: matches.slice(0, limit).map(strip), ambiguous: true, hint: `${matches.length} places match "${q}"; add the state (e.g. state:"TX") or the kind to narrow it.` };
}
function describeOthers(list) {
  const parts = list.slice(0, 6).map(m => `${m.name}${m.pop55 !== null && m.pop55 !== undefined ? ` (${m.pop55} residents 55+)` : ''}${m.via ? ` via ${m.via.split(' is in ')[0]}` : ''}`);
  return parts.join(', ') + (list.length > 6 ? ` and ${list.length - 6} more` : '');
}
