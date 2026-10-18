"""In-app chat per listing (Phase 8b). Called from api.py with the authenticated `sub`. Contract: MESSAGES_API.md.

Security model:
  * Only the buyer and the seller of the conversation can read or write it. Everyone else (and a missing
    conversation) gets the same 404, so existence is never confirmed.
  * Neither party ever receives the other's email or sub: only a short display name and the campus.
  * Messages are plain text, at most 1000 characters, no links. Clients render them as text. They are never sent
    to a model.
  * Per-user limits per minute and per day, a spam guard, blocks, reports with evidence for the admin queue.
"""
import json
import re

from lib import convos, db, guard, limits, util

import listings_api as L

MAX_NEW_CONVOS_PER_DAY = 30
MAX_MESSAGES_PER_DAY = 200
MAX_REPORTS_PER_DAY = 10

_DEMO_SELLER_SUB = "__demo__"
_DEMO_REPLIES = (
    "Hey! This is a demo listing. Feel free to place an order to try the checkout flow!",
    "Hi there! This listing is set up for demo purposes — go ahead and place an order!",
    "Thanks for reaching out! This is a demo listing. You can order to see the full flow.",
    "Hey! Demo listing here. Try placing an order to test the checkout experience.",
    "Hi! This is a demo item. Place an order and see how the handover flow works.",
)
DEFAULT_PAGE, MAX_PAGE = 50, 100
_ID_RE = re.compile(r"^[a-z0-9]{8}$")
_CURSOR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[0-9:.]{8,16}Z#[a-z0-9]{4}$")


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


def _body(event: dict, allowed: set) -> dict:
    return L._body(event, allowed)


def _check_id(value) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise L._Bad(404, "not_found", "Not found")
    return value


def _load(sub: str, cid: str):
    """The conversation and the caller's role, or the standard 404."""
    _check_id(cid)
    meta = db.get_item(f"CONVO#{cid}", "META")
    role = convos.participant_role(meta, sub)
    if not role:
        raise L._Bad(404, "not_found", "Conversation not found")
    return meta, role


def _campus_ok(meta: dict) -> bool:
    """The listing's campus is still usable for this pair (not disabled; open to the network if it is another campus)."""
    lt = db.get_item("TENANTS", f"T#{meta.get('listingTenantId')}")
    if not lt or lt.get("disabled"):
        return False
    buyer_campus = (meta.get("buyerCampus") or {}).get("id")
    return lt.get("id") == buyer_campus or L.network_visible(lt)


def _reason(meta: dict) -> str | None:
    listing = db.get_item(f"LISTING#{meta['listingId']}", "META")
    return convos.closed_reason(meta, listing, _campus_ok(meta))


def _campus(c) -> dict:
    c = c or {}
    return {"id": c.get("id", ""), "name": guard.clean_text(c.get("name", ""), 120), "shortName": guard.clean_text(c.get("shortName", ""), 12)}


def _last(ptr_or_none: dict | None, role: str):
    if not ptr_or_none or not ptr_or_none.get("lastAt"):
        return None
    frm = ptr_or_none.get("lastFrom")
    return {"from": "system" if frm == "system" else ("me" if frm == role else "them"),
            "text": guard.clean_text(ptr_or_none.get("lastPreview") or "", 90), "at": ptr_or_none.get("lastAt")}


def _num(v):
    if v is None:
        return None
    f = float(v)
    return int(f) if f == int(f) else round(f, 2)


