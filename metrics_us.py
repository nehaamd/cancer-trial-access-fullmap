"""National county / district / state access metrics. Same definitions as the Texas pipeline.
Usage: python metrics_us.py [--min-max-age 55] [--out out_adult55]"""
import argparse, collections, json, re
from pathlib import Path
import geopandas as gpd, numpy as np, pandas as pd
import config
from tier4_covering import city_keys

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


def _mi(a, b):
    return float(np.hypot((a[0] - b[0]) * 69.0, (a[1] - b[1]) * 69.0 * np.cos(np.radians(a[0]))))


def zip_typos(sites):
    """Registry rows whose ZIP code is a typing error, judged from the registry's own other rows.
    Returns {row index: (evidence, ZIP at which the registry most often lists that facility near the stated city)}.

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
    rows put that facility (their most common ZIP), and the mistyped ZIP is not printed."""
    from tier4_covering import norm
    zc = pd.read_csv(REF / "zcta_pop55.csv", dtype={"zcta": str}); zxy = {z: (float(a), float(b)) for z, a, b in zip(zc.zcta, zc.lat, zc.lon)}
    z2c = dict(pd.read_csv(REF / "zcta_county.csv", dtype=str).values); radius = {}
    if (REF / "zcta_land_area.csv").exists():
        ar = pd.read_csv(REF / "zcta_land_area.csv", dtype={"zcta": str}); radius = {z: float(np.sqrt(a / np.pi)) for z, a in zip(ar.zcta, ar.land_sqmi.astype(float))}
    gz = pd.read_csv(REF / "gazetteer_places.csv", dtype={"state": str, "place": str}); places = collections.defaultdict(list)
    for a, b, c, d in zip(gz.state, gz.place, gz.lat, gz.lon): places[(a, b)].append((float(c), float(d)))

    def city_pts(state, city):
        c = (city or "").strip().lower()
        for cand in (c, c.replace("saint ", "st. "), c.replace("st ", "st. "), c.replace("ft. ", "fort ").replace("ft ", "fort ")):
            if (state, cand) in places: return places[(state, cand)]
        return []
    rows = []
    for i, st, city, z, fac, sf, nct in zip(sites.index, sites.state, sites.city, sites.zip, sites.facility, sites.state_fips, sites.nct_id):
        z = (z or "")[:5]
        if not (z.isdigit() and len(z) == 5 and z in zxy and z2c.get(z, "")[:2] == sf): continue      # the ZIP is not used for this row anyway
        pts = city_pts(st, city)
        if not pts: continue                                                                           # the city is not a Census place: nothing to compare
        near = min(pts, key=lambda q: _mi(zxy[z], q)); d = _mi(zxy[z], near)
        rows.append((i, st, z, norm(fac), d > max(CONFLICT_MI, 2 * radius.get(z, 0.0)), near, nct))
    agree = collections.defaultdict(list); same_zip = collections.defaultdict(set)
    for i, st, z, nm, conflict, near, nct in rows:
        if conflict: same_zip[(st, nm, z)].add(nct)
        elif nm: agree[st].append((frozenset(nm.split()), nm, zxy[z], z))
    out = {}
    for i, st, z, nm, conflict, near, nct in rows:
        if not conflict or not nm or GENERIC_NAME.search(nm) or not re.search(r"[a-z]{3}", nm): continue
        tok = frozenset(nm.split())
        if len(tok) < 2 or len(same_zip[(st, nm, z)]) > 1: continue
        zs = [z2 for t, n2, q, z2 in agree[st] if n2 == nm and _mi(q, near) <= NEAR_MI]
        if len(zs) < MIN_LISTINGS: continue
        if any((t <= tok or tok <= t) and len(t & tok) >= 2 and _mi(q, zxy[z]) <= NEAR_MI for t, n2, q, z2 in agree[st]): continue
        best = collections.Counter(zs).most_common(1)[0][0]
        out[i] = (f"listed {len(zs)}x near the stated city (most often at ZIP {best}), never near ZIP {z}", best)
    return out


# A Census place that spans several counties has one internal point (New York's is in Brooklyn); a row in such a place keeps its
# ZIP-prefix county when that county is one the place covers ("New York, NY 100xx" stays in Manhattan).
MULTI_COUNTY_PLACE = {("NY", "new york"): {"36005", "36047", "36061", "36081", "36085"}, ("NY", "new york city"): {"36005", "36047", "36061", "36081", "36085"}}


