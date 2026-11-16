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
STOP = set("the of at and for in a an on by".split()) | set("inc llc pllc pc pa lp llp ltd corp co dba psc sc apc".split())

# words that say what kind of place or which unit it is, not whose it is
GENERIC = set("""center cancer medical university hospital health system oncology hematology research institute care clinical clinic comprehensive specialists medicine associates group
network foundation partners services department division program unit section treatment therapy physicians practice college school science sciences academic campus main
regional community general memorial national american advanced first united new professional outpatient ambulatory pavilion building tower plaza infusion pharmacy investigational
office offices data collection only all protocol activities activites site location facility study trial trials adult adults blood disorders tumor tumors institution
""".split())

# a direction or a landform alone does not name an institution ("Northwest Oncology" and "Northwest Cancer Centers" are two practices)
WEAK = set("""north south east west central northern southern eastern western northeast northwest southeast southwest midwest mid downtown midtown uptown upper lower greater
valley coast coastal mountain mountains lake lakes bay river park city county state metro metropolitan pacific atlantic gulf premier united""".split())

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


def flat_tokens(raw):
    """The words of a registry facility name, in order: site codes and anything in brackets dropped, lower case, abbreviations spelled
    out, initials joined ("M. D. Anderson" -> "md anderson"), filler words and legal suffixes dropped."""
    y = SITECODE.sub(" ", str(raw)); y = re.sub(r"\([^)]*\)?", " ", y)
    y = y.lower().replace("&", " and "); y = re.sub(r"[’'`?]s\b", "s", y); y = re.sub(r"[’'`]", "", y)
    t = re.sub(r"[^a-z0-9 ]", " ", y).split(); out = []; i = 0
    while i < len(t):
        if len(t[i]) == 1 and t[i].isalpha():
            j = i
            while j < len(t) and len(t[j]) == 1 and t[j].isalpha(): j += 1
            out.append("".join(t[i:j])); i = j
        else: out.append(t[i]); i += 1
    return [w for w in (ABBR.get(w, w) for w in out) if w not in STOP]


# A sponsor's placeholder, not an institution: "Research Site", "GSK Investigational Site", "Exelixis Clinical Site #12", "Site 0173",
# "Investigative Site US031", "USA04-0", "Zai Lab Site 02002". Decided on the name as the registry gives it, with bracketed parts set
# aside first: "Kaiser Permanente - Santa Clara ( Site 0123)" is Kaiser Permanente with a sponsor's code after it, not a placeholder.
_PH_PHRASE = re.compile(r"\b(investigational|investigative|investigator|recruiting)\s+(sites?|center|centre|location)\b|\b(clinical|research)\s+(study|trial)\s+sites?\b|\b(study|trial)\s+sites?\b"
                        r"|^\W*(clinical\s+)?(research|clinical)\s+(sites?|facility)\b[\s#:.\-]*[\w-]*\W*$|^\W*(local institution|site)\b[\s#:.\-]*[\w-]*\W*$", re.I)
_PH_ENDS_SITE = re.compile(r"^(.*?)\bsite\b[\s#:.\-]*([\w-]*)\W*$", re.I)
_PH_CODE = re.compile(r"^(?:site|study site|center|centre|location)?[\s#:.-]*(?:[A-Za-z]{0,3}[\s-]?)?\d[\dA-Za-z-]*$", re.I)
_REAL = re.compile(r"\b(hospital|universit|clinics?\b|medical|medicine|cancer|oncolog|hematolog|urolog|health|institute|college|associates|specialists|physicians|cent(er|re)s?\b|foundation|permanente)", re.I)
def is_placeholder(raw):
    s = re.sub(r"\([^)]*\)?", " ", str(raw)).strip(" -,/#:;")
    if not re.search(r"[A-Za-z]", s) or _PH_CODE.match(s): return True
    if _PH_PHRASE.search(s): return not _REAL.search(_PH_PHRASE.sub(" ", s))        # "Mayo Clinic Research Site" keeps its name
    m = _PH_ENDS_SITE.match(s)
    if m:                                                                            # "Zai Lab Site 02002", "NEO-811 NYC Site"; not "City of Hope - Duarte Main Site"
        head = m.group(1)
        return not _REAL.search(head) and (bool(re.search(r"\d", head)) or len(re.findall(r"[A-Za-z0-9]+", head)) <= 2)
    return not flat_tokens(s)


