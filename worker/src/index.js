/* "Ask the map" — the helper behind the question box on the Cancer Trial Access Map.
   A question comes in; a deterministic parser (parse.js) reads it with a fixed vocabulary and the place indexes built from the
   data files; only when the parser is not confident does a small model propose a plan, and that plan is then corrected against
   the question text (checkPlan). The plan runs against the site's published data files (api/*.json) with ordinary arithmetic
   (execute.js); a deterministic answer is composed from the resulting table; a second model may rewrite it, but every number in
   its text must already be in the table, or the deterministic answer is used. The models never compute, never see anything but
   the question and the table, and nothing they write becomes a URL, an id or code. Every number carries the file it came from;
   questions outside the data get a fixed reply; nothing about the visitor is stored. */
import { METRICS, TYPES, TYPE_LABEL, STATES, SCOPE_TEXT, OTHER_TEXT, ACS, SITES } from './lexicon.js';
import { parseQuestion, checkPlan } from './parse.js';
import { execute, composeAnswer, verifyAnswer, setFixedTexts, numbersIn } from './execute.js';
export { parseQuestion, checkPlan, execute, composeAnswer, verifyAnswer, numbersIn, METRICS, TYPES, TYPE_LABEL, STATES, SCOPE_TEXT, OTHER_TEXT };
setFixedTexts(SCOPE_TEXT, OTHER_TEXT);

const PLAN_SYSTEM = `You turn one question about cancer clinical trial access in the United States into a JSON plan. You do not answer the question.
The site has: (a) a trial finder by ZIP code with filters (cancer type, age, keyword); (b) data files for every US county, congressional district and state, for residents aged 55 and older, with these measures (metric keys):
${Object.entries(METRICS).map(([k, m]) => `  ${k}: ${m.label} [${m.levels.join('/')}]`).join('\n')}
  acs takes acs: veh (no vehicle) | bb (broadband) | unins (uninsured) | unins55 (uninsured 55-64) | pov (poverty). inc/mort take site: ${SITES.map(s => s[0]).join('|')}.
  districts also have the House member's name, party and whether they cosponsor H.R. 3521 (Clinical Trial Modernization Act); states have senators and S. 4440.
Cancer type keys: ${TYPES.join(', ')}.
Return exactly one JSON object with keys:
  route: "search" (a person wants trials near a place), "data" (a question the measures above can answer), "scope" (eligibility, prognosis, whether to join a trial, treatment advice, a specific person's situation, drug questions), or "other" (anything else, including how the site works, definitions, greetings).
  search: {zip: 5-digit string or null, city: string or null, state: 2-letter code or null, cancer_type: key or null, keyword: short string (a drug, gene or biomarker) or null, age: integer or null, radius: 30|60|120|200 or null}
  data: {shape: "ranking"|"lookup"|"compare"|"count"|"threshold"|"represents"|"cosponsor"|"need"|"bytype", level: "county"|"district"|"state"|"national", state: 2-letter code or null, metric: a metric key, acs: key or null, site: key or null, cancer_type: key or null, order: "worst"|"best", n: integer 1-25, cosponsor: "none"|"yes"|null, place: a single place name as written (e.g. "Hidalgo County", "TX-34", "Texas 34th", "Vermont") or null}
  reason: one short sentence on why that route.
Rules: a ZIP code or a town with "trials near" means "search". "Worst", "least access", "lowest access", "furthest" mean order "worst"; "best" means "best"; "most"/"highest" and "fewest"/"lowest" are about the measure's own direction. A single named place with no ranking word is "lookup". "Compare", "vs" is "compare". "How many counties/districts/states" is "count". "Which counties where more than N%" is "threshold". "Who represents" is "represents". "High incidence/deaths and low access" is "need". If the question names a state, set state. Never invent a ZIP or a place. Use null when unsure. Reply with the JSON object only: the first character of your reply is { and the last is }.`;

