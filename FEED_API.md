# Blackboard feed sync API (Phase 6)

**Direction v2 (the internal planning notes item D): there is no global Calendar Sync agent. Each CLASS agent checks Blackboard: feed events attach to class agents, every class exposes its own Blackboard stats and a Blackboard tab (`GET /courses/{id}/feed`, `POST /courses/{id}/feed/sync`). Storage stays one feed URL per student and one sync job that processes all of the student's classes. Events that match no class (Unassigned) live in the Study tab.**

Owner: Security/Backend agent. Modules: `backend/feed_api.py` (routes), `backend/lib/feedsync.py` (fetch, parse, diff, classify, upsert), `backend/lib/secretbox.py` (encryption at rest), `backend/sync_blackboard.py` (scheduled poller). Builder wires the routes and the schedule (end of this file). Status: **contract first; code and tests follow, offline only, not deployed, not routed.** Additive changes only after Designer and Mobile start coding against this file; breaks are announced in the internal planning notes.

All routes need the student ID token. The student always comes from the token; ids in the path or body only choose a sort key inside that student's own data. Errors use `{ "error": "<code>", "message": "<text safe to show>" }`. Rate-limit errors are `429` with `Retry-After`.

**We have not seen a real Blackboard feed yet.** Everything about how events map to classes is built to work with whatever the feed contains, and anything uncertain goes to the Unassigned inbox. The UI must therefore make the inbox a first-class, friendly place, not an error state.

## Concepts

- **Feed**: the student's own Blackboard "Share Calendar" iCal link (an https URL). It is a secret: it is never logged and never returned after saving (only a masked form). We never ask for a Blackboard password.
- **Synced event**: one VEVENT, identified by its UID. Each becomes one of three states:
  - `matched`: we are confident which class it belongs to; an assignment was created or updated (`source: "feed"`, `feedUid`).
  - `unassigned`: we are not confident; it waits in the inbox for one click.
  - `dismissed`: the student said it is not a deadline for any class.
- **Uid in this API** is an opaque 24-character id (`[a-f0-9]{24}`), a hash of the calendar UID. Use it as given. Assignments created by the feed carry the same value in `feedUid`.
- Feed dates are written to assignments with `dateSource: "feed"` (a new value besides `stated`, `resolved`, `manual`; treat it as a normal confirmed date, not an estimate). If the student edits an item (any date, title, type or notes), later feed updates do not overwrite what they changed.

## `PUT /me/feed`

Body: `{ "url": "https://..." }` (at most 3,000 bytes; no other fields). `webcal://` links are accepted and converted to `https://`.

The server validates the URL (https, port 443, no credentials, public host only), fetches it once to test it (8 s timeout, 2 MB cap) and checks it parses as a calendar. Then it stores the URL encrypted and schedules the first poll.

`200`:
```
{ "connected": true, "urlMasked": "https://bb.example.edu/…ab12",
  "eventCount": 42, "upcomingCount": 17 }
```
Right after a successful save, call `POST /me/feed/sync` to pull the events straight away (the first manual sync has no cooldown).

Errors: `400 validation_error` (not text, missing url), `400 feed_bad_url` (not an https address), `400 feed_blocked_address`, `feed_dns`, `feed_redirect`, `feed_too_large`, `feed_timeout`, `feed_http_status`, `feed_tls`, `feed_network`, `feed_not_ical` ("That link doesn't look like a calendar feed."), each with a student-safe message that never contains the URL; `429` (bucket `feed_save`, 3 per minute, 30 per day); `413`.

Replacing a feed (PUT again) forgets the previous feed's cache but keeps the assignments already created, and re-links them if the same events appear again.

## `GET /me/feed`

