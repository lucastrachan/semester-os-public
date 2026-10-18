"""Master agent routes (handoff 7.4, 7.5, 9). Contract: MASTER_API.md.

handle(event, sub, path, method, deps=None) returns a response dict, or None when the path is not one of its own.
The master has NO write tools: it reads, plans and routes. Changes happen only inside a class tutor (chat_api/tutor
code, with that code's own validation, budget and undo), reached by handoff in the same request.
`deps` (tests): {"backend", "table", "converse", "converse_fast", "now_local", "env"}.
"""
import json
import re
import time
from datetime import datetime, timedelta, timezone

from lib import briefing, guard, history, limits, materials, redact, routing, tools_impl, tutor, util

_ID_RE = re.compile(r"^[a-z0-9]{8}$")
_AGENT_RE = re.compile(r"^(master|[a-z0-9]{8})$")
VIEW_PREFIXES = ("COURSE", "ASG", "ACT", "BRIEF", "PROFILE", "PLAN", "MAT")   # code-only view: never given to a model
ACT_TTL = 30 * 24 * 3600
BRIEF_TTL = 14 * 24 * 3600
OWN_PATHS = {("GET", "/briefing/today"), ("POST", "/briefing/regenerate"), ("POST", "/chat/master"),
             ("GET", "/agents"), ("GET", "/activity")}
TURN_DEADLINE_SECONDS = 20.0



