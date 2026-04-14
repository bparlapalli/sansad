"""
parser/pdf_parser.py — Extracts attributed statements from Lok Sabha debate PDFs

The debate PDFs follow this structure:
  SHRI RAHUL GANDHI (WAYANAD): This is what I said...
  THE SPEAKER: Order, order.
  SHRI NARENDRA MODI (VARANASI): My response is...

We parse each page, detect speaker transitions, and split into
atomic statement records.

Supports:
  - English (UCD + lsd PDFs): full parsing
  - Hindi / regional (lsd PDFs): statement extraction with language detection,
    translation handled separately in translator.py
"""

import sys
import re
import sqlite3
import pdfplumber
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection

# ── Speaker detection patterns ────────────────────────────────────────────────
SPEAKER_PATTERNS = [
    # Standard MP with constituency: SHRI RAHUL GANDHI (WAYANAD):
    r'^((?:SHRI|SHRIMATI|SMT\.|DR\.|PROF\.|KUM\.|KUMARI|ADV\.|SUSHRI)\s+[A-Z][A-Z\s\.\-]+?)\s*\(([A-Z][A-Z\s\-]+?)\)\s*:',
    # Standard MP without constituency: SHRI ARUN NEHRU:
    r'^((?:SHRI|SHRIMATI|SMT\.|DR\.|PROF\.|KUM\.|KUMARI|ADV\.|SUSHRI)\s+[A-Z][A-Z\s\.\-]{3,}?)\s*:',
    # Speaker / Deputy Speaker / Chairman
    r'^((?:HON\'BLE\s+)?(?:THE\s+)?(?:SPEAKER|DEPUTY SPEAKER|CHAIRMAN|DEPUTY CHAIRMAN))\s*:',
    # Minister without constituency
    r'^(THE\s+(?:MINISTER|MINISTER OF STATE|PRIME MINISTER|HOME MINISTER)[A-Z\s]+?)\s*:',
    # MR. PREFIX
    r'^(MR\.\s+(?:SPEAKER|DEPUTY SPEAKER|CHAIRMAN))\s*:',
]

SPEAKER_RE = re.compile(
    '|'.join(f'(?:{p})' for p in SPEAKER_PATTERNS),
    re.MULTILINE
)

TITLE_PREFIXES = ['SHRI', 'SHRIMATI', 'SMT.', 'DR.', 'PROF.', 'KUM.', 'KUMARI', 'ADV.', 'MR.']

# Devanagari Unicode range
DEVANAGARI_RE = re.compile(r'[\u0900-\u097F]')


def detect_language(text: str) -> str:
    """
    Detect whether text is primarily Hindi/Devanagari or English.
    Returns ISO language code: 'hi' for Hindi, 'en' for English.
    Extend this as needed for Bengali (bn), Telugu (te), etc.
    """
    if not text:
        return 'en'
    devanagari_chars = len(DEVANAGARI_RE.findall(text))
    ratio = devanagari_chars / max(len(text), 1)
    return 'hi' if ratio > 0.08 else 'en'


def normalize_name(raw_name: str) -> str:
    name = raw_name.strip().upper()
    for prefix in TITLE_PREFIXES:
        name = name.replace(prefix, '').strip()
    return name.lower().strip()


def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """
    Extract text page by page.
    Returns list of {page_num, text} dicts.
    """
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text:
                pages.append({"page_num": i, "text": text})
    return pages


def parse_statements(pages: list[dict]) -> list[dict]:
    """
    Walk pages and split text into speaker-attributed statements.
    Returns list of statement dicts with language detection applied.
    """
    statements = []
    current_speaker_raw = None
    current_constituency = None
    current_text_chunks = []
    current_page = None

    def flush_statement():
        nonlocal current_speaker_raw, current_text_chunks, current_page
        if current_speaker_raw and current_text_chunks:
            text = " ".join(current_text_chunks).strip()
            if len(text) > 20:
                lang = detect_language(text)
                statements.append({
                    "speaker_raw":    current_speaker_raw,
                    "constituency":   current_constituency,
                    "statement_text": text,
                    "word_count":     len(text.split()),
                    "page_number":    current_page,
                    "language":       lang,
                    "statement_type": classify_statement_type(current_speaker_raw, text),
                })

    for page_num, page_text in [(p["page_num"], p["text"]) for p in pages]:
        for line in page_text.split('\n'):
            line = line.strip()
            if not line:
                continue

            match = SPEAKER_RE.match(line)
            if match:
                flush_statement()

                matched_groups = match.groups()
                speaker_name = None
                constituency = None
                for g in matched_groups:
                    if g is not None and speaker_name is None:
                        speaker_name = g.strip()
                    elif g is not None and constituency is None:
                        constituency = g.strip()

                current_speaker_raw  = speaker_name
                current_constituency = constituency
                current_page         = page_num
                rest_of_line         = line[match.end():].strip()
                current_text_chunks  = [rest_of_line] if rest_of_line else []
            else:
                if len(line) < 10 and line.replace(' ', '').isdigit():
                    continue
                if 'LOK SABHA DEBATES' in line or 'RAJYA SABHA DEBATES' in line:
                    continue
                if current_speaker_raw is not None:
                    current_text_chunks.append(line)

    flush_statement()
    return statements


