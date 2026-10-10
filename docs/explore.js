/* Cancer Trial Access Map — helpers for the question-based pages (community.html, act.html, learn.html).
   Reads community.js (built by build_community.py from the same files the map reads) so these pages cannot disagree with the map.
   Nothing here depends on a particular data pull. */
window.EXPLORE = (function () {
  const X = window.COMMUNITY, M = X.meta, CC = X.ccols, NAT = M.nat;
  const fmt = n => (n === null || n === undefined || isNaN(n)) ? '—' : Math.round(n).toLocaleString('en-US');
  const pct = v => (v === null || v === undefined || isNaN(v)) ? '—' : (Math.round(v * 10) / 10).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const people = n => n === null || n === undefined ? '—' : n >= 9.95e5 ? (n / 1e6).toFixed(1) + ' million' : fmt(Math.round(n));   // the map's rule (index.html), so the same figure prints the same everywhere
  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  const cdLabel = cd => (cd === '0' || cd === '00' || cd === 0 || cd === 'AL') ? 'At large' : String(+cd);
  const stName = st => X.states[st] ? X.states[st].name : st;
  const typeLabel = {}; M.types.forEach(([k, l]) => typeLabel[k] = l);
  const typeIndex = {}; M.types.forEach(([k], i) => typeIndex[k] = i);          // position in a by-type array (ct)
  const btypeIndex = {}; M.btypes.forEach((k, i) => btypeIndex[k] = i);        // position in a county's zero-share array (zt)
  const dataDate = () => SITE.dataDate({ registry_data_timestamp: M.registry_data_timestamp, pull: M.pull });

  // ---- places ----
  function county(cf) { const a = X.counties[cf]; if (!a) return null; const o = { k: cf, kind: 'county' }; CC.forEach((c, i) => o[c] = a[i]); o.label = o.n + ', ' + o.st; o.name = o.n; o.metro = o.ru === null ? null : o.ru <= 3; return o; }
  function district(k) { const d = X.districts[k]; if (!d) return null; return { k, kind: 'district', ...d, label: d.st + '-' + cdLabel(d.cd), name: stName(d.st) + (cdLabel(d.cd) === 'At large' ? ' (at-large district)' : "'s " + SITE.ordinal(+d.cd) + ' congressional district') }; }
  function state(st) { const g = X.states[st]; if (!g) return null; return { k: st, kind: 'state', ...g, label: g.name }; }
  const nation = () => ({ k: 'US', kind: 'nat', ...NAT, label: 'United States', name: 'the United States' });
  function fromParams(p) { if (p.get('c') && X.counties[p.get('c')]) return county(p.get('c')); if (p.get('d') && X.districts[p.get('d')]) return district(p.get('d')); if (p.get('s') && X.states[(p.get('s') || '').toUpperCase()]) return state(p.get('s').toUpperCase()); return null; }
  const param = pl => pl.kind === 'county' ? 'c=' + pl.k : pl.kind === 'district' ? 'd=' + pl.k : pl.kind === 'state' ? 's=' + pl.k : '';
  const links = pl => { const q = param(pl); return { map: 'index.html' + (q ? '?' + q : ''), brief: 'brief.html' + (q ? '?' + q : ''), act: 'act.html' + (q ? '?' + q : ''), community: 'community.html' + (q ? '?' + q : ''), compare: pl.kind === 'county' ? `index.html?s=${pl.st}&tab=compare` : pl.kind === 'district' ? `index.html?s=${pl.st}&tab=compare` : pl.kind === 'state' ? `index.html?s=${pl.k}&tab=compare` : 'index.html?tab=compare', trials: pl.kind === 'county' ? `trials.html?county=${pl.k}` : null }; };

  // ---- comparisons ----
  function stateOf(pl) { return pl.kind === 'state' ? pl : pl.kind === 'nat' ? null : state(pl.st); }
  // rank of a county's share-short among the counties of its state (1 = most residents short)
  function countyRank(c) { const rows = Object.keys(X.counties).filter(k => k.slice(0, 2) === c.k.slice(0, 2)).map(k => county(k)).filter(x => x.l20 !== null && x.l20 !== undefined); rows.sort((a, b) => b.l20 - a.l20); const i = rows.findIndex(x => x.k === c.k); return { rank: i + 1, of: rows.length, above: rows.filter(x => x.l20 > c.l20).length }; }
  function districtRank(d) { const rows = Object.keys(X.districts).map(k => district(k)); rows.sort((a, b) => b.l20 - a.l20); const i = rows.findIndex(x => x.k === d.k); const inState = rows.filter(x => x.st === d.st); return { rank: i + 1, of: rows.length, stRank: inState.findIndex(x => x.k === d.k) + 1, stOf: inState.length }; }
  function stateRank(s) { const rows = Object.keys(X.states).map(k => state(k)); rows.sort((a, b) => b.l20 - a.l20); return { rank: rows.findIndex(x => x.k === s.k) + 1, of: rows.length }; }

  // ---- the local summary: a few plain sentences with their numbers (the same figures the map and brief show) ----
  function facts(pl) {
    const F = []; const st = stateOf(pl); const n20 = pl.kind === 'nat' && pl.people_l20 ? pl.people_l20 : pl.p * pl.l20 / 100, n0 = pl.kind === 'nat' && pl.people_z60 ? pl.people_z60 : pl.p * pl.z60 / 100;   // nation: tract sums, as on the map
    const where = pl.kind === 'county' ? 'in ' + pl.n : pl.kind === 'district' ? 'in ' + pl.label : pl.kind === 'state' ? 'in ' + pl.name : 'in the United States';
    F.push({ id: 'short', num: pct(pl.l20), unit: '%', hot: pl.l20 >= 50,
      text: `of residents 55 and older ${where} — ${people(n20)} people — have fewer than 20 recruiting cancer treatment trials within 60 road-miles of home. ${n0 < 1 ? 'Everyone here has at least one listed trial within that distance.' : `${pct(pl.z60)}% (${people(n0)}) have none.`}`,
      cmp: pl.kind === 'nat' ? '' : `${st && pl.kind !== 'state' ? `${esc(st.name)}: ${pct(st.l20)}% · ` : ''}United States: ${pct(NAT.l20)}%`,
      why: 'Twenty trials is an exploratory threshold chosen for this map, not a clinical cut-off: any one person qualifies for only some trials, so it asks whether there is some choice nearby. Distance is measured in road-miles; how long the drive takes varies with roads, traffic and where people live. Trials often need repeated visits.' });
    if (pl.kind === 'county') {
      F.push({ id: 'trials', num: fmt(pl.t), unit: pl.t === 1 ? ' trial' : ' trials', hot: pl.t === 0,
        text: pl.t ? `${pl.t === 1 ? 'has' : 'have'} a recruiting site in the county (${fmt(pl.f)} ${SITE.plural(pl.f, 'site')}); ${fmt(pl.t60)} within 60 road-miles of the county’s population center. The typical (median) resident 55+ has ${fmt(pl.tm)} within reach.` : `No listed trial has a recruiting site in the county. ${fmt(pl.t60)} ${SITE.plural(pl.t60, 'trial has', 'trials have')} a site within 60 road-miles of the county’s population center; the typical resident 55+ has ${fmt(pl.tm)} within reach.`,
        cmp: st ? `${esc(st.name)}: ${fmt(st.cwt)} of ${fmt(st.counties)} counties have a trial · ${fmt(st.broad)} host a broad menu (100 or more)` : '',
        why: 'A trial “in the county” is a registry row that lists a recruiting site here. Big centers appear under many names, and a listed site is not a promise that it is enrolling this week.' });
    }
    const road = pl.kind === 'county'
      ? (pl.noroad === 'island' ? { num: '—', unit: '', text: `No road connection from this county to ${pl.rn !== null ? 'a broad menu of trials; the nearest NCI-designated center is ' + esc(pl.nn) + ', ' + fmt(pl.rn) + ' road-miles' : 'any NCI-designated cancer center or broad menu of trials'} (island or disconnected network).` }
        : pl.noroad === 'off' ? { num: '—', unit: '', text: 'The county’s population center is more than 30 miles from any primary or secondary road, so no road distance is reported.' }
        : { num: fmt(pl.rn), unit: ' road-miles', hot: pl.rn >= 150, text: `from the county’s population center to the nearest NCI-designated cancer center, ${esc(pl.nn)}. ${pl.rb === 0 ? 'The county itself hosts a broad menu (100 or more trials).' : `The nearest broad menu of trials (a county with 100 or more) is ${fmt(pl.rb)} road-miles away, in ${esc(pl.nbm)}.`}` })
      : pl.medn === null ? { num: '—', unit: '', text: `No census tract ${where} has a road route to an NCI-designated cancer center. ${pct(pl.g60b)}% of residents 55+ live more than 60 road-miles from a broad menu of trials (a county with 100 or more) or have no road route to one.` }
      : { num: fmt(pl.medn), unit: ' road-miles', hot: pl.medn >= 100, text: `is the median distance from home to the nearest NCI-designated cancer center for residents 55+ ${where}${pl.mnci ? ' (most often ' + esc(pl.mnci) + ')' : ''}${pl.nrn >= 1 ? `, among the ${pct(100 - pl.nrn)}% who have a road route to one (${pct(pl.nrn)}% have none)` : ''}. ${pct(pl.g60n)}% live more than 60 road-miles from one; ${pct(pl.g60b)}% live more than 60 road-miles from a broad menu of trials (a county with 100 or more).` };
    road.id = 'road'; road.cmp = pl.kind === 'nat' ? '' : `${st && pl.kind !== 'state' ? `${esc(st.name)} median ${st.medn === null ? 'no route' : fmt(st.medn) + ' road-miles'} · ` : ''}United States median ${fmt(NAT.medn)} road-miles`;
    road.why = 'NCI-designated centers run the widest range of trials, including early-phase studies that community practices rarely open. Distance is measured on the road network from where people live, not as the crow flies.'; F.push(road);
    if (pl.kind === 'county' && pl.mort && pl.mort[2] <= 1 && pl.mort[0] !== null) {
      const t = M.mort_tertile; const band = t ? (pl.mort[0] >= t[1] ? 'in the top third of US counties' : pl.mort[0] >= t[0] ? 'in the middle third of US counties' : 'in the bottom third of US counties') : '';
      F.push({ id: 'deaths', num: pl.mort[0], unit: ' per 100,000', hot: t && pl.mort[0] >= t[1] && pl.l20 >= 50,
        text: `age-adjusted cancer death rate, ${M.mort_period} (about ${fmt(pl.mort[1])} deaths a year)${band ? ', ' + band : ''}${pl.mort[2] === 1 ? ' — small numbers, interpret with caution' : ''}.${t && pl.mort[0] >= t[1] && pl.l20 >= 50 ? ' This county is one where cancer deaths are high and trials are far.' : ''}`,
        cmp: `United States: 143.2 per 100,000`, why: 'A death rate says how heavy the burden of cancer is here; it does not say why. The two measures are shown side by side, never combined into a score.' });
    }
    if (pl.kind !== 'county' && pl.rural) {
      const [mp, ml] = pl.rural.metro, [np_, nl] = pl.rural.nonmetro; if (np_ && mp) F.push({ id: 'rural', num: pct(nl), unit: '%', hot: nl >= 50,
        text: `of residents 55+ in nonmetro (rural) counties ${where} have fewer than 20 trials within 60 road-miles; in metro counties, ${pct(ml)}%. ${pct(100 * np_ / (np_ + mp))}% of residents 55+ here live in nonmetro counties.`,
        cmp: `United States: nonmetro ${pct(NAT.rural.nonmetro[1])}%, metro ${pct(NAT.rural.metro[1])}%`, why: 'Metro and nonmetro follow the USDA rural-urban continuum codes (metro = codes 1–3). The gap is the single largest pattern in the data.' });
    }
    if (pl.kind === 'district' && pl.nm !== null && pl.nm !== undefined) F.push({ id: 'districtrural', num: pct(pl.nm), unit: '%', text: `of this district’s residents 55+ live in nonmetro (rural) counties. The district touches ${fmt(pl.counties.length)} ${SITE.plural(pl.counties.length, 'county', 'counties')}.`, cmp: '', why: '' });
    return F;
  }

  // ---- a particular cancer: what changes for this place ----
  function cancerLine(pl, type) {
    if (!type) return null; const lab = typeLabel[type] || type; const bi = btypeIndex[type], ti = typeIndex[type];
    if (pl.kind === 'county') { const z = pl.zt && bi !== undefined ? pl.zt[bi] : null; if (z === null || z === undefined) return { text: `No county figure for ${lab} here.`, more: '' };
      return { text: `${pct(z)}% of residents 55+ in ${esc(pl.n)} have no recruiting ${lab} trial within 60 road-miles of home${z >= 50 ? ' — most of the county' : ''}.`, more: `Basket and umbrella trials that name ${lab} among several cancers are counted.` }; }
    const n = pl.ct && ti !== undefined ? pl.ct[ti] : null; const nn = NAT.ct && ti !== undefined ? NAT.ct[ti] : null;
    return { text: n === null || n === undefined ? `No figure for ${lab} here.` : `The average resident 55+ ${pl.kind === 'nat' ? 'in the United States' : 'in ' + esc(pl.label)} has ${fmt(n)} recruiting ${lab} ${SITE.plural(n, 'trial')} within 60 road-miles of home${pl.kind !== 'nat' && nn !== null ? `; nationally, ${fmt(nn)}` : ''}.`, more: 'An average is pulled up by residents near a big center; the map recomputes the share with none for this cancer when you filter it.' };
  }
  // one sentence of teaching per cancer type: why the total count can mislead (shared with the map, in site.js)
  const teach = SITE.teach;
  // ---- search over counties, districts, states and members (cities and ZIP codes loaded on demand) ----
  const norm = s => String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9 -]/g, ' ').replace(/\s+/g, ' ').trim();
  let IDX = null, PLACES = null, ZIP = null, PLp = null, ZIPp = null;
  function index() { if (IDX) return IDX; IDX = [];
    Object.keys(X.states).forEach(st => IDX.push({ t: 's', k: st, l: X.states[st].name, s: 'State', w: norm(X.states[st].name + ' ' + st), pri: 3 }));
    Object.keys(X.districts).forEach(k => { const d = X.districts[k]; const lab = d.st + '-' + cdLabel(d.cd); IDX.push({ t: 'd', k, l: lab + (d.member ? ' · ' + d.member : ''), s: 'Congressional district · ' + stName(d.st) + (d.member ? ' · ' + d.member + ' (' + d.party + ')' : ' · vacant'), w: norm(lab + ' ' + lab.replace('-', ' ') + ' ' + stName(d.st) + ' ' + cdLabel(d.cd) + ' ' + (d.member || '')), pri: 1 }); });
    Object.keys(X.counties).forEach(cf => { const c = county(cf); IDX.push({ t: 'c', k: cf, l: c.n + ', ' + c.st, s: 'County · ' + stName(c.st), w: norm(c.n + ' ' + c.st + ' ' + stName(c.st)), pri: 0.6 }); });
    return IDX; }
  const loadPlaces = () => PLp || (PLp = fetch('places.json').then(r => r.ok ? r.json() : null).then(j => { PLACES = []; if (!j) return; Object.entries(j.places).forEach(([st, list]) => list.forEach(([name, cf, size]) => { if (!X.counties[cf]) return; PLACES.push({ t: 'p', k: cf, l: name + ', ' + st, s: 'City or town · opens ' + county(cf).n, w: norm(name + ' ' + st + ' ' + stName(st)), pri: 0.3 + (size || 0) / 10 }); })); }).catch(() => { PLACES = []; }));
  const loadZip = () => ZIPp || (ZIPp = fetch('zip_county.json').then(r => r.json()).then(j => { ZIP = {}; Object.entries(j).forEach(([cf, zs]) => zs.forEach(z => ZIP[z] = cf)); return ZIP; }));
  function search(text, limit) { const t = norm(text); if (!t) return []; const ws = t.split(' ');
    const score = e => { let sc = 0; for (const w of ws) { if (e.w.split(' ').includes(w)) sc += 6; else if (e.w.includes(' ' + w) || e.w.startsWith(w)) sc += 4; else if (e.w.includes(w)) sc += 1; else return -1; } if (e.w === t || norm(e.l) === t || norm(e.l).startsWith(t)) sc += 10; return sc + e.pri; };
    return index().concat(PLACES || []).map(e => [score(e), e]).filter(x => x[0] > 0).sort((a, b) => b[0] - a[0] || a[1].l.localeCompare(b[1].l)).slice(0, limit || 8).map(x => x[1]); }
  // wire a search box: calls onPick({t,k,l}) with t in s|d|c|p|z (p and z resolve to a county)
  function wireSearch(input, listEl, onPick) { let opts = [], cur = -1;
    const show = (items, note) => { opts = items; cur = -1; listEl.innerHTML = items.map((e, i) => `<div class="opt" role="option" data-i="${i}"><span><b>${esc(e.l)}</b><span class="sub">${esc(e.s)}</span></span></div>`).join('') + (note ? `<div class="none">${note}</div>` : ''); listEl.hidden = !items.length && !note; input.setAttribute('aria-expanded', String(!listEl.hidden)); listEl.querySelectorAll('.opt').forEach(o => o.addEventListener('mousedown', ev => { ev.preventDefault(); go(opts[+o.dataset.i]); })); };
    const go = e => { if (!e) return; listEl.hidden = true; input.value = e.l; onPick(e); };
    const lookup = () => { const v = input.value.trim();
      if (/^\d{5}$/.test(v)) { loadZip().then(Z => { if (input.value.trim() !== v) return; const cf = Z[v]; if (cf && X.counties[cf]) show([{ t: 'z', k: cf, l: 'ZIP ' + v + ' · ' + county(cf).label, s: 'County where most of this ZIP code’s residents live' }]); else show([], /^00[6-9]|^969/.test(v) ? 'That ZIP code is in a US territory; this site covers the 50 states and the District of Columbia.' : 'No county found for that ZIP code. Try the city or county name.'); }); return; }
      if (/^\d{1,4}$/.test(v)) { show([], 'Keep typing a 5-digit ZIP code, or type a city, county, district, state or member’s name.'); return; }
      const r = search(v); show(r, !r.length && v.length > 1 ? 'Nothing matches yet. Try a county (“Warren County, KY”), a city, a district (“KY-2”), a state, a member of Congress or a ZIP code.' : ''); };
    input.addEventListener('input', () => { const p = loadPlaces(); lookup(); p.then(() => { if (document.activeElement === input && !/^\d+$/.test(input.value.trim())) lookup(); }); });
    input.addEventListener('focus', loadPlaces, { once: true });
    input.addEventListener('keydown', ev => { if (listEl.hidden) { if (ev.key === 'Enter') { ev.preventDefault(); const r = search(input.value); if (r.length) go(r[0]); } return; }
      if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') { if (!opts.length) return; ev.preventDefault(); cur = (cur + (ev.key === 'ArrowDown' ? 1 : -1) + opts.length) % opts.length; listEl.querySelectorAll('.opt').forEach((o, i) => o.classList.toggle('on', i === cur)); }
      else if (ev.key === 'Enter') { ev.preventDefault(); go(opts[cur >= 0 ? cur : 0]); } else if (ev.key === 'Escape') listEl.hidden = true; });
    input.addEventListener('blur', () => setTimeout(() => { listEl.hidden = true; }, 120)); }
  const pickToPlace = e => e.t === 's' ? state(e.k) : e.t === 'd' ? district(e.k) : county(e.k);

  // ---- legislation: roles for a place's delegation ----
  const ROLE = { sponsor: 'introduced the bill', original: 'original cosponsor', cosponsor: 'cosponsor' };
  function roleOf(bio, bill) { const r = bio && M.roles[bio] ? M.roles[bio][bill] : null; return r || ''; }
  function delegation(pl) { const st = pl.kind === 'county' || pl.kind === 'district' ? pl.st : pl.kind === 'state' ? pl.k : null; if (!st) return null;
    const house = pl.kind === 'district' ? [pl] : pl.kind === 'county' ? pl.d.map(k => district(k)).filter(Boolean) : Object.keys(X.districts).filter(k => X.districts[k].st === st).map(k => district(k)).sort((a, b) => (+a.cd) - (+b.cd));
    return { st, house, senators: (X.states[st] || {}).senators || [] }; }

  return { X, M, NAT, fmt, pct, people, esc, cdLabel, stName, typeLabel, county, district, state, nation, fromParams, param, links, stateOf, countyRank, districtRank, stateRank, facts, cancerLine, teach, search, wireSearch, pickToPlace, loadZip, roleOf, ROLE, delegation, dataDate };
})();