def conversation_view(meta: dict, sub: str, ptr: dict | None, listing: dict | None = None, reason: str | None = None) -> dict:
    role = convos.participant_role(meta, sub)
    other_buyer = role == "seller"
    lst = {"id": meta.get("listingId"), "title": guard.clean_text(meta.get("listingTitle") or "", 160)}
    if listing is not None:
        lst.update(price=_num(listing.get("price")), status=listing.get("status") or "available")
    return {
        "id": meta["id"], "role": role, "listing": lst,
        "other": {"name": guard.clean_text((meta.get("buyerName") if other_buyer else meta.get("sellerName")) or "Student", 24) or "Student",
                  "avatar": (meta.get("buyerAvatar") if other_buyer else meta.get("sellerAvatar")) or None,
                  "id": meta.get("buyerId") if other_buyer else meta.get("sellerId"),
                  "campus": _campus(meta.get("buyerCampus") if other_buyer else meta.get("sellerCampus"))},
        "status": "closed" if reason else "open", "closedReason": reason, "canSend": reason is None,
        "lastMessage": _last(ptr, role), "unread": int((ptr or {}).get("unread") or 0),
        "createdAt": meta.get("createdAt"), "lastMessageAt": meta.get("lastMessageAt") or meta.get("createdAt"),
    }


def _pointer_view(ptr: dict, sub: str) -> dict:
    role = ptr.get("role")
    reason = ptr.get("closedReason") or ("admin" if ptr.get("status") == "closed" else None)
    return {
        "id": ptr.get("id"), "role": role,
        "listing": {"id": ptr.get("listingId"), "title": guard.clean_text(ptr.get("listingTitle") or "", 160)},
        "other": {"name": guard.clean_text(ptr.get("otherName") or "Student", 24) or "Student",
                  "avatar": ptr.get("otherAvatar") or None, "id": ptr.get("otherId"),
                  "campus": _campus(ptr.get("otherCampus"))},
        "status": "closed" if ptr.get("status") == "closed" else "open", "closedReason": reason,
        "canSend": ptr.get("status") != "closed",
        "lastMessage": _last(ptr, role), "unread": int(ptr.get("unread") or 0),
        "createdAt": ptr.get("createdAt"), "lastMessageAt": ptr.get("lastAt") or ptr.get("createdAt"),
    }


def _pointers(sub: str) -> list:
    """The caller's own inbox pointers. `sub` comes from the verified token; the partition key is always USER#{sub}."""
    return [p for p in db.query_pk(f"USER#{sub}", "CONV#") if p.get("pk") == f"USER#{sub}"]


def _my_pointer(sub: str, cid: str):
    return db.get_item(f"USER#{sub}", f"CONV#{cid}")


def _send_checks(sub: str, text: str) -> None:
    limits.check_user(_table(), sub, "message")
    convos.check_spam(sub, text)
    convos.daily_cap(sub, "msgs", MAX_MESSAGES_PER_DAY, f"You've sent {MAX_MESSAGES_PER_DAY} messages today. Try again tomorrow.")


# ── POST /listings/{id}/conversations ─────────────────────────────────────────