def classify_statement_type(speaker_raw: str, text: str) -> str:
    speaker_upper = speaker_raw.upper()
    text_upper    = text.upper()[:100]

    if 'SPEAKER' in speaker_upper or 'CHAIRMAN' in speaker_upper:
        return 'ruling'
    if 'MINISTER' in speaker_upper or 'PRIME MINISTER' in speaker_upper:
        return 'answer'
    if text_upper.startswith('WILL THE MINISTER') or text_upper.startswith('WHETHER'):
        return 'question'
    if len(text.split()) < 15:
        return 'interruption'
    return 'speech'


def get_or_create_member(conn: sqlite3.Connection, speaker_raw: str,
                          constituency: str = None) -> int:
    name_norm = normalize_name(speaker_raw)
    c = conn.cursor()
    c.execute("SELECT id FROM members WHERE name_normalized = ?", (name_norm,))
    row = c.fetchone()
    if row:
        return row["id"]
    c.execute("""
        INSERT INTO members (name, name_normalized, constituency, house)
        VALUES (?, ?, ?, 'lok_sabha')
    """, (speaker_raw.title(), name_norm, constituency))
    conn.commit()
    return c.lastrowid


def store_statements(conn: sqlite3.Connection, statements: list[dict],
                     pdf_record: dict) -> int:
    """
    Insert parsed statements into the database.
    Returns count of inserted rows.
    """
    c     = conn.cursor()
    count = 0

    for stmt in statements:
        member_id = get_or_create_member(
            conn, stmt["speaker_raw"], stmt.get("constituency")
        )
        c.execute("""
            INSERT INTO statements (
                member_id, speaker_raw, sitting_date,
                lok_sabha_no, session_no, statement_type,
                statement_text, original_language,
                source_pdf_id, page_number,
                language, word_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            member_id,
            stmt["speaker_raw"],
            pdf_record["sitting_date"],
            pdf_record["lok_sabha_no"],
            pdf_record["session_no"],
            stmt["statement_type"],
            stmt["statement_text"],
            stmt["language"] if stmt["language"] != "en" else None,
            pdf_record["id"],
            stmt["page_number"],
            stmt["language"],
            stmt["word_count"],
        ))
        count += 1

    conn.commit()
    c.execute("UPDATE source_pdfs SET parse_status='done' WHERE id=?", (pdf_record["id"],))
    conn.commit()
    return count


def parse_pdf_file(pdf_path: str, pdf_record: dict) -> int:
    """
    Full pipeline: extract text → parse statements → store in DB.
    Returns number of statements stored.
    """
    print(f"\nParsing: {Path(pdf_path).name}")
    conn = get_connection()

    try:
        pages = extract_text_from_pdf(pdf_path)
        print(f"  Pages extracted: {len(pages)}")

        statements = parse_statements(pages)

        # Language breakdown
        en_count = sum(1 for s in statements if s["language"] == "en")
        hi_count = sum(1 for s in statements if s["language"] == "hi")
        other    = len(statements) - en_count - hi_count
        print(f"  Statements found: {len(statements)}  "
              f"(English: {en_count}, Hindi: {hi_count}, Other: {other})")

        if statements:
            count = store_statements(conn, statements, pdf_record)
            print(f"  Stored in DB: {count} rows")
            for s in statements[:3]:
                preview = s["statement_text"][:120].replace('\n', ' ')
                lang_tag = f"[{s['language'].upper()}]" if s["language"] != "en" else ""
                print(f"    [{s['statement_type'].upper()}]{lang_tag} {s['speaker_raw']}: {preview}...")
            return count
        else:
            conn.execute("UPDATE source_pdfs SET parse_status='done' WHERE id=?",
                         (pdf_record["id"],))
            conn.commit()
            print(f"  ℹ No attributed statements found")
            return 0

    except Exception as e:
        print(f"  ✗ Parse error: {e}")
        conn.execute("UPDATE source_pdfs SET parse_status='error' WHERE id=?",
                     (pdf_record["id"],))
        conn.commit()
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    pdf_dir = _ROOT / "pdfs"
    pdfs    = list(pdf_dir.glob("*.pdf"))

    if not pdfs:
        print("No PDFs found. Run scraper first.")
    else:
        conn = get_connection()
        for pdf_path in pdfs:
            c = conn.cursor()
            c.execute("SELECT * FROM source_pdfs WHERE filename=?", (pdf_path.name,))
            record = c.fetchone()
            conn.close()
            if record:
                parse_pdf_file(str(pdf_path), dict(record))
            else:
                print(f"No DB record for {pdf_path.name} — run scraper first.")
