import socket
import unittest

from _fakes import FakeDb  # noqa
from lib import safe_fetch as sf


def resolver_for(mapping):
    def r(host, port, type=0):
        if host not in mapping:
            raise socket.gaierror("nope")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in mapping[host]]
    return r


class FakeTransport:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, host, ip, path, timeout, max_bytes, deadline):
        self.calls.append((host, ip, path))
        status, headers, body = self.routes[host]
        if len(body) > max_bytes:
            raise sf.FetchError("too_large")
        return status, headers, body


PUBLIC = "93.184.216.34"
ICS = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR"


def run(url, routes, dns, **kw):
    t = FakeTransport(routes)
    return sf.fetch(url, resolver=resolver_for(dns), transport=t, **kw), t


class Addresses(unittest.TestCase):
    def test_blocked(self):
        for a in ["127.0.0.1", "127.1.2.3", "169.254.169.254", "10.0.0.5", "172.16.0.1", "172.31.255.255", "192.168.1.1",
                  "100.64.0.1", "0.0.0.0", "255.255.255.255", "224.0.0.1", "192.0.0.1", "198.18.0.1", "::1", "::", "fe80::1",
                  "fd00:ec2::254", "fc00::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254",
                  "2002:7f00:0001::", "2001:0:4136:e378:8000:63bf:3fff:fdd2", "64:ff9b::7f00:1", "ff02::1", "not-an-ip"]:
            self.assertFalse(sf.is_public_ip(a), a)

    def test_allowed(self):
        for a in ["93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946"]:
            self.assertTrue(sf.is_public_ip(a), a)


class UrlChecks(unittest.TestCase):
    def bad(self, url):
        with self.assertRaises(sf.FetchError) as cm:
            sf.check_url(url)
        self.assertEqual(cm.exception.code, "bad_url", url)

    def test_rejects_unsafe_urls(self):
        for u in ["http://example.edu/a.ics", "ftp://example.edu/a", "file:///etc/passwd", "gopher://x.example/", "//example.edu/a",
                  "https://127.0.0.1/a", "https://[::1]/a", "https://169.254.169.254/latest/meta-data/",
                  "https://2130706433/", "https://0x7f.0.0.1/", "https://0x7f000001/", "https://017700000001/", "https://127.1/",
                  "https://0177.0.0.1/", "https://localhost/a", "https://user:pw@example.edu/a", "https://example.edu@evil.test/",
                  "https://example.edu:8443/a", "https://example.edu:22/a", "https://example.edu\\@evil.test/", "https://exa mple.edu/",
                  "https://10.0.0.5.nip.io.0x7f/", "", None, 5, "https://" + "a" * 300 + ".edu/", "https://example.edu/" + "a" * 3000,
                  "https://-bad.edu/", "https://bad..edu/", "https://example.edu/a\nHost: evil"]:
            self.bad(u)

    def test_accepts_normal_urls(self):
        self.assertEqual(sf.check_url("https://bb.example.edu/webapps/x.ics?a=1"), ("bb.example.edu", "/webapps/x.ics?a=1"))
        self.assertEqual(sf.check_url("https://Example.EDU:443/")[0], "example.edu")
        self.assertEqual(sf.check_url("https://example.edu./")[0], "example.edu")


