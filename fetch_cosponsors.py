"""Cosponsor tracking for the bills this site follows, joined to House districts and Senate seats.

Tracked (119th Congress):
  Clinical Trial Modernization Act — H.R. 3521 (Ruiz) and S. 4440 (Scott): grants for trial outreach in underserved
      communities, anti-kickback safe harbours for participant expense reimbursement and free digital health tools, and a
      tax exclusion for trial participation payments.
Add a bill to BILLS below to track another one.

Sources, in the order tried:
  1. govinfo.gov bulk data, BILLSTATUS XML (no key needed): https://www.govinfo.gov/bulkdata/BILLSTATUS/119/hr/BILLSTATUS-119hr1492.xml
  2. api.congress.gov v3 (set CONGRESS_API_KEY; free at https://api.congress.gov/sign-up/), which is the authoritative feed.
  3. The last saved pull, cosponsors_raw.json, when neither host is reachable (the build container cannot reach either).
Member names, parties, chambers and districts come from unitedstates/congress-legislators (legislators-current.json), the
same file the rest of the site uses; a sponsor or cosponsor who has since left Congress is kept and flagged "former".

Output: docs/cosponsors.js (window.COSPONSORS) — bills, per-member roles, a district -> member map and state -> senators map.
Usage: python fetch_cosponsors.py [--require-network]   (the flag makes the run fail instead of reusing the saved pull when the feed is unreachable)
"""
import json, os, sys, time, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

BILLS = [
    {"key": "ctma_hr", "congress": 119, "type": "hr", "number": 3521, "topic": "ctma", "label": "H.R. 3521", "short": "Clinical Trial Modernization Act"},
    {"key": "ctma_s", "congress": 119, "type": "s", "number": 4440, "topic": "ctma", "label": "S. 4440", "short": "Clinical Trial Modernization Act"},
    # To track another bill, add its House and/or Senate entry here with a shared "topic", and describe the topic in TOPICS, e.g.
    # {"key": "epic_hr", "congress": 119, "type": "hr", "number": 1492, "topic": "epic", "label": "H.R. 1492", "short": "EPIC Act"},
    # {"key": "epic_s",  "congress": 119, "type": "s",  "number": 832,  "topic": "epic", "label": "S. 832",    "short": "EPIC Act"},
]
TOPICS = {"ctma": {"name": "Clinical Trial Modernization Act", "long": "Clinical Trial Modernization Act", "what": "would fund trial outreach in underserved and rural communities and let sponsors cover participants' travel and other costs without anti-kickback exposure"}}
STFIPS = {"AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
          "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
          "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56"}
UA = {"User-Agent": "cancer-trial-access-map (cosponsor refresh)"}


def find(name):
    for d in [".", "data/ref", "docs"]:
        p = Path(d) / name
        if p.exists(): return p
    return None


def docs_dir():
    return Path("docs") if Path("docs").is_dir() and not Path("data.js").exists() else Path(".")


