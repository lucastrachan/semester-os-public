# Chat history and opening message API (the internal planning notes item A and G)

Owner: Class-agent platform module agent. Code: `backend/lib/history.py`, `backend/lib/opening.py`, `backend/history_api.py` (routes), small hooks in `chat_api.py` and `master_api.py`. Status: **coded and tested offline, not routed, not deployed.** Additive changes only after Designer/Mobile start coding against this file.

All routes need the student ID token. The student always comes from the token and the class from the path, never from the body. Errors use `{ "error": "<code>", "message": "<text safe to show>" }`. All text in responses is plain text (render as text nodes, never HTML).

## `GET /courses/{id}/chat/history?before=&limit=`
## `GET /chat/master/history?before=&limit=`

- `limit`: 1 to 100, default 30. `before`: optional cursor, the `id` of the oldest message the client already has (or the `nextBefore` of the previous page). Omit it for the newest page.
- Success `200`:
```
{
  "messages": [
    { "id": "2026-10-17T21:04:11.120301Z", "role": "user" | "assistant", "content": "text",
      "mode": "explain" | "quiz" | "flashcards" | "cram",
      "actions": [ { "id": "k3j9x0ab12cd", "kind": "assignment_added", "summary": "Added Exam 2 on 2026-11-10",
                     "courseId": "abcd1234", "undoable": true } ],
      "sources": [ { "materialId": "m1a2b3c4", "title": "Lecture 4.pdf" } ],
      "quiz": null | { "questions": [...] },          // same shape as the chat response, assistant messages only
      "flashcards": null | { "cards": [...] },
      "handoff": null | { "courseId": "abcd1234", "courseCode": "MIS 430", "title": "...", "reason": "..." },
      "at": "2026-10-17T21:04:11.120301Z" }
  ],
  "nextBefore": "2026-10-17T20:59:02.001200Z" | null
}
```
- `messages` are in chronological order (oldest first) within the page. `nextBefore` is the id to pass as `before` to load the page of older messages, and is `null` when there is nothing older. The first page holds the newest messages.
- `id` is the timestamp (UTC, microseconds) and is also the sort key, so ids sort like times. `at` equals `id`.
- `actions[].undoable` is `false` once the server's undo recipe has expired (7 days); never show Undo then. `sources`, `quiz`, `flashcards`, `handoff` are always present (empty array or `null`).
- Errors: `400 validation_error` (bad `before` or `limit`), `404 not_found` (class id not yours), `429 rate_limited`.
- The class history is separate per class. A turn sent to `/chat/master` that was handed to a class agent is stored in BOTH the master history (with `handoff` filled) and that class's history, so the class chat tab shows it.

### How history is written (clients do nothing)
- `POST /courses/{id}/chat` and `POST /chat/master` append the newest user message and the reply to the history after every successful turn. A failed or rejected turn writes nothing. Undo does not edit history.
- Stored items: `pk USER#{sub}`, `sk CHAT#{agentId}#{ts}` (`agentId` is the class id or `master`), `ttl` = 90 days after the write (DynamoDB TTL attribute `ttl`, epoch seconds). Student text is capped at 4,000 characters and replies at 20,000, control and zero-width characters are stripped.
- **Per-agent cap: 400 stored messages** (about 200 turns). When a write goes over, the oldest are deleted.
- Deleting a class deletes its history (`classdata.purge_course`, called from `courses_api.delete_course`).
- The server never feeds stored history back into a prompt on its own: the client still sends `messages`. If a feature uses it later it must go through `history.prompt_block`, which wraps it as untrusted data with the request nonce.

### Client rules
- The web and app stop using sessionStorage for chat. On opening the chat tab: `GET .../chat/history`, render, and keep sending the visible conversation (the last 20 turns) in `messages` as before.
- To load older messages when scrolling up: call again with `before=<nextBefore>`.
- `DELETE /courses/{id}/chat/history` is NOT provided in this version (history is removed with the class or after 90 days). Tell the Planner if a "clear chat" button is wanted.

## `GET /courses/{id}/opening`

The proactive first message and quick chips for the class chat tab. Computed entirely in code from deadlines, recent activity, materials and memory; **no model is called** unless polishing is enabled (see below). Cheap: call it each time the chat tab opens (rate limit bucket `default`).

Success `200`:
```
{
  "message": "Exam 2 is in 6 days. Want a study plan?",
  "chips": [
    { "label": "Make a study plan", "prompt": "Make me a day-by-day study plan for Exam 2", "mode": "cram" },
    { "label": "Quiz me on Exam 2", "prompt": "Quiz me for Exam 2", "mode": "quiz" },
    { "label": "What's due this week?", "prompt": "What's due this week in this class?", "mode": "explain" }
  ],
  "reason": "exam_soon",
  "polished": false
}
```
- `chips` has 2 to 5 items. `mode` is one of the chat modes; send `prompt` as the student's message with that `mode` when a chip is tapped. For `quiz`/`flashcards` chips the client may send `messages: [{role:"user", content: prompt}]`.
- `reason` is one of `exam_soon`, `overdue`, `due_this_week`, `new_material`, `no_materials`, `welcome` (for analytics and tests; do not branch UI on it).
- Priority of the rules: exam, quiz or project due within 14 days, then overdue unfinished items, then items due in the next 7 days, then a material added in the last 3 days, then "no materials yet", then a plain welcome.
- Titles inside `message` and `prompt` come from the syllabus or Blackboard, which are untrusted. Chip prompts only contain a title after it was reduced to letters, digits and basic punctuation (50 characters), because a chip prompt becomes the student's own trusted message. Always render `message` as text.
- `polished`: normally `false`. Optional tone polish: set env `OPENING_POLISH=1` (off by default) and call `?polish=1`; at most one model call (fast model, one sentence). The result is accepted only if it is under 240 characters, has no links and keeps every number from the computed message; otherwise the computed message is returned. Chips are never model-written.
- Errors: `404 not_found`, `429 rate_limited`. A class that is not `READY` still gets a message ("Your class agent is still being built.") with no chips except a placeholder-free empty list.

## Wiring for Builder (module files only, no stack change)

`api.py` protected section, before the generic `/courses/{id}` handlers:
```python
import history_api   # top of file
r = history_api.handle(event, sub, path, method)
if r is not None:
    return r
```
`history_api.handle` returns `None` for paths that are not its own (`GET /courses/{id}/chat/history`, `GET /courses/{id}/opening`, `GET /chat/master/history`). Order matters only in that it must come before any catch-all and before `chat_api` for `/courses/{id}/chat` (different method and path, so no clash).

`infra/stack.py`: nothing new. The API Lambda already has table read/write. DynamoDB TTL must be enabled on the attribute `ttl` (already used by other items). Optional env: `OPENING_POLISH=1`.
