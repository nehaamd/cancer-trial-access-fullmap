/* "Ask the map" — the helper behind the question box on the Cancer Trial Access Map.
   A question comes in; a small model turns it into a structured plan; this code executes the plan against the site's published
   data files (api/*.json) with ordinary arithmetic; a second model writes two or three sentences from the numbers it is handed.
   The models never compute and never see anything but the question and the table. Every number in an answer carries the file it
   came from, questions outside the data get a fixed reply, and nothing about the visitor is stored. */

const TYPES = ['bladder_urothelial', 'brain_cns', 'breast', 'colorectal', 'gastric_esophageal', 'gynecologic', 'head_neck', 'kidney', 'leukemia', 'liver_biliary', 'lung', 'lymphoma', 'mds_mpn', 'melanoma_skin', 'myeloma', 'neuroendocrine_endocrine', 'pancreatic', 'prostate', 'sarcoma'];
const TYPE_LABEL = { bladder_urothelial: 'bladder & urothelial', brain_cns: 'brain & CNS', breast: 'breast', colorectal: 'colorectal', gastric_esophageal: 'gastric & esophageal', gynecologic: 'gynecologic', head_neck: 'head & neck', kidney: 'kidney', leukemia: 'leukemia', liver_biliary: 'liver & biliary', lung: 'lung & thoracic', lymphoma: 'lymphoma', mds_mpn: 'MDS / MPN', melanoma_skin: 'melanoma & skin', myeloma: 'myeloma', neuroendocrine_endocrine: 'neuroendocrine', pancreatic: 'pancreatic', prostate: 'prostate', sarcoma: 'sarcoma' };
const STATES = { AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California', CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont', VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming' };

// metrics the data route can rank or look up: key in the files -> label, direction ("worse" = higher is worse), map layer code
const METRICS = {
  pct_lt20_trials_within_60rdmi: { label: 'share of residents 55+ with fewer than 20 recruiting trials within 60 road-miles', unit: '%', worse: 'high', layer: 'l20' },
  people_lt20_trials_within_60rdmi: { label: 'residents 55+ with fewer than 20 recruiting trials within 60 road-miles', unit: 'people', worse: 'high', layer: 'l20' },
  pct_zero_trials_within_60rdmi: { label: 'share of residents 55+ with no recruiting trial within 60 road-miles', unit: '%', worse: 'high', layer: 'z60' },
  pct_gt60rdmi_nci: { label: 'share of residents 55+ more than 60 road-miles from an NCI-designated center', unit: '%', worse: 'high', layer: 'g60n' },
  pct_gt60rdmi_broad_menu: { label: 'share of residents 55+ more than 60 road-miles from a county with 100+ trials', unit: '%', worse: 'high', layer: 'g60b' },
  median_road_mi_nci: { label: 'median road-miles to the nearest NCI-designated center', unit: 'miles', worse: 'high', layer: 'medn' },
  median_road_mi_broad_menu: { label: 'median road-miles to the nearest county with 100+ trials', unit: 'miles', worse: 'high', layer: 'g60b' },
  wmean_trials_within_60rdmi: { label: 'average number of recruiting trials within 60 road-miles', unit: 'trials', worse: 'low', layer: 'l20' },
  trials_listed_here: { label: 'recruiting trials with a site in the place', unit: 'trials', worse: 'low', layer: 'l20' },
  cancer_type: { label: 'average number of recruiting trials for that cancer within 60 road-miles', unit: 'trials', worse: 'low', layer: 'l20' },   // needs cancer_type
};

const PLAN_SYSTEM = `You turn one question about cancer clinical trial access in the United States into a JSON plan. You do not answer the question.
The site has: (a) a trial finder by ZIP code with filters (cancer type, age, keyword); (b) data files with these fields for every US county, congressional district and state, for residents aged 55 and older:
${Object.entries(METRICS).filter(([k]) => k !== 'cancer_type').map(([k, m]) => `  ${k}: ${m.label}`).join('\n')}
  trials for one cancer type within 60 road-miles (cancer_type)
  for districts only: the House member's name and party, and whether they cosponsor H.R. 3521 (Clinical Trial Modernization Act)
  nearest NCI-designated center; context: no_vehicle, broadband, uninsured, uninsured_55_64, poverty (ACS, %)
Cancer type keys: ${TYPES.join(', ')}.
Return exactly one JSON object with keys:
  route: "search" (a person wants trials near a place), "data" (a question the fields above can answer), "scope" (eligibility, prognosis, whether to join a trial, treatment advice, a specific person's situation, drug questions), or "other" (anything else, including how the site works, definitions, greetings).
  search: {zip: 5-digit string or null, city: string or null, state: 2-letter code or null, cancer_type: key or null, keyword: short string (a drug, gene or biomarker) or null, age: integer or null, radius: 30|60|120|200 or null}
  data: {level: "county"|"district"|"state"|"national", state: 2-letter code or null, metric: one field name above or "cancer_type", cancer_type: key or null, order: "worst"|"best", n: integer 1-10, cosponsor: "none"|"yes"|null, place: a single place name as written (e.g. "Hidalgo County", "TX-34", "Texas 34th", "Vermont") or null}
  reason: one short sentence on why that route.
Rules: a ZIP code or a city means "search". "Worst", "least", "lowest access", "furthest" mean order "worst"; "best", "most" mean "best". A single named place with no ranking word means a lookup (place set, n 1). If the question names a state, set state. If it asks who represents or cosponsors, level is "district". Never invent a ZIP. Use null when unsure. JSON only.`;

const WRITE_SYSTEM = `You write the answer to a question about cancer clinical trial access, using ONLY the table of numbers you are given. You are not a medical adviser.
Rules: two or three plain sentences, then nothing else. Use the numbers exactly as given (same rounding). Name places as given. Do not compute new numbers, do not compare with anything outside the table, do not speculate about causes, do not advise anyone, do not mention trials being "available" to a person. If the table cannot answer the question, say what it does show and that the rest is not in the data. Mention nothing about yourself.`;

const SCOPE_TEXT = 'This box answers questions about where trials are and the numbers behind the map. It cannot say whether a trial is right for someone, who qualifies, or what treatment to choose; the study team and your care team decide that. For help finding and understanding trials, call the NCI Cancer Information Service at 1-800-4-CANCER or use the "Understand trials" page.';
const OTHER_TEXT = 'This box answers two kinds of question: trials near a ZIP code or town, and questions about the numbers on the map (for example "which Texas districts have the least lung-cancer trial access?" or "how far is Hidalgo County from an NCI center?"). For how the map is built, see Methods & data; for definitions, see the Key terms there.';

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get('Origin') || '';
    const cors = corsHeaders(origin, env);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    const url = new URL(request.url);
    if (url.pathname === '/health') return json({ ok: true, site: env.SITE_BASE }, cors);
    if (url.pathname !== '/ask' || request.method !== 'POST') return json({ error: 'POST /ask with {"q": "..."}' }, cors, 404);
    if (!allowed(origin, env)) return json({ error: 'origin not allowed' }, cors, 403);
    if (!rate(request, env)) return json({ error: 'Too many questions in a minute; please wait a moment.', retry: true }, cors, 429);
    let q = '';
    try { q = String((await request.json()).q || '').trim().slice(0, 300); } catch (e) { return json({ error: 'bad request' }, cors, 400); }
    if (q.length < 3) return json({ error: 'Ask a question of a few words.' }, cors, 400);
    try {
      const plan = await planFor(q, env);
      let out;
      if (plan.route === 'search') out = await doSearch(q, plan.search || {}, env);
      else if (plan.route === 'data') out = await doData(q, plan.data || {}, env);
      else if (plan.route === 'scope') out = { route: 'scope', answer: SCOPE_TEXT, sources: [], view: null };
      else out = { route: 'other', answer: OTHER_TEXT, sources: [{ title: 'Methods & data', url: env.SITE_BASE + 'map.html#methods' }], view: null };
      console.log(JSON.stringify({ q, route: out.route, view: out.view && out.view.qs, answer: (out.answer || '').slice(0, 300) }));
      return json({ q, ...out, note: 'Answers come from the published data files; every number links to its file. Not medical advice.' }, cors);
    } catch (e) {
      console.log(JSON.stringify({ q, error: String(e).slice(0, 300) }));
      return json({ error: 'The question box is unavailable right now; the map and its filters still work.', detail: String(e).slice(0, 200) }, cors, 502);
    }
  }
};

