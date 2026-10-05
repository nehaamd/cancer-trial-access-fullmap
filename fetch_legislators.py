"""Refresh the list of sitting members of Congress: data/ref/legislators-current.json and data/ref/legislators_log.json.

Source: the public-domain unitedstates/congress-legislators project (the file the map, the briefs and the cosponsor table
all read). Seats change between elections - resignations, deaths, special elections - so a copy saved once goes stale: a
district would keep a departed member's name, or stay "vacant" after the seat is filled.

This step never stops a refresh. If neither address answers, or the download does not look like the full membership, the saved
file is kept and the log records why; the page shows the date of the last successful download ("House members as of ...").

Usage: python fetch_legislators.py
"""
import json, sys, urllib.request
from datetime import date
from pathlib import Path

REF = Path("data/ref"); FILE = REF / "legislators-current.json"; LOG = REF / "legislators_log.json"
URLS = ["https://unitedstates.github.io/congress-legislators/legislators-current.json",
        "https://raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages/legislators-current.json"]
UA = {"User-Agent": "cancer-trial-access-map (member list refresh)"}
FIRST_SAVED = "2026-09-09"   # date of the copy committed before this script existed


def summary(members):
    last = [m["terms"][-1] for m in members]
    return {"members": len(members), "representatives": sum(1 for t in last if t["type"] == "rep"), "senators": sum(1 for t in last if t["type"] == "sen")}


def looks_complete(members):
    """The full membership is 100 senators and up to 441 representatives and delegates; a short or malformed file is rejected."""
    if not isinstance(members, list): return "not a list"
    try: s = summary(members); ok = all(m["id"]["bioguide"] and m["name"] and m["terms"][-1]["state"] for m in members)
    except Exception as e: return f"unexpected structure ({type(e).__name__})"
    if not ok: return "member without an id, name or state"
    if not (90 <= s["senators"] <= 100): return f"{s['senators']} senators"
    if not (400 <= s["representatives"] <= 441): return f"{s['representatives']} representatives"
    return ""


def main():
    old = json.loads(LOG.read_text()) if LOG.exists() else {"fetched": FIRST_SAVED, "source": "unitedstates/congress-legislators, gh-pages"}
    errors = []
    for url in URLS:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r: raw = r.read()
            members = json.loads(raw); bad = looks_complete(members)
            if bad: errors.append(f"{url}: rejected ({bad})"); continue
            before = {m["id"]["bioguide"] for m in json.loads(FILE.read_text())} if FILE.exists() else set(); now = {m["id"]["bioguide"] for m in members}
            FILE.write_bytes(raw)
            log = {"fetched": str(date.today()), "source": url, "status": "downloaded", **summary(members), "joined_since_last_file": len(now - before), "left_since_last_file": len(before - now)}
            LOG.write_text(json.dumps(log, indent=1)); print("members of Congress:", json.dumps(log)); return
        except Exception as e:
            errors.append(f"{url}: {type(e).__name__} {str(e)[:100]}")
    if not FILE.exists(): sys.exit("no saved legislators-current.json and the download failed: " + "; ".join(errors))
    log = {**old, "status": "kept the saved file", "last_attempt": str(date.today()), "last_error": "; ".join(errors)[:400]}
    LOG.write_text(json.dumps(log, indent=1)); print("members of Congress: download failed, saved file kept —", log["last_error"])


if __name__ == "__main__":
    main()
