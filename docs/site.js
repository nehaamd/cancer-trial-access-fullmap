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

  const plural = (n, one, many) => n === 1 ? one : (many || one + 's');
  function ordinal(n) { const v = n % 100, s = ['th', 'st', 'nd', 'rd']; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
  return { USPS, countyName, countyLabel, dataDate, nice, today, daysOld, stampText, isStale, STALE_DAYS, phaseLabel, namedCancers, cancerLine, plural, ordinal };
})();
