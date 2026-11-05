/* Executes a plan against the loaded data files, with ordinary arithmetic only: filtering, sorting, counting, summing.
   execute(plan, data) is pure and total (no network, never throws on a well-formed plan). The table it returns is the only
   thing the writer model sees; every value in it is read from a row or is a count/sum of row values, and every column
   is labelled with its unit and data basis. composeAnswer writes the deterministic answer from the same table;
   verifyAnswer checks a model-written answer against it. */
import { METRICS, STATES, TERRITORIES, TYPES, TYPE_LABEL, SITE_LABEL, SITES, ACS, BILLS, LEVEL_NOUN, metricLabel, metricWorse } from './lexicon.js';

const fmtInt = v => (v === null || v === undefined) ? 'not in the data' : Number(v).toLocaleString('en-US');
const isNum = v => typeof v === 'number' && !Number.isNaN(v);
const nz = v => v === null || v === undefined;
const cmpName = (a, b) => String(a.name).localeCompare(String(b.name));
const byPop = (a, b) => (b.pop55 || 0) - (a.pop55 || 0) || cmpName(a, b);
const SITE_BASE = 'https://nehaamd.github.io/cancer-trial-access-fullmap/';

export function execute(plan, data) {
  const asOf = (data && data.index && data.index.data_as_of) || (data && data.national && data.national.data_as_of) || null;
  const base = { route: plan.route || 'data', shape: plan.shape, answer_facts: {}, summary: null, table: [], rows: [], view: null, sources: [], data_as_of: asOf, caveats: [], plan };
  try {
    if (plan.level_note) { const ln = plan.level_note; base.caveats.push(`${capital(metricLabel(ln.metric, plan))} is published for ${LEVEL_NOUN[ln.used]} only, not ${LEVEL_NOUN[ln.asked]}; the answer is at ${ln.used} level${ln.asked !== 'county' && plan.state ? ` within ${STATES[plan.state] || plan.state}` : ''}.`); }
    if (plan.flags && Array.isArray(plan.flags.also_named)) for (const a of plan.flags.also_named) base.caveats.push(`${a.assumed} assumed; there is also a ${a.others.join(' and a ')} — add the state to ask about it.`);
    if (plan.route === 'scope' || plan.route === 'other') return base;
    if (plan.route === 'search') return doSearch(plan, data, base);
    if (plan.shape === 'ambiguous') return doAmbiguous(plan, base);
    if (plan.shape === 'territory') { base.answer_facts = { kind: 'territory', name: TERRITORIES[plan.territory] || 'that territory' }; return base; }
    if (plan.shape === 'unknown_place') { const u = plan.places.find(p => p.unknown); base.answer_facts = { kind: 'unknown_place', name: u ? u.name : 'that place', zip: u && u.via && u.via.zip }; return base; }
    switch (plan.shape) {
      case 'lookup': return doLookup(plan, data, base);
      case 'compare': return doCompare(plan, data, base);
      case 'count': return doCount(plan, data, base);
      case 'threshold': return doThreshold(plan, data, base);
      case 'represents': return doRepresents(plan, data, base);
      case 'cosponsor': return doCosponsor(plan, data, base);
      case 'need': return doNeed(plan, data, base);
      case 'bytype': return doByType(plan, data, base);
      default: return doRanking(plan, data, base);
    }
  } catch (e) { base.answer_facts = { kind: 'error', detail: String(e && e.message || e).slice(0, 200) }; base.caveats.push('The question could not be run against the data files.'); return base; }
}

// ---------- rows and columns ----------
function rowsFor(level, data) { if (level === 'national') return data.national ? [data.national] : []; const f = { county: 'counties', district: 'districts', state: 'states' }[level]; return Array.isArray(data[f]) ? data[f] : []; }
function rowOf(place, data) { if (place.kind === 'national') return data.national || null; const rows = rowsFor(place.kind, data); return rows.find(r => r.id === place.id) || null; }
function levelFile(level, r) { return level === 'national' ? 'api/national.json' : `api/${level}/${r.id}.json`; }
const hlId = (level, r) => level === 'district' ? (r.geoid || r.id) : r.id;
function fmtVal(key, v, plan) { const M = METRICS[key]; if (nz(v)) return 'not in the data'; if (M.text) return String(v); if (M.unit === '%') return `${v}%`; if (M.unit === 'people') return fmtInt(v); const unit = v === 1 && /^(trials|sites|oncologists|hours)$/.test(M.unit) ? M.unit.slice(0, -1) : M.unit; return `${isNum(v) && Math.abs(v) >= 10000 ? fmtInt(v) : v} ${unit}`.trim(); }
function colLabel(key, plan, r) { const M = METRICS[key]; const lab = metricLabel(key, plan); const period = M.periodOf && r ? M.periodOf(r) : null; const parts = [M.unit && M.unit !== '%' && M.unit !== 'people' ? M.unit : null, M.basis && !lab.includes(M.basis) ? M.basis : null, period ? String(period) : null].filter(Boolean); return parts.length ? `${lab} (${parts.join('; ')})` : lab; }
function memberText(r) { if (!r.member) return null; const m = r.member; const st = m.ctma_hr3521; return `${m.name || 'vacant seat'}${m.party ? ` (${m.party})` : ''}, ${st === 'none' || !st ? 'not a cosponsor of' : st === 'sponsor' ? 'sponsor of' : st === 'original' ? 'original cosponsor of' : 'cosponsor of'} H.R. 3521`; }
function senatorsText(r) { if (!Array.isArray(r.senators) || !r.senators.length) return null; return r.senators.map(s => `${s.name}${s.party ? ` (${s.party})` : ''}: ${s.s4440 === 'none' || !s.s4440 ? 'not a cosponsor' : s.s4440} of S. 4440`).join('; '); }
function placeCell(level, r) { return r.name; }
// one table row: the metric first, then the fixed context for that level
function tableRow(level, r, plan, metricKey, extraCols) {
  const o = { place: placeCell(level, r) }; const M = METRICS[metricKey];
  if (M) o[colLabel(metricKey, plan, r)] = fmtVal(metricKey, M.get(r, plan), plan);
  o['residents 55+'] = fmtInt(r.pop55);
  if (metricKey !== 'pct_lt20') o['share with fewer than 20 trials within 60 road-miles (%; residents 55+)'] = fmtVal('pct_lt20', METRICS.pct_lt20.get(r), plan);
  for (const [k, lab] of extraCols || []) { if (k === 'member') o[lab] = memberText(r) || 'not in the data'; else if (k === 'senators') o[lab] = senatorsText(r) || 'not in the data'; else if (METRICS[k] && k !== metricKey) { const v = METRICS[k].get(r, plan); o[lab || colLabel(k, plan, r)] = fmtVal(k, v, plan); } }   // every row carries every column, so the table is uniform
  return o;
}
const CTX_COLS = { county: [['trials_here', 'recruiting trials with a site in the county'], ['wmean60', 'average trials within 60 road-miles (population-weighted)'], ['med_nci', 'median road-miles to the nearest NCI center'], ['nearest_nci', 'nearest NCI-designated center'], ['metro', 'metro or nonmetro (RUCC 2023)']], district: [['med_nci', 'median road-miles to the nearest NCI center'], ['nearest_nci', 'nearest NCI-designated center'], ['member', 'House member (119th Congress)']], state: [['pct_zero', 'share with no trial within 60 road-miles (%)'], ['med_nci', 'median road-miles to the nearest NCI center'], ['nearest_nci', 'nearest NCI-designated center (to most residents)'], ['senators', 'senators (S. 4440)']], national: [['pct_zero', 'share with no trial within 60 road-miles (%)'], ['med_nci', 'median road-miles to the nearest NCI center']] };

