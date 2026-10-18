"""/listings routes (handoff sections 5, 6, 9; Phase 8). Called from api.py with the authenticated `sub`.

Rules this module enforces (contract: MARKETPLACE_API.md):
  * The campus (tenant) comes from the caller's profile, never from the request.
  * A listing is visible to other campuses only if its tenant is openToNetwork, not disabled, and none of its
    domains is on the blocked list. Sold, removed and flagged listings are visible to their owner only.
  * Only the owner can edit a listing; anyone else (or a demo listing) gets 404 so existence is never confirmed.
  * Seller email and sub are never returned; only a short display name.
  * All text is cleaned with guard.clean_text on write and on read, and is untrusted wherever it is rendered
    or sent to a model. Links are rejected. No payments, no images in this phase.
  * Writes are rate-limited per user (limits.check_user) and there are daily and active caps.
"""
import hashlib
import json
import re
from datetime import datetime, timezone

from lib import convos, db, guard, limits, market, matching, util

BLOCK_PK = "BLOCKED_DOMAINS"
CONDITIONS = ("New", "Like new", "Good", "Acceptable")
_AVATAR_SLUGS = frozenset(f"robot-{n:02d}" for n in range(1, 13))
DEFAULT_CATEGORIES = list(market.CATEGORIES)
REPORT_REASONS = ("spam", "scam", "prohibited", "wrong_info", "other")
SAFETY = "Meet in a public, well-lit campus spot. Payment happens in person, never through this app."

MAX_PRICE = 1000
DAILY_LISTINGS = 10
DAILY_REPORTS = 20
MAX_ACTIVE = 40
MAX_ACTIVE_BY_CATEGORY = {"tickets": 10, "tutoring": 3}
MAX_ACTIVE_WANTED = 10
MAX_RATE = 200
MAX_TICKET_QTY = 10
MAX_EVENT_DAYS = 400
FLAG_AT_REPORTS = 3
PER_TENANT_FETCH = 200
MAX_NETWORK_TENANTS = 50
DEFAULT_LIMIT, MAX_LIMIT = 30, 60
REPORT_TTL_DAYS = 180

_ID_RE = re.compile(r"^[a-z0-9]{8}$")
_LINK_RE = re.compile(r"(?i)(?:\b(?:https?|ftp|file|javascript|data)\s*:|\bwww\s*\.|//[a-z0-9\-]+\.[a-z]{2,})")
_CREATE_FIELDS = {"title", "author", "isbn", "edition", "price", "condition", "category", "courseCode", "description", "pickupSpot",
                  "kind", "tradeFor", "acceptCash", "ticket", "tutoring"}
_PATCH_FIELDS = _CREATE_FIELDS | {"status"}  # `kind` is accepted only to give a clear error
_STATUSES = ("available", "sold", "removed")


