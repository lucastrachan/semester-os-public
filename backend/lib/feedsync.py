"""Blackboard calendar feed sync (Phase 6, contract: FEED_API.md).

Pipeline for one student: decrypt the stored feed URL -> safe_fetch (size and time capped) -> defensive ICS parse
-> diff against the FEED#{key} cache -> classify each new or changed event to one of the student's classes with
layered matchers -> create or update assignments (never overwriting what the student edited) -> activity entries
and per-class stats. Events we cannot place with confidence stay `unassigned` for the student to resolve in one click.

We have NOT seen a real feed. Nothing here assumes events carry a course code: every layer is optional, the matcher
rules are data (DEFAULT_RULES, overridable from backend/data/feed_rules.json) and low confidence means "ask the student".

Security: all event text is untrusted. It is cleaned with guard.clean_text, HTML is stripped, lengths are capped, it is
only ever stored and returned as plain text, and if it reaches a model (optional tie-breaker, off by default) it goes
through guard.wrap_untrusted. The feed URL is never logged or returned.

Storage under USER#{sub} (all reached through guard.UserScopedDB):
  FEED                config: encrypted URL, masked URL, status, counts (head `FEED` is denied to model views)
  FEED#{key}          kind=event cache (hash, status matched|unassigned|dismissed, snapshot) or kind=rule (learned mapping)
  ASG#{courseId}#{id} assignments with source=feed, feedUid=key, dateSource=feed, feedBase=what the feed last wrote
  ACT#...             activity entries
System index (no user text, no secret): pk FEEDUSER#{shard}, sk U#{sub}, nextSyncAt, failures.
"""
import hashlib
import html
import json
import os
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import agents, guard, limits, safe_fetch, secretbox, util

PURPOSE = "feed-url"
SHARDS = 16
MAX_LINES = 60_000
MAX_LINE_CHARS = 8_000
MAX_PER_COURSE = 400
ACT_TTL = 30 * 24 * 3600

DEFAULT_RULES = {
    "autoThreshold": 0.75,           # best class needs at least this confidence ...
    "margin": 0.15,                  # ... and must lead the runner-up by this much
    "scores": {                      # evidence strength per layer (0 to 1)
        "learned": 0.90, "learnedConflict": 0.50, "stemHistory": 0.80,
        "identifier": 0.98, "codeTitle": 0.95, "codeCategory": 0.95, "codeDescription": 0.80, "codeLocation": 0.70, "codeUid": 0.60,
        "titlePhrase": 0.90, "titleWordsBase": 0.55, "titleWordsSpan": 0.35, "titleSingleWord": 0.60,
        "acronym": 0.55, "instructor": 0.50, "descriptionOnlyFactor": 0.80, "corroborationBonus": 0.10,
        "model": 0.76,
    },
    "autoImportClasses": False, "maxImportPerRun": 12, "maxImportPerStudent": 20,   # create class agents from the feed
    "currentTermOnly": True,         # events carrying only old-term identifiers are ignored
    "window": {"pastDays": 7, "futureDays": 240},    # events outside are ignored (a feed spans many terms)
    "meetingUidPatterns": ["CalendarEntry"],         # UIDs that are class sessions, not deadlines
    "maxOccurrences": 60,                            # RRULE expansion cap per series, inside the window
    "maxEvents": 1000, "maxNewPerSync": 150, "recheckMinutes": 60, "useModel": False, "maxModelCalls": 10,
    "ignoreTitlePatterns": [],       # regexes (case-insensitive) for events that are never deadlines, e.g. "office hours"
    "genericWords": ["quiz", "exam", "test", "midterm", "final", "homework", "assignment", "assignments", "due", "week",
                     "weekly", "chapter", "ch", "module", "unit", "part", "project", "paper", "essay", "reading", "readings",
                     "discussion", "post", "posting", "response", "reflection", "lab", "report", "draft", "submit",
                     "submission", "deadline", "calendar", "course", "class", "event", "blackboard", "ultra", "section",
                     "open", "close", "closes", "opens", "available", "grade", "graded", "group", "individual", "team",
                     "presentation", "review", "case", "study", "exercise", "problem", "set", "worksheet", "journal"],
    "stopWords": ["the", "and", "for", "with", "from", "into", "intro", "introduction", "principles", "fundamentals",
                  "topics", "special", "advanced", "ii", "iii", "you", "your", "our", "its", "are", "that", "this"],
    "typeKeywords": [                # first match wins; matched against whole words of the title
        ["quiz", ["quiz", "quizzes"]],
        ["exam", ["exam", "midterm", "midterms", "test", "final exam"]],
        ["project", ["project", "presentation", "capstone"]],
        ["paper", ["paper", "essay", "memo", "report"]],
        ["reading", ["reading", "readings", "read"]],
        ["homework", ["homework", "assignment", "hw", "problem set", "pset", "worksheet", "lab", "discussion",
                      "reflection", "journal", "post", "case"]],
    ],
}

_rules_cache = {}


def load_rules(path: str | None = None) -> dict:
    """DEFAULT_RULES with an optional JSON override merged on top (one level deep for dicts)."""
    p = Path(path) if path else Path(__file__).resolve().parents[1] / "data" / "feed_rules.json"
    key = str(p)
    if key in _rules_cache:
        return _rules_cache[key]
    rules = json.loads(json.dumps(DEFAULT_RULES))
    try:
        if p.stat().st_size < 200_000:
            over = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(over, dict):
                for k, v in over.items():
                    if k in rules and isinstance(rules[k], dict) and isinstance(v, dict):
                        rules[k].update(v)
                    elif k in rules and type(rules[k]) is type(v):
                        rules[k] = v
    except (OSError, ValueError):
        pass
    _rules_cache[key] = rules
    return rules


class FeedError(Exception):
    """A student-safe failure. `code` starts with feed_ and never contains the URL."""

    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class NotConnected(Exception):
    pass


# ── ICS parsing (hand written, defensive) ─────────────────────────────────────

def unfold(text: str) -> list:
    """RFC 5545 line unfolding on CRLF, LF or CR input. Bounded in lines and line length."""
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n", MAX_LINES + 1)[:MAX_LINES]
    out = []
    for ln in raw:
        if ln[:1] in (" ", "\t") and out:
            if len(out[-1]) < MAX_LINE_CHARS:
                out[-1] += ln[1:]
        else:
            out.append(ln)
    return [ln[:MAX_LINE_CHARS] for ln in out]


def split_prop(line: str):
    """'NAME;P=V;P2="a:b":value' -> (NAME, {P: V}, value). Quotes protect ':' and ';' inside parameters."""
    in_q, i = False, 0
    for i, ch in enumerate(line):
        if ch == '"':
            in_q = not in_q
        elif ch == ":" and not in_q:
            break
    else:
        return None
    head, value = line[:i], line[i + 1:]
    parts, cur, in_q = [], "", False
    for ch in head:
        if ch == '"':
            in_q = not in_q
            cur += ch
        elif ch == ";" and not in_q:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    name = parts[0].strip().upper()
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip().strip('"')
    return name, params, value


_ESC = re.compile(r"\\(.)", re.S)


def unescape(value: str) -> str:
    return _ESC.sub(lambda m: "\n" if m.group(1) in "nN" else m.group(1), value)


_WIN_ZONES = {"central standard time": "America/Chicago", "eastern standard time": "America/New_York",
              "mountain standard time": "America/Denver", "pacific standard time": "America/Los_Angeles", "utc": "UTC"}
_ABBR = {"UTC": 0, "GMT": 0, "EST": -5, "EDT": -4, "CST": -6, "CDT": -5, "MST": -7, "MDT": -6, "PST": -8, "PDT": -7}
_ABBR_RE = re.compile(r"\(\s*(UTC|GMT|EST|EDT|CST|CDT|MST|MDT|PST|PDT)\s*\)")


def _zone(name):
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 (unknown, empty or Windows-style names)
        alt = _WIN_ZONES.get(str(name).strip().lower())
        try:
            return ZoneInfo(alt) if alt else None
        except Exception:  # noqa: BLE001
            return None


def abbr_hint(*texts) -> str | None:
    """A zone abbreviation such as CDT or CST written in the event text, e.g. 'Due date: 11/5/26, 11:59 PM (CDT)'."""
    for t in texts:
        m = _ABBR_RE.search(t or "")
        if m:
            return m.group(1)
    return None


_DUE_TEXT = re.compile(r"Due date:\s*(\d{1,2})/(\d{1,2})/(\d{2,4}),?\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])?\s*(?:\(\s*([A-Z]{2,4})\s*\))?")


def parse_due_text(text: str, local_tz: str):
    """Fallback when DTSTART is missing or unreadable: Blackboard's own wording 'Due date: M/D/YY, h:mm AM (CDT)'."""
    m = _DUE_TEXT.search(text or "")
    if not m:
        return None
    try:
        mo, dd, yy, hh, mi = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))
        yy += 2000 if yy < 100 else 0
        ap = (m.group(6) or "").upper()
        if ap:
            hh = hh % 12 + (12 if ap == "PM" else 0)
        base = datetime(yy, mo, dd, hh, mi)
        zone = _zone(local_tz) or timezone.utc
        off = _ABBR.get(m.group(7) or "")
        src = timezone(timedelta(hours=off)) if off is not None else zone
        dt = base.replace(tzinfo=src).astimezone(zone)
        return {"date": dt.date().isoformat(), "time": dt.strftime("%H:%M"), "allDay": False}
    except (ValueError, OverflowError):
        return None


def parse_when(value: str, params: dict, local_tz: str, hint: str | None = None):
    """Returns {"date": "YYYY-MM-DD", "time": "HH:MM" | None, "allDay": bool} in the campus wall clock, or None."""
    v = (value or "").strip()
    zone = _zone(local_tz) or timezone.utc
    try:
        if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", v):
            d = datetime.strptime(v[:8], "%Y%m%d").date()
            return {"date": d.isoformat(), "time": None, "allDay": True}
        m = re.fullmatch(r"(\d{8})T(\d{2})(\d{2})(\d{2})?(Z?)", v.upper())
        if not m:
            return None
        base = datetime.strptime(m.group(1) + m.group(2) + m.group(3), "%Y%m%d%H%M")
        if m.group(5) == "Z":
            dt = base.replace(tzinfo=timezone.utc).astimezone(zone)
        else:
            src = _zone(params.get("TZID", ""))
            if src is None and hint in _ABBR:       # floating time with a CDT/CST style label in the text
                src = timezone(timedelta(hours=_ABBR[hint]))
            src = src or zone
            dt = base.replace(tzinfo=src).astimezone(zone)
        return {"date": dt.date().isoformat(), "time": dt.strftime("%H:%M"), "allDay": False}
    except (ValueError, OverflowError):
        return None


_TAG_BREAKS = re.compile(r"(?i)<\s*br\s*/?\s*>|<\s*/\s*(p|div|li|tr|h[1-6])\s*>")
_TAG_BLOCKS = re.compile(r"(?is)<\s*(script|style)\b.*?(?:<\s*/\s*\1\s*>|$)")
_TAGS = re.compile(r"<[^<>]{0,2000}>")


