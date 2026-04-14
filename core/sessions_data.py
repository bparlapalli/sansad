"""
sessions_data.py — Master list of 18th Lok Sabha sessions and sitting dates.

Sources:
  - PRS Legislative Research (prsindia.org/parliamenttrack/vital-stats)
  - PIB press releases (pib.gov.in)
  - Sansad.in provisional calendars
  - eparlib.sansad.in confirmed document URLs (reverse-engineered)

Confirmed eparlib doc_id anchors (used for download URL estimation):
  Session 2, 2024-08-01 → doc_id 2981286  (lsd_18_II_01-08-2024.pdf)
  Session 4, 2025-03-19 → doc_id 2989556  (UCD_18_4_19-03-2025_Fullday.pdf)
  Session 4, 2025-04-01 → doc_id 2990867  (lsd_18_IV_01-04-2025.pdf)

Notes on sitting date accuracy:
  - Session 1 & 2: Dates derived from PRS stats + known parliamentary calendar.
  - Session 3: 20 weekdays listed; PRS reports 19 actual sittings (1 day
    likely adjourned without business — scraper will skip gracefully).
  - Session 4 Part 1: 10 weekdays listed; PRS reports 9 sittings (1 day
    may have been adjourned — scraper will skip gracefully).
  - Session 4 Part 2: Mar 14 excluded (Holi); 18 sittings confirmed.
  - All dates are best estimates; the auto-discover function in scraper.py
    will verify actual PDF availability for each date.
"""

# ── Session type constants ────────────────────────────────────────────────────
SESSION_TYPE_SPECIAL  = "special"   # New LS constitution, emergency, joint sittings
SESSION_TYPE_BUDGET   = "budget"    # Union Budget presented
SESSION_TYPE_MONSOON  = "monsoon"   # Monsoon / Summer session
SESSION_TYPE_WINTER   = "winter"    # Winter session

# Roman numeral map for eparlib filename pattern (lsd_18_II_..., lsd_18_IV_...)
SESSION_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"}

