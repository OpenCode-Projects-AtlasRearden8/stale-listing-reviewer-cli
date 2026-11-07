"""Core staleness rules, ladder math, and holding-cost calculations.

All math here is pure and dependency-free so it is easy to test. Money is
handled with Decimal and rounded to cents (ROUND_HALF_UP).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

CSV_COLUMNS = ("id", "title", "listed_date", "price", "views", "sold")

FLAG_OK = "OK"
FLAG_WATCH = "WATCH"
FLAG_STALE = "STALE"

CENT = Decimal("0.01")


class ListingCSVError(ValueError):
    """Raised when a listings CSV is malformed."""


def money(value: Decimal) -> Decimal:
    """Round a Decimal amount to cents."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Listing:
    listing_id: str
    title: str
    listed_date: date
    price: Decimal
    views: int
    sold: int


@dataclass(frozen=True)
class LadderRung:
    run: int
    effective_date: date
    price: Decimal


@dataclass(frozen=True)
class ReviewRow:
    listing: Listing
    age: int
    cart_rate: float | None
    age_stale: bool
    cart_stale: bool
    flag: str
    holding_cost: Decimal
    ladder: tuple[LadderRung, ...]
    relist_date: date


def parse_date(text: str) -> date:
    """Parse an ISO date (YYYY-MM-DD)."""
    try:
        return date.fromisoformat(text.strip())
    except (AttributeError, ValueError) as exc:
        raise ListingCSVError(f"invalid date {text!r}: expected YYYY-MM-DD") from exc


def parse_listing(row: dict[str, str]) -> Listing:
    """Build a Listing from a raw CSV row dict."""
    for column in CSV_COLUMNS:
        if column not in row or row[column] is None:
            raise ListingCSVError(f"missing column {column!r}")
    try:
        price = Decimal(row["price"].strip())
    except Exception as exc:
        raise ListingCSVError(f"invalid price {row['price']!r} for listing {row['id']!r}") from exc
    try:
        views = int(row["views"].strip() or "0")
    except ValueError as exc:
        raise ListingCSVError(f"invalid views {row['views']!r} for listing {row['id']!r}") from exc
    try:
        sold = int(row["sold"].strip() or "0")
    except ValueError as exc:
        raise ListingCSVError(f"invalid sold {row['sold']!r} for listing {row['id']!r}") from exc
    if price < 0:
        raise ListingCSVError(f"negative price for listing {row['id']!r}")
    if views < 0 or sold < 0:
        raise ListingCSVError(f"negative views/sold for listing {row['id']!r}")
    return Listing(
        listing_id=row["id"].strip(),
        title=row["title"].strip(),
        listed_date=parse_date(row["listed_date"]),
        price=money(price),
        views=views,
        sold=sold,
    )


def load_listings(path: str | Path) -> list[Listing]:
    """Load listings from a CSV file with a header row."""
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [c for c in CSV_COLUMNS if c not in fieldnames]
        if missing:
            raise ListingCSVError(f"CSV is missing required columns: {', '.join(missing)}")
        return [parse_listing(row) for row in reader]


def age_days(listing: Listing, today: date) -> int:
    """Whole days the listing has been live."""
    return (today - listing.listed_date).days


def cart_rate(listing: Listing) -> float | None:
    """Sold/views conversion rate; None when nobody has seen it yet."""
    if listing.views <= 0:
        return None
    return listing.sold / listing.views


def is_age_stale(age: int, threshold_days: int) -> bool:
    """A listing is age-stale when it has been live at least threshold days."""
    return age >= threshold_days


def is_cart_stale(rate: float | None, threshold: float) -> bool:
    """A listing is cart-stale when its cart rate is below threshold.

    Listings with zero views have no evidence either way, so they are
    treated as cart-stale (they need exposure, not a price cut).
    """
    if rate is None:
        return True
    return rate < threshold


def holding_cost(price: Decimal, annual_rate: float, days: int) -> Decimal:
    """Estimated cost of holding an item for `days` at an annual rate.

    daily_cost = price * rate / 365, pro-rated over the full age of the
    listing. Aged 0 days means no holding cost yet.
    """
    if days <= 0:
        return Decimal("0.00")
    daily = price * (Decimal(str(annual_rate)) / Decimal(365))
    return money(daily * days)


