"""Tests for staleness rules: age, cart rate, flags, and holding cost."""

import unittest
from datetime import date
from decimal import Decimal

from stale_listing_reviewer.core import (
    FLAG_OK,
    FLAG_STALE,
    FLAG_WATCH,
    Listing,
    ListingCSVError,
    holding_cost,
    is_age_stale,
    is_cart_stale,
    parse_date,
    parse_listing,
    review_row,
    review_listings,
)

TODAY = date(2026, 11, 6)


def make_listing(
    listing_id="a1",
    title="Test item",
    listed_date=TODAY,
    price="100.00",
    views=0,
    sold=0,
):
    row = {
        "id": listing_id,
        "title": title,
        "listed_date": listed_date if isinstance(listed_date, str) else listed_date.isoformat(),
        "price": str(price),
        "views": str(views),
        "sold": str(sold),
    }
    return parse_listing(row)


class ParseTests(unittest.TestCase):
    def test_parse_iso_date(self):
        self.assertEqual(parse_date("2026-01-15"), date(2026, 1, 15))

    def test_parse_date_rejects_bad_format(self):
        with self.assertRaises(ListingCSVError):
            parse_date("01/15/2026")

    def test_parse_listing_rounds_price(self):
        listing = parse_listing(
            {"id": "x", "title": "t", "listed_date": "2026-01-01",
             "price": "19.9849", "views": "10", "sold": "1"}
        )
        self.assertEqual(listing.price, Decimal("19.98"))

    def test_parse_listing_rejects_negative_price(self):
        row = {"id": "x", "title": "t", "listed_date": "2026-01-01",
               "price": "-5", "views": "10", "sold": "1"}
        with self.assertRaises(ListingCSVError):
            parse_listing(row)

    def test_parse_listing_missing_column(self):
        with self.assertRaises(ListingCSVError):
            parse_listing({"id": "x", "title": "t", "listed_date": "2026-01-01", "price": "1"})


class AgeStaleTests(unittest.TestCase):
    def test_at_threshold_is_stale(self):
        self.assertTrue(is_age_stale(30, 30))

    def test_below_threshold_is_not(self):
        self.assertFalse(is_age_stale(29, 30))

    def test_zero_age_not_stale(self):
        self.assertFalse(is_age_stale(0, 30))


class CartStaleTests(unittest.TestCase):
    def test_below_threshold_is_stale(self):
        self.assertTrue(is_cart_stale(0.01, 0.02))

    def test_at_threshold_is_not(self):
        self.assertFalse(is_cart_stale(0.02, 0.02))

    def test_zero_views_counts_as_stale(self):
        self.assertTrue(is_cart_stale(None, 0.02))


class HoldingCostTests(unittest.TestCase):
    def test_one_year_at_10pct(self):
        self.assertEqual(
            holding_cost(Decimal("100.00"), 0.10, 365), Decimal("10.00")
        )

    def test_thirty_days(self):
        self.assertEqual(
            holding_cost(Decimal("100.00"), 0.10, 30), Decimal("0.82")
        )

    def test_zero_age_is_zero(self):
        self.assertEqual(holding_cost(Decimal("100.00"), 0.10, 0), Decimal("0.00"))

    def test_negative_age_is_zero(self):
        self.assertEqual(holding_cost(Decimal("100.00"), 0.10, -5), Decimal("0.00"))


class ReviewRowFlagTests(unittest.TestCase):
    def test_fresh_selling_listing_is_ok(self):
        row = review_row(
            make_listing(listed_date="2026-10-20", views=100, sold=5),
            TODAY,
            age_threshold=30,
            cart_threshold=0.02,
            holding_rate=0.10,
            ladder_step=0.05,
            ladder_tiers=3,
            ladder_interval=14,
        )
        self.assertEqual(row.flag, FLAG_OK)
        self.assertEqual(row.ladder, ())
        self.assertEqual(row.age, 17)
        self.assertFalse(row.age_stale)
        self.assertFalse(row.cart_stale)

    def test_old_but_selling_is_watch(self):
        row = review_row(
            make_listing(listed_date="2026-01-01", views=100, sold=10),
            TODAY,
            age_threshold=30,
            cart_threshold=0.02,
            holding_rate=0.10,
            ladder_step=0.05,
            ladder_tiers=3,
            ladder_interval=14,
        )
        self.assertEqual(row.flag, FLAG_WATCH)
        self.assertTrue(row.age_stale)
        self.assertFalse(row.cart_stale)
        self.assertEqual(len(row.ladder), 1)  # WATCH gets one gentle rung

    def test_old_and_low_cart_is_stale(self):
        row = review_row(
            make_listing(listed_date="2026-01-01", views=200, sold=1),
            TODAY,
            age_threshold=30,
            cart_threshold=0.02,
            holding_rate=0.10,
            ladder_step=0.05,
            ladder_tiers=3,
            ladder_interval=14,
        )
        self.assertEqual(row.flag, FLAG_STALE)
        self.assertTrue(row.age_stale)
        self.assertTrue(row.cart_stale)
        self.assertEqual(len(row.ladder), 3)

    def test_zero_views_and_old_is_stale(self):
        row = review_row(
            make_listing(listed_date="2026-01-01", views=0, sold=0),
            TODAY,
            age_threshold=30,
            cart_threshold=0.02,
            holding_rate=0.10,
            ladder_step=0.05,
            ladder_tiers=3,
            ladder_interval=14,
        )
        self.assertEqual(row.flag, FLAG_STALE)

    def test_relist_date_is_one_interval_past_final_rung(self):
        row = review_row(
            make_listing(listed_date="2026-01-01", views=200, sold=1),
            TODAY,
            age_threshold=30,
            cart_threshold=0.02,
            holding_rate=0.10,
            ladder_step=0.05,
            ladder_tiers=3,
            ladder_interval=14,
        )
        # rungs land at TODAY+14/+28/+42; re-list one interval later (2027-01-01)
        self.assertEqual(row.relist_date, date(2027, 1, 1))


class ReviewListingsSortTests(unittest.TestCase):
    def test_sorted_by_holding_cost_desc(self):
        rows = review_listings(
            [
                make_listing(listing_id="cheap", listed_date="2026-11-01", price="50.00"),
                make_listing(listing_id="pricy", listed_date="2026-01-01", price="500.00"),
                make_listing(listing_id="mid", listed_date="2026-10-01", price="200.00"),
            ],
            TODAY,
        )
        ids = [row.listing.listing_id for row in rows]
        self.assertEqual(ids[0], "pricy")
        self.assertEqual(ids[-1], "cheap")
        costs = [row.holding_cost for row in rows]
        self.assertEqual(costs, sorted(costs, reverse=True))

    def test_empty(self):
        self.assertEqual(review_listings([], TODAY), [])


if __name__ == "__main__":
    unittest.main()
