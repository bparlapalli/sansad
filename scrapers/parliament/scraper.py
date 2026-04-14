"""
scrapers/parliament/scraper.py — Downloads Lok Sabha debate PDFs from eparlib.sansad.in

URL pattern:
  https://eparlib.sansad.in/bitstream/123456789/{doc_id}/1/{filename}

Two filename patterns:
  UCD_{ls}_{session}_{DD-MM-YYYY}_Fullday.pdf  ← uncorrected debates (released quickly)
  lsd_{ls}_{roman_session}_{DD-MM-YYYY}.pdf    ← final edited version (released later)

Doc-ID estimation:
  DSpace IDs are roughly sequential by upload date.
  We use confirmed anchors from core/sessions_data.py and interpolate.
  A probe then searches ±PROBE_RADIUS IDs around the estimate.

Confirmed anchors:
  2024-08-01 → 2981286  (lsd_18_II_01-08-2024.pdf)
  2025-03-19 → 2989556  (UCD_18_4_19-03-2025_Fullday.pdf)
  2025-04-01 → 2990867  (lsd_18_IV_01-04-2025.pdf)

Run standalone:
  python scrapers/parliament/scraper.py
"""

import sys
import time
import random
import sqlite3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path
from datetime import datetime

# ── Add project root to sys.path so core/ imports work ───────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection, init_db
from core.sessions_data import (
    ALL_SESSIONS, DOC_ID_ANCHORS, SESSION_ROMAN,
    closest_anchor, find_session_for_date, get_latest_session,
)

# ── Config ────────────────────────────────────────────────────────────────────
PDF_DIR      = _ROOT / "pdfs"
PDF_DIR.mkdir(exist_ok=True)

BASE_URL     = "https://eparlib.sansad.in/bitstream/123456789"
REFERER_BASE = "https://eparlib.sansad.in/handle/123456789/7"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

# IDs per calendar day — from confirmed anchors:
#   Aug 1 2024 → Mar 19 2025: (2989556 - 2981286) / 230 days ≈ 35.9 ids/day
#   Mar 19 2025 → Apr 1 2025: (2990867 - 2989556) / 13 days ≈ 100.8 ids/day
#   Average ≈ 40 ids/day (upload bursts handled by probe)
IDS_PER_DAY  = 40
PROBE_RADIUS = 300   # search ±300 around estimate (wider = better for 2026 dates far from anchors)
PROBE_STEP   = 25    # jump in steps of 25

DELAY_BETWEEN_PROBES = (1.5, 3.5)
DELAY_BETWEEN_DATES  = (4.0, 8.0)
DELAY_AFTER_ERROR    = (8.0, 15.0)


# ── Session with retry + browser headers ─────────────────────────────────────

def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://",  adapter)
    return session


def get_headers(doc_id: int | None = None) -> dict:
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
    dt    = datetime.strptime(date_str, "%Y-%m-%d")
    dmy   = dt.strftime("%d-%m-%Y")
    roman = SESSION_ROMAN.get(session, str(session))
    return f"lsd_{lok_sabha}_{roman}_{dmy}.pdf"


def candidate_filenames(date_str: str, lok_sabha: int, session: int) -> list[str]:
    """Return filenames to try, UCD first (released faster)."""
    return [
        ucd_filename(date_str, lok_sabha, session),
        lsd_filename(date_str, lok_sabha, session),
    ]


# ── Doc-ID estimation ─────────────────────────────────────────────────────────

def estimate_doc_id(date_str: str) -> int:
    anchor_date, anchor_id, _ = closest_anchor(date_str)
    target  = datetime.strptime(date_str,   "%Y-%m-%d")
    anchor  = datetime.strptime(anchor_date, "%Y-%m-%d")
    delta   = (target - anchor).days
    return max(1, anchor_id + int(delta * IDS_PER_DAY))


# ── Download ──────────────────────────────────────────────────────────────────

_http = make_session()


def _sleep(range_secs: tuple[float, float]):
    time.sleep(random.uniform(*range_secs))


