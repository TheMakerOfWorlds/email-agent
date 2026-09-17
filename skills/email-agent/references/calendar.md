# Calendar

Use `python3 <plugin-root>/scripts/google_agent.py calendar ACCOUNT ACTION --input FILE`.
Choose the company/account first. `calendars` lists names, access roles, primary flag and refs; do not infer a calendar from email sender aliases. An explicitly supplied `"calendar":"primary"` means that selected account's primary calendar. Otherwise supply its calendar ref. Shared calendars may expose titles/details to others.

| Action | Input JSON |
| --- | --- |
| `calendars` | `{}` |
| `events` | `{"calendar":"CALENDAR_REF","after":"2026-10-01T00:00:00-07:00","before":"2026-10-08T00:00:00-07:00","query":"optional words"}` |
| `availability` | `{"calendars":["CALENDAR_REF"],"after":"...offset time...","before":"...offset time..."}` |
| `get` | `{"ref":"EVENT_REF"}` |
| `create` | `{"calendar":"CALENDAR_REF","event":{"summary":"Project review","start":{"dateTime":"2026-10-01T10:00:00-07:00"},"end":{"dateTime":"2026-10-01T10:30:00-07:00"},"attendees":[{"email":"requested-guest@example.com"}]},"meet":true,"notify":"all"}` |
| `update` | `{"ref":"EVENT_REF","event":{"summary":"New title"},"notify":"all"}` |
| `cancel` | `{"ref":"EVENT_REF","notify":"all"}` |

Create/update/cancel require `--request-id STABLE_ID`; use `--preview` to inspect the local plan. `event` accepts summary, description, location, start/end, attendees, recurrence, visibility, transparency, reminders. Start/end must both be offset-qualified dateTime values, or all-day date values with exclusive end. For recurrence, include the intended IANA timeZone in start/end. Do not assume a time zone from an ambiguous time.

`meet:true` creates a unique conference on an event. Read the event again if conference status is pending; do not promise a usable link until it appears. Standalone links use the Meet reference. Meeting creation may be limited by the selected account's Google policies.

Invites/updates/cancellations to events with guests require explicit `notify:all`. These send notifications: include only authorized recipients. `notify:none` is for a personal event without guests, not a way to silently change an invited event. Existing refs fix the calendar; moving an event between accounts is not supported.

Event list output includes organizer, creator, attendees and links. Google may report attendee truncation; fetch one event and do not assume unseen invitees. `--limit` 1–25 and `--cursor` page matching searches. Availability returns busy intervals without event descriptions; use that for cross-account conflict checks when private details are unnecessary. Query each chosen account separately; do not put another account's refs into this command.
