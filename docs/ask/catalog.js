/* Ask the map v3 — the data catalog.
   One dictionary shared by the engine (field validation, defaults), the worker (the model's system prompt and tool schemas) and
   the client (labels, map parameters). Nothing here reads data; it describes it. Field paths are dotted paths into the rows the
   engine builds from docs/api/*.json plus the map's own data files (see ASK_CONTRACT.md §4). Keep descriptions short, exact and
   in the site's own words: the model reads them verbatim. */

export const SITE_BASE = 'https://cancertrialaccess.org/';
export const API_BASE = SITE_BASE + 'api/';

// ---------- vintages and sources (filled with dates by the engine from the loaded files where available) ----------
export const SOURCES = {
  registry: { label: 'ClinicalTrials.gov registry (recruiting, interventional, treatment, oncology, US site)', vintage_key: 'data_as_of', note: 'Trials are counted, not matched to any person; "recruiting" in the registry can lag reality by months.' },
  acs: { label: 'Census Bureau ACS 5-year (2020–2024), by census tract', vintage: '2020-2024' },
  roads: { label: 'TIGER/Line 2025 primary and secondary roads; road-miles from the tract point or the county population center', vintage: '2025' },
  nci: { label: 'NCI-designated cancer centers (65 centers that treat adults, at 67 locations; St. Jude excluded)', vintage: '2026-10' },
  incidence: { label: 'State Cancer Profiles incidence, age-adjusted per 100,000, all ages', vintage: '2019-2023' },
  mortality: { label: 'State Cancer Profiles death rates, age-adjusted per 100,000, all ages', vintage: '2020-2024' },
  rucc: { label: 'USDA ERS Rural-Urban Continuum Codes, 2023 release (2013 for Connecticut legacy counties)', vintage: '2023' },
  oncologists: { label: 'CMS Doctors and Clinicians (Care Compare): primary specialty medical oncology, hematology/oncology or hematology, at every Medicare practice location; pediatric excluded', vintage: '2026-10-02' },
  congress: { label: 'congress.gov / govinfo bill status (119th Congress) and congress-legislators', vintage: '2026-11-03' },
  districts: { label: '119th Congress district plan (2024 election maps); tracts apportioned by residents 55+', vintage: '119th Congress' },
};

export const FILES = {
  counties: { file: 'api/all_counties.json', per_place: 'api/county/{FIPS}.json' },
  districts: { file: 'api/all_districts.json', per_place: 'api/district/{USPS}-{NN}.json' },
  states: { file: 'api/all_states.json', per_place: 'api/state/{USPS}.json' },
  national: { file: 'api/national.json' },
  nci_centers: { file: 'data.js (DATA.nci)' },
  facilities: { file: 'data.js (DATA.counties[*].fac)' },
  senators: { file: 'api/all_states.json (senators) + cosponsors.js' },
  cosponsors: { file: 'cosponsors.js (COSPONSORS.by_member)' },
  trials: { file: 'data.js (DATA.T)' },
};

