"""Facility names: the registry spells one institution many ways ("MD Anderson Cancer Center", "The University of Texas M. D. Anderson
Cancer Center", "UT MD Anderson Cancer Center, Division of Cancer Medicine" ...). This module decides which spellings are one facility.

The unit is ONE INSTITUTION AT ONE ZIP CODE IN ONE COUNTY. Two spellings are merged only when they are listed in the same county, the
registry gives them the same ZIP code, and one of four rules says they name the same institution:

  same-words   the same words once case, punctuation, brackets, sponsor site codes, legal suffixes ("Inc", "PLLC"), filler words
               ("the", "of", "at") and common abbreviations ("Ctr", "Univ", "Hosp", "St.") are set aside, in any order
  misspelling  the same words but for one that differs by a letter ("Sloane Kettering", "Icahan", "Universtiy")
  same-name    the same distinctive words once generic ones ("Hospital", "Cancer Center", "Health System", "Department of ...") and
               the place's own city and state are set aside ("Henry Ford Hospital" / "Henry Ford Health System")
  family       both match one line of data/ref/site_families.csv, a hand-written list of large institutions and the names their
               cancer programs go by ("NYU Langone" / "Perlmutter Cancer Center"; "Emory" / "Winship")

A satellite at another ZIP code ("MD Anderson West Houston", 77079) is never merged into the main campus (77030), whatever it is called.
Sponsor placeholders ("Research Site", "GSK Investigational Site", "Site 0173") name no institution: they are never merged with a named
facility and are flagged, not guessed at.

Nothing here touches where a site is placed on the map or any access figure: those are computed per trial and per registry row.
It changes which rows are listed together as one facility, and therefore the facility count.

    python3 site_names.py            report what would merge in the current pull (reads out_adult55/site_assignment_qc.csv)
    python3 site_names.py --test     self-test on fixed examples
"""
import csv, re, sys
from collections import defaultdict
from pathlib import Path

# the same sponsor-site-code pattern the site build uses (build_webapp_data_v3.SITECODE): "( Site 0087)", "Local Institution - 0012", "/ID# 12345"
SITECODE = re.compile(r"\(?\s*(site|study site|local institution|investigative site|clinical site|id|site id|site number|site #)\s*[-#:]?\s*\d+[a-z]?\s*\)?|\(\s*\d{3,6}\s*\)|/\s*id#?\s*\d+|\bsite\s+\d{2,6}\b", re.I)

ABBR = {"ctr": "center", "cntr": "center", "centre": "center", "centers": "center", "centres": "center", "ctrs": "center", "univ": "university", "uni": "university", "hosp": "hospital",
        "hospitals": "hospital", "med": "medical", "inst": "institute", "institutes": "institute", "dept": "department", "mt": "mount", "st": "saint", "hlth": "health", "healthcare": "health",
        "onc": "oncology", "oncol": "oncology", "hem": "hematology", "heme": "hematology", "hematol": "hematology", "haematology": "hematology", "assoc": "associates", "associate": "associates",
        "grp": "group", "specialist": "specialists", "physician": "physicians", "clinics": "clinic", "svc": "services", "service": "services", "cancers": "cancer", "comp": "comprehensive"}
# "ca" is left alone: it is California as often as cancer
STOP = set("the of at and for in a an on by".split()) | set("inc llc pllc lp llp ltd corp dba".split())
# "P.C.", "P.A.", "S.C.", "Co." are legal suffixes, but PA, SC and CO are also states: dropped unless the word opens the name or follows
# "of / in / at / from" ("SC Cancer Specialists", "Medical University of SC")
LEGAL_AMBIG = set("pc pa sc co apc psc".split())

# words that say what kind of place or which unit it is, not whose it is
GENERIC = set("""center cancer medical university hospital health system oncology hematology research institute care clinical clinic comprehensive specialists medicine associates group
network foundation partners services department division program unit section treatment therapy physicians practice college school science sciences academic campus main
regional community general memorial national american america advanced first united new professional professionals outpatient ambulatory pavilion building tower plaza infusion pharmacy
investigational office offices data collection only all protocol activities activites site location facility study trial trials adult adults blood disorders tumor tumors institution number
urology urologic urological dermatology radiology gynecology gynecologic surgery surgical specialty specialties consultants consultant affiliates advisors oncologists doctors usor uso scri
""".split())

