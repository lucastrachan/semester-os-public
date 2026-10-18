"""Log redaction: remove secrets and personal data from any text before it reaches CloudWatch.

Removes JWTs and bearer tokens, AWS keys, admin-key headers, email addresses, calendar-feed tokens, any URL
that has a query string or looks like a calendar feed (the Blackboard Share Calendar link is a secret), and long
random-looking strings. Use `redact.safe(e)` when printing exceptions and `redact.install()` once at import time
in each Lambda handler module to cover print() and logging as a safety net.
"""
import logging
import re
import sys

_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]*")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{8,}")
_AWS_KEY = re.compile(r"\b(AKIA|ASIA|AGPA|AIDA|AROA)[A-Z0-9]{12,}\b")
_AWS_SECRET_CTX = re.compile(r"(?i)(secret[_ \-]?(access[_ \-]?)?key|session[_ \-]?token|x-admin-key|authorization|api[_ \-]?key|password|passwd)(\"?\s*[:=]\s*\"?)[^\s\"',;}]{3,}")
_CAL_PATH = re.compile(r"(/cal/)[A-Za-z0-9_\-]{8,}(\.ics)?")
_URL = re.compile(r"(?i)\b(?:https?|webcal|webcals)://[^\s<>\"')\]]+")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,255}\.[A-Za-z]{2,}\b")
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
_FEEDISH = re.compile(r"(?i)(\.ics\b|webcal|blackboard|bbcal|/calendar/|/ical|ultra/|learn\.)")


def _url_sub(m: "re.Match") -> str:
    url = m.group(0)
    if _FEEDISH.search(url):
        return "[feed-url]"
    if "?" in url or "#" in url:
        return re.split(r"[?#]", url, maxsplit=1)[0] + "?[redacted]"
    return url


def redact(text) -> str:
    """Return text with secrets and personal data removed. Safe on any input; never raises."""
    try:
        s = text if isinstance(text, str) else str(text)
        s = _URL.sub(_url_sub, s)
        s = _CAL_PATH.sub(r"\1[token]\2", s)
        s = _JWT.sub("[jwt]", s)
        s = _BEARER.sub(lambda m: m.group(1) + " [token]", s)
        s = _AWS_KEY.sub("[aws-key]", s)
        s = _AWS_SECRET_CTX.sub(lambda m: m.group(1) + m.group(3) + "[redacted]", s)
        s = _EMAIL.sub("[email]", s)
        s = _LONG_TOKEN.sub("[token]", s)
        return s
    except Exception:
        return "[unprintable]"


def safe(obj) -> str:
    """For exceptions and objects: print(f"failed: {redact.safe(e)}"). Also trims very long messages."""
    return redact(obj)[:500]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:
            record.msg, record.args = "[unprintable]", ()
        return True


class _RedactingStream:
    def __init__(self, inner):
        self._inner = inner
        self._redacting = True

    def write(self, data):
        return self._inner.write(redact(data) if isinstance(data, str) else data)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def install() -> None:
    """Idempotent. Wrap stdout/stderr (what print() and tracebacks use in Lambda) and the root logger."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if not getattr(stream, "_redacting", False):
            setattr(sys, name, _RedactingStream(stream))
    root = logging.getLogger()
    if not any(isinstance(f, RedactingFilter) for f in root.filters):
        root.addFilter(RedactingFilter())
    for h in root.handlers:
        if not any(isinstance(f, RedactingFilter) for f in h.filters):
            h.addFilter(RedactingFilter())
