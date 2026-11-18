#!/usr/bin/env python3
"""Browser check of the pages a visitor uses: do the main buttons, links, lists and downloads work, on the data in docs/?

It opens the site in a real browser (Chromium, through Playwright) and does what a visitor does: opens the map, presses its main
buttons, opens a county, its trials and its sites, downloads a file and an image, looks trials up by ZIP code, and loads every other
page at phone and laptop width. It exists because the automatic checks guarded the numbers and nothing guarded the controls: two of
the map's main buttons did nothing for twelve days in November 2026 before a reviewer pressed them.

Every expectation follows the data in docs/ (a count is read from the page's own data and compared with what the page shows), so a
registry refresh cannot make it fail by moving a number. The question box's server is never called: requests to it are blocked.

    python3 tests/browser_check.py                 # serves docs/ itself on a free port
    python3 tests/browser_check.py http://host/    # or checks a site that is already being served
Exit code 1 if any check fails. Needs: pip install playwright; playwright install chromium (or set CHROME to a browser's path).
"""
import asyncio, functools, http.server, os, re, socket, sys, threading
from pathlib import Path
from playwright.async_api import async_playwright

DOCS = Path(__file__).resolve().parent.parent / "docs"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail)); print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def serve():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DOCS)); handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}/"


BAD_TEXT = re.compile(r"\bundefined\b|\bNaN\b|\[object Object\]")
PAGES = ["index.html", "findings.html", "find.html", "learn.html", "methods.html", "about.html", "api.html", "act.html", "community.html", "brief.html", "404.html"]


