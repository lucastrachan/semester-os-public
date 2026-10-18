"""Rate limits, abuse caps, size caps and the AI kill switch.

Counters live in the app table: pk USER#{sub} (or IP#{hash}), sk LIMIT#{scope}#{bucket}#{window}, attribute n,
plus `ttl` so DynamoDB deletes them. One conditional UpdateItem both checks and increments, so concurrent
requests cannot slip past the limit, and rejected requests do not grow the counter.
The Lambda role needs only dynamodb:UpdateItem on the table for this (see SECURITY.md wiring requests).

`table` is a boto3 Table (db.table()). All functions take `now` for testing.
"""
import hashlib
import json
import os
import time
from datetime import datetime, timezone

# bucket -> (per_minute, per_day). Tune freely; the point is that every Bedrock-backed route has a number.
USER_LIMITS = {
    "chat": (6, 200),
    "syllabus": (3, 10),
    "briefing": (2, 20),
    "plan": (2, 20),
    "quiz": (4, 60),
    "feed_save": (3, 30),
    "material": (30, 200),
    "feed_sync": (2, 24),
    "course_import": (6, 60),
    "default": (30, 2000),
}
# bucket -> (per_hour, per_day), keyed by hashed client IP, for endpoints with no login
IP_LIMITS = {
    "campus_request": (5, 20),
    "resolve": (60, 300),
    "default": (60, 600),
}

# Size caps (characters unless noted)
MAX_SYLLABUS_CHARS = 60_000
MAX_CHAT_MESSAGE_CHARS = 4_000
MAX_CHAT_TURNS = 20
MAX_BODY_BYTES = 200_000
MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_FEED_BYTES = 2 * 1024 * 1024
MAX_MATERIALS_PER_COURSE = 80
MAX_OUTPUT_TOKENS = {"chat": 500, "chat_moderate": 700, "chat_detail": 900, "quiz": 2048, "extract": 8192,
                     "briefing": 1500, "plan": 1500, "router": 200, "default": 1024}


class LimitError(Exception):
    status = 400
    code = "limit"

    def __init__(self, message: str = "", retry_after: int = 0):
        super().__init__(message or self.code)
        self.message, self.retry_after = message or self.code, retry_after


class RateLimited(LimitError):
    status, code = 429, "rate_limited"


class AiDisabled(LimitError):
    status, code = 503, "ai_disabled"


class InputTooLarge(LimitError):
    status, code = 413, "too_large"


def error_response(exc: LimitError) -> dict:
    """API Gateway response for a LimitError (same shape as util.error plus Retry-After)."""
    headers = {"Content-Type": "application/json"}
    if exc.retry_after:
        headers["Retry-After"] = str(int(exc.retry_after))
    return {"statusCode": exc.status, "headers": headers,
            "body": json.dumps({"error": exc.code, "message": exc.message})}


# ── Counters ──────────────────────────────────────────────────────────────────

def _hit(table, pk: str, sk: str, limit: int, ttl_epoch: int) -> bool:
    """Increment if below the limit. Returns True when allowed, False when the limit is already reached."""
    try:
        table.update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression="ADD #n :one SET #t = if_not_exists(#t, :ttl)",
            ConditionExpression="attribute_not_exists(#n) OR #n < :limit",
            ExpressionAttributeNames={"#n": "n", "#t": "ttl"},
            ExpressionAttributeValues={":one": 1, ":ttl": ttl_epoch, ":limit": limit},
            ReturnValues="UPDATED_NEW",
        )
        return True
    except Exception as e:  # botocore ClientError, or a test fake with the same .response shape
        code = (getattr(e, "response", None) or {}).get("Error", {}).get("Code", "")
        if code == "ConditionalCheckFailedException":
            return False
        raise


def _ts(now: float | None) -> datetime:
    return datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc)


def check_user(table, sub: str, bucket: str, now: float | None = None) -> None:
    """Per-minute then per-day counter for a signed-in user. Raises RateLimited."""
    per_min, per_day = USER_LIMITS.get(bucket, USER_LIMITS["default"])
    t = _ts(now)
    epoch = int(t.timestamp())
    pk = f"USER#{sub}"
    if not _hit(table, pk, f"LIMIT#min#{bucket}#{t:%Y%m%d%H%M}", per_min, epoch + 180):
        raise RateLimited("You're going a bit fast. Wait a few seconds and try again.", 60 - t.second)
    if not _hit(table, pk, f"LIMIT#day#{bucket}#{t:%Y%m%d}", per_day, epoch + 2 * 86400):
        secs = 86400 - (t.hour * 3600 + t.minute * 60 + t.second)
        raise RateLimited("You've hit today's limit for this. It resets at midnight UTC.", secs)