function sourcesFor(level, rows) { const seen = new Set(); const out = []; for (const r of rows) { const u = levelFile(level, r); if (seen.has(u)) continue; seen.add(u); out.push({ title: r.name, url: SITE_BASE + u }); } return out; }
const HL_CAP = 400;
function capRows(rows, base, level, how) { if (rows.length <= HL_CAP) return rows; base.caveats.push(`${fmtInt(rows.length)} ${LEVEL_NOUN[level]} match; the map outlines the first ${HL_CAP} of them (${how || 'in the table\'s order'}).`); return rows.slice(0, HL_CAP); }
// table, rows and hl are one list in one order: the table shows the first `shown`, rows and hl carry the first HL_CAP
function setList(base, level, ordered, shown, rowFn, how) { const capped = capRows(ordered, base, level, how); base.table = ordered.slice(0, shown).map(rowFn); base.rows = capped.map(r => ({ id: r.id, level, name: r.name, geoid: r.geoid || null, state: r.state || null })); return capped; }
function viewFor(plan, level, rows, metricKey, opts = {}) {
  const qs = new URLSearchParams(); const M = METRICS[metricKey] || METRICS.pct_lt20; const unit = level === 'national' ? 'county' : level;
  if (unit !== 'county') qs.set('u', unit);
  let m = opts.layer || (unit === 'county' ? M.county : M.geo); if (unit === 'state' && m && m.startsWith('cos_')) m = 'l20'; qs.set('m', m);
  const params = M.params ? M.params(plan) : {}; for (const [k, v] of Object.entries(params)) if (v) qs.set(k, String(v));
  if (plan.rural === 'nonmetro' || plan.rural === 'metro') qs.set('rural', '1');
  if (plan.cancer_type && TYPES.includes(plan.cancer_type) && !qs.get('type')) qs.set('type', plan.cancer_type);
  if (opts.tab) qs.set('tab', opts.tab); for (const [k, v] of Object.entries(opts.extra || {})) qs.set(k, String(v));
  const ids = rows.map(r => hlId(unit, r)); if (level === 'national' && !opts.keepNational) ids.length = 0;
  if (rows.length === 1 && level !== 'national') { const r = rows[0]; if (unit === 'county') qs.set('c', r.id); else if (unit === 'district') qs.set('d', r.geoid || r.id); else qs.set('s', r.id); if (opts.stateScope && plan.state && STATES[plan.state] && unit !== 'state') qs.set('s', plan.state); }
  else if (plan.state && STATES[plan.state] && unit !== 'state') qs.set('s', plan.state);
  else if (plan.state && STATES[plan.state] && unit === 'state' && rows.length !== 1 && opts.stateScope) qs.set('s', plan.state);
  return { page: 'map', qs: qs.toString(), hl: ids.slice(0, 2000), unit, layer: m };
}
function filterScope(rows, plan, base) {
  let out = rows; if (plan.state && plan.level !== 'national' && plan.level !== 'state') out = out.filter(r => r.state === plan.state);
  if (plan.level === 'state' && plan.state && plan.shape !== 'ranking') out = out.filter(r => r.id === plan.state);
  if (plan.cosponsor && plan.level === 'district') { const vacant = out.filter(r => !r.member || !r.member.name); if (vacant.length && plan.cosponsor === 'none') base.caveats.push(`${vacant.map(r => r.name).join(', ')}: vacant seat, not counted as a non-cosponsor.`); const f = plan.cosponsor === 'none' ? (r => r.member && r.member.name && (r.member.ctma_hr3521 === 'none' || !r.member.ctma_hr3521)) : (r => r.member && r.member.ctma_hr3521 && r.member.ctma_hr3521 !== 'none'); out = out.filter(f); }
  if (plan.onc_no_trials && plan.level === 'county') { const have = out.some(r => r.oncologists && typeof r.oncologists.class === 'number'); if (!have) base.caveats.push('The oncologists-vs-trials classification is not in the data files yet, so "oncologists but no trials" could not be applied.'); else out = out.filter(r => r.oncologists && r.oncologists.class === 2); }
  if (plan.rural && plan.level === 'county') { const have = out.some(r => typeof r.metro === 'boolean'); if (!have) base.caveats.push('Metro / nonmetro status (RUCC) is not in the data files yet, so the rural filter was not applied.'); else out = out.filter(r => plan.rural === 'nonmetro' ? r.metro === false : r.metro === true); }
  else if (plan.rural && plan.level !== 'county' && plan.shape === 'ranking') base.caveats.push('Rural / metro is a county classification; districts and states are shown by their nonmetro share instead.');
  return out;
}
function sortWorst(rows, key, plan, order) { const M = METRICS[key]; if (M.text) return rows.slice().sort(byPop); const worse = metricWorse(key, plan); const sign = ((worse === 'high') === ((order || 'worst') === 'worst')) ? -1 : 1;   // -1: largest first
  return rows.slice().sort((a, b) => { const va = M.get(a, plan), vb = M.get(b, plan); return sign * (va - vb) || byPop(a, b); }); }
function typeCaveat(plan, base) { if (plan.cancer_type && plan.level === 'county') base.caveats.push(`Trial counts by cancer type are published for districts and states only (average ${TYPE_LABEL[plan.cancer_type] || plan.cancer_type} trials within 60 road-miles); counties have no by-type field, so the county figures are for all cancer trials. The map opens with the ${TYPE_LABEL[plan.cancer_type] || plan.cancer_type} filter set.`); else if (plan.cancer_type && plan.metric === 'type_trials') base.caveats.push(`By-type figures are population-weighted averages of recruiting ${TYPE_LABEL[plan.cancer_type] || plan.cancer_type} trials within 60 road-miles of home, at ${plan.level} level.`); }
function smallNumbersCaveat(rows, plan, base) { const k = plan.metric === 'mort' || plan.metric === 'mort_deaths' ? 'mortality' : 'incidence'; const small = rows.filter(r => r[k] && r[k].small_numbers === true).length; const sup = rows.filter(r => r[k] && (r[k].status === 'suppressed' || r[k].status === 'no data')).length; if (small) base.caveats.push(`${small} of these counties ${small === 1 ? 'has' : 'have'} small-numbers ${k} rates (few cases a year): interpret with caution.`); if (sup) base.caveats.push(`${sup} ${sup === 1 ? 'county has' : 'counties have'} no published ${k} rate (suppressed by the source or not available).`); }
function routeCaveat(rows, plan, base) { if (['med_nci', 'med_broad'].includes(plan.metric) && rows.some(r => nz(METRICS[plan.metric].get(r, plan)))) base.caveats.push('Places with no road route to a center (islands, remote Alaska) have no median and are left out of the ranking.'); }
function vacantCaveat(rows, base) { const v = rows.filter(r => r.member && !r.member.name); if (v.length) base.caveats.push(`${v.map(r => r.name).join(', ')}: the seat is vacant in the data.`); if (rows.some(r => r.member || r.plan)) base.caveats.push('District boundaries are the 119th Congress plan (2024 election maps).'); }
const NEW_FIELDS = new Set(['rucc', 'metro', 'nonmetro_pct', 'rn_center', 'rb_center', 'rl_center', 'hn', 'hb', 't60', 'f60', 'inc', 'inc_cases', 'mort', 'mort_deaths', 'onc', 'onc60', 'onc_class', 'onc_no_trials_pct', 'onc_per100k', 'nonmetro_lt20', 'metro_lt20', 'nonmetro_zero', 'metro_zero', 'nonmetro_mean', 'metro_mean', 'cos_s4440']);   // fields the API may not carry yet: all-null means "not published", not "no value"
function absentCaveat(key, rows, plan, base) { const M = METRICS[key]; if (!M || !rows.length || !NEW_FIELDS.has(key)) return false; if (rows.every(r => nz(M.get(r, plan)))) { base.caveats.push(`${capital(metricLabel(key, plan))} is not published for ${LEVEL_NOUN[plan.level] || plan.level} (it is published for ${M.levels.map(l => LEVEL_NOUN[l]).join(', ')}); the table shows the headline access measure instead.`); return true; } return false; }
const capital = s => String(s).replace(/^[a-z]/, c => c.toUpperCase());

const fallbackFor = (key, level) => { const F = { hn: 'med_nci', hb: 'med_broad', rn_center: 'med_nci', rb_center: 'med_broad', rl_center: 'med_broad', t60: 'wmean60', f60: 'trials_here', facilities: 'trials_here', mort: 'inc', mort_deaths: 'inc_cases', onc60: 'onc', onc_class: 'onc', onc_no_trials_pct: 'onc', rucc: 'nonmetro_pct', metro: 'nonmetro_pct', nonmetro_pct: 'rucc', no_route: 'med_nci', onc_per100k: 'onc', type_trials: 'wmean60' }; let k = key; for (let i = 0; i < 3 && !(METRICS[k] && METRICS[k].levels.includes(level)); i++) k = F[k] || 'pct_lt20'; return METRICS[k] && METRICS[k].levels.includes(level) ? k : 'pct_lt20'; };
// ---------- shapes ----------
function doRanking(plan, data, base) {
  const level = plan.level === 'national' ? 'state' : plan.level; plan = { ...plan, level }; let key = plan.metric; const M = METRICS[key];
  let rows = filterScope(rowsFor(level, data), plan, base); const scopeN = rows.length;
  if (M.text) key = { nearest_nci: 'med_nci', nearest_broad: 'med_broad', metro: 'rucc', onc_class: 'onc' }[key] || 'pct_lt20';
  if (absentCaveat(key, rows, plan, base)) key = 'pct_lt20';
  typeCaveat(plan, base);
  const withVal = rows.filter(r => !nz(METRICS[key].get(r, plan))); const missing = rows.length - withVal.length;
  if (rows.length && !withVal.length) { base.caveats.push(['med_nci', 'med_broad', 'rn_center', 'rb_center', 'hn', 'hb'].includes(key) ? `No ${LEVEL_NOUN[level]} in ${plan.state ? STATES[plan.state] : 'scope'} have a road route to a center in the road network used, so there is no distance to rank.` : `"${metricLabel(key, plan)}" has no value for any of these ${LEVEL_NOUN[level]}.`); }
  const sorted = sortWorst(withVal, key, plan, plan.order); const top = sorted.slice(0, Math.min(25, Math.max(1, plan.n || 5)));
  const extra = (CTX_COLS[level] || []).filter(([k]) => k !== key); if (M.text) extra.unshift([plan.metric, metricLabel(plan.metric, plan)]);
  if (['inc', 'inc_cases'].includes(key)) extra.unshift(['inc_cases', 'average annual new cases (all sites)']); if (['mort', 'mort_deaths'].includes(key)) extra.unshift(['mort_deaths', 'average annual cancer deaths (all sites)']);
  const scopeText = `${LEVEL_NOUN[level]} in ${plan.state ? STATES[plan.state] : (plan.cosponsor ? 'the House' : 'the United States')}${plan.cosponsor ? ` whose member ${plan.cosponsor === 'none' ? 'has not cosponsored' : 'cosponsors'} H.R. 3521` : ''}${plan.onc_no_trials ? ' with oncologists but no recruiting trial' : ''}${plan.rural ? ` (${plan.rural} only)` : ''}`;
  base.summary = { rule: `${scopeText}, ranked by ${metricLabel(key, plan)}, ${plan.order === 'best' ? 'best' : 'worst'} first${METRICS[key].computed ? ` (${METRICS[key].basis})` : ''}`, counts: { [`${LEVEL_NOUN[level]} in scope`]: scopeN, [`${LEVEL_NOUN[level]} shown`]: top.length } };
  setList(base, level, top, top.length, r => tableRow(level, r, plan, key, extra), 'rank order');
  const firstVal = top.length ? METRICS[key].get(top[0], plan) : null; const tied = top.length ? sorted.filter(r => METRICS[key].get(r, plan) === firstVal).length : 0;
  if (tied > top.length) { base.caveats.push(`${fmtInt(tied)} ${LEVEL_NOUN[level]} tie at ${fmtVal(key, firstVal, plan)}; the ${top.length} listed are the most populous of them (residents 55+).`); base.summary.counts[`${LEVEL_NOUN[level]} tied at ${fmtVal(key, firstVal, plan)}`] = tied; }
  base.answer_facts = { kind: 'ranking', scopeText, type_fallback: !!(plan.flags && plan.flags.type_fallback), tied: tied > top.length ? tied : 0, firstVal: fmtVal(key, firstVal, plan), level_note: plan.level_note || null, countish: !['%', 'per 100,000', 'road-miles', 'hours', ''].includes(METRICS[key].unit), level, scope: plan.state ? STATES[plan.state] : (plan.cosponsor ? 'the House' : 'the United States'), metric: key, label: metricLabel(key, plan), order: plan.order || 'worst', n: top.length, of: scopeN, missing, cosponsor: plan.cosponsor, rural: plan.rural, values: top.map(r => ({ name: r.name, v: fmtVal(key, METRICS[key].get(r, plan), plan) })) };
  if (missing) base.caveats.push(`${missing} of ${scopeN} ${LEVEL_NOUN[level]} have no value for this measure and are left out.`);
  if (['inc', 'inc_cases', 'mort', 'mort_deaths'].includes(key)) smallNumbersCaveat(top, plan, base); routeCaveat(rows, plan, base); if (level === 'district') vacantCaveat(top, base);
  if (plan.flags && plan.flags.site_unavailable) base.caveats.push(`Incidence and death rates are published for ${SITES.length - 1} cancer sites; "${plan.flags.site_unavailable}" is not one of them, so the all-sites rate is shown.`);
  base.sources = sourcesFor(level, top).concat([{ title: `all_${{ county: 'counties', district: 'districts', state: 'states' }[level]}.json`, url: SITE_BASE + `api/all_${{ county: 'counties', district: 'districts', state: 'states' }[level]}.json` }]);
  base.view = viewFor(plan, level, top, key, { stateScope: true, ...(plan.cosponsor && level === 'district' ? { layer: 'cos_ctma_hr' } : {}) }); return base;
}