# a direction or a landform alone does not name an institution ("Northwest Oncology" and "Northwest Cancer Centers" are two practices)
WEAK = set("""north south east west central northern southern eastern western northeast northwest southeast southwest midwest mid downtown midtown uptown upper lower greater
valley coast coastal mountain mountains lake lakes bay river park city county state metro metropolitan pacific atlantic gulf premier united hope shore alliance""".split())

# words of a physician practice's name; two of them added to a hospital's name mean a practice with an office there
PRACTICE = set("oncology hematology specialists associates physicians partners urology consultants group".split())

STATE_NAME = {"01": "alabama", "02": "alaska", "04": "arizona", "05": "arkansas", "06": "california", "08": "colorado", "09": "connecticut", "10": "delaware", "11": "district columbia washington dc",
              "12": "florida", "13": "georgia", "15": "hawaii", "16": "idaho", "17": "illinois", "18": "indiana", "19": "iowa", "20": "kansas", "21": "kentucky", "22": "louisiana", "23": "maine",
              "24": "maryland", "25": "massachusetts", "26": "michigan", "27": "minnesota", "28": "mississippi", "29": "missouri", "30": "montana", "31": "nebraska", "32": "nevada",
              "33": "new hampshire", "34": "new jersey", "35": "new mexico", "36": "new york", "37": "north carolina", "38": "north dakota", "39": "ohio", "40": "oklahoma", "41": "oregon",
              "42": "pennsylvania", "44": "rhode island", "45": "south carolina", "46": "south dakota", "47": "tennessee", "48": "texas", "49": "utah", "50": "vermont", "51": "virginia",
              "53": "washington", "54": "west virginia", "55": "wisconsin", "56": "wyoming", "72": "puerto rico"}
USPS = {"01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA",
        "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM",
        "36": "NY", "37": "NC", "38": "ND", "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
        "54": "WV", "55": "WI", "56": "WY", "72": "PR"}


def _unbracket(x):
    """Bracketed asides dropped ("(Data Collection Only)", "(MDACC)"); a bracket that never closes loses only the bracket."""
    y = str(x)
    while True:
        z = re.sub(r"\([^()]*\)", " ", y)
        if z == y: break
        y = z
    return y.replace("(", " ").replace(")", " ")


def flat_tokens(raw):
    """The words of a registry facility name, in order: site codes and bracketed asides dropped, lower case, abbreviations spelled out,
    initials joined ("M. D. Anderson" -> "md anderson"), filler words and legal suffixes dropped."""
    y = _unbracket(SITECODE.sub(" ", str(raw))).lower()
    y = re.sub(r"\ba\s*&\s*m\b", "am", y).replace("&", " and "); y = re.sub(r"[’'`?]s\b", "s", y); y = re.sub(r"[’'`]", "", y)
    y = re.sub(r"\bveterans?\s+(affairs|administration)\b", " veterans ", y); y = re.sub(r"\bhealth\s+care\b", "health", y); y = y.replace("newyork", "new york")
    # "VA" is the Veterans Affairs system before "Medical Center" and the like, and Virginia after a city ("Richmond, VA")
    y = re.sub(r"\bvamc\b", " veterans medical center ", y); y = re.sub(r"(^\W*|\b)v\.?a\.?(?=\s+(medical|med|health|healthcare|hlth|hospital|hosp|greater|central|[a-z.]+\s+(health|healthcare|medical)))", " veterans ", y)
    t = re.sub(r"[^a-z0-9 ]", " ", y).split(); out = []; i = 0
    while i < len(t):
        if len(t[i]) == 1 and t[i].isalpha():
            j = i
            while j < len(t) and len(t[j]) == 1 and t[j].isalpha(): j += 1
            out.append("".join(t[i:j])); i = j
        else: out.append(t[i]); i += 1
    keep = []
    for k, w in enumerate(out):
        if w in LEGAL_AMBIG and not (k == 0 or out[k - 1] in ("of", "in", "at", "from")): continue
        keep.append(w)
    return [w for w in (ABBR.get(w, w) for w in keep) if w not in STOP]


