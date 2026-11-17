"""National county / district / state access metrics. Same definitions as the Texas pipeline.
Usage: python metrics_us.py [--min-max-age 55] [--out out_adult55]"""
import argparse, collections, json, re, sys
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


CITY_GAP_MI = 15.0     # a ZIP whose residents' centre lies more than this beyond the edge of the stated city (and beyond the ZIP's own radius) disagrees with it
AGREE_MI = 5.0         # a row whose ZIP lies within this of the stated city agrees with it: such rows are the evidence the review weighs


def zip_city_review(sites, skip=()):
    """Registry rows whose ZIP code and city disagree, and what the registry's own other rows say about which is right.
    Returns {row index: {"verdict": "zip" | "city" | "ambiguous", "rule", "note", "mi", "zip_place", "fix_zip"}}.

    A row is reviewed when its ZIP is a Census ZIP area in the stated state, the stated city is a Census place of that state, and the
    ZIP's population centre lies more than CITY_GAP_MI beyond the edge of every place of that name (the city's edge is its point
    plus the radius of a circle of its land area) and beyond the ZIP's own radius. Rows in `skip` (already judged a typing error by
    zip_typos) are not reviewed. About 90 of 55,000 rows qualify. Each is weighed on two sides.

    Evidence that the site is at the ZIP:
      - the facility's name names a place that lies at the ZIP ("Georgia Cancer Center Augusta University, Atlanta, 30912");
      - the same facility name is listed at this ZIP by other trials whose city agrees with the ZIP;
      - the same institution (data/ref/site_families.csv) is listed at this ZIP by other trials whose city agrees.
    Evidence that the site is in the stated city:
      - the facility's name names the stated city ("Karmanos Cancer Institute at McLaren Lapeer Region, Lapeer, 48466");
      - the same facility name, or the same institution, is listed in the stated city by other trials (rows whose ZIP agrees with
        the city, and rows whose ZIP is not a Census ZIP area and so cannot disagree).
    A city that carries no information counts for nothing: "New York" is written for clinics all over Long Island
    (MULTI_COUNTY_PLACE), and "Florida City", "Texas City", "Ohio City" and "Arkansas City" appear where the form repeated the state
    (no registry row is located in the place of that name).

    Listings weigh more than the name: a row counts as listed at the ZIP (or in the city) when at least MIN_LISTINGS other trials
    list the same name or institution there in rows whose own ZIP and city do not disagree. The name alone decides only when
    neither side has a listing.

    Verdict "zip": listed at the ZIP (or named for a place at it) and not listed in the city at all, or the city carries no
    information. The row stays where it is and the pages print the ZIP's own place instead of the registry's city ("Jacksonville",
    not "Florida City"). Verdict "city": listed in the city (or named for it) and not listed at the ZIP at all, with no facility of
    a longer or shorter form of the name at the ZIP (a second campus). The ZIP is the error; the row is placed like a mistyped
    ZIP (assign_sites), at the ZIP where the registry's other rows list the facility in that city. Verdict "ambiguous": listed in
    both places, or in neither (a sponsor's placeholder name says nothing). The row stays at its ZIP, which is usually the better
    half of an address, and the pages flag it. data/ref/zip_city_overrides.csv holds the few rows a person has checked against the
    institution's own address; it is applied first."""
    import site_names
    from tier4_covering import norm, gazetteer_frame
    zc = pd.read_csv(REF / "zcta_pop55.csv", dtype={"zcta": str}); zxy = {z: (float(a), float(b)) for z, a, b in zip(zc.zcta, zc.lat, zc.lon)}
    if (REF / "zcta_popcenter.csv").exists():     # where the ZIP's residents live: a ZIP's own centroid can be far from them (99701, Fairbanks, by 184 miles)
        pc = pd.read_csv(REF / "zcta_popcenter.csv", dtype={"zcta": str}); zxy.update({z: (float(a), float(b)) for z, a, b in zip(pc.zcta, pc.lat, pc.lon) if z in zxy})
    z2c = dict(pd.read_csv(REF / "zcta_county.csv", dtype=str).values); radius = {}
    if (REF / "zcta_land_area.csv").exists():
        ar = pd.read_csv(REF / "zcta_land_area.csv", dtype={"zcta": str}); radius = {z: float(np.sqrt(a / np.pi)) for z, a in zip(ar.zcta, ar.land_sqmi.astype(float))}
    fams = site_names.load_families(REF / "site_families.csv") if (REF / "site_families.csv").exists() else []
    gz = gazetteer_frame(); places = collections.defaultdict(list)
    for st, pl, la, lo, nm, a in zip(gz.state, gz.place, gz.lat, gz.lon, gz.name, gz.aland_sqmi): places[st].append((pl, float(la), float(lo), nm, float(np.sqrt(float(a) / np.pi))))
    state_name = {USPS[k]: str(v).lower() for k, v in pd.read_csv(REF / "county_centroids.csv", dtype=str)[["state_fips", "state_name"]].drop_duplicates().values if k in USPS}
    edge = lambda q, p: max(0.0, _mi(q, (p[1], p[2])) - p[4])                    # miles from a point to the edge of a place
    ckey = lambda c: re.sub(r"\s+", " ", str(c or "").strip().lower()).strip(" .,")
    over = {}
    if (REF / "zip_city_overrides.csv").exists():
        with open(REF / "zip_city_overrides.csv", newline="", encoding="utf-8") as fh:
            import csv
            for r in csv.DictReader(row for row in fh if not row.lstrip().startswith("#")):
                if (r.get("facility") or "").strip(): over[(r["state"].strip(), norm(r["facility"]), ckey(r["city"]), r["zip"].strip()[:5])] = (r["verdict"].strip(), (r.get("note") or "").strip())
    rows = []                                                                    # every row with a location statement the review can use
    for i, st, city, z, fac, sf, nct in zip(sites.index, sites.state, sites.city, sites.zip, sites.facility, sites.state_fips, sites.nct_id):
        z = (z or "")[:5]; usable = z.isdigit() and len(z) == 5 and z in zxy and z2c.get(z, "")[:2] == sf
        pts = _city_pts(st, city)
        if not pts: continue                                                      # the city is not a Census place: nothing to compare
        ph = site_names.is_placeholder(fac, fams, city) or bool(GENERIC_NAME.search(norm(fac)))
        tok = site_names.flat_tokens(fac); key = " ".join(tok)
        fam = None if ph else site_names.family_of(tok, st, fams, site_names.is_childrens(fac))[0]
        out = min(max(0.0, _mi(zxy[z], q) - q[2]) for q in pts) if usable else None
        rows.append((i, st, ckey(city), z if usable else "", key if not ph and len(tok) >= 2 else "", fam, out, nct, city, norm(fac)))
    conflict = lambda z, out: out > max(CITY_GAP_MI, radius.get(z, 0.0))
    at_zip_name, at_zip_fam, in_city_name, in_city_fam = [collections.defaultdict(set) for _ in range(4)]
    in_city_zip, in_city_any, zip_city, near_zip = [collections.defaultdict(list) for _ in range(4)]
    for i, st, ck, z, key, fam, out, nct, city, nm in rows:
        if z and not conflict(z, out):                                            # ZIP and city do not disagree: the row is evidence for both
            if key: at_zip_name[(st, key, z)].add(nct); in_city_name[(st, key, ck)].add(nct); in_city_zip[(st, key, ck)].append(z); near_zip[st].append((frozenset(key.split()), zxy[z]))
            if fam: at_zip_fam[(st, fam, z)].add(nct); in_city_fam[(st, fam, ck)].add(nct); in_city_zip[(st, "\0" + fam, ck)].append(z)
            in_city_any[(st, ck)].append(z); zip_city[(st, z)].append(city.strip())
        elif not z:                                                               # no usable ZIP: the city is the row's only statement of place
            if key: in_city_name[(st, key, ck)].add(nct)
            if fam: in_city_fam[(st, fam, ck)].add(nct)
    others = lambda d, k, nct: len(d.get(k, set()) - {nct})   # trials other than the row's own
    city_zips = collections.defaultdict(set)                  # every ZIP the registry writes with a city, Census ZIP area or not (27157 is Wake Forest Baptist's own)
    for st_, c_, z_ in zip(sites.state, sites.city, sites.zip):
        if re.fullmatch(r"\d{5}", (z_ or "")[:5]): city_zips[(st_, ckey(c_))].add(z_[:5])

    def slip(z, used):                                        # one digit changed, or two neighbours swapped, gives a ZIP used in the city
        near = {z[:k] + d + z[k + 1:] for k in range(5) for d in "0123456789"} | {z[:k] + z[k + 1] + z[k] + z[k + 2:] for k in range(4)}
        return bool((near - {z}) & set(used))

    def place_of(st, z):                                                          # the name to print for a ZIP: the city the registry most often gives with it, else the Census place it lies in
        if zip_city.get((st, z)): return collections.Counter(zip_city[(st, z)]).most_common(1)[0][0]
        best = min(places[st], key=lambda p: (edge(zxy[z], p), _mi(zxy[z], (p[1], p[2]))), default=None)   # of the places whose circle covers the ZIP, the one whose centre is nearest
        return best[3] if best and edge(zxy[z], best) <= 3.0 else ""

    res = {}
    for i, st, ck, z, key, fam, out, nct, city, nm in rows:
        if i in skip or not z or out is None or not conflict(z, out): continue
        cty = city.strip(); zp = place_of(st, z); base = (f"ZIP {z} is in {zp}, " if zp else f"ZIP {z} is ") + f"{out:.0f} miles from {cty}"
        r = {"verdict": "ambiguous", "rule": "", "note": base, "mi": round(out), "zip_place": zp, "fix_zip": ""}
        padded = f" {nm} "; own = set(city_keys(st, city)); generic = site_names.GENERIC | site_names.WEAK
        names_zip = [p for p in places[st] if len(p[0]) >= 4 and p[0] not in own and p[0] not in generic and f" {norm(p[0])} " in padded and edge(zxy[z], p) <= max(5.0, radius.get(z, 0.0))]
        rest = padded
        for p_ in names_zip: rest = rest.replace(f" {norm(p_[0])} ", "  ")       # "North Chicago" names North Chicago, not Chicago
        names_city = any(len(k) >= 4 and k not in generic and f" {norm(k)} " in rest for k in own)
        loose = (st, ck) in MULTI_COUNTY_PLACE or (ck == state_name.get(st, "\0") + " city" and not in_city_any.get((st, ck)))
        lz_n, lz_f = (others(at_zip_name, (st, key, z), nct) if key else 0), (others(at_zip_fam, (st, fam, z), nct) if fam else 0)
        lc_n, lc_f = (others(in_city_name, (st, key, ck), nct) if key else 0), (others(in_city_fam, (st, fam, ck), nct) if fam else 0)
        listed_zip, listed_city = max(lz_n, lz_f), max(lc_n, lc_f)
        tok = frozenset(key.split())
        campus = bool(key) and any((t <= tok or tok <= t) and len(t & tok) >= 2 and _mi(q, zxy[z]) <= AGREE_MI for t, q in near_zip[st])   # a facility whose name contains this name, or is contained in it, is listed at the ZIP: a second campus
        o = over.get((st, nm, ck, z))
        if o and o[0] in ("zip", "city"):
            r.update(verdict=o[0], rule="checked by a person", note=f"{base}; {o[1]}" if o[1] else base)
            if o[0] == "city": r["fix_zip"] = (collections.Counter(in_city_zip.get((st, key, ck), []) or in_city_zip.get((st, "\0" + (fam or ""), ck), []) or in_city_any.get((st, ck), [])).most_common(1) or [("", 0)])[0][0]
        elif loose:
            why = f'"{cty}" is written for sites across the metropolitan area' if (st, ck) in MULTI_COUNTY_PLACE else f"no registry row is located in {cty}; the city field repeats the state"
            r.update(verdict="zip", rule="the city carries no information", note=f"{base}; {why}")
        elif names_zip and not names_city and lc_n == 0:                          # a name that names the ZIP's own town is specific; the institution having another site in the stated city does not outweigh it
            r.update(verdict="zip", rule="the name names the ZIP's place", note=f"{base}; the facility's name names {names_zip[0][3]}, and no other row lists this name in {cty}")
        elif listed_city == 0 and listed_zip >= MIN_LISTINGS:
            why = f"the same name is listed at this ZIP by {lz_n} other trials" if lz_n >= MIN_LISTINGS else f"{fam} is listed at this ZIP by {lz_f} other trials"
            r.update(verdict="zip", rule="listed at the ZIP, not in the city", note=f"{base}; {why}, and no other row lists it in {cty}")
        elif listed_zip == 0 and not campus and (lc_n >= MIN_LISTINGS or (names_city and not names_zip) or (lc_f >= MIN_LISTINGS and slip(z, city_zips.get((st, ck), ())))):
            # An institution with many sites may have one at the ZIP that no other trial lists, so its presence in the city decides only
            # when the ZIP is also one slip of the keyboard from a ZIP the registry uses in that city. The same name, or a name that
            # names the city, needs no such support.
            fz = (collections.Counter(in_city_zip.get((st, key, ck), []) or in_city_zip.get((st, "\0" + (fam or ""), ck), []) or in_city_any.get((st, ck), [])).most_common(1) or [("", 0)])[0][0]
            if fz:
                why = f"the same name is listed in {cty} by {lc_n} other trials" if lc_n >= MIN_LISTINGS else (f"the facility's name names {cty}" if names_city and not names_zip else f"{fam} is listed in {cty} by {lc_f} other trials and the ZIP is one keystroke from a ZIP used there")
                r.update(verdict="city", rule="listed in the city, not at the ZIP", note=f"{base}; {why}, and no other row lists it at ZIP {z}; placed at ZIP {fz}", fix_zip=fz)
        elif (listed_zip or campus) and listed_city: r["note"] = base + "; the registry lists the same institution in both places"
        if r["verdict"] == "city" and not r["fix_zip"]: r["verdict"] = "ambiguous"
        if r["verdict"] == "zip" and not zp: r["verdict"] = "ambiguous"          # no name to print for the ZIP's place: the stated city stays, so the row is flagged
        res[i] = r
    return res


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
    # ZIP and city that disagree (zip_city_review): where the registry's other rows show the ZIP to be the error, the row is placed like a
    # mistyped ZIP; where they show the city to be the error, or cannot tell, the row stays at its ZIP and carries the verdict
    review = zip_city_review(sites, skip=set(typos))
    for i_, r_ in review.items():
        if r_["verdict"] == "city": typos[i_] = (r_["note"], r_["fix_zip"])
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
    # zip_city: "zip" (the city is the error: the pages print city_fix, the ZIP's own place), "ambiguous" (the pages flag the row), or
    # "" (ZIP and city agree, cannot be compared, or the ZIP was the error and the row is a zip_typo_corrected row)
    at_own_zip = [m_ in ("zip", "zip_pop") for m_ in method]
    kept = [review.get(i_) if ok_ else None for i_, ok_ in zip(sites.index, at_own_zip)]
    sites["zip_city"] = [r_["verdict"] if r_ and r_["verdict"] in ("zip", "ambiguous") else "" for r_ in kept]
    sites["city_fix"] = [r_["zip_place"] if r_ and r_["verdict"] == "zip" else "" for r_ in kept]
    sites["zip_place"] = [r_["zip_place"] if r_ and r_["verdict"] in ("zip", "ambiguous") else "" for r_ in kept]      # the place the ZIP is in, for the flag's wording
    sites["zip_city_mi"] = [str(r_["mi"]) if r_ and r_["verdict"] in ("zip", "ambiguous") else "" for r_ in kept]      # miles from the ZIP to the edge of the stated city
    sites["zip_city_note"] = [r_["note"] if r_ and r_["verdict"] in ("zip", "ambiguous") else "" for r_ in kept]
    return sites