class _Bad(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ── dependencies and context ──────────────────────────────────────────────────

def _default_deps() -> dict:
    from lib import bedrock, db  # late import: tests need no AWS libraries

    def main(system, messages, tools, force_tool, max_tokens):
        return bedrock.converse(bedrock.MODEL_MAIN, system, messages, tools=tools, force_tool=force_tool, max_tokens=max_tokens)

    def fast(system, messages, tools, force_tool, max_tokens):
        return bedrock.converse(bedrock.MODEL_FAST, system, messages, tools=tools, force_tool=force_tool, max_tokens=max_tokens)

    return {"backend": db, "table": None, "converse": main, "converse_fast": fast, "now_local": None, "env": None}


class _Ctx:
    def __init__(self, sub: str, deps: dict):
        self.sub, self.deps, self.backend = sub, deps, deps["backend"]
        self.view = guard.UserScopedDB(sub, self.backend, allowed_prefixes=VIEW_PREFIXES)
        self.table = deps.get("table") or (self.backend.table() if hasattr(self.backend, "table") else None)
        self.env = deps.get("env")
        self.profile = self.view.get("PROFILE") or {}
        self._now = deps.get("now_local")

    @property
    def now_local(self) -> datetime:
        if self._now is not None:
            return self._now
        from zoneinfo import ZoneInfo
        tz = "America/Chicago"
        try:
            tenant = self.backend.get_item("TENANTS", f"T#{self.profile.get('tenantId', '')}") or {}
            tz = tenant.get("timezone") or tz
            return datetime.now(ZoneInfo(tz))
        except Exception:  # noqa: BLE001
            return datetime.now(ZoneInfo("America/Chicago"))

    @property
    def today(self):
        return self.now_local.date()

    def ai_env(self) -> dict:
        return {"env": self.env} if self.env is not None else {}


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(ctx: _Ctx, agent_id: str, kind: str, text: str) -> None:
    ctx.view.put(f"ACT#{_iso_now()}#{util.short_id(4)}",
                 {"agentId": agent_id, "kind": kind, "text": guard.clean_text(text, 300).replace("\n", " "),
                  "ttl": int(time.time()) + ACT_TTL})


def _json_body(event: dict) -> dict:
    limits.check_body_size(event)
    try:
        data = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        raise _Bad(400, "bad_request", "Invalid JSON")
    if not isinstance(data, dict):
        raise _Bad(400, "bad_request", "Body must be a JSON object")
    return data


# ── entry point ───────────────────────────────────────────────────────────────

def handle(event: dict, sub: str, path: str, method: str, deps: dict | None = None):
    method = (method or "").upper()
    if (method, path) not in OWN_PATHS:
        return None
    try:
        ctx = _Ctx(sub, deps or _default_deps())
        if (method, path) == ("GET", "/briefing/today"):
            return _briefing_today(ctx)
        if (method, path) == ("POST", "/briefing/regenerate"):
            return _briefing_regenerate(ctx)
        if (method, path) == ("POST", "/chat/master"):
            return _chat_master(ctx, event)
        limits.check_user(ctx.table, sub, "default")
        if (method, path) == ("GET", "/agents"):
            return _agents(ctx)
        return _activity(ctx, event)
    except limits.LimitError as e:
        return limits.error_response(e)
    except _Bad as e:
        return util.error(e.status, e.code, e.message)
    except tutor.TutorError as e:
        return util.error(e.status, e.code, e.message)
    except guard.ScopeError:
        return util.error(401, "unauthorized", "Missing or invalid token")
    except Exception as e:  # noqa: BLE001
        print(f"master_api unexpected error: {type(e).__name__}")
        return util.error(500, "internal_error", "An internal error occurred")


# ── briefing ──────────────────────────────────────────────────────────────────

def _active_courses(ctx: _Ctx) -> list:
    return [c for c in ctx.view.query("COURSE#") if not c.get("archived")]


def _facts(ctx: _Ctx) -> dict:
    prefs = ctx.profile.get("prefs") or {}
    return briefing.build_facts(_active_courses(ctx), ctx.view.query("ASG#"), prefs,
                                ctx.profile.get("displayName", ""), ctx.today, ctx.now_local)


def _body(date_s: str, generated: str, source: str, b: dict) -> dict:
    return {"date": date_s, "generatedAt": generated, "source": source, "briefing": b}


def _store(ctx: _Ctx, b: dict, generated: str) -> None:
    ctx.view.put(f"BRIEF#{ctx.today.isoformat()}", {"date": ctx.today.isoformat(), "generatedAt": generated,
                                                    "source": "model", "briefing": b, "ttl": int(time.time()) + BRIEF_TTL})
    _log(ctx, "master", "briefing", "Your morning briefing is ready")


def _briefing_today(ctx: _Ctx) -> dict:
    today = ctx.today.isoformat()
    item = ctx.view.get(f"BRIEF#{today}")
    if item and isinstance(item.get("briefing"), dict):
        return util.ok(_body(today, item.get("generatedAt", ""), item.get("source", "model"), item["briefing"]))
    facts = _facts(ctx)
    try:
        limits.require_ai_enabled(**ctx.ai_env())
        limits.check_user(ctx.table, ctx.sub, "briefing")
        b, source = briefing.make(facts, ctx.deps["converse"])
        generated = _iso_now()
        _store(ctx, b, generated)
    except Exception as e:  # noqa: BLE001  (limits, kill switch, model trouble: always answer with the computed one)
        if not isinstance(e, (limits.LimitError, briefing.BriefingModelError)):
            print(f"briefing model call failed: {type(e).__name__}")
        b, source = briefing.make_computed(facts)
        generated = _iso_now()
    return util.ok(_body(today, generated, source, b))


def _briefing_regenerate(ctx: _Ctx) -> dict:
    limits.require_ai_enabled(**ctx.ai_env())
    limits.check_body_size({"body": ""})
    limits.check_user(ctx.table, ctx.sub, "briefing")
    facts = _facts(ctx)
    try:
        b, _ = briefing.make(facts, ctx.deps["converse"])
    except Exception as e:  # noqa: BLE001
        print(f"briefing regenerate failed: {type(e).__name__}")
        return util.error(503, "master_busy", "The assistant is busy. Try again in a few seconds.")
    generated = _iso_now()
    _store(ctx, b, generated)
    return util.ok(_body(ctx.today.isoformat(), generated, "model", b))


def generate_briefing_for_user(sub: str, deps: dict | None = None) -> bool:
    """For daily_run: store a model briefing for today. Never raises; False when skipped."""
    try:
        ctx = _Ctx(sub, deps or _default_deps())
        limits.require_ai_enabled(**ctx.ai_env())
        b, _ = briefing.make(_facts(ctx), ctx.deps["converse"])
        _store(ctx, b, _iso_now())
        return True
    except Exception as e:  # noqa: BLE001
        print(f"daily briefing skipped: {type(e).__name__}")
        return False


# ── master chat ───────────────────────────────────────────────────────────────

MASTER_SYSTEM = (
    "You are Semester OS's Chief of Staff for one college student. Help them plan their week, prioritise deadlines and "
    "decide what to do next, using only the data blocks below. You cannot change anything yourself: if the student wants a "
    "deadline changed or help learning a class's material, tell them to open that class's tutor. Be warm, brief and concrete. "
    "Plain text with light markdown only: no HTML, no images, no links you were not given.\n"
)


def _master_answer(ctx: _Ctx, courses: list, messages: list, deadline: float) -> str:
    nonce = guard.new_nonce()
    today = ctx.today
    live = [c for c in courses if c.get("status") == "READY"]
    labels = {c["id"]: routing.course_label(c) for c in live}
    soon = [{**a, "course": labels.get(a["courseId"], "")} for a in briefing.due_soon(ctx.view.query("ASG#"), today)]
    cls = [{"course": labels[r["courseId"]], "time": r["time"], "location": r["location"]} for r in briefing.classes_today(live, today)]
    blocks = [
        guard.wrap_untrusted("classes", json.dumps([{"course": routing.course_label(c), "title": guard.clean_text(c.get("title", ""), 80)} for c in live]), nonce),
        guard.wrap_untrusted("classes_today", json.dumps(cls), nonce),
        guard.wrap_untrusted("deadlines", json.dumps(soon), nonce),
    ]
    system = (MASTER_SYSTEM + f"Today is {today.isoformat()} ({briefing.DAY_ABBR[today.weekday()]}).\n"
              + guard.data_rules(nonce) + "\n" + "\n".join(blocks))
    first = tutor.user_text(messages[:-1], messages[-1]["content"], nonce)
    if time.monotonic() > deadline:
        raise TimeoutError("deadline")
    resp = ctx.deps["converse"](system, [{"role": "user", "content": [{"text": first}]}], None, None, limits.max_output_tokens("chat"))
    text = " ".join(b["text"] for b in (resp.get("output", {}).get("message", {}) or {}).get("content", []) or []
                    if isinstance(b, dict) and isinstance(b.get("text"), str)).strip()
    return guard.sanitize_model_output(text) or tutor.FALLBACK_REPLY


_HELP_RE = re.compile(
    r"\b(help|question|explain|understand|assignment|exam|quiz|study|stuck|how|what|tell me|show me|about|review|learn|need)\b",
    re.IGNORECASE)


def _looks_like_class_request(msg: str) -> bool:
    return bool(_HELP_RE.search(msg))


def _reply_suggests_course(reply: str, courses: list) -> dict | None:
    """Return the ONE active course whose code the master reply mentions (case-insensitive), or None."""
    matched = []
    for c in courses:
        code = (c.get("courseCode") or "").strip()
        if code and re.search(r"\b" + re.escape(code) + r"\b", reply, re.IGNORECASE):
            matched.append(c)
    return matched[0] if len(matched) == 1 else None


def _chat_master(ctx: _Ctx, event: dict) -> dict:
    resp = _chat_master_turn(ctx, event)
    if resp.get("statusCode") == 200:   # persistent history (HISTORY_API.md); never fails the turn
        try:
            out = json.loads(resp["body"])
            body = json.loads(event.get("body") or "{}")
            mode = body.get("mode") if body.get("mode") in tutor.MODES else "explain"
            text = history.turn_user_text(body.get("messages") or [], mode)
            history.safe_append(ctx.backend, ctx.sub, "master", text, out, mode)
            if out.get("agent") == "class" and out.get("courseId"):    # the class chat tab shows handed-off turns too
                history.safe_append(ctx.backend, ctx.sub, out["courseId"], text, out, mode)
        except Exception as e:  # noqa: BLE001
            print(f"master history skipped: {type(e).__name__}")
    return resp


def _chat_master_turn(ctx: _Ctx, event: dict) -> dict:
    body = _json_body(event)
    try:
        messages = limits.cap_messages(body.get("messages"))
    except limits.InputTooLarge:
        raise
    except limits.LimitError as e:
        raise _Bad(400, "validation_error", e.message)
    mode = body.get("mode", "explain")
    if mode not in tutor.MODES:
        raise _Bad(400, "validation_error", f"mode must be one of {', '.join(tutor.MODES)}")
    target = body.get("target")
    if target is not None and (not isinstance(target, str) or not (target == "master" or _ID_RE.match(target))):
        raise _Bad(400, "validation_error", "target must be 'master' or a class id")

    courses = _active_courses(ctx)
    by_id = {c["id"]: c for c in courses}
    if target not in (None, "master"):
        all_by_id = {c["id"]: c for c in ctx.view.query("COURSE#")}
        if target not in all_by_id:
            raise _Bad(404, "not_found", "Class not found")
        if all_by_id[target].get("archived"):
            raise _Bad(409, "archived", "That class is archived.")
        if all_by_id[target].get("status") != "READY":
            raise _Bad(409, "not_ready", "Your tutor is still being built. Try again in a moment.")

    limits.require_ai_enabled(**ctx.ai_env())
    limits.check_user(ctx.table, ctx.sub, "chat")
    started = time.monotonic()
    out = {"agent": "master", "courseId": None, "reply": "", "actions": [], "handoff": None, "clarify": None}
    latest = messages[-1]["content"]

    decision, route_result = "master", routing.MASTER_ROUTE
    if target == "master":
        decision = "master"
    elif target:
        decision, route_result = "handoff", {"target": target, "confidence": 1.0, "reason": ""}
    else:
        assignments = ctx.view.query("ASG#")
        try:
            route_result = routing.route(latest, messages[:-1], courses, assignments, ctx.view, ctx.deps["converse_fast"], ctx.today,
                                         materials.router_topics(ctx.view.query("MAT#")))
        except Exception as e:  # noqa: BLE001  (router trouble must never block the master)
            print(f"router failed: {type(e).__name__}")
            route_result = dict(routing.MASTER_ROUTE)
        decision = routing.decide(route_result)

    if decision == "clarify":
        q = routing.clarify(by_id[route_result["target"]])
        out.update(reply=q["question"], clarify=q)
        return util.ok(out)

    if decision == "handoff":
        course = by_id[route_result["target"]]
        reason = route_result.get("reason") or routing.default_reason(course)
        tool_view = tools_impl.scoped_view(ctx.sub, ctx.backend)
        remaining = max(8.0, TURN_DEADLINE_SECONDS - (time.monotonic() - started))
        try:
            answer = tutor.respond(course, mode, messages, "", 5 if mode == "quiz" else 10, tool_view,
                                   ctx.deps["converse"], ctx.today, deadline_seconds=remaining)
        except tutor.TutorError:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"handoff tutor call failed: {type(e).__name__}")
            return util.error(503, "master_busy", "The assistant is busy. Try again in a few seconds.")
        label = routing.course_label(course)
        _log(ctx, "master", "handoff", f"Handed off to your {label} tutor: {reason}")
        out.update(answer)
        out.update(agent="class", courseId=course["id"],
                   handoff={"courseId": course["id"], "courseCode": guard.clean_text(course.get("courseCode", ""), 30),
                            "title": guard.clean_text(course.get("title", ""), 80), "reason": reason,
                            "confidence": round(float(route_result["confidence"]), 2),
                            "materials": [{"id": s["materialId"], "title": s["title"]} for s in (answer.get("sources") or [])]})
        if course["id"] == target:      # already in this class's context: suppress the "Switch to" prompt
            out["handoff"] = None
        return util.ok(out)

    try:
        out["reply"] = _master_answer(ctx, courses, messages, started + TURN_DEADLINE_SECONDS)
    except Exception as e:  # noqa: BLE001
        print(f"master answer failed: {type(e).__name__}")
        return util.error(503, "master_busy", "The assistant is busy. Try again in a few seconds.")

    # Safety net: if master reply mentions exactly one course code and message looks like a class request,
    # do a handoff to that course instead of surfacing the "open the tutor" text.
    if _looks_like_class_request(latest):
        suggest = _reply_suggests_course(out["reply"], courses)
        if suggest and suggest["id"] in by_id:
            remaining = max(6.0, TURN_DEADLINE_SECONDS - (time.monotonic() - started))
            try:
                tool_view = tools_impl.scoped_view(ctx.sub, ctx.backend)
                answer = tutor.respond(suggest, mode, messages, "", 5 if mode == "quiz" else 10,
                                       tool_view, ctx.deps["converse"], ctx.today, deadline_seconds=remaining)
            except Exception as e:  # noqa: BLE001
                print(f"safety-net handoff failed: {type(e).__name__}")
            else:
                reason = routing.default_reason(suggest)
                _log(ctx, "master", "handoff", f"Auto-routed to your {routing.course_label(suggest)} tutor: {reason}")
                out.update(answer)
                out.update(agent="class", courseId=suggest["id"],
                           handoff={"courseId": suggest["id"],
                                    "courseCode": guard.clean_text(suggest.get("courseCode", ""), 30),
                                    "title": guard.clean_text(suggest.get("title", ""), 80),
                                    "reason": reason, "confidence": 0.7,
                                    "materials": [{"id": s["materialId"], "title": s["title"]}
                                                  for s in (answer.get("sources") or [])]})

    return util.ok(out)


