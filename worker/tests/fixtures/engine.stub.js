/* A stand-in for docs/ask/engine.js with the interface of ASK_CONTRACT.md §11, for exercising the client (docs/ask/ask.js) in a
   browser before the real engine is wired in, or without the network. It answers every `query` on the counties table with the same
   two Texas counties (from window.DATA when the map page has it, so the ids are real), and the other tools with small fixed results.
   Use on localhost:  localStorage.setItem('askEngineUrl', '/worker/tests/fixtures/engine.stub.js')  with the repository root served
   (python3 -m http.server 8765, then http://localhost:8765/docs/map.html) and stub_worker.js on port 8766 (localStorage askUrl). */
export function createEngine(opts = {}) {
  const g = opts.globals || {}; const onProgress = opts.onProgress || (() => {});
  const full = new Map(); let loaded = false;
  const IDS = ['48215', '48505', '48047'];   // Hidalgo, Starr, Brooks counties, Texas
  const rowsFor = () => IDS.map((id, i) => { const c = g.DATA && g.DATA.counties && g.DATA.counties[id]; return { id, name: c ? (g.SITE ? g.SITE.countyLabel(c, id) : c.n) : `County ${id}`, state: 'TX', pop55: c ? c.p : 1000 * (i + 1), 'oncologists.count': [31, 2, 1][i], trials_listed_here: 0, metro: [true, false, false][i] }; });
  const COLS = ['id', 'name', 'state', 'pop55', 'oncologists.count', 'trials_listed_here', 'metro'];
  const SRC = { file: 'api/all_counties.json', url: 'https://cancertrialaccess.org/api/all_counties.json', as_of: '2026-11-03' };
  const engine = {
    loaded: { counties: false, districts: false, states: false, national: false, optional: {} },
    async load() { if (loaded) return; onProgress('Loading the data files (first question only)… counties'); await new Promise(r => setTimeout(r, 300)); onProgress('Loading the data files (first question only)… districts, states'); await new Promise(r => setTimeout(r, 200)); loaded = true; engine.loaded = { counties: true, districts: true, states: true, national: true, optional: { burden: !!g.BURDEN, mortality: !!g.MORTALITY, oncologists: !!g.ONCOLOGISTS, rucc: !!g.RUCC, cosponsors: !!g.COSPONSORS } }; },
    async run(name, input, callId) {
      await new Promise(r => setTimeout(r, 250));
      if (name === 'query') { const rows = rowsFor(); full.set(callId, { ids: rows.map(r => r.id), unit: 'county', rows, columns: COLS }); return { table: input.table || 'counties', count: rows.length, in_scope: 254, returned: rows.length, columns: COLS, rows, nulls: {}, ids_truncated: false, sum_pop55_matching: rows.reduce((s, r) => s + r.pop55, 0), source: SRC }; }
      if (name === 'find_places') { full.set(callId, { ids: ['48215'], unit: 'county', rows: [{ id: '48215', name: 'Hidalgo County, Texas', state: 'TX', pop55: 182206 }], columns: ['id', 'name', 'state', 'pop55'] }); return { matches: [{ id: '48215', table: 'counties', kind: 'county', name: 'Hidalgo County, Texas', state: 'TX', pop55: 182206, how: 'exact' }], ambiguous: false }; }
      if (name === 'aggregate') return { table: input.table || 'counties', count: 3, groups: [{ group: null, n: 3, sum_pop55: 230000, measures: { 'pop55:sum': 230000 } }], note: 'Computed by the engine across the matching rows; a mean of county rates is not the published state rate (use the states table for that).', source: SRC };
      if (name === 'site_info') return { topic: input.topic, text: 'Stub text for ' + input.topic, url: 'https://cancertrialaccess.org/methods.html#methods' };
      if (name === 'trials') return { count: 0, by_phase: {}, by_sponsor_type: {}, by_cancer_type: [], sample: [], link: 'trials.html?county=48215', note: 'Trials listed, never trials available to a person.' };
      return { error: `unknown tool '${name}'`, hint: 'tools: find_places, query, aggregate, profile, compare, trials, site_info, final_answer' };
    },
    describeCall(name, input) { if (name === 'query') return `${input.table || 'counties'} where ${(input.where || []).map(c => `${c.field} ${c.op} ${JSON.stringify(c.value)}`).join(' and ') || 'anything'}`; return `${name} ${JSON.stringify(input).slice(0, 80)}`; },
    describeResult(name, input, r) { if (r && r.error) return `error: ${r.error}`; if (name === 'query') return `${r.count} match; showing ${r.returned}`; if (name === 'find_places') return `${r.matches.length} place${r.matches.length === 1 ? '' : 's'}`; return 'done'; },
    full(callId) { return full.get(callId) || null; },
    sourcesFor(tables) { return (tables || []).map(t => t === 'counties' ? { table: t, title: 'Counties', ...SRC } : { table: t, title: t, file: `api/all_${t}.json`, url: `https://cancertrialaccess.org/api/all_${t}.json`, as_of: '2026-11-03' }); },
    placeName(id) { const c = g.DATA && g.DATA.counties && g.DATA.counties[id]; return c ? (g.SITE ? g.SITE.countyLabel(c, id) : c.n) : null; },
    unitOf(id) { const s = String(id); return /^\d{5}$/.test(s) ? 'county' : /^[A-Z]{2}-\d{2}$/.test(s) ? 'district' : /^[A-Z]{2}$/.test(s) ? 'state' : null; },
    vintages() { return { data_as_of: '2026-11-03', incidence_period: '2019-2023', mortality_period: '2020-2024', oncologists_pulled: '2026-10-19', cosponsors_fetched: '2026-11-03', acs: '2020-2024' }; },
  };
  return engine;
}