class _Bad(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def handled(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except _Bad as e:
            return util.error(e.status, e.code, e.message)
        except limits.LimitError as e:
            return limits.error_response(e)
    wrapper.__name__ = fn.__name__
    return wrapper


def _table():
    return db.table()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_conditional_failure(e: Exception) -> bool:
    return (getattr(e, "response", None) or {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException"


# ── Viewer, tenants, visibility ───────────────────────────────────────────────

def scoped(sub: str) -> guard.UserScopedDB:
    try:
        return guard.UserScopedDB(sub, db, allowed_prefixes=("PROFILE", "COURSE", "LISTING"))
    except guard.ScopeError:
        raise _Bad(401, "unauthorized", "Missing or invalid token")


def viewer(sub: str):
    """(scoped db, profile, tenant) for the caller. 403 when the campus is disabled."""
    sdb = scoped(sub)
    if convos.is_banned(sub):
        raise _Bad(403, "account_restricted", "This account can't use the marketplace.")
    profile = sdb.get("PROFILE")
    if not profile:
        raise _Bad(404, "not_found", "Open the app once first so your profile exists.")
    tenant = db.get_item("TENANTS", f"T#{profile.get('tenantId')}") if profile.get("tenantId") else None
    if not tenant:
        raise _Bad(403, "no_campus", "Your school isn't on Semester OS yet.")
    if tenant.get("disabled"):
        raise _Bad(403, "campus_disabled", "Your campus is currently unavailable.")
    return sdb, profile, tenant


def domain_blocked(domain: str) -> bool:
    parts = str(domain or "").lower().strip(".").split(".")
    return any(db.get_item(BLOCK_PK, "D#" + ".".join(parts[i:])) for i in range(len(parts) - 1))


def network_visible(tenant: dict) -> bool:
    return (tenant.get("openToNetwork") is True and not tenant.get("disabled")
            and not any(domain_blocked(d) for d in tenant.get("domains") or []))


def visible_tenants(own_tenant: dict) -> dict:
    """{tenantId: tenant} for the caller's campus plus every campus whose listings the network may show.

    Loads ALL visible tenants (one DynamoDB query), then caps at MAX_NETWORK_TENANTS by preferring
    campuses with the most recent listing activity so every campus is eventually represented.
    """
    own_id = own_tenant["id"]
    out = {own_id: own_tenant}
    others = []
    for t in db.query_pk("TENANTS", "T#"):
        if t.get("id") and t["id"] != own_id and network_visible(t):
            others.append(t)
    others.sort(key=lambda t: (t.get("lastListingAt") or "", t.get("id") or ""), reverse=True)
    for t in others[:MAX_NETWORK_TENANTS - 1]:
        out[t["id"]] = t
    return out


def gsi_query(index: str, pk_value: str, newest_first: bool = True, limit: int = PER_TENANT_FETCH) -> list:
    """Query gsi1 (tenant listings by createdAt) or gsi2 (listings by ISBN), following pagination up to `limit`."""
    from boto3.dynamodb.conditions import Key
    attr = {"gsi1": "gsi1pk", "gsi2": "gsi2pk"}[index]
    kwargs = {"IndexName": index, "KeyConditionExpression": Key(attr).eq(pk_value), "ScanIndexForward": not newest_first}
    items = []
    while len(items) < limit:
        resp = _table().query(**kwargs)
        items.extend(i for i in resp.get("Items", []) if str(i.get("pk", "")).startswith("LISTING#") and i.get("sk") == "META")
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items[:limit]


def shown_to_others(item: dict) -> bool:
    return item.get("status", "available") == "available" and not item.get("flagged") and not market.is_expired(item)


def is_offer(item: dict) -> bool:
    """Not a wanted post (matching engines only match against things people actually offer)."""
    return market.kind_of(item) != "wanted"


# ── Presentation ──────────────────────────────────────────────────────────────

def _s(v, n: int) -> str:
    return guard.clean_text(v, n).strip() if v else ""


def _num(v):
    if v is None:
        return None
    f = float(v)
    return int(f) if f == int(f) else round(f, 2)


MAX_IMAGES = 4


def images_view(raw) -> list:
    """[{url, alt}] for the read paths: only same-origin '/demo/...' paths or plain https URLs, alt as clean text, at most 4.
    Anything else is dropped. Users cannot set images yet (create and edit reject the field)."""
    out = []
    for im in (raw if isinstance(raw, (list, tuple)) else []):
        url, alt = (im.get("url"), im.get("alt")) if isinstance(im, dict) else (im, "")
        if not isinstance(url, str):
            continue
        url = url.strip()
        ok_demo = re.fullmatch(r"/demo/[A-Za-z0-9._\-]+(?:/[A-Za-z0-9._\-]+)*", url) and ".." not in url
        ok_https = re.fullmatch(r"https://[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?::\d{2,5})?(?:/[A-Za-z0-9._~!$&'()*+,;=:@%/\-]*)?(?:\?[A-Za-z0-9._~!$&'()*+,;=:@%/?\-]*)?", url)
        if len(url) > 300 or not (ok_demo or ok_https):
            continue
        out.append({"url": url, "alt": _s(alt, 120)})
        if len(out) >= MAX_IMAGES:
            break
    return out


def _ticket_view(t):
    if not isinstance(t, dict):
        return None
    return {"event": _s(t.get("event"), 120), "eventAt": t.get("eventAt"), "venue": _s(t.get("venue"), 120),
            "section": _s(t.get("section"), 40), "quantity": int(t.get("quantity") or 1), "faceValue": _num(t.get("faceValue")),
            "transferMethod": t.get("transferMethod") if t.get("transferMethod") in market.TRANSFER_METHODS else "other",
            "externalLink": _s(t.get("externalLink"), 300)}


def _tutoring_view(t):
    if not isinstance(t, dict):
        return None
    return {"subjects": [_s(x, 60) for x in (t.get("subjects") or [])[:5]],
            "courseCodes": [_s(x, 16) for x in (t.get("courseCodes") or [])[:5]],
            "mode": t.get("mode") if t.get("mode") in market.TUTOR_MODES else "in_person",
            "availability": _s(t.get("availability"), 200),
            "standing": t.get("standing") if t.get("standing") in market.STANDINGS else ""}


def view(item: dict, tenants: dict, own_tenant_id: str, sub: str) -> dict:
    """The listing as the API shows it. Never includes sellerSub, email or tenant domains."""
    t = tenants.get(item.get("tenantId")) or {}
    demo = bool(item.get("demo"))
    price = item.get("price")  # int or Decimal from DynamoDB
    return {
        "kind": market.kind_of(item),
        "tradeFor": _s(item.get("tradeFor"), 120),
        "acceptCash": bool(item.get("acceptCash")),
        "ticket": _ticket_view(item.get("ticket")),
        "tutoring": _tutoring_view(item.get("tutoring")),
        "expired": market.is_expired(item),
        "images": images_view(item.get("images")),
        "id": item.get("id"),
        "title": _s(item.get("title"), 160),
        "author": _s(item.get("author"), 120),
        "isbn": item.get("isbn") or None,
        "edition": _s(item.get("edition"), 40),
        "price": _num(price),
        "condition": _s(item.get("condition"), 20),
        "category": market.canon_category(_s(item.get("category"), 40)),
        "courseCode": _s(item.get("courseCode"), 16),
        "description": guard.clean_text(item.get("description") or "", 500).strip(),
        "pickupSpot": _s(item.get("pickupSpot"), 80),
        "status": item.get("status") or "available",
        "flagged": bool(item.get("flagged")),
        "demo": demo,
        "sellerName": _s(item.get("sellerName"), 24) or ("Demo seller" if demo else "Student"),
        "sellerAvatar": item.get("sellerAvatar") if item.get("sellerAvatar") in _AVATAR_SLUGS else None,
        "sellerId": item.get("sellerId") or None,
        "campus": {"id": item.get("tenantId"), "name": t.get("name", ""), "shortName": t.get("shortName", "")},
        "onYourCampus": item.get("tenantId") == own_tenant_id,
        "mine": bool(sub) and item.get("sellerSub") == sub,
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt") or item.get("createdAt"),
    }


def campuses_info(tenants: dict, ids, own_tenant_id: str) -> dict:
    out = {}
    for tid in ids:
        t = tenants.get(tid)
        if t:
            out[tid] = {"id": tid, "name": t.get("name", ""), "shortName": t.get("shortName", ""),
                        "pickupSpots": [_s(p, 80) for p in (t.get("pickupSpots") or [])[:20]],
                        "onYourCampus": tid == own_tenant_id}
    return out


# ── Validation ────────────────────────────────────────────────────────────────

def _body(event: dict, allowed: set) -> dict:
    limits.check_body_size(event, 20_000)
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        raise _Bad(400, "bad_request", "Invalid JSON")
    if not isinstance(data, dict):
        raise _Bad(400, "bad_request", "Body must be a JSON object")
    extra = set(data) - allowed
    if extra:
        raise _Bad(400, "validation_error", f"Unexpected field(s): {', '.join(sorted(str(e)[:30] for e in extra))}")
    return data


def _text(data: dict, key: str, max_len: int, min_len: int = 0, multiline: bool = False) -> str:
    v = data.get(key)
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise _Bad(400, "validation_error", f"{key} must be text")
    cleaned = guard.clean_text(v, max_len + 1)
    if not multiline:
        cleaned = cleaned.replace("\n", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    if len(cleaned) > max_len:
        raise _Bad(400, "validation_error", f"{key} is longer than {max_len} characters")
    if len(cleaned) < min_len:
        raise _Bad(400, "validation_error", f"{key} must be at least {min_len} characters" if min_len > 1 else f"{key} is required")
    if _LINK_RE.search(cleaned):
        raise _Bad(400, "validation_error", f"Links aren't allowed in listings ({key}).")
    return cleaned


def _price(v) -> float | int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not 0 <= v <= MAX_PRICE:
        raise _Bad(400, "validation_error", f"price must be a number from 0 to {MAX_PRICE}")
    r = round(float(v), 2)
    return int(r) if r == int(r) else r


def _category(v, tenant: dict) -> str:
    allowed = market.enabled_categories(tenant)
    cleaned = market.canon_category(guard.clean_text(v, 40)) if isinstance(v, str) else ""
    if cleaned in allowed:
        return cleaned
    raise _Bad(400, "validation_error", f"category must be one of: {', '.join(allowed)}")


def _pickup(data: dict, tenant: dict) -> str:
    spot = _text(data, "pickupSpot", 80)
    spots = [str(s) for s in (tenant.get("pickupSpots") or [])]
    if spot and spots:
        for s in spots:
            if s.lower() == spot.lower():
                return s
        raise _Bad(400, "validation_error", f"pickupSpot must be one of your campus spots: {', '.join(spots)}")
    return spot


def _isbn(v) -> str | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    isbn13 = matching.to_isbn13(v) if isinstance(v, str) else None
    if not isbn13:
        raise _Bad(400, "validation_error", "That ISBN is not valid (check the digits), or leave it blank.")
    return isbn13


def _condition(v) -> str:
    if not isinstance(v, str) or v not in CONDITIONS:
        raise _Bad(400, "validation_error", f"condition must be one of: {', '.join(CONDITIONS)}")
    return v


def _https_link(v) -> str:
    """The one link a listing may carry (ticket.externalLink): plain https, a host with a dot, no credentials."""
    if v is None or v == "":
        return ""
    bad = _Bad(400, "validation_error", "externalLink must be a plain https:// address")
    if not isinstance(v, str):
        raise bad
    url = v.strip()
    if len(url) > 300 or guard.clean_text(url, 301) != url or " " in url or "\\" in url:
        raise bad
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or "." not in u.hostname or u.username or u.password or "@" in u.netloc:
        raise bad
    return url


def _int_in(v, lo: int, hi: int, label: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise _Bad(400, "validation_error", f"{label} must be a whole number from {lo} to {hi}")
    return v


def _money(v, label: str, hi: int = MAX_PRICE):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not 0 <= v <= hi:
        raise _Bad(400, "validation_error", f"{label} must be a number from 0 to {hi}")
    r = round(float(v), 2)
    return int(r) if r == int(r) else r


def _event_time(v) -> str:
    if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z", v.strip()):
        raise _Bad(400, "validation_error", "ticket.eventAt must be an ISO time in UTC such as 2026-10-24T19:00:00Z")
    t = v.strip()
    if len(t) == 17:
        t = t[:16] + ":00Z"
    try:
        when = datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise _Bad(400, "validation_error", "ticket.eventAt is not a real date")
    now = datetime.now(timezone.utc)
    if when <= now:
        raise _Bad(400, "validation_error", "That event has already happened.")
    if (when - now).days > MAX_EVENT_DAYS:
        raise _Bad(400, "validation_error", f"ticket.eventAt can be at most {MAX_EVENT_DAYS} days away")
    return t


def _ticket(obj, kind: str) -> dict:
    if not isinstance(obj, dict):
        raise _Bad(400, "validation_error", "ticket details are required for tickets")
    extra = set(obj) - {"event", "eventAt", "venue", "section", "quantity", "faceValue", "transferMethod", "externalLink"}
    if extra:
        raise _Bad(400, "validation_error", f"Unexpected ticket field(s): {', '.join(sorted(str(e)[:30] for e in extra))}")
    wanted = kind == "wanted"
    out = {"event": _text(obj, "event", 120, min_len=3), "section": _text(obj, "section", 40),
           "externalLink": _https_link(obj.get("externalLink"))}
    if wanted and "eventAt" not in obj:
        out["eventAt"] = None
    else:
        out["eventAt"] = _event_time(obj.get("eventAt"))
    out["venue"] = _text(obj, "venue", 120, min_len=0 if wanted else 2)
    out["quantity"] = _int_in(obj.get("quantity", 1), 1, MAX_TICKET_QTY, "ticket.quantity")
    if wanted and obj.get("faceValue") is None:
        out["faceValue"] = None
    else:
        out["faceValue"] = _money(obj.get("faceValue"), "ticket.faceValue")
    tm = obj.get("transferMethod")
    if tm is None and wanted:
        tm = "other"
    if tm not in market.TRANSFER_METHODS:
        raise _Bad(400, "validation_error", f"ticket.transferMethod must be one of: {', '.join(market.TRANSFER_METHODS)}")
    out["transferMethod"] = tm
    if out["eventAt"] is None:
        out.pop("eventAt")
    if out["faceValue"] is None:
        out.pop("faceValue")
    return out


def _tutoring(obj, tenant: dict) -> dict:
    if not isinstance(obj, dict):
        raise _Bad(400, "validation_error", "tutoring details are required for tutors")
    extra = set(obj) - {"subjects", "courseCodes", "mode", "availability", "standing"}
    if extra:
        raise _Bad(400, "validation_error", f"Unexpected tutoring field(s): {', '.join(sorted(str(e)[:30] for e in extra))}")

    def items(key, lo, hi, maxlen, norm=None):
        raw = obj.get(key, [])
        if not isinstance(raw, list) or len(raw) > hi:
            raise _Bad(400, "validation_error", f"tutoring.{key} must be a list of at most {hi}")
        out = []
        for x in raw:
            if not isinstance(x, str):
                raise _Bad(400, "validation_error", f"tutoring.{key} entries must be text")
            c = _text({"v": x}, "v", maxlen, min_len=2)
            c = norm(c) if norm else c
            if c and c not in out:
                out.append(c)
        if len(out) < lo:
            raise _Bad(400, "validation_error", f"tutoring.{key} needs at least {lo} entry")
        return out

    mode = obj.get("mode", "in_person")
    if mode not in market.TUTOR_MODES:
        raise _Bad(400, "validation_error", f"tutoring.mode must be one of: {', '.join(market.TUTOR_MODES)}")
    standing = obj.get("standing", "")
    if standing not in market.STANDINGS:
        raise _Bad(400, "validation_error", f"tutoring.standing must be one of: {', '.join(s for s in market.STANDINGS if s)} or empty")
    return {"subjects": items("subjects", 1, 5, 60), "courseCodes": items("courseCodes", 0, 5, 24, matching.normalize_course_code),
            "mode": mode, "availability": _text(obj, "availability", 200), "standing": standing}


def validate_fields(data: dict, tenant: dict, partial: bool, existing: dict = None) -> dict:
    """Clean and validate listing fields. Create: `partial=False`. Edit: `partial=True` with the stored item as `existing`
    (only the keys present in `data` are validated, but the per-kind rules are checked on the merged result)."""
    out = {}
    existing = existing or {}
    need = lambda k: (not partial) or k in data
    if partial and "kind" in data and data["kind"] != market.kind_of(existing):
        raise _Bad(400, "validation_error", "A listing's kind can't be changed. Post a new listing instead.")
    kind = market.kind_of(existing) if partial else data.get("kind", "sell")
    if kind not in market.KINDS:
        raise _Bad(400, "validation_error", f"kind must be one of: {', '.join(market.KINDS)}")
    if not partial:
        out["kind"] = kind

    old_cat = market.canon_category(existing.get("category")) if partial else ""
    if need("title"):
        out["title"] = _text(data, "title", 160, min_len=3)
    if need("category"):
        cat = market.canon_category(data.get("category")) if isinstance(data.get("category"), str) else ""
        if partial and cat == old_cat:
            out["category"] = cat   # unchanged: stays valid even if the campus has since turned it off
        else:
            out["category"] = _category(data.get("category"), tenant)
            if partial and ("tickets" in (cat, old_cat) or "tutoring" in (cat, old_cat)):
                raise _Bad(400, "validation_error", "Tickets and tutoring listings can't change category. Post a new listing instead.")
    cat = out.get("category") or old_cat

    if kind == "service" and cat != "tutoring":
        raise _Bad(400, "validation_error", "Services must be in the tutoring category")
    if cat == "tutoring" and kind not in ("service", "wanted"):
        raise _Bad(400, "validation_error", "Tutoring listings must be the service kind (or a wanted post)")

    # condition: required for goods you sell, trade or give away
    if "condition" in data and data["condition"] not in (None, ""):
        out["condition"] = _condition(data["condition"])
    elif "condition" in data:
        out["condition"] = ""
    final_cond = out["condition"] if "condition" in out else existing.get("condition", "")
    if not final_cond and kind in ("sell", "trade", "free") and cat in market.GOODS:
        raise _Bad(400, "validation_error", f"condition must be one of: {', '.join(CONDITIONS)}")

    # price per kind
    if kind == "free":
        if "price" in data and data["price"] not in (None, 0, 0.0):
            raise _Bad(400, "validation_error", "Free listings can't have a price")
        if not partial:
            out["price"] = 0
    elif kind == "sell":
        if need("price"):
            out["price"] = _price(data.get("price"))   # 0 stays allowed (old behaviour: 0 = free)
    elif kind == "trade":
        if "price" in data or not partial:
            out["price"] = _price(data.get("price", 0))
    elif kind == "wanted":
        if "price" in data and data["price"] is not None:
            out["price"] = _price(data["price"])
        elif "price" in data or not partial:
            out["price"] = None
    elif kind == "service":
        if need("price"):
            out["price"] = _money(data.get("price"), "price (hourly rate)", MAX_RATE)

    # trade fields
    for k in ("tradeFor", "acceptCash"):
        if k in data and kind != "trade":
            raise _Bad(400, "validation_error", f"{k} only applies to trade listings")
    if kind == "trade":
        if need("tradeFor"):
            out["tradeFor"] = _text(data, "tradeFor", 120, min_len=3)
        if "acceptCash" in data:
            if not isinstance(data["acceptCash"], bool):
                raise _Bad(400, "validation_error", "acceptCash must be true or false")
            out["acceptCash"] = data["acceptCash"]
        final_cash = out.get("acceptCash", existing.get("acceptCash", False))
        final_price = out["price"] if "price" in out else existing.get("price", 0)
        if final_cash and not (final_price and float(final_price) > 0):
            raise _Bad(400, "validation_error", "Set a cash price if you also accept cash")

    if "author" in data:
        out["author"] = _text(data, "author", 120)
    if "edition" in data:
        out["edition"] = _text(data, "edition", 40)
    if "isbn" in data:
        out["isbn"] = _isbn(data["isbn"])
    if "courseCode" in data:
        out["courseCode"] = matching.normalize_course_code(_text(data, "courseCode", 24))
    if "description" in data:
        out["description"] = _text(data, "description", 500, multiline=True)
    if "pickupSpot" in data:
        out["pickupSpot"] = _pickup(data, tenant)

    # tickets
    if "ticket" in data and cat != "tickets":
        raise _Bad(400, "validation_error", "ticket details only apply to the tickets category")
    if cat == "tickets":
        if "ticket" in data or not partial:
            if data.get("ticket") is None and kind == "wanted":
                raise _Bad(400, "validation_error", "ticket.event is required")
            out["ticket"] = _ticket(data.get("ticket"), kind)
        ticket = out.get("ticket") or existing.get("ticket") or {}
        price = out["price"] if "price" in out else existing.get("price")
        if market.ticket_cap_on(tenant) and kind in ("sell", "trade") and price is not None and ticket.get("faceValue") is not None \
                and float(price) > float(ticket["faceValue"]):
            fv = _num(ticket["faceValue"])
            raise _Bad(400, "validation_error", f"Tickets can't be listed above face value (${fv}).")

    # tutoring
    if "tutoring" in data and cat != "tutoring":
        raise _Bad(400, "validation_error", "tutoring details only apply to the tutoring category")
    if cat == "tutoring":
        if "tutoring" in data or (not partial and kind == "service"):
            out["tutoring"] = _tutoring(data.get("tutoring"), tenant)
        elif not partial and kind == "wanted":
            out["tutoring"] = None
        if kind == "service" and not (out.get("tutoring") or existing.get("tutoring")):
            raise _Bad(400, "validation_error", "tutoring details are required for tutors")
    return out


def seller_name(profile: dict) -> str:
    """'FirstName L.' from profile.displayName (shared helper: lib/market.public_name). Never email-derived."""
    return market.public_name(profile)


# ── GET /listings ─────────────────────────────────────────────────────────────

@handled
def list_listings(event: dict, sub: str):
    qs = event.get("queryStringParameters") or {}
    sdb, profile, tenant = viewer(sub)
    scope = qs.get("scope") or "campus"
    if scope not in ("campus", "network", "mine"):
        raise _Bad(400, "validation_error", "scope must be campus, network or mine")
    try:
        limit = int(qs.get("limit") or DEFAULT_LIMIT)
    except ValueError:
        raise _Bad(400, "validation_error", "limit must be a number")
    if not 1 <= limit <= MAX_LIMIT:
        raise _Bad(400, "validation_error", f"limit must be between 1 and {MAX_LIMIT}")
    q = guard.clean_text(qs.get("q") or "", 81).strip()
    if len(q) > 80:
        raise _Bad(400, "validation_error", "q is too long")
    isbn = None
    if qs.get("isbn"):
        isbn = matching.to_isbn13(qs["isbn"])
        if not isbn:
            raise _Bad(400, "validation_error", "isbn is not valid")
    category = market.canon_category(guard.clean_text(qs.get("category") or "", 40))
    if category and category not in market.CATEGORIES:
        raise _Bad(400, "validation_error", f"category must be one of: {', '.join(market.CATEGORIES)}")
    kind = guard.clean_text(qs.get("kind") or "", 12).strip().lower()
    if kind and kind not in market.KINDS:
        raise _Bad(400, "validation_error", f"kind must be one of: {', '.join(market.KINDS)}")
    price_min = _qs_price(qs, "priceMin")
    price_max = _qs_price(qs, "priceMax")
    if price_min is not None and price_max is not None and price_min > price_max:
        raise _Bad(400, "validation_error", "priceMin is more than priceMax")
    condition = (qs.get("condition") or "").strip()
    if condition and condition not in CONDITIONS:
        raise _Bad(400, "validation_error", f"condition must be one of: {', '.join(CONDITIONS)}")
    course = matching.normalize_course_code(qs["courseCode"]) if qs.get("courseCode") else ""
    before = qs.get("before") or ""
    if before and not re.fullmatch(r"\d{4}-\d{2}-\d{2}T[0-9:.]{8,16}Z", before):
        raise _Bad(400, "validation_error", "before must be a createdAt value from a previous page")

    own_id = tenant["id"]
    tenants = visible_tenants(tenant) if scope == "network" else {own_id: tenant}

    if scope == "mine":
        pointers = sorted(sdb.query("LISTING#"), key=lambda p: p.get("createdAt", ""), reverse=True)[:MAX_LIMIT * 2]
        items = [db.get_item(f"LISTING#{p['id']}", "META") for p in pointers if _ID_RE.match(str(p.get("id")))]
        items = [i for i in items if i and i.get("sellerSub") == sub and i.get("status") != "removed"]
        tenants = {**tenants}
    elif isbn:
        items = [i for i in gsi_query("gsi2", f"ISBN#{isbn}") if i.get("tenantId") in tenants]
        items = [i for i in items if shown_to_others(i)]
    else:
        items = []
        for tid in tenants:
            items.extend(i for i in gsi_query("gsi1", f"TENANT#{tid}#LISTINGS") if shown_to_others(i))

    out = []
    for it in items:
        if category and market.canon_category(it.get("category")) != category:
            continue
        if kind and market.kind_of(it) != kind:
            continue
        if not kind and scope != "mine" and market.kind_of(it) not in market.BROWSE_KINDS:
            continue   # wanted posts only show with kind=wanted
        if (price_min is not None or price_max is not None):
            pr = it.get("price")
            if pr is None or (price_min is not None and float(pr) < price_min) or (price_max is not None and float(pr) > price_max):
                continue
        if condition and it.get("condition") != condition:
            continue
        if course and course != matching.normalize_course_code(it.get("courseCode")) and                 course not in [matching.normalize_course_code(c) for c in ((it.get("tutoring") or {}).get("courseCodes") or [])]:
            continue
        if q and not matching.search_match(q, it):
            continue
        if before and str(it.get("createdAt", "")) >= before:
            continue
        out.append(it)
    out.sort(key=lambda i: (str(i.get("createdAt", "")), str(i.get("id", ""))), reverse=True)
    page = out[:limit]
    next_before = page[-1].get("createdAt") if len(out) > limit and page else None

    if scope == "mine":  # make sure the campus record of my own listings is available for rendering
        tenants = {own_id: tenant}
    return util.ok({
        "listings": [view(i, tenants, own_id, sub) for i in page],
        "campuses": campuses_info(tenants, {i.get("tenantId") for i in page} | {own_id}, own_id),
        "campus": {"id": own_id, "name": tenant.get("name", ""), "shortName": tenant.get("shortName", ""),
                   "pickupSpots": [_s(p, 80) for p in (tenant.get("pickupSpots") or [])[:20]],
                   "categories": market.enabled_categories(tenant), "ticketPriceCap": market.ticket_cap_on(tenant)},
        "kinds": list(market.KINDS),
        "safety": SAFETY,
        "nextBefore": next_before,
    })


# ── POST /listings ────────────────────────────────────────────────────────────

def _qs_price(qs: dict, key: str):
    raw = qs.get(key)
    if raw in (None, ""):
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise _Bad(400, "validation_error", f"{key} must be a number")
    if not 0 <= v <= MAX_PRICE or v != v:
        raise _Bad(400, "validation_error", f"{key} must be between 0 and {MAX_PRICE}")
    return v


def _cap(sub: str, name: str, cap: int, message: str) -> None:
    now = datetime.now(timezone.utc)
    n = db.incr_counter(f"USER#{sub}", f"CAP#{name}#{now:%Y%m%d}", int(now.timestamp()) + 2 * 86400)
    if n > cap:
        raise _Bad(429, "daily_cap", message)


@handled
def create_listing(event: dict, sub: str):
    sdb, profile, tenant = viewer(sub)
    data = _body(event, _CREATE_FIELDS)
    fields = validate_fields(data, tenant, partial=False)
    limits.check_user(_table(), sub, "listing")
    pointers = sdb.query("LISTING#")
    active = [p for p in pointers if p.get("status", "available") == "available"]
    if len(active) >= MAX_ACTIVE:
        raise _Bad(409, "limit", f"You already have {MAX_ACTIVE} active listings. Mark some as sold or remove them first.")
    if fields["kind"] == "wanted" and sum(1 for p in active if p.get("kind") == "wanted") >= MAX_ACTIVE_WANTED:
        raise _Bad(409, "limit", f"You already have {MAX_ACTIVE_WANTED} active wanted posts. Close some first.")
    cap = MAX_ACTIVE_BY_CATEGORY.get(fields["category"])
    if cap and sum(1 for p in active if p.get("category") == fields["category"] and p.get("kind") != "wanted") >= cap             and fields["kind"] != "wanted":
        raise _Bad(409, "limit", f"You already have {cap} active {fields['category']} listings. Close one first.")
    _cap(sub, "listings", DAILY_LISTINGS, f"You can post {DAILY_LISTINGS} new listings a day. Try again tomorrow.")

    listing_id = util.short_id()
    now = _now()
    tenant_id = tenant["id"]
    item = {
        "pk": f"LISTING#{listing_id}", "sk": "META", "id": listing_id, "tenantId": tenant_id,
        "sellerSub": sub, "sellerName": seller_name(profile),
        "sellerAvatar": profile.get("avatar") if profile.get("avatar") in _AVATAR_SLUGS else None,
        "sellerId": convos.user_hash(sub),
        "title": fields["title"], "author": fields.get("author", ""), "edition": fields.get("edition", ""),
        "isbn": fields.get("isbn"), "price": fields.get("price"), "condition": fields.get("condition", ""),
        "category": fields["category"], "courseCode": fields.get("courseCode", ""),
        "description": fields.get("description", ""), "pickupSpot": fields.get("pickupSpot", ""),
        "status": "available", "createdAt": now, "updatedAt": now,
        "kind": fields["kind"], "images": [],
        "gsi1pk": f"TENANT#{tenant_id}#LISTINGS", "gsi1sk": now,
    }
    for k in ("tradeFor", "acceptCash", "ticket", "tutoring"):
        if fields.get(k) not in (None, "", False):
            item[k] = fields[k]
    if item["price"] is None:
        item.pop("price")
    if item["isbn"]:
        item["gsi2pk"], item["gsi2sk"] = f"ISBN#{item['isbn']}", f"{tenant_id}#{listing_id}"
    else:
        item.pop("isbn")
    db.put_item(util.to_dynamo(item))
    sdb.put(f"LISTING#{listing_id}", {"id": listing_id, "createdAt": now, "status": "available", "kind": fields["kind"], "category": fields["category"]})
    db.update_item("TENANTS", f"T#{tenant_id}", {"lastListingAt": now})
    return util.ok({"listing": view(item, {tenant_id: tenant}, tenant_id, sub)}, 201)


# ── PATCH /listings/{id} ──────────────────────────────────────────────────────

def _update_item(pk: str, sk: str, sets: dict, removes: list, owner_sub: str) -> None:
    """SET / REMOVE with a database-level ownership check (belt and braces on top of the read check)."""
    names, values, set_parts, rem_parts = {}, {":owner": owner_sub}, [], []
    for i, (k, v) in enumerate(sets.items()):
        names[f"#s{i}"], values[f":s{i}"] = k, v
        set_parts.append(f"#s{i} = :s{i}")
    for i, k in enumerate(removes):
        names[f"#r{i}"] = k
        rem_parts.append(f"#r{i}")
    expr = ("SET " + ", ".join(set_parts) if set_parts else "") + (" REMOVE " + ", ".join(rem_parts) if rem_parts else "")
    try:
        _table().update_item(Key={"pk": pk, "sk": sk}, UpdateExpression=expr.strip(),
                             ConditionExpression="attribute_exists(pk) AND sellerSub = :owner",
                             ExpressionAttributeNames=names, ExpressionAttributeValues=values)
    except Exception as e:
        if _is_conditional_failure(e):
            raise _Bad(404, "not_found", "Listing not found")
        raise


@handled
def update_listing(event: dict, sub: str, listing_id: str):
    sdb, profile, tenant = viewer(sub)
    if not _ID_RE.match(listing_id or ""):
        raise _Bad(404, "not_found", "Listing not found")
    item = db.get_item(f"LISTING#{listing_id}", "META")
    if not item or item.get("sellerSub") != sub:
        raise _Bad(404, "not_found", "Listing not found")  # same answer for "not yours" and "does not exist"
    data = _body(event, _PATCH_FIELDS)
    if not data:
        raise _Bad(400, "validation_error", "Nothing to change")

    listing_tenant = db.get_item("TENANTS", f"T#{item.get('tenantId')}") or tenant
    fields = validate_fields({k: v for k, v in data.items() if k != "status"}, listing_tenant, partial=True, existing=item)
    if "status" in data:
        if data["status"] not in _STATUSES:
            raise _Bad(400, "validation_error", f"status must be one of: {', '.join(_STATUSES)}")
        fields["status"] = data["status"]

    sets, removes = {}, []
    for k, v in fields.items():
        if k == "isbn":
            if v is None:
                if item.get("isbn"):
                    removes += ["isbn", "gsi2pk", "gsi2sk"]
            elif v != item.get("isbn"):
                sets.update({"isbn": v, "gsi2pk": f"ISBN#{v}", "gsi2sk": f"{item['tenantId']}#{listing_id}"})
        elif item.get(k) != v:
            sets[k] = v
    if not sets and not removes:
        return util.ok({"listing": view(item, {item["tenantId"]: listing_tenant}, tenant["id"], sub)})

    limits.check_user(_table(), sub, "listing")
    sets["updatedAt"] = _now()
    _update_item(f"LISTING#{listing_id}", "META", util.to_dynamo(sets), removes, sub)
    if "status" in sets:
        db.update_item(f"USER#{sub}", f"LISTING#{listing_id}", {"status": sets["status"]})
    fresh = db.get_item(f"LISTING#{listing_id}", "META") or {**item, **sets}
    if sets.get("status") == "sold" and item.get("status") != "sold":
        try:
            convos.notify_listing_sold(listing_id)   # automatic notice in the buyers' open chats; never fails the edit
        except Exception:
            print("sold notice failed")
    return util.ok({"listing": view(fresh, {fresh["tenantId"]: listing_tenant}, tenant["id"], sub)})


def _queue_report(item: dict, reporter_hash: str, reason: str, note: str, now) -> None:
    """Also put the report in the admin queue (REPORTS partition) so staff see it without scanning listings."""
    lid = item["id"]
    t = db.get_item("TENANTS", f"T#{item.get('tenantId')}") or {}
    entry = {
        "pk": "REPORTS", "sk": convos.report_sk("listing", lid, reporter_hash), "id": convos.new_report_id("listing", lid, reporter_hash),
        "kind": "listing", "targetId": lid, "listingId": lid, "listingTitle": _s(item.get("title"), 160),
        "reason": reason, "note": note, "reportedSub": item.get("sellerSub") or "", "reportedName": item.get("sellerName") or "",
        "reportedCampus": {"id": item.get("tenantId"), "name": t.get("name", ""), "shortName": t.get("shortName", "")},
        "demo": bool(item.get("demo")), "status": "open", "createdAt": now.isoformat().replace("+00:00", "Z"),
        "ttl": int(now.timestamp()) + convos.REPORT_TTL_DAYS * 86400,
    }
    try:
        _table().put_item(Item=entry, ConditionExpression="attribute_not_exists(pk)")
    except Exception as e:
        if not _is_conditional_failure(e):
            raise


# ── POST /listings/{id}/report ────────────────────────────────────────────────

@handled
def report_listing(event: dict, sub: str, listing_id: str):
    sdb, profile, tenant = viewer(sub)
    if not _ID_RE.match(listing_id or ""):
        raise _Bad(404, "not_found", "Listing not found")
    data = _body(event, {"reason", "note"})
    reason = data.get("reason")
    if reason not in REPORT_REASONS:
        raise _Bad(400, "validation_error", f"reason must be one of: {', '.join(REPORT_REASONS)}")
    note = guard.clean_text(data.get("note") or "", 201).replace("\n", " ").strip()
    if len(note) > 200:
        raise _Bad(400, "validation_error", "note is longer than 200 characters")

    item = db.get_item(f"LISTING#{listing_id}", "META")
    tenants = visible_tenants(tenant)
    if not item or item.get("tenantId") not in tenants or item.get("status", "available") == "removed":
        raise _Bad(404, "not_found", "Listing not found")
    if item.get("sellerSub") == sub:
        raise _Bad(400, "validation_error", "You can't report your own listing.")

    limits.check_user(_table(), sub, "report")
    _cap(sub, "reports", DAILY_REPORTS, "You've sent a lot of reports today. Try again tomorrow.")
    reporter = hashlib.sha256(sub.encode()).hexdigest()[:16]
    now = datetime.now(timezone.utc)
    try:
        _table().put_item(Item={
            "pk": f"LISTING#{listing_id}", "sk": f"REPORT#{reporter}", "reason": reason, "note": note,
            "createdAt": now.isoformat().replace("+00:00", "Z"), "ttl": int(now.timestamp()) + REPORT_TTL_DAYS * 86400,
        }, ConditionExpression="attribute_not_exists(pk)")
    except Exception as e:
        if not _is_conditional_failure(e):
            raise
        return util.ok({"reported": True})  # already reported by this person: accepted, counted once
    _queue_report(item, reporter, reason, note, now)
    if len(db.query_pk(f"LISTING#{listing_id}", "REPORT#")) >= FLAG_AT_REPORTS and not item.get("flagged"):
        db.update_item(f"LISTING#{listing_id}", "META", {"flagged": True, "flaggedAt": _now()})
    return util.ok({"reported": True})