def get(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()


def from_govinfo(b):
    url = f"https://www.govinfo.gov/bulkdata/BILLSTATUS/{b['congress']}/{b['type']}/BILLSTATUS-{b['congress']}{b['type']}{b['number']}.xml"
    root = ET.fromstring(get(url)); bill = root.find("bill")
    t = lambda el, path: (el.findtext(path) or "").strip()
    sp = bill.find("sponsors/item")
    la = bill.find("latestAction")
    titles = [t(x, "title") for x in bill.findall("titles/item") if (x.findtext("titleType") or "").startswith("Short Title(s) as Introduced")]
    return {"congress": b["congress"], "type": b["type"], "number": b["number"], "title": t(bill, "title"), "short_title": titles[0] if titles else "",
            "introduced": t(bill, "introducedDate"), "latest_action": {"date": t(la, "actionDate") if la is not None else "", "text": t(la, "text") if la is not None else ""},
            "sponsor": {"bioguide": t(sp, "bioguideId"), "name": t(sp, "fullName"), "party": t(sp, "party"), "state": t(sp, "state"), "district": (int(t(sp, "district")) if t(sp, "district").isdigit() else None)},
            "cosponsors": [[t(c, "bioguideId"), t(c, "sponsorshipDate")] for c in bill.findall("cosponsors/item") if not t(c, "sponsorshipWithdrawnDate")]}


def from_congress_api(b, key):
    base = f"https://api.congress.gov/v3/bill/{b['congress']}/{b['type']}/{b['number']}"
    meta = json.loads(get(f"{base}?api_key={key}&format=json"))["bill"]
    cos, off = [], 0
    while True:
        page = json.loads(get(f"{base}/cosponsors?api_key={key}&format=json&limit=250&offset={off}"))
        items = page.get("cosponsors", []); cos += [[c["bioguideId"], c.get("sponsorshipDate", "")] for c in items if not c.get("sponsorshipWithdrawnDate")]
        if len(items) < 250: break
        off += 250; time.sleep(1)
    sp = meta["sponsors"][0]
    return {"congress": b["congress"], "type": b["type"], "number": b["number"], "title": meta.get("title", ""), "short_title": "",
            "introduced": meta.get("introducedDate", ""), "latest_action": {"date": meta.get("latestAction", {}).get("actionDate", ""), "text": meta.get("latestAction", {}).get("text", "")},
            "sponsor": {"bioguide": sp["bioguideId"], "name": sp.get("fullName", ""), "party": sp.get("party", ""), "state": sp.get("state", ""), "district": sp.get("district")}, "cosponsors": cos}


def fetch_all():
    key = os.environ.get("CONGRESS_API_KEY")
    out, source = {}, None
    for b in BILLS:
        rec, err = None, []
        for name, fn in [("govinfo BILLSTATUS XML", lambda: from_govinfo(b))] + ([("api.congress.gov v3", lambda: from_congress_api(b, key))] if key else []):
            try: rec = fn(); source = source or name; break
            except Exception as e: err.append(f"{name}: {type(e).__name__} {str(e)[:80]}")
        if rec is None: return None, "; ".join(err)
        out[b["key"]] = rec
    return out, source


def main():
    raw_path = find("cosponsors_raw.json") or Path("cosponsors_raw.json")
    fetched, source = fetch_all()
    if fetched:
        raw = {"fetched": str(date.today()), "source": source, "bills": fetched}; raw_path.write_text(json.dumps(raw, indent=1)); print("fetched live from", source)
    else:
        if "--require-network" in sys.argv: sys.exit(f"could not fetch the bill-status feed ({source}); not falling back to the saved pull because --require-network was given")
        if not raw_path.exists(): sys.exit(f"no network ({source}) and no saved cosponsors_raw.json")
        raw = json.loads(raw_path.read_text()); print(f"network unavailable ({source}); using saved pull from {raw['fetched']} ({raw['source'][:60]}...)")
    legis = json.load(open(find("legislators-current.json")))
    members, district_map, senators = {}, {}, {}
    for l in legis:
        t = l["terms"][-1]; bid = l["id"]["bioguide"]; name = l["name"].get("official_full") or f'{l["name"]["first"]} {l["name"]["last"]}'
        party = {"Republican": "R", "Democrat": "D"}.get(t["party"], "I")
        members[bid] = {"name": name, "party": party, "state": t["state"], "chamber": t["type"], "district": t.get("district")}
        if t["type"] == "rep" and t["state"] in STFIPS:
            d = t.get("district") or 0; district_map[f"{STFIPS[t['state']]}{(98 if t['state'] == 'DC' else d):02d}"] = bid
        elif t["type"] == "sen": senators.setdefault(t["state"], []).append(bid)
    bills, by_member, former = {}, {}, []
    for b in BILLS:
        r = raw["bills"][b["key"]]; sp = r["sponsor"]["bioguide"]
        bills[b["key"]] = {**{k: b[k] for k in ("congress", "type", "number", "topic", "label", "short")}, "title": r["title"], "short_title": r.get("short_title", ""), "introduced": r["introduced"], "latest_action": r["latest_action"],
                           "sponsor": sp, "n_cosponsors": len(r["cosponsors"]), "n_original": sum(1 for _, d in r["cosponsors"] if d == r["introduced"]),
                           "parties": {p: sum(1 for c, _ in r["cosponsors"] if members.get(c, {}).get("party") == p) for p in ("R", "D", "I")},
                           "url": f"https://www.congress.gov/bill/{b['congress']}th-congress/{'house' if b['type'] == 'hr' else 'senate'}-bill/{b['number']}",
                           "cosponsors_url": f"https://www.congress.gov/bill/{b['congress']}th-congress/{'house' if b['type'] == 'hr' else 'senate'}-bill/{b['number']}/cosponsors"}
        by_member.setdefault(sp, {})[b["key"]] = {"role": "sponsor", "date": r["introduced"]}
        for c, d in r["cosponsors"]:
            by_member.setdefault(c, {})[b["key"]] = {"role": "original" if d == r["introduced"] else "cosponsor", "date": d}
        for bid in [sp] + [c for c, _ in r["cosponsors"]]:
            if bid not in members: former.append(bid); members[bid] = {"name": r["sponsor"]["name"] if bid == sp else bid, "party": "", "state": "", "chamber": "", "district": None, "former": True}
    out = {"meta": {"fetched": raw["fetched"], "source": raw["source"], "built": str(date.today()), "members_file": "legislators-current.json", "topics": TOPICS, "former_members": sorted(set(former)),
                    "note": "Cosponsorship as recorded in the Library of Congress bill status feed on the fetch date. Members who withdrew are excluded. Verify on congress.gov before citing in a meeting."},
           "bills": bills, "members": members, "by_member": by_member, "district_map": district_map, "senators": senators}
    s = json.dumps(out, separators=(",", ":"), ensure_ascii=False); (docs_dir() / "cosponsors.js").write_text("window.COSPONSORS=" + s + ";", encoding="utf-8")
    for k, v in bills.items(): print(f"{v['label']:10s} {v['short']:34s} sponsor {members[v['sponsor']]['name']:24s} cosponsors {v['n_cosponsors']:3d} (R {v['parties']['R']}, D {v['parties']['D']})  latest {v['latest_action']['date']}")
    print("cosponsors.js KB", len(s) // 1024, "| former members flagged:", sorted(set(former)) or "none")


if __name__ == "__main__":
    main()
