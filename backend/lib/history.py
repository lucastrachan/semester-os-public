"""Persistent chat history per agent (a class id, or "master"). Contract: HISTORY_API.md.

Items: pk USER#{sub}, sk CHAT#{agentId}#{ts} (ts = UTC with microseconds, so sort keys sort like times), with `ttl`
(90 days). CHATMETA#{agentId} keeps an approximate count so the cap is enforced without reading the history each turn.
Everything is read and written through a UserScopedDB limited to CHAT/CHATMETA. Stored text is cleaned data: when it is
ever put into a prompt it must go through prompt_block (untrusted wrapper), never raw.
"""
import re
from datetime import datetime, timedelta, timezone

from . import classdata, guard, limits, util

TTL_SECONDS = 90 * 24 * 3600
CAP = 400                 # stored messages per agent (about 200 turns)
TRIM_SLACK = 20           # trim only when this far over the cap, so most turns do no extra reads
ACTION_UNDO_SECONDS = 7 * 24 * 3600
DEFAULT_LIMIT, MAX_LIMIT = 30, 100
MAX_ASSISTANT_CHARS = 20_000
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_MODES = ("explain", "quiz", "flashcards", "cram")
PREFIXES = ("CHAT", "CHATMETA")


class HistoryError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _view(sub: str, backend):
    return classdata.view(sub, backend, *PREFIXES)


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _check_agent(agent_id) -> str:
    if not isinstance(agent_id, str) or not classdata.AGENT_ID_RE.match(agent_id):
        raise HistoryError(404, "not_found", "Class not found")
    return agent_id


def _plain(v, n: int) -> str:
    return guard.clean_text(v if isinstance(v, str) else "", n).strip()


def _clean_actions(actions) -> list:
    out = []
    for a in (actions or [])[:10]:
        if not isinstance(a, dict):
            continue
        out.append({"id": _plain(a.get("id"), 24), "kind": _plain(a.get("kind"), 40),
                    "summary": _plain(a.get("summary"), 200), "courseId": _plain(a.get("courseId"), 8),
                    "undoable": bool(a.get("undoable"))})
    return out


def _clean_sources(sources) -> list:
    out = []
    for s in (sources or [])[:10]:
        if isinstance(s, dict) and isinstance(s.get("materialId"), str):
            out.append({"materialId": _plain(s["materialId"], 8), "title": _plain(s.get("title"), 120)})
    return out


def _clean_handoff(h):
    if not isinstance(h, dict):
        return None
    return {"courseId": _plain(h.get("courseId"), 8), "courseCode": _plain(h.get("courseCode"), 30),
            "title": _plain(h.get("title"), 80), "reason": _plain(h.get("reason"), 200)}


# ── write ─────────────────────────────────────────────────────────────────────

def append(backend, sub: str, agent_id: str, user_text: str, out: dict, mode: str, now: datetime | None = None,
           cap: int = CAP, slack: int = TRIM_SLACK) -> None:
    """Store one finished turn: the student's message and the agent's reply. `out` is the response body of the turn
    (reply, actions, quiz, flashcards, handoff, sources). Chat endpoints call safe_append instead."""
    agent_id = _check_agent(agent_id)
    view = _view(sub, backend)
    now = now or datetime.now(timezone.utc)
    mode = mode if mode in _MODES else "explain"
    ttl = int(now.timestamp()) + TTL_SECONDS
    user_ts, bot_ts = fmt_ts(now), fmt_ts(now + timedelta(microseconds=1))
    base = {"agentId": agent_id, "mode": mode, "ttl": ttl}
    view.put(f"CHAT#{agent_id}#{user_ts}", {**base, "id": user_ts, "role": "user", "at": user_ts,
                                            "content": _plain(user_text, limits.MAX_CHAT_MESSAGE_CHARS)})
    bot = {**base, "id": bot_ts, "role": "assistant", "at": bot_ts,
           "content": guard.clean_text(out.get("reply") or "", MAX_ASSISTANT_CHARS).strip(),
           "actions": _clean_actions(out.get("actions")), "sources": _clean_sources(out.get("sources")),
           "handoff": _clean_handoff(out.get("handoff"))}
    for key in ("quiz", "flashcards"):
        if isinstance(out.get(key), dict):
            bot[key] = util.to_dynamo(out[key])
    view.put(f"CHAT#{agent_id}#{bot_ts}", bot)
    _bump(view, agent_id, 2, ttl, cap, slack)


