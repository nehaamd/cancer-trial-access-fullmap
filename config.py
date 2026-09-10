"""
Configuration for the Texas Trial Access Snapshot pipeline.
Edit thresholds, NCI centers, and the city->county fallback here.
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