function doLookup(plan, data, base) {
  const place = plan.places[0]; const level = place.kind; const r = rowOf(place, data);
  if (!r) { base.answer_facts = { kind: 'unknown_place', name: place.name }; return base; }
  let key = plan.metric; const M = METRICS[key]; let metricAbsent = false;
  if (key === 'type_trials' && level === 'county') { key = 'wmean60'; typeCaveat(plan, base); }
  else if ((key === 'rucc' || key === 'metro' || key === 'nonmetro_pct' && level === 'national' || key === 'pct_lt20' && plan.rural) && (level === 'state' || level === 'national') && !nz(METRICS.nonmetro_lt20.get(r))) key = 'nonmetro_lt20';
  else if (M && !M.levels.includes(level)) { const alt = fallbackFor(key, level); base.caveats.push(`${capital(metricLabel(key, plan))} is published for ${M.levels.map(l => LEVEL_NOUN[l]).join(', ')} only; ${r.name} is shown with ${metricLabel(alt, plan)} instead.`); base.substituted = { asked: metricLabel(key, plan), used: metricLabel(alt, plan), levels: M.levels.map(l => LEVEL_NOUN[l]).join(', ') }; key = alt; }
  else if (nz(M.get(r, plan))) { metricAbsent = true; base.caveats.push(`"${metricLabel(key, plan)}" is not in the data file for ${r.name}${['inc', 'mort', 'onc', 'rucc', 'metro', 'hn', 'hb', 't60', 'f60', 'rn_center', 'rb_center', 'onc60', 'onc_class', 'nonmetro_pct', 'onc_no_trials_pct', 'inc_cases', 'mort_deaths'].includes(key) ? ' (the field may not be published yet)' : ''}.`); }
  const extra = (CTX_COLS[level] || []).filter(([k]) => k !== key);
  if (level === 'county') { for (const k of ['pct_zero', 'pct_gt60_nci', 'med_broad', 'facilities', 'rucc', 'rn_center', 'hn', 't60', 'inc', 'inc_cases', 'mort', 'mort_deaths', 'onc', 'onc_class']) if (k !== key && !nz(METRICS[k].get(r, plan))) extra.push([k, colLabel(k, plan, r)]); for (const a of Object.keys(ACS)) extra.push(['acs', `${ACS[a].label} (%; ACS, all ages)`, a]); }
  if (level === 'district' || level === 'state') { for (const k of ['pct_zero', 'pct_gt60_nci', 'med_broad', 'trials_here', 'wmean60', 'inc', 'nonmetro_pct', 'onc', 'onc_no_trials_pct']) if (k !== key && !nz(METRICS[k].get(r, plan))) extra.push([k, colLabel(k, plan, r)]); }
  if (level === 'national') { for (const k of ['people_lt20', 'pct_gt60_nci', 'pct_gt60_broad', 'med_broad', 'wmean60', 'trials_here', 'facilities', 'onc', 'nonmetro_pct']) if (k !== key && !nz(METRICS[k].get(r, plan))) extra.push([k, colLabel(k, plan, r)]); }
  if ((level === 'state' || level === 'national') && (plan.rural || /^(non)?metro_/.test(key) || plan.metric === 'nonmetro_pct' || plan.metric === 'rucc')) for (const k of ['nonmetro_lt20', 'metro_lt20', 'nonmetro_zero', 'metro_zero', 'nonmetro_mean', 'metro_mean']) if (k !== key && !nz(METRICS[k].get(r, plan))) extra.push([k, colLabel(k, plan, r)]);
  const row = tableRow(level, r, plan, key, extra.filter(e => e[0] !== 'acs'));
  for (const e of extra.filter(e => e[0] === 'acs')) { const v = METRICS.acs.get(r, { acs: e[2] }); if (!nz(v)) row[e[1]] = `${v}%`; }
  if (place.via && place.via.zip) row['note'] = `ZIP ${place.via.zip} is in ${r.name}`; if (place.via && place.via.city) row['note'] = `${place.via.city} is in ${r.name}`;
  if (plan.cancer_type && level !== 'county') { const v = METRICS.type_trials.get(r, plan); row[`average ${TYPE_LABEL[plan.cancer_type]} trials within 60 road-miles (trials; population-weighted, residents 55+)`] = nz(v) ? 'not in the data' : `${v} trials`; }
  base.table = [row]; base.rows = [{ id: r.id, level, name: r.name, geoid: r.geoid || null, state: r.state || null }];
  const split = (level === 'state' || level === 'national') && !nz(METRICS.nonmetro_lt20.get(r)) && (plan.rural || /^(non)?metro_/.test(key) || plan.metric === 'nonmetro_pct') ? { nonmetro: fmtVal('nonmetro_lt20', METRICS.nonmetro_lt20.get(r)), metro: fmtVal('metro_lt20', METRICS.metro_lt20.get(r)), nonmetro_mean: fmtVal('nonmetro_mean', METRICS.nonmetro_mean.get(r)), metro_mean: fmtVal('metro_mean', METRICS.metro_mean.get(r)) } : null;
  base.answer_facts = { kind: 'lookup', level, name: r.name, metric: key, label: metricLabel(key, plan), value: fmtVal(key, METRICS[key].get(r, plan), plan), metricAbsent, split, substituted: base.substituted || null, level_note: plan.level_note || null, via: place.via || null, pct_lt20: fmtVal('pct_lt20', r.pct_lt20_trials_within_60rdmi), trials_here: r.trials_listed_here, med_nci: r.median_road_mi_nci, nearest_nci: METRICS.nearest_nci.get(r), member: memberText(r), senators: senatorsText(r), pop55: fmtInt(r.pop55) };
  if (['inc', 'inc_cases', 'mort', 'mort_deaths'].includes(key)) smallNumbersCaveat([r], plan, base); if (level === 'district') vacantCaveat([r], base);
  base.sources = sourcesFor(level, [r]); base.view = viewFor(plan, level, [r], key, {}); return base;
}

function doCompare(plan, data, base) {
  const found = plan.places.map(p => ({ p, r: rowOf(p, data) })).filter(x => x.r); const missing = plan.places.filter(p => !found.some(f => f.p === p));
  if (found.length < 2) { base.answer_facts = { kind: 'unknown_place', name: missing.map(p => p.name).join(', ') || 'the second place' }; return base; }
  let key = plan.metric; if (found.some(f => f.p.kind === 'county') && key === 'type_trials') { key = 'wmean60'; typeCaveat(plan, base); }
  const cols = [key, 'pct_lt20', 'pct_zero', 'wmean60', 'trials_here', 'med_nci', 'pct_gt60_nci'].filter((k, i, a) => a.indexOf(k) === i);
  base.table = found.map(({ p, r }) => { const o = { place: r.name, level: p.kind, 'residents 55+': fmtInt(r.pop55) }; for (const k of cols) { const v = METRICS[k].get(r, plan); o[colLabel(k, plan, r)] = fmtVal(k, v, plan); } if (plan.cancer_type && p.kind !== 'county') { const v = METRICS.type_trials.get(r, plan); o[`average ${TYPE_LABEL[plan.cancer_type]} trials within 60 road-miles`] = nz(v) ? 'not in the data' : `${v} trials`; } return o; });
  base.rows = found.map(({ p, r }) => ({ id: r.id, level: p.kind, name: r.name, geoid: r.geoid || null, state: r.state || null }));
  if (missing.length) base.caveats.push(`${missing.map(p => p.name).join(', ')}: not found in the data.`);
  const finest = ['county', 'district', 'state', 'national'].find(l => found.some(f => f.p.kind === l)); const fin = found.filter(f => f.p.kind === finest).map(f => f.r);
  const common = [...new Set(found.map(f => f.r.state).filter(Boolean))]; const vplan = { ...plan, state: common.length === 1 ? common[0] : null, level: finest };
  base.answer_facts = { kind: 'compare', metric: key, label: metricLabel(key, plan), items: found.map(({ r }) => ({ name: r.name, v: fmtVal(key, METRICS[key].get(r, plan), plan), pct: fmtVal('pct_lt20', r.pct_lt20_trials_within_60rdmi) })) };
  base.sources = found.map(({ p, r }) => ({ title: r.name, url: SITE_BASE + levelFile(p.kind, r) }));
  base.view = viewFor(vplan, finest, fin, key, { keepNational: false }); if (fin.length > 1 && finest !== 'national') { const u = new URLSearchParams(base.view.qs); u.delete('c'); u.delete('d'); if (finest !== 'state' && common.length === 1) u.set('s', common[0]); base.view.qs = u.toString(); }
  return base;
}