// ---------- routes ----------
async function doSearch(q, s, env) {
  const type = TYPES.includes(s.cancer_type) ? s.cancer_type : (s.cancer_type === 'multi' ? 'multi' : null);
  const bits = [type ? TYPE_LABEL[type] || type : 'cancer', 'trials'];
  if (/^\d{5}$/.test(s.zip || '')) {
    const p = new URLSearchParams({ zip: s.zip }); if (type) p.set('type', type); if (s.keyword) p.set('q', String(s.keyword).slice(0, 60)); if (s.age) p.set('age', String(s.age)); if ([30, 120, 200].includes(+s.radius)) p.set('mi', String(s.radius));
    return { route: 'search', answer: `Opening the trial finder for ZIP ${s.zip}: recruiting ${bits.join(' ')} within about ${[30, 120, 200].includes(+s.radius) ? s.radius : 60} miles${s.keyword ? `, matching "${s.keyword}"` : ''}. Trials are listed, not matched; the study team decides eligibility.`,
             sources: [{ title: 'Trial finder', url: env.SITE_BASE + 'find.html?' + p }], view: { page: 'find', qs: p.toString() } };
  }
  // a town or county: open its county's trial list on the map
  const st = (s.state || '').toUpperCase(); const city = (s.city || '').trim();
  if (city) {
    const places = await getJSON(env, 'places.json'); const name = city.toLowerCase().replace(/\s+(city|town|village)$/, '');
    const cands = []; for (const [usps, arr] of Object.entries(places.places || {})) { if (st && usps !== st) continue; for (const [n, fips, pop] of arr) if (n.toLowerCase() === name) cands.push({ usps, n, fips, pop }); }
    if (!cands.length) for (const [usps, arr] of Object.entries(places.places || {})) { if (st && usps !== st) continue; for (const [n, fips, pop] of arr) if (n.toLowerCase().startsWith(name)) cands.push({ usps, n, fips, pop }); }
    if (cands.length) {
      cands.sort((a, b) => b.pop - a.pop); const c = cands[0]; const county = await getJSON(env, `api/county/${c.fips}.json`);
      const p = new URLSearchParams({ c: c.fips, tab: 'trials' }); if (type) p.set('type', type);
      return { route: 'search', answer: `${c.n}, ${STATES[c.usps] || c.usps} is in ${county.name}. ${county.trials_listed_here} recruiting trial${county.trials_listed_here === 1 ? '' : 's'} list a site in the county, and residents there have on average ${county.wmean_trials_within_60rdmi} within 60 road-miles. Opening the county's trial list; for a list by driving distance, use the finder with a ZIP code.`,
               sources: [{ title: county.name, url: env.SITE_BASE + `api/county/${c.fips}.json` }], view: { page: 'map', qs: p.toString(), hl: [c.fips] } };
    }
  }
  if (st && STATES[st]) { const p = new URLSearchParams({ s: st }); if (type) p.set('type', type); return { route: 'search', answer: `Opening ${STATES[st]} on the map${type ? ` filtered to ${TYPE_LABEL[type] || type} trials` : ''}. For trials near a specific place, give a ZIP code.`, sources: [], view: { page: 'map', qs: p.toString() } }; }
  return { route: 'search', answer: 'To list trials near a place, give a ZIP code (for example "lung cancer trials near 78501") or a town and state.', sources: [{ title: 'Trial finder', url: env.SITE_BASE + 'find.html' }], view: { page: 'find', qs: '' } };
}