def load_families(path):
    """data/ref/site_families.csv -> [(family, set of USPS codes or None, compiled pattern, campus ZIPs)], in file order (the first match wins)."""
    fam = []
    if not Path(path).exists(): return fam
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(row for row in fh if not row.lstrip().startswith("#")):
            if not (r.get("family") or "").strip(): continue
            st = {x.strip().upper() for x in re.split(r"[|; ]+", r.get("states") or "") if x.strip()} or None
            zips = [z for z in re.split(r"[|; ]+", (r.get("zips") or "").strip()) if z]
            fam.append((r["family"].strip(), st, re.compile(r["pattern"].strip()), zips))
    return fam

_FAMS = None
def _default_families():
    global _FAMS
    if _FAMS is None: _FAMS = load_families(Path(__file__).parent / "data/ref/site_families.csv")
    return _FAMS


# A sponsor's placeholder, not an institution: "Research Site", "GSK Investigational Site", "Exelixis Clinical Site #12", "Site 0173",
# "Investigative Site US031", "USA04-0", "Zai Lab Site 02002", "ALX Center 7". Decided on the name as the registry gives it, with bracketed
# parts set aside first: "Kaiser Permanente - Santa Clara ( Site 0123)" is Kaiser Permanente with a sponsor's code after it. A name that
# matches a line of the institution list is never a placeholder ("MD Anderson Site 12", "USC 1").
_PH_PHRASE = re.compile(r"\b(investigational|investigative|investigator|recruiting)\s+(sites?|center|centre|location)\b|\b(clinical|research)\s+(study|trial)\s+sites?\b|\b(study|trial)\s+sites?\b"
                        r"|^\W*(clinical\s+)?(research|clinical)\s+(sites?|facility)\b|^\W*(local institution|site)\b[\s#:.\-]*[\w-]*\W*$", re.I)
_PH_ENDS_SITE = re.compile(r"^(.*?)\bsite\b[\s#:.\-]*([\w-]*)\W*$", re.I)
_PH_CODE = re.compile(r"^(?:site|study site|center|centre|location)?[\s#:.-]*(?:[A-Za-z]{0,3}[\s-]?)?\d[\dA-Za-z-]*$", re.I)
_PH_NUMBERED = re.compile(r"^\W*(\S{1,10})\s+(study\s+)?(cent(er|re)|location)\s*#?\s*\d+\W*$", re.I)       # "ALX Center 7", "Study Center 12"
# words that mark a real institution; a specialty alone ("Oncology Investigational Site") does not
_INST = re.compile(r"\b(hospital|universit|clinics?\b|institute|college|associates|specialists|physicians|cent(er|re)s?\b|foundation|permanente|health)", re.I)
def is_placeholder(raw, families=None):
    s = _unbracket(raw).strip(" -,/#:;")
    if not re.search(r"[A-Za-z]", s): return True
    flat = " ".join(flat_tokens(s))
    if any(rx.search(flat) for _, _, rx, _ in (_default_families() if families is None else families)): return False
    if _PH_CODE.match(s): return True
    m = _PH_NUMBERED.match(s)
    if m: return not _INST.search(m.group(1))
    if _PH_PHRASE.search(s): return not _INST.search(_PH_PHRASE.sub(" ", s))         # "Mayo Clinic Research Site" keeps its name
    m = _PH_ENDS_SITE.match(s)
    if m:                                                                            # "Zai Lab Site 02002", "NEO-811 NYC Site"; not "City of Hope - Duarte Main Site"
        head = m.group(1)
        return not _INST.search(head) and (bool(re.search(r"\d", head)) or len(re.findall(r"[A-Za-z0-9]+", head)) <= 2)
    return not flat


_CHILD = re.compile(r"\b(childrens?|pediatrics?|paediatrics?|kids)\b")
def is_childrens(raw, tokens=None):
    """A children's hospital, judged on the name's own words; "children" inside brackets counts ("UAB (Children's of Alabama)"), a
    bracketed "(Adults and Pediatrics)" after a general hospital's name does not."""
    return bool(_CHILD.search(" ".join(flat_tokens(raw) if tokens is None else tokens))) or "children" in str(raw).lower().replace("’", "").replace("'", "")