function predicate(plan, key) {
  const t = plan.threshold || { op: '>=', value: 50, unit: '%' }; const M = METRICS[key]; const v = r => M.get(r, plan); const x = t.value;
  if (t.op === 'absent') return { test: r => !nz(v(r)), text: key === 'no_route_broad' ? 'there is no road route to a county with 100+ recruiting trials (its median road-miles is null)' : 'there is no road route to an NCI-designated center (its median road-miles is null)', assumed: false };
  if (t.op === 'between') return { test: r => !nz(v(r)) && v(r) >= x && v(r) <= t.hi, text: `the ${metricLabel(key, plan)} is between ${x}${M.unit === '%' ? '%' : ''} and ${t.hi}${M.unit === '%' ? '%' : M.unit ? ' ' + M.unit : ''}`, assumed: false };
  if (plan.onc_no_trials) return { test: r => !!(r.oncologists && r.oncologists.class === 2), text: 'the county has oncologists (CMS) but no recruiting trial', assumed: false };
  const f = { '>': r => v(r) > x, '>=': r => v(r) >= x, '<': r => v(r) < x, '<=': r => v(r) <= x, '==': r => v(r) === x }[t.op] || (r => v(r) >= x);
  return { test: r => !nz(v(r)) && f(r), text: t.every && key === 'pct_zero' ? 'every resident 55+ has no recruiting trial within 60 road-miles (share with none = 100%)' : t.every ? `every resident 55+ has fewer than 20 recruiting trials within 60 road-miles (share = 100%)` : `the ${metricLabel(key, plan)} is ${({ '>': 'more than', '>=': 'at least', '<': 'less than', '<=': 'at most', '==': 'exactly' })[t.op]} ${x}${M.unit === '%' ? '%' : M.unit ? ' ' + (x === 1 && /s$/.test(M.unit) ? M.unit.slice(0, -1) : M.unit) : ''}`, assumed: !!t.assumed };
}
// rows that satisfy a predicate are listed largest-first for "more than" rules and smallest-first for "fewer than" rules
function sortByRule(rows, key, plan) { const M = METRICS[key]; if (M.text) return rows.slice().sort(byPop); const op = plan.threshold && plan.threshold.op; const asc = op === '<' || op === '<='; return rows.slice().sort((a, b) => (asc ? 1 : -1) * (M.get(a, plan) - M.get(b, plan)) || byPop(a, b)); }
const ruleWord = plan => !plan.threshold || plan.threshold.op === '==' || plan.threshold.op === 'absent' || plan.onc_no_trials && plan.threshold.op === '>' && plan.threshold.unit !== 'oncologists' ? null : (plan.threshold.op === '<' || plan.threshold.op === '<=') ? 'Lowest' : 'Highest';
function thresholdMetric(plan, rows, base) {
  let key = plan.metric; const t = plan.threshold; if (!t || t.op === 'absent' || plan.onc_no_trials) return key;
  // the unit of the number names the field when it disagrees with the metric phrase ("counties with fewer than 5 trials")
  if (t.unit === 'trials' && !['trials_here', 'wmean60', 't60', 'type_trials'].includes(key)) key = 'trials_here';
  if (t.unit === 'road-miles' && !['med_nci', 'med_broad', 'rn_center', 'rb_center', 'rl_center'].includes(key)) key = 'med_nci';
  if (t.unit === 'hours' && !['hn', 'hb'].includes(key)) key = 'hn';
  if (t.unit === 'oncologists' && !['onc', 'onc60'].includes(key)) key = 'onc';
  if (t.unit === 'sites' && !['facilities', 'f60'].includes(key)) key = 'facilities';
  if (t.unit === 'people' && key === 'pct_lt20') key = 'people_lt20';
  if (t.unit === 'count' && METRICS[key].unit === '%') key = 'trials_here';
  if (t.unit === '%' && METRICS[key].unit !== '%') key = { trials_here: 'pct_lt20', wmean60: 'pct_lt20', onc: 'pct_lt20', facilities: 'pct_lt20', med_nci: 'pct_gt60_nci', med_broad: 'pct_gt60_broad', hn: 'pct_gt60_nci' }[key] || 'pct_lt20';
  if (!METRICS[key].levels.includes(plan.level)) key = 'pct_lt20';
  if (absentCaveat(key, rows, plan, base)) key = 'pct_lt20';
  return key;
}
function doCount(plan, data, base) {
  const level = plan.level === 'national' ? 'county' : plan.level; plan = { ...plan, level }; let rows = filterScope(rowsFor(level, data), { ...plan, onc_no_trials: false }, base); const key = thresholdMetric(plan, rows, base); const P = predicate(plan, key);
  const hit = rows.filter(P.test); const pop = hit.reduce((s, r) => s + (r.pop55 || 0), 0); const short = hit.reduce((s, r) => s + (r.people_lt20_trials_within_60rdmi || 0), 0); const missing = rows.filter(r => nz(METRICS[key].get(r, plan))).length;
  const scope = plan.state ? STATES[plan.state] : 'the United States'; const rule = `${LEVEL_NOUN[level]} in ${scope} where ${P.text}`;
  base.summary = { rule, counts: { [`${LEVEL_NOUN[level]} matching`]: hit.length, [`${LEVEL_NOUN[level]} in scope`]: rows.length, 'residents 55+ in the matching places (sum)': pop, 'residents 55+ with fewer than 20 trials within 60 road-miles in them (sum)': short } };
  if (plan.threshold && plan.threshold.every && key === 'pct_zero') { const some = rows.filter(r => { const z = METRICS.pct_zero.get(r); return z > 0 && z < 100; }).length; base.summary.counts[`${LEVEL_NOUN[level]} where some but not all residents 55+ have no trial within 60 road-miles`] = some; base.answer_facts_some = some; }
  const ordered = (plan.threshold && plan.threshold.op === '==') ? sortWorst(hit, 'pct_lt20', plan, 'worst') : sortByRule(hit, key, plan); const ex = ordered.slice(0, 5);
  const capped = setList(base, level, ordered, 5, r => tableRow(level, r, plan, key, []), ruleWord(plan) ? `${ruleWord(plan).toLowerCase()} values first` : 'most residents 55+ with fewer than 20 trials first');
  base.answer_facts = { kind: 'count', level, scope, rule, count: hit.length, of: rows.length, pop: fmtInt(pop), short: fmtInt(short), assumed: P.assumed, word: ruleWord(plan), some: base.answer_facts_some, examples: (plan.threshold && plan.threshold.op === '==') ? [] : ex.map(r => ({ name: r.name, v: fmtVal(key, METRICS[key].get(r, plan), plan) })), among: (plan.threshold && plan.threshold.op === '==') ? ex.slice(0, 3).map(r => `${r.name} (${fmtInt(r.pop55)} residents 55+)`) : [], metric: key };
  if (P.assumed) base.caveats.push(`The question gave no cut-off, so the rule used is "${P.text}" (the map's default low-access threshold is half of residents 55+).`);
  if (missing) base.caveats.push(`${missing} ${LEVEL_NOUN[level]} have no value for this measure and are not counted.`);
  base.sources = [{ title: `all_${{ county: 'counties', district: 'districts', state: 'states' }[level]}.json`, url: SITE_BASE + `api/all_${{ county: 'counties', district: 'districts', state: 'states' }[level]}.json` }];
  base.view = viewFor({ ...plan, level }, level, capped, key, { stateScope: true, ...(plan.cosponsor && level === 'district' ? { layer: 'cos_ctma_hr' } : {}) }); const u = new URLSearchParams(base.view.qs); u.delete('c'); u.delete('d'); if (level !== 'state' && plan.state) u.set('s', plan.state); base.view.qs = u.toString(); delete base.answer_facts_some; return base;
}
function doThreshold(plan, data, base) {
  const level = plan.level === 'national' ? 'county' : plan.level; plan = { ...plan, level }; let rows = filterScope(rowsFor(level, data), { ...plan, onc_no_trials: false }, base); const key = thresholdMetric(plan, rows, base); const P = predicate(plan, key);
  const hit = sortByRule(rows.filter(P.test), key, plan); const shown = hit.slice(0, Math.min(25, Math.max(plan.n || 15, 10))); const pop = hit.reduce((s, r) => s + (r.pop55 || 0), 0);
  const scope = plan.state ? STATES[plan.state] : 'the United States'; const rule = `${LEVEL_NOUN[level]} in ${scope} where ${P.text}`;
  base.summary = { rule, counts: { [`${LEVEL_NOUN[level]} matching`]: hit.length, [`${LEVEL_NOUN[level]} in scope`]: rows.length, 'residents 55+ in the matching places (sum)': pop } };
  const capped = setList(base, level, hit, shown.length, r => tableRow(level, r, plan, key, (CTX_COLS[level] || []).filter(([k]) => k !== key)), ruleWord(plan) ? `${ruleWord(plan).toLowerCase()} values first` : 'most residents 55+ first');
  base.answer_facts = { kind: 'threshold', level, scope, rule, count: hit.length, of: rows.length, pop: fmtInt(pop), shown: shown.length, word: ruleWord(plan), values: shown.map(r => ({ name: r.name, v: fmtVal(key, METRICS[key].get(r, plan), plan), pop: fmtInt(r.pop55) })), assumed: P.assumed };
  if (hit.length > shown.length) base.caveats.push(`${hit.length} ${LEVEL_NOUN[level]} match; the table lists ${shown.length} of them (${ruleWord(plan) ? ruleWord(plan).toLowerCase() + ' values first' : 'most residents 55+ first'}) and the map outlines ${hit.length > HL_CAP ? `the first ${HL_CAP}` : 'all of them'}.`);
  if (P.assumed) base.caveats.push(`The question gave no cut-off, so the rule used is "${P.text}".`); if (level === 'district') vacantCaveat(shown, base);
  base.sources = sourcesFor(level, shown); base.view = viewFor(plan, level, capped, key, { stateScope: true }); const u = new URLSearchParams(base.view.qs); if (hit.length !== 1) { u.delete('c'); u.delete('d'); if (level !== 'state' && plan.state) u.set('s', plan.state); } base.view.qs = u.toString(); return base;
}

