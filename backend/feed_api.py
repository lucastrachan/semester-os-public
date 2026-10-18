"""Blackboard feed routes (Phase 6, per class). Contract: FEED_API.md.

handle(event, sub, path, method, deps=None) returns a response dict, or None when the path is not one of its own.
`deps` (tests): {"backend", "table", "fetch", "fetchKwargs", "rules", "now", "chooser"}.
The feed URL is a secret: stored encrypted (lib/secretbox), never logged, never returned (only a masked form).
Every item is reached through guard.UserScopedDB; ids from the client only choose a sort key inside the caller's data.
"""
import json
import re
import time

from lib import feedsync, guard, limits, safe_fetch, secretbox, util

import assignments_api

_ID_RE = re.compile(r"^[a-z0-9]{8}$")
ROUTES = [
    ("PUT", re.compile(r"^/me/feed$"), "put_feed"),
    ("GET", re.compile(r"^/me/feed$"), "get_feed"),
    ("DELETE", re.compile(r"^/me/feed$"), "delete_feed"),
    ("POST", re.compile(r"^/me/feed/sync$"), "sync_all"),
    ("GET", re.compile(r"^/me/feed/classes$"), "classes"),
    ("POST", re.compile(r"^/courses/quick$"), "quick"),
    ("POST", re.compile(r"^/courses/import$"), "import_courses"),
    ("GET", re.compile(r"^/feed/unassigned$"), "list_unassigned"),
    ("POST", re.compile(r"^/feed/unassigned/([a-f0-9]{24})/(assign|dismiss)$"), "resolve"),
    ("POST", re.compile(r"^/feed/unassigned/groups/([a-f0-9]{12})/(assign|dismiss)$"), "resolve_group"),
    ("POST", re.compile(r"^/feed/seen$"), "seen"),
    ("GET", re.compile(r"^/courses/([a-z0-9]{8})/feed$"), "class_feed"),
    ("POST", re.compile(r"^/courses/([a-z0-9]{8})/feed/sync$"), "class_sync"),
]