def family_of(tokens, usps, families, child=False):
    """(family, campus ZIPs) for a name's words, or (None, ()). A children's hospital is its own institution: it joins a family only
    when the family is itself a children's hospital ("St. Jude Children's Research Hospital")."""
    flat = " ".join(tokens)
    for name, states, rx, zips in families:
        if (states is None or usps in states) and rx.search(flat):
            if child and not _CHILD.search(" ".join(flat_tokens(name))): return None, ()
            return name, zips
    return None, ()


def _edit1(a, b):
    """True when a and b differ by one letter added, dropped, changed or swapped with its neighbour."""
    if a == b or abs(len(a) - len(b)) > 1: return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    if len(a) > len(b): a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]: i += 1
    return a[i:] == b[i + 1:]


def _tidy(name):
    """Lower is better: a spelling shown to readers should not be in capitals, carry a code, or be cut off mid-word."""
    n = str(name); letters = [c for c in n if c.isalpha()]
    return (int(bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.6) + int(bool(re.search(r"\d|#|'S\b|\bAttn\b", n))), len(n), n)


def merge_map(spellings, families=()):
    """spellings: iterable of dicts with county_fips, fac (the build's name key), name (the registry spelling most rows use), zip (the
    5-digit ZIP most rows give, or ""), city, n (registry rows). Returns (alias, audit, shown):
      alias  {(county_fips, fac): canonical fac}, only for spellings that move
      audit  one dict per moved spelling: county_fips, zip, kept (the name the site shows), merged (the spelling folded in), rows, rule
      shown  {(county_fips, canonical fac): the name to show} for every facility that absorbed a spelling
    The result does not depend on the order of the input."""
    groups = defaultdict(list)
    for s in sorted(spellings, key=lambda x: (x["county_fips"], x["fac"])):
        if not s["zip"] or is_placeholder(s["name"], families): continue
        s = dict(s); s["_tok"] = flat_tokens(s["name"]); s["_child"] = is_childrens(s["name"], s["_tok"])
        s["_fam"], campus = family_of(s["_tok"], USPS.get(s["county_fips"][:2]), families, s["_child"])
        groups[(s["county_fips"], campus[0] if s["zip"] in campus else s["zip"])].append(s)   # a family's campus ZIPs are one place
    alias, audit, shown = {}, [], {}
    for (county, z), g in sorted(groups.items()):
        if len(g) < 2: continue
        st = county[:2]; geo_state = set(STATE_NAME.get(st, "").split()) | {USPS.get(st, "").lower()}
        parent = list(range(len(g))); why = {}
        def find(i):
            while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
            return i
        def union(i, j, rule):
            a, b = find(i), find(j)
            if a != b: parent[max(a, b)] = min(a, b); why.setdefault(i, rule); why.setdefault(j, rule)
        toks = [s["_tok"] for s in g]; sets = [set(t) for t in toks]
        fam = [s["_fam"] for s in g]   # a spelling that names a listed institution is not pulled elsewhere by the same-name rule
        geo = [geo_state | set(flat_tokens(s.get("city", ""))) for s in g]
        # same words: the place's own city and state set aside ("... Medical Center" / "... Medical Center, Knoxville, TN"); a children's
        # hospital never shares a key with a general one, even when the word sits in brackets
        # ("University of California" alone could be any of its campuses or hospitals: it keeps its place words and joins nothing by them)
        bare = [(sets[i] - geo[i]) <= {"university"} for i in range(len(g))]
        cores = [" ".join(sorted(sets[i] if bare[i] else sets[i] - geo[i])) + (" |children" if g[i]["_child"] else "") for i in range(len(g))]
        # "Albany Medical Center" is not the practice "New York Oncology Hematology - Albany Medical Center" that has an office there
        guest = lambda i, j: bool(({"hospital"} <= sets[i] or {"medical", "center"} <= sets[i]) and len((sets[j] - sets[i]) & PRACTICE) >= 2)
        own = [{w for w in sets[i] if w not in GENERIC and w not in geo[i]} for i in range(len(g))]        # the words that are the name's own
        strong = [bool(d) and any(w not in WEAK and not w.isdigit() for w in d) and not (len(d) == 1 and len(next(iter(d))) < 4) for d in own]
        dist = [" ".join(sorted(own[i])) if strong[i] else "" for i in range(len(g))]
        first = {}
        for i in range(len(g)):
            # (same words never joins two listed institutions: "Tennessee Oncology Nashville - SCRI Oncology Partners" stays with the first)
            for key, rule in ((("c", cores[i], fam[i]), "same-words"), (("f", fam[i]), "family"), (("d", dist[i]) if fam[i] is None else ("d", ""), "same-name")):
                if not key[1]: continue
                if key in first: union(first[key], i, rule)
                else: first[key] = i
        # a name with no distinctive word of its own joins only a longer form of itself: "Pacific Cancer Care" / "Pacific Cancer Care -
        # Oncology", "Tampa General Hospital" / "Tampa General Hospital Cancer Institute". A name made only of generic words ("University
        # Hospital", "Cancer Center") does so only when its longer forms are one place already; a place name alone ("West Virginia") never
        for i in range(len(g)):
            if fam[i] or dist[i] or len(toks[i]) < 2 or bare[i]: continue
            longer = [j for j in range(len(g)) if i != j and not fam[j] and sets[i] < sets[j] and (sets[j] - sets[i]) <= (GENERIC | geo[j]) and not guest(i, j)]
            if longer and ((sets[i] - GENERIC) or "memorial" in sets[i] or len({find(j) for j in longer}) == 1):
                for j in longer: union(i, j, "same-name")
        # a listed institution's spelling that contains every word of an unlisted name at the same place is that place
        # ("Hillcrest Hospital" / "Cleveland Clinic - Hillcrest Hospital"), provided it points at one institution only
        for i in range(len(g)):
            if fam[i] or not dist[i]: continue
            ok = [j for j in range(len(g)) if fam[j] and g[j]["_child"] == g[i]["_child"] and (sets[i] - geo[i]) <= sets[j] and not guest(i, j)]
            if len({find(j) for j in ok}) == 1: union(i, ok[0], "same-name")
        # one misspelled word: the same number of words, all but one equal, the odd pair one letter apart (five letters or more, no digits)
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                if find(i) == find(j) or len(sets[i]) != len(sets[j]) or (fam[i] and fam[j] and fam[i] != fam[j]): continue
                a, b = sets[i] - sets[j], sets[j] - sets[i]
                if len(a) == 1 and len(b) == 1:
                    x, y = next(iter(a)), next(iter(b))
                    if x.isalpha() and y.isalpha() and min(len(x), len(y)) >= 5 and _edit1(x, y): union(i, j, "misspelling")
        comp = defaultdict(list)
        for i in range(len(g)): comp[find(i)].append(i)
        for members in comp.values():
            if len(members) < 2: continue
            # the name shown: the wording most registry rows use (spellings with the same words counted together), then its tidiest spelling
            by_core = defaultdict(list)
            for i in members: by_core[cores[i]].append(i)
            best = min(by_core.items(), key=lambda kv: (-sum(g[i]["n"] for i in kv[1]), -len(kv[1]), len(kv[0]), kv[0]))[1]
            keep = min(best, key=lambda i: (-g[i]["n"], _tidy(g[i]["name"]), g[i]["fac"]))
            shown[(county, g[keep]["fac"])] = g[keep]["name"]
            for i in members:
                if i == keep or g[i]["fac"] == g[keep]["fac"]: continue
                alias[(county, g[i]["fac"])] = g[keep]["fac"]
                if fam[i] and fam[i] == fam[keep]: rule = "family: " + fam[i]
                elif cores[i] == cores[keep]: rule = "same-words"
                elif dist[i] and dist[i] == dist[keep]: rule = "same-name"
                else: rule = why.get(i, "same-name") + ("" if why.get(i) == "misspelling" and len(sets[i] ^ sets[keep]) == 2 else " (through another spelling)")
                audit.append({"county_fips": county, "zip": g[i]["zip"], "kept": g[keep]["name"], "merged": g[i]["name"], "rows": g[i]["n"], "rule": rule})
    return alias, audit, shown