function doRepresents(plan, data, base) {
  const districts = rowsFor('district', data); const states = rowsFor('state', data); const out = []; const seen = new Set(); const facts = { kind: 'represents', items: [], senators: [], asks: plan.flags && plan.flags.cosponsor_words ? true : false, bill: plan.bill || 'ctma_hr' };
  const addD = (r, via) => { if (!r || seen.has(r.id)) return; seen.add(r.id); out.push(r); facts.items.push({ district: r.name, member: r.member && r.member.name ? r.member.name : 'vacant seat', party: r.member && r.member.party || '', status: r.member ? (r.member.ctma_hr3521 || 'none') : 'none', via }); };
  for (const p of plan.places) {
    if (p.kind === 'district') addD(districts.find(r => r.id === p.id), p.via && p.via.member ? `member ${p.via.member}` : null);
    else if (p.kind === 'county') { const ds = districts.filter(r => Array.isArray(r.counties) && r.counties.includes(p.id)); if (!ds.length) base.caveats.push(`${p.name}: no district in the data lists this county.`); for (const d of ds) addD(d, `overlaps ${p.name}`); const st = states.find(s => s.id === p.state); if (st && Array.isArray(st.senators)) facts.senators.push({ state: st.name, text: senatorsText(st) }); }
    else if (p.kind === 'state') { const st = states.find(s => s.id === p.id); if (st) { if (Array.isArray(st.senators) && st.senators.length) facts.senators.push({ state: st.name, text: senatorsText(st), list: st.senators }); else base.caveats.push(`Senators are not in the data file for ${st.name} yet.`); } if (plan.bill !== 'ctma_s') for (const d of districts.filter(r => r.state === p.id)) addD(d, null); }
  }
  if (!out.length && !facts.senators.length) { base.answer_facts = { kind: 'unknown_place', name: plan.places.map(p => p.name).join(', ') || 'that place' }; return base; }
  base.table = out.slice(0, 25).map(r => tableRow('district', r, plan, 'pct_lt20', [['member', 'House member (119th Congress) and H.R. 3521 status']]));
  base.summary = { rule: plan.places[0] && plan.places[0].kind === 'county' ? `House districts that overlap ${plan.places[0].name}` : plan.places[0] && plan.places[0].kind === 'state' ? `the ${plan.places[0].name} delegation` : 'the member and district asked about', counts: { 'House districts': out.length } };
  for (const s of facts.senators) base.summary.counts[`${s.state} senators (S. 4440, Clinical Trial Modernization Act)`] = s.text || 'not in the data';
  if (!out.length && facts.senators.length) base.table = facts.senators.map(s => ({ place: `${s.state} (Senate)`, 'senators (S. 4440, Clinical Trial Modernization Act)': s.text || 'not in the data' }));
  base.rows = (out.length ? out.slice(0, 25) : []).map(r => ({ id: r.id, level: 'district', name: r.name, geoid: r.geoid || null, state: r.state || null }));
  if (!out.length && facts.senators.length) base.rows = facts.senators.map(s => { const st = states.find(x => x.name === s.state); return { id: st ? st.id : s.state, level: 'state', name: s.state, geoid: null, state: st ? st.id : null }; });
  if (out.length > 25) base.caveats.push(`${out.length} districts; the table lists 25.`); vacantCaveat(out, base);
  facts.county = plan.places.find(p => p.kind === 'county'); facts.state = plan.places.find(p => p.kind === 'state');
  base.answer_facts = facts; base.sources = sourcesFor('district', out.slice(0, 25)).concat(facts.senators.map(s => ({ title: s.state, url: SITE_BASE + `api/state/${(states.find(x => x.name === s.state) || {}).id}.json` })));
  const vp = { ...plan, level: 'district', state: out.length ? out[0].state : (plan.places[0] && plan.places[0].state) || null };
  base.view = out.length ? viewFor(vp, 'district', out, 'pct_lt20', { layer: 'cos_ctma_hr' }) : { page: 'map', qs: new URLSearchParams({ u: 'state', m: 'l20', s: vp.state || '' }).toString(), hl: vp.state ? [vp.state] : [], unit: 'state', layer: 'l20' };
  return base;
}
function doCosponsor(plan, data, base) {
  const bill = plan.bill === 'ctma_s' ? 'ctma_s' : 'ctma_hr'; const want = plan.cosponsor || 'yes';
  if (bill === 'ctma_s') {
    let sts = rowsFor('state', data); if (plan.state) sts = sts.filter(s => s.id === plan.state); const have = sts.some(s => Array.isArray(s.senators));
    if (!have) { base.caveats.push('Senate cosponsors (S. 4440) are not in the data files yet.'); base.answer_facts = { kind: 'absent', what: 'Senate cosponsorship of S. 4440' }; base.view = { page: 'map', qs: new URLSearchParams({ u: 'state', m: 'l20', ...(plan.state ? { s: plan.state } : {}) }).toString(), hl: plan.state ? [plan.state] : [], unit: 'state', layer: 'l20' }; return base; }
    const items = []; for (const s of sts) for (const sen of s.senators || []) { const yes = sen.s4440 && sen.s4440 !== 'none'; if (want === 'yes' ? yes : !yes) items.push({ state: s.name, id: s.id, name: sen.name, party: sen.party || '', status: sen.s4440 || 'none', pct: s.pct_lt20_trials_within_60rdmi }); }
    base.summary = { rule: `senators in ${plan.state ? STATES[plan.state] : 'the Senate'} who ${want === 'yes' ? 'cosponsor or sponsor' : 'have not cosponsored'} S. 4440 (Clinical Trial Modernization Act)`, counts: { 'senators matching': items.length, 'senators in scope': sts.reduce((n, s) => n + ((s.senators || []).length), 0) } };
    base.table = items.slice(0, 25).map(i => ({ place: `${i.state} (Senate)`, senator: `${i.name}${i.party ? ` (${i.party})` : ''}`, 'S. 4440 status': i.status === 'none' ? 'not a cosponsor' : i.status, 'share of residents 55+ with fewer than 20 trials within 60 road-miles (%)': `${i.pct}%` }));
    base.rows = base.table.map(t => { const id = (items.find(i => `${i.state} (Senate)` === t.place) || {}).id || (sts.find(s => `${s.name} (Senate)` === t.place) || {}).id; return { id, level: 'state', name: STATES[id] || id, geoid: null, state: id }; });
    const others = plan.state ? sts.flatMap(s => (s.senators || []).filter(sen => want === 'yes' ? !(sen.s4440 && sen.s4440 !== 'none') : (sen.s4440 && sen.s4440 !== 'none')).map(sen => `${sen.name} (${sen.party || '?'})`)) : [];
    if (plan.state && !items.length) base.table.push(...sts.flatMap(s => (s.senators || []).map(sen => ({ place: `${s.name} (Senate)`, senator: `${sen.name}${sen.party ? ` (${sen.party})` : ''}`, 'S. 4440 status': sen.s4440 === 'none' || !sen.s4440 ? 'not a cosponsor' : sen.s4440, 'share of residents 55+ with fewer than 20 trials within 60 road-miles (%)': `${s.pct_lt20_trials_within_60rdmi}%` }))));
    base.answer_facts = { kind: 'cosponsor', bill, want, count: items.length, of: sts.reduce((n, s) => n + ((s.senators || []).length), 0), scope: plan.state ? STATES[plan.state] : 'the Senate', items: items.slice(0, 6).map(i => `${i.name} (${i.party || '?'}, ${i.state}, ${i.pct}% of residents 55+ short of trials)`), others };
    base.sources = sts.slice(0, 25).map(s => ({ title: s.name, url: SITE_BASE + `api/state/${s.id}.json` })); base.view = { page: 'map', qs: new URLSearchParams({ u: 'state', m: 'l20', ...(plan.state ? { s: plan.state } : {}) }).toString(), hl: [...new Set(base.rows.map(r => r.id))], unit: 'state', layer: 'l20' }; return base;
  }
  let rows = rowsFor('district', data); if (plan.state) rows = rows.filter(r => r.state === plan.state); const scopeN = rows.length; const filled = rows.filter(r => r.member && r.member.name).length; const vacant = scopeN - filled;
  const hit = rows.filter(r => r.member && r.member.name && (want === 'yes' ? (r.member.ctma_hr3521 && r.member.ctma_hr3521 !== 'none') : (!r.member.ctma_hr3521 || r.member.ctma_hr3521 === 'none')));
  const sorted = sortWorst(hit, 'pct_lt20', plan, 'worst'); const shown = sorted.slice(0, Math.min(25, Math.max(plan.n || 10, 10)));
  base.summary = { rule: `House districts in ${plan.state ? STATES[plan.state] : 'the United States'} whose member ${want === 'yes' ? 'cosponsors (or sponsors)' : 'has not cosponsored'} H.R. 3521`, counts: { 'districts matching': hit.length, 'seats filled': filled, 'seats vacant': vacant, 'districts in scope': scopeN, 'by party': ['D', 'R', 'I'].map(p => `${p}: ${hit.filter(r => r.member.party === p).length}`).join(', ') } };
  const capped = setList(base, 'district', sorted, shown.length, r => tableRow('district', r, plan, 'pct_lt20', [['member', 'House member (119th Congress) and H.R. 3521 status']]), 'largest share short of trials first');
  base.answer_facts = { kind: 'cosponsor', bill, want, count: hit.length, of: filled, districts: scopeN, vacant, scope: plan.state ? STATES[plan.state] : 'the House', items: shown.slice(0, 6).map(r => `${r.member.name || 'vacant'} (${r.member.party || '?'}, ${r.name})`), parties: ['D', 'R', 'I'].map(p => [p, hit.filter(r => r.member.party === p).length]).filter(x => x[1]) };
  if (hit.length > shown.length) base.caveats.push(`${hit.length} districts match; the table lists the ${shown.length} with the largest share short of trials and the map outlines ${hit.length > HL_CAP ? `the first ${HL_CAP}` : 'all of them'}.`); vacantCaveat(rows, base);
  base.sources = sourcesFor('district', shown).concat([{ title: 'all_districts.json', url: SITE_BASE + 'api/all_districts.json' }]);
  base.view = viewFor({ ...plan, level: 'district' }, 'district', capped, 'pct_lt20', { layer: 'cos_ctma_hr', stateScope: true }); const u = new URLSearchParams(base.view.qs); if (hit.length !== 1) { u.delete('d'); if (plan.state) u.set('s', plan.state); } base.view.qs = u.toString(); return base;
}

