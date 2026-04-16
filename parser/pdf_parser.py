"""
parser/pdf_parser.py — Extracts attributed statements from Lok Sabha debate PDFs

The debate PDFs follow this structure:

  English (UCD files):
    SHRI RAHUL GANDHI (WAYANAD): This is what I said...
    THE SPEAKER: Order, order.

  Hindi (lsd files):
    श्री राहुल गांधी (वायनाड) : यह सदन में मैं कहना चाहता हूं...
    अध्यक्ष महोदय : आपका समय समाप्त हो गया।

We parse each page, detect speaker transitions, and split into
atomic statement records.

Supports:
  - English (UCD + lsd PDFs): full parsing
  - Hindi / regional (lsd PDFs): full parsing with Devanagari patterns
    translation handled separately in translator.py
"""

import sys
import re
import logging
import sqlite3
import pdfplumber
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection

# ── Devanagari Unicode range ──────────────────────────────────────────────────
DEVANAGARI_RE = re.compile(r'[\u0900-\u097F]')

# ── CID artifact cleanup ──────────────────────────────────────────────────────
# pdfplumber outputs (cid:NNN) when a PDF uses a custom/non-standard font
# encoding it can't resolve — common in Indian government PDFs.
# We strip these so text is readable (some chars will be missing, but the
# structure and key words remain intact for speaker detection + translation).
CID_RE = re.compile(r'\(cid:\d+\)')

def clean_extracted_text(text: str) -> str:
    """
    Remove pdfplumber CID artifacts and normalise whitespace.
    Example: 'अ(cid:197)य (cid:177)' → 'अय' (incomplete but matchable).
    """
    text = CID_RE.sub('', text)          # drop (cid:NNN) placeholders
    text = re.sub(r'[ \t]{2,}', ' ', text)  # collapse multiple spaces/tabs
    return text

