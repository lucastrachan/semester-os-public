# Class tutor API (Phase 4)

Owner: Security agent wrote the backend modules (`backend/chat_api.py`, `backend/lib/tutor.py`, `backend/lib/tools_impl.py`). Builder wires the route (snippet at the end). Status: **coded and tested offline, not deployed, not routed yet.** Additive changes only after Mobile starts coding against this file; breaks are announced in the internal planning notes.

All routes need the student ID token (`Authorization: Bearer <ID token>`), like the rest of `/courses`. The student and course always come from the token and the path, never from the body. Errors use the usual shape `{ "error": "<code>", "message": "<text safe to show>" }`.

## `POST /courses/{id}/chat`

Request body (JSON, at most 200,000 bytes):
```
{
  "mode":     "explain" | "quiz" | "flashcards" | "cram",     // required
  "messages": [ { "role": "user" | "assistant", "content": "text" } ],   // the conversation so far, last item must be role "user"
  "topic":    "optional focus, up to 120 characters",
  "count":    5                                                // optional: quiz 3..10 (default 5), flashcards 5..20 (default 10)
}
```
- `messages`: at most 20 turns are used (the newest), each at most 4,000 characters. Only `user` and `assistant` roles are accepted; a `system` role is rejected with `400`. `messages` may be omitted or empty for `quiz` and `flashcards` when `topic` is given (or neither: the whole class). For `explain` and `cram` it is required.
- Earlier turns are treated by the server as untrusted data (a client can forge "assistant" turns), so they inform the answer but cannot give the tutor orders. Send the whole visible conversation each time; the server stores no chat text.