async def main(base):
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.environ.get("CHROME") or None, args=["--no-sandbox"])
        errors = []

        async def new_page(width=1440, height=900, js=True, downloads=False):
            ctx = await browser.new_context(viewport={"width": width, "height": height}, java_script_enabled=js, accept_downloads=downloads)
            await ctx.route(re.compile(r"workers\.dev"), lambda r: r.abort())          # the question box's server is never called
            pg = await ctx.new_page(); pg.on("pageerror", lambda e: errors.append(f"{pg.url.split('/')[-1][:60]}: {str(e)[:160]}")); return pg

        async def text(pg): return await pg.inner_text("body")

        # ------------------------------------------------------------------ the map
        m = await new_page(downloads=True)
        await m.goto(base + "map.html"); await m.wait_for_function("window.DATA && document.querySelectorAll('#map path').length > 3000", timeout=60000); await m.wait_for_timeout(1500)
        check("map: opens and draws the counties", True, f"{await m.evaluate('document.querySelectorAll(\"#map path\").length')} shapes")
        t = await text(m); check("map: the opening panel shows a headline share", re.search(r"\d\.\d%", t) is not None)
        check("map: no 'undefined' or 'NaN' in the opening view", not BAD_TEXT.search(t), (BAD_TEXT.search(t) or [""])[0])
        for sel, label in (("#st-d", "Browse states and districts"), ("#st-c", "Find a county")):
            if await m.locator(sel).count():
                await m.locator(sel).first.click(); await m.wait_for_timeout(400)
                opened = await m.evaluate("(() => { const e = document.getElementById('explore-pop'); return !!e && !e.hidden && getComputedStyle(e).display !== 'none'; })()")
                focus = await m.evaluate("document.activeElement.id")
                check(f"map: the '{label}' button opens the picker", opened and focus.startswith("pick-"), f"menu open {opened}, focus on {focus or 'nothing'}")
                await m.keyboard.press("Escape"); await m.wait_for_timeout(200)
            else: check(f"map: the '{label}' button exists", False, f"{sel} not found")

        # a county that has trials and sites, chosen from the data: the one with the most trials
        cf = await m.evaluate("Object.entries(DATA.counties).sort((a, b) => b[1].t - a[1].t)[0][0]")
        want = await m.evaluate(f"(() => {{ const c = DATA.counties['{cf}']; return {{ t: c.t, f: c.f, name: c.n }}; }})()")
        await m.goto(base + f"map.html?c={cf}&lt=1"); await m.wait_for_function("document.querySelector('#pane-body') && document.querySelector('#pane-body').innerText.length > 200", timeout=60000); await m.wait_for_timeout(1200)
        t = await m.inner_text("#pane-body")
        check("map: a county link opens that county's panel", want["name"].split(" ")[0] in t, want["name"])
        check("map: the county panel shows the county's trial count from the data", f"{want['t']:,}" in t, f"{want['t']:,} trials")
        check("map: no 'undefined' or 'NaN' in the county panel", not BAD_TEXT.search(t))
        await m.goto(base + f"map.html?c={cf}&lt=1&tab=trials"); await m.wait_for_selector("#tr-table tr", timeout=60000); await m.wait_for_timeout(800)
        n_rows = await m.locator("#tr-table tbody tr").count(); cnt = await m.inner_text("#tr-count")
        check("map: the Trials tab lists the county's trials", n_rows > 0 and f"{want['t']:,}" in cnt, f"{n_rows} rows shown; header says '{cnt.strip()[:40]}'")
        async with m.expect_download(timeout=30000) as d: await m.click("#tr-csv")
        lines = Path(await (await d.value).path()).read_text(encoding="utf-8-sig").strip().split("\n")
        check("map: the Trials CSV download has one line per trial", len(lines) - 2 == want["t"], f"{len(lines) - 2} data lines for {want['t']:,} trials")
        await m.goto(base + f"map.html?c={cf}&lt=1&tab=sites"); await m.wait_for_selector("#si-table tr", timeout=60000); await m.wait_for_timeout(800)
        cnt = await m.inner_text("#si-count")
        check("map: the Sites tab lists the county's sites", await m.locator("#si-table tbody tr").count() > 0 and f"{want['f']:,}" in cnt, cnt.strip()[:50])
        async with m.expect_download(timeout=30000) as d: await m.click("#si-csv")
        lines = Path(await (await d.value).path()).read_text(encoding="utf-8-sig").strip().split("\n")
        check("map: the Sites CSV download has one line per site", len(lines) - 2 == want["f"], f"{len(lines) - 2} data lines for {want['f']:,} sites")

        # every cut-off and every unit loads, and the selection's veil stays under the circles
        for q in ("?lt=1", "?lt=20", "?lt=5", "?lt=100", "?u=district&lt=1", "?u=state&lt=20", "?tab=changes&lt=1", "?tab=burden&lt=1", "?tab=compare&lt=1", "?lt=1&type=breast", "?m=inc&lt=1", "?m=onc&lt=1"):
            before = len(errors); await m.goto(base + "map.html" + q); await m.wait_for_function("window.DATA && document.querySelectorAll('#map path').length > 50", timeout=60000); await m.wait_for_timeout(2500)
            t = await text(m); check(f"map: view {q} loads cleanly", len(errors) == before and not BAD_TEXT.search(t), (errors[-1] if len(errors) > before else (BAD_TEXT.search(t) or [""])[0]))
        st = await m.evaluate("Object.keys(DATA.state_data || {}).includes('TX') ? 'TX' : Object.keys(DATA.state_data || {})[0]")
        for lt in ("1", "5"):
            await m.goto(base + f"map.html?s={st}&lt={lt}"); await m.wait_for_selector("path.veil", state="attached", timeout=60000); await m.wait_for_timeout(5000)
            above = await m.evaluate("(() => { const v = document.querySelector('path.veil'); const sib = [...v.parentNode.children]; return sib.slice(sib.indexOf(v) + 1).filter(e => e.querySelectorAll('circle').length).length; })()")
            check(f"map: a selected state stands out at cut-off {lt} (no circles drawn over the veil)", above == 0, f"{above} circle layers above it")
        await m.goto(base + f"map.html?s={st}&lt=1"); await m.wait_for_timeout(3500); await m.click("#btn-more"); await m.wait_for_timeout(300)
        async with m.expect_download(timeout=60000) as d: await m.click("#btn-png")
        size = Path(await (await d.value).path()).stat().st_size
        check("map: 'Download this view as an image' gives an image", size > 20000, f"{size // 1024} KB")

        # the search box: a county name typed in finds the county
        await m.goto(base + "map.html"); await m.wait_for_function("window.DATA && document.querySelectorAll('#map path').length > 3000", timeout=60000); await m.wait_for_timeout(1500)
        await m.fill("#q", want["name"]); await m.wait_for_timeout(1200)
        hits = await m.locator("#q-list > *").count()
        check("map: typing a county name in the search box offers it", hits > 0, f"{hits} suggestions for '{want['name']}'")

        # phone width: the page fits and the panel is reachable
        ph = await new_page(390, 800); await ph.goto(base + f"map.html?c={cf}&lt=1"); await ph.wait_for_timeout(5000)
        over = await ph.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("map: no sideways scroll on a phone", over <= 2, f"{over}px")

        # ------------------------------------------------------------------ the ZIP finder
        f = await new_page()
        await f.goto(base + "find.html"); await f.wait_for_function("window.DATA && window.FIND", timeout=60000)
        # a ZIP code with trials nearby, from the data: the ZIP of the busiest site point
        z = await f.evaluate("(() => { let best = '', n = 0; DATA.SPX.forEach(ents => ents.forEach(e => { if (/^\\d{5}$/.test(e[0]) && e[1].length > n) { n = e[1].length; best = e[0]; } })); return best; })()")
        await f.goto(base + f"find.html?zip={z}&mi=25"); await f.wait_for_selector(".card", timeout=60000); await f.wait_for_timeout(800)
        n_cards = await f.locator(".card").count(); head = (await f.locator(".summary").first.inner_text()).split("\n")[0]
        total = int(re.sub(r"[^\d]", "", (re.search(r"([\d,]+) recruiting", head) or ["", "0"])[1]) or 0)
        check("ZIP finder: a ZIP code with sites nearby lists trials", n_cards > 0 and total > 0, f"ZIP {z}: {head[:60]}")
        href = await f.locator(".card a[href*='clinicaltrials.gov']").first.get_attribute("href")
        check("ZIP finder: each trial links to its registry record", bool(href) and re.search(r"NCT\d{8}", href) is not None, href or "no link")
        nct = re.search(r"NCT\d{8}", href or "").group(0) if href else ""
        await f.goto(base + f"find.html?zip={z}&mi=25&q={nct}"); await f.wait_for_timeout(2500)
        check("ZIP finder: an NCT number typed in the search finds that trial", await f.locator(".card").count() == 1, f"{nct}: {await f.locator('.card').count()} result(s)")
        await f.goto(base + f"find.html?zip={z}&mi=25&q=MET"); await f.wait_for_timeout(2500)
        head2 = (await f.locator(".summary").first.inner_text()).split("\n")[0]; n_met = int(re.sub(r"[^\d]", "", (re.search(r"([\d,]+) recruiting", head2) or ["", "0"])[1]) or 0)
        check("ZIP finder: a gene name matches whole words (MET is not 'metastatic')", n_met < total / 5, f"MET: {n_met} of {total}")
        if total > 50:
            await f.goto(base + f"find.html?zip={z}&mi=25"); await f.wait_for_selector(".card", timeout=60000); await f.emulate_media(media="print")
            check("ZIP finder: the printed handout says when it lists only the nearest trials", await f.locator(".print-note").first.is_visible())
            await f.emulate_media(media="screen")
        await f.goto(base + "find.html?zip=00000"); await f.wait_for_timeout(2000); t = await text(f)
        check("ZIP finder: an unknown ZIP code gets a plain message", await f.locator(".card").count() == 0 and not BAD_TEXT.search(t) and len(await f.locator(".empty, .summary").all_inner_texts()) > 0)
        # a site whose registry city and ZIP disagree carries its note (only when the data hold such a site)
        dz = await f.evaluate("(() => { for (const ents of DATA.SPX) for (const e of ents) if (e[3] && /^\\d{5}$/.test(e[0])) return e[0]; return ''; })()")
        if dz:
            await f.goto(base + f"find.html?zip={dz}&mi=10"); await f.wait_for_timeout(3000)
            check("ZIP finder: a site whose city and ZIP disagree shows the 'check this address' note", await f.locator(".doubt, .doubt-in").count() > 0, f"ZIP {dz}")

        # ------------------------------------------------------------------ every other page, at phone and laptop width
        for width in (390, 1280):
            pg = await new_page(width, 900)
            for name in PAGES + [f"trials.html?county={cf}", f"community.html?c={cf}", f"brief.html?c={cf}", f"act.html?c={cf}"]:
                before = len(errors); await pg.goto(base + name); await pg.wait_for_timeout(1800 if "brief" not in name else 2600)
                t = await text(pg); over = await pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                h1 = await pg.locator("h1").count()
                ok = len(errors) == before and not BAD_TEXT.search(t) and over <= 2 and h1 >= 1 and len(t) > 300
                check(f"{name} at {width}px: loads, has a heading, fits the screen", ok, "" if ok else f"errors {len(errors) - before}, bad text {(BAD_TEXT.search(t) or [''])[0]!r}, sideways {over}px, h1 {h1}, {len(t)} characters")

        # links in the header, the footer and the homepage's body point at pages that exist
        pg = await new_page(); await pg.goto(base + "index.html"); await pg.wait_for_timeout(1500)
        hrefs = sorted(set(await pg.evaluate("[...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')).filter(h => h && !/^(https?:|mailto:|tel:|#)/.test(h)).map(h => h.split('#')[0].split('?')[0]).filter(Boolean)")))
        missing = [h for h in hrefs if not (DOCS / h).exists()]
        check("homepage: every internal link points at a page that exists", not missing, f"{len(hrefs)} links" + (f"; missing {missing}" if missing else ""))

        # the homepage and Key findings show the same figures with JavaScript off
        for name in ("index.html", "findings.html"):
            on = await new_page(); await on.goto(base + name); await on.wait_for_timeout(2000)
            off = await new_page(js=False); await off.goto(base + name); await off.wait_for_timeout(800)
            grab = "[...document.querySelectorAll('[data-f]')].map(e => e.getAttribute('data-f') + '=' + e.textContent.trim())"
            a, b = await on.evaluate(grab) if True else [], None
            b = [f"{await e.get_attribute('data-f')}={(await e.text_content()).strip()}" for e in await off.locator("[data-f]").all()]
            check(f"{name}: the figures are the same with JavaScript off", a == b and len(a) > 5, f"{len(a)} figures" + ("" if a == b else f"; first difference: {next((x, y) for x, y in zip(a, b) if x != y) if len(a) == len(b) else (len(a), len(b))}"))

        # the question box: with its server unreachable the visitor gets a sentence, never a raw error
        qb = await new_page(1280, 900); await qb.goto(base + "map.html"); await qb.wait_for_function("window.DATA", timeout=60000); await qb.wait_for_timeout(2500)
        await qb.fill("#q", "Which counties in Texas have no trial within 60 miles?"); await qb.keyboard.press("Enter"); await qb.wait_for_timeout(4000)
        t = await text(qb)
        check("question box: an unreachable server gives a plain sentence, not a raw error", not re.search(r"TypeError|Failed to fetch|\bundefined\b|at \w+ \(|Error:", t))

        check("no script error on any page during the whole check", not errors, "; ".join(errors[:4]))
        await browser.close()
    bad = [r for r in RESULTS if not r[1]]
    print(f"\nbrowser check: {len(RESULTS) - len(bad)} of {len(RESULTS)} pass" + ("" if not bad else "; FAILED: " + "; ".join(r[0] for r in bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else serve())))
