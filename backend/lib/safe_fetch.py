"""SSRF-safe HTTPS fetch for user-supplied URLs (the Blackboard Share Calendar link).

Rules enforced here, in code:
  * https only, port 443 only, no user:password@, no IP literals, hostname must have a letter-leading last label
    (this rejects decimal/hex/octal tricks such as 2130706433, 0x7f.1, 017700000001, and bare names like localhost)
  * the hostname is resolved HERE, every address must be a public global address (IPv4 and IPv6; loopback,
    private, link-local, metadata, CGNAT, multicast, reserved, IPv4-mapped, 6to4, Teredo and NAT64 are rejected)
  * the connection goes to the vetted IP (TLS still verifies the hostname), which defeats DNS rebinding
  * redirects are followed manually, at most 3, https only, and every hop is vetted again
  * connect/read timeout, an overall deadline and a response size cap (Accept-Encoding: identity, so no gzip bombs)
  * nothing is logged and error messages never contain the URL, because the URL is a secret
`resolver` and `transport` are injectable so the tests never touch the network.
"""
import ipaddress
import re
import socket
import ssl
import time
from http.client import HTTPSConnection
from urllib.parse import urljoin, urlsplit

MAX_REDIRECTS = 3
DEFAULT_TIMEOUT = 8.0
DEFAULT_DEADLINE = 15.0
DEFAULT_MAX_BYTES = 2 * 1024 * 1024
MAX_URL_LENGTH = 2000


class FetchError(Exception):
    """`code` is one of: bad_url, blocked_address, dns, redirect, too_large, timeout, http_status, tls, network."""

    _TEXT = {
        "bad_url": "That link isn't a valid https address.",
        "blocked_address": "That link points somewhere we can't connect to.",
        "dns": "We couldn't find that address.",
        "redirect": "That link redirected too many times or somewhere unsafe.",
        "too_large": "That calendar is too large.",
        "timeout": "The calendar took too long to respond.",
        "http_status": "The calendar server refused the request.",
        "tls": "The secure connection to the calendar failed.",
        "network": "We couldn't reach the calendar.",
        "not_ical": "That link doesn't look like a calendar feed.",
    }

    def __init__(self, code: str, status: int | None = None):
        super().__init__(self._TEXT.get(code, "Fetch failed."))  # deliberately no URL, host or IP in here
        self.code, self.status, self.message = code, status, self._TEXT.get(code, "Fetch failed.")


# ── Address vetting ───────────────────────────────────────────────────────────

_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")


def is_public_ip(addr: str) -> bool:
    """True only for a normal public internet address."""
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return is_public_ip(str(ip.ipv4_mapped))
        if ip.sixtofour is not None or ip.teredo is not None:
            return False
        if ip in _NAT64 or ip in _NAT64_LOCAL:
            return False
    return bool(ip.is_global) and not (ip.is_multicast or ip.is_unspecified or ip.is_loopback
                                       or ip.is_link_local or ip.is_private or ip.is_reserved)


_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9\-]{0,61}[a-z0-9]$|"
                      r"^(?=.{1,253}$)([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]$")


def check_url(url: str) -> tuple[str, str]:
    """Validate the URL text. Returns (hostname, path_with_query). Raises FetchError('bad_url')."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise FetchError("bad_url")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise FetchError("bad_url")
    if parts.scheme.lower() != "https" or parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise FetchError("bad_url")
    if port not in (None, 443):
        raise FetchError("bad_url")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host or ":" in host or "\\" in url:
        raise FetchError("bad_url")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise FetchError("bad_url")
    if not _HOST_RE.match(host):
        raise FetchError("bad_url")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return host, path


def resolve_public(host: str, resolver=socket.getaddrinfo) -> list:
    """Resolve and require EVERY address to be public (one private answer poisons the set)."""
    try:
        infos = resolver(host, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError, UnicodeError):
        raise FetchError("dns")
    addrs = []
    for info in infos:
        a = info[4][0]
        if a not in addrs:
            addrs.append(a)
    if not addrs:
        raise FetchError("dns")
    if not all(is_public_ip(a) for a in addrs):
        raise FetchError("blocked_address")
    return addrs


# ── Transport (real network; tests replace it) ────────────────────────────────

class _PinnedHTTPSConnection(HTTPSConnection):
    """Connects to a vetted IP while TLS and the Host header use the original hostname."""

    def __init__(self, host, ip, timeout):
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _https_transport(host, ip, path, timeout, max_bytes, deadline):
    conn = _PinnedHTTPSConnection(host, ip, timeout)
    try:
        conn.request("GET", path, headers={"Host": host, "User-Agent": "SemesterOS-CalendarSync/1",
                                           "Accept": "text/calendar, text/plain;q=0.5, */*;q=0.1",
                                           "Accept-Encoding": "identity", "Connection": "close"})
        resp = conn.getresponse()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        if resp.status in (301, 302, 303, 307, 308):
            return resp.status, headers, b""
        try:
            if int(headers.get("content-length", "0")) > max_bytes:
                raise FetchError("too_large")
        except ValueError:
            pass
        body = bytearray()
        while True:
            if time.monotonic() > deadline:
                raise FetchError("timeout")
            chunk = resp.read(min(65536, max_bytes + 1 - len(body)))
            if not chunk:
                break
            body += chunk
            if len(body) > max_bytes:
                raise FetchError("too_large")
        return resp.status, headers, bytes(body)
    except FetchError:
        raise
    except ssl.SSLError:
        raise FetchError("tls")
    except (socket.timeout, TimeoutError):
        raise FetchError("timeout")
    except OSError:
        raise FetchError("network")
    finally:
        conn.close()


# ── Public API ────────────────────────────────────────────────────────────────

def fetch(url: str, *, max_bytes: int = DEFAULT_MAX_BYTES, timeout: float = DEFAULT_TIMEOUT,
          deadline_seconds: float = DEFAULT_DEADLINE, max_redirects: int = MAX_REDIRECTS,
          resolver=socket.getaddrinfo, transport=_https_transport) -> bytes:
    """GET `url` and return the body bytes. Raises FetchError (message safe to show and to log)."""
    deadline = time.monotonic() + deadline_seconds
    current = url
    for hop in range(max_redirects + 1):
        if time.monotonic() > deadline:
            raise FetchError("timeout")
        try:
            host, path = check_url(current)
        except FetchError:
            raise FetchError("redirect" if hop else "bad_url")
        try:
            ip = resolve_public(host, resolver)[0]
        except FetchError as e:
            raise FetchError("redirect") if hop and e.code == "blocked_address" else e
        status, headers, body = transport(host, ip, path, timeout, max_bytes, deadline)
        if status in (301, 302, 303, 307, 308):
            loc = headers.get("location")
            if not loc or hop >= max_redirects:
                raise FetchError("redirect")
            current = urljoin(current, loc)   # relative redirects stay https on the same host
            continue
        if status != 200:
            raise FetchError("http_status", status)
        if len(body) > max_bytes:
            raise FetchError("too_large")
        return body
    raise FetchError("redirect")


def fetch_ical(url: str, **kw) -> str:
    """fetch() plus a sanity check that the body is an iCalendar file. Returns text (UTF-8, errors replaced)."""
    body = fetch(url, **kw)
    text = body.decode("utf-8-sig", errors="replace")
    if not text.lstrip().upper().startswith("BEGIN:VCALENDAR"):
        raise FetchError("not_ical")
    return text
