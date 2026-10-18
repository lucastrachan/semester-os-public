"""/assignments routes (handoff section 9, Phase 3). Called from api.py with the authenticated `sub`.

Every item is reached through guard.UserScopedDB, so the partition key is always USER#{sub} (from the JWT);
ids sent by the client only choose a sort key. All text is cleaned and length-capped on write.
Contract: CALENDAR_API.md.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone

from lib import db, guard, limits, util

MAX_LIST = 500
MAX_PER_COURSE = 400
DATE_WINDOW_DAYS = 800
_ID_RE = re.compile(r"^[a-z0-9]{8}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_PATCH_FIELDS = {"title", "type", "dueDate", "dueTime", "notes", "weight", "done"}
_CREATE_FIELDS = {"courseId", "title", "type", "dueDate", "dueTime", "notes", "weight"}


class _Bad(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def _table():
    return db.table()


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _scoped(sub: str) -> guard.UserScopedDB:
    try:
        return guard.UserScopedDB(sub, db, allowed_prefixes=("ASG", "COURSE"))
    except guard.ScopeError:
        raise _Bad(401, "unauthorized", "Missing or invalid token")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── Validation ────────────────────────────────────────────────────────────────

def _body(event: dict, allowed: set) -> dict:
    try:
        limits.check_body_size(event, 20_000)
    except limits.LimitError as e:
        raise _Bad(e.status, e.code, e.message)
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        raise _Bad(400, "bad_request", "Invalid JSON")
    if not isinstance(data, dict):
        raise _Bad(400, "bad_request", "Body must be a JSON object")
    extra = set(data) - allowed
    if extra:
        raise _Bad(400, "validation_error", f"Unexpected field(s): {', '.join(sorted(str(e)[:30] for e in extra))}")
    return data


def _v_text(data: dict, key: str, max_len: int, required: bool = False, min_len: int = 1):
    v = data.get(key)
    if v is None:
        if required:
            raise _Bad(400, "validation_error", f"{key} is required")
        return None
    if not isinstance(v, str):
        raise _Bad(400, "validation_error", f"{key} must be text")
    cleaned = guard.clean_text(v, max_len + 1).replace("\n", " ").strip() if key != "notes" else guard.clean_text(v, max_len + 1).strip()
    if len(cleaned) > max_len:
        raise _Bad(400, "validation_error", f"{key} is longer than {max_len} characters")
    if required and len(cleaned) < min_len:
        raise _Bad(400, "validation_error", f"{key} is required")
    return cleaned


def _v_date(v, key: str = "dueDate") -> str:
    if not isinstance(v, str) or not _DATE_RE.match(v):
        raise _Bad(400, "validation_error", f"{key} must be YYYY-MM-DD")
    try:
        d = date.fromisoformat(v)
    except ValueError:
        raise _Bad(400, "validation_error", f"{key} is not a real calendar date")
    if abs((d - _today()).days) > DATE_WINDOW_DAYS:
        raise _Bad(400, "validation_error", f"{key} is too far from today")
    return d.isoformat()


def _v_time(v) -> str:
    if not isinstance(v, str) or not _TIME_RE.match(v):
        raise _Bad(400, "validation_error", "dueTime must be HH:MM (24-hour)")
    return v


def _v_weight(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not 0 <= v <= 100:
        raise _Bad(400, "validation_error", "weight must be a number from 0 to 100")
    return v


def _v_type(v) -> str:
    if not isinstance(v, str) or v not in guard.ASSIGNMENT_TYPES:
        raise _Bad(400, "validation_error", f"type must be one of {', '.join(guard.ASSIGNMENT_TYPES)}")
    return v


def _v_id(v, key: str = "courseId") -> str:
    if not isinstance(v, str) or not _ID_RE.match(v):
        raise _Bad(400, "validation_error", f"{key} is not a valid id")
    return v


def _limit(sub: str) -> None:
    try:
        limits.check_user(_table(), sub, "default")
    except limits.LimitError as e:
        raise _Bad(e.status, e.code, e.message)


# ── Presentation ──────────────────────────────────────────────────────────────

def present(item: dict, course: dict | None) -> dict:
    out = {k: v for k, v in item.items() if k not in ("pk", "sk") and not str(k).startswith("gsi")}
    out.setdefault("dueDate", None)
    out.setdefault("dueTime", None)
    out.setdefault("weight", None)
    out.setdefault("notes", "")
    out.setdefault("done", False)
    out.setdefault("dueText", "")
    out.setdefault("dateSource", None)
    out["sequence"] = int(out.get("sequence") or 0)
    out["updatedAt"] = out.get("updatedAt") or out.get("createdAt")
    out["courseCode"] = (course or {}).get("courseCode") or ""
    out["courseColor"] = (course or {}).get("color") or ""
    return out


def _sort_key(a: dict):
    return (a.get("dueDate") is None, a.get("dueDate") or "", a.get("dueTime") is None, a.get("dueTime") or "", a.get("title", ""))


def _handle(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _Bad as e:
            return util.error(e.status, e.code, e.message)
    wrapper.__name__ = fn.__name__
    return wrapper


# ── Routes ────────────────────────────────────────────────────────────────────

@_handle
def list_assignments(event: dict, sub: str):
    qs = event.get("queryStringParameters") or {}
    scoped = _scoped(sub)
    d_from = _v_date(qs["from"], "from") if qs.get("from") else None
    d_to = _v_date(qs["to"], "to") if qs.get("to") else None
    if d_from and d_to and d_from > d_to:
        raise _Bad(400, "validation_error", "from must not be after to")
    done = qs.get("done")
    if done not in (None, "", "true", "false"):
        raise _Bad(400, "validation_error", "done must be true or false")
    include_undated = qs.get("undated") == "include"

    course_id = qs.get("courseId")
    courses = {c.get("id"): c for c in scoped.query("COURSE#")}
    if course_id:
        _v_id(course_id)
        if course_id not in courses:
            raise _Bad(404, "not_found", "Class not found")
        items = scoped.query(f"ASG#{course_id}#")
    else:
        items = scoped.query("ASG#")

    out = []
    for it in items:
        due = it.get("dueDate")
        if (d_from or d_to) and not due:
            if not include_undated:
                continue
        elif due:
            if d_from and due < d_from:
                continue
            if d_to and due > d_to:
                continue
        if done in ("true", "false") and bool(it.get("done")) != (done == "true"):
            continue
        out.append(present(it, courses.get(it.get("courseId"))))
    out.sort(key=_sort_key)
    return util.ok({"assignments": out[:MAX_LIST]})


@_handle
def create_assignment(event: dict, sub: str):
    scoped = _scoped(sub)
    data = _body(event, _CREATE_FIELDS)
    course_id = _v_id(data.get("courseId"))
    title = _v_text(data, "title", 160, required=True)
    kind = _v_type(data.get("type"))
    due_date = _v_date(data["dueDate"]) if data.get("dueDate") is not None else None
    due_time = _v_time(data["dueTime"]) if data.get("dueTime") is not None else None
    if due_time and not due_date:
        raise _Bad(400, "validation_error", "dueTime needs a dueDate")
    notes = _v_text(data, "notes", 400) or ""
    weight = _v_weight(data["weight"]) if data.get("weight") is not None else None

    course = scoped.get(f"COURSE#{course_id}")
    if not course:
        raise _Bad(404, "not_found", "Class not found")
    _limit(sub)
    if len(scoped.query(f"ASG#{course_id}#")) >= MAX_PER_COURSE:
        raise _Bad(409, "limit", "That class already has the maximum number of items.")

    asg_id = util.short_id()
    now = _now()
    item = util.to_dynamo({
        "id": asg_id, "courseId": course_id, "title": title, "type": kind,
        "dueDate": due_date, "dueTime": due_time, "weight": weight, "notes": notes,
        "dueText": "", "dateSource": "manual" if due_date else None,
        "done": False, "source": "manual", "sequence": 0, "createdAt": now, "updatedAt": now,
    })
    scoped.put(f"ASG#{course_id}#{asg_id}", item)
    return util.ok({"assignment": present(item, course)}, 201)


@_handle
def update_assignment(event: dict, sub: str, asg_id: str):
    scoped = _scoped(sub)
    if not _ID_RE.match(asg_id or ""):
        raise _Bad(404, "not_found", "Item not found")
    data = _body(event, _PATCH_FIELDS)
    if not data:
        raise _Bad(400, "validation_error", "Nothing to change")

    current = next((i for i in scoped.query("ASG#") if i.get("id") == asg_id), None)
    if not current:
        raise _Bad(404, "not_found", "Item not found")  # also the answer for another user's id
    sk = f"ASG#{current['courseId']}#{asg_id}"

    new = {}
    if "title" in data:
        new["title"] = _v_text(data, "title", 160, required=True)
    if "type" in data:
        new["type"] = _v_type(data["type"])
    if "notes" in data:
        if data["notes"] is None:
            raise _Bad(400, "validation_error", "notes must be text")
        new["notes"] = _v_text(data, "notes", 400) or ""
    if "weight" in data:
        new["weight"] = None if data["weight"] is None else _v_weight(data["weight"])
    if "done" in data:
        if not isinstance(data["done"], bool):
            raise _Bad(400, "validation_error", "done must be true or false")
        new["done"] = data["done"]
    if "dueDate" in data:
        new["dueDate"] = None if data["dueDate"] is None else _v_date(data["dueDate"])
    if "dueTime" in data:
        new["dueTime"] = None if data["dueTime"] is None else _v_time(data["dueTime"])

    final_date = new.get("dueDate", current.get("dueDate"))
    if "dueDate" in new and new["dueDate"] is None:
        new["dueTime"] = None  # an item with no date cannot have a time
    final_time = new.get("dueTime", current.get("dueTime"))
    if final_time and not final_date:
        raise _Bad(400, "validation_error", "dueTime needs a dueDate")

    changed = {k: v for k, v in new.items() if current.get(k) != v}
    course = scoped.get(f"COURSE#{current['courseId']}")
    if not changed:
        return util.ok({"assignment": present(current, course)})
    _limit(sub)

    if "dueDate" in changed or "dueTime" in changed:
        changed["dateSource"] = "manual" if final_date else None
    changed["sequence"] = int(current.get("sequence") or 0) + 1
    changed["updatedAt"] = _now()
    updated = scoped.update(sk, util.to_dynamo(changed))
    merged = {**current, **updated}
    return util.ok({"assignment": present(merged, course)})
