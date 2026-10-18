"""POST /courses/{id}/chat and /courses/{id}/chat/undo (handoff 7.3, 9). See TUTOR_API.md.

handle(event, sub, course_id, undo=False, deps=None) always returns an API Gateway response dict. `deps` lets tests
inject {"backend": db-like, "table": counter table, "converse": fn, "today": date, "env": dict}.
"""
import json
import re
from datetime import datetime, timezone

from lib import guard, history, limits, tools_impl, tutor, util

_ID_RE = re.compile(r"^[a-z0-9]{8}$")
MAX_TOPIC = 120


def _default_deps(sub: str) -> dict:
    from lib import bedrock, db  # imported late so the pure logic and tests need no AWS libraries

    def converse(system, messages, tools, force_tool, max_tokens):
        return bedrock.converse(bedrock.MODEL_MAIN, system, messages, tools=tools, force_tool=force_tool,
                                max_tokens=max_tokens)

    return {"backend": db, "table": None, "converse": converse, "today": None, "env": None}


def _today(backend, sub: str):
    from datetime import date
    from zoneinfo import ZoneInfo
    try:
        profile = backend.get_item(f"USER#{sub}", "PROFILE") or {}
        tenant = backend.get_item("TENANTS", f"T#{profile.get('tenantId', '')}") or {}
        return datetime.now(ZoneInfo(tenant.get("timezone") or "America/Chicago")).date()
    except Exception:  # noqa: BLE001
        return date.today()


def _body(event: dict) -> dict:
    limits.check_body_size(event)
    try:
        data = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        raise tutor.TutorError(400, "bad_request", "Invalid JSON")
    if not isinstance(data, dict):
        raise tutor.TutorError(400, "bad_request", "Body must be a JSON object")
    return data


def _int(v, lo, hi, default):
    if v is None:
        return default
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise tutor.TutorError(400, "validation_error", f"'count' must be a whole number from {lo} to {hi}")
    return v


def handle(event: dict, sub: str, course_id: str, undo: bool = False, deps: dict | None = None) -> dict:
    try:
        deps = deps or _default_deps(sub)
        backend = deps["backend"]
        table = deps.get("table") or (backend.table() if hasattr(backend, "table") else None)
        env = deps.get("env")
        if not isinstance(course_id, str) or not _ID_RE.match(course_id):
            return util.error(404, "not_found", "Class not found")
        view = tools_impl.scoped_view(sub, backend)
        course = view.get(f"COURSE#{course_id}")
        if not course:
            return util.error(404, "not_found", "Class not found")

        if undo:
            return _undo(event, view, table, sub, course_id)

        limits.require_ai_enabled(**({"env": env} if env is not None else {}))
        body = _body(event)
        mode = body.get("mode")
        if mode not in tutor.MODES:
            raise tutor.TutorError(400, "validation_error", f"mode must be one of {', '.join(tutor.MODES)}")
        topic = body.get("topic")
        if topic is not None and (not isinstance(topic, str) or len(topic) > MAX_TOPIC):
            raise tutor.TutorError(400, "validation_error", f"topic must be text up to {MAX_TOPIC} characters")
        topic = guard.clean_text(topic or "", MAX_TOPIC).strip()
        raw = body.get("messages")
        if raw in (None, []) and mode in ("quiz", "flashcards"):
            messages = []
        else:
            try:
                messages = limits.cap_messages(raw)
            except limits.InputTooLarge:
                raise
            except limits.LimitError as e:
                raise tutor.TutorError(400, "validation_error", e.message)
        count = _int(body.get("count"), 3, 10, 5) if mode == "quiz" else _int(body.get("count"), 5, 20, 10)
        fetch_failed = body.get("fetchFailed")
        if fetch_failed is not None and not isinstance(fetch_failed, str):
            raise tutor.TutorError(400, "validation_error", "'fetchFailed' must be a string URL")

        if course.get("status") != "READY":
            return util.error(409, "not_ready", "Your tutor is still being built. Try again in a moment.")

        limits.check_user(table, sub, tutor.MODE_BUCKET[mode])
        today = deps.get("today") or _today(backend, sub)
        try:
            out = tutor.respond(course, mode, messages, topic, count, view, deps["converse"], today,
                                fetch_failed=fetch_failed)
        except tutor.TutorError:
            raise
        except guard.ScopeError:
            return util.error(404, "not_found", "Class not found")
        except Exception as e:  # noqa: BLE001  (model chain exhausted, timeouts, throttling)
            print(f"tutor model call failed: {type(e).__name__}")   # class name only: no message, no content
            return util.error(503, "tutor_busy", "The tutor is busy. Try again in a few seconds.")
        # persistent history (HISTORY_API.md): never allowed to fail the turn the student already got
        history.safe_append(backend, sub, course_id, history.turn_user_text(messages, mode, topic), out, mode)
        return util.ok(out)

    except limits.LimitError as e:
        return limits.error_response(e)
    except tutor.TutorError as e:
        return util.error(e.status, e.code, e.message)
    except Exception as e:  # noqa: BLE001
        print(f"chat_api unexpected error: {type(e).__name__}")
        return util.error(500, "internal_error", "An internal error occurred")


def _undo(event: dict, view, table, sub: str, course_id: str) -> dict:
    body = _body(event)
    limits.check_user(table, sub, "default")
    try:
        tools_impl.undo_action(view, course_id, body.get("actionId"))
    except tools_impl.UndoError as e:
        return util.error(e.status, e.code, e.message)
    return util.ok({"undone": body["actionId"]})
