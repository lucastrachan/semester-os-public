# Master agent API (Phase 5): briefing, master chat with routing, agent library, activity

Owner: Security agent wrote the backend modules (`backend/master_api.py`, `backend/lib/briefing.py`, `backend/lib/routing.py`). Builder wires the routes (snippets at the end). Status: **coded and offline-tested (211 backend tests), smoke-tested once against the real models, not deployed, not routed.** Shapes below are the contract; changes after Mobile starts are additive only and announced in the internal planning notes.

All routes need the student ID token (`Authorization: Bearer <ID token>`). The student, their campus and time zone always come from the token and profile, never from the request. Errors use `{ "error": "<code>", "message": "<text safe to show>" }`.

Everything the model writes is plain text with light markdown (HTML and images are removed server-side). Everything that can be computed (dates, times, conflicts, which classes meet today, study-block suggestions, ids) is computed in code, never by the model, and model-supplied ids are never trusted.

## `GET /briefing/today`

Returns today's briefing for the student's campus time zone, generating it first if there is none yet. Never fails because of limits: if the AI is paused, rate limited or unavailable it returns a plain, fully computed briefing (`source: "computed"`) instead.

`200`
```
{
  "date": "2026-10-17",                       // the student's local date
  "generatedAt": "2026-10-17T13:02:11Z",
  "source": "model" | "computed",             // "computed" = no AI text, generic greeting and hints
  "briefing": {
    "greeting": "Good morning, Luca. Two classes today and Exam 2 is Tuesday.",
    "classesToday": [ { "courseId": "abcd1234", "time": "09:00-09:50", "location": "Gordon Palmer 101", "prep": ["Finish chapter 3 reading"] } ],
    "dueSoon":      [ { "assignmentId": "x1y2z3w4", "title": "Quiz 3", "courseId": "abcd1234", "dueDate": "2026-10-19", "hint": "Review slides 10-20" } ],
    "priorities":   [ "Start the lab write-up tonight", "..." ],
    "warnings":     [ "3 deadlines on Fri Oct 23: Quiz 3, Lab 4, Essay 1", "No study time scheduled for Exam 2 (due 2026-10-27)" ],
    "suggestedStudyBlocks": [ { "courseId": "abcd1234", "start": "2026-10-17T18:00", "end": "2026-10-17T18:50", "focus": "Prepare for Exam 2" } ]
  }
}
```
- This is exactly the handoff 7.4 shape. Look up course code, title and colour from `GET /courses` by `courseId`.
- `classesToday` is sorted by start time and comes from course `meetings`. `prep` is model text (up to 3 short items per class), `[]` in the computed fallback.
- `dueSoon`: not-done items due from 3 days ago (overdue) through the next 7 days, soonest first, at most 10. `hint` is model text, `""` in the computed fallback.
- `priorities`: up to 5 ordered strings. In the computed fallback they are derived from `dueSoon` in code.
- `warnings` are produced in code: several deadlines on one day (3 or more), overlapping class meetings or study blocks, deadlines for exams, projects, papers and quizzes within 7 days with no study block before them, overdue items, undated items. Each is a short text string. Titles inside them come from the student's own syllabus and are shown as text.
- `suggestedStudyBlocks`: free slots inside the student's waking hours (`prefs.wakeHour` to `prefs.sleepHour`) that do not overlap classes or existing study blocks, length `prefs.studyBlockMinutes`, at most 3, for the most urgent class. Times are local wall-clock `YYYY-MM-DDTHH:MM` (no time zone). Nothing is scheduled by the briefing; the student creates blocks through the class tutor's cram mode.

## `POST /briefing/regenerate`

No body needed (`{}`). Always generates a fresh briefing and stores it, replacing today's.
- `200` same body as `GET /briefing/today` (`source` is `"model"`)
- `429 rate_limited` (bucket `briefing`: 2 per minute, 20 per day; `Retry-After` header), `503 ai_disabled`, `503 master_busy` (all models busy or timed out; the previous briefing is kept)

## `POST /chat/master`

The Chief of Staff chat. Each message first goes through a fast router, which decides whether the master answers or a class tutor does.

Request:
```
{
  "messages": [ { "role": "user" | "assistant", "content": "text" } ],   // required, last item must be role "user", same limits as the tutor chat
  "target":   "master" | "<courseId>",    // optional: skip the router and send to this agent (used by "Undo" and by the clarifying question buttons)
  "mode":     "explain" | "quiz" | "flashcards" | "cram"   // optional, only used when a class tutor answers; default "explain"
}
```
Response `200` has one of three forms. Always present: `agent`, `courseId`, `reply`, `actions`, `handoff`, `clarify`. A handoff response also carries the tutor's extra fields (`mode`, `quiz`, `flashcards`). Exactly one of the three cases is true.