def load_families(path):
    """data/ref/site_families.csv -> [(family, set of USPS codes or None, compiled pattern)], in file order (the first match wins)."""
    fam = []
    if not Path(path).exists(): return fam
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(row for row in fh if not row.lstrip().startswith("#")):
            if not (r.get("family") or "").strip(): continue
            st = {x.strip().upper() for x in re.split(r"[|; ]+", r.get("states") or "") if x.strip()} or None
            zips = [z for z in re.split(r"[|; ]+", (r.get("zips") or "").strip()) if z]
            fam.append((r["family"].strip(), st, re.compile(r["pattern"].strip()), zips))
    return fam


_CHILD = re.compile(r"\b(childrens?|pediatrics?|paediatrics?|kids)\b")
def family_of(tokens, usps, families):
    """(family, campus ZIPs) for a name's words, or (None, ()). A children's hospital is its own institution: it joins a family only
    when the family is itself a children's hospital ("St. Jude Children's Research Hospital")."""
    flat = " ".join(tokens)
    for name, states, rx, zips in families:
        if (states is None or usps in states) and rx.search(flat):
            if _CHILD.search(flat) and not _CHILD.search(" ".join(flat_tokens(name))): return None, ()
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


def merge_map(spellings, families=()):
    """spellings: iterable of dicts with county_fips, fac (the build's name key), name (the registry spelling most rows use), zip (the
    5-digit ZIP most rows give, or ""), city, n (registry rows). Returns (alias, audit):
      alias  {(county_fips, fac): canonical fac}, only for spellings that move
      audit  one dict per moved spelling: county_fips, zip, kept (the name kept), merged (the spelling folded in), rows, rule"""
    groups = defaultdict(list)
    for s in spellings:
        if not s["zip"] or is_placeholder(s["name"]): continue
        s = dict(s); s["_tok"] = flat_tokens(s["name"]); s["_fam"], campus = family_of(s["_tok"], USPS.get(s["county_fips"][:2]), families)
        groups[(s["county_fips"], campus[0] if s["zip"] in campus else s["zip"])].append(s)   # a family's campus ZIPs are one place
    alias, audit = {}, []
    for (county, z), g in groups.items():
        if len(g) < 2: continue
        st = county[:2]; geo_state = set(STATE_NAME.get(st, "").split())
        parent = list(range(len(g))); why = {}
        def find(i):
            while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
            return i
        def union(i, j, rule):
            a, b = find(i), find(j)
            if a != b: parent[b] = a; why[(min(i, j), max(i, j))] = rule
        toks = [s["_tok"] for s in g]; cores = [" ".join(sorted(set(t))) for t in toks]
        fam = [s["_fam"] for s in g]   # a spelling that names a listed institution is not pulled elsewhere by the same-name rule
        dist = []
        for s, t in zip(g, toks):
            geo = geo_state | set(flat_tokens(s.get("city", "")))
            d = sorted({w for w in t if w not in GENERIC and w not in geo})
            ok = d and any(w not in WEAK and not w.isdigit() for w in d) and not (len(d) == 1 and len(d[0]) < 4)
            dist.append(" ".join(d) if ok else "")
        first = {}
        for i in range(len(g)):
            for key, rule in ((("c", cores[i]), "same-words"), (("f", fam[i]), "family"), (("d", dist[i]) if fam[i] is None else ("d", ""), "same-name")):
                if not key[1]: continue
                if key in first: union(first[key], i, rule)
                else: first[key] = i
        # a name with no distinctive word of its own ("Pacific Cancer Care") joins only a longer form of itself ("Pacific Cancer Care - Oncology")
        for i in range(len(g)):
            for j in range(len(g)):
                if i != j and not fam[i] and not fam[j] and not dist[i] and len(toks[i]) >= 2 and set(toks[i]) < set(toks[j]) and (set(toks[j]) - set(toks[i])) <= GENERIC:
                    union(i, j, "same-name")
        # one misspelled word: the same number of words, all but one equal, the odd pair one letter apart (five letters or more, no digits)
        sets = [set(c.split()) for c in cores]
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
            keep = min(members, key=lambda i: (-g[i]["n"], len(g[i]["name"]), g[i]["fac"]))
            rules = {}
            for (i, j), rule in why.items():
                for k in (i, j): rules.setdefault(k, rule)
            for i in members:
                if i == keep or g[i]["fac"] == g[keep]["fac"]: continue
                alias[(county, g[i]["fac"])] = g[keep]["fac"]
                audit.append({"county_fips": county, "zip": g[i]["zip"], "kept": g[keep]["name"], "merged": g[i]["name"], "rows": g[i]["n"],
                              "rule": "family: " + fam[i] if fam[i] and fam[i] == fam[keep] else rules.get(i, "same-name")})
    return alias, audit