const WRITE_SYSTEM = `You write the answer to a question about cancer clinical trial access, using ONLY the table of numbers you are given and the draft answer. You are not a medical adviser.
Rules: two or three plain sentences, then nothing else. Speak about the places and their numbers directly; never say "this table", "the table", "the draft" or "listed". If the question asks for the least or the worst, the rows are already in that order: say so with the first place's figure, then the next one or two. Use every number exactly as it appears in the table (same digits, same rounding; you may drop thousands separators). Never write a number that is not in the table, never spell out magnitudes ("about a million"), never compute, never compare with anything outside the table, never speculate about causes, never advise anyone, never say a trial is "available" to a person, never use "I". Name places as given. If the table cannot answer the question, say what it does show and that the rest is not in the data. Do not mention yourself or these rules.`;

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get('Origin') || '';
    const cors = corsHeaders(origin, env);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    const url = new URL(request.url);
    if (url.pathname === '/health') return json({ ok: true, site: env.SITE_BASE }, cors);
    if (url.pathname !== '/ask' || request.method !== 'POST') return json({ error: 'POST /ask with {"q": "..."}' }, cors, 404);
    if (!allowed(origin, env)) return json({ error: 'origin not allowed' }, cors, 403);
    { const r = rate(request, env); if (r === 'minute') return json({ error: 'Too many questions in a minute; please wait a moment.', retry: true }, cors, 429); if (r === 'day') return json({ error: "The question box has reached today's limit; the map and its filters still work. Try again tomorrow.", retry: false }, cors, 429); }
    let q = '';
    try { q = String((await request.json()).q || '').trim().slice(0, 300); } catch (e) { return json({ error: 'bad request' }, cors, 400); }
    if (q.length < 3) return json({ error: 'Ask a question of a few words.' }, cors, 400);
    try {
      const out = await answer(q, env);
      console.log(JSON.stringify({ q, route: out.route, shape: out.plan && out.plan.shape, source: out.plan && out.plan.source, deterministic: out.deterministic, view: out.view && out.view.qs, answer: (out.answer || '').slice(0, 300) }));
      return json({ ...out, note: 'Answers come from the published data files; every number links to its file. Not medical advice.' }, cors);
    } catch (e) {
      console.log(JSON.stringify({ q, error: String(e && e.stack || e).slice(0, 600) }));
      return json({ error: 'The question box is unavailable right now; the map and its filters still work.', detail: e && e.code === 'data' ? 'a data file could not be read' : 'internal error' }, cors, 502);
    }
  }
};

