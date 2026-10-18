"""Chat history and opening message routes. Contract: HISTORY_API.md.

handle(event, sub, path, method, deps=None) returns a response dict, or None when the path is not one of its own.
`deps` (tests): {"backend", "table", "env", "now", "converse_fast"}.
"""
import os
import re
from datetime import datetime, timezone

from lib import classdata, history, limits, opening, util

_HIST_RE = re.compile(r"^/courses/([a-z0-9]{8})/chat/history$")
_OPEN_RE = re.compile(r"^/courses/([a-z0-9]{8})/opening$")
VIEW_PREFIXES = ("COURSE", "ASG", "MAT")


def _default_deps() -> dict:
    from lib import bedrock, db  # late import: tests need no AWS libraries

    def fast(system, messages, tools, force_tool, max_tokens):
        return bedrock.converse(bedrock.MODEL_FAST, system, messages, tools=tools, force_tool=force_tool,
                                max_tokens=max_tokens)

    return {"backend": db, "table": None, "env": None, "now": None, "converse_fast": fast}


def _is_own(method: str, path: str) -> bool:
    if method != "GET":
        return False
    return path == "/chat/master/history" or bool(_HIST_RE.match(path) or _OPEN_RE.match(path))


def handle(event: dict, sub: str, path: str, method: str, deps: dict | None = None):
    method = (method or "").upper()
    if not _is_own(method, path):
        return None
    try:
        deps = deps or _default_deps()
        backend = deps["backend"]
        table = deps.get("table") or (backend.table() if hasattr(backend, "table") else None)
        now = deps.get("now") or datetime.now(timezone.utc)
        qs = event.get("queryStringParameters") or {}
        limits.check_user(table, sub, "default")
        if path == "/chat/master/history":
            before, limit = history.parse_params(qs)
            return util.ok(history.page(backend, sub, "master", before, limit, now))
        m = _HIST_RE.match(path)
        if m:
            _course(backend, sub, m.group(1))
            before, limit = history.parse_params(qs)
            return util.ok(history.page(backend, sub, m.group(1), before, limit, now))
        course_id = _OPEN_RE.match(path).group(1)
        return _opening(backend, sub, course_id, qs, deps, table, now)
    except limits.LimitError as e:
        return limits.error_response(e)
    except history.HistoryError as e:
        return util.error(e.status, e.code, e.message)
    except Exception as e:  # noqa: BLE001  (includes guard.ScopeError)
        print(f"history_api unexpected error: {type(e).__name__}")
        return util.error(500, "internal_error", "An internal error occurred")


def _course(backend, sub: str, course_id: str) -> dict:
    course = classdata.view(sub, backend, *VIEW_PREFIXES).get(f"COURSE#{course_id}")
    if not course:
        raise history.HistoryError(404, "not_found", "Class not found")
    return course


def _local_today(backend, sub: str, now: datetime):
    try:
        from zoneinfo import ZoneInfo
        profile = backend.get_item(f"USER#{sub}", "PROFILE") or {}
        tenant = backend.get_item("TENANTS", f"T#{profile.get('tenantId', '')}") or {}
        return now.astimezone(ZoneInfo(tenant.get("timezone") or "America/Chicago")).date()
    except Exception:  # noqa: BLE001
        return now.date()


def _opening(backend, sub: str, course_id: str, qs: dict, deps: dict, table, now: datetime) -> dict:
    course = _course(backend, sub, course_id)
    view = classdata.view(sub, backend, *VIEW_PREFIXES)
    today = deps.get("today") or _local_today(backend, sub, now)
    out = opening.build(course, view.query(f"ASG#{course_id}#"), view.query(f"MAT#{course_id}#"), today, now)
    env = deps.get("env") if deps.get("env") is not None else os.environ
    if qs.get("polish") == "1" and str(env.get("OPENING_POLISH", "0")) == "1" and out["chips"]:
        try:
            limits.require_ai_enabled(env=env)
            limits.check_user(table, sub, "briefing")
            better = opening.polish(out["message"], deps["converse_fast"])
        except limits.LimitError:
            better = None
        if better:
            out["message"], out["polished"] = better, True
    return util.ok(out)
