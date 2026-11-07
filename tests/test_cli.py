"""Tests for CSV loading, worksheet rendering, and CLI exit paths."""

import argparse
import contextlib
import io
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from stale_listing_reviewer.cli import main, parse_today
from stale_listing_reviewer.core import (
    FLAG_OK,
    FLAG_STALE,
    FLAG_WATCH,
    ListingCSVError,
    load_listings,
    review_listings,
)
from stale_listing_reviewer.worksheet import HEADER, render_markdown, render_text

SAMPLE = """id,title,listed_date,price,views,sold
vintage-weenie,Classic 1992 VHS sealed,2026-01-05,45.00,180,1
boots-820A,Steel toe boots size 10,2026-10-02,120.00,95,2
board-game,Ticket to Ride 1st ed,2026-10-20,30.00,40,0
camera-30,Canon AF film camera,2026-11-01,15.00,0,0
"""
TODAY = date(2026, 11, 6)


class LoadListingsTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        Path(self.path).write_text(SAMPLE, encoding="utf-8")

    def tearDown(self):
        Path(self.path).unlink()

    def test_load_sample(self):
        listings = load_listings(self.path)
        self.assertEqual(len(listings), 4)
        self.assertEqual(listings[0].title, "Classic 1992 VHS sealed")
        self.assertEqual(listings[1].price, Decimal("120.00"))
        self.assertEqual(listings[3].views, 0)

    def test_missing_required_column_raises(self):
        bad = Path(self.path).with_name("bad-cols.csv")
        bad.write_text("id,title,price\nx,t,1.00\n", encoding="utf-8")
        try:
            with self.assertRaises(ListingCSVError):
                load_listings(bad)
        finally:
            bad.unlink()


class FixtureTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        Path(self.path).write_text(SAMPLE, encoding="utf-8")

    def tearDown(self):
        Path(self.path).unlink()

    def test_flags_match_expectations(self):
        rows = review_listings(load_listings(self.path), TODAY)
        flags = {row.listing.listing_id: row.flag for row in rows}
        self.assertEqual(flags["boots-820A"], FLAG_WATCH)   # 35d old but good cart rate
        self.assertEqual(flags["vintage-weenie"], FLAG_STALE)  # old + 0.6% carts
        self.assertEqual(flags["board-game"], FLAG_WATCH)   # old enough, some carts
        self.assertEqual(flags["camera-30"], FLAG_WATCH)    # young, zero views: WATCH, not STALE

    def test_render_text_contains_header_and_flags(self):
        text = render_text(review_listings(load_listings(self.path), TODAY), TODAY)
        for token in (HEADER[0], "STALE", "WATCH", "OK", "holding cost"):
            self.assertIn(token, text)

    def test_markdown_renders_pipe_table(self):
        md = render_markdown(review_listings(load_listings(self.path), TODAY), TODAY)
        self.assertTrue(md.startswith("# Stale Listing Review"))
        self.assertIn("| ID | TITLE |", md)


class CliTests(unittest.TestCase):
    def setUp(self):
        fd, self.csv_path = tempfile.mkstemp(suffix=".csv")
        Path(self.csv_path).write_text(SAMPLE, encoding="utf-8")

    def tearDown(self):
        Path(self.csv_path).unlink()

    def test_parse_today(self):
        self.assertEqual(parse_today("2026-11-06"), TODAY)
        self.assertIn(parse_today(None), (date(2026, 11, 7), date.today()))

    def test_parse_today_bad(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_today("tomorrow")

    def test_main_prints_worksheet(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main([self.csv_path, "--today", "2026-11-06"])
        self.assertEqual(code, 0)
        out = buffer.getvalue()
        self.assertIn("vintage-weenie", out)
        self.assertIn("42.75@", out)  # stale ladder rung 1: 45 * 0.95

    def test_main_writes_markdown_out(self):
        out_md = Path(self.csv_path).with_suffix(".md")
        try:
            code = main([self.csv_path, "--today", "2026-11-06", "--out", str(out_md)])
            self.assertEqual(code, 0)
            self.assertIn("STALE", out_md.read_text(encoding="utf-8"))
        finally:
            out_md.unlink(missing_ok=True)

    def test_main_bad_csv_returns_error(self):
        bad = Path(self.csv_path).with_name("bad.csv")
        bad.write_text("id,foo\n1,bar\n", encoding="utf-8")
        try:
            code = main([str(bad), "--today", "2026-11-06"])
        except SystemExit as exc:
            code = exc.code
        self.assertEqual(code, 2)
        bad.unlink()

    def test_main_missing_file_returns_error(self):
        try:
            code = main(["nope-not-here.csv"])
        except SystemExit as exc:
            code = exc.code
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
