"""Oncologists in practice, from two public federal sources: the reference extract for the "Oncologists and trials" layer.

  1. CMS Doctors and Clinicians national downloadable file (Care Compare; data.cms.gov provider-data dataset mj5m-pzi6): clinicians enrolled
     in Medicare, one row per clinician x practice location, with the CMS specialty (primary and secondary). Clinicians appear when they have
     billed Medicare recently, so the file stands for "in practice and seeing Medicare patients": the primary source for this layer.
  2. NPPES full replacement file (CMS National Plan and Provider Enumeration System, monthly): every NPI, with the self-reported taxonomy
     codes and one practice-location address. NPIs are rarely retired when a physician stops practising, so NPPES over-counts; it is kept
     as the cross-check (does the Medicare file miss oncologists who see no Medicare patients?) and to read the taxonomy behind a specialty.

Both are public domain (federal works). Only clinicians whose specialty or taxonomy is oncology or haematology are kept; the extract holds
NPIs and practice addresses (public in both sources) but no names. The site publishes counts by county, never individuals.

The hosts are not reachable from every network; the workflow "Refresh oncologist reference data" runs this script on GitHub's runner.
Outputs (data/ref/):
  oncologists_cms.csv     npi, pri_spec, sec_spec_all, org_pac_id, facility, adrs_id, city, state, zip5, grd_yr
  oncologists_nppes.csv   npi, taxonomy codes kept (primary first), primary_code, city, state, zip5, enumeration, last_update, deactivated
  oncologists_log.json    source URLs, file dates and sizes, row counts, every specialty string and taxonomy code kept with counts
Run: python3 fetch_oncologists.py [--cms-only | --nppes-only]
"""
import io, json, re, sys, time, zipfile
from pathlib import Path
import pandas as pd, requests

REF = Path("data/ref"); TMP = Path("data/tmp_onc"); TMP.mkdir(parents=True, exist_ok=True)
s = requests.Session(); s.headers["User-Agent"] = "us-trial-access-map/3.0 (research)"
CMS_META = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/mj5m-pzi6?show-reference-ids=false"
NPPES_PAGE = "https://download.cms.gov/nppes/NPI_Files.html"

# CMS specialty strings kept (upper case; matched as substrings so "HEMATOLOGY/ONCOLOGY" and "HEMATOLOGY-ONCOLOGY" both count). Everything
# with ONCOL or HEMATOL is kept in the extract; build_oncologists.py decides which groups count, and the log lists every string seen.
CMS_RX = re.compile(r"ONCOL|HEMATOL", re.I)
# NUCC taxonomy codes (www.nucc.org): every code kept in the extract is listed here, with its group; the build decides what counts.
TAXONOMY = {
    "207RX0202X": "medical_oncology",        # Internal Medicine, Medical Oncology
    "207RH0003X": "hematology_oncology",     # Internal Medicine, Hematology & Oncology
    "207RH0000X": "hematology",              # Internal Medicine, Hematology
    "2085R0001X": "radiation_oncology",      # Radiology, Radiation Oncology
    "2085R0203X": "therapeutic_radiology",   # Radiology, Therapeutic Radiology (older name for radiation oncology)
    "207VX0201X": "gynecologic_oncology",    # Obstetrics & Gynecology, Gynecologic Oncology
    "2086X0206X": "surgical_oncology",       # Surgery, Surgical Oncology
    "2080P0207X": "pediatric_hem_onc",       # Pediatrics, Pediatric Hematology-Oncology (kept for the log; not counted for adults 55+)
}


def get(url, stream=False, tries=4):
    for k in range(tries):
        try:
            r = s.get(url, timeout=600, stream=stream); r.raise_for_status(); return r
        except Exception as e:
            print(f"  retry {k + 1} {url}: {e}", flush=True); time.sleep(10 * (k + 1))
    sys.exit(f"could not fetch {url}")


