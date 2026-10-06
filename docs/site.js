/* Cancer Trial Access Map — helpers shared by every page (loaded before each page's own script).
   Nothing here depends on a particular data pull: every label is derived from the data files at view time. */
window.SITE = (function () {
  const USPS = {"01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE","11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA","20":"KS","21":"KY","22":"LA","23":"ME","24":"MD","25":"MA","26":"MI","27":"MN","28":"MS","29":"MO","30":"MT","31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM","36":"NY","37":"NC","38":"ND","39":"OH","40":"OK","41":"OR","42":"PA","44":"RI","45":"SC","46":"SD","47":"TN","48":"TX","49":"UT","50":"VT","51":"VA","53":"WA","54":"WV","55":"WI","56":"WY"};

  // Full name of a county-equivalent: "Harris County", "Baltimore city", "Orleans Parish", "Anchorage Municipality".
  // data.js carries the Census Bureau's own full name as c.nl; the rules below only cover a data file built before that field existed.
  function countyName(c, fips) {
    if (c && c.nl) return c.nl;
    const n = c ? c.n : '', st = String(fips || '').slice(0, 2), co = +String(fips || '').slice(2);
    if (fips === '11001' || fips === '32510') return n;                       // District of Columbia, Carson City
    if (st === '22') return n + ' Parish';
    if (st === '02') return n;                                                // Alaska: boroughs, census areas and municipalities
    if ((st === '51' && co >= 500) || fips === '24510' || fips === '29510') return n + ' city';   // independent cities
    return n + ' County';
  }
  const countyLabel = (c, fips) => countyName(c, fips) + ', ' + (USPS[String(fips || '').slice(0, 2)] || '');

  // Dates. The "data as of" date is the registry's own data timestamp when the pull recorded one.
  const dataDate = meta => String(meta.registry_data_timestamp || meta.pull || '').slice(0, 10);
  function nice(iso, month) { const d = new Date(String(iso).slice(0, 10) + 'T12:00:00'); return isNaN(d) ? String(iso) : d.toLocaleDateString('en-US', { month: month || 'short', day: 'numeric', year: 'numeric' }); }
  function today() { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }   // the reader's date, not UTC
  function daysOld(iso) { const d = new Date(String(iso).slice(0, 10) + 'T12:00:00'); return isNaN(d) ? null : Math.floor((Date.now() - d.getTime()) / 864e5); }
  const STALE_DAYS = 10;   // older than this, the pages say how many days old the registry data is
  function stampText(meta) { const dd = dataDate(meta), age = daysOld(dd); return 'Data as of ' + nice(dd) + (age !== null && age > STALE_DAYS ? ' (' + age + ' days ago)' : ''); }
  const isStale = meta => { const a = daysOld(dataDate(meta)); return a !== null && a > STALE_DAYS; };

  // Trial phase as the registry writes it ("PHASE1", "PHASE1/PHASE2", "PHASE2;PHASE3", "NA") or as this site stores it ("1-2", "NA").
  function phaseLabel(p) {
    const s = String(p == null ? '' : p).trim().toUpperCase();
    if (!s || s === 'NA' || s === 'N/A') return 'Not phased';
    const nums = s.replace(/EARLY_PHASE1/g, '1').replace(/PHASE/g, '').split(/[\/;,|\s-]+/).filter(Boolean);
    return nums.length && nums.every(x => /^\d$/.test(x)) ? 'Phase ' + nums.join('-') : 'Phase ' + s;
  }

  // The cancers a trial names, leaving out the two catch-all buckets (a basket trial never "names" its own bucket).
  function namedCancers(T, j) { return (T.cats[j] || []).filter(ci => T.types[ci] && T.types[ci][0] !== 'multi' && T.types[ci][0] !== 'other_unclassified').map(ci => T.types[ci][1]); }
  // One plain-text line for a trial's cancer type: "Breast", or "Multiple cancer types / basket or umbrella: names Breast, Lung & thoracic".
  function cancerLine(T, j) {
    const primary = T.types[T.ct[j]] ? T.types[T.ct[j]][1] : ''; if (!T.multi[j]) return primary;
    const named = namedCancers(T, j); return primary + (named.length ? ': names ' + named.join(', ') : ' (cancers not named individually)');
  }

const TEACH = {
    breast: 'Breast cancer trials are usually written for one subtype — hormone-receptor-positive, HER2-positive or triple-negative — and for a stage or setting (before surgery, after surgery, or metastatic). A county with 20 breast trials may have none for a given person.',
    lung: 'Lung cancer trials separate small-cell from non-small-cell disease and, within non-small-cell, often require a specific driver mutation (EGFR, ALK, KRAS G12C and others) or a PD-L1 level. Stage and prior treatment narrow the list further.',
    colorectal: 'For colorectal cancer, stage, biomarkers such as mismatch-repair (MSI) status and RAS or BRAF mutations, and prior treatment lines determine which trials might be relevant. The count here is every colorectal trial, not the ones that would fit one patient.',
    prostate: 'Prostate trials are divided by whether the cancer still responds to hormone therapy (castration-sensitive or castration-resistant), whether it has spread, and prior treatments. A local trial for one setting may not apply to another.',
    leukemia: 'Leukemia trials depend on the type (acute or chronic, myeloid or lymphoid), genetic features of the disease and whether it is newly diagnosed or has relapsed. Many open only at centers with transplant programs.',
    lymphoma: 'Lymphoma trials are written for specific subtypes (Hodgkin, diffuse large B-cell, follicular, mantle cell and others) and for newly diagnosed or relapsed disease. CAR-T and bispecific-antibody trials mostly open at large centers.',
    myeloma: 'Myeloma trials specify how many prior lines of treatment a patient has had and which drug classes they have received. Early trials of cell therapies are concentrated at a few centers.',
    pancreatic: 'Pancreatic cancer trials separate resectable from locally advanced and metastatic disease and often require good performance status. Many are early-phase studies at academic centers.',
    melanoma_skin: 'Melanoma trials depend on stage, BRAF status and prior immunotherapy. Trials for non-melanoma skin cancers are fewer and usually for advanced disease.',
    gynecologic: 'Ovarian, uterine and cervical cancers are different diseases with different trials; within ovarian cancer, BRCA status and platinum sensitivity decide eligibility for many studies.',
    brain_cns: 'Brain tumor trials are written for a tumor type and grade (glioblastoma, lower-grade glioma, meningioma) and often for newly diagnosed or recurrent disease separately. Most open at neuro-oncology centers.',
    mds_mpn: 'Myelodysplastic syndromes and myeloproliferative neoplasms are uncommon, and their trials are split by risk group and genetic features. Most open at academic centers, so distance matters more for these diseases.',
    sarcoma: 'Sarcomas are dozens of rare diseases. A trial for one subtype rarely applies to another, and most open at a handful of referral centers.',
    head_neck: 'Head and neck cancer trials depend on the site (mouth, throat, larynx), HPV status and whether the cancer is newly diagnosed, recurrent or metastatic.',
    kidney: 'Kidney cancer trials depend on the cell type (clear cell or not), risk group and prior immunotherapy or targeted therapy.',
    liver_biliary: 'Liver and bile-duct cancers are separate diseases; liver cancer trials also depend on how well the liver itself is working (Child-Pugh class) and on prior treatment.',
    gastric_esophageal: 'Stomach and esophageal cancer trials depend on location, HER2 and PD-L1 status, and whether the cancer can be removed surgically.',
    bladder_urothelial: 'Bladder cancer trials separate non-muscle-invasive from muscle-invasive and metastatic disease; some require specific genetic alterations (such as FGFR).',
    neuroendocrine_endocrine: 'Neuroendocrine and endocrine cancers are uncommon and varied; trials often specify the organ of origin, grade and receptor imaging results.',
    other_named: 'Rarer cancers have few trials each, and most open only at specialized centers, so the distance to one is often the whole story.',
    multi: 'Basket and umbrella trials enroll several cancers that share a target or a biomarker. They widen what counts as “a trial near me”, but each still has its own eligibility rules.',
    other_unclassified: 'A few studies name a condition the classifier could not place; treat their count with caution.'
  };
  const teach = type => TEACH[type] || 'Stage, biomarkers and prior treatment further determine which trials might be relevant; a count of trials is a count of doors, not of doors that will open for one person.';
  // One sentence for the distance figures: a distance on the map is a trip that participation may require many times.
  const TRIPS = 'Participation may require this trip many times: treatment trials often need visits every one to three weeks at first, plus extra scans and blood tests.';
  const plural = (n, one, many) => n === 1 ? one : (many || one + 's');
  function ordinal(n) { const v = n % 100, s = ['th', 'st', 'nd', 'rd']; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
  return { TEACH, teach, TRIPS, USPS, countyName, countyLabel, dataDate, nice, today, daysOld, stampText, isStale, STALE_DAYS, phaseLabel, namedCancers, cancerLine, plural, ordinal };
})();
