"""Phase 3: RFC 5545 iCalendar generator for the outbound feed (no third-party dependencies).

Rules that matter:
  * EVERY user- or model-derived text value goes through guard.ical_text (control/bidi characters removed,
    newlines flattened, backslash/semicolon/comma escaped), so a title can never add a property or an alarm.
  * Lines are folded at 75 octets (never inside a UTF-8 character) and end in CRLF.
  * UIDs are stable ({id}@semesteros); DTSTAMP and SEQUENCE come from the item, so unchanged items do not
    look changed to the subscribing calendar.
  * Local times are converted to UTC with zoneinfo using the campus timezone (DST-correct).
"""
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import guard

UTC = timezone.utc
CAL_NAME = "Semester OS"
PRODID = "-//Semester OS//Calendar Feed//EN"
DUE_EVENT_MINUTES = 30
DEFAULT_TZ = "America/New_York"
_UID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


# ── Low level ─────────────────────────────────────────────────────────────────

def fold(line: str) -> str:
    """Fold one content line at 75 octets. Continuation lines start with a single space (and count it)."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur, cur_len, limit = [], [], 0, 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if cur_len + n > limit:
            parts.append("".join(cur))
            cur, cur_len, limit = [], 0, 74  # the leading space takes one octet
        cur.append(ch)
        cur_len += n
    parts.append("".join(cur))
    return "\r\n ".join(parts)


def text(value, max_len: int = 200) -> str:
    """The only way text enters the feed. U+2028/2029 are also flattened: some parsers split lines on them."""
    value = str(value if value is not None else "").replace(" ", " ").replace(" ", " ")
    return guard.ical_text(value, max_len)


def fmt_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def zone(name) -> ZoneInfo:
    try:
        return ZoneInfo(str(name))
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def local_to_utc(d: date, hhmm: str, tz: ZoneInfo) -> datetime:
    m = _TIME_RE.match(hhmm)
    if not m:
        raise ValueError("bad time")
    local = datetime(d.year, d.month, d.day, int(m.group(1)), int(m.group(2)), tzinfo=tz)
    return local.astimezone(UTC)


def parse_stamp(value, fallback: datetime) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)
    except (ValueError, TypeError):
        return fallback


def _seq(value) -> int:
    try:
        return max(0, min(int(value), 100000))
    except (ValueError, TypeError):
        return 0


# ── Event builders ────────────────────────────────────────────────────────────

def _title(course: dict | None, title) -> str:
    code = guard.clean_text((course or {}).get("courseCode") or "", 24).replace("\n", " ").strip()
    t = guard.clean_text(title, 160).replace("\n", " ").strip() or "Untitled"
    return f"[{code}] {t}" if code else t


def assignment_event(asg: dict, course: dict | None, tz_name: str, now: datetime) -> dict | None:
    """Return an event dict for the feed, or None when the item should not appear
    (done, no valid date, or an id that cannot be a safe UID)."""
    uid_id = str(asg.get("id") or "")
    if asg.get("done") or not _UID_RE.match(uid_id):
        return None
    try:
        d = date.fromisoformat(str(asg.get("dueDate") or ""))
    except ValueError:
        return None
    tz = zone(tz_name)
    desc = []
    kind = str(asg.get("type") or "")
    if kind:
        desc.append(f"Type: {kind}")
    if isinstance(asg.get("weight"), (int, float)) and not isinstance(asg.get("weight"), bool):
        desc.append(f"Weight: {asg['weight']:g}% of grade")
    if asg.get("dateSource") == "resolved":
        desc.append("Date estimated from the syllabus. Check it.")
    if asg.get("notes"):
        desc.append(str(asg["notes"]))
    ev = {
        "uid": f"{uid_id}@semesteros",
        "summary": _title(course, asg.get("title")),
        "description": desc,
        "stamp": parse_stamp(asg.get("updatedAt") or asg.get("createdAt"), now),
        "sequence": _seq(asg.get("sequence")),
    }
    due_time = asg.get("dueTime")
    if due_time and _TIME_RE.match(str(due_time)):
        end = local_to_utc(d, str(due_time), tz)
        ev.update(start=end - timedelta(minutes=DUE_EVENT_MINUTES), end=end, all_day=None)
    else:
        ev.update(all_day=d, start=None, end=None)
    return ev


def study_event(item: dict, course: dict | None, tz_name: str, now: datetime) -> dict | None:
    """A study block: {id, courseId, start, end, focus, sequence, updatedAt}, ISO times (no zone = campus zone)."""
    uid_id = str(item.get("id") or "")
    if not _UID_RE.match(uid_id):
        return None
    tz = zone(tz_name)
    try:
        s = datetime.fromisoformat(str(item["start"]).replace("Z", "+00:00"))
        e = datetime.fromisoformat(str(item["end"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None
    s = (s if s.tzinfo else s.replace(tzinfo=tz)).astimezone(UTC)
    e = (e if e.tzinfo else e.replace(tzinfo=tz)).astimezone(UTC)
    if not timedelta(minutes=5) <= e - s <= timedelta(hours=12):
        return None
    focus = guard.clean_text(item.get("focus") or "", 120).replace("\n", " ").strip()
    code = guard.clean_text((course or {}).get("courseCode") or "", 24).replace("\n", " ").strip()
    summary = "Study" + (f": {focus}" if focus else "")
    return {
        "uid": f"{uid_id}@semesteros",
        "summary": f"[{code}] {summary}" if code else summary,
        "description": ["Study block planned by Semester OS"],
        "stamp": parse_stamp(item.get("updatedAt") or item.get("createdAt"), now),
        "sequence": _seq(item.get("sequence")),
        "start": s, "end": e, "all_day": None,
    }


# ── Calendar ──────────────────────────────────────────────────────────────────

def render_event(ev: dict) -> list:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{ev['uid']}",
        f"DTSTAMP:{fmt_utc(ev['stamp'])}",
        f"SEQUENCE:{_seq(ev.get('sequence'))}",
    ]
    if ev.get("all_day"):
        d = ev["all_day"]
        lines += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}", "TRANSP:TRANSPARENT"]
    else:
        lines += [f"DTSTART:{fmt_utc(ev['start'])}", f"DTEND:{fmt_utc(ev['end'])}"]
    lines.append("SUMMARY:" + text(ev["summary"], 200))
    parts = [text(p, 400) for p in ev.get("description") or [] if str(p).strip()]
    if parts:
        lines.append("DESCRIPTION:" + "\\n".join(parts)[:1500])
    lines.append("END:VEVENT")
    return lines


def build_calendar(events: list, name: str = CAL_NAME) -> str:
    """Render events (dicts from the *_event functions) as a complete VCALENDAR string with CRLF endings."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:" + text(name, 80),
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for ev in events:
        lines += render_event(ev)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"