def build_ladder(
    current_price: Decimal,
    step: float,
    tiers: int,
    interval_days: int,
    start_date: date,
) -> tuple[LadderRung, ...]:
    """Build a price-drop ladder from a current price.

    Each rung drops the ORIGINAL price by the step fraction, so the ladder
    is 5%/10%/15% of the original price (simple percent-off ladder), not a
    percentage of the previous rung. First rung lands interval_days after
    start_date.

        build_ladder(100.00, 0.05, 3, 14, 2026-11-06)
        -> rung 1: 95.00 on 2026-11-20
           rung 2: 90.00 on 2026-12-04
           rung 3: 85.00 on 2026-12-18
    """
    if tiers < 0:
        raise ValueError("tiers must be >= 0")
    if interval_days <= 0:
        raise ValueError("interval_days must be > 0")
    if step < 0 or step > 1:
        raise ValueError("step must be between 0 and 1")
    pct = Decimal(str(step))
    rungs: list[LadderRung] = []
    for tier in range(1, tiers + 1):
        price = money(current_price * (Decimal(1) - pct * Decimal(tier)))
        rung_date = start_date + timedelta(days=interval_days * tier)
        if price < 0:
            raise ValueError("ladder drops below zero; use fewer tiers or a smaller step")
        rungs.append(LadderRung(run=tier, effective_date=rung_date, price=price))
    return tuple(rungs)


def relist_date(start_date: date, tiers: int, interval_days: int) -> date:
    """Suggested re-list date: one interval after the final rung.

    Marketplace search favors fresh listings, so once the ladder bottoms
    out, it pays to end and re-list one interval later.
    """
    if tiers < 0:
        raise ValueError("tiers must be >= 0")
    if interval_days <= 0:
        raise ValueError("interval_days must be > 0")
    return start_date + timedelta(days=interval_days * (tiers + 1))


def review_row(
    listing: Listing,
    today: date,
    age_threshold: int,
    cart_threshold: float,
    holding_rate: float,
    ladder_step: float,
    ladder_tiers: int,
    ladder_interval: int,
) -> ReviewRow:
    """Apply staleness rules and build price suggestions for one listing."""
    age = age_days(listing, today)
    rate = cart_rate(listing)
    age_stale = is_age_stale(age, age_threshold)
    cart_stale = is_cart_stale(rate, cart_threshold)

    if age_stale and cart_stale:
        flag = FLAG_STALE
        # Stale on both axes: green-light the full ladder.
        tiers = ladder_tiers
    else:
        flag = FLAG_WATCH if age_stale or cart_stale else FLAG_OK
        # Promising enough to keep: one gentle nudge rung at most.
        tiers = min(ladder_tiers, 1)

    ladder = build_ladder(
        listing.price, ladder_step, tiers, ladder_interval, today
    ) if flag != FLAG_OK else ()
    hop = relist_date(today, tiers, ladder_interval) if flag != FLAG_OK else today

    return ReviewRow(
        listing=listing,
        age=age,
        cart_rate=rate,
        age_stale=age_stale,
        cart_stale=cart_stale,
        flag=flag,
        holding_cost=holding_cost(listing.price, holding_rate, age),
        ladder=ladder,
        relist_date=hop,
    )


def review_listings(
    listings: list[Listing],
    today: date,
    age_threshold: int = 30,
    cart_threshold: float = 0.02,
    holding_rate: float = 0.10,
    ladder_step: float = 0.05,
    ladder_tiers: int = 3,
    ladder_interval: int = 14,
) -> list[ReviewRow]:
    """Review all listings, sorted by highest holding cost first."""
    rows = [
        review_row(
            listing,
            today,
            age_threshold=age_threshold,
            cart_threshold=cart_threshold,
            holding_rate=holding_rate,
            ladder_step=ladder_step,
            ladder_tiers=ladder_tiers,
            ladder_interval=ladder_interval,
        )
        for listing in listings
    ]
    rows.sort(key=lambda row: (row.holding_cost, row.age), reverse=True)
    return rows