def _selftest_zip_city():
    """zip_city_review on fixed, made-up registry rows (the places and ZIP codes are real). Prints one line and returns True when
    every verdict is the expected one. validate_v3.py runs it at every refresh, so a change to the rules that breaks one of these
    stops the release."""
    fips = {v: k for k, v in USPS.items()}; rows = []; want = []; n = [0]

    def add(fac, city, st, z, times=1):
        for _ in range(times): n[0] += 1; rows.append({"nct_id": f"NCT9{n[0]:07d}", "facility": fac, "city": city, "state_fips": fips[st], "state": st, "zip": z, "site_status": "RECRUITING"})
        return len(rows) - 1

    def case(label, fac, city, st, z, verdict, key=None, value=None): want.append((label, add(fac, city, st, z), verdict, key, value))
    add("Mayo Clinic", "Jacksonville", "FL", "32224", 3)
    case("a city field that repeats the state", "Mayo Clinic", "Florida City", "FL", "32224", "zip", "zip_place", "Jacksonville")
    case('"New York" written for a Long Island clinic', "Memorial Sloan Kettering Commack", "New York", "NY", "11725", "zip", "zip_place", "Commack")
    case("the name names the place of the ZIP", "UC San Diego Moores Cancer Center", "Sacramento", "CA", "92093", "zip")
    add("Georgia Cancer Center", "Augusta", "GA", "30912", 3)
    case("listed at the ZIP by other trials, never in the city", "Georgia Cancer Center", "Atlanta", "GA", "30912", "zip", "zip_place", "Augusta")
    add("Karmanos Cancer Institute at McLaren Lapeer Region", "Lapeer", "MI", "48446", 3)
    case("listed in the city by other trials, never at the ZIP", "Karmanos Cancer Institute at McLaren Lapeer Region", "Lapeer", "MI", "48466", "city", "fix_zip", "48446")
    add("Lone Star Oncology Group", "Tyler", "TX", "75702", 2); add("Lone Star Oncology Group", "McAllen", "TX", "78503", 2)
    case("listed in both places", "Lone Star Oncology Group", "Tyler", "TX", "78503", "ambiguous")
    case("a sponsor placeholder says nothing", "GSK Investigational Site", "Sioux Falls", "SD", "57501", "ambiguous")
    add("Orange Coast Cancer Center", "Duarte", "CA", "91010", 3); add("Orange Coast Cancer Center Irvine Campus", "Irvine", "CA", "92618", 3)
    case("a second campus of the name at the ZIP", "Orange Coast Cancer Center Irvine Campus", "Irvine", "CA", "91010", "ambiguous")
    case("a row a person has checked (zip_city_overrides.csv)", "Saint Catherine Hospital", "Indianapolis", "IN", "46312", "zip", "zip_place", "East Chicago")
    case("a suburb's ZIP under the main city's name is not a conflict", "Lakeside Cancer Clinic", "Orlando", "FL", "32804", None)
    df = pd.DataFrame(rows); res = zip_city_review(df); bad = []
    for label, i, verdict, key, value in want:
        got = res.get(i)
        if (got["verdict"] if got else None) != verdict or (key and got[key] != value): bad.append(f"{label}: expected {verdict}{' ' + str(value) if key else ''}, got {(got['verdict'], got.get(key)) if got else None}")
    print(f"ZIP and city rules: {len(want) - len(bad)} of {len(want)} fixed examples pass" + ("".join("\n  FAILED " + b for b in bad)))
    return not bad


