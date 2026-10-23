#!/usr/bin/env python3
"""Render source-backed regional earnings tables using Pacific calendar dates."""
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PACIFIC = ZoneInfo('America/Los_Angeles')
REGIONS = ['United States', 'Korea', 'Japan', 'Taiwan', 'Europe']

def exact(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError('Exact timestamps must include a UTC offset')
    return dt.astimezone(PACIFIC)

def stamp(dt):
    clock = dt.strftime('%I:%M %p').lstrip('0').lower()
    return f'{dt:%a, %b %d, %Y} · {clock} {dt:%Z}'

def event_date(event):
    for part in ['release', 'call']:
        item = event.get(part, {})
        if item.get('at'):
            return exact(item['at']).date()
        if item.get('session'):
            return session_dt(item).date()
    raise ValueError(f'No dated event: {event["id"]}')

def rolling_window(day):
    """Seven Pacific calendar dates, including the as-of date, on every weekday."""
    if isinstance(day, datetime):
        if day.tzinfo is None:
            raise ValueError('As-of datetime must be timezone-aware')
        day = day.astimezone(PACIFIC).date()
    return day, day + timedelta(days=6)

def interval(item):
    """Possible timing interval; an exact point is represented with a tiny span."""
    if item.get('at'):
        dt = exact(item['at'])
        return dt, dt + timedelta(microseconds=1)
    if item.get('not_before') or item.get('before'):
        key = 'not_before' if item.get('not_before') else 'before'
        source = datetime.fromisoformat(item[key])
        if source.tzinfo is None:
            raise ValueError('Timing bounds require a UTC offset')
        start = datetime.combine(source.date(), time.min, source.tzinfo)
        end = start + timedelta(days=1)
        return ((source if key == 'not_before' else start).astimezone(PACIFIC),
                (end if key == 'not_before' else source).astimezone(PACIFIC))
    if item.get('session'):
        boundary = session_dt(item)
        zone = ZoneInfo(item['exchange_timezone'])
        start = datetime.combine(date.fromisoformat(item['date']), time.min, zone)
        end = start + timedelta(days=1)
        return ((boundary if item['session'] == 'after_close' else start.astimezone(PACIFIC)),
                (end.astimezone(PACIFIC) if item['session'] == 'after_close' else boundary))
    if item.get('local_date'):
        start = datetime.combine(date.fromisoformat(item['local_date']), time.min,
                                 ZoneInfo(item['timezone']))
        return start.astimezone(PACIFIC), (start + timedelta(days=1)).astimezone(PACIFIC)
    return None

def overlaps(event, start, end):
    lower = datetime.combine(start, time.min, PACIFIC)
    upper = datetime.combine(end + timedelta(days=1), time.min, PACIFIC)
    return any(span and span[0] < upper and span[1] > lower
               for span in (interval(event.get(p, {})) for p in ('release', 'call')))

def first_possible(event):
    spans = [interval(event.get(p, {})) for p in ('release', 'call')]
    return min(s[0] for s in spans if s)

def session_dt(item):
    clock = time(16) if item['session'] == 'after_close' else time(9, 30)
    return datetime.combine(date.fromisoformat(item['date']), clock,
                            ZoneInfo(item['exchange_timezone'])).astimezone(PACIFIC)

def timing(item):
    if item.get('at'):
        return ('Approx. ' if item.get('approximate') else '') + stamp(exact(item['at']))
    if item.get('not_before') or item.get('before'):
        key = 'not_before' if item.get('not_before') else 'before'
        prefix = 'At or after ' if key == 'not_before' else 'Before '
        return prefix + stamp(exact(item[key])) + '; exact minute unpublished'
    if item.get('local_date'):
        start, end = interval(item)
        last = end - timedelta(microseconds=1)
        dates = f'{start:%a, %b %d, %Y}'
        if start.date() != last.date():
            dates += f' through {last:%a, %b %d, %Y}'
        zones = start.strftime('%Z')
        if start.strftime('%Z') != last.strftime('%Z'):
            zones += '/' + last.strftime('%Z')
        return f'Possible {dates} {zones}; time unpublished (source date {item["local_date"]}, {item["timezone"]})'
    if item.get('session'):
        dt = session_dt(item)
        relation = 'After' if item['session'] == 'after_close' else 'Before'
        return f'{dt:%a, %b %d, %Y} · {relation} {dt.strftime("%I:%M %p").lstrip("0").lower()} {dt:%Z}; exact minute unpublished'
    return item.get('note', 'Separate release time unpublished')

def sources(event):
    return ', '.join(f'[{s["label"]}]({s["url"]})' for s in event['sources'])

def table(events):
    lines = ['| Company | Ticker | Results release — Pacific | Call / presentation — Pacific | Sources |',
             '|---|---|---|---|---|']
    for event in sorted(events, key=first_possible):
        call = timing(event.get('call', {}))
        if event.get('call', {}).get('type') == 'presentation':
            call += ' (presentation)'
        lines.append(f'| {event["company"]} | {event["ticker"]} | {timing(event.get("release", {}))} | {call} | {sources(event)} |')
    return '\n'.join(lines)

def render(data):
    start, end = map(date.fromisoformat, [data['window_start'], data['window_end']])
    assert (start, end) == rolling_window(start), 'Window must contain exactly seven Pacific dates'
    in_week = [e for e in data['events'] if overlaps(e, start, end)]
    later = [e for e in data['events'] if e not in in_week and any(
        span and span[0].date() > end
        for span in (interval(e.get(p, {})) for p in ('release', 'call')))]
    lines = ['# AI earnings calendar', '',
             f'**Next 7 days: {start:%a, %b %d, %Y}–{end:%a, %b %d, %Y} · Verified: {data["updated_at_pacific"]}**', '',
             'The window includes today and the following six Pacific calendar dates. It advances every day, including Sundays. Today’s already-passed times remain until the next day; earlier dates are preserved in history.', '',
             'All dates, weekdays, and clock times are in **America/Los_Angeles (Pacific time)**. PDT/PST adjusts with daylight saving time. Midnight means the start of the stated date.', '',
             'Regions follow the selected IBKR watchlist groups: US AI, Korean AI, Japan AI, Taiwan AI, and Euro AI. China AI is excluded. An issuer included only through US AI stays in United States. When a native-region list and a foreign-listing alias both contain it, the native watchlist group displays one row with all source labels.', '',
             'Results releases and earnings calls are separate events. Before/after market open/close uses the relevant exchange; U.S. regular hours are 6:30 a.m.–1:00 p.m. Pacific. Session labels do not establish an exact release minute.', '',
             f'**{len(in_week)} identified company results schedules overlap this window.** A row is included when either its release or call/presentation overlaps. Date-only ranges may overlap; they do not confirm one Pacific date. Dates and times reflect cited schedules, not certification that an event occurred.', '',
             '[United States](#united-states) · [Korea](#korea) · [Japan](#japan) · [Taiwan](#taiwan) · [Europe](#europe)', '']
    for region in REGIONS:
        lines += [f'## {region}', '']
        regional = [e for e in in_week if e['region'] == region]
        lines += [table(regional) if regional else 'No company-confirmed earnings event identified in this window; see unresolved dates below.', '']
        for e in regional:
            if len(e.get('watchlists', [])) > 1:
                lines += [f'- **{e["ticker"]} source groups:** ' + ', '.join(e['watchlists']) + '. Shown once; multiple listings are deduplicated.', '']
            if e.get('notes'):
                lines += [f'- **{e["ticker"]}:** {e["notes"]}', '']
    if later:
        lines += ['## Confirmed later dates', '',
                  'Selected verified dates beyond the rolling window, retained when an event moves. This is not an exhaustive later preview.', '', table(later), '']
    lines += ['## Unresolved dates and coverage limits', '']
    for item in data['unresolved']:
        candidate = (' **' + timing(item['candidate']) + '.**') if item.get('candidate') else ''
        lines += [f'- **{item["company"]} ({item["ticker"]}, {item["region"]}):** {item["note"]}' + candidate + ' ' + ', '.join(f'[{s["label"]}]({s["url"]})' for s in item.get('sources', [])), '']
    lines += [data['coverage_note'], '', '## Schedule changes', '']
    for item in data['changes']:
        lines += [f'- **{item["date"]}:** {item["note"]}', '']
    lines += ['## Updates and history', '',
              'Daily refresh is scheduled through Codex at **9:00 a.m. America/Los_Angeles**. Every run fetches the selected watchlists and screens today plus the following six Pacific dates. Sunday chat previews use the same rolling window. Daily snapshots are saved in [`snapshots/`](snapshots/); earlier weekly snapshots remain in [`weeks/`](weeks/). Git history records revisions.', '',
              'The schedule runs through the connected Codex automation. Its operation depends on connected IBKR and GitHub services and the automation being able to run. The verification timestamp records the research time; Git history records publication time.', '',
              '[Structured calendar](data/calendar.json) · [Update procedure](RUNBOOK.md)', '']
    return '\n'.join(lines)

def main():
    data = json.loads((ROOT / 'data/calendar.json').read_text())
    ids = [e['id'] for e in data['events']]
    assert len(ids) == len(set(ids)), 'Duplicate company events'
    for event in data['events']:
        assert event['region'] in REGIONS
        assert event['sources'] and all(s['url'].startswith('https://') for s in event['sources'])
        first_possible(event)
    text = render(data)
    (ROOT / 'README.md').write_text(text)
    (ROOT / 'snapshots').mkdir(exist_ok=True)
    (ROOT / f'snapshots/{data["window_start"]}.md').write_text(text.replace('(snapshots/)', '(./)').replace('(weeks/)', '(../weeks/)').replace('(data/calendar.json)', '(../data/calendar.json)').replace('(RUNBOOK.md)', '(../RUNBOOK.md)'))
    print(f'Rendered {len(ids)} source-backed events across {len(REGIONS)} regions')

if __name__ == '__main__':
    main()
