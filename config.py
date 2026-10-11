"""
Configuration shared by the pipeline scripts (it began as the Texas Trial Access Snapshot; the national build reuses it).
Thresholds, the registry query, and - at the end - the national NCI-center loader and the register of method changes.
The NCI_CENTERS list below is the Texas build's and is not used by the national scripts (see qc_us.py for the national list).
"""

# ---------------------------------------------------------------------------
# ClinicalTrials.gov API v2
# ---------------------------------------------------------------------------
CTGOV_BASE = "https://clinicaltrials.gov/api/v2/studies"

# Broad oncology condition query (Essie syntax is handled by the API).
CONDITION_QUERY = (
    "cancer OR neoplasm OR neoplasms OR carcinoma OR lymphoma OR leukemia OR "
    "myeloma OR sarcoma OR melanoma OR malignancy OR malignant OR tumor OR tumour OR glioma OR mesothelioma"
)
# The registry matches whole words and the disease terms it has coded for each study. The list above therefore finds every study
# the registry has coded as a neoplasm, but it misses (a) cancers the registry files outside its neoplasm tree - myelodysplastic
# syndromes, myelofibrosis and the other myeloproliferative neoplasms, Langerhans cell histiocytosis - and (b) studies whose
# condition text the registry has not coded at all, when that text uses a compound word ("Pancreatic Ductal Adenocarcinoma",
# "Uterine Leiomyosarcoma", "Glioblastoma", "Liver Metastases", "AML"). A check against every recruiting US treatment study
# (5 Oct 2026) found 107 such cancer trials, among them a 139-site cooperative-group trial in myelodysplastic syndrome.
# The terms below ask for them by name. They also return unrelated studies (the registry treats "secondary" as a synonym of
# "metastasis"); those never reach the data, because qc_us.py keeps a study only if its conditions or title name a cancer.
CONDITION_QUERY += (
    " OR adenocarcinoma OR cholangiocarcinoma OR carcinomatosis OR glioblastoma OR astrocytoma OR oligodendroglioma OR neuroblastoma OR medulloblastoma"
    " OR leiomyosarcoma OR angiosarcoma OR osteosarcoma OR liposarcoma OR rhabdomyosarcoma OR chondrosarcoma"
    " OR myelodysplastic OR myelodysplasia OR myelofibrosis OR myeloproliferative OR \"polycythemia vera\" OR \"essential thrombocythemia\" OR mastocytosis"
    " OR \"Langerhans cell histiocytosis\" OR metastasis OR metastases OR metastatic OR oligometastatic OR oligometastasis OR hepatocellular"
    " OR AML OR MDS OR HCC OR PDAC OR NSCLC OR macroglobulinemia"
)
# Added 11 Oct 2026 after a check against every recruiting US treatment study (registry data of 9 Oct 2026): light-chain (AL) amyloidosis,
# a plasma-cell disorder already counted with myeloma (12 such trials were in the data, one with 12 US sites was not), post-transplant
# lymphoproliferative disorder (a lymphoma) and mantle cell lymphoma written only as "MCL" were not found by the terms above. Each phrase
# adds only those studies; "amyloidosis" or "lymphoproliferative" alone would also return transthyretin amyloidosis and autoimmune
# lymphoproliferative syndrome trials, which are not cancer.
CONDITION_QUERY += ' OR "light chain amyloidosis" OR "AL amyloidosis" OR "post-transplant lymphoproliferative" OR "posttransplant lymphoproliferative" OR PTLD OR MCL'

# Overall study status to include. Add "NOT_YET_RECRUITING" for a sensitivity analysis.
OVERALL_STATUS = ["RECRUITING"]

# Restrict to treatment trials (mirrors the ASCO 2024 county analysis).
PRIMARY_PURPOSE = "TREATMENT"

# Location text filter passed to the API (studies must list at least one site here).
LOCATION_QUERY = "Texas"

# Fields to request (keeps payloads small). Names follow CT.gov "piece" names.
FIELDS = [
    "NCTId", "BriefTitle", "OverallStatus", "StudyType", "Phase",
    "DesignPrimaryPurpose", "Condition", "InterventionType", "InterventionName",
    "InterventionDescription", "LeadSponsorClass", "StartDate",
    "LocationFacility", "LocationCity", "LocationState", "LocationZip",
    "LocationCountry", "LocationStatus",
]