async function doData(q, d, env) {
  const level = ['county', 'district', 'state', 'national'].includes(d.level) ? d.level : 'district';
  const st = STATES[(d.state || '').toUpperCase()] ? d.state.toUpperCase() : null;
  const metricKey = METRICS[d.metric] ? d.metric : (d.cancer_type ? 'cancer_type' : 'pct_lt20_trials_within_60rdmi');
  const ctype = TYPES.includes(d.cancer_type) ? d.cancer_type : null;
  const M = METRICS[metricKey]; const valueOf = r => metricKey === 'cancer_type' ? (r.trials_within_60rdmi_by_cancer_type || {})[ctype] : r[metricKey];
  const idx = await getJSON(env, 'api/index.json'); const asOf = idx.data_as_of;
  if (level === 'national') {
    const n = await getJSON(env, 'api/national.json');
    return finish(q, [n], metricKey, ctype, M, asOf, env, { page: 'map', qs: '', hl: [] }, 'national');
  }
  let rows = await getJSON(env, `api/all_${level === 'county' ? 'counties' : level + 's'}.json`);
  if (st) rows = rows.filter(r => r.state === st);
  if (level === 'district' && d.cosponsor === 'none') rows = rows.filter(r => r.member && r.member.ctma_hr3521 === 'none');
  if (level === 'district' && d.cosponsor === 'yes') rows = rows.filter(r => r.member && r.member.ctma_hr3521 !== 'none');
  if (d.place) {   // a single place lookup
    const p = String(d.place).toLowerCase().replace(/\s+/g, ' ').trim(); const m = p.match(/^([a-z]{2})[- ](\d{1,2})$/);
    const hit = rows.find(r => r.id.toLowerCase() === p) || (m ? rows.find(r => r.id.toLowerCase() === `${m[1]}-${m[2].padStart(2, '0')}`) : null)
      || rows.find(r => r.name.toLowerCase() === p) || rows.find(r => r.name.toLowerCase().startsWith(p)) || rows.find(r => r.name.toLowerCase().includes(p));
    if (!hit) return { route: 'data', answer: `No ${level} called "${d.place}" is in the data${st ? ` for ${STATES[st]}` : ''}. Try the county or district name as it appears on the map.`, sources: [], view: null };
    rows = [hit];
  } else {
    rows = rows.filter(r => valueOf(r) !== null && valueOf(r) !== undefined);
    const worst = (d.order || 'worst') === 'worst'; const sign = (M.worse === 'high') === worst ? -1 : 1;   // worst & higher-is-worse -> descending
    rows.sort((a, b) => sign * (valueOf(b) - valueOf(a)) || (b.pop55 - a.pop55));
    rows = rows.slice(0, Math.min(10, Math.max(1, parseInt(d.n) || 5)));
  }
  const qs = new URLSearchParams(); if (level !== 'county') qs.set('u', level); if (st) qs.set('s', st); if (ctype) qs.set('type', ctype);
  const layer = level === 'county' ? null : M.layer; if (layer && layer !== 'l20') qs.set('m', layer);
  if (rows.length === 1) { const r = rows[0]; if (level === 'county') { qs.delete('u'); qs.set('c', r.id); } else if (level === 'district') qs.set('d', r.geoid); else qs.set('s', r.id); }
  return finish(q, rows, metricKey, ctype, M, asOf, env, { page: 'map', qs: qs.toString(), hl: rows.map(r => level === 'district' ? r.geoid : r.id) }, level);
}

