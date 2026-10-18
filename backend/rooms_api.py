"""Class group chats ("rooms"). Called from api.py with the authenticated `sub`. Contract: ROOMS_API.md.

Security model:
  * Membership is computed from the caller's own classes on their own campus. A non-member (or unknown room, or a
    room on another campus) gets the same 404. Enrollment is NOT verified: every room says `verified: false`.
  * Nobody receives anyone's email, real name or sub: only a nickname (default "Classmate NNNN").
  * Plain text only (500 chars), no links, no @, no phone/ID numbers; per-user rate limits; spam guard; blocks;
    reports with evidence into the admin REPORTS queue; admin can close a room; banned users and disabled campuses 403.
  * Message text is never sent to a model.
"""
import re

from lib import convos, db, guard, limits, rooms, util

import listings_api as L

MAX_REPORTS_PER_DAY = 10
DEFAULT_PAGE, MAX_PAGE = 50, 100

_RID = r"([a-z0-9-]{1,40}\.[A-Za-z0-9-]{1,20}\.[A-Z0-9]{2,12})"
_ROOM_RE = re.compile(rf"^/rooms/{_RID}$")
_ROOM_SUB_RE = re.compile(rf"^/rooms/{_RID}/(messages|info|mute|unmute|leave|rejoin|report|block)$")


def _table():
    return db.table()


