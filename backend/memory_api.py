"""Class memory routes. Contract: MEMORY_API.md.

handle(event, sub, path, method, deps=None) returns a response dict, or None when the path is not one of its own.
`deps` (tests): {"backend", "table"}.
"""
import json
import re

from lib import classdata, limits, memory, util

_COLL_RE = re.compile(r"^/courses/([a-z0-9]{8})/memory$")
_NOTE_RE = re.compile(r"^/courses/([a-z0-9]{8})/memory/([A-Za-z0-9_\-]{1,40})$")
VIEW_PREFIXES = ("COURSE", "MEM")


def _default_deps() -> dict:
    from lib import db  # late import: tests need no AWS libraries
    return {"backend": db, "table": None}


def _is_own(method: str, path: str) -> bool:
    if _COLL_RE.match(path):
        return method in ("GET", "POST", "DELETE")
    return bool(_NOTE_RE.match(path)) and method in ("PATCH", "DELETE")


def _text(event: dict) -> str:
    limits.check_body_size(event, 10_000)
    try:
        data = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        raise memory.NoteError(400, "bad_request", "Invalid JSON")
    if not isinstance(data, dict):
        raise memory.NoteError(400, "bad_request", "Body must be a JSON object")
    return data.get("text")


def handle(event: dict, sub: str, path: str, method: str, deps: dict | None = None):
    method = (method or "").upper()
    if not _is_own(method, path):
        return None
    try:
        deps = deps or _default_deps()
        backend = deps["backend"]
        table = deps.get("table") or (backend.table() if hasattr(backend, "table") else None)
        m = _COLL_RE.match(path) or _NOTE_RE.match(path)
        course_id = m.group(1)
        limits.check_user(table, sub, "default")
        view = classdata.view(sub, backend, *VIEW_PREFIXES)
        if not view.get(f"COURSE#{course_id}"):
            return util.error(404, "not_found", "Class not found")
        if m.re is _COLL_RE:
            if method == "GET":
                notes = memory.list_notes(view, course_id)
                return util.ok({"notes": notes, "limit": memory.MAX_NOTES, "count": len(notes)})
            if method == "POST":
                note = memory.add(view, course_id, _text(event), "student")
                note.pop("duplicate", None)
                return util.ok({"note": note}, 201)
            return util.ok({"deleted": memory.clear(view, course_id)})
        note_id = m.group(2)
        if method == "PATCH":
            return util.ok({"note": memory.update(view, course_id, note_id, _text(event))})
        memory.delete(view, course_id, note_id)
        return util.ok({"deleted": note_id})
    except limits.LimitError as e:
        return limits.error_response(e)
    except memory.NoteError as e:
        return util.error(e.status, e.code, e.message)
    except Exception as e:  # noqa: BLE001  (includes guard.ScopeError)
        print(f"memory_api unexpected error: {type(e).__name__}")
        return util.error(500, "internal_error", "An internal error occurred")