def mode(values):
    """The most common value; ties go to the tidiest, then the first in alphabetical order, so the answer does not depend on row order."""
    c = defaultdict(int)
    for v in values: c[v] += 1
    return min(c, key=lambda v: (-c[v], _tidy(v))) if c else ""


def spellings_from_rows(rows):
    """rows: DataFrame with county_fips, fac, facility, city, zip (and zip_own when the build has it: the ZIP of rows placed at their own
    ZIP, blank for rows whose ZIP was judged a typing error) -> the spelling records merge_map() reads."""
    zc = rows["zip_own"] if "zip_own" in rows.columns else rows["zip"]
    z5 = zc.astype(str).str[:5]; rows = rows.assign(_z=z5.where(z5.str.fullmatch(r"\d{5}"), ""))
    busy = rows[rows["_z"] != ""].groupby(["county_fips", "_z"]).size().to_dict()   # registry rows at each ZIP of a county
    out, counts = [], {}
    for (c, f), g in rows.groupby(["county_fips", "fac"], sort=True):
        n = defaultdict(int)
        for z in g["_z"]:
            if z: n[z] += 1
        counts[(c, f)] = n
        out.append({"county_fips": c, "fac": f, "name": mode(g["facility"]), "city": mode(g["city"]), "zip": "", "n": len(g)})
    # The ZIP most of a spelling's rows give. A tie (a name listed once each at several addresses) goes to the ZIP where the county's
    # other spellings of the same name have the most rows, then to the county's busiest ZIP, then to the lower number: never to row order.
    by_county = defaultdict(list)
    for o in out:
        t = set(flat_tokens(o["name"])); o["_k"] = (t - GENERIC) or t; o["_t"] = t; by_county[o["county_fips"]].append(o)
    for o in out:
        n = counts[(o["county_fips"], o["fac"])]
        if not n: continue
        top = max(n.values()); tied = [q for q in n if n[q] == top]
        if len(tied) > 1:
            kin = defaultdict(int)
            for r in by_county[o["county_fips"]]:
                if r is not o and o["_k"] and (o["_k"] <= r["_t"] or (r["_k"] and r["_k"] <= o["_t"])):
                    for q, v in counts[(r["county_fips"], r["fac"])].items(): kin[q] += v
            o["zip"] = min(tied, key=lambda q: (-kin.get(q, 0), -busy.get((o["county_fips"], q), 0), q))
        else: o["zip"] = tied[0]
    for o in out: del o["_k"], o["_t"]
    return out


