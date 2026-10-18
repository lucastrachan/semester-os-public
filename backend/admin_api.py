"""
Admin API handlers (staff only).

Entry point: handle(event) -> response dict, or None when the path is not an admin route.
Builder wires it in api.py (see ADMIN.md). Authentication is two layers:
  1. API Gateway's JWT authorizer (staff Cognito pool, its own app client) validates the token.
  2. This module re-checks that the verified claims contain the `admins` group, and that the
     issuer is the staff pool. ADMIN_USER_POOL_ID MUST be set: if it is missing the API fails
     closed (500) rather than skipping the issuer check. Student tokens fail both layers.
Nothing here ever logs or stores a token.
"""
import json
import os
import re
import unicodedata
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, available_timezones

from lib import convos, db, market, util

ADMIN_GROUP = "admins"
AUDIT_PK = "ADMIN_AUDIT"
AUDIT_TTL_DAYS = 90
MAX_BODY_BYTES = 32_000

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$")
MAX_URL = 300
REPORTS_PK = "REPORTS"
BANNED_PK = "BANNED_USERS"
DEMO_REGISTRY_PK = "DEMOACCTS"
MAX_DEMO_ACCOUNTS = 20
COLOR_REVIEW_STATES = ("needs_review", "placeholder")

LMS_TYPES = {"blackboard_ultra", "canvas", "other"}
LMS_CONNECTOR = {"blackboard_ultra": "ical_feed", "canvas": "pending_admin_approval", "other": "none"}
DEFAULT_CATEGORIES = list(market.CATEGORIES)

# Public mailbox providers can never identify a campus.
FREE_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "outlook.com", "hotmail.com", "live.com",
    "msn.com", "icloud.com", "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com", "pm.me",
    "gmx.com", "gmx.net", "mail.com", "zoho.com", "yandex.com", "yandex.ru", "qq.com", "163.com",
    "126.com", "163.net", "sina.com", "naver.com", "hey.com", "fastmail.com", "tutanota.com",
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com", "yopmail.com",
}


