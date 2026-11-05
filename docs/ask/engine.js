/* Ask the map v3 — the data engine (ASK_CONTRACT.md §4, §5, §11).
   createEngine(options) builds the tables the model's tools read (counties, districts, states, national, nci_centers, facilities,
   senators, cosponsors) from the published API files plus the map's own data files, and runs the tools: find_places, query,
   aggregate, profile, compare, trials, site_info (final_answer is a no-op here). Every value a tool returns is read from a row or
   is a count/sum/mean of row values; nothing is reformatted. run() never throws: errors come back as {error, hint}.
   Loading: browser → options.globals (window.DATA, BURDEN, …) + options.fetchJSON(base + 'api/…'); Node → options.root (files on disk).
   No dependencies, no build step; plain ES module for Node 22 and modern browsers. */
import { TABLES, DEFAULT_COLUMNS, FILES, SOURCES, STATES, CANCER_TYPES, SITE_INFO, PHASES, SPONSOR_TYPES, SITE_BASE, UNIT_OF_TABLE, TYPE_KEYS_BY_TYPE_ACCESS, fieldFor, allPaths, groupableFields } from './catalog.js';
import { buildPlaceIndex, findPlaces, stateCode, editDistance } from './places.js';

const API_FILES = { counties: 'api/all_counties.json', districts: 'api/all_districts.json', states: 'api/all_states.json', national: 'api/national.json' };
const MAP_FILES = {   // key → [file under docs/, window global]
  data: ['data.js', 'DATA'], burden: ['burden.js', 'BURDEN'], mortality: ['mortality.js', 'MORTALITY'], oncologists: ['oncologists.js', 'ONCOLOGISTS'],
  rucc: ['rucc.js', 'RUCC'], cosponsors: ['cosponsors.js', 'COSPONSORS'], findings: ['findings.js', 'FINDINGS'], changes: ['changes.js', 'CHANGES'],
};
const STRIP = ['source', 'license', 'cite', 'methods', 'links', 'level', 'data_as_of'];
const OPS = ['=', '!=', '>', '>=', '<', '<=', 'in', 'not_in', 'is_null', 'not_null', 'contains', 'includes', 'intersects', 'between'];
const STATS = ['count', 'count_not_null', 'sum', 'mean', 'weighted_mean', 'median', 'min', 'max', 'share_true', 'share_eq'];
const TOOLS = ['find_places', 'query', 'aggregate', 'profile', 'compare', 'trials', 'site_info', 'final_answer'];
const RUCC_KEYS = { p: 'pop55', n: 'counties', l20: 'pct_lt20', z60: 'pct_zero', l100: 'pct_lt100', t60: 'mean_trials_60', g60n: 'pct_gt60rdmi_nci', g60b: 'pct_gt60rdmi_broad_menu', medn: 'median_road_mi_nci', medb: 'median_road_mi_broad_menu' };
const METRO_ALIASES = { people_lt20: 'people_lt20_trials_within_60rdmi', people_zero: 'people_zero_trials_within_60rdmi', pct_lt100: 'pct_lt100_trials_within_60rdmi', pct_lt20: 'pct_lt20_trials_within_60rdmi', pct_zero: 'pct_zero_trials_within_60rdmi', mean_trials_60: 'mean_trials_within_60rdmi' };
const AGG_NOTE = 'Computed by the engine across the matching rows; a mean of county rates is not the published state rate (use the states table for that).';
const TRIALS_NOTE = 'These are trials listed on ClinicalTrials.gov as recruiting with a site in scope; they are counted, not matched to anyone, and nothing here says a trial is available to a particular person.';
const TABLE_LABEL = { counties: 'Counties', districts: 'Districts', states: 'States', national: 'The national row', nci_centers: 'NCI centers', facilities: 'Trial sites', senators: 'Senators', cosponsors: 'Cosponsor records' };

const isNull = v => v === null || v === undefined;
const round1 = x => Math.round(x * 10) / 10;
const clone = x => JSON.parse(JSON.stringify(x));
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

// walks a dotted path; null when an intermediate is null, undefined when a key is missing (= not loaded for optional fields)
export function get(row, path) {
  let v = row;
  for (const p of String(path).split('.')) {
    if (v === null) return null;
    if (v === undefined || typeof v !== 'object' || !(p in v)) return undefined;
    v = v[p];
  }
  return v;
}
// loose equality the model can rely on: numbers vs numeric strings, booleans vs "true"/"false", case-insensitive strings
function eq(a, b) {
  if (isNull(a) || isNull(b)) return false;
  if (typeof a === 'number' && typeof b === 'string') return b.trim() !== '' && !Number.isNaN(+b) && a === +b;
  if (typeof a === 'string' && typeof b === 'number') return a.trim() !== '' && !Number.isNaN(+a) && +a === b;
  if (typeof a === 'boolean' && typeof b === 'string') return a === (b.trim().toLowerCase() === 'true');
  if (typeof a === 'string' && typeof b === 'string') return a.toLowerCase() === b.toLowerCase();
  return a === b;
}
// ordering for numbers, numeric strings, dates and plain strings; null when the two cannot be compared
function cmp(a, b) {
  if (isNull(a) || isNull(b)) return null;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  if (typeof a === 'number' && typeof b === 'string' && b.trim() !== '' && !Number.isNaN(+b)) return a - +b;
  if (typeof a === 'string' && typeof b === 'number' && a.trim() !== '' && !Number.isNaN(+a)) return +a - b;
  if (typeof a === 'boolean' && typeof b === 'boolean') return (a ? 1 : 0) - (b ? 1 : 0);
  if (typeof a === 'string' && typeof b === 'string') return a < b ? -1 : a > b ? 1 : 0;
  return null;
}
const tieBreak = (a, b) => ((b.pop55 || 0) - (a.pop55 || 0)) || String(a.name).localeCompare(String(b.name));

