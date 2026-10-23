"""Boundary checks for the rolling Pacific calendar; no network access."""
import unittest
from datetime import date, datetime, timedelta
from render_calendar import PACIFIC, exact, interval, overlaps, rolling_window, timing


class RollingCalendarTests(unittest.TestCase):
    def test_every_weekday_including_sunday_starts_today(self):
        for offset in range(7):
            day = date(2026, 10, 23) + timedelta(days=offset)
            self.assertEqual(rolling_window(day), (day, day + timedelta(days=6)))

    def test_window_uses_pacific_date(self):
        instant = datetime.fromisoformat('2026-10-24T02:00:00+00:00')
        self.assertEqual(rolling_window(instant)[0], date(2026, 10, 23))

    def test_any_component_can_overlap(self):
        event = {'release': {'at': '2026-10-22T16:00:00-07:00'},
                 'call': {'at': '2026-10-23T08:00:00-07:00'}}
        self.assertTrue(overlaps(event, date(2026, 10, 23), date(2026, 10, 29)))

    def test_seven_dates_have_exclusive_next_midnight(self):
        start, end = rolling_window(date(2026, 10, 23))
        self.assertTrue(overlaps({'call': {'at': '2026-10-29T23:59:59-07:00'}}, start, end))
        self.assertFalse(overlaps({'call': {'at': '2026-10-30T00:00:00-07:00'}}, start, end))
        self.assertFalse(overlaps({'call': {'at': '2026-10-22T23:59:59-07:00'}}, start, end))

    def test_overseas_date_without_time_stays_a_range(self):
        item = {'local_date': '2026-10-30', 'timezone': 'Asia/Tokyo'}
        self.assertIn('Thu, Oct 29, 2026 through Fri, Oct 30, 2026', timing(item))
        self.assertTrue(overlaps({'release': item}, date(2026, 10, 23), date(2026, 10, 29)))

    def test_dst_offsets_and_date_only_day_length(self):
        self.assertEqual(exact('2026-10-28T14:00:00+08:00').strftime('%a %H:%M %Z'), 'Tue 23:00 PDT')
        self.assertEqual(exact('2026-11-03T14:00:00+08:00').strftime('%a %H:%M %Z'), 'Mon 22:00 PST')
        start, end = interval({'local_date': '2026-11-01', 'timezone': 'America/Los_Angeles'})
        self.assertEqual(end.timestamp() - start.timestamp(), 25 * 3600)


if __name__ == '__main__':
    unittest.main()