# ── 18th Lok Sabha sessions ───────────────────────────────────────────────────
SESSIONS_18 = [
    {
        "lok_sabha_no":  18,
        "session_no":    1,
        "session_name":  "First Session",
        "session_type":  SESSION_TYPE_SPECIAL,
        "start_date":    "2024-06-24",
        "end_date":      "2024-07-03",
        "total_sittings": 8,
        "notes": (
            "18th Lok Sabha constituted after 2024 general elections. "
            "Pro-tem Speaker: Bhartruhari Mahtab. Speaker elected: Om Birla (Jun 26). "
            "Presidential Address: Jun 27. Motion of Thanks debate: Jun 28 – Jul 3."
        ),
        "sitting_dates": [
            "2024-06-24", "2024-06-25", "2024-06-26", "2024-06-27", "2024-06-28",
            "2024-07-01", "2024-07-02", "2024-07-03",
        ],
    },
    {
        "lok_sabha_no":  18,
        "session_no":    2,
        "session_name":  "Budget Session (July–August 2024)",
        "session_type":  SESSION_TYPE_BUDGET,
        "start_date":    "2024-07-22",
        "end_date":      "2024-08-09",
        "total_sittings": 15,
        "notes": (
            "Full Union Budget 2024-25 presented July 23, 2024 by FM Nirmala Sitharaman. "
            "Confirmed eparlib anchor: 2024-08-01 = doc_id 2981286 (lsd_18_II_01-08-2024.pdf)."
        ),
        "sitting_dates": [
            "2024-07-22", "2024-07-23", "2024-07-24", "2024-07-25", "2024-07-26",
            "2024-07-29", "2024-07-30", "2024-07-31",
            "2024-08-01", "2024-08-02",
            "2024-08-05", "2024-08-06", "2024-08-07", "2024-08-08", "2024-08-09",
        ],
    },
    {
        "lok_sabha_no":  18,
        "session_no":    3,
        "session_name":  "Winter Session 2024",
        "session_type":  SESSION_TYPE_WINTER,
        "start_date":    "2024-11-25",
        "end_date":      "2024-12-20",
        "total_sittings": 19,
        "notes": (
            "20 weekdays scheduled; PRS reports 19 actual sittings — 1 day lost to "
            "adjournments. Session was heavily disrupted by Opposition protests."
        ),
        "sitting_dates": [
            "2024-11-25", "2024-11-26", "2024-11-27", "2024-11-28", "2024-11-29",
            "2024-12-02", "2024-12-03", "2024-12-04", "2024-12-05", "2024-12-06",
            "2024-12-09", "2024-12-10", "2024-12-11", "2024-12-12", "2024-12-13",
            "2024-12-16", "2024-12-17", "2024-12-18", "2024-12-19", "2024-12-20",
        ],
    },
    {
        "lok_sabha_no":  18,
        "session_no":    4,
        "session_name":  "Budget Session 2025",
        "session_type":  SESSION_TYPE_BUDGET,
        "start_date":    "2025-01-31",
        "end_date":      "2025-04-04",
        "total_sittings": 27,
        "notes": (
            "Two-part session. Part 1: Jan 31 – Feb 13 (9 sittings, Presidential Address + "
            "Budget). Recess: Feb 14 – Mar 9 (Standing Committees examined Demands for Grants). "
            "Part 2: Mar 10 – Apr 4 (18 sittings). Mar 14 excluded (Holi). Sine die: Apr 4. "
            "Confirmed anchors: Mar 19 = doc_id 2989556, Apr 1 = doc_id 2990867."
        ),
        "sitting_dates": [
            # Part 1 — 10 weekdays listed; PRS says 9 actual sittings (1 may be zero-business)
            "2025-01-31",
            "2025-02-03", "2025-02-04", "2025-02-05", "2025-02-06", "2025-02-07",
            "2025-02-10", "2025-02-11", "2025-02-12", "2025-02-13",
            # Part 2 — 18 sittings confirmed; Mar 14 (Holi) excluded
            "2025-03-10", "2025-03-11", "2025-03-12", "2025-03-13",
            "2025-03-17", "2025-03-18", "2025-03-19", "2025-03-20", "2025-03-21",
            "2025-03-24", "2025-03-25", "2025-03-26", "2025-03-27", "2025-03-28",
            "2025-04-01", "2025-04-02", "2025-04-03", "2025-04-04",
        ],
    },
    {
        "lok_sabha_no":  18,
        "session_no":    5,
        "session_name":  "Monsoon Session 2025",
        "session_type":  SESSION_TYPE_MONSOON,
        "start_date":    "2025-07-21",
        "end_date":      "2025-08-22",
        "total_sittings": None,   # to be confirmed
        "notes": (
            "Dates are estimated from typical parliamentary calendar. "
            "Add confirmed sitting dates and doc_id anchors as PDFs are found."
        ),
        "sitting_dates": [
            # Estimated weekdays — verify against actual eparlib PDFs
            "2025-07-21", "2025-07-22", "2025-07-23", "2025-07-24", "2025-07-25",
            "2025-07-28", "2025-07-29", "2025-07-30", "2025-07-31",
            "2025-08-01",
            "2025-08-04", "2025-08-05", "2025-08-06", "2025-08-07", "2025-08-08",
            "2025-08-11", "2025-08-12",
            "2025-08-18", "2025-08-19", "2025-08-20", "2025-08-21", "2025-08-22",
        ],
    },
    {
        "lok_sabha_no":  18,
        "session_no":    6,
        "session_name":  "Winter Session 2025",
        "session_type":  SESSION_TYPE_WINTER,
        "start_date":    "2025-11-24",
        "end_date":      "2025-12-19",
        "total_sittings": None,   # to be confirmed
        "notes": (
            "Winter Session 2025. Confirmed sitting dates: Dec 8, Dec 19 (user has PDFs). "
            "Other dates estimated from typical parliamentary schedule. "
            "Filename pattern confirmed: lsd_18_VI_DD-MM-YYYY.pdf"
        ),
        "sitting_dates": [
            # Estimated — only Dec 8 and Dec 19 confirmed via downloaded PDFs
            "2025-11-24", "2025-11-25", "2025-11-26", "2025-11-27", "2025-11-28",
            "2025-12-01", "2025-12-02", "2025-12-03", "2025-12-04", "2025-12-05",
            "2025-12-08", "2025-12-09", "2025-12-10", "2025-12-11", "2025-12-12",
            "2025-12-15", "2025-12-16", "2025-12-17", "2025-12-18", "2025-12-19",
        ],
    },
    {
        "lok_sabha_no":  18,
        "session_no":    7,
        "session_name":  "Budget Session 2026",
        "session_type":  SESSION_TYPE_BUDGET,
        "start_date":    "2026-01-30",
        "end_date":      "2026-05-08",   # estimated
        "total_sittings": None,           # to be confirmed
        "notes": (
            "Budget Session 2026 (7th Session of 18th Lok Sabha). "
            "Dates estimated from typical parliamentary calendar — verify against sansad.in. "
            "Union Budget 2026-27 typically presented Feb 1. "
            "Part 1: Jan 30 – Feb 13; Recess: Feb 14 – Mar 9; Part 2: Mar 10 – May 8 (est). "
            "No confirmed eparlib doc_id anchors yet — add as PDFs are found."
        ),
        "sitting_dates": [
            # Part 1 — estimated ~10 sittings (budget + discussion)
            "2026-01-30", "2026-01-31",
            "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
            "2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13",
            # Part 2 — estimated from Mar 10, ~20+ sittings
            "2026-03-10", "2026-03-11", "2026-03-12", "2026-03-13",
            "2026-03-16", "2026-03-17", "2026-03-18", "2026-03-19", "2026-03-20",
            "2026-03-23", "2026-03-24", "2026-03-25", "2026-03-26", "2026-03-27",
            "2026-03-30", "2026-03-31",
            "2026-04-01", "2026-04-02", "2026-04-03",
            "2026-04-06", "2026-04-07", "2026-04-08", "2026-04-09", "2026-04-10",
            "2026-04-13", "2026-04-14", "2026-04-17",
            "2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23", "2026-04-24",
            "2026-04-27", "2026-04-28", "2026-04-29", "2026-04-30",
            "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07", "2026-05-08",
        ],
    },
]