def download(url, dest):
    if dest.exists() and dest.stat().st_size > 0: print(f"  cached {dest} ({dest.stat().st_size / 1e6:,.0f} MB)"); return
    r = get(url, stream=True); n = 0
    with open(dest, "wb") as f:
        for b in r.iter_content(1 << 22): f.write(b); n += len(b)
    print(f"  downloaded {url} -> {dest} ({n / 1e6:,.0f} MB)", flush=True)


def norm(c): return re.sub(r"[^a-z0-9]", "", c.lower())


def pick(cols, *cands, required=True):
    """The column whose normalised name equals one of the candidates (the file's headers have changed case and spelling over the years)."""
    m = {norm(c): c for c in cols}
    for c in cands:
        if norm(c) in m: return m[norm(c)]
    if required: sys.exit(f"no column among {cands}; header: {list(cols)}")
    return None


def zip5(z): return z.astype(str).str.replace(r"\D", "", regex=True).str[:5].where(lambda x: x.str.len() == 5, "")


def cms(log):
    meta = get(CMS_META).json()
    dist = meta.get("distribution") or []
    urls = [d.get("downloadURL") or (d.get("data") or {}).get("downloadURL") for d in dist]
    url = next((u for u in urls if u and u.lower().endswith(".csv")), None) or sys.exit(f"no CSV in the CMS metastore entry: {urls}")
    dest = TMP / "cms_dac.csv"; download(url, dest)
    head = pd.read_csv(dest, nrows=0).columns
    c = {"npi": pick(head, "NPI"), "pri": pick(head, "pri_spec", "Primary specialty"), "sec": pick(head, "sec_spec_all", "All secondary specialties", required=False),
         "org": pick(head, "org_pac_id", "Group PAC ID", required=False), "fac": pick(head, "Facility Name", "org_nm", required=False),
         "adr": pick(head, "adrs_id", "Address ID", required=False), "city": pick(head, "City/Town", "cty", "City"), "st": pick(head, "State", "st"),
         "zip": pick(head, "ZIP Code", "zip", "zip_cd"), "grd": pick(head, "grd_yr", "Graduation year", required=False)}
    use = [v for v in c.values() if v]; keep, total, spec_all = [], 0, {}
    for ch in pd.read_csv(dest, dtype=str, usecols=use, chunksize=400_000, keep_default_na=False):
        total += len(ch)
        sec = ch[c["sec"]] if c["sec"] else ""
        hit = ch[c["pri"]].str.contains(CMS_RX) | (sec.str.contains(CMS_RX) if c["sec"] else False)
        keep.append(ch[hit])
    df = pd.concat(keep, ignore_index=True)
    out = pd.DataFrame({"npi": df[c["npi"]].str.strip(), "pri_spec": df[c["pri"]].str.strip().str.upper(),
                        "sec_spec_all": df[c["sec"]].str.strip().str.upper() if c["sec"] else "",
                        "org_pac_id": df[c["org"]].str.strip() if c["org"] else "", "facility": df[c["fac"]].str.strip() if c["fac"] else "",
                        "adrs_id": df[c["adr"]].str.strip() if c["adr"] else "", "city": df[c["city"]].str.strip(), "state": df[c["st"]].str.strip().str.upper(),
                        "zip5": zip5(df[c["zip"]]), "grd_yr": df[c["grd"]].str.strip() if c["grd"] else ""}).drop_duplicates()
    out.to_csv(REF / "oncologists_cms.csv", index=False)
    log["cms"] = {"url": url, "dataset": "mj5m-pzi6", "modified": meta.get("modified"), "title": meta.get("title"), "bytes": dest.stat().st_size,
                  "rows_in_file": total, "rows_kept": len(out), "clinicians_kept": int(out.npi.nunique()), "columns_used": c,
                  "pri_spec_counts": out.drop_duplicates("npi").pri_spec.value_counts().to_dict()}
    print(f"CMS: {total:,} rows; kept {len(out):,} rows, {out.npi.nunique():,} clinicians", flush=True)


