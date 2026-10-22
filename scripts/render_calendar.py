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

def session_dt(item):
    clock = time(16) if item['session'] == 'after_close' else time(9, 30)
    return datetime.combine(date.fromisoformat(item['date']), clock,
                            ZoneInfo(item['exchange_timezone'])).astimezone(PACIFIC)

def timing(item):
    if item.get('at'):
        return ('Approx. ' if item.get('approximate') else '') + stamp(exact(item['at']))
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
    def sort_key(event):
        if event.get('release', {}).get('at'):
            return exact(event['release']['at'])
        if event.get('call', {}).get('at'):
            return exact(event['call']['at'])
        return session_dt(event['release'])
    for event in sorted(events, key=sort_key):
        call = timing(event.get('call', {}))
        if event.get('call', {}).get('type') == 'presentation':
            call += ' (presentation)'
        lines.append(f'| {event["company"]} | {event["ticker"]} | {timing(event.get("release", {}))} | {call} | {sources(event)} |')
    return '\n'.join(lines)

def render(data):
    start, end = map(date.fromisoformat, [data['week_start'], data['week_end']])
    in_week = [e for e in data['events'] if start <= event_date(e) <= end]
    later = [e for e in data['events'] if event_date(e) > end]
    lines = ['# AI earnings calendar', '',
             f'**Week: {start:%B %d}–{end:%d, %Y} · Updated: {data["updated_at_pacific"]}**', '',
             'All dates, weekdays, and clock times are in **America/Los_Angeles (Pacific time)**. PDT/PST adjusts with daylight saving time. Midnight means the start of the stated date.', '',
             'Regions follow the selected IBKR watchlist groups: US AI, Korean AI, Japan AI, Taiwan AI, and Euro AI. China AI is excluded. A foreign issuer held through a U.S. listing remains in the U.S. watchlist section.', '',
             'Results releases and earnings calls are separate events. Before/after market open/close uses the relevant exchange; U.S. regular hours are 6:30 a.m.–1:00 p.m. Pacific. Session labels do not establish an exact release minute.', '',
             f'**{len(in_week)} identified company earnings events this week.** Past events remain visible for the full week. Dates and times below reflect the cited announcement; this page does not certify attendance or completion of a call.', '',
             '[United States](#united-states) · [Korea](#korea) · [Japan](#japan) · [Taiwan](#taiwan) · [Europe](#europe)', '']
    for region in REGIONS:
        lines += [f'## {region}', '']
        regional = [e for e in in_week if e['region'] == region]
        lines += [table(regional) if regional else 'No company-confirmed earnings event identified for this week; see unresolved dates below.', '']
        for e in regional:
            if e.get('notes'):
                lines += [f'- **{e["ticker"]}:** {e["notes"]}', '']
    if later:
        lines += ['## Confirmed later dates', '',
                  'Selected verified dates beyond this week, retained when an event moves. This is not a complete preview of the following week.', '', table(later), '']
    lines += ['## Unresolved dates and coverage limits', '']
    for item in data['unresolved']:
        lines += [f'- **{item["company"]} ({item["ticker"]}, {item["region"]}):** {item["note"]} ' + ', '.join(f'[{s["label"]}]({s["url"]})' for s in item.get('sources', [])), '']
    lines += [data['coverage_note'], '', '## Schedule changes', '']
    for item in data['changes']:
        lines += [f'- **{item["date"]}:** {item["note"]}', '']
    lines += ['## Updates and history', '',
              'Daily refresh is scheduled through Codex at **9:00 a.m. America/Los_Angeles**. It fetches the selected watchlists afresh and verifies public earnings announcements. On Sundays the preview advances to the coming Monday–Sunday. Weekly snapshots are saved in [`weeks/`](weeks/); Git history records daily revisions.', '',
              'The schedule runs through the connected Codex automation, not GitHub Actions. Its operation depends on the connected IBKR and GitHub services and the automation being able to run. The timestamp above is the most recent successful publication, not a claim of continuous monitoring.', '',
              '[Structured calendar](data/calendar.json) · [Update procedure](RUNBOOK.md)', '']
    return '\n'.join(lines)

def main():
    data = json.loads((ROOT / 'data/calendar.json').read_text())
    ids = [e['id'] for e in data['events']]
    assert len(ids) == len(set(ids)), 'Duplicate company events'
    for event in data['events']:
        assert event['region'] in REGIONS
        assert event['sources'] and all(s['url'].startswith('https://') for s in event['sources'])
        event_date(event)
    text = render(data)
    (ROOT / 'README.md').write_text(text)
    (ROOT / 'weeks').mkdir(exist_ok=True)
    (ROOT / f'weeks/{data["week_start"]}.md').write_text(text.replace('(weeks/)', '(./)').replace('(data/calendar.json)', '(../data/calendar.json)').replace('(RUNBOOK.md)', '(../RUNBOOK.md)'))
    print(f'Rendered {len(ids)} source-backed events across {len(REGIONS)} regions')

if __name__ == '__main__':
    main()
