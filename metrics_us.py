"""National county / district / state access metrics. Same definitions as the Texas pipeline.
Usage: python metrics_us.py [--min-max-age 55] [--out out_adult55]"""
import argparse, collections, json, re
from pathlib import Path
import numpy as np, pandas as pd
import config
from tier4_covering import city_keys, USPS

RAW, REF = Path("data/raw"), Path("data/ref")
R_MI = 3958.8


def hav_matrix(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1)[:, None], np.radians(lat2)[None, :]
    dphi = p2 - p1; dl = np.radians(lon2)[None, :] - np.radians(lon1)[:, None]
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R_MI * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


CONFLICT_MI = 40.0     # a ZIP centroid farther than this from every place of the stated name does not belong to that city
NEAR_MI = 25.0         # "the same facility is listed near here"
MIN_LISTINGS = 2       # the facility must be listed at least this often, by name, near the stated city
GENERIC_NAME = re.compile(r"\b(site|sites|investigational|investigative|clinical study|clinical research|trial|trials)\b")
SWAP_CONFLICT_MI = 25.0   # a ZIP this far (and more than twice its radius) from the stated city is tested for two swapped digits


def _mi(a, b):
    return float(np.hypot((a[0] - b[0]) * 69.0, (a[1] - b[1]) * 69.0 * np.cos(np.radians(a[0]))))


def _city_pts(state, city):
    """Every Census place of the stated name in the state (all spellings tier4_covering.city_keys tries), as (lat, lon, radius mi)."""
    from tier4_covering import gazetteer_points
    g = gazetteer_points()
    for k in city_keys(state, city):
        if (state, k) in g: return [(la, lo, float(np.sqrt(ar / np.pi))) for la, lo, _, ar in g[(state, k)]]
    return []


