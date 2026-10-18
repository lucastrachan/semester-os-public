"""Storage and rules for class group chats ("rooms"). Contract: ROOMS_API.md.

A room is (tenantId, term, normalised course code); roomId = "{tenant}.{TERM}.{CODE}". Membership is computed at read
time from the caller's own COURSE# items (no fan-out writes). Enrollment is NOT verified: the API says so.
Per-user settings live in USER#{sub}/RM#{roomId}; messages in ROOMMSG#{roomId}/M#{iso}#{rand}.
Nothing here returns or stores an email, real name or sub in a message; messages carry only a nickname and an
internal sender hash (never sent to clients). This module does not import the API layer.
"""
import hashlib
import re
import secrets
import string
from datetime import datetime, timedelta, timezone

from . import convos, db, guard, limits

MAX_TEXT = 500
MAX_ROOM_MESSAGES = 300
RETAIN_DAYS = 60
REPORT_TTL_DAYS = 180
MEMBER_TTL_DAYS = 240
PREVIEW = 90
EVIDENCE = 10
PER_MINUTE, PER_DAY = 12, 300
limits.USER_LIMITS.setdefault("room", (PER_MINUTE, PER_DAY))   # additive: no edit to limits.py

ROOM_ID_RE = re.compile(r"^[a-z0-9-]{1,40}\.[A-Za-z0-9-]{1,20}\.[A-Z0-9]{2,12}$")
CURSOR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[0-9:.]{8,16}Z#[a-z0-9]{4}$")
REPORT_REASONS = convos.REPORT_REASONS
SAFETY_TIPS = (
    "Classmates who added this class are not verified students. Treat everyone as a stranger.",
    "Never share your phone number, student ID, address, passwords or exam answers.",
    "Don't click or post links; Semester OS blocks them. Meet in public on campus.",
    "Use Report or Block on any message that makes you uncomfortable.",
)

_ALPHABET = string.ascii_lowercase + string.digits
_SEASONS = {"fall": "FA", "autumn": "FA", "fa": "FA", "spring": "SP", "sp": "SP", "summer": "SU", "su": "SU", "winter": "WI", "wi": "WI"}
_SEASON_RE = re.compile(r"(?i)\b(fall|autumn|spring|summer|winter|fa|sp|su|wi)\b")
_YEAR_RE = re.compile(r"(?<!\d)(\d{4}|\d{2})(?!\d)")
_DATES = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/:]\d{1,2}(?:[/:]\d{2,4})?\b")
_DIGIT_RUN = re.compile(r"\d(?:[ \-.()/]?\d){6,}")
_MARKUP = re.compile(r"[<>@]|!\[|\]\(")
_SECRET = re.compile(r"(?i)\b(?:password|passwd|passcode|ssn|social security|credit card|cvv|api[_ \-]?key)\b")
_PROFANE = re.compile(r"(?i)\b(?:fuck\w*|shit\w*|bitch\w*|cunt\w*|nigg\w+|fag(?:got)?s?|retard\w*|whore\w*|slut\w*|kill yourself|kys)\b")
_NICK_OK = re.compile(r"^[A-Za-z0-9 ._'\-]{2,24}$")


class RoomError(convos.MsgError):
    pass


def _bad(msg: str) -> RoomError:
    return RoomError(400, "validation_error", msg)


# ── Identity ──────────────────────────────────────────────────────────────────

def user_hash(sub: str) -> str:
    return convos.user_hash(sub)


def default_nickname(sub: str) -> str:
    n = int(hashlib.sha256(("nick:" + str(sub)).encode()).hexdigest(), 16) % 10000
    return f"Classmate {n:04d}"


_AVATAR_SLUGS = frozenset(f"robot-{n:02d}" for n in range(1, 13))


def get_nickname(sub: str) -> tuple:
    it = db.get_item(f"USER#{sub}", "NICK")
    nick = str((it or {}).get("nickname") or "")
    avatar = (it or {}).get("avatar")
    avatar = avatar if avatar in _AVATAR_SLUGS else None
    if nick and _NICK_OK.match(nick):
        return nick, False, avatar
    return default_nickname(sub), True, avatar


def clean_nickname(raw) -> str:
    if not isinstance(raw, str):
        raise _bad("Nickname must be text.")
    s = re.sub(r"\s+", " ", guard.clean_text(raw, 60)).strip()
    if not _NICK_OK.match(s):
        raise _bad("Nicknames are 2-24 characters: letters, numbers, spaces and . _ - '")
    if convos.LINK_RE.search(s) or _DIGIT_RUN.search(s) or re.search(r"\d{5,}", s) or _PROFANE.search(s) or _SECRET.search(s):
        raise _bad("Choose a different nickname (no links, numbers that look like IDs, or rude words).")
    if not re.search(r"[A-Za-z]", s):
        raise _bad("A nickname needs at least one letter.")
    return s


