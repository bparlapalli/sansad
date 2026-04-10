"""
scraper.py — Downloads Lok Sabha debate PDFs from eparlib.sansad.in

URL pattern:
  https://eparlib.sansad.in/bitstream/123456789/{doc_id}/1/{filename}

Two filename patterns:
  UCD_{ls}_{session}_{DD-MM-YYYY}_Fullday.pdf  ← uncorrected debates (released quickly)
  lsd_{ls}_{roman_session}_{DD-MM-YYYY}.pdf    ← final edited version (released later)

We try both patterns per date. UCD is usually available first.

Doc-ID estimation:
  DSpace IDs are roughly sequential by upload date but not perfectly linear.
  We use confirmed anchors from sessions_data.py and interpolate based on
  calendar days to the nearest anchor. A probe then searches ±100 IDs around
  the estimate to find the exact match.

Confirmed anchors (date → doc_id):
  2024-08-01 → 2981286  (lsd_18_II_01-08-2024.pdf)
  2025-03-19 → 2989556  (UCD_18_4_19-03-2025_Fullday.pdf)
  2025-04-01 → 2990867  (lsd_18_IV_01-04-2025.pdf)
"""

import time
import random
import sqlite3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path
from datetime import datetime

from db import get_connection, init_db
from sessions_data import ALL_SESSIONS, DOC_ID_ANCHORS, SESSION_ROMAN, closest_anchor, find_session_for_date

# ── Config ────────────────────────────────────────────────────────────────────
PDF_DIR  = Path(__file__).parent / "pdfs"
PDF_DIR.mkdir(exist_ok=True)

BASE_URL     = "https://eparlib.sansad.in/bitstream/123456789"
REFERER_BASE = "https://eparlib.sansad.in/handle/123456789/7"

# Realistic browser headers — rotate User-Agent to avoid fingerprinting
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

# IDs per calendar day — estimated from confirmed anchors:
#   Aug 1 2024 → Mar 19 2025: (2989556 - 2981286) / 230 days ≈ 35.9 ids/day
#   Mar 19 2025 → Apr 1 2025: (2990867 - 2989556) / 13 days ≈ 100.8 ids/day
# Average ≈ 40 ids/day (upload bursts make it uneven; probe handles the slack)
IDS_PER_DAY  = 40
PROBE_RADIUS = 150   # search ±150 around estimate — kept smaller to limit requests
PROBE_STEP   = 25    # jump in steps of 25 (vs old 10) — far fewer total probes

# Delay ranges (seconds) — randomised to look human
DELAY_BETWEEN_PROBES    = (1.5, 3.5)   # between each HEAD/GET attempt
DELAY_BETWEEN_DATES     = (4.0, 8.0)   # between sitting dates
DELAY_AFTER_ERROR       = (8.0, 15.0)  # back-off after a connection error


# ── Session with retry + browser headers ─────────────────────────────────────

def make_session() -> requests.Session:
    """
    Create a requests.Session that looks like a real browser.
    - Rotates User-Agent per call (set in get_headers())
    - Retries on transient network errors (not on 4xx)
    - Keeps cookies across requests (as a real browser would)
    """
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2,          # waits 2s, 4s, 8s between retries
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://",  adapter)
    return session


def get_headers(doc_id: int | None = None) -> dict:
    """Return browser-like headers, optionally with a Referer for the given doc."""
    referer = (
        f"https://eparlib.sansad.in/handle/123456789/{doc_id}"
        if doc_id else REFERER_BASE
    )
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer":         referer,
        "Connection":      "keep-alive",
        "DNT":             "1",
    }


# ── Filename helpers ──────────────────────────────────────────────────────────

def ucd_filename(date_str: str, lok_sabha: int, session: int) -> str:
    """Uncorrected debates: UCD_18_4_19-03-2025_Fullday.pdf"""
    dt  = datetime.strptime(date_str, "%Y-%m-%d")
    dmy = dt.strftime("%d-%m-%Y")
    return f"UCD_{lok_sabha}_{session}_{dmy}_Fullday.pdf"


def lsd_filename(date_str: str, lok_sabha: int, session: int) -> str:
    """Final edited debates: lsd_18_IV_01-04-2025.pdf"""
    dt     = datetime.strptime(date_str, "%Y-%m-%d")
    dmy    = dt.strftime("%d-%m-%Y")
    roman  = SESSION_ROMAN.get(session, str(session))
    return f"lsd_{lok_sabha}_{roman}_{dmy}.pdf"


def candidate_filenames(date_str: str, lok_sabha: int, session: int) -> list[str]:
    """Return filenames to try for a date, UCD first (released faster)."""
    return [
        ucd_filename(date_str, lok_sabha, session),
        lsd_filename(date_str, lok_sabha, session),
    ]


