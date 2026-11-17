/* The figures Key findings prints in its text, worked out from findings.js. One function, used twice: by findings.html in the browser,
   and by prerender_findings.js at each data refresh, which writes the same figures into findings.html so the page shows them with
   JavaScript off (and to anything that reads the page without running it). Keys are the page's data-f names. */
(function (root) {
  function findingsVals(F, locale) {
    const N = F.nat, R = F.rural;
    const fmt = v => Number(v).toLocaleString('en-US', { maximumFractionDigits: 12 });   // thousands separators, as d3.format(',') writes them
    const pct = v => (Math.round(v * 10) / 10).toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const M = v => (Math.round(v / 1e5) / 10).toLocaleString(locale, { maximumFractionDigits: 1 });   // people, in millions to one decimal
    const nice = s => { const d = new Date(s + 'T12:00:00'); return isNaN(d) ? s : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); };   // one date style across the site (SITE.nice)
    const numWord = n => (['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen', 'Twenty'])[n] || String(n);
    const listNames = a => a.length > 1 ? a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1] : a.join('');
    const noBroad = F.states_no_broad_list, dataDate = (F.meta.registry_data_timestamp || F.meta.pull).slice(0, 10);
    return { acs: F.meta.acs || 'ACS 5-year', pull: nice(dataDate), people_l20_m: M(N.people_l20), people_z60_m: M(N.people_z60), l20: pct(N.l20), z60: pct(N.z60), g60b: pct(N.g60b), g120b: pct(N.g120b), medn: fmt(N.medn), g60n: pct(N.g60n),
      nm_z60: pct(R.nonmetro.z60), m_z60: pct(R.metro.z60), t60_typ: Math.round(N.t60_med / 10) * 10, t60_med: fmt(N.t60_med), t60_mean: fmt(N.t60), nm_share: pct(100 * R.nonmetro.p / (R.nonmetro.p + R.metro.p)), nm_ratio: Math.round(R.nonmetro.z60 / R.metro.z60), nm_medn: fmt(R.nonmetro.medn), m_medn: fmt(R.metro.medn),
      states_no_broad: F.states_no_broad, states_no_broad_cap: numWord(F.states_no_broad), states_no_broad_names: listNames(noBroad), nci_text: (F.meta.nci_centers ? F.meta.nci_centers + ' centers at ' : '') + F.meta.n_nci + ' locations' + ((F.meta.nci_excluded || []).length ? '; ' + F.meta.nci_excluded.join(', ') + ', which treats children, is not counted' : ''), districts_all_beyond: F.districts.all_beyond_60_broad, broad_counties: fmt(F.states.reduce((s, x) => s + x.broad, 0)), plan: F.meta.plan,
      hb_counties: fmt(F.burden.hb_la_counties), hb_pop: fmt(F.burden.hb_la_pop55), hb_cases: fmt(F.burden.hb_la_cases), cos_date: nice(F.meta.cosponsors_fetched), trials: fmt(F.meta.trials), facilities: fmt(F.meta.facilities_named || F.meta.facilities), fac_word: F.meta.facilities_named ? `named facilities (and ${fmt(F.meta.sites_unresolved)} registry entries that name no institution)` : 'registry-listed facilities', n_tracts: fmt(F.meta.n_tracts), router_mean: F.meta.router.mean_pct, n_nci: F.meta.n_nci };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = findingsVals; else root.findingsVals = findingsVals;
})(typeof window !== 'undefined' ? window : this);