def ip_key(ip: str) -> str:
    """Hash of the client IP so raw addresses are not stored. IP_HASH_SALT should be set in the environment."""
    salt = os.environ.get("IP_HASH_SALT", "semesteros-ip")
    return "IP#" + hashlib.sha256(f"{salt}|{ip}".encode()).hexdigest()[:32]


def client_ip(event: dict) -> str:
    """API Gateway HTTP API puts the real client address here; X-Forwarded-For can be forged by the caller."""
    return str((event.get("requestContext", {}).get("http", {}) or {}).get("sourceIp") or "unknown")


def check_ip(table, ip: str, bucket: str = "campus_request", now: float | None = None) -> None:
    """Per-hour then per-day counter for anonymous endpoints. Raises RateLimited."""
    per_hour, per_day = IP_LIMITS.get(bucket, IP_LIMITS["default"])
    t = _ts(now)
    epoch = int(t.timestamp())
    pk = ip_key(ip)
    if not _hit(table, pk, f"LIMIT#hour#{bucket}#{t:%Y%m%d%H}", per_hour, epoch + 2 * 3600):
        raise RateLimited("Too many requests from your network. Try again later.", 3600 - t.minute * 60 - t.second)
    if not _hit(table, pk, f"LIMIT#day#{bucket}#{t:%Y%m%d}", per_day, epoch + 2 * 86400):
        raise RateLimited("Too many requests from your network today.", 3600)


# ── Kill switch ───────────────────────────────────────────────────────────────

_OFF = {"0", "false", "off", "no", "disabled"}
_cache = {"value": True, "at": 0.0}


def ai_enabled(env: dict | None = None, ssm_get=None, now: float | None = None, ttl: float = 30.0) -> bool:
    """False when AI_ENABLED is off. Checks the AI_ENABLED env var first (flip it with a config update), then the
    SSM parameter named by AI_ENABLED_PARAM (flip it with `aws ssm put-parameter`, effective within `ttl` seconds
    with no redeploy). If SSM cannot be read, the last known value is kept (default on), so an SSM outage does
    not take the app down; set the env var to 0 for a hard stop."""
    env = os.environ if env is None else env
    if str(env.get("AI_ENABLED", "1")).strip().lower() in _OFF:
        return False
    param = env.get("AI_ENABLED_PARAM")
    if not param:
        return True
    t = now if now is not None else time.time()
    if t - _cache["at"] < ttl:
        return _cache["value"]
    try:
        getter = ssm_get or _ssm_get
        _cache["value"] = str(getter(param)).strip().lower() not in _OFF
        _cache["at"] = t
    except Exception:
        _cache["at"] = t - ttl + 5  # retry soon, keep the last known value
    return _cache["value"]


def _ssm_get(name: str) -> str:
    import boto3  # imported late: tests and the env-var path need no AWS libraries
    return boto3.client("ssm", region_name=os.environ.get("REGION", "us-east-1")).get_parameter(Name=name)["Parameter"]["Value"]


def require_ai_enabled(**kw) -> None:
    if not ai_enabled(**kw):
        raise AiDisabled("The AI features are paused for a moment. Your data is safe. Please try again later.", 300)


def reset_cache_for_tests() -> None:
    _cache.update(value=True, at=0.0)


# ── Size caps ─────────────────────────────────────────────────────────────────

def check_body_size(event: dict, max_bytes: int = MAX_BODY_BYTES) -> None:
    body = event.get("body") or ""
    if len(body.encode("utf-8", "ignore")) > max_bytes:
        raise InputTooLarge("That request is too large.")


def cap_text(text, max_chars: int, what: str = "text") -> str:
    if not isinstance(text, str):
        raise LimitError(f"{what} must be text")
    if len(text) > max_chars:
        raise InputTooLarge(f"That {what} is too long (limit {max_chars:,} characters).")
    return text


def cap_messages(messages, max_turns: int = MAX_CHAT_TURNS, max_chars: int = MAX_CHAT_MESSAGE_CHARS) -> list:
    """Keep the last max_turns messages; each must be {role: user|assistant, content: str<=max_chars}.
    Roles from the client are checked here: a client can never inject a 'system' turn."""
    if not isinstance(messages, list) or not messages:
        raise LimitError("messages must be a non-empty list")
    out = []
    for m in messages[-max_turns:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant") or not isinstance(m.get("content"), str):
            raise LimitError("each message needs a role (user or assistant) and text content")
        out.append({"role": m["role"], "content": cap_text(m["content"], max_chars, "message")})
    if out[-1]["role"] != "user":
        raise LimitError("the last message must be from the user")
    return out


def max_output_tokens(purpose: str, requested: int | None = None) -> int:
    cap = MAX_OUTPUT_TOKENS.get(purpose, MAX_OUTPUT_TOKENS["default"])
    return min(cap, requested) if requested else cap
