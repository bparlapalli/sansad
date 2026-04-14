"""
scrapers/parliament/playwright_scraper.py  —  v1.0
ParamaSrota Parliament Intelligence

Scrapes eparlib.sansad.in (Parliament Digital Library) using a real
Chromium browser via Playwright.  A plain requests-based scraper is blocked
by the site (HTTP 403 / bot detection); Playwright presents a full browser
fingerprint and session, which the site accepts.

───────────────────────────────────────────────────────────────────────────────
Site structure (DSpace — no REST API or OAI-PMH exposed)
───────────────────────────────────────────────────────────────────────────────
  Collection browse page : /handle/123456789/{handle}?offset={N}
      Lists 20 items per page.  Each row: Date | Title | Type | View link.
      "View" link href = /handle/123456789/{doc_id}?view_type=browse
      Paginate with ?offset=20, ?offset=40, … until no "next >" link.

  Item detail page       : /handle/123456789/{doc_id}
      Shows a "Files in This Item" table with the exact PDF filename and a
      bitstream download link.

  Bitstream download URL : /bitstream/123456789/{doc_id}/1/{filename}
      Direct PDF link; only works when fetched from a browser session that
      has already visited the item page (referrer check).

───────────────────────────────────────────────────────────────────────────────
Three-phase workflow  (all phases are independently re-runnable / idempotent)
───────────────────────────────────────────────────────────────────────────────
  Phase 1  --catalog   Scrape browse pages → store doc_id + date + title in
                       the `catalog` DB table.  FAST: ~1 request / 20 items.
                       6,458 debate items ≈ 323 pages ≈ 10–12 minutes.

  Phase 2  --resolve   Visit each item detail page → record exact filename
                       and bitstream URL.  Slower: 1 request / item.
                       Run with --limit to do this incrementally.

  Phase 3  --download  Trigger browser downloads for resolved entries.
                       Uses JS to click a synthetic <a download> element so
                       Playwright's download handler can intercept and save.
                       Supports --from / --to date filters and --limit.

───────────────────────────────────────────────────────────────────────────────
Setup (one-time)
───────────────────────────────────────────────────────────────────────────────
  pip install playwright
  playwright install chromium

  A persistent browser profile is stored at .playwright_profile/ so that
  cookies and session state are reused across runs.

───────────────────────────────────────────────────────────────────────────────
Usage
───────────────────────────────────────────────────────────────────────────────
  # Build catalog for default collections (debates + presidential + budget + pm)
  python scrapers/parliament/playwright_scraper.py --catalog

  # Specific collections only
  python scrapers/parliament/playwright_scraper.py --catalog --collections debates presidential budget

  # Resolve filenames for most-recent 200 unresolved entries
  python scrapers/parliament/playwright_scraper.py --resolve --limit 200

  # Download up to 30 PDFs from 2024 onwards
  python scrapers/parliament/playwright_scraper.py --download --from 2024-01-01 --limit 30

  # Full pipeline in one shot (catalog → resolve → download, capped at 20)
  python scrapers/parliament/playwright_scraper.py --catalog --resolve --download --collections debates --limit 20

  # Status dashboard
  python scrapers/parliament/playwright_scraper.py --status
"""

import sys
import asyncio
import re
import sqlite3
import time
import random
import argparse
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection, init_db, sync_db

