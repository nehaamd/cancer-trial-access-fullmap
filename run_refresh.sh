#!/bin/sh
# Refresh chain: registry pull -> QC -> county metrics -> cancer types -> routing -> site routing -> tract/district metrics -> Tier 4 -> web payload
#   -> rural/urban layer -> burden-vs-access layer -> ZIP-lookup data -> cosponsor pull (govinfo; set CONGRESS_API_KEY for api.congress.gov) -> validation.
# Reference data (Census, roads graph, burden, covariates) are reused; re-run their scripts separately when those sources update.
set -e; cd "$(dirname "$0")"
python3 fetch_us.py && python3 qc_us.py && python3 metrics_us.py --min-max-age 55 --out out_adult55 && python3 classify_cancer_type.py \
 && python3 route_us.py && python3 route_sites_us.py && python3 tract_metrics_us.py && python3 tier4_covering.py && python3 build_webapp_data_v3.py \
 && python3 build_rucc.py && python3 build_burden_access.py && python3 build_find_data.py && python3 fetch_cosponsors.py && python3 validate_v3.py
