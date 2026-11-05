/* Deterministic question parser for "Ask the map". No model: a question is read with a fixed vocabulary (lexicon.js) and the
   place indexes (places.js). It returns a plan, or null when it is not confident (then the model planner runs and its plan is
   checked against the same readings by checkPlan). Plan fields:
     route: search | data | scope | other
     shape: ranking | lookup | compare | count | threshold | represents | cosponsor | need | bytype   (data route)
     level: county | district | state | national;  state: USPS or null;  places: [{kind, id, name, state, geoid?, via?}]
     metric: key in METRICS;  site: incidence/mortality site key;  acs: veh|bb|unins|unins55|pov;  cancer_type: trial type key
     order: worst | best;  n: 1..25;  cosponsor: yes | none | null;  bill: ctma_hr | ctma_s;  rural: metro | nonmetro | null
     threshold: {op, value, unit};  need: {measure, site, crit, thr};  search: {zip, city, state, cancer_type, keyword, age, radius}
     ambiguity: {kind, options}  when a name matches several places and nothing in the question picks one
     source: 'parser' | 'model';  flags: readings of the question text that checkPlan uses */
import { METRICS, TYPES, CANCER_WORDS, ACS, STATES, TERRITORIES, SITE_LABEL, metricWorse } from './lexicon.js';
import { buildIndex, findStates, fuzzyStates, findCounties, findBareCounty, findDistricts, findZips, findCities, findMembers, norm, key, editDistance } from './places.js';

// a misspelt keyword ("distrcits", "acess") is read as the keyword when it is one edit away and is not itself a known name
const KEYWORDS = ['districts', 'district', 'counties', 'county', 'states', 'access', 'trials', 'trial', 'cosponsor', 'cosponsors', 'cosponsored', 'sponsor', 'incidence', 'mortality', 'oncologists', 'oncologist', 'nearest', 'closest', 'median', 'average', 'rural', 'residents', 'members', 'senators', 'parishes', 'within', 'miles', 'center', 'uninsured', 'poverty', 'broadband', 'vehicle', 'deaths', 'worst', 'least', 'fewest', 'highest', 'lowest', 'share', 'people', 'compare', 'represents', 'national', 'nationally', 'cancer', 'facilities', 'hours', 'drive', 'percent', 'congressional'];
function fixSpelling(n, ix) {
  return n.replace(/[a-z]{5,}/g, t => { if (KEYWORDS.includes(t)) return t; if (STATE_WORD_SET.has(t) || (ix.countyWords && ix.countyWords.has(t)) || (ix.counties && ix.counties.has(key(t))) || (ix.places && ix.places.has(key(t))) || (ix.members && ix.members.has(t)) || CANCER_WORD_SET.has(t)) return t; if (PROTECT.has(t)) return t; const hits = KEYWORDS.filter(k => Math.abs(k.length - t.length) <= 1 && k !== t + 's' && t !== k + 's' && editDistance(t, k, 1) <= 1); return hits.length === 1 ? hits[0] : t; });
}
const PROTECT = new Set('state states cities county trial trials rates hours shares deaths miles center centre drives sponsor senate house median averages percent people nearest farthest worst least fewer fewest which where there these those their about around after before other within without under every single average members member rural metro cancer cancers access excess acres sites cases years older adults women counts total totals rates places place shares short shorts drive hours hour tracts trial trials sponsors sponsor houses senators senator member parish parishes borough towns town'.split(' '));
const STATE_KEY_OF = Object.fromEntries(Object.entries(STATES).map(([u, nm]) => [key(nm), u]));
const STATE_WORD_SET = new Set(Object.values(STATES).flatMap(x => x.toLowerCase().split(' ')));
const CANCER_WORD_SET = new Set(CANCER_WORDS.flatMap(([w]) => w.split(' ')));