# ── Collection registry ───────────────────────────────────────────────────────
# Maps a short CLI name → (DSpace handle, human label, scrape priority)
#
# Handles were discovered by browsing /community-list on eparlib.sansad.in.
# Priority 1 = scrape first / most important; 5 = historical / low priority.
#
# The "debates" collection (handle 7) is the canonical full-text index of all
# Lok Sabha debates from 1952 onwards and contains 6,458+ items.
# debates_en / debates_hi / debates_ucd are sub-collections of the same PDFs
# partitioned by language/version — scraping "debates" alone is usually enough.
COLLECTIONS = {
    # ── Lok Sabha Debates ─────────────────────────────────────────────────────
    # "debates" is the master list; the others are filtered sub-views.
    # Prefer debates_ucd for recent sessions — UCD (Uncorrected) files are
    # published within days of a sitting; corrected lsd files follow weeks later.
    "debates":        ("7",        "Lok Sabha Debates (Text)",          1),
    "debates_en":     ("2963706",  "Lok Sabha Debates (English)",       2),
    "debates_hi":     ("796090",   "Lok Sabha Debates (Hindi)",         3),
    "debates_ucd":    ("2953354",  "Lok Sabha Debates (Uncorrected)",   2),

    # ── Parliamentary Documents ───────────────────────────────────────────────
    # presidential: President addresses both Houses at the start of each LS
    #               and at the first session of each year. 181 items from 1950.
    # budget:       General + Railway budget speeches. Key for finance tracking.
    # committee:    All-party parliamentary committee reports.
    # resume:       Per-session "Resume of Work Done" — useful for session metadata.
    # bulletin1/2:  Daily business notices and procedural documents.
    # pm_speeches:  PM speeches delivered in Parliament.
    "presidential":   ("14",       "Presidential Addresses",            1),
    "budget":         ("12",       "Budget Speeches",                   1),
    "committee":      ("13",       "Parliamentary Committee Reports",   2),
    "resume":         ("785924",   "Resume of Work Done by Lok Sabha",  3),
    "bulletin1":      ("795919",   "Lok Sabha Bulletin I",              3),
    "bulletin2":      ("1933333",  "Lok Sabha Bulletin II",             3),
    "pm_speeches":    ("800962",   "PM Speeches",                       2),

    # ── Questions ─────────────────────────────────────────────────────────────
    # Question Hour transcripts, split into starred (Q&A) and unstarred (other).
    "questions_p1":   ("9",        "Questions Part 1 (Q&A)",            3),
    "questions_p2":   ("10",       "Questions Part 2 (Other)",          3),

    # ── Historical (1st–17th Lok Sabha, 1952–2019) ────────────────────────────
    # Large collections; scrape only if deep historical research is needed.
    "historical":     ("3",        "Historical Debates",                5),
    "constituent":    ("4",        "Constituent Assembly Debates",      5),
}

# Collections scraped when --collections is not specified.
# Covers the most analytically valuable document types for current sessions.
DEFAULT_COLLECTIONS = ["debates", "presidential", "budget", "pm_speeches"]

BASE_URL  = "https://eparlib.sansad.in"
PDF_DIR   = _ROOT / "pdfs"
PDF_DIR.mkdir(exist_ok=True)


# ── Date parsing ──────────────────────────────────────────────────────────────

