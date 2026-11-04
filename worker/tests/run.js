// node tests/run.js https://trial-map-ask.<account>.workers.dev/ask
const url = process.argv[2]; if (!url) { console.error('usage: node tests/run.js <ask url>'); process.exit(2); }
const qs = require('./questions.json');
(async () => {
  let bad = 0;
  for (const t of qs) {
    const t0 = Date.now();
    const r = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json', 'origin': 'http://localhost:8080' }, body: JSON.stringify({ q: t.q }) });
    const j = await r.json().catch(() => ({}));
    const vq = (j.view && j.view.qs) || '';
    const ok = r.ok && j.route === t.route && t.qs_has.every(s => vq.includes(s));
    if (!ok) bad++;
    console.log(`${ok ? 'ok  ' : 'FAIL'} ${Date.now() - t0}ms  [${j.route || r.status}] ${t.q}\n      view: ${vq || '-'}  hl: ${(j.view && j.view.hl || []).join(',') || '-'}\n      ${(j.answer || j.error || '').replace(/\s+/g, ' ').slice(0, 280)}\n`);
  }
  console.log(`${qs.length - bad}/${qs.length} as expected`); process.exit(bad ? 1 : 0);
})();