const low = q => String(q || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[“”"]/g, '').replace(/\s+/g, ' ').trim();
const WORDNUM = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, twelve: 12, fifteen: 15, twenty: 20, 'twenty-five': 25 };

const SCOPE_RE = /\b(am i|i am (?!\d)|i'm (?!\d)|i have|i've|i was|my (wife|husband|mother|father|mom|dad|son|daughter|friend|sister|brother|partner|patient|doctor|oncologist|diagnosis|cancer|tumou?r)|eligib|qualif|should i|should (he|she|they|we)|prognosis|survival rate|cure|cured|best (hospital|doctor|oncologist|treatment|drug|center for)|which (hospital|doctor|oncologist) (should|is best)|recommend|chemo|immunotherapy|radiation|side effects?|dosage|dose|stage (1|2|3|4|i{1,3}v?)\b|metasta|remission|second opinion|what treatment|treatment options?|enroll me|sign me up|can i join|how do i join)/;
const OTHER_RE = /\b(poem|joke|story|song|haiku|limerick|recipe|essay|system prompt|your (rules|instructions|prompt)|ignore (your|all|the|previous|prior)|disregard|pretend|roleplay|who are you|what are you|what model|hello|hi there|good (morning|afternoon|evening)|thank you|thanks)\b/;
const DEFINE_RE = /\b(what does .{2,40} mean|what is meant by|define|definition of|how (is|are|was|were) .{2,40} (calculated|computed|measured|counted|defined|built)|methodology|how does (the|this) (map|site|box|tool) work|where does the data come from|what is (a|an|the) (broad menu|nci[- ]designated|nci center|recruiting trial|road[- ]mile|rucc|age[- ]adjusted)|what counts as)\b/;

export function parseQuestion(q, ctx) {
  const text = String(q || '').trim().slice(0, 300); if (text.length < 2) return null;
  const ix = buildIndex(ctx || {}); const n0 = low(text); const n = fixSpelling(n0, ix); const flags = {}; if (n !== n0) flags.spelling = n;
  let states = findStates(text); let stateCodes = [...new Set(states.filter(s => !s.territory).map(s => s.usps))]; const territory = states.find(s => s.territory);
  const counties = findCounties(text, ix, stateCodes); const districts = findDistricts(text, ix, stateCodes); const zips = findZips(text, ix);
  for (let i = counties.length - 1; i >= 0; i--) { const c = counties[i]; const stem = c.matches[0].stem; if (STATE_KEY_OF[key(stem)] && stateCodes.includes(STATE_KEY_OF[key(stem)]) && /\b(which|single|worst|best|most|least|fewest|lowest|highest|top)\b/.test(n) && !states.some(st => st.start >= c.end && st.start <= c.end + 3)) counties.splice(i, 1); }   // "which Texas county is worst" is Texas, not Texas County (OK/MO)
  for (let i = districts.length - 1; i >= 0; i--) { const d = districts[i]; const num = +d.id.slice(3); const after = n.slice(d.end, d.end + 14); if (num > 53 || /^\s*(\+|%|percent|and older|and over|or older|years|year|residents|people|plus|miles|mi\b|trials)/.test(after)) districts.splice(i, 1); }   // "Texas 55+ residents" is not a district
  if (!stateCodes.length) { const fz = fuzzyStates(text, ix, counties.map(c => [c.start, c.end])); if (fz.length) { states = states.concat(fz); stateCodes = [...new Set(fz.map(s => s.usps))]; flags.fuzzy_state = fz.map(f => `${f.word}->${f.usps}`); } }
  const spans = [...counties.map(c => [c.start, c.end]), ...districts.map(d => [d.start, d.end]), ...states.filter(s => !s.territory).map(s => [s.start, s.end]), ...zips.map(z => [z.start, z.end])];
  const cancer = findCancer(n); const metricRead = readMetric(n, cancer); const order = readOrder(n, metricRead); const count = readN(n);
  const cos = readCosponsor(n); const level = readLevel(n); const needRead = readNeed(n, cancer);
  const represents = /\b(who (represents|is the (rep|representative|congress(man|woman|member)|house member|member of congress))|whose district|which (congressional )?district (is|contains|covers|includes|has|serves)|representative (for|of)\b|who are (the )?(senators|representatives)|which (district|member) (represents|serves|covers))/.test(n);
  const memberCtx = represents || !!cos || /\b(member|congress|district|vote|bill)\b/.test(n) || n.split(/\s+/).length <= 3;
  const members = findMembers(text, ix, memberCtx, new Set(counties.flatMap(c => c.phrase.split(/[\s,]+/)).concat(districts.map(d => d.id.toLowerCase()))));
  const cities = findCities(text, ix, states, spans, new Set(members.flatMap(m => m.tokens || [m.surname])));
  const rankish = /\b(which|counties|districts|states|most|least|fewest|lowest|highest|worst|best|top|how many|share|percent|average|median|compare|vs|versus)\b/.test(n);
  const searchCue = /\b(near me|close to (me|where i live|home|my home)|where i live|my area|around me|around here|nearby me)\b/.test(n); const findCue = /\b(find|search|searching|looking for|look for|show me|get me|list)\b/.test(n) && /\b(trials?|studies|study)\b/.test(n);
  const lookupish = /\b(how does|how is|tell me about|who represents|look ?up|access|share|how far|how many|what is|what's|rate|median|average|incidence|deaths|oncolog)\b/.test(n) && !findCue && !searchCue;
  const searchy = searchCue || (!counties.length && !districts.length && !lookupish && ((zips.length && (cancer || /\b(trials|studies|near|find)\b/.test(n))) || (!rankish && ((zips.length || cities.length) && /\b(trials|studies)\b/.test(n) && /\b(near|nearby|around|close to|in|at|within \d+ (mi|miles)|find|search|looking for|list)\b/.test(n))) || (!rankish && findCue && !metricRead)));
  Object.assign(flags, { states: stateCodes, zips: zips.map(z => z.zip), order_words: order.words, cosponsor_words: cos ? cos.word : null, cancer_words: cancer ? cancer.word : null, level_words: level.word, metric_words: metricRead ? metricRead.word : null, count_words: readCountShape(n) });

  // 1. out-of-scope and off-topic questions that are clear without a model
  if (DEFINE_RE.test(n) && !counties.length && !districts.length && !zips.length) return { route: 'other', shape: 'other', source: 'parser', flags, definition: true };
  if (SCOPE_RE.test(n) && !represents && !cos) return { route: 'scope', shape: 'scope', source: 'parser', flags };
  if (OTHER_RE.test(n) && !metricRead && !counties.length && !districts.length && !zips.length && !cities.length) return { route: 'other', shape: 'other', source: 'parser', flags };
  if (territory && !stateCodes.length && !counties.length && !districts.length && !zips.length) return { route: 'data', shape: 'territory', territory: territory.usps, source: 'parser', flags, places: [], level: 'state', metric: 'pct_lt20' };

  // 2. the finder: trials near a ZIP or a town
  if (searchy && (zips.length || cities.length || searchCue || findCue || (!counties.length && !districts.length && stateCodes.length))) {
    if (!metricRead || ['trials_here', 'wmean60', 'type_trials', 'pct_lt20'].includes(metricRead.key) || zips.length || searchCue) {
      const z = zips[0]; const c = cities[0];
      if (c && c.ambiguous && !z) return { route: 'data', shape: 'ambiguous', source: 'parser', flags, ambiguity: { kind: 'city', options: c.hits.slice(0, 8).map(h => ({ name: h.name, id: h.fips, state: h.state })) }, places: [] };
      return { route: 'search', shape: 'search', source: 'parser', flags, search: { zip: z ? z.zip : null, zip_county: z ? z.fips : null, city: c ? c.best.name : null, city_county: c ? c.best.fips : null, state: c ? c.best.state : (stateCodes[0] || null), cancer_type: cancer ? cancer.type : null, keyword: readKeyword(n), age: readAge(n), radius: readRadius(n) } };
    }
  }

  // 3. places named in the question, resolved to ids (counties first, then districts, members, ZIPs, towns, states)
  const places = []; let ambiguity = null; const hasStateHint = stateCodes.length > 0;
  for (const c of counties) {
    let hits = c.matches; const after = states.find(st => !st.territory && st.start >= c.end && st.start <= c.end + 3 && /^[\s,]*$/.test(norm(text).slice(c.end, st.start)));
    if (hits.length > 1 && after) { const inAfter = hits.filter(h => h.state === after.usps); if (inAfter.length) hits = inAfter; }   // "Iowa County, Wisconsin": the state after the name wins
    if (hits.length > 1 && hasStateHint) { const inState = hits.filter(h => stateCodes.includes(h.state)); if (inState.length) hits = inState; }
    if (hits.length > 1 && hits.length <= 3) { const sorted = hits.slice().sort((a, b) => (b.pop55 || 0) - (a.pop55 || 0)); if (sorted[0].pop55 > 0 && sorted.slice(1).every(h => (h.pop55 || 0) * 20 <= sorted[0].pop55)) { flags.also_named = (flags.also_named || []).concat([{ assumed: sorted[0].name, others: sorted.slice(1).map(h => `${h.base} in ${STATES[h.state] || h.state}`) }]); hits = [sorted[0]]; } }   // Hidalgo County: Texas has 100x the 55+ residents of New Mexico's
    if (hits.length > 1) { ambiguity = { kind: 'county', phrase: c.phrase, options: hits.slice(0, 8).map(h => ({ name: h.name, id: h.id, state: h.state })), total: hits.length }; continue; }
    places.push({ kind: 'county', id: hits[0].id, name: hits[0].name, state: hits[0].state });
  }
  for (const d of districts) { if (d.unknown) { places.push({ kind: 'district', id: d.id, unknown: true, state: d.state, name: d.id }); continue; } places.push({ kind: 'district', id: d.id, geoid: d.geoid, name: d.name, state: d.state }); }
  for (const m of members) {
    if (m.entries.length > 1 && !ambiguity) { const inState = hasStateHint ? m.entries.filter(e => stateCodes.includes(e.state)) : []; if (inState.length === 1) { m.entries = inState; } else { ambiguity = { kind: 'member', phrase: m.surname, options: m.entries.slice(0, 8).map(e => ({ name: e.member ? e.member.name : e.name, id: e.id || e.state, state: e.state })) }; continue; } }
    if (m.kind === 'house' && m.alsoSenate && (cos && cos.bill === 'ctma_s' || /\bsenat/.test(n))) { m.kind = 'senate'; m.entries = m.alsoSenate; }
    const e = m.entries[0]; if (m.kind === 'house') places.push({ kind: 'district', id: e.id, geoid: e.geoid, name: e.name, state: e.state, via: { member: e.member && e.member.name } }); else places.push({ kind: 'state', id: e.state, name: STATES[e.state], state: e.state, via: { senator: e.name } });
  }
  // a ZIP or a town names a county by FIPS; when the county file is not loaded yet the row (and its name) is fetched later by id
  for (const z of zips) { if (z.fips && ix.countyById.has(z.fips)) { const e = ix.countyById.get(z.fips); places.push({ kind: 'county', id: e.id, name: e.name, state: e.state, via: { zip: z.zip } }); } else if (z.fips && !ix.hasCounties && ix.fipsState.has(z.fips.slice(0, 2))) places.push({ kind: 'county', id: z.fips, name: `the county of ZIP ${z.zip}`, state: ix.fipsState.get(z.fips.slice(0, 2)), via: { zip: z.zip }, unnamed: true }); else places.push({ kind: 'county', id: null, unknown: true, name: `ZIP ${z.zip}`, via: { zip: z.zip } }); }
  if (!counties.length && !districts.length) for (const c of cities) { if (c.ambiguous) { if (!ambiguity) ambiguity = { kind: 'city', phrase: c.phrase, options: c.hits.slice(0, 8).map(h => ({ name: h.name, id: h.fips, state: h.state })) }; continue; } const e = ix.countyById.get(c.best.fips); const via = { city: `${c.best.name}, ${STATES[c.best.state] || c.best.state}` }; if (e) places.push({ kind: 'county', id: e.id, name: e.name, state: e.state, via }); else if (!ix.hasCounties) places.push({ kind: 'county', id: c.best.fips, name: `the county of ${via.city}`, state: c.best.state, via, unnamed: true }); }
  if (!places.length && !ambiguity && stateCodes.length === 1 && /\b(how does|tell me about|look ?up|show me|what about|compare)\b/.test(n)) { const bare = findBareCounty(text, ix, stateCodes[0]); if (bare && !new RegExp(`\\b${norm(STATES[stateCodes[0]])}\\b`).test(norm(bare.stem))) places.push({ kind: 'county', id: bare.id, name: bare.name, state: bare.state }); }
  // state mentions that are places in their own right (not just "counties in Texas"): a lookup/compare of the state itself
  const stateIsPlace = (u) => { const ms = states.filter(s => s.usps === u); return ms.some(m => !counties.some(c => m.start >= c.start && m.start <= c.end + 3) && !districts.some(d => m.start >= d.start && m.start < d.end) && !cities.some(c => m.start >= c.start && m.start <= c.end + 3)); };
  const nationalWord = level.level === 'national' || /\b(national(ly)? average|the nation|nationally|national (figure|level|rate|share|median|number)|whole country|the (us|u\.s\.|united states|country)( as a whole| average| overall)?|us average|america(n)? average|rest of the country|average american)\b/.test(n);
  if (ambiguity) return { route: 'data', shape: 'ambiguous', source: 'parser', flags, ambiguity, places, state: stateCodes[0] || null, metric: metricRead ? metricRead.key : 'pct_lt20', level: ambiguity.kind === 'member' ? 'district' : 'county' };

  // 4. shape
  const compareWords = /\b(compare|compared (with|to)|comparison|vs\.?|versus|difference between|against (the )?(national|us|state)|than (the )?(national|us|state) average|better or worse than|stack(s)? up|side by side|how does .{3,60} (compare|do against|measure up))\b/.test(n);
  const rankWords = /\b(which|rank|ranking|list|top|bottom|worst|best|most|least|fewest|lowest|highest|furthest|farthest|closest|nearest|longest|largest|smallest|biggest|greatest|leading)\b/.test(n) || /\b(where|who) (are|is|has|have)\b.*\b(counties|districts|states)\b/.test(n);
  const orCompare = stateCodes.length >= 2 && !level.word && /\b(or|better|worse|than)\b/.test(n) && !places.length;
  const countShape = readCountShape(n); const thr = metricRead && metricRead.key === 'onc_class' ? null : readThreshold(n, metricRead);
  const lookupWords = /\b(how (does|is|do)|tell me about|look ?up|show me|what about|what is|what's|how far|how many|how much|stats? for|numbers for|profile|does)\b/.test(n);
  const byType = /\b(by (cancer )?type|breakdown|broken down|each cancer|per cancer type|which cancer types?|for each type|all cancer types)\b/.test(n);
  const explicitPlaceKinds = new Set(places.map(p => p.kind));
  const placeState = places.length ? places[0].state : null;
  const state = stateCodes[0] || placeState || null;
  let shape = null, lvl = level.level;
  const unknownPlace = places.find(p => p.unknown);
  if (unknownPlace) return { route: 'data', shape: 'unknown_place', source: 'parser', flags, places, state, metric: metricRead ? metricRead.key : 'pct_lt20', level: unknownPlace.kind };

  if (cos && cos.bill === 'ctma_s' && (cos.asks || /\bthe \w+ senators\b/.test(n)) && stateCodes.length === 1 && !places.length && !members.length) places.push({ kind: 'state', id: stateCodes[0], name: STATES[stateCodes[0]], state: stateCodes[0], via: { senators: true } });
  let forceLookup = false;
  if (metricRead && metricRead.key === 'onc_class' && /\b(share|percent|percentage|fraction)\b/.test(n) && !places.length && (!level.word || (level.word === 'county' && /\bin counties with\b/.test(n) && !/\b(which|most|fewest|highest|lowest|top)\b/.test(n)))) { forceLookup = true; level.level = stateCodes.length ? 'state' : 'national'; level.word = null; if (stateCodes.length === 1) places.push({ kind: 'state', id: stateCodes[0], name: STATES[stateCodes[0]], state: stateCodes[0] }); else if (!stateCodes.length) places.push({ kind: 'national', id: 'US', name: 'United States' }); }
  if (represents && !places.length && !members.length && stateCodes.length === 1) places.push({ kind: 'state', id: stateCodes[0], name: STATES[stateCodes[0]], state: stateCodes[0] });
  if (forceLookup && places.length === 1) shape = 'lookup';
  else if (represents && (places.length || members.length)) shape = 'represents';
  else if (places.length === 1 && places[0].via && places[0].via.senators) shape = 'represents';
  else if (cos && !metricRead) shape = places.some(p => p.kind === 'district') ? 'represents' : members.length ? 'represents' : 'cosponsor';   // "how many districts have cosponsors" is a cosponsor count, not a threshold
  else if (cos && members.length && !rankWords) shape = 'represents';
  else if (needRead) shape = 'need';
  else if ((compareWords || orCompare) && (places.length >= 2 || (places.length === 1 && (nationalWord || stateCodes.length || /\b(state average|its state|the state|their state|statewide)\b/.test(n))) || (stateCodes.length >= 2) || (stateCodes.length === 1 && nationalWord))) shape = 'compare';
  else if (countShape) shape = 'count';
  else if (byType && (places.length === 1 || stateCodes.length === 1 || nationalWord)) shape = 'bytype';
  else if (thr && (rankWords || /\b(counties|districts|states)\b/.test(n))) shape = 'threshold';
  else if (places.length === 1 && !rankWords && !/\b(counties|districts|states)\b/.test(n.replace(/\bunited states\b/, ''))) shape = 'lookup';
  else if (places.length === 1 && (lookupWords || !metricRead) && !/\b(counties|districts|states)\b/.test(n) && !/\b(which|top|worst|best|most|least|fewest|lowest|highest)\b/.test(n.replace(/\b(how does|how is|how do)\b/g, ''))) shape = 'lookup';
  else if (places.length >= 2 && !rankWords) shape = 'compare';
  else if (places.length === 1 && places[0].kind !== 'state' && metricRead && !/\b(counties|districts|states|members)\b/.test(n) && level.level === null) shape = 'lookup';
  else if (!places.length && stateCodes.length === 1 && /\b(rural|nonmetro|non-metro|metro|urban)\b/.test(n) && !level.word && /\b(how does|how do|differ|compare|gap|versus|vs|between)\b/.test(n)) shape = 'lookup';   // "metro vs rural Alabama": the state's split
  else if (!places.length && stateCodes.length === 1 && !metricRead && !level.word && !rankWords && !searchy) shape = 'lookup';   // "Vermont", "how does Texas do"
  else if (!places.length && stateCodes.length === 1 && lookupWords && !metricRead && !level.word && !/\b(which|worst|best|most|least)\b/.test(n)) shape = 'lookup';
  else if (!places.length && stateCodes.length === 1 && !level.word && metricRead && /\b(how far|how many|number of|what is|what's|what share|what percent|what percentage|what fraction|how much|how rural)\b/.test(n) && !/\b(which|districts|states)\b/.test(n) && !/\b(which|top|worst|best) .{0,20}counties\b/.test(n) && !level.word) shape = 'lookup';   // "how far is Texas from an NCI center"
  else if (nationalWord && !places.length && !stateCodes.length && (!level.word || level.word === 'national') && !rankWords && (metricRead || lookupWords)) shape = 'lookup';
  else if (metricRead || rankWords || level.word) shape = 'ranking';
  if (!shape) return null;

  // 5. level
  if (metricRead && metricRead.level_hint === 'county' && !lvl && !stateCodes.length && ['ranking', 'threshold', 'count'].includes(shape)) lvl = 'county';
  if (shape === 'lookup') lvl = places.length ? places[0].kind : (nationalWord && !stateCodes.length ? 'national' : 'state');
  else if (shape === 'represents') lvl = places.length && places.every(p => p.kind === 'state') ? 'state' : 'district';
  else if (shape === 'cosponsor') lvl = cos && cos.bill === 'ctma_s' ? 'state' : 'district';
  else if (shape === 'need') lvl = 'county';
  else if (shape === 'bytype') lvl = places.length ? places[0].kind : (stateCodes.length ? 'state' : 'national');
  else if (shape === 'compare') { const kinds = places.map(p => p.kind); lvl = kinds.includes('county') ? 'county' : kinds.includes('district') ? 'district' : 'state'; }
  else if (!lvl) lvl = (cos || members.length) ? 'district' : stateCodes.length ? 'county' : (nationalWord ? 'county' : 'state');
  if (lvl === 'national' && ['ranking', 'threshold', 'count'].includes(shape)) lvl = level.sub || 'county';   // "nationally, which counties …"

  // 6. metric
  let metric = metricRead ? metricRead.key : null; let site = cancer && cancer.site ? cancer.site : 'all'; let acs = metricRead && metricRead.acs || null;
  if (!metric) metric = cos ? 'pct_lt20' : shape === 'need' ? 'pct_lt20' : 'pct_lt20';
  if (metric === 'type_trials' && !cancer) metric = 'wmean60';
  if (metric === 'nonmetro_pct' && lvl === 'county') metric = 'rucc'; if (metric === 'onc_class' && lvl !== 'county') metric = 'onc_no_trials_pct';
  let level_note = null;
  if (metric === 'type_trials' && lvl === 'county' && shape !== 'lookup' && shape !== 'compare' && shape !== 'bytype') { metric = 'wmean60'; flags.type_fallback = cancer ? cancer.type : true; }   // by-type counts exist for districts and states only: the county ranking uses all-cancer trials, with the type filter set on the map and the substitution named
  const M = METRICS[metric];
  if (M && !M.levels.includes(lvl) && shape !== 'lookup' && shape !== 'compare' && shape !== 'bytype' && metric !== 'type_trials') {
    // the measure is not published at the asked level: never swap in another measure silently; move to the level that has it
    const asked = lvl; const has = l => M.levels.includes(l);
    if (has('county') && ['ranking', 'threshold', 'count'].includes(shape)) { lvl = 'county'; level_note = { metric, asked, used: 'county' }; }
    else if (has('state') && stateCodes.length === 1 && !places.length) { shape = 'lookup'; lvl = 'state'; places.push({ kind: 'state', id: stateCodes[0], name: STATES[stateCodes[0]], state: stateCodes[0] }); level_note = { metric, asked, used: 'state', lookup: true }; }
    else if (has('state') && ['ranking', 'threshold', 'count'].includes(shape)) { lvl = 'state'; level_note = { metric, asked, used: 'state' }; }
    else if (has('national')) { shape = 'lookup'; lvl = 'national'; places.length = 0; places.push({ kind: 'national', id: 'US', name: 'United States' }); level_note = { metric, asked, used: 'national', lookup: true }; }
    flags.level_fallback = level_note;
  }
  if (['inc', 'mort', 'inc_cases', 'mort_deaths'].includes(metric) && cancer && !cancer.site) { flags.site_unavailable = cancer.word; site = 'all'; }
  let rural = /\b(rural|nonmetro|non-metro|non metro)\b/.test(n) ? 'nonmetro' : /\b(metro|urban)\b/.test(n) && !/\bnonmetro|non-metro\b/.test(n) ? 'metro' : null;
  let onc_no_trials = false; if (metric === 'onc_class') { if (lvl === 'county') { onc_no_trials = true; metric = 'onc'; if (shape === 'threshold') shape = 'ranking'; } else metric = 'onc_no_trials_pct'; }
  if (metric === 'nonmetro_pct' && lvl === 'county') metric = 'rucc';
  if (metric === 'rucc' || metric === 'nonmetro_pct') rural = null;
  if (metric === 'no_route' || metric === 'no_route_broad') { shape = 'threshold'; }

  const finalOrder = order.quality ? order.quality : order.mag ? orderFromMag(order.mag, metric, { acs }, metricRead && metricRead.inverted) : order.order;
  const typeWanted = !!cancer && ((metricRead && metricRead.key === 'type_trials') || !!flags.type_fallback || byType || (!metricRead && /\btrials?\b/.test(n)));
  const plan = { route: 'data', shape, level: lvl, state: (shape === 'lookup' || shape === 'represents' || shape === 'bytype') && places.length && places[0].state ? places[0].state : state, metric, site, acs, cancer_type: typeWanted ? cancer.type : null, order: finalOrder, n: count || (shape === 'lookup' ? 1 : 5), cosponsor: cos ? cos.status : null, bill: cos ? cos.bill : null, rural, onc_no_trials, places, threshold: thr, need: needRead, national: nationalWord, level_note, source: 'parser', flags };
  if (shape === 'lookup' && !places.length) { if (lvl === 'national') plan.places = [{ kind: 'national', id: 'US', name: 'United States' }]; else if (stateCodes.length) plan.places = [{ kind: 'state', id: stateCodes[0], name: STATES[stateCodes[0]], state: stateCodes[0] }]; plan.state = stateCodes[0] || null; }
  if (shape === 'compare') { const have = new Set(plan.places.map(p => p.id)); for (const u of stateCodes) if (!have.has(u) && stateIsPlace(u)) { plan.places.push({ kind: 'state', id: u, name: STATES[u], state: u }); have.add(u); } if (nationalWord || (/\bnational\b/.test(n) && plan.places.length === 1)) plan.places.push({ kind: 'national', id: 'US', name: 'United States' }); if (/\b(state average|its state|the state|their state|statewide)\b/.test(n) && plan.places.length === 1 && plan.places[0].state) plan.places.push({ kind: 'state', id: plan.places[0].state, name: STATES[plan.places[0].state], state: plan.places[0].state }); if (plan.places.length < 2) return null; plan.places = plan.places.slice(0, 4); const kinds = plan.places.map(p => p.kind); plan.level = kinds.includes('county') ? 'county' : kinds.includes('district') ? 'district' : kinds.includes('state') ? 'state' : 'national'; }
  if (shape === 'bytype') { plan.metric = 'type_trials'; if (cancer) plan.cancer_type = cancer.type; if (!plan.places.length) plan.places = stateCodes.length ? [{ kind: 'state', id: stateCodes[0], name: STATES[stateCodes[0]], state: stateCodes[0] }] : [{ kind: 'national', id: 'US', name: 'United States' }]; plan.level = plan.places[0].kind; }
  if (shape === 'need') { plan.level = 'county'; plan.metric = needRead.measure === 'mort' ? 'mort' : 'inc'; plan.site = needRead.site; }
  if (plan.onc_no_trials && (shape === 'count' || shape === 'threshold')) plan.threshold = { op: '>', value: 0, unit: 'oncologists' };
  if (plan.metric === 'no_route' || plan.metric === 'no_route_broad') plan.threshold = { op: 'absent', value: null, unit: 'route' };
  if (shape === 'count' || shape === 'threshold') { if (!plan.threshold) plan.threshold = defaultThreshold(n, plan.metric); }
  if (shape === 'cosponsor' && !plan.cosponsor) plan.cosponsor = 'yes';
  if (shape === 'cosponsor') plan.metric = plan.bill === 'ctma_s' ? 'cos_s4440' : 'cos_hr3521';
  if (shape === 'represents' && !metricRead) plan.metric = plan.places.some(p => p.kind === 'state') && (plan.bill === 'ctma_s' || plan.places[0].via && plan.places[0].via.senators) ? 'cos_s4440' : 'cos_hr3521';
  if (shape === 'ranking' && plan.cosponsor && plan.level !== 'district') plan.level = 'district';
  return plan;
}

// ---------- readers ----------
export function findCancer(n) { const s = ' ' + n.replace(/[-]/g, ' ') + ' '; for (const [w, type, site] of CANCER_WORDS) { const re = new RegExp(`[\\s(]${w.replace(/\s+/g, '\\s+')}(s|cancers?|carcinoma|tumou?rs?)?[\\s,.?!)]`); if (re.test(s)) return { word: w, type, site }; } return null; }

export function readMetric(n, cancer) {
  const nci = /\b(nci|nci-designated|cancer cent(er|re)s?|comprehensive cancer|designated cent)/.test(n); const broad = /\b(broad[- ]menu|broad trial menu|100\+|100 or more|100 trials|hundred trials)(?![a-z0-9])/.test(n); const limited = /\b(limited menu|20\+ trials|20 or more trials)\b/.test(n);
  const people = /\b(how many|number of|count of|most|fewest|more|fewer|total) (\w+ )?(people|residents|adults|americans|texans|folks|seniors)\b/.test(n) && !/\b(share|percent|percentage|proportion|fraction|rate|half|quarter|third)\b|\d ?%/.test(n);
  const center = /\b(county|population) cent(er|re)\b/.test(n);
  const has = re => re.test(n); const n2 = n.replace(/\bwithin (60|sixty|\d+)( road[- ]?)?( ?mi| ?miles)?\b/g, ' ').replace(/\b(60|sixty) ?(road[- ]?)?(mi|miles) (radius|of home)\b/g, ' '); const has2 = re => re.test(n2);
  { const tm = n.match(/\b(more than|over|at least|fewer than|less than|under|at most)\s+(\d{1,4})\s+(recruiting |cancer |open )?(trials?|studies)\b/); const nearby = has(/\bwithin (60|sixty)\b|\bnearby\b|\bnear(by)? (them|home)\b|\bclose by\b|\bin reach\b|\bwithin reach\b/);
    if (tm && !(+tm[2] === 20 && /^(fewer|less|under)/.test(tm[1]) && nearby) && !(+tm[2] === 100 && /\b(residents|people|share)\b/.test(n.slice(0, tm.index)))) return { key: nearby ? 'wmean60' : 'trials_here', word: `${tm[1]} ${tm[2]} trials${nearby ? ' nearby' : ''}`, threshold: { op: opOf(tm[1]), value: +tm[2], unit: 'trials' } }; }
  if (has(/\bno (road )?route\b|\bwithout a (road )?route\b|\bunreachable by road\b|\bno road connection\b/)) return { key: broad && !nci ? 'no_route_broad' : 'no_route', word: 'no road route' };
  if (has(/\b(oncologist|oncologists|hematologist|cancer doctors?)\b/)) { if (has(/\bper (100,?000|100k|capita)\b|\brate\b|\bper resident/)) return { key: 'onc_per100k', word: 'oncologists per 100,000' }; if (has(/\b(but|and|with|yet|without|lack|lacking|no|zero)\b[^.]{0,12}\b(no |zero |without |lack(ing)? of )?trials?\b/) && has(/\b(no|zero|without|lack)\b/)) return { key: 'onc_class', word: 'oncologists but no trials', level_hint: 'county', alt: 'onc_no_trials_pct' }; if (has(/\bwithin 60|\bnearby|\bnear(by)? home/)) return { key: 'onc60', word: 'oncologists within 60' }; return { key: 'onc', word: 'oncologists' }; }
  if (has(/\b(death rate|deaths|death|mortality|die|dying|died|fatal)\b/) && !has(/\bdeath (vs|versus)/)) { if (!(cancer && cancer.site) && (has(/\b(how many|number of|annual|a year|per year|most|fewest|total) (cancer )?deaths/) || has(/\bdeaths (per year|a year|annually|each year)\b/))) return { key: 'mort_deaths', word: 'deaths per year' }; return { key: 'mort', word: 'death rate' }; }
  if (has(/\b(incidence|new cases|diagnos(es|ed|is)|cancer rates?|cases per|case rate|cancer burden|cases a year|cases per year|annual cases)\b/)) { if (!(cancer && cancer.site) && (has(/\b(how many|number of|annual|a year|per year|most|fewest|total) (new )?(cancer )?(cases|diagnoses)/) || has(/\b(cases|diagnoses) (per year|a year|annually|each year)\b/))) return { key: 'inc_cases', word: 'cases per year' }; return { key: 'inc', word: 'incidence' }; }
  if (has(/\b(no|zero|without (a|any)|not (a )?single|lack(s|ing)? (a|any))\s+(recruiting |cancer |open |active )?(trials?|studies)\b[^.]{0,30}\b(within|nearby|near(by)? (them|home)|in reach|close by|close to home|60)/) || has(/\b(trials?|studies) (at all )?within 60[^.]{0,20}\b(none|zero)\b/)) return { key: people ? 'people_zero' : 'pct_zero', word: 'no trial within 60' };
  if (has(/\b(no|zero|without (a|any)) (recruiting |cancer )?trials? (at all|nearby|near(by)? them|in reach|close)\b/) || has(/\bnot (one|a single) trial\b/)) return { key: people ? 'people_zero' : 'pct_zero', word: 'no trial nearby' };
  if (has(/\b(fewer|less) than 100\b|\bunder 100 (recruiting )?trials|\b(fewer|less) than a hundred/)) return { key: 'pct_lt100', word: 'fewer than 100' };
  if (has(/\b(more|further|farther|greater|longer) than (60|sixty) (road[- ]?)?(mi|miles)|\bbeyond (60|sixty)( road[- ]?)?( ?mi| ?miles)?|\bover (60|sixty) (road[- ]?)?(mi|miles)|\b(60|sixty)\+? ?(road[- ]?)?(mi|miles) (or more )?(away|from)|\bmore than an hour('s)? (drive|away)/)) { if (broad && !nci) return { key: people ? 'people_gt60_broad' : 'pct_gt60_broad', word: 'beyond 60 miles of a broad menu' }; return { key: people ? 'people_gt60_nci' : 'pct_gt60_nci', word: 'beyond 60 miles of an NCI center' }; }
  if (has(/\b(driv(e|ing) (time|hours?)|hours? (of )?driv|hours? (to|from|away)|how long (to|does it take to|is the) driv|drive hours|hours' drive|hour drive|hours? (is|are|was) the driv(e|ing)|(longest|shortest|long|short|far) (a )?(drive|driving|trip)|drive (to|from) (an? |the )?(nci|cancer|broad)|driving (distance|time))\b/)) return { key: broad && !nci ? 'hb' : 'hn', word: 'drive hours' };
  if ((has(/\b(nearest|closest) (nci|cancer cent|comprehensive)/) || has(/\b(which|what) (nci|cancer|nci-designated) cent(er|re)s? (is|are) (the )?(nearest|closest)/)) && has(/\b(which|what|name|where|who|is the|is their|is its)\b/) && !has(/\bhow far|\bmiles|\bdistance/)) return { key: 'nearest_nci', word: 'nearest NCI center name' };
  if (has(/\b(nearest|closest) (broad[- ]menu|county with 100|100\+ county|place with 100)/) && !has(/\bhow far|\bmiles|\bdistance/)) return { key: 'nearest_broad', word: 'nearest broad-menu county' };
  if (has(/\b(fewer|less) than (20|twenty)\b|\bunder (20|twenty)\b|\bshort of trials|\btrial[- ]?short|\bshortage|\bshortfall|\b(20|twenty) or more\b|\bat least (20|twenty)\b|\b20\+|\btwenty\+/)) { const inverted = has(/\b(20|twenty) or more\b|\bat least (20|twenty)\b|\b20\+|\btwenty\+/); const ppl = people || (has(/\b(residents|people) (short|with fewer|who are short)\b/) && !/\b(share|percent|percentage|proportion|fraction|rate)\b|\d ?%/.test(n)); return { key: ppl ? 'people_lt20' : 'pct_lt20', word: 'fewer than 20', inverted }; }
  if (has2(/\b(median|typical|average|mean) (road[- ]?)?(mi|miles|distance)|\bhow far\b|\bdistance\b|\b(road[- ]?)?miles? (to|from|away)\b|\bfar (from|to|away)\b|\bfurthest|\bfarthest|\bclosest|\bnearest|\bremote(st)?\b|\bisolated\b|\bmiles\b/)) { if (broad && !nci) return { key: center ? 'rb_center' : 'med_broad', word: 'miles to broad menu' }; if (limited) return { key: 'rl_center', word: 'miles to limited menu' }; return { key: center ? 'rn_center' : 'med_nci', word: 'miles to NCI center' }; }
  if (has(/\b(no|without|lack(s|ing)?) (a )?(vehicle|car)|\bvehicle|\bcar ownership|\bcarless|\bno cars?\b/)) return { key: 'acs', acs: 'veh', word: 'no vehicle' };
  if (has(/\bbroadband|\binternet\b/)) return { key: 'acs', acs: 'bb', word: 'broadband' };
  if (has(/\buninsured[^.]{0,25}\b(55|ages? 55|55-64|55 to 64)|\b55[^.]{0,8}64[^.]{0,25}uninsured/)) return { key: 'acs', acs: 'unins55', word: 'uninsured 55-64' };
  if (has(/\buninsured|\bno (health )?insurance|\bwithout (health )?insurance|\bhealth insurance|\binsurance coverage/)) return { key: 'acs', acs: 'unins', word: 'uninsured' };
  if (has(/\bpoverty|\bpoor(est)? (counties|places|households|areas|districts)|\blow[- ]income/)) return { key: 'acs', acs: 'pov', word: 'poverty' };
  if (has(/\btrials? (with|that have|having) (a |an |any )?(sites?|locations?|facilit)/) || has(/\btrials? listed\b/) || has(/\btrials? (based|located|listed|running|recruiting) in\b/)) { if (cancer && has(/\b(within|nearby|near(by)? home|in reach)\b/)) return { key: 'type_trials', word: `${cancer.word} trials within 60` }; return { key: 'trials_here', word: 'trials with a site' }; }
  if (has(/\b(facilit(y|ies)|trial sites?|sites? (with|running|hosting) trials|sites? in the|how many sites|locations? (with|running) trials)\b/)) { if (has(/\bwithin 60|\bnearby|\bnear(by)? home/)) return { key: 'f60', word: 'sites within 60' }; return { key: center ? 'f60' : 'facilities', word: 'facilities' }; }
  if (has(/\bbroad menu\b/) && has(/\b(has|have|with|having|offer|offers|offering) (a )?broad menu/)) return { key: 'trials_here', word: 'has a broad menu', threshold: { op: '>=', value: 100, unit: 'trials' } };
  if (has(/\b(average|mean|typical|on average) (number of )?(recruiting )?(cancer )?trials|\btrials (within|in) 60|\btrials? (nearby|near(by)? (home|them)|within reach|close to home|in reach)|\bhow many trials (are |do (they|residents) have )?(nearby|within|in reach|close)|\btrials within (60 )?(road[- ]?)?miles/)) { if (cancer && has(/\btrials?\b/)) return { key: 'type_trials', word: `${cancer.word} trials within 60` }; return { key: center ? 't60' : 'wmean60', word: 'average trials within 60' }; }
  if (has(/\b(trials?|studies) (listed|based|located|running|open|recruiting|taking place|with (a )?sites?|that have sites?) (in|here|there|at)\b|\btrials? in the (county|district|state|area)|\b(how many|number of|count of|total) (recruiting |active |open |cancer )*(trials?|studies)\b|\btrials? (are|is) (there )?(in|at)\b|\bhost(s|ing)? trials|\brecruiting trials in\b|\bsites? for trials/)) { if (cancer && has(/\b(within|nearby|near(by)? home|in reach)\b/)) return { key: 'type_trials', word: `${cancer.word} trials within 60` }; return { key: 'trials_here', word: 'trials in the place' }; }
  if (has2(/\b(most|fewest|more|fewer|how many|number of|highest number of|lowest number of) (recruiting |cancer |open |active )?(trials|studies)\b/) && !has(/\b(nearby|near(by)? (home|them)|in reach|within)\b/)) { if (cancer && !has(/\b(listed|with a site|in the (county|district|state))\b/)) return { key: 'type_trials', word: `${cancer.word} trials` }; return { key: 'trials_here', word: 'most/fewest trials' }; }
  if (broad && !has(/\bwithin 60\b/)) return { key: 'pct_gt60_broad', word: 'broad menu' };
  if (cancer && has(/\btrials?\b/) && !has(/\b(incidence|death|mortality)\b/)) return { key: 'type_trials', word: `${cancer.word} trials` };
  if (has(/\b(rural|nonmetro|non-metro|urban|metro)\b/) && has(/\b(most|least|largest|smallest|highest|lowest|biggest|how) (rural|nonmetro|non-metro|urban|metro)\b|\b(rural|nonmetro|non-metro|metro|urban) (share|percent|percentage|population|residents)\b|\bshare (of )?(residents |people )?(in |living in )?(rural|nonmetro|metro|urban)|\bpercent (rural|nonmetro)/)) return { key: 'nonmetro_pct', word: 'nonmetro share', alt: 'rucc' };
  if (has(/\b(access|underserved|gap|gaps|deserts?|worst off|short)\b/)) { const people = has(/\b(how many|number of|count of|most) (people|residents|adults|americans)\b|\b(people|residents) (55|aged|who)/); return { key: people ? 'people_lt20' : 'pct_lt20', word: 'access' }; }
  if (has(/\b(how many|number of|most|fewest) (people|residents|adults|americans)\b/) && has(/\b(trials?|short|fewer)\b/)) return { key: 'people_lt20', word: 'people short' };
  if (has(/\b(most|fewest|largest|smallest|biggest|how many|number of|total) (residents|people|population|adults)( 55| aged 55| 55\+| 55 and older| 55 and over| over 55| aged)?\b/) || has(/\bpopulation (55|aged|over)\b/) || has(/\b(residents|people) (55|aged 55|55\+) (and older|and over|or older|plus)?\s*(live|lives|living|are there|reside)\b/)) return { key: 'pop55', word: 'residents 55+' };
  return null;
}

export function orderFromMag(mag, metric, plan, inverted) { const worse = metricWorse(metric, plan || {}); let order = (mag === worse) ? 'worst' : 'best'; if (inverted) order = order === 'worst' ? 'best' : 'worst'; return order; }
export function readOrder(n0, metricRead) {
  const n = n0.replace(/\b(at least|at most|not least|at the least|at the most)\b/g, ' ');
  const quality = /\b(worst|poorest|weakest|lowest access|least access|worst off|worst access|bottom|most underserved|least served)\b/.test(n) ? 'worst' : /\b(best|strongest|greatest access|best access|best served|most access)\b/.test(n) ? 'best' : null;
  const mag = /\b(most|highest|largest|greatest|biggest|longest|furthest|farthest|heaviest|max(imum)?)\b/.test(n) ? 'high' : /\b(least|fewest|lowest|smallest|shortest|closest|nearest|min(imum)?)\b/.test(n) ? 'low' : null;
  const words = [quality, mag].filter(Boolean).join('+') || null;
  if (quality) return { order: quality, quality, mag, words };
  if (mag) return { order: orderFromMag(mag, metricRead ? metricRead.key : 'pct_lt20', { acs: metricRead && metricRead.acs }, metricRead && metricRead.inverted), mag, words };
  if (/\btop (\d+ |three |five |ten )?(counties|districts|states|places)\b|\btop[- ]ranked\b|\bbest\b/.test(n)) return { order: 'best', quality: 'best', words: 'top' };
  return { order: 'worst', words };
}

export function readN(n) { if (/\b(single|one) (\w+ )?(county|district|state|place|member)\b/.test(n) || /\bwhich (\w+ )?(county|district|state) (is|has)\b/.test(n)) return 1; for (const re of [/\btop (\d{1,2}|[a-z]+)\b/, /\b(\d{1,2}|[a-z]+) (worst|best|lowest|highest|most|least|fewest|largest|smallest|counties|districts|states|places)\b/, /\b(worst|best|lowest|highest|bottom|top|first|last) (\d{1,2}|[a-z]+)\b/, /\b(\d{1,2}|two|three|four|five|six|seven|eight|nine|ten) (?:[a-z]+ ){0,2}(counties|districts|states|parishes|places)\b/]) { const m = n.match(re); if (!m) continue; const w = /^\d+$/.test(m[1]) ? +m[1] : WORDNUM[m[1]]; if (w) return Math.min(25, Math.max(1, w)); } return null; }
export function readAge(n) { const m = n.match(/\b(\d{2})[- ]?(years?[- ]?old|yo|y\/o)\b/) || n.match(/\b(?:age|aged)\s+(\d{2})\b/) || n.match(/\bi(?:'m| am)\s+(\d{2})\b/); const a = m ? +m[1] : null; return a && a >= 18 && a <= 110 ? a : null; }
export function readRadius(n) { const m = n.match(/\bwithin (30|60|120|200) (mi|miles)\b/); return m ? +m[1] : null; }
export function readKeyword(n) { const m = n.match(/\b([a-z]{4,}(?:mab|nib|tide|lisib|ciclib|parib|sertib|zumab|ximab|tinib|rafenib|platin|taxel|rubicin|vantage))\b/) || n.match(/\b(kras|egfr|her2|brca[12]?|alk|braf|msi-h|msi|pd-?l?1|ntrk|ret|met|fgfr|idh[12]?|car-?t|tmb|pik3ca|esr1|nrg1|ros1|claudin)\b/); return m ? m[1] : null; }
export function readLevel(n) {
  const nat = /\b(national(ly)?|nationwide|nation-wide|in the (us|u\.s\.|usa|united states|country|nation)|across the (country|us|u\.s\.|nation|states)|americans?|the whole country|us-wide|countrywide|anywhere in the us)\b/.test(n);
  const n1 = n.replace(/\bunited states\b/g, ''); const found = [['county', /\b(counties|county level|by county|per county|each county|every county|which county|what county|(single|one) (\w+ )?county)\b/], ['district', /\b(districts|district level|by district|per district|each district|every district|house members|members of congress|congressmen|representatives|which district|what district|(single|one) (\w+ )?district)\b/], ['state', /\b(states|state level|by state|per state|each state|every state|which state|what state|(single|one) (\w+ )?state)\b/]].map(([w, re]) => { const m = n1.match(re); return m ? [w, m.index] : null; }).filter(Boolean).sort((a, b) => a[1] - b[1]);
  const word = found.length ? found[0][0] : null;   // the first level word wins: "which districts have residents in counties with…" is about districts
  if (word) return { level: word, word, sub: word };
  if (nat) return { level: 'national', word: 'national', sub: null };
  return { level: null, word: null };
}
export function readCosponsor(n) {
  const bill = /\bs\.? ?4440\b|\bsenate bill|\bsenators?\b/.test(n) && !/\bh\.? ?r\.? ?3521\b|\bhouse\b/.test(n) ? 'ctma_s' : 'ctma_hr';
  const word = (n.match(/\b(co-?sponsor(s|ed|ing|ship)?|sponsor(s|ed|ing)?|h\.? ?r\.? ?3521|s\.? ?4440|clinical trial modernization act|ctma)\b/) || [])[0];
  if (!word) return null;
  const neg = /\b(not|haven't|hasn't|have not|has not|don't|doesn't|do not|does not|aren't|isn't|never|no|without|non|yet to|failed to|refuse|declined)[- ]?(a |an |to |yet |been )?(co-?sponsor|sponsor|sign|back|support)/.test(n) || /\bnon-?co-?sponsors?\b|\b(have|has) not (yet )?(co-?)?sponsored|\b(who|which|that) (have|has)n't\b/.test(n);
  const asks = /\b(does|do|did|is|has|have|are)\b/.test(n) && !/\b(which|who|what|list|how many)\b/.test(n);
  return { word, bill, status: neg ? 'none' : 'yes', asks };
}
export function readCountShape(n) { return /\b(how many|number of|count of|count the|what number of) (of )?(the )?((texas|[a-z]+) )?(counties|districts|states|house members|members|places|congressional districts|representatives)\b/.test(n) || /\bhow many (of (the|its|their) )?(counties|districts|states|members)\b/.test(n) ? 'count' : null; }
export function readThreshold(n, metricRead) {
  if (metricRead && metricRead.threshold) return metricRead.threshold;
  let s = n.replace(/\b(fewer|less) than (20|twenty|100)( recruiting| cancer)? trials?( within (60|sixty)( road[- ]?)?(mi|miles)?)?/g, ' ').replace(/\b(more|further|farther|greater) than (60|sixty) (road[- ]?)?(mi|miles)/g, ' ').replace(/\bwithin (60|sixty)( road[- ]?)?( mi| miles)?/g, ' ').replace(/\b100\+? (or more )?(recruiting )?trials/g, ' ').replace(/\b(20|twenty) or more trials/g, ' ').replace(/\btop \d+|\b\d+ (worst|best|lowest|highest|most|least|fewest)\b/g, ' ').replace(/\b(h\.? ?r\.? ?3521|s\.? ?4440)\b/g, ' ').replace(/\b\d{5}\b/g, ' ').replace(/\b(19|20)\d\d\b/g, ' ');
  const pct = s.match(/\b(more than|over|above|exceeding|greater than|at least|a minimum of|fewer than|less than|under|below|at most|no more than|up to)\s+(\d{1,3}(?:\.\d+)?)\s*(%|percent|per cent|pct)/) || s.match(/\b(\d{1,3}(?:\.\d+)?)\s*(%|percent|per cent)\s+(or more|or higher|and above|or fewer|or less|or lower|and below|plus)/);
  if (pct) { const op = pct[3] && !pct[1].match(/^(more|over|above|exceed|greater|at least|a minimum|fewer|less|under|below|at most|no more|up to)/) ? (/(more|higher|above|plus)/.test(pct[3]) ? '>=' : '<=') : opOf(pct[1]); return { op, value: +(pct[2] || pct[1]), unit: '%' }; }
  const half = s.match(/\b(more than|over|at least|under|fewer than|less than|about|around)?\s*(half|a majority|the majority|a third|two[- ]thirds|a quarter|three[- ]quarters)\b/); if (half && /\b(residents|people|population|of (its|their|the) residents|of (the )?people|adults)\b/.test(s)) { const v = { half: 50, 'a majority': 50, 'the majority': 50, 'a third': 33.3, 'two thirds': 66.7, 'two-thirds': 66.7, 'a quarter': 25, 'three quarters': 75, 'three-quarters': 75 }[half[2]]; return { op: half[1] ? opOf(half[1]) : '>=', value: v, unit: '%' }; }
  const hr = s.match(/\b(more than|over|at least|a minimum of|under|less than|fewer than|at most|within|up to)\s+(an|one|two|three|four|five|six|half an|a half|one and a half)\s+hours?('s)?\b/); if (hr) { const v = { an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, 'half an': 0.5, 'a half': 0.5, 'one and a half': 1.5 }[hr[2]]; return { op: /^(within|up to)$/.test(hr[1]) ? '<=' : opOf(hr[1]), value: v, unit: 'hours' }; }
  const between = s.match(/\bbetween\s+(\d{1,3}(?:\.\d+)?)\s*(%|percent)?\s+and\s+(\d{1,3}(?:\.\d+)?)\s*(%|percent)?/); if (between) { const u = between[2] || between[4] ? '%' : (metricRead && METRICS[metricRead.key] && METRICS[metricRead.key].unit) || '%'; return { op: 'between', value: +between[1], hi: +between[3], unit: u }; }
  const unitm = s.match(/\b(more than|over|above|exceeding|greater than|at least|a minimum of|fewer than|less than|under|below|at most|no more than|up to)\s+(\d{1,4}(?:\.\d+)?)\s*(recruiting |cancer |road[- ]?)?(trials?|studies|miles?|mi|hours?|oncologists?|sites?|facilities|people|residents|cases|deaths)\b/) || s.match(/\b(\d{1,4}(?:\.\d+)?)\s*(\+|or more|or fewer|or less)\s*(recruiting |cancer |road[- ]?)?(trials?|studies|miles?|mi|hours?|oncologists?|sites?|facilities)\b/);
  if (unitm) { const op = unitm[2] && /^(\+|or more|or fewer|or less)$/.test(unitm[2]) ? (/(\+|more)/.test(unitm[2]) ? '>=' : '<=') : opOf(unitm[1]); const value = +(unitm[2] && /^(\+|or more|or fewer|or less)$/.test(unitm[2]) ? unitm[1] : unitm[2]); const u = (unitm[4] || '').replace(/s$/, ''); return { op, value, unit: /^mi/.test(u) ? 'road-miles' : /^hour/.test(u) ? 'hours' : /^(trial|stud)/.test(u) ? 'trials' : /^oncolog/.test(u) ? 'oncologists' : /^(site|facilit)/.test(u) ? 'sites' : /^(people|resident)/.test(u) ? 'people' : u }; }
  if (/\b(no|zero|without (any|a)|not (a )?single|lack(s|ing)? (a |any )?)\s*(recruiting |cancer |open )?(trials?|studies|sites?|oncologists?)\b/.test(s) && !/\bwithin\b|\bnearby\b|\bnear(by)? (them|home)\b/.test(n)) return { op: '==', value: 0, unit: 'count' };
  if (/\b(have|has|with|host|hosting|hosts) (a |any |at least one |one or more )?(recruiting |cancer |open )?(trials?|studies|trial sites?|oncologists?)\b/.test(s) && !/\bwithin\b|\bnearby\b/.test(n)) return { op: '>', value: 0, unit: 'count' };
  if (/\b(all|every|100%|entire) (of )?(its |their |the )?(residents?|people|person|population)\b/.test(s)) return { op: '>=', value: 100, unit: '%', every: true };
  if (/\b(any|some) (of )?(its |their |the )?(residents|people)\b/.test(s)) return { op: '>', value: 0, unit: '%' };
  return null;
}
const opOf = w => /^(more|over|above|exceed|greater)/.test(w) ? '>' : /^(at least|a minimum)/.test(w) ? '>=' : /^(fewer|less|under|below)/.test(w) ? '<' : /^(at most|no more|up to)/.test(w) ? '<=' : '>=';
export function defaultThreshold(n, metric) { const M = METRICS[metric]; if (!M) return null; if (metric === 'pct_zero' && /\b(no|zero|without (a|any)|not a single) (recruiting |cancer )?trials?\b/.test(n)) return { op: '==', value: 100, unit: '%', every: true }; if (metric === 'pct_lt20' && /\b(all|every) (of )?(its |their |the )?(residents?|people|person)\b/.test(n)) return { op: '==', value: 100, unit: '%', every: true }; if (M.unit === '%') return { op: '>=', value: 50, unit: '%', assumed: true }; if (M.text) return null; if (/\b(no|zero|without|lack)\b/.test(n)) return { op: '==', value: 0, unit: 'count', assumed: true }; return { op: '>', value: 0, unit: 'count', assumed: true }; }
export function readNeed(n, cancer) {
  const burden = /\b(incidence|burden|new cases|diagnos|cancer rates?|death rates?|deaths|mortality|dying|die)\b/.test(n); const access = /\b(access|short of trials|fewer than 20|no trials?( within| nearby)?|few trials|trial(s)? (nearby|within)|low trial|lack of trials|trial deserts?|underserved)\b/.test(n);
  const pair = /\b(vs\.?|versus|and|but|with|yet|despite|plus|while|against|where|that also|who also)\b/.test(n); const hi = /\b(high|highest|above[- ]median|elevated|heavy|heaviest|top third|most|worst|a lot of|many)\b/.test(n); const lo = /\b(low|lowest|poor|little|few|fewest|limited|weak|no|without|short|lack|fewer|least|worst|far)\b/.test(n);
  const named = /\b(need (vs|versus|and|against) access|burden (vs|versus|and) access|incidence (vs|versus) access|deaths (vs|versus) access|hot ?spots?|need-vs-access|high[- ]need|high[- ]burden,? low[- ]access|double (burden|jeopardy))\b/.test(n);
  if (!(named || (burden && access && pair && (hi || lo)))) return null;
  const measure = /\b(death|deaths|mortality|die|dying)\b/.test(n) ? 'mort' : 'inc'; const crit = /\b(no trials?|zero trials?|not a single trial|without (a|any) trial)\b/.test(n) ? 'z60' : 'l20';
  const t = n.match(/\b(at least|more than|over)\s+(25|50|75)\s*(%|percent)/) || n.match(/\b(25|50|75)\s*(%|percent)\s+or more/); const thr = t ? +(t[2] && /^\d+$/.test(t[2]) ? t[2] : t[1]) : /\bthree[- ]quarters\b/.test(n) ? 75 : /\ba quarter\b/.test(n) ? 25 : 50;
  return { measure, site: cancer && cancer.site ? cancer.site : 'all', crit, thr: [25, 50, 75].includes(thr) ? thr : 50, site_word: cancer ? cancer.word : null };
}
export function fallbackMetric(metric, level) {
  const F = { type_trials: 'wmean60', facilities: 'trials_here', mort: 'inc', mort_deaths: 'inc', inc_cases: 'inc', rucc: 'nonmetro_pct', metro: 'nonmetro_pct', nonmetro_pct: 'rucc', rn_center: 'med_nci', rb_center: 'med_broad', rl_center: 'med_broad', hn: 'med_nci', hb: 'med_broad', t60: 'wmean60', f60: 'trials_here', onc60: 'onc', onc_class: 'onc_no_trials_pct', onc_no_trials_pct: 'onc_class' };
  let k = metric; for (let i = 0; i < 3 && k && !(METRICS[k] && METRICS[k].levels.includes(level)); i++) k = F[k] || 'pct_lt20'; return METRICS[k] && METRICS[k].levels.includes(level) ? k : 'pct_lt20';
}

// ---------- model plan correction ----------
// The model's plan is only a hint: everything the parser can read from the question text overrides it, and place names are
// resolved by the same index (a name the data does not know is reported, never guessed).
export function checkPlan(q, plan, ctx) {
  const src = plan && typeof plan === 'object' && !Array.isArray(plan) ? plan : {};   // only known keys are copied: a planner reply can carry "__proto__" or "constructor"
  const p = { route: ['search', 'data', 'scope', 'other'].includes(src.route) ? src.route : 'other', data: src.data && typeof src.data === 'object' && !Array.isArray(src.data) ? src.data : {}, search: src.search && typeof src.search === 'object' && !Array.isArray(src.search) ? src.search : {}, source: 'model', corrections: [] };
  const n = low(q); const ix = buildIndex(ctx || {}); const states = findStates(q).filter(s => !s.territory); const codes = [...new Set(states.map(s => s.usps))];
  const cancer = findCancer(n); const metricRead = readMetric(n, cancer); const order = readOrder(n, metricRead); const cos = readCosponsor(n); const level = readLevel(n); const zips = findZips(q, ix);
  if (SCOPE_RE.test(n) && p.route !== 'scope') { p.route = 'scope'; p.corrections.push('scope words in the question'); }
  if (p.route === 'search') {
    p.search = p.search || {}; if (zips.length && p.search.zip !== zips[0].zip) { p.search.zip = zips[0].zip; p.corrections.push('zip from question'); } if (!zips.length && p.search.zip) { p.search.zip = null; p.corrections.push('model invented a zip'); }
    if (zips[0]) { p.search.zip_county = zips[0].fips || null; const ce = zips[0].fips && ix.countyById.get(zips[0].fips); if (ce) { p.search.state = ce.state; } }
    if (cancer && p.search.cancer_type !== cancer.type) { p.search.cancer_type = cancer.type; p.corrections.push('cancer type from question'); } if (!cancer) p.search.cancer_type = null; if (!TYPES.includes(p.search.cancer_type)) p.search.cancer_type = null;
    { const st = codes[0] || (zips[0] && zips[0].fips && ix.countyById.has(zips[0].fips) ? ix.countyById.get(zips[0].fips).state : null); if (p.search.state !== st) { if (p.search.state) p.corrections.push('model state not in the question'); p.search.state = st; } }   // a state only from the question (or the ZIP's county)
    { const cs = findCities(q, ix, states, []); const hit = (typeof p.search.city === 'string' && cs.find(c => key2(c.best.name) === key2(p.search.city))) || cs[0]; if (hit && !hit.ambiguous) { p.search.city = hit.best.name; p.search.city_county = hit.best.fips; p.search.state = hit.best.state; } else if (hit && hit.ambiguous) { return { route: 'data', shape: 'ambiguous', source: 'model', ambiguity: { kind: 'city', options: hit.hits.slice(0, 8).map(h => ({ name: h.name, id: h.fips, state: h.state })) }, places: [], corrections: ['town from question is ambiguous'], flags: { states: codes } }; } else { if (p.search.city) p.corrections.push('model town not in the question'); p.search.city = null; p.search.city_county = null; } }   // a town only from the question text
    { const kw = readKeyword(n) || (typeof p.search.keyword === 'string' && p.search.keyword.length >= 2 && p.search.keyword.length <= 40 && n.includes(p.search.keyword.toLowerCase()) ? p.search.keyword : null); p.search.keyword = kw ? kw.replace(/[^\w\s\-+]/g, '').trim().slice(0, 40) || null : null; }   // only words that are in the question itself can reach the finder's URL
    p.search.age = readAge(n) || (Number.isInteger(+p.search.age) && +p.search.age >= 18 && +p.search.age <= 110 ? +p.search.age : null); p.search.radius = readRadius(n) || ([30, 60, 120, 200].includes(+p.search.radius) ? +p.search.radius : null); p.search.age = readAge(n) || (Number.isInteger(p.search.age) && p.search.age >= 18 && p.search.age <= 110 ? p.search.age : null); p.search.radius = readRadius(n) || ([30, 60, 120, 200].includes(+p.search.radius) ? +p.search.radius : null);
    p.flags = { states: codes, zips: zips.map(z => z.zip) }; p.search = { zip: p.search.zip || null, zip_county: p.search.zip_county || null, city: p.search.city || null, city_county: p.search.city_county || null, state: p.search.state || null, cancer_type: p.search.cancer_type || null, keyword: p.search.keyword || null, age: p.search.age || null, radius: p.search.radius || null }; return p;
  }
  if (p.route !== 'data') { p.shape = p.route; p.flags = { states: codes }; return p; }
  const d = p.data; const det = parseQuestion(q, ctx); const own = (o, k) => typeof k === 'string' && Object.hasOwn(o, k);
  if (det && det.route === 'data' && det.shape !== 'ranking') { det.source = 'model+parser'; det.corrections = ['parser reading used for shape ' + det.shape]; return det; }   // the parser knows this shape well; the model only confirmed the route
  const placeInQ = typeof d.place === 'string' && d.place.length <= 60 && n.includes(low(d.place).replace(/[^a-z0-9 ,.'-]/g, '').trim()) ? d.place : null;   // the model may only name a place the question itself names
  if (d.place && !placeInQ) p.corrections.push('model named a place the question does not');
  const shape = ['ranking', 'lookup', 'compare', 'count', 'threshold', 'represents', 'cosponsor', 'need', 'bytype'].includes(d.shape) ? d.shape : (placeInQ ? 'lookup' : 'ranking');
  let lvl = ['county', 'district', 'state', 'national'].includes(d.level) ? d.level : 'district';
  if (level.level && level.level !== lvl) { lvl = level.level; p.corrections.push('level from question words'); }
  let st = own(STATES, d.state) ? d.state : null; if (codes.length && st !== codes[0]) { st = codes[0]; p.corrections.push('state from question'); } if (!codes.length && st && !det) { st = null; p.corrections.push('model invented a state'); }
  let metric = own(METRICS, d.metric) ? d.metric : null; if (metricRead && metric !== metricRead.key) { metric = metricRead.key; p.corrections.push('metric from question words'); } if (!metric) metric = cancer ? 'type_trials' : 'pct_lt20';
  let ctype = TYPES.includes(d.cancer_type) ? d.cancer_type : null; if (cancer && ctype !== cancer.type) { ctype = cancer.type; p.corrections.push('cancer type from question'); } if (!cancer && ctype) { ctype = null; p.corrections.push('model invented a cancer type'); }
  if (metric === 'type_trials' && !ctype) metric = 'wmean60';
  let ord = d.order === 'best' ? 'best' : 'worst'; if (order.words && ord !== order.order) { ord = order.order; p.corrections.push('order from question words'); }
  let cosp = ['yes', 'none'].includes(d.cosponsor) ? d.cosponsor : null; if (cos && cosp !== cos.status) { cosp = cos.status; p.corrections.push('cosponsor words from question'); } if (!cos && cosp) { cosp = null; p.corrections.push('model invented a cosponsor filter'); }
  const nn = readN(n) || (Number.isInteger(+d.n) && +d.n >= 1 ? Math.min(25, +d.n) : 5);
  const places = det && det.places ? det.places : [];   // the only way a place gets an id is through the resolver
  if (placeInQ && !places.length) { const sub = parseQuestion(placeInQ, ctx); if (sub && sub.places && sub.places.length) places.push(...sub.places); else if (sub && sub.ambiguity) { return { route: 'data', shape: 'ambiguous', source: 'model', ambiguity: sub.ambiguity, places: [], corrections: ['place name resolved to several'], flags: { states: codes } }; } else p.corrections.push('place name is not in the data'); }
  let level_note = null; if (!METRICS[metric].levels.includes(lvl) && shape !== 'lookup') { const M2 = METRICS[metric]; if (M2.levels.includes('county')) { level_note = { metric, asked: lvl, used: 'county' }; lvl = 'county'; } else if (M2.levels.includes('state')) { level_note = { metric, asked: lvl, used: 'state' }; lvl = 'state'; } else metric = 'pct_lt20'; }
  const out = { route: 'data', shape: places.length === 1 && shape === 'ranking' && !level.word ? 'lookup' : shape, level: places.length && shape === 'lookup' ? places[0].kind : lvl, state: st || (places[0] && places[0].state) || null, metric, site: cancer && cancer.site ? cancer.site : 'all', acs: metricRead && metricRead.acs || (own(ACS, d.acs) ? d.acs : null), cancer_type: ctype, order: ord, n: nn, cosponsor: cosp, bill: cos ? cos.bill : (cosp ? 'ctma_hr' : null), rural: /\b(rural|nonmetro|non-metro)\b/.test(n) ? 'nonmetro' : /\b(metro|urban)\b/.test(n) ? 'metro' : null, places, threshold: readThreshold(n, metricRead) || (shape === 'count' || shape === 'threshold' ? defaultThreshold(n, metric) : null), need: readNeed(n, cancer), national: /\bnational/.test(n), level_note, source: 'model', corrections: p.corrections, flags: { states: codes, zips: zips.map(z => z.zip), order_words: order.words, cosponsor_words: cos ? cos.word : null, cancer_words: cancer ? cancer.word : null, level_words: level.word, metric_words: metricRead ? metricRead.word : null } };
  if (out.shape === 'need') { out.level = 'county'; out.need = out.need || { measure: 'inc', site: 'all', crit: 'l20', thr: 50 }; out.metric = out.need.measure === 'mort' ? 'mort' : 'inc'; out.site = out.need.site; }
  if (out.shape === 'lookup' && !out.places.length) { if (out.state) out.places = [{ kind: 'state', id: out.state, name: STATES[out.state], state: out.state }]; else out.places = [{ kind: 'national', id: 'US', name: 'United States' }]; out.level = out.places[0].kind; }
  if (out.shape === 'compare' && out.places.length < 2) out.shape = out.places.length ? 'lookup' : 'ranking';
  if (out.cosponsor && out.shape === 'ranking') out.level = 'district';
  if (out.shape === 'represents' && !out.places.length) out.shape = 'cosponsor';
  return out;
}
const key2 = s => norm(s).replace(/[^a-z0-9]/g, '');
export { SCOPE_RE, OTHER_RE };