@handled
def start_conversation(event: dict, sub: str, listing_id: str):
    sdb, profile, tenant = L.viewer(sub)
    _check_id(listing_id)
    data = _body(event, {"message"})
    text = convos.validate_message(data.get("message"))

    listing = db.get_item(f"LISTING#{listing_id}", "META")
    existing = _existing_for(sub, listing_id)
    if existing:   # an existing chat answers first (a removed listing reads as "closed", not "missing")
        return _add_to_existing(sub, existing, text, created=False)
    tenants = L.visible_tenants(tenant)
    is_demo = bool(listing and listing.get("demo"))
    if not listing or listing.get("tenantId") not in tenants or not L.shown_to_others(listing):
        raise L._Bad(404, "not_found", "Listing not found")
    seller = listing.get("sellerSub") or (_DEMO_SELLER_SUB if is_demo else None)
    if not is_demo:
        if not seller:
            raise L._Bad(400, "demo_listing", "This is a demo listing, so there is no seller to message.")
        if seller == sub:
            raise L._Bad(400, "own_listing", "You can't message your own listing.")
        if convos.is_banned(seller):
            raise L._Bad(404, "not_found", "Listing not found")
        if convos.is_blocked(seller, sub):
            raise L._Bad(403, "cannot_message", "You can't message this seller.")

    _send_checks(sub, text)
    convos.daily_cap(sub, "convs", MAX_NEW_CONVOS_PER_DAY, f"You can start {MAX_NEW_CONVOS_PER_DAY} new chats a day. Try again tomorrow.")

    cid = util.short_id()
    at = convos.now_dt()
    try:
        _table().put_item(Item={"pk": f"USER#{sub}", "sk": f"CVLK#{listing_id}", "cid": cid, "ttl": convos.ttl_epoch(at)},
                          ConditionExpression="attribute_not_exists(pk)")
    except Exception as e:  # two simultaneous starts: the loser joins the winner's conversation
        if not convos._is_conditional_failure(e):
            raise
        winner = _existing_for(sub, listing_id, refresh=False)
        if winner:
            return _add_to_existing(sub, winner, text, created=False)
        raise

    seller_tenant = tenants.get(listing["tenantId"]) or {}
    seller_campus = {"id": listing["tenantId"], "name": seller_tenant.get("name", ""), "shortName": seller_tenant.get("shortName", "")}
    buyer_campus = {"id": tenant["id"], "name": tenant.get("name", ""), "shortName": tenant.get("shortName", "")}
    seller_name = "Demo seller (auto-reply)" if is_demo else (guard.clean_text(listing.get("sellerName") or "", 24).strip() or "Student")
    buyer_name = L.seller_name(profile)
    seller_avatar = listing.get("sellerAvatar") or None
    buyer_avatar = profile.get("avatar") if profile.get("avatar") in L._AVATAR_SLUGS else None
    seller_id = listing.get("sellerId") or convos.user_hash(seller)
    buyer_id = convos.user_hash(sub)
    title = guard.clean_text(listing.get("title") or "", 160)
    ttl = convos.ttl_epoch(at)
    meta = {"pk": f"CONVO#{cid}", "sk": "META", "id": cid, "listingId": listing_id, "listingTitle": title,
            "listingTenantId": listing["tenantId"], "sellerSub": seller, "buyerSub": sub,
            "sellerName": seller_name, "buyerName": buyer_name, "sellerAvatar": seller_avatar, "buyerAvatar": buyer_avatar,
            "sellerId": seller_id, "buyerId": buyer_id,
            "sellerCampus": seller_campus, "buyerCampus": buyer_campus,
            "status": "open", "msgCount": 0, "createdAt": convos.iso(at), "lastMessageAt": convos.iso(at), "ttl": ttl}
    db.put_item(util.to_dynamo(meta))
    for who, role, other_name, other_campus, other_avatar, other_id in (
            (sub, "buyer", seller_name, seller_campus, seller_avatar, seller_id),
            (seller, "seller", buyer_name, buyer_campus, buyer_avatar, buyer_id)):
        db.put_item(util.to_dynamo({"pk": f"USER#{who}", "sk": f"CONV#{cid}", "id": cid, "role": role, "listingId": listing_id,
                                    "listingTitle": title, "otherName": other_name, "otherCampus": other_campus,
                                    "otherAvatar": other_avatar, "otherId": other_id,
                                    "status": "open", "unread": 0, "createdAt": convos.iso(at), "lastAt": convos.iso(at), "ttl": ttl}))
    db.put_item({"pk": f"LISTING#{listing_id}", "sk": f"CONV#{cid}", "cid": cid, "ttl": ttl})
    msg = convos.append_message(cid, meta, "buyer", text, unread_for=("seller",))
    if is_demo:
        reply_idx = sum(ord(c) for c in listing_id) % len(_DEMO_REPLIES)
        convos.append_message(cid, meta, "seller", _DEMO_REPLIES[reply_idx], unread_for=("buyer",))
    fresh = db.get_item(f"CONVO#{cid}", "META") or meta
    return util.ok({"conversation": conversation_view(fresh, sub, _my_pointer(sub, cid)),
                    "messages": [convos.message_view(msg, "buyer")], "created": True}, 201)