def nppes(log):
    page = get(NPPES_PAGE).text
    links = re.findall(r'href="([^"]*NPPES_Data_Dissemination_[A-Za-z]+_\d{4}[^"]*\.zip)"', page)
    full = [l for l in links if not re.search(r"weekly|deactiv|_\d{6}_\d{6}", l, re.I)]
    if not full: sys.exit(f"no full replacement file on {NPPES_PAGE}; links: {links[:10]}")
    url = requests.compat.urljoin(NPPES_PAGE, full[0]); dest = TMP / Path(url).name; download(url, dest)
    z = zipfile.ZipFile(dest)
    member = next((n for n in z.namelist() if re.search(r"npidata_pfile_\d{8}-\d{8}\.csv$", n)), None) or sys.exit(f"no npidata file in {z.namelist()}")
    with z.open(member) as f: head = pd.read_csv(f, nrows=0).columns
    tax = [pick(head, f"Healthcare Provider Taxonomy Code_{i}") for i in range(1, 16)]
    sw = [pick(head, f"Healthcare Provider Primary Taxonomy Switch_{i}") for i in range(1, 16)]
    c = {"npi": pick(head, "NPI"), "ent": pick(head, "Entity Type Code"),
         "city": pick(head, "Provider Business Practice Location Address City Name"), "st": pick(head, "Provider Business Practice Location Address State Name"),
         "zip": pick(head, "Provider Business Practice Location Address Postal Code"),
         "enum": pick(head, "Provider Enumeration Date"), "upd": pick(head, "Last Update Date"),
         "deact": pick(head, "NPI Deactivation Date"), "react": pick(head, "NPI Reactivation Date")}
    codes = set(TAXONOMY); rows, total, indiv = [], 0, 0
    with z.open(member) as f:
        for ch in pd.read_csv(f, dtype=str, usecols=list(c.values()) + tax + sw, chunksize=500_000, keep_default_na=False):
            total += len(ch); ch = ch[ch[c["ent"]] == "1"]; indiv += len(ch)
            hit = ch[tax].isin(codes).any(axis=1); ch = ch[hit]
            for _, r in ch.iterrows():
                kept = [(r[t], r[w] == "Y") for t, w in zip(tax, sw) if r[t] in codes]
                prim = next((r[t] for t, w in zip(tax, sw) if r[w] == "Y"), "")
                rows.append({"npi": r[c["npi"]], "codes": ";".join(k for k, p in sorted(kept, key=lambda x: not x[1])), "primary_code": prim,
                             "city": r[c["city"]].strip(), "state": r[c["st"]].strip().upper(), "zip5": re.sub(r"\D", "", r[c["zip"]])[:5],
                             "enumeration": r[c["enum"]], "last_update": r[c["upd"]], "deactivated": r[c["deact"]], "reactivated": r[c["react"]]})
            print(f"  NPPES: {total:,} rows read, {len(rows):,} kept", flush=True)
    out = pd.DataFrame(rows); out["zip5"] = out.zip5.where(out.zip5.str.len() == 5, "")
    out.to_csv(REF / "oncologists_nppes.csv", index=False)
    log["nppes"] = {"url": url, "member": member, "bytes": dest.stat().st_size, "rows_in_file": total, "individual_npis": indiv, "kept": len(out),
                    "code_counts_any": {k: int(out.codes.str.contains(k).sum()) for k in TAXONOMY},
                    "code_counts_primary": {k: int((out.primary_code == k).sum()) for k in TAXONOMY}, "taxonomy_groups": TAXONOMY}
    print(f"NPPES: {total:,} rows, {indiv:,} individuals; kept {len(out):,}", flush=True)


if __name__ == "__main__":
    lp = REF / "oncologists_log.json"; log = json.loads(lp.read_text()) if lp.exists() else {}
    log["pulled"] = time.strftime("%Y-%m-%d")
    if "--nppes-only" not in sys.argv: cms(log)
    if "--cms-only" not in sys.argv: nppes(log)
    lp.write_text(json.dumps(log, indent=1))