def plain(text, max_len: int, one_line: bool = False) -> str:
    """HTML to plain text, invisible characters removed, capped. Safe to store and to render as text."""
    s = guard.clean_text(text, max_len * 4 + 200)
    for _ in range(2):  # twice: entity-encoded tags appear after the first unescape
        s = _TAG_BLOCKS.sub(" ", s)
        s = _TAG_BREAKS.sub("\n", s)
        s = _TAGS.sub(" ", s)
        s = html.unescape(s)
    s = guard.clean_text(s, max_len * 4)
    s = re.sub(r"[ \t\f\v]+", " ", s)
    s = re.sub(r" ?\n ?", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    if one_line:
        s = re.sub(r"\s+", " ", s)
    return s[:max_len].strip()


def classify_type(title: str, rules: dict) -> str:
    words = " " + re.sub(r"[^\w]+", " ", title.lower()) + " "
    for kind, kws in rules["typeKeywords"]:
        if any(f" {k} " in words for k in kws) and kind in guard.ASSIGNMENT_TYPES:
            return kind
    return "other"


def event_key(uid: str) -> str:
    return hashlib.sha256(uid.encode("utf-8", "replace")).hexdigest()[:24]


def _norm_event(props: dict, local_tz: str, rules: dict):
    def first(name):
        return (props.get(name) or [("", {})])[0]
    uid_raw = plain(first("UID")[0], 200, True)
    title = plain(unescape(first("SUMMARY")[0]), 160, True) or "Untitled event"
    desc = plain(unescape(first("DESCRIPTION")[0]), 1000)
    loc = plain(unescape(first("LOCATION")[0]), 120, True)
    cats = []
    for val, _ in props.get("CATEGORIES", [])[:10]:
        for c in re.split(r"(?<!\\),", val):
            c = plain(unescape(c), 60, True)
            if c and c not in cats and len(cats) < 8:
                cats.append(c)
    hint = abbr_hint(title, desc)
    when = parse_when(first("DTSTART")[0], first("DTSTART")[1], local_tz, hint) if props.get("DTSTART") else None
    if when is None:
        when = parse_due_text(title + " " + desc, local_tz)
    status = plain(first("STATUS")[0], 20, True).upper()
    rec_id = first("RECURRENCE-ID")[0]
    seed = uid_raw or ("synth:" + title + "|" + (first("DTSTART")[0] or ""))
    key = event_key(seed + ("|" + rec_id if rec_id else ""))
    ev = {
        "key": key, "uid": seed[:200], "title": title, "description": desc, "location": loc, "categories": cats,
        "dueDate": when["date"] if when else None, "dueTime": when["time"] if when else None,
        "allDay": bool(when and when["allDay"]), "status": status,
        "recurring": bool(props.get("RRULE") or props.get("RDATE")),
        "kind": "meeting" if any(p and p in seed for p in rules.get("meetingUidPatterns") or []) else "deadline",
    }
    if props.get("DTEND") and when and not when["allDay"]:
        end = parse_when(first("DTEND")[0], first("DTEND")[1], local_tz, hint)
        ev["endTime"] = end["time"] if end and end["date"] == when["date"] else None
    ev["type"] = classify_type(title, rules)
    _rehash(ev)
    return ev


def _rehash(ev: dict) -> None:
    ev["hash"] = hashlib.sha256(json.dumps(
        [ev.get(k) for k in ("title", "description", "location", "categories", "dueDate", "dueTime", "allDay", "status")],
        ensure_ascii=False).encode()).hexdigest()[:32]


_WD = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def expand_series(start: date, rrule: str, extra: list, excluded: set, lo: date, hi: date, cap: int = 60) -> list:
    """Dates of a recurring series that fall inside [lo, hi]. Minimal RRULE: DAILY, WEEKLY (with BYDAY), MONTHLY, YEARLY, with
    INTERVAL, COUNT and UNTIL. Hard caps on iterations and on results. RDATE values come in via `extra`, EXDATE via `excluded`."""
    parts = {}
    for seg in (rrule or "").split(";"):
        if "=" in seg:
            k, v = seg.split("=", 1)
            parts[k.strip().upper()] = v.strip().upper()
    freq = parts.get("FREQ", "")
    try:
        interval = max(1, min(52, int(parts.get("INTERVAL", "1"))))
        count = min(1000, int(parts["COUNT"])) if "COUNT" in parts else None
    except ValueError:
        interval, count = 1, None
    until = None
    if parts.get("UNTIL"):
        try:
            until = datetime.strptime(parts["UNTIL"][:8], "%Y%m%d").date()
        except ValueError:
            until = None
    byday = sorted({_WD[d[-2:]] for d in parts.get("BYDAY", "").split(",") if d[-2:] in _WD})
    out, made, k = set(extra), 0, 0
    if lo <= start <= hi:
        out.add(start)          # DTSTART is always an occurrence, even with RDATE only
    if freq in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        while k < 3000:
            cands = []
            if freq == "DAILY":
                cands = [start + timedelta(days=k * interval)]
            elif freq == "WEEKLY":
                wk0 = start - timedelta(days=start.weekday()) + timedelta(weeks=k * interval)
                cands = [wk0 + timedelta(days=wd) for wd in (byday or [start.weekday()])]
            elif freq == "MONTHLY":
                m = start.month - 1 + k * interval
                try:
                    cands = [date(start.year + m // 12, m % 12 + 1, start.day)]
                except ValueError:
                    cands = []
            else:
                try:
                    cands = [date(start.year + k * interval, start.month, start.day)]
                except ValueError:
                    cands = []
            k += 1
            stop = False
            for d in cands:
                if d < start:
                    continue
                if (until and d > until) or (count is not None and made >= count) or d > hi:
                    stop = True
                    break
                made += 1
                if lo <= d <= hi:
                    out.add(d)
            if stop or len(out) > cap * 3:
                break
    return sorted(d for d in out if lo <= d <= hi and d not in excluded)[:cap]


def parse_ics(text: str, local_tz: str, rules: dict | None = None, today: date | None = None) -> list:
    """Parse VEVENTs into normalized dicts. Never raises on malformed input; caps events and field sizes."""
    return parse_ics_ex(text, local_tz, rules, today)[0]


def _series_dates(props: dict, ev: dict, local_tz: str, lo: date, hi: date, rules: dict) -> list:
    def dates_of(name):
        got = set()
        for value, params in props.get(name, [])[:20]:
            for v in str(value).split(",")[:60]:
                w = parse_when(v, params, local_tz)
                if w:
                    got.add(date.fromisoformat(w["date"]))
        return got
    start = date.fromisoformat(ev["dueDate"])
    rr = (props.get("RRULE") or [("", {})])[0][0]
    return expand_series(start, rr, [d for d in dates_of("RDATE") if lo <= d <= hi], dates_of("EXDATE"), lo, hi,
                         rules.get("maxOccurrences", 60))


def parse_ics_ex(text: str, local_tz: str, rules: dict | None = None, today: date | None = None):
    """Like parse_ics but returns (events, skipped): `skipped` counts VEVENTs that could not be read at all.
    Recurring series (RRULE/RDATE) are expanded only inside the date window, at most `maxOccurrences` per series."""
    rules = rules or load_rules()
    today = today or datetime.now(_zone(local_tz) or timezone.utc).date()
    lo = today - timedelta(days=rules["window"]["pastDays"])
    hi = today + timedelta(days=rules["window"]["futureDays"])
    skipped = 0
    events, props, depth, in_event = {}, None, 0, False
    if not isinstance(text, str):
        return [], 0
    for line in unfold(text):
        if not line.strip():
            continue
        parsed = split_prop(line)
        if not parsed:
            continue
        name, params, value = parsed
        if name == "BEGIN":
            v = value.strip().upper()
            if v == "VEVENT" and not in_event:
                in_event, props, depth = True, {}, 0
            elif in_event:
                depth += 1  # VALARM and anything nested: its properties are ignored
            continue
        if name == "END":
            v = value.strip().upper()
            if in_event and depth > 0:
                depth -= 1
            elif v == "VEVENT" and in_event:
                in_event = False
                try:
                    ev = _norm_event(props, local_tz, rules)
                    if ev["recurring"] and ev["dueDate"]:
                        for d in _series_dates(props, ev, local_tz, lo, hi, rules):
                            occ = dict(ev, dueDate=d.isoformat(), key=event_key(ev["uid"] + "|r|" + d.isoformat()))
                            _rehash(occ)
                            events[occ["key"]] = occ
                    else:
                        events[ev["key"]] = ev  # a repeated key keeps the last one
                except Exception:  # noqa: BLE001 (one broken event must not lose the rest)
                    skipped += 1
                if len(events) >= rules["maxEvents"]:
                    break
            continue
        if in_event and depth == 0 and len(props) < 60:
            props.setdefault(name, []).append((value, params))
    return list(events.values()), skipped


# ── Classification ────────────────────────────────────────────────────────────

_WORD = re.compile(r"[^\W\d_]{3,}", re.U)
_CODE = re.compile(r"([A-Za-z]{2,6})\s*[-_.]?\s*(\d{2,4}[A-Za-z]?)")


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").casefold()


_DATEISH = re.compile(r"\b\d{1,2}[/.\-]\d{1,2}(?:[/.\-]\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b")


def title_pattern(title: str) -> str:
    """Normalised shape of a title for grouping: dates, numbers and 'Week 3' style labels removed, so
    '10/19 Reading Journal' and '11/2 Reading Journal' share one pattern ('reading journal')."""
    s = _fold(title)
    s = _DATEISH.sub(" ", s)
    s = re.sub(r"\d+", " ", s)
    s = re.sub(r"[^\w]+", " ", s, flags=re.U)
    s = re.sub(r"\b(?:week|wk|ch|chapter|module|unit|part|no|lesson|session|day|due|by|of|the|a)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:80] or "untitled"


def pattern_is_specific(pat: str, rules: dict) -> bool:
    """A learned pattern rule must not be a single generic word such as 'quiz' (it would claim every quiz)."""
    words = pat.split()
    return bool(words) and pat != "untitled" and (len(words) >= 2 or bool(distinctive(words, rules)))


def tokens(text: str) -> list:
    return _WORD.findall(_fold(text))


def distinctive(toks, rules) -> list:
    skip = set(rules["genericWords"]) | set(rules["stopWords"])
    return [t for t in toks if t not in skip]


def title_stem(title: str, rules: dict) -> str:
    return " ".join(distinctive(tokens(title), rules))


_IDENT = re.compile(r"(?<![0-9A-Za-z])(\d{6})-([A-Za-z]{2,6})-(\d{2,4}[A-Za-z]?)-([A-Za-z0-9]{1,6})(?![0-9A-Za-z])")


def find_identifiers(ev: dict) -> list:
    """UA Blackboard course identifiers '<term 6 digits>-<DEPT>-<NUM>-<section>' (also inside
    '<numeric id>.<term>: <identifier>') found anywhere in an event's text. Returns up to 5 dicts."""
    text = " | ".join([str(ev.get("title") or ""), " | ".join(ev.get("categories") or []), str(ev.get("description") or ""),
                       str(ev.get("location") or ""), str(ev.get("uid") or "")])
    out, seen = [], set()
    for m in _IDENT.finditer(text):
        term, dept, num, sec = m.group(1), m.group(2).upper(), m.group(3).upper(), m.group(4).upper()
        ident = f"{term}-{dept}-{num}-{sec}"
        if ident not in seen and len(out) < 5:
            seen.add(ident)
            out.append({"term": term, "dept": dept, "num": num, "section": sec, "code": f"{dept} {num}", "identifier": ident})
    return out


def _safe_in_window(ev, today, rules) -> bool:
    try:
        return _in_window(ev, today, rules)
    except Exception:  # noqa: BLE001
        return False


def current_terms(events: list, today: date, rules: dict, courses: list | None = None) -> set:
    """The current term code(s): the newest term among identifiers of events inside the date window, plus any `termCode`
    stored on a class. Old-term calendars have old events, so they do not win. Empty set = unknown (nothing is filtered)."""
    terms = set()
    for ev in events:
        try:
            if _safe_in_window(ev, today, rules) and ev.get("dueDate"):
                terms.update(i["term"] for i in find_identifiers(ev))
        except Exception:  # noqa: BLE001
            continue
    out = {max(terms)} if terms else set()
    for c in courses or []:
        if re.fullmatch(r"\d{6}", str(c.get("termCode") or "")):
            out.add(str(c["termCode"]))
    return out


_TITLE_CODE = re.compile(r"(?<![A-Za-z])([A-Z]{2,5})\s?(\d{3,4}[A-Z]?)(?![A-Za-z0-9])")


def suggest_codes(events: list, today: date, rules: dict) -> list:
    """Course codes written in event titles (for example 'EN 210 Lecture'), seen at least twice in the window:
    [{code, eventCount}], most frequent first. Chips for the onboarding page; they create nothing."""
    counts = {}
    for ev in events:
        try:
            if not _safe_in_window(ev, today, rules) or ev.get("status") == "CANCELLED":
                continue
            for m in set(_TITLE_CODE.findall(str(ev.get("title") or ""))):
                counts[f"{m[0]} {m[1]}"] = counts.get(f"{m[0]} {m[1]}", 0) + 1
        except Exception:  # noqa: BLE001
            continue
    return [{"code": c, "eventCount": n} for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if n >= 2][:30]


def suggest_codes_safe(events: list, today: date, rules: dict) -> list:
    try:
        return suggest_codes(events, today, rules)
    except Exception:  # noqa: BLE001
        return []


def detect_classes(events: list, today: date, rules: dict) -> dict:
    """Distinct classes named in the feed for the current term: {term, classes:[{code, section, term, identifier, eventCount}]}."""
    cur = current_terms(events, today, rules)
    found = {}
    for ev in events:
        try:
            if not _safe_in_window(ev, today, rules) or ev.get("status") == "CANCELLED":
                continue
            for i in find_identifiers(ev):
                if i["term"] in cur:
                    row = found.setdefault(i["identifier"], {"code": i["code"], "section": i["section"], "term": i["term"],
                                                             "identifier": i["identifier"], "eventCount": 0})
                    row["eventCount"] += 1
        except Exception:  # noqa: BLE001
            continue
    if not found:   # no identifiers in this feed: fall back to course codes written in titles ("EN 210 ...")
        rows = [{"code": r["code"], "section": "", "term": None, "identifier": None, "eventCount": r["eventCount"]}
                for r in suggest_codes(events, today, rules)]
        return {"term": None, "classes": rows}
    rows = sorted(found.values(), key=lambda r: (r["code"], r["section"]))[:30]
    return {"term": max(cur) if cur else None, "classes": rows}


def detect_classes_safe(events: list, today: date, rules: dict) -> dict:
    """detect_classes that can never raise (onboarding must work even with an odd feed)."""
    try:
        return detect_classes(events, today, rules)
    except Exception:  # noqa: BLE001
        return {"term": None, "classes": []}


def _tomb_sk(identifier: str) -> str:
    return "FEEDSKIP#" + identifier


def write_tombstone(scoped, row: dict, stamp: str) -> None:
    scoped.put(_tomb_sk(row["identifier"]), {"kind": "skip", "code": row.get("code"), "term": row.get("term"),
                                              "identifier": row["identifier"], "createdAt": stamp})


def tombstone_course(sub: str, backend, course: dict, now: float | None = None) -> bool:
    """Hook for courses_api.delete_course (call BEFORE deleting): remembers that the student removed a class that the feed
    created, so the next sync does not recreate it. Returns True when a tombstone was written."""
    if not isinstance(course, dict) or course.get("source") not in ("feed", "blackboard"):
        return False
    ident = course.get("feedIdentifier") or course.get("bbIdentifier")
    if not isinstance(ident, str):
        return False
    write_tombstone(scoped_view(sub, backend), {"identifier": ident, "code": course.get("courseCode"), "term": course.get("termCode")},
                    now_iso(now))
    return True


_QUICK_CODE = re.compile(r"^([A-Za-z]{2,5})\s*[-_.]?\s*(\d{3,4}[A-Za-z]?)$")
MAX_QUICK_PER_CALL = 12
MAX_QUICK_PER_STUDENT = 20


def normalize_code(raw) -> str | None:
    """'mis405', 'MIS-405 ', 'mis  405' -> 'MIS 405'; None when it is not DEPT (2-5 letters) + number (3-4 digits, optional letter)."""
    if not isinstance(raw, str):
        return None
    m = _QUICK_CODE.match(plain(raw, 24, True))
    return f"{m.group(1).upper()} {m.group(2).upper()}" if m else None


def needs_syllabus(course: dict) -> bool:
    """True for a class created from the feed or by code that no syllabus has filled in yet (the UI can nudge an upload)."""
    if not isinstance(course, dict) or course.get("source") not in ("feed", "quick", "blackboard"):
        return False
    pol = course.get("policies") or {}
    return not (course.get("summary") or course.get("grading") or course.get("meetings") or course.get("officeHours")
                or course.get("books") or any(pol.get(k) for k in pol) or course.get("syllabusAt"))


def add_courses_by_code(scoped, sub: str, items: list, courses: list, term: str, t: float) -> tuple:
    """Create READY class agents for [{code, title?, section?}]. Returns (created, skipped, invalid): created rows are
    {id, courseCode, title, color}; skipped are codes the student already has or that exceed the 20-per-student cap."""
    stamp = now_iso(t)
    have = {code_key(c.get("courseCode")) for c in courses if code_key(c.get("courseCode"))}
    mine = sum(1 for c in courses if c.get("source") in ("feed", "quick"))
    created, skipped, invalid = [], [], []
    for it in items:
        code = normalize_code(it.get("code") if isinstance(it, dict) else None)
        if not code:
            invalid.append(plain(str((it or {}).get("code") if isinstance(it, dict) else it), 24, True))
            continue
        if code_key(code) in have or mine >= MAX_QUICK_PER_STUDENT:
            skipped.append(code)
            continue
        title = plain(it.get("title") or "", 120, True) if isinstance(it.get("title"), str) else ""
        sec = plain(it.get("section") or "", 6, True) if isinstance(it.get("section"), str) else ""
        sec = sec if re.fullmatch(r"[A-Za-z0-9]{1,6}", sec or "") else ""
        course = _feed_course(sub, {"code": code, "term": term or "", "section": sec, "identifier": None}, len(courses), stamp)
        course.update(source="quick", title=title or code)
        course.pop("feedIdentifier", None)
        course.pop("termCode", None)
        course["pipeline"][0]["detail"] = "Added by code"
        course["pipeline"][1]["detail"] = "From your Blackboard calendar"
        scoped.put(f"COURSE#{course['id']}", course)
        courses.append({**course, "pk": scoped.pk, "sk": f"COURSE#{course['id']}"})
        have.add(code_key(code))
        mine += 1
        created.append({"id": course["id"], "courseCode": code, "title": course["title"], "color": course["color"]})
    return created, skipped, invalid


# ── Extension import (POST /courses/import) ──────────────────────────────────

MAX_IMPORT_CLASSES = 12
MAX_IMPORT_ASSIGNMENTS = 200
MAX_COURSES_BY_CONNECTORS = 30
_BB_IDENT = re.compile(r"^(\d{6})-([A-Z]{2,6})-(\d{2,4}[A-Z]?)-([A-Z0-9]{1,6})$")
_CANVAS_IDENT = re.compile(r"^canvas:[a-z0-9_\-]{1,60}$", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _bb_when(due_date, due_time, tz_abbr, campus_tz: str):
    """(dueDate, dueTime) in the campus time zone from the page's wall clock and its label (CDT, CST ...). None if invalid."""
    if not isinstance(due_date, str) or not _DATE_RE.match(due_date):
        return None
    try:
        d = date.fromisoformat(due_date)
    except ValueError:
        return None
    if abs((d - datetime.now(timezone.utc).date()).days) > 800:
        return None
    if due_time in (None, ""):
        return d.isoformat(), None
    if not isinstance(due_time, str) or not _TIME_RE.match(due_time):
        return None
    zone = _zone(campus_tz) or timezone.utc
    label = str(tz_abbr or "").strip().upper()
    off = _ABBR.get(label)
    base = datetime(d.year, d.month, d.day, int(due_time[:2]), int(due_time[3:]))
    src = timezone(timedelta(hours=off)) if off is not None else (_zone(str(tz_abbr)) if tz_abbr and _zone(str(tz_abbr)) else zone)
    dt = base.replace(tzinfo=src).astimezone(zone)
    return dt.date().isoformat(), dt.strftime("%H:%M")


def _clean_class(raw: dict):
    """Validated class dict or None. Accepts Blackboard identifiers (YYMMDD-DEPT-NUM-SEC) and Canvas
    identifiers (canvas:<courseId>); non-matching identifiers fall back to code-only matching."""
    ident_raw = str(raw.get("identifier") or "").strip()
    ident = ident_raw.upper()
    m = _BB_IDENT.match(ident)
    canvas = _CANVAS_IDENT.match(ident_raw) if not m else None
    code = normalize_code(raw.get("code")) if raw.get("code") else None
    term = str(raw.get("term") or "").strip()
    sec = plain(raw.get("section") or "", 6, True).upper() if isinstance(raw.get("section"), str) else ""
    if m:
        code = code or f"{m.group(2)} {m.group(3)}"
        term = term if re.fullmatch(r"\d{6}", term) else m.group(1)
        sec = sec if re.fullmatch(r"[A-Z0-9]{1,6}", sec or "") else m.group(4)
    elif canvas:
        ident = ident_raw.lower()   # normalise to lowercase canvas:id
        sec = sec if re.fullmatch(r"[A-Z0-9]{1,6}", sec or "") else ""
        term = term if re.fullmatch(r"\d{6}", term) else ""
    else:
        ident = ""
        sec = sec if re.fullmatch(r"[A-Z0-9]{1,6}", sec or "") else ""
        term = term if re.fullmatch(r"\d{6}", term) else ""
    if not code:
        return None
    title = plain(raw.get("title") or "", 120, True) if isinstance(raw.get("title"), str) else ""
    instr = plain(raw.get("instructor") or "", 80, True) if isinstance(raw.get("instructor"), str) else ""
    return {"identifier": ident or None, "code": code, "term": term, "section": sec, "title": title, "instructor": instr}


def import_blackboard(scoped, sub: str, classes: list, rules: dict, campus_tz: str, t: float, source: str = "blackboard") -> dict:
    """Create or update class agents and upsert their assignments from what the browser extension read on LMS pages.
    Accepts source='blackboard' or source='canvas'. Idempotent by identifier (bbIdentifier on the course; an existing class
    with the same code is adopted), assignments are matched by (title, dueDate), student edits are never overwritten, and
    a manual or stated date wins."""
    stamp = now_iso(t)
    courses = [c for c in scoped.query("COURSE#") if isinstance(c, dict) and not c.get("archived")]
    assignments = [a for a in scoped.query("ASG#") if isinstance(a, dict)]
    created, updated, skipped = [], [], 0
    made = sum(1 for c in courses if c.get("source") in ("feed", "quick", "blackboard", "canvas"))
    for raw in classes:
        info = _clean_class(raw)
        if not info:
            skipped += 1
            continue
        course = next((c for c in courses if info["identifier"] and c.get("bbIdentifier") == info["identifier"]), None) \
            or next((c for c in courses if code_key(c.get("courseCode")) == code_key(info["code"])), None)
        is_new = course is None
        if is_new:
            if made >= MAX_COURSES_BY_CONNECTORS:
                skipped += 1
                continue
            course = _feed_course(sub, {"code": info["code"], "term": info["term"], "section": info["section"], "identifier": info["identifier"]},
                                  len(courses), stamp)
            lms_label = "Canvas" if source == "canvas" else "Blackboard"
            course.update(source=source, title=info["title"] or info["code"], instructor=info["instructor"],
                          bbIdentifier=info["identifier"])
            course.pop("feedIdentifier", None)
            if not info["term"]:
                course.pop("termCode", None)
            course["pipeline"][0]["detail"] = f"Imported from {lms_label}"
            course["pipeline"][1]["detail"] = f"From your {lms_label} calendar"
            scoped.put(f"COURSE#{course['id']}", course)
            courses.append({**course, "pk": scoped.pk, "sk": f"COURSE#{course['id']}"})
            made += 1
            if info["identifier"]:
                try:
                    scoped.delete(_tomb_sk(info["identifier"]))   # an explicit import re-creates a class the student removed
                except Exception:  # noqa: BLE001
                    pass
        else:
            fill = {}
            if not course.get("bbIdentifier") and info["identifier"]:
                fill["bbIdentifier"] = info["identifier"]
            if info["instructor"] and not course.get("instructor"):
                fill["instructor"] = info["instructor"]
            if info["title"] and (not course.get("title") or course.get("title") == course.get("courseCode")):
                fill["title"] = info["title"]
            if info["section"] and not course.get("section"):
                fill["section"] = info["section"]
            if info["term"] and not course.get("term"):
                fill["term"] = info["term"]
            if fill:
                scoped.update(f"COURSE#{course['id']}", fill)
                course.update(fill)
        cid = course["id"]
        added = changed = 0
        incoming = raw.get("assignments") if isinstance(raw.get("assignments"), list) else []
        clean = []
        for a in incoming[:MAX_IMPORT_ASSIGNMENTS]:
            if not isinstance(a, dict):
                continue
            title = plain(a.get("title") or "", 200, True)[:160] if isinstance(a.get("title"), str) else ""
            when = _bb_when(a.get("dueDate"), a.get("dueTime"), a.get("tz"), campus_tz)
            if title and when:
                clean.append((title, when[0], when[1]))
        titles_in = {}
        for title, d, tm in clean:
            titles_in[_norm_title(title)] = titles_in.get(_norm_title(title), 0) + 1
        mine = [a for a in assignments if a.get("courseId") == cid]
        for title, d, tm in clean:
            nt = _norm_title(title)
            same = next((a for a in mine if a.get("bbKey") == f"{nt}|{d}"
                         or (_norm_title(a.get("title", "")) == nt and a.get("dueDate") == d)), None)
            if same:
                if tm and not same.get("dueTime") and same.get("dateSource") not in ("manual",):
                    scoped.update(f"ASG#{cid}#{same['id']}", {"dueTime": tm, "sequence": int(same.get("sequence") or 0) + 1, "updatedAt": stamp})
                    same["dueTime"] = tm
                    changed += 1
                continue
            moved = None
            if titles_in[nt] == 1:   # one incoming and one stored Blackboard item with this title: the instructor moved it
                olds = [a for a in mine if _norm_title(a.get("title", "")) == nt and a.get("source") == "blackboard"]
                if len(olds) == 1 and olds[0].get("dueDate") != d:
                    if olds[0].get("dateSource") in ("manual",):
                        continue   # the student set this date: never fight it, never duplicate it
                    moved = olds[0]
            if moved:
                upd = {"dueDate": d, "dueTime": tm, "dateSource": "stated", "sequence": int(moved.get("sequence") or 0) + 1, "updatedAt": stamp}
                scoped.update(f"ASG#{cid}#{moved['id']}", upd)
                moved.update(upd)
                changed += 1
                continue
            if len(mine) >= MAX_PER_COURSE:
                continue
            aid = hashlib.sha256(f"{sub}|{cid}|{nt}|{d}".encode()).hexdigest()[:8]
            if any(x.get("id") == aid for x in assignments):
                aid = util.short_id()
            item = {"id": aid, "courseId": cid, "title": title, "type": classify_type(title, rules), "dueDate": d, "dueTime": tm,
                    "weight": None, "notes": "", "dueText": "", "dateSource": "stated", "done": False, "source": source,
                    "sequence": 0, "createdAt": stamp, "updatedAt": stamp, "bbKey": f"{nt}|{d}"}
            scoped.put(f"ASG#{cid}#{aid}", item)
            row = {**item, "pk": scoped.pk, "sk": f"ASG#{cid}#{aid}"}
            assignments.append(row)
            mine.append(row)
            added += 1
        knows = dict(course.get("knows") or {})
        knows.update(assignmentsCount=int(knows.get("assignmentsCount") or 0) + added,
                     newItemsCount=int(knows.get("newItemsCount") or 0) + (added if not is_new else 0), lastUpdatedAt=stamp)
        scoped.update(f"COURSE#{cid}", {"knows": knows})
        course["knows"] = knows
        if is_new:
            created.append({"id": cid, "courseCode": course["courseCode"], "title": course["title"], "color": course["color"],
                            "assignmentsAdded": added})
        else:
            updated.append({"id": cid, "courseCode": course["courseCode"], "assignmentsAdded": added, "assignmentsUpdated": changed})
    if created:
        log_activity(scoped, "master", "bb_imported", f"Imported {len(created)} class{'es' if len(created) != 1 else ''} from Blackboard", t)
    return {"created": created, "updated": updated, "skipped": skipped}


def reclassify_unassigned(scoped, sub: str, rules: dict, t: float, limit: int = 300) -> int:
    """Re-run placement for stored Unassigned (and parked) events with the current classes and learned rules. Returns how many
    events were placed. Never fetches; events the feed has not delivered yet are handled by the next sync."""
    courses = [c for c in scoped.query("COURSE#") if isinstance(c, dict)]
    index = CourseIndex(courses, rules)
    by_id = {c["id"]: c for c in courses if isinstance(c.get("id"), str)}
    rows = scoped.query("FEED#")
    learned = [r for r in rows if r.get("kind") == "rule"]
    assignments = [a for a in scoped.query("ASG#") if isinstance(a, dict)]
    stamp, placed, per = now_iso(t), 0, {}
    for row in rows:
        if placed >= limit:
            break
        if row.get("kind") != "event" or row.get("status") != "unassigned":
            continue
        key = row["sk"][5:]
        try:
            ev = _event_from_row(row, key)
            ev["ids"] = find_identifiers(ev)
            res = classify(ev, index, rules, learned)
            cid = res["courseId"]
            if not cid or cid not in by_id:
                continue
            action, item = upsert_assignment(scoped, sub, ev, cid, assignments, stamp)
            if not item:
                continue
            scoped.put(row["sk"], {**_strip(row), "status": "matched", "courseId": cid, "assignmentId": item.get("id"),
                                   "confidence": res["confidence"], "reason": res["reason"], "lastChangedAt": stamp,
                                   "isNew": True, "pendingClass": None})
            placed += 1
            if action == "created":
                per[cid] = per.get(cid, 0) + 1
        except Exception:  # noqa: BLE001 (one odd event never blocks the rest)
            continue
    for cid, n in per.items():
        knows = dict(by_id[cid].get("knows") or {})
        knows.update(newItemsCount=int(knows.get("newItemsCount") or 0) + n, assignmentsCount=int(knows.get("assignmentsCount") or 0) + n)
        scoped.update(f"COURSE#{cid}", {"knows": knows})
    if placed:
        log_activity(scoped, "master", "feed_added", f"Placed {placed} Blackboard item{'s' if placed != 1 else ''} into your new classes", t)
    return placed


def _feed_course(sub: str, row: dict, n_existing: int, stamp: str) -> dict:
    pipeline = agents.new_pipeline()
    for step in pipeline:
        step["state"] = "done"
    pipeline[0]["detail"] = "Imported from Blackboard"
    pipeline[1]["detail"] = "From your Blackboard calendar"
    pipeline[3]["detail"] = "Add the syllabus to find books"
    cid = util.short_id()
    return {"id": cid, "status": "READY", "color": agents.PALETTE[n_existing % len(agents.PALETTE)],
            "createdAt": stamp, "updatedAt": stamp, "pipeline": pipeline,
            "courseCode": row["code"], "title": row["code"], "instructor": "", "term": row["term"], "termCode": row["term"],
            "section": row["section"], "source": "feed", "feedIdentifier": row["identifier"], "officeHours": "", "summary": "",
            "meetings": [], "books": [], "grading": [],
            "policies": {"late": "", "attendance": "", "ai": "", "other": ""},
            "knows": {"materialsCount": 0, "assignmentsCount": 0, "lastUpdatedAt": stamp, "lastFeedCheckAt": None, "newItemsCount": 0}}


def import_classes(scoped, sub: str, cfg: dict, detected: dict, courses: list, rules: dict, t: float) -> list:
    """Create a READY class agent for every current-term class named in the feed that matches no class, skipping classes the
    student deleted (FEEDSKIP tombstones), at most maxImportPerRun per call and maxImportPerStudent in total.
    Returns [{code, section, term, identifier, courseId}]. `courses` is extended in place."""
    if not rules.get("autoImportClasses", False):
        return []
    stamp = now_iso(t)
    existing_ids = {c.get("id") for c in courses}
    imported_ids = dict(cfg.get("importedIds") or {})
    changed = False
    for ident, cid in list(imported_ids.items()):          # a class we made that is gone: the student deleted it
        if cid not in existing_ids:
            bits = ident.split("-")
            write_tombstone(scoped, {"identifier": ident, "code": " ".join(bits[1:3]) if len(bits) >= 4 else None, "term": bits[0]}, stamp)
            imported_ids.pop(ident)
            changed = True
    tombs = [r for r in scoped.query("FEEDSKIP#") if r.get("kind") == "skip"]
    skip_ids = {r.get("identifier") for r in tombs}
    skip_codes = {(r.get("code"), r.get("term")) for r in tombs if r.get("code")}
    keys = {code_key(c.get("courseCode")) for c in courses if code_key(c.get("courseCode"))}
    total = int(cfg.get("importedTotal") or 0)
    made = []
    for row in (detected or {}).get("classes") or []:
        if len(made) >= rules.get("maxImportPerRun", 12) or total >= rules.get("maxImportPerStudent", 20):
            break
        key = code_key(row.get("code"))
        if not row.get("identifier") or not key or key in keys or row["identifier"] in skip_ids or (row["code"], row["term"]) in skip_codes:
            continue
        course = _feed_course(sub, row, len(courses), stamp)
        scoped.put(f"COURSE#{course['id']}", course)
        courses.append({**course, "pk": scoped.pk, "sk": f"COURSE#{course['id']}"})
        keys.add(key)
        imported_ids[row["identifier"]] = course["id"]
        total += 1
        changed = True
        made.append({"code": row["code"], "section": row["section"], "term": row["term"], "identifier": row["identifier"],
                     "courseId": course["id"]})
    if changed:
        scoped.update("FEED", {"importedIds": imported_ids, "importedTotal": total})
        cfg.update(importedIds=imported_ids, importedTotal=total)
    if made:
        log_activity(scoped, "master", "feed_imported",
                     f"Imported {len(made)} class{'es' if len(made) != 1 else ''} from Blackboard", t)
    return made


def code_key(code: str):
    m = _CODE.search(str(code or ""))
    return (m.group(1).upper(), m.group(2).upper()) if m else None


class CourseIndex:
    def __init__(self, courses: list, rules: dict):
        self.rules, self.items = rules, []
        for c in courses:
            cid = c.get("id")
            if not isinstance(cid, str):
                continue
            code = str(c.get("courseCode") or "")
            m = _CODE.search(code)
            pattern = None
            if m:
                dept, num = re.escape(m.group(1)), re.escape(m.group(2))
                tail = r"(?![0-9A-Za-z])" if re.search(r"[A-Za-z]$", m.group(2)) else r"(?![0-9])"
                pattern = re.compile(rf"(?<![A-Za-z]){dept}[\s\-_.]*{num}{tail}", re.I)
            title_toks = [t for t in tokens(str(c.get("title") or "")) if t not in rules["stopWords"]]
            acro_src = [t for t in tokens(str(c.get("title") or "")) if t not in rules["stopWords"]]
            acronym = "".join(t[0] for t in acro_src) if len(acro_src) >= 3 else ""
            phrase = " ".join(title_toks) if len(title_toks) >= 2 else ""
            instr = [t for t in tokens(str(c.get("instructor") or "")) if len(t) >= 4 and t not in ("professor", "instructor")]
            self.items.append({"id": cid, "code": code, "key": code_key(code), "pattern": pattern, "titleToks": title_toks, "phrase": phrase,
                               "acronym": acronym.lower() if len(acronym) >= 3 else "",
                               "surname": instr[-1] if instr else ""})

    def by_id(self, cid):
        return next((i for i in self.items if i["id"] == cid), None)


def _score_course(ci: dict, ev: dict, rules: dict) -> list:
    """Evidence list [(layer, score)] for one class and one event."""
    sc = rules["scores"]
    title, desc, loc = ev.get("title", ""), ev.get("description", ""), ev.get("location", "")
    cats = " | ".join(ev.get("categories") or [])
    uid = ev.get("uid", "")
    ev_list = []
    if ci.get("key") and any((i["dept"], i["num"]) == ci["key"] for i in (ev.get("ids") or find_identifiers(ev))):
        ev_list.append(("identifier", sc["identifier"]))
    if ci["pattern"]:
        p = ci["pattern"]
        if p.search(title):
            ev_list.append(("codeTitle", sc["codeTitle"]))
        if p.search(cats):
            ev_list.append(("codeCategory", sc["codeCategory"]))
        if p.search(desc):
            ev_list.append(("codeDescription", sc["codeDescription"]))
        if p.search(loc):
            ev_list.append(("codeLocation", sc["codeLocation"]))
        if p.search(uid):
            ev_list.append(("codeUid", sc["codeUid"]))
    primary = _fold(title + " " + cats)
    primary_t, all_t = set(tokens(primary)), set(tokens(primary + " " + desc + " " + loc))
    if ci["phrase"] and re.search(rf"(?<!\w){re.escape(ci['phrase'])}(?!\w)", primary):
        ev_list.append(("titlePhrase", sc["titlePhrase"]))
    elif ci["titleToks"]:
        want = [t for t in dict.fromkeys(ci["titleToks"])]
        hit_p = [t for t in want if t in primary_t]
        hit_a = [t for t in want if t in all_t]
        if len(want) == 1 and hit_p:
            ev_list.append(("titleSingleWord", sc["titleSingleWord"]))
        elif len(want) >= 2 and len(hit_p) >= 2:
            ev_list.append(("titleWords", sc["titleWordsBase"] + sc["titleWordsSpan"] * len(hit_p) / len(want)))
        elif len(want) >= 2 and len(hit_a) >= 2:
            ev_list.append(("titleWordsDesc", (sc["titleWordsBase"] + sc["titleWordsSpan"] * len(hit_a) / len(want))
                            * sc["descriptionOnlyFactor"]))
    if ci["acronym"] and ci["acronym"] in primary_t:
        ev_list.append(("acronym", sc["acronym"]))
    if ci["surname"] and ci["surname"] in all_t:
        ev_list.append(("instructor", sc["instructor"]))
    return ev_list


def combine(evidence: list, rules: dict):
    """Best single layer, plus a small bonus for each extra independent layer (max two)."""
    if not evidence:
        return 0.0, ""
    best = max(evidence, key=lambda e: e[1])
    extra = min(2, len({e[0] for e in evidence}) - 1)
    return min(0.99, best[1] + rules["scores"]["corroborationBonus"] * extra), best[0]


def rule_matches(rule: dict, ev: dict, rules: dict) -> bool:
    kind, value = rule.get("ruleKind"), rule.get("value")
    if kind == "category":
        return value in [_fold(c) for c in ev.get("categories") or []]
    if kind == "tokens":
        return bool(value) and set(str(value).split()) <= set(tokens(ev.get("title", "")))
    if kind == "stem":
        return bool(value) and value == title_stem(ev.get("title", ""), rules)
    if kind == "pattern":
        return bool(value) and value == title_pattern(ev.get("title", ""))
    return False


def classify(ev: dict, index: CourseIndex, rules: dict, learned: list | None = None, stems: dict | None = None) -> dict:
    """Returns {courseId, confidence, reason, ignore, candidates:[{courseId, confidence, reason}]}. courseId is set only when
    the best class clears the threshold and the margin; `candidates` is always the top 3 for suggestions."""
    sc = rules["scores"]
    per = {}  # course id -> evidence list
    ignore_hit = False
    for r in learned or []:
        if rule_matches(r, ev, rules):
            conf = sc["learned"] if not r.get("conflicts") else sc["learnedConflict"]
            if r.get("ignore"):
                ignore_hit = ignore_hit or conf >= rules["autoThreshold"]
            elif index.by_id(r.get("courseId")):
                per.setdefault(r["courseId"], []).append(("learned", conf))
    stem = title_stem(ev.get("title", ""), rules)
    if stems and stem and len(stems.get(stem, ())) == 1:
        (cid,) = tuple(stems[stem])
        if index.by_id(cid):
            per.setdefault(cid, []).append(("stemHistory", sc["stemHistory"]))
    for ci in index.items:
        found = _score_course(ci, ev, rules)
        if found:
            per.setdefault(ci["id"], []).extend(found)
    ranked = sorted(((*combine(e, rules), cid) for cid, e in per.items()), reverse=True)
    cands = [{"courseId": cid, "confidence": round(conf, 2), "reason": why} for conf, why, cid in ranked[:3]]
    out = {"courseId": None, "confidence": cands[0]["confidence"] if cands else 0.0,
           "reason": cands[0]["reason"] if cands else "none", "ignore": False, "candidates": cands}
    if ignore_hit:
        out.update(ignore=True, reason="learned-ignore")
        return out
    if ranked:
        top = ranked[0]
        second = ranked[1][0] if len(ranked) > 1 else 0.0
        if top[0] >= rules["autoThreshold"] and top[0] - second >= rules["margin"]:
            out["courseId"] = top[2]
    return out


def default_chooser(ev: dict, cands: list, courses_by_id: dict, converse=None):
    """Optional model tie-breaker (FEEDSYNC_MODEL=1). Returns a course id from `cands` or None. The model sees the event
    only as a wrapped untrusted block, may only pick one of the offered ids (checked in code), and its answer lifts the
    event to just above the auto threshold, never higher. Any error means None."""
    try:
        from . import bedrock
        converse = converse or bedrock.converse
        nonce = guard.new_nonce()
        options = "\n".join(f"- {c['courseId']}: {guard.clean_text(courses_by_id.get(c['courseId'], {}).get('courseCode', ''), 30)} "
                            f"{guard.clean_text(courses_by_id.get(c['courseId'], {}).get('title', ''), 80)}" for c in cands)
        block = guard.wrap_untrusted("calendar_event", f"{ev.get('title','')}\n{ev.get('description','')[:400]}\n"
                                     f"{' '.join(ev.get('categories') or [])}", nonce)
        system = ("You pick which class a calendar event belongs to. Choose only from the listed class ids, or none. "
                  "Call the tool once.\n" + guard.data_rules(nonce))
        tool = {"toolSpec": {"name": "choose_course", "description": "Pick the class.", "inputSchema": {"json": {
            "type": "object", "properties": {"courseId": {"type": "string"}}, "required": ["courseId"]}}}}
        resp = converse(bedrock.MODEL_FAST, system, [{"role": "user", "content": [{"text": f"Classes:\n{options}\n\n{block}"}]}],
                                tools=[tool], force_tool="choose_course", max_tokens=limits.max_output_tokens("router"))
        use = bedrock.extract_tool_use(resp)
        if use and use[0] == "choose_course":
            cid = (use[2] or {}).get("courseId")
            if isinstance(cid, str) and cid in {c["courseId"] for c in cands}:
                return cid
    except Exception:  # noqa: BLE001
        pass
    return None


# ── Learned rules ─────────────────────────────────────────────────────────────

def _rule_sk(kind: str, value: str) -> str:
    return "FEED#rule_" + hashlib.sha256(f"{kind}|{value}".encode()).hexdigest()[:16]


def learn(scoped, ev: dict, course_id: str | None, rules: dict, now: str, ignore: bool = False) -> int:
    """Remember a mapping from one resolved event. Skipped when nothing about the event is distinctive. Returns rules written."""
    wanted = []
    for c in ev.get("categories") or []:
        if distinctive(tokens(c), rules) or re.search(r"\d", c):
            wanted.append(("category", _fold(c)))
    pat = title_pattern(ev.get("title", ""))
    if pattern_is_specific(pat, rules):
        wanted.append(("pattern", pat))
    toks = list(dict.fromkeys(distinctive(tokens(ev.get("title", "")), rules)))[:3]
    if toks:
        wanted.append(("tokens", " ".join(sorted(toks))))
    else:
        stem = title_stem(ev.get("title", ""), rules)
        if stem:
            wanted.append(("stem", stem))
    n = 0
    for kind, value in wanted:
        if not value or len(value) > 120:
            continue
        sk = _rule_sk(kind, value)
        cur = scoped.get(sk)
        conflicts = int((cur or {}).get("conflicts") or 0)
        if cur and (cur.get("courseId") != course_id or bool(cur.get("ignore")) != ignore):
            conflicts += 1
        scoped.put(sk, {"kind": "rule", "ruleKind": kind, "value": value, "courseId": course_id, "ignore": ignore,
                        "conflicts": conflicts, "hits": int((cur or {}).get("hits") or 0) + 1, "updatedAt": now})
        n += 1
    return n


# ── Assignments ───────────────────────────────────────────────────────────────

def derive_fields(ev: dict) -> dict:
    return {"title": ev["title"][:160], "type": ev.get("type") or "other", "dueDate": ev.get("dueDate"),
            "dueTime": ev.get("dueTime"), "notes": (ev.get("description") or "")[:400]}


def _asg_id(sub: str, key: str) -> str:
    return hashlib.sha256(f"{sub}|{key}".encode()).hexdigest()[:8]  # hex is a subset of [a-z0-9]; same event = same id


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(t))


def upsert_assignment(scoped, sub: str, ev: dict, course_id: str, assignments: list, now: str):
    """Returns (action, item). action: created | updated | linked | unchanged | capped. Never overwrites a field the
    student changed (compared with `feedBase`, what the feed itself wrote last) and never overwrites a manual or stated date."""
    want = derive_fields(ev)
    key = ev["key"]
    existing = next((a for a in assignments if a.get("feedUid") == key), None)
    if existing:
        base = existing.get("feedBase") or {}
        changes = {}
        newbase = dict(base)
        for f, nv in want.items():
            cur = existing.get(f)
            if f in ("dueDate", "dueTime") and existing.get("dateSource") in ("manual", "stated"):
                continue
            # overwrite only a field the student has not touched (still equal to what the feed wrote last);
            # an item with no feedBase (legacy) is never overwritten
            if f in base and cur == base[f] and cur != nv:
                changes[f] = nv
                newbase[f] = nv
        if changes:
            if "dueDate" in changes or "dueTime" in changes:
                changes["dateSource"] = "feed" if (changes.get("dueDate", existing.get("dueDate"))) else None
            changes.update(feedBase=newbase, sequence=int(existing.get("sequence") or 0) + 1, updatedAt=now)
            sk = f"ASG#{existing['courseId']}#{existing['id']}"
            upd = scoped.update(sk, util.to_dynamo(changes))
            existing.update(upd or changes)
            return "updated", existing
        return "unchanged", existing
    # adopt a look-alike (same class, same date, same title) instead of creating a duplicate
    nt = _norm_title(want["title"])
    for a in assignments:
        if (a.get("courseId") == course_id and not a.get("feedUid") and a.get("dueDate") == want["dueDate"]
                and a.get("dueDate") and _norm_title(a.get("title", "")) == nt):
            scoped.update(f"ASG#{course_id}#{a['id']}", {"feedUid": key, "feedBase": util.to_dynamo(want)})
            a["feedUid"], a["feedBase"] = key, want
            return "linked", a
    if sum(1 for a in assignments if a.get("courseId") == course_id) >= MAX_PER_COURSE:
        return "capped", None
    aid = _asg_id(sub, key)
    if any(a.get("id") == aid for a in assignments):
        aid = util.short_id()
    item = util.to_dynamo({
        "id": aid, "courseId": course_id, **want, "weight": None, "dueText": "",
        "dateSource": "feed" if want["dueDate"] else None, "done": False, "source": "feed", "feedUid": key,
        "feedBase": want, "sequence": 0, "createdAt": now, "updatedAt": now})
    scoped.put(f"ASG#{course_id}#{aid}", item)
    assignments.append({**item, "pk": scoped.pk, "sk": f"ASG#{course_id}#{aid}"})
    return "created", item


# ── Time and presentation helpers ─────────────────────────────────────────────

def num(v, default: float = 0.0) -> float:
    """float() for any number read from DynamoDB (Decimal), tolerating None and junk."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def now_iso(t=None) -> str:
    return datetime.fromtimestamp(num(t, time.time()) if t is not None else time.time(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mask_url(url: str) -> str:
    try:
        host, _ = safe_fetch.check_url(url)
    except safe_fetch.FetchError:
        return "https://…"
    return f"https://{host}/…{url[-4:] if len(url) >= 12 else ''}"


def _day_label(d: str | None) -> str:
    try:
        return date.fromisoformat(d).strftime("%a %b ") + str(date.fromisoformat(d).day) if d else "no date"
    except (TypeError, ValueError):
        return "no date"


def shard_of(sub: str) -> int:
    return int(hashlib.sha256(sub.encode()).hexdigest()[:4], 16) % SHARDS


def safe_trace(exc: BaseException, limit: int = 10) -> str:
    """Exception type plus traceback frames as `file:line function` only: no messages, no locals, no source text,
    so a log line can show WHERE something failed without ever carrying a URL or event text."""
    import traceback
    try:
        frames = traceback.extract_tb(exc.__traceback__)[-limit:]
        where = " <- ".join(f"{os.path.basename(f.filename)}:{f.lineno} {f.name}" for f in reversed(frames))
    except Exception:  # noqa: BLE001
        where = "?"
    return f"{type(exc).__name__} at {where}"


def dynamo_safe(value):
    """Recursively make a value storable by DynamoDB: floats become Decimal, dates become ISO text, sets and tuples
    become lists, non-finite numbers and unknown objects become None or text."""
    from decimal import Decimal
    if value is None or isinstance(value, (str, bool, int, Decimal)):
        return value
    if isinstance(value, float):
        return Decimal(str(value)) if value == value and value not in (float("inf"), float("-inf")) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value
    if isinstance(value, dict):
        return {str(k): dynamo_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [dynamo_safe(v) for v in value]
    return str(value)


class _SafeScoped(guard.UserScopedDB):
    """UserScopedDB whose writes always pass through dynamo_safe, so no code path can send a float to DynamoDB."""

    def put(self, sk, item):
        super().put(sk, dynamo_safe(item))

    def update(self, sk, updates):
        return super().update(sk, dynamo_safe(updates))


def scoped_view(sub: str, backend):
    return _SafeScoped(sub, backend, allowed_prefixes=("FEED", "FEEDSKIP", "ASG", "COURSE", "ACT", "PROFILE"))


def index_put(backend, sub: str, next_sync_at: float, failures: int = 0) -> None:
    backend.put_item(dynamo_safe({"pk": f"FEEDUSER#{shard_of(sub)}", "sk": f"U#{sub}", "sub": sub,
                                  "nextSyncAt": int(next_sync_at), "failures": int(failures)}))


def index_delete(backend, sub: str) -> None:
    backend.delete_item(f"FEEDUSER#{shard_of(sub)}", f"U#{sub}")


def log_activity(scoped, agent_id: str, kind: str, text: str, t: float | None = None) -> None:
    ts = now_iso(t)
    scoped.put(f"ACT#{ts}#{util.short_id(4)}", {"agentId": agent_id, "kind": kind,
                                                  "text": guard.clean_text(text, 300).replace("\n", " "),
                                                  "ttl": int((t or time.time()) + ACT_TTL)})


def _course_label(c: dict) -> str:
    return plain(c.get("courseCode") or c.get("title") or "Class", 30, True) or "Class"


def class_stats(cfg: dict | None, course: dict, cache_items: list, now: float) -> dict:
    cid = course.get("id")
    events = [i for i in cache_items if i.get("kind") == "event"]
    knows = course.get("knows") or {}
    unassigned = sum(1 for i in events if i.get("status") == "unassigned"
                     and (i.get("topSuggestion") == cid))
    cool = 0
    if cfg and cfg.get("lastManualSyncAt"):
        cool = max(0, int(MANUAL_COOLDOWN - (now - float(cfg["lastManualSyncAt"]))))
    return {"lastCheckedAt": (cfg or {}).get("lastCheckedAt"), "lastStatus": (cfg or {}).get("lastStatus") or "never",
            "lastError": (cfg or {}).get("lastError"), "newItemsCount": int(knows.get("newItemsCount") or 0),
            "unassignedCount": unassigned,
            "itemCount": sum(1 for i in events if i.get("status") == "matched" and i.get("courseId") == cid),
            "syncCooldownSeconds": cool}


MANUAL_COOLDOWN = 120


# ── Sync ──────────────────────────────────────────────────────────────────────

def _default_fetch(url: str, **kw) -> str:
    return safe_fetch.fetch_ical(url, max_bytes=limits.MAX_FEED_BYTES, **kw)


def _tz_for(scoped, backend) -> str:
    try:
        prof = scoped.get("PROFILE") or {}
        tenant = backend.get_item("TENANTS", f"T#{prof.get('tenantId')}") if prof.get("tenantId") else None
        name = (tenant or {}).get("timezone") or "America/Chicago"
    except Exception:  # noqa: BLE001
        name = "America/Chicago"
    return name if _zone(name) else "America/Chicago"


def _record(scoped, backend, sub, cfg, fields: dict, mirror: dict, t: float):
    cfg.update(fields)
    scoped.update("FEED", util.to_dynamo(fields))
    if scoped.get("PROFILE"):
        scoped.update("PROFILE", util.to_dynamo({"feed": {"connected": True, "urlMasked": cfg.get("urlMasked"), **mirror}}))


def sync_user(sub: str, deps: dict | None = None, now: float | None = None, manual: bool = False) -> dict:
    """Run one full sync for one student. Raises NotConnected or FeedError (the error is recorded first)."""
    d = deps or {}
    backend = d.get("backend") or _backend()
    rules = d.get("rules") or load_rules()
    t = now if now is not None else time.time()
    stamp = now_iso(t)
    deadline = t + float(d.get("budgetSeconds", 20)) if now is None else float("inf")
    scoped = scoped_view(sub, backend)
    cfg = scoped.get("FEED")
    if not cfg or not cfg.get("urlEnc"):
        raise NotConnected()
    cfg = dict(cfg)
    try:
        url = secretbox.open_(cfg["urlEnc"], PURPOSE, sub)
    except secretbox.SecretBoxError:
        _record(scoped, backend, sub, cfg, {"lastStatus": "error", "lastError": {"code": "feed_decrypt", "message": "Please save your Blackboard link again."}, "lastCheckedAt": stamp},
                {"lastStatus": "Please save your Blackboard link again", "lastCheckedAt": stamp}, t)
        raise FeedError("feed_decrypt", "Please save your Blackboard link again.")
    try:
        text = (d.get("fetch") or _default_fetch)(url, **(d.get("fetchKwargs") or {}))
    except safe_fetch.FetchError as e:
        code, msg = "feed_" + e.code, e.message
        _record(scoped, backend, sub, cfg, {"lastStatus": "error", "lastError": {"code": code, "message": msg}, "lastCheckedAt": stamp},
                {"lastStatus": msg, "lastCheckedAt": stamp}, t)
        raise FeedError(code, msg)
    finally:
        url = ""  # drop the secret from this frame as early as possible
    tz = _tz_for(scoped, backend)
    events = parse_ics(text, tz, rules, today_local(tz, t))
    body_hash = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:32]

    courses = [c for c in scoped.query("COURSE#") if isinstance(c, dict) and not c.get("archived")]
    imported = []
    try:
        detected = detect_classes_safe(events, today_local(tz, t), rules)
        imported = import_classes(scoped, sub, cfg, detected, courses, rules, t)
    except Exception as e:  # noqa: BLE001 (importing is a bonus: never fail the sync)
        print(f"feedsync class import skipped: {safe_trace(e)}")
    index = CourseIndex(courses, rules)
    course_sig = hashlib.sha256(json.dumps([[c.get("id"), c.get("courseCode"), c.get("title"), c.get("instructor")] for c in courses],
                                           sort_keys=True).encode()).hexdigest()[:16]
    cache_items = scoped.query("FEED#")
    cache = {i["sk"][5:]: i for i in cache_items if i.get("kind") == "event"}
    learned = [i for i in cache_items if i.get("kind") == "rule"]
    has_unassigned = any(i.get("status") == "unassigned" for i in cache.values())
    summary = {"added": 0, "updated": 0, "unassigned": 0, "unchanged": 0, "deferred": 0, "removed": 0, "addedByCourse": {}}

    if cfg.get("lastBodyHash") == body_hash and cfg.get("courseSig") == course_sig and not has_unassigned and cfg.get("lastStatus") != "error":
        status = "unchanged"
    else:
        status = _process(scoped, backend, sub, events, cache, learned, courses, index, rules, tz, t, stamp, deadline, d, summary)
        cache_items = scoped.query("FEED#")
        cache = {i["sk"][5:]: i for i in cache_items if i.get("kind") == "event"}

    counts = {"events": len(events), "matched": 0, "unassigned": 0, "dismissed": 0}
    for i in cache.values():
        if i.get("status") in counts and not (i.get("status") == "unassigned" and i.get("pendingClass")):
            counts[i["status"]] += 1
    counts.update(addedLastSync=summary["added"], updatedLastSync=summary["updated"])
    interval = rules["recheckMinutes"] * 60
    _record(scoped, backend, sub, cfg,
            {"lastStatus": status, "lastError": None, "lastCheckedAt": stamp, "lastBodyHash": body_hash, "courseSig": course_sig,
             "counts": counts, "classesDetected": detect_classes_safe(events, today_local(tz, t), rules),
             "meetingHints": _hints_safe(events, index, rules, today_local(tz, t)),
             "suggestedCodes": suggest_codes_safe(events, today_local(tz, t), rules), "nextSyncAt": int(t + interval), **({"lastManualSyncAt": t} if manual else {})},
            {"lastStatus": status, "lastCheckedAt": stamp}, t)
    # class stats
    by_course = summary.get("addedByCourse") or {}
    for c in courses:
        knows = dict(c.get("knows") or {})
        n_new = by_course.get(c["id"], {}).get("new", 0)
        knows.update(lastFeedCheckAt=stamp, newItemsCount=int(knows.get("newItemsCount") or 0) + n_new,
                     assignmentsCount=int(knows.get("assignmentsCount") or 0) + by_course.get(c["id"], {}).get("created", 0))
        scoped.update(f"COURSE#{c['id']}", util.to_dynamo({"knows": knows}))
    summary.update(status=status, checkedAt=stamp, counts=counts, importedClasses=imported,
                   byCourse={k: {"created": v.get("created", 0), "updated": v.get("updated", 0)} for k, v in by_course.items()})
    summary.pop("addedByCourse", None)
    return summary


_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def meeting_hints(events: list, index, rules: dict, today: date) -> dict:
    """Class sessions (not deadlines) whose title names one class: {courseId: [{weekday, start, end, count}]}, most frequent
    first. Only a hint to pre-fill meeting times; it never creates anything."""
    acc = {}
    for ev in events:
        try:
            if ev.get("kind") != "meeting" or not ev.get("dueTime") or not _safe_in_window(ev, today, rules):
                continue
            res = classify(ev, index, rules)
            if not res["courseId"]:
                continue
            k = (res["courseId"], _DAYS[date.fromisoformat(ev["dueDate"]).weekday()], ev["dueTime"], ev.get("endTime") or "")
            acc[k] = acc.get(k, 0) + 1
        except Exception:  # noqa: BLE001
            continue
    out = {}
    for (cid, wd, st, en), n in sorted(acc.items(), key=lambda kv: -kv[1]):
        if n >= 2 and len(out.setdefault(cid, [])) < 6:
            out[cid].append({"weekday": wd, "start": st, "end": en or None, "count": n})
    return {k: v for k, v in out.items() if v}


def today_local(tz: str, t: float) -> date:
    try:
        return datetime.fromtimestamp(float(t), tz=_zone(tz) or timezone.utc).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return datetime.now(timezone.utc).date()


def classes_view(cfg: dict | None, courses: list) -> dict:
    """GET /me/feed/classes body from the detection stored at the last save or sync."""
    det = (cfg or {}).get("classesDetected") or {}
    by_key = {}
    for c in courses:
        k = code_key(c.get("courseCode"))
        if k and isinstance(c.get("id"), str):
            by_key.setdefault(k, c["id"])
    rows = []
    for r in det.get("classes") or []:
        rows.append({**{k: r.get(k) for k in ("code", "section", "term", "identifier", "eventCount")},
                     "matchedCourseId": by_key.get(code_key(r.get("code")))})
    have = {k for k in by_key}
    suggested = [s for s in (cfg or {}).get("suggestedCodes") or [] if code_key(s.get("code")) not in have]
    return {"connected": bool(cfg), "term": det.get("term"), "classes": rows,
            "suggested": [{"code": s.get("code"), "eventCount": s.get("eventCount")} for s in suggested]}


def _hints_safe(events, index, rules, today) -> dict:
    try:
        return meeting_hints(events, index, rules, today)
    except Exception:  # noqa: BLE001
        return {}


def _backend():
    from . import db  # late import: tests need no AWS libraries
    return db


def _in_window(ev: dict, today: date, rules: dict) -> bool:
    if not ev.get("dueDate"):
        return True
    try:
        dd = date.fromisoformat(str(ev["dueDate"])[:10])   # always a plain date: never compared with a datetime
    except ValueError:
        return False
    return -rules["window"]["pastDays"] <= (dd - today).days <= rules["window"]["futureDays"]


def _snapshot(ev: dict) -> dict:
    return {k: ev.get(k) for k in ("uid", "title", "description", "location", "categories", "dueDate", "dueTime", "allDay", "type")}


def _process(scoped, backend, sub, events, cache, learned, courses, index, rules, tz, t, stamp, deadline, d, summary):
    today = datetime.fromtimestamp(num(t), tz=_zone(tz) or timezone.utc).date()
    assignments = [a for a in scoped.query("ASG#") if isinstance(a, dict)]
    stems = {}
    for a in assignments:
        if a.get("source") == "feed" and a.get("courseId"):
            s = title_stem(a.get("title", ""), rules)
            if s:
                stems.setdefault(s, set()).add(a["courseId"])
    courses_by_id = {c["id"]: c for c in courses if isinstance(c.get("id"), str)}
    ignore_res = []
    for p in rules.get("ignoreTitlePatterns") or []:
        try:
            ignore_res.append(re.compile(p, re.I))
        except re.error:
            pass
    chooser = d.get("chooser") or (default_chooser if (rules.get("useModel") or os.environ.get("FEEDSYNC_MODEL") == "1") and limits.ai_enabled() else None)
    model_calls, new_seen, new_unassigned, changed = 0, 0, [], False
    per = summary["addedByCourse"]
    log_budget = {}
    seen_keys = set()
    cur_terms = current_terms(events, today, rules, courses) if rules.get("currentTermOnly") else set()
    class_keys = {ci["key"] for ci in index.items if ci.get("key")}
    for ev in events:
        try:
            if not _safe_in_window(ev, today, rules) or ev["status"] == "CANCELLED" or any(r.search(ev["title"]) for r in ignore_res):
                continue
            if ev.get("kind") == "meeting":
                summary["meetings"] = summary.get("meetings", 0) + 1   # class sessions: never an assignment, never Unassigned
                continue
            ids = find_identifiers(ev)
            if cur_terms and ids and not any(i["term"] in cur_terms for i in ids):
                summary["oldTerm"] = summary.get("oldTerm", 0) + 1   # an old-term calendar: never creates anything
                continue
            ev["ids"] = ids
            seen_keys.add(ev["key"])
            row = cache.get(ev["key"])
            if row and row.get("hash") == ev["hash"] and row.get("status") != "unassigned":
                summary["unchanged"] += 1
                if row.get("goneAt"):
                    scoped.update(f"FEED#{ev['key']}", {"goneAt": None})
                continue
            if time.time() > deadline or (not row and new_seen >= rules["maxNewPerSync"]):
                summary["deferred"] += 1
                continue
            if not row:
                new_seen += 1
            status_prev = (row or {}).get("status")
            if status_prev == "dismissed":
                scoped.put(f"FEED#{ev['key']}", {**_strip(row), "hash": ev["hash"], "ev": _snapshot(ev), "lastChangedAt": stamp})
                continue
            if status_prev == "matched" and row.get("courseId") in courses_by_id:
                cid, conf, reason = row["courseId"], row.get("confidence", 1.0), row.get("reason", "kept")
            else:
                res = classify(ev, index, rules, learned, stems)
                if res["ignore"]:
                    scoped.put(f"FEED#{ev['key']}", {"kind": "event", "uid": ev["uid"], "hash": ev["hash"], "status": "dismissed",
                                                     "ev": _snapshot(ev), "firstSeenAt": stamp, "lastChangedAt": stamp, "reason": "learned-ignore"})
                    continue
                cid, conf, reason = res["courseId"], res["confidence"], res["reason"]
                if cid is None and chooser and model_calls < rules["maxModelCalls"] and len(res["candidates"]) >= 2 \
                        and res["candidates"][0]["confidence"] >= 0.5:
                    model_calls += 1
                    pick = chooser(ev, res["candidates"], courses_by_id)
                    if pick:
                        cid, conf, reason = pick, rules["scores"]["model"], "model"
            if cid is None:
                if row and status_prev == "unassigned" and row.get("hash") == ev["hash"]:
                    continue  # still unassigned and unchanged: no write
                top = (res["candidates"] or [{}])[0].get("courseId")
                first = (row or {}).get("firstSeenAt") or stamp
                # a current-term identifier for a class the student has not added: park it (placed automatically once added)
                pending = next((i["code"] for i in ids if i["term"] in cur_terms and (i["dept"], i["num"]) not in class_keys), None) if ids else None
                scoped.put(f"FEED#{ev['key']}", {"kind": "event", "uid": ev["uid"], "hash": ev["hash"], "status": "unassigned",
                                                 "ev": _snapshot(ev), "firstSeenAt": first, "lastChangedAt": stamp,
                                                 "confidence": conf, "topSuggestion": top, "pendingClass": pending})
                if (not row or status_prev != "unassigned") and not pending:
                    summary["unassigned"] += 1
                    new_unassigned.append(ev["title"])
                continue
            action, item = upsert_assignment(scoped, sub, ev, cid, assignments, stamp)
            if action == "capped":
                scoped.put(f"FEED#{ev['key']}", {"kind": "event", "uid": ev["uid"], "hash": ev["hash"], "status": "unassigned",
                                                 "ev": _snapshot(ev), "firstSeenAt": stamp, "lastChangedAt": stamp, "confidence": conf, "topSuggestion": cid})
                continue
            is_new = action in ("created", "linked") and not row
            scoped.put(f"FEED#{ev['key']}", {"kind": "event", "uid": ev["uid"], "hash": ev["hash"], "status": "matched",
                                             "courseId": cid, "assignmentId": item.get("id") if item else None, "confidence": conf,
                                             "reason": reason, "ev": _snapshot(ev), "firstSeenAt": (row or {}).get("firstSeenAt") or stamp,
                                             "lastChangedAt": stamp, "isNew": bool(is_new or (row or {}).get("isNew"))})
            slot = per.setdefault(cid, {"new": 0, "created": 0})
            label = _course_label(courses_by_id[cid])
            when = _day_label(ev.get("dueDate"))
            if action == "created":
                summary["added"] += 1
                slot["new"] += 1
                slot["created"] += 1
                _log_limited(scoped, log_budget, cid, "feed_added", f"{label} agent added: {ev['title'][:80]}, due {when}", t)
            elif action == "linked":
                summary["unchanged"] += 1
                slot["new"] += 0
            elif action == "updated":
                summary["updated"] += 1
                slot["updated"] = slot.get("updated", 0) + 1
                _log_limited(scoped, log_budget, cid, "feed_updated", f"{label} agent updated: {ev['title'][:80]}, due {when}", t)
            else:
                summary["unchanged"] += 1
        except Exception:  # noqa: BLE001 (one odd event must never fail the whole feed)
            summary["skippedEvents"] = summary.get("skippedEvents", 0) + 1

    for cid, kinds in log_budget.items():
        for kind, extra in kinds.items():
            if extra["more"]:
                verb = "added" if kind == "feed_added" else "updated"
                log_activity(scoped, cid, kind, f"{_course_label(courses_by_id[cid])} agent {verb} {extra['more']} more items from Blackboard", t)
    if new_unassigned:
        log_activity(scoped, "master", "feed_unassigned",
                     f"{len(new_unassigned)} Blackboard item{'s' if len(new_unassigned) != 1 else ''} need a class (open Study)", t)
    # events that vanished from the feed (never deletes assignments)
    if events:
        gone = 0
        for key, row in cache.items():
            if key in seen_keys or row.get("goneAt") or row.get("status") != "matched" or gone >= 5:
                continue
            due = (row.get("ev") or {}).get("dueDate")
            if due and due >= today.isoformat():
                scoped.update(f"FEED#{key}", {"goneAt": stamp})
                c = courses_by_id.get(row.get("courseId"))
                if c:
                    log_activity(scoped, c["id"], "feed_removed", f"{_course_label(c)}: {(row.get('ev') or {}).get('title', 'An item')[:80]} is no longer in your Blackboard calendar", t)
                gone += 1
                summary["removed"] += 1
    return "changed" if (summary["added"] or summary["updated"] or summary["unassigned"] or summary["removed"]) else "ok"


def _strip(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in ("pk", "sk")}


def _log_limited(scoped, budget: dict, cid: str, kind: str, text: str, t: float, cap: int = 3):
    slot = budget.setdefault(cid, {}).setdefault(kind, {"n": 0, "more": 0})
    if slot["n"] < cap:
        slot["n"] += 1
        log_activity(scoped, cid, kind, text, t)
    else:
        slot["more"] += 1


# ── Unassigned inbox ──────────────────────────────────────────────────────────

class NotFound(Exception):
    pass


def _fresh_index(scoped, rules):
    courses = [c for c in scoped.query("COURSE#") if isinstance(c, dict)]
    return courses, CourseIndex(courses, rules)


def inbox(scoped, rules: dict | None = None, course_id: str | None = None, limit: int = 200) -> list:
    rules = rules or load_rules()
    courses, index = _fresh_index(scoped, rules)
    by_id = {c["id"]: c for c in courses if isinstance(c.get("id"), str)}
    items = scoped.query("FEED#")
    learned = [i for i in items if i.get("kind") == "rule"]
    out = []
    for row in items:
        if row.get("kind") != "event" or row.get("status") != "unassigned" or row.get("pendingClass"):
            continue
        ev = dict(row.get("ev") or {})
        res = classify(ev, index, rules, learned)
        sugg = [{"courseId": c["courseId"], "courseCode": _course_label(by_id[c["courseId"]]), "confidence": c["confidence"]}
                for c in res["candidates"] if c["courseId"] in by_id and c["confidence"] >= 0.3]
        if course_id and not (sugg and sugg[0]["courseId"] == course_id):
            continue
        out.append({"uid": row["sk"][5:], "title": ev.get("title", ""), "description": (ev.get("description") or "")[:300],
                    "categories": list(ev.get("categories") or [])[:8], "dueDate": ev.get("dueDate"), "dueTime": ev.get("dueTime"),
                    "allDay": bool(ev.get("allDay")), "type": ev.get("type") or "other", "firstSeenAt": row.get("firstSeenAt"),
                    "suggestions": sugg})
    out.sort(key=lambda x: (x["dueDate"] is None, x["dueDate"] or "", x["title"]))
    return out[:limit]


def _event_from_row(row: dict, key: str) -> dict:
    ev = dict(row.get("ev") or {})
    ev["key"] = key
    ev.setdefault("status", "")
    return ev


def _assign_row(scoped, sub, row, key, course_id, course, assignments, stamp, t, log=True):
    ev = _event_from_row(row, key)
    action, item = upsert_assignment(scoped, sub, ev, course_id, assignments, stamp)
    if action == "capped" or not item:
        return None, ev
    scoped.put(f"FEED#{key}", {**_strip(row), "status": "matched", "courseId": course_id, "assignmentId": item.get("id"),
                               "confidence": 1.0, "reason": "student", "lastChangedAt": stamp, "isNew": False})
    if log:
        log_activity(scoped, course_id, "feed_added", f"{_course_label(course)} agent added: {ev.get('title', '')[:80]}, due {_day_label(ev.get('dueDate'))}", t)
    return item, ev


def build_groups(items: list) -> list:
    """Group inbox items by normalised title pattern (two or more items). Each group can be assigned or dismissed in one tap."""
    by = {}
    for it in items:
        by.setdefault(title_pattern(it.get("title", "")), []).append(it)
    groups = []
    for pat, its in by.items():
        if len(its) < 2:
            continue
        acc, labels = {}, {}
        for it in its:
            for s in it.get("suggestions") or []:
                acc[s["courseId"]] = acc.get(s["courseId"], 0.0) + s["confidence"]
                labels[s["courseId"]] = s["courseCode"]
        sugg = [{"courseId": c, "courseCode": labels[c], "confidence": round(v / len(its), 2)}
                for c, v in sorted(acc.items(), key=lambda kv: -kv[1])[:3]]
        dues = [i["dueDate"] for i in its if i.get("dueDate")]
        groups.append({"groupId": hashlib.sha256(pat.encode()).hexdigest()[:12], "pattern": pat, "label": pat.title(),
                       "count": len(its), "uids": [i["uid"] for i in its][:100], "sampleTitles": [i["title"] for i in its][:3],
                       "firstDue": min(dues) if dues else None, "lastDue": max(dues) if dues else None, "suggestions": sugg})
    groups.sort(key=lambda g: (-g["count"], g["pattern"]))
    return groups


def _group_uids(scoped, rules, group_id: str) -> list:
    g = next((g for g in build_groups(inbox(scoped, rules, limit=2000)) if g["groupId"] == group_id), None)
    if not g:
        raise NotFound()
    return g


def assign_group(scoped, sub: str, group_id: str, course_id: str, remember: bool, rules: dict | None = None, t: float | None = None) -> dict:
    rules = rules or load_rules()
    course = scoped.get(f"COURSE#{course_id}")
    if not course:
        raise NotFound()
    g = _group_uids(scoped, rules, group_id)
    stamp = now_iso(t)
    assignments = [a for a in scoped.query("ASG#") if isinstance(a, dict)]
    done, first_ev = 0, None
    for uid in g["uids"]:
        row = scoped.get(f"FEED#{uid}")
        if not row or row.get("kind") != "event" or row.get("status") != "unassigned":
            continue
        item, ev = _assign_row(scoped, sub, row, uid, course_id, course, assignments, stamp, t, log=False)
        if item:
            done += 1
            first_ev = first_ev or ev
    if done:
        log_activity(scoped, course_id, "feed_added", f"{_course_label(course)} agent added {done} item{'s' if done != 1 else ''} from Blackboard", t)
    learned = bool(remember and first_ev and learn(scoped, first_ev, course_id, rules, stamp) > 0)
    return {"assigned": done, "learned": learned, "remaining": max(0, g["count"] - len(g["uids"]))}


def dismiss_group(scoped, group_id: str, remember: bool, rules: dict | None = None, t: float | None = None) -> dict:
    rules = rules or load_rules()
    g = _group_uids(scoped, rules, group_id)
    stamp = now_iso(t)
    n, first_ev = 0, None
    for uid in g["uids"]:
        row = scoped.get(f"FEED#{uid}")
        if row and row.get("kind") == "event" and row.get("status") == "unassigned":
            scoped.put(f"FEED#{uid}", {**_strip(row), "status": "dismissed", "lastChangedAt": stamp})
            first_ev = first_ev or _event_from_row(row, uid)
            n += 1
    learned = bool(remember and first_ev and learn(scoped, first_ev, None, rules, stamp, ignore=True) > 0)
    return {"dismissed": n, "learned": learned}


def assign_event(scoped, sub: str, key: str, course_id: str, remember: bool, rules: dict | None = None, t: float | None = None) -> dict:
    rules = rules or load_rules()
    row = scoped.get(f"FEED#{key}")
    course = scoped.get(f"COURSE#{course_id}")
    if not row or row.get("kind") != "event" or row.get("status") != "unassigned" or not course:
        raise NotFound()
    stamp = now_iso(t)
    assignments = [a for a in scoped.query("ASG#") if isinstance(a, dict)]
    item, ev = _assign_row(scoped, sub, row, key, course_id, course, assignments, stamp, t)
    if not item:
        raise NotFound()
    learned_n, also = 0, 0
    if remember:
        learned_n = learn(scoped, ev, course_id, rules, stamp)
        courses, index = _fresh_index(scoped, rules)
        rule_rows = [i for i in scoped.query("FEED#") if i.get("kind") == "rule"]
        for other in scoped.query("FEED#"):
            if also >= 50:
                break
            if other.get("kind") != "event" or other.get("status") != "unassigned" or other["sk"][5:] == key:
                continue
            oev = _event_from_row(other, other["sk"][5:])
            res = classify(oev, index, rules, rule_rows)
            if res["courseId"] == course_id and res["reason"] == "learned":
                a2, i2 = upsert_assignment(scoped, sub, oev, course_id, assignments, stamp)
                if i2:
                    scoped.put(other["sk"], {**_strip(other), "status": "matched", "courseId": course_id, "assignmentId": i2.get("id"),
                                             "confidence": res["confidence"], "reason": "learned", "lastChangedAt": stamp, "isNew": True})
                    also += 1
    return {"assignment": item, "course": course, "learned": learned_n > 0, "alsoAssigned": also}


def dismiss_event(scoped, key: str, remember: bool, rules: dict | None = None, t: float | None = None) -> dict:
    rules = rules or load_rules()
    row = scoped.get(f"FEED#{key}")
    if not row or row.get("kind") != "event" or row.get("status") != "unassigned":
        raise NotFound()
    stamp = now_iso(t)
    scoped.put(f"FEED#{key}", {**_strip(row), "status": "dismissed", "lastChangedAt": stamp})
    learned = learn(scoped, _event_from_row(row, key), None, rules, stamp, ignore=True) > 0 if remember else False
    return {"dismissed": True, "learned": learned}


def class_items(scoped, course_id: str, limit: int = 100) -> list:
    rows = [r for r in scoped.query("FEED#") if r.get("kind") == "event" and r.get("status") == "matched" and r.get("courseId") == course_id]
    rows.sort(key=lambda r: r.get("lastChangedAt") or "", reverse=True)
    out = []
    for r in rows[:limit]:
        ev = r.get("ev") or {}
        out.append({"uid": r["sk"][5:], "assignmentId": r.get("assignmentId"), "title": ev.get("title", ""), "type": ev.get("type") or "other",
                    "dueDate": ev.get("dueDate"), "dueTime": ev.get("dueTime"), "firstSeenAt": r.get("firstSeenAt"),
                    "lastChangedAt": r.get("lastChangedAt"), "isNew": bool(r.get("isNew")), "removedFromFeed": bool(r.get("goneAt"))})
    return out


def mark_seen(scoped, course_id: str | None) -> None:
    for r in scoped.query("FEED#"):
        if r.get("kind") == "event" and r.get("isNew") and (course_id is None or r.get("courseId") == course_id):
            scoped.update(r["sk"], {"isNew": False})
    for c in scoped.query("COURSE#"):
        if course_id is None or c.get("id") == course_id:
            knows = dict(c.get("knows") or {})
            if knows.get("newItemsCount"):
                knows["newItemsCount"] = 0
                scoped.update(f"COURSE#{c['id']}", {"knows": knows})