def _bump(view, agent_id: str, n: int, ttl: int, cap: int, slack: int) -> None:
    meta = view.get(f"CHATMETA#{agent_id}") or {}
    try:
        count = int(meta.get("count", 0)) + n
    except (TypeError, ValueError):
        count = n
    if count > cap + slack:
        items = sorted(i["sk"] for i in view.query(f"CHAT#{agent_id}#"))
        for sk in items[:max(0, len(items) - cap)]:
            view.delete(sk)
        count = min(len(items), cap)
    view.put(f"CHATMETA#{agent_id}", {"count": count, "ttl": ttl})


def safe_append(*args, **kwargs) -> bool:
    """For the chat endpoints: a history problem must never fail or slow the turn the student already got."""
    try:
        append(*args, **kwargs)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"history append skipped: {type(e).__name__}")
        return False


def turn_user_text(messages: list, mode: str, topic: str = "") -> str:
    """The student's line for this turn. Quiz and flashcards may be asked with no message at all."""
    if messages and isinstance(messages[-1], dict) and messages[-1].get("content"):
        return messages[-1]["content"]
    what = "a quiz" if mode == "quiz" else "flashcards"
    return f"Make me {what}" + (f" on {topic}" if topic else "")


# ── read ──────────────────────────────────────────────────────────────────────

def _present(item: dict, now: datetime) -> dict:
    ts = item.get("id") or item["sk"].split("#", 2)[2]
    try:
        age = (now - _parse_ts(ts)).total_seconds()
    except ValueError:
        age = ACTION_UNDO_SECONDS + 1
    actions = []
    for a in item.get("actions") or []:
        if isinstance(a, dict):
            actions.append({"id": _plain(a.get("id"), 24), "kind": _plain(a.get("kind"), 40),
                            "summary": _plain(a.get("summary"), 200), "courseId": _plain(a.get("courseId"), 8),
                            "undoable": bool(a.get("undoable")) and age <= ACTION_UNDO_SECONDS})
    mode = item.get("mode") if item.get("mode") in _MODES else "explain"
    return {"id": ts, "role": "assistant" if item.get("role") == "assistant" else "user",
            "content": guard.clean_text(item.get("content") or "", MAX_ASSISTANT_CHARS), "mode": mode,
            "actions": actions, "sources": _clean_sources(item.get("sources")),
            "quiz": item.get("quiz") if isinstance(item.get("quiz"), dict) else None,
            "flashcards": item.get("flashcards") if isinstance(item.get("flashcards"), dict) else None,
            "handoff": _clean_handoff(item.get("handoff")), "at": ts}


def parse_params(qs: dict | None) -> tuple:
    """(before or None, limit) from the query string, or HistoryError 400."""
    qs = qs or {}
    before, raw = qs.get("before"), qs.get("limit")
    if before is not None and not (isinstance(before, str) and _TS_RE.match(before)):
        raise HistoryError(400, "validation_error", "before must be a message id from an earlier response")
    limit = DEFAULT_LIMIT
    if raw is not None:
        if not (isinstance(raw, str) and raw.isdigit() and 1 <= int(raw) <= MAX_LIMIT):
            raise HistoryError(400, "validation_error", f"limit must be a whole number from 1 to {MAX_LIMIT}")
        limit = int(raw)
    return before, limit


def page(backend, sub: str, agent_id: str, before: str | None = None, limit: int = DEFAULT_LIMIT,
         now: datetime | None = None) -> dict:
    """Newest `limit` messages older than `before`, oldest first, plus the cursor for the next older page."""
    agent_id = _check_agent(agent_id)
    now = now or datetime.now(timezone.utc)
    rows = [i for i in _view(sub, backend).query(f"CHAT#{agent_id}#")
            if isinstance(i.get("sk"), str) and _TS_RE.match(i["sk"].split("#", 2)[-1])]
    rows.sort(key=lambda i: i["sk"])
    if before:
        rows = [i for i in rows if i["sk"].split("#", 2)[2] < before]
    older = len(rows) > limit
    chunk = rows[-limit:] if rows else []
    next_before = chunk[0]["sk"].split("#", 2)[2] if (older and chunk) else None
    return {"messages": [_present(i, now) for i in chunk], "nextBefore": next_before}


def prompt_block(backend, sub: str, agent_id: str, nonce: str, n: int = 10) -> str:
    """The last n stored messages as ONE untrusted block (for features that feed stored history to a model)."""
    msgs = page(backend, sub, agent_id, limit=n)["messages"]
    text = "\n".join(("Student: " if m["role"] == "user" else "Tutor: ") + m["content"] for m in msgs)
    return guard.wrap_untrusted("stored_history", text or "(none)", nonce)
