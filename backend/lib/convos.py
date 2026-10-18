"""Storage and rules for in-app chat per listing (Phase 8b). Contract: MESSAGES_API.md.

Layout: CONVO#{cid}/META and CONVO#{cid}/MSG#{iso}#{rand}; per-user inbox pointers USER#{sub}/CONV#{cid} with an
`unread` counter changed by conditional ADD; USER#{buyer}/CVLK#{listing} makes (listing, buyer) unique;
LISTING#{lid}/CONV#{cid} lets a "sold" notice find the chats. Everything expires 90 days after the last message.

Nothing here returns or stores an email. Subs are internal (used only to authorise and to let admins act).
This module does not import the API layer, so listings_api can call it without a cycle.
"""
import hashlib
import re
import secrets
import string
from datetime import datetime, timedelta, timezone

from . import db, guard, util

MAX_MESSAGE = 1000
MAX_MESSAGES = 500
RETAIN_DAYS = 90
REPORT_TTL_DAYS = 180
SPAM_MIN_LENGTH = 15
SPAM_REPEATS_PER_DAY = 3
PREVIEW = 80
EVIDENCE_MESSAGES = 10
REPORT_REASONS = ("spam", "harassment", "scam", "inappropriate", "other")
SOLD_NOTICE = "The seller marked this item as sold."
LINK_RE = re.compile(r"(?i)(?:\b(?:https?|ftp|file|javascript|data|mailto)\s*:|\bwww\s*\.|//[a-z0-9\-]+\.[a-z]{2,}|\b[a-z0-9\-]+\.(?:com|net|org|edu|io|co|me|ly|app|xyz|info|biz|us|gg|link|site|online|dev|ai|ru|cn|tk)\b)")
_ALPHABET = string.ascii_lowercase + string.digits


class MsgError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _table():
    return db.table()


