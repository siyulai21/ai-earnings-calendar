"""Boundary checks for the rolling Pacific calendar; no network access."""
import unittest
from datetime import date, datetime, timedelta
from render_calendar import PACIFIC, day_marker, exact, interval, overlaps, rolling_window, table, timing


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

    def test_unspecified_source_timezone_preserves_possible_pacific_dates(self):
        release = {'possible_pacific_dates': ['2026-11-01', '2026-11-02'],
                   'note': 'Source timezone unknown; possible November 1–2 Pacific'}
        self.assertTrue(overlaps({'release': release}, date(2026, 10, 26), date(2026, 11, 1)))
        self.assertFalse(overlaps({'release': release}, date(2026, 10, 25), date(2026, 10, 31)))
        self.assertEqual(day_marker(release, date(2026, 11, 1)), '🟡 **POSSIBLY TODAY**')
        self.assertEqual(day_marker(release, date(2026, 11, 2)), '🟡 **POSSIBLY TODAY**')
        self.assertEqual(day_marker(release, date(2026, 11, 3)), '')

    def test_call_today_does_not_highlight_unknown_release(self):
        event = {'company': 'Example', 'ticker': 'EX', 'sources': [],
                 'release': {'note': 'Release time unknown'},
                 'call': {'at': '2026-11-06T08:00:00-05:00'}}
        row = table([event], today=date(2026, 11, 6)).splitlines()[-1].split('|')
        self.assertIn('🟢 **TODAY**', row[1])
        self.assertNotIn('TODAY', row[3])
        self.assertIn('🟢 **TODAY**', row[4])

    def test_conflicting_hours_can_still_establish_a_day(self):
        call = {'alternatives': [{'at': '2026-11-02T17:00:00-04:00'},
                                 {'at': '2026-11-02T17:00:00-05:00'}],
                'note': 'Hour conflicts; no single timestamp selected'}
        self.assertEqual(day_marker(call, date(2026, 11, 2)), '🟢 **TODAY**')
        self.assertEqual(timing(call), call['note'])
        call['alternatives'].append({'note': 'Unbounded alternative'})
        self.assertEqual(day_marker(call, date(2026, 11, 2)), '')

    def test_multi_day_meeting_window_preserves_source_bounds(self):
        item = {'starts_at': '2026-11-04T09:00:00+09:00',
                'ends_at': '2026-11-05T18:00:00+09:00',
                'note': 'Individual appointments unspecified'}
        start, end = interval(item)
        self.assertEqual(start.strftime('%a %H:%M %Z'), 'Tue 16:00 PST')
        self.assertEqual(end.strftime('%a %H:%M %Z'), 'Thu 01:00 PST')
        self.assertEqual(day_marker(item, date(2026, 11, 3)), '🟡 **POSSIBLY TODAY**')
        self.assertTrue(overlaps({'call': item}, date(2026, 11, 5), date(2026, 11, 11)))
        self.assertFalse(overlaps({'call': item}, date(2026, 11, 6), date(2026, 11, 12)))
        self.assertIn('Individual appointments unspecified', timing(item))

    def test_invalid_meeting_window_is_rejected(self):
        with self.assertRaises(ValueError):
            interval({'starts_at': '2026-11-05T18:00:00+09:00',
                      'ends_at': '2026-11-04T09:00:00+09:00'})

    def test_extra_presentation_can_overlap_without_release_or_call(self):
        event = {'release': {'note': 'Unpublished'},
                 'call': {'at': '2026-11-11T11:00:00+01:00'},
                 'presentations': [{'at': '2026-11-11T08:00:00+01:00'}]}
        self.assertTrue(overlaps(event, date(2026, 11, 4), date(2026, 11, 10)))
        self.assertFalse(overlaps(event, date(2026, 11, 3), date(2026, 11, 9)))

    def test_two_presentations_keep_independent_day_markers_in_one_company_row(self):
        event = {'company': 'Example', 'ticker': 'EX', 'sources': [],
                 'release': {'note': 'Release unknown'},
                 'call': {'at': '2026-11-11T11:00:00+01:00', 'label': 'Analyst call'},
                 'presentations': [{'at': '2026-11-11T08:00:00+01:00',
                                    'label': 'Press conference', 'type': 'presentation'}]}
        row = table([event], today=date(2026, 11, 10)).splitlines()[-1].split('|')
        self.assertIn('🟢 **TODAY**', row[1])
        self.assertNotIn('TODAY', row[3])
        analyst, press = row[4].split('<br>')
        self.assertNotIn('TODAY', analyst)
        self.assertIn('🟢 **TODAY**', press)
        self.assertIn('Tue, Nov 10, 2026 · 11:00 pm PST', press)

    def test_date_only_multi_day_presentation_keeps_last_local_day(self):
        item = {'local_date': '2026-11-12', 'local_end_date': '2026-11-13',
                'timezone': 'Asia/Taipei', 'note': 'Individual appointments unspecified'}
        self.assertIn('Wed, Nov 11, 2026 through Fri, Nov 13, 2026', timing(item))
        self.assertTrue(overlaps({'presentations': [item]}, date(2026, 11, 13), date(2026, 11, 19)))
        self.assertEqual(day_marker(item, date(2026, 11, 12)), '🟡 **POSSIBLY TODAY**')
        self.assertIn('Individual appointments unspecified', timing(item))


if __name__ == '__main__':
    unittest.main()