class _Bad(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


# ── Entry point ───────────────────────────────────────────────────────────────

def handle(event: dict):
    path = event.get("rawPath", "/")
    if not path.startswith("/admin/"):
        return None
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET").upper()
    try:
        admin = _require_admin(event)

        if path == "/admin/me" and method == "GET":
            return util.ok({"email": admin["email"], "groups": admin["groups"]})
        if path == "/admin/overview" and method == "GET":
            return overview()
        if path == "/admin/campuses" and method == "GET":
            return list_campuses()
        if path == "/admin/campuses" and method == "POST":
            return create_campus(event, admin)
        m = re.fullmatch(r"/admin/campuses/([a-z0-9\-]{1,80})", path)
        if m and method in ("PUT", "PATCH"):
            return edit_campus(event, admin, m.group(1))
        m = re.fullmatch(r"/admin/campuses/([a-z0-9\-]{1,80})/(disable|enable)", path)
        if m and method == "POST":
            return set_campus_disabled(event, admin, m.group(1), m.group(2) == "disable")
        if path == "/admin/blocked-domains" and method == "GET":
            return list_blocked()
        if path == "/admin/blocked-domains" and method == "POST":
            return block_domain(event, admin)
        m = re.fullmatch(r"/admin/blocked-domains/([a-z0-9.\-]{3,100})", path)
        if m and method == "DELETE":
            return unblock_domain(admin, m.group(1))
        if path == "/admin/audit" and method == "GET":
            return list_audit(admin)
        if path == "/admin/reports" and method == "GET":
            return list_reports(event, admin)
        m = re.fullmatch(r"/admin/reports/([a-z]{4,12}\.[a-z0-9]{8}\.[0-9a-f]{16})/resolve", path)
        if m and method == "POST":
            return resolve_report(event, admin, m.group(1))
        m = re.fullmatch(r"/admin/listings/([a-z0-9]{8})/(hide|unhide)", path)
        if m and method == "POST":
            return set_listing_hidden(event, admin, m.group(1), m.group(2) == "hide")
        m = re.fullmatch(r"/admin/conversations/([a-z0-9]{8})/close", path)
        if m and method == "POST":
            return close_conversation(event, admin, m.group(1))
        m = re.fullmatch(r"/admin/users/([A-Za-z0-9\-_:.]{8,128})/(ban|unban)", path)
        if m and method == "POST":
            return ban_user(event, admin, m.group(1)) if m.group(2) == "ban" else unban_user(event, admin, m.group(1))
        m = re.fullmatch(r"/admin/campuses/([a-z0-9\-]{1,80})/color(?:/(approve))?", path)
        if m and method == "POST":
            return approve_color(admin, m.group(1)) if m.group(2) else set_color(event, admin, m.group(1))
        m = re.fullmatch(r"/admin/campuses/([a-z0-9\-]{1,80})/marketplace", path)
        if m and method == "POST":
            return set_marketplace(event, admin, m.group(1))
        if path == "/admin/demo-accounts" and method == "GET":
            return list_demo_accounts(admin)
        if path == "/admin/demo-accounts" and method == "POST":
            return add_demo_account(event, admin)
        m = re.fullmatch(r"/admin/demo-accounts/([0-9a-f]{16})", path)
        if m and method == "DELETE":
            return remove_demo_account(admin, m.group(1))
        return util.error(404, "not_found", "Route not found")
    except _Bad as e:
        return util.error(e.status, e.code, e.message)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _claims(event: dict) -> dict:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"] or {}
    except (KeyError, TypeError):
        return {}


def parse_groups(raw) -> list:
    """HTTP API passes array claims as a string such as '[admins ops]' (or a real list in tests)."""
    if isinstance(raw, (list, tuple)):
        return [str(g) for g in raw]
    s = str(raw or "").strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    return [g for g in re.split(r"[\s,]+", s.replace('"', "")) if g]


def _ctx(event: dict) -> dict:
    http = (event.get("requestContext") or {}).get("http") or {}
    ua = str((event.get("headers") or {}).get("user-agent") or "")
    return {"ip": str(http.get("sourceIp") or "")[:64], "ua": clean_text(ua, 120)}


def _require_admin(event: dict) -> dict:
    claims = _claims(event)
    if not claims.get("sub"):
        raise _Bad(401, "unauthorized", "Missing or invalid token")
    ctx = _ctx(event)
    who = {"sub": str(claims["sub"]), "email": clean_text(claims.get("email") or claims.get("username") or "unknown", 200), **ctx}
    route = f"{(event.get('requestContext') or {}).get('http', {}).get('method', '')} {event.get('rawPath', '')}"[:200]

    def deny(status, code, message, reason):
        try:
            db.put_item(_audit_item(who, "admin.denied", route, {"reason": reason}))
        except Exception:
            print("audit write failed for denied request")  # never block the 403 on the log
        raise _Bad(status, code, message)

    pool = os.environ.get("ADMIN_USER_POOL_ID", "")
    if not pool:  # fail closed: without the pool id we cannot prove the issuer
        print("ADMIN_USER_POOL_ID is not set; refusing all admin requests")
        raise _Bad(500, "misconfigured", "Admin API is not configured")
    if not str(claims.get("iss", "")).endswith("/" + pool):
        deny(403, "forbidden", "Not an admin session", "wrong_issuer")
    groups = parse_groups(claims.get("cognito:groups"))
    if ADMIN_GROUP not in groups:
        deny(403, "forbidden", "Admin access required", "not_in_admins_group")
    return {**who, "groups": groups}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    if len(raw) > MAX_BODY_BYTES:
        raise _Bad(413, "too_large", "Request body too large")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise _Bad(400, "bad_request", "Invalid JSON")
    if not isinstance(data, dict):
        raise _Bad(400, "bad_request", "Body must be a JSON object")
    return data


def _strip(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk")}


def _audit_item(admin: dict, action: str, target: str, detail: dict = None) -> dict:
    now = datetime.now(timezone.utc)
    iso = now.isoformat().replace("+00:00", "Z")
    return {
        "pk": AUDIT_PK,
        "sk": f"{iso}#{util.short_id(6)}",
        "adminEmail": admin["email"],
        "adminSub": admin["sub"],
        "sourceIp": admin.get("ip", ""),
        "userAgent": admin.get("ua", ""),
        "action": action,
        "target": str(target)[:200],
        "detail": util.to_dynamo(detail or {}),
        "at": iso,
        "ttl": int((now + timedelta(days=AUDIT_TTL_DAYS)).timestamp()),
    }


def _audit(admin: dict, action: str, target: str, detail: dict = None) -> None:
    """Audit-only write (reads). If this fails the request fails: no unlogged reads of PII."""
    db.put_item(_audit_item(admin, action, target, detail))


def _put_op(item: dict, condition: str = None) -> dict:
    op = {"TableName": db.table().name, "Item": item}
    if condition:
        op["ConditionExpression"] = condition
    return {"Put": op}


def _update_op(pk: str, sk: str, updates: dict) -> dict:
    names = {f"#f{i}": k for i, k in enumerate(updates)}
    values = {f":v{i}": v for i, v in enumerate(updates.values())}
    return {"Update": {
        "TableName": db.table().name, "Key": {"pk": pk, "sk": sk},
        "UpdateExpression": "SET " + ", ".join(f"#f{i} = :v{i}" for i in range(len(updates))),
        "ExpressionAttributeNames": names, "ExpressionAttributeValues": values,
        "ConditionExpression": "attribute_exists(pk)",
    }}


def _tx(ops: list, audit_item: dict) -> None:
    """Apply the change(s) and the audit item atomically: both happen or neither."""
    try:
        db.table().meta.client.transact_write_items(TransactItems=ops + [_put_op(audit_item)])
    except Exception as e:
        code = (getattr(e, "response", {}) or {}).get("Error", {}).get("Code")
        if code == "TransactionCanceledException":
            raise _Bad(409, "conflict", "The record changed or already exists. Nothing was changed.")
        raise


def _luminance(hex_color: str) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def ink_for(hex_color: str) -> str:
    """Readable text colour on the campus colour: white or near-black, whichever contrasts more."""
    lum = _luminance(hex_color)
    white = 1.05 / (lum + 0.05)
    dark = (lum + 0.05) / (_luminance("#10131A") + 0.05)
    return "#ffffff" if white >= dark else "#10131A"


def _derive_short_name(name: str) -> str:
    stop = {"of", "the", "at", "and", "university", "college", "institute", "technology"}
    initials = "".join(w[0].upper() for w in name.split() if w.lower() not in stop)
    return initials[:8] or name[:4].upper()


# ── Untrusted-text hygiene ────────────────────────────────────────────────────
# Admin-provided names, notes and links are rendered by other apps and may reach prompts and feeds.

def clean_text(value, maxlen: int) -> str:
    """Strip control, format (bidi overrides, zero-width), surrogate and separator characters; collapse spaces."""
    out = []
    for ch in str(value or ""):
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"):
            out.append(" " if ch in "\t\n\r" else "")
        else:
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()[:maxlen]


def valid_https_url(raw, label: str) -> str:
    url = str(raw or "").strip()
    if not url:
        return ""
    bad = _Bad(400, "validation_error", f"{label}: link must be a plain https:// address")
    if len(url) > MAX_URL or clean_text(url, MAX_URL + 1) != url or " " in url:
        raise bad
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or "." not in u.hostname or u.username or u.password or "@" in u.netloc:
        raise bad
    return url


# ── Validation ────────────────────────────────────────────────────────────────

def _valid_domain(raw) -> str:
    d = str(raw or "").lower().strip().lstrip("@").lstrip("*.").rstrip(".")
    if not DOMAIN_RE.match(d) or len(d) > 100:
        raise _Bad(400, "validation_error", f"Invalid domain: {str(raw)[:60]!r}. Use a form like ua.edu")
    if util.normalize_domain(d) in FREE_MAIL_DOMAINS or d in FREE_MAIL_DOMAINS:
        raise _Bad(400, "validation_error", f"{d} is a public mail provider and cannot be a campus domain")
    return d


def _valid_timezone(raw) -> str:
    tz = str(raw or "").strip()
    if not tz or len(tz) > 64 or not re.fullmatch(r"[A-Za-z0-9_+\-/]+", tz):
        raise _Bad(400, "validation_error", "timezone must be an IANA name such as America/Chicago")
    try:
        ZoneInfo(tz)
    except Exception:
        raise _Bad(400, "validation_error", f"Unknown timezone: {tz}")
    return tz


def validate_campus(body: dict, default_name: str = "", default_domains: list = None) -> dict:
    """Return the cleaned campus fields (no ids or keys), or raise _Bad."""
    name = clean_text(body.get("name") or default_name or "", 120)
    if not 2 <= len(name):
        raise _Bad(400, "validation_error", "Campus name must be 2 to 120 characters")

    short = clean_text(body.get("shortName") or "", 40) or _derive_short_name(name)
    if len(short) > 8:
        raise _Bad(400, "validation_error", "shortName must be at most 8 characters")

    raw_domains = body.get("domains")
    if raw_domains is None:
        raw_domains = default_domains or []
    if isinstance(raw_domains, str):
        raw_domains = [d for d in re.split(r"[\s,;]+", raw_domains) if d]
    if not isinstance(raw_domains, list) or not 1 <= len(raw_domains) <= 8:
        raise _Bad(400, "validation_error", "Provide 1 to 8 email domains")
    domains = []
    for d in raw_domains:
        d = _valid_domain(d)
        if d not in domains:
            domains.append(d)

    color = str(body.get("themeColor") or "#1a56db").strip()
    if not HEX_RE.match(color):
        raise _Bad(400, "validation_error", "themeColor must look like #RRGGBB")

    tz = _valid_timezone(body.get("timezone") or "America/Chicago")

    lms_type = str(body.get("lmsType") or "blackboard_ultra")
    if lms_type not in LMS_TYPES:
        raise _Bad(400, "validation_error", f"lmsType must be one of {sorted(LMS_TYPES)}")

    resources = []
    for r in (body.get("tutoringResources") or [])[:10]:
        if not isinstance(r, dict):
            raise _Bad(400, "validation_error", "tutoringResources entries must be objects")
        rname = clean_text(r.get("name"), 120)
        if not rname:
            continue
        url = valid_https_url(r.get("url"), f"Tutoring resource {rname}")
        resources.append({"name": rname, "description": clean_text(r.get("description"), 400), "url": url})

    spots = []
    for s in (body.get("pickupSpots") or [])[:20]:
        s = clean_text(s, 120)
        if s:
            spots.append(s)

    open_net = body.get("openToNetwork", True)
    if not isinstance(open_net, bool):
        raise _Bad(400, "validation_error", "openToNetwork must be true or false")

    return {
        "name": name, "shortName": short, "domains": domains,
        "theme": {"primary": color, "accent": color, "ink": ink_for(color)},
        "timezone": tz,
        "lms": {"type": lms_type, "connector": LMS_CONNECTOR[lms_type]},
        "tutoringResources": resources, "pickupSpots": spots,
        "categories": DEFAULT_CATEGORIES, "ticketPriceCap": True, "openToNetwork": open_net,
    }


# ── Campus creation (atomic, never overwrites) ────────────────────────────────

def _create_tenant(fields: dict, now: str, admin: dict, action: str, target_extra: dict = None) -> str:
    """Write the tenant and one DOMAIN# map per domain in ONE transaction. Each Put carries
    attribute_not_exists(pk), so an existing campus or domain makes the whole thing fail (409)."""
    # The signup gate looks domains up by util.normalize_domain, so the maps are keyed the same way.
    keys = []
    for d in fields["domains"]:
        n = util.normalize_domain(d)
        if n not in keys:
            keys.append(n)
    tenant_id = keys[0].replace(".", "-")

    tenant = util.to_dynamo({"pk": "TENANTS", "sk": f"T#{tenant_id}", "id": tenant_id, **fields,
                             "domains": keys, "createdAt": now})
    items = [_put_op(tenant, "attribute_not_exists(pk)")]
    for n in keys:
        items.append(_put_op({"pk": f"DOMAIN#{n}", "sk": "MAP", "tenantId": tenant_id}, "attribute_not_exists(pk)"))
    detail = {"domains": keys, "name": fields["name"], **(target_extra or {})}
    _tx(items, _audit_item(admin, action, tenant_id, detail))  # tenant, domain maps and audit: one transaction
    return tenant_id


def create_campus(event: dict, admin: dict):
    body = _body(event)
    fields = validate_campus(body)
    for d in fields["domains"]:
        if _is_blocked(d):
            raise _Bad(400, "validation_error", f"{d} is on the blocked domains list")
    tenant_id = _create_tenant(fields, _now(), admin, "campus.create")
    return util.ok({"tenantId": tenant_id, "status": "created"}, 201)


# ── Edit / disable / block ────────────────────────────────────────────────────

def _get_tenant(tenant_id: str) -> dict:
    t = db.get_item("TENANTS", f"T#{tenant_id}")
    if not t:
        raise _Bad(404, "not_found", "Campus not found")
    return t


def edit_campus(event: dict, admin: dict, tenant_id: str):
    """Edit name, short name, colour, timezone, LMS, tutoring, pickup spots, openToNetwork.
    Domains are NOT editable here (they key the signup gate)."""
    tenant = _get_tenant(tenant_id)
    body = _body(event)
    merged = {
        "name": tenant.get("name"), "shortName": tenant.get("shortName"), "domains": tenant.get("domains") or [],
        "themeColor": (tenant.get("theme") or {}).get("primary"), "timezone": tenant.get("timezone"),
        "lmsType": (tenant.get("lms") or {}).get("type"), "tutoringResources": tenant.get("tutoringResources") or [],
        "pickupSpots": tenant.get("pickupSpots") or [], "openToNetwork": tenant.get("openToNetwork", True),
    }
    for k in ("name", "shortName", "themeColor", "timezone", "lmsType", "tutoringResources", "pickupSpots", "openToNetwork"):
        if k in body:
            merged[k] = body[k]
    fields = validate_campus(merged)
    updates = {
        "name": fields["name"], "shortName": fields["shortName"], "theme": fields["theme"],
        "timezone": fields["timezone"], "tutoringResources": util.to_dynamo(fields["tutoringResources"]),
        "pickupSpots": fields["pickupSpots"], "openToNetwork": fields["openToNetwork"],
        "updatedAt": _now(),
    }
    old_lms = (tenant.get("lms") or {}).get("type")
    updates["lms"] = tenant["lms"] if old_lms == fields["lms"]["type"] and tenant.get("lms") else fields["lms"]
    if fields["theme"]["primary"].lower() != str((tenant.get("theme") or {}).get("primary") or "").lower():
        updates.update({"colorStatus": "verified", "colorSource": "admin", "colorConfidence": 1})  # a human chose it
    changed = sorted(k for k in updates if k != "updatedAt" and updates[k] != tenant.get(k))
    _tx([_update_op("TENANTS", f"T#{tenant_id}", updates)], _audit_item(admin, "campus.edit", tenant_id, {"changed": changed}))
    return util.ok({"tenantId": tenant_id, "changed": changed})


def set_campus_disabled(event: dict, admin: dict, tenant_id: str, disable: bool):
    _get_tenant(tenant_id)
    reason = clean_text(_body(event).get("reason"), 200) if disable else ""
    updates = {"disabled": disable, "updatedAt": _now()}
    if disable:
        updates["disabledReason"] = reason
        updates["disabledAt"] = _now()
    _tx([_update_op("TENANTS", f"T#{tenant_id}", updates)],
        _audit_item(admin, "campus.disable" if disable else "campus.enable", tenant_id, {"reason": reason} if disable else {}))
    return util.ok({"tenantId": tenant_id, "disabled": disable})


BLOCK_PK = "BLOCKED_DOMAINS"


def _is_blocked(domain: str) -> bool:
    parts = domain.lower().strip(".").split(".")
    return any(db.get_item(BLOCK_PK, "D#" + ".".join(parts[i:])) for i in range(len(parts) - 1))


def block_domain(event: dict, admin: dict):
    body = _body(event)
    d = str(body.get("domain") or "").lower().strip().lstrip("@").lstrip("*.").rstrip(".")
    if not DOMAIN_RE.match(d) or len(d) > 100:
        raise _Bad(400, "validation_error", "Invalid domain. Use a form like example.edu")
    reason = clean_text(body.get("reason"), 200)
    _tx([_put_op({"pk": BLOCK_PK, "sk": f"D#{d}", "domain": d, "reason": reason,
                  "blockedBy": admin["email"], "blockedAt": _now()})],
        _audit_item(admin, "domain.block", d, {"reason": reason}))
    return util.ok({"domain": d, "blocked": True}, 201)


def unblock_domain(admin: dict, domain: str):
    _tx([{"Delete": {"TableName": db.table().name, "Key": {"pk": BLOCK_PK, "sk": f"D#{domain}"}}}],
        _audit_item(admin, "domain.unblock", domain))
    return util.ok({"domain": domain, "blocked": False})


def list_blocked():
    items = db.query_pk(BLOCK_PK, "D#")
    return util.ok({"domains": sorted((_strip(i) for i in items), key=lambda i: i.get("domain", ""))})


# ── Reports queue and moderation ──────────────────────────────────────────────

LISTING_ID_RE = re.compile(r"^[a-z0-9]{8}$")
SUB_RE = re.compile(r"^[A-Za-z0-9\-_:.]{8,128}$")
REPORT_STATUSES = ("open", "resolved", "all")
RESOLUTIONS = ("dismissed", "actioned")


def _text_only(value, n: int) -> str:
    return clean_text(value, n)


def _report_view(r: dict) -> dict:
    """One report for the admin console. Everything is plain text; user-written fields are re-cleaned."""
    out = {
        "id": r.get("id"), "kind": r.get("kind"), "targetId": r.get("targetId"), "listingId": r.get("listingId"),
        "listingTitle": _text_only(r.get("listingTitle"), 160), "reason": _text_only(r.get("reason"), 20),
        "note": _text_only(r.get("note"), 200), "status": r.get("status", "open"), "createdAt": r.get("createdAt"),
        "reportedSub": r.get("reportedSub") or "", "reportedName": _text_only(r.get("reportedName"), 40),
        "reportedCampus": (r.get("reportedCampus") or {}).get("shortName") or (r.get("reportedCampus") or {}).get("name") or "",
        "reporterRole": r.get("reporterRole"), "demo": bool(r.get("demo")),
        "resolution": r.get("resolution"), "resolutionNote": _text_only(r.get("resolutionNote"), 200),
    }
    if r.get("kind") == "conversation":
        out["evidence"] = [{"from": _text_only(m.get("from"), 10), "text": _text_only(m.get("text"), convos.MAX_MESSAGE),
                            "at": m.get("at")} for m in (r.get("evidence") or [])[-convos.EVIDENCE_MESSAGES:]]
        meta = db.get_item(f"CONVO#{r.get('targetId')}", "META")
        out["conversation"] = {"exists": bool(meta), "status": (meta or {}).get("status"), "closedReason": (meta or {}).get("closedReason")} if meta else {"exists": False}
    else:
        lst = db.get_item(f"LISTING#{r.get('targetId')}", "META")
        out["listing"] = {"exists": True, "title": _text_only(lst.get("title"), 160), "description": _text_only(lst.get("description"), 500),
                          "price": lst.get("price"), "status": lst.get("status", "available"), "hidden": bool(lst.get("flagged"))} if lst else {"exists": False}
        if lst:
            out["listing"]["price"] = float(lst["price"]) if lst.get("price") is not None else None
    return out


def list_reports(event: dict, admin: dict):
    qs = event.get("queryStringParameters") or {}
    status = qs.get("status") or "open"
    if status not in REPORT_STATUSES:
        raise _Bad(400, "validation_error", "status must be open, resolved or all")
    _audit(admin, "report.list", status)   # reports hold other students' messages: reads are logged
    rows = [r for r in db.query_pk(REPORTS_PK, "R#") if status == "all" or r.get("status", "open") == status]
    rows.sort(key=lambda r: r.get("createdAt", ""), reverse=True)
    rows.sort(key=lambda r: 0 if r.get("status", "open") == "open" else 1)
    return util.ok({"reports": [_report_view(r) for r in rows[:100]], "total": len(rows)})


def _find_report(report_id: str) -> dict:
    for r in db.query_pk(REPORTS_PK, "R#"):
        if r.get("id") == report_id:
            return r
    raise _Bad(404, "not_found", "Report not found")


def resolve_report(event: dict, admin: dict, report_id: str):
    body = _body(event)
    resolution = body.get("resolution", "actioned")
    if resolution not in RESOLUTIONS:
        raise _Bad(400, "validation_error", "resolution must be dismissed or actioned")
    note = clean_text(body.get("note"), 200)
    r = _find_report(report_id)
    if r.get("status", "open") != "open":
        raise _Bad(409, "conflict", "This report is already resolved")
    _tx([_update_op(r["pk"], r["sk"], {"status": "resolved", "resolution": resolution, "resolutionNote": note,
                                       "resolvedAt": _now(), "resolvedBy": admin["sub"]})],
        _audit_item(admin, "report.resolve", report_id, {"resolution": resolution, "note": note}))
    return util.ok({"id": report_id, "status": "resolved", "resolution": resolution})


def set_listing_hidden(event: dict, admin: dict, listing_id: str, hide: bool):
    _body(event)
    if not LISTING_ID_RE.match(listing_id):
        raise _Bad(404, "not_found", "Listing not found")
    if not db.get_item(f"LISTING#{listing_id}", "META"):
        raise _Bad(404, "not_found", "Listing not found")
    updates = {"flagged": hide, "adminHidden": hide, "updatedAt": _now()}
    if hide:
        updates["flaggedAt"] = _now()
    _tx([_update_op(f"LISTING#{listing_id}", "META", updates)],
        _audit_item(admin, "listing.hide" if hide else "listing.unhide", listing_id))
    return util.ok({"listingId": listing_id, "hidden": hide})


def close_conversation(event: dict, admin: dict, cid: str):
    _body(event)
    meta = db.get_item(f"CONVO#{cid}", "META") if re.fullmatch(r"[a-z0-9]{8}", cid) else None
    if not meta:
        raise _Bad(404, "not_found", "Conversation not found")
    if meta.get("status") == "closed":
        return util.ok({"conversationId": cid, "closed": True, "alreadyClosed": True})
    ops = [_update_op(f"CONVO#{cid}", "META", {"status": "closed", "closedReason": "admin"})]
    for sub in (meta.get("buyerSub"), meta.get("sellerSub")):
        if sub and db.get_item(f"USER#{sub}", f"CONV#{cid}"):
            ops.append(_update_op(f"USER#{sub}", f"CONV#{cid}", {"status": "closed", "closedReason": "admin"}))
    _tx(ops, _audit_item(admin, "conversation.close", cid, {"listingId": meta.get("listingId")}))
    return util.ok({"conversationId": cid, "closed": True})


def ban_user(event: dict, admin: dict, sub: str):
    body = _body(event)
    reason = clean_text(body.get("reason"), 200)
    if sub == admin["sub"]:
        raise _Bad(400, "validation_error", "You can't ban your own account")
    if not db.get_item(f"USER#{sub}", "PROFILE"):
        raise _Bad(404, "not_found", "User not found")
    _tx([_put_op({"pk": BANNED_PK, "sk": f"U#{sub}", "reason": reason, "by": admin["sub"], "at": _now()}, "attribute_not_exists(pk)")],
        _audit_item(admin, "user.ban", sub, {"reason": reason}))
    # Follow-up (outside the transaction, safe to repeat): remove their live listings and close their chats.
    removed = closed = 0
    for ptr in db.query_pk(f"USER#{sub}", "LISTING#"):
        lid = str(ptr.get("sk", ""))[len("LISTING#"):]
        item = db.get_item(f"LISTING#{lid}", "META") if LISTING_ID_RE.match(lid) else None
        if item and item.get("sellerSub") == sub and item.get("status", "available") != "removed":
            db.update_item(f"LISTING#{lid}", "META", {"status": "removed", "removedAt": _now(), "removedBy": "admin_ban"})
            db.update_item(f"USER#{sub}", ptr["sk"], {"status": "removed"})
            removed += 1
    for ptr in db.query_pk(f"USER#{sub}", "CONV#"):
        if ptr.get("id") and convos.close_conversation(ptr["id"], "banned"):
            closed += 1
    return util.ok({"sub": sub, "banned": True, "listingsRemoved": removed, "conversationsClosed": closed})


def unban_user(event: dict, admin: dict, sub: str):
    _body(event)
    if not db.get_item(BANNED_PK, f"U#{sub}"):
        raise _Bad(404, "not_found", "That user is not banned")
    _tx([{"Delete": {"TableName": db.table().name, "Key": {"pk": BANNED_PK, "sk": f"U#{sub}"}}}],
        _audit_item(admin, "user.unban", sub))
    return util.ok({"sub": sub, "banned": False})


# ── Campus colour review ──────────────────────────────────────────────────────

def approve_color(admin: dict, tenant_id: str):
    t = _get_tenant(tenant_id)
    if not HEX_RE.match(str((t.get("theme") or {}).get("primary") or "")):
        raise _Bad(409, "conflict", "This campus has no colour to approve. Set one instead.")
    _tx([_update_op("TENANTS", f"T#{tenant_id}", {"colorStatus": "verified", "updatedAt": _now()})],
        _audit_item(admin, "campus.color.approve", tenant_id, {"color": t["theme"]["primary"], "was": t.get("colorStatus", "")}))
    return util.ok({"tenantId": tenant_id, "colorStatus": "verified"})


def set_color(event: dict, admin: dict, tenant_id: str):
    t = _get_tenant(tenant_id)
    color = str(_body(event).get("color") or "").strip()
    if not HEX_RE.match(color):
        raise _Bad(400, "validation_error", "color must look like #RRGGBB")
    color = color.lower()
    theme = {"primary": color, "accent": color, "ink": ink_for(color)}
    _tx([_update_op("TENANTS", f"T#{tenant_id}", {"theme": theme, "colorStatus": "verified", "colorSource": "admin",
                                                  "colorConfidence": 1, "updatedAt": _now()})],
        _audit_item(admin, "campus.color.set", tenant_id, {"color": color, "was": (t.get("theme") or {}).get("primary", "")}))
    return util.ok({"tenantId": tenant_id, "theme": theme, "colorStatus": "verified"})


# ── Per-campus marketplace settings ───────────────────────────────────────────

def set_marketplace(event: dict, admin: dict, tenant_id: str):
    """Enabled marketplace categories and the ticket price cap for one campus (MARKETPLACE_V2_API.md section 5)."""
    t = _get_tenant(tenant_id)
    body = _body(event)
    extra = set(body) - {"categories", "ticketPriceCap"}
    if extra or not body:
        raise _Bad(400, "validation_error", "Send categories and/or ticketPriceCap")
    updates = {"updatedAt": _now()}
    if "categories" in body:
        raw = body["categories"]
        if not isinstance(raw, list) or not 1 <= len(raw) <= len(market.CATEGORIES) or not all(isinstance(c, str) for c in raw):
            raise _Bad(400, "validation_error", "categories must be a list of marketplace categories")
        cats = [market.canon_category(c) for c in raw]
        if any(c not in market.CATEGORIES for c in cats) or len(set(cats)) != len(cats):
            raise _Bad(400, "validation_error", f"categories must be unique values from: {', '.join(market.CATEGORIES)}")
        if "books" not in cats:
            raise _Bad(400, "validation_error", "The books category can't be turned off (class book matching needs it)")
        updates["categories"] = [c for c in market.CATEGORIES if c in cats]
    if "ticketPriceCap" in body:
        if not isinstance(body["ticketPriceCap"], bool):
            raise _Bad(400, "validation_error", "ticketPriceCap must be true or false")
        updates["ticketPriceCap"] = body["ticketPriceCap"]
    _tx([_update_op("TENANTS", f"T#{tenant_id}", updates)],
        _audit_item(admin, "campus.marketplace", tenant_id, {k: v for k, v in updates.items() if k != "updatedAt"}))
    return util.ok({"tenantId": tenant_id, "categories": updates.get("categories", market.enabled_categories(t)),
                    "ticketPriceCap": updates.get("ticketPriceCap", market.ticket_cap_on(t))})


# ── Demo accounts (Luca's test students) ──────────────────────────────────────
# Contract with Builder (pre_signup and /me): pk DEMOACCT#{normalised lowercase email}, sk MAP, fields
# tenantId, note, createdAt, createdBy. The registry (pk DEMOACCTS, sk H#{hash}) exists so the console can list them.

EMAIL_RE = re.compile(r"^[a-z0-9._%\-]{1,64}@[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$")


def _email_hash(email: str) -> str:
    import hashlib
    return hashlib.sha256(email.encode()).hexdigest()[:16]


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def add_demo_account(event: dict, admin: dict):
    body = _body(event)
    email = str(body.get("email") or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise _Bad(400, "validation_error", "Enter a plain email address such as name@gmail.com")
    if "+" in email:
        raise _Bad(400, "validation_error", "Plus-alias addresses are not allowed")
    tenant_id = str(body.get("tenantId") or "").strip()
    tenant = db.get_item("TENANTS", f"T#{tenant_id}") if re.fullmatch(r"[a-z0-9\-]{1,80}", tenant_id) else None
    if not tenant:
        raise _Bad(400, "validation_error", "Pick an existing campus")
    if tenant.get("disabled"):
        raise _Bad(400, "validation_error", "That campus is disabled")
    note = clean_text(body.get("note"), 200)
    if len(db.query_pk(DEMO_REGISTRY_PK, "H#")) >= MAX_DEMO_ACCOUNTS:
        raise _Bad(409, "limit_reached", f"At most {MAX_DEMO_ACCOUNTS} demo accounts. Remove one first.")
    h, now = _email_hash(email), _now()
    ops = [
        _put_op({"pk": f"DEMOACCT#{email}", "sk": "MAP", "tenantId": tenant_id, "note": note, "createdAt": now, "createdBy": admin["sub"]},
                "attribute_not_exists(pk)"),
        _put_op({"pk": DEMO_REGISTRY_PK, "sk": f"H#{h}", "emailHash": h, "email": email, "masked": _mask_email(email),
                 "tenantId": tenant_id, "note": note, "createdAt": now, "createdBy": admin["sub"]}, "attribute_not_exists(pk)"),
    ]
    _tx(ops, _audit_item(admin, "demo.add", h, {"email": _mask_email(email), "tenantId": tenant_id}))
    return util.ok({"emailHash": h, "email": email, "masked": _mask_email(email), "tenantId": tenant_id, "note": note}, 201)


def list_demo_accounts(admin: dict):
    rows = sorted(db.query_pk(DEMO_REGISTRY_PK, "H#"), key=lambda r: r.get("createdAt", ""))
    return util.ok({"accounts": [{"emailHash": r.get("emailHash"), "email": r.get("masked"), "tenantId": r.get("tenantId"),
                                  "note": clean_text(r.get("note"), 200), "createdAt": r.get("createdAt")} for r in rows],
                    "max": MAX_DEMO_ACCOUNTS})


def remove_demo_account(admin: dict, email_hash: str):
    reg = db.get_item(DEMO_REGISTRY_PK, f"H#{email_hash}")
    if not reg:
        raise _Bad(404, "not_found", "Demo account not found")
    email = reg["email"]
    ops = [{"Delete": {"TableName": db.table().name, "Key": {"pk": f"DEMOACCT#{email}", "sk": "MAP"}}},
           {"Delete": {"TableName": db.table().name, "Key": {"pk": DEMO_REGISTRY_PK, "sk": f"H#{email_hash}"}}}]
    _tx(ops, _audit_item(admin, "demo.remove", email_hash, {"email": reg.get("masked", "")}))
    return util.ok({"emailHash": email_hash, "removed": True})


# ── Read-only views ───────────────────────────────────────────────────────────

def list_campuses():
    items = db.query_pk("TENANTS", "T#")
    campuses = sorted((_strip(i) for i in items), key=lambda c: c.get("name", "").lower())
    return util.ok({"campuses": campuses})


def overview():
    campuses = db.query_pk("TENANTS", "T#")
    reports = db.query_pk(REPORTS_PK)
    return util.ok({
        "campuses": len(campuses),
        "demoCampuses": sum(1 for c in campuses if c.get("demo")),
        "colorReviews": sum(1 for c in campuses if c.get("colorStatus") in COLOR_REVIEW_STATES),
        "openReports": sum(1 for r in reports if r.get("status") == "open"),
        "demoAccounts": len(db.query_pk(DEMO_REGISTRY_PK, "H#")),
    })


def list_audit(admin: dict):
    _audit(admin, "audit.read", "audit")
    items = db.query_pk(AUDIT_PK)
    items.sort(key=lambda i: i.get("sk", ""), reverse=True)
    return util.ok({"entries": [_strip(i) for i in items[:100]]})


def timezones() -> list:
    return sorted(available_timezones())