def _is_conditional_failure(e: Exception) -> bool:
    return (getattr(e, "response", None) or {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def ttl_epoch(dt: datetime, days: int = RETAIN_DAYS) -> int:
    return int((dt + timedelta(days=days)).timestamp())


def user_hash(sub: str) -> str:
    return hashlib.sha256(str(sub).encode()).hexdigest()[:16]


# ── Text ──────────────────────────────────────────────────────────────────────

def norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def text_hash(text: str) -> str:
    return hashlib.sha256(norm_text(text).encode()).hexdigest()[:16]


def validate_message(text) -> str:
    """Clean plain text: 1 to 1000 characters, no links. Raises MsgError(400)."""
    if not isinstance(text, str):
        raise MsgError(400, "validation_error", "Write a message first.")
    cleaned = guard.clean_text(text, MAX_MESSAGE + 1)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if not cleaned:
        raise MsgError(400, "validation_error", "Write a message first.")
    if len(cleaned) > MAX_MESSAGE:
        raise MsgError(400, "validation_error", f"Messages can be up to {MAX_MESSAGE} characters.")
    if LINK_RE.search(cleaned):
        raise MsgError(400, "validation_error", "Links aren't allowed in messages. Describe it instead, and meet on campus.")
    return cleaned


def preview(text: str) -> str:
    one = re.sub(r"\s+", " ", str(text or "")).strip()
    return one if len(one) <= PREVIEW else one[:PREVIEW - 1] + "…"


def check_spam(sub: str, text: str) -> None:
    """The same long text more than 3 times a day (anywhere) is spam."""
    n = norm_text(text)
    if len(n) < SPAM_MIN_LENGTH:
        return
    day = now_dt()
    count = db.incr_counter(f"USER#{sub}", f"SPAM#{text_hash(n)}#{day:%Y%m%d}", int(day.timestamp()) + 2 * 86400)
    if count > SPAM_REPEATS_PER_DAY:
        raise MsgError(429, "spam", "You've sent that same message several times. Please write something different.")


def daily_cap(sub: str, name: str, cap: int, message: str) -> None:
    day = now_dt()
    n = db.incr_counter(f"USER#{sub}", f"CAP#{name}#{day:%Y%m%d}", int(day.timestamp()) + 2 * 86400)
    if n > cap:
        raise MsgError(429, "daily_cap", message)


# ── Participants, blocks, bans ────────────────────────────────────────────────

def participant_role(meta: dict | None, sub: str) -> str | None:
    if not meta or not sub or not isinstance(sub, str):
        return None
    if meta.get("buyerSub") == sub:
        return "buyer"
    if meta.get("sellerSub") == sub:
        return "seller"
    return None


def is_banned(sub: str) -> bool:
    return bool(db.get_item("BANNED_USERS", f"U#{sub}"))


def is_blocked(blocker_sub: str, other_sub: str) -> bool:
    return bool(blocker_sub and db.get_item(f"USER#{blocker_sub}", f"BLOCK#{user_hash(other_sub)}"))


def closed_reason(meta: dict, listing: dict | None, campus_ok: bool) -> str | None:
    """Why this conversation cannot take new messages right now, or None. Computed on read, never stored."""
    if meta.get("status") == "closed":
        return meta.get("closedReason") or "admin"
    if not listing or listing.get("status") == "removed":
        return "listing_removed"
    if listing.get("flagged"):
        return "listing_flagged"
    if not campus_ok:
        return "campus_unavailable"
    return None


# ── Writes ────────────────────────────────────────────────────────────────────

def _update(pk: str, sk: str, sets: dict, add: dict = None, cond: str = "attribute_exists(pk)", extra_values: dict = None) -> bool:
    """SET/ADD with a condition. Returns False when the condition fails (item missing or limit reached)."""
    names, values, set_parts, add_parts = {}, dict(extra_values or {}), [], []
    for i, (k, v) in enumerate(sets.items()):
        names[f"#s{i}"], values[f":s{i}"] = k, v
        set_parts.append(f"#s{i} = :s{i}")
    for i, (k, v) in enumerate((add or {}).items()):
        names[f"#a{i}"], values[f":a{i}"] = k, v
        add_parts.append(f"#a{i} :a{i}")
    expr = ("SET " + ", ".join(set_parts) if set_parts else "") + (" ADD " + ", ".join(add_parts) if add_parts else "")
    try:
        _table().update_item(Key={"pk": pk, "sk": sk}, UpdateExpression=expr.strip(), ConditionExpression=cond,
                             ExpressionAttributeNames=names, ExpressionAttributeValues=values)
        return True
    except Exception as e:
        if _is_conditional_failure(e):
            return False
        raise


def new_message_sk(at: datetime) -> str:
    return f"MSG#{iso(at)}#" + "".join(secrets.choice(_ALPHABET) for _ in range(4))


def append_message(cid: str, meta: dict, from_role: str, text: str, unread_for: tuple = ()) -> dict:
    """Store one message and update the conversation and both inboxes.
    from_role is buyer|seller|system; `unread_for` lists the roles whose unread counter goes up.
    The conversation's msgCount is bumped first with a condition, which enforces the 500-message cap."""
    at = now_dt()
    ttl = ttl_epoch(at)
    if not _update(f"CONVO#{cid}", "META", {"lastMessageAt": iso(at), "ttl": ttl}, add={"msgCount": 1},
                   cond="attribute_exists(pk) AND msgCount < :max", extra_values={":max": MAX_MESSAGES}):
        raise MsgError(409, "conversation_full", "This conversation has reached its message limit.")
    sk = new_message_sk(at)
    item = {"pk": f"CONVO#{cid}", "sk": sk, "from": from_role, "text": text, "at": iso(at), "ttl": ttl}
    _table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    for role in ("buyer", "seller"):
        sub = meta.get("buyerSub" if role == "buyer" else "sellerSub")
        sets = {"lastAt": iso(at), "lastPreview": preview(text), "lastFrom": from_role, "ttl": ttl}
        _update(f"USER#{sub}", f"CONV#{cid}", sets, add={"unread": 1} if role in unread_for else None)
    _update(f"LISTING#{meta['listingId']}", f"CONV#{cid}", {"ttl": ttl})
    return item


def message_cursor(sk: str) -> str:
    return sk[len("MSG#"):]


def list_messages(cid: str) -> list:
    return sorted(db.query_pk(f"CONVO#{cid}", "MSG#"), key=lambda m: m["sk"])


def message_view(item: dict, role: str) -> dict:
    frm = item.get("from")
    return {"id": message_cursor(item["sk"]), "from": "system" if frm == "system" else ("me" if frm == role else "them"),
            "text": guard.clean_text(item.get("text") or "", MAX_MESSAGE), "at": item.get("at")}


def mark_read(sub: str, cid: str) -> None:
    _update(f"USER#{sub}", f"CONV#{cid}", {"unread": 0})


def close_conversation(cid: str, reason: str, blocked_by: str | None = None) -> bool:
    """Close for both sides (silently: nobody is told who did it). Returns False if the conversation is gone."""
    meta = db.get_item(f"CONVO#{cid}", "META")
    if not meta:
        return False
    sets = {"status": "closed", "closedReason": reason}
    if blocked_by:
        sets["blockedBy"] = blocked_by
    _update(f"CONVO#{cid}", "META", sets)
    for sub in (meta.get("buyerSub"), meta.get("sellerSub")):
        _update(f"USER#{sub}", f"CONV#{cid}", {"status": "closed", "closedReason": reason})
    return True


def block_user(blocker_sub: str, other_sub: str) -> None:
    db.put_item({"pk": f"USER#{blocker_sub}", "sk": f"BLOCK#{user_hash(other_sub)}", "at": iso(now_dt())})


def notify_listing_sold(listing_id: str) -> int:
    """Called when a seller marks a listing sold: each open conversation gets one automatic notice for the buyer."""
    sent = 0
    for link in db.query_pk(f"LISTING#{listing_id}", "CONV#"):
        cid = link.get("cid")
        meta = db.get_item(f"CONVO#{cid}", "META") if cid else None
        if not meta or meta.get("status") == "closed" or meta.get("soldNotified"):
            continue
        try:
            append_message(cid, meta, "system", SOLD_NOTICE, unread_for=("buyer",))
            db.update_item(f"CONVO#{cid}", "META", {"soldNotified": True})
            sent += 1
        except MsgError:
            continue
    return sent


def delete_conversation(cid: str) -> None:
    meta = db.get_item(f"CONVO#{cid}", "META")
    for m in db.query_pk(f"CONVO#{cid}", "MSG#"):
        db.delete_item(m["pk"], m["sk"])
    if meta:
        for sub in (meta.get("buyerSub"), meta.get("sellerSub")):
            db.delete_item(f"USER#{sub}", f"CONV#{cid}")
        db.delete_item(f"USER#{meta.get('buyerSub')}", f"CVLK#{meta.get('listingId')}")
        db.delete_item(f"LISTING#{meta.get('listingId')}", f"CONV#{cid}")
    db.delete_item(f"CONVO#{cid}", "META")


def delete_user_data(sub: str) -> int:
    """Delete every chat the user is part of (the other person loses it too, by design), then the user's own
    chat bookkeeping: pointers, one-per-listing keys, blocks and counters. Returns how many chats were removed."""
    pk = f"USER#{sub}"
    n = 0
    for ptr in db.query_pk(pk, "CONV#"):
        if ptr.get("id"):
            delete_conversation(ptr["id"])
            n += 1
        db.delete_item(ptr["pk"], ptr["sk"])
    for prefix in ("CVLK#", "BLOCK#", "SPAM#"):
        for it in db.query_pk(pk, prefix):
            db.delete_item(it["pk"], it["sk"])
    for it in db.query_pk(pk, "CAP#"):
        if it["sk"].startswith(("CAP#convs#", "CAP#msgs#", "CAP#msgreports#")):
            db.delete_item(it["pk"], it["sk"])
    return n


def new_report_id(kind: str, target_id: str, reporter_hash: str) -> str:
    return f"{kind}.{target_id}.{reporter_hash}"


def report_sk(kind: str, target_id: str, reporter_hash: str) -> str:
    return f"R#{kind}#{target_id}#{reporter_hash}"
