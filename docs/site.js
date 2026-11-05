/* Cancer Trial Access Map — helpers shared by every page (loaded before each page's own script).
   Nothing here depends on a particular data pull: every label is derived from the data files at view time. */
window.SITE = (function () {
  const USPS = {"01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE","11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA","20":"KS","21":"KY","22":"LA","23":"ME","24":"MD","25":"MA","26":"MI","27":"MN","28":"MS","29":"MO","30":"MT","31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM","36":"NY","37":"NC","38":"ND","39":"OH","40":"OK","41":"OR","42":"PA","44":"RI","45":"SC","46":"SD","47":"TN","48":"TX","49":"UT","50":"VT","51":"VA","53":"WA","54":"WV","55":"WI","56":"WY"};

  // Full name of a county-equivalent: "Harris County", "Baltimore city", "Orleans Parish", "Anchorage Municipality".
  // data.js carries the Census Bureau's own full name as c.nl; the rules below only cover a data file built before that field existed.
  function countyName(c, fips) {
    if (c && c.nl) return c.nl;
    const n = c ? c.n : '', st = String(fips || '').slice(0, 2), co = +String(fips || '').slice(2);
    if (fips === '11001' || fips === '32510') return n;                       // District of Columbia, Carson City
    if (st === '22') return n + ' Parish';
    if (st === '02') return n;                                                // Alaska: boroughs, census areas and municipalities
    if ((st === '51' && co >= 500) || fips === '24510' || fips === '29510') return n + ' city';   // independent cities
    return n + ' County';
  }
  const countyLabel = (c, fips) => countyName(c, fips) + ', ' + (USPS[String(fips || '').slice(0, 2)] || '');

  // Dates. The "data as of" date is the registry's own data timestamp when the pull recorded one.
  const dataDate = meta => String(meta.registry_data_timestamp || meta.pull || '').slice(0, 10);
  function nice(iso, month) { const d = new Date(String(iso).slice(0, 10) + 'T12:00:00'); return isNaN(d) ? String(iso) : d.toLocaleDateString('en-US', { month: month || 'short', day: 'numeric', year: 'numeric' }); }
  function today() { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }   // the reader's date, not UTC
  function daysOld(iso) { const d = new Date(String(iso).slice(0, 10) + 'T12:00:00'); return isNaN(d) ? null : Math.floor((Date.now() - d.getTime()) / 864e5); }
  const STALE_DAYS = 10;   // older than this, the pages say how many days old the registry data is
  function stampText(meta) { const dd = dataDate(meta), age = daysOld(dd); return 'Data as of ' + nice(dd) + (age !== null && age > STALE_DAYS ? ' (' + age + ' days ago)' : ''); }
  const isStale = meta => { const a = daysOld(dataDate(meta)); return a !== null && a > STALE_DAYS; };

  // Trial phase as the registry writes it ("PHASE1", "PHASE1/PHASE2", "PHASE2;PHASE3", "NA") or as this site stores it ("1-2", "NA").
  function phaseLabel(p) {
    const s = String(p == null ? '' : p).trim().toUpperCase();
    if (!s || s === 'NA' || s === 'N/A') return 'Not phased';
    const nums = s.replace(/EARLY_PHASE1/g, '1').replace(/PHASE/g, '').split(/[\/;,|\s-]+/).filter(Boolean);
    return nums.length && nums.every(x => /^\d$/.test(x)) ? 'Phase ' + nums.join('-') : 'Phase ' + s;
  }

  // The cancers a trial names, leaving out the two catch-all buckets (a basket trial never "names" its own bucket).
  function namedCancers(T, j) { return (T.cats[j] || []).filter(ci => T.types[ci] && T.types[ci][0] !== 'multi' && T.types[ci][0] !== 'other_unclassified').map(ci => T.types[ci][1]); }
  // One plain-text line for a trial's cancer type: "Breast", or "Multiple cancer types / basket or umbrella: names Breast, Lung & thoracic".
  function cancerLine(T, j) {
    const primary = T.types[T.ct[j]] ? T.types[T.ct[j]][1] : ''; if (!T.multi[j]) return primary;
    const named = namedCancers(T, j); return primary + (named.length ? ': names ' + named.join(', ') : ' (cancers not named individually)');
  }

  // One general sentence shown when a cancer type is chosen: a count of trials overstates the options for any one person.
  const teach = () => 'A count of trials is not the same as trials that fit one person: stage, test results and past treatment narrow the list.';
  // One sentence for the distance figures: a distance on the map is a trip that participation may require many times.
  const TRIPS = 'Participation may require this trip many times: treatment trials often need visits every one to three weeks at first, plus extra scans and blood tests.';
  // Phone only (640 px and narrower): fold long reading pages section by section. containers: elements whose direct
  // children are the heading (h2) and its content; keepOpen: indexes left open. Laptop and tablet layouts are untouched.
  function foldOnPhone(containers, keepOpen) {
    if (!window.matchMedia('(max-width:640px)').matches) return;
    // the heading stays a heading for assistive technology; a button inside it carries the expanded state and the keyboard behaviour
    const ensureBtn = (hh, on) => { let b = hh.querySelector(':scope > button.fold-btn'); if (!b) { b = document.createElement('button'); b.type = 'button'; b.className = 'fold-btn'; while (hh.firstChild) b.appendChild(hh.firstChild); hh.appendChild(b); } b.setAttribute('aria-expanded', String(on)); return b; };
    containers.forEach((box, i) => { const h = box.querySelector(':scope > h2'); if (!h || box.dataset.folded) return; box.dataset.folded = '1'; box.classList.add('fold');
      if ((keepOpen || []).includes(i)) box.classList.add('open'); ensureBtn(h, box.classList.contains('open'));
      // delegated, so a page that re-renders the section's content keeps working
      const flip = () => { const on = !box.classList.contains('open'); box.classList.toggle('open', on); const hh = box.querySelector(':scope > h2'); if (hh) ensureBtn(hh, on); };
      const isHead = t => { const hh = t.closest('h2'); return hh && hh.parentElement === box; };
      box.addEventListener('click', e => { if (isHead(e.target)) flip(); }); });
    const openHash = () => { const t = location.hash && document.getElementById(location.hash.slice(1)); if (!t) return; const box = t.closest('.fold') || (t.querySelector && t.querySelector(':scope > .fold')); if (box && !box.classList.contains('open')) { box.classList.add('open'); const h = box.querySelector(':scope > h2'); const b = h && h.querySelector(':scope > button.fold-btn'); if (b) b.setAttribute('aria-expanded', 'true'); } setTimeout(() => t.scrollIntoView({ block: 'start' }), 30); };
    openHash(); window.addEventListener('hashchange', openHash); }
  // Drive time from hours, as the map writes it: "a few minutes", "about 25 min", "about 1 h 50 min".
  function driveTime(h) { const m = Math.round(h * 60); if (m < 5) return 'a few minutes'; if (m < 60) return `about ${Math.round(m / 5) * 5} min`; const hh = Math.floor(m / 60), mm = Math.round((m - hh * 60) / 10) * 10; return mm === 60 ? `about ${hh + 1} h` : `about ${hh} h${mm ? ' ' + mm + ' min' : ''}`; }
  // A published rate or percentage with its one decimal kept ("173.0", not "173"); a period with an en dash ("2020–2024").
  const rate = v => v === null || v === undefined ? '—' : Number(v).toFixed(1);
  const period = s => String(s).replace('-', '–');
  const plural = (n, one, many) => n === 1 ? one : (many || one + 's');
  const listJoin = a => a.length <= 1 ? a.join('') : a.length === 2 ? a.join(' and ') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1];   // "A, B and C"
  function ordinal(n) { const v = n % 100, s = ['th', 'st', 'nd', 'rd']; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
  // The places nearest to the most residents 55+ of an area, from the [[name, % of residents], ...] list the data files carry (ns / bs: the top three,
  // tract_metrics_us.py): "Markey Cancer Center (Kentucky) for 78.3% of residents · Vanderbilt-Ingram Cancer Center 21.4% · OSU – James 0.3%".
  // Replaces the single "most often X" (X is the first entry). '' when nobody there has a road route; the old parenthetical when a data file predates the list.
  // Named only when a place is nearest for at least one resident in ten: below that (the nation: 3.3%) the names say nothing.
  function nearestFor(list, modal, esc) { const e = esc || (x => x); const p = v => v >= 99.95 ? '100' : v < 0.05 ? '<0.1' : v.toFixed(1);
    if (Array.isArray(list)) return list.length && list[0][1] >= 10 ? ' (' + list.map((x, i) => i === 0 ? `${e(x[0])} for ${p(x[1])}% of residents` : `${e(x[0])} ${p(x[1])}%`).join(' · ') + ')' : '';
    return modal && !/^NO ROAD/.test(modal) ? ' (most often ' + e(modal) + ')' : ''; }

  // Header: on a phone the page links sit behind a Menu button (the links stay visible without JavaScript);
  // on a laptop the two audience groups open as small menus, one at a time, and close on a click elsewhere or Escape.
  document.documentElement.classList.add('js');
  function wireHeader() {
    const hdr = document.querySelector('header.site'), nav = hdr && hdr.querySelector('.hdr-links'); if (!hdr || !nav || hdr.querySelector('.hdr-menu-btn')) return;
    if (!nav.id) nav.id = 'hdr-links';
    const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'hdr-menu-btn'; btn.setAttribute('aria-expanded', 'false'); btn.setAttribute('aria-controls', nav.id);
    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>Menu';
    btn.addEventListener('click', () => { const on = !hdr.classList.contains('nav-open'); hdr.classList.toggle('nav-open', on); btn.setAttribute('aria-expanded', String(on)); });
    nav.parentNode.insertBefore(btn, nav);
    const groups = Array.from(nav.querySelectorAll('details.hdr-group'));
    groups.forEach(g => g.addEventListener('toggle', () => { if (g.open) groups.forEach(o => { if (o !== g) o.open = false; }); }));
    document.addEventListener('click', e => { if (!hdr.contains(e.target)) groups.forEach(o => { o.open = false; }); });
    // Escape closes the audience menus and, on a phone, the open page menu (focus goes back to its button)
    document.addEventListener('keydown', e => { if (e.key !== 'Escape') return; groups.forEach(o => { o.open = false; });
      if (hdr.classList.contains('nav-open')) { hdr.classList.remove('nav-open'); btn.setAttribute('aria-expanded', 'false'); const a = document.activeElement; if (!a || a === document.body || nav.contains(a)) btn.focus(); } });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wireHeader); else wireHeader();


  // ---- "Ask the map": the question box. The site posts the question to a small helper (a Cloudflare Worker, worker/ in the
  // repository) that reads the same published data files as the Data API and returns {answer, table, sources, view}.
  // ASK_URL is the helper's address; while it is empty every question box stays hidden and the site works exactly as before.
  const ASK_URL = 'https://trial-map-ask.nehaamd.workers.dev/ask';
  async function ask(q) {
    const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), 45000);
    try {
      const r = await fetch(ASK_URL, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ q }), signal: ctrl.signal });
      const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status)); return j;
    } finally { clearTimeout(t); }
  }
  const escA = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // The answer card: the question, the answer, the rows it was written from, the files it read, and what the box is not.
  function askCardHTML(q, res) {
    const rows = Array.isArray(res.table) ? res.table : []; let table = '';
    if (rows.length) { const cols = Object.keys(rows[0]); table = '<div class="ask-tbl"><table><thead><tr>' + cols.map(c => '<th>' + escA(c) + '</th>').join('') + '</tr></thead><tbody>' + rows.map(r => '<tr>' + cols.map(c => '<td>' + escA(r[c]) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div>'; }
    const src = (res.sources || []).length ? '<p class="ask-src">Read from: ' + res.sources.map(s => '<a href="' + escA(s.url) + '" target="_blank" rel="noopener">' + escA(s.title) + '</a>').join(', ') + (res.data_as_of ? ' · data as of ' + escA(nice(res.data_as_of)) : '') + '</p>' : '';
    const note = res.route === 'search' || res.route === 'data' ? '<p class="ask-note">Figures are read from this site’s published data files, not written by the model. The box lists and ranks; it does not match patients to trials or give medical advice.</p>' : '';
    return '<div class="ask-card" id="ask-card" role="region" aria-label="Answer"><button type="button" class="ask-x" aria-label="Close answer">×</button><p class="ask-q">' + escA(q) + '</p><div class="ask-a">' + escA(res.answer || '').split(/\n+/).map(x => '<p>' + x + '</p>').join('') + '</div>' + table + src + note + '</div>';
  }
  const ASK_CSS = '.ask{display:flex;gap:6px;align-items:stretch}.ask input{flex:1;min-width:0;border:1px solid var(--rule);border-radius:8px;padding:.5rem .65rem;font:inherit;font-size:var(--fs-0,.95rem);background:var(--card,#fff);color:var(--ink)}.ask input:focus{outline:2px solid var(--gulf,#2F6F8F);outline-offset:1px}.ask button{border:0;border-radius:8px;padding:.45rem .8rem;font:inherit;font-weight:600;background:var(--navy,#1B2430);color:#fff;cursor:pointer}.ask button[disabled]{opacity:.6;cursor:progress}.ask-hint{margin:.15rem 0 0;font-size:.8rem;color:var(--ink-3,#6B7280)}'
    + '.ask-card{position:relative;margin:.8rem 1.25rem 0;padding:.8rem 2.2rem .7rem .9rem;border:1px solid var(--rule);border-left:4px solid var(--rust,#B5452F);border-radius:8px;background:var(--paper,#F7F4EE)}.ask-card .ask-x{position:absolute;top:.35rem;right:.45rem;border:0;background:none;font-size:1.3rem;line-height:1;color:var(--ink-3);cursor:pointer}.ask-card .ask-q{margin:0 0 .35rem;font-weight:600;color:var(--ink-2)}.ask-card .ask-a p{margin:0 0 .4rem}.ask-tbl{overflow:auto;margin:.4rem 0}.ask-tbl table{border-collapse:collapse;font-size:.82rem;width:100%}.ask-tbl th,.ask-tbl td{text-align:left;padding:.25rem .45rem;border-bottom:1px solid var(--rule);vertical-align:top}.ask-tbl th{font-weight:600;color:var(--ink-2)}.ask-src,.ask-note{margin:.35rem 0 0;font-size:.78rem;color:var(--ink-3)}.ask-card.err{border-left-color:var(--ink-3)}'
    + '@media (max-width:720px){.ask-card{margin:.6rem var(--gutter,1rem) 0}}';
  function askStyles() { if (document.getElementById('ask-css')) return; const st = document.createElement('style'); st.id = 'ask-css'; st.textContent = ASK_CSS; document.head.appendChild(st); }

  return { ASK_URL, ask, askCardHTML, askStyles, foldOnPhone, teach, TRIPS, USPS, countyName, countyLabel, dataDate, nice, today, daysOld, stampText, isStale, STALE_DAYS, phaseLabel, namedCancers, cancerLine, plural, listJoin, ordinal, nearestFor, driveTime, rate, period };
})();