class Fetch(unittest.TestCase):
    def test_happy_path_pins_vetted_ip(self):
        body, t = run("https://bb.example.edu/c.ics", {"bb.example.edu": (200, {}, ICS)}, {"bb.example.edu": [PUBLIC]})
        self.assertEqual(body, ICS)
        self.assertEqual(t.calls, [("bb.example.edu", PUBLIC, "/c.ics")])

    def test_hostname_resolving_to_private_blocked(self):
        for ip in ["127.0.0.1", "169.254.169.254", "10.1.2.3", "::1", "fd00:ec2::254", "::ffff:10.0.0.1"]:
            with self.assertRaises(sf.FetchError) as cm:
                run("https://evil.example/a", {"evil.example": (200, {}, ICS)}, {"evil.example": [ip]})
            self.assertEqual(cm.exception.code, "blocked_address", ip)

    def test_one_private_answer_among_public_blocks(self):
        with self.assertRaises(sf.FetchError) as cm:
            run("https://evil.example/a", {"evil.example": (200, {}, ICS)}, {"evil.example": [PUBLIC, "10.0.0.1"]})
        self.assertEqual(cm.exception.code, "blocked_address")

    def test_dns_failure(self):
        with self.assertRaises(sf.FetchError) as cm:
            run("https://missing.example/a", {}, {})
        self.assertEqual(cm.exception.code, "dns")

    def test_redirect_to_private_address_blocked(self):
        routes = {"a.example": (302, {"location": "https://internal.example/x"}, b""), "internal.example": (200, {}, ICS)}
        dns = {"a.example": [PUBLIC], "internal.example": ["169.254.169.254"]}
        with self.assertRaises(sf.FetchError) as cm:
            run("https://a.example/c", routes, dns)
        self.assertEqual(cm.exception.code, "redirect")

    def test_redirect_to_literal_ip_or_http_blocked(self):
        for loc in ["https://127.0.0.1/x", "http://b.example/x", "https://2130706433/", "ftp://b.example/", "file:///etc/passwd"]:
            routes = {"a.example": (301, {"location": loc}, b""), "b.example": (200, {}, ICS)}
            with self.assertRaises(sf.FetchError) as cm:
                run("https://a.example/c", routes, {"a.example": [PUBLIC], "b.example": [PUBLIC]})
            self.assertEqual(cm.exception.code, "redirect", loc)

    def test_follows_up_to_three_redirects(self):
        routes = {"h0.example": (302, {"location": "https://h1.example/"}, b""),
                  "h1.example": (302, {"location": "https://h2.example/"}, b""),
                  "h2.example": (200, {}, ICS)}
        dns = {h: [PUBLIC] for h in ("h0.example", "h1.example", "h2.example")}
        body, t = run("https://h0.example/", routes, dns)
        self.assertEqual(body, ICS)
        self.assertEqual(len(t.calls), 3)

    def test_four_redirects_is_too_many_and_loops_end(self):
        routes = {"loop.example": (302, {"location": "https://loop.example/"}, b"")}
        with self.assertRaises(sf.FetchError) as cm:
            run("https://loop.example/", routes, {"loop.example": [PUBLIC]})
        self.assertEqual(cm.exception.code, "redirect")

    def test_redirect_without_location(self):
        with self.assertRaises(sf.FetchError):
            run("https://a.example/", {"a.example": (302, {}, b"")}, {"a.example": [PUBLIC]})

    def test_oversize_body(self):
        with self.assertRaises(sf.FetchError) as cm:
            run("https://a.example/", {"a.example": (200, {}, b"x" * 101)}, {"a.example": [PUBLIC]}, max_bytes=100)
        self.assertEqual(cm.exception.code, "too_large")

    def test_non_200(self):
        with self.assertRaises(sf.FetchError) as cm:
            run("https://a.example/", {"a.example": (403, {}, b"")}, {"a.example": [PUBLIC]})
        self.assertEqual((cm.exception.code, cm.exception.status), ("http_status", 403))

    def test_errors_never_contain_the_url(self):
        secret = "https://secret-host.example/feed/TOP-SECRET-TOKEN.ics"
        for dns, routes in [({}, {}), ({"secret-host.example": ["10.0.0.1"]}, {})]:
            with self.assertRaises(sf.FetchError) as cm:
                run(secret, routes, dns)
            for text in (str(cm.exception), cm.exception.message, repr(cm.exception)):
                self.assertNotIn("TOP-SECRET", text)
                self.assertNotIn("secret-host", text)

    def test_fetch_ical_checks_content(self):
        t = FakeTransport({"a.example": (200, {}, b"<html>login</html>")})
        with self.assertRaises(sf.FetchError) as cm:
            sf.fetch_ical("https://a.example/", resolver=resolver_for({"a.example": [PUBLIC]}), transport=t)
        self.assertEqual(cm.exception.code, "not_ical")
        t2 = FakeTransport({"a.example": (200, {}, b"\xef\xbb\xbfBEGIN:VCALENDAR\r\nEND:VCALENDAR")})
        text = sf.fetch_ical("https://a.example/", resolver=resolver_for({"a.example": [PUBLIC]}), transport=t2)
        self.assertTrue(text.startswith("BEGIN:VCALENDAR"))

    def test_real_transport_is_pinned_without_connecting(self):
        c = sf._PinnedHTTPSConnection("bb.example.edu", PUBLIC, 3)
        self.assertEqual((c.host, c._ip), ("bb.example.edu", PUBLIC))


if __name__ == "__main__":
    unittest.main()
