"""Morning briefing (handoff 7.4). Everything that can be computed is computed HERE, in code:
which classes meet today, what is due, conflicts, free study slots, ids. The model only writes short text
(greeting, per-class prep lines, per-deadline hints, priorities), and that text is validated against the
code's facts: ids the model invents are dropped, every string is sanitised and capped.

Pure functions plus injected `converse`; no AWS imports, so it is testable offline.
"""
import json
import re
from datetime import date, datetime, timedelta

from . import guard, limits

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
BIG_TYPES = ("exam", "project", "paper", "quiz")
MAX_WARNINGS = 8
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class BriefingModelError(Exception):
    """The model did not produce usable text (the caller falls back to the computed briefing)."""


# ── small helpers ─────────────────────────────────────────────────────────────

def _min(hhmm) -> int | None:
    m = _HHMM.match(hhmm) if isinstance(hhmm, str) else None
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _d(s) -> date | None:
    try:
        return date.fromisoformat(s) if isinstance(s, str) else None
    except ValueError:
        return None


def _txt(v, limit: int) -> str:
    return guard.clean_text(v if isinstance(v, str) else "", limit).replace("\n", " ").strip()[:limit]


def _label(course: dict) -> str:
    return _txt(course.get("courseCode") or course.get("title") or "a class", 30) or "a class"


def _nice(d: date) -> str:
    return f"{DAY_ABBR[d.weekday()]} {d.strftime('%b')} {d.day}"


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


# ── deterministic parts ───────────────────────────────────────────────────────

def meetings_on(course: dict, d: date) -> list:
    """[(start_min, end_min, location)] for this course on that date."""
    out = []
    for m in course.get("meetings") or []:
        if not isinstance(m, dict) or DAY_ABBR[d.weekday()] not in (m.get("days") or []):
            continue
        s, e = _min(m.get("start")), _min(m.get("end"))
        if s is not None and e is not None and s < e:
            out.append((s, e, _txt(m.get("location"), 120)))
    return out


def classes_today(courses: list, today: date) -> list:
    rows = []
    for c in courses:
        for s, e, loc in meetings_on(c, today):
            rows.append({"courseId": c["id"], "time": f"{_hhmm(s)}-{_hhmm(e)}", "location": loc, "_start": s})
    rows.sort(key=lambda r: r["_start"])
    for r in rows:
        del r["_start"]
    return rows


def study_blocks(asgs: list) -> list:
    out = []
    for a in asgs:
        if a.get("type") == "study" and _d(a.get("dueDate")) and _min(a.get("dueTime")) is not None:
            end = _min(a.get("endTime"))
            start = _min(a["dueTime"])
            if end is not None and end > start:
                out.append({"courseId": a.get("courseId"), "date": a["dueDate"], "start": start, "end": end})
    return out


def due_soon(asgs: list, today: date) -> list:
    lo, hi = today - timedelta(days=3), today + timedelta(days=7)
    rows = []
    for a in asgs:
        d = _d(a.get("dueDate"))
        if a.get("done") or a.get("type") == "study" or not d or not lo <= d <= hi:
            continue
        rows.append({"assignmentId": a.get("id"), "title": _txt(a.get("title"), 160), "courseId": a.get("courseId"),
                     "dueDate": d.isoformat(), "_t": a.get("dueTime") or "99:99"})
    rows.sort(key=lambda r: (r["dueDate"], r["_t"]))
    for r in rows:
        del r["_t"]
    return rows[:10]