PAGE_SIZE = 1000          # API maximum
REQUEST_SLEEP_SEC = 0.6   # be polite

# ---------------------------------------------------------------------------
# Site-level status to count as "available". Missing status is kept.
# ---------------------------------------------------------------------------
SITE_STATUS_KEEP = {"RECRUITING", None, ""}

# ---------------------------------------------------------------------------
# Registry "sites" that are not places. A fully decentralized study lists the same telemedicine service once per city
# ("Ohio State University-Telemedicine" in 107 cities for NCT06906562); a resident of one of those cities is no closer to the
# trial than anyone else, so such a row is not a location: it is not assigned to a county, not drawn, and not counted as a trial
# "within 60 road-miles". The trial stays in the data (at its physical sites, if it lists any), and the pages show it as a
# group of its own, labelled Telemedicine, for the states it names: panels, trial lists, briefs and the ZIP finder (DATA.T.tele).
# Set VIRTUAL_SITES_ARE_LOCATIONS = True to count these rows as ordinary sites again.
# ---------------------------------------------------------------------------
# Science 37 runs a "virtual clinical metasite" listed at its offices (Morrisville NC, Culver City CA); 4 of its 9 listings among recruiting
# US treatment studies on 9 Oct 2026 did not say "virtual" ("Science 37", "Science 37, Inc.", "Science 37 (at-home option)"), nor did
# "This is an At-Home Study - no travel or on-site visits are needed at all". None is in the cancer data yet.
VIRTUAL_SITE_PATTERN = (r"\btele-?(?:medicine|health)\b|\bvirtual\b|\bdecentrali[sz]ed\b|\bremote (?:site|enrol\w*|participation|study)\b|\bonline study\b"
                        r"|\bscience ?37\b|\bat-?home (?:study|option|trial)\b")
VIRTUAL_SITES_ARE_LOCATIONS = False

# ---------------------------------------------------------------------------
# Names members of Congress go by that data/ref/legislators-current.json does not carry (it has a "nickname" field for some members:
# "Bernie" for Bernard Sanders). Keyed by bioguide id; the value is the full name as searched. build_community.py and
# fetch_cosponsors.py add it as "nick" so the pages' search finds the member by it. Add a member only when the name is verified on the
# member's own house.gov / senate.gov page. B001323: Nicholas J. Begich III, AK-At Large ("Representative Nick Begich", begich.house.gov, 11 Oct 2026).
# ---------------------------------------------------------------------------
NICKNAMES_EXTRA = {"B001323": "Nick Begich"}

# ---------------------------------------------------------------------------
# Distance thresholds (miles). Straight-line distance is inflated by
# ROAD_FACTOR to approximate driving distance. State this in the methods.
# ---------------------------------------------------------------------------
MENU_THRESHOLDS = {"limited": 20, "broad": 100}   # trials at a county to count as a "menu"
DISTANCE_BANDS_MI = [60, 120]                       # 60 = ASCO-style "beyond an hour"; 120 = Mayo cutoff
ROAD_FACTOR = 1.2

# ---------------------------------------------------------------------------
# NCI-designated cancer centers in Texas. Tiers verified 2026-09-04 against cancer.gov and
# institutional announcements (Simmons renewal 2026; Mays renewed as an NCI-designated, non-comprehensive
# Cancer Center). Coordinates are approximate campus locations (MD Anderson cross-checked at 29.7078, -95.3975).
# ---------------------------------------------------------------------------
NCI_CENTERS = [
    {"name": "MD Anderson Cancer Center", "city": "Houston", "county_fips": "48201", "lat": 29.7070, "lon": -95.3970, "tier": "Comprehensive"},
    {"name": "Dan L Duncan Comprehensive Cancer Center (Baylor College of Medicine)", "city": "Houston", "county_fips": "48201", "lat": 29.7105, "lon": -95.3967, "tier": "Comprehensive"},
    {"name": "Harold C. Simmons Comprehensive Cancer Center (UT Southwestern)", "city": "Dallas", "county_fips": "48113", "lat": 32.8129, "lon": -96.8404, "tier": "Comprehensive"},
    {"name": "Mays Cancer Center (UT Health San Antonio)", "city": "San Antonio", "county_fips": "48029", "lat": 29.5080, "lon": -98.5750, "tier": "Cancer Center (non-comprehensive)"},
]

