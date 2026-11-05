/* Signatures for the assistant turns of the step protocol (ASK_CONTRACT.md §3).
   The worker keeps no state, so the client carries the transcript. Every assistant turn the worker returns is signed with
   HMAC-SHA256 over the canonical JSON of its content blocks; a turn that comes back with a different body or a forged signature
   is rejected (400 "bad transcript"). Web Crypto only: runs unchanged in Cloudflare Workers and Node 22. */

const enc = new TextEncoder();

// Canonical JSON: keys sorted at every level, so the client may re-serialise the blocks with any key order.
export function canonical(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value === undefined ? null : value);
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  return '{' + Object.keys(value).filter(k => value[k] !== undefined).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
}

const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
const keys = new Map();   // secret -> CryptoKey (one import per isolate)
async function hmacKey(secret) {
  if (!secret) throw new Error('signing secret missing');
  let k = keys.get(secret);
  if (!k) { k = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']); keys.set(secret, k); }
  return k;
}

export async function sign(blocks, secret) { return hex(await crypto.subtle.sign('HMAC', await hmacKey(secret), enc.encode(canonical(blocks)))); }

export async function verifySig(blocks, sig, secret) {
  if (typeof sig !== 'string' || !/^[0-9a-f]{64}$/.test(sig)) return false;
  return constantTimeEqual(await sign(blocks, secret), sig);
}

export function constantTimeEqual(a, b) {
  a = String(a); b = String(b);
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0;
}

export async function sha256hex(text) { return hex(await crypto.subtle.digest('SHA-256', enc.encode(String(text)))); }

// The secret: ASK_SIGNING_SECRET when set, else the SHA-256 of the API key (never returned anywhere; a different key = new secret).
export async function secretFor(env) {
  if (env && env.ASK_SIGNING_SECRET) return String(env.ASK_SIGNING_SECRET);
  if (env && env.ANTHROPIC_API_KEY) return sha256hex(env.ANTHROPIC_API_KEY);
  throw new Error('neither ASK_SIGNING_SECRET nor ANTHROPIC_API_KEY is set');
}
