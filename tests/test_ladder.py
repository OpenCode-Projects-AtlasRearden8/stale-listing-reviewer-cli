"""Tests for price-drop ladder math and re-list dates."""

import unittest
from datetime import date
from decimal import Decimal

from stale_listing_reviewer.core import build_ladder, money, relist_date

START = date(2026, 11, 6)


class BuildLadderTests(unittest.TestCase):
    def test_basic_three_rung_ladder(self):
        rungs = build_ladder(Decimal("100.00"), 0.05, 3, 14, START)
        self.assertEqual(len(rungs), 3)
        self.assertEqual(rungs[0].price, Decimal("95.00"))
        self.assertEqual(rungs[1].price, Decimal("90.00"))
        self.assertEqual(rungs[2].price, Decimal("85.00"))

    def test_steps_are_percent_of_original_price(self):
        # 100 -> each rung drops 5% of the ORIGINAL price, not compounding.
        rungs = build_ladder(Decimal("100.00"), 0.05, 3, 14, START)
        deltas = [Decimal("100.00") - r.price for r in rungs]
        self.assertEqual(deltas, [Decimal("5.00"), Decimal("10.00"), Decimal("15.00")])

    def test_rung_dates_spaced_by_interval(self):
        rungs = build_ladder(Decimal("100.00"), 0.05, 3, 14, START)
        self.assertEqual(rungs[0].effective_date, date(2026, 11, 20))
        self.assertEqual(rungs[1].effective_date, date(2026, 12, 4))
        self.assertEqual(rungs[2].effective_date, date(2026, 12, 18))

    def test_first_rung_is_one_interval_after_start(self):
        rungs = build_ladder(Decimal("40.00"), 0.10, 2, 7, START)
        self.assertEqual(rungs[0].effective_date, date(2026, 11, 13))

    def test_money_is_rounded_to_cents(self):
        # 33.37 at 7% off of the original: 33.37*0.93 = 31.0341 -> 31.03
        rungs = build_ladder(Decimal("33.37"), 0.07, 1, 14, START)
        self.assertEqual(rungs[0].price, Decimal("31.03"))

    def test_money_rounds_half_up(self):
        # 3.33 * 0.95 = 3.1635 -> .1635 rounds half-up to .17? 1635 -> 16.35 cents
        # -> .1635 in cents is 16.35c; HALF_UP gives 16c? No: 0.01 cent ULP,
        # 3.1635 = 316.35 cents -> 316 cents? HALF_UP on .35 -> 3.16? Keep exact:
        # half-up: 316.35c -> 316.4c? ULP is 1 cent here (two decimals: 3.16 or
        # 3.16+). 3.1635 quantized to cents HALF_UP -> 3.16? No: 3.1635 = 3.1600
        # + 0.0035 -> rounds at 2nd decimal: third digit 3 -> 3.16.
        # Use a clean tie instead: 2.335 -> 2.34 (HALF_UP), Python default
        # banker's would give 2.34 too, so use 2.345: HALF_UP -> 2.35.
        rungs = build_ladder(Decimal("4.69"), 0.5, 1, 14, START)
        # 4.69 * 0.50 = 2.345 exactly -> HALF_UP -> 2.35
        self.assertEqual(rungs[0].price, Decimal("2.35"))

    def test_zero_tiers_gives_empty_ladder(self):
        self.assertEqual(build_ladder(Decimal("100.00"), 0.05, 0, 14, START), ())

    def test_single_rung(self):
        rungs = build_ladder(Decimal("10.00"), 0.25, 1, 30, START)
        self.assertEqual(rungs[0].price, Decimal("7.50"))
        self.assertEqual(rungs[0].run, 1)

    def test_step_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            build_ladder(Decimal("100.00"), 1.5, 3, 14, START)
        with self.assertRaises(ValueError):
            build_ladder(Decimal("100.00"), -0.05, 3, 14, START)

    def test_tiers_reject_negative(self):
        with self.assertRaises(ValueError):
            build_ladder(Decimal("100.00"), 0.05, -1, 14, START)

    def test_interval_rejects_zero(self):
        with self.assertRaises(ValueError):
            build_ladder(Decimal("100.00"), 0.05, 3, 0, START)

    def test_ladder_never_goes_negative(self):
        with self.assertRaises(ValueError):
            build_ladder(Decimal("10.00"), 0.05, 25, 14, START)  # 10*.05*25 = 12.5 > 10


class RelistDateTests(unittest.TestCase):
    def test_one_interval_past_final_rung(self):
        # 3 tiers x 14 days: final drop at start+42, re-list at start+56.
        self.assertEqual(relist_date(START, 3, 14), date(2027, 1, 1))

    def test_single_tier(self):
        self.assertEqual(relist_date(START, 1, 14), date(2026, 12, 4))

    def test_zero_tiers_is_one_interval(self):
        self.assertEqual(relist_date(START, 0, 14), date(2026, 11, 20))

    def test_rejects_bad_args(self):
        with self.assertRaises(ValueError):
            relist_date(START, -1, 14)
        with self.assertRaises(ValueError):
            relist_date(START, 3, 0)


class MoneyTests(unittest.TestCase):
    def test_money_half_up(self):
        self.assertEqual(money(Decimal("2.345")), Decimal("2.35"))
        self.assertEqual(money(Decimal("2.344")), Decimal("2.34"))


if __name__ == "__main__":
    unittest.main()