# ---------------------------------------------------------------------------
# Oral-agent heuristic: INN stems typical of oral small-molecule oncology drugs.
# This is a screening flag only; every flagged trial should be manually reviewed.
# ---------------------------------------------------------------------------
ORAL_SUFFIXES = (
    "nib", "lisib", "parib", "ciclib", "degib", "lutamide", "rasib", "lidomide",
    "sertib", "metinib", "rafenib", "zomib", "tinib", "clax", "stat", "tegrast",
)
ORAL_KEYWORDS = ("oral", "tablet", "capsule", "by mouth", "p.o.", "po ")

# ---------------------------------------------------------------------------
# City -> county FIPS fallback for sites with missing/invalid ZIPs (Texas).
# Extend as needed; county FIPS are 5-digit strings.
# ---------------------------------------------------------------------------
CITY_COUNTY_FALLBACK = {
    "houston": "48201", "dallas": "48113", "san antonio": "48029", "austin": "48453",
    "fort worth": "48439", "el paso": "48141", "lubbock": "48303", "amarillo": "48375",
    "temple": "48027", "tyler": "48423", "midland": "48329", "odessa": "48135",
    "san angelo": "48451", "mcallen": "48215", "edinburg": "48215", "harlingen": "48061",
    "brownsville": "48061", "corpus christi": "48355", "waco": "48309", "abilene": "48441",
    "wichita falls": "48485", "laredo": "48479", "beaumont": "48245", "galveston": "48167",
    "sugar land": "48157", "the woodlands": "48339", "plano": "48085", "irving": "48113",
    "arlington": "48439", "round rock": "48491", "college station": "48041", "bryan": "48041",
    "longview": "48183", "texarkana": "48037", "nacogdoches": "48347", "victoria": "48469",
    "denton": "48121", "frisco": "48085", "mckinney": "48085", "lewisville": "48121",
    "webster": "48201", "pearland": "48039", "league city": "48167", "katy": "48201",
    "conroe": "48339", "baytown": "48201", "pasadena": "48201", "kingwood": "48201",
    "bedford": "48439", "grapevine": "48439", "garland": "48113", "mesquite": "48113",
    "richardson": "48113", "carrollton": "48113", "southlake": "48439", "new braunfels": "48091",
    "san marcos": "48209", "killeen": "48027", "sherman": "48181", "paris": "48277",
    "lufkin": "48005", "kerrville": "48265", "georgetown": "48491", "cedar park": "48491",
    "boerne": "48259", "seguin": "48187", "humble": "48201", "cypress": "48201",
    "spring": "48201", "tomball": "48201", "missouri city": "48157", "rosenberg": "48157",
    "friendswood": "48167", "texas city": "48167", "port arthur": "48245", "orange": "48361",
    "lake jackson": "48039", "angleton": "48039", "huntsville": "48471", "livingston": "48373",
    "athens": "48213", "palestine": "48001", "jacksonville": "48073", "marshall": "48203",
    "mount pleasant": "48449", "greenville": "48231", "rockwall": "48397", "waxahachie": "48139",
    "cleburne": "48251", "granbury": "48221", "weatherford": "48367", "stephenville": "48143",
    "brownwood": "48049", "big spring": "48227", "snyder": "48415", "plainview": "48189",
    "levelland": "48219", "hereford": "48117", "pampa": "48179", "borger": "48233",
    "dumas": "48341", "del rio": "48465", "eagle pass": "48323", "uvalde": "48463",
    "alpine": "48043", "fort stockton": "48371", "pecos": "48389", "marfa": "48377",
    "rio grande city": "48427", "weslaco": "48215", "mission": "48215", "pharr": "48215",
    "kingsville": "48273", "alice": "48249", "beeville": "48025", "port lavaca": "48057",
    "bay city": "48321", "el campo": "48481", "wharton": "48481", "sealy": "48015",
    "brenham": "48477", "la grange": "48149", "bastrop": "48021", "lockhart": "48055",
    "fredericksburg": "48171", "burnet": "48053", "marble falls": "48053", "llano": "48299",
    "lampasas": "48281", "gatesville": "48099", "hillsboro": "48217", "corsicana": "48349",
    "ennis": "48139", "terrell": "48257", "kaufman": "48257", "sulphur springs": "48223",
    "denison": "48181", "gainesville": "48097", "decatur": "48497", "mineral wells": "48363",
    "graham": "48503", "vernon": "48487", "childress": "48075", "canyon": "48381",
}


