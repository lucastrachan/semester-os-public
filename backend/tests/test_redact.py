import io
import sys
import unittest

from _fakes import FakeDb  # noqa
from lib import redact


class Redact(unittest.TestCase):
    def test_jwt_bearer_aws(self):
        jwt = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJlc2lnbg"
        s = redact.redact(f"Authorization: Bearer {jwt} key AKIAIOSFODNN7EXAMPLE tok {jwt}")
        self.assertNotIn("eyJ", s)
        self.assertNotIn("AKIA", s)

    def test_secret_contexts(self):
        for line in ['x-admin-key: hunter2hunter2', 'password="abc12345"', "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG"]:
            out = redact.redact(line)
            self.assertIn("[redacted]", out)
            self.assertNotIn("hunter2", out)
            self.assertNotIn("abc12345", out)

    def test_feed_url_and_query_urls(self):
        feed = "https://bb.example.edu/webapps/calendar/calendarFeed/abcDEF123456/learn.ics"
        self.assertEqual(redact.redact(f"fetching {feed}"), "fetching [feed-url]")
        self.assertEqual(redact.redact("see https://example.com/page?token=SECRET&x=1"), "see https://example.com/page?[redacted]")
        self.assertEqual(redact.redact("see https://example.com/page"), "see https://example.com/page")
        self.assertEqual(redact.redact("webcal://x.example/c.ics"), "[feed-url]")

    def test_cal_token_path_and_email(self):
        self.assertEqual(redact.redact("GET /cal/abcdefghij0123456789abcd.ics"), "GET /cal/[token].ics")
        out = redact.redact("user student@example.edu failed")
        self.assertNotIn("student@", out)
        self.assertIn("[email]", out)

    def test_long_tokens_and_safe(self):
        self.assertIn("[token]", redact.redact("x" * 10 + "A1b2" * 10))
        self.assertLessEqual(len(redact.safe(Exception("a b " * 500))), 500)
        self.assertEqual(redact.redact(None), "None")

    def test_stdout_install_is_idempotent_and_redacts(self):
        real = sys.stdout
        buf = io.StringIO()
        sys.stdout = buf
        try:
            redact.install()
            redact.install()
            print("mail me at a.b@school.edu")
            wrapped_once = not isinstance(sys.stdout._inner, redact._RedactingStream)
        finally:
            sys.stdout = real
        self.assertNotIn("a.b@school.edu", buf.getvalue())
        self.assertTrue(wrapped_once)


if __name__ == "__main__":
    unittest.main()