def _existing_for(sub: str, listing_id: str, refresh: bool = True):
    link = db.get_item(f"USER#{sub}", f"CVLK#{listing_id}")
    if not link:
        return None
    meta = db.get_item(f"CONVO#{link.get('cid')}", "META")
    if not meta:   # the conversation expired but the key lingered: clear it so a fresh one can start
        if refresh:
            db.delete_item(f"USER#{sub}", f"CVLK#{listing_id}")
        return None
    return meta


def _add_to_existing(sub: str, meta: dict, text: str, created: bool):
    reason = _reason(meta)
    if reason:
        raise L._Bad(409, "conversation_closed", "That conversation is closed.")
    _guard_repeat(meta, "buyer", text)
    _send_checks(sub, text)
    msg = convos.append_message(meta["id"], meta, "buyer", text, unread_for=("seller",))
    return util.ok({"conversation": conversation_view(db.get_item(f"CONVO#{meta['id']}", "META") or meta, sub, _my_pointer(sub, meta["id"])),
                    "messages": [convos.message_view(msg, "buyer")], "created": created}, 200)


def _guard_repeat(meta: dict, role: str, text: str) -> None:
    """The same text as your own previous message in this conversation is rejected (accidental double send or spam)."""
    mine = [m for m in convos.list_messages(meta["id"])[-3:] if m.get("from") == role]
    if mine and convos.norm_text(mine[-1].get("text")) == convos.norm_text(text) and len(convos.norm_text(text)) >= 4:
        raise L._Bad(400, "validation_error", "You just sent that message.")


# ── GET /conversations, /conversations/unread ─────────────────────────────────

@handled
def list_conversations(event: dict, sub: str):
    qs = event.get("queryStringParameters") or {}
    sdb, profile, tenant = L.viewer(sub)
    status = qs.get("status") or "all"
    if status not in ("open", "closed", "all"):
        raise L._Bad(400, "validation_error", "status must be open, closed or all")
    try:
        limit = int(qs.get("limit") or 30)
    except ValueError:
        raise L._Bad(400, "validation_error", "limit must be a number")
    if not 1 <= limit <= 50:
        raise L._Bad(400, "validation_error", "limit must be between 1 and 50")
    ptrs = _pointers(sub)
    ptrs.sort(key=lambda p: p.get("lastAt") or p.get("createdAt") or "", reverse=True)
    views = [_pointer_view(p, sub) for p in ptrs if p.get("id")]
    unread_total = sum(v["unread"] for v in views)
    if status != "all":
        views = [v for v in views if v["status"] == status]
    return util.ok({"conversations": views[:limit], "unreadTotal": unread_total})


@handled
def unread_count(event: dict, sub: str):
    sdb, profile, tenant = L.viewer(sub)
    return util.ok({"unread": sum(int(p.get("unread") or 0) for p in _pointers(sub))})


# ── GET /conversations/{id} ───────────────────────────────────────────────────

@handled
def get_conversation(event: dict, sub: str, cid: str):
    qs = event.get("queryStringParameters") or {}
    L.viewer(sub)
    meta, role = _load(sub, cid)
    after = qs.get("after") or ""
    if after and not _CURSOR_RE.match(after):
        raise L._Bad(400, "validation_error", "after must be a cursor from a previous response")
    try:
        limit = int(qs.get("limit") or DEFAULT_PAGE)
    except ValueError:
        raise L._Bad(400, "validation_error", "limit must be a number")
    if not 1 <= limit <= MAX_PAGE:
        raise L._Bad(400, "validation_error", f"limit must be between 1 and {MAX_PAGE}")

    items = convos.list_messages(cid)
    if after:
        page = [m for m in items if convos.message_cursor(m["sk"]) > after][:limit]
    else:
        page = items[-limit:]
    next_cursor = convos.message_cursor(page[-1]["sk"]) if page else (after or None)

    ptr = _my_pointer(sub, cid)
    if ptr and int(ptr.get("unread") or 0) > 0:
        convos.mark_read(sub, cid)
    listing = db.get_item(f"LISTING#{meta['listingId']}", "META")
    reason = convos.closed_reason(meta, listing, _campus_ok(meta))
    view = conversation_view(meta, sub, ptr, listing=listing, reason=reason)
    view["unread"] = 0  # this call marks it read
    return util.ok({"conversation": view, "messages": [convos.message_view(m, role) for m in page], "nextCursor": next_cursor})


