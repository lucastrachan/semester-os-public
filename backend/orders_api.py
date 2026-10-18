"""Mock checkout and Orders (demo-mode only). Contract: ORDERS_API.md.

No real money, no card fields, no payment data. Status flow:
  paid -> handed_over -> completed
  paid -> refunded (buyer cancel or seller decline)
Demo listings have no real seller: paid auto-advances to handed_over at read time.
"""
import json
import re
from datetime import datetime, timezone

from lib import convos, db, limits, market, util
import listings_api as L

_ID_RE = re.compile(r"^[a-z0-9]{8}$")
_ORDERABLE = frozenset({"sell", "free", "service", "ticket"})

limits.USER_LIMITS.setdefault("order", (3, 10))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _to_cents(price) -> int:
    try:
        return max(0, round(float(price or 0) * 100))
    except (TypeError, ValueError):
        return 0


def _effective_status(order: dict) -> str:
    """Demo listings auto-advance paid -> handed_over at read time (no real seller)."""
    st = order.get("status", "paid")
    if order.get("listingIsDemo") and st == "paid":
        return "handed_over"
    return st


def _view(order: dict, sub: str) -> dict:
    is_buyer = order.get("buyerSub") == sub
    snap = order.get("listingSnapshot") or {}
    return {
        "id": order["id"],
        "status": _effective_status(order),
        "timeline": order.get("timeline") or [],
        "listing": {
            "id": order.get("listingId"),
            "title": snap.get("title"),
            "image": snap.get("imageUrl"),
            "campus": snap.get("campusName") or order.get("campus"),
        },
        "counterpart": {
            "name": order.get("sellerDisplay") if is_buyer else order.get("buyerDisplay"),
            "avatar": order.get("sellerAvatar") if is_buyer else order.get("buyerAvatar"),
        },
        "amountCents": order.get("amountCents", 0),
        "method": order.get("method"),
        "note": order.get("note"),
        "demo": True,
        "role": "buying" if is_buyer else "selling",
        "createdAt": order.get("createdAt"),
    }


@L.handled
def create_order(event: dict, sub: str, listing_id: str) -> dict:
    if not _ID_RE.match(listing_id or ""):
        raise L._Bad(404, "not_found", "Listing not found")

    body = {}
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        pass
    if not isinstance(body, dict):
        body = {}

    method = body.get("method")
    if method not in ("pickup", "ship"):
        return util.error(400, "validation_error", "method must be pickup or ship")
    note = str(body.get("note") or "")[:500] or None

    try:
        limits.check_user(db.table(), sub, "order")
    except limits.LimitError as e:
        return limits.error_response(e)

    listing = db.get_item(f"LISTING#{listing_id}", "META")
    if not listing or listing.get("status", "available") != "available":
        raise L._Bad(404, "not_found", "Listing not found or not available")

    if market.kind_of(listing) not in _ORDERABLE:
        return util.error(400, "not_orderable", "This listing type cannot be ordered")

    seller_sub = listing.get("sellerSub") or listing.get("sub") or ""
    if not seller_sub or seller_sub == sub:
        return util.error(400, "own_listing", "You cannot order your own listing")

    sdb, buyer_profile, buyer_tenant = L.viewer(sub)
    visible = L.visible_tenants(buyer_tenant)
    if listing.get("tenantId") not in visible:
        return util.error(400, "not_visible", "This listing is not available on your network")

    seller_profile = db.get_item(f"USER#{seller_sub}", "PROFILE") or {}
    now = _now()
    oid = util.short_id(8)
    amount_cents = _to_cents(listing.get("price"))
    campus_name = listing.get("campusName") or listing.get("tenantId") or ""
    images = listing.get("images") or []

    snapshot = {
        "title": listing.get("title") or "",
        "price": listing.get("price") or "0",
        "amountCents": amount_cents,
        "category": listing.get("category") or "",
        "imageUrl": images[0] if images else None,
        "campusName": campus_name,
    }

    order = {
        "pk": f"ORDER#{oid}",
        "sk": "META",
        "id": oid,
        "listingId": listing_id,
        "listingIsDemo": bool(listing.get("demo")),
        "listingSnapshot": snapshot,
        "buyerSub": sub,
        "sellerSub": seller_sub,
        "buyerHash": convos.user_hash(sub),
        "sellerHash": convos.user_hash(seller_sub),
        "buyerDisplay": market.public_name(buyer_profile),
        "sellerDisplay": listing.get("sellerName") or market.public_name(seller_profile),
        "buyerAvatar": buyer_profile.get("avatar") or None,
        "sellerAvatar": listing.get("sellerAvatar") or None,
        "amountCents": amount_cents,
        "status": "paid",
        "method": method,
        "note": note,
        "payment": {"mode": "demo", "ref": f"DEMO-{oid.upper()}"},
        "timeline": [{"status": "paid", "at": now}],
        "campus": campus_name,
        "createdAt": now,
        "updatedAt": now,
    }

    db.put_item(order)
    db.put_item({"pk": f"USER#{sub}", "sk": f"ORDER#buying#{oid}", "orderId": oid, "at": now})
    db.put_item({"pk": f"USER#{seller_sub}", "sk": f"ORDER#selling#{oid}", "orderId": oid, "at": now})
    db.update_item(f"LISTING#{listing_id}", "META", {"status": "pending"})

    return util.ok({"order": _view(order, sub)})


