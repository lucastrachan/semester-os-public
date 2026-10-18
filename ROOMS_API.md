# Class group chats (rooms): contract: owner: Rooms agent

Status: **coded and tested offline, not deployed, not wired.** Builder wires the routes (bottom). Designer: build against these shapes. Errors are `{ "error": code, "message": text }`. JWT (student pool) on every route. No public routes. Rooms appear in the same Messages area as marketplace DMs (`GET /conversations`) but are a separate list: `GET /rooms`.

## Honesty rule (the UI must say it)

**Enrollment is NOT verified.** A student is auto-added to a room when they add a class with that course code to their own account. Anyone can add any class. Every room therefore carries `verified: false`; show it as "Classmates who added this class", never "your classmates" or "enrolled students". Rooms are same campus only.

## Who is in which room

A room is `(tenantId, term, normalised course code)`. `roomId = "{tenantId}.{term}.{CODE}"`, e.g. `ua.FA26.MIS405` (URL safe, readable, contains no personal data). Membership is computed at read time from the caller's own classes (`USER#{sub}/COURSE#` items): no fan-out writes, no membership items.
- Code: `courseCode` upper-cased with everything except letters and digits removed (`"MIS 405"` -> `MIS405`). A class with no code yet (still building) is in no room.
- Term: the class's `termCode` or `term`. `"Fall 2026"`, `"fall 26"` -> `FA26` (FA, SP, SU, WI + 2-digit year). A numeric feed code like `202640` is kept as is. When the class has no term (syllabus-created), the term is derived from `createdAt`: Jan-May `SP`, Jun-Jul `SU`, Aug-Dec `FA`, plus the 2-digit year. Limitation: a feed class (`202640`) and a syllabus class (`FA26`) for the same course land in different rooms; they merge only if both use the same label.
- Campus: the caller's tenant. Disabled campus -> `403 campus_disabled`. Banned user -> `403 account_restricted`.
- Non-member roomId (or unknown, or other campus) -> `404 not_found` (same answer, existence never confirmed). Deleting the class removes the room from the list immediately (and read/write access).
- `left: true` (per-user) hides the room from the default list and blocks reading and posting until `rejoin`.

## Objects

```
Room = {
  id: "ua.FA26.MIS405", code: "MIS405", displayCode: "MIS 405" | "MIS405", title: "Intro to Systems" | "",
  term: "FA26", campus: { id, shortName },
  verified: false,                              // ALWAYS false
  memberCount: 14,                              // approximate: students who opened Messages with this class (>=1)
  muted: false, left: false, closed: false, canSend: true,
  lastMessage: { from: "me"|"them", name, text <=90, at } | null,
  unread: 0,                                    // 0 when muted or left
  lastMessageAt: iso | null
}
Message = { id: "<opaque cursor>", from: "me" | "them", name: "Classmate 4821", text, at }
```
`name` is the sender's nickname at send time. Never an email, real name or id. Message text is plain text: render as text only (never HTML, never auto-link).

## Nickname

`GET /me/nickname` -> `200 { nickname, isDefault }`. Default `Classmate NNNN` (4 digits from a hash of your id; stable).
`PATCH /me/nickname` body `{ nickname }` (2-24 chars; letters, digits, space, `. _ - '`; no links, emails, `@`, long digit runs or profanity) -> `200 { nickname, isDefault: false }`; `{ nickname: "" }` or `null` resets to the default. `400 validation_error`. Uniqueness is not required. Old messages keep the name they were sent with.

## GET /rooms

Query: `includeLeft=true` (default false). `200 { rooms: Room[] (latest activity first, then code), unreadTotal }`. Opening it counts you once in each room's `memberCount`. Cheap enough to poll every 30 s.

## GET /rooms/{roomId}/info

`200 { room: Room, info: { code, title, campusShortName, memberCount, verified: false, notice: "Classmates who added this class. Enrollment is not verified.", safetyTips: [..] , rules: {maxChars: 500, perMinute: 12, perDay: 300} } }`.

## GET /rooms/{roomId}/messages?after=<cursor>&limit=50

Oldest first. No `after`: the last `limit` (default 50, max 100). With `after` (the previous `nextCursor`): only newer (the polling call). `200 { room, messages, nextCursor }`. Marks the room read. Messages from people you blocked are omitted. `400 validation_error` for a bad cursor, `404 not_found`, `403 room_left` if you left.

