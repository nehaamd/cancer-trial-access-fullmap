/* "Ask the map" v3 — the Cloudflare Worker behind the question box (ASK_CONTRACT.md §3).
   HTTP only: CORS, /health, POST /ask. The worker is a stateless, signed, rate-limited model proxy with a verifier: it holds the
   API key, builds the system prompt and tool schemas from the catalog (prompt.js), calls the model (one step per request),
   verifies the final answer against the tool results the client sent (verify.js), signs what the model said (sign.js) and
   returns it. Tools run in the browser against the site's own data (docs/ask/engine.js); the worker never reads data files.
   Nothing about the visitor is stored; the per-request log line carries no visitor identifier. */
import { step, StepError, PROTOCOL_VERSION } from './loop.js';

export default {
  async fetch(request, env) { return handle(request, env, makeCallModel(env)); }
};

export async function handle(request, env, callModel) {
  const origin = request.headers.get('Origin') || '';
  const cors = corsHeaders(origin, env);
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
  const url = new URL(request.url);
  if (url.pathname === '/health') return json({ ok: true, v: PROTOCOL_VERSION, model: env.MODEL || null, site: env.SITE_BASE || null }, cors);
  if (url.pathname !== '/ask' || request.method !== 'POST') return json({ error: 'POST /ask with {"v":3,"q":"…","turns":[]}' }, cors, 404);
  if (!allowed(origin, env)) return json({ error: 'This page is not allowed to use the question box.' }, cors, 403);
  let body;
  try { body = await request.json(); } catch (e) { return json({ error: 'The request was not understood.' }, cors, 400); }
  const turns = body && Array.isArray(body.turns) ? body.turns.length : 0;
  if (turns === 0) {   // only the first step of a question counts toward the limits; later steps of the same question are free
    const r = checkLimits(request.headers.get('CF-Connecting-IP') || 'x', env);
    if (!r.ok) return json({ error: r.error, retry_after_s: r.retry_after_s }, { ...cors, 'retry-after': String(r.retry_after_s) }, 429);
  }
  const t0 = Date.now(); const q = body && typeof body.q === 'string' ? body.q.slice(0, 400) : '';
  try {
    const out = await step(body, env, callModel);
    console.log(JSON.stringify({ q, step: out.step, kind: out.kind, model: out.model, ok: out.kind === 'answer' ? out.verification.ok : null, issues: out.kind === 'answer' ? out.verification.issues.slice(0, 5) : undefined, retries: out.retries ?? (out.verification && out.verification.retries), calls: out.calls ? out.calls.map(c => c.name) : undefined, ms: Date.now() - t0, usage: out.usage }));
    const { usage, retries, ...pub } = out;   // usage stays in the log
    return json(pub, cors);
  } catch (e) {
    if (e instanceof StepError) { if (e.status >= 500) console.log(JSON.stringify({ q, step: turns + 1, error: e.message, detail: e.detail })); return json(e.status === 400 && e.message === 'bad transcript' ? { error: 'bad transcript' } : { error: e.message, ...(e.detail && e.status >= 500 ? { detail: String(e.detail).slice(0, 300) } : {}) }, cors, e.status); }
    const msg = String(e && e.message || e);
    if (e && (e.name === 'TimeoutError' || e.name === 'AbortError' || e.code === 'timeout')) { console.log(JSON.stringify({ q, step: turns + 1, timeout: true, ms: Date.now() - t0 })); return json({ error: 'The model took too long to answer; try again in a moment.' }, cors, 504); }
    console.log(JSON.stringify({ q, step: turns + 1, error: msg.slice(0, 600) }));
    return json({ error: 'The question box is unavailable right now; the map and its filters still work.', detail: msg.slice(0, 300) }, cors, 502);
  }
}

// ---------- the model ----------
export const MODEL_TIMEOUT_MS = 25000;
export function makeCallModel(env, fetchFn = (typeof fetch === 'function' ? fetch : null)) {
  return async function callModel(payload) {
    if (!env.ANTHROPIC_API_KEY) throw new Error('ANTHROPIC_API_KEY is not set on the worker');
    const body = JSON.stringify(payload);
    for (let attempt = 0; ; attempt++) {
      const signal = typeof AbortSignal !== 'undefined' && AbortSignal.timeout ? AbortSignal.timeout(MODEL_TIMEOUT_MS) : undefined;
      let r;
      try { r = await fetchFn('https://api.anthropic.com/v1/messages', { method: 'POST', signal, headers: { 'content-type': 'application/json', 'x-api-key': env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' }, body }); }
      catch (e) { if (e && (e.name === 'TimeoutError' || e.name === 'AbortError')) { const t = new Error('model timed out'); t.code = 'timeout'; throw t; } throw e; }
      if (r.ok) { const j = await r.json(); return { content: j.content || [], stop_reason: j.stop_reason, usage: j.usage, model: j.model }; }
      const text = (await r.text().catch(() => '')).slice(0, 300);
      if (attempt === 0 && (r.status === 429 || r.status === 529 || r.status >= 500)) { await new Promise(res => setTimeout(res, 1500)); continue; }   // one retry after 1.5 s
      throw new Error(`model ${payload.model}: HTTP ${r.status} ${text}`);
    }
  };
}

// ---------- limits (best effort, per worker isolate; the spending limit on the key is the hard stop) ----------
const seen = new Map(); let dayCount = 0, dayStamp = '';
export function checkLimits(ip, env, now = Date.now()) {
  const per = parseInt(env.PER_MINUTE) || 12, cap = parseInt(env.DAILY_CAP) || 3000;
  const arr = (seen.get(ip) || []).filter(t => now - t < 60000);
  if (arr.length >= per) return { ok: false, error: 'Too many questions in a minute; please wait a moment.', retry_after_s: Math.max(1, Math.ceil((60000 - (now - arr[0])) / 1000)) };
  const today = new Date(now).toISOString().slice(0, 10); if (today !== dayStamp) { dayStamp = today; dayCount = 0; }
  if (dayCount >= cap) { const midnight = Date.UTC(new Date(now).getUTCFullYear(), new Date(now).getUTCMonth(), new Date(now).getUTCDate() + 1); return { ok: false, error: "The question box has reached today's limit; the map and its filters still work. Try again tomorrow.", retry_after_s: Math.max(60, Math.ceil((midnight - now) / 1000)) }; }
  arr.push(now); seen.set(ip, arr); if (seen.size > 5000) seen.clear();
  dayCount++;
  return { ok: true };
}
export function resetLimits() { seen.clear(); dayCount = 0; dayStamp = ''; }

// ---------- plumbing ----------
function allowed(origin, env) { if (!origin) return true; return (env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean).includes(origin); }
function corsHeaders(origin, env) { return { 'Access-Control-Allow-Origin': allowed(origin, env) && origin ? origin : 'null', 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'content-type', 'Access-Control-Max-Age': '86400', 'Vary': 'Origin' }; }
function json(obj, headers, status = 200) { return new Response(JSON.stringify(obj), { status, headers: { ...headers, 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } }); }
