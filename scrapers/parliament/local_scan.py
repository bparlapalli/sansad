"""
scrapers/parliament/local_scan.py — Register manually-dropped PDFs from the pdfs/ directory.

Since eparlib.sansad.in blocks scripted downloads, the workflow is:
  1. Download PDFs manually in a browser and drop them into pdfs/
  2. Run this scanner to register them in the DB
  3. Run parser/pipeline.py to extract statements

Filename patterns recognised:
  UCD_{ls}_{session}_{DD-MM-YYYY}_Fullday.pdf    e.g. UCD_18_4_19-03-2025_Fullday.pdf
  lsd_{ls}_{roman}_{DD-MM-YYYY}.pdf              e.g. lsd_18_VI_08-12-2025.pdf

Run standalone:
  python scrapers/parliament/local_scan.py           # scan and register new PDFs
  python scrapers/parliament/local_scan.py --dry-run  # show what would be registered
  python scrapers/parliament/local_scan.py --list     # list all registered PDFs in DB
"""

import re
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection, init_db, sync_db
from core.sessions_data import SESSION_ROMAN, find_session_for_date

PDF_DIR = _ROOT / "pdfs"

# Reverse map: roman numeral → session number
ROMAN_SESSION = {v: k for k, v in SESSION_ROMAN.items()}   # e.g. "VI" → 6

# Regex patterns for known filename formats from eparlib.
#
# UCD (Uncorrected Debate Copy) — released within days of a sitting:
#   UCD_18_4_19-03-2025_Fullday.pdf
#
# LSD (Lok Sabha Debates) — corrected/final version, released weeks later.
#   Older format (Sessions I–VI):
#     lsd_18_VI_08-12-2025.pdf
#   Newer format (Session VII onwards) — "_original_corrected" suffix indicates
#   the original-language (usually Hindi) corrected version:
#     lsd_18_VII_28-01-2026_original_corrected.pdf
#   English version would be "_english_corrected" (if/when published):
#     lsd_18_VII_28-01-2026_english_corrected.pdf
_UCD_RE = re.compile(
    r"^UCD_(\d+)_(\d+)_(\d{2}-\d{2}-\d{4})_Fullday\.pdf$", re.IGNORECASE
)
_LSD_RE = re.compile(
    r"^lsd_(\d+)_([IVX]+)_(\d{2}-\d{2}-\d{4})(?:_([a-z_]+))?\.pdf$", re.IGNORECASE
)


def parse_pdf_filename(filename: str) -> dict | None:
    """
    Parse a PDF filename into metadata.
    Returns dict with keys: filename, fn_type, lok_sabha, session, sitting_date
    Returns None if filename doesn't match either pattern.
    """
    name = Path(filename).name

    m = _UCD_RE.match(name)
    if m:
        ls, sess, dmy = int(m.group(1)), int(m.group(2)), m.group(3)
        date_str = datetime.strptime(dmy, "%d-%m-%Y").strftime("%Y-%m-%d")
        return dict(filename=name, fn_type="UCD", lok_sabha=ls, session=sess,
                    sitting_date=date_str)

    m = _LSD_RE.match(name)
    if m:
        ls, roman, dmy = int(m.group(1)), m.group(2).upper(), m.group(3)
        suffix = (m.group(4) or "").lower()  # e.g. "original_corrected", "english_corrected"
        sess = ROMAN_SESSION.get(roman)
        if sess is None:
            print(f"  ⚠ Unknown roman numeral '{roman}' in {name} — skipping")
            return None
        date_str = datetime.strptime(dmy, "%d-%m-%Y").strftime("%Y-%m-%d")
        # Infer language from filename suffix
        if "english" in suffix:
            lang = "english"
        elif "original" in suffix or "hindi" in suffix:
            lang = "hindi"
        else:
            lang = "hindi"  # older lsd files without suffix are original (Hindi)
        return dict(filename=name, fn_type="lsd", lok_sabha=ls, session=sess,
                    sitting_date=date_str, language=lang)

    return None


