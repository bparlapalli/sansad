# How to use ParamaSrota

A searchable record of what was actually said on the floor of the Lok Sabha. This is the same content as
the live site's [`/how-to-use`](../app/templates/how_to_use.html) page, kept here for anyone reading the repo.

ParamaSrota parses Lok Sabha debate PDFs into individual, attributed statements — who said what, on which
date, on which subject — instead of leaving them buried in a scanned transcript.

## Search modes

- **By Date** — pick a sitting day and see everything said that day, in order.
- **Politician** — pull up every statement from a specific MP, optionally combined with a keyword.
- **Party** — see all MPs from a party and what they've said, optionally filtered by date or keyword.
- **Free Text** — search across every statement for a word or phrase (a bill name, a scheme, a topic).

## Reading a result

A speech in the House can run to hundreds of words covering several subjects. Keyword search results show
the specific passage that matched — not the whole speech — via a `statement_chunks` layer (paragraph-sized,
sentence-safe slices, indexed separately from the full statement). Click **"Show full statement"** to expand
to the complete remarks with full speaker/date/page context.

## What's in the data

This is an actively-growing dataset. The full historical archive is maintained locally and grows daily; the
public site shows a rolling recent window (see [Deployment](#deployment) below) rather than the complete
record. Older sessions are added to the local archive over time.

## Other pages

- **Today** — the latest sitting day's summary and proceedings.
- **News** — a running briefing of recent parliamentary activity.
- **PDFs** — the source debate documents processed so far.
- **Speakers** — every MP with a statement in the dataset, each with a profile page.
- **Sessions** — an overview of Lok Sabha sessions and their sitting dates.

## Where this comes from

Source PDFs are published by the Lok Sabha Secretariat at [eparlib.sansad.in](https://eparlib.sansad.in).
Statements are extracted and attributed automatically, non-English statements are translated where noted,
and daily summaries are AI-generated from the parsed statements — treat them as a starting point for finding
the primary source, not a substitute for it.

## Deployment

The live site is intentionally a **partial mirror**: the complete `sansad.db` never leaves the machine it's
scraped and parsed on. A trimmed export (default: last 30 days of statements, relative to the newest sitting
date in the data) is pushed to the deployed app over an authenticated endpoint. See
[CLAUDE.md § Deployment](../CLAUDE.md#deployment) for the full architecture.
