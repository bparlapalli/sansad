"""
parser/pipeline.py — Parse + Translate pipeline

Orchestrates:
  1. Find PDFs with parse_status = 'pending' or 'error'
  2. Extract text from each PDF (pdf_parser.py)
  3. Detect speaker attributions + language per statement
  4. Translate Hindi/regional statements → English (translator.py / Sarvam AI)
  5. Store everything in the DB

Run standalone:
    python parser/pipeline.py                # parse all pending PDFs (no translation)
    python parser/pipeline.py --translate    # parse + translate Hindi statements
    python parser/pipeline.py --pdf path/to/file.pdf --translate
    python parser/pipeline.py --status       # show parse status
"""

import sys
import argparse
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection, init_db
from parser.pdf_parser import (
    extract_text_from_pdf, parse_statements,
    store_statements, get_or_create_member,
)
from parser.translator import batch_translate


def get_pending_pdfs() -> list[dict]:
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT * FROM source_pdfs
        WHERE parse_status IN ('pending', 'error')
        ORDER BY sitting_date DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def parse_and_translate(pdf_path: str, pdf_record: dict,
                        translate: bool = False) -> dict:
    """
    Full pipeline for one PDF.
    Returns summary dict with counts.
    """
    print(f"\n{'─'*60}")
    print(f"PDF:     {Path(pdf_path).name}")
    print(f"Date:    {pdf_record['sitting_date']}")
    print(f"Translate: {'yes (Sarvam AI)' if translate else 'no'}")

    conn = get_connection()

    try:
        # Step 1 — Extract text
        pages = extract_text_from_pdf(pdf_path)
        print(f"  Pages extracted: {len(pages)}")

        # Step 2 — Parse into statements
        statements = parse_statements(pages)

        en_count = sum(1 for s in statements if s["language"] == "en")
        hi_count = sum(1 for s in statements if s["language"] == "hi")
        other    = len(statements) - en_count - hi_count
        print(f"  Statements found: {len(statements)}  "
              f"(English: {en_count}, Hindi: {hi_count}, Other: {other})")

        # Step 3 — Translate if requested
        if translate and (hi_count + other) > 0:
            print(f"  Translating {hi_count + other} non-English statements via Sarvam AI...")
            statements = batch_translate(statements)
            translated_count = sum(1 for s in statements if s.get("translated"))
            print(f"  Translated: {translated_count}")

        # Step 4 — Store
        if statements:
            count = _store_with_translations(conn, statements, pdf_record)
            print(f"  Stored: {count} statements")
        else:
            conn.execute(
                "UPDATE source_pdfs SET parse_status='done' WHERE id=?",
                (pdf_record["id"],)
            )
            conn.commit()
            count = 0

        return {
            "pdf":        pdf_record["filename"],
            "date":       pdf_record["sitting_date"],
            "total":      len(statements),
            "english":    en_count,
            "hindi":      hi_count,
            "stored":     count,
        }

    except Exception as e:
        print(f"  ✗ Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        conn.execute(
            "UPDATE source_pdfs SET parse_status='error' WHERE id=?",
            (pdf_record["id"],)
        )
        conn.commit()
        return {"pdf": pdf_record["filename"], "date": pdf_record["sitting_date"],
                "total": 0, "english": 0, "hindi": 0, "stored": 0}
    finally:
        conn.close()


def _store_with_translations(conn, statements: list[dict], pdf_record: dict) -> int:
    """
    Insert statements into DB, preserving original text for translated statements.
    """
    c     = conn.cursor()
    count = 0

    for stmt in statements:
        member_id = get_or_create_member(
            conn, stmt["speaker_raw"], stmt.get("constituency")
        )

        # If translated, store original text separately
        original_text  = stmt.get("original_text")
        original_lang  = stmt.get("language") if stmt.get("translated") else None
        stored_text    = stmt["statement_text"]   # English (translated or original)
        stored_lang    = "english" if stmt.get("translated") else stmt["language"]

        c.execute("""
            INSERT INTO statements (
                member_id, speaker_raw, sitting_date,
                lok_sabha_no, session_no, statement_type,
                statement_text, original_text, original_language,
                source_pdf_id, page_number,
                language, word_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            member_id,
            stmt["speaker_raw"],
            pdf_record["sitting_date"],
            pdf_record["lok_sabha_no"],
            pdf_record["session_no"],
            stmt["statement_type"],
            stored_text,
            original_text,
            original_lang,
            pdf_record["id"],
            stmt["page_number"],
            stored_lang,
            stmt["word_count"],
        ))
        count += 1

    conn.commit()
    conn.execute("UPDATE source_pdfs SET parse_status='done' WHERE id=?",
                 (pdf_record["id"],))
    conn.commit()
    return count


def show_parse_status():
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT parse_status, COUNT(*) as n
        FROM source_pdfs
        GROUP BY parse_status
    """)
    rows = c.fetchall()
    conn.close()

    print("\n📄 PDF Parse Status")
    print("─" * 30)
    for row in rows:
        print(f"  {row['parse_status']:<10} {row['n']:>4} PDFs")

    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT
            sp.filename, sp.sitting_date, sp.parse_status,
            COUNT(s.id) as stmt_count,
            SUM(CASE WHEN s.original_language IS NOT NULL THEN 1 ELSE 0 END) as translated
        FROM source_pdfs sp
        LEFT JOIN statements s ON s.source_pdf_id = sp.id
        GROUP BY sp.id
        ORDER BY sp.sitting_date DESC
    """)
    rows = c.fetchall()
    conn.close()

    print("\n  Filename                                  Date        Status     Stmts  Trans")
    print("  " + "─" * 80)
    for row in rows:
        fn = row["filename"][:40]
        print(f"  {fn:<42} {row['sitting_date']}  {row['parse_status']:<10} "
              f"{row['stmt_count'] or 0:>5}  {row['translated'] or 0:>5}")


def main():
    ap = argparse.ArgumentParser(description="Parser + translation pipeline")
    ap.add_argument("--translate",  action="store_true",
                    help="Translate Hindi/regional statements to English via Sarvam AI")
    ap.add_argument("--pdf",        help="Process a specific PDF file path")
    ap.add_argument("--status",     action="store_true", help="Show parse status")
    args = ap.parse_args()

    init_db()

    if args.status:
        show_parse_status()
        return

    pdf_dir = _ROOT / "pdfs"

    if args.pdf:
        # Specific file
        pdf_path = Path(args.pdf)
        conn = get_connection()
        c    = conn.cursor()
        c.execute("SELECT * FROM source_pdfs WHERE filename = ?", (pdf_path.name,))
        record = c.fetchone()
        conn.close()

        if not record:
            print(f"✗ No DB record for {pdf_path.name}. Run scraper first.")
            return

        parse_and_translate(str(pdf_path), dict(record), translate=args.translate)

    else:
        pending = get_pending_pdfs()
        print(f"\n🗂  Parser Pipeline")
        print(f"   PDFs pending: {len(pending)}")
        print(f"   Translation:  {'enabled (Sarvam AI)' if args.translate else 'disabled'}\n")

        summaries = []
        for record in pending:
            local_path = pdf_dir / record["filename"]
            if local_path.exists():
                summary = parse_and_translate(str(local_path), record, translate=args.translate)
                summaries.append(summary)
            else:
                print(f"  ✗ PDF not found locally: {record['filename']}")

        total_stored = sum(s["stored"] for s in summaries)
        print(f"\n{'='*60}")
        print(f"✅ Parser complete — {total_stored} statements stored")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
