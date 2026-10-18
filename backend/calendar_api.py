"""Outbound calendar feed (handoff section 8, Phase 3).

  GET  /cal/{token}.ics            public. The unguessable token is the credential.
  POST /me/calendar-token/rotate   JWT. New token; the old URL stops working at once.

Never log the token (lib/redact masks /cal/<token>.ics if a path is ever logged).
Contract: CALENDAR_API.md.
"""
import re
import secrets
import string
from datetime import datetime, timezone

from lib import db, guard, ics, limits, util

TOKEN_LENGTH = 32
_TOKEN_RE = re.compile(r"^[a-z0-9]{24,64}$")          # new_token() output; the first tokens (24 chars) are also valid
_PATH_RE = re.compile(r"^/cal/([^/]{1,200})\.ics$")
_ALPHABET = string.ascii_lowercase + string.digits
ROTATIONS_PER_DAY = 5
DEFAULT_TZ = ics.DEFAULT_TZ


def _table():
    return db.table()


def new_token() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(TOKEN_LENGTH))


def _not_found() -> dict:
    return util.error(404, "not_found", "Calendar not found")


def _miss(event: dict) -> dict:
    """Every failure looks the same, and each miss counts against the caller's per-IP budget."""
    try:
        limits.check_ip(_table(), limits.client_ip(event), "cal_miss")
    except limits.RateLimited as e:
        return limits.error_response(e)
    return _not_found()


def get_feed(event: dict) -> dict:
    m = _PATH_RE.match(event.get("rawPath") or "")
    token = m.group(1) if m else ""
    if not _TOKEN_RE.match(token):
        return _miss(event)

    mapping = db.get_item(f"CAL#{token}", "MAP")
    sub = (mapping or {}).get("sub")
    if not sub:
        return _miss(event)
    try:
        scoped = guard.UserScopedDB(sub, db, allowed_prefixes=("PROFILE", "COURSE", "ASG", "STUDY"))
    except guard.ScopeError:
        return _miss(event)
    profile = scoped.get("PROFILE")
    if not profile or profile.get("calToken") != token:  # deleted user, or a token that was rotated away
        return _miss(event)

    tenant = db.get_item("TENANTS", f"T#{profile.get('tenantId')}") if profile.get("tenantId") else None
    tz_name = (tenant or {}).get("timezone") or DEFAULT_TZ
    courses = {c.get("id"): c for c in scoped.query("COURSE#") if not c.get("archived")}
    now = datetime.now(timezone.utc)

    events = []
    for a in scoped.query("ASG#"):
        ev = ics.assignment_event(a, courses.get(a.get("courseId")), tz_name, now)
        if ev:
            events.append(ev)
    for s in scoped.query("STUDY#"):
        ev = ics.study_event(s, courses.get(s.get("courseId")), tz_name, now)
        if ev:
            events.append(ev)
    events.sort(key=lambda e: e["uid"])  # stable order: unchanged data gives a byte-identical file

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/calendar; charset=utf-8",
            "Content-Disposition": 'inline; filename="semester-os.ics"',
            "Cache-Control": "private, max-age=300",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
        "body": ics.build_calendar(events),
    }


def rotate_token(event: dict, sub: str) -> dict:
    try:
        scoped = guard.UserScopedDB(sub, db, allowed_prefixes=("PROFILE",))
    except guard.ScopeError:
        return util.error(401, "unauthorized", "Missing or invalid token")
    profile = scoped.get("PROFILE")
    if not profile:
        return util.error(404, "not_found", "Profile not found. Open the app once first.")
    try:
        _daily_rotation(sub)
    except limits.RateLimited as e:
        return limits.error_response(e)

    old = profile.get("calToken")
    token = new_token()
    db.put_item({"pk": f"CAL#{token}", "sk": "MAP", "sub": sub})        # 1. new mapping first
    scoped.update("PROFILE", {"calToken": token, "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})  # 2. profile
    if old and old != token:
        db.delete_item(f"CAL#{old}", "MAP")                              # 3. old URL dies
    return util.ok({"calToken": token, "calendarPath": f"/cal/{token}.ics"})


def _daily_rotation(sub: str) -> None:
    """A small own cap (limits.py has no bucket for this): ROTATIONS_PER_DAY per UTC day."""
    now = datetime.now(timezone.utc)
    ttl = int(now.timestamp()) + 2 * 86400
    n = db.incr_counter(f"USER#{sub}", f"CAP#calrotate#{now:%Y%m%d}", ttl)
    if n > ROTATIONS_PER_DAY:
        raise limits.RateLimited("You can rotate the calendar link a few times a day. Try again tomorrow.", 3600)
