"""Marketplace v2 vocabulary shared by listings_api, market_api and admin_api (no I/O). Contract: MARKETPLACE_V2_API.md."""
import re
from datetime import datetime, timezone

KINDS = ("sell", "trade", "free", "wanted", "service")
BROWSE_KINDS = ("sell", "trade", "free", "service")      # shown when no `kind` filter is given
CATEGORIES = ["books", "supplies", "electronics", "dorm", "clothing", "tickets", "tutoring", "rides", "other"]
ALIASES = {"textbooks": "books", "textbook": "books"}
GOODS = ("books", "supplies", "electronics", "dorm", "clothing", "other")
TRANSFER_METHODS = ("official_app", "mobile_wallet", "will_call", "other")
TUTOR_MODES = ("in_person", "online", "both")
STANDINGS = ("", "freshman", "sophomore", "junior", "senior", "graduate")


def canon_category(value) -> str:
    c = str(value or "").strip().lower()
    return ALIASES.get(c, c)


def enabled_categories(tenant: dict) -> list:
    """The categories a campus allows, canonical and in the standard order. A campus with none set allows all."""
    raw = [canon_category(c) for c in (tenant.get("categories") or [])]
    picked = [c for c in CATEGORIES if c in raw]
    return picked or list(CATEGORIES)


def ticket_cap_on(tenant: dict) -> bool:
    return tenant.get("ticketPriceCap") is not False


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_expired(item: dict) -> bool:
    """A ticket listing whose event time has passed."""
    t = item.get("ticket")
    return bool(isinstance(t, dict) and t.get("eventAt") and str(t["eventAt"]) < now_iso())


def kind_of(item: dict) -> str:
    k = item.get("kind")
    return k if k in KINDS else "sell"


def public_name(profile: dict) -> str:
    """How a student appears to other students in listings, tutors and chats: first name plus last initial
    ("Sam S."). Uses firstName/lastName when present; falls back to displayName. Never returns an email,
    sub or full surname. An empty or email-like name shows as "Student". Room nicknames are separate."""
    p = profile or {}
    if p.get("firstName"):
        return public_name_from_parts(p.get("firstName", ""), p.get("lastName", ""))
    from . import guard
    name = guard.clean_text(p.get("displayName") or "", 80)
    name = re.sub(r"\s+", " ", name).strip()
    local = str(p.get("email") or "").split("@")[0].strip().lower()
    if not name or "@" in name or name.lower() == local or re.search(r"https?:|www\.|\.(com|edu|net|org)", name, re.I):
        return "Student"
    parts = [w for w in re.split(r"[ ,]+", name) if w]
    if "," in name:                       # "Student, Sam" form
        first_last = [w for w in re.split(r"[ ,]+", name.split(",", 1)[1]) if w] + [name.split(",", 1)[0].strip()]
        parts = [w for w in first_last if w]
    first = re.sub(r"[^\w'\-]", "", parts[0], flags=re.UNICODE)[:16]
    if not first or first.isdigit():
        return "Student"
    last_w = re.sub(r"[^\w]", "", parts[-1], flags=re.UNICODE) if len(parts) > 1 else ""
    return f"{first} {last_w[0].upper()}." if last_w else first


def public_name_from_parts(first_name: str, last_name: str) -> str:
    """Build 'Sam S.' from explicit firstName/lastName fields."""
    from . import guard
    first = re.sub(r"[^\w'\-]", "", guard.clean_text(first_name or "", 40).strip(), flags=re.UNICODE)[:16]
    if not first or first.isdigit():
        return "Student"
    last_initial = re.sub(r"[^\w]", "", guard.clean_text(last_name or "", 40).strip(), flags=re.UNICODE)
    return f"{first} {last_initial[0].upper()}." if last_initial else first