def patch_order(event: dict, sub: str, order_id: str) -> dict:
    if not _ID_RE.match(order_id or ""):
        return util.error(404, "not_found", "Order not found")

    order = db.get_item(f"ORDER#{order_id}", "META")
    if not order:
        return util.error(404, "not_found", "Order not found")

    is_buyer = order.get("buyerSub") == sub
    is_seller = order.get("sellerSub") == sub
    if not is_buyer and not is_seller:
        return util.error(404, "not_found", "Order not found")

    body = {}
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        pass
    if not isinstance(body, dict):
        body = {}

    action = body.get("action")
    if action not in ("handed_over", "received", "cancel", "decline"):
        return util.error(400, "validation_error", "action must be handed_over, received, cancel, or decline")

    raw_status = order.get("status", "paid")
    eff_status = _effective_status(order)
    now = _now()

    if action == "handed_over":
        if not is_seller:
            return util.error(403, "forbidden", "Only the seller can mark handed over")
        if raw_status != "paid":
            return util.error(409, "wrong_status", f"Cannot mark handed over from status {raw_status!r}")
        new_status = "handed_over"

    elif action == "received":
        if not is_buyer:
            return util.error(403, "forbidden", "Only the buyer can confirm receipt")
        if eff_status != "handed_over":
            return util.error(409, "wrong_status", "Item has not been handed over yet")
        new_status = "completed"
        db.update_item(f"LISTING#{order['listingId']}", "META", {"status": "sold"})

    elif action == "cancel":
        if not is_buyer:
            return util.error(403, "forbidden", "Only the buyer can cancel")
        if eff_status != "paid":
            return util.error(409, "wrong_status", "Can only cancel before handover")
        new_status = "refunded"
        db.update_item(f"LISTING#{order['listingId']}", "META", {"status": "available"})

    elif action == "decline":
        if not is_seller:
            return util.error(403, "forbidden", "Only the seller can decline")
        if raw_status != "paid":
            return util.error(409, "wrong_status", "Can only decline before handover")
        new_status = "refunded"
        db.update_item(f"LISTING#{order['listingId']}", "META", {"status": "available"})

    else:
        return util.error(400, "validation_error", "Unknown action")

    new_timeline = list(order.get("timeline") or []) + [{"status": new_status, "at": now}]
    updated = db.update_item(f"ORDER#{order_id}", "META", {
        "status": new_status,
        "timeline": new_timeline,
        "updatedAt": now,
    })
    return util.ok({"order": _view(updated, sub)})


def list_orders(event: dict, sub: str) -> dict:
    qs = event.get("queryStringParameters") or {}
    role = qs.get("role", "buying")
    if role not in ("buying", "selling"):
        return util.error(400, "validation_error", "role must be buying or selling")

    ptrs = db.query_pk(f"USER#{sub}", f"ORDER#{role}#")
    orders = []
    for ptr in ptrs:
        oid = ptr.get("orderId")
        if not oid:
            continue
        o = db.get_item(f"ORDER#{oid}", "META")
        if o:
            orders.append(_view(o, sub))

    orders.sort(key=lambda o: o.get("createdAt") or "", reverse=True)
    return util.ok({"orders": orders})


def get_order(event: dict, sub: str, order_id: str) -> dict:
    if not _ID_RE.match(order_id or ""):
        return util.error(404, "not_found", "Order not found")

    order = db.get_item(f"ORDER#{order_id}", "META")
    if not order:
        return util.error(404, "not_found", "Order not found")
    if order.get("buyerSub") != sub and order.get("sellerSub") != sub:
        return util.error(404, "not_found", "Order not found")

    return util.ok({"order": _view(order, sub)})