function doNeed(plan, data, base) {
  const need = plan.need || { measure: 'inc', site: 'all', crit: 'l20', thr: 50 }; const measure = need.measure === 'mort' ? 'mort' : 'inc'; const site = need.site || 'all'; const crit = need.crit === 'z60' ? 'z60' : 'l20'; const thr = [25, 50, 75].includes(need.thr) ? need.thr : 50;
  let rows = filterScope(rowsFor('county', data), { ...plan, level: 'county', cosponsor: null }, base); const scopeN = rows.length;
  const flagKey = measure === 'mort' ? 'mortality_top_third' : 'incidence_above_county_median'; const rateKey = measure; const accessKey = crit === 'z60' ? 'pct_zero' : 'pct_lt20';
  const scope = plan.state ? STATES[plan.state] : 'the United States'; const critText = crit === 'z60' ? 'no recruiting trial' : 'fewer than 20 recruiting trials';
  const haveFlag = rows.some(r => typeof r[flagKey] === 'boolean');
  const vplan = { ...plan, level: 'county', site, metric: measure, cancer_type: null, rural: null }; const extra = { crit, ...(thr !== 50 ? { thr } : {}), ...(site !== 'all' ? { site } : {}) };
  base.view = viewFor(vplan, 'county', [], measure === 'mort' ? 'mort' : 'inc', { layer: measure === 'mort' ? 'mva' : 'bva', tab: 'burden', extra }); { const u = new URLSearchParams(base.view.qs); u.delete('site'); if (site !== 'all') u.set('site', site); if (plan.state) u.set('s', plan.state); base.view.qs = u.toString(); }
  if (!haveFlag) { base.caveats.push(`The ${measure === 'mort' ? 'deaths' : 'incidence'}-vs-access classification (${flagKey}) is not in the data files yet; the map's Need vs access tab shows it.`); base.answer_facts = { kind: 'absent', what: `the ${measure === 'mort' ? 'deaths' : 'incidence'}-vs-access classification`, scope }; base.sources = [{ title: 'all_counties.json', url: SITE_BASE + 'api/all_counties.json' }]; return base; }
  const classified = rows.filter(r => typeof r[flagKey] === 'boolean' && !nz(METRICS[accessKey].get(r)));
  const cell = classified.filter(r => r[flagKey] === true && METRICS[accessKey].get(r) >= thr);
  const rate = r => METRICS[rateKey].get(r, { site }); const sorted = cell.slice().sort((a, b) => ((rate(b) || 0) - (rate(a) || 0)) || byPop(a, b)); const shown = sorted.slice(0, Math.min(25, Math.max(plan.n || 10, 10)));
  const pop = cell.reduce((s, r) => s + (r.pop55 || 0), 0); const events = cell.reduce((s, r) => s + ((measure === 'mort' ? METRICS.mort_deaths.get(r) : METRICS.inc_cases.get(r)) || 0), 0);
  const rule = `counties in ${scope} with ${measure === 'mort' ? `an all-sites cancer death rate in the top third of US counties` : `all-sites cancer incidence above the median of US counties`} AND at least ${thr}% of residents 55+ with ${critText} within 60 road-miles`;
  const rateLab = `${SITE_LABEL[site]} ${measure === 'mort' ? 'death rate' : 'incidence'} (per 100,000, age-adjusted; ${measure === 'mort' ? 'deaths 2020-2024' : 'cases 2019-2023'})`;
  base.summary = { rule, counts: { 'counties matching': cell.length, 'counties classified': classified.length, 'counties in scope': scopeN, 'residents 55+ in the matching counties (sum)': pop, [measure === 'mort' ? 'cancer deaths a year in them, all sites (sum)' : 'new cancer cases a year in them, all sites (sum)']: Math.round(events) } };
  const capped = setList(base, 'county', sorted, shown.length, r => { const o = { place: r.name }; o[rateLab] = nz(rate(r)) ? 'not in the data' : `${rate(r)}`; const ev = measure === 'mort' ? METRICS.mort_deaths.get(r) : METRICS.inc_cases.get(r); o[measure === 'mort' ? 'cancer deaths a year, all sites' : 'new cancer cases a year, all sites'] = fmtInt(ev); o[`share of residents 55+ with ${critText} within 60 road-miles (%)`] = fmtVal(accessKey, METRICS[accessKey].get(r)); o['residents 55+'] = fmtInt(r.pop55); o['recruiting trials with a site in the county'] = fmtInt(r.trials_listed_here); o['median road-miles to the nearest NCI center'] = nz(r.median_road_mi_nci) ? 'no road route' : `${r.median_road_mi_nci} road-miles`; if (r[measure === 'mort' ? 'mortality' : 'incidence'] && r[measure === 'mort' ? 'mortality' : 'incidence'].small_numbers) o[rateLab] += ' (small numbers)'; return o; }, 'highest rate first');
  base.answer_facts = { kind: 'need', measure, site, crit, thr, scope, rule, count: cell.length, classified: classified.length, of: scopeN, pop: fmtInt(pop), events: fmtInt(Math.round(events)), examples: shown.slice(0, 3).map(r => ({ name: r.name, rate: rate(r), access: fmtVal(accessKey, METRICS[accessKey].get(r)) })) };
  if (site !== 'all') base.caveats.push(`The high-${measure === 'mort' ? 'death-rate' : 'incidence'} test uses the all-sites rate (the by-site cut-offs are not in the data files); the ${SITE_LABEL[site]} rate is shown for each county and the map opens on that site.`);
  if (classified.length < scopeN) base.caveats.push(`${scopeN - classified.length} counties have no published rate or access share and are not classified.`); smallNumbersCaveat(shown, { ...plan, metric: measure }, base);
  if (cell.length > shown.length) base.caveats.push(`${cell.length} counties match; the table lists the ${shown.length} with the highest rate and the map outlines ${cell.length > HL_CAP ? `the first ${HL_CAP}` : 'all of them'}.`);
  base.sources = sourcesFor('county', shown).concat([{ title: 'all_counties.json', url: SITE_BASE + 'api/all_counties.json' }]); base.view.hl = capped.map(r => r.id); return base;
}

function doByType(plan, data, base) {
  const place = plan.places[0]; const r = rowOf(place, data); if (!r) { base.answer_facts = { kind: 'unknown_place', name: place.name }; return base; }
  const bt = r.trials_within_60rdmi_by_cancer_type;
  if (!bt || typeof bt !== 'object') { typeCaveat({ ...plan, cancer_type: plan.cancer_type || 'lung', level: place.kind }, base); base.caveats.pop(); base.caveats.push('Trial counts by cancer type are published for districts, states and the nation only; counties have no by-type field. The county is shown with its all-cancer figures.'); return doLookup({ ...plan, metric: 'wmean60', shape: 'lookup' }, data, base); }
  const items = Object.entries(bt).filter(([k, v]) => !nz(v)).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  base.table = [{ place: r.name, 'cancer type': 'all cancer trials', 'average recruiting trials for that type within 60 road-miles (trials; population-weighted, residents 55+)': fmtVal('wmean60', r.wmean_trials_within_60rdmi) }].concat(items.map(([k, v]) => ({ place: r.name, 'cancer type': TYPE_LABEL[k] || k, 'average recruiting trials for that type within 60 road-miles (trials; population-weighted, residents 55+)': `${v} trials` })));
  base.rows = [{ id: r.id, level: place.kind, name: r.name, geoid: r.geoid || null, state: r.state || null }];
  base.answer_facts = { kind: 'bytype', name: r.name, items: items.map(([k, v]) => ({ type: TYPE_LABEL[k] || k, v })), all: r.wmean_trials_within_60rdmi };
  base.sources = sourcesFor(place.kind, [r]); base.view = viewFor({ ...plan, cancer_type: null }, place.kind, [r], 'wmean60', {}); return base;
}