// ---------- the engine ----------
export function createEngine(options = {}) {
  const opt = { ...(options.sources || {}), ...options };
  const S = { api: {}, files: {}, tables: null, byId: {}, placeIx: null, calls: new Map(), loading: null, done: false, loaded: null, asOf: null, districtsOfCounty: new Map() };
  const progress = t => { try { if (typeof opt.onProgress === 'function') opt.onProgress(t); } catch (e) { /* progress is best effort */ } };

  // ---- loading ----
  // JSON file relative to docs/ (browser: fetchJSON(base + rel); Node: read from root/docs/rel); null when it cannot be read
  async function readJSON(rel, required) {
    try {
      if (opt.root) { const fs = await import('node:fs/promises'); const path = await import('node:path'); return JSON.parse(await fs.readFile(path.join(opt.root, 'docs', rel), 'utf8')); }
      if (typeof opt.fetchJSON === 'function') return await opt.fetchJSON((opt.base || '') + rel);
      throw new Error('no fetchJSON or root given');
    } catch (e) { if (required) throw new Error(`could not load ${rel}: ${e.message || e}`); return null; }
  }
  // a window.X = {...}; file: the browser has it as a global, Node slices the assignment off the file text
  async function readWindowFile(key) {
    const [file, global] = MAP_FILES[key];
    if (opt.globals && opt.globals[global]) return opt.globals[global];
    if (!opt.root) return null;
    try {
      const fs = await import('node:fs/promises'); const path = await import('node:path');
      const text = await fs.readFile(path.join(opt.root, 'docs', file), 'utf8');
      let body = text.slice(text.indexOf('=') + 1).trim();
      if (body.endsWith(';')) body = body.slice(0, -1);
      return JSON.parse(body);
    } catch (e) { return null; }
  }
  // loads and parses everything once; later calls return the same promise
  function load() {
    if (S.loading) return S.loading;
    S.loading = (async () => {
      progress('Loading the data files (first question only)…');
      for (const [t, rel] of Object.entries(API_FILES)) { progress(`Loading ${rel}…`); S.api[t] = await readJSON(rel, true); }
      for (const key of Object.keys(MAP_FILES)) S.files[key] = await readWindowFile(key);
      S.files.places = await readJSON('places.json', false);
      S.files.zips = await readJSON('zip_county.json', false);
      progress('Building the tables…');
      buildTables();
      S.placeIx = buildPlaceIndex({ counties: S.tables.counties, districts: S.tables.districts, states: S.tables.states, nci: S.tables.nci_centers, zips: S.files.zips, places: S.files.places });
      S.loaded = { counties: true, districts: true, states: true, national: true, places: !!S.files.places, zips: !!S.files.zips, optional: Object.fromEntries(Object.keys(MAP_FILES).map(k => [k, !!S.files[k]])) };
      S.done = true;
      progress('Data loaded.');
    })().catch(e => { S.loading = null; throw e; });
    return S.loading;
  }

  // ---- row building ----
  function buildTables() {
    const F = S.files;
    const api = { counties: Array.isArray(S.api.counties) ? S.api.counties : [], districts: Array.isArray(S.api.districts) ? S.api.districts : [], states: Array.isArray(S.api.states) ? S.api.states : [], national: S.api.national || {} };
    S.asOf = api.national.data_as_of || (api.counties[0] && api.counties[0].data_as_of) || null;
    for (const d of api.districts) for (const f of d.counties || []) { if (!S.districtsOfCounty.has(f)) S.districtsOfCounty.set(f, []); S.districtsOfCounty.get(f).push(d.id); }
    const countyName = new Map(api.counties.map(r => [r.id, r.name]));
    const countyState = new Map(api.counties.map(r => [r.id, r.state]));
    const T = {};
    T.counties = api.counties.map(r => buildCounty(r, F));
    T.districts = api.districts.map(r => buildDistrict(r, F, countyName));
    T.nci_centers = buildNci(F.data);
    T.states = api.states.map(r => buildState(r, F, T.nci_centers));
    T.national = [buildNational(api.national, F)];
    T.facilities = buildFacilities(F.data, countyName, countyState);
    T.senators = buildSenators(api.states, F.cosponsors);
    T.cosponsors = buildCosponsors(F.cosponsors);
    S.tables = T;
    for (const t of Object.keys(T)) S.byId[t] = new Map(T[t].map(r => [String(r.id), r]));
    S.byId.districtsByGeoid = new Map(T.districts.map(r => [String(r.geoid), r]));
  }
  // the API row minus boilerplate
  function strip(r) { const o = { ...r }; for (const k of STRIP) delete o[k]; return o; }
  // county: API row + districts, zero_trial_share_by_type, oncologists.per_100k_pop55, the two computed classifications, menu
  function buildCounty(r, F) {
    const o = strip(r);
    o.districts = Array.isArray(r.districts) && r.districts.length ? r.districts.slice() : (S.districtsOfCounty.get(r.id) || []).slice();
    if (F.burden) {
      const b = F.burden.county && F.burden.county[r.id];
      const types = (F.burden.meta && F.burden.meta.types) || TYPE_KEYS_BY_TYPE_ACCESS;
      o.zero_trial_share_by_type = b && Array.isArray(b.zt) ? Object.fromEntries(types.map((t, i) => [t, isNull(b.zt[i]) ? null : b.zt[i]])) : null;
    }
    o.oncologists = { ...(r.oncologists || {}) };
    const n = o.oncologists.count;
    o.oncologists.per_100k_pop55 = !isNull(n) && r.pop55 > 0 ? round1(n / r.pop55 * 100000) : null;
    const l20 = r.pct_lt20_trials_within_60rdmi;
    o.high_incidence_low_access = isNull(r.incidence_above_county_median) || isNull(l20) ? null : (r.incidence_above_county_median === true && l20 >= 50);
    o.high_deaths_low_access = isNull(r.mortality_top_third) || isNull(l20) ? null : (r.mortality_top_third === true && l20 >= 50);
    const t = r.trials_listed_here;
    o.menu = isNull(t) ? null : t >= 100 ? 'broad' : t >= 20 ? 'limited' : t >= 1 ? 'few' : 'none';
    return o;
  }
  // district: API row + member.bioguide / cosponsor_date / vacant, county_names, deaths_vs_access
  function buildDistrict(r, F, countyName) {
    const o = strip(r);
    const m = { ...(r.member || { name: null, party: null, ctma_hr3521: 'none' }) };
    m.vacant = !m.name;
    if (F.cosponsors) {
      const bio = (F.cosponsors.district_map || {})[r.geoid] || null;
      m.bioguide = bio;
      const rec = bio && F.cosponsors.by_member && F.cosponsors.by_member[bio] && F.cosponsors.by_member[bio].ctma_hr;
      m.cosponsor_date = rec && rec.date ? rec.date : null;
    }
    o.member = m;
    o.county_names = (r.counties || []).map(f => (countyName.get(f) || f).replace(/,\s*[^,]+$/, ''));
    if (F.mortality) {
      const d = F.mortality.summary && F.mortality.summary.districts && F.mortality.summary.districts[r.geoid];
      o.deaths_vs_access = d ? { counties_classified: isNull(d.classified) ? null : d.classified, high_death_low_access_counties: Array.isArray(d.hh) ? d.hh.length : null, ids: Array.isArray(d.hh) ? d.hh.slice() : null } : null;
    }
    return o;
  }
  // the metro / nonmetro objects carry long keys; the catalog names the short ones
  function metroAliases(obj) {
    if (!obj || typeof obj !== 'object') return obj;
    const o = { ...obj };
    for (const [short, long] of Object.entries(METRO_ALIASES)) if (!(short in o) && long in o) o[short] = o[long];
    return o;
  }
  // RUCC per-code objects: short keys → the catalog's measure names; every code 1–9 present (null when the place has none)
  function ruccCodes(codes) {
    const out = {};
    for (const c of ['1', '2', '3', '4', '5', '6', '7', '8', '9']) {
      const src = codes && codes[c];
      out[c] = src ? Object.fromEntries(Object.entries(RUCC_KEYS).map(([k, name]) => [name, isNull(src[k]) ? null : src[k]])) : null;
    }
    return out;
  }
  // state: API row + senators' dates and summary, DATA.state_data counts, NCI centers, need/deaths vs access, by_rucc
  function buildState(r, F, nci) {
    const o = strip(r);
    o.metro = metroAliases(r.metro); o.nonmetro = metroAliases(r.nonmetro);
    const sens = Array.isArray(r.senators) ? r.senators.map(s => ({ ...s })) : [];
    if (F.cosponsors) for (const s of sens) { const rec = s.bioguide && F.cosponsors.by_member && F.cosponsors.by_member[s.bioguide] && F.cosponsors.by_member[s.bioguide].ctma_s; s.cosponsor_date = rec && rec.date ? rec.date : null; }
    o.senators = sens;
    o.senator_names = sens.map(s => s.name);
    o.senators_s4440 = sens.length ? sens.map(s => `${s.name} (${s.party || '?'}): ${s.s4440 || 'none'}`).join('; ') : null;
    o.senators_cosponsoring_s4440 = sens.filter(s => s.s4440 && s.s4440 !== 'none').length;
    if (F.data && F.data.state_data && F.data.state_data[r.id]) {
      const sd = F.data.state_data[r.id];
      o.trials_distinct = sd.trials ?? null; o.counties = sd.counties ?? null; o.counties_with_trials = sd.counties_with_trials ?? null; o.broad_menu_counties = sd.broad ?? null; o.limited_menu_counties = sd.limited ?? null;
    }
    if (F.data) { const mine = nci.filter(c => c.state === r.id); o.nci_centers_count = mine.length; o.nci_center_names = mine.map(c => c.name); }
    if (F.burden) o.need_vs_access = needVsAccess(F.burden.summary && F.burden.summary.states && F.burden.summary.states[r.id]);
    if (F.mortality) o.deaths_vs_access = deathsVsAccess(F.mortality.summary && F.mortality.summary.states && F.mortality.summary.states[r.id]);
    if (F.rucc) o.by_rucc = ruccCodes(F.rucc.states && F.rucc.states[r.id] && F.rucc.states[r.id].codes);
    return o;
  }
  // BURDEN.summary.{states[st]|nat} → the catalog's need_vs_access object
  function needVsAccess(b) {
    if (!b) return null;
    return { counties_classified: b.counties_classified ?? null, high_incidence_low_access_counties: b.hb_la_counties ?? null, pop55: b.hb_la_pop55 ?? null, cases_per_year: b.hb_la_cases ?? null };
  }
  // MORTALITY.summary.{states[st]|nat} → the catalog's deaths_vs_access object
  function deathsVsAccess(m) {
    if (!m) return null;
    return { counties_classified: m.counties_classified ?? null, high_death_low_access_counties: m.hh_counties ?? null, pop55: m.hh_pop55 ?? null, deaths_per_year: m.hh_deaths ?? null };
  }
  // national: API row + published death rates by site, by_rucc, need/deaths vs access, states with no broad menu, history
  function buildNational(r, F) {
    const o = strip(r);
    o.metro = metroAliases(r.metro); o.nonmetro = metroAliases(r.nonmetro);
    if (F.mortality && F.mortality.meta && F.mortality.meta.us) o.mortality = { by_site: Object.fromEntries(Object.entries(F.mortality.meta.us).map(([k, v]) => [k, { rate: v && !isNull(v.rate) ? v.rate : null, deaths: v && !isNull(v.deaths) ? v.deaths : null }])) };
    if (F.rucc) o.by_rucc = ruccCodes(F.rucc.nat && F.rucc.nat.codes);
    if (F.burden) o.need_vs_access = needVsAccess(F.burden.summary && F.burden.summary.nat);
    if (F.mortality) o.deaths_vs_access = deathsVsAccess(F.mortality.summary && F.mortality.summary.nat);
    if (F.findings && Array.isArray(F.findings.states_no_broad_list)) o.states_with_no_broad_menu_county = F.findings.states_no_broad_list.map(n => stateCode(n) || n);
    if (F.changes && Array.isArray(F.changes.history)) o.history = F.changes.history.map(h => ({ pull: h.pull ?? null, trials: h.trials ?? null, pct_lt20: h.l20 ?? null, pct_zero: h.z60 ?? null, pct_gt60_broad: h.g60b ?? null, pct_gt60_nci: h.g60n ?? null, median_road_mi_nci: h.medn ?? null }));
    return o;
  }
  function buildNci(data) {
    if (!data || !Array.isArray(data.nci)) return [];
    return data.nci.map((c, i) => ({ id: `nci:${i}`, name: c.n, full_name: c.full, state: c.st, tier: c.tier, lat: c.lat, lon: c.lon }));
  }
  // DATA.counties[f].fac = [name, city, zip, [trial idx], site_id, unresolved]
  function buildFacilities(data, countyName, countyState) {
    if (!data || !data.counties) return [];
    const out = [];
    for (const [f, c] of Object.entries(data.counties)) {
      for (const fa of c.fac || []) out.push({ id: `fac:${fa[4]}`, name: fa[0], city: fa[1], zip: fa[2], county_id: f, county_name: countyName.get(f) || c.nl || f, state: countyState.get(f) || null, trials: Array.isArray(fa[3]) ? fa[3].length : 0, unresolved: !!fa[5] });
    }
    return out;
  }
  function buildSenators(states, cos) {
    const out = [];
    for (const st of states) for (const s of st.senators || []) {
      const rec = cos && s.bioguide && cos.by_member && cos.by_member[s.bioguide] && cos.by_member[s.bioguide].ctma_s;
      out.push({ id: s.bioguide || `${st.id}:${s.name}`, name: s.name, party: s.party || null, state: st.id, s4440: s.s4440 || 'none', cosponsor_date: cos ? (rec && rec.date ? rec.date : null) : undefined });
    }
    return out;
  }
  // COSPONSORS.by_member × members × bills → one row per member per bill
  function buildCosponsors(cos) {
    if (!cos || !cos.by_member) return [];
    const out = [];
    for (const [bio, bills] of Object.entries(cos.by_member)) {
      const m = (cos.members || {})[bio] || {};
      for (const [bill, rec] of Object.entries(bills || {})) {
        const b = (cos.bills || {})[bill] || {};
        const house = m.chamber !== 'sen';
        const district_id = house && m.state ? `${m.state}-${String(m.district || 0).padStart(2, '0')}` : null;
        out.push({ id: `${bio}:${bill}`, name: m.name || bio, party: m.party || null, state: m.state || null, chamber: house ? 'house' : 'senate', district_id, bill, bill_label: b.label || bill, role: rec.role || null, date: rec.date || null });
      }
    }
    return out;
  }

  // ---- shared helpers ----
  const ready = () => S.done && S.tables;
  function tableOf(name) {
    if (!name || !TABLES[name]) return { error: `unknown table '${name}'`, hint: 'tables: ' + Object.keys(TABLES).join(', ') };
    return { table: name };
  }
  const hasField = (table, path) => !!fieldFor(table, path);
  // up to 12 field names close to a wrong one: substring matches first, then edit distance
  function nearestFields(table, path) {
    const p = String(path).toLowerCase(); const last = p.split('.').pop();
    const scored = allPaths(table).map(f => {
      const fl = f.toLowerCase(); const fLast = fl.split('.').pop();
      let s = 100;
      if (fl === p) s = 0; else if (fl.includes(p) || p.includes(fl)) s = 1; else if (fLast.includes(last) || last.includes(fLast)) s = 2;
      else s = 3 + Math.min(editDistance(fLast, last, 6), editDistance(fl, p, 6));
      return [s, f];
    }).filter(x => x[0] < 9).sort((a, b) => a[0] - b[0] || a[1].localeCompare(b[1]));
    return scored.slice(0, 12).map(x => x[1]);
  }
  function unknownField(table, path) {
    const near = nearestFields(table, path);
    return { error: `unknown field '${path}' in table '${table}'`, hint: (near.length ? `did you mean ${near[0]}? ` : '') + 'Fields: ' + (near.length ? near : allPaths(table).slice(0, 12)).join(', ') };
  }
  // state names and demonyms → USPS in condition values on state fields
  function normStateValue(v) { if (Array.isArray(v)) return v.map(normStateValue); if (typeof v === 'string') return stateCode(v) || v; return v; }
  const isStateField = (table, field) => field === 'state' || (table === 'states' && (field === 'id'));
  // the value a condition compares against, for one row ({field: path} reads the other field)
  function condValue(row, c) { return c.ref ? get(row, c.ref) : c.value; }
  // does one row satisfy one condition
  function testCond(row, c) {
    const v = get(row, c.field);
    const x = condValue(row, c);
    switch (c.op) {
      case 'is_null': return isNull(v);
      case 'not_null': return !isNull(v);
      case '=': return eq(v, x);
      case '!=': return !isNull(v) && !isNull(x) && !eq(v, x);
      case '>': case '>=': case '<': case '<=': { const d = cmp(v, x); if (d === null) return false; return c.op === '>' ? d > 0 : c.op === '>=' ? d >= 0 : c.op === '<' ? d < 0 : d <= 0; }
      case 'in': return Array.isArray(x) && x.some(y => eq(v, y));
      case 'not_in': return !isNull(v) && Array.isArray(x) && !x.some(y => eq(v, y));
      case 'contains': { if (isNull(x)) return false; const s = String(x).toLowerCase(); if (typeof v === 'string') return v.toLowerCase().includes(s); if (Array.isArray(v)) return v.some(e => String(e).toLowerCase().includes(s)); return false; }
      case 'includes': return Array.isArray(v) && v.some(e => eq(e, x));
      case 'intersects': return Array.isArray(v) && Array.isArray(x) && x.some(y => v.some(e => eq(e, y)));
      case 'between': { if (!Array.isArray(x) || x.length !== 2) return false; const lo = cmp(v, x[0]), hi = cmp(v, x[1]); return lo !== null && hi !== null && lo >= 0 && hi <= 0; }
      default: return false;
    }
  }
  const testNode = (row, n) => n.any_of ? n.any_of.some(m => testNode(row, m)) : testCond(row, n);
  // validates `where`; returns {conds (tree), scope (top-level state conditions), fields, warnings} or {error}
  function parseWhere(table, where) {
    const out = { conds: [], scope: [], fields: [], warnings: [] };
    if (where === undefined || where === null) return out;
    if (!Array.isArray(where) && where && typeof where === 'object' && ('field' in where || 'any_of' in where)) where = [where];   // a single condition is accepted
    if (!Array.isArray(where)) return { error: '`where` must be an array of conditions', hint: 'e.g. where: [{field:"state", op:"=", value:"TX"}]' };
    const parseNode = (n, depth) => {
      if (!n || typeof n !== 'object') return { error: 'each condition must be an object {field, op, value}' };
      if (Array.isArray(n.any_of)) { if (depth > 2) return { error: 'any_of nested too deeply' }; const kids = []; for (const k of n.any_of) { const r = parseNode(k, depth + 1); if (r.error) return r; kids.push(r); } return { any_of: kids }; }
      const field = String(n.field || '');
      if (!hasField(table, field)) return unknownField(table, field);
      let op = n.op === '==' ? '=' : n.op;
      if (!OPS.includes(op)) return { error: `unknown op '${n.op}'`, hint: 'ops: ' + OPS.join(' ') };
      if (n.value === null && (op === '=' || op === '!=')) op = op === '=' ? 'is_null' : 'not_null';   // "= null" means is_null (comparisons never match null)
      const c = { field, op };
      out.fields.push(field);
      if (op === 'is_null' || op === 'not_null') return c;
      if (n.value && typeof n.value === 'object' && !Array.isArray(n.value) && 'field' in n.value) { const ref = String(n.value.field); if (!hasField(table, ref)) return unknownField(table, ref); c.ref = ref; out.fields.push(ref); return c; }
      if (n.value === undefined) return { error: `condition on '${field}' with op '${op}' needs a value` };
      let value = n.value;
      if (['in', 'not_in', 'intersects'].includes(op) && !Array.isArray(value)) value = [value];
      if (op === 'between' && !(Array.isArray(value) && value.length === 2)) return { error: `'between' needs value: [lo, hi]` };
      if (isStateField(table, field)) value = normStateValue(value);
      const fd = fieldFor(table, field);
      if (fd && fd.enum && ['=', '!=', 'in', 'not_in', 'includes'].includes(op)) {   // a value outside the enumeration is a warning, not an error
        const bad = (Array.isArray(value) ? value : [value]).filter(x => !fd.enum.some(e => eq(e, x) || e === x));
        if (bad.length) out.warnings.push(`'${bad.join("', '")}' is not a value of ${field}; its values are ${fd.enum.map(e => e === null ? 'null' : e).join(', ')}`);
      }
      c.value = value;
      return c;
    };
    for (const n of where) {
      const r = parseNode(n, 0);
      if (r.error) return r;
      out.conds.push(r);
      if (!r.any_of && isStateField(table, r.field) && !r.ref && ['=', 'in'].includes(r.op)) out.scope.push(r);
    }
    out.fields = [...new Set(out.fields)];
    return out;
  }
  function parseOrder(table, order_by) {
    const out = { keys: [], fields: [] };
    if (order_by === undefined || order_by === null) return out;
    const list = Array.isArray(order_by) ? order_by : [order_by];
    for (const o of list) {
      const field = typeof o === 'string' ? o : o && o.field;
      if (!hasField(table, String(field || ''))) return unknownField(table, field);
      const dir = o && o.dir && String(o.dir).toLowerCase() === 'asc' ? 'asc' : 'desc';
      out.keys.push({ field: String(field), dir }); out.fields.push(String(field));
    }
    return out;
  }
  function parseColumns(table, columns) {
    if (columns === undefined || columns === null) return { list: null };
    const list = Array.isArray(columns) ? columns : [columns];
    for (const c of list) if (!hasField(table, String(c))) return unknownField(table, c);
    return { list: list.map(String) };
  }
  const baseColumns = t => ['id', 'name', ...(hasField(t, 'state') ? ['state'] : []), ...(hasField(t, 'pop55') ? ['pop55'] : []), ...(t === 'districts' ? ['geoid'] : [])];
  // the columns a result carries: id/name/state/pop55(/geoid), then the requested or default set, then every filtered/sorted field
  function finalColumns(table, requested, extra) {
    const base = baseColumns(table);
    const want = [...(requested || DEFAULT_COLUMNS[table] || []), ...extra];
    const out = [...base];
    for (const c of want) if (!out.includes(c)) out.push(c);
    return out;
  }
  // one output row: dotted paths as keys; "not loaded" when the field's file is absent (a missing key; null stays null)
  function flatten(table, row, columns) {
    const o = {};
    for (const c of columns) { const v = get(row, c); o[c] = v === undefined ? 'not loaded' : v; }
    return o;
  }
  function sortRows(rows, keys) {
    rows.sort((a, b) => {
      for (const { field, dir } of keys) {
        const va = get(a, field), vb = get(b, field);
        const na = isNull(va), nb = isNull(vb);
        if (na && nb) continue; if (na) return 1; if (nb) return -1;
        const d = cmp(va, vb); if (d) return dir === 'desc' ? -d : d;
      }
      return tieBreak(a, b);
    });
  }
  const clampLimit = (v, dflt, max) => { const n = Math.floor(+v); return Number.isFinite(n) && n >= 1 ? Math.min(n, max) : dflt; };
  function sourceOf(table) {
    const f = FILES[table] || {};
    const file = f.file || null;
    const url = !file ? null : SITE_BASE + file.replace(/\s.*$/, '');   // "api/all_states.json (senators) + cosponsors.js" → the first file
    const asOf = table === 'cosponsors' || table === 'senators' ? ((S.files.cosponsors && S.files.cosponsors.meta && S.files.cosponsors.meta.fetched) || S.asOf) : table === 'nci_centers' ? SOURCES.nci.vintage : S.asOf;
    return { file, url, as_of: asOf };
  }
  const sumPop = rows => rows.reduce((s, r) => s + (typeof r.pop55 === 'number' ? r.pop55 : 0), 0);
  const remember = (callId, rec) => { if (callId) S.calls.set(String(callId), rec); };

  // resolves an id as the model may write it: FIPS with or without leading zero, district id or geoid, state name or USPS
  function resolveRow(table, id) {
    if (isNull(id)) return null;
    let s = String(id).trim();
    const m = S.byId[table];
    if (m.has(s)) return m.get(s);
    if (table === 'counties' && /^\d{1,5}$/.test(s)) return m.get(s.padStart(5, '0')) || null;
    if (table === 'districts') {
      const u = s.toUpperCase().replace(/\s+/g, '-');
      if (m.has(u)) return m.get(u);
      if (S.byId.districtsByGeoid.has(s)) return S.byId.districtsByGeoid.get(s);
      const mm = u.match(/^([A-Z]{2})-?(\d{1,2})$/);
      if (mm) return m.get(`${mm[1]}-${mm[2].padStart(2, '0')}`) || null;
      if (/^([A-Z]{2})-(AL)$/.test(u)) return m.get(u.slice(0, 2) + '-00') || null;
      return null;
    }
    if (table === 'states') { const u = stateCode(s); return u ? m.get(u) || null : null; }
    if (table === 'national') return S.tables.national[0];
    if (table === 'nci_centers' && /^\d+$/.test(s)) return m.get('nci:' + s) || null;
    if (table === 'facilities' && !s.startsWith('fac:')) return m.get('fac:' + s) || null;
    if (table === 'senators') return S.tables.senators.find(r => r.name.toLowerCase() === s.toLowerCase()) || null;
    return null;
  }

  // ---- query ----
  function runQuery(input, callId) {
    const t = tableOf(input.table); if (t.error) return t;
    const table = t.table; const rows = S.tables[table];
    const where = parseWhere(table, input.where); if (where.error) return where;
    const order = parseOrder(table, input.order_by); if (order.error) return order;
    const cols = parseColumns(table, input.columns); if (cols.error) return cols;
    const limit = clampLimit(input.limit, 20, 50);
    const scope = rows.filter(r => where.scope.every(c => testCond(r, c)));
    const matching = scope.filter(r => where.conds.every(n => testNode(r, n)));
    sortRows(matching, order.keys);
    const columns = finalColumns(table, cols.list, [...where.fields, ...order.fields]);
    const all = matching.map(r => flatten(table, r, columns));
    const out = all.slice(0, limit);
    const nulls = {};
    for (const f of new Set([...where.fields, ...order.fields])) nulls[f] = scope.filter(r => isNull(get(r, f))).length;
    // filtered = a condition beyond the state scope; a ranking (ordered, unfiltered) outlines the rows returned, a filter outlines every match
    remember(callId, { ids: matching.map(r => r.id), returned_ids: out.map(r => r.id), filtered: where.conds.length > where.scope.length, ordered: order.keys.length > 0, unit: UNIT_OF_TABLE[table] || null, rows: all, columns });
    const res = { table, count: matching.length, in_scope: scope.length, returned: out.length, columns, rows: out, nulls, ids_truncated: matching.length > out.length, sum_pop55_matching: hasField(table, 'pop55') ? sumPop(matching) : null, source: sourceOf(table) };
    if (where.warnings.length) res.warnings = where.warnings;
    return res;
  }

  // ---- aggregate ----
  function median(vals) { const v = vals.slice().sort((a, b) => a - b); const n = v.length; if (!n) return null; return n % 2 ? v[(n - 1) / 2] : (v[n / 2 - 1] + v[n / 2]) / 2; }
  // one statistic over the rows of a group
  function stat(rows, m) {
    const vals = m.field ? rows.map(r => get(r, m.field)) : [];
    const nums = vals.filter(v => typeof v === 'number' && !Number.isNaN(v));
    switch (m.stat) {
      case 'count': return rows.length;
      case 'count_not_null': return vals.filter(v => !isNull(v)).length;
      case 'sum': { if (!nums.length) return null; const s = nums.reduce((a, b) => a + b, 0); return Number.isInteger(s) ? s : round1(s); }
      case 'mean': return nums.length ? round1(nums.reduce((a, b) => a + b, 0) / nums.length) : null;
      case 'weighted_mean': { let num = 0, den = 0; for (const r of rows) { const v = get(r, m.field), w = get(r, m.weight); if (typeof v === 'number' && typeof w === 'number' && w > 0) { num += v * w; den += w; } } return den > 0 ? round1(num / den) : null; }
      case 'median': return median(nums);
      case 'min': return nums.length ? Math.min(...nums) : null;
      case 'max': return nums.length ? Math.max(...nums) : null;
      case 'share_true': { const nn = vals.filter(v => !isNull(v)); return nn.length ? round1(nn.filter(v => v === true).length / nn.length * 100) : null; }
      case 'share_eq': { const nn = vals.filter(v => !isNull(v)); return nn.length ? round1(nn.filter(v => eq(v, m.value)).length / nn.length * 100) : null; }
      default: return null;
    }
  }
  function runAggregate(input) {
    const t = tableOf(input.table); if (t.error) return t;
    const table = t.table; const rows = S.tables[table];
    const where = parseWhere(table, input.where); if (where.error) return where;
    let groupBy = null;
    if (!isNull(input.group_by) && input.group_by !== '') {
      groupBy = String(input.group_by);
      if (!hasField(table, groupBy)) return unknownField(table, groupBy);
      const ok = groupableFields(table);
      if (!ok.includes(groupBy)) return { error: `'${groupBy}' is not a groupable field of '${table}'`, hint: 'group_by accepts: ' + ok.join(', ') };
    }
    const measures = Array.isArray(input.measures) ? input.measures : input.measures ? [input.measures] : [];
    if (!measures.length) return { error: 'aggregate needs measures: [{field, stat}]', hint: 'stats: ' + STATS.join(', ') };
    const ms = [];
    for (const m of measures) {
      if (!m || typeof m !== 'object') return { error: 'each measure is {field, stat}' };
      const st = String(m.stat || '');
      if (!STATS.includes(st)) return { error: `unknown stat '${m.stat}'`, hint: 'stats: ' + STATS.join(', ') };
      const field = m.field ? String(m.field) : null;
      if (st !== 'count' && !field) return { error: `stat '${st}' needs a field` };
      if (field && !hasField(table, field)) return unknownField(table, field);
      const weight = st === 'weighted_mean' ? String(m.weight || 'pop55') : null;
      if (weight && !hasField(table, weight)) return unknownField(table, weight);
      if (st === 'share_eq' && m.value === undefined) return { error: `share_eq needs a value` };
      ms.push({ field, stat: st, weight, value: m.value, key: `${field || '*'}:${st}` });
    }
    const scope = rows.filter(r => where.scope.every(c => testCond(r, c)));
    const matching = scope.filter(r => where.conds.every(n => testNode(r, n)));
    const groups = new Map();
    for (const r of matching) { const g = groupBy ? get(r, groupBy) : null; const k = isNull(g) ? '\u0000null' : typeof g + ':' + String(g); if (!groups.has(k)) groups.set(k, { group: isNull(g) ? null : g, rows: [] }); groups.get(k).rows.push(r); }
    const out = [...groups.values()].sort((a, b) => { const na = isNull(a.group), nb = isNull(b.group); if (na && nb) return 0; if (na) return 1; if (nb) return -1; return cmp(a.group, b.group) || 0; })
      .map(g => ({ group: g.group, n: g.rows.length, sum_pop55: hasField(table, 'pop55') ? sumPop(g.rows) : null, measures: Object.fromEntries(ms.map(m => [m.key, stat(g.rows, m)])) }));
    const res = { table, count: matching.length, in_scope: scope.length, group_by: groupBy, groups: out, note: AGG_NOTE, source: sourceOf(table) };
    if (where.warnings.length) res.warnings = where.warnings;
    return res;
  }

  // ---- profile ----
  // the four headline figures of a place, for `related`
  const headline = r => !r ? null : {
    id: r.id, name: r.name, pct_lt20_trials_within_60rdmi: r.pct_lt20_trials_within_60rdmi ?? null, pct_zero_trials_within_60rdmi: r.pct_zero_trials_within_60rdmi ?? null,
    median_road_mi_nci: r.median_road_mi_nci ?? null, wmean_trials_within_60rdmi: r.wmean_trials_within_60rdmi ?? null,
  };
  const senatorsOf = st => { const s = S.byId.states.get(st); return s ? (s.senators || []).map(x => ({ name: x.name, party: x.party || null, s4440: x.s4440 || 'none', cosponsor_date: x.cosponsor_date === undefined ? 'not loaded' : x.cosponsor_date })) : []; };
  // what sits around a row: districts/senators/state/national for a county, counties/member/senators for a district, …
  function relatedFor(table, row) {
    if (table === 'counties') {
      const ds = (row.districts || []).map(id => S.byId.districts.get(id)).filter(Boolean).map(d => ({ id: d.id, name: d.name, member: d.member.name, party: d.member.party, ctma_hr3521: d.member.ctma_hr3521, vacant: d.member.vacant }));
      return { districts: ds, senators: senatorsOf(row.state), state_row_headline: headline(S.byId.states.get(row.state)), national_headline: headline(S.tables.national[0]) };
    }
    if (table === 'districts') {
      const cs = (row.counties || []).map(f => S.byId.counties.get(f)).filter(Boolean).map(c => ({ id: c.id, name: c.name, pop55: c.pop55 }));
      return { counties: cs, member: { ...row.member }, senators: senatorsOf(row.state), state_row_headline: headline(S.byId.states.get(row.state)) };
    }
    if (table === 'states') return { senators: senatorsOf(row.id), nci_centers: S.tables.nci_centers.filter(c => c.state === row.id).map(c => c.name), metro_nonmetro: { metro: row.metro || null, nonmetro: row.nonmetro || null }, national_headline: headline(S.tables.national[0]) };
    if (table === 'facilities') { const c = S.byId.counties.get(row.county_id); return { county: headline(c) }; }
    if (table === 'senators') return { state_row_headline: headline(S.byId.states.get(row.state)) };
    if (table === 'cosponsors') return row.district_id ? { district: (d => d ? { id: d.id, name: d.name, pop55: d.pop55 } : null)(S.byId.districts.get(row.district_id)) } : { state_row_headline: headline(S.byId.states.get(row.state)) };
    return {};
  }
  function runProfile(input, callId) {
    const t = tableOf(input.table); if (t.error) return t;
    const table = t.table;
    const row = resolveRow(table, table === 'national' && isNull(input.id) ? 'US' : input.id);
    if (!row) return { error: `no row '${input.id}' in table '${table}'`, hint: `ids are ${TABLES[table].id_desc}; use find_places to resolve a name` };
    const notLoaded = TABLES[table].fields.filter(fd => get(row, fd.path.split('.<')[0]) === undefined).map(fd => fd.path);
    const columns = finalColumns(table, null, []);
    remember(callId, { ids: [row.id], unit: UNIT_OF_TABLE[table] || null, rows: [flatten(table, row, columns)], columns });
    const res = { table, id: row.id, name: row.name, row: clone(row), related: relatedFor(table, row), source: sourceOf(table) };
    if (notLoaded.length) res.not_loaded = [...new Set(notLoaded)];
    return res;
  }

  // ---- compare ----
  function runCompare(input, callId) {
    const t = tableOf(input.table); if (t.error) return t;
    const table = t.table;
    const ids = Array.isArray(input.ids) ? input.ids : [];
    if (ids.length < 2 || ids.length > 6) return { error: 'compare needs 2 to 6 ids', hint: `ids are ${TABLES[table].id_desc}` };
    const cols = parseColumns(table, input.columns); if (cols.error) return cols;
    const rows = []; const missing = [];
    for (const id of ids) { const r = resolveRow(table, id); if (r) rows.push(r); else missing.push(String(id)); }
    if (missing.length) return { error: `unknown id${missing.length > 1 ? 's' : ''} in table '${table}': ${missing.join(', ')}`, hint: 'use find_places to resolve names to ids' };
    const columns = finalColumns(table, cols.list ? [...(DEFAULT_COLUMNS[table] || []), ...cols.list] : null, []);
    const out = rows.map(r => flatten(table, r, columns));
    const reference = [];
    const refRows = (refTable, list) => { const rc = columns.filter(c => hasField(refTable, c)); for (const r of list) reference.push({ table: refTable, ...flatten(refTable, r, rc) }); };
    if (table === 'counties' || table === 'districts') refRows('states', [...new Set(rows.map(r => r.state))].map(s => S.byId.states.get(s)).filter(Boolean));
    if (table === 'counties' || table === 'districts' || table === 'states') refRows('national', S.tables.national);
    remember(callId, { ids: rows.map(r => r.id), unit: UNIT_OF_TABLE[table] || null, rows: out, columns });
    return { table, columns, rows: out, reference, source: sourceOf(table) };
  }

  // ---- trials ----
  // the trial indices in scope and a description of the scope; {error} when the scope is not usable
  function trialScope(scope) {
    const D = S.files.data;
    const county = f => { const r = resolveRow('counties', f); return r ? { row: r, c: D.counties[r.id] } : null; };
    if (typeof scope === 'string' || typeof scope === 'number') { const t = String(scope).trim(); scope = /^\d{1,5}$/.test(t) ? { county_id: t } : /^(us|usa|national|united states)$/i.test(t) ? { national: true } : { state: t }; }   // a bare id is read as the obvious scope
    if (!scope || typeof scope !== 'object') return { error: 'trials needs a scope', hint: 'scope: {county_id} | {within_60_of_county_id} | {state} | {national: true}' };
    const noCounty = id => ({ error: `unknown county '${id}'`, hint: 'use find_places to get the 5-digit FIPS' });
    if (scope.county_id !== undefined) {   // trials with a site in the county: DATA.counties[f].tr
      const h = county(scope.county_id); if (!h) return noCounty(scope.county_id);
      return { kind: 'county', id: h.row.id, name: h.row.name, state: h.row.state, idx: (h.c && h.c.tr) || [], text: `with a site in ${h.row.name}`, link: `trials.html?county=${h.row.id}` };
    }
    if (scope.within_60_of_county_id !== undefined) {   // the map's t60: the union of SP over the site points within 60 road-miles of the center
      const h = county(scope.within_60_of_county_id); if (!h) return noCounty(scope.within_60_of_county_id);
      const set = new Set();
      for (const s of (h.c && h.c.nb) || []) for (const j of D.SP[s] || []) set.add(j);
      return { kind: 'within_60', id: h.row.id, name: h.row.name, state: h.row.state, idx: [...set], text: `with a site within 60 road-miles of the ${h.row.name} population center`, link: `map.html?c=${h.row.id}` };
    }
    if (scope.state !== undefined) {   // the union of tr over the state's counties (= DATA.state_data[st].trials)
      const u = stateCode(scope.state);
      if (!u || !S.byId.states.has(u)) return { error: `unknown state '${scope.state}'`, hint: 'use a USPS code or a state name' };
      const fips = S.byId.states.get(u).fips; const set = new Set();
      for (const [f, c] of Object.entries(D.counties)) if (f.startsWith(fips)) for (const j of c.tr || []) set.add(j);
      return { kind: 'state', id: u, name: STATES[u], state: u, idx: [...set], text: `with a site in ${STATES[u]}`, link: 'find.html' };
    }
    if (scope.national) return { kind: 'national', id: 'US', name: 'United States', state: null, idx: D.T.id.map((_, j) => j), text: 'with a US site (all listed trials)', link: 'find.html' };
    return { error: 'scope must be one of {county_id}, {within_60_of_county_id}, {state}, {national: true}' };
  }
  function runTrials(input) {
    const D = S.files.data;
    if (!D || !D.T || !D.counties) return { error: 'the trial list (data.js) is not loaded', hint: 'trial-level questions need the map page; county, district and state tables still answer counts (trials_listed_here, wmean_trials_within_60rdmi)' };
    const T = D.T;
    const sc = trialScope(input.scope); if (sc.error) return sc;
    const filters = {};
    let typeIdx = -1;
    if (!isNull(input.cancer_type) && input.cancer_type !== '') { const k = String(input.cancer_type).trim().toLowerCase(); typeIdx = T.types.findIndex(x => x[0] === k); if (typeIdx < 0) return { error: `unknown cancer_type '${input.cancer_type}'`, hint: 'types: ' + Object.keys(CANCER_TYPES).join(', ') }; filters.cancer_type = k; }
    if (!isNull(input.phase) && input.phase !== '') { const p = String(input.phase).trim().replace(/^phase\s*/i, '').replace(/\//, '-').toUpperCase(); if (!PHASES.includes(p)) return { error: `unknown phase '${input.phase}'`, hint: 'phases: ' + PHASES.join(', ') }; filters.phase = p; }
    if (!isNull(input.sponsor_type) && input.sponsor_type !== '') { const s = String(input.sponsor_type).trim().toLowerCase(); if (!SPONSOR_TYPES[s]) return { error: `unknown sponsor_type '${input.sponsor_type}'`, hint: 'sponsor types: ' + Object.keys(SPONSOR_TYPES).join(', ') }; filters.sponsor_type = s; }
    if (!isNull(input.keyword) && String(input.keyword).trim() !== '') filters.keyword = String(input.keyword).trim().toLowerCase();
    if (!isNull(input.min_age_at_most) && input.min_age_at_most !== '') { const a = +input.min_age_at_most; if (!Number.isFinite(a)) return { error: 'min_age_at_most must be a number' }; filters.min_age_at_most = a; }
    const limit = clampLimit(input.limit, 10, 25);
    const bucket = filters.cancer_type === 'multi' || filters.cancer_type === 'other_unclassified';   // the finder's rule: the two catch-all buckets match the primary category only
    const pass = j => (typeIdx < 0 || (bucket ? T.ct[j] === typeIdx : (T.cats[j] || []).includes(typeIdx))) && (!filters.phase || T.phases[T.ph[j]] === filters.phase) && (!filters.sponsor_type || T.sponsors[T.sp[j]][0] === filters.sponsor_type)
      && (!filters.keyword || `${T.title[j]} ${T.iv[j]} ${T.kw[j]}`.toLowerCase().includes(filters.keyword)) && (filters.min_age_at_most === undefined || T.amin[j] === null || T.amin[j] <= filters.min_age_at_most);
    const hits = sc.idx.filter(pass);
    const byPhase = Object.fromEntries(PHASES.map(p => [p, 0])); const bySp = Object.fromEntries(Object.keys(SPONSOR_TYPES).map(k => [k, 0])); const byType = new Map();
    for (const j of hits) { byPhase[T.phases[T.ph[j]]]++; bySp[T.sponsors[T.sp[j]][0]]++; for (const ci of T.cats[j] || []) { const k = T.types[ci][0]; byType.set(k, (byType.get(k) || 0) + 1); } }
    const byTypeOut = [...byType.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 10).map(([k, n]) => ({ type: k, label: CANCER_TYPES[k] || k, count: n }));
    const sample = hits.slice().sort((a, b) => String(T.upd[b]).localeCompare(String(T.upd[a])) || String(T.id[a]).localeCompare(String(T.id[b]))).slice(0, limit)
      .map(j => ({ nct: T.id[j], title: T.title[j], phase: T.phases[T.ph[j]], sponsor: T.spn[j], sponsor_type: T.sponsors[T.sp[j]][0], cancer_types: (T.cats[j] || []).map(ci => T.types[ci][0]), start: T.start[j], last_update: T.upd[j] }));
    const link = SITE_BASE + sc.link + (filters.cancer_type ? (sc.link.includes('?') ? '&' : '?') + 'type=' + filters.cancer_type : '');
    return {
      scope: { kind: sc.kind, id: sc.id, name: sc.name, state: sc.state, text: sc.text }, filters, count: hits.length, in_scope_before_filters: sc.idx.length,
      by_phase: byPhase, by_sponsor_type: bySp, by_cancer_type: byTypeOut, sample, returned: sample.length, link, note: TRIALS_NOTE,
      source: { file: FILES.trials.file, url: SITE_BASE + 'data.js', as_of: S.asOf },
    };
  }

  // ---- site_info ----
  // the numbers behind a site_info topic, read from the loaded files at call time (null when the topic has none)
  function siteNumbers(topic) {
    const F = S.files; const nat = S.tables.national[0];
    switch (topic) {
      case 'bills': return { bills: billNumbers(F.cosponsors), fetched: F.cosponsors && F.cosponsors.meta ? F.cosponsors.meta.fetched : null };
      case 'findings': return findingsNumbers(F.findings);
      case 'history': return F.changes ? { history: nat.history || F.changes.history, summary: F.changes.summary } : null;
      case 'changes': return changesNumbers(F.changes);
      case 'rural': return { headline: F.rucc && F.rucc.meta ? F.rucc.meta.headline : null, metro: nat.metro, nonmetro: nat.nonmetro, nonmetro_pct: nat.nonmetro_pct };
      case 'need_vs_access': return F.burden ? { nat: F.burden.summary && F.burden.summary.nat, median_incidence_all_sites: F.burden.meta && F.burden.meta.median_all, definition: F.burden.meta && F.burden.meta.definition } : null;
      case 'deaths_vs_access': return F.mortality ? { nat: F.mortality.summary && F.mortality.summary.nat, tertiles_all_sites: F.mortality.meta && F.mortality.meta.tertiles && F.mortality.meta.tertiles.all, us_by_site: nat.mortality ? nat.mortality.by_site : null } : null;
      case 'oncologists': return F.oncologists ? { nat: F.oncologists.nat, source_modified: F.oncologists.meta && F.oncologists.meta.source_modified, pulled: F.oncologists.meta && F.oncologists.meta.pulled } : { nat: nat.oncologists };
      case 'sources': return { vintages: vintages(), files: Object.fromEntries(Object.entries(FILES).map(([k, f]) => [k, f.file])) };
      default: return null;
    }
  }
  // COSPONSORS.bills → introduced, cosponsor counts, parties, latest action, urls, sponsor name
  function billNumbers(cos) {
    if (!cos || !cos.bills) return null;
    const out = {};
    for (const [k, b] of Object.entries(cos.bills)) {
      const sponsor = (cos.members && cos.members[b.sponsor] && cos.members[b.sponsor].name) || b.sponsor;
      out[k] = { label: b.label, introduced: b.introduced, n_cosponsors: b.n_cosponsors, n_original: b.n_original, parties: b.parties, latest_action: b.latest_action, sponsor, url: b.url, cosponsors_url: b.cosponsors_url };
    }
    return out;
  }
  // FINDINGS → the national headline block, the no-broad-menu states and the district counts
  function findingsNumbers(F) {
    if (!F) return null;
    const d = F.districts || null; const m = F.meta || null;
    return {
      nat: F.nat, states_no_broad: F.states_no_broad, states_no_broad_list: F.states_no_broad_list,
      districts: d ? { n: d.n, all_beyond_60_broad: d.all_beyond_60_broad, half_lt20: d.half_lt20, worst: d.worst } : null,
      meta: m ? { pull: m.pull, trials: m.trials, facilities: m.facilities, n_tracts: m.n_tracts, n_nci: m.n_nci, nci_centers: m.nci_centers } : null,
    };
  }
  // CHANGES → the week's summary and short lists (capped at 12 each)
  function changesNumbers(C) {
    if (!C) return null;
    return {
      summary: C.summary, counties_crossing: (C.county_changes || []).slice(0, 12),
      new_trials: (C.new_trials || []).slice(0, 12).map(t => ({ nct: t.nct_id, title: t.title, phase: t.phase, sponsor: t.sponsor })),
      no_longer_listed: (C.no_longer_listed || []).slice(0, 12).map(t => ({ nct: t.nct_id, title: t.title })),
    };
  }
  function runSiteInfo(input) {
    const topic = String(input.topic || '');
    const t = SITE_INFO[topic];
    if (!t) return { error: `unknown topic '${topic}'`, hint: 'topics: ' + Object.keys(SITE_INFO).join(', ') };
    const res = { topic, title: t.title, text: t.text, url: t.url };
    const numbers = siteNumbers(topic);
    if (numbers !== null) res.numbers = numbers;
    return res;
  }

  // ---- find_places ----
  function runFindPlaces(input, callId) {
    const res = findPlaces(S.placeIx, input || {});
    if (res.error) return res;
    const geo = res.matches.filter(m => ['county', 'district', 'state'].includes(m.kind));
    const units = new Set(geo.map(m => m.kind));
    const columns = ['id', 'name', 'state', 'pop55', 'kind', 'how', 'via'];
    remember(callId, { ids: geo.map(m => m.id), unit: units.size === 1 ? [...units][0] : null, rows: res.matches.map(m => Object.fromEntries(columns.map(c => [c, m[c] === undefined ? null : m[c]]))), columns });
    return res;
  }

  // ---- public surface ----
  async function run(name, input, callId) {
    try {
      if (!TOOLS.includes(name)) return { error: `unknown tool '${name}'`, hint: 'tools: ' + TOOLS.join(', ') };
      if (name === 'final_answer') return { ok: true };
      if (!ready()) return { error: 'the engine has not loaded its data yet', hint: 'call engine.load() first' };
      const inp = input && typeof input === 'object' ? input : {};
      switch (name) {
        case 'find_places': return runFindPlaces(inp, callId);
        case 'query': return runQuery(inp, callId);
        case 'aggregate': return runAggregate(inp);
        case 'profile': return runProfile(inp, callId);
        case 'compare': return runCompare(inp, callId);
        case 'trials': return runTrials(inp);
        case 'site_info': return runSiteInfo(inp);
        default: return { error: `unknown tool '${name}'` };
      }
    } catch (e) { return { error: 'internal: ' + String(e && e.message || e).slice(0, 200) }; }
  }
  // "Hidalgo County, Texas" for any id the engine knows (county FIPS, district id/geoid, USPS, US, nci:/fac:/bioguide)
  function placeName(id) {
    if (isNull(id)) return null;
    const s = String(id);
    for (const t of ['counties', 'districts', 'states', 'national', 'nci_centers', 'facilities', 'senators']) { const r = S.byId[t] && S.byId[t].get(s); if (r) return r.name; }
    if (S.byId.districtsByGeoid && S.byId.districtsByGeoid.has(s)) return S.byId.districtsByGeoid.get(s).name;
    const u = stateCode(s); if (u && S.byId.states && S.byId.states.has(u)) return S.byId.states.get(u).name;
    return null;
  }
  function unitOf(id) {
    if (isNull(id) || !S.byId.counties) return null;
    const s = String(id);
    if (S.byId.counties.has(s)) return 'county';
    if (S.byId.districts.has(s) || S.byId.districtsByGeoid.has(s)) return 'district';
    if (S.byId.states.has(s) || (stateCode(s) && S.byId.states.has(stateCode(s)))) return 'state';
    return null;
  }
  function vintages() {
    const F = S.files; const out = {};
    if (S.asOf) out.data_as_of = S.asOf;
    if (F.data && F.data.meta && F.data.meta.pull_utc) out.registry_pull = F.data.meta.pull_utc;
    const c0 = S.tables && S.tables.counties[0];
    out.incidence_period = (c0 && c0.incidence && c0.incidence.period) || SOURCES.incidence.vintage;
    out.mortality_period = (F.mortality && F.mortality.meta && F.mortality.meta.period) || (c0 && c0.mortality && c0.mortality.period) || SOURCES.mortality.vintage;
    if (F.oncologists && F.oncologists.meta) { out.oncologists_pulled = F.oncologists.meta.pulled || null; out.oncologists_source_modified = F.oncologists.meta.source_modified || null; } else out.oncologists_pulled = SOURCES.oncologists.vintage;
    out.cosponsors_fetched = (F.cosponsors && F.cosponsors.meta && F.cosponsors.meta.fetched) || SOURCES.congress.vintage;
    out.acs = SOURCES.acs.vintage; out.rucc = SOURCES.rucc.vintage; out.roads = SOURCES.roads.vintage; out.nci = SOURCES.nci.vintage; out.district_plan = SOURCES.districts.vintage;
    return out;
  }
  function sourcesFor(tables) {
    const list = Array.isArray(tables) ? tables : tables ? [tables] : [];
    const out = []; const seen = new Set();
    for (const t of list) { if (!TABLES[t] && t !== 'trials' || seen.has(t)) continue; seen.add(t); const s = sourceOf(t); out.push({ table: t, title: t === 'trials' ? 'recruiting trials (the map\'s trial list)' : TABLES[t].label, file: s.file, url: s.url, as_of: s.as_of }); }
    return out;
  }
  function full(callId) { const r = S.calls.get(String(callId)); return r ? { ids: r.ids.slice(), returned_ids: (r.returned_ids || r.ids).slice(), filtered: r.filtered !== false, ordered: !!r.ordered, unit: r.unit, rows: r.rows.slice(), columns: r.columns.slice() } : null; }
  // The ids a final_answer.map.highlight names: explicit ids, or a call's rows. A ranking (an ordered query with no condition
  // beyond the state scope) outlines only the rows returned (the top N the question asked for); a filtered query outlines every
  // match; highlight.rows = "all" | "returned" overrides. Returns { ids, unit, mode } or null when nothing resolves.
  function highlightIds(highlight) {
    if (!highlight || typeof highlight !== 'object') return null;
    if (Array.isArray(highlight.ids)) return { ids: highlight.ids.map(String).slice(0, 5000), unit: null, mode: 'ids' };
    const f = full(highlight.from_call); if (!f) return null;
    const mode = highlight.rows === 'all' || highlight.rows === 'returned' ? highlight.rows : (f.ordered && !f.filtered ? 'returned' : 'all');
    return { ids: mode === 'returned' ? f.returned_ids : f.ids, unit: f.unit, mode };
  }

  // ---- plain-English descriptions for the progress line and the step log ----
  const fmtVal = v => v && typeof v === 'object' && !Array.isArray(v) && 'field' in v ? v.field : Array.isArray(v) ? '[' + v.map(fmtVal).join(', ') + ']' : typeof v === 'string' ? `"${v}"` : String(v);
  const condText = n => n.any_of ? '(' + n.any_of.map(condText).join(' or ') + ')' : n.op === 'is_null' ? `${n.field} is null` : n.op === 'not_null' ? `${n.field} is not null` : `${n.field} ${n.op} ${fmtVal(n.value)}`;
  // "in TX" from the state conditions, "where …" from the rest
  function whereText(where) {
    const list = Array.isArray(where) ? where.filter(n => n && typeof n === 'object') : [];
    const st = list.filter(n => n.field === 'state' && ['=', 'in'].includes(n.op) && !(n.value && typeof n.value === 'object' && !Array.isArray(n.value)));
    const rest = list.filter(n => !st.includes(n));
    const inText = st.length ? ' in ' + st.map(n => Array.isArray(n.value) ? n.value.map(normStateValue).join(', ') : normStateValue(n.value)).join(', ') : '';
    const whereT = rest.length ? ' where ' + rest.map(condText).join(' and ') : '';
    return { inText, whereT };
  }
  const nameOf = id => placeName(id) || String(id);
  const joinAnd = a => a.length <= 1 ? a.join('') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1];
  function describeCall(name, input) {
    const i = input && typeof input === 'object' ? input : {};
    try {
      switch (name) {
        case 'find_places': return `Looking up "${i.query}"` + (i.kind ? ` (${i.kind})` : '') + (i.state ? ` in ${normStateValue(i.state)}` : '');
        case 'query': return describeQuery(i);
        case 'aggregate': return describeAggregate(i);
        case 'profile': return `Profile of ${nameOf(i.id)}`;
        case 'compare': return `Comparing ${joinAnd((Array.isArray(i.ids) ? i.ids : []).map(nameOf))}`;
        case 'trials': return describeTrials(i);
        case 'site_info': return `Reading the site's text on ${i.topic}`;
        case 'final_answer': return 'Writing the answer';
        default: return `Running ${name}`;
      }
    } catch (e) { return `Running ${name}`; }
  }
  // "Counties in TX where oncologists.count > 0 and trials_listed_here = 0, ordered by pop55 desc (first 20)"
  function describeQuery(i) {
    const { inText, whereT } = whereText(i.where);
    const keys = Array.isArray(i.order_by) ? i.order_by : i.order_by ? [i.order_by] : [];
    const ord = keys.length ? ', ordered by ' + keys.map(o => typeof o === 'string' ? o + ' desc' : `${o.field} ${o.dir || 'desc'}`).join(', ') : '';
    return `${TABLE_LABEL[i.table] || cap(String(i.table))}${inText}${whereT}${ord} (first ${clampLimit(i.limit, 20, 50)})`;
  }
  // "Count and mean of pct_lt20_trials_within_60rdmi across counties in TX grouped by metro"
  function describeAggregate(i) {
    const { inText, whereT } = whereText(i.where);
    const ms = (Array.isArray(i.measures) ? i.measures : []).map(m => m.stat === 'count' ? 'count' : `${String(m.stat || '').replace('_', ' ')} of ${m.field}`);
    return `${cap(joinAnd(ms) || 'aggregate')} across ${String(i.table || '').replace('national', 'the national row')}${inText}${whereT}${i.group_by ? ' grouped by ' + i.group_by : ''}`;
  }
  // "Trials with a site in Hidalgo County, Texas (lung & thoracic, phase 3)"
  function describeTrials(i) {
    const sc = i.scope && typeof i.scope === 'object' ? i.scope : {};
    const where = sc.county_id !== undefined ? `with a site in ${nameOf(sc.county_id)}` : sc.within_60_of_county_id !== undefined ? `within 60 road-miles of the ${nameOf(sc.within_60_of_county_id)} center`
      : sc.state !== undefined ? `with a site in ${STATES[stateCode(sc.state)] || sc.state}` : 'with a US site';
    const f = [i.cancer_type ? String(CANCER_TYPES[i.cancer_type] || i.cancer_type).split(' (')[0] : null, i.phase ? `phase ${i.phase}` : null, i.sponsor_type ? SPONSOR_TYPES[i.sponsor_type] || i.sponsor_type : null,
      i.keyword ? `"${i.keyword}"` : null, !isNull(i.min_age_at_most) ? `minimum age ≤ ${i.min_age_at_most}` : null].filter(Boolean);
    return `Trials ${where}` + (f.length ? ` (${f.join(', ')})` : '');
  }
  function describeResult(name, input, result) {
    const r = result || {};
    if (r.error) return `error: ${r.error}`;
    const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
    switch (name) {
      case 'query': return `${r.count} match; showing ${r.returned}`;
      case 'aggregate': return r.group_by ? plural((r.groups || []).length, 'group') : `1 result over ${plural(r.count || 0, 'row')}`;
      case 'find_places': return !r.matches || !r.matches.length ? 'no match' : r.ambiguous ? `${r.matches.length} candidates (ambiguous)` : plural(r.matches.length, 'place') + ' found';
      case 'profile': return r.name || 'found';
      case 'compare': return `${(r.rows || []).length} rows compared`;
      case 'trials': return plural(r.count || 0, 'trial');
      case 'site_info': return r.title || r.topic || 'text';
      case 'final_answer': return 'answer written';
      default: return 'done';
    }
  }

  return { load, run, describeCall, describeResult, full, highlightIds, sourcesFor, placeName, unitOf, vintages, get loaded() { return S.loaded; }, table: t => (S.tables && S.tables[t]) || null, get: (t, id) => resolveRow(t, id) };
}