# ── All sessions (expand when adding Rajya Sabha or older Lok Sabhas) ─────────
ALL_SESSIONS = SESSIONS_18

# ── Confirmed doc_id anchors (date → eparlib doc_id) ─────────────────────────
# NOTE: When you successfully download a new PDF, add its anchor here to
# improve estimation accuracy for nearby dates.
# Used by scraper to estimate doc_ids for other dates without probing.
# The more anchors, the more accurate the estimates.
# Format: (date_str, doc_id, filename_type)
#   filename_type: 'lsd' (final edited) | 'UCD' (uncorrected full-day)
DOC_ID_ANCHORS = [
    ("2024-08-01", 2981286, "lsd"),   # Session 2 — confirmed from eparlib search result
    ("2025-03-19", 2989556, "UCD"),   # Session 4 — original anchor in scraper
    ("2025-04-01", 2990867, "lsd"),   # Session 4 — confirmed from eparlib search result
]


def get_all_sitting_dates() -> list[dict]:
    """Return flat list of all sitting dates across all sessions, with session metadata."""
    result = []
    for session in ALL_SESSIONS:
        for i, date_str in enumerate(session["sitting_dates"], start=1):
            result.append({
                "sitting_date":  date_str,
                "sitting_number": i,
                "lok_sabha_no":  session["lok_sabha_no"],
                "session_no":    session["session_no"],
                "session_name":  session["session_name"],
                "session_type":  session["session_type"],
            })
    return result


def get_session(lok_sabha_no: int, session_no: int) -> dict | None:
    """Look up a session by Lok Sabha + session number."""
    for s in ALL_SESSIONS:
        if s["lok_sabha_no"] == lok_sabha_no and s["session_no"] == session_no:
            return s
    return None


def find_session_for_date(date_str: str, lok_sabha_no: int = 18) -> dict | None:
    """
    Given a sitting date, find which session it belongs to.
    Checks the sitting_dates list first, then falls back to start/end date range.
    Returns the session dict or None if not found.
    """
    # Exact match in sitting_dates list
    for s in ALL_SESSIONS:
        if s["lok_sabha_no"] == lok_sabha_no and date_str in s["sitting_dates"]:
            return s
    # Fallback: check if date falls within session's start/end range
    from datetime import datetime
    target = datetime.strptime(date_str, "%Y-%m-%d")
    for s in ALL_SESSIONS:
        if s["lok_sabha_no"] != lok_sabha_no:
            continue
        start = datetime.strptime(s["start_date"], "%Y-%m-%d")
        end   = datetime.strptime(s["end_date"],   "%Y-%m-%d") if s.get("end_date") else None
        if start <= target and (end is None or target <= end):
            return s
    return None


def closest_anchor(date_str: str) -> tuple[str, int, str]:
    """Return the DOC_ID_ANCHOR closest in time to the given date."""
    from datetime import datetime
    target = datetime.strptime(date_str, "%Y-%m-%d")
    return min(
        DOC_ID_ANCHORS,
        key=lambda a: abs((datetime.strptime(a[0], "%Y-%m-%d") - target).days)
    )


def get_active_session(lok_sabha_no: int = 18) -> dict | None:
    """
    Return the session that is currently active (today's date falls within it)
    or None if parliament is in recess.
    """
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    for s in reversed(ALL_SESSIONS):
        if s["lok_sabha_no"] != lok_sabha_no:
            continue
        if s["start_date"] <= today <= (s.get("end_date") or "9999-12-31"):
            return s
    return None


def get_latest_session(lok_sabha_no: int = 18) -> dict:
    """
    Return the most recent session (active or most recently ended).
    Never returns None — falls back to last known session.
    """
    sessions = [s for s in ALL_SESSIONS if s["lok_sabha_no"] == lok_sabha_no]
    active = get_active_session(lok_sabha_no)
    if active:
        return active
    # Return the session with the latest end_date
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    past = [s for s in sessions if s.get("end_date", "9999-12-31") <= today]
    return past[-1] if past else sessions[-1]


def get_pending_sitting_dates(lok_sabha_no: int = 18, session_no: int | None = None,
                               only_past: bool = True) -> list[dict]:
    """
    Return sitting dates that have no confirmed PDF yet.
    If only_past=True (default), skips future dates.
    """
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    result = []
    for s in ALL_SESSIONS:
        if s["lok_sabha_no"] != lok_sabha_no:
            continue
        if session_no is not None and s["session_no"] != session_no:
            continue
        for d in s["sitting_dates"]:
            if only_past and d > today:
                continue
            result.append({
                "sitting_date": d,
                "lok_sabha_no": s["lok_sabha_no"],
                "session_no":   s["session_no"],
                "session_name": s["session_name"],
            })
    return result