def scan_local_pdfs(dry_run: bool = False) -> list[dict]:
    """
    Scan pdfs/ directory, register any unregistered PDFs in the DB.
    Returns list of newly registered PDFs.
    """
    conn = get_connection()
    c    = conn.cursor()

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"  No PDF files found in {PDF_DIR}")
        return []

    print(f"\n{'='*60}")
    print(f"Local PDF Scanner — {PDF_DIR}")
    print(f"Found {len(pdf_files)} PDF file(s) on disk")
    print(f"{'='*60}")

    newly_registered = []

    for pdf_path in pdf_files:
        filename = pdf_path.name
        meta = parse_pdf_filename(filename)

        if meta is None:
            print(f"\n  ⚠ Unrecognised filename pattern: {filename}")
            print(f"     Expected: UCD_18_N_DD-MM-YYYY_Fullday.pdf")
            print(f"          or: lsd_18_RN_DD-MM-YYYY.pdf")
            continue

        # Check if already in DB
        c.execute("SELECT id FROM source_pdfs WHERE filename = ?", (filename,))
        row = c.fetchone()
        if row:
            print(f"\n  ✓ Already registered: {filename}  (pdf_id={row['id']})")
            continue

        # Validate sitting date against known sessions
        session_info = find_session_for_date(meta["sitting_date"], meta["lok_sabha"])
        if session_info is None:
            print(f"\n  ⚠ {filename}")
            print(f"     Date {meta['sitting_date']} not in any known session — registering anyway")
        else:
            # Prefer the session from the filename over the lookup (they should match)
            pass

        kb = pdf_path.stat().st_size // 1024
        print(f"\n  + {filename}  ({kb:,} KB)")
        print(f"    Date: {meta['sitting_date']}  Session: {meta['session']}  Type: {meta['fn_type']}")

        if dry_run:
            print(f"    [dry-run: would register]")
            continue

        # Register in source_pdfs
        # Language is inferred from filename suffix: _original/_hindi → hindi, _english → english
        local_url = f"local://{filename}"
        language  = meta.get("language", "hindi")
        c.execute("""
            INSERT OR IGNORE INTO source_pdfs
                (lok_sabha_no, session_no, sitting_date, pdf_type, filename_type,
                 language, url, filename, doc_id, downloaded_at)
            VALUES (?, ?, ?, 'fullday', ?, ?, ?, ?, NULL, datetime('now'))
        """, (
            meta["lok_sabha"], meta["session"], meta["sitting_date"],
            meta["fn_type"], language, local_url, filename,
        ))
        conn.commit()

        c.execute("SELECT id FROM source_pdfs WHERE filename = ?", (filename,))
        pdf_id = c.fetchone()["id"]

        # Mark sitting_date as having a PDF
        conn.execute("""
            UPDATE sitting_dates
            SET has_debate_pdf = 1, source_pdf_id = ?
            WHERE sitting_date = ? AND lok_sabha_no = ? AND session_no = ?
        """, (pdf_id, meta["sitting_date"], meta["lok_sabha"], meta["session"]))
        conn.commit()

        print(f"    → Registered as pdf_id={pdf_id}")

        newly_registered.append({**meta, "pdf_id": pdf_id, "local_path": str(pdf_path)})

    conn.close()

    # Write local DB back to mounted filesystem
    if not dry_run and newly_registered:
        sync_db()

    print(f"\n{'='*60}")
    if dry_run:
        print(f"[dry-run] Would register {len(newly_registered)} new PDF(s)")
    else:
        print(f"✓ Registered {len(newly_registered)} new PDF(s)")
    print(f"{'='*60}\n")

    return newly_registered


def list_registered_pdfs() -> None:
    """Print all PDFs currently registered in the DB."""
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT id, lok_sabha_no, session_no, sitting_date, filename_type,
               filename, downloaded_at
        FROM source_pdfs
        ORDER BY sitting_date DESC
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("  No PDFs registered in DB yet.")
        return

    print(f"\n{'─'*70}")
    print(f"{'ID':>4}  {'Date':>12}  {'Sess':>4}  {'Type':>5}  Filename")
    print(f"{'─'*70}")
    for r in rows:
        print(f"{r['id']:>4}  {r['sitting_date']:>12}  {r['session_no']:>4}  "
              f"{r['filename_type']:>5}  {r['filename']}")
    print(f"{'─'*70}")
    print(f"  {len(rows)} PDF(s) total\n")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Register local PDFs in DB")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be registered without writing to DB")
    ap.add_argument("--list",    action="store_true",
                    help="List all registered PDFs in DB")
    args = ap.parse_args()

    init_db()

    if args.list:
        list_registered_pdfs()
    else:
        scan_local_pdfs(dry_run=args.dry_run)
