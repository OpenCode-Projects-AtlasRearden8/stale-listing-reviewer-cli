# stale-listing-reviewer

A local-first Python CLI for resellers (eBay, Poshmark, Mercari, Amazon...).
Point it at a CSV of your listings and it will:

1. **Flag stale listings** using two rules at once - listing age and cart rate
   (sold/views), so you see both "it's been sitting too long" and "people look
   but don't buy".
2. **Suggest a price-drop ladder** - concrete dollar amounts and dates
   (e.g. $42.75 on 11-20, then $40.50 on 12-04, then $38.25 on 12-18).
3. **Suggest a re-list date** - one interval after the final rung, since fresh
   listings get a visibility bump.
4. **Print a review worksheet** sorted by highest estimated holding cost, so
   the money-dreamers get worked on first.
5. Optionally add a **plain-English AI summary blurb** via any
   OpenAI-compatible endpoint - [Ollama](https://ollama.com) works out of the
   box with no key, nothing leaves your machine unless you point it elsewhere.

This tool is deliberately **distinct from its siblings**:

| Tool | Question it answers |
| --- | --- |
| stale-listing-reviewer (this tool) | "Which of my *existing* listings are going stale, and when do I cut/re-list?" |
| resale-season-calendar-webapp | "When is the *right month* to list this item?" |
| price-floor-calculator-cli | "What's the *lowest price* I can afford to take?" |

## Quick start

No dependencies beyond Python 3.10+ (stdlib only):

```bash
python3 -m stale_listing_reviewer examples/sample_listings.csv --today 2026-11-06
```

Expected output looks like:

```
Stale Listing Review - as of 2026-11-06
--------------------
ID              TITLE                    LISTED       AGE   PRICE  VIEWS  SOLD  CART%   FLAG  HOLD$  LADDER                                   RE-LIST
--------------  -----------------------  ----------  ----  -----  -----  ----  -----   ----  -----  ---------------------------------------  ----------
vintage-weenie  Classic 1992 VHS sealed  2026-01-05  305d  45.00    180     1   0.6%    STALE   3.76  42.75@11-20 > 40.50@12-04 > 38.25@12-18  2027-01-01
boots-820A      Steel toe boots size 10  2026-10-02   35d  120.00     95     2   2.1%    WATCH   1.15  114.00@11-20                             2026-12-04
...
```

## CSV format

Required header row (ISO dates, no comma-heavy formats needed):

```csv
id,title,listed_date,price,views,sold
vintage-weenie,Classic 1992 VHS sealed,2026-01-05,45.00,180,1
```

- `id` - your own label; it just flows through to the worksheet
- `title` - free text
- `listed_date` - `YYYY-MM-DD`
- `price` - current asking price
- `views` - lifetime listing views (0 is fine)
- `sold` - lifetime carts/sales (0 is fine)

## How the rules work

- **Age-stale**: `age >= --age-threshold` (default 30 days).
- **Cart-stale**: `sold/views < --cart-threshold` (default 2%, i.e.
  0.02). Zero views counts as cart-stale - the item needs eyes, not a
  price cut.
- Flag: `STALE` when both rules fire (recommended full ladder),
  `WATCH` when only one (one gentle rung), `OK` otherwise.
- **Holding cost** = `price x --holding-rate/365 x age`. It is a
  *simple, honest estimate* of what each lingering listing is quietly
  costing you (capital + storage), not an accounting-grade model. The
  worksheet sorts by it, highest first.

## Price ladder math

Each rung drops the *original* price by `--ladder-step` per rung (5%
per rung by default), spaced `--ladder-interval` days apart. The re-list
date is one further interval past the final rung. Example with defaults and
`--today 2026-11-06`, base price \$45, STALE: \$42.75 on 2026-11-20 ->
\$40.50 on 2026-12-04 -> \$38.25 on 2026-12-18, re-list 2027-01-01.

## Optional AI summary (no keys, Ollama welcome)

```bash
# 1. Ollama running locally? You already have everything:
ollama serve &
ollama pull llama3.1
python3 -m stale_listing_reviewer my_listings.csv --summary

# 2. Any other OpenAI-compatible endpoint:
python3 -m stale_listing_reviewer my_listings.csv --summary \
  --api-base http://localhost:1234/v1 --model mistral

# 3. A hosted endpoint that needs a key: set the env var, never a file.
OPENAI_API_KEY=sk-... python3 -m stale_listing_reviewer my_listings.csv \
  --summary --api-base https://api.example.com/v1 --model gpt-4o-mini
```

The summary asks for plain English, names the worst offenders, and offers one
next action. Keep it that way - this is a review aid, not a crystal ball.

## Save a printable worksheet

```bash
python3 -m stale_listing_reviewer my_listings.csv --out worksheet.md
```

## Full options

```text
--today YYYY-MM-DD        review as of a date other than system today
--age-threshold DAYS      age rule threshold        (default: 30)
--cart-threshold RATE     sold/views floor          (default: 0.02)
--holding-rate RATE       annual holding rate       (default: 0.10)
--ladder-step FRAC        price drop per rung       (default: 0.05)
--ladder-tiers N          rungs for STALE items     (default: 3)
--ladder-interval DAYS    days between rungs        (default: 14)
--out FILE.md             also write a markdown worksheet
--summary                 ask the LLM for a summary blurb
--api-base URL            OpenAI-compatible base URL (default: Ollama)
--model NAME              model name (default: llama3.1)
```

## Tests

```bash
python3 -m unittest discover -s tests
```

Coverage focuses on the two sets of math you must be able to trust:
staleness rules and ladder math.

## Who this is for

Built by [Asdale Dynamics, LLC](https://dylanasdale.github.io) - plain-English
AI education and practical small-business tools by Dylan Asdale, author of
*The Massive AI Manual*. Designed to be beginner-friendly: one CSV in, one
worksheet out, no accounts, no cloud, no jargon.

## License

MIT - see [LICENSE](LICENSE). Copyright (c) 2026 Asdale Dynamics, LLC.