_MONTH_MAP = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def parse_date(raw: str) -> str | None:
    """Convert '6-Feb-2026' → '2026-02-06'. Returns None if unparseable."""
    raw = raw.strip()
    # Try DD-Mon-YYYY
    m = re.match(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", raw)
    if m:
        d, mon, y = m.groups()
        month = _MONTH_MAP.get(mon.capitalize())
        if month:
            return f"{y}-{month}-{int(d):02d}"
    # Try YYYY-MM-DD passthrough
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    return None


# ── DB helpers ────────────────────────────────────────────────────────────────

def upsert_catalog_items(items: list[dict]) -> int:
    """Insert/ignore a batch of catalog items. Returns count of new rows."""
    if not items:
        return 0
    conn = get_connection()
    c = conn.cursor()
    added = 0
    for item in items:
        c.execute("""
            INSERT OR IGNORE INTO catalog
                (doc_id, collection_handle, collection_name,
                 item_date, item_date_raw, title, language)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            item["doc_id"],
            item["collection_handle"],
            item["collection_name"],
            item.get("item_date"),
            item.get("item_date_raw"),
            item.get("title"),
            item.get("language"),
        ))
        if c.rowcount:
            added += 1
    conn.commit()
    conn.close()
    sync_db()
    return added


def update_catalog_filename(doc_id: int, filename: str, bitstream_url: str,
                            language: str | None = None,
                            debate_type: str | None = None,
                            lok_sabha_no: int | None = None,
                            session_no: int | None = None,
                            session_no_raw: str | None = None):
    conn = get_connection()
    conn.execute("""
        UPDATE catalog SET
            filename      = ?,
            bitstream_url = ?,
            language      = COALESCE(?, language),
            debate_type   = COALESCE(?, debate_type),
            lok_sabha_no  = COALESCE(?, lok_sabha_no),
            session_no    = COALESCE(?, session_no),
            session_no_raw= COALESCE(?, session_no_raw)
        WHERE doc_id = ?
    """, (filename, bitstream_url, language, debate_type,
          lok_sabha_no, session_no, session_no_raw, doc_id))
    conn.commit()
    conn.close()
    sync_db()


def mark_downloaded(doc_id: int, local_path: str):
    conn = get_connection()
    conn.execute("""
        UPDATE catalog
        SET downloaded = 1, local_path = ?, downloaded_at = datetime('now')
        WHERE doc_id = ?
    """, (local_path, doc_id))
    conn.commit()
    conn.close()
    sync_db()


def get_unresolved(limit: int = 100, collection_handles: list[str] = None) -> list[sqlite3.Row]:
    """Catalog entries with no filename yet."""
    conn = get_connection()
    c = conn.cursor()
    if collection_handles:
        placeholders = ",".join("?" * len(collection_handles))
        c.execute(f"""
            SELECT doc_id, collection_handle, collection_name, item_date, title
            FROM catalog WHERE filename IS NULL
              AND collection_handle IN ({placeholders})
            ORDER BY item_date DESC NULLS LAST
            LIMIT ?
        """, (*collection_handles, limit))
    else:
        c.execute("""
            SELECT doc_id, collection_handle, collection_name, item_date, title
            FROM catalog WHERE filename IS NULL
            ORDER BY item_date DESC NULLS LAST
            LIMIT ?
        """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_pending_downloads(limit: int = 50, from_date: str = None,
                          to_date: str = None,
                          collection_handles: list[str] = None) -> list[sqlite3.Row]:
    """Catalog entries that have a filename but haven't been downloaded."""
    conn = get_connection()
    c = conn.cursor()
    filters = ["filename IS NOT NULL", "downloaded = 0"]
    params: list = []

    if from_date:
        filters.append("item_date >= ?")
        params.append(from_date)
    if to_date:
        filters.append("item_date <= ?")
        params.append(to_date)
    if collection_handles:
        ph = ",".join("?" * len(collection_handles))
        filters.append(f"collection_handle IN ({ph})")
        params.extend(collection_handles)

    where = " AND ".join(filters)
    params.append(limit)
    c.execute(f"""
        SELECT doc_id, collection_handle, collection_name,
               item_date, title, filename, bitstream_url
        FROM catalog WHERE {where}
        ORDER BY item_date DESC NULLS LAST
        LIMIT ?
    """, params)
    rows = c.fetchall()
    conn.close()
    return rows


def print_status():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT collection_name,
               COUNT(*)                              AS total,
               SUM(CASE WHEN filename IS NOT NULL THEN 1 ELSE 0 END)   AS resolved,
               SUM(downloaded)                       AS downloaded
        FROM catalog
        GROUP BY collection_handle, collection_name
        ORDER BY total DESC
    """)
    rows = c.fetchall()
    conn.close()

    print(f"\n{'='*70}")
    print("📚  Catalog Status")
    print(f"{'='*70}")
    print(f"  {'Collection':<40} {'Total':>6} {'Resolved':>8} {'Downloaded':>10}")
    print(f"  {'-'*40} {'-'*6} {'-'*8} {'-'*10}")
    for r in rows:
        print(f"  {r['collection_name']:<40} {r['total']:>6} "
              f"{r['resolved']:>8} {r['downloaded']:>10}")

    c2 = get_connection().cursor()
    c2.execute("SELECT COUNT(*) as n FROM catalog")
    total = c2.fetchone()["n"]
    print(f"{'='*70}")
    print(f"  Total catalog entries: {total}")
    print(f"{'='*70}\n")


# ── Playwright core ───────────────────────────────────────────────────────────

# ── Playwright helpers ────────────────────────────────────────────────────────

async def _random_delay(lo: float = 0.8, hi: float = 2.5):
    """Randomised pause between requests — reduces chance of rate-limiting."""
    await asyncio.sleep(random.uniform(lo, hi))


async def _wait_for_content(page, timeout: int = 15000):
    """
    Wait for the items table to render.  DSpace pages use a short JS init
    cycle; waiting for at least one <td> ensures the DOM is populated.
    Silently passes if the page has no results (empty collection page).
    """
    try:
        await page.wait_for_selector("table tr td", timeout=timeout)
    except Exception:
        pass


# ── Phase 1: Catalog ──────────────────────────────────────────────────────────

async def scrape_collection_catalog(page, handle: str, collection_name: str,
                                    max_items: int | None = None) -> int:
    """
    Paginate through a DSpace collection's browse pages and upsert every
    discovered item into the `catalog` table.

    Each browse page lists 20 items sorted by date descending.  We step
    through with ?offset=0, ?offset=20, … until either:
      - a page returns no rows (end of collection), or
      - the page has no "next >" link, or
      - we've reached max_items (if set).

    Only the doc_id, date, and title are captured here — the exact filename
    is resolved separately in Phase 2 (--resolve) to keep this phase fast.

    Returns the number of *new* rows added to the catalog (0 = already known).
    """
    total_added = 0
    offset = 0
    page_num = 0

    while True:
        page_num += 1
        url = f"{BASE_URL}/handle/123456789/{handle}?offset={offset}"
        print(f"    Page {page_num} (offset={offset}) ...", end=" ", flush=True)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _wait_for_content(page)
        except Exception as e:
            print(f"⚠ Error loading page: {e}")
            break

        # The items table has columns: Date | Title | Type | View
        # The "View..." link in the last column carries the doc_id in its href:
        #   /handle/123456789/{doc_id}?view_type=browse
        rows = await page.query_selector_all("table tr")
        items = []
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 3:
                continue  # header row or malformed
            date_raw  = (await cells[0].inner_text()).strip()
            title_raw = (await cells[1].inner_text()).strip()
            link = await cells[-1].query_selector("a[href*='/handle/123456789/']")
            if not link:
                continue
            href = await link.get_attribute("href")
            if not href:
                continue
            m = re.search(r"/handle/123456789/(\d+)", href)
            if not m:
                continue
            doc_id = int(m.group(1))
            items.append({
                "doc_id":             doc_id,
                "collection_handle":  handle,
                "collection_name":    collection_name,
                "item_date":          parse_date(date_raw),   # ISO YYYY-MM-DD
                "item_date_raw":      date_raw,               # original "6-Feb-2026"
                "title":              title_raw,
                "language":           None,                   # resolved in Phase 2
            })

        added = upsert_catalog_items(items)
        total_added += added
        print(f"found {len(items)} items, {added} new")

        if not items:
            break  # empty page — past the end of the collection

        # Check for a "next >" pagination link to decide whether to continue
        next_links = await page.query_selector_all("a")
        has_next = any(
            "next" in (await a.inner_text()).lower() and ">" in (await a.inner_text())
            for a in next_links
        )
        if not has_next:
            break
        if max_items and (offset + 20) >= max_items:
            break

        offset += 20
        await _random_delay(1.0, 2.5)

    return total_added


# ── Phase 2: Resolve filenames ────────────────────────────────────────────────

async def resolve_filenames(page, rows: list, verbose: bool = True) -> int:
    """
    For each catalog entry that has no filename yet, visit its item detail
    page to extract the exact PDF filename and bitstream download URL.

    Item detail pages contain a "Files in This Item" table with a link of
    the form:  /bitstream/123456789/{doc_id}/1/{filename.pdf}
    We also read the Language metadata cell to tag items as english/hindi/etc.

    Updates `catalog.filename`, `catalog.bitstream_url`, `catalog.language`.
    Returns the count of successfully resolved entries.
    """
    resolved = 0
    for i, row in enumerate(rows, 1):
        doc_id = row["doc_id"]
        url = f"{BASE_URL}/handle/123456789/{doc_id}"

        if verbose:
            print(f"  [{i}/{len(rows)}] doc_id={doc_id}  {row['item_date'] or '?'} ...",
                  end=" ", flush=True)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            if verbose:
                print(f"⚠ load error: {e}")
            continue

        # Locate the bitstream PDF link — format:
        #   /bitstream/123456789/{doc_id}/1/{filename}.pdf
        links = await page.query_selector_all("a[href*='bitstream']")
        filename = None
        bitstream_url = None
        for link in links:
            href = (await link.get_attribute("href") or "").strip()
            if f"bitstream/123456789/{doc_id}" in href and href.endswith(".pdf"):
                bitstream_url = href if href.startswith("http") else BASE_URL + href
                filename = href.split("/")[-1]
                break

        # Read structured metadata from the label→value table on the item page.
        # Fields we capture: Language, Lok Sabha Number, Session Number, Debate Type.
        # The table alternates label cells ("Language:") with value cells ("Original").
        language       = None
        debate_type    = None
        lok_sabha_no   = None
        session_no     = None
        session_no_raw = None

        meta_cells = await page.query_selector_all("td")
        pending_label = None
        for cell in meta_cells:
            txt = (await cell.inner_text()).strip()
            if pending_label == "language":
                language = txt.lower()
                pending_label = None
            elif pending_label == "lok_sabha":
                try:
                    lok_sabha_no = int(txt)
                except ValueError:
                    pass
                pending_label = None
            elif pending_label == "session":
                session_no_raw = txt  # store raw roman e.g. "VII"
                # Convert roman numeral to integer
                roman_map = {"I":1,"II":2,"III":3,"IV":4,"V":5,"VI":6,
                             "VII":7,"VIII":8,"IX":9,"X":10}
                session_no = roman_map.get(txt.upper())
                pending_label = None
            elif pending_label == "debate_type":
                debate_type = txt.upper()  # normalise to uppercase for consistency
                pending_label = None
            # Detect label cells
            elif txt == "Language:":
                pending_label = "language"
            elif txt in ("Lok Sabha Number:", "Lok Sabha No:"):
                pending_label = "lok_sabha"
            elif txt in ("Session Number:", "Session No:"):
                pending_label = "session"
            elif txt in ("Debate Type:", "Type of Debate:"):
                pending_label = "debate_type"

        if filename:
            update_catalog_filename(
                doc_id, filename, bitstream_url,
                language=language,
                debate_type=debate_type,
                lok_sabha_no=lok_sabha_no,
                session_no=session_no,
                session_no_raw=session_no_raw,
            )
            resolved += 1
            if verbose:
                print(f"✓ {filename}")
        else:
            if verbose:
                print("✗ no PDF link found on item page")

        await _random_delay(0.8, 2.0)

    return resolved


# ── Phase 3: Download ─────────────────────────────────────────────────────────

async def download_pdfs(page, rows: list, verbose: bool = True) -> int:
    """
    Download PDFs for catalog entries that have a resolved filename.

    Direct navigation to a bitstream URL causes an inline PDF viewer, not a
    file download.  Instead we inject a synthetic <a download> element and
    click it — this triggers Playwright's download interception, allowing us
    to save the file to the local pdfs/ directory.

    Files already present on disk are skipped (idempotent).
    The catalog row is updated with local_path + downloaded_at on success.

    Returns the count of successfully downloaded files.
    """
    downloaded = 0

    for i, row in enumerate(rows, 1):
        doc_id   = row["doc_id"]
        filename = row["filename"]
        url      = row["bitstream_url"] or f"{BASE_URL}/bitstream/123456789/{doc_id}/1/{filename}"
        dest     = PDF_DIR / filename

        # Skip if already on disk (e.g. manually placed or re-run)
        if dest.exists():
            print(f"  [{i}/{len(rows)}] Already on disk: {filename}")
            mark_downloaded(doc_id, str(dest))
            downloaded += 1
            continue

        if verbose:
            print(f"  [{i}/{len(rows)}] {filename} ...", end=" ", flush=True)

        try:
            # Inject an <a download> and click it so the browser treats it as
            # a file download rather than inline PDF rendering.
            async with page.expect_download(timeout=120000) as dl_info:
                await page.evaluate(f"""
                    (() => {{
                        const a = document.createElement('a');
                        a.href = '{url}';
                        a.download = '{filename}';
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                    }})()
                """)
            dl = await dl_info.value
            await dl.save_as(str(dest))
            size_kb = dest.stat().st_size // 1024
            mark_downloaded(doc_id, str(dest))
            downloaded += 1
            if verbose:
                print(f"✓ ({size_kb} KB)")
        except Exception as e:
            if verbose:
                print(f"⚠ download failed: {str(e)[:80]}")
            # Fallback: navigate directly — the site may allow it in some cases
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass

        # Longer delay between downloads — files are large and the server
        # is more likely to throttle bulk PDF requests than HTML pages.
        await _random_delay(2.0, 4.0)

    return downloaded


# ── Main entrypoint ───────────────────────────────────────────────────────────

async def run(args):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌  Playwright not installed.")
        print("    pip install playwright && playwright install chromium")
        sys.exit(1)

    init_db()

    if args.status:
        print_status()
        return

    # Resolve collection handles for requested collection names
    if args.collections:
        requested = args.collections
    else:
        requested = DEFAULT_COLLECTIONS

    target_collections = []
    for name in requested:
        if name not in COLLECTIONS:
            print(f"⚠ Unknown collection '{name}'. Available: {', '.join(COLLECTIONS.keys())}")
            continue
        handle, label, _ = COLLECTIONS[name]
        target_collections.append((handle, label))

    async with async_playwright() as pw:
        # Launch real Chromium with a persistent profile (keeps cookies/sessions)
        user_data_dir = _ROOT / ".playwright_profile"
        user_data_dir.mkdir(exist_ok=True)

        browser = await pw.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=args.headless,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
            downloads_path=str(PDF_DIR),
        )
        page = await browser.new_page()

        # ── Phase 1: Catalog ──────────────────────────────────────────────────
        if args.catalog:
            print(f"\n{'='*60}")
            print(f"📋  Catalog Phase — {len(target_collections)} collection(s)")
            print(f"{'='*60}\n")

            total_new = 0
            for handle, label in target_collections:
                print(f"\n▸ {label}  (handle={handle})")
                new = await scrape_collection_catalog(
                    page, handle, label,
                    max_items=args.limit
                )
                total_new += new
                print(f"  → {new} new items added")

            print(f"\n✅ Catalog complete. {total_new} new items discovered total.")

        # ── Phase 2: Resolve filenames ────────────────────────────────────────
        if args.resolve:
            handles = [COLLECTIONS[n][0] for n in requested if n in COLLECTIONS]
            unresolved = get_unresolved(
                limit=args.limit or 500,
                collection_handles=handles if args.collections else None,
            )
            print(f"\n{'='*60}")
            print(f"🔍  Resolve Phase — {len(unresolved)} entries to resolve")
            print(f"{'='*60}\n")

            if not unresolved:
                print("  Nothing to resolve.")
            else:
                n = await resolve_filenames(page, unresolved)
                print(f"\n✅ Resolved {n}/{len(unresolved)} filenames.")

        # ── Phase 3: Download ─────────────────────────────────────────────────
        if args.download:
            handles = [COLLECTIONS[n][0] for n in requested if n in COLLECTIONS]
            pending = get_pending_downloads(
                limit=args.limit or 50,
                from_date=args.from_date,
                to_date=args.to_date,
                collection_handles=handles if args.collections else None,
            )
            print(f"\n{'='*60}")
            print(f"⬇  Download Phase — {len(pending)} PDFs to download")
            print(f"{'='*60}\n")

            if not pending:
                print("  Nothing to download (run --catalog then --resolve first).")
            else:
                n = await download_pdfs(page, pending)
                print(f"\n✅ Downloaded {n}/{len(pending)} PDFs → {PDF_DIR}")

        await browser.close()

    print_status()


def main():
    ap = argparse.ArgumentParser(
        description="Playwright-based eparlib.sansad.in catalog + downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Discover all items in default collections (debates, presidential, budget, pm_speeches)
  python scrapers/parliament/playwright_scraper.py --catalog

  # Discover only debate PDFs
  python scrapers/parliament/playwright_scraper.py --catalog --collections debates

  # Discover everything
  python scrapers/parliament/playwright_scraper.py --catalog --collections debates debates_en debates_hi debates_ucd presidential budget committee pm_speeches

  # Resolve filenames for top 200 unresolved entries
  python scrapers/parliament/playwright_scraper.py --resolve --limit 200

  # Download last 30 debate PDFs
  python scrapers/parliament/playwright_scraper.py --download --collections debates --limit 30

  # Full pipeline for recent debates
  python scrapers/parliament/playwright_scraper.py --catalog --resolve --download --collections debates --limit 20

  # Show catalog status
  python scrapers/parliament/playwright_scraper.py --status

Collections available:
  """ + "\n  ".join(f"{k:<20} {v[1]}" for k, v in COLLECTIONS.items()),
    )

    ap.add_argument("--catalog",     action="store_true", help="Scrape browse pages to build catalog")
    ap.add_argument("--resolve",     action="store_true", help="Fetch item pages to get exact filenames")
    ap.add_argument("--download",    action="store_true", help="Download PDFs for resolved entries")
    ap.add_argument("--status",      action="store_true", help="Show catalog status and exit")

    ap.add_argument("--collections", nargs="+",  metavar="NAME",
                    help=f"Collections to target (default: {' '.join(DEFAULT_COLLECTIONS)})")
    ap.add_argument("--limit",       type=int,   default=None,
                    help="Max items to process per phase")
    ap.add_argument("--from",        dest="from_date", metavar="YYYY-MM-DD",
                    help="Only download items on or after this date")
    ap.add_argument("--to",          dest="to_date",   metavar="YYYY-MM-DD",
                    help="Only download items on or before this date")
    ap.add_argument("--headless",    action="store_true", default=False,
                    help="Run browser in headless mode (default: visible)")

    args = ap.parse_args()

    if not any([args.catalog, args.resolve, args.download, args.status]):
        ap.print_help()
        sys.exit(0)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
