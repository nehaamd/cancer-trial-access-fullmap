"""Render assets/og-image.png (the 1200x630 card shown when a link is shared) and assets/map-national.png (the clean
national map used on the Key findings page) from the current data. Needs Playwright with Chromium; re-run after a data refresh.
    pip install playwright && playwright install chromium && python3 make_assets.py"""
import subprocess, sys, time, socket
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parent
def free_port():
    s = socket.socket(); s.bind(("", 0)); p = s.getsockname()[1]; s.close(); return p
port = free_port(); srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.2)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 630}); pg.goto(f"http://localhost:{port}/assets/og-template.html", wait_until="networkidle"); pg.wait_for_timeout(800)
        pg.screenshot(path=str(ROOT / "assets" / "og-image.png")); pg.close()
        pg = b.new_page(viewport={"width": 1600, "height": 1000}); pg.goto(f"http://localhost:{port}/assets/og-template.html?plain", wait_until="networkidle"); pg.wait_for_timeout(800)
        pg.screenshot(path=str(ROOT / "assets" / "map-national.png")); pg.close()
        for size, name in [(32, "favicon-32.png"), (180, "apple-touch-icon.png"), (512, "icon-512.png")]:
            pg = b.new_page(viewport={"width": size, "height": size}); pg.set_content(f'<html><body style="margin:0"><img src="http://localhost:{port}/assets/favicon.svg" width="{size}" height="{size}" style="display:block"></body></html>'); pg.wait_for_timeout(200)
            pg.screenshot(path=str(ROOT / "assets" / name), omit_background=True); pg.close()
        b.close()
finally:
    srv.terminate()
try:  # shrink the two large PNGs to a small palette (flat colours; no visible loss)
    from PIL import Image
    for n, k in (("og-image.png", 128), ("map-national.png", 64)):
        f = ROOT / "assets" / n; Image.open(f).convert("P", palette=Image.ADAPTIVE, colors=k).save(f, optimize=True)
except ImportError:
    pass
print("wrote assets/og-image.png, assets/map-national.png and the favicon PNGs")