// ---------- enumerations ----------
export const STATES = { AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California', CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont', VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming' };
export const TERRITORIES = { PR: 'Puerto Rico', GU: 'Guam', VI: 'the U.S. Virgin Islands', AS: 'American Samoa', MP: 'the Northern Mariana Islands' };
export const DEMONYMS = { texan: 'TX', texans: 'TX', ohioan: 'OH', ohioans: 'OH', californian: 'CA', californians: 'CA', floridian: 'FL', floridians: 'FL', 'new yorker': 'NY', 'new yorkers': 'NY', georgian: 'GA', virginian: 'VA', kentuckian: 'KY', hoosier: 'IN', hoosiers: 'IN', michigander: 'MI', pennsylvanian: 'PA', illinoisan: 'IL', alabamian: 'AL', alaskan: 'AK', arizonan: 'AZ', arkansan: 'AR', coloradan: 'CO', 'north carolinian': 'NC', 'south carolinian': 'SC', tennessean: 'TN', oklahoman: 'OK', louisianan: 'LA', louisianian: 'LA', mississippian: 'MS', missourian: 'MO', montanan: 'MT', nebraskan: 'NE', nevadan: 'NV', 'new mexican': 'NM', 'new jerseyan': 'NJ', oregonian: 'OR', utahn: 'UT', vermonter: 'VT', washingtonian: 'WA', 'west virginian': 'WV', wisconsinite: 'WI', wyomingite: 'WY', iowan: 'IA', kansan: 'KS', marylander: 'MD', minnesotan: 'MN', 'north dakotan': 'ND', 'south dakotan': 'SD', idahoan: 'ID', hawaiian: 'HI', mainer: 'ME', 'rhode islander': 'RI', delawarean: 'DE', connecticuter: 'CT', 'new hampshirite': 'NH' };

// trial cancer types (the finder's categories and the by-type access fields); key -> label
export const CANCER_TYPES = { bladder_urothelial: 'bladder & urothelial', brain_cns: 'brain & CNS', breast: 'breast', colorectal: 'colorectal', gastric_esophageal: 'gastric & esophageal', gynecologic: 'gynecologic (ovary, uterus, cervix)', head_neck: 'head & neck', kidney: 'kidney', leukemia: 'leukemia', liver_biliary: 'liver & biliary', lung: 'lung & thoracic', lymphoma: 'lymphoma', mds_mpn: 'MDS / MPN', melanoma_skin: 'melanoma & skin', myeloma: 'myeloma', neuroendocrine_endocrine: 'neuroendocrine & endocrine', other_named: 'other named cancers', pancreatic: 'pancreatic', prostate: 'prostate', sarcoma: 'sarcoma', multi: 'multiple or unspecified cancers (basket / solid-tumour trials)', other_unclassified: 'unclassified' };
export const TYPE_KEYS_BY_TYPE_ACCESS = Object.keys(CANCER_TYPES).filter(k => k !== 'multi' && k !== 'other_unclassified');   // the 20 keys of trials_within_60rdmi_by_cancer_type and zero_trial_share_by_type

// incidence / death-rate sites (State Cancer Profiles); key -> label. 'all' is all cancer sites.
export const SITES = { all: 'all cancer sites', breast: 'breast', colorectal: 'colon & rectum', lung: 'lung & bronchus', prostate: 'prostate', melanoma_skin: 'melanoma of the skin', lymphoma: 'non-Hodgkin lymphoma', leukemia: 'leukemia', pancreatic: 'pancreas', liver_biliary: 'liver & bile duct', bladder_urothelial: 'bladder', kidney: 'kidney & renal pelvis', brain_cns: 'brain & other nervous system', gynecologic_ovary: 'ovary', gynecologic_uterus: 'uterus (corpus and NOS)', gynecologic_cervix: 'cervix', head_neck: 'oral cavity & pharynx', thyroid: 'thyroid', esophagus: 'esophagus', stomach: 'stomach' };
export const SITE_KEYS = Object.keys(SITES).filter(k => k !== 'all');

// words people use -> {type (trial category key), site (incidence/mortality key or null)}; longer phrases first
export const CANCER_WORDS = [
  ['non small cell lung', 'lung', 'lung'], ['small cell lung', 'lung', 'lung'], ['nsclc', 'lung', 'lung'], ['sclc', 'lung', 'lung'], ['lung', 'lung', 'lung'], ['thoracic', 'lung', 'lung'], ['mesothelioma', 'lung', 'lung'],
  ['colorectal', 'colorectal', 'colorectal'], ['colon', 'colorectal', 'colorectal'], ['rectal', 'colorectal', 'colorectal'], ['rectum', 'colorectal', 'colorectal'], ['bowel', 'colorectal', 'colorectal'], ['crc', 'colorectal', 'colorectal'],
  ['breast', 'breast', 'breast'], ['prostate', 'prostate', 'prostate'],
  ['melanoma', 'melanoma_skin', 'melanoma_skin'], ['skin', 'melanoma_skin', 'melanoma_skin'],
  ['non hodgkin', 'lymphoma', 'lymphoma'], ['hodgkin', 'lymphoma', 'lymphoma'], ['lymphoma', 'lymphoma', 'lymphoma'], ['nhl', 'lymphoma', 'lymphoma'],
  ['leukemia', 'leukemia', 'leukemia'], ['leukaemia', 'leukemia', 'leukemia'], ['aml', 'leukemia', 'leukemia'], ['cll', 'leukemia', 'leukemia'], ['cml', 'leukemia', 'leukemia'], ['acute lymphoblastic', 'leukemia', 'leukemia'], ['acute myeloid', 'leukemia', 'leukemia'],
  ['pancreatic', 'pancreatic', 'pancreatic'], ['pancreas', 'pancreatic', 'pancreatic'],
  ['hepatocellular', 'liver_biliary', 'liver_biliary'], ['hcc', 'liver_biliary', 'liver_biliary'], ['cholangiocarcinoma', 'liver_biliary', 'liver_biliary'], ['bile duct', 'liver_biliary', 'liver_biliary'], ['biliary', 'liver_biliary', 'liver_biliary'], ['liver', 'liver_biliary', 'liver_biliary'],
  ['bladder', 'bladder_urothelial', 'bladder_urothelial'], ['urothelial', 'bladder_urothelial', 'bladder_urothelial'],
  ['kidney', 'kidney', 'kidney'], ['renal', 'kidney', 'kidney'], ['rcc', 'kidney', 'kidney'],
  ['glioblastoma', 'brain_cns', 'brain_cns'], ['glioma', 'brain_cns', 'brain_cns'], ['gbm', 'brain_cns', 'brain_cns'], ['brain', 'brain_cns', 'brain_cns'], ['cns', 'brain_cns', 'brain_cns'],
  ['ovarian', 'gynecologic', 'gynecologic_ovary'], ['ovary', 'gynecologic', 'gynecologic_ovary'], ['uterine', 'gynecologic', 'gynecologic_uterus'], ['uterus', 'gynecologic', 'gynecologic_uterus'], ['endometrial', 'gynecologic', 'gynecologic_uterus'], ['cervical', 'gynecologic', 'gynecologic_cervix'], ['cervix', 'gynecologic', 'gynecologic_cervix'], ['gynecologic', 'gynecologic', null], ['gynecological', 'gynecologic', null], ['gyn', 'gynecologic', null],
  ['head and neck', 'head_neck', 'head_neck'], ['head & neck', 'head_neck', 'head_neck'], ['oral cavity', 'head_neck', 'head_neck'], ['oral', 'head_neck', 'head_neck'], ['pharynx', 'head_neck', 'head_neck'], ['larynx', 'head_neck', 'head_neck'], ['laryngeal', 'head_neck', 'head_neck'], ['throat', 'head_neck', 'head_neck'], ['mouth', 'head_neck', 'head_neck'],
  ['thyroid', 'neuroendocrine_endocrine', 'thyroid'], ['neuroendocrine', 'neuroendocrine_endocrine', null], ['carcinoid', 'neuroendocrine_endocrine', null], ['adrenal', 'neuroendocrine_endocrine', null],
  ['esophageal', 'gastric_esophageal', 'esophagus'], ['esophagus', 'gastric_esophageal', 'esophagus'], ['oesophageal', 'gastric_esophageal', 'esophagus'], ['gastric', 'gastric_esophageal', 'stomach'], ['stomach', 'gastric_esophageal', 'stomach'], ['gastroesophageal', 'gastric_esophageal', 'esophagus'],
  ['multiple myeloma', 'myeloma', null], ['myeloma', 'myeloma', null],
  ['myelodysplastic', 'mds_mpn', null], ['mds', 'mds_mpn', null], ['mpn', 'mds_mpn', null], ['myelofibrosis', 'mds_mpn', null], ['polycythemia', 'mds_mpn', null], ['myeloproliferative', 'mds_mpn', null],
  ['sarcoma', 'sarcoma', null], ['gist', 'sarcoma', null],
];

export const RUCC_LABELS = { 1: 'Metro: counties in metro areas of 1 million population or more', 2: 'Metro: counties in metro areas of 250,000 to 1 million population', 3: 'Metro: counties in metro areas of fewer than 250,000 population', 4: 'Nonmetro: urban population of 20,000 or more, adjacent to a metro area', 5: 'Nonmetro: urban population of 20,000 or more, not adjacent to a metro area', 6: 'Nonmetro: urban population of 5,000 to 19,999, adjacent to a metro area', 7: 'Nonmetro: urban population of 5,000 to 19,999, not adjacent to a metro area', 8: 'Nonmetro: urban population of fewer than 5,000, adjacent to a metro area', 9: 'Nonmetro: urban population of fewer than 5,000, not adjacent to a metro area' };
export const ONC_CLASSES = { 1: 'Oncologists and trials', 2: 'Oncologists, no trials', 3: 'Trials, no oncologist listed', 4: 'Neither' };
export const COSPONSOR_ROLES = { sponsor: 'introduced the bill', original: 'original cosponsor (signed on the day it was introduced)', cosponsor: 'cosponsor (signed later)', none: 'not a cosponsor' };
export const BILLS = { ctma_hr: { label: 'H.R. 3521', chamber: 'House', title: 'Clinical Trial Modernization Act', url: 'https://www.congress.gov/bill/119th-congress/house-bill/3521' }, ctma_s: { label: 'S. 4440', chamber: 'Senate', title: 'Clinical Trial Modernization Act', url: 'https://www.congress.gov/bill/119th-congress/senate-bill/4440' } };
export const ACS_KEYS = { veh: 'no_vehicle', bb: 'broadband', unins: 'uninsured', unins55: 'uninsured_55_64', pov: 'poverty' };
export const PHASES = ['1', '1-2', '2', '2-3', '3', '4', 'NA'];
export const SPONSOR_TYPES = { industry: 'industry', academic_other: 'academic, hospital or other', nih_federal: 'NIH or other federal' };

// ---------- field definitions ----------
// f(path, type, unit, desc, extra) -> a field entry. type: number | integer | string | boolean | array | object. unit: '%', 'people', 'road-miles', 'hours', 'trials', 'sites', 'oncologists', 'per 100,000', 'cases per year', 'deaths per year', 'code', ''.
const f = (path, type, unit, desc, x = {}) => ({ path, type, unit, desc, ...x });
const P55 = 'residents 55+';
const PCT = (what) => f(what.path, 'number', '%', what.desc, { nulls: what.nulls || 'not computable', layer: what.layer, source: what.source || 'registry' });

// the access fields every geographic level shares (county, district, state, national)
const CORE_ACCESS = (lv) => [
  f('pop55', 'integer', 'people', 'Residents aged 55 and older (ACS 5-year, summed from census tracts).', { source: 'acs' }),
  PCT({ path: 'pct_lt20_trials_within_60rdmi', desc: 'Share of residents 55+ with fewer than 20 recruiting cancer treatment trials within 60 road-miles of home. The site\'s headline "short of trials" / "least access" measure; higher = worse access.', layer: { county: 'short', district: 'l20', state: 'l20' } }),
  f('people_lt20_trials_within_60rdmi', 'integer', 'people', 'The same as a count of people (pop55 × share, rounded).', { layer: { county: 'short', district: 'l20', state: 'l20' } }),
  PCT({ path: 'pct_zero_trials_within_60rdmi', desc: 'Share of residents 55+ with no recruiting trial at all within 60 road-miles.', layer: { district: 'z60', state: 'z60' } }),
  f('people_zero_trials_within_60rdmi', 'integer', 'people', 'The same as a count of people.', { layer: { district: 'z60', state: 'z60' } }),
  PCT({ path: 'pct_lt100_trials_within_60rdmi', desc: 'Share of residents 55+ with fewer than 100 trials within 60 road-miles.' }),
  PCT({ path: 'pct_gt60rdmi_broad_menu', desc: 'Share of residents 55+ living more than 60 road-miles from a county with 100 or more recruiting trials (a "broad menu").', layer: { county: 'rb', district: 'g60b', state: 'g60b' } }),
  PCT({ path: 'pct_gt60rdmi_nci', desc: 'Share of residents 55+ living more than 60 road-miles from an NCI-designated cancer center.', layer: { county: 'rn', district: 'g60n', state: 'g60n' } }),
  f('median_road_mi_nci', 'integer', 'road-miles', 'Median road-miles from home to the nearest NCI-designated center, over residents 55+ who have a road route.', { nulls: 'no road route (islands, remote Alaska)', layer: { county: 'rn', district: 'medn', state: 'medn' }, source: 'roads' }),
  f('median_road_mi_broad_menu', 'integer', 'road-miles', 'Median road-miles from home to the nearest county with 100+ recruiting trials.', { nulls: 'no road route', layer: { county: 'rb', district: 'g60b', state: 'g60b' }, source: 'roads' }),
  f('wmean_trials_within_60rdmi', 'integer', 'trials', 'Population-weighted mean number of recruiting trials within 60 road-miles of home (residents 55+).', { layer: { county: 'short', district: 'l20', state: 'l20' } }),
  f('trials_listed_here', 'integer', 'trials', lv === 'county' ? 'Recruiting cancer treatment trials with at least one site in the county (distinct trials).' : 'Distinct recruiting trials with a site in any county of the ' + lv + (lv === 'district' ? ' (counties that overlap it; a trial in a county shared by two districts counts for both)' : '') + '.', lv === 'county' ? { layer: { county: 't' } } : {}),
  f('nearest_nci', 'string', '', 'Name of the NCI-designated center nearest to most residents (by road).', { layer: { county: 'rn', district: 'medn', state: 'medn' }, source: 'nci' }),
  f('nearest_broad_menu', 'string', '', 'The broad-menu county nearest to most residents, as "County, State" (no "County" suffix).', { layer: { county: 'rb' } }),
  f('context.no_vehicle', 'number', '%', 'Households with no vehicle (ACS, all ages, population-weighted).', { source: 'acs', layer: { county: 'acs', district: 'gacs', state: 'gacs' }, params: { acs: 'veh' } }),
  f('context.broadband', 'number', '%', 'Households with a broadband subscription (ACS). Lower = worse.', { source: 'acs', layer: { county: 'acs', district: 'gacs', state: 'gacs' }, params: { acs: 'bb' } }),
  f('context.uninsured', 'number', '%', 'Uninsured, all ages (ACS).', { source: 'acs', layer: { county: 'acs', district: 'gacs', state: 'gacs' }, params: { acs: 'unins' } }),
  f('context.uninsured_55_64', 'number', '%', 'Uninsured, ages 55–64 (ACS).', { source: 'acs', layer: { county: 'acs', district: 'gacs', state: 'gacs' }, params: { acs: 'unins55' } }),
  f('context.poverty', 'number', '%', 'Poverty rate, all ages (ACS).', { source: 'acs', layer: { county: 'acs', district: 'gacs', state: 'gacs' }, params: { acs: 'pov' } }),
];
const BY_TYPE = f('trials_within_60rdmi_by_cancer_type.<type>', 'integer', 'trials', 'Population-weighted mean recruiting trials of that cancer type within 60 road-miles of home. <type> is one of the 20 type keys (see CANCER_TYPES; multi and other_unclassified are not published).', { keys: TYPE_KEYS_BY_TYPE_ACCESS, layer: { district: 'l20', state: 'l20' }, params_from_key: 'type' });
const METRO_SPLIT = (which) => [
  f(`${which}.pop55`, 'integer', 'people', `Residents 55+ living in ${which} counties (RUCC ${which === 'metro' ? '1–3' : '4–9'}).`, { source: 'rucc' }),
  f(`${which}.counties`, 'integer', '', `Number of ${which} counties.`, { source: 'rucc' }),
  f(`${which}.pct_lt20`, 'number', '%', `Share of ${which} residents 55+ with fewer than 20 trials within 60 road-miles.`, { layer: { state: 'l20' }, params: { rural: '1' } }),
  f(`${which}.people_lt20`, 'integer', 'people', `${which} residents 55+ with fewer than 20 trials within 60 road-miles.`),
  f(`${which}.pct_zero`, 'number', '%', `Share of ${which} residents 55+ with no trial within 60 road-miles.`, { layer: { state: 'z60' }, params: { rural: '1' } }),
  f(`${which}.people_zero`, 'integer', 'people', `${which} residents 55+ with no trial within 60 road-miles.`),
  f(`${which}.pct_lt100`, 'number', '%', `Share of ${which} residents 55+ with fewer than 100 trials within 60 road-miles.`),
  f(`${which}.mean_trials_60`, 'integer', 'trials', `Population-weighted mean trials within 60 road-miles, ${which} residents 55+.`),
  f(`${which}.pct_gt60rdmi_nci`, 'number', '%', `Share of ${which} residents 55+ more than 60 road-miles from an NCI-designated center.`),
  f(`${which}.pct_gt60rdmi_broad_menu`, 'number', '%', `Share of ${which} residents 55+ more than 60 road-miles from a broad menu.`),
  f(`${which}.median_road_mi_nci`, 'integer', 'road-miles', `Median road-miles to the nearest NCI-designated center, ${which} residents 55+.`, { nulls: 'no road route' }),
  f(`${which}.median_road_mi_broad_menu`, 'integer', 'road-miles', `Median road-miles to the nearest broad-menu county, ${which} residents 55+.`, { nulls: 'no road route' }),
];
const RUCC_MEASURES = ['pop55', 'counties', 'pct_lt20', 'pct_zero', 'pct_lt100', 'mean_trials_60', 'pct_gt60rdmi_nci', 'pct_gt60rdmi_broad_menu', 'median_road_mi_nci', 'median_road_mi_broad_menu'];
const BY_RUCC = f('by_rucc.<code>.<measure>', 'number', '', 'Access figures for residents 55+ of counties with that RUCC code (1–9); <measure> is one of pop55, counties, pct_lt20, pct_zero, pct_lt100, mean_trials_60, pct_gt60rdmi_nci, pct_gt60rdmi_broad_menu, median_road_mi_nci, median_road_mi_broad_menu. Null when the state has no county with that code.', { optional: true, source: 'rucc', keys: ['1', '2', '3', '4', '5', '6', '7', '8', '9'], keys2: RUCC_MEASURES });
const ONC_SUMMARY = (lv) => [
  f('oncologists.count', 'integer', 'oncologists', `Oncologists with a Medicare practice location in the ${lv === 'national' ? 'country' : lv}${lv === 'district' ? ' (in counties overlapping it)' : ''}; an oncologist with locations in two counties is counted in both.`, { source: 'oncologists' }),
  f('oncologists.pct_pop55_in_counties_with_oncologists_no_trials', 'number', '%', 'Share of residents 55+ living in counties that have oncologists but no recruiting trial (county class 2).', { source: 'oncologists' }),
  f('oncologists.pct_pop55_in_counties_with_both', 'number', '%', 'Share of residents 55+ in counties with oncologists and trials (class 1).', { source: 'oncologists' }),
  f('oncologists.pct_pop55_in_counties_with_trials_no_oncologist', 'number', '%', 'Share of residents 55+ in counties with trials but no oncologist listed (class 3).', { source: 'oncologists' }),
  f('oncologists.pct_pop55_in_counties_with_neither', 'number', '%', 'Share of residents 55+ in counties with neither (class 4).', { source: 'oncologists' }),
  f('oncologists.counties_with_oncologists_no_trials', lv === 'district' ? 'array' : 'integer', '', lv === 'district' ? 'FIPS codes of the overlapping counties that have oncologists but no recruiting trial.' : 'Number of counties with oncologists but no recruiting trial.', { source: 'oncologists' }),
];

export const TABLES = {
  counties: {
    label: 'counties', noun: 'county', id_desc: '5-digit county FIPS code (string, e.g. "48215")', name_desc: '"Hidalgo County, Texas" (parishes, boroughs, census areas and independent cities keep their own suffix)',
    desc: 'One row per US county or equivalent (3,143). Every county field exists for every county unless its "nulls" note says otherwise.',
    fields: [
      f('id', 'string', '', '5-digit FIPS code.'), f('name', 'string', '', 'County name with state, e.g. "Hidalgo County, Texas".'), f('state', 'string', '', 'USPS state code.', { enum: Object.keys(STATES), groupable: true }),
      ...CORE_ACCESS('county'),
      f('facilities', 'integer', 'sites', 'Trial sites (distinct facility names) in the county with a recruiting trial.', { layer: { county: 't' } }),
      f('districts', 'array', '', 'Ids of the congressional districts that overlap the county (e.g. ["TX-15","TX-34"]). Most counties sit in one district; large counties in several.', { source: 'districts' }),
      f('rucc', 'integer', 'code', 'USDA Rural-Urban Continuum Code 1 (large metro) … 9 (most rural). 1–3 metro, 4–9 nonmetro.', { enum: [1, 2, 3, 4, 5, 6, 7, 8, 9], groupable: true, source: 'rucc', layer: { county: 'short' }, params: { rural: '1' } }),
      f('rucc_label', 'string', '', 'Short label for the code in the map\'s wording ("Metro, 1 million or more" … "Nonmetro, urban population under 5,000, not adjacent").', { source: 'rucc' }),
      f('metro', 'boolean', '', 'true = metro county (RUCC 1–3); false = nonmetro / rural (RUCC 4–9).', { groupable: true, source: 'rucc', layer: { county: 'short' }, params: { rural: '1' } }),
      f('road_mi_nci_from_center', 'integer', 'road-miles', 'Road-miles from the county population center to the nearest NCI-designated center (the map\'s "road-miles to an NCI center" county layer).', { nulls: 'no road route', layer: { county: 'rn' }, source: 'roads' }),
      f('road_mi_broad_menu_from_center', 'integer', 'road-miles', 'Road-miles from the population center to the nearest county with 100+ recruiting trials; 0 when the county itself has a broad menu.', { nulls: 'no road route', layer: { county: 'rb' }, source: 'roads' }),
      f('road_mi_limited_menu_from_center', 'integer', 'road-miles', 'Road-miles from the population center to the nearest county with 20+ recruiting trials; 0 when the county itself has one.', { nulls: 'no road route', layer: { county: 'rb' }, source: 'roads' }),
      f('no_road_route_reason', 'string', '', 'null when road distances exist; "island" = no road connection to any center; "off" = population center more than 30 miles from a primary/secondary road.', { enum: [null, 'island', 'off'], groupable: true, source: 'roads' }),
      f('drive_hours_nci', 'number', 'hours', 'Driving time from the county population center to the nearest NCI-designated center (one decimal).', { nulls: 'no road route', layer: { county: 'rn' }, source: 'roads' }),
      f('drive_hours_broad_menu', 'number', 'hours', 'Driving time from the population center to the nearest broad-menu county.', { nulls: 'no road route', layer: { county: 'rb' }, source: 'roads' }),
      f('trials_within_60rdmi_of_center', 'integer', 'trials', 'Recruiting trials with a site within 60 road-miles of the county population center (the county card\'s "trials within 60 road-miles"; the resident-weighted figure is wmean_trials_within_60rdmi).', { layer: { county: 'short' } }),
      f('facilities_within_60rdmi_of_center', 'integer', 'sites', 'Trial sites within 60 road-miles of the county population center.'),
      f('incidence.all', 'number', 'per 100,000', 'All-sites cancer incidence rate, age-adjusted, all ages, 2019–2023 (State Cancer Profiles).', { nulls: 'suppressed by the source or not available (see incidence.status)', source: 'incidence', layer: { county: 'inc' } }),
      f('incidence.cases_per_year', 'integer', 'cases per year', 'Average annual new cancer cases, all sites.', { nulls: 'not published', source: 'incidence', layer: { county: 'inc' } }),
      f('incidence.small_numbers', 'boolean', '', 'true when fewer than 16 cases a year: the rate is published but should be read with caution.', { source: 'incidence' }),
      f('incidence.status', 'string', '', 'ok, suppressed, or "no data".', { enum: ['ok', 'suppressed', 'no data'], groupable: true, source: 'incidence' }),
      f('incidence.by_site.<site>', 'number', 'per 100,000', 'Incidence rate for one cancer site, 2019–2023; <site> is one of the 19 site keys (see SITES). Many are null in small counties (suppressed).', { keys: SITE_KEYS, nulls: 'suppressed or not published for that site', source: 'incidence', layer: { county: 'inc' }, params_from_key: 'site' }),
      f('mortality.all', 'number', 'per 100,000', 'All-sites cancer death rate, age-adjusted, all ages, 2020–2024 (State Cancer Profiles). County level only; not published for districts or states in this data.', { nulls: 'suppressed or not available (see mortality.status)', source: 'mortality', layer: { county: 'mva' } }),
      f('mortality.deaths_per_year', 'integer', 'deaths per year', 'Average annual cancer deaths, all sites.', { nulls: 'not published', source: 'mortality', layer: { county: 'mva' } }),
      f('mortality.small_numbers', 'boolean', '', 'true when fewer than 16 deaths a year.', { source: 'mortality' }),
      f('mortality.status', 'string', '', 'ok, suppressed, or "no data".', { enum: ['ok', 'suppressed', 'no data'], groupable: true, source: 'mortality' }),
      f('mortality.by_site.<site>', 'number', 'per 100,000', 'Death rate for one cancer site, 2020–2024; null in most counties for most sites (suppressed by the source).', { keys: SITE_KEYS, nulls: 'suppressed', source: 'mortality', layer: { county: 'mva' }, params_from_key: 'site' }),
      f('oncologists.count', 'integer', 'oncologists', 'Oncologists (CMS: medical oncology, hematology/oncology, hematology) with a Medicare practice location in the county.', { source: 'oncologists', layer: { county: 'onc' } }),
      f('oncologists.radiation', 'integer', 'oncologists', 'Radiation oncologists with a practice location in the county.', { source: 'oncologists' }),
      f('oncologists.gynecologic', 'integer', 'oncologists', 'Gynecologic oncologists in the county.', { source: 'oncologists' }),
      f('oncologists.surgical', 'integer', 'oncologists', 'Surgical oncologists in the county.', { source: 'oncologists' }),
      f('oncologists.within_60rdmi', 'integer', 'oncologists', 'Oncologists within 60 road-miles of the county population center.', { source: 'oncologists', layer: { county: 'onc' } }),
      f('oncologists.class', 'integer', 'code', 'The map\'s "oncologists vs trials" class: 1 oncologists and trials; 2 oncologists, no trials (no recruiting trial with a site in the county); 3 trials, no oncologist listed; 4 neither.', { enum: [1, 2, 3, 4], groupable: true, source: 'oncologists', layer: { county: 'onc' } }),
      f('oncologists.class_label', 'string', '', 'The label of the class.', { enum: Object.values(ONC_CLASSES), groupable: true, source: 'oncologists', layer: { county: 'onc' } }),
      f('oncologists.all_also_elsewhere', 'boolean', '', 'true when every oncologist counted here also lists a location in another county (likely part-time or outreach clinics).', { source: 'oncologists' }),
      f('oncologists.per_100k_pop55', 'number', 'per 100,000', 'Oncologists per 100,000 residents 55+ (computed: oncologists.count ÷ pop55 × 100,000, one decimal). Not a published figure.', { computed: true, source: 'oncologists' }),
      f('incidence_above_county_median', 'boolean', '', 'true when the all-sites incidence rate is above the median of counties with a published rate (471.1 per 100,000). The "high incidence" half of the map\'s incidence-vs-access layer.', { nulls: 'no published rate', groupable: true, source: 'incidence', layer: { county: 'bva' } }),
      f('mortality_top_third', 'boolean', '', 'true when the all-sites death rate is in the top third of counties with a published rate (172.6 per 100,000 or more). The "high deaths" part of the deaths-vs-access layer.', { nulls: 'no published rate', groupable: true, source: 'mortality', layer: { county: 'mva' } }),
      f('high_incidence_low_access', 'boolean', '', 'The map\'s incidence-vs-access classification at its default setting: incidence_above_county_median AND pct_lt20_trials_within_60rdmi ≥ 50 (computed). null when the county has no published incidence rate.', { computed: true, groupable: true, layer: { county: 'bva' } }),
      f('high_deaths_low_access', 'boolean', '', 'The map\'s deaths-vs-access classification at its default setting: mortality_top_third AND pct_lt20_trials_within_60rdmi ≥ 50 (computed). null when no published death rate.', { computed: true, groupable: true, layer: { county: 'mva' } }),
      f('menu', 'string', '', 'Computed from trials_listed_here: "broad" (100+ recruiting trials in the county), "limited" (20–99), "few" (1–19), "none" (0).', { computed: true, enum: ['broad', 'limited', 'few', 'none'], groupable: true, layer: { county: 't' } }),
      f('zero_trial_share_by_type.<type>', 'number', '%', 'Share of residents 55+ with no recruiting trial of that cancer type within 60 road-miles (the map\'s by-type access for counties). <type> is one of the 20 type keys.', { keys: TYPE_KEYS_BY_TYPE_ACCESS, optional: true, layer: { county: 'short' }, params_from_key: 'type' }),
    ],
  },
  districts: {
    label: 'congressional districts', noun: 'district', id_desc: '"TX-34" (USPS-number; at-large is XX-00); geoid is the 4-digit map id', name_desc: '"Texas 34th", "Wyoming at-large"',
    desc: 'One row per House district of the 119th Congress (436 incl. DC delegate). District figures are population-weighted over the tracts in the district.',
    fields: [
      f('id', 'string', '', 'USPS-number, e.g. "TX-34"; at-large "WY-00".'), f('geoid', 'string', '', '4-digit map id (state FIPS + district), e.g. "4834".'), f('name', 'string', '', '"Texas 34th".'), f('state', 'string', '', 'USPS state code.', { enum: Object.keys(STATES), groupable: true }),
      ...CORE_ACCESS('district'), BY_TYPE,
      f('member.name', 'string', '', 'The House member (119th Congress).', { nulls: 'vacant seat', source: 'congress' }),
      f('member.party', 'string', '', 'D, R or I.', { enum: ['D', 'R', 'I'], groupable: true, nulls: 'vacant seat', source: 'congress' }),
      f('member.ctma_hr3521', 'string', '', 'The member\'s position on H.R. 3521 (Clinical Trial Modernization Act): sponsor, original, cosponsor or none.', { enum: ['sponsor', 'original', 'cosponsor', 'none'], groupable: true, source: 'congress', layer: { district: 'cos_ctma_hr' } }),
      f('member.cosponsor_date', 'string', '', 'Date the member sponsored or cosponsored H.R. 3521 (YYYY-MM-DD).', { nulls: 'not a cosponsor', optional: true, source: 'congress' }),
      f('member.bioguide', 'string', '', 'Bioguide id.', { optional: true, source: 'congress' }),
      f('member.vacant', 'boolean', '', 'true when the seat is vacant in the data (computed).', { computed: true, groupable: true }),
      f('counties', 'array', '', 'FIPS codes of the counties that overlap the district.'),
      f('county_names', 'array', '', 'Names of those counties, same order.'),
      f('nonmetro_pct', 'number', '%', 'Share of residents 55+ living in nonmetro (RUCC 4–9) counties.', { source: 'rucc', layer: { district: 'l20' }, params: { rural: '1' } }),
      f('incidence_all_sites', 'number', 'per 100,000', 'All-sites incidence: residents-55+-weighted mean of the county rates (not a published district rate).', { source: 'incidence', layer: { district: 'ginc' } }),
      f('incidence_all_sites_cases_per_year', 'integer', 'cases per year', 'Approximate annual new cases (county counts shared out by residents 55+).', { source: 'incidence' }),
      ...ONC_SUMMARY('district'),
      f('deaths_vs_access.counties_classified', 'integer', '', 'Overlapping counties with a published death rate.', { optional: true, source: 'mortality' }),
      f('deaths_vs_access.high_death_low_access_counties', 'integer', '', 'Overlapping counties in the top third of death rates with at least half of residents 55+ short of trials.', { optional: true, source: 'mortality', layer: { district: 'l20' } }),
      f('deaths_vs_access.ids', 'array', '', 'FIPS codes of those counties.', { optional: true, source: 'mortality' }),
      f('plan', 'string', '', '"119th Congress (2024 election maps)".'),
    ],
  },
  states: {
    label: 'states', noun: 'state', id_desc: 'USPS code ("TX"); DC included', name_desc: '"Texas"',
    desc: 'One row per state plus DC (51). State figures are population-weighted over all tracts in the state.',
    fields: [
      f('id', 'string', '', 'USPS code.', { enum: Object.keys(STATES) }), f('name', 'string', '', 'State name.'), f('state', 'string', '', 'Same as id.'), f('fips', 'string', '', '2-digit state FIPS.'),
      ...CORE_ACCESS('state'), BY_TYPE,
      f('nonmetro_pct', 'number', '%', 'Share of residents 55+ living in nonmetro (RUCC 4–9) counties.', { source: 'rucc', layer: { state: 'l20' }, params: { rural: '1' } }),
      ...METRO_SPLIT('metro'), ...METRO_SPLIT('nonmetro'), BY_RUCC,
      f('incidence_all_sites', 'number', 'per 100,000', 'All-sites incidence: residents-55+-weighted mean of the county rates. For the state\'s own published rate use incidence_published.all.', { source: 'incidence', layer: { state: 'ginc' } }),
      f('incidence_all_sites_cases_per_year', 'integer', 'cases per year', 'Approximate annual new cases summed from counties.', { source: 'incidence' }),
      f('incidence_published.all', 'number', 'per 100,000', 'The state\'s published all-sites incidence rate (State Cancer Profiles, 2019–2023).', { source: 'incidence' }),
      f('incidence_published.cases_per_year', 'integer', 'cases per year', 'Published average annual new cases, all sites.', { source: 'incidence' }),
      f('incidence_published.by_site.<site>', 'number', 'per 100,000', 'Published state incidence rate by site (19 site keys).', { keys: SITE_KEYS, source: 'incidence' }),
      ...ONC_SUMMARY('state'),
      f('oncologists.oncologists_per_100k_pop55', 'number', 'per 100,000', 'Oncologists per 100,000 residents 55+ (published in the API for states and the nation).', { source: 'oncologists' }),
      f('senator_names', 'array', '', 'The two senators\' names (empty for DC).', { computed: true, source: 'congress' }),
      f('senators_s4440', 'string', '', 'Summary of the senators\' positions on S. 4440, e.g. "Tim Scott (R): sponsor; Lindsey Graham (R): none".', { computed: true, source: 'congress' }),
      f('senators_cosponsoring_s4440', 'integer', '', 'How many of the state\'s senators sponsor or cosponsor S. 4440 (0–2).', { computed: true, groupable: true, source: 'congress' }),
      f('trials_distinct', 'integer', 'trials', 'Distinct recruiting trials with a site anywhere in the state (same as trials_listed_here).', { optional: true }),
      f('counties', 'integer', '', 'Number of counties in the state.', { optional: true }),
      f('counties_with_trials', 'integer', '', 'Counties with at least one recruiting trial site.', { optional: true }),
      f('broad_menu_counties', 'integer', '', 'Counties with 100+ recruiting trials.', { optional: true }),
      f('limited_menu_counties', 'integer', '', 'Counties with 20–99 recruiting trials.', { optional: true }),
      f('nci_centers_count', 'integer', '', 'NCI-designated center locations in the state (of 67).', { computed: true, source: 'nci' }),
      f('nci_center_names', 'array', '', 'Their names.', { computed: true, source: 'nci' }),
      f('need_vs_access.counties_classified', 'integer', '', 'Counties with a published incidence rate.', { optional: true, source: 'incidence' }),
      f('need_vs_access.high_incidence_low_access_counties', 'integer', '', 'Counties above the median incidence with at least half of residents 55+ short of trials.', { optional: true, source: 'incidence' }),
      f('need_vs_access.pop55', 'integer', 'people', 'Residents 55+ in those counties.', { optional: true, source: 'incidence' }),
      f('need_vs_access.cases_per_year', 'integer', 'cases per year', 'Approximate annual new cases in those counties.', { optional: true, source: 'incidence' }),
      f('deaths_vs_access.counties_classified', 'integer', '', 'Counties with a published death rate.', { optional: true, source: 'mortality' }),
      f('deaths_vs_access.high_death_low_access_counties', 'integer', '', 'Counties in the top third of death rates with at least half of residents 55+ short of trials.', { optional: true, source: 'mortality' }),
      f('deaths_vs_access.pop55', 'integer', 'people', 'Residents 55+ in those counties.', { optional: true, source: 'mortality' }),
      f('deaths_vs_access.deaths_per_year', 'integer', 'deaths per year', 'Approximate annual cancer deaths in those counties.', { optional: true, source: 'mortality' }),
    ],
  },
  national: {
    label: 'the United States', noun: 'nation', id_desc: '"US"', name_desc: '"United States"',
    desc: 'One row for the whole country (50 states + DC; territories are not covered).',
    fields: [
      f('id', 'string', '', '"US".'), f('name', 'string', '', '"United States".'),
      ...CORE_ACCESS('national').filter(x => x.path !== 'trials_listed_here'),
      f('trials_listed_here', 'integer', 'trials', 'All recruiting cancer treatment trials with a US site in the data (4,035 at the last pull).'),
      f('facilities', 'integer', 'sites', 'Trial sites (distinct facility names) with a recruiting trial.'),
      BY_TYPE, f('nonmetro_pct', 'number', '%', 'Share of residents 55+ living in nonmetro counties.', { source: 'rucc' }),
      ...METRO_SPLIT('metro'), ...METRO_SPLIT('nonmetro'), BY_RUCC,
      f('incidence_all_sites', 'number', 'per 100,000', 'Residents-55+-weighted mean of county incidence rates.', { source: 'incidence' }),
      f('incidence_published.all', 'number', 'per 100,000', 'Published US all-sites incidence rate (453.4).', { source: 'incidence' }),
      f('incidence_published.cases_per_year', 'integer', 'cases per year', 'Published US annual new cases.', { source: 'incidence' }),
      f('incidence_published.by_site.<site>', 'number', 'per 100,000', 'Published US incidence rate by site.', { keys: SITE_KEYS, source: 'incidence' }),
      f('mortality.by_site.<site>.rate', 'number', 'per 100,000', 'Published US cancer death rate by site (all = all sites), 2020–2024.', { keys: ['all', ...SITE_KEYS], optional: true, source: 'mortality' }),
      f('mortality.by_site.<site>.deaths', 'integer', 'deaths per year', 'Published US annual cancer deaths by site.', { keys: ['all', ...SITE_KEYS], optional: true, source: 'mortality' }),
      ...ONC_SUMMARY('national'), f('oncologists.oncologists_per_100k_pop55', 'number', 'per 100,000', 'Oncologists per 100,000 residents 55+.', { source: 'oncologists' }),
      f('oncologists.counties_by_class.<class>', 'integer', '', 'Number of counties in each oncologists-vs-trials class (1–4).', { keys: ['1', '2', '3', '4'], source: 'oncologists' }),
      f('need_vs_access.high_incidence_low_access_counties', 'integer', '', 'Counties above the median incidence with at least half of residents 55+ short of trials (480).', { optional: true }),
      f('need_vs_access.pop55', 'integer', 'people', 'Residents 55+ in those counties.', { optional: true }), f('need_vs_access.cases_per_year', 'integer', 'cases per year', 'Approximate annual new cases in them.', { optional: true }),
      f('deaths_vs_access.high_death_low_access_counties', 'integer', '', 'Counties in the top third of death rates with at least half short of trials (472).', { optional: true }),
      f('deaths_vs_access.pop55', 'integer', 'people', 'Residents 55+ in those counties.', { optional: true }), f('deaths_vs_access.deaths_per_year', 'integer', 'deaths per year', 'Approximate annual deaths in them.', { optional: true }),
      f('states_with_no_broad_menu_county', 'array', '', 'USPS codes of states with no county of 100+ recruiting trials.', { optional: true, computed: true }),
      f('history', 'array', '', 'One entry per weekly registry pull since September 2026: {pull, trials, pct_lt20, pct_zero, pct_gt60_broad, pct_gt60_nci, median_road_mi_nci}. The only time series in the data.', { optional: true }),
    ],
  },
  nci_centers: {
    label: 'NCI-designated cancer center locations', noun: 'center', id_desc: '"nci:<index>"', name_desc: '"Mays Cancer Center (UT Health San Antonio)"',
    desc: '67 locations of the 65 NCI-designated centers that treat adults (St. Jude excluded as a distance target).',
    fields: [f('id', 'string', '', 'nci:<index>.'), f('name', 'string', '', 'Short name.'), f('full_name', 'string', '', 'Full name.'), f('state', 'string', '', 'USPS code.', { enum: Object.keys(STATES), groupable: true }), f('tier', 'string', '', '"Comprehensive" or "Clinical" (NCI designation tier).', { enum: ['Comprehensive', 'Clinical'], groupable: true }), f('lat', 'number', '', 'Latitude.'), f('lon', 'number', '', 'Longitude.')],
  },
  facilities: {
    label: 'trial sites (facilities)', noun: 'facility', id_desc: '"fac:<site id>"', name_desc: 'the facility name as registered',
    desc: '9,655 facilities (distinct registry names per county) with at least one recruiting trial. About 400 carry an unresolved placeholder name.',
    fields: [f('id', 'string', '', 'fac:<site id>.'), f('name', 'string', '', 'Facility name.'), f('city', 'string', '', 'City.'), f('zip', 'string', '', 'ZIP code as registered.'), f('county_id', 'string', '', 'FIPS of the county the site was assigned to.'), f('county_name', 'string', '', 'That county\'s name.'), f('state', 'string', '', 'USPS code.', { enum: Object.keys(STATES), groupable: true }), f('trials', 'integer', 'trials', 'Recruiting trials at the facility.'), f('unresolved', 'boolean', '', 'true when the registry name could not be resolved to a real facility (placeholder).', { groupable: true })],
  },
  senators: {
    label: 'senators', noun: 'senator', id_desc: 'bioguide id', name_desc: '"Tim Scott"',
    desc: '100 senators (119th Congress) with their position on S. 4440 (Clinical Trial Modernization Act, Senate bill).',
    fields: [f('id', 'string', '', 'Bioguide id.'), f('name', 'string', '', 'Name.'), f('party', 'string', '', 'D, R or I.', { enum: ['D', 'R', 'I'], groupable: true }), f('state', 'string', '', 'USPS code.', { enum: Object.keys(STATES), groupable: true }), f('s4440', 'string', '', 'sponsor, original, cosponsor or none.', { enum: ['sponsor', 'original', 'cosponsor', 'none'], groupable: true }), f('cosponsor_date', 'string', '', 'Date signed on (YYYY-MM-DD).', { nulls: 'not a cosponsor' })],
  },
  cosponsors: {
    label: 'sponsors and cosponsors of the two bills', noun: 'cosponsor record', id_desc: '"<bioguide>:<bill>"', name_desc: 'member name',
    desc: 'One row per member per bill they sponsor or cosponsor (H.R. 3521: sponsor + 30 cosponsors; S. 4440: sponsor + 1 cosponsor at the last pull). Members not on a bill are not rows here; use districts.member.ctma_hr3521 = "none" or senators.s4440 = "none" for them.',
    fields: [f('id', 'string', '', '<bioguide>:<bill>.'), f('name', 'string', '', 'Member name.'), f('party', 'string', '', 'D, R or I.', { enum: ['D', 'R', 'I'], groupable: true }), f('state', 'string', '', 'USPS code.', { enum: Object.keys(STATES), groupable: true }), f('chamber', 'string', '', 'house or senate.', { enum: ['house', 'senate'], groupable: true }), f('district_id', 'string', '', 'District id for House members ("TX-11"); null for senators.', { nulls: 'senator' }), f('bill', 'string', '', 'ctma_hr (H.R. 3521) or ctma_s (S. 4440).', { enum: ['ctma_hr', 'ctma_s'], groupable: true }), f('bill_label', 'string', '', '"H.R. 3521" or "S. 4440".'), f('role', 'string', '', 'sponsor, original or cosponsor.', { enum: ['sponsor', 'original', 'cosponsor'], groupable: true }), f('date', 'string', '', 'Date signed on (YYYY-MM-DD).')],
  },
};

// columns a query returns when the model names none (besides id/name/state/pop55 and the fields it filtered or sorted on)
export const DEFAULT_COLUMNS = {
  counties: ['pct_lt20_trials_within_60rdmi', 'trials_listed_here', 'wmean_trials_within_60rdmi', 'median_road_mi_nci', 'metro'],
  districts: ['pct_lt20_trials_within_60rdmi', 'pct_zero_trials_within_60rdmi', 'median_road_mi_nci', 'member.name', 'member.party', 'member.ctma_hr3521'],
  states: ['pct_lt20_trials_within_60rdmi', 'pct_zero_trials_within_60rdmi', 'median_road_mi_nci', 'nonmetro_pct'],
  national: ['pct_lt20_trials_within_60rdmi', 'pct_zero_trials_within_60rdmi', 'median_road_mi_nci', 'trials_listed_here'],
  nci_centers: ['full_name', 'tier'], facilities: ['city', 'county_name', 'trials', 'unresolved'], senators: ['party', 's4440', 'cosponsor_date'], cosponsors: ['party', 'chamber', 'district_id', 'bill_label', 'role', 'date'],
};

// ---------- the map: what each layer shows, per unit, and the parameters it accepts ----------
export const MAP_LAYERS = {
  county: {
    short: { label: 'Residents short of trials (fewer than 20 within 60 road-miles): circles sized by people short; with rural=1 metro circles are solid and nonmetro rings', fields: ['pct_lt20_trials_within_60rdmi', 'people_lt20_trials_within_60rdmi', 'wmean_trials_within_60rdmi', 'metro', 'rucc'], params: ['lt', 'rural', 'type'] },
    shortt: { label: 'Residents short of trials, drawn over trials in the county', fields: ['pct_lt20_trials_within_60rdmi', 'trials_listed_here'], params: ['lt', 'rural', 'type'] },
    t: { label: 'Trials in the county (recruiting trials with a site in the county); the menu classes', fields: ['trials_listed_here', 'facilities', 'menu'], params: ['type'] },
    rn: { label: 'Road-miles from the county center to the nearest NCI-designated center', fields: ['road_mi_nci_from_center', 'drive_hours_nci', 'median_road_mi_nci', 'nearest_nci', 'pct_gt60rdmi_nci'], params: [] },
    rb: { label: 'Road-miles from the county center to a broad trial menu (100+ trials)', fields: ['road_mi_broad_menu_from_center', 'drive_hours_broad_menu', 'median_road_mi_broad_menu', 'nearest_broad_menu', 'pct_gt60rdmi_broad_menu', 'road_mi_limited_menu_from_center'], params: [] },
    inc: { label: 'Cancer incidence rate (age-adjusted per 100,000); site= picks the cancer site', fields: ['incidence.all', 'incidence.by_site.<site>', 'incidence.cases_per_year'], params: ['site'] },
    acs: { label: 'Household context (ACS); acs= picks the variable', fields: ['context.no_vehicle', 'context.broadband', 'context.uninsured', 'context.uninsured_55_64', 'context.poverty'], params: ['acs'] },
    bva: { label: 'Cancer incidence vs trial access (four classes: high incidence × low access etc.); crit=l20|z60 and thr=25|50|75 set the low-access rule, site= the cancer site', fields: ['high_incidence_low_access', 'incidence_above_county_median'], params: ['crit', 'thr', 'site'] },
    mva: { label: 'Cancer deaths vs trial access (four classes: top-third death rate × low access etc.)', fields: ['high_deaths_low_access', 'mortality_top_third', 'mortality.all', 'mortality.deaths_per_year', 'mortality.by_site.<site>'], params: ['crit', 'thr', 'site'] },
    onc: { label: 'Oncologists vs trials in the county (four classes)', fields: ['oncologists.class', 'oncologists.class_label', 'oncologists.count', 'oncologists.within_60rdmi', 'oncologists.per_100k_pop55'], params: [] },
  },
  district: {
    l20: { label: 'Residents 55+ with fewer than 20 trials within 60 road-miles (share); type= shows that cancer type\'s access', fields: ['pct_lt20_trials_within_60rdmi', 'people_lt20_trials_within_60rdmi', 'wmean_trials_within_60rdmi', 'trials_within_60rdmi_by_cancer_type.<type>', 'nonmetro_pct'], params: ['lt', 'type'] },
    z60: { label: 'Residents 55+ with no trial within 60 road-miles (share)', fields: ['pct_zero_trials_within_60rdmi', 'people_zero_trials_within_60rdmi'], params: [] },
    g60b: { label: 'Residents 55+ more than 60 road-miles from a broad menu (share)', fields: ['pct_gt60rdmi_broad_menu', 'median_road_mi_broad_menu'], params: [] },
    g60n: { label: 'Residents 55+ more than 60 road-miles from an NCI center (share)', fields: ['pct_gt60rdmi_nci'], params: [] },
    medn: { label: 'Median road-miles to the nearest NCI center', fields: ['median_road_mi_nci', 'nearest_nci'], params: [] },
    ginc: { label: 'Cancer incidence, all sites (weighted mean of county rates)', fields: ['incidence_all_sites', 'incidence_all_sites_cases_per_year'], params: [] },
    gacs: { label: 'Household context (ACS); acs= picks the variable', fields: ['context.no_vehicle', 'context.broadband', 'context.uninsured', 'context.uninsured_55_64', 'context.poverty'], params: ['acs'] },
    cos_ctma_hr: { label: 'Cosponsors of the Clinical Trial Modernization Act (H.R. 3521) by district', fields: ['member.ctma_hr3521', 'member.name', 'member.party'], params: [] },
  },
  state: {
    l20: { label: 'Residents 55+ with fewer than 20 trials within 60 road-miles (share)', fields: ['pct_lt20_trials_within_60rdmi', 'people_lt20_trials_within_60rdmi', 'wmean_trials_within_60rdmi', 'trials_within_60rdmi_by_cancer_type.<type>', 'nonmetro_pct', 'metro.pct_lt20', 'nonmetro.pct_lt20', 'senators_s4440', 'oncologists.count'], params: ['lt', 'type'] },
    z60: { label: 'Residents 55+ with no trial within 60 road-miles (share)', fields: ['pct_zero_trials_within_60rdmi', 'people_zero_trials_within_60rdmi', 'metro.pct_zero', 'nonmetro.pct_zero'], params: [] },
    g60b: { label: 'Residents 55+ more than 60 road-miles from a broad menu (share)', fields: ['pct_gt60rdmi_broad_menu', 'median_road_mi_broad_menu'], params: [] },
    g60n: { label: 'Residents 55+ more than 60 road-miles from an NCI center (share)', fields: ['pct_gt60rdmi_nci'], params: [] },
    medn: { label: 'Median road-miles to the nearest NCI center', fields: ['median_road_mi_nci', 'nearest_nci'], params: [] },
    ginc: { label: 'Cancer incidence, all sites (weighted mean of county rates)', fields: ['incidence_all_sites', 'incidence_published.all'], params: [] },
    gacs: { label: 'Household context (ACS); acs= picks the variable', fields: ['context.no_vehicle', 'context.broadband', 'context.uninsured', 'context.uninsured_55_64', 'context.poverty'], params: ['acs'] },
  },
};
export const MAP_PARAMS = { site: Object.keys(SITES), acs: Object.keys(ACS_KEYS), type: Object.keys(CANCER_TYPES), lt: ['5', '10', '20', '50', '100'], rural: ['1'], crit: ['l20', 'z60'], thr: ['25', '50', '75'] };
export const UNIT_OF_TABLE = { counties: 'county', districts: 'district', states: 'state' };

// ---------- definitions (the site's key terms, in its own words) ----------
export const DEFINITIONS = {
  'recruiting trial': 'An interventional cancer treatment trial listed on ClinicalTrials.gov as Recruiting, with at least one US site that is recruiting (or has no site status). Trials whose maximum age is under 55 and non-cancer studies are excluded. Trials are counted, not matched: nothing here says a trial is open to a particular person.',
  'residents 55+': 'People aged 55 and older by census tract (ACS 5-year). Every share in the data is a share of them. Why 55: most cancers are diagnosed after 55, and the Census Bureau publishes that age group by tract.',
  'road-miles': 'Distance on the highway network (TIGER primary and secondary roads) from where people live (the tract point) or from the county population center to the nearest trial site, NCI center or broad-menu county. No ferries; no link across coastal water, so islands and much of Alaska have "no road route" and are labelled, not scored. The ZIP finder uses straight-line × 1.2 instead.',
  'short of trials': 'Fewer than 20 recruiting trials within 60 road-miles of home. The 20 and 60 lines are exploratory, not clinical; the map can move the line to 5, 10, 50 or 100 (lt=).',
  'broad menu': 'A county with 100 or more recruiting cancer treatment trials (after ASCO 2024, Kirkwood et al.).',
  'limited menu': 'A county with 20 or more recruiting trials (this map\'s own line; on the brief "limited" means 20–99).',
  'NCI-designated center': 'One of the 65 cancer centers that treat adults and hold an NCI designation (Comprehensive or Clinical), at 67 locations. St. Jude (children) is not a distance target.',
  'population-weighted': 'District, state and national figures are averages over census tracts weighted by residents 55+, so the three levels add up; a mean of county values is not the same thing.',
  'RUCC / metro / nonmetro': 'USDA Rural-Urban Continuum Code 1–9 (2023). 1–3 = metro, 4–9 = nonmetro ("rural" on the site). nonmetro_pct is the share of residents 55+ living in nonmetro counties.',
  'age-adjusted rate': 'Incidence and death rates per 100,000 are age-adjusted to the US standard population and cover all ages (State Cancer Profiles). They are not restricted to residents 55+ and come from different years than the trial data.',
  'small numbers': 'A county with fewer than 16 cases (or deaths) a year keeps its published rate but is flagged small_numbers: read with caution. The source suppresses counties with 3 or fewer deaths.',
  'incidence vs access (need vs access)': 'A cross-tabulation, never a score: high incidence = all-sites incidence above the median of counties with a rate (471.1 per 100,000); low access = at least 50% of residents 55+ short of trials (crit=l20, thr=50; z60 = no trial within 60 road-miles). With a cancer type chosen, low access = no trial of that type within 60 road-miles.',
  'deaths vs access': 'Death rate in the top third of counties with a published rate (172.6 per 100,000 or more; the middle third starts at 151.4) crossed with at least 50% of residents 55+ short of trials.',
  'oncologists vs trials': 'Counties in four classes: 1 oncologists and trials; 2 oncologists but no recruiting trial with a site in the county; 3 trials but no oncologist listed; 4 neither. Oncologists are CMS clinicians with primary specialty medical oncology, hematology/oncology or hematology at any Medicare practice location in the county; one clinician can count in several counties.',
  'cosponsor': 'A member who signed on to a bill. "original" = on the day it was introduced; "sponsor" introduced it. Cosponsorship is one signal of a member\'s position, not a vote. H.R. 3521 is the House bill, S. 4440 the Senate bill, both the Clinical Trial Modernization Act (119th Congress).',
  'district plan': 'Districts are the 119th Congress plan (2024 election maps). Two seats were vacant at the last pull (member.name null).',
  'trials within 60 road-miles of the county center': 'The county card figure (trials_within_60rdmi_of_center) counts trials at sites within 60 road-miles of the county population center; wmean_trials_within_60rdmi is the resident-weighted average over the county\'s tracts. They differ in large or oddly shaped counties.',
};

// what people ask for that is not in the data; the model must say so plainly rather than approximate
export const NOT_IN_DATA = [
  'Tract-level or ZIP-level figures (the map draws tracts; the question box answers at county, district, state and national level; a ZIP or town resolves to its county).',
  'Figures for people under 55, or by race, ethnicity, sex, language or insurance type.',
  'Enrolment status, eligibility criteria matching, trial results, costs, or whether a trial is open to a given person.',
  'Death rates for districts (only counties have published death rates; states have the deaths-vs-access county counts and the nation has published rates by site).',
  'Incidence or death rates by cancer site for districts; by-site incidence for districts is not published (states and counties have it).',
  'Trial counts by cancer type for counties as averages (counties have zero_trial_share_by_type and the trials tool; districts and states have trials_within_60rdmi_by_cancer_type).',
  'Time trends other than the weekly national history since September 2026 (no historical county or district series).',
  'Travel cost, travel time by transit, telehealth availability by place, or hospital quality.',
  'US territories (Puerto Rico, Guam, the Virgin Islands, American Samoa, the Northern Mariana Islands): not in any file.',
  'Why a figure is what it is (causes): the data describes, it does not explain.',
  'Commission on Cancer or NCORP site lists (not in the data); only NCI-designated centers and registry trial sites.',
];

// common phrasings and the readings the model should consider (the first is the default; the others go in `alternatives`)
export const INTERPRETATIONS = [
  { phrase: 'no access to trials / no trials', readings: ['no recruiting trial with a site in the place (trials_listed_here = 0; for counties also oncologists.class = 2 when oncologists are present)', 'most residents have no trial within 60 road-miles (pct_zero_trials_within_60rdmi ≥ 50)', 'the place is short of trials (pct_lt20_trials_within_60rdmi ≥ 50)'] },
  { phrase: 'least access / worst access / underserved', readings: ['highest pct_lt20_trials_within_60rdmi (the headline measure)', 'highest pct_zero_trials_within_60rdmi', 'highest median_road_mi_nci'] },
  { phrase: 'best access', readings: ['lowest pct_lt20_trials_within_60rdmi', 'highest wmean_trials_within_60rdmi'] },
  { phrase: 'far from a cancer center / remote', readings: ['median_road_mi_nci (residents) or road_mi_nci_from_center (county center)', 'pct_gt60rdmi_nci', 'drive_hours_nci'] },
  { phrase: 'rural', readings: ['metro = false (RUCC 4–9) for counties', 'nonmetro_pct for districts and states', 'the nonmetro.* split for states and the nation'] },
  { phrase: 'high cancer burden / need', readings: ['incidence_above_county_median (or incidence.all)', 'mortality_top_third (or mortality.all)', 'high_incidence_low_access / high_deaths_low_access for need-vs-access'] },
  { phrase: 'how many people', readings: ['people_* counts or aggregate sum of pop55 over matching rows (sum_pop55_matching is returned by query)'] },
  { phrase: 'oncologists but no trials', readings: ['counties: oncologists.class = 2 (equivalently oncologists.count > 0 and trials_listed_here = 0)', 'districts/states: oncologists.pct_pop55_in_counties_with_oncologists_no_trials, and districts list the counties in oncologists.counties_with_oncologists_no_trials'] },
  { phrase: 'my representative / who represents', readings: ['resolve the place with find_places, then profile the county (related.districts) or district (member)'] },
];

// ---------- site_info topics: the site's own words (numbers are filled by the engine from the loaded files) ----------
export const SITE_INFO = {
  bills: { title: 'The Clinical Trial Modernization Act (H.R. 3521 / S. 4440)', url: SITE_BASE + 'act.html#policy', text: 'H.R. 3521 (House, introduced 2025-05-20 by Raul Ruiz, D-CA) and S. 4440 (Senate, introduced 2026-04-29 by Tim Scott, R-SC) are the Clinical Trial Modernization Act, 119th Congress. What it would do: Sec. 3 funds outreach grants, with priority for multilingual materials and tribal areas; Sec. 4 creates an anti-kickback safe harbor so sponsors can pay travel, transportation and meals and give free digital health tools; Sec. 5 lets manufacturers cover participants\' cost-sharing, with safeguards; Sec. 6 makes up to $2,000 a year of trial payments non-taxable; Sec. 2 defines "underrepresented population"; Sec. 7 keeps other anti-kickback protections. Which barriers it addresses: the cost of taking part, repeated visits (indirectly), information and referral. Which it leaves: distance itself (the map would look the same the day it passed), eligibility rules and registry accuracy, time off work and caregivers. Both bills were referred to committee; cosponsor counts and the latest action are refreshed weekly from congress.gov. Cosponsorship is one signal of a member\'s position, not a vote.' },
  methods: { title: 'Methods', url: SITE_BASE + 'map.html#methods', text: 'Trials: ClinicalTrials.gov API v2, interventional, Recruiting, primary purpose Treatment, an oncology condition, a US site that is Recruiting or has no reported status; trials with a maximum age under 55 and non-cancer studies are dropped. Sites go to a county by ZIP (with rules for ZIPs that span counties, PO boxes, typing errors and wrong states) and sit at the ZIP centroid for routing. People: residents 55+ in each of 84,397 census tracts (ACS 2020–2024), located at the tract\'s internal point. Roads: TIGER primary and secondary roads, a node at least every 400 m, no link across a county line or coastal water, no ferries. Each tract\'s trials within 60 road-miles are counted as distinct trials at sites within that distance; county, district, state and national shares are population-weighted over tracts (district splits of a tract apportioned by land area, 119th Congress plan). Broad menu = a county with 100+ trials; limited = 20+. NCI centers: 65 adult centers at 67 locations. Incidence (2019–2023) and death rates (2020–2024) are State Cancer Profiles, age-adjusted, all ages. Oncologists: CMS Doctors and Clinicians, counted at every Medicare practice location. RUCC: USDA ERS 2023. Districts: tracts weighted by residents 55+. The ZIP finder uses straight-line distance × 1.2.' },
  definitions: { title: 'Key terms', url: SITE_BASE + 'map.html#methods', text: Object.entries(DEFINITIONS).map(([k, v]) => `${k}: ${v}`).join('\n') },
  sources: { title: 'Sources and data dates', url: SITE_BASE + 'api.html', text: 'ClinicalTrials.gov registry (weekly pull; data_as_of is the registry date); Census Bureau ACS 2020–2024 5-year by tract; TIGER/Line 2025 roads; 2020 tract-to-district relationship (119th Congress); USDA ERS RUCC 2023; State Cancer Profiles incidence 2019–2023 (pulled 2026-10-11) and death rates 2020–2024 (pulled 2026-10-06); CMS Doctors and Clinicians (modified 2026-10-02, pulled 2026-10-19); the NCI center list; govinfo bill status and congress-legislators (2026-11-03). The data API (api/) is CC BY 4.0: Agrawal N. Cancer Clinical Trial Access Map (beta). https://cancertrialaccess.org/' },
  limits: { title: 'Limits', url: SITE_BASE + 'act.html#findings', text: 'Trials are counted, not matched to anyone\'s eligibility; "recruiting" in the registry can lag by months. Distance is the only barrier measured; cost, time off work, caregivers, referral, language and trust are not. County figures can turn on a single trial. Site counts are distinct registry names. Site locations are ZIP or city centroids. The road network is highway-only with no ferries, so islands and much of Alaska have no road route (labelled, not scored). Road distances are compared only with published approximate distances, not an independent router. About 28% of trials are multi-cancer ("basket") trials. Incidence and death rates are from different years than the trials; most site-specific county death rates are suppressed; small numbers (fewer than 16 a year) are flagged. Territories are not covered. Vacant seats are shown as vacant. Not medical advice.' },
  how_to_act: { title: 'What can I do?', url: SITE_BASE + 'act.html#contribute', text: 'The Act page (act.html) opens on any county, district, state or ZIP and shows: Part 1, what the data shows for that place with sources and limits; Part 2, policy options (the Clinical Trial Modernization Act, with the place\'s delegation and each member\'s role, plus other approaches often discussed: NCORP and the NCTN, FDA guidance on decentralized trial elements (Sept 2024) and broader eligibility (Dec 2025), coverage of routine costs under Medicare, Medicaid and the ACA, and navigation through the NCI Cancer Information Service, 1-800-4-CANCER); Part 3, ways to contribute for anyone, patients and families, clinicians, research teams and organizations. The contact script names the House member and senators and says a short note that names your county and one figure from Part 1 is enough; it links to house.gov and senate.gov contact pages. The printable brief (brief.html) carries the place\'s figures and an editable ask. To report an error, use the prefilled GitHub issue link.' },
  findings: { title: 'Key findings', url: SITE_BASE + 'findings.html', text: 'Headline: cancer clinical trials are close for most Americans and out of reach for millions. Five numbers (residents 55+): the share short of trials; the share with none within 60 road-miles; the share more than 60 road-miles from a broad menu; the median road-miles to an NCI center; the states with no broad-menu county and the districts where everyone 55+ is more than 60 road-miles from one. The gap is rural (metro vs nonmetro). Need vs access and deaths vs access count the counties where high burden meets low access. The numbers are read live from the data files (see numbers).' },
  history: { title: 'How the headline numbers have moved', url: SITE_BASE + 'map.html?tab=changes', text: 'The registry is pulled weekly (Mondays). The changes tab lists new and dropped trials, site changes and counties whose trial count crossed a menu line since the previous pull, and a history of the national headline figures per pull since September 2026. No longer series exists.' },
  changes: { title: 'This week\'s registry changes', url: SITE_BASE + 'map.html?tab=changes', text: 'Week-over-week diff of the registry pull: new trials, trials no longer listed, recruiting-site changes, counties with a changed trial count and counties that crossed the 20- or 100-trial line (see numbers).' },
  about: { title: 'About', url: SITE_BASE + 'about.html', text: 'The map was made by Neha Y. Agrawal, MD, a hematology–oncology fellow at MD Anderson, with AI-assisted tools. It is independent: not an official initiative of MD Anderson, NCCN or any other affiliated organization. Citation: Agrawal N. Cancer Clinical Trial Access Map (beta). https://cancertrialaccess.org/ (data as of the date shown on the page; data CC BY 4.0). The site is in beta: methods and figures are reviewed weekly and may change.' },
  finder: { title: 'The trial finder', url: SITE_BASE + 'find.html', text: 'find.html lists recruiting trials near a ZIP code (radius 30/60/120/200/400 miles, straight-line × 1.2), with filters for cancer type, age, keyword, phase and sponsor type, and a separate list of telemedicine trials for the state. It lists trials; it does not match patients to them. For help: NCI Cancer Information Service 1-800-4-CANCER (option 2), American Cancer Society 1-800-227-2345, Blood Cancer United 1-800-955-4572. Territory ZIPs are not covered.' },
  rural: { title: 'Rural / urban', url: SITE_BASE + 'findings.html#rural', text: 'Metro = RUCC 1–3, nonmetro = RUCC 4–9 (USDA ERS 2023). The site reports access for metro and nonmetro residents 55+ nationally and per state (metro.* and nonmetro.* fields, and by_rucc.* per code), and nonmetro_pct for districts and states. Figures are in numbers.' },
  need_vs_access: { title: 'Incidence vs trial access', url: SITE_BASE + 'findings.html#need', text: DEFINITIONS['incidence vs access (need vs access)'] + ' National and state counts are in numbers (counties, residents 55+, cases a year).' },
  deaths_vs_access: { title: 'Cancer deaths vs trial access', url: SITE_BASE + 'findings.html#deaths', text: DEFINITIONS['deaths vs access'] + ' National and state counts are in numbers.' },
  oncologists: { title: 'Oncologists vs trials', url: SITE_BASE + 'map.html#methods', text: DEFINITIONS['oncologists vs trials'] + ' Validated against ASCO\'s 2025 workforce study. Reach is 60 road-miles. National figures are in numbers.' },
};

export const SCOPE_TEXT = 'This box answers questions about where trials are and the numbers behind the map. It cannot say whether a trial is right for someone, who qualifies, or what treatment to choose; the study team and your care team decide that. For help finding and understanding trials, call the NCI Cancer Information Service at 1-800-4-CANCER or use the "Understand trials" page.';
export const OTHER_TEXT = 'This box answers questions about the numbers on the map: trial access, distances to cancer centers, cancer incidence and deaths, oncologists, rural and household context, and who in Congress cosponsors the Clinical Trial Modernization Act, for any county, district or state. For how the map is built, see Methods & data.';

// numbers the verifier always allows: the measures' own definitions and the bills
export const CONSTANTS = ['55', '60', '20', '100', '30', '120', '200', '400', '50', '25', '75', '5', '10', '3521', '4440', '119', '2000', '16', '1.2', '800', '422', '6237', '227', '2345', '955', '4572', '471.1', '172.6', '151.4', '2016', '2019', '2020', '2023', '2024', '2025', '2026', '65', '67', '84,397', '84397',
  '64',   // the ACS age band 55–64 (context.uninsured_55_64)
  '3,143', '3143', '436', '51'];   // the row counts of the counties, districts and states tables, as the catalog states them

// short column labels for the results table (the field path stays in the tooltip); labelFor() humanises any path not listed
export const LABELS = {
  id: 'id', name: 'place', state: 'state', geoid: 'map id', pop55: 'residents 55+', fips: 'FIPS',
  pct_lt20_trials_within_60rdmi: 'short of trials (% of 55+)', people_lt20_trials_within_60rdmi: 'residents 55+ short of trials', pct_zero_trials_within_60rdmi: 'no trial within 60 mi (% of 55+)', people_zero_trials_within_60rdmi: 'residents 55+ with no trial within 60 mi', pct_lt100_trials_within_60rdmi: 'fewer than 100 trials within 60 mi (%)',
  pct_gt60rdmi_broad_menu: '> 60 mi from a broad menu (%)', pct_gt60rdmi_nci: '> 60 mi from an NCI center (%)', median_road_mi_nci: 'median road-mi to NCI center', median_road_mi_broad_menu: 'median road-mi to broad menu', wmean_trials_within_60rdmi: 'avg trials within 60 mi', trials_listed_here: 'trials with a site here', facilities: 'trial sites', nearest_nci: 'nearest NCI center', nearest_broad_menu: 'nearest broad-menu county',
  'context.no_vehicle': 'no vehicle (%)', 'context.broadband': 'broadband (%)', 'context.uninsured': 'uninsured (%)', 'context.uninsured_55_64': 'uninsured 55–64 (%)', 'context.poverty': 'poverty (%)',
  districts: 'districts', rucc: 'RUCC', rucc_label: 'RUCC label', metro: 'metro', road_mi_nci_from_center: 'road-mi to NCI center (county center)', road_mi_broad_menu_from_center: 'road-mi to broad menu (county center)', road_mi_limited_menu_from_center: 'road-mi to limited menu (county center)', no_road_route_reason: 'no road route', drive_hours_nci: 'drive hours to NCI center', drive_hours_broad_menu: 'drive hours to broad menu', trials_within_60rdmi_of_center: 'trials within 60 mi of county center', facilities_within_60rdmi_of_center: 'trial sites within 60 mi of center',
  'incidence.all': 'incidence, all sites (per 100k)', 'incidence.cases_per_year': 'new cases / year', 'incidence.small_numbers': 'small numbers (incidence)', 'incidence.status': 'incidence status', 'mortality.all': 'death rate, all sites (per 100k)', 'mortality.deaths_per_year': 'deaths / year', 'mortality.small_numbers': 'small numbers (deaths)', 'mortality.status': 'death-rate status',
  'oncologists.count': 'oncologists', 'oncologists.radiation': 'radiation oncologists', 'oncologists.gynecologic': 'gyn oncologists', 'oncologists.surgical': 'surgical oncologists', 'oncologists.within_60rdmi': 'oncologists within 60 mi', 'oncologists.class': 'oncologists vs trials (class)', 'oncologists.class_label': 'oncologists vs trials', 'oncologists.all_also_elsewhere': 'all oncologists also elsewhere', 'oncologists.per_100k_pop55': 'oncologists per 100k 55+', 'oncologists.oncologists_per_100k_pop55': 'oncologists per 100k 55+',
  'oncologists.pct_pop55_in_counties_with_oncologists_no_trials': '55+ in counties with oncologists, no trials (%)', 'oncologists.pct_pop55_in_counties_with_both': '55+ in counties with both (%)', 'oncologists.pct_pop55_in_counties_with_trials_no_oncologist': '55+ in counties with trials, no oncologist (%)', 'oncologists.pct_pop55_in_counties_with_neither': '55+ in counties with neither (%)', 'oncologists.counties_with_oncologists_no_trials': 'counties with oncologists, no trials',
  incidence_above_county_median: 'incidence above county median', mortality_top_third: 'death rate in top third', high_incidence_low_access: 'high incidence × low access', high_deaths_low_access: 'high deaths × low access', menu: 'trial menu',
  'member.name': 'House member', 'member.party': 'party', 'member.ctma_hr3521': 'H.R. 3521', 'member.cosponsor_date': 'cosponsor date', 'member.bioguide': 'bioguide', 'member.vacant': 'vacant', counties: 'counties', county_names: 'counties', nonmetro_pct: 'nonmetro share of 55+ (%)', incidence_all_sites: 'incidence, all sites (per 100k)', incidence_all_sites_cases_per_year: 'new cases / year', plan: 'district plan',
  'incidence_published.all': 'published incidence (per 100k)', 'incidence_published.cases_per_year': 'published new cases / year', senator_names: 'senators', senators_s4440: 'S. 4440', senators_cosponsoring_s4440: 'senators on S. 4440', trials_distinct: 'distinct trials', counties_with_trials: 'counties with trials', broad_menu_counties: 'broad-menu counties', limited_menu_counties: 'limited-menu counties', nci_centers_count: 'NCI centers', nci_center_names: 'NCI centers',
  full_name: 'full name', tier: 'tier', lat: 'lat', lon: 'lon', city: 'city', zip: 'ZIP', county_id: 'county FIPS', county_name: 'county', trials: 'trials', unresolved: 'unresolved name', party: 'party', s4440: 'S. 4440', cosponsor_date: 'cosponsor date', chamber: 'chamber', district_id: 'district', bill: 'bill', bill_label: 'bill', role: 'role', date: 'date',
};
const SPLIT_LABELS = { pct_lt20: 'short of trials (% of 55+)', people_lt20: 'residents 55+ short of trials', pct_zero: 'no trial within 60 mi (%)', people_zero: 'residents 55+ with no trial within 60 mi', pct_lt100: 'fewer than 100 trials within 60 mi (%)', mean_trials_60: 'avg trials within 60 mi', counties: 'counties' };
export function labelFor(path) {
  if (LABELS[path]) return LABELS[path];
  if (SPLIT_LABELS[path]) return SPLIT_LABELS[path];
  let m;
  if ((m = path.match(/^incidence\.by_site\.([a-z_]+)$/))) return `${SITES[m[1]] || m[1]} incidence (per 100k)`;
  if ((m = path.match(/^mortality\.by_site\.([a-z_]+)$/))) return `${SITES[m[1]] || m[1]} death rate (per 100k)`;
  if ((m = path.match(/^incidence_published\.by_site\.([a-z_]+)$/))) return `published ${SITES[m[1]] || m[1]} incidence (per 100k)`;
  if ((m = path.match(/^trials_within_60rdmi_by_cancer_type\.([a-z_]+)$/))) return `avg ${CANCER_TYPES[m[1]] || m[1]} trials within 60 mi`;
  if ((m = path.match(/^zero_trial_share_by_type\.([a-z_]+)$/))) return `no ${CANCER_TYPES[m[1]] || m[1]} trial within 60 mi (% of 55+)`;
  if ((m = path.match(/^(metro|nonmetro)\.(.+)$/))) return `${m[1]}: ${labelFor(m[2]).replace(/^short of trials/, 'short of trials')}`;
  if ((m = path.match(/^by_rucc\.(\d)\.(.+)$/))) return `RUCC ${m[1]}: ${labelFor(m[2])}`;
  if ((m = path.match(/^(need_vs_access|deaths_vs_access)\.(.+)$/))) return `${m[1] === 'need_vs_access' ? 'incidence vs access' : 'deaths vs access'}: ${m[2].replace(/_/g, ' ')}`;
  return path.replace(/\./g, ' · ').replace(/_/g, ' ');
}

// paths that take a key: expand "<key>" for validation and prompt rendering
export function expandPath(field) { if (!field.keys) return [field.path]; const first = field.keys.map(k => field.path.replace(/<[a-z]+>/, String(k))); if (!field.keys2) return first; return first.flatMap(p => field.keys2.map(k => p.replace(/<[a-z]+>/, String(k)))); }
export function tableFields(table) { return TABLES[table] ? TABLES[table].fields : []; }
export function allPaths(table) { const out = []; for (const fd of tableFields(table)) for (const p of expandPath(fd)) out.push(p); return out; }
export function fieldFor(table, path) { for (const fd of tableFields(table)) { if (fd.path === path) return fd; if (fd.keys) { const re = new RegExp('^' + fd.path.replace(/\./g, '\\.').replace(/<[a-z]+>/g, '([^.]+)') + '$'); const m = path.match(re); if (m && fd.keys.map(String).includes(m[1]) && (!fd.keys2 || fd.keys2.includes(m[2]))) return fd; } } return null; }
export function groupableFields(table) { return tableFields(table).filter(fd => fd.groupable).map(fd => fd.path); }
export const VERSION = 3;