function doSearch(plan, data, base) {
  const s = plan.search || {}; const type = TYPES.includes(s.cancer_type) ? s.cancer_type : null; const label = type ? TYPE_LABEL[type] : 'cancer';
  if (/^\d{5}$/.test(s.zip || '')) {
    const p = new URLSearchParams({ zip: s.zip }); if (type) p.set('type', type); if (s.keyword) p.set('q', String(s.keyword).slice(0, 60)); if (s.age) p.set('age', String(s.age)); if ([30, 120, 200].includes(+s.radius)) p.set('mi', String(s.radius));
    const county = s.zip_county && Array.isArray(data.counties) ? data.counties.find(r => r.id === s.zip_county) : null;
    base.answer_facts = { kind: 'search', zip: s.zip, label, keyword: s.keyword || null, radius: [30, 120, 200].includes(+s.radius) ? +s.radius : 60, county: county ? county.name : null, trials_here: county ? county.trials_listed_here : null, wmean: county ? county.wmean_trials_within_60rdmi : null };
    if (county) { base.table = [{ place: county.name, 'recruiting trials with a site in the county': fmtInt(county.trials_listed_here), 'average trials within 60 road-miles (population-weighted, residents 55+)': fmtInt(county.wmean_trials_within_60rdmi), note: `ZIP ${s.zip} is in ${county.name}`, 'finder radius (miles)': String(base.answer_facts.radius) }]; base.rows = [{ id: county.id, level: 'county', name: county.name, state: county.state }]; base.sources = [{ title: county.name, url: SITE_BASE + `api/county/${county.id}.json` }]; }
    base.sources.unshift({ title: 'Trial finder', url: SITE_BASE + 'find.html?' + p }); base.view = { page: 'find', qs: p.toString(), hl: [] }; return base;
  }
  if (s.city_county && Array.isArray(data.counties)) {
    const county = data.counties.find(r => r.id === s.city_county);
    if (county) { const p = new URLSearchParams({ c: county.id, tab: 'trials' }); if (type) p.set('type', type);
      base.answer_facts = { kind: 'search_city', city: s.city, state: STATES[s.state] || s.state, county: county.name, trials_here: county.trials_listed_here, wmean: county.wmean_trials_within_60rdmi, label };
      base.table = [{ place: county.name, 'recruiting trials with a site in the county': fmtInt(county.trials_listed_here), 'average trials within 60 road-miles (population-weighted, residents 55+)': fmtInt(county.wmean_trials_within_60rdmi), note: `${s.city}, ${STATES[s.state] || s.state} is in ${county.name}` }]; base.rows = [{ id: county.id, level: 'county', name: county.name, state: county.state }];
      base.sources = [{ title: county.name, url: SITE_BASE + `api/county/${county.id}.json` }]; p.set('m', 't'); base.view = { page: 'map', qs: p.toString(), hl: [county.id], unit: 'county', layer: 't' }; return base; }
  }
  if (s.state && STATES[s.state]) { const p = new URLSearchParams({ u: 'state', m: 'l20', s: s.state }); if (type) p.set('type', type); base.answer_facts = { kind: 'search_state', state: STATES[s.state], label: type ? TYPE_LABEL[type] : null }; base.view = { page: 'map', qs: p.toString(), hl: [s.state], unit: 'state', layer: 'l20' }; return base; }
  base.answer_facts = { kind: 'search_none' }; base.sources = [{ title: 'Trial finder', url: SITE_BASE + 'find.html' }]; base.view = { page: 'find', qs: '', hl: [] }; return base;
}
function doAmbiguous(plan, base) { base.ambiguity = plan.ambiguity; base.answer_facts = { ...plan.ambiguity, kind: 'ambiguous', what: plan.ambiguity.kind }; base.table = (plan.ambiguity.options || []).map(o => ({ place: o.name, state: STATES[o.state] || o.state, id: o.id })); base.view = null; return base; }

// ---------- the deterministic answer ----------
export function composeAnswer(plan, result) {
  const f = (result && result.answer_facts) || {}; const asOf = result && result.data_as_of ? ` Data as of ${result.data_as_of}.` : '';
  const route = (result && result.route) || (plan && plan.route);
  if (route === 'scope') return SCOPE();
  if (route === 'other') return OTHER();
  const joinV = items => items.map((x, i) => `${x.name} (${x.v})`).join(i => ', ');
  const list = items => items.map(x => `${x.name} ${x.v}`).join('; ');
  switch (f.kind) {
    case 'ranking': { if (!f.values.length) return `No ${LEVEL_NOUN[f.level]} in ${f.scope} have a value for ${f.label}.${asOf}`; const high = f.order === 'worst' ? metricWorse(f.metric, plan) === 'high' : metricWorse(f.metric, plan) !== 'high'; const dir = f.countish ? (high ? 'most' : 'fewest') : (high ? 'highest' : 'lowest'); const noun = f.countish ? f.label.replace(/^(share of |average |median )/, '') : f.label;
      const pre = f.level_note ? `${capital(metricLabel(f.level_note.metric, plan))} is published for ${LEVEL_NOUN[f.level_note.used]} only, not ${LEVEL_NOUN[f.level_note.asked]}; here are the ${LEVEL_NOUN[f.level_note.used]}${plan.state ? ` in ${STATES[plan.state]}` : ''} instead. ` : f.type_fallback ? `Trial counts by cancer type are published for districts and states only; here are the counties ranked by all-cancer trials within 60 road-miles (the map opens with the ${TYPE_LABEL[plan.cancer_type] || 'type'} filter set). ` : '';
      const scope = f.of === 1 ? f.scopeText.replace(/^(\w+)/, (m) => ({ counties: 'county', districts: 'district', states: 'state' })[m] || m) : f.scopeText;
      if (f.tied) return `${pre}${fmtInt(f.tied)} of the ${f.of} ${scope} tie at the ${dir === 'most' || dir === 'highest' ? 'top' : 'bottom'} with ${f.firstVal}; the ${f.n} most populous of them are: ${list(f.values)}.${asOf}`;
      return `${pre}Of the ${f.of === 1 ? 'one' : f.of} ${scope}, the ${f.n === 1 ? 'one' : f.n} with the ${dir} ${noun} ${f.n === 1 ? 'is' : 'are'}: ${list(f.values)}.${asOf}`; }
    case 'lookup': { let s = f.substituted ? `${capital(f.substituted.asked)} is published for ${f.substituted.levels} only; the closest published measure for ${f.name} is ${f.substituted.used}. ` : f.level_note ? `${capital(metricLabel(f.level_note.metric, plan))} is published for ${LEVEL_NOUN[f.level_note.used]} only, so here is ${f.name}. ` : ''; s += f.via && f.via.zip ? `ZIP ${f.via.zip} is in ${f.name}. ` : f.via && f.via.city ? `${f.via.city} is in ${f.name}. ` : ''; if (f.metricAbsent) s += `${f.name}: ${f.label} is not in the data file. `; else s += `${f.name}: ${f.label} is ${f.value}. `; if (f.metric !== 'pct_lt20') s += `${f.pct_lt20} of its ${f.pop55} residents 55+ have fewer than 20 recruiting trials within 60 road-miles`; else s += `It has ${f.pop55} residents 55+`; if (!nz(f.trials_here)) s += `; ${fmtInt(f.trials_here)} recruiting trials list a site in the ${f.level === 'national' ? 'country' : f.level}`; if (f.nearest_nci && f.level !== 'national') s += `; the nearest NCI-designated center is ${f.nearest_nci}${nz(f.med_nci) ? '' : ` (median ${f.med_nci} road-miles)`}`; else if (f.level === 'national' && !nz(f.med_nci)) s += `; the median road distance to an NCI-designated center is ${f.med_nci} road-miles`; s += '.'; if (f.split) s += ` Nonmetro (rural) residents 55+: ${f.split.nonmetro} have fewer than 20 trials within 60 road-miles (average ${f.split.nonmetro_mean} nearby); metro residents: ${f.split.metro} (average ${f.split.metro_mean}).`; if (f.member) s += ` House member: ${f.member}.`; if (f.senators) s += ` Senators: ${f.senators}.`; return s + asOf; }
    case 'compare': return `${f.label[0].toUpperCase() + f.label.slice(1)}: ${f.items.map(i => `${i.name} ${i.v}`).join('; ')}.${f.metric !== 'pct_lt20' ? ` Share of residents 55+ with fewer than 20 trials within 60 road-miles: ${f.items.map(i => `${i.name} ${i.pct}`).join('; ')}.` : ''}${asOf}`;
    case 'count': return `${f.count} of the ${f.of} ${f.rule.split(' where ')[0]} are places where ${f.rule.split(' where ')[1]}; together they have ${f.pop} residents 55+${f.metric === 'pct_lt20' || f.metric === 'people_lt20' ? ` (${f.short} of them with fewer than 20 trials within 60 road-miles)` : ''}.${f.some !== undefined && f.some !== null ? ` A further ${f.some} ${f.rule.split(' in ')[0]} in scope have some, but not all, residents 55+ with no trial within 60 road-miles.` : ''}${f.examples.length ? ` ${f.word || 'Highest'}: ${list(f.examples)}.` : f.among && f.among.length ? ` Among them: ${f.among.join('; ')}.` : ''}${asOf}`;
    case 'threshold': return `${f.count} of the ${f.of} ${f.rule.split(' where ')[0]} are places where ${f.rule.split(' where ')[1]}; together they have ${f.pop} residents 55+.${f.values.length && f.word ? ` ${f.word}: ${list(f.values.slice(0, 5))}.` : f.values.length ? ` Among them: ${f.values.slice(0, 5).map(x => `${x.name} (${x.pop} residents 55+)`).join('; ')}.` : ''}${asOf}`;
    case 'represents': { const parts = []; if (f.county) parts.push(`${f.county.name} is in ${f.items.length === 1 ? 'one House district' : `${f.items.length} House districts`}: ${f.items.map(i => `${i.district}, ${i.member}${i.party ? ` (${i.party})` : ''}, ${statusText(i.status)} H.R. 3521`).join('; ')}.`); else if (f.items.length) parts.push(f.items.map(i => `${i.district} is represented by ${i.member}${i.party ? ` (${i.party})` : ''}, ${statusText(i.status)} H.R. 3521 (Clinical Trial Modernization Act)`).join('. ') + '.'); for (const s of f.senators) parts.push(`${s.state} senators: ${s.text || 'not in the data'}.`); return parts.join(' ') + asOf; }
    case 'cosponsor': { const b = BILLS[f.bill] || BILLS.ctma_hr; return `${f.count} of the ${f.of} ${f.bill === 'ctma_s' ? 'senators' : `House members${f.vacant ? ` (${f.districts} districts, ${f.vacant} ${f.vacant === 1 ? 'seat' : 'seats'} vacant)` : ''}`} in ${f.scope} ${f.want === 'yes' ? 'cosponsor or sponsor' : 'have not cosponsored'} ${b.label} (${b.short})${f.parties && f.parties.length ? ` (${f.parties.map(([p, c]) => `${p}: ${c}`).join(', ')})` : ''}.${f.items.length ? ` ${f.count > f.items.length ? 'Among them' : 'They are'}: ${f.items.join('; ')}.` : ''}${f.others && f.others.length ? ` ${f.want === 'yes' ? 'Not cosponsoring' : 'Cosponsoring'}: ${f.others.join('; ')}.` : ''}${asOf}`; }
    case 'need': return `${f.count} of the ${f.classified} classified counties in ${f.scope} (${f.of} in scope) have ${f.measure === 'mort' ? 'an all-sites cancer death rate in the top third of US counties' : 'all-sites cancer incidence above the US county median'} and at least ${f.thr}% of residents 55+ with ${f.crit === 'z60' ? 'no recruiting trial' : 'fewer than 20 recruiting trials'} within 60 road-miles; together they have ${f.pop} residents 55+ and about ${f.events} ${f.measure === 'mort' ? 'cancer deaths' : 'new cancer cases'} a year.${f.examples.length ? ` Highest ${SITE_LABEL[f.site]} rate: ${f.examples.map(e => `${e.name} ${e.rate} per 100,000 (${e.access} low access)`).join('; ')}.` : ''}${asOf}`;
    case 'bytype': return `${f.name}: average recruiting trials within 60 road-miles by cancer type, highest first: ${f.items.slice(0, 8).map(i => `${i.type} ${i.v}`).join('; ')}${f.items.length > 8 ? '; and more in the table' : ''}. All cancer trials: ${f.all}.${asOf}`;
    case 'search': return `Opening the trial finder for ZIP ${f.zip}: recruiting ${f.label} trials within about ${f.radius} miles${f.keyword ? `, matching "${f.keyword}"` : ''}.${f.county ? ` ZIP ${f.zip} is in ${f.county}, where ${fmtInt(f.trials_here)} recruiting trials list a site and residents have on average ${fmtInt(f.wmean)} within 60 road-miles.` : ''} Trials are listed, not matched; the study team decides eligibility.`;
    case 'search_city': return `${f.city}, ${f.state} is in ${f.county}. ${fmtInt(f.trials_here)} recruiting trial${f.trials_here === 1 ? '' : 's'} list a site in the county, and residents there have on average ${fmtInt(f.wmean)} within 60 road-miles. Opening the county's trial list${f.label !== 'cancer' ? ` filtered to ${f.label} trials` : ''}; for a list by driving distance, use the finder with a ZIP code.`;
    case 'search_state': return `Opening ${f.state} on the map${f.label ? ` filtered to ${f.label} trials` : ''}. For trials near a specific place, give a ZIP code.`;
    case 'search_none': return 'To list trials near a place, give a ZIP code (for example "lung cancer trials near 78501") or a town and state.';
    case 'ambiguous': { const what = f.what === 'member' ? 'Several members of Congress have that name' : f.what === 'city' ? 'Several places have that name' : `More than one county is called "${titleCase(f.phrase || 'that')}"`; return `${what}: ${f.options.map(o => `${o.name}${f.what === 'county' ? '' : ` (${STATES[o.state] || o.state})`}`).join('; ')}${f.total > f.options.length ? '; and others' : ''}. Which do you mean? Name the state in the question.`; }
    case 'territory': return `${f.name} is not in the data: the map covers the states and the District of Columbia only (trial sites there are not counted).`;
    case 'unknown_place': return f.zip ? `ZIP ${f.zip} is not in the ZIP-to-county file, so it cannot be placed. Check the ZIP or give the county.` : `No place called "${f.name}" is in the data. Try the county, district (e.g. TX-34) or state name as it appears on the map.`;
    case 'absent': return `${f.what[0].toUpperCase() + f.what.slice(1)} is not in the published data files yet${f.scope ? ` for ${f.scope}` : ''}, so there is nothing to report from the files.${asOf}`;
    case 'error': return 'The question could not be run against the data files. Try naming the place and the measure (for example "which Ohio counties have the most residents short of trials?").';
    default: return OTHER();
  }
}
const statusText = s => s === 'none' || !s ? 'not a cosponsor of' : s === 'sponsor' ? 'sponsor of' : s === 'original' ? 'original cosponsor of' : 'cosponsor of';
const titleCase = s => String(s).replace(/\b[a-z]/g, c => c.toUpperCase());
let SCOPE = () => '', OTHER = () => ''; export function setFixedTexts(scope, other) { SCOPE = () => scope; OTHER = () => other; }

