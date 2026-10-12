"""Behavioral checks for the single-date display contract, with synthetic clocks."""
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gann.multiclock import WINDOW_COLUMNS
from gann.time_points import KEY_POINT_COLUMNS, MEMBER_COLUMNS, select_time_key_points
from build_multiclock_time_ledger import write_summary

AS_OF = pd.Timestamp("2026-09-22")
END = pd.Timestamp("2026-11-30")


def window(identifier, center="2026-09-25", *, source="major_natural", causal="price_pivot_clock",
           clock="natural_day", tolerance=2, status="calendar_day", confirm="2026-09-21",
           start=None, end=None):
    center = pd.Timestamp(center)
    return dict(zip(WINDOW_COLUMNS, [
        source, causal, clock, pd.Timestamp("2026-06-27"), "L", 3000,
        pd.Timestamp(confirm), 90, None, center,
        pd.Timestamp(start) if start else center - pd.Timedelta(days=tolerance),
        pd.Timestamp(end) if end else center + pd.Timedelta(days=tolerance),
        tolerance, status, identifier,
    ]))


def sessions():
    # Explicit synthetic open-only fixture; Sep 26/27 are deliberately absent.
    return pd.DataFrame({"date": pd.bdate_range("2026-09-21", END), "session_status": "exchange_calendar"})


def select(rows, calendar=None, **kwargs):
    return select_time_key_points(pd.DataFrame(rows, columns=WINDOW_COLUMNS),
                                  sessions() if calendar is None else calendar, AS_OF, END, **kwargs)


