/* Cancer Clinical Trial Access Map — helpers shared by every page (loaded before each page's own script).
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


  // ---- "Ask the map": the question box. On the map page, ask/ask.js (an ES module) owns the box's behaviour: it posts the question to the
  // helper (a Cloudflare Worker, worker/ in the repository) one model step at a time, runs the model's data tools in the browser over the
  // same files the map draws (ask/engine.js), checks the written summary number by number, renders the answer card and moves the map.
  // The homepage shows the same box and hands the question to map.html?ask=. ASK_URL is the helper's address; while it is empty every
  // question box stays hidden and the site works exactly as before. ASK_TIMEOUT_S is the client's wait per step (ASK_CONTRACT.md §3).
  const ASK_URL = 'https://trial-map-ask.nehaamd.workers.dev/ask';
  const ASK_TIMEOUT_S = 120;
  const escA = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // Example questions showing the breadth of what the box reads: deaths vs access, oncologists vs trials across two units, cosponsors,
  // an NCI distance, a comparison, a rural count, a ZIP lookup, incidence. The short label is what the chip shows; the full question is what it asks.
  const ASK_EXAMPLES = [
    ['Deaths vs access in Texas', 'Which Texas counties have the highest cancer death rates and the least trial access?'],
    ['Texas: oncologists, no trials', 'Counties and districts in Texas with oncologists but no trials'],
    ['Ohio members and H.R. 3521', 'Which Ohio House members have not cosponsored H.R. 3521?'],
    ['Hidalgo County to an NCI center', 'How far is Hidalgo County from an NCI center?'],
    ['Harris vs Hidalgo County', 'Compare Harris County and Hidalgo County'],
    ['Rural Ohio: no trial within 60 mi', 'How many rural Ohio counties have no trial within 60 miles?'],
    ['Breast cancer trials near 78501', 'Breast cancer trials near 78501'],
    ['Highest lung cancer incidence', 'Which counties have the highest lung cancer incidence?']
  ];
  // what the box can answer, in one line: the long form for the homepage, the short form under the box on the map page
  const ASK_HINT = 'Answers questions about the numbers on this map — trial access, distances, incidence and deaths, oncologists, rural and household context, cosponsors — for any county, district or state. Every figure is read from the published data files and the written answer is checked against them number by number. Not medical advice, and not a match of patients to trials.';
  const ASK_HINT_SHORT = 'Answers checked against the map’s data files · not medical advice';
  // The box itself: the label, a two-line question field, the Ask button, the example chips (one row that scrolls, plus a list of all of
  // them under "Try"), and the one-line hint (with the busy status in the same line on the map page). ids askf / askq / askb are fixed.
  // Both pages write the box with this (SITE.mountAskBox), so the markup, the examples and the hint live in one place.
  // hero: the larger homepage version. action: a form action (the homepage hands the question to map.html?ask=). status: a live status line.
  const askChipsHTML = cls => ASK_EXAMPLES.map(([l, q]) => `<button type="button" class="${cls}" data-q="${escA(q)}" title="${escA(q)}">${escA(cls === 'ask-ex-q' ? l : q)}</button>`).join('');
  function askBoxHTML(o) { o = o || {};
    return `<form class="ask${o.hero ? ' ask-hero' : ''}" id="askf" autocomplete="off"${o.action ? ` action="${escA(o.action)}" method="get"` : ''} aria-labelledby="ask-lab">
      <label class="ask-lab" id="ask-lab" for="askq">Ask the map</label>
      <textarea id="askq" name="ask" rows="2" maxlength="400" placeholder="${escA(o.placeholder || 'e.g. Which Texas counties have the least trial access?')}" aria-describedby="ask-hint" enterkeyhint="send"></textarea>
      <button type="submit" id="askb">Ask</button>
      <div class="ask-exrow">${o.hero ? '<span class="ask-ex-lead">Try:</span>' : '<details class="ask-more"><summary aria-label="All example questions">Try <span aria-hidden="true">▾</span></summary><div class="ask-ex-list" role="group" aria-label="Example questions">' + askChipsHTML('ask-ex-full') + '</div></details>'}<div class="ask-ex" role="group" aria-label="Example questions">${askChipsHTML('ask-ex-q')}</div></div>
      <p class="ask-foot"><span class="ask-hint" id="ask-hint">${o.hero ? ASK_HINT : ASK_HINT_SHORT}</span>${o.status ? '<span class="ask-status" id="ask-status" role="status" aria-live="polite"></span>' : ''}</p>
    </form>`; }
  // Keyboard and chips: Enter asks (Shift+Enter starts a new line); a chip fills the box and asks; the "Try" list closes on Escape or a click elsewhere.
  function wireAskBox(form) { const ta = form.querySelector('#askq'); if (!ta) return;
    const submit = () => { if (form.requestSubmit) form.requestSubmit(); else form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true })); };
    ta.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); } });
    const more = form.querySelector('.ask-more');
    form.querySelectorAll('.ask-ex-q,.ask-ex-full').forEach(b => b.addEventListener('click', () => { if (more) more.open = false; ta.value = b.dataset.q; ta.focus(); submit(); }));
    if (more) { const host = form.closest('.fcard'); more.addEventListener('toggle', () => { if (host) host.classList.toggle('ask-open', more.open); });   // the open list paints over the map's other cards
      document.addEventListener('click', e => { if (more.open && !more.contains(e.target)) more.open = false; });
      more.addEventListener('keydown', e => { if (e.key === 'Escape' && more.open) { e.stopPropagation(); more.open = false; more.querySelector('summary').focus(); } });
      more.addEventListener('focusout', e => { if (more.open && e.relatedTarget && !more.contains(e.relatedTarget)) more.open = false; }); } }
  // Writes the box into its mount point and wires it; returns the form. The mount stays empty (and hidden) while ASK_URL is empty.
  function mountAskBox(el, o) { if (!el) return null; el.innerHTML = askBoxHTML(o); const f = el.querySelector('#askf'); wireAskBox(f); el.hidden = false; return f; }
  // ids the map uses: a county FIPS (5 digits), a district geoid (4 digits), a state USPS code (2 letters)
  const idKind = id => /^\d{5}$/.test(String(id)) ? 'county' : /^\d{4}$/.test(String(id)) ? 'district' : /^[A-Z]{2}$/i.test(String(id)) ? 'state' : null;
  const placeHref = id => { const k = idKind(id); return k === 'county' ? 'map.html?c=' + id : k === 'district' ? 'map.html?d=' + id : k === 'state' ? 'map.html?s=' + String(id).toUpperCase() : null; };
  // The box's styles (both pages). The answer card's styles are in ask/ask.css, loaded by ask/ask.js on the map page.
  // Colours come from the site's tokens (site.css :root); the two tints are mixed from them, with the paper colour as the fallback.
  const ASK_CSS = '.ask{--ask-tint:var(--paper,#F7F5F0);--ask-tint-2:var(--rule,#E6E2DA);--ask-tint:color-mix(in srgb,var(--sky,#9EC4E0) 22%,var(--card,#fff));--ask-tint-2:color-mix(in srgb,var(--sky,#9EC4E0) 40%,var(--card,#fff))}.ask{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 8px;align-items:stretch}.ask[hidden],.ask-mount[hidden]{display:none!important}'
    + '.ask .ask-lab{grid-column:1/-1;margin:0;line-height:1.25;font-weight:700;color:var(--navy);font-size:var(--fs-2,1.08rem);letter-spacing:-.01em}'
    + '.ask textarea,.ask input{grid-column:1;width:100%;min-width:0;border:1px solid var(--rule-2,#CFCBC2);border-radius:8px;padding:.45rem .65rem;font:inherit;font-size:var(--fs-1,.95rem);line-height:1.3;background:var(--card,#fff);color:var(--ink);resize:none;box-sizing:border-box}'
    + '.ask textarea{min-height:calc(2 * 1.3em + .9rem + 2px)}.ask textarea:focus,.ask input:focus{outline:none;border-color:var(--gulf,#3F7FB5);box-shadow:0 0 0 4px rgba(63,127,181,.15)}'
    + '.ask button[type=submit]{grid-column:2;align-self:stretch;border:0;border-radius:8px;padding:.45rem 1.1rem;font:inherit;font-size:var(--fs-1,.95rem);font-weight:700;background:var(--navy,#0B3C5D);color:#fff;cursor:pointer;min-width:4.2rem}.ask button[type=submit]:hover{background:var(--gulf,#3F7FB5)}.ask button[type=submit][disabled]{opacity:.65;cursor:progress}'
    // the example row: "Try ▾" opens the full list; beside it one row of chips scrolls sideways, the last one cut off as the sign that there are more
    + '.ask .ask-exrow{grid-column:1/-1;display:flex;align-items:center;gap:.3rem;min-width:0}'
    + '.ask .ask-ex{flex:1 1 auto;display:flex;align-items:center;gap:.3rem;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch;padding:1px 0 2px;margin:0 -2px;min-width:0;mask-image:linear-gradient(90deg,#000 calc(100% - 28px),transparent);-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 28px),transparent)}.ask .ask-ex::-webkit-scrollbar{display:none}'
    + '.ask .ask-ex-lead{flex:0 0 auto;font-size:var(--fs-0,.84rem);font-weight:650;color:var(--ink-2);padding-left:2px}'
    + '.ask .ask-ex-q,.ask .ask-ex-full{flex:0 0 auto;font:inherit;font-size:var(--fs-0,.84rem);font-weight:600;color:var(--navy,#0B3C5D);background:var(--ask-tint);border:1px solid var(--ask-tint-2);border-radius:999px;padding:.26rem .7rem;cursor:pointer;line-height:1.3;white-space:nowrap}.ask .ask-ex-q:hover,.ask .ask-ex-full:hover{background:var(--ask-tint-2);border-color:var(--gulf,#3F7FB5)}'
    + '.ask .ask-more{position:relative;flex:0 0 auto}.ask .ask-more>summary{list-style:none;cursor:pointer;font-size:var(--fs-0,.84rem);font-weight:650;color:var(--navy);padding:.26rem .4rem .26rem 2px;border-radius:6px;white-space:nowrap}.ask .ask-more>summary::-webkit-details-marker{display:none}.ask .ask-more>summary:hover,.ask .ask-more[open]>summary{background:var(--ask-tint)}'
    + '.ask .ask-ex-list{position:absolute;left:0;top:calc(100% + 6px);z-index:35;display:grid;gap:.25rem;width:max-content;max-width:min(520px,calc(100vw - 32px));padding:.45rem;background:var(--card,#fff);border:1px solid var(--rule-2,#CFCBC2);border-radius:10px;box-shadow:0 10px 28px rgba(27,36,48,.16)}.ask .ask-ex-full{white-space:normal;text-align:left;border-radius:8px}'
    + '.ask .ask-foot{grid-column:1/-1;margin:0;font-size:.78rem;line-height:1.3;color:var(--ink-3,#5F6B78);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}.ask.ask-hero .ask-foot{white-space:normal}.ask .ask-status{color:var(--ink-2);font-weight:600}.ask .ask-hint[hidden]{display:none}'
    // the homepage: a larger box with the chips wrapping onto several lines
    + '.ask.ask-hero{gap:8px 10px;padding:1.1rem 1.2rem 1rem;background:var(--card,#fff);border:1px solid var(--rule,#E6E2DA);border-left:5px solid var(--navy,#0B3C5D);border-radius:var(--r,10px);box-shadow:var(--shadow)}'
    + '.ask.ask-hero .ask-lab{font-family:"Source Serif 4",Georgia,serif;font-size:var(--fs-3,1.35rem);font-weight:600}.ask.ask-hero textarea{font-size:var(--fs-2,1.08rem);padding:.6rem .8rem;min-height:calc(2 * 1.3em + 1.2rem + 2px)}'
    + '.ask.ask-hero button[type=submit]{font-size:var(--fs-2,1.08rem);padding:.6rem 1.5rem;border-radius:999px;min-width:6rem}.ask.ask-hero .ask-exrow{align-items:baseline;flex-wrap:wrap}.ask.ask-hero .ask-ex{flex:1 1 320px;flex-wrap:wrap;overflow:visible;mask-image:none;-webkit-mask-image:none;margin:2px 0 0}.ask.ask-hero .ask-ex-q{padding:.3rem .75rem}.ask.ask-hero .ask-foot{font-size:var(--fs-0,.84rem)}'
    + '@media (max-width:720px){.ask .ask-lab{font-size:var(--fs-1,.95rem)}.ask.ask-hero{padding:.9rem .9rem .8rem}}'
    + '@media (max-width:640px){.ask textarea,.ask input{font-size:16px}.ask.ask-hero textarea{min-height:calc(3 * 1.3em + 1.2rem + 2px)}.ask .ask-ex-q,.ask .ask-ex-full,.ask button[type=submit],.ask .ask-more>summary{min-height:40px}.ask .ask-ex-list{position:fixed;left:12px;right:12px;top:auto;bottom:12px;max-width:none;width:auto;max-height:70vh;overflow:auto}}'
    + '@media (prefers-reduced-motion:reduce){.ask .ask-ex{scroll-behavior:auto}}';
  function askStyles() { if (document.getElementById('ask-css')) return; const st = document.createElement('style'); st.id = 'ask-css'; st.textContent = ASK_CSS; document.head.appendChild(st); }

  return { ASK_URL, ASK_TIMEOUT_S, ASK_EXAMPLES, ASK_HINT, ASK_HINT_SHORT, askBoxHTML, mountAskBox, wireAskBox, askStyles, escA, idKind, placeHref, foldOnPhone, teach, TRIPS, USPS, countyName, countyLabel, dataDate, nice, today, daysOld, stampText, isStale, STALE_DAYS, phaseLabel, namedCancers, cancerLine, plural, listJoin, ordinal, nearestFor, driveTime, rate, period };
})();
