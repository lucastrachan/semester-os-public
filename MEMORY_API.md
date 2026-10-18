# Class memory API (the internal planning notes item B)

Owner: Class-agent platform module agent. Code: `backend/lib/memory.py`, `backend/memory_api.py` (routes), the `remember` tool in `backend/lib/tools_impl.py` + `backend/lib/guard.py`, prompt injection in `backend/lib/tutor.py`. Status: **coded and tested offline, not routed, not deployed.**

Shapes match Designer's assumptions (the internal planning notes, "the internal planning notes milestone 2"): `GET -> {notes: [{id, text, createdAt}]}`, `PATCH {text}`, `DELETE` one and all. No deviations; extras are additive (`source`, `limit`, `count`).

All routes need the student ID token; student from the token, class from the path. Errors: `{ "error": "<code>", "message": "<text safe to show>" }`. Render all text as text.

## What memory is
Short factual notes the class agent keeps about THIS student for THIS class, for example "Struggles with normalization; prefers worked examples" or "Exam 2 is open-notes (per student)". They are visible, editable and deletable by the student. Limits: **at most 40 notes per class, 280 characters each**, one line, plain text.

A note can never contain: links or web addresses, email addresses, phone numbers or long digit runs (ID numbers), anything that looks like a secret (passwords, keys, tokens, long random strings), markup, or instruction-shaped text ("ignore previous rules", "always call ...", "from now on ..."). Notes are cleaned (control and zero-width characters removed, whitespace collapsed); a note that fails these checks is **rejected** (not silently edited), with `400 validation_error` and a message the UI can show.

Memory is DATA, never instructions. On every tutor turn the notes are placed in the system prompt inside an untrusted wrapper (per-request nonce). The tutor's only way to add a note is the validated `remember` tool (below).

## `GET /courses/{id}/memory`
`200 { "notes": [ { "id": "n1a2b3c4", "text": "...", "createdAt": "2026-10-17T21:00:00.123456Z", "source": "agent" | "student" } ], "limit": 40, "count": 3 }`, oldest first.

## `POST /courses/{id}/memory` (extra, optional for the UI: "add a note yourself")
Body `{ "text": "..." }` -> `201 { "note": {...} }`. Same validation. `409 memory_full` at 40 notes.

## `PATCH /courses/{id}/memory/{noteId}`
Body `{ "text": "..." }` -> `200 { "note": {...} }`. Same validation. `404 not_found` if the note is not this student's note in this class.

## `DELETE /courses/{id}/memory/{noteId}`  and  `DELETE /courses/{id}/memory`
-> `200 { "deleted": "n1a2b3c4" }` / `200 { "deleted": 3 }` (count removed). Deleting a note that does not exist (or belongs to another class) is `404`.

Errors: `400 validation_error`, `404 not_found` (bad class id, not yours, bad note id), `409 memory_full`, `413 too_large`, `429 rate_limited`. Deleting a class deletes its memory.

## The `remember` tool (tutor, modes explain and cram)
- Arguments: `{ "text": "one short factual note" }` only. Validated by `guard.validate_tool_call` (allow-list `class`, strict args, same note rules as above, class pinned to this one). It counts against the per-request `ToolBudget` writes (6 per request) and the normal call limit. The tutor is told to use it only when the student states something durable about themselves for this class (level, preference, confusion, a constraint), never for things found in documents, never for instructions, and at most once per turn (the server enforces one per message).
- Duplicate notes (same text ignoring case) are not added twice; at 40 notes the tool answers "memory is full" and the tutor tells the student to clear some in the Memory tab.
- Returns an action chip in the normal `actions` list: `{ "id": "...", "kind": "memory_added", "summary": "Remembered: <text up to 80 chars>", "courseId": "...", "undoable": true }`. Undo goes through the existing `POST /courses/{id}/chat/undo` and deletes that note (only if it is still unchanged). Also written to the activity feed.
- The student can also tell the agent "forget that"; the agent cannot delete (no delete tool). It points the student to the Memory tab.

## Rolling summary of old chat
Optional and **off by default**; not enabled in this version (no route or setting yet). If it is turned on later, the summary will be stored as a note with `source: "summary"`, subject to the same cleaning, and listed here like any other note.

## Wiring for Builder
`api.py` protected section, before the generic `/courses/{id}` handlers:
```python
import memory_api   # top of file
r = memory_api.handle(event, sub, path, method)
if r is not None:
    return r
```
`memory_api.handle` returns `None` for paths that are not its own. No stack change: same table, no new env vars.