// ---------- the pipeline: parse -> (model plan + check) -> load -> execute -> compose -> (model write + verify) ----------
export async function answer(q, env, loader) {
  const load = loader || (path => getJSON(env, path));
  const data = { index: await load('api/index.json') };
  for (const f of filesForText(q)) data[f] = await load(FILE[f]);
  let plan = parseQuestion(q, data); let modelPlan = null;
  if (!plan) { modelPlan = await planWithModel(q, env); plan = checkPlan(q, modelPlan, data); }
  await loadForPlan(plan, data, load);
  if (modelPlan && !(plan.places || []).length) { const re = checkPlan(q, modelPlan, data); if (re && re.places && re.places.length) { plan = re; await loadForPlan(plan, data, load); } }   // a place may resolve only after its file was loaded
  const result = execute(plan, data);
  const draft = composeAnswer(plan, result);
  let text = draft, deterministic = true;
  if (result.route === 'data' && result.table && result.table.length && !result.ambiguity && env && env.ANTHROPIC_API_KEY && env.MODEL_WRITE) {
    try { const model = await write(q, draft, result, env); const v = verifyAnswer(model, result.table, [result.data_as_of || '', result.summary || '']); if (v.ok && model.length < 900) { text = model; deterministic = false; } else console.log(JSON.stringify({ q, rejected: v.badNumbers, model: model.slice(0, 200) })); } catch (e) { console.log(JSON.stringify({ q, write_error: String(e).slice(0, 200) })); }
  }
  const out = { q, route: result.route, answer: text, table: result.table, rows: result.rows, summary: result.summary || null, sources: result.sources, view: result.view, data_as_of: result.data_as_of, caveats: result.caveats, plan: publicPlan(plan), deterministic };
  if (result.ambiguity) out.ambiguity = result.ambiguity;
  if (result.route === 'other') out.sources = [{ title: 'Methods & data', url: (env && env.SITE_BASE || '') + 'map.html#methods' }];
  return out;
}
const FILE = { counties: 'api/all_counties.json', ask_counties: 'api/ask/counties.json', county_sites: 'api/ask/county_sites.json', county_names: 'api/county_names.json', districts: 'api/all_districts.json', states: 'api/all_states.json', national: 'api/national.json', places: 'places.json', zips: 'zip_county.json' };
// Which files the parser needs to read the question text. all_counties.json (~9 MB) is loaded only when a county is named by
// its suffix (County, Parish, Borough, ...) or the question is plainly about counties; district, state and national questions never touch it.
export function filesForText(q) {
  const n = String(q).toLowerCase(); const f = new Set(['states', 'national']);
  if (/\b(county|counties|parish|parishes|borough|boroughs|census area|municipality|carson city)\b/.test(n) || /\b[a-z]+ city\b/.test(n) && !/\b(oklahoma|kansas|jersey|salt lake|new york|carson|iowa|texas|michigan|nevada|colorado|dodge|sioux|rapid|garden|ponca|atlantic|ocean|panama|johnson|silver|boulder|cedar|union|bay|mason|cell)\b/.test(n)) f.add('county_names');
  if (/\b(district|districts|member|members|represent|represents|cosponsor|cosponsors|cosponsored|sponsor|sponsors|congress|congressional|rep\.?|representative|representatives|house|h\.? ?r\.?|bill|senator|senators|senate)\b/.test(n) || /\b[a-z]{2}[- ]?\d{1,2}\b/.test(n) || /\b[a-z]{2}-al\b/.test(n) || /\b\d{1,2}(st|nd|rd|th)\b/.test(n) || /\bat[- ]large\b/.test(n)) f.add('districts');
  if (/\b\d{5}\b/.test(n)) f.add('zips');
  if (/\b(near|in|at|around|from|to|for|about)\s+[a-z]/.test(n) || /,\s*[a-z]/.test(n) || /\b[A-Z][a-z]+/.test(String(q).replace(/^\w+/, '')) || /^\s*[A-Z][a-z]+\s*$/.test(String(q))) f.add('places');
  const bare = !/\b(county|counties|district|districts|state|states|national|nationally|us|america|zip|trial|trials|access|miles|nci|incidence|death|deaths|oncolog|cosponsor|represent|rural|metro|poverty|uninsured|broadband|vehicle)\b/.test(n);
  if (bare) { if (!/,\s*[a-z]/.test(n)) f.add('districts'); f.add('places'); }   // a bare name: a member, a town or a district code may be all there is
  return [...f];
}
// Which rows the plan needs: every county row only for county-level rankings, counts, thresholds and need-vs-access;
// a single county (a lookup, a comparison, a ZIP or a town) is fetched from its own small file.
export function filesForPlan(plan) {
  if (!plan) return []; const f = new Set(['states', 'national']); const lv = plan.level; const kinds = new Set((plan.places || []).map(p => p.kind));
  if (lv === 'county' && ['ranking', 'count', 'threshold', 'need'].includes(plan.shape)) { f.add('ask_counties'); if (needsSites(plan)) f.add('county_sites'); }
  if (lv === 'district' || kinds.has('district') || ['represents', 'cosponsor'].includes(plan.shape) || plan.cosponsor) f.add('districts');
  return [...f];
}
export const needsSites = plan => !!(plan && plan.site && plan.site !== 'all' && (['inc', 'mort', 'inc_cases', 'mort_deaths'].includes(plan.metric) || plan.shape === 'need'));
// ask/counties.json -> rows shaped like all_counties.json (nested context / incidence / mortality / oncologists), so execute() is unchanged
export function expandCounties(compact, sites) {
  const cols = compact.cols; const rows = []; const siteKeys = sites && sites.sites; const srows = sites && sites.rows;
  for (const arr of compact.rows) { const r = { level: 'county', context: {}, incidence: { by_site: null }, mortality: { by_site: null }, oncologists: {} };
    for (let i = 0; i < cols.length; i++) { const k = cols[i], v = arr[i]; const dot = k.indexOf('.'); if (dot < 0) r[k] = v; else r[k.slice(0, dot)][k.slice(dot + 1)] = v; }
    if (srows && srows[r.id]) { const [inc, mort] = srows[r.id]; r.incidence.by_site = Object.fromEntries(siteKeys.map((k, i) => [k, inc[i]])); r.mortality.by_site = Object.fromEntries(siteKeys.map((k, i) => [k, mort[i]])); }
    rows.push(r); }
  return rows;
}
export function countyIdsForPlan(plan) { const ids = new Set(); for (const p of plan.places || []) if (p.kind === 'county' && p.id) ids.add(p.id); if (plan.search) { if (plan.search.zip_county) ids.add(plan.search.zip_county); if (plan.search.city_county) ids.add(plan.search.city_county); } return [...ids]; }
async function loadForPlan(plan, data, load) {
  for (const f of filesForPlan(plan)) if (!data[f]) data[f] = await load(FILE[f]);
  if (!data.counties && data.ask_counties) data.counties = expandCounties(data.ask_counties, data.county_sites || null);   // the compact table stands in for all_counties.json
  else if (data.counties && data.counties_partial && data.ask_counties) data.counties = expandCounties(data.ask_counties, data.county_sites || null);
  if (!data.counties) { const ids = countyIdsForPlan(plan); if (ids.length) { const rows = []; for (const id of ids.slice(0, 6)) { try { rows.push(await load(`api/county/${id}.json`)); } catch (e) { const err = new Error(`county file ${id}: ${String(e).slice(0, 120)}`); err.code = 'data'; throw err; } } data.counties = rows; data.counties_partial = true; } }
  for (const p of plan.places || []) if (p.kind === 'county' && p.unnamed) { const r = (data.counties || []).find(x => x.id === p.id); if (r) { p.name = r.name; p.state = r.state; delete p.unnamed; } else { p.unknown = true; } }
}
function publicPlan(plan) { const { places, flags, model, ...rest } = plan || {}; return { ...rest, places: (places || []).map(p => ({ kind: p.kind, id: p.id, name: p.name, state: p.state, via: p.via || null })), flags: flags || null }; }