async function finish(q, rows, metricKey, ctype, M, asOf, env, view, level) {
  const fmt = v => v === null || v === undefined ? 'not in the data' : M.unit === '%' ? `${v}%` : M.unit === 'people' ? Number(v).toLocaleString('en-US') : `${v} ${M.unit}`;
  const table = rows.map(r => {
    const v = metricKey === 'cancer_type' ? (r.trials_within_60rdmi_by_cancer_type || {})[ctype] : r[metricKey];
    const o = { place: r.name, [metricKey === 'cancer_type' ? `trials for ${TYPE_LABEL[ctype]} within 60 road-miles (average)` : M.label]: fmt(v), 'residents 55+': Number(r.pop55).toLocaleString('en-US') };
    if (metricKey !== 'pct_lt20_trials_within_60rdmi') o['share with fewer than 20 trials within 60 road-miles'] = `${r.pct_lt20_trials_within_60rdmi}%`;
    if (r.nearest_nci) o['nearest NCI-designated center'] = r.nearest_nci;
    if (r.median_road_mi_nci !== undefined && metricKey !== 'median_road_mi_nci') o['median road-miles to that center'] = r.median_road_mi_nci === null ? 'no road route' : r.median_road_mi_nci;
    if (r.member) o['House member'] = `${r.member.name || 'vacant'}${r.member.party ? ` (${r.member.party})` : ''}, ${r.member.ctma_hr3521 === 'none' ? 'not a cosponsor of' : r.member.ctma_hr3521 + ' of'} H.R. 3521`;
    return o;
  });
  const sources = rows.map(r => ({ title: r.name, url: env.SITE_BASE + (level === 'national' ? 'api/national.json' : `api/${level}/${r.id}.json`) }));
  const answer = await write(q, table, asOf, env);
  return { route: 'data', answer, table, sources, view, data_as_of: asOf };
}