# ── agent library and activity ────────────────────────────────────────────────

def _activity_rows(ctx: _Ctx) -> list:
    course_colors = {c["id"]: c.get("color") for c in ctx.view.query("COURSE#") if c.get("id")}
    rows = []
    for it in ctx.view.query("ACT#"):
        parts = str(it.get("sk", "")).split("#", 2)
        if len(parts) == 3:
            agent_id = it.get("agentId", "")
            rows.append({"id": f"{parts[1]}#{parts[2]}", "agentId": agent_id, "kind": _plain(it.get("kind"), 40),
                         "text": _plain(it.get("text"), 300), "at": parts[1],
                         "color": course_colors.get(agent_id)})
    rows.sort(key=lambda r: r["id"], reverse=True)
    return rows


def _plain(v, n: int) -> str:
    return redact.redact(guard.clean_text(v if isinstance(v, str) else "", n)).replace("\n", " ")


def _last(rows: list, agent_id: str):
    for r in rows:
        if r["agentId"] == agent_id:
            return {"kind": r["kind"], "text": r["text"], "at": r["at"]}
    return None


def _agents(ctx: _Ctx) -> dict:
    rows = _activity_rows(ctx)
    courses = sorted(ctx.view.query("COURSE#"), key=lambda c: c.get("createdAt", ""))
    brief = ctx.view.get(f"BRIEF#{ctx.today.isoformat()}")
    agents = [{"id": "master", "kind": "master", "name": "Chief of Staff", "role": "Morning briefing, planning and routing",
               "status": "ready", "detail": "Briefing ready for today" if brief else "Your briefing is built when you open Today",
               "color": None, "courseId": None, "pipeline": None, "stats": None, "lastActivity": _last(rows, "master")}]
    for c in courses:
        st = {"READY": "ready", "BUILDING": "building", "ERROR": "error"}.get(c.get("status"), "building")
        knows = c.get("knows") or {}
        agents.append({
            "id": c["id"], "kind": "class", "name": _plain(c.get("courseCode"), 30) or "New class",
            "role": "Class tutor and deadline keeper", "status": st,
            "detail": {"ready": "Ready to tutor", "building": "Building from your syllabus", "error": _plain(c.get("error"), 120) or "Something went wrong"}[st],
            "title": c.get("title"), "color": c.get("color"), "courseId": c["id"],
            "pipeline": c.get("pipeline") if st in ("building", "error") else None,
            "stats": {"assignments": int(knows.get("assignmentsCount", 0) or 0), "materials": int(knows.get("materialsCount", 0) or 0),
                      "newItems": int(knows.get("newItemsCount", 0) or 0)},
            "lastActivity": _last(rows, c["id"])})
    return util.ok({"agents": agents})


def _activity(ctx: _Ctx, event: dict) -> dict:
    qs = event.get("queryStringParameters") or {}
    raw_limit, agent = qs.get("limit"), qs.get("agentId")
    limit = 30
    if raw_limit is not None:
        if not (isinstance(raw_limit, str) and raw_limit.isdigit() and 1 <= int(raw_limit) <= 100):
            raise _Bad(400, "validation_error", "limit must be a whole number from 1 to 100")
        limit = int(raw_limit)
    if agent is not None and not (isinstance(agent, str) and _AGENT_RE.match(agent)):
        raise _Bad(400, "validation_error", "agentId is not valid")
    rows = [r for r in _activity_rows(ctx) if agent is None or r["agentId"] == agent]
    return util.ok({"activity": rows[:limit]})
