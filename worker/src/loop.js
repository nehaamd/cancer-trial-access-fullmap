/* Ask the map v3 — one step of the client ⇄ worker protocol (ASK_CONTRACT.md §3).
   step(body, env, callModel) validates the request, checks the signatures of the earlier assistant turns, builds the messages,
   calls the model once (plus up to MAX_RETRIES extra calls when a final_answer fails verification), signs the assistant blocks
   and returns the response object. Pure apart from callModel: no fetch, no clock, no storage; errors are StepError(status, text).

   The transcript the model sees: [prior Q/A pairs as plain text turns] → the question → for each earlier turn the assistant
   blocks and a user turn of tool_result blocks → (within this request, on a verification failure) the failed assistant turn and
   a tool_result error for its final_answer call.

   Rules enforced here: MAX_STEPS model calls per question (the last forced to final_answer), max_tokens 1200, each tool_result
   content ≤ 24 KB, ≤ 8 tool calls per turn, final_answer alone in its turn (when it comes with other calls the step returns
   kind:"tools" with ALL calls and the client answers the final_answer call with {ok:true, note:"call final_answer alone, after
   the other results"}; the model then calls final_answer again, alone). */
import * as DEFAULT_CATALOG from '../../docs/ask/catalog.js';
import { systemPrompt, toolDefinitions, TOOL_NAMES } from './prompt.js';
import { verify, buildContext } from './verify.js';
import { sign, verifySig, secretFor } from './sign.js';

export const PROTOCOL_VERSION = 3;
export const MAX_STEPS = 8;
export const MAX_TOKENS = 2500;   // a final_answer with interpretation, alternatives, caveats and follow-ups is ~600 tokens; the margin keeps a wordy one from being cut off
export const MAX_RESULT_BYTES = 24 * 1024;
export const MAX_CALLS_PER_TURN = 8;
export const MAX_RETRIES = 2;
export const MAX_PRIOR = 3;
export const Q_MIN = 3, Q_MAX = 400;
export const DEFAULT_MODEL = 'claude-sonnet-5-5';
export const FINAL_NOTE = 'call final_answer alone, after the other results';   // what the client answers a premature final_answer with
export const FORCE_FINAL_TEXT = 'You have used all the tool steps for this question. Call final_answer now, alone, with what the results so far show; say in not_in_data what could not be looked up.';

export class StepError extends Error { constructor(status, message, detail) { super(message); this.status = status; this.detail = detail; } }
const bad = (msg, detail) => new StepError(400, msg, detail);
const bytes = s => new TextEncoder().encode(s).length;

// ---------- request validation (§3) ----------
export function validateBody(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw bad('The request was not understood.');
  if (body.v !== undefined && body.v !== PROTOCOL_VERSION) throw bad(`This question box speaks protocol version ${PROTOCOL_VERSION}; reload the page.`);
  const q = typeof body.q === 'string' ? body.q.replace(/\s+/g, ' ').trim() : '';
  if (q.length < Q_MIN) throw bad('Ask a question of a few words.');
  if (q.length > Q_MAX) throw bad(`The question is too long (${Q_MAX} characters at most).`);
  const turns = body.turns === undefined ? [] : body.turns;
  if (!Array.isArray(turns) || turns.length > MAX_STEPS) throw bad('bad transcript', 'turns must be a list of at most ' + MAX_STEPS);
  for (const [i, t] of turns.entries()) {
    if (!t || typeof t !== 'object' || !Array.isArray(t.assistant) || typeof t.sig !== 'string' || !Array.isArray(t.results)) throw bad('bad transcript', `turn ${i} must be {assistant:[blocks], sig, results:[…]}`);
    const uses = t.assistant.filter(b => b && b.type === 'tool_use');
    if (uses.length > MAX_CALLS_PER_TURN) throw bad('bad transcript', `turn ${i} has ${uses.length} tool calls; at most ${MAX_CALLS_PER_TURN}`);
    if (t.results.length > MAX_CALLS_PER_TURN) throw bad('bad transcript', `turn ${i} has ${t.results.length} results; at most ${MAX_CALLS_PER_TURN}`);
    const ids = new Set(uses.map(b => b.id)); const seen = new Set();
    for (const r of t.results) {
      if (!r || typeof r !== 'object' || typeof r.tool_use_id !== 'string') throw bad('bad transcript', `turn ${i}: each result needs a tool_use_id`);
      if (!ids.has(r.tool_use_id)) throw bad('bad transcript', `turn ${i}: result for unknown call ${r.tool_use_id}`);
      if (seen.has(r.tool_use_id)) throw bad('bad transcript', `turn ${i}: two results for call ${r.tool_use_id}`);
      seen.add(r.tool_use_id);
      if (typeof r.content !== 'string') throw bad('bad transcript', `turn ${i}: result content must be a string`);
      if (bytes(r.content) > MAX_RESULT_BYTES) throw bad(`A tool result is too large (${Math.round(bytes(r.content) / 1024)} KB; the limit is ${MAX_RESULT_BYTES / 1024} KB).`);
      if (r.is_error !== undefined && typeof r.is_error !== 'boolean') throw bad('bad transcript', `turn ${i}: is_error must be a boolean`);
    }
    for (const id of ids) if (!seen.has(id)) throw bad('bad transcript', `turn ${i}: call ${id} has no result`);
  }
  let prior = body.prior === undefined || body.prior === null ? [] : body.prior;
  if (!Array.isArray(prior)) throw bad('The request was not understood.', 'prior must be a list');
  prior = prior.slice(-MAX_PRIOR).filter(p => p && typeof p === 'object' && typeof p.q === 'string' && typeof p.answer === 'string' && p.q.trim() && p.answer.trim()).map(p => ({ q: p.q.replace(/\s+/g, ' ').trim().slice(0, Q_MAX), answer: p.answer.replace(/\s+/g, ' ').trim().slice(0, 1200) }));
  const client = body.client && typeof body.client === 'object' ? { page: String(body.client.page || '').slice(0, 20), unit: String(body.client.unit || '').slice(0, 10) } : null;
  return { q, turns, prior, client };
}