def zip_typos(sites):
    """Registry rows whose ZIP code is a typing error, judged from the registry's own other rows or from the digits themselves.
    Returns {row index: (evidence, the ZIP the row is placed at)}.

    A row is examined when its ZIP centroid is more than CONFLICT_MI (and more than twice the ZIP's own radius) from every Census
    place of the stated city name in the same state. Usually the ZIP is then the better half of the address: sponsors write the
    parent organisation's city for a satellite clinic ("New York" for Riverhead, "Sioux Falls" for Yankton), and those rows are
    left alone. The ZIP is judged a typing error only when all of these hold:
      - the facility has a name of its own (not "Research Site" or a sponsor's site code);
      - the same facility name is listed at least MIN_LISTINGS times, in rows whose ZIP and city agree, within NEAR_MI of the
        stated city;
      - no facility whose name contains this name, or is contained in it, is listed within NEAR_MI of the ZIP (a second campus);
      - no other trial lists the same facility with the same ZIP (a slip of the keyboard is not repeated by another sponsor).
    Example: "University of Iowa, Iowa City, 52252". The university is at 52242; 52252 is a village 45 miles away with no trial
    site, and the row put a trial within reach of Dubuque that is not there. Such a row is located where the registry's other
    rows put that facility (their most common ZIP), and the mistyped ZIP is not printed.

    Second test, for names that are listed only once or are sponsor site codes: two adjacent digits swapped. A ZIP more than
    SWAP_CONFLICT_MI (and twice its radius) from the stated city is a typing error when exactly one swap of two adjacent digits
    gives a ZIP area inside that city (its centre within the city's radius x 1.5, at least 5 miles), no place named in the
    facility name lies at the ZIP ("...VA North Chicago, Chicago, 60064" is right), the city is not New York (sponsors write
    "New York" for clinics all over Long Island) and no other trial lists the facility at that ZIP. "GC2202 Study Site 109,
    Greenville NC, 27843" is Greenville's 27834, not Hobgood in Halifax County; "Northwest Cancer Specialists, Vancouver WA,
    98648" is 98684, not Stevenson in Skamania County. Each had put a county's only trial 28-80 miles from where it is."""
    from tier4_covering import norm, gazetteer_points
    zc = pd.read_csv(REF / "zcta_pop55.csv", dtype={"zcta": str}); zxy = {z: (float(a), float(b)) for z, a, b in zip(zc.zcta, zc.lat, zc.lon)}
    z2c = dict(pd.read_csv(REF / "zcta_county.csv", dtype=str).values); radius = {}
    if (REF / "zcta_land_area.csv").exists():
        ar = pd.read_csv(REF / "zcta_land_area.csv", dtype={"zcta": str}); radius = {z: float(np.sqrt(a / np.pi)) for z, a in zip(ar.zcta, ar.land_sqmi.astype(float))}
    names = collections.defaultdict(list)                                     # places of each state with names of 4+ letters (the swap guard)
    for (st, pl), v in gazetteer_points().items():
        if len(pl) >= 4: names[st].append((pl, v))
    rows = []
    for i, st, city, z, fac, sf, nct in zip(sites.index, sites.state, sites.city, sites.zip, sites.facility, sites.state_fips, sites.nct_id):
        z = (z or "")[:5]
        if not (z.isdigit() and len(z) == 5 and z in zxy and z2c.get(z, "")[:2] == sf): continue      # the ZIP is not used for this row anyway
        pts = _city_pts(st, city)
        if not pts: continue                                                                           # the city is not a Census place: nothing to compare
        near = min(pts, key=lambda q: _mi(zxy[z], q)); d = _mi(zxy[z], near)
        rows.append((i, st, sf, city, z, norm(fac), d > max(CONFLICT_MI, 2 * radius.get(z, 0.0)), near, nct, d, pts))
    agree = collections.defaultdict(list); same_zip = collections.defaultdict(set)
    for i, st, sf, city, z, nm, conflict, near, nct, d, pts in rows:
        same_zip[(st, nm, z)].add(nct)
        if not conflict and nm: agree[st].append((frozenset(nm.split()), nm, zxy[z], z))
    out = {}
    for i, st, sf, city, z, nm, conflict, near, nct, d, pts in rows:
        if not conflict or not nm or GENERIC_NAME.search(nm) or not re.search(r"[a-z]{3}", nm): continue
        tok = frozenset(nm.split())
        if len(tok) < 2 or len(same_zip[(st, nm, z)]) > 1: continue
        zs = [z2 for t, n2, q, z2 in agree[st] if n2 == nm and _mi(q, near) <= NEAR_MI]
        if len(zs) < MIN_LISTINGS: continue
        if any((t <= tok or tok <= t) and len(t & tok) >= 2 and _mi(q, zxy[z]) <= NEAR_MI for t, n2, q, z2 in agree[st]): continue
        best = collections.Counter(zs).most_common(1)[0][0]
        out[i] = (f"listed {len(zs)}x near the stated city (most often at ZIP {best}), never near ZIP {z}", best)
    for i, st, sf, city, z, nm, conflict, near, nct, d, pts in rows:                                     # second test: two adjacent digits swapped
        if i in out or d <= max(SWAP_CONFLICT_MI, 2 * radius.get(z, 0.0)) or (st, (city or "").strip().lower()) in MULTI_COUNTY_PLACE: continue
        if nm and len(same_zip[(st, nm, z)]) > 1: continue
        swaps = {z[:k] + z[k + 1] + z[k] + z[k + 2:] for k in range(4)} - {z}
        hit = [v for v in sorted(swaps) if v in zxy and z2c.get(v, "")[:2] == sf and any(_mi(zxy[v], q) <= max(5.0, 1.5 * q[2]) for q in pts)]
        if len(hit) != 1: continue
        padded = f" {nm} "
        if any(f" {pl} " in padded and any(_mi(zxy[z], q) <= max(10.0, 2 * radius.get(z, 0.0), 1.5 * float(np.sqrt(q[3] / np.pi))) for q in v) for pl, v in names[st]): continue
        out[i] = (f"ZIP {z} lies {d:.0f} miles from {city}; with two adjacent digits swapped it reads {hit[0]}, in {city}", hit[0])
    return out