def spellings_from_rows(rows):
    """rows: DataFrame with county_fips, fac, facility, city, zip -> the spelling records merge_map() reads."""
    z5 = rows["zip"].astype(str).str[:5]; rows = rows.assign(_z=z5.where(z5.str.fullmatch(r"\d{5}"), ""))
    out = []
    for (c, f), g in rows.groupby(["county_fips", "fac"]):
        z = g["_z"][g["_z"] != ""]
        out.append({"county_fips": c, "fac": f, "name": g["facility"].value_counts().index[0], "city": g["city"].value_counts().index[0],
                    "zip": z.value_counts().index[0] if len(z) else "", "n": len(g)})
    return out


def _selftest():
    F = load_families(Path(__file__).parent / "data/ref/site_families.csv")
    S = lambda c, name, z, n=1, city="": {"county_fips": c, "fac": re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", name.lower())).strip(), "name": name, "zip": z, "n": n, "city": city}
    def together(*sp):
        al, _ = merge_map(list(sp), F); k = {al.get((s["county_fips"], s["fac"]), s["fac"]) for s in sp}; return len(k) == 1
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
    ]
    ph = [("Research Site", True), ("GSK Investigational Site", True), ("Exelixis Clinical Site #12", True), ("Site 0173", True), ("USA04-0", True), ("Investigative Site US031", True), ("Zai Lab Site 02002", True),
          ("Clinical Study Site", True), ("Memorial Sloan Kettering Cancer Center", False), ("Palo Alto Medical Foundation Research Center", False), ("Rocky Mountain Cancer Centers (RMCC) ( Site 0123)", False),
          ("Mayo Clinic", False), ("START San Antonio", False), ("Kaiser Permanente - Santa Clara ( Site 0123)", False), ("City of Hope - Duarte Main Site", False), ("VA Long Beach Healthcare System ( Site 0041)", False),
          ("NEO-811 NYC Site", True), ("I-Mab Site 1002", True), ("Avenzo Therapeutics Recruiting Site", True), ("010", True), ("Clinical Study Sites", True), ("CBCC Global Research Site 0010", False),
          ("Site 0221 - Tufts Medical Center - PPDS", False), ("US Oncology Research Investigational Products Center", False)]
    bad = [n for n, got, want in ok if got != want] + [f"placeholder: {n}" for n, want in ph if is_placeholder(n) != want]
    print(f"site_names self-test: {len(ok) + len(ph) - len(bad)}/{len(ok) + len(ph)} pass" + ("" if not bad else " | FAILED: " + "; ".join(bad)))
    return not bad


def main():
    if "--test" in sys.argv: sys.exit(0 if _selftest() else 1)
    import pandas as pd
    norm = lambda x: re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", SITECODE.sub(" ", str(x)).lower())).strip()
    s = pd.read_csv("out_adult55/site_assignment_qc.csv", dtype=str).fillna(""); s = s[s.county_fips != ""].copy(); s["fac"] = s.facility.map(norm)
    sp = spellings_from_rows(s); alias, audit = merge_map(sp, load_families("data/ref/site_families.csv"))
    after = len({(x["county_fips"], alias.get((x["county_fips"], x["fac"]), x["fac"])) for x in sp}); ph = sum(is_placeholder(x["name"]) for x in sp)
    print(f"{len(sp):,} spellings -> {after:,} facilities ({len(alias):,} spellings folded in); {ph:,} of the spellings are sponsor placeholders")
    by = defaultdict(int)
    for a in audit: by[a["rule"].split(":")[0]] += 1
    print("by rule:", dict(by))


if __name__ == "__main__":
    main()