// ---------- model calls ----------
async function planFor(q, env) {
  const txt = await claude(env, env.MODEL_PLAN, PLAN_SYSTEM, `Question: ${q}\n\nReturn the JSON plan.`, 400);
  const m = txt.match(/\{[\s\S]*\}/); if (!m) throw new Error('planner returned no JSON');
  const plan = JSON.parse(m[0]); if (!['search', 'data', 'scope', 'other'].includes(plan.route)) plan.route = 'other';
  return plan;
}
async function write(q, table, asOf, env) {
  const user = `Question: ${q}\n\nTable (data as of ${asOf}, residents aged 55 and older, distances in road miles):\n${JSON.stringify(table, null, 1)}\n\nWrite the answer.`;
  return (await claude(env, env.MODEL_WRITE, WRITE_SYSTEM, user, 350)).trim();
}
async function claude(env, model, system, user, maxTokens) {
  if (!env.ANTHROPIC_API_KEY) throw new Error('ANTHROPIC_API_KEY is not set on the worker');
  const r = await fetch('https://api.anthropic.com/v1/messages', { method: 'POST', headers: { 'content-type': 'application/json', 'x-api-key': env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify({ model, max_tokens: maxTokens, temperature: 0, system, messages: [{ role: 'user', content: user }] }) });
  if (!r.ok) throw new Error(`model ${model}: HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
  const j = await r.json(); return (j.content || []).filter(b => b.type === 'text').map(b => b.text).join('');
}

// ---------- data files, cached at the edge for an hour ----------
async function getJSON(env, path) {
  const u = env.SITE_BASE + path; const cache = caches.default; const key = new Request(u);
  let r = await cache.match(key);
  if (!r) { r = await fetch(u, { cf: { cacheTtl: 3600 } }); if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`); const c = new Response(r.body, r); c.headers.set('Cache-Control', 'max-age=3600'); await cache.put(key, c.clone()); r = c; }
  return r.json();
}

// ---------- limits and plumbing ----------
const seen = new Map(); let dayCount = 0, dayStamp = '';
function rate(request, env) {
  const ip = request.headers.get('CF-Connecting-IP') || 'x'; const now = Date.now(); const per = parseInt(env.PER_MINUTE) || 12;
  const arr = (seen.get(ip) || []).filter(t => now - t < 60000); if (arr.length >= per) return false; arr.push(now); seen.set(ip, arr);
  if (seen.size > 5000) seen.clear();
  const today = new Date().toISOString().slice(0, 10); if (today !== dayStamp) { dayStamp = today; dayCount = 0; }
  if (++dayCount > (parseInt(env.DAILY_CAP) || 3000)) return false;
  return true;
}
function allowed(origin, env) { if (!origin) return true; return (env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).includes(origin); }
function corsHeaders(origin, env) { return { 'Access-Control-Allow-Origin': allowed(origin, env) && origin ? origin : 'null', 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'content-type', 'Vary': 'Origin' }; }
function json(obj, headers, status = 200) { return new Response(JSON.stringify(obj), { status, headers: { ...headers, 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } }); }