// ---------- model calls ----------
function parsePlan(txt) {
  const m = String(txt || '').replace(/```[a-z]*/gi, '').match(/\{[\s\S]*\}/); if (!m) return null;
  const tries = [m[0], m[0].replace(/\/\/[^\n]*/g, '').replace(/,\s*([}\]])/g, '$1').replace(/'([^'\n]*)'/g, '"$1"')];
  for (const t of tries) { try { const o = JSON.parse(t); if (o && typeof o === 'object') return o; } catch (e) {} }
  return null;
}
export async function planWithModel(q, env) {
  if (!env || !env.ANTHROPIC_API_KEY) return { route: 'other', reason: 'no model configured' };
  let txt; try { txt = await claude(env, env.MODEL_PLAN, PLAN_SYSTEM, `Question: ${q}\n\nReturn the JSON plan.`, 900, PLAN_TIMEOUT_MS); } catch (e) { console.log(JSON.stringify({ q, plan_error: String(e).slice(0, 200) })); return { route: 'other', reason: 'planner unavailable' }; }   // a slow or failing planner means the fixed reply, not a 502
  let plan = parsePlan(txt);
  if (!plan) { let again = ''; try { again = await claude(env, env.MODEL_PLAN, PLAN_SYSTEM, `Question: ${q}\n\nYour previous reply was not valid JSON. Return ONLY the JSON plan, with double-quoted keys and strings and no comments.`, 900, PLAN_TIMEOUT_MS); } catch (e) { again = ''; } plan = parsePlan(again); if (!plan) { console.log(JSON.stringify({ q, plan_error: 'no usable JSON' })); return { route: 'other', reason: 'planner returned no plan' }; } }
  if (!['search', 'data', 'scope', 'other'].includes(plan.route)) plan.route = 'other';
  return plan;
}
async function write(q, draft, result, env) {
  const user = `Question: ${q}\n\n${result.summary ? `Rule and totals: ${JSON.stringify(result.summary)}\n\n` : ''}Table (data as of ${result.data_as_of}, residents aged 55 and older, distances in road miles):\n${JSON.stringify(result.table, null, 1)}\n${result.caveats && result.caveats.length ? `\nCaveats to keep in mind (do not quote numbers from them):\n${result.caveats.map(c => '- ' + c).join('\n')}\n` : ''}\nDraft answer (correct, plain; improve its wording only):\n${draft}\n\nWrite the answer.`;
  return (await claude(env, env.MODEL_WRITE, WRITE_SYSTEM, user, 400, WRITE_TIMEOUT_MS)).trim();
}
const PLAN_TIMEOUT_MS = 8000, WRITE_TIMEOUT_MS = 15000;   // the page waits 45 s in all; a model that does not answer in time is skipped, not waited for
async function claude(env, model, system, user, maxTokens, timeoutMs) {
  if (!env.ANTHROPIC_API_KEY) throw new Error('ANTHROPIC_API_KEY is not set on the worker');
  const signal = typeof AbortSignal !== 'undefined' && AbortSignal.timeout ? AbortSignal.timeout(timeoutMs || WRITE_TIMEOUT_MS) : undefined;
  const r = await fetch('https://api.anthropic.com/v1/messages', { method: 'POST', headers: { 'content-type': 'application/json', 'x-api-key': env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' }, signal,
    body: JSON.stringify({ model, max_tokens: maxTokens, system, messages: [{ role: 'user', content: user }] }) });
  if (!r.ok) throw new Error(`model ${model}: HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
  const j = await r.json(); return (j.content || []).filter(b => b.type === 'text').map(b => b.text).join('');
}

// ---------- data files: parsed once per isolate (an hour), then the edge cache (an hour), then the site ----------
const memo = new Map(); const MEMO_MS = 3600 * 1000;
async function getJSON(env, path) {
  const hit = memo.get(path); if (hit && Date.now() - hit.at < MEMO_MS) return hit.json;
  const json = await fetchJSON(env, path); memo.set(path, { at: Date.now(), json }); if (memo.size > 64) { const oldest = [...memo.entries()].sort((a, b) => a[1].at - b[1].at)[0]; if (oldest) memo.delete(oldest[0]); } return json;
}
async function fetchJSON(env, path) {
  const u = env.SITE_BASE + path; const cache = caches.default; const key = new Request(u);
  let r = await cache.match(key);
  if (!r) { r = await fetch(u, { cf: { cacheTtl: 3600 } }); if (!r.ok) { const err = new Error(`${path}: HTTP ${r.status}`); err.code = 'data'; throw err; } const c = new Response(r.body, r); c.headers.set('Cache-Control', 'max-age=3600'); await cache.put(key, c.clone()); r = c; }
  return r.json();
}

// ---------- limits and plumbing ----------
const seen = new Map(); let dayCount = 0, dayStamp = '';
function rate(request, env) {
  const ip = request.headers.get('CF-Connecting-IP') || 'x'; const now = Date.now(); const per = parseInt(env.PER_MINUTE) || 12;
  const arr = (seen.get(ip) || []).filter(t => now - t < 60000); if (arr.length >= per) return 'minute'; arr.push(now); seen.set(ip, arr);
  if (seen.size > 5000) seen.clear();
  const today = new Date().toISOString().slice(0, 10); if (today !== dayStamp) { dayStamp = today; dayCount = 0; }
  if (++dayCount > (parseInt(env.DAILY_CAP) || 3000)) return 'day';
  return 'ok';
}
function allowed(origin, env) { if (!origin) return true; return (env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).includes(origin); }
function corsHeaders(origin, env) { return { 'Access-Control-Allow-Origin': allowed(origin, env) && origin ? origin : 'null', 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'content-type', 'Vary': 'Origin' }; }
function json(obj, headers, status = 200) { return new Response(JSON.stringify(obj), { status, headers: { ...headers, 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } }); }