### Success: `200`
```
{
  "mode": "explain",
  "reply": "plain text with light markdown (bold, lists, code). Never HTML, never images.",
  "actions": [
    { "id": "k3j9x0ab12cd", "kind": "assignment_updated" | "assignment_added" | "study_blocks_created",
      "summary": "Moved Exam 2 to 2026-11-12", "courseId": "abcd1234", "undoable": true }
  ],
  "quiz": null | {
    "questions": [
      { "id": "q1", "type": "mc",    "question": "...", "choices": ["A","B","C","D"], "answerIndex": 2, "explanation": "..." },
      { "id": "q2", "type": "short", "question": "...", "answer": "model answer", "explanation": "..." }
    ]
  },
  "flashcards": null | { "cards": [ { "front": "term", "back": "definition" } ] },
  "handoff": null
}
```
- `reply` is always present (a short intro for quiz and flashcards, the tutor's answer or study plan for explain and cram). Render it as text (React text nodes, RN `<Text>`); simple markdown is allowed but HTML and images have been removed server-side and must not be re-enabled.
- `actions` is empty unless the tutor changed something. Each action is a chip: show `summary`, and an Undo button when `undoable` is true. Every action is also written to the activity feed (`agentId` = the course id).
- `quiz.questions`: 1 to 10 items, `mc` has 2 to 5 `choices` and an `answerIndex` that is in range. `short` has an `answer` for self-checking. Items that failed validation are dropped; if none survive you get `502 bad_model_output`.
- `flashcards.cards`: 1 to 30 items, `front` at most 200 and `back` at most 400 characters.
- `cram`: the reply contains a day-by-day study plan as text. It only schedules study blocks after the student explicitly asks to ("yes, put those in my calendar"); then `actions` contains one `study_blocks_created` chip. Study blocks are saved as assignments with `type: "study"` and `source: "agent"` (they appear in `GET /courses/{id}` and the outbound calendar feed), with `dueDate`, `dueTime` (start) and `endTime` (all local wall-clock, no time zone).
- `handoff` is reserved for the master agent routing; always `null` here.

What the tutor can change (and nothing else): add an assignment, update an assignment (title, date, time, done, notes, type), create study blocks, all in THIS class only. It cannot delete anything, read another class, read the profile, or reach the network. When it changes a date it records `dateSource: "stated"` (the student said so) and the old values for undo.

### Errors

| HTTP | `error` | When | What to show |
|---|---|---|---|
| 400 | `bad_request` | invalid JSON, not an object | generic |
| 400 | `validation_error` | bad `mode`, missing or malformed `messages` (including a `system` role or last message not from the user), bad `topic` or `count` | `message` |
| 401 | `unauthorized` | missing or invalid token (from the router) | sign in again |
| 404 | `not_found` | course id not yours or malformed | "Class not found" |
| 409 | `not_ready` | course `status` is not `READY` (still building, or `ERROR`) | "Your tutor is still being built" |
| 413 | `too_large` | body over 200,000 bytes or a message over 4,000 characters | `message` |
| 429 | `rate_limited` | per-minute or per-day limit hit; header `Retry-After` in seconds | `message`, disable Send until `Retry-After` |
| 502 | `bad_model_output` | quiz, flashcards could not be produced in valid form | "I couldn't make that. Try again." |
| 503 | `ai_disabled` | the AI kill switch is on; header `Retry-After: 300` | `message` |
| 503 | `tutor_busy` | all models busy or timed out | "The tutor is busy. Try again in a few seconds." |
| 500 | `internal_error` | anything unexpected | generic |

### Limits (per student; all numbers live in `backend/lib/limits.py`)
- `explain` and `cram` count against bucket `chat`: 6 per minute and 200 per day.
- `quiz` and `flashcards` count against bucket `quiz`: 4 per minute and 60 per day.
- Rejected requests do not count. Day windows reset at midnight UTC. Replies are capped at 1,024 tokens (explain, cram) or 2,048 (quiz, flashcards). One request makes at most 5 model round trips, 12 tool calls and 6 writes, and stops after about 24 seconds.

## `POST /courses/{id}/chat/undo`

Body `{ "actionId": "k3j9x0ab12cd" }` (an `id` from an earlier response's `actions`). Reverses that action: deletes the study blocks or added assignment it created, or restores the previous values of the updated assignment. The client never sends the undo data, only the id; the server holds the recipe (kept 7 days).
- `200 { "undone": "k3j9x0ab12cd" }`
- `404 not_found` (unknown id, other class, expired), `409 already_undone`, `409 changed_since` (an added or updated item was edited or deleted after the action; nothing is changed), `429 rate_limited`.
Undo also writes an activity entry.

## Behaviour notes for the UI
- Not streaming: show a typing indicator. Typical latency is 4 to 20 seconds; the request can take up to about 25 seconds in the worst case (the API Lambda limit is 29 seconds).
- After a response with actions, refetch `GET /courses/{id}` to show the new or changed deadlines.
- The tutor follows the course's AI policy (`course.policies.ai`) and teaches rather than writing graded work. If the policy forbids help, the reply says so.

## Wiring for Builder (Security did not touch these files)

`backend/api.py`, in the protected section (after `sub = _get_sub(event)`, any place before the 404):
```python
import chat_api   # top of file
m = re.fullmatch(r"/courses/([a-z0-9]+)/chat(/undo)?", path)
if m and method == "POST":
    return chat_api.handle(event, sub, m.group(1), undo=bool(m.group(2)))
```
`api.py`'s generic handler should also catch `limits.LimitError` (`return limits.error_response(e)`), but `chat_api.handle` already catches its own errors and always returns a response dict.

`infra/stack.py`: no new resources. The API Lambda already has the table read/write and Bedrock. Environment (optional): `AI_ENABLED_PARAM=/semesteros/ai_enabled` plus `ssm:GetParameter` on that parameter, `IP_HASH_SALT` (random string, not used by this route). `MODEL_MAIN` and its fallbacks are already set. The `/courses/{proxy+}` style catch-all already routes through the JWT authorizer, so no new route is needed in API Gateway. The Bedrock IAM scope should list the model ids in `model_env` (see `SECURITY.md` W10).
Because a chat turn can take up to ~25 s, keep the API Lambda timeout at 29 s and `BEDROCK_CHAIN_BUDGET_SECONDS` at its default 18.
