# Calendar backend contract (Phase 3) — owner: Admin agent

Status: **coded and tested offline, not deployed, not wired.** Builder adds the routes (bottom of this file). Mobile and Designer: code against the shapes below. All JSON errors are `{ "error": code, "message": text }`. JWT (student pool) on everything except `GET /cal/{token}.ics`.

## Assignment object

```
{
  id: "ab12cd34",             // 8 chars
  courseId: "ef56gh78",
  courseCode: "MIS 405",      // read-only, joined from the course ("" if unknown)
  courseColor: "#0D9488",     // read-only, the class colour (use data-theme / classIndexFromHex)
  title: "Quiz 3",
  type: "exam|quiz|homework|project|paper|reading|study|other",
  dueDate: "2026-11-05" | null,   // YYYY-MM-DD in the CAMPUS timezone
  dueTime: "14:30" | null,        // HH:MM 24h, campus timezone. null = all-day
  weight: 10 | null,              // percent of grade
  notes: "",
  done: false,
  source: "syllabus|feed|manual|agent",
  dateSource: "stated|resolved|manual" | null,   // "resolved" = estimated, show it as such; "manual" = the student set or confirmed it
  dueText: "the Friday after Exam 1" | "",       // syllabus wording, informational
  sequence: 0,                    // bumps on every edit; used by the iCal feed
  createdAt, updatedAt            // ISO UTC
}
```

## GET /assignments

Query (all optional): `from=YYYY-MM-DD`, `to=YYYY-MM-DD` (inclusive, on `dueDate`), `courseId=<id>`, `done=true|false`, `undated=include` (undated items are left out whenever `from` or `to` is given, unless this is set).
`200 { assignments: Assignment[] }` sorted by `dueDate`, then `dueTime`, then title; undated last. At most 500 items.
Errors: `400 validation_error` (bad date, `from` after `to`, bad id), `404 not_found` (unknown/other user's `courseId`).

## POST /assignments (manual add)

Body: `{ courseId (required), title (required, 1-160), type (required), dueDate?, dueTime?, notes? (<=400), weight? (0-100) }`. `dueTime` needs `dueDate`.
`201 { assignment }` with `source: "manual"`, `dateSource: "manual"` (if a date was given), `sequence: 0`.
Errors: `400 validation_error` (message names the field), `404 not_found` (class is not yours), `409 limit` (400 items in that class), `429 rate_limited`.

## PATCH /assignments/{id}

Body: any of `title, type, dueDate (null clears), dueTime (null clears), notes, weight (null clears), done`. Unknown fields are rejected. The class cannot be changed. Dates must be real calendar dates within 800 days of today.
Changing `dueDate` or `dueTime` sets `dateSource: "manual"`. Every change bumps `sequence` and `updatedAt`.
`200 { assignment }`. Errors: `400 validation_error`, `404 not_found` (id not yours or not found), `429 rate_limited`.
Marking `done: true` removes the item from the outbound iCal feed (the subscribed calendar deletes the event); `done: false` brings it back.

## POST /me/calendar-token/rotate

No body. Creates a new random token (32 url-safe chars), points the profile at it and **deletes the old token mapping, so the old feed URL stops working immediately** (404).
`200 { calToken, calendarPath: "/cal/<token>.ics" }`. The full URL is `<apiUrl>` + `calendarPath`; `webcal://` links use the same host and path. The token is a secret: never log it, never show it in a screenshot. `429 rate_limited` after 5 rotations a day.
`/me` should expose the same `calendarPath` (Builder: build it from `profile.calToken`).

## GET /cal/{token}.ics (public, no JWT)

`200`, `Content-Type: text/calendar; charset=utf-8`, `Cache-Control: private, max-age=300`, `Referrer-Policy: no-referrer`. Any token that is malformed, unknown, rotated away, or whose user no longer exists returns the same `404 { error: "not_found" }`. `429` only for a client that has produced many misses in an hour (per-IP, on misses only, so shared Google or campus NAT addresses are not blocked by successful refreshes).

Feed contents:
- `X-WR-CALNAME:Semester OS`, `REFRESH-INTERVAL;VALUE=DURATION:PT1H`, `X-PUBLISHED-TTL:PT1H`, `METHOD:PUBLISH`.
- One event per not-done assignment that has a `dueDate`. UID `{assignmentId}@semesteros`, stable. `SEQUENCE` = the item's `sequence`. `DTSTAMP` = the item's `updatedAt`.
- No time: all-day (`DTSTART;VALUE=DATE`, `DTEND` the next day, transparent). With a time: a 30-minute event ending at the due time, converted from the campus timezone to UTC (`...Z`), DST-correct.
- `SUMMARY` is `[MIS 405] Quiz 3` (course code prefix when known). `DESCRIPTION` has type, weight, notes, and "Date estimated from the syllabus; check it" for `dateSource: "resolved"`.
- Study blocks: if `STUDY#...` items exist (`{id, courseId, start, end, focus, sequence, updatedAt}`, ISO times), they appear as events. Plan blocks come later.
- Every text value goes through `guard.ical_text` (newlines can never add properties), lines are folded at 75 octets, the file uses CRLF.
- Honest note for the UI: Google Calendar refreshes subscribed feeds on its own schedule (often many hours); Apple and Outlook are faster; the in-app calendar is always live.

## Data and safety rules (all handlers)
- Every user item is addressed through `guard.UserScopedDB(sub, db)`: partition key is always `USER#{sub}` from the JWT; ids from the client only select a sort key.
- All text is cleaned with `guard.clean_text` (control, bidi, zero-width removed) and length-capped on write; the feed escapes it again on output.
- Nothing logs tokens.

## Wiring for Builder (small; Admin did not touch api.py or stack.py)

`backend/api.py`:
```python
import assignments_api, calendar_api
...
# public, before the JWT section (replace the get_calendar stub):
if path.startswith("/cal/") and method == "GET":
    return calendar_api.get_feed(event)

# protected section, after `sub = _get_sub(event)`:
if path == "/assignments" and method == "GET":
    return assignments_api.list_assignments(event, sub)
if path == "/assignments" and method == "POST":
    return assignments_api.create_assignment(event, sub)
m = re.fullmatch(r"/assignments/([a-z0-9]{8})", path)
if m and method == "PATCH":
    return assignments_api.update_assignment(event, sub, m.group(1))
if path == "/me/calendar-token/rotate" and method == "POST":
    return calendar_api.rotate_token(event, sub)
```
Delete the old `get_calendar` stub. In `get_me`, create the first token with `calendar_api.new_token()` (same format) and return `calendarPath` next to `profile`.

`infra/stack.py`: nothing new in IAM (api_fn already has read/write on the table, which covers the conditional counter updates). `/cal/{proxy+}` is already a public route and `/{proxy+}` (JWT) already covers `/assignments*` and `/me/calendar-token/rotate`. Optional: set `IP_HASH_SALT` in the API Lambda environment so the hashed-IP counters use a private salt.

Tests: `python -I -m unittest discover -s backend/tests` from the repo root (files `test_assignments_api.py`, `test_ics.py`, `test_calendar_api.py`).