def assign_sites(sites, cent):
    z2c = dict(pd.read_csv(REF / "zcta_county.csv", dtype=str).values)
    z3 = dict(pd.read_csv(REF / "zip3_county.csv", dtype=str).values)
    gaz = pd.read_csv(REF / "gazetteer_places.csv", dtype={"state": str, "place": str})
    counties = gpd.read_file("zip://data/geo/cb.zip")[["STATEFP", "GEOID", "geometry"]]
    # Connecticut: the 2023 cartographic file carries planning regions (091xx); ZIP/ACS/population files use the 8 legacy counties,
    # so splice in the 2021 county shapes for CT (same fix as the web-app geometry) so city-fallback sites get legacy codes.
    ct2021 = gpd.read_file("zip://data/geo/cb500_2021.zip"); ct2021 = ct2021[ct2021.STATEFP == "09"][["STATEFP", "GEOID", "geometry"]].to_crs(counties.crs)
    counties = pd.concat([counties[counties.STATEFP != "09"], ct2021], ignore_index=True)
    counties = gpd.GeoDataFrame(counties, geometry="geometry", crs=ct2021.crs)[["GEOID", "geometry"]].to_crs(4326)
    pts = gpd.GeoDataFrame(gaz, geometry=gpd.points_from_xy(gaz.lon, gaz.lat), crs=4326)
    gaz_county = gpd.sjoin(pts, counties, how="left", predicate="within")
    city2c = {(r.state, r.place): r.GEOID for r in gaz_county.dropna(subset=["GEOID"]).itertuples()}
    # A ZIP that spans counties: zcta_county.csv gives the county with most of its land. Where most of the ZIP's residents 55+
    # live in a different county (zcta_county_parts.csv), the site goes to that county instead - unless the site's own city is
    # known to lie in the land-area county. Hospitals stand where the people are: ZIP 49684 is 61% Leelanau County by land, but
    # Munson Medical Center and two-thirds of the ZIP's older residents are in Traverse City, Grand Traverse County.
    zpop = {}
    if (REF / "zcta_county_parts.csv").exists():
        pp = pd.read_csv(REF / "zcta_county_parts.csv", dtype={"zcta": str, "county_fips": str}); pp = pp[pp.pop55_share.notna()]
        zpop = pp.sort_values("pop55_share", ascending=False).drop_duplicates("zcta").set_index("zcta").county_fips.to_dict()

    def city_county(state, city):   # the same spellings route_sites_us.py tries when it places the site (tier4_covering.city_keys)
        for cand in city_keys(state, city):
            cc = city2c.get((state, cand))
            if cc: return cc
        return None
    # Rows that are not places (config.VIRTUAL_SITE_PATTERN) get no county, so nothing downstream draws or measures to them;
    # rows whose ZIP is a typing error (zip_typos) are assigned through the ZIP at which the registry's other rows list that facility.
    virtual = None if config.VIRTUAL_SITES_ARE_LOCATIONS else re.compile(config.VIRTUAL_SITE_PATTERN, re.I)
    typos = zip_typos(sites)
    method, county = [], []
    for s in sites.itertuples():
        if virtual is not None and virtual.search(s.facility or ""): method.append("virtual_site"); county.append(None); continue
        if s.Index in typos:
            zf = typos[s.Index][1]; cz = z2c.get(zf); cp = zpop.get(zf)      # the ZIP where the registry's other rows put this facility, and its county
            if cz and cp and cp != cz and cp[:2] == s.state_fips and city_county(s.state, s.city) != cz: cz = cp
            if cz and cz[:2] == s.state_fips: method.append("zip_typo_corrected"); county.append(cz); continue
        z = (s.zip or "")[:5]; st = s.state_fips
        c = z2c.get(z) if z.isdigit() and len(z) == 5 else None
        if c and c[:2] == st:
            cp = zpop.get(z)
            if cp and cp != c and cp[:2] == st and city_county(s.state, s.city) != c: method.append("zip_pop"); county.append(cp); continue
            method.append("zip"); county.append(c); continue
        c3 = z3.get(z[:3]) if len(z) >= 3 and z[:3].isdigit() else None
        cc = city_county(s.state, s.city)
        if c3 and c3[:2] == st:
            # A ZIP with no Census area (a PO box, a unique institutional ZIP, or a typing error) says only which three-digit region the
            # row is in; the row's own city is the more specific statement, so when the city is a known place in the state its county
            # wins. "Trinity Health Ann Arbor, 48106" was counted in Wayne County instead of Washtenaw; "Mary Crowley Cancer Research,
            # Dallas, 75521" went to Cass County and "MyMichigan Medical Center Tawas, Tawas City, 48764" to Tuscola County, 60 miles
            # from the hospital, where route_sites_us.py then drew them at the county center as phantom sites.
            if cc and cc[:2] == st and cc != c3 and c3 not in MULTI_COUNTY_PLACE.get((s.state, (s.city or "").strip().lower()), ()): method.append("city_over_zip3"); county.append(cc); continue
            method.append("zip3"); county.append(c3); continue
        if cc and cc[:2] == st: method.append("city_gazetteer"); county.append(cc); continue
        method.append("unassigned"); county.append(None)
    sites = sites.copy(); sites["county_fips"] = county; sites["assign_method"] = method
    sites["assign_note"] = [typos[i][0] if m == "zip_typo_corrected" else "" for i, m in zip(sites.index, method)]
    sites["zip_fix"] = [typos[i][1] if m == "zip_typo_corrected" else "" for i, m in zip(sites.index, method)]   # where route_sites_us.py puts the row
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