// ---------- verification of model text ----------
const NUM_RE = /\d[\d,]*(?:\.\d+)?/g;
export function numbersIn(s) { const out = []; let m; const re = new RegExp(NUM_RE.source, 'g'); while ((m = re.exec(String(s)))) out.push(m[0].replace(/,/g, '')); return out; }
const NUMBER_WORDS = /\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|hundreds|thousand|thousands|million|millions|billion|billions|half|third|thirds|quarter|quarters|dozen|dozens)\b/gi;
const CAP_STOP = new Set('The A An In Of On At By For With From To And Or But Among Across About Data These Those This That It Its They Their There Here Only Both All No None Not Residents Share Average Median Nearest Most Fewest Highest Lowest Overall Statewide Nationally Nationwide Together Each Every Some Many Few Several Other Others Another Than When Where Which While Although However Also Still Yet Just Nearly About Around Roughly Over Under Up Down As If So Then Now Today Trials Trial Cancer County Counties District Districts State States House Senate Members Member Oncologists NCI ACS CMS RUCC USDA ERS H.R S Act Congress Clinical Modernization Medicare Road Miles Within Fewer Less More Recruiting Shares People Percent Per Rate Rates Deaths Death Incidence Mortality Seats Seat Vacant Filled Yes Its United America American Americans Nonmetro Metro Rural Urban Senators Senator Representative Rep Sen Dr Mr Ms Mrs Jr Sr'.split(' '));
export function verifyAnswer(text, table, extraAllowed) {
  const t = String(text || ''); const bad = [];
  if (!t.trim()) return { ok: false, badNumbers: ['(empty)'] };
  if (t === SCOPE() || t === OTHER()) return { ok: true, badNumbers: [] };
  if (/https?:\/\/|www\.|[a-z0-9-]\.(com|org|net|io|gov\/)/i.test(t.replace(/clinicaltrials\.gov/gi, ''))) bad.push('(url)');
  if (/\b(as an ai|i am an ai|i'm an ai|language model|i cannot|i can't|i'm sorry|i am sorry|i think|i believe|i recommend|i would|i'd)\b/i.test(t)) bad.push('(first person)');
  if (/\b(should|recommend|recommended|advise|advised|consult your|talk to your|you should|you may want|consider enrolling|eligible|eligibility)\b/i.test(t) && !/decides eligibility/i.test(t)) bad.push('(advice)');
  if (/\*\*|`|^\s*#|^\s*[-*•]\s|^\s*\d+\.\s|<\/?[a-z]+>/m.test(t)) bad.push('(markdown)');
  // every number in the text must be in the table (same digits, same rounding; thousands separators tolerated)
  const tableText = []; const allowed = new Set(); const addFrom = s => { for (const n of numbersIn(s)) allowed.add(n); };
  const walk = v => { if (v === null || v === undefined) return; if (Array.isArray(v)) v.forEach(walk); else if (typeof v === 'object') { for (const [k, x] of Object.entries(v)) { addFrom(k); tableText.push(k); walk(x); } } else { addFrom(String(v)); tableText.push(String(v)); } };
  walk(table); for (const s of extraAllowed || []) { if (s && typeof s === 'object') walk(s); else { addFrom(s); tableText.push(String(s)); } } for (const c of ['55', '60', '20', '100', '3521', '4440', '119']) allowed.add(c);   // the measures' own definitions (residents 55+, 60 road-miles, fewer than 20, 100+ trials, the bills, the Congress)
  const corpus = tableText.join('\n'); const corpusLc = corpus.toLowerCase();
  for (const m of t.matchAll(/\b(\d+(?:\.\d+)?)\s*(million|billion|thousand|k|m)\b/gi)) if (!allowed.has(m[1])) bad.push(m[0]);
  const nums = numbersIn(t); const tableNums = []; (function w(v) { if (v === null || v === undefined) return; if (Array.isArray(v)) v.forEach(w); else if (typeof v === 'object') { for (const [k, x] of Object.entries(v)) if (!/^(id|geoid|state)$/.test(k)) w(x); } else tableNums.push(...numbersIn(String(v))); })([table, ...(extraAllowed || []).filter(x => x && typeof x === 'object')]);
  if (!tableNums.length) return { ok: bad.length === 0, badNumbers: bad };   // no figures to check against (an ambiguity, a territory, an unknown place): style checks only
  if (!nums.length) bad.push('(no number from the table)');
  for (const n of nums) { if (allowed.has(n)) continue; if (/^0+$/.test(n) && allowed.has('0')) continue; bad.push(n); }
  for (const m of t.matchAll(NUMBER_WORDS)) { const w = m[1].toLowerCase(); if (!new RegExp(`\\b${w}\\b`).test(corpusLc)) bad.push(m[1]); }   // "one million", "half of": number words only when the table itself has them
  // every capitalised word must be in the table (a place, a centre, a member) or be ordinary vocabulary: no re-attributed figures
  for (const m of t.matchAll(/(^|[\s(,;:"'])([A-Z][A-Za-z.'’-]+)/g)) { const w = m[2].replace(/['’]s$/, '').replace(/[.,;:'’]+$/, ''); if (CAP_STOP.has(w) || w.length < 3 || /^[A-Z]{1,2}\.?$/.test(w)) continue; if (corpusLc.includes(w.toLowerCase())) continue; bad.push(`(place not in table: ${w})`); }
  // the first place row must be reported with its own value
  const first = (Array.isArray(table) ? table : []).find(r => r && typeof r === 'object' && (r.place || r.name)); if (first) { const name = String(first.place || first.name).replace(/\s*\(Senate\)$/, ''); if (!t.includes(name) && !t.includes(name.replace(/,.*$/, ''))) bad.push(`(first place missing: ${name})`); else { const vals = Object.entries(first).filter(([k]) => !/^(place|name|level|state|id|note|rule)$/.test(k)).flatMap(([, v]) => numbersIn(v)); if (vals.length && !vals.some(v => nums.includes(v))) bad.push(`(first place's value missing: ${vals[0]})`); } }   // the first row must be reported with at least one of its own figures
  return { ok: bad.length === 0, badNumbers: [...new Set(bad)] };
}
