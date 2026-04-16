"""
parser/inspect_pdf.py — Diagnostic: show raw extracted text from any PDF.

Run this on your local machine to see what pdfplumber actually extracts
so we can write correct speaker-detection patterns.

Usage:
    python parser/inspect_pdf.py pdfs/lsd_18_VII_28-01-2026_original_corrected.pdf
    python parser/inspect_pdf.py pdfs/lsd_18_VII_28-01-2026_original_corrected.pdf --pages 1-5
    python parser/inspect_pdf.py pdfs/lsd_18_VII_28-01-2026_original_corrected.pdf --find-speakers
"""

import sys
import re
import argparse
import pdfplumber
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

DEVANAGARI_RE = re.compile(r'[\u0900-\u097F]')
COLON_LINE_RE = re.compile(r'.{3,}\s*:\s*$|.{3,}\s*:\s+\S')  # lines with "name : text" pattern


def inspect(pdf_path: str, page_range: tuple[int, int] | None = None,
            find_speakers: bool = False):
    print(f"\n{'='*70}")
    print(f"PDF: {Path(pdf_path).name}")
    print(f"{'='*70}\n")

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"Total pages: {total}\n")

        start_p = (page_range[0] - 1) if page_range else 0
        end_p   = page_range[1] if page_range else min(5, total)

        for page_num in range(start_p, end_p):
            page = pdf.pages[page_num]
            text = page.extract_text()

            print(f"{'─'*70}")
            print(f"PAGE {page_num + 1}")
            print(f"{'─'*70}")

            if not text:
                print("  [NO TEXT — may be scanned image]")
                continue

            lines = text.split('\n')
            devanagari_lines = sum(1 for l in lines if DEVANAGARI_RE.search(l))
            print(f"  Lines: {len(lines)}  |  Devanagari lines: {devanagari_lines}")
            print()

            for i, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                has_dev  = bool(DEVANAGARI_RE.search(line))
                has_col  = ':' in line
                marker   = ''
                if has_dev and has_col:
                    marker = ' ◀ SPEAKER?'
                elif has_dev:
                    marker = ' [dev]'
                print(f"  {i:>3}: {repr(line)}{marker}")

            print()

    if find_speakers:
        print(f"\n{'='*70}")
        print("SPEAKER CANDIDATE LINES (contain colon + Devanagari or uppercase)")
        print(f"{'='*70}\n")
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages[:20], 1):
                text = page.extract_text()
                if not text:
                    continue
                for line in text.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    # Candidate: has a colon AND (Devanagari OR looks like a name)
                    if ':' in line and (DEVANAGARI_RE.search(line) or
                                        re.match(r'^[A-Z]{3,}', line)):
                        print(f"  p{page_num}: {repr(line)}")


def main():
    ap = argparse.ArgumentParser(description="Inspect raw PDF text extraction")
    ap.add_argument("pdf",          help="Path to PDF file")
    ap.add_argument("--pages",      help="Page range e.g. 1-5", default=None)
    ap.add_argument("--find-speakers", action="store_true",
                    help="Scan first 20 pages for speaker-candidate lines")
    args = ap.parse_args()

    page_range = None
    if args.pages:
        parts = args.pages.split('-')
        page_range = (int(parts[0]), int(parts[1]) if len(parts) > 1 else int(parts[0]) + 1)

    inspect(args.pdf, page_range, find_speakers=args.find_speakers)


if __name__ == "__main__":
    main()
