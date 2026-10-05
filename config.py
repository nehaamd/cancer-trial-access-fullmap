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
VIRTUAL_SITE_PATTERN = r"\btele-?(?:medicine|health)\b|\bvirtual\b|\bdecentrali[sz]ed\b|\bremote (?:site|enrol\w*|participation|study)\b|\bonline study\b"
VIRTUAL_SITES_ARE_LOCATIONS = False

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
# Add an entry (and so bump the version) whenever a change to the pipeline is expected to move the headline shares.
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
]
METHOD_VERSION = METHOD_CHANGES[-1]["version"]