// ---------- messages ----------
export function buildMessages(req, extra = []) {
  const messages = [];
  for (const p of req.prior) { messages.push({ role: 'user', content: p.q }); messages.push({ role: 'assistant', content: p.answer }); }
  messages.push({ role: 'user', content: req.q });
  for (const t of req.turns) {
    messages.push({ role: 'assistant', content: t.assistant });
    messages.push({ role: 'user', content: t.results.map(r => ({ type: 'tool_result', tool_use_id: r.tool_use_id, content: r.content, ...(r.is_error ? { is_error: true } : {}) })) });
  }
  for (const m of extra) messages.push(m);
  return messages;
}

// ---------- the step ----------
export async function step(body, env, callModel, options = {}) {
  const catalog = options.catalog || DEFAULT_CATALOG;
  const req = validateBody(body);
  const secret = options.secret || await secretFor(env || {});
  for (const [i, t] of req.turns.entries()) { let ok = false; try { ok = await verifySig(t.assistant, t.sig, secret); } catch (e) { ok = false; } if (!ok) throw bad('bad transcript', `turn ${i}: signature does not match`); }   // a malformed block (too deep to canonicalise) is a bad transcript, not a 502

  const model = (env && env.MODEL) || DEFAULT_MODEL;
  // env.MODEL_FAST is read and ignored on purpose: one model for every step until the lead decides otherwise (§3 allows a
  // cheaper model for tools-only steps; switching models mid-transcript also loses the prompt cache).
  void (env && env.MODEL_FAST);
  const maxSteps = Math.max(1, parseInt(env && env.MAX_STEPS) || MAX_STEPS);
  const stepNo = req.turns.length + 1;
  const forceFinal = stepNo >= maxSteps;
  const base = { model, max_tokens: MAX_TOKENS, system: [{ type: 'text', text: systemPrompt(catalog), cache_control: { type: 'ephemeral' } }], tools: toolDefinitions(catalog) };
  const extra = []; const usage = { input_tokens: 0, output_tokens: 0, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 };
  let retries = 0, last = null;
  for (;;) {
    // on a verification retry the model may still fetch a missing figure, so only the forced last step pins final_answer
    // current models accept only tool_choice auto (type "any" / "tool" are rejected with HTTP 400), so the last step is forced in words
    const payload = { ...base, tool_choice: { type: 'auto' }, messages: buildMessages(req, forceFinal && !extra.length ? [{ role: 'user', content: FORCE_FINAL_TEXT }] : extra) };
    const res = await callModel(payload);
    const blocks = Array.isArray(res && res.content) ? res.content.filter(b => b && (b.type === 'text' || b.type === 'tool_use')) : [];
    addUsage(usage, res && res.usage);
    const calls = blocks.filter(b => b.type === 'tool_use');
    if (res && res.stop_reason === 'max_tokens' && retries < MAX_RETRIES) {   // the reply was cut off (usually a final_answer with a long inline table): ask for a shorter one
      const note = 'Your reply was cut off at the token limit. Reply more briefly: use table.from_call instead of inline rows, keep the answer to a few sentences, and call final_answer alone.';
      // every tool_use in the cut-off turn must be answered with a tool_result, or the API rejects the transcript
      retries++; extra.push({ role: 'assistant', content: blocks.length ? blocks : [{ type: 'text', text: '(cut off)' }] }, { role: 'user', content: calls.length ? calls.map(c => ({ type: 'tool_result', tool_use_id: c.id, is_error: true, content: note })) : note });
      continue;
    }
    const unknown = calls.find(c => !TOOL_NAMES.includes(c.name)); if (unknown) throw new StepError(502, 'The question box is unavailable right now; the map and its filters still work.', `model called unknown tool ${unknown.name}`);
    const finals = calls.filter(c => c.name === 'final_answer'); const others = calls.filter(c => c.name !== 'final_answer');

    if (others.length && calls.length > MAX_CALLS_PER_TURN && retries < MAX_RETRIES) {   // too many calls: tell the model and try again
      retries++; extra.push({ role: 'assistant', content: blocks }, { role: 'user', content: calls.map(c => ({ type: 'tool_result', tool_use_id: c.id, is_error: true, content: `Too many tool calls in one turn (${calls.length}; the limit is ${MAX_CALLS_PER_TURN}). Call at most ${MAX_CALLS_PER_TURN} tools per turn.` })) });
      continue;
    }
    if (others.length) {   // tools (possibly with a premature final_answer, which the client answers with FINAL_NOTE)
      if (calls.length > MAX_CALLS_PER_TURN) throw new StepError(502, 'The question box is unavailable right now; the map and its filters still work.', `model returned ${calls.length} tool calls`);
      return { v: PROTOCOL_VERSION, kind: 'tools', step: stepNo, assistant: blocks, sig: await sign(blocks, secret), calls: calls.map(c => ({ id: c.id, name: c.name, input: c.input && typeof c.input === 'object' ? c.input : {} })), ...(finals.length ? { note: `final_answer must be called alone; answer its call with {"ok":true,"note":"${FINAL_NOTE}"}` } : {}), model, usage, retries };
    }
    // a text-only reply (possible with tool_choice auto) is a lost turn, not an answer: nudge the model back to the tools, up to the retry cap
    if (!calls.length && retries < MAX_RETRIES) {
      retries++; extra.push({ role: 'assistant', content: blocks.length ? blocks : [{ type: 'text', text: '(empty)' }] }, { role: 'user', content: 'Text replies are not shown to the visitor. Continue with tool calls (find_places, query, aggregate, profile, compare, trials, site_info, method) and then call final_answer alone with the answer.' });
      continue;
    }
    // an answer: a final_answer call, or (after the nudges) a text-only reply
    const final = finals[0] || null;
    const answer = final ? (final.input && typeof final.input === 'object' ? final.input : {}) : { answer: blocks.filter(b => b.type === 'text').map(b => b.text).join('\n').trim(), answerable: 'partly', interpretation: 'Answered in text without a final_answer call.' };
    const verification = verify(answer, buildContext({ question: req.q, turns: req.turns, catalog }));
    last = { v: PROTOCOL_VERSION, kind: 'answer', step: stepNo, assistant: blocks, sig: await sign(blocks, secret), answer, verification: { ok: verification.ok, issues: verification.issues, retries }, model, usage };
    if (verification.ok || retries >= MAX_RETRIES) return last;
    retries++; last.verification.retries = retries;
    const text = `Verification failed: ${verification.issues.join(' ')} Rewrite the final answer using only numbers and names from the tool results of this question (rounded at most to the precision you write), or call a tool to get the missing figure, then call final_answer again, alone.`;
    extra.push({ role: 'assistant', content: blocks.length ? blocks : [{ type: 'text', text: '(empty)' }] });
    extra.push(final ? { role: 'user', content: [{ type: 'tool_result', tool_use_id: final.id, is_error: true, content: text }] } : { role: 'user', content: text });
  }
}
function addUsage(acc, u) { if (!u || typeof u !== 'object') return; for (const k of Object.keys(acc)) if (typeof u[k] === 'number') acc[k] += u[k]; }
