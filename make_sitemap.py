"""Write docs/sitemap.xml and docs/robots.txt for the published site (https://cancertrialaccess.org/, set by docs/CNAME).

Lists the site's real pages, each with <lastmod> set to the registry data date (the date every page's figures come from: the same
date SITE.dataDate prints, read from docs/findings.js), so a weekly refresh tells search engines the pages changed. Left out:
v4.html (a redirect stub to map.html), sites.html (an unlisted research prototype) and trials.html (it needs ?county=FIPS; the
county pages are reached from the map). Runs in run_refresh.sh after build_readme.py. Usage: python3 make_sitemap.py
"""
import json, sys
from pathlib import Path

SITE = "https://cancertrialaccess.org/"   # keep in step with build_api.py, docs/ask/catalog.js and worker/wrangler.toml
PAGES = [("", "1.0"), ("map.html", "0.9"), ("findings.html", "0.8"), ("find.html", "0.8"), ("community.html", "0.7"), ("act.html", "0.7"),
         ("learn.html", "0.6"), ("brief.html", "0.5"), ("api.html", "0.5"), ("about.html", "0.5")]
DOCS = Path(__file__).resolve().parent / "docs"


def data_date():
    meta = json.loads((DOCS / "findings.js").read_text(encoding="utf-8").split("=", 1)[1].strip().rstrip(";"))["meta"]
    d = str(meta.get("registry_data_timestamp") or meta.get("pull") or "")[:10]
    if len(d) != 10: sys.exit("make_sitemap: no data date in docs/findings.js")
    return d


def main():
    d = data_date()
    for page, _ in PAGES:
        if not (DOCS / (page or "index.html")).exists(): sys.exit(f"make_sitemap: docs/{page or 'index.html'} is listed but missing")
    urls = "".join(f"  <url><loc>{SITE}{p}</loc><lastmod>{d}</lastmod><changefreq>weekly</changefreq><priority>{pr}</priority></url>\n" for p, pr in PAGES)
    (DOCS / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                      + urls + "</urlset>\n", encoding="utf-8")
    (DOCS / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}sitemap.xml\n", encoding="utf-8")
    print(f"sitemap: {len(PAGES)} pages, lastmod {d} -> docs/sitemap.xml, docs/robots.txt")


if __name__ == "__main__":
    main()
