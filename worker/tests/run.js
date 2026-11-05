// Live check against a deployed worker (needs the network and the worker's model key; the offline suite is worker/tests/offline.js).
//   node worker/tests/run.js https://trial-map-ask.<account>.workers.dev/ask [--only <substring>] [--max <n>] [--fast]
// Reads the same questions.json as offline.js: each case's expect.route (or routes) and expect.qs_has are checked; the rest of the
// expectations (table checks, hl ids, plan fields) are offline-only. Accepts the response shape {q, route, answer, table, sources,
// view, data_as_of, caveats, plan, deterministic} and the older one without caveats/deterministic/plan.
const argv = process.argv.slice(2);
const url = argv.find(a => /^https?:\/\//.test(a)); if (!url) { console.error('usage: node tests/run.js <ask url> [--only <substring>] [--max <n>] [--fast]'); process.exit(2); }
const opt = (name) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
const only = (opt('--only') || '').toLowerCase(); const max = parseInt(opt('--max')) || Infinity; const fast = argv.includes('--fast');
let qs = require('./questions.json');
qs = qs.filter(t => !only || String(t.q).toLowerCase().includes(only) || String(t.cat || '').toLowerCase().includes(only)).slice(0, max);
(async () => {
  let bad = 0; let det = 0, fallback = 0;
  for (const t of qs) {
    if (qs.indexOf(t) && !fast) await new Promise(r => setTimeout(r, 5000));   // stay under the per-visitor rate limit
    const ex = t.expect || t;   // new shape {expect:{route|routes, qs_has}} or the old flat one {route, qs_has}
    const routes = ex.routes || (ex.route ? [ex.route] : []); const qsHas = ex.qs_has || [];
    const t0 = Date.now();
    let r, j = {};
    try { r = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json', 'origin': 'http://localhost:8080' }, body: JSON.stringify({ q: t.q }) }); j = await r.json().catch(() => ({})); }
    catch (e) { console.log(`FAIL ${t.q}\n      fetch error: ${e}`); bad++; continue; }
    const view = j.view || {}; const vq = typeof view.qs === 'string' ? view.qs : view.qs ? new URLSearchParams(view.qs).toString() : '';
    const ok = r.ok && (!routes.length || routes.includes(j.route)) && qsHas.every(s => vq.includes(s));
    if (!ok) bad++;
    if (j.deterministic === true) det++; else if (j.deterministic === false) fallback++;
    const caveats = Array.isArray(j.caveats) ? j.caveats : (j.caveats ? [String(j.caveats)] : []);
    console.log(`${ok ? 'ok  ' : 'FAIL'} ${Date.now() - t0}ms  [${j.route || r.status}${j.deterministic === true ? ', deterministic' : j.deterministic === false ? ', model-written' : ''}] ${t.q}\n      view: ${vq || '-'}  hl: ${(view.hl || []).join(',') || '-'}${caveats.length ? '\n      caveats: ' + caveats.join(' | ').slice(0, 240) : ''}\n      ${(j.answer || j.error || '').replace(/\s+/g, ' ').slice(0, 280)}${j.detail ? '\n      detail: ' + String(j.detail).slice(0, 300) : ''}\n`);
  }
  console.log(`${qs.length - bad}/${qs.length} as expected${det || fallback ? ` (${det} deterministic answers, ${fallback} model-written)` : ''}`); process.exit(bad ? 1 : 0);
})();