def try_download(doc_id: int, filename: str) -> tuple[bool, str]:
    """
    HEAD check then GET. Returns (success, local_path_str).
    """
    local = PDF_DIR / filename
    if local.exists():
        print(f"    ↳ Already exists: {filename}")
        return True, str(local)

    url     = f"{BASE_URL}/{doc_id}/1/{filename}"
    headers = get_headers(doc_id)

    try:
        head = _http.head(url, headers=headers, timeout=15, allow_redirects=True)
        if head.status_code != 200:
            return False, ""
        ct = head.headers.get("content-type", "")
        if "pdf" not in ct.lower():
            return False, ""

        _sleep((0.5, 1.5))
        headers = get_headers(doc_id)
        resp = _http.get(url, headers=headers, timeout=60, stream=True)
        if resp.status_code == 200:
            with open(local, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            kb = local.stat().st_size // 1024
            print(f"    ✓ Downloaded: {filename} ({kb} KB)")
            return True, str(local)
        return False, ""

    except Exception as e:
        print(f"    ⚠ Connection error: {str(e)[:80]}")
        print(f"    ↳ Backing off...")
        _sleep(DELAY_AFTER_ERROR)
        return False, ""


def probe_for_date(date_str: str, lok_sabha: int, session: int) -> tuple[bool, str, int, str]:
    """
    Find and download a debate PDF for a sitting date.
    Returns (success, local_path, doc_id_found, filename_used).
    """
    est_id    = estimate_doc_id(date_str)
    filenames = candidate_filenames(date_str, lok_sabha, session)

    # Check local disk first — no network needed
    for filename in filenames:
        local = PDF_DIR / filename
        if local.exists():
            print(f"    ↳ Already on disk: {filename}")
            return True, str(local), 0, filename

    print(f"    Estimated doc_id: {est_id}  (±{PROBE_RADIUS} step {PROBE_STEP})")

    for filename in filenames:
        ok, path = try_download(est_id, filename)
        if ok:
            return True, path, est_id, filename
        _sleep(DELAY_BETWEEN_PROBES)

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
    c = conn.cursor()
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
    conn.execute("""
        UPDATE sitting_dates
        SET has_debate_pdf = 1, source_pdf_id = ?
        WHERE sitting_date = ? AND lok_sabha_no = ? AND session_no = ?
    """, (pdf_id, date_str, lok_sabha, session))
    conn.commit()


# ── Main entry point ──────────────────────────────────────────────────────────

def run_scraper(dates: list[str] = None, lok_sabha: int = 18,
                session: int = None, max_pdfs: int = 5,
                all_sessions: bool = False) -> list[dict]:
    """
    Download debate PDFs.
    - If dates given:   session is auto-detected per date.
    - If all_sessions:  scan all sessions for pending sitting dates (most recent first).
    - If session given: pulls pending dates for that specific session.
    - Default (no args): uses the latest active or most-recent session.
    """
    conn = get_connection()
    c    = conn.cursor()

    # Resolve default session
    if session is None:
        latest = get_latest_session(lok_sabha)
        session = latest["session_no"]

    if dates:
        targets = []
        for d in dates:
            s = find_session_for_date(d, lok_sabha)
            if s:
                targets.append((d, s["lok_sabha_no"], s["session_no"]))
            else:
                print(f"  ⚠ No session found for {d} — using session {session}")
                targets.append((d, lok_sabha, session))
    elif all_sessions:
        # Pull pending dates across all sessions, most recent first, up to max_pdfs
        c.execute("""
            SELECT sitting_date, lok_sabha_no, session_no FROM sitting_dates
            WHERE lok_sabha_no = ? AND has_debate_pdf = 0
            ORDER BY sitting_date DESC
            LIMIT ?
        """, (lok_sabha, max_pdfs))
        targets = [(row["sitting_date"], row["lok_sabha_no"], row["session_no"])
                   for row in c.fetchall()]
    else:
        c.execute("""
            SELECT sitting_date FROM sitting_dates
            WHERE lok_sabha_no = ? AND session_no = ?
              AND has_debate_pdf = 0
            ORDER BY sitting_date DESC
            LIMIT ?
        """, (lok_sabha, session, max_pdfs))
        targets = [(row["sitting_date"], lok_sabha, session) for row in c.fetchall()]

    print(f"\n{'='*60}")
    print(f"Parliament Scraper — {lok_sabha}th Lok Sabha")
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
                "date": date_str, "session": sess, "filename": filename,
                "doc_id": doc_id, "pdf_id": pdf_id,
                "local_path": local_path, "fn_type": fn_type,
            })
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
    import argparse
    ap = argparse.ArgumentParser(description="Parliament PDF scraper")
    ap.add_argument("--dates",     nargs="+", help="Specific sitting dates (YYYY-MM-DD)")
    ap.add_argument("--session",   type=int,  default=4)
    ap.add_argument("--max-pdfs",  type=int,  default=5)
    args = ap.parse_args()

    init_db()
    run_scraper(dates=args.dates, session=args.session, max_pdfs=args.max_pdfs)