## POST /rooms/{roomId}/messages

Body `{ text }`. `201 { message, canSend: true }`.
Rules: plain text 1-500 chars; rejected: links or domains, `@` anywhere, `<`, `>`, markdown images, emails, phone/ID-like digit runs (7+ digits; dates like 2026-10-20 are fine), obvious profanity, the same text as your own previous message in that room.
Errors: `400 validation_error`, `403 room_closed` (admin closed), `403 room_left`, `404 not_found`, `403 account_restricted`, `403 campus_disabled`, `429 rate_limited` (12/minute, 300/day), `429 spam` (same 15+ char text over 3 times a day). Each room keeps the newest 300 messages (older ones are trimmed); messages also expire after 60 days.

## Per-user actions (no body, all idempotent, `200`)

`POST /rooms/{roomId}/mute` -> `{ muted: true }`, `/unmute` -> `{ muted: false }`, `/leave` -> `{ left: true }`, `/rejoin` -> `{ left: false }`.
Rooms you cannot reach (class deleted) cannot be muted or left (404).

## POST /rooms/{roomId}/block

Body `{ messageId }`. Hides that message's sender from you in this and every room (silent; the sender is not told). `200 { blocked: true }`. `400` if the message is yours or not found, `404` not a member.

## POST /rooms/{roomId}/report

Body `{ reason: "spam|harassment|scam|inappropriate|other", note?: <=200, messageId?: <id> }`. Saves a report for the admin queue with the last 10 messages as evidence (and the reported sender when `messageId` is given). One per person per room (repeats accepted, counted once). `200 { reported: true }`. `429` after 10 a day.

## Item layout (DynamoDB single table)

| Item | pk | sk | Notes |
|---|---|---|---|
| Message | `ROOMMSG#{roomId}` | `M#{iso}#{rand4}` | `senderHash` (internal), `name`, `text`, `at`, `ttl` 60 days. Cursor = sk without `M#` |
| Room summary | `ROOM#{roomId}` | `META` | `lastAt, lastPreview, lastName, lastHash, ttl` |
| Member counter | `ROOM#{roomId}` | `MEMBERS` | `n` approximate; +1 first time a user sees the room, -1 on leave |
| My settings | `USER#{sub}` | `RM#{roomId}` | `muted, left, counted, lastRead` |
| Nickname | `USER#{sub}` | `NICK` | `nickname` |
| Block | `USER#{sub}` | `RMBLOCK#{sha256(sender)[:16]}` | `at` |
| Closed room | `ROOMCLOSED#{roomId}` | `META` | `reason, by, at`; presence closes the room (read ok, no posts) |
| Report | `REPORTS` | `R#room#{h8}#{reporterHash}` | `id = room.{h8}.{reporterHash}`, `kind "room"`, `targetId` = first 8 hex of sha256(roomId), `roomId`, `reason, note, reportedSub?, reportedName?, evidence[], status "open", createdAt, ttl 180 days`. Same shape as conversation reports, so it passes the admin resolve route |

Counters reuse `limits` (bucket `room`) and `convos.check_spam`. `lib/rooms.delete_user_data(sub)` removes the user's settings, nickname and blocks (call from account deletion; their past messages stay, anonymous, and expire in 60 days).

## Admin follow-ups (after the freeze, additive)

1. `admin_api._report_view`: add a branch for `kind == "room"` (show `roomId`, `evidence`, `reportedSub`); today it falls into the listing branch and shows `listing: {exists: false}`.
2. A route to close/reopen a room: write or delete `ROOMCLOSED#{roomId}/META` (`rooms.close_room(room_id, by, reason)` / `rooms.reopen_room(room_id)` exist).

## Wiring for Builder (api.py, protected section; put BEFORE any generic `/courses` or `/me` patterns)

```python
import rooms_api
...
if path.startswith("/rooms") or path == "/me/nickname":
    r = rooms_api.handle(event, sub, path, method)
    if r is not None:
        return r
```
`rooms_api.handle` returns `None` for paths it does not own. No new IAM (same table). Tests: `python -I -m unittest discover -s backend/tests` (`test_rooms.py`).
