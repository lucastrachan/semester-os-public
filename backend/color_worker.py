"""Color finder worker Lambda.

Invoked asynchronously when a campus is created without a verified color.
Payload: {"domain": "ua.edu", "tenantId": "ua-edu"}

Flow:
1. Check whether campus already has a verified/needs_review color — exit early if so.
2. Fetch https://www.{domain} (then bare https://{domain} on failure) via safe_fetch.
3. Extract CSS custom properties and theme-color meta from the HTML.
4. Ask MODEL_FAST to pick the best brand color from candidates.
5. Validate the chosen color: must be #RRGGBB, not near-white/black, saturation above floor.
6. Store theme.primary, colorSource="autodetected", colorConfidence, colorStatus="needs_review".
7. On any failure leave the existing placeholder and record colorStatus="placeholder".

Limits: runs once per campus (exits if color already resolved), daily cap enforced via DynamoDB counter.
Kill switch: COLOR_WORKER_ENABLED env var must be "1".
"""
import json
import os
import re
import time

from lib import bedrock as bd, db
from lib.color_utils import ink
from lib.safe_fetch import fetch, FetchError

KILL_SWITCH = os.environ.get("COLOR_WORKER_ENABLED", "1")
DAILY_CAP = int(os.environ.get("COLOR_WORKER_DAILY_CAP", "200"))
MAX_BYTES = 512 * 1024  # 512 KB of HTML is more than enough
FETCH_TIMEOUT = 10.0

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_CSS_PROP_RE = re.compile(r"--[a-z][a-z0-9\-]*\s*:\s*(#[0-9A-Fa-f]{3,8})", re.IGNORECASE)
_THEME_META_RE = re.compile(r'<meta[^>]+name=["\']theme-color["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)
_THEME_META_RE2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']theme-color["\']', re.IGNORECASE)


def handler(event, context):
    if KILL_SWITCH != "1":
        print("color_worker: disabled via kill switch")
        return

    domain = event.get("domain", "").strip().lower()
    tenant_id = event.get("tenantId", "").strip()
    if not domain or not tenant_id:
        print("color_worker: missing domain or tenantId")
        return

    tenant = db.get_item("TENANTS", f"T#{tenant_id}")
    if not tenant:
        print(f"color_worker: tenant {tenant_id} not found")
        return

    existing_status = tenant.get("colorStatus", "placeholder")
    if existing_status in ("verified", "needs_review"):
        print(f"color_worker: {tenant_id} already has status={existing_status}, skipping")
        return

    # Daily cap: at most DAILY_CAP runs across all campuses per day
    today = time.strftime("%Y-%m-%d", time.gmtime())
    try:
        count = db.incr_counter("COLOR_WORKER_CAP", f"D#{today}", _day_ttl())
        if count > DAILY_CAP:
            print(f"color_worker: daily cap {DAILY_CAP} reached")
            return
    except Exception as e:
        print(f"color_worker: cap check failed ({e}), proceeding")

    candidates = _extract_candidates(domain)
    if not candidates:
        print(f"color_worker: no color candidates found for {domain}")
        _update_status(tenant_id, "placeholder")
        return

    chosen, confidence = _ask_model(domain, tenant.get("name", domain), candidates)
    if not chosen or not _valid_color(chosen):
        print(f"color_worker: model returned invalid color for {domain}: {chosen!r}")
        _update_status(tenant_id, "placeholder")
        return

    db.update_item("TENANTS", f"T#{tenant_id}", {
        "theme": {**tenant.get("theme", {}), "primary": chosen, "ink": ink(chosen)},
        "colorSource": "autodetected",
        "colorConfidence": confidence,
        "colorStatus": "needs_review",
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    print(f"color_worker: stored {chosen} (confidence={confidence}) for {tenant_id}")


def _extract_candidates(domain: str) -> list[str]:
    urls = [f"https://www.{domain}", f"https://{domain}"]
    for url in urls:
        try:
            body = fetch(url, max_bytes=MAX_BYTES, timeout=FETCH_TIMEOUT, deadline_seconds=15.0)
            html = body.decode("utf-8", errors="replace")
            colors = set()
            for m in _CSS_PROP_RE.finditer(html):
                c = _normalize_hex(m.group(1))
                if c:
                    colors.add(c)
            for pattern in (_THEME_META_RE, _THEME_META_RE2):
                for m in pattern.finditer(html):
                    c = _normalize_hex(m.group(1))
                    if c:
                        colors.add(c)
            if colors:
                return list(colors)[:20]
        except FetchError as e:
            print(f"color_worker: fetch {url} failed: {e.code}")
        except Exception as e:
            print(f"color_worker: fetch {url} error: {e}")
    return []


def _normalize_hex(value: str) -> str | None:
    v = value.strip()
    if re.match(r"^#[0-9A-Fa-f]{6}$", v):
        return v.upper()
    if re.match(r"^#[0-9A-Fa-f]{3}$", v):
        r, g, b = v[1], v[2], v[3]
        return f"#{r*2}{g*2}{b*2}".upper()
    return None


def _ask_model(domain: str, school_name: str, candidates: list[str]) -> tuple[str | None, float]:
    system = "You identify the primary brand color of a university from a list of hex color candidates."
    prompt = (
        f"School: {school_name} ({domain})\n"
        f"Color candidates extracted from the school homepage: {', '.join(candidates)}\n\n"
        "Which single color is most likely the school's primary brand color? "
        "Reply with ONLY the hex code (e.g. #1A2B3C) and a confidence score 0.0-1.0 separated by a space. "
        "Nothing else."
    )
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    try:
        resp = bd.converse(
            os.environ.get("MODEL_FAST", "amazon.nova-lite-v1:0"),
            system,
            messages,
            max_tokens=20,
        )
        content = bd.extract_text(resp).strip()
        parts = content.split()
        if len(parts) >= 1:
            color = _normalize_hex(parts[0])
            confidence = float(parts[1]) if len(parts) >= 2 else 0.5
            return color, min(max(confidence, 0.0), 1.0)
    except Exception as e:
        print(f"color_worker: model call failed: {e}")
    return None, 0.0


def _valid_color(hex_color: str) -> bool:
    """Reject near-white, near-black, and unsaturated colors."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        if lum < 20 or lum > 230:
            return False
        max_c = max(r, g, b)
        min_c = min(r, g, b)
        saturation = (max_c - min_c) / max_c if max_c > 0 else 0
        return saturation >= 0.15
    except Exception:
        return False


def _update_status(tenant_id: str, status: str):
    try:
        db.update_item("TENANTS", f"T#{tenant_id}", {
            "colorStatus": status,
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception as e:
        print(f"color_worker: failed to update status: {e}")


def _day_ttl() -> int:
    import calendar
    t = time.gmtime()
    next_day = time.mktime((t.tm_year, t.tm_mon, t.tm_mday + 1, 0, 0, 0, 0, 0, 0))
    return int(next_day) + 3600