# ── Doc-ID estimation ─────────────────────────────────────────────────────────

def estimate_doc_id(date_str: str) -> int:
    """
    Estimate the eparlib doc_id for a date using the nearest confirmed anchor
    and a linear extrapolation of IDS_PER_DAY.
    """
    anchor_date, anchor_id, _ = closest_anchor(date_str)
    target  = datetime.strptime(date_str,   "%Y-%m-%d")
    anchor  = datetime.strptime(anchor_date, "%Y-%m-%d")
    delta   = (target - anchor).days
    return max(1, anchor_id + int(delta * IDS_PER_DAY))


# ── Download ──────────────────────────────────────────────────────────────────

_session = make_session()   # one persistent session for the whole run


def _sleep(range_secs: tuple[float, float]):
    """Sleep for a random duration within range_secs."""
    time.sleep(random.uniform(*range_secs))


def try_download(doc_id: int, filename: str) -> tuple[bool, str]:
    """
    Attempt to download a specific (doc_id, filename) combination.
    Uses HEAD first to check existence cheaply, then GET for the actual file.
    Returns (success, local_path_str).
    """
    local = PDF_DIR / filename
    if local.exists():
        print(f"    ↳ Already exists: {filename}")
        return True, str(local)

    url = f"{BASE_URL}/{doc_id}/1/{filename}"
    headers = get_headers(doc_id)

    try:
        # HEAD check first — much lighter than a full GET
        head = _session.head(url, headers=headers, timeout=15, allow_redirects=True)
        if head.status_code != 200:
            return False, ""
        ct = head.headers.get("content-type", "")
        if "pdf" not in ct.lower():
            return False, ""

        # Confirmed PDF — now download it
        _sleep((0.5, 1.5))   # brief pause between HEAD and GET
        headers = get_headers(doc_id)   # refresh headers
        resp = _session.get(url, headers=headers, timeout=60, stream=True)
        if resp.status_code == 200:
            with open(local, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            kb = local.stat().st_size // 1024
            print(f"    ✓ Downloaded: {filename} ({kb} KB)")
            return True, str(local)
        return False, ""

    except Exception as e:
        short = str(e)[:80]
        print(f"    ⚠ Connection error: {short}")
        print(f"    ↳ Backing off {DELAY_AFTER_ERROR[0]:.0f}–{DELAY_AFTER_ERROR[1]:.0f}s...")
        _sleep(DELAY_AFTER_ERROR)
        return False, ""


def probe_for_date(date_str: str, lok_sabha: int, session: int) -> tuple[bool, str, int, str]:
    """
    Try to find and download a debate PDF for a given sitting date.

    Strategy:
      1. Estimate doc_id from nearest confirmed anchor + IDS_PER_DAY
      2. For each candidate filename (UCD first, then lsd):
         a. Try exact estimate
         b. Spiral outward in steps of PROBE_STEP up to ±PROBE_RADIUS
         c. Pause DELAY_BETWEEN_PROBES between each attempt
      3. Return (success, local_path, doc_id_found, filename_used)

    Total worst-case requests per date:
      2 filenames × (1 + 2 × PROBE_RADIUS/PROBE_STEP) ≈ 26 HEAD requests
      Each with 1.5–3.5s delay → ~50–90 seconds per date max.
    """
    est_id    = estimate_doc_id(date_str)
    filenames = candidate_filenames(date_str, lok_sabha, session)

    # ── Check local disk first for ALL filenames — no network needed ──────────
    for filename in filenames:
        local = PDF_DIR / filename
        if local.exists():
            print(f"    ↳ Already on disk: {filename}")
            return True, str(local), 0, filename

    # ── File not on disk — probe eparlib ─────────────────────────────────────
    print(f"    Estimated doc_id: {est_id}  (±{PROBE_RADIUS} step {PROBE_STEP})")

    for filename in filenames:
        ok, path = try_download(est_id, filename)
        if ok:
            return True, path, est_id, filename
        _sleep(DELAY_BETWEEN_PROBES)

        # Spiral outward: +step, -step, +2*step, -2*step, ...
        for delta in range(PROBE_STEP, PROBE_RADIUS + 1, PROBE_STEP):
            for offset in [delta, -delta]:
                candidate_id = est_id + offset
                if candidate_id < 1:
                    continue
                ok, path = try_download(candidate_id, filename)
                if ok:
                    return True, path, candidate_id, filename
                _sleep(DELAY_BETWEEN_PROBES)

    return False, "", 0, ""


# ── DB helpers ────────────────────────────────────────────────────────────────

def record_pdf(conn: sqlite3.Connection, date_str: str, url: str, filename: str,
               lok_sabha: int, session: int, doc_id: int, filename_type: str) -> int:
    """Insert/ignore a source_pdfs row; return its id.
    For manually downloaded files, doc_id=0 and url is set to the local filename."""
    c = conn.cursor()
    # Use filename as unique key for manually placed files (doc_id=0, no real URL)
    unique_key = url if doc_id else f"local://{filename}"
    c.execute("""
        INSERT OR IGNORE INTO source_pdfs
            (lok_sabha_no, session_no, sitting_date, pdf_type, filename_type,
             language, url, filename, doc_id, downloaded_at)
        VALUES (?, ?, ?, 'fullday', ?, 'english', ?, ?, ?, datetime('now'))
    """, (lok_sabha, session, date_str, filename_type, unique_key, filename, doc_id or None))
    conn.commit()
    c.execute("SELECT id FROM source_pdfs WHERE url = ?", (unique_key,))
    return c.fetchone()["id"]


def mark_sitting_date_downloaded(conn: sqlite3.Connection, date_str: str,
                                  lok_sabha: int, session: int, pdf_id: int):
    """Flag sitting_dates.has_debate_pdf = 1 and link the source pdf."""
    conn.execute("""
        UPDATE sitting_dates
        SET has_debate_pdf = 1, source_pdf_id = ?
        WHERE sitting_date = ? AND lok_sabha_no = ? AND session_no = ?
    """, (pdf_id, date_str, lok_sabha, session))
    conn.commit()


# ── Main entry point ──────────────────────────────────────────────────────────

def run_scraper(dates: list[str] = None, lok_sabha: int = 18,
                session: int = 4, max_pdfs: int = 5) -> list[dict]:
    """
    Download debate PDFs for the given sitting dates.

    If explicit dates are given, the session is auto-detected per date from
    sessions_data — so you can mix dates from different sessions in one call.
    If no dates are given, pulls pending sitting dates for the specified session.
    """
    conn = get_connection()
    c    = conn.cursor()

    if dates:
        # Build list of (date, lok_sabha_no, session_no) — auto-detect session per date
        targets = []
        for d in dates:
            s = find_session_for_date(d, lok_sabha)
            if s:
                targets.append((d, s["lok_sabha_no"], s["session_no"]))
            else:
                print(f"  ⚠ No session found for {d} — using default session {session}")
                targets.append((d, lok_sabha, session))
    else:
        # Fetch un-downloaded sitting dates for this session, newest first
        c.execute("""
            SELECT sitting_date FROM sitting_dates
            WHERE lok_sabha_no = ? AND session_no = ?
              AND has_debate_pdf = 0
            ORDER BY sitting_date DESC
            LIMIT ?
        """, (lok_sabha, session, max_pdfs))
        targets = [(row["sitting_date"], lok_sabha, session) for row in c.fetchall()]

    print(f"\n{'='*60}")
    print(f"Sansad Scraper — {lok_sabha}th Lok Sabha")
    print(f"Targeting {len(targets)} sitting dates")
    print(f"{'='*60}\n")

    downloaded = []

    for date_str, ls, sess in targets:
        print(f"\n── {date_str}  (Session {sess}) ──")
        success, local_path, doc_id, filename = probe_for_date(date_str, ls, sess)

        if success:
            fn_type  = "UCD" if filename.startswith("UCD") else "lsd"
            url      = f"{BASE_URL}/{doc_id}/1/{filename}" if doc_id else ""
            pdf_id   = record_pdf(conn, date_str, url, filename, ls, sess, doc_id, fn_type)
            mark_sitting_date_downloaded(conn, date_str, ls, sess, pdf_id)

            downloaded.append({
                "date":       date_str,
                "session":    sess,
                "filename":   filename,
                "doc_id":     doc_id,
                "pdf_id":     pdf_id,
                "local_path": local_path,
                "fn_type":    fn_type,
            })
            # Only pause between network downloads — no delay for local files
            if doc_id:
                _sleep(DELAY_BETWEEN_DATES)
        else:
            print(f"    ✗ No PDF found for {date_str} after probing ±{PROBE_RADIUS} IDs.")
            _sleep(DELAY_BETWEEN_DATES)

    conn.close()
    print(f"\n{'='*60}")
    print(f"✓ Registered {len(downloaded)} / {len(targets)} PDFs → {PDF_DIR}")
    print(f"{'='*60}\n")
    return downloaded


if __name__ == "__main__":
    results = run_scraper(max_pdfs=5)
    for r in results:
        print(f"  {r['date']} [{r['fn_type']}] → {r['filename']}")