# ── POST /conversations/{id}/messages ─────────────────────────────────────────

@handled
def send_message(event: dict, sub: str, cid: str):
    L.viewer(sub)
    meta, role = _load(sub, cid)
    data = _body(event, {"text"})
    text = convos.validate_message(data.get("text"))
    if _reason(meta):
        raise L._Bad(403, "conversation_closed", "This conversation is closed.")
    _guard_repeat(meta, role, text)
    _send_checks(sub, text)
    other = "seller" if role == "buyer" else "buyer"
    msg = convos.append_message(cid, meta, role, text, unread_for=(other,))
    return util.ok({"message": convos.message_view(msg, role), "canSend": True}, 201)


# ── POST /conversations/{id}/block ────────────────────────────────────────────

@handled
def block_conversation(event: dict, sub: str, cid: str):
    L.viewer(sub)
    meta, role = _load(sub, cid)
    other_sub = meta["sellerSub"] if role == "buyer" else meta["buyerSub"]
    limits.check_user(_table(), sub, "message")
    convos.block_user(sub, other_sub)
    convos.close_conversation(cid, "blocked", blocked_by=sub)
    return util.ok({"blocked": True})


# ── POST /conversations/{id}/report ───────────────────────────────────────────

@handled
def report_conversation(event: dict, sub: str, cid: str):
    L.viewer(sub)
    meta, role = _load(sub, cid)
    data = _body(event, {"reason", "note"})
    reason = data.get("reason")
    if reason not in convos.REPORT_REASONS:
        raise L._Bad(400, "validation_error", f"reason must be one of: {', '.join(convos.REPORT_REASONS)}")
    note = guard.clean_text(data.get("note") or "", 201).replace("\n", " ").strip()
    if len(note) > 200:
        raise L._Bad(400, "validation_error", "note is longer than 200 characters")
    limits.check_user(_table(), sub, "message")
    convos.daily_cap(sub, "msgreports", MAX_REPORTS_PER_DAY, "You've sent a lot of reports today. Try again tomorrow.")

    at = convos.now_dt()
    rh = convos.user_hash(sub)
    other_role = "seller" if role == "buyer" else "buyer"
    evidence = [{"from": m.get("from"), "text": guard.clean_text(m.get("text") or "", convos.MAX_MESSAGE), "at": m.get("at")}
                for m in convos.list_messages(cid)[-convos.EVIDENCE_MESSAGES:]]
    item = {
        "pk": "REPORTS", "sk": convos.report_sk("conversation", cid, rh), "id": convos.new_report_id("conversation", cid, rh),
        "kind": "conversation", "targetId": cid, "listingId": meta["listingId"], "listingTitle": meta.get("listingTitle", ""),
        "reason": reason, "note": note, "reporterRole": role, "reportedRole": other_role,
        "reportedSub": meta["sellerSub"] if role == "buyer" else meta["buyerSub"],
        "reportedName": (meta.get("sellerName") if role == "buyer" else meta.get("buyerName")) or "Student",
        "reportedCampus": (meta.get("sellerCampus") if role == "buyer" else meta.get("buyerCampus")) or {},
        "evidence": evidence, "status": "open", "createdAt": convos.iso(at), "ttl": convos.ttl_epoch(at, convos.REPORT_TTL_DAYS),
    }
    try:
        _table().put_item(Item=util.to_dynamo(item), ConditionExpression="attribute_not_exists(pk)")
    except Exception as e:
        if not convos._is_conditional_failure(e):
            raise
    return util.ok({"reported": True})