class TimePointTests(unittest.TestCase):
    def test_only_original_centers_not_coverage_days(self):
        rows = [window(str(i)) for i in range(3)]
        points, members = select(rows)
        self.assertEqual(points["date"].tolist(), [pd.Timestamp("2026-09-25")])
        self.assertEqual(len(members), 3)
        self.assertTrue(members["is_exact_center"].all())
        self.assertNotIn("start_date", points)
        self.assertIn("start_date", members)

    def test_future_confirmation_cannot_supply_center_or_density(self):
        rows = [window("known"), window("future1", confirm="2026-09-23"),
                window("future2", confirm="2026-09-24")]
        self.assertTrue(select(rows)[0].empty)

    def test_center_must_be_after_confirmation_and_inside_valid_window(self):
        self.assertTrue(select([window(str(i), confirm="2026-09-25") for i in range(3)])[0].empty)
        self.assertTrue(select([window(str(i), start="2026-09-26") for i in range(3)])[0].empty)

    def test_shared_price_clocks_are_not_independent(self):
        rows = [window("natural"), window("major", source="major_trading", clock="trading_bar", status="exchange_calendar"),
                window("local", source="local_trading", clock="trading_bar", status="exchange_calendar")]
        points, _ = select(rows)
        self.assertEqual(points.iloc[0]["source_family_count"], 3)
        self.assertEqual(points.iloc[0]["independent_family_count"], 1)
        self.assertTrue(select(rows[:2])[0].empty)

    def test_two_causal_families_can_qualify(self):
        rows = [window("price"), window("wave", source="wave_duration", causal="wave_duration")]
        points, _ = select(rows)
        self.assertEqual(points.iloc[0]["window_count"], 2)
        self.assertEqual(points.iloc[0]["independent_family_count"], 2)

    def test_sensitivity_and_duplicate_ids_do_not_inflate_counts(self):
        rows = [window("a"), window("a", tolerance=3), window("b"), window("c", tolerance=3)]
        self.assertTrue(select(rows)[0].empty)
        rows += [window("d"), window("d")]
        points, members = select(rows)
        self.assertEqual(points.iloc[0]["window_count"], 3)
        self.assertEqual(set(members["window_id"]), {"a", "b", "d"})
        self.assertTrue(members["tolerance"].eq(2).all())

    def test_holiday_natural_center_is_not_shifted(self):
        points, _ = select([window(str(i), center="2026-09-26") for i in range(3)])
        self.assertEqual(points.iloc[0]["date"], pd.Timestamp("2026-09-26"))
        self.assertEqual(points.iloc[0]["session_status"], "natural_nontrading_day")

    def test_missing_calendar_keeps_natural_date_with_uncertainty(self):
        estimated = sessions().assign(session_status="estimated_weekday")
        points, _ = select([window(str(i)) for i in range(3)], calendar=estimated)
        self.assertEqual(points.iloc[0]["session_status"], "natural_calendar_unverified")

    def test_estimated_trading_centers_and_contributors_are_excluded(self):
        rows = [window("price"), window("t1", clock="trading_bar", status="estimated_weekday"),
                window("t2", clock="trading_bar", status="estimated_weekday")]
        self.assertTrue(select(rows)[0].empty)
        # A misleading row status alone cannot substitute for a session calendar.
        rows = [window(str(i), clock="trading_bar", status="exchange_calendar") for i in range(3)]
        self.assertTrue(select(rows, calendar=sessions().assign(session_status="estimated_weekday"))[0].empty)

    def test_nearby_highest_rank_wins_over_earliest(self):
        rows = [window(f"a{i}", "2026-09-25", tolerance=0) for i in range(3)]
        rows += [window(f"b{i}", "2026-09-29", tolerance=0) for i in range(4)]
        points, _ = select(rows)
        # Two exchange intervals (Mon/Tue), although four calendar days apart.
        self.assertEqual(points["date"].tolist(), [pd.Timestamp("2026-09-29")])

    def test_ties_are_deterministic_and_maximum_is_chronological(self):
        rows = [window(f"{d}:{i}", d, tolerance=0) for d in ("2026-09-25", "2026-09-29") for i in range(3)]
        self.assertEqual(select(rows)[0]["date"].tolist(), [pd.Timestamp("2026-09-25")])
        dates = pd.date_range("2026-09-25", periods=9, freq="7D")
        rows = [window(f"{d}:{i}", d, tolerance=0) for d in dates for i in range(3)]
        points, _ = select(rows)
        self.assertEqual(len(points), 8)
        self.assertEqual(points["date"].tolist(), list(dates[:8]))
        self.assertEqual(select(list(reversed(rows)))[0]["date"].tolist(), points["date"].tolist())

    def test_past_center_may_supply_future_overlap_but_not_future_key(self):
        rows = [window("past", "2026-09-22", confirm="2026-09-21", end="2026-09-26"),
                window("future1"), window("future2")]
        points, members = select(rows)
        self.assertEqual(points.iloc[0]["window_count"], 3)
        self.assertEqual(points.iloc[0]["center_member_count"], 2)
        self.assertEqual(int(members["is_exact_center"].sum()), 2)

    def test_empty_headers_and_horizon(self):
        points, members = select([])
        self.assertEqual(list(points.columns), KEY_POINT_COLUMNS)
        self.assertEqual(list(members.columns), MEMBER_COLUMNS)
        self.assertTrue(select([window(str(i), "2026-12-01") for i in range(3)])[0].empty)

    def test_summary_projects_selected_rows_not_audit_intervals(self):
        rows = [window(str(i)) for i in range(3)]
        points, _ = select(rows)
        confirmation = pd.DataFrame(columns=["date"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.md"
            write_summary(path, AS_OF, points, pd.DataFrame(rows), confirmation, "synthetic open-only calendar")
            text = path.read_text()
        table = text.split("## 重要关键时间点", 1)[1].split("仅展示", 1)[0]
        lines = [line for line in table.splitlines() if line.startswith("| 2026-")]
        self.assertEqual(len(lines), 1)
        cells = [cell.strip() for cell in lines[0].split("|")[1:-1]]
        self.assertEqual(len(cells), 12)
        self.assertEqual(cells[0], "2026-09-25")
        self.assertEqual(cells[9], "0、1、2")
        # Source confirmations are actual single dates, never tolerance edges.
        self.assertEqual(cells[10:12], ["2026-06-27", "2026-09-21"])
        self.assertNotIn("2026-09-23", table)
        self.assertNotIn("2026-09-27", table)


if __name__ == "__main__":
    unittest.main()