# ── English speaker detection patterns ───────────────────────────────────────
ENGLISH_SPEAKER_PATTERNS = [
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

# ── Hindi (Devanagari) speaker detection patterns ─────────────────────────────
# Lok Sabha Hindi debate format: श्री [NAME] ([CONSTITUENCY]) : [text]
# Titles: श्री (Shri), श्रीमती (Shrimati), डॉ. (Dr.), प्रो. (Prof.), कुमारी (Kumari)
# Presiding officers: अध्यक्ष महोदय, उपाध्यक्ष महोदय, सभापति महोदय
# Ministers: [title] मंत्री
#
# Note: constituency may be in Hindi OR English; colon may be preceded by space.
_D = r'[\u0900-\u097F]'          # any Devanagari char (shorthand)
_DWORD = rf'{_D}[\u0900-\u097F\s\.\-]*'   # Devanagari word(s)

HINDI_SPEAKER_PATTERNS = [
    # श्री / श्रीमती NAME (CONSTITUENCY) :
    rf'^((?:श्री|श्रीमती|डॉ\.?\s*|प्रो\.?\s*|कुमारी\s*|सुश्री\s*|अध्यक्ष\s*){_DWORD}?)\s*\(([^)]+)\)\s*:',
    # Same but name may contain English chars (transliterated or mixed)
    rf'^((?:श्री|श्रीमती|डॉ\.?\s*|प्रो\.?\s*|कुमारी\s*|सुश्री\s*)\s*[A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F\s\.\-]+?)\s*\(([^)]+)\)\s*:',
    # Presiding officers without constituency
    rf'^((?:माननीय\s+)?(?:अध्यक्ष|उपाध्यक्ष|सभापति|उपसभापति)\s*(?:महोदय|महोदया)?)\s*:',
    # Minister patterns
    rf'^((?:श्री|श्रीमती|डॉ\.?\s*)?{_DWORD}(?:मंत्री|मंत्रालय){_D}*)\s*:',
    # Simple: title + name with no constituency (fallback)
    rf'^((?:श्री|श्रीमती|डॉ\.?\s*|प्रो\.?\s*|कुमारी\s*|सुश्री\s*){_DWORD})\s*:',

    # ── CID-tolerant patterns ─────────────────────────────────────────────────
    # For PDFs with custom font encoding: (cid:NNN) already stripped by
    # clean_extracted_text(), but name chars may be missing → match loosely.
    #
    # माननीय + any short word(s) + optional (CONSTITUENCY) + colon
    # Matches: 'माननीय अय  :', 'माननीय सदयगण,', 'माननीय अय (वाराणसी) :'
    rf'^(माननीय\s+\S{{1,30}}(?:\s+\S{{1,10}})?)\s*(?:\([^)]*\)\s*)?:',
    # Secretary-General announcing items (English in Hindi PDF)
    r'^(SECRETARY-GENERAL)\s*:',
]

# Combined pattern list — Hindi first (more specific), then English
SPEAKER_PATTERNS = HINDI_SPEAKER_PATTERNS + ENGLISH_SPEAKER_PATTERNS

SPEAKER_RE = re.compile(
    '|'.join(f'(?:{p})' for p in SPEAKER_PATTERNS),
    re.MULTILINE | re.UNICODE
)

TITLE_PREFIXES = ['SHRI', 'SHRIMATI', 'SMT.', 'DR.', 'PROF.', 'KUM.', 'KUMARI', 'ADV.', 'MR.',
                  'श्री', 'श्रीमती', 'डॉ', 'प्रो', 'कुमारी', 'सुश्री']

# ── Hindi page noise patterns to skip ────────────────────────────────────────
HINDI_NOISE_RE = re.compile(
    r'^(?:'
    r'लोक\s*सभा\s*वाद-विवाद|'      # "Lok Sabha debates" header
    r'राज्य\s*सभा\s*वाद-विवाद|'
    r'\d+\s*लोक\s*सभा|'             # "18 Lok Sabha" page number area
    r'सत्र\s*\d+|'                  # "Session N"
    r'बैठक\s*संख्या\s*\d+|'        # "Sitting number N"
    r'^\d+$'                         # bare page numbers
    r')',
    re.UNICODE
)


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


def _extract_with_pdfminer(pdf_path: str) -> dict[int, str]:
    """
    Extract text using pdfminer.six — sometimes handles custom Hindi font
    encodings better than pdfplumber (decodes more glyphs correctly).
    Returns {page_num: text} dict (1-indexed). Empty dict if pdfminer unavailable.
    """
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer, LAParams
    except ImportError:
        return {}

    result = {}
    laparams = LAParams(line_margin=0.5, word_margin=0.1)
    try:
        for page_num, layout in enumerate(extract_pages(pdf_path, laparams=laparams), start=1):
            lines = []
            for element in layout:
                if isinstance(element, LTTextContainer):
                    lines.append(element.get_text())
            text = "".join(lines).strip()
            if text:
                result[page_num] = text
    except Exception as e:
        logger.warning(f"pdfminer extraction failed: {e}")
    return result


def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """
    Extract text page by page, cleaning CID font artifacts.

    Strategy:
      1. Extract with pdfplumber (fast, good layout)
      2. If a page has heavy CID artifacts (>5% of chars), try pdfminer for
         that page — it sometimes decodes custom Hindi fonts more completely.
      3. Use whichever version has fewer CID codes (= better font decoding).

    Returns list of {page_num, text, had_cid, extractor} dicts.
    """
    pages = []
    pdfminer_cache: dict[int, str] = {}  # lazy-loaded on first CID page

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            raw = page.extract_text() or ""
            had_cid = bool(CID_RE.search(raw))

            if had_cid:
                # CID ratio: if >3% of chars are inside (cid:NNN), try pdfminer
                cid_chars = sum(len(m.group()) for m in CID_RE.finditer(raw))
                cid_ratio = cid_chars / max(len(raw), 1)

                if cid_ratio > 0.03:
                    # Lazy-load pdfminer for the whole doc on first CID page
                    if not pdfminer_cache:
                        logger.debug(f"Page {i}: CID ratio {cid_ratio:.1%} — trying pdfminer")
                        pdfminer_cache = _extract_with_pdfminer(pdf_path)

                    pm_raw = pdfminer_cache.get(i, "")
                    pm_cid = CID_RE.search(pm_raw) if pm_raw else True

                    # Pick whichever has fewer CID codes
                    if pm_raw and not pm_cid:
                        raw      = pm_raw
                        had_cid  = False
                        extractor = "pdfminer"
                    else:
                        extractor = "pdfplumber+cleaned"
                else:
                    extractor = "pdfplumber"
            else:
                extractor = "pdfplumber"

            text = clean_extracted_text(raw)
            if text.strip():
                pages.append({
                    "page_num":  i,
                    "text":      text,
                    "had_cid":   had_cid,
                    "extractor": extractor,
                })

    return pages


def parse_statements(pages: list[dict]) -> list[dict]:
    """
    Walk pages and split text into speaker-attributed statements.
    Handles both English (UCD) and Hindi (lsd) Lok Sabha debate PDFs.
    Returns list of statement dicts with language detection applied.
    """
    statements = []
    current_speaker_raw  = None
    current_constituency = None
    current_text_chunks  = []
    current_page         = None

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

            # ── Noise / header lines to skip ──────────────────────────────────
            # English headers
            if 'LOK SABHA DEBATES' in line or 'RAJYA SABHA DEBATES' in line:
                continue
            # Bare page numbers
            if len(line) < 10 and line.replace(' ', '').isdigit():
                continue
            # Hindi headers / footers
            if HINDI_NOISE_RE.match(line):
                continue

            # ── Speaker detection ──────────────────────────────────────────────
            match = SPEAKER_RE.match(line)
            if match:
                flush_statement()

                # Extract speaker name and constituency from first two non-None groups
                matched_groups = match.groups()
                speaker_name = None
                constituency = None
                for g in matched_groups:
                    if g is not None and speaker_name is None:
                        speaker_name = g.strip()
                    elif g is not None and constituency is None:
                        constituency = g.strip()
                        break

                current_speaker_raw  = speaker_name
                current_constituency = constituency
                current_page         = page_num
                rest_of_line         = line[match.end():].strip()
                current_text_chunks  = [rest_of_line] if rest_of_line else []
            else:
                if current_speaker_raw is not None:
                    current_text_chunks.append(line)

    flush_statement()
    return statements


def classify_statement_type(speaker_raw: str, text: str) -> str:
    speaker_upper = speaker_raw.upper()
    text_upper    = text.upper()[:100]

    # English presiding officers
    if 'SPEAKER' in speaker_upper or 'CHAIRMAN' in speaker_upper:
        return 'ruling'
    if 'MINISTER' in speaker_upper or 'PRIME MINISTER' in speaker_upper:
        return 'answer'
    if text_upper.startswith('WILL THE MINISTER') or text_upper.startswith('WHETHER'):
        return 'question'

    # Hindi presiding officers / ministers
    if any(t in speaker_raw for t in ('अध्यक्ष', 'उपाध्यक्ष', 'सभापति', 'उपसभापति')):
        return 'ruling'
    if 'मंत्री' in speaker_raw:
        return 'answer'

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
