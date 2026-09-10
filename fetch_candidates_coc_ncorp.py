"""Tier 4 candidate universe — INTENDED sources (Commission on Cancer-accredited programs + NCORP affiliates).

STATUS: NOT RUN. www.facs.org and ncorp.cancer.gov were added to the sandbox allowlist but the running container did not pick up
the change (egress proxy: host_not_allowed), so this script could not be written against the live page structure. It documents
the contract tier4_covering.py needs and the crawl plan, and it will raise until the domains resolve. Do not treat its output as
existing until it has been run and its log reviewed.

Contract for the candidates file (data/ref/candidates_coc_ncorp.csv), one row per facility:
    name, city, state (USPS), zip (5 digits), county_fips (may be blank; tier4_covering.py geocodes by ZIP, then city), source
    source in {"coc", "ncorp", "coc+ncorp"}
    optional: n_trials_hosted_2016plus (left blank; not meaningful for these sources)

Crawl plan:
  CoC   https://www.facs.org/  — the "Find a Cancer Program" / hospital locator lists accredited programs by state; nearly 1,400
        hospitals and cancer centers are accredited. Fetch state by state, one request every 2 s, keep program name, city, state,
        ZIP, accreditation category. If the locator loads results from a separate API host, that host must be allowlisted too;
        record it in the log.
  NCORP https://ncorp.cancer.gov/findasite/?state=<State Name> — each community-site grantee lists its affiliates and sub-affiliates
        (1,000+ across 48 states; VT, NH, MA, CT, RI, WV have no NCORP coverage). Keep affiliate name, city, state; ZIP is usually
        absent, so those rows geocode by city.
  Then: normalise names with the same site-code rule as the rest of the pipeline; de-duplicate CoC vs NCORP on (state, normalised
        name, city); write the file and a log with the counts captured versus the published totals (~1,400 CoC; 1,000+ NCORP),
        so an incomplete crawl is visible.
Run:  python tier4_covering.py --candidates data/ref/candidates_coc_ncorp.csv --label "CoC-accredited programs + NCORP affiliates"
"""
import sys, requests

if __name__ == "__main__":
    for host in ("https://www.facs.org/", "https://ncorp.cancer.gov/findasite/"):
        try:
            r = requests.get(host, timeout=30); ok = r.status_code == 200 and "host_not_allowed" not in r.headers.get("x-deny-reason", "")
        except Exception as e:
            ok = False
        print(host, "reachable" if ok else "NOT reachable")
    sys.exit("fetch_candidates_coc_ncorp.py: crawl not implemented against live pages yet — see docstring. Nothing was written.")
