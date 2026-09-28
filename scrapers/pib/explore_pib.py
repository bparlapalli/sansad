"""
scrapers/pib/explore_pib.py — Diagnostic probe of PIB's press release archive.

This is NOT a production scraper. pib.gov.in blocks plain HTTP requests
(same as eparlib), and its page structure hasn't been verified against a
real render yet — this script's job is to load the page with a real browser
(Playwright, same approach as scrapers/parliament/playwright_scraper.py),
try a few plausible ways of finding the release list, and dump whatever it
finds so we can see the ACTUAL structure before writing a real scraper
against guessed selectors.

Usage:
    python scrapers/pib/explore_pib.py
    python scrapers/pib/explore_pib.py --url "https://www.pib.gov.in/PressReleasePage.aspx?PRID=..."

Output: prints a summary to the console AND writes the full rendered HTML
to scrapers/pib/_probe_output.html so it can be inspected directly.
"""

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

_HERE = Path(__file__).resolve().parent

DEFAULT_URL = "https://www.pib.gov.in/PressReleasePage.aspx"
# Alternates worth trying if the default doesn't show a list:
#   https://www.pib.gov.in/allRel.aspx
#   https://www.pib.gov.in/AllReleasem.aspx?reg=3&lang=1   (English)
#   https://www.pib.gov.in/AllReleasem.aspx?reg=48&lang=2  (Hindi)


async def probe(url: str, headless: bool):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        print(f"Loading {url} ...")
        await page.goto(url, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(2000)  # let any JS-rendered content settle

        title = await page.title()
        print(f"Page title: {title}")

        # Try a few plausible containers for a press-release list.
        candidates = {
            "table rows":        "table tr",
            "list items":        "li",
            "release links":     "a[href*='PressRelease']",
            "release links alt": "a[href*='PRID']",
        }
        for label, selector in candidates.items():
            els = await page.query_selector_all(selector)
            print(f"  {label} ({selector!r}): {len(els)} found")
            if els:
                for el in els[:5]:
                    text = (await el.inner_text()).strip().replace("\n", " ")[:120]
                    if text:
                        print(f"    - {text}")

        html = await page.content()
        out_path = _HERE / "_probe_output.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"\nFull rendered HTML saved to {out_path} — open it or paste a chunk back "
              f"so we can write real selectors against it.")

        await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--headless", action="store_true", default=False)
    args = ap.parse_args()
    asyncio.run(probe(args.url, args.headless))