# A Census place that spans several counties has one internal point (New York's is in Brooklyn); a row in such a place keeps its
# ZIP-prefix county when that county is one the place covers ("New York, NY 100xx" stays in Manhattan).
MULTI_COUNTY_PLACE = {("NY", "new york"): {"36005", "36047", "36061", "36081", "36085"}, ("NY", "new york city"): {"36005", "36047", "36061", "36081", "36085"}}


def facility_listings(sites):
    """For rows whose ZIP cannot place them (not a Census ZIP area in the stated state): the ZIP at which the registry's other rows
    list the same named facility in the same city. Returns {row index: (evidence, ZIP, whether the city anchored the listing)};
    assign_sites uses it only when it gives another county than the city or the ZIP's first three digits would, and then
    assigns and places the row as a row at that ZIP.

    The city alone cannot say which county a row is in when the city spans counties or the city field is loose: "University of
    Colorado Denver, Aurora, 80208" went to Arapahoe County (most of Aurora) although the cancer centre is on the Anschutz campus
    in Adams County, where the registry lists it at 80045; "Dana-Farber Cancer Institute, Brookline, 02251" went to Norfolk
    County, while the registry lists the institute 344 times at 02215, Boston; "Emory Winship Cancer Institute, Atlanta, 30302"
    (a post-office ZIP) went to Fulton County, while Winship is listed at 30322 in DeKalb. A listing counts when the facility has
    a name of its own (as in zip_typos), at least MIN_LISTINGS rows with a usable ZIP list the same name within the stated city
    (centre within 1.5 x the city's radius, at least 5 miles) and two thirds of them are in one county; the row goes to their
    most common ZIP in that county. When the stated city is not a Census place, every listing in the state counts, but only for
    a row that would otherwise have no county ("Memorial Sloan Kettering Cancer Center - Monmouth, Middletown, NJ, 00748")."""
    from tier4_covering import norm
    zc = pd.read_csv(REF / "zcta_pop55.csv", dtype={"zcta": str}); zxy = {z: (float(a), float(b)) for z, a, b in zip(zc.zcta, zc.lat, zc.lon)}
    z2c = dict(pd.read_csv(REF / "zcta_county.csv", dtype=str).values)
    nm = sites.facility.map(norm); z5 = sites.zip.str[:5]
    usable = [bool(z in zxy and z2c.get(z, "")[:2] == sf) for z, sf in zip(z5, sites.state_fips)]
    listing = collections.defaultdict(list)
    for st, n, z, ok in zip(sites.state, nm, z5, usable):
        if ok and n: listing[(st, n)].append((zxy[z], z, z2c[z]))
    out = {}
    for i, st, city, n, ok in zip(sites.index, sites.state, sites.city, nm, usable):
        if ok or not n or GENERIC_NAME.search(n) or not re.search(r"[a-z]{3}", n) or len(n.split()) < 2 or (st, n) not in listing: continue
        pts = _city_pts(st, city)
        # with no Census place of the stated name (a township, a borough, a misspelling) every listing in the state counts, and the
        # result is used only for a row that would otherwise have no county (assign_sites)
        near = [(z, c) for q, z, c in listing[(st, n)] if not pts or any(_mi(q, p) <= max(5.0, 1.5 * p[2]) for p in pts)]
        if len(near) < MIN_LISTINGS: continue
        top, k = collections.Counter(c for _, c in near).most_common(1)[0]
        if 3 * k < 2 * len(near): continue
        best = collections.Counter(z for z, c in near if c == top).most_common(1)[0][0]
        out[i] = (f"listed {k}x " + (f"in {city}" if pts else "in the state") + f" (most often at ZIP {best})", best, bool(pts))
    return out