def _selftest():
    F = load_families(Path(__file__).parent / "data/ref/site_families.csv")
    S = lambda c, name, z, n=1, city="": {"county_fips": c, "fac": re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", name.lower())).strip(), "name": name, "zip": z, "n": n, "city": city}
    def together(*sp):
        al, _, _ = merge_map(list(sp), F); k = {al.get((s["county_fips"], s["fac"]), s["fac"]) for s in sp}; return len(k) == 1
    def shown(*sp): return next(iter(merge_map(list(sp), F)[2].values()), None)
    ok = [
        ("initials and 'The University of Texas'", together(S("48201", "MD Anderson Cancer Center", "77030", 265, "Houston"), S("48201", "The University of Texas M. D. Anderson Cancer Center", "77030", 61, "Houston"), S("48201", "UT MD Anderson Cancer Center, Division of Cancer Medicine", "77030", 1, "Houston")), True),
        ("a satellite at another ZIP stays apart", together(S("48201", "MD Anderson Cancer Center", "77030", 265, "Houston"), S("48201", "MD Anderson West Houston", "77079", 8, "Houston")), False),
        ("a misspelled word", together(S("36061", "Memorial Sloan Kettering Cancer Center", "10065", 334, "New York"), S("36061", "Memorial Sloane Kettering Cancer Center", "10065", 2, "New York")), True),
        ("legal suffix and ampersand", together(S("01003", "Southern Cancer Center", "36526", 5, "Daphne"), S("01003", "Southern Cancer Center, P.C.", "36526", 1, "Daphne")), True),
        ("hospital and health system of one name", together(S("26163", "Henry Ford Hospital", "48202", 60, "Detroit"), S("26163", "Henry Ford Health System", "48202", 20, "Detroit")), True),
        ("two different hospitals at one ZIP stay apart", together(S("48201", "Houston Methodist Hospital", "77030", 40, "Houston"), S("48201", "Texas Children's Hospital", "77030", 12, "Houston")), False),
        ("a city name alone joins nothing", together(S("12086", "University of Miami", "33136", 30, "Miami"), S("12086", "Miami Cancer Institute", "33136", 5, "Miami")), False),
        ("a placeholder is never merged", together(S("36061", "GSK Investigational Site", "10065", 10, "New York"), S("36061", "Memorial Sloan Kettering Cancer Center", "10065", 334, "New York")), False),
        ("a children's hospital is not folded into the university beside it", together(S("17031", "Northwestern University", "60611", 80, "Chicago"), S("17031", "Ann & Robert H. Lurie Children's Hospital of Chicago", "60611", 9, "Chicago")), False),
        ("a named cancer center and its university", together(S("13089", "Emory University Hospital", "30322", 80, "Atlanta"), S("13089", "Winship Cancer Institute", "30322", 9, "Atlanta")), True),
        ("a university's own ZIP beside the street ZIP", together(S("37135", "UNC Lineberger Comprehensive Cancer Center", "27599", 80, "Chapel Hill"), S("37135", "University of North Carolina Hospitals", "27514", 9, "Chapel Hill")), True),
        ("north and south stay apart", together(S("05119", "Mercy Clinic North", "72205", 3, "Little Rock"), S("05119", "Mercy Clinic South", "72205", 3, "Little Rock")), False),
        ("a county hospital is not folded into the university named in it", together(S("06037", "USC / Norris Comprehensive Cancer Center", "90033", 120, "Los Angeles"), S("06037", "Los Angeles County-USC Medical Center", "90033", 2, "Los Angeles")), False),
        ("a public hospital beside a medical school stays apart", together(S("36005", "Montefiore Medical Center-Einstein Campus", "10461", 85, "Bronx"), S("36005", "Jacobi Medical Center - Albert Einstein College of Medicine", "10461", 1, "Bronx")), False),
        ("a practice named for a neighbourhood is not the hospital of that name", together(S("32003", "Summerlin Hospital Medical Center", "89144", 9, "Las Vegas"), S("32003", "Comprehensive Cancer Centers of Nevada-Summerlin", "89144", 11, "Las Vegas")), False),
        ("a children's hospital named in brackets stays apart", together(S("01073", "University of Alabama at Birmingham", "35233", 40, "Birmingham"), S("01073", "University of Alabama at Birmingham (Children's of Alabama)", "35233", 1, "Birmingham")), False),
        ("two campuses in one ZIP stay apart", together(S("53033", "Swedish Medical Center-First Hill", "98122", 30, "Seattle"), S("53033", "Swedish Medical Center-Cherry Hill", "98122", 19, "Seattle")), False),
        ("a listed institution takes the plain name of the same place", together(S("39035", "Cleveland Clinic - Hillcrest Hospital", "44124", 20, "Mayfield Heights"), S("39035", "Hillcrest Hospital", "44124", 5, "Mayfield Heights")), True),
        ("a city and state after the name change nothing", together(S("48201", "Michael E DeBakey VA Medical Center", "77030", 9, "Houston"), S("48201", "Michael E. DeBakey Veterans Affairs Medical Center, Houston, TX", "77030", 2, "Houston")), True),
        ("a name ending in its own city", together(S("47093", "University of Tennessee Medical Center", "37920", 20, "Knoxville"), S("47093", "University of Tennessee Medical Center Knoxville", "37920", 3, "Knoxville")), True),
        ("a specialty is not a name", together(S("08059", "Colorado Urology", "80228", 4, "Lakewood"), S("08059", "Advanced Urology", "80228", 2, "Lakewood")), False),
        ("a generic name does not chain two places together", together(S("12057", "University Hospital", "33606", 4, "Tampa"), S("12057", "University Community Hospital", "33606", 2, "Tampa"), S("12057", "University General Hospital", "33606", 2, "Tampa")), False),
        ("a town's hospital and its cancer institute", together(S("12057", "Tampa General Hospital", "33606", 30, "Tampa"), S("12057", "Tampa General Hospital Cancer Institute", "33606", 6, "Tampa")), True),
        ("a place name alone joins nothing", together(S("54061", "West Virginia University Healthcare", "26506", 30, "Morgantown"), S("54061", "West Virginia", "26506", 1, "Morgantown")), False),
        ("row order does not matter", merge_map([S("48201", "MD Anderson", "77030", 5, "Houston"), S("48201", "M D Anderson Cancer Center", "77030", 5, "Houston"), S("48201", "UT MD Anderson Cancer Center", "77030", 5, "Houston")], F)
            == merge_map([S("48201", "UT MD Anderson Cancer Center", "77030", 5, "Houston"), S("48201", "MD Anderson", "77030", 5, "Houston"), S("48201", "M D Anderson Cancer Center", "77030", 5, "Houston")], F), True),
        ("the name shown is the commonest wording, not a misspelling", shown(S("42003", "UPMC Hillman Cancer Center", "15232", 60, "Pittsburgh"), S("42003", "UMPC Hillman Cancer Center", "15232", 2, "Pittsburgh"), S("42003", "UPMC Hillman Cancer Ctr", "15232", 9, "Pittsburgh")) == "UPMC Hillman Cancer Center", True),
    ]
    ph = [("Research Site", True), ("GSK Investigational Site", True), ("Exelixis Clinical Site #12", True), ("Site 0173", True), ("USA04-0", True), ("Investigative Site US031", True), ("Zai Lab Site 02002", True),
          ("Clinical Study Site", True), ("Memorial Sloan Kettering Cancer Center", False), ("Palo Alto Medical Foundation Research Center", False), ("Rocky Mountain Cancer Centers (RMCC) ( Site 0123)", False),
          ("Mayo Clinic", False), ("START San Antonio", False), ("Kaiser Permanente - Santa Clara ( Site 0123)", False), ("City of Hope - Duarte Main Site", False), ("VA Long Beach Healthcare System ( Site 0041)", False),
          ("NEO-811 NYC Site", True), ("I-Mab Site 1002", True), ("Avenzo Therapeutics Recruiting Site", True), ("010", True), ("Clinical Study Sites", True), ("CBCC Global Research Site 0010", False),
          ("Site 0221 - Tufts Medical Center - PPDS", False), ("US Oncology Research Investigational Products Center", False), ("ALX Center 7", True), ("Study Center 12", True),
          ("MD Anderson Site 12", False), ("Houston Methodist Site", False), ("Research Site - Los Angeles", True), ("Oncology Investigational Site", True), ("(UCLA Medical Center", False),
          ("Mayo Clinic Research Site", False)]
    bad = [n for n, got, want in ok if got != want] + [f"placeholder: {n}" for n, want in ph if is_placeholder(n) != want]
    print(f"site_names self-test: {len(ok) + len(ph) - len(bad)}/{len(ok) + len(ph)} pass" + ("" if not bad else " | FAILED: " + "; ".join(bad)))
    return not bad


def main():
    if "--test" in sys.argv: sys.exit(0 if _selftest() else 1)
    import pandas as pd
    norm = lambda x: re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", SITECODE.sub(" ", str(x)).lower())).strip()
    s = pd.read_csv("out_adult55/site_assignment_qc.csv", dtype=str).fillna(""); s = s[s.county_fips != ""].copy(); s["fac"] = s.facility.map(norm)
    sp = spellings_from_rows(s); alias, audit, _ = merge_map(sp, load_families("data/ref/site_families.csv"))
    after = len({(x["county_fips"], alias.get((x["county_fips"], x["fac"]), x["fac"])) for x in sp}); ph = sum(is_placeholder(x["name"]) for x in sp)
    print(f"{len(sp):,} spellings -> {after:,} facilities ({len(alias):,} spellings folded in); {ph:,} of the spellings are sponsor placeholders")
    by = defaultdict(int)
    for a in audit: by[a["rule"].split(":")[0]] += 1
    print("by rule:", dict(by))


if __name__ == "__main__":
    main()