def set_nickname(sub: str, raw, avatar=None) -> tuple:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if avatar is not None and avatar in _AVATAR_SLUGS:
            db.put_item({"pk": f"USER#{sub}", "sk": "NICK", "nickname": "", "avatar": avatar})
            return default_nickname(sub), True, avatar
        db.delete_item(f"USER#{sub}", "NICK")
        return default_nickname(sub), True, None
    nick = clean_nickname(raw)
    av = avatar if avatar in _AVATAR_SLUGS else None
    item: dict = {"pk": f"USER#{sub}", "sk": "NICK", "nickname": nick}
    if av is not None:
        item["avatar"] = av
    db.put_item(item)
    return nick, False, av


# ── Room identity and membership ──────────────────────────────────────────────

def norm_code(raw) -> str:
    code = re.sub(r"[^A-Za-z0-9]", "", str(raw or "")).upper()[:12]
    return code if 2 <= len(code) and re.search(r"[A-Z]", code) and re.search(r"\d", code) else ""


def norm_term(raw, created: str = "") -> str:
    s = str(raw or "").strip()
    if re.fullmatch(r"\d{6}", s):
        return s
    if s:
        sm, ym = _SEASON_RE.search(s), _YEAR_RE.search(s)
        if sm and ym:
            return _SEASONS[sm.group(1).lower()] + ym.group(1)[-2:]
        flat = re.sub(r"[^A-Za-z0-9]", "", s).upper()[:12]
        if flat:
            return flat
    try:
        dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.now(timezone.utc)
    season = "SP" if dt.month <= 5 else ("SU" if dt.month <= 7 else "FA")
    return f"{season}{dt.year % 100:02d}"


def room_id(tenant_id: str, term: str, code: str) -> str:
    return f"{tenant_id}.{term}.{code}"


def my_rooms(sub: str, tenant_id: str) -> dict:
    """{roomId: {id, code, displayCode, title, term}} from the caller's own classes on their campus."""
    out = {}
    for c in db.query_pk(f"USER#{sub}", "COURSE#"):
        if c.get("pk") != f"USER#{sub}" or c.get("archived"):
            continue
        code = norm_code(c.get("courseCode"))
        if not code or not re.fullmatch(r"[a-z0-9-]{1,40}", str(tenant_id or "")):
            continue
        term = norm_term(c.get("termCode") or c.get("term"), c.get("createdAt") or "")
        rid = room_id(tenant_id, term, code)
        title = guard.clean_text(c.get("title") or "", 80).replace("\n", " ").strip()
        disp = guard.clean_text(c.get("courseCode") or "", 20).strip() or code
        cur = out.setdefault(rid, {"id": rid, "code": code, "displayCode": disp, "title": "", "term": term})
        if title and title.upper().replace(" ", "") != code and not cur["title"]:
            cur["title"] = title
    return out


# ── Settings, counters ────────────────────────────────────────────────────────

def _skey(rid: str) -> str:
    return f"RM#{rid}"


