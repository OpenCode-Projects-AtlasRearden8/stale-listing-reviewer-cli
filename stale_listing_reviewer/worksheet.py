"""Render the review worksheet as text and markdown."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .core import ReviewRow

HEADER = (
    "ID",
    "TITLE",
    "LISTED",
    "AGE",
    "PRICE",
    "VIEWS",
    "SOLD",
    "CART%",
    "FLAG",
    "HOLD$",
    "LADDER",
    "RE-LIST",
)


def _cart_text(rate: float | None) -> str:
    if rate is None:
        return "n/a"
    return f"{rate * 100:.1f}%"


def _ladder_text(row: ReviewRow) -> str:
    if not row.ladder:
        return "-"
    return " > ".join(f"{rung.price:g}@{rung.effective_date:%m-%d}" for rung in row.ladder)


def _relist_text(row: ReviewRow, today: date) -> str:
    if row.flag == "OK":
        return "-"
    return f"{row.relist_date:%Y-%m-%d}"


def worksheet_rows(rows: list[ReviewRow], today: date) -> tuple[tuple[str, ...], ...]:
    """Build display tuples for worksheet rows (header excluded)."""
    out = []
    for row in rows:
        out.append(
            (
                row.listing.listing_id,
                row.listing.title,
                f"{row.listing.listed_date:%Y-%m-%d}",
                f"{row.age}d",
                f"{row.listing.price:g}",
                str(row.listing.views),
                str(row.listing.sold),
                _cart_text(row.cart_rate),
                row.flag,
                f"{row.holding_cost:g}",
                _ladder_text(row) if row.flag != "OK" else "-",
                _relist_text(row, today),
            )
        )
    return tuple(out)


def render_text(rows: list[ReviewRow], today: date) -> str:
    """Plain-text worksheet sorted by highest holding cost."""
    widths = [len(h) for h in HEADER]
    body = worksheet_rows(rows, today)
    for record in body:
        for i, cell in enumerate(record):
            widths[i] = max(widths[i], len(cell))

    def render_line(cells: tuple[str, ...]) -> str:
        # Last two columns are long; left-align them so they can breathe.
        left_align = {len(cells) - 1}
        parts = []
        for i, cell in enumerate(cells):
            pad = " " * (widths[i] - len(cell))
            parts.append(f"{cell}{pad}" if i in left_align or i == 0 else f"{pad}{cell}")
        return "  ".join(parts).rstrip()

    lines = [f"Stale Listing Review - as of {today:%Y-%m-%d}", "-" * 20]
    lines.append(render_line(HEADER))
    lines.append("  ".join("-" * w for w in widths))
    lines.extend(render_line(record) for record in body)
    total_hold = sum((row.holding_cost for row in rows), Decimal("0"))
    counts = {flag: sum(1 for row in rows if row.flag == flag) for flag in ("STALE", "WATCH", "OK")}
    lines.append("  ".join("-" * w for w in widths))
    lines.append(
        f"{len(rows)} listings | STALE {counts['STALE']} | WATCH {counts['WATCH']} | "
        f"OK {counts['OK']} | est. holding cost: {total_hold:g}"
    )
    return "\n".join(lines) + "\n"


def render_markdown(rows: list[ReviewRow], today: date) -> str:
    """Markdown version of the worksheet (good for keeping/printing)."""
    body = worksheet_rows(rows, today)
    lines = [
        f"# Stale Listing Review — {today:%Y-%m-%d}",
        "",
        "Sorted by highest estimated holding cost. Ladder shows suggested "
        "price drops (amount@date). Re-list = suggested fresh-listing date.",
        "",
        "| " + " | ".join(HEADER) + " |",
        "| " + " | ".join("---" for _ in HEADER) + " |",
    ]
    lines.extend("| " + " | ".join(record) + " |" for record in body)
    lines.append("")
    return "\n".join(lines) + "\n"
