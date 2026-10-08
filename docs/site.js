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
    containers.forEach((box, i) => { const h = box.querySelector(':scope > h2'); if (!h || box.dataset.folded) return; box.dataset.folded = '1'; box.classList.add('fold');
      if ((keepOpen || []).includes(i)) box.classList.add('open'); h.setAttribute('role', 'button'); h.setAttribute('tabindex', '0'); h.setAttribute('aria-expanded', String(box.classList.contains('open')));
      // delegated, so a page that re-renders the section's content keeps working
      const flip = () => { const on = !box.classList.contains('open'); box.classList.toggle('open', on); const hh = box.querySelector(':scope > h2'); if (hh) { hh.setAttribute('role', 'button'); hh.setAttribute('tabindex', '0'); hh.setAttribute('aria-expanded', String(on)); } };
      const isHead = t => { const hh = t.closest('h2'); return hh && hh.parentElement === box; };
      box.addEventListener('click', e => { if (isHead(e.target)) flip(); }); box.addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && isHead(e.target)) { e.preventDefault(); flip(); } }); });
    const openHash = () => { const t = location.hash && document.getElementById(location.hash.slice(1)); if (!t) return; const box = t.closest('.fold') || (t.querySelector && t.querySelector(':scope > .fold')); if (box && !box.classList.contains('open')) { box.classList.add('open'); const h = box.querySelector(':scope > h2'); if (h) h.setAttribute('aria-expanded', 'true'); } setTimeout(() => t.scrollIntoView({ block: 'start' }), 30); };
    openHash(); window.addEventListener('hashchange', openHash); }
  const plural = (n, one, many) => n === 1 ? one : (many || one + 's');
  function ordinal(n) { const v = n % 100, s = ['th', 'st', 'nd', 'rd']; return n + (s[(v - 20) % 10] || s[v] || s[0]); }

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
    document.addEventListener('keydown', e => { if (e.key === 'Escape') groups.forEach(o => { o.open = false; }); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wireHeader); else wireHeader();

  return { foldOnPhone, teach, TRIPS, USPS, countyName, countyLabel, dataDate, nice, today, daysOld, stampText, isStale, STALE_DAYS, phaseLabel, namedCancers, cancerLine, plural, ordinal };
})();
