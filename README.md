# Sansad Parliament Scraper

Scrapes Lok Sabha debate PDFs, extracts attributed statements, and stores them in SQLite so you can answer: **"Did X really say this, and when?"**

---

## Setup

```bash
pip install requests pdfplumber
```

That's it. No other dependencies. SQLite is built into Python.

---

## Run

```bash
# Full pipeline: download + parse + store
python main.py

# Download only specific dates
python main.py --dates 2025-03-19 2025-03-18 2025-03-17

# Re-parse already downloaded PDFs
python main.py --parse-only
```

---

## Query

```bash
# Who said what and when
python query.py --speaker "Rahul Gandhi"
python query.py --speaker "Modi" --from 2025-03-01 --to 2025-03-31

# Full text search across all statements
python query.py --search "education bill"
python query.py --search "farmers protest"

# Database stats
python query.py --stats
```

---

## Database Schema

```
source_pdfs        — one row per PDF downloaded
  id, lok_sabha_no, session_no, sitting_date, url, filename, parse_status

members            — one row per unique MP
  id, name, name_normalized, party, constituency, house

statements         — one row per attributed statement (the core fact table)
  id, member_id, speaker_raw, sitting_date, lok_sabha_no, session_no
  statement_type, statement_text, source_pdf_id, page_number, word_count

statements_fts     — FTS5 full text search index over statements
```

---

## Statement Types

| Type | Meaning |
|------|---------|
| `speech` | Substantive speech during debate |
| `question` | Question posed to minister |
| `answer` | Minister's response |
| `interruption` | Short interjection |
| `ruling` | Speaker/Chair ruling |

---

## Data Source

All data from: **https://eparlib.sansad.in**
Official Parliament Digital Library. PDFs are public records.

Current scope:
- 18th Lok Sabha (2024–present)
- Session 4 (Budget Session 2025)
- English version debates

---

## Next Phases

- [ ] Add Rajya Sabha
- [ ] Add historical sessions (1st–17th Lok Sabha)
- [ ] Add party affiliation lookup (from ECI data)
- [ ] YouTube transcript matching
- [ ] Court document cross-referencing
- [ ] REST API layer (FastAPI)
- [ ] Web UI (search interface)

---

## Notes on PDF quality

- **18th Lok Sabha (2024–present)**: Digital PDFs, clean extraction
- **15th–17th (2009–2024)**: Mixed, mostly clean
- **Older sessions**: Scanned, OCR quality varies

The parser is tuned for English version debates. Hindi version support is a future addition.