def settings(sub: str, rid: str) -> dict:
    return db.get_item(f"USER#{sub}", _skey(rid)) or {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _members_n(rid: str) -> int:
    return int((db.get_item(f"ROOM#{rid}", "MEMBERS") or {}).get("n") or 0)


def ensure_counted(sub: str, rid: str, st: dict) -> dict:
    """First time this user sees the room: count them (approximate member counter)."""
    if st.get("counted"):
        return st
    db.incr_counter(f"ROOM#{rid}", "MEMBERS", int((_now() + timedelta(days=MEMBER_TTL_DAYS)).timestamp()))
    msgs = list_messages(rid)
    start = cursor_of(msgs[-1]) if msgs else ""   # history from before you joined is not "unread"
    upd = {"counted": True}
    if not st.get("lastRead"):
        upd["lastRead"] = start
    db.update_item(f"USER#{sub}", _skey(rid), upd)
    return {**st, **upd}


def member_count(rid: str) -> int:
    return max(1, _members_n(rid))


def set_flag(sub: str, rid: str, **flags) -> None:
    db.update_item(f"USER#{sub}", _skey(rid), flags)


def leave(sub: str, rid: str) -> None:
    st = settings(sub, rid)
    if not st.get("left"):
        if st.get("counted"):
            n = _members_n(rid)
            db.update_item(f"ROOM#{rid}", "MEMBERS", {"n": max(0, n - 1)})
        set_flag(sub, rid, left=True, counted=False)


def rejoin(sub: str, rid: str) -> None:
    st = settings(sub, rid)
    if st.get("left"):
        set_flag(sub, rid, left=False)
        ensure_counted(sub, rid, {**st, "counted": False})


def mark_read(sub: str, rid: str, cursor: str) -> None:
    if cursor:
        set_flag(sub, rid, lastRead=cursor)


# ── Closed rooms, bans ────────────────────────────────────────────────────────

def is_closed(rid: str) -> bool:
    return bool(db.get_item(f"ROOMCLOSED#{rid}", "META"))


def close_room(rid: str, by: str = "admin", reason: str = "") -> None:
    db.put_item({"pk": f"ROOMCLOSED#{rid}", "sk": "META", "reason": guard.clean_text(reason, 200), "by": by, "at": convos.iso(_now())})


def reopen_room(rid: str) -> None:
    db.delete_item(f"ROOMCLOSED#{rid}", "META")


# ── Messages ──────────────────────────────────────────────────────────────────

def validate_text(text) -> str:
    """Plain text, 1-500 chars; no links, @, markup, emails, phone/ID digit runs or profanity. Raises RoomError(400)."""
    if not isinstance(text, str):
        raise _bad("Write a message first.")
    s = guard.clean_text(text, MAX_TEXT + 1)
    s = re.sub(r"[ \t]+", " ", re.sub(r"\n{2,}", "\n", s)).strip()
    if not s:
        raise _bad("Write a message first.")
    if len(s) > MAX_TEXT:
        raise _bad(f"Messages can be up to {MAX_TEXT} characters.")
    if convos.LINK_RE.search(s):
        raise _bad("Links aren't allowed in class chats.")
    if _MARKUP.search(s):
        raise _bad("Please don't use @, < or > in messages.")
    if _DIGIT_RUN.search(_DATES.sub("", s)) or _SECRET.search(s):
        raise _bad("Don't share phone numbers, ID numbers or passwords in a class chat.")
    if _PROFANE.search(s):
        raise _bad("Please keep it respectful.")
    return s


def preview(text: str) -> str:
    one = re.sub(r"\s+", " ", str(text or "")).strip()
    return one if len(one) <= PREVIEW else one[:PREVIEW - 1] + "…"


def list_messages(rid: str) -> list:
    return sorted(db.query_pk(f"ROOMMSG#{rid}", "M#"), key=lambda m: m["sk"])


def cursor_of(item: dict) -> str:
    return item["sk"][2:]


def check_repeat(rid: str, sub: str, text: str) -> None:
    h = user_hash(sub)
    mine = [m for m in list_messages(rid)[-10:] if m.get("senderHash") == h]
    n = convos.norm_text(text)
    if mine and convos.norm_text(mine[-1].get("text")) == n and len(n) >= 4:
        raise _bad("You just sent that message.")


def add_message(rid: str, sub: str, name: str, text: str, avatar: str | None = None) -> dict:
    at = _now()
    ttl = int((at + timedelta(days=RETAIN_DAYS)).timestamp())
    h = user_hash(sub)
    sk = f"M#{convos.iso(at)}#" + "".join(secrets.choice(_ALPHABET) for _ in range(4))
    item: dict = {"pk": f"ROOMMSG#{rid}", "sk": sk, "senderHash": h, "name": name, "text": text, "at": convos.iso(at), "ttl": ttl}
    if avatar and avatar in _AVATAR_SLUGS:
        item["avatar"] = avatar
    db.put_item(item)
    db.update_item(f"ROOM#{rid}", "META", {"lastAt": convos.iso(at), "lastPreview": preview(text), "lastName": name,
                                          "lastHash": h, "ttl": ttl})
    msgs = list_messages(rid)
    for old in msgs[:max(0, len(msgs) - MAX_ROOM_MESSAGES)]:
        db.delete_item(old["pk"], old["sk"])
    return item


def message_view(item: dict, sub: str) -> dict:
    av = item.get("avatar")
    return {"id": cursor_of(item), "from": "me" if item.get("senderHash") == user_hash(sub) else "them",
            "name": guard.clean_text(item.get("name") or "Classmate", 24) or "Classmate",
            "avatar": av if av in _AVATAR_SLUGS else None,
            "userId": item.get("senderHash"),
            "text": guard.clean_text(item.get("text") or "", MAX_TEXT), "at": item.get("at")}


# ── Blocks ────────────────────────────────────────────────────────────────────

def blocked_hashes(sub: str) -> set:
    return {i["sk"][len("RMBLOCK#"):] for i in db.query_pk(f"USER#{sub}", "RMBLOCK#")}


def block_hash(sub: str, h: str) -> None:
    db.put_item({"pk": f"USER#{sub}", "sk": f"RMBLOCK#{h}", "at": convos.iso(_now())})


def find_message(rid: str, message_id: str) -> dict | None:
    if not isinstance(message_id, str) or not CURSOR_RE.match(message_id):
        return None
    return db.get_item(f"ROOMMSG#{rid}", f"M#{message_id}")


def unread_count(sub: str, rid: str, st: dict, blocked: set) -> int:
    last = st.get("lastRead") or ""
    me = user_hash(sub)
    return sum(1 for m in list_messages(rid) if cursor_of(m) > last and m.get("senderHash") not in blocked and m.get("senderHash") != me)


# ── Reports ───────────────────────────────────────────────────────────────────

def room_hash8(rid: str) -> str:
    return hashlib.sha256(rid.encode()).hexdigest()[:8]


def delete_user_data(sub: str) -> int:
    n = 0
    for prefix in ("RM#", "RMBLOCK#", "NICK"):
        for it in db.query_pk(f"USER#{sub}", prefix):
            db.delete_item(it["pk"], it["sk"])
            n += 1
    return n