def warnings(courses: list, asgs: list, today: date) -> list:
    by_id = {c["id"]: c for c in courses}
    out = []
    live = [a for a in asgs if not a.get("done") and a.get("type") != "study"]

    # 1. several deadlines on one day
    days: dict = {}
    for a in live:
        d = _d(a.get("dueDate"))
        if d and today <= d <= today + timedelta(days=14):
            days.setdefault(d, []).append(_txt(a.get("title"), 40))
    for d in sorted(days):
        if len(days[d]) >= 3:
            out.append(f"{len(days[d])} deadlines on {_nice(d)}: {', '.join(days[d][:4])}")

    # 2. overlapping class meetings
    seen = set()
    for i, c1 in enumerate(courses):
        for c2 in courses[i + 1:]:
            for m1 in c1.get("meetings") or []:
                for m2 in c2.get("meetings") or []:
                    if not (isinstance(m1, dict) and isinstance(m2, dict)):
                        continue
                    shared = set(m1.get("days") or []) & set(m2.get("days") or [])
                    s1, e1, s2, e2 = _min(m1.get("start")), _min(m1.get("end")), _min(m2.get("start")), _min(m2.get("end"))
                    if shared and None not in (s1, e1, s2, e2) and _overlap(s1, e1, s2, e2) and (c1["id"], c2["id"]) not in seen:
                        seen.add((c1["id"], c2["id"]))
                        out.append(f"{_label(c1)} and {_label(c2)} overlap on {', '.join(sorted(shared, key=DAY_ABBR.index))}")

    # 3. study blocks that overlap each other or a class
    blocks = [b for b in study_blocks(asgs) if _d(b["date"]) and today <= _d(b["date"]) <= today + timedelta(days=14)]
    flagged = 0
    for i, b in enumerate(blocks):
        d = _d(b["date"])
        clash = any(b2 is not b and b2["date"] == b["date"] and _overlap(b["start"], b["end"], b2["start"], b2["end"])
                    for b2 in blocks[i + 1:])
        clash = clash or any(_overlap(b["start"], b["end"], s, e) for c in courses for s, e, _ in meetings_on(c, d))
        if clash and flagged < 2:
            flagged += 1
            out.append(f"A study block on {_nice(d)} at {_hhmm(b['start'])} overlaps another commitment")

    # 4. big deadlines with no study time scheduled
    missing = 0
    for a in sorted(live, key=lambda x: x.get("dueDate") or ""):
        d = _d(a.get("dueDate"))
        if a.get("type") in BIG_TYPES and d and today <= d <= today + timedelta(days=7) and missing < 3:
            has = any(b["courseId"] == a.get("courseId") and today <= _d(b["date"]) <= d for b in study_blocks(asgs))
            if not has:
                missing += 1
                out.append(f"No study time scheduled for {_txt(a.get('title'), 50)} (due {d.isoformat()})")

    # 5. overdue and undated
    overdue = [a for a in live if _d(a.get("dueDate")) and today - timedelta(days=30) <= _d(a["dueDate"]) < today]
    if overdue:
        out.append(f"{len(overdue)} overdue item{'s' if len(overdue) != 1 else ''}: "
                   + ", ".join(_txt(a.get("title"), 40) for a in overdue[:3]))
    undated = [a for a in live if not a.get("dueDate")]
    if undated:
        out.append(f"{len(undated)} item{'s' if len(undated) != 1 else ''} have no date yet")
    return out[:MAX_WARNINGS]