# ---------------------------------------------------------------------------
# National build: NCI-designated centers used as distance targets.
# data/ref/nci_centers.csv is written by qc_us.py (one row per location). A center that does not treat adults
# (adult = 0: St. Jude Children's Research Hospital) stays in that file but is not a place a resident aged 55+
# can be treated, so it is never the "nearest NCI center". Every script that measures distance to an NCI center
# reads the list through this function so they all use the same rows in the same order.
# ---------------------------------------------------------------------------
def nci_targets(path="data/ref/nci_centers.csv"):
    import pandas as pd
    n = pd.read_csv(path)
    if "adult" in n.columns: n = n[n.adult == 1].reset_index(drop=True)
    return n


def nci_summary(path="data/ref/nci_centers.csv"):
    """{"locations": distance targets, "centers": distinct designations among them, "excluded": names not used as targets}."""
    import pandas as pd
    n = pd.read_csv(path); a = n[n.adult == 1] if "adult" in n.columns else n
    return {"locations": int(len(a)), "centers": int(a["center"].nunique()) if "center" in a.columns else None,
            "excluded": sorted(n.loc[n.adult == 0, "name"]) if "adult" in n.columns else []}


# ---------------------------------------------------------------------------
# Method changes that move the published figures (newest last). tract_metrics_us.py stamps METHOD_VERSION into
# national_metrics_v3.json, and every archived pull keeps that file, so the release gate does not mistake a change of
# method for a broken refresh, and the "Recent changes" tab says which rows were calculated differently.
# Add an entry (and so bump the version) whenever a change to the pipeline is expected to move the headline shares, in the
# same commit as the change. An entry registered only after a refresh has already used the new rules also names that pull
# in "first_pull" (the pull's UTC date, as in its fetch_log.json): that pull and every later one count as calculated with the
# new method although their files carry the older stamp (method_of below). Version 4 is such an entry: the rules of
# 10 October 2026 were first used by the pull of 11 October, whose files said version 3 until they were re-stamped.
# An entry registered before its first refresh (version 5) has no "first_pull": the next full run stamps METHOD_VERSION
# on its files, and the "Recent changes" tab shows the entry once a pull carries that stamp. A re-aggregation of an older
# tract table (tract_metrics_us.py --from-tract-access) must keep that table's own version, not METHOD_VERSION.
# ---------------------------------------------------------------------------
METHOD_CHANGES = [
    {"version": 1, "date": "2026-09-09", "note": "First national release."},
    {"version": 2, "date": "2026-10-05", "note": (
        "Road network rebuilt: a node at least every 400 m, highway dead ends linked to the adjoining road, and no link across a county line or coastal water. "
        "This corrected in-town trips that had been routed the long way round (for example parts of Tucson, Kalispell, Spokane, Pueblo and Duluth). "
        "Sites in ZIP codes that span counties are now assigned to the county where most of the ZIP's residents live, "
        "and sites in ZIP codes larger than 100 square miles are placed at their city rather than at the centroid of the ZIP (which was 15 miles outside Billings and Great Falls). "
        "NCI centers are located at their hospital's ZIP code rather than the city center, and St. Jude Children's Research Hospital, which treats children, is no longer a distance target. "
        "On the same registry data (Sep 30, 2026) the national figures moved as follows: fewer than 20 trials within 60 miles 12.7% to 11.8%; none within 60 miles 4.4% to 3.8%; "
        "beyond 60 miles of a broad menu 38.8% to 38.1%; beyond 60 miles of an NCI center 44.2% to 43.7%; median distance to an NCI center 50 to 48 miles.")},
    {"version": 3, "date": "2026-10-05", "note": (
        "Which registry rows count as a place, and which studies count as cancer trials. "
        "A row that names a telemedicine or virtual service instead of a clinic is no longer a site: one fully decentralized study listed such a row in 107 cities, "
        "and it had been the only trial within 60 road-miles for about 346,000 residents 55+. "
        "Rows whose ZIP code is a typing error (the same named hospital is listed repeatedly in the stated city and never near that ZIP) are located where the registry's other rows list that hospital. "
        "The registry search now also asks by name for cancers it files outside its neoplasm category or has not coded "
        "(myelodysplastic syndromes, myelofibrosis, adenocarcinomas, glioblastoma, metastases: 107 more trials on Oct 5, 2026), "
        "and studies kept only for wording such as 'tumor necrosis factor' or 'non-malignant' are dropped (8 studies). "
        "On the same registry data (Sep 30, 2026) the telemedicine, ZIP and screening rules moved the national figures as follows: "
        "none within 60 miles 3.8% to 4.2%; fewer than 20 trials within 60 miles 11.8% to 12.0%; counties with any trial 848 to 833; "
        "distances to broad menus and NCI centers did not move. The wider search then added trials without moving these shares.")},
    {"version": 4, "date": "2026-10-10", "first_pull": "2026-10-11", "note": (
        "Where a registry row is counted and drawn. A row whose ZIP code has no Census area (a PO box or a hospital's own ZIP) took the county of the ZIP's first three digits "
        "even when its own city lay in another county, and was drawn at that county's center: 58 rows sat 43 to 251 miles from their city "
        "(31 Tawas City, Michigan rows in Tuscola County; Liberal, Kansas in Morton County; Pueblo in Conejos County, Colorado; Omaha in Lincoln County, Nebraska; Dallas in Cass County, Texas). "
        "The row's own city now decides the county and the row is drawn there; one spelling rule for city names (Saint/St., Fort/Ft., Lexington-Fayette, Nashville-Davidson) puts 21 more rows at their city. "
        "A trial for spread from a named cancer (to the brain, liver or peritoneum) is classified with that cancer (6 trials), and leptomeningeal disease counts as cancer "
        "(NCT07814352, which was in the Oct 5 pull but appears among the trials newly listed between Oct 5 and Oct 9). "
        "First used for the registry data of Oct 9, 2026 (pulled Oct 11). On the same registry data (Oct 5, 2026) these rules moved 194 site rows of 100 trials to another county "
        "and changed the trial count of 69 counties (Tuscola, Michigan 31 to 2; Iosco 0 to 31; Midland 1 to 12; Washtenaw 233 to 240; Stanly, North Carolina 2 to 9; "
        "Union, New Jersey 29 to 36; Pueblo, Colorado and Hudson, New Jersey 19 to 20); counties with any trial 838 to 833; "
        "none within 60 road-miles 4.2% to 4.3% (76,538 more residents 55+: 92 census tracts around Texarkana, North Platte, the San Luis Valley, northeast Alabama "
        "and the Oklahoma Panhandle lost a trial that existed only at a misplaced point, and 17 tracts gained one); fewer than 20 trials within 60 road-miles 12.0%, unchanged; "
        "distances to broad menus and NCI centers did not move. The registry's own changes between Oct 5 and Oct 9 moved no one across 'none within 60 road-miles' "
        "and added 57,428 residents 55+ to 'fewer than 20' (still 12.0%).")},
    {"version": 5, "date": "2026-10-11", "note": (
        "Where a site is drawn, which rows are cancer trials, and how trials are classified by cancer type; first applied at the refresh after Oct 11, 2026. "
        "Site placement: San Francisco's Census city point lies in the Pacific near the Farallon Islands, so the 103 UCSF rows that name the city without a usable ZIP "
        "(ZIP 94143; 102 trials) were drawn 50 road-miles from the city. City points now come from one table used both to assign a row to a county and to draw it: "
        "a point in no county's land takes the nearest county (23 coastal places), and a point more than a mile out to sea moves to where the county's residents 55+ live. "
        "A row whose registry state is wrong follows its ZIP when the stated city is a place of the ZIP's state at that ZIP, or other trials list the same facility there "
        "(19 rows: Mayo Clinic 'Rochester, New York, 55905' was in Monroe County, New York; Luminis 'Annapolis, Missouri' in Iron County; Gabrail 'Canton, Oklahoma' in Blaine County; "
        "Mary Crowley 'Dallas, Pennsylvania' in Luzerne County; Sibley Memorial, filed under Baltimore, is in the District of Columbia). "
        "A ZIP 25 or more miles from the stated city is a typing error when exactly one swap of two adjacent digits gives a ZIP inside that city (11 rows). "
        "New York and its boroughs map to their own counties; a city name that occurs twice in a state resolves to the largest place within 40 miles of the ZIP; "
        "a row with no usable ZIP follows the registry's other listings of the same facility in the same city (the Anschutz campus in Aurora, Colorado to Adams County; "
        "Dana-Farber to Suffolk County; Emory 30302 to DeKalb County). "
        "On the registry data of Oct 9, 2026 these placement rules move 138 rows and place 9 that had no county: counties with any trial 832 to 825 "
        "(Ashtabula, Ohio; Gage, Nebraska; Halifax, North Carolina; Skamania, Washington; Stewart, Tennessee; Iron, Missouri; Grimes, Texas and Blaine, Oklahoma lose a trial that is not there; "
        "Madison, Indiana gains its first); 380 limited and 82 broad menus unchanged; none within 60 road-miles 4.3% to 4.4% (4.293% to 4.375%: 80,988 more residents 55+ in 84 census tracts, "
        "each of whose only trial was a misplaced site; Oklahoma 12.5% to 15.2%, Nebraska 18.0% to 19.7%, Kentucky 1.6% to 2.2%, Tennessee 5.9% to 6.4%, Missouri 5.8% to 6.2%, "
        "Kansas 4.0% to 4.3%, North Carolina 1.0% to 1.2%, Texas 5.6% to 5.7%); fewer than 20 trials within 60 road-miles 12.0%, unchanged; "
        "Bay Area tracts gain up to 98 trials within 60 road-miles (a San Mateo County tract 338 to 417) without any share moving. "
        "Registry screen: non-muscle-invasive and muscle-invasive bladder cancer written as NMIBC/MIBC, mantle cell lymphoma written as MCL (but not the knee's MCL) and hemangioendothelioma "
        "count as cancer, and the registry search asks by name for light-chain (AL) amyloidosis, post-transplant lymphoproliferative disorder and mantle cell lymphoma: "
        "6 more trials on the same data (4,007 to 4,013; 27 site rows in 22 counties that each already have 65 to 1,052 trials, so no county crosses 1, 20 or 100 trials and no share moves). "
        "Science 37's virtual sites and 'at-home study' rows count as telemedicine (8 rows, none in the cancer data on Oct 9). "
        "Classifier: 36 trials change cancer type (29 their primary type): chronic myelomonocytic leukemia strings came out empty, so a CMML trial (NCT07033598) showed as Other / unclassified; "
        "myeloid sarcoma and histiocytic sarcomas are blood cancers, not Sarcoma; 'metastatic ... in the lung' and 'brain tumor - metastatic' no longer tag Lung or Brain; "
        "renal medullary carcinoma, sinonasal cancers, ETMR, ATRT, pineoblastoma, familial adenomatous polyposis, anal HSIL, misspelt 'hepatocellular' and HER2-expressing baskets are recognised. "
        "Other / unclassified 38 to 23 trials; the multi-cancer share 27.9% to 28.1%. No county's trial count and no access share moves from the screen or the classifier.")},
]
METHOD_VERSION = METHOD_CHANGES[-1]["version"]


def method_of(stamp, pull_date):
    """The method version a pull was calculated with: the version stamped in its national_metrics_v3.json, or the newest
    METHOD_CHANGES entry whose first_pull is on or before the pull's date (YYYY-MM-DD...), whichever is later."""
    late = [m["version"] for m in METHOD_CHANGES if m.get("first_pull") and str(pull_date)[:10] >= m["first_pull"]]
    return max([int(stamp or 1)] + late)