Not connected: `200 { "connected": false }`. Connected:
```
{ "connected": true,
  "urlMasked": "https://bb.example.edu/…ab12",
  "lastCheckedAt": "2026-10-17T12:30:00Z" | null,
  "lastStatus": "never" | "ok" | "unchanged" | "changed" | "error",
  "lastError": null | { "code": "feed_timeout", "message": "The calendar took too long to respond." },
  "nextCheckAt": "2026-10-17T13:30:00Z" | null,
  "counts": { "events": 42, "matched": 30, "unassigned": 9, "dismissed": 3,
              "addedLastSync": 2, "updatedLastSync": 1, "newSinceSeen": 3 },
  "syncCooldownSeconds": 0 }
```
- `lastStatus`: `ok` = checked, nothing new (also used after an unchanged feed), `changed` = something was added or updated, `error` = see `lastError` (the previous data stays). `never` until the first check.
- `syncCooldownSeconds`: seconds until `POST /me/feed/sync` is allowed again (0 = now). Disable the Refresh button while it is above 0.
- The full URL never appears in any response. `GET /me` still returns `profile.feed` with the same non-secret fields (`connected`, `urlMasked`, `lastCheckedAt`, `lastStatus`), so the old `/agents` code keeps working while it is reshaped. (There is no Calendar Sync agent anymore; `/agents` should show per-class Blackboard status from `knows` or `GET /courses/{id}/feed`.)

## `DELETE /me/feed`