ZIP_CITY_DECISION = {"zip": "ZIP kept, city corrected", "ambiguous": "undecided, flagged on the pages", "city": "city kept, ZIP corrected"}


def zip_city_audit(sites):
    """One line per registry row whose ZIP and city disagreed, with what was decided and why (written to zip_city_review.csv by
    main, so anyone can check a decision against the registry). Covers the rows judged by zip_city_review and the rows whose ZIP
    was judged a typing error by zip_typos; both of the latter are assign_method zip_typo_corrected."""
    s = sites[(sites.zip_city != "") | (sites.assign_method == "zip_typo_corrected")].copy()
    s["decision"] = [ZIP_CITY_DECISION[v or "city"] for v in s.zip_city]
    s["zip_used"] = [zf if v == "" else z[:5] for v, zf, z in zip(s.zip_city, s.zip_fix, s.zip)]
    s["city_shown"] = [cf if v == "zip" else c.strip() for v, cf, c in zip(s.zip_city, s.city_fix, s.city)]
    s["why"] = [n if v else an for v, n, an in zip(s.zip_city, s.zip_city_note, s.assign_note)]
    s["zip"] = s.zip.str[:5]
    return s.sort_values(["decision", "state", "city", "facility", "nct_id"])[["nct_id", "facility", "city", "state", "zip", "decision", "county_fips", "zip_used", "city_shown", "why"]]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--min-max-age", type=float); ap.add_argument("--out", default="out")
    ap.add_argument("--test-zip-city", action="store_true", help="run the fixed examples of the ZIP/city review and exit")
    a = ap.parse_args()
    if a.test_zip_city: sys.exit(0 if _selftest_zip_city() else 1)
    OUT = Path(a.out); OUT.mkdir(exist_ok=True)
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
    audit = zip_city_audit(sites); audit.to_csv(OUT / "zip_city_review.csv", index=False)
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
    log = {"age_filter": age_note, "site_rows": len(sites), "site_assignment": qc, "zip_city_review": {k: int(v) for k, v in audit.decision.value_counts().items()}, "distinct_trials": int(trials.nct_id.nunique()),
           "counties": len(c), "counties_with_any_trial": int((c.trials_in_county > 0).sum()), "broad_menu_counties": int(len(brd_idx)), "limited_menu_counties": int(len(lim_idx)),
           "districts": len(dist), "us": us}
    json.dump(log, open(OUT / "metrics_log.json", "w"), indent=2); print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
