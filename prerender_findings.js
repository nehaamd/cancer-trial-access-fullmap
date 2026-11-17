/* Writes the figures of Key findings and of the homepage into docs/findings.html and docs/index.html, so the pages show them with JavaScript off and to anything that reads
   the page without running it (search engines, link previews). With JavaScript on, the page fills the same places from findings.js
   with the same function (docs/findings-vals.js), so the two cannot disagree.

     node prerender_findings.js           rewrite docs/findings.html from docs/findings.js
     node prerender_findings.js --check   change nothing; exit 1 if the page's written figures are not the ones findings.js gives

   Runs after build_findings.py in the registry refresh and in the cosponsor refresh; release_gate.py runs the check. Only the text
   inside <span data-f="..."> is touched. Charts and tables are still drawn by the page's script. */
const fs = require('fs'), path = require('path'), vm = require('vm');
const DOCS = path.join(__dirname, 'docs');
const box = { window: {} }; vm.runInNewContext(fs.readFileSync(path.join(DOCS, 'findings.js'), 'utf8'), box);
const F = box.window.FINDINGS; if (!F || !F.nat) { console.error('prerender_findings: docs/findings.js did not define window.FINDINGS'); process.exit(1); }
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
// each page and the function that gives its figures (the page's own script calls the same function in the browser)
const PAGES = [['findings.html', 'findings-vals.js'], ['index.html', 'index-vals.js']];
let failed = false;
for (const [page, fn] of PAGES) {
  const PAGE = path.join(DOCS, page), vals = require(path.join(DOCS, fn))(F, 'en-US');
  const html = fs.readFileSync(PAGE, 'utf8'); let n = 0; const missing = new Set();
  const out = html.replace(/(<span data-f="([a-z0-9_]+)"[^>]*>)([^<]*)(<\/span>)/g, (m, open, key, old, close) => {
    if (vals[key] === undefined || vals[key] === null) { missing.add(key); return m; }
    n++; return open + esc(vals[key]) + close; });
  if (missing.size) { console.error(`prerender_findings: no value for ${[...missing].join(', ')} in docs/${page}`); process.exit(1); }
  if (!n) { console.error(`prerender_findings: no <span data-f> found in docs/${page}`); process.exit(1); }
  if (process.argv.includes('--check')) {
    if (out !== html) { console.error(`prerender_findings: docs/${page} does not carry the figures of docs/findings.js (run: node prerender_findings.js)`); failed = true; }
    else console.log(`prerender_findings: ${n} figures in docs/${page} match docs/findings.js`);
  } else {
    if (out !== html) fs.writeFileSync(PAGE, out);
    console.log(`prerender_findings: ${n} figures written into docs/${page}` + (out === html ? ' (no change)' : ''));
  }
}
if (failed) process.exit(1);
