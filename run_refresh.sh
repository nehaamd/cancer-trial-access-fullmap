#!/bin/sh
# Refresh chain (stops, and publishes nothing, if the classification audit or the release gate fails): registry pull -> QC -> county metrics -> cancer types
#   -> road graph (rebuilt only when its rules changed) -> routing -> site routing -> tract/district metrics -> Tier 4 -> member list -> web payload
#   -> rural/urban layer -> burden-vs-access layer -> deaths-vs-access layer (mortality.js) -> ZIP-lookup data -> place names for the search box -> cosponsor pull (govinfo; set CONGRESS_API_KEY
#   for api.congress.gov) -> findings -> README headline numbers -> validation -> release gate.
# Reference data (Census tables, burden, covariates) are reused; re-run their scripts separately when those sources update.
# REFRESH_SKIP_FETCH=1 re-runs everything on the registry pull already in data/raw/ (used to test a change to the method without changing the data).
set -e; cd "$(dirname "$0")"
if [ -z "$REFRESH_SKIP_FETCH" ]; then python3 fetch_us.py && python3 qc_us.py; else echo "REFRESH_SKIP_FETCH set: keeping the registry pull in data/raw/"; python3 qc_us.py --nci-only; fi
python3 metrics_us.py --min-max-age 55 --out out_adult55 && python3 classify_cancer_type.py && python3 audit_cancer_types.py \
 && python3 build_roads_us.py --if-stale \
 && python3 route_us.py && python3 route_sites_us.py && python3 tract_metrics_us.py && python3 tier4_covering.py && python3 fetch_legislators.py && python3 build_webapp_data_v3.py && python3 build_tract_context.py \
 && python3 build_rucc.py && python3 build_burden_access.py && python3 build_mortality.py && python3 build_find_data.py && python3 build_places.py && python3 fetch_cosponsors.py && python3 build_findings.py \
 && python3 build_readme.py && python3 validate_v3.py && python3 release_gate.py