def handled(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (L._Bad, convos.MsgError) as e:
            return util.error(e.status, e.code, e.message)
        except limits.LimitError as e:
            return limits.error_response(e)
    wrapper.__name__ = fn.__name__
    return wrapper


def _campus(tenant: dict) -> dict:
    return {"id": tenant.get("id", ""), "shortName": guard.clean_text(tenant.get("shortName", ""), 12)}


def _load(sub: str, rid: str):
    """(profile, tenant, room info, settings) for a room the caller belongs to, or the standard 404."""
    sdb, profile, tenant = L.viewer(sub)
    if not rooms.ROOM_ID_RE.match(rid or ""):
        raise L._Bad(404, "not_found", "Room not found")
    mine = rooms.my_rooms(sub, tenant["id"])
    if rid not in mine:
        raise L._Bad(404, "not_found", "Room not found")
    return tenant, mine[rid], rooms.settings(sub, rid)


def _view(sub: str, tenant: dict, info: dict, st: dict, blocked: set, with_unread: bool = True) -> dict:
    rid = info["id"]
    meta = db.get_item(f"ROOM#{rid}", "META") or {}
    last = None
    if meta.get("lastAt") and meta.get("lastHash") not in blocked:
        last = {"from": "me" if meta.get("lastHash") == rooms.user_hash(sub) else "them",
                "name": guard.clean_text(meta.get("lastName") or "Classmate", 24) or "Classmate",
                "text": guard.clean_text(meta.get("lastPreview") or "", rooms.PREVIEW), "at": meta["lastAt"]}
    closed = rooms.is_closed(rid)
    left = bool(st.get("left"))
    unread = 0 if (left or st.get("muted") or not with_unread) else rooms.unread_count(sub, rid, st, blocked)
    return {"id": rid, "code": info["code"], "displayCode": info["displayCode"], "title": info["title"], "term": info["term"],
            "campus": _campus(tenant), "verified": False, "memberCount": rooms.member_count(rid),
            "muted": bool(st.get("muted")), "left": left, "closed": closed, "canSend": not closed and not left,
            "lastMessage": last, "unread": unread, "lastMessageAt": meta.get("lastAt")}


def _page_args(qs: dict):
    after = qs.get("after") or ""
    if after and not rooms.CURSOR_RE.match(after):
        raise L._Bad(400, "validation_error", "after must be a cursor from a previous response")
    try:
        limit = int(qs.get("limit") or DEFAULT_PAGE)
    except ValueError:
        raise L._Bad(400, "validation_error", "limit must be a number")
    if not 1 <= limit <= MAX_PAGE:
        raise L._Bad(400, "validation_error", f"limit must be between 1 and {MAX_PAGE}")
    return after, limit


# ── Nickname ──────────────────────────────────────────────────────────────────

@handled
def get_nickname(event: dict, sub: str):
    L.viewer(sub)
    nick, is_default, avatar = rooms.get_nickname(sub)
    return util.ok({"nickname": nick, "isDefault": is_default, "avatar": avatar})


@handled
def patch_nickname(event: dict, sub: str):
    L.viewer(sub)
    data = L._body(event, {"nickname", "avatar"})
    if "nickname" not in data and "avatar" not in data:
        raise L._Bad(400, "validation_error", "nickname or avatar is required")
    avatar_raw = data.get("avatar")
    if "avatar" in data and avatar_raw not in rooms._AVATAR_SLUGS and avatar_raw is not None:
        raise L._Bad(400, "validation_error", "avatar must be robot-01 through robot-12")
    nick, is_default, avatar = rooms.set_nickname(sub, data.get("nickname"), avatar=avatar_raw)
    return util.ok({"nickname": nick, "isDefault": is_default, "avatar": avatar})


# ── GET /rooms ────────────────────────────────────────────────────────────────

@handled
def list_rooms(event: dict, sub: str):
    qs = event.get("queryStringParameters") or {}
    sdb, profile, tenant = L.viewer(sub)
    include_left = str(qs.get("includeLeft") or "").lower() == "true"
    blocked = rooms.blocked_hashes(sub)
    views = []
    for rid, info in rooms.my_rooms(sub, tenant["id"]).items():
        st = rooms.settings(sub, rid)
        if st.get("left") and not include_left:
            continue
        if not st.get("counted") and not st.get("left"):
            st = rooms.ensure_counted(sub, rid, st)
        views.append(_view(sub, tenant, info, st, blocked))
    views.sort(key=lambda v: v["code"])
    views.sort(key=lambda v: v["lastMessageAt"] or "", reverse=True)
    return util.ok({"rooms": views, "unreadTotal": sum(v["unread"] for v in views)})


# ── GET /rooms/{id}/info ──────────────────────────────────────────────────────

@handled
def room_info(event: dict, sub: str, rid: str):
    tenant, info, st = _load(sub, rid)
    v = _view(sub, tenant, info, st, rooms.blocked_hashes(sub))
    return util.ok({"room": v, "info": {
        "code": info["displayCode"], "title": info["title"], "campusShortName": v["campus"]["shortName"],
        "memberCount": v["memberCount"], "verified": False,
        "notice": "Classmates who added this class. Enrollment is not verified.",
        "safetyTips": list(rooms.SAFETY_TIPS),
        "rules": {"maxChars": rooms.MAX_TEXT, "perMinute": rooms.PER_MINUTE, "perDay": rooms.PER_DAY}}})


# ── GET /rooms/{id}/messages ──────────────────────────────────────────────────

@handled
def get_messages(event: dict, sub: str, rid: str):
    qs = event.get("queryStringParameters") or {}
    tenant, info, st = _load(sub, rid)
    after, limit = _page_args(qs)
    if st.get("left"):
        raise L._Bad(403, "room_left", "You left this chat. Rejoin to read it.")
    st = rooms.ensure_counted(sub, rid, st)
    blocked = rooms.blocked_hashes(sub)
    items = [m for m in rooms.list_messages(rid) if m.get("senderHash") not in blocked]
    page = [m for m in items if rooms.cursor_of(m) > after][:limit] if after else items[-limit:]
    newest_all = rooms.list_messages(rid)
    # mark read up to the newest message seen (including hidden ones, so a block does not leave a stale badge)
    if page:
        rooms.mark_read(sub, rid, rooms.cursor_of(page[-1]))
        if not after and newest_all:
            rooms.mark_read(sub, rid, rooms.cursor_of(newest_all[-1]))
    elif newest_all and rooms.cursor_of(newest_all[-1]) > (st.get("lastRead") or ""):
        rooms.mark_read(sub, rid, rooms.cursor_of(newest_all[-1]))
    v = _view(sub, tenant, info, st, blocked, with_unread=False)
    v["unread"] = 0
    next_cursor = rooms.cursor_of(page[-1]) if page else (after or None)
    return util.ok({"room": v, "messages": [rooms.message_view(m, sub) for m in page], "nextCursor": next_cursor})


# ── POST /rooms/{id}/messages ─────────────────────────────────────────────────

@handled
def send_message(event: dict, sub: str, rid: str):
    tenant, info, st = _load(sub, rid)
    data = L._body(event, {"text"})
    text = rooms.validate_text(data.get("text"))
    if st.get("left"):
        raise L._Bad(403, "room_left", "You left this chat. Rejoin to post.")
    if rooms.is_closed(rid):
        raise L._Bad(403, "room_closed", "This chat is closed.")
    rooms.check_repeat(rid, sub, text)
    limits.check_user(_table(), sub, "room")
    convos.check_spam(sub, text)
    rooms.ensure_counted(sub, rid, st)
    name, _, avatar = rooms.get_nickname(sub)
    item = rooms.add_message(rid, sub, name, text, avatar)
    rooms.mark_read(sub, rid, rooms.cursor_of(item))
    return util.ok({"message": rooms.message_view(item, sub), "canSend": True}, 201)


# ── mute / unmute / leave / rejoin ────────────────────────────────────────────

@handled
def room_action(event: dict, sub: str, rid: str, action: str):
    _load(sub, rid)
    if action == "mute":
        rooms.set_flag(sub, rid, muted=True)
        return util.ok({"muted": True})
    if action == "unmute":
        rooms.set_flag(sub, rid, muted=False)
        return util.ok({"muted": False})
    if action == "leave":
        rooms.leave(sub, rid)
        return util.ok({"left": True})
    rooms.rejoin(sub, rid)
    return util.ok({"left": False})


# ── POST /rooms/{id}/block ────────────────────────────────────────────────────

@handled
def block_sender(event: dict, sub: str, rid: str):
    _load(sub, rid)
    data = L._body(event, {"messageId"})
    msg = rooms.find_message(rid, data.get("messageId"))
    if not msg:
        raise L._Bad(400, "validation_error", "That message wasn't found.")
    if msg.get("senderHash") == rooms.user_hash(sub):
        raise L._Bad(400, "validation_error", "You can't block yourself.")
    limits.check_user(_table(), sub, "default")
    rooms.block_hash(sub, msg["senderHash"])
    return util.ok({"blocked": True})


# ── POST /rooms/{id}/report ───────────────────────────────────────────────────

@handled
def report_room(event: dict, sub: str, rid: str):
    tenant, info, st = _load(sub, rid)
    data = L._body(event, {"reason", "note", "messageId"})
    reason = data.get("reason")
    if reason not in rooms.REPORT_REASONS:
        raise L._Bad(400, "validation_error", f"reason must be one of: {', '.join(rooms.REPORT_REASONS)}")
    note = guard.clean_text(data.get("note") or "", 201).replace("\n", " ").strip()
    if len(note) > 200:
        raise L._Bad(400, "validation_error", "note is longer than 200 characters")
    target = None
    if data.get("messageId") not in (None, ""):
        target = rooms.find_message(rid, data.get("messageId"))
        if not target:
            raise L._Bad(400, "validation_error", "That message wasn't found.")
    limits.check_user(_table(), sub, "default")
    convos.daily_cap(sub, "roomreports", MAX_REPORTS_PER_DAY, "You've sent a lot of reports today. Try again tomorrow.")

    at = convos.now_dt()
    rh, h8 = rooms.user_hash(sub), rooms.room_hash8(rid)
    evidence = [{"from": guard.clean_text(m.get("name") or "Classmate", 24), "text": guard.clean_text(m.get("text") or "", rooms.MAX_TEXT),
                 "at": m.get("at")} for m in rooms.list_messages(rid)[-rooms.EVIDENCE:]]
    item = {
        "pk": "REPORTS", "sk": convos.report_sk("room", h8, rh), "id": convos.new_report_id("room", h8, rh),
        "kind": "room", "targetId": h8, "roomId": rid, "listingId": "", "listingTitle": f"{info['displayCode']} ({info['term']})",
        "reason": reason, "note": note, "reporterRole": "member", "reportedRole": "member",
        "reportedSub": "", "reportedName": "", "reportedCampus": _campus(tenant),
        "evidence": evidence, "status": "open", "createdAt": convos.iso(at), "ttl": convos.ttl_epoch(at, convos.REPORT_TTL_DAYS),
    }
    if target:
        item["reportedName"] = guard.clean_text(target.get("name") or "Classmate", 24)
        item["reportedHash"] = target.get("senderHash")
        item["reportedMessage"] = guard.clean_text(target.get("text") or "", rooms.MAX_TEXT)
    try:
        _table().put_item(Item=util.to_dynamo(item), ConditionExpression="attribute_not_exists(pk)")
    except Exception as e:
        if not convos._is_conditional_failure(e):
            raise
    return util.ok({"reported": True})


# ── Router for api.py ─────────────────────────────────────────────────────────

def handle(event: dict, sub: str, path: str, method: str):
    """Returns a response, or None when the path is not a rooms route."""
    if path == "/me/nickname":
        if method == "GET":
            return get_nickname(event, sub)
        if method == "PATCH":
            return patch_nickname(event, sub)
        return None
    if path == "/rooms" and method == "GET":
        return list_rooms(event, sub)
    m = _ROOM_SUB_RE.match(path)
    if not m:
        return None
    rid, what = m.group(1), m.group(2)
    if what == "messages":
        return get_messages(event, sub, rid) if method == "GET" else send_message(event, sub, rid) if method == "POST" else None
    if what == "info":
        return room_info(event, sub, rid) if method == "GET" else None
    if method != "POST":
        return None
    if what in ("mute", "unmute", "leave", "rejoin"):
        return room_action(event, sub, rid, what)
    return block_sender(event, sub, rid) if what == "block" else report_room(event, sub, rid)