`200 { "connected": false }`. Removes the stored URL, the cache of synced events (including the Unassigned inbox) and the learned mapping rules. **Assignments already created stay** (they are the student's data now). Idempotent: deleting when nothing is connected is also `200`.

## `POST /me/feed/sync`

Manual refresh. No body. Per-user cooldown of 120 seconds between manual syncs, plus the `feed_sync` bucket (2 per minute, 24 per day); the poll runs inside the request (about 15 s at most).

`200`:
```
{ "status": "changed" | "unchanged" | "ok",
  "added": 2, "updated": 1, "unassigned": 3, "unchanged": 36, "checkedAt": "2026-10-17T12:30:00Z" }
```
Errors: `409 not_connected`; `429 rate_limited` with `Retry-After` (cooldown); `502 feed_<code>` when the fetch failed (same codes and messages as above; the stored data is untouched and `GET /me/feed` shows `lastStatus: "error"`).

## `GET /feed/unassigned`

The inbox: events we could not place with confidence. Newest due first is not guaranteed, so sort in the UI; the server returns them soonest-due first, undated last, at most 200.
```
{ "unassigned": [
  { "uid": "9f2c...24hex",
    "title": "Quiz 3 due",                    // plain text, at most 160 chars
    "description": "plain text, at most 300",  // HTML stripped
    "categories": ["BUS 301"],                 // as found in the feed, plain text
    "dueDate": "2026-11-05" | null, "dueTime": "23:59" | null, "allDay": false,
    "type": "quiz",                            // our guess from the title
    "firstSeenAt": "2026-10-17T12:30:00Z",
    "suggestions": [ { "courseId": "abcd1234", "courseCode": "MIS 405", "confidence": 0.55 } ] }  // 0 to 3, best first, may be empty
] }
```
All text is untrusted: render it as plain text only (React text nodes, RN `<Text>`). Suggestions are hints, not decisions: show them as pre-selected chips, but one tap on a class is the only thing that assigns.

## `POST /feed/unassigned/{uid}/assign`

Body: `{ "courseId": "abcd1234", "remember": true }` (`remember` optional, default `true`). The course must belong to the student (else `404 not_found`, same answer as for another student's id). The assignment is created from the event (or an existing look-alike is linked, no duplicates), the event becomes `matched`, an activity entry is written, and with `remember` the server learns a rule so similar future events go to that class automatically.

`200 { "assignment": { ...same shape as GET /assignments items... }, "learned": true, "alsoAssigned": 2 }`. `alsoAssigned` is how many other inbox events the new rule placed in the same class straight away (show "and 2 similar items"). Errors: `400 validation_error`, `404 not_found` (unknown uid or course, or the event is no longer unassigned), `409 conflict` never (assigning twice is a `404`).

## `POST /feed/unassigned/{uid}/dismiss`

Body (optional): `{ "remember": false }`. `remember: true` also learns "ignore events like this". `200 { "dismissed": true, "learned": false }`. `404 not_found` for an unknown uid. Dismissed events stay dismissed when the feed changes them; only an event with a new UID shows up again.

## `GET /courses/{id}/feed` (the class page Blackboard tab)

`id` is the class id (404 `not_found` if it is not the student's). Works whether or not a feed is connected.
```
{ "connected": true,
  "stats": { "lastCheckedAt": "2026-10-17T12:30:00Z" | null,
             "lastStatus": "never" | "ok" | "unchanged" | "changed" | "error",
             "lastError": null | { "code": "feed_timeout", "message": "..." },
             "newItemsCount": 3, "unassignedCount": 2, "itemCount": 11, "syncCooldownSeconds": 0 },
  "items": [ { "uid": "9f2c...24hex", "assignmentId": "ab12cd34", "title": "Quiz 3", "type": "quiz",
               "dueDate": "2026-11-05" | null, "dueTime": "23:59" | null, "firstSeenAt": "...", "lastChangedAt": "...",
               "isNew": true, "removedFromFeed": false } ],
  "unassigned": [ ...same item shape as GET /feed/unassigned, only events whose best suggestion is THIS class... ] }
```
- `items`: this class's feed-sourced items (newest change first, at most 100). `isNew` is true for items added since the last `POST /feed/seen` for this class.
- `unassigned`: inbox events whose top suggestion is this class (so the class page can offer "Is this yours?" with one tap); the full inbox is `GET /feed/unassigned` (Study tab).
- Not connected: `{ "connected": false, "stats": null, "items": [], "unassigned": [] }` (show the "add your Blackboard link" prompt, linking to Settings).

## `POST /courses/{id}/feed/sync`

"Check now" on the class page. No body. Runs the same single sync as `POST /me/feed/sync` (the feed is one link for the whole student, so every class is refreshed together), then returns this class's view: `200 { "status": "changed", "added": 1, "updated": 0, "unassigned": 2, "stats": { same as above } }` where `added` and `updated` count this class only and `unassigned` counts the whole inbox. The cooldown (120 s) is per student and shared with `POST /me/feed/sync`; errors are the same (`409 not_connected`, `429`, `502 feed_<code>`), `404` for an unknown class.

## `POST /feed/seen`

Body (optional): `{ "courseId": "abcd1234" }`. Resets the "new from Blackboard" badge (`knows.newItemsCount`) and the `isNew` flags for that class, or for all classes when omitted. Call it when the student opens the class Blackboard tab. `200 { "ok": true }`. Call it when the student opens the class or the activity list.

## What the sync writes elsewhere (read-only for the UI)

- Assignments: `source: "feed"`, `feedUid`, `dateSource: "feed"`; times are the campus wall clock (`dueDate` `YYYY-MM-DD`, `dueTime` `HH:MM`, none for all-day events).
- Class card: `knows.lastFeedCheckAt` on every class at each check; `knows.newItemsCount` goes up by the number of items added to that class; `knows.assignmentsCount` goes up for created items. Per-class Blackboard stats are also on `GET /courses/{id}/feed`.
- Activity feed (`GET /activity`): `kind` is `feed_added`, `feed_updated`, `feed_removed` (agentId = the class id) or `feed_unassigned` (agentId `master`, because the item has no class yet); text such as "MIS 405 agent added: Quiz 3, due Fri Nov 5". Plain text.
- Honest limits to show in the UI: the feed carries dates and events only, not announcements, files or grades; it mixes all classes; some instructors do not use the Blackboard calendar; Blackboard decides how often its feed refreshes, and we check about hourly.

## Classification (for the curious, and for tuning once we see a real feed)

Layers, strongest first, each adds evidence for a class: learned rules (from earlier Assign clicks and earlier feed assignments), course code in the title, categories, description or location (`MIS 405`, `MIS405`, `MIS-405-01`), words from the class title, an acronym of the class title, the instructor's surname. The best class wins only when its confidence is at least 0.75 and it leads the runner-up by at least 0.15; everything else is `unassigned`. The numbers and word lists live in `DEFAULT_RULES` at the top of `backend/lib/feedsync.py` and can be overridden by a JSON file (`backend/data/feed_rules.json`) without code changes. An optional model tie-breaker exists but is off by default (`FEEDSYNC_MODEL=1` turns it on).

## Wiring for Builder (Security did not touch these files)

`backend/api.py`, protected section after `sub = _get_sub(event)`:
```python
import feed_api   # top of file
r = feed_api.handle(event, sub, path, method)   # response dict, or None when the path is not its own
if r is not None:
    return r
```
Owned paths: `PUT|GET|DELETE /me/feed`, `POST /me/feed/sync`, `GET /courses/{id}/feed`, `POST /courses/{id}/feed/sync`, `GET /feed/unassigned`, `POST /feed/unassigned/{uid}/assign`, `POST /feed/unassigned/{uid}/dismiss`, `POST /feed/seen`. Put the call BEFORE the `/courses/([a-z0-9]+)` handlers so `/courses/{id}/feed` and `/courses/{id}/feed/sync` reach this module (`feed_api.handle` returns None for every other path). Methods `PUT` and `DELETE` must be allowed in CORS (they already are in SECURITY W8). The `/{proxy+}` JWT route covers the paths; no new routes.

`backend/sync_blackboard.py` (scheduled): `handler(event, context)` is already the entry point. It calls `process_batch(limit)` and returns a small summary (counts only).

Environment for the API Lambda and the sync Lambda: `TABLE_NAME` (existing), `KMS_KEY_ID` (the feed key id), `REQUIRE_KMS=1` (deployed environments; refuses the dev fallback), optional `FEEDSYNC_MODEL=1`, `MODEL_FAST` (only used with the tie-breaker). `REGION` as usual.

Infra (`infra/stack.py`):
1. KMS key `FeedKey` (rotation on, RETAIN) as in SECURITY W7. API Lambda: `kms:Encrypt` and `kms:Decrypt` (it must decrypt for a manual sync; `feed_key.grant_encrypt_decrypt(api_fn)`). Sync Lambda: `kms:Decrypt` only.
2. Schedule: EventBridge rule `rate(15 minutes)` targeting the `sync_blackboard` function (a new Lambda, handler `sync_blackboard.handler`, timeout 120 s, memory 512 MB, reserved concurrency 1 so two runs never overlap). Each run takes a capped batch (default 25 users), so 15-minute runs cover 2,400 users per day at the default hourly per-user interval. Raise the limit and timeout together.
3. Sync Lambda IAM: table read/write (scope with `dynamodb:LeadingKeys` on `USER#*` and `FEEDUSER#*` if desired), `kms:Decrypt`, outbound internet (no VPC). No S3. Bedrock only if `FEEDSYNC_MODEL=1` (`bedrock:InvokeModel` on `MODEL_FAST`).
4. No new table index is needed (see the poller design below).

## Poller design note

Goal: find the users who have a feed and are due, without a table scan.

Option A, a GSI: put `gsi1pk = "FEED"`, `gsi1sk = nextSyncAt` on each user's `FEED` item (a sparse index: only feed users appear) and query it by time. Works, but needs the existing `gsi1` to be free for this (`gsi1` is used elsewhere) or a third index, every user lands in ONE partition key (a hot partition at scale, fine for thousands, not millions), and DynamoDB backfills nothing for items written before.

Option B, a dedicated index item (**recommended**): `PUT /me/feed` writes `pk = FEEDUSER#{shard}`, `sk = U#{sub}` with `nextSyncAt` (epoch seconds), `failures`; `shard` is `0..15`, a stable hash of the sub. `DELETE /me/feed` removes it. The poller queries the 16 shard partitions (one `Query` each, a few KB per user) and works through the items whose `nextSyncAt` is due, oldest first, up to the batch cap, then writes the next time (hourly on success, exponential backoff up to 24 h on repeated failures, so a dead link is not hammered). No scan, no GSI, no infra change, the load is spread over 16 partitions, and the item holds no secret (only the sub and times). The cost is one extra small item per feed user, kept in step by the same code that writes the feed config; a self-heal path exists: `GET /me/feed` re-creates a missing index item.

Failure and safety rules in the poller: each user is processed in its own try/except (one bad feed never stops the batch), a per-run time budget stops starting new users near the Lambda timeout, size and time caps come from `safe_fetch`, and logs contain only counts and sub-less error codes, never URLs or event text.

## Notes added after coding
- Assignments created by the feed also carry `feedUid` and `feedBase` (what the feed last wrote; used to detect student edits). The UI can ignore `feedBase`.
- `lib/secretbox.py` calls KMS Encrypt/Decrypt directly (feed URLs are under 2,000 bytes, so no data key or AES library is needed) with an encryption context binding purpose and student. Ciphertext prefix `kms1:`; the labelled dev fallback is `dev1:` and is refused when `REQUIRE_KMS=1`.
- Tests: `backend/tests/test_feed.py` (51 tests, offline).

## UA Blackboard identifiers, current term, time zones (the internal planning notes findings)

- **Identifier matcher.** Events whose text (title, categories, description, location or UID) contains `<term 6 digits>-<DEPT>-<NUM>-<section>`, bare or as `<numeric id>.<term>: <identifier>`, match the class whose code is `DEPT NUM` (for example `MIS 430`) with confidence 0.98. Section is informational. Synthetic-format tests only; the real feed is still unseen, so every other layer stays as a fallback.
- **Current term only.** The current term is the newest term code among identifiers of in-window events (plus `termCode` on a class, if one is ever stored). Events carrying only older-term identifiers are ignored entirely: never cached, never an assignment, never a class. Events without any identifier are processed as before.
- **Classes the student has not added.** A current-term event for a class the student has not created is parked: it is not shown in `GET /feed/unassigned` and not counted in `counts.unassigned`, and it is placed automatically at the next sync once that class exists. The feed sync never creates classes.
- **Time zones.** UTC (`Z`) and `TZID` (including Windows names such as "Central Standard Time") are honoured; a floating time with a label such as `(CDT)` or `(CST)` in the text is read with that label; if `DTSTART` is missing or unreadable the text `Due date: M/D/YY, h:mm AM (CST)` is parsed. Results are converted to the campus time zone.

## `GET /me/feed/classes` (onboarding: show class names before syllabi exist)

Not connected: `200 { "connected": false, "term": null, "classes": [] }`. Connected:
```
{ "connected": true, "term": "202640",
  "classes": [ { "code": "MIS 430", "section": "001", "term": "202640", "identifier": "202640-MIS-430-001",
                 "eventCount": 7, "matchedCourseId": "abcd1234" | null } ] }
```
- Distinct classes named in the feed for the current term only, sorted by code then section, at most 30. `eventCount` counts in-window events naming that identifier. `matchedCourseId` is the student's class with that code, or `null` (create it from the syllabus; the matching feed items then flow in at the next sync).
- Computed when the link is saved (`PUT /me/feed`) and refreshed at every sync, so it needs no fetch and responds instantly; call `POST /me/feed/sync` to refresh it on demand. `term` is `null` when the feed carries no identifiers (then `classes` is empty and the page should say so and offer syllabus upload). Class codes and sections are plain text. Bucket `default`.
- Wiring: `feed_api.handle` already owns the path; no extra Builder change.

## Auto-import of classes (code kept but OFF by default)

**Disabled by default (`autoImportClasses: false`)**: Luca's real feed carries no course identifiers, so nothing can be imported from it; `importedClasses` is therefore always `[]`. Enable it only by setting `autoImportClasses: true` in `backend/data/feed_rules.json` once a feed with identifiers exists.

When the feed names a current-term class (identifier `<term>-<DEPT>-<NUM>-<section>`) that matches none of the student's classes, the server creates a class agent for it, then places that class's feed events as assignments. This happens in `PUT /me/feed`, `POST /me/feed/sync`, `POST /courses/{id}/feed/sync` and the scheduled poller.
- The new class is `status: "READY"` with a finished pipeline (first step detail "Imported from Blackboard"), `courseCode: "MIS 430"`, `title: "MIS 430"` (until a syllabus adds a real title), `section`, `term` and `termCode` (`"202640"`), `source: "feed"`, `feedIdentifier`, empty meetings, books, grading and policies, `knows` counts at 0, and the next free class colour.
- Limits: current term only; at most 12 created per run and 20 per student in total; one class per code (a second section of the same code is not a second class).
- A class the student deletes is never recreated: a `FEEDSKIP#<identifier>` tombstone is written (detected automatically at the next sync, or immediately if `courses_api.delete_course` calls `feedsync.tombstone_course(sub, db, course)` before deleting; recommended one-line hook for Builder).
- Responses: `PUT /me/feed`, `POST /me/feed/sync` and `POST /courses/{id}/feed/sync` now include `importedClasses: [{ "code": "MIS 430", "section": "001", "term": "202640", "identifier": "202640-MIS-430-001", "courseId": "abcd1234" }]` (empty when nothing new). The onboarding page can show the classes appearing from this, then call `POST /me/feed/sync` to pull their deadlines. Activity: `feed_imported`, agentId `master`, "Imported 4 classes from Blackboard".
- Dates written by the feed carry `dateSource: "feed"`.
- The tutor for such a class tells the student it has the deadlines but no syllabus yet and suggests uploading the syllabus for grading and policies (`tutor.has_syllabus_facts`).
- Open point for Builder: uploading a syllabus must FILL the imported class (same course id) rather than create a second class with the same code; two classes with one code make the identifier match ambiguous and push events to Unassigned.
- Kill switch: `autoImportClasses` in the rules (`backend/data/feed_rules.json`).

## Diagnostics
Unexpected errors log `feed_api unexpected error: <ExceptionType> at file:line function <- ...` (frames only; never messages, locals or text). Secondary writes (profile mirror, poller index) are best effort and cannot fail a save; one unreadable VEVENT is skipped, never failing the feed.


## The real feed shape: date window, recurring events, class sessions, grouped Unassigned

Luca's real export has no course identifiers: deadline items (UID contains `GradableItem`) and class-session entries (UID contains `CalendarEntry`), `DTSTART;TZID=America/Chicago`, hundreds of events across many terms, some `RRULE`/`RDATE`. Behaviour:
- **Date window.** Only events from 7 days ago to 240 days (8 months) ahead are used (`window.pastDays`/`futureDays` in the rules). Old terms and the far future are ignored: never cached, never an assignment, never a class.
- **Recurring events.** `RRULE` (DAILY, WEEKLY with BYDAY, MONTHLY, YEARLY, with INTERVAL, COUNT, UNTIL), `RDATE` and `EXDATE` are expanded inside the window only, at most 60 occurrences per series (`maxOccurrences`). DTSTART is always an occurrence.
- **Class sessions are not deadlines.** Events whose UID matches `meetingUidPatterns` (default `["CalendarEntry"]`) never become assignments and never appear in Unassigned. If their title names one of the student's classes (for example `EN 210 Lecture`), they produce meeting-time hints: `GET /courses/{id}/feed` now also returns `"meetings": [ { "weekday": "Mon", "start": "09:30", "end": "10:45" | null, "count": 12 } ]` (at most 6, most frequent first, only patterns seen at least twice; `[]` when none) that the UI can offer to pre-fill the class meeting times. Hints never change anything by themselves.
- **Matching** uses what the feed has: a course code in the title (`EN 210`), learned rules, class-title words, instructor surname. Most deadlines will land in Unassigned, so:

### Grouped Unassigned (additive)
`GET /feed/unassigned` now returns `{ "unassigned": [...first 200 items as before...], "groups": [ ... ] }`. A group is two or more inbox items with the same normalised title pattern (dates, numbers and "Week 3" style labels removed, so `10/19 Reading Journal` and `11/2 Reading Journal` share the pattern `reading journal`), at most 50 groups, biggest first:
```
{ "groupId": "a1b2c3d4e5f6", "pattern": "reading journal", "label": "Reading Journal", "count": 12,
  "uids": ["<24hex>", ...],                 // at most 100
  "sampleTitles": ["10/19 Reading Journal", ...],   // at most 3, plain text
  "firstDue": "2026-10-19" | null, "lastDue": "2026-12-07" | null,
  "suggestions": [ { "courseId": "abcd1234", "courseCode": "EN 210", "confidence": 0.5 } ] }
```
- `POST /feed/unassigned/groups/{groupId}/assign` body `{ "courseId", "remember": true }`: assigns every item in the group to that class in one call and, with `remember`, learns the pattern so later items of the same shape land in the class automatically (a single generic word such as "quiz" is never learned). `200 { "assigned": 12, "learned": true, "remaining": 0 }` (`remaining` > 0 when a group had more than 100 items: call again). `404 not_found` for an unknown or already resolved group or class (also for another student's), `400 validation_error` for a bad body.
- `POST /feed/unassigned/groups/{groupId}/dismiss` body `{ "remember": false }`: `200 { "dismissed": 12, "learned": false }`. With `remember` it also learns to ignore items of that pattern.
- Show groups first ("Reading Journal x12, assign all to...") and keep the single-item list below for the rest. Group ids change when the group's pattern changes; always take them from the latest `GET`.

### Onboarding classes without identifiers
`GET /me/feed/classes` falls back to course codes written in titles when the feed has no identifiers: `{ "code": "EN 210", "section": "", "term": null, "identifier": null, "eventCount": 12, "matchedCourseId": null }`, only codes seen at least twice in the window. `term` and `identifier` are `null` in that case.

### Performance
A synthetic 389-event feed parses in well under 3 seconds. A sync handles at most 150 new events and about 20 seconds per run; the rest continues at the next poll (about hourly), so the first sync of a big feed may leave some items for the next check.

## Add classes by code: `POST /courses/quick` (the calendar link alone cannot list classes)

Body: `{ "courses": [ { "code": "MIS 405", "title": "Management Information Systems", "section": "001" } ] }` (1 to 12 items; `title` and `section` optional; no other fields; at most 8,000 bytes).
- Codes are normalised: department 2 to 5 letters plus number 3 to 4 digits with an optional letter, any spacing or dash (`mis405`, ` en-210 `) becomes `MIS 405`, `EN 210`. Anything else is reported in `invalid`.
- Codes the student already has (matched on the normalised code) are returned in `skipped`, as are codes beyond the 20-classes-per-student cap (counts classes made by the feed or by this route).
- Each new class is a READY class agent exactly like an imported one: pipeline all done (first step detail "Added by code"), `courseCode`, `title` (given, or the code), colour assigned, `knows` at 0, `source: "quick"`. Title and section text are cleaned.
- If a feed is connected, stored Unassigned and parked events are re-placed against the new classes straight away (matching by code, learned rules and class words); other items are placed at the next sync.

`201` (or `200` when nothing was created):
`{ "created": [ { "id": "abcd1234", "courseCode": "MIS 405", "title": "Management Information Systems", "color": "#4F46E5" } ], "skipped": ["EN 210"], "invalid": [], "placed": 3 }`
(`placed` = how many feed items were assigned to classes because of this call.) Errors: `400 validation_error`, `429` (bucket `default`).

## Suggested codes and `needsSyllabus`

- `GET /me/feed/classes` now also returns `suggested: [ { "code": "EN 210", "eventCount": 12 } ]`: course codes written in event titles (seen at least twice in the date window), most frequent first, minus codes the student already has. The onboarding page can show them as chips; tapping one calls `POST /courses/quick`. `[]` when not connected. Computed at save and at every sync.
- `GET /courses/{id}/feed` now includes `needsSyllabus: true|false` (also when no feed is connected): true for a class made by the feed or by code that has no syllabus facts yet, so the class page can show "Upload your syllabus for grading and policies". Builder: `feedsync.needs_syllabus(course)` is a one-line helper if `GET /courses/{id}` should return the same flag.

## Extension import: `POST /courses/import` (the browser extension is the main connector; the calendar link is "advanced")

The extension reads classes and their deadlines from the student's own Blackboard pages (course list: identifier and instructor; Calendar "Due dates" view: `<title>`, `Due date: 10/19/26, 5:00 PM (CDT) ∙ 40541.202640: 202640-EN-210-010`) and posts them here. JWT required. Body (at most 600,000 bytes, no other fields):
```
{ "source": "blackboard",
  "classes": [ { "identifier": "202640-EN-210-010", "code": "EN 210", "section": "010", "term": "202640",
                 "title": "American Literature", "instructor": "Dr. Jane Rivera",
                 "assignments": [ { "title": "Reading Journal 1", "dueDate": "2026-10-19", "dueTime": "17:00" | null, "tz": "CDT" } ] } ] }
```
- Limits: 12 classes per call, 200 assignments per class; titles are cleaned to plain text and capped (160 stored); `identifier`, `title`, `instructor`, `section`, `term`, `tz` and `dueTime` are optional except that each class needs a usable `identifier` or `code`. Unknown fields are rejected with `400 validation_error`; unusable classes count in `skipped`, unusable assignments (bad title, date or time, more than 800 days from today) are dropped silently.
- **Idempotent.** A class is matched by `bbIdentifier` (stored on the course), else by its normalised code (an existing class from a syllabus or quick-add with the same code is adopted, not duplicated). Re-importing updates the class (fills empty title, instructor, section, term; never overwrites what exists) and upserts assignments by (title, dueDate), also via a stored `bbKey`, so renamed or re-dated items are not duplicated. A stored Blackboard item whose title appears once in the new data with a new date is treated as moved by the instructor and updated, unless the student set its date (`dateSource: "manual"`), which always wins; `done`, notes and the student's edits are never touched.
- **New class** = READY class agent (source `blackboard`, `bbIdentifier`, `term`/`termCode`, colour assigned, pipeline done with "Imported from Blackboard", `title` falls back to the code, `needsSyllabus: true` until syllabus facts exist, `knows` counts).
- **Assignments**: `source: "blackboard"`, `dateSource: "stated"`, type inferred from the title (exam, quiz, project, paper, reading, homework, else other). Due date and time are converted from the page's wall clock and its label (`CDT`, `CST`, `EDT`, `PST` ...; empty or unknown label = campus time zone) to the campus time zone. No time = date only.
- **Tombstones.** Deleting a Blackboard-created class writes `FEEDSKIP#<identifier>` (done by `courses_api.delete_course`), which stops the feed's auto-import from recreating it; an explicit import re-creates it and clears the tombstone.
- If a calendar link is connected, stored Unassigned events are re-placed against new classes straight away.

`201` when at least one class was created, else `200`:
`{ "created": [ { "id": "abcd1234", "courseCode": "EN 210", "title": "American Literature", "color": "#4F46E5", "assignmentsAdded": 3 } ], "updated": [ { "id": "efgh5678", "courseCode": "MIS 430", "assignmentsAdded": 2, "assignmentsUpdated": 1 } ], "skipped": 0 }`
Errors: `400 validation_error`, `413`, `429` (bucket `course_import`: 6 per minute, 60 per day).

`GET /courses` and `GET /courses/{id}` now return `source` (`syllabus`, `feed`, `quick`, `blackboard`) and `needsSyllabus` on the course. No api.py change: `feed_api.handle` already runs before the generic `/courses` handlers.