1. **Master answers** (router said master, confidence too low, or `target: "master"`):
```
{ "agent": "master", "courseId": null, "reply": "text", "actions": [], "handoff": null, "clarify": null }
```
2. **Handoff** (router confidence 0.75 or more for one of the student's classes, or `target: "<courseId>"`): the class tutor answered in the same request, with all of its tutor-API fields:
```
{
  "agent": "class", "courseId": "abcd1234",
  "reply": "tutor text", "actions": [ { "id", "kind", "summary", "courseId", "undoable" } ],
  "quiz": null, "flashcards": null,          // present when mode is quiz or flashcards, same shapes as TUTOR_API.md
  "handoff": { "courseId": "abcd1234", "courseCode": "MIS 405", "title": "Systems Analysis", "reason": "You asked about the Exam 2 study guide", "confidence": 0.86 },
  "clarify": null
}
```
   The UI shows "Switching you to your MIS 405 tutor: <reason>" with an **Undo** button and re-themes to the class colour. Undo is client-side: show the master chat again and re-send the same message with `target: "master"` (the handoff is recorded in the activity feed either way). `handoff.reason` is short text; when the model gives none, the server writes "This looks like a question about MIS 405".
3. **Clarifying question** (router confidence from 0.5 up to 0.75 for a class):
```
{
  "agent": "master", "courseId": null,
  "reply": "Is this about MIS 405 or about planning your week?",   // written by the server from course codes, not by the model
  "actions": [], "handoff": null,
  "clarify": { "question": "Is this about MIS 405 or about planning your week?",
               "options": [ { "target": "abcd1234", "label": "MIS 405" }, { "target": "master", "label": "Planning" } ] }
}
```
   Render the options as buttons; a tap re-sends the same `messages` with `target` set to the option's `target`. No extra rate-limit cost beyond one chat request.

Rules the server enforces: the router can only pick one of the student's own READY classes or `master` (an id the model invents, or one written inside a syllabus or chat text, is ignored and the master answers); the master has **no write tools** (it cannot add, change or delete anything; changes happen only inside a class tutor, with the tutor's own validation and undo); all prior turns are treated as untrusted data; replies are sanitised.

Errors: `400 validation_error` (bad `messages`, `target`, `mode`), `404 not_found` (`target` is not your class), `409 not_ready` (target class still building), `413 too_large`, `429 rate_limited` (bucket `chat`, shared with the tutor: 6 per minute, 200 per day), `503 ai_disabled`, `503 master_busy`, `502 bad_model_output` (quiz or flashcards only). Typical latency 3 to 20 seconds (router call, then the answer).

## `GET /agents`

The Agent Library. `200 { "agents": [Agent] }` in this order: master, class agents (oldest first), then the system agents.
```
Agent = {
  "id": "master" | "<courseId>" | "calendar_sync" | "planner" | "books",
  "kind": "master" | "class" | "system",
  "name": "Chief of Staff" | "MIS 405" | "Calendar Sync" | "Planner" | "Books",   // class: courseCode, or "New class" while building
  "role": "Morning briefing, planning and routing",                              // short fixed text
  "status": "ready" | "building" | "error" | "active" | "idle" | "not_connected" | "coming_soon",
  "detail": "Briefing ready for today",          // one line, text
  "color": "#4F46E5" | null,                      // class agents only
  "courseId": "abcd1234" | null,
  "pipeline": [ { "key", "label", "state", "detail" } ] | null,    // class agents only while status is "building" or "error"
  "stats": { "assignments": 12, "materials": 0, "newItems": 0 } | null,   // class agents only
  "lastActivity": { "kind": "built", "text": "MIS 405 agent is ready: 12 items", "at": "2026-10-17T12:30:00Z" } | null
}
```
- Master: `ready`, detail says whether today's briefing exists.
- Calendar Sync: `not_connected` until the student saves a feed, then `active` (detail "Last checked <time>") or `error` (detail from the last sync status). The feed URL is never returned.
- Planner: `coming_soon` until the first daily plan exists, then `active`.
- Books: `idle` (detail "No required books found yet") or `active` (detail "N books found, marketplace matching comes later").

## `GET /activity`

`GET /activity?limit=30&agentId=abcd1234` (both optional; `limit` 1 to 100, default 30; `agentId` is `master`, a system agent id or a course id). `200 { "activity": [ { "id": "<stable id>", "agentId": "abcd1234", "kind": "built" | "started" | "error" | "assignment_updated" | "assignment_added" | "study_blocks_created" | "undo" | "handoff" | "briefing" | "...", "text": "plain text", "at": "2026-10-17T12:30:00Z" } ] }`, newest first. Entries expire after 30 days. `400 validation_error` for a bad `limit` or `agentId`. Text is plain text; render it as text.

## Limits and caps
`/chat/master`: bucket `chat`. `/briefing/*` generation: bucket `briefing`. `/agents`, `/activity`: 30 per minute (bucket `default`). Request bodies at most 200,000 bytes; replies at most 1,024 output tokens, briefings 1,500. The AI kill switch (`AI_ENABLED`) makes `/chat/master` and `/briefing/regenerate` return `503 ai_disabled`; `/briefing/today`, `/agents` and `/activity` keep working.

## Wiring for Builder (Security did not touch these files)

`backend/api.py`, protected section after `sub = _get_sub(event)`:
```python
import master_api   # top of file
r = master_api.handle(event, sub, path, method)    # returns a response dict, or None when the route is not one of its own
if r is not None:
    return r
```
It owns exactly: `GET /briefing/today`, `POST /briefing/regenerate`, `POST /chat/master`, `GET /agents`, `GET /activity`.

`backend/daily_run.py` (scheduled, for every user): `master_api.generate_briefing_for_user(sub)` returns `True` when a model briefing was stored and `False` when it skipped (kill switch, rate limit or model error); it never raises.

`infra/stack.py`: no new resources and no new routes (the `/{proxy+}` JWT route already covers these paths). The API Lambda needs `bedrock:InvokeModel` on both `MODEL_FAST` (`amazon.nova-lite-v1:0`) and `MODEL_MAIN` models (and their fallbacks); both are already in `model_env`. Keep the Lambda timeout at 29 s: a handoff turn is two model calls (router, then tutor) and the code stops starting new model calls after about 24 s.
