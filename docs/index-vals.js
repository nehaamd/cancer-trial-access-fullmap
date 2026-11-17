/* The figures the homepage prints in its text, worked out from findings.js. One function, used twice: by index.html in the browser,
   and by prerender_findings.js at each data refresh, which writes the same figures into index.html so the page shows current
   numbers with JavaScript off (and to search engines and link previews). Keys are the page's data-f names. Until November 2026 the
   text in index.html was typed once and went stale at the next refresh. */
(function (root) {
  function indexVals(F, locale) {
    const N = F.nat, R = F.rural;
    const M = v => (Math.round(v / 1e5) / 10).toLocaleString(locale, { maximumFractionDigits: 1 });
    const pct = v => (Math.round(v * 10) / 10).toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const pct0 = v => Math.round(v).toLocaleString(locale);
    const fmt = v => Number(v).toLocaleString(locale);
    // the headline: the typical resident (the median over census tracts, rounded to the nearest ten for the sentence) and the residents with no trial within reach
    const med = N.t60_med, nmZ = Math.round(R.nonmetro.z60), mZ = Math.round(R.metro.z60);
    return { people_z60_m: M(N.people_z60), z60: pct(N.z60), nm_z60: String(nmZ), m_z60: String(mZ), nm_have: nmZ === 1 ? 'has' : 'have', m_have: mZ === 1 ? 'has' : 'have',
             nm_share_z60: R.nonmetro.n_z60 && N.people_z60 ? pct0(100 * R.nonmetro.n_z60 / N.people_z60) : undefined,
             trials: fmt(F.meta.trials), facilities: fmt(F.meta.facilities_named || F.meta.facilities), fac_word: F.meta.facilities_named ? 'named facilities' : 'facilities', t60: fmt(N.t60), t60_med: med ? fmt(med) : undefined, t60_typ: med ? fmt(Math.round(med / 10) * 10) : undefined };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = indexVals; else root.indexVals = indexVals;
})(typeof window !== 'undefined' ? window : this);