class _Bad(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _body(event: dict, allowed: set, max_bytes: int = 4000) -> dict:
    limits.check_body_size(event, max_bytes)
    try:
        data = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        raise _Bad(400, "bad_request", "Invalid JSON")
    if not isinstance(data, dict):
        raise _Bad(400, "bad_request", "Body must be a JSON object")
    if set(data) - allowed:
        raise _Bad(400, "validation_error", "Unexpected field(s)")
    return data


class _Ctx:
    def __init__(self, sub: str, deps: dict):
        if deps.get("backend") is None:
            from lib import db  # late import: tests need no AWS libraries
            deps = {**deps, "backend": db}
        self.deps = deps
        self.backend = deps["backend"]
        self.sub = sub
        self.scoped = feedsync.scoped_view(sub, self.backend)
        self.rules = deps.get("rules") or feedsync.load_rules()
        self.now = deps.get("now")

    @property
    def table(self):
        return self.deps["table"] if self.deps.get("table") is not None else self.backend.table()

    def t(self) -> float:
        return self.now if self.now is not None else time.time()

    def limit(self, bucket: str) -> None:
        limits.check_user(self.table, self.sub, bucket, now=self.now)

    def course(self, course_id: str) -> dict:
        c = self.scoped.get(f"COURSE#{course_id}")
        if not c:
            raise _Bad(404, "not_found", "Class not found")
        return c


def handle(event: dict, sub: str, path: str, method: str, deps: dict | None = None):
    method = (method or "").upper()
    for m, rx, name in ROUTES:
        match = rx.match(path or "")
        if m == method and match:
            break
    else:
        return None
    try:
        ctx = _Ctx(sub, deps or {})
        return globals()["_" + name](ctx, event, *match.groups())
    except limits.LimitError as e:
        return limits.error_response(e)
    except _Bad as e:
        return util.error(e.status, e.code, e.message)
    except feedsync.NotConnected:
        return util.error(409, "not_connected", "Add your Blackboard calendar link first.")
    except feedsync.FeedError as e:
        return util.error(e.status, e.code, e.message)
    except feedsync.NotFound:
        return util.error(404, "not_found", "Item not found")
    except guard.ScopeError:
        return util.error(401, "unauthorized", "Missing or invalid token")
    except Exception as e:  # noqa: BLE001
        print(f"feed_api unexpected error: {feedsync.safe_trace(e)}")  # type and file:line frames only: messages could carry the URL
        return util.error(500, "internal_error", "An internal error occurred")


# ── helpers ───────────────────────────────────────────────────────────────────

def _cfg(ctx: _Ctx):
    return ctx.scoped.get("FEED")


def _best_effort(what: str, fn, *args) -> None:
    """Secondary writes (profile mirror, poller index) must never fail the request: log where, not what."""
    try:
        fn(*args)
    except Exception as e:  # noqa: BLE001
        print(f"feed_api {what} skipped: {feedsync.safe_trace(e)}")


def _mirror(ctx: _Ctx, feed) -> None:
    def go():
        if ctx.scoped.get("PROFILE"):
            ctx.scoped.update("PROFILE", {"feed": feed})
    _best_effort("profile mirror", go)


def _cooldown(cfg: dict | None, now: float) -> int:
    if cfg and cfg.get("lastManualSyncAt"):
        return max(0, int(feedsync.MANUAL_COOLDOWN - (now - float(cfg["lastManualSyncAt"]))))
    return 0


def _status_view(ctx: _Ctx, cfg: dict) -> dict:
    counts = dict(cfg.get("counts") or {})
    new_since = sum(int((c.get("knows") or {}).get("newItemsCount") or 0) for c in ctx.scoped.query("COURSE#"))
    return {"connected": True, "urlMasked": cfg.get("urlMasked"), "lastCheckedAt": cfg.get("lastCheckedAt"),
            "lastStatus": cfg.get("lastStatus") or "never", "lastError": cfg.get("lastError"),
            "nextCheckAt": feedsync.now_iso(cfg["nextSyncAt"]) if cfg.get("nextSyncAt") else None,
            "counts": {"events": counts.get("events", 0), "matched": counts.get("matched", 0),
                       "unassigned": counts.get("unassigned", 0), "dismissed": counts.get("dismissed", 0),
                       "addedLastSync": counts.get("addedLastSync", 0), "updatedLastSync": counts.get("updatedLastSync", 0),
                       "newSinceSeen": new_since},
            "syncCooldownSeconds": _cooldown(cfg, ctx.t())}


# ── /me/feed ──────────────────────────────────────────────────────────────────

def _put_feed(ctx: _Ctx, event: dict):
    data = _body(event, {"url"})
    url = data.get("url")
    if not isinstance(url, str):
        raise _Bad(400, "validation_error", "url must be text")
    url = url.strip()
    if url[:9].lower() == "webcal://":
        url = "https://" + url[9:]
    ctx.limit("feed_save")
    try:
        safe_fetch.check_url(url)
        text = (ctx.deps.get("fetch") or feedsync._default_fetch)(url, **(ctx.deps.get("fetchKwargs") or {}))
    except safe_fetch.FetchError as e:
        raise _Bad(400, "feed_" + e.code, e.message)
    tz = feedsync._tz_for(ctx.scoped, ctx.backend)
    events = feedsync.parse_ics(text, tz, ctx.rules)
    today = time.strftime("%Y-%m-%d", time.gmtime(ctx.t()))
    try:
        sealed = secretbox.seal(url, feedsync.PURPOSE, ctx.sub)
    except secretbox.SecretBoxError:
        raise _Bad(503, "encryption_unavailable", "We can't store your link safely right now. Please try again later.")
    masked = feedsync.mask_url(url)
    for row in ctx.scoped.query("FEED#"):          # a new feed starts with a clean cache (assignments stay and are re-linked)
        ctx.scoped.delete(row["sk"])
    now = ctx.t()
    ctx.scoped.put("FEED", {"urlEnc": sealed, "urlMasked": masked, "addedAt": feedsync.now_iso(now), "lastCheckedAt": None,
                            "lastStatus": "never", "lastError": None, "counts": {}, "nextSyncAt": int(now),
                            "classesDetected": feedsync.detect_classes_safe(events, feedsync.today_local(tz, now), ctx.rules),
                            "suggestedCodes": feedsync.suggest_codes_safe(events, feedsync.today_local(tz, now), ctx.rules)})
    _mirror(ctx, {"connected": True, "urlMasked": masked, "lastCheckedAt": None, "lastStatus": "never"})
    _best_effort("poller index", feedsync.index_put, ctx.backend, ctx.sub, now)
    imported = []
    try:
        courses = [c for c in ctx.scoped.query("COURSE#") if isinstance(c, dict)]
        cfg_now = dict(ctx.scoped.get("FEED") or {})
        imported = feedsync.import_classes(ctx.scoped, ctx.sub, cfg_now, cfg_now.get("classesDetected") or {}, courses, ctx.rules, now)
    except Exception as e:  # noqa: BLE001 (the link is saved either way)
        print(f"feed_api class import skipped: {feedsync.safe_trace(e)}")
    return util.ok({"connected": True, "urlMasked": masked, "importedClasses": imported, "eventCount": len(events),
                    "upcomingCount": sum(1 for e in events if e.get("dueDate") and e["dueDate"] >= today)})


def _get_feed(ctx: _Ctx, event: dict):
    ctx.limit("default")
    cfg = _cfg(ctx)
    if not cfg:
        return util.ok({"connected": False})
    if not ctx.backend.get_item(f"FEEDUSER#{feedsync.shard_of(ctx.sub)}", f"U#{ctx.sub}"):
        feedsync.index_put(ctx.backend, ctx.sub, ctx.t())   # self-heal a missing poller index item
    return util.ok(_status_view(ctx, cfg))


def _classes(ctx: _Ctx, event: dict):
    ctx.limit("default")
    courses = [c for c in ctx.scoped.query("COURSE#") if isinstance(c, dict)]
    return util.ok(feedsync.classes_view(_cfg(ctx), courses))


def _quick(ctx: _Ctx, event: dict):
    data = _body(event, {"courses"}, 8000)
    items = data.get("courses")
    if not isinstance(items, list) or not items or len(items) > feedsync.MAX_QUICK_PER_CALL:
        raise _Bad(400, "validation_error", f"courses must be a list of 1 to {feedsync.MAX_QUICK_PER_CALL} items")
    if any(not isinstance(i, dict) or set(i) - {"code", "title", "section"} for i in items):
        raise _Bad(400, "validation_error", "each course needs a code, and may have a title and section")
    ctx.limit("default")
    courses = [c for c in ctx.scoped.query("COURSE#") if isinstance(c, dict)]
    cfg = _cfg(ctx) or {}
    term = (cfg.get("classesDetected") or {}).get("term") or next((c.get("termCode") for c in courses if c.get("termCode")), "") or ""
    created, skipped, invalid = feedsync.add_courses_by_code(ctx.scoped, ctx.sub, items, courses, str(term), ctx.t())
    placed = 0
    if created and cfg:
        try:
            placed = feedsync.reclassify_unassigned(ctx.scoped, ctx.sub, ctx.rules, ctx.t())
        except Exception as e:  # noqa: BLE001 (the classes exist either way)
            print(f"feed_api placement skipped: {feedsync.safe_trace(e)}")
    return util.ok({"created": created, "skipped": skipped, "invalid": invalid, "placed": placed}, 201 if created else 200)


_IMPORT_CLASS_KEYS = {"identifier", "code", "section", "term", "title", "instructor", "assignments"}
_IMPORT_ASG_KEYS = {"title", "dueDate", "dueTime", "tz"}


def _import_courses(ctx: _Ctx, event: dict):
    data = _body(event, {"source", "classes"}, 600_000)
    source = data.get("source")
    if source not in ("blackboard", "canvas"):
        raise _Bad(400, "validation_error", "source must be blackboard or canvas")
    classes = data.get("classes")
    if not isinstance(classes, list) or not classes or len(classes) > feedsync.MAX_IMPORT_CLASSES:
        raise _Bad(400, "validation_error", f"classes must be a list of 1 to {feedsync.MAX_IMPORT_CLASSES} items")
    for c in classes:
        if not isinstance(c, dict) or set(c) - _IMPORT_CLASS_KEYS:
            raise _Bad(400, "validation_error", "unexpected field in a class")
        asg = c.get("assignments", [])
        if not isinstance(asg, list) or len(asg) > feedsync.MAX_IMPORT_ASSIGNMENTS:
            raise _Bad(400, "validation_error", f"assignments must be a list of at most {feedsync.MAX_IMPORT_ASSIGNMENTS}")
        if any(not isinstance(a, dict) or set(a) - _IMPORT_ASG_KEYS for a in asg):
            raise _Bad(400, "validation_error", "unexpected field in an assignment")
    ctx.limit("course_import")
    tz = feedsync._tz_for(ctx.scoped, ctx.backend)
    out = feedsync.import_blackboard(ctx.scoped, ctx.sub, classes, ctx.rules, tz, ctx.t(), source=source)
    if out["created"] and _cfg(ctx):
        try:
            feedsync.reclassify_unassigned(ctx.scoped, ctx.sub, ctx.rules, ctx.t())
        except Exception as e:  # noqa: BLE001
            print(f"feed_api placement skipped: {feedsync.safe_trace(e)}")
    return util.ok(out, 201 if out["created"] else 200)


def _delete_feed(ctx: _Ctx, event: dict):
    ctx.limit("default")
    for row in ctx.scoped.query("FEED#"):
        ctx.scoped.delete(row["sk"])
    ctx.scoped.delete("FEED")
    feedsync.index_delete(ctx.backend, ctx.sub)
    _mirror(ctx, None)
    return util.ok({"connected": False})


def _run_sync(ctx: _Ctx):
    cfg = _cfg(ctx)
    if not cfg:
        raise feedsync.NotConnected()
    wait = _cooldown(cfg, ctx.t())
    if wait:
        raise limits.RateLimited("You just checked. Try again in a couple of minutes.", wait)
    ctx.limit("feed_sync")
    d = {k: ctx.deps[k] for k in ("backend", "fetch", "fetchKwargs", "rules", "chooser") if ctx.deps.get(k) is not None}
    return feedsync.sync_user(ctx.sub, d, now=ctx.now, manual=True)


def _sync_all(ctx: _Ctx, event: dict):
    s = _run_sync(ctx)
    return util.ok({"status": s["status"], "added": s["added"], "updated": s["updated"], "unassigned": s["counts"]["unassigned"],
                    "unchanged": s["unchanged"], "checkedAt": s["checkedAt"],
                    "importedClasses": s.get("importedClasses") or []})


# ── Unassigned inbox ──────────────────────────────────────────────────────────

def _list_unassigned(ctx: _Ctx, event: dict):
    ctx.limit("default")
    items = feedsync.inbox(ctx.scoped, ctx.rules, limit=2000)
    return util.ok({"unassigned": items[:200], "groups": feedsync.build_groups(items)[:50]})


def _resolve(ctx: _Ctx, event: dict, uid: str, action: str):
    if action == "assign":
        data = _body(event, {"courseId", "remember"})
        cid = data.get("courseId")
        if not isinstance(cid, str) or not _ID_RE.match(cid):
            raise _Bad(400, "validation_error", "courseId is not a valid id")
        remember = data.get("remember", True)
        if not isinstance(remember, bool):
            raise _Bad(400, "validation_error", "remember must be true or false")
        ctx.limit("default")
        r = feedsync.assign_event(ctx.scoped, ctx.sub, uid, cid, remember, ctx.rules, ctx.now)
        return util.ok({"assignment": assignments_api.present(r["assignment"], r["course"]), "learned": r["learned"],
                        "alsoAssigned": r["alsoAssigned"]})
    data = _body(event, {"remember"})
    remember = data.get("remember", False)
    if not isinstance(remember, bool):
        raise _Bad(400, "validation_error", "remember must be true or false")
    ctx.limit("default")
    return util.ok(feedsync.dismiss_event(ctx.scoped, uid, remember, ctx.rules, ctx.now))


def _resolve_group(ctx: _Ctx, event: dict, gid: str, action: str):
    if action == "assign":
        data = _body(event, {"courseId", "remember"})
        cid = data.get("courseId")
        if not isinstance(cid, str) or not _ID_RE.match(cid):
            raise _Bad(400, "validation_error", "courseId is not a valid id")
        remember = data.get("remember", True)
        if not isinstance(remember, bool):
            raise _Bad(400, "validation_error", "remember must be true or false")
        ctx.limit("default")
        return util.ok(feedsync.assign_group(ctx.scoped, ctx.sub, gid, cid, remember, ctx.rules, ctx.now))
    data = _body(event, {"remember"})
    remember = data.get("remember", False)
    if not isinstance(remember, bool):
        raise _Bad(400, "validation_error", "remember must be true or false")
    ctx.limit("default")
    return util.ok(feedsync.dismiss_group(ctx.scoped, gid, remember, ctx.rules, ctx.now))


def _seen(ctx: _Ctx, event: dict):
    data = _body(event, {"courseId"})
    cid = data.get("courseId")
    if cid is not None:
        if not isinstance(cid, str) or not _ID_RE.match(cid):
            raise _Bad(400, "validation_error", "courseId is not a valid id")
        ctx.course(cid)
    ctx.limit("default")
    feedsync.mark_seen(ctx.scoped, cid)
    return util.ok({"ok": True})


# ── Per class ─────────────────────────────────────────────────────────────────

def _class_view(ctx: _Ctx, course_id: str):
    course = ctx.course(course_id)
    cfg = _cfg(ctx)
    if not cfg:
        return {"connected": False, "stats": None, "items": [], "unassigned": [], "meetings": [],
                "needsSyllabus": feedsync.needs_syllabus(course)}
    rows = ctx.scoped.query("FEED#")
    return {"connected": True, "stats": feedsync.class_stats(cfg, course, rows, ctx.t()),
            "needsSyllabus": feedsync.needs_syllabus(course),
            "items": feedsync.class_items(ctx.scoped, course_id),
            "meetings": (cfg.get("meetingHints") or {}).get(course_id, []),
            "unassigned": feedsync.inbox(ctx.scoped, ctx.rules, course_id=course_id)}


def _class_feed(ctx: _Ctx, event: dict, course_id: str):
    ctx.course(course_id)
    ctx.limit("default")
    return util.ok(_class_view(ctx, course_id))


def _class_sync(ctx: _Ctx, event: dict, course_id: str):
    ctx.course(course_id)
    s = _run_sync(ctx)
    view = _class_view(ctx, course_id)
    mine = s.get("byCourse", {}).get(course_id, {})
    return util.ok({"status": s["status"], "added": mine.get("created", 0), "updated": mine.get("updated", 0),
                    "unassigned": s["counts"]["unassigned"], "stats": view["stats"],
                    "importedClasses": s.get("importedClasses") or []})