def listed_at_zip(sites):
    """{(normalised facility name, ZIP): number of trials whose rows list that facility at that ZIP, ZIP and state agreeing}."""
    from tier4_covering import norm
    z2c = dict(pd.read_csv(REF / "zcta_county.csv", dtype=str).values)
    z5 = sites.zip.str[:5]; ok = [z2c.get(z, "")[:2] == sf for z, sf in zip(z5, sites.state_fips)]
    d = pd.DataFrame({"n": sites.facility.map(norm), "z": z5, "t": sites.nct_id})[ok]
    return d.groupby(["n", "z"]).t.nunique().to_dict()


def assign_sites(sites, cent):
    from tier4_covering import find_place, gazetteer_points
    z2c = dict(pd.read_csv(REF / "zcta_county.csv", dtype=str).values)
    z3 = dict(pd.read_csv(REF / "zip3_county.csv", dtype=str).values)
    zc = pd.read_csv(REF / "zcta_pop55.csv", dtype={"zcta": str}); zxy = {z: (float(a), float(b)) for z, a, b in zip(zc.zcta, zc.lat, zc.lon)}
    radius = {}
    if (REF / "zcta_land_area.csv").exists():
        ar = pd.read_csv(REF / "zcta_land_area.csv", dtype={"zcta": str}); radius = {z: float(np.sqrt(a / np.pi)) for z, a in zip(ar.zcta, ar.land_sqmi.astype(float))}
    if cent is None: cent = pd.read_csv(REF / "county_centroids.csv", dtype={"county_fips": str, "state_fips": str})   # diff_snapshots.py passes None
    cxy = {f: (float(a), float(b)) for f, a, b in zip(cent.county_fips, cent.lat, cent.lon)}
    known = set(cxy)   # the 3,143 counties of the 50 states and DC: a row placed anywhere else (Puerto Rico is in the Gazetteer and the
    # county file) gets no county, so nothing downstream looks it up (route_sites_us.py reads the county's population centre)
    gazetteer_points()   # city points and their counties (tier4_covering): one source for this script and route_sites_us.py
    # A ZIP that spans counties: zcta_county.csv gives the county with most of its land. Where most of the ZIP's residents 55+
    # live in a different county (zcta_county_parts.csv), the site goes to that county instead - unless the site's own city is
    # known to lie in the land-area county. Hospitals stand where the people are: ZIP 49684 is 61% Leelanau County by land, but
    # Munson Medical Center and two-thirds of the ZIP's older residents are in Traverse City, Grand Traverse County.
    zpop = {}
    if (REF / "zcta_county_parts.csv").exists():
        pp = pd.read_csv(REF / "zcta_county_parts.csv", dtype={"zcta": str, "county_fips": str}); pp = pp[pp.pop55_share.notna()]
        zpop = pp.sort_values("pop55_share", ascending=False).drop_duplicates("zcta").set_index("zcta").county_fips.to_dict()

    def city_county(state, city, near=None):   # the same places route_sites_us.py uses when it places the site (tier4_covering.find_place)
        p = find_place(state, city, near)
        return p[2] if p and p[2] else None

    def by_zip(z, c, state, city):                  # the county of a usable ZIP: its land county, or the county where its residents live
        cp = zpop.get(z)
        if cp and cp != c and cp[:2] == c[:2] and city_county(state, city, zxy.get(z)) != c: return "zip_pop", cp
        return "zip", c
    # Rows that are not places (config.VIRTUAL_SITE_PATTERN) get no county, so nothing downstream draws or measures to them;
    # rows whose ZIP is a typing error (zip_typos) are assigned through the ZIP at which the registry's other rows list that facility.
    virtual = None if config.VIRTUAL_SITES_ARE_LOCATIONS else re.compile(config.VIRTUAL_SITE_PATTERN, re.I)
    from tier4_covering import norm
    typos = zip_typos(sites); listed = facility_listings(sites); at_zip = listed_at_zip(sites)
    method, county, fixz, note = [], [], [], []
    for s in sites.itertuples():
        m = c = None; zf = ""; nt = ""
        if virtual is not None and virtual.search(s.facility or ""): method.append("virtual_site"); county.append(None); fixz.append(""); note.append(""); continue
        z = (s.zip or "")[:5]; st = s.state_fips
        if s.Index in typos:
            nt, zf = typos[s.Index]; cz = z2c.get(zf); cp = zpop.get(zf)      # the ZIP where the registry's other rows put this facility, and its county
            if cz and cp and cp != cz and cp[:2] == st and city_county(s.state, s.city, zxy.get(zf)) != cz: cz = cp
            if cz and cz[:2] == st: m, c = "zip_typo_corrected", cz
            else: zf = nt = ""
        if m is None:
            cz = z2c.get(z) if z.isdigit() and len(z) == 5 else None
            if cz and cz[:2] == st: m, c = by_zip(z, cz, s.state, s.city)
            elif cz and z in zxy and USPS.get(cz[:2]):
                # The ZIP is a Census ZIP area in another state, and either the stated city is a place of that state at the ZIP, or
                # other trials list the same named facility at that ZIP: the state (or city) field is the error. "Mayo
                # Clinic_Rochester, Rochester, New York, 55905" is Rochester MN; "Luminis Health ... Anne Arundel, Annapolis,
                # Missouri, 21401" is Annapolis MD; "Gabrail Cancer Center, Canton, Oklahoma, 44718" is Canton OH; "University of
                # Kansas Cancer Center - Overland Park, Overland, MO, 66210" is listed 43 times at 66210 in Overland Park, KS. Before
                # October 2026 the city won and 19 such rows went to a same-named town of the stated state (Annapolis MO, Anderson
                # TX, Canton OK and Dallas PA each showed a trial that is not there; Overland MO, Middletown NY) or to no county.
                zst = USPS[cz[:2]]; q = find_place(zst, s.city, zxy[z]); fn = norm(s.facility)
                named = bool(fn) and not GENERIC_NAME.search(fn) and len(fn.split()) >= 2
                if (q and _mi(zxy[z], q) <= max(10.0, 2 * radius.get(z, 0.0))) or (named and at_zip.get((fn, z), 0) >= MIN_LISTINGS):
                    m, c = by_zip(z, cz, zst, s.city); m = "zip_state_corrected"
        if m is None:
            c3 = z3.get(z[:3]) if len(z) >= 3 and z[:3].isdigit() else None
            cc = city_county(s.state, s.city, cxy.get(c3) if c3 else None)
            if c3 and c3[:2] == st:
                # A ZIP with no Census area (a PO box, a unique institutional ZIP, or a typing error) says only which three-digit region the
                # row is in; the row's own city is the more specific statement, so when the city is a known place in the state its county
                # wins. "Trinity Health Ann Arbor, 48106" was counted in Wayne County instead of Washtenaw; "Mary Crowley Cancer Research,
                # Dallas, 75521" went to Cass County and "MyMichigan Medical Center Tawas, Tawas City, 48764" to Tuscola County, 60 miles
                # from the hospital, where route_sites_us.py then drew them at the county center as phantom sites.
                if cc and cc[:2] == st and cc != c3 and c3 not in MULTI_COUNTY_PLACE.get((s.state, (s.city or "").strip().lower()), ()): m, c = "city_over_zip3", cc
                else: m, c = "zip3", c3
            elif cc and cc[:2] == st: m, c = "city_gazetteer", cc
            else: m, c = "unassigned", None
            # ... unless the registry lists the same named facility in the same city, at a usable ZIP in another county (facility_listings):
            # the Anschutz campus in Aurora is in Adams County, not in Arapahoe where most of Aurora is.
            if s.Index in listed and (listed[s.Index][2] or m == "unassigned"):
                nt1, zf1, _ = listed[s.Index]; m1, c1 = by_zip(zf1, z2c[zf1], s.state, s.city)
                if c1 != c: m, c, nt, zf = "facility_listing", c1, nt1, zf1
        if c and c not in known: m, c, zf, nt = "outside_50_states_dc", None, "", ""
        method.append(m); county.append(c); fixz.append(zf if m in ("zip_typo_corrected", "facility_listing") else ""); note.append(nt if m in ("zip_typo_corrected", "facility_listing") else "")
    sites = sites.copy(); sites["county_fips"] = county; sites["assign_method"] = method
    sites["assign_note"] = note
    sites["zip_fix"] = fixz   # where route_sites_us.py puts the row (zip_typo_corrected, facility_listing)
    return sites


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--min-max-age", type=float); ap.add_argument("--out", default="out")
    a = ap.parse_args(); OUT = Path(a.out); OUT.mkdir(exist_ok=True)
    trials = pd.read_csv(RAW / "trials.csv", dtype=str)
    sites = pd.read_csv(RAW / "us_sites.csv", dtype=str).fillna("")
    age_note = "all ages"
    if a.min_max_age is not None:
        mx = pd.to_numeric(trials.max_age_years, errors="coerce"); drop = set(trials.loc[mx < a.min_max_age, "nct_id"])
        trials = trials[~trials.nct_id.isin(drop)]; sites = sites[~sites.nct_id.isin(drop)]
        age_note = f"trials with maximum age < {a.min_max_age:g} excluded (n={len(drop)})"
    cent = pd.read_csv(REF / "county_centroids.csv", dtype={"county_fips": str, "state_fips": str})
    pop = pd.read_csv(REF / "county_pop55.csv", dtype={"county_fips": str})
    cd = pd.read_csv(REF / "county_cd.csv", dtype=str); cd["share"] = cd.share.astype(float)
    nci = config.nci_targets()

    sites = assign_sites(sites, cent); sites.to_csv(OUT / "site_assignment_qc.csv", index=False)
    qc = sites.assign_method.value_counts().to_dict()
    oral = dict(zip(trials.nct_id, trials.oral_candidate.astype(int))); indet = dict(zip(trials.nct_id, trials.oral_indeterminate.astype(int)))
    ct = sites.dropna(subset=["county_fips"]).groupby("county_fips").nct_id.agg(set).to_dict()

    c = cent.merge(pop, on="county_fips", how="left"); c["pop55"] = c.pop55.fillna(0).astype(int)
    c["trials_in_county"] = c.county_fips.map(lambda f: len(ct.get(f, set())))
    c["oral_trials_in_county"] = c.county_fips.map(lambda f: sum(oral.get(n, 0) for n in ct.get(f, set())))
    c["oral_indeterminate_in_county"] = c.county_fips.map(lambda f: sum(indet.get(n, 0) for n in ct.get(f, set())))
    lat, lon = c.lat.values, c.lon.values
    D = hav_matrix(lat, lon, lat, lon) * config.ROAD_FACTOR
    lim_idx = np.where(c.trials_in_county.values >= config.MENU_THRESHOLDS["limited"])[0]
    brd_idx = np.where(c.trials_in_county.values >= config.MENU_THRESHOLDS["broad"])[0]
    c["dist_to_limited_mi"] = D[:, lim_idx].min(axis=1); c.loc[c.trials_in_county >= config.MENU_THRESHOLDS["limited"], "dist_to_limited_mi"] = 0
    c["dist_to_broad_mi"] = D[:, brd_idx].min(axis=1); c.loc[c.trials_in_county >= config.MENU_THRESHOLDS["broad"], "dist_to_broad_mi"] = 0
    Dn = hav_matrix(lat, lon, nci.lat.values, nci.lon.values) * config.ROAD_FACTOR
    c["dist_to_nci_mi"] = Dn.min(axis=1); c["nearest_nci"] = nci.name.values[Dn.argmin(axis=1)]
    fips = c.county_fips.values
    for band in config.DISTANCE_BANDS_MI:
        t, o, i = [], [], []
        for k in range(len(c)):
            pool = set().union(*[ct.get(fips[j], set()) for j in np.where(D[k] <= band)[0]])
            t.append(len(pool)); o.append(sum(oral.get(n, 0) for n in pool)); i.append(sum(indet.get(n, 0) for n in pool))
        c[f"trials_within_{band}mi"], c[f"oral_trials_within_{band}mi"], c[f"oral_indeterminate_within_{band}mi"] = t, o, i
    c.sort_values("trials_in_county", ascending=False).to_csv(OUT / "county_metrics.csv", index=False)

    m = cd.merge(c, on=["county_fips", "state_fips"], how="inner"); m["w"] = m.pop55 * m.share
    m["zero"] = (m.trials_in_county == 0).astype(int)
    for b in config.DISTANCE_BANDS_MI:
        m[f"b{b}_broad"] = (m.dist_to_broad_mi > b).astype(int); m[f"b{b}_lim"] = (m.dist_to_limited_mi > b).astype(int)

    def agg(g, keys):
        W = g.w.sum()
        def wm(col): return (g[col] * g.w).sum() / W if W else np.nan
        row = dict(keys); row.update({"pop55_weighted": int(round(W)), "n_counties_touched": g.county_fips.nunique(),
            "pct_pop55_in_counties_with_zero_trials": round(100 * wm("zero"), 1),
            "wmean_trials_in_own_county": round(wm("trials_in_county"), 0),
            "wmean_dist_to_broad_menu_mi": round(wm("dist_to_broad_mi"), 1), "wmean_dist_to_limited_menu_mi": round(wm("dist_to_limited_mi"), 1),
            "wmean_dist_to_nci_mi": round(wm("dist_to_nci_mi"), 1), "wmean_trials_within_60mi": round(wm("trials_within_60mi"), 0),
            "wmean_oral_trials_within_60mi": round(wm("oral_trials_within_60mi"), 0), "wmean_oral_indeterminate_within_60mi": round(wm("oral_indeterminate_within_60mi"), 0)})
        for b in config.DISTANCE_BANDS_MI:
            row[f"pct_pop55_beyond_{b}mi_of_broad_menu"] = round(100 * wm(f"b{b}_broad"), 1); row[f"pct_pop55_beyond_{b}mi_of_limited_menu"] = round(100 * wm(f"b{b}_lim"), 1)
        return row
    st_name = dict(zip(cent.state_fips, cent.state_name))
    dist = pd.DataFrame([agg(g, {"cd_geoid": k, "state_fips": k[:2], "state": st_name[k[:2]], "cd": k[2:]}) for k, g in m.groupby("cd_geoid")])
    dist.to_csv(OUT / "district_metrics.csv", index=False)
    # state summary uses full county populations (no shares)
    c["zero"] = (c.trials_in_county == 0).astype(int); c["w"] = c.pop55
    for b in config.DISTANCE_BANDS_MI:
        c[f"b{b}_broad"] = (c.dist_to_broad_mi > b).astype(int); c[f"b{b}_lim"] = (c.dist_to_limited_mi > b).astype(int)
    states = pd.DataFrame([agg(g, {"state_fips": k, "state": st_name[k]}) for k, g in c.groupby("state_fips")])
    states["n_counties"] = states.state_fips.map(c.groupby("state_fips").size()); states["n_counties_with_trials"] = states.state_fips.map(c[c.trials_in_county > 0].groupby("state_fips").size()).fillna(0).astype(int)
    states["n_districts"] = states.state_fips.map(dist.groupby("state_fips").size())
    states.to_csv(OUT / "state_metrics.csv", index=False)
    us = agg(c.assign(w=c.pop55), {"scope": "US (50 states + DC)"})
    log = {"age_filter": age_note, "site_rows": len(sites), "site_assignment": qc, "distinct_trials": int(trials.nct_id.nunique()),
           "counties": len(c), "counties_with_any_trial": int((c.trials_in_county > 0).sum()), "broad_menu_counties": int(len(brd_idx)), "limited_menu_counties": int(len(lim_idx)),
           "districts": len(dist), "us": us}
    json.dump(log, open(OUT / "metrics_log.json", "w"), indent=2); print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
