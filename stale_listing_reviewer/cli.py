"""Command-line entry point for the stale listing reviewer."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from . import __version__
from .core import FLAG_OK, ListingCSVError, load_listings, review_listings
from .worksheet import render_markdown, render_text

DEFAULT_API_BASE = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stale-listing-reviewer",
        description=(
            "Read a listings CSV (id, title, listed_date, price, views, sold), "
            "flag stale listings by age and cart-rate rules, suggest price-drop "
            "ladders and re-list dates, and print a review worksheet sorted by "
            "highest holding cost."
        ),
        epilog=(
            "Optional AI summary: --summary calls any OpenAI-compatible endpoint "
            "(Ollama works out of the box, no keys). Distinct from "
            "resale-season-calendar-webapp (seasonality) and price-floor-calculator-cli "
            "(floor pricing)."
        ),
    )
    parser.add_argument("csv_path", type=Path, help="path to listings CSV")
    parser.add_argument(
        "--today",
        metavar="YYYY-MM-DD",
        help="date to review as of (default: today, useful for tests/replays)",
    )
    parser.add_argument("--age-threshold", type=int, default=30, metavar="DAYS",
                        help="age in days before a listing counts as stale (default: 30)")
    parser.add_argument("--cart-threshold", type=float, default=0.02, metavar="RATE",
                        help="minimum sold/views cart rate; below this is stale (default: 0.02)")
    parser.add_argument("--holding-rate", type=float, default=0.10, metavar="RATE",
                        help="annual holding-cost rate as a fraction of price (default: 0.10)")
    parser.add_argument("--ladder-step", type=float, default=0.05, metavar="FRAC",
                        help="price drop per ladder rung as a fraction (default: 0.05)")
    parser.add_argument("--ladder-tiers", type=int, default=3, metavar="N",
                        help="number of rungs for STALE listings (default: 3)")
    parser.add_argument("--ladder-interval", type=int, default=14, metavar="DAYS",
                        help="days between ladder rungs (default: 14)")
    parser.add_argument("--out", type=Path, metavar="FILE.md",
                        help="also save the worksheet as a markdown file")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="add an AI summary blurb via an OpenAI-compatible endpoint (optional, local-first)",
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, metavar="URL",
                        help=f"OpenAI-compatible base URL (default: {DEFAULT_API_BASE})")
    parser.add_argument("--model", default=DEFAULT_MODEL, metavar="NAME",
                        help=f"model name for the endpoint (default: {DEFAULT_MODEL})")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def parse_today(text: str | None) -> date:
    """Resolve the as-of date; None means punt to the system clock."""
    if text is None:
        return date.today()
    try:
        return datetime.fromisoformat(text.strip()).date() if "T" in text else date.fromisoformat(
            text.strip()
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid --today {text!r}: expected YYYY-MM-DD") from exc


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        today = parse_today(args.today)
    except (
        argparse.ArgumentTypeError
    ) as exc:  # argparse would do this in parse_args, but --today is a str here
        parser.error(str(exc))
        return 2

    try:
        listings = load_listings(args.csv_path)
    except ListingCSVError as exc:
        parser.error(f"{args.csv_path}: {exc}")
        return 2
    except OSError as exc:
        parser.error(f"cannot read {args.csv_path}: {exc.strerror or exc}")
        return 2

    if not listings:
        print("No listings found in CSV; nothing to review.", file=sys.stderr)
        return 1

    rows = review_listings(
        listings,
        today,
        age_threshold=args.age_threshold,
        cart_threshold=args.cart_threshold,
        holding_rate=args.holding_rate,
        ladder_step=args.ladder_step,
        ladder_tiers=args.ladder_tiers,
        ladder_interval=args.ladder_interval,
    )

    print(render_text(rows, today))

    if args.out is not None:
        args.out.write_text(render_markdown(rows, today), encoding="utf-8")
        print(f"Worksheet saved to {args.out}", file=sys.stderr)

    if args.summary:
        try:
            from .llm import SummaryError, summarize

            blurb = summarize(
                render_markdown(rows, today), api_base=args.api_base, model=args.model
            )
            print("\nSummary")
            print("-------")
            print(blurb)
        except SummaryError as exc:
            print(f"Summary skipped: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"Summary skipped: {type(exc).__name__}: {exc}", file=sys.stderr)

    if all(row.flag == FLAG_OK for row in rows):
        print("(No stale or watch-list listings - you are all caught up.)", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
