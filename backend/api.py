import json
import os
import re
from datetime import datetime, timezone
from lib import db, limits, util
from lib.color_utils import ink as _ink
from lib.registry import edu_root, lookup as registry_lookup
import admin_api
import assignments_api
import books_api
import calendar_api
import chat_api
import courses_api
import feed_api
import history_api
import listings_api
import market_api
import master_api
import materials_api
import memory_api
import messages_api
import orders_api
import rooms_api


# school_colors.json: verified brand colors for auto-created campuses only (keyed by root domain)
def _load_colors() -> dict:
    path = os.path.join(os.path.dirname(__file__), "data", "school_colors.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

_SCHOOL_COLORS = _load_colors()

# Deterministic placeholder palette (passes AA contrast against white ink)
_PALETTE = [
    "#1F3A93", "#8E44AD", "#27AE60", "#2980B9",
    "#C0392B", "#D35400", "#16A085", "#2C3E50",
    "#3498DB", "#884EA0", "#1E8449", "#922B21",
]


def _derive_color(name: str) -> str:
    h = 0
    for c in name:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return _PALETTE[h % len(_PALETTE)]


def _short_name(name: str) -> str:
    stop = {"of", "the", "at", "in", "and", "for", "a", "an"}
    words = name.split()
    initials = "".join(w[0].upper() for w in words if w.lower() not in stop and w[0].isalpha())
    return initials[:4] if initials else name[:4].upper()


def _tenant_id_from_root(root: str) -> str:
    """Deterministic tenant ID from domain root: ua.edu -> ua-edu"""
    return root.replace(".", "-")


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET").upper()
    path = event.get("rawPath", "/")

    try:
        # ── Admin (separate staff pool; authorised at API Gateway, group re-checked in admin_api) ──
        if path.startswith("/admin/"):
            return admin_api.handle(event) or util.error(404, "not_found", "Route not found")

        # ── Public ────────────────────────────────────────────────────────────
        if path == "/public/tenants" and method == "GET":
            return get_tenants()

        if path == "/public/resolve" and method == "GET":
            return resolve_domain(event)

        # ── Calendar feed (public, no JWT) ────────────────────────────────────
        if path.startswith("/cal/") and method == "GET":
            return calendar_api.get_feed(event)

        # ── Protected (JWT required) ──────────────────────────────────────────
        sub = _get_sub(event)

        if path == "/me" and method in ("GET", "POST"):
            return get_me(event, sub)

        if path == "/me" and method == "PATCH":
            return patch_me(event, sub)

        # master agent: /briefing/*, /chat/master, /agents, /activity (None when the route is not its own)
        r = master_api.handle(event, sub, path, method)
        if r is not None:
            return r

        r = history_api.handle(event, sub, path, method)
        if r is not None:
            return r

        r = memory_api.handle(event, sub, path, method)
        if r is not None:
            return r

        r = materials_api.handle(event, sub, path, method)
        if r is not None:
            return r

        r = feed_api.handle(event, sub, path, method)
        if r is not None:
            return r

        if path.startswith("/rooms") or path == "/me/nickname":
            r = rooms_api.handle(event, sub, path, method)
            if r is not None:
                return r

        if path == "/courses" and method == "POST":
            return courses_api.create_course(event, sub)
        if path == "/courses" and method == "GET":
            return courses_api.list_courses(sub, event)
        if path == "/courses/archived" and method == "GET":
            return courses_api.list_courses(sub, {"queryStringParameters": {"archived": "true"}})
        m = re.fullmatch(r"/courses/([a-z0-9]{8})", path)
        if m and method == "GET":
            return courses_api.get_course(sub, m.group(1))
        if m and method == "PATCH":
            return courses_api.patch_course(sub, m.group(1), event)
        if m and method == "DELETE":
            return courses_api.delete_course(sub, m.group(1))

        m = re.fullmatch(r"/courses/([a-z0-9]+)/chat(/undo)?", path)
        if m and method == "POST":
            return chat_api.handle(event, sub, m.group(1), undo=bool(m.group(2)))

        if path == "/assignments" and method == "GET":
            return assignments_api.list_assignments(event, sub)
        if path == "/assignments" and method == "POST":
            return assignments_api.create_assignment(event, sub)
        m = re.fullmatch(r"/assignments/([a-z0-9]{8})", path)
        if m and method == "PATCH":
            return assignments_api.update_assignment(event, sub, m.group(1))
        if path == "/me/calendar-token/rotate" and method == "POST":
            return calendar_api.rotate_token(event, sub)

        if path == "/listings/for-you" and method == "GET":
            return market_api.for_you(event, sub)
        m = re.fullmatch(r"/courses/([a-z0-9]{8})/tutors", path)
        if m and method == "GET":
            return market_api.tutors_for_course(event, sub, m.group(1))

        if path == "/listings" and method == "GET":
            return listings_api.list_listings(event, sub)
        if path == "/listings" and method == "POST":
            return listings_api.create_listing(event, sub)
        m = re.fullmatch(r"/listings/([a-z0-9]{8})", path)
        if m and method == "PATCH":
            return listings_api.update_listing(event, sub, m.group(1))
        m = re.fullmatch(r"/listings/([a-z0-9]{8})/orders", path)
        if m and method == "POST":
            return orders_api.create_order(event, sub, m.group(1))
        m = re.fullmatch(r"/listings/([a-z0-9]{8})/report", path)
        if m and method == "POST":
            return listings_api.report_listing(event, sub, m.group(1))
        m = re.fullmatch(r"/listings/([a-z0-9]{8})/conversations", path)
        if m and method == "POST":
            return messages_api.start_conversation(event, sub, m.group(1))

        if path == "/orders" and method == "GET":
            return orders_api.list_orders(event, sub)
        m = re.fullmatch(r"/orders/([a-z0-9]{8})", path)
        if m and method == "GET":
            return orders_api.get_order(event, sub, m.group(1))
        if m and method == "PATCH":
            return orders_api.patch_order(event, sub, m.group(1))

        if path == "/books/matches" and method == "GET":
            return books_api.get_matches(event, sub)

        if path == "/conversations" and method == "GET":
            return messages_api.list_conversations(event, sub)
        if path == "/conversations/unread" and method == "GET":
            return messages_api.unread_count(event, sub)
        m = re.fullmatch(r"/conversations/([a-z0-9]{8})", path)
        if m and method == "GET":
            return messages_api.get_conversation(event, sub, m.group(1))
        m = re.fullmatch(r"/conversations/([a-z0-9]{8})/(messages|block|report)", path)
        if m and method == "POST":
            action = m.group(2)
            cid = m.group(1)
            if action == "messages":
                return messages_api.send_message(event, sub, cid)
            if action == "block":
                return messages_api.block_conversation(event, sub, cid)
            return messages_api.report_conversation(event, sub, cid)

        return util.error(404, "not_found", "Route not found")

    except limits.LimitError as e:
        return limits.error_response(e)
    except _AuthError:
        return util.error(401, "unauthorized", "Missing or invalid token")
    except Exception as e:
        print(f"Unhandled error: {e}")
        import traceback; traceback.print_exc()
        return util.error(500, "internal_error", "An internal error occurred")


# ── Public ────────────────────────────────────────────────────────────────────

def get_tenants():
    items = db.query_pk("TENANTS")
    tenants = [_strip_keys(i) for i in items if i.get("sk", "").startswith("T#")]
    return util.ok({"tenants": tenants})


def resolve_domain(event):
    """GET /public/resolve?domain=ua.edu
    Returns school name, theme and colorStatus for a known .edu domain.
    Returns 404 for non-.edu or completely unknown domains (not even in registry).
    Rate-limited per IP to prevent enumeration.
    """
    qs = event.get("queryStringParameters") or {}
    domain = (qs.get("domain") or "").strip().lower()
    if not domain:
        return util.error(400, "bad_request", "domain is required")

    limits.check_ip(db.table(), limits.client_ip(event), bucket="resolve")

    root = edu_root(domain)
    if not root:
        return util.error(404, "not_found", "Not found")

    if db.get_item("BLOCKED_DOMAINS", f"D#{root}"):
        return util.error(404, "not_found", "Not found")

    # Check if a live campus exists
    domain_map = db.get_item(f"DOMAIN#{root}", "MAP")
    if domain_map:
        tenant = db.get_item("TENANTS", f"T#{domain_map['tenantId']}")
        if tenant and not tenant.get("disabled"):
            theme = tenant.get("theme") or {}
            return util.ok({
                "found": True,
                "name": tenant.get("name"),
                "theme": theme,
                "colorStatus": tenant.get("colorStatus", "verified"),
            })

    # Not a live campus yet — check the registry
    entry = registry_lookup(root)
    if not entry:
        return util.error(404, "not_found", "Not found")

    # School is in registry but has no campus yet — return what we know
    color_entry = _SCHOOL_COLORS.get(root)
    if color_entry:
        primary = color_entry["primary"]
        color_status = "verified"
    else:
        primary = _derive_color(entry["name"])
        color_status = "placeholder"
    return util.ok({
        "found": True,
        "name": entry["name"],
        "theme": {"primary": primary, "ink": _ink(primary)},
        "colorStatus": color_status,
    })


# ── Protected ─────────────────────────────────────────────────────────────────

def get_me(event, sub: str):
    from botocore.exceptions import ClientError

    # Banned user check
    if db.get_item("BANNED_USERS", f"U#{sub}"):
        return util.error(403, "account_restricted", "This account has been restricted.")

    email = _get_email(event)
    domain = email.split("@")[-1].lower().strip()

    # Optional timezone from request body (POST /me)
    tz = None
    if event.get("requestContext", {}).get("http", {}).get("method", "GET").upper() == "POST":
        try:
            body = json.loads(event.get("body") or "{}")
            tz_raw = body.get("tz") if isinstance(body, dict) else None
            if isinstance(tz_raw, str) and tz_raw.strip():
                import zoneinfo
                try:
                    zoneinfo.ZoneInfo(tz_raw.strip())
                    tz = tz_raw.strip()
                except (zoneinfo.ZoneInfoNotFoundError, KeyError):
                    pass
        except (json.JSONDecodeError, Exception):
            pass

    # Demo account: DEMOACCT#{email} / MAP carries the tenantId to use
    demo_item = db.get_item(f"DEMOACCT#{email.lower()}", "MAP")
    if demo_item:
        tenant_id = demo_item["tenantId"]
        tenant = db.get_item("TENANTS", f"T#{tenant_id}")
        if not tenant:
            return util.error(403, "no_campus", "Demo campus not found.")
        if tenant.get("disabled"):
            return util.error(403, "campus_disabled", "This campus is currently unavailable.")
        return _build_me_response(event, sub, email, tenant, tenant_id)

    # .edu path — lazy campus creation
    root = edu_root(domain)
    if not root:
        return util.error(403, "account_not_enabled", "This account is not enabled. Contact support if you think this is an error.")

    if db.get_item("BLOCKED_DOMAINS", f"D#{root}"):
        return util.error(403, "domain_paused", f"Signups from {root} are temporarily paused. Contact support if you think this is an error.")

    domain_map = db.get_item(f"DOMAIN#{root}", "MAP")
    if domain_map:
        tenant_id = domain_map["tenantId"]
        tenant = db.get_item("TENANTS", f"T#{tenant_id}")
        if tenant and tenant.get("disabled"):
            return util.error(403, "campus_disabled", "This campus is currently unavailable.")
    else:
        # First signup at this school — create campus lazily
        tenant_id = _tenant_id_from_root(root)
        entry = registry_lookup(root)
        name = entry["name"] if entry else root
        color_entry = _SCHOOL_COLORS.get(root)
        if color_entry:
            primary = color_entry["primary"]
            color_source = "verified-table"
            color_status = "verified"
        else:
            primary = _derive_color(name)
            color_source = "placeholder"
            color_status = "placeholder"
        ink = _ink(primary)
        now = _now()
        campus = {
            "pk": "TENANTS",
            "sk": f"T#{tenant_id}",
            "id": tenant_id,
            "name": name,
            "shortName": _short_name(name),
            "domains": entry["domains"] if entry else [root],
            "theme": {"primary": primary, "ink": ink},
            "colorSource": color_source,
            "colorStatus": color_status,
            "timezone": tz or "America/New_York",
            "lms": {"type": "other", "connector": "none"},
            "tutoringResources": [],
            "pickupSpots": [],
            "categories": ["textbooks", "electronics", "furniture", "clothing", "other"],
            "openToNetwork": True,
            "autoCreated": True,
            "createdBy": _sub_hash(sub),
            "createdAt": now,
            "updatedAt": now,
        }
        domain_ptr = {
            "pk": f"DOMAIN#{root}",
            "sk": "MAP",
            "tenantId": tenant_id,
        }
        # Atomic write: campus + domain pointer together; conditional on campus not existing.
        try:
            db.transact_put_items([
                (campus, "attribute_not_exists(pk)"),
                (domain_ptr, None),
            ])
            tenant = campus
            # Async color worker for schools not in the verified table
            if color_status == "placeholder":
                _invoke_color_worker(root, tenant_id)
        except Exception as e:
            code = (getattr(e, "response", None) or {}).get("Error", {}).get("Code", "")
            if code in ("TransactionCanceledException", "ConditionalCheckFailedException"):
                # Race: another signup just created the campus; use their version
                domain_map2 = db.get_item(f"DOMAIN#{root}", "MAP")
                tenant_id = domain_map2["tenantId"] if domain_map2 else tenant_id
                tenant = db.get_item("TENANTS", f"T#{tenant_id}")
            else:
                raise

    return _build_me_response(event, sub, email, tenant, tenant_id)


_NAME_PART_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ .'\-]{0,39}$")


def _split_name(full: str) -> tuple:
    """Split 'First Last' → (first, last). Single word → (word, '')."""
    parts = full.strip().split(" ", 1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (parts[0].strip(), "")


def _validate_name_part(value: str, field: str):
    """Return cleaned name part or an error dict. field is 'firstName' or 'lastName'."""
    from lib import guard
    v = guard.clean_text(value, 40).strip()
    if len(v) < 1 or len(v) > 40:
        return util.error(400, "bad_request", f"{field} must be 1–40 characters")
    if not _NAME_PART_RE.match(v):
        return util.error(400, "bad_request", f"{field} may contain only letters, spaces, apostrophes, hyphens, and periods")
    return v


_AVATAR_SLUGS = frozenset(f"robot-{n:02d}" for n in range(1, 13))


def _valid_avatar(v) -> str | None:
    """Return the slug if valid, None if empty/null (clear), or raise ValueError if invalid."""
    if v is None or v == "":
        return None
    if not isinstance(v, str) or v not in _AVATAR_SLUGS:
        raise ValueError("avatar must be robot-01 through robot-12")
    return v


_LMS_VALUES = frozenset({"blackboard", "canvas", "other"})


def _valid_lms(v) -> str | None:
    """Return value if valid, None to clear, or raise ValueError if invalid."""
    if v is None or v == "":
        return None
    if not isinstance(v, str) or v not in _LMS_VALUES:
        raise ValueError("lms must be blackboard, canvas, or other")
    return v


def patch_me(event: dict, sub: str) -> dict:
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        body = {}
    if not isinstance(body, dict):
        body = {}

    # Standalone profile-field update: {avatar} and/or {lms}, no name fields
    _name_fields = {"firstName", "lastName", "displayName"}
    if ("avatar" in body or "lms" in body) and not (_name_fields & set(body)):
        updates: dict = {"updatedAt": _now()}
        if "avatar" in body:
            try:
                updates["avatar"] = _valid_avatar(body["avatar"])
            except ValueError as e:
                return util.error(400, "validation_error", str(e))
        if "lms" in body:
            try:
                updates["lms"] = _valid_lms(body["lms"])
            except ValueError as e:
                return util.error(400, "validation_error", str(e))
        profile = db.get_item(f"USER#{sub}", "PROFILE")
        if not profile:
            return util.error(404, "not_found", "Profile not found")
        try:
            limits.check_user(db.table(), sub, "default")
        except limits.LimitError as e:
            return limits.error_response(e)
        updated = db.update_item(f"USER#{sub}", "PROFILE", updates)
        return util.ok({"profile": _strip_keys(updated)})

    # Accept {firstName, lastName} or {displayName} (split on first space for backward compat)
    if "displayName" in body and "firstName" not in body and "lastName" not in body:
        raw = body.get("displayName", "")
        if not isinstance(raw, str):
            return util.error(400, "bad_request", "displayName must be a string")
        full = raw.strip()
        if len(full) < 2:
            return util.error(400, "bad_request", "displayName must be at least 2 characters")
        first_raw, last_raw = _split_name(full)
        body = {"firstName": first_raw, "lastName": last_raw}

    first_raw = body.get("firstName")
    last_raw = body.get("lastName")
    if first_raw is None and last_raw is None:
        return util.error(400, "bad_request", "Provide firstName and/or lastName")

    profile = db.get_item(f"USER#{sub}", "PROFILE")
    if not profile:
        return util.error(404, "not_found", "Profile not found")

    updates = {}
    if first_raw is not None:
        result = _validate_name_part(str(first_raw), "firstName")
        if isinstance(result, dict):
            return result
        updates["firstName"] = result
    if last_raw is not None:
        result = _validate_name_part(str(last_raw), "lastName")
        if isinstance(result, dict):
            return result
        updates["lastName"] = result

    # Derive combined displayName
    first = updates.get("firstName", profile.get("firstName", ""))
    last = updates.get("lastName", profile.get("lastName", ""))
    updates["displayName"] = f"{first} {last}".strip()

    if not updates.get("firstName", profile.get("firstName")):
        return util.error(400, "bad_request", "firstName is required")

    try:
        limits.check_user(db.table(), sub, "default")
    except limits.LimitError as e:
        return limits.error_response(e)

    updates["updatedAt"] = _now()
    updated = db.update_item(f"USER#{sub}", "PROFILE", updates)
    return util.ok({"profile": _strip_keys(updated)})


def _build_me_response(event, sub: str, email: str, tenant: dict, tenant_id: str):
    from lib import guard
    profile = db.get_item(f"USER#{sub}", "PROFILE")
    name_claim = guard.clean_text(_get_name_claim(event), 80).strip()
    email_prefix = email.split("@")[0]

    if not profile:
        cal_token = calendar_api.new_token()
        now = _now()
        first, last = _split_name(name_claim) if name_claim else ("", "")
        profile = {
            "pk": f"USER#{sub}",
            "sk": "PROFILE",
            "sub": sub,
            "email": email,
            "tenantId": tenant_id,
            "firstName": first,
            "lastName": last,
            "displayName": f"{first} {last}".strip(),
            "calToken": cal_token,
            "prefs": {"wakeHour": 7, "sleepHour": 23, "studyBlockMinutes": 50},
            "feed": None,
            "createdAt": now,
            "updatedAt": now,
        }
        db.put_item(profile)
        db.put_item({"pk": f"CAL#{cal_token}", "sk": "MAP", "sub": sub})
    elif name_claim and not profile.get("firstName"):
        # Refresh firstName/lastName from name claim for profiles that still have no first name
        first, last = _split_name(name_claim)
        if first:
            changes = {"firstName": first, "lastName": last,
                       "displayName": f"{first} {last}".strip(), "updatedAt": _now()}
            profile.update(changes)
            db.update_item(f"USER#{sub}", "PROFILE", changes)

    tenant_view = _strip_keys(tenant) if tenant else None
    needs_name = not profile.get("firstName")
    return util.ok({
        "profile": _strip_keys(profile),
        "tenant": tenant_view,
        "calendarPath": f"/cal/{profile['calToken']}.ics",
        "needsName": needs_name,
    })


def _invoke_color_worker(root: str, tenant_id: str):
    fn = os.environ.get("COLOR_WORKER_FN")
    if not fn:
        return
    try:
        import boto3
        region = os.environ.get("REGION", "us-east-1")
        boto3.client("lambda", region_name=region).invoke(
            FunctionName=fn,
            InvocationType="Event",
            Payload=json.dumps({"domain": root, "tenantId": tenant_id}).encode(),
        )
    except Exception as exc:
        print(f"color_worker invoke failed (non-fatal): {exc}")


# ── Internal helpers ──────────────────────────────────────────────────────────

class _AuthError(Exception):
    pass


def _get_sub(event: dict) -> str:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    except (KeyError, TypeError):
        raise _AuthError()


def _get_email(event: dict) -> str:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]["email"]
    except (KeyError, TypeError):
        raise _AuthError()


def _get_name_claim(event: dict) -> str:
    try:
        raw = event["requestContext"]["authorizer"]["jwt"]["claims"].get("name") or ""
        return raw.strip()
    except (AttributeError, KeyError, TypeError):
        return ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sub_hash(sub: str) -> str:
    import hashlib
    return hashlib.sha256(sub.encode()).hexdigest()[:16]


def _strip_keys(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk")}
