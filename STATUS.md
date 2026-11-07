# STATUS.md — stale-listing-reviewer

## What was built

`stale-listing-reviewer` — a local-first, stdlib-only Python CLI for resellers.
It reads a listings CSV (`id, title, listed_date, price, views, sold`), flags
stale listings using **two rules** (listing age and cart rate = sold/views),
suggests **price-drop ladders** (dollar amounts + dates) and **re-list dates**
(one interval after the final rung), and prints a **review worksheet sorted by
highest estimated holding cost**. An optional `--summary` blurb calls any
OpenAI-compatible endpoint (Ollama works with no keys; `OPENAI_API_KEY` env var
supported for hosted endpoints — nothing is ever stored in files).

Package layout:
- `stale_listing_reviewer/core.py` — staleness rules, ladder math, holding cost (pure, Decimal, testable)
- `stale_listing_reviewer/worksheet.py` — text + markdown worksheet rendering
- `stale_listing_reviewer/cli.py` — argparse entry point (`python -m stale_listing_reviewer`)
- `stale_listing_reviewer/llm.py` — optional OpenAI-compatible /chat/completions call
- `tests/` — 53 tests across staleness rules, ladder math, CSV/CLI, and LLM (mocked endpoint)

## How to run it

```bash
# From the repo root (Python 3.10+, no dependencies):
python3 -m stale_listing_reviewer examples/sample_listings.csv --today 2026-11-06

# Common options:
python3 -m stale_listing_reviewer my_listings.csv \
  --age-threshold 30 --cart-threshold 0.02 --ladder-step 0.05 \
  --ladder-tiers 3 --ladder-interval 14 --out worksheet.md

# Optional AI summary with local Ollama (no key needed: `ollama pull llama3.1` first):
python3 -m stale_listing_reviewer my_listings.csv --summary

# Or install as a command:
pip install . && stale-listing-reviewer my_listings.csv
```

RUN TESTS command: `python3 -m unittest discover -s tests`

## Verification results (all run on 2026-11-07)

- `python3 -m unittest discover -s tests` — **53 tests, all pass, exit 0**
- `python3 -m stale_listing_reviewer examples/sample_listings.csv --today 2026-11-06` — exit 0, worksheet printed
  (6 listings: 3 STALE, 3 WATCH; vintage-weenie tops the sheet at $3.76 holding cost
  with ladder $42.75 > $40.50 > $38.25, re-list 2027-01-01)
- `--out worksheet.md` — markdown worksheet written and verified
- `--summary` against a local mock OpenAI endpoint (localhost HTTP server) — blurb printed, exit 0
- `--summary` against an unreachable endpoint — clean skip with a helpful message, exit 0
- Malformed CSV / missing file — exits 2 with a clear parser error
- `pip install` into a fresh venv — builds, console script `stale-listing-reviewer` works

## Known gaps

- Holding cost is a simple estimate (`price × rate/365 × age`); it ignores
  shipping/storage-unit fixed costs, marketplace fees, and capital opportunity.
- Ladder drops are percent-off the *original* price (simple ladder), with no
  demand modeling — no connection to views-per-week momentum yet.
- CSV is the only input; no marketplace API import (deliberate: local-first).
- Zero-view listings are treated as cart-stale by design (needs exposure, not
  a price cut), but there is no separate "needs photos/keywords" report.
- No timezone handling in `--today` (naive local dates).
- LLM summary output is not structured/verified (free-form text by design).
- Deliberate scope boundary: seasonality lives in resale-season-calendar-webapp;
  floor pricing lives in price-floor-calculator-cli.