def suggest_blocks(courses: list, asgs: list, prefs: dict, today: date, now_minutes: int) -> list:
    """Up to 3 free slots (one per day) for the most urgent big deadline in the next 7 days."""
    wake = max(0, min(int(prefs.get("wakeHour", 7)), 23)) * 60
    sleep = max(1, min(int(prefs.get("sleepHour", 23)), 24)) * 60
    length = max(20, min(int(prefs.get("studyBlockMinutes", 50)), 180))
    horizon = today + timedelta(days=7)
    live = [a for a in asgs if not a.get("done") and a.get("type") != "study" and _d(a.get("dueDate"))
            and today <= _d(a["dueDate"]) <= horizon]
    if not live:
        return []
    live.sort(key=lambda a: (a.get("type") not in BIG_TYPES, a["dueDate"]))
    target = live[0]
    by_id = {c["id"]: c for c in courses}
    course = by_id.get(target.get("courseId"))
    if not course:
        return []
    existing = study_blocks(asgs)
    due = _d(target["dueDate"])
    out, d = [], today
    while d <= due and len(out) < 3:
        busy = [(s, e) for c in courses for s, e, _ in meetings_on(c, d)]
        busy += [(b["start"], b["end"]) for b in existing if b["date"] == d.isoformat()]
        earliest = max(wake, ((now_minutes + 30 + 29) // 30) * 30) if d == today else wake
        best = None
        for start in range(earliest, sleep - length + 1, 30):
            if any(_overlap(start, start + length, s, e) for s, e in busy):
                continue
            score = 0 if 16 * 60 <= start <= 20 * 60 + 30 else 1
            if best is None or score < best[0]:
                best = (score, start)
        if best:
            out.append({"courseId": course["id"], "start": f"{d.isoformat()}T{_hhmm(best[1])}",
                        "end": f"{d.isoformat()}T{_hhmm(best[1] + length)}",
                        "focus": f"Prepare for {_txt(target.get('title'), 60)}"})
        d += timedelta(days=1)
    return out


# ── facts, model text, assembly ───────────────────────────────────────────────

def build_facts(courses: list, asgs: list, prefs: dict, display_name: str, today: date, now_local: datetime) -> dict:
    by_id = {c["id"]: c for c in courses}
    live = [c for c in courses if c.get("status") == "READY"]
    classes = classes_today(live, today)
    soon = due_soon(asgs, today)
    name = _txt(display_name, 24)
    if "@" in name or not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{0,23}", name or ""):
        name = ""
    return {
        "today": today.isoformat(), "weekday": DAY_ABBR[today.weekday()], "hour": now_local.hour, "name": name,
        "classes": classes, "dueSoon": soon, "warnings": warnings(live, asgs, today),
        "blocks": suggest_blocks(live, asgs, prefs, today, now_local.hour * 60 + now_local.minute),
        "labels": {c["id"]: _label(c) for c in live},
    }


def _daypart(hour: int) -> str:
    return "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"


def computed_text(facts: dict) -> dict:
    n, m = len(facts["classes"]), len(facts["dueSoon"])
    name = f", {facts['name']}" if facts["name"] else ""
    greeting = (f"Good {_daypart(facts['hour'])}{name}. "
                f"{n} class{'es' if n != 1 else ''} today and {m} deadline{'s' if m != 1 else ''} in the next week.")
    prios = [f"{a['title']} (due {a['dueDate']})" for a in facts["dueSoon"][:3]]
    return {"greeting": greeting, "prep": {}, "hints": {}, "priorities": prios}


SYSTEM = (
    "You write a short morning briefing for a college student from the facts in the data block. "
    "Use ONLY those facts. Never invent classes, assignments, ids, dates or times. Keep every line short and "
    "concrete. Plain text, no HTML, no images, no links.\n"
    "Call write_briefing with: greeting (one or two friendly sentences using the student's first name only if given), "
    "prep (for each class today, up to 3 things to bring, read or finish, keyed by courseId), hints (one short tip per "
    "due item, keyed by assignmentId), priorities (up to 5, most important first).\n"
)
WRITE_TOOL = {"toolSpec": {"name": "write_briefing", "description": "Return the briefing text.", "inputSchema": {"json": {
    "type": "object", "properties": {
        "greeting": {"type": "string"},
        "prep": {"type": "array", "items": {"type": "object", "properties": {
            "courseId": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}}}},
        "hints": {"type": "array", "items": {"type": "object", "properties": {
            "assignmentId": {"type": "string"}, "hint": {"type": "string"}}}},
        "priorities": {"type": "array", "items": {"type": "string"}}},
    "required": ["greeting", "priorities"]}}}}


def _parse_json(text: str):
    text = re.sub(r"```(?:json)?", "", text or "")
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _blocks(resp: dict) -> list:
    return (resp.get("output", {}).get("message", {}) or {}).get("content", []) or []


def ask_model(facts: dict, converse) -> dict | None:
    nonce = guard.new_nonce()
    public = {k: facts[k] for k in ("today", "weekday", "name", "classes", "dueSoon", "warnings")}
    public["classes"] = [{**c, "course": facts["labels"].get(c["courseId"], "")} for c in facts["classes"]]
    public["dueSoon"] = [{**a, "course": facts["labels"].get(a["courseId"], "")} for a in facts["dueSoon"]]
    system = SYSTEM + guard.data_rules(nonce) + "\n" + guard.wrap_untrusted("facts", json.dumps(public), nonce)
    ask = "Write today's briefing."
    max_tokens = limits.max_output_tokens("briefing")
    for tools, force, text in [([WRITE_TOOL], "write_briefing", ask),
                               (None, None, ask + " Reply with ONE JSON object only (keys greeting, prep, hints, priorities).")]:
        try:
            resp = converse(system, [{"role": "user", "content": [{"text": text}]}], tools, force, max_tokens)
        except Exception as e:  # noqa: BLE001
            if (getattr(e, "response", None) or {}).get("Error", {}).get("Code") == "ValidationException":
                continue
            raise
        for b in _blocks(resp):
            if isinstance(b, dict) and isinstance(b.get("toolUse"), dict):
                data = b["toolUse"].get("input")
                data = _parse_json(data) if isinstance(data, str) else data
                if isinstance(data, dict):
                    return data
        data = _parse_json(" ".join(b.get("text", "") for b in _blocks(resp) if isinstance(b, dict)))
        if data:
            return data
    return None


def validate_text(data, facts: dict) -> dict:
    """Keep only text that attaches to ids the CODE produced. Everything else is dropped."""
    def s(v, n):
        return guard.sanitize_model_output(v if isinstance(v, str) else "", max_len=n).replace("\n", " ").strip()[:n]

    if not isinstance(data, dict):
        raise BriefingModelError("no data")
    class_ids = {c["courseId"] for c in facts["classes"]}
    asg_ids = {a["assignmentId"] for a in facts["dueSoon"]}
    greeting = s(data.get("greeting"), 240)
    if not greeting:
        raise BriefingModelError("no greeting")
    prep = {}
    for p in data.get("prep") if isinstance(data.get("prep"), list) else []:
        if isinstance(p, dict) and p.get("courseId") in class_ids and isinstance(p.get("items"), list):
            items = [x for x in (s(i, 120) for i in p["items"][:3]) if x]
            if items:
                prep[p["courseId"]] = items
    hints = {}
    for h in data.get("hints") if isinstance(data.get("hints"), list) else []:
        if isinstance(h, dict) and h.get("assignmentId") in asg_ids and s(h.get("hint"), 140):
            hints[h["assignmentId"]] = s(h["hint"], 140)
    prios = [x for x in (s(p, 140) for p in (data.get("priorities") if isinstance(data.get("priorities"), list) else [])[:5]) if x]
    return {"greeting": greeting, "prep": prep, "hints": hints, "priorities": prios}


def assemble(facts: dict, text: dict) -> dict:
    """The exact 7.4 shape."""
    return {
        "greeting": text["greeting"],
        "classesToday": [{**c, "prep": text["prep"].get(c["courseId"], [])} for c in facts["classes"]],
        "dueSoon": [{**a, "hint": text["hints"].get(a["assignmentId"], "")} for a in facts["dueSoon"]],
        "priorities": text["priorities"] or computed_text(facts)["priorities"],
        "warnings": facts["warnings"],
        "suggestedStudyBlocks": facts["blocks"],
    }


def make(facts: dict, converse) -> tuple:
    """(briefing, source). Raises BriefingModelError / model exceptions when the model path fails."""
    text = validate_text(ask_model(facts, converse), facts)
    return assemble(facts, text), "model"


def make_computed(facts: dict) -> tuple:
    return assemble(facts, computed_text(facts)), "computed"
