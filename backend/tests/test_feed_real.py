"""Regression: the REAL lib/db.py and the REAL feed_api._put_feed path against a fake DynamoDB table that behaves like
the real one (rejects floats, returns Decimal for numbers, parses the update expressions db.py builds) and a fake KMS
that validates parameter types, fed a realistic synthetic Blackboard style calendar (no real student data)."""
import contextlib
import io
import json
import os
import re
import unittest
from decimal import Decimal

import _fakes  # noqa: F401 (sets sys.path)
import feed_api
import sync_blackboard
from lib import db, feedsync, secretbox

ME = "user-aaaa-1111"
URL = "https://bb.example.edu/webapps/calendar/calendarFeed/SECRETTOKEN123456/learn.ics"
CRLF = "\r\n"


def _check(v, path="item"):
    if isinstance(v, float):
        raise TypeError("Float types are not supported. Use Decimal types instead.")
    if isinstance(v, (set, frozenset)):
        raise TypeError("sets are not allowed here")
    if v is not None and not isinstance(v, (str, bool, int, Decimal, bytes, list, dict)):
        raise TypeError(f"Unsupported type {type(v).__name__} at {path}")
    if isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str):
                raise TypeError("map keys must be strings")
            _check(x, f"{path}.{k}")
    if isinstance(v, list):
        for i, x in enumerate(v):
            _check(x, f"{path}[{i}]")


def _dec(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, dict):
        return {k: _dec(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_dec(x) for x in v]
    return v


class ClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class DynTable:
    """Just enough of boto3's Table for lib/db.py and lib/limits.py."""

    def __init__(self):
        self.items = {}

    def get_item(self, Key):
        it = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": json.loads(json.dumps(it, default=lambda o: o)) if False else dict(it)} if it else {}

    def put_item(self, Item):
        _check(Item)
        self.items[(Item["pk"], Item["sk"])] = _dec(dict(Item))

    def delete_item(self, Key):
        self.items.pop((Key["pk"], Key["sk"]), None)

    def query(self, KeyConditionExpression, **kw):
        expr = KeyConditionExpression.get_expression()
        conds = [expr] if expr["operator"] != "AND" else list(expr["values"])
        pk, prefix = None, None
        for c in conds:
            e = c.get_expression() if hasattr(c, "get_expression") else c
            if e["operator"] == "=":
                pk = e["values"][1]
            elif e["operator"] == "begins_with":
                prefix = e["values"][1]
        rows = [dict(v) for (p, s), v in sorted(self.items.items()) if p == pk and (prefix is None or s.startswith(prefix))]
        return {"Items": rows}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues, ConditionExpression=None, ReturnValues=None):
        _check(ExpressionAttributeValues)
        k = (Key["pk"], Key["sk"])
        row = self.items.setdefault(k, {"pk": Key["pk"], "sk": Key["sk"]}) if not ConditionExpression else self.items.setdefault(k, {})
        names, vals = ExpressionAttributeNames, ExpressionAttributeValues
        if ConditionExpression:
            n = row.get("n")
            if n is not None and not n < vals[":limit"]:
                raise ClientError("ConditionalCheckFailedException")
        for m in re.finditer(r"(?:SET\s+|,\s*)(#\w+)\s*=\s*(if_not_exists\((#\w+),\s*(:\w+)\)|(:\w+))", UpdateExpression):
            name = names[m.group(1)]
            if m.group(3):
                row.setdefault(name, _dec(vals[m.group(4)]))
            else:
                row[name] = _dec(vals[m.group(5)])
        add = re.search(r"ADD\s+(#\w+)\s+(:\w+)", UpdateExpression)
        if add:
            nm = names[add.group(1)]
            row[nm] = Decimal(row.get(nm, 0)) + vals[add.group(2)]
        return {"Attributes": dict(row)}

    def batch_writer(self):
        outer = self

        class W:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def delete_item(self, Key):
                outer.delete_item(Key)
        return W()


class StrictKms:
    def __init__(self):
        self.calls = 0

    def encrypt(self, **kw):
        self.calls += 1
        assert set(kw) == {"KeyId", "Plaintext", "EncryptionContext"}, kw.keys()
        assert isinstance(kw["KeyId"], str) and isinstance(kw["Plaintext"], bytes)
        assert all(isinstance(a, str) and isinstance(b, str) for a, b in kw["EncryptionContext"].items())
        return {"CiphertextBlob": b"KMS" + kw["Plaintext"][::-1]}

    def decrypt(self, **kw):
        assert isinstance(kw["CiphertextBlob"], bytes) and isinstance(kw["EncryptionContext"], dict)
        return {"Plaintext": kw["CiphertextBlob"][3:][::-1]}


def folded(line, width=60):
    out, first = [], True
    data = line
    while len(data.encode()) > width:
        cut = width
        while len(data[:cut].encode()) > width:
            cut -= 1
        out.append(data[:cut])
        data = data[cut:]
        width = 59
    out.append(data)
    return (CRLF + " ").join(out)


def realistic_ics():
    tz = ["BEGIN:VTIMEZONE", "TZID:America/Chicago", "X-LIC-LOCATION:America/Chicago", "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0600",
          "TZOFFSETTO:-0500", "TZNAME:CDT", "DTSTART:19700308T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
          "BEGIN:STANDARD", "TZOFFSETFROM:-0500", "TZOFFSETTO:-0600", "TZNAME:CST", "DTSTART:19701101T020000",
          "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD", "END:VTIMEZONE"]

    def ev(uid, summary, start_line, desc=None, cats=None, extra=()):
        lines = ["BEGIN:VEVENT", f"UID:{uid}", "DTSTAMP:20261017T150000Z", start_line, f"SUMMARY:{summary}"]
        if desc:
            lines.append("DESCRIPTION:" + desc)
        if cats:
            lines.append("CATEGORIES:" + cats)
        lines += list(extra) + ["X-BB-ID:12345", "X-ALT-DESC;FMTTYPE=text/html:<p>hi</p>", "END:VEVENT"]
        return CRLF.join(folded(x) if len(x) > 60 else x for x in lines)

    due = "Due date: 10/19/26\\, 5:00 PM (CDT) ∙ 40541.202640: 202640-EN-210-010"
    return CRLF.join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Blackboard Inc.//Learn//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:My Calendar", "X-WR-TIMEZONE:America/Chicago", *tz,
        ev("_1234_1", "10/19 Reading Journal", "DTSTART;TZID=America/Chicago:20261019T170000", due, "40541.202640: 202640-EN-210-010"),
        ev("_1235_1", "Essay 2 – café résumé ☃", "DTSTART;VALUE=DATE:20261105", "Due date: 11/5/26\\, 11:59 PM (CST) ∙ 40541.202640: 202640-EN-210-010"),
        ev("_2001_1", "Quiz 3", "DTSTART:20261107T045900Z", "Due date: 11/6/26\\, 11:59 PM (CST) ∙ 40611.202640: 202640-MIS-430-001",
           extra=["RRULE:FREQ=WEEKLY;COUNT=3", "DTEND:20261107T050000Z"]),
        ev("_2002_1", "Project proposal", "DTSTART;TZID=America/Chicago:20261110T235900", None, "40611.202640: 202640-MIS-430-001"),
        ev("0f8c-ab12@bb.example.edu", "Old term homework", "DTSTART;VALUE=DATE:20261020", "40001.202530: 202530-ACC-100-001"),
        ev("_3001_1", "No time zone info", "DTSTART:20261112T180000", "Due date: 11/12/26\\, 6:00 PM (CST)"),
        ev("_3002_1", "Weird date", "DTSTART:2026-11-13 18:00", "Due date: 2/30/26\\, 1:00 PM (CST)"),
        "BEGIN:VEVENT", "UID:_9999_1", "SUMMARY:Event with no start at all", "END:VEVENT",
        "BEGIN:VEVENT", "SUMMARY:No uid and bad \\ escape\\", "DTSTART;VALUE=DATE:20261114", "END:VEVENT",
        "END:VCALENDAR", ""])


class RealPath(unittest.TestCase):
    def setUp(self):
        self.table = DynTable()
        self._saved = db._table
        db._table = self.table
        self.kms = StrictKms()
        secretbox.set_kms_client(self.kms)
        os.environ["KMS_KEY_ID"] = "alias/feed"
        os.environ["REQUIRE_KMS"] = "1"
        self.addCleanup(self.cleanup)
        db.put_item({"pk": f"USER#{ME}", "sk": "PROFILE", "sub": ME, "tenantId": "t1", "email": "student@example.edu"})
        db.put_item({"pk": "TENANTS", "sk": "T#t1", "timezone": "America/Chicago"})
        db.put_item({"pk": f"USER#{ME}", "sk": "COURSE#c0000210", "id": "c0000210", "courseCode": "EN 210", "title": "",
                     "knows": {"newItemsCount": 0, "assignmentsCount": 0}})
        self.text = realistic_ics()
        self.now = 1792238400.5   # a float with a fraction, like time.time()

    def cleanup(self):
        db._table = self._saved
        secretbox.set_kms_client(None)
        os.environ.pop("KMS_KEY_ID", None)
        os.environ.pop("REQUIRE_KMS", None)

    def call(self, method, path, body=None):
        deps = {"fetch": lambda url, **kw: self.text, "now": self.now}
        if getattr(self, "rules", None):
            deps["rules"] = self.rules   # real db module, real table fake
        r = feed_api.handle({"body": json.dumps(body) if body is not None else None}, ME, path, method, deps)
        return r["statusCode"], json.loads(r["body"]), r

    def test_put_feed_with_realistic_feed_succeeds(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            st, body, _ = self.call("PUT", "/me/feed", {"url": URL})
        self.assertEqual(st, 200, (body, buf.getvalue()))
        self.assertTrue(body["connected"])
        self.assertGreaterEqual(body["eventCount"], 6)
        self.assertEqual(self.kms.calls, 1)
        cfg = self.table.items[(f"USER#{ME}", "FEED")]
        self.assertTrue(cfg["urlEnc"].startswith("kms1:"))
        for item in self.table.items.values():
            self.assertNotIn("SECRETTOKEN", json.dumps(item, default=str))

    def test_classes_sync_and_poller_with_realistic_feed(self):
        self.assertEqual(self.call("PUT", "/me/feed", {"url": URL})[0], 200)
        st, body, _ = self.call("GET", "/me/feed/classes")
        self.assertEqual(st, 200, body)
        codes = {c["code"]: c for c in body["classes"]}
        self.assertEqual(set(codes), {"EN 210", "MIS 430"})                 # the old term is not offered
        self.assertEqual(codes["EN 210"]["matchedCourseId"], "c0000210")
        self.assertEqual(codes["EN 210"]["eventCount"], 2)
        self.now += 300
        st, body, _ = self.call("POST", "/me/feed/sync")
        self.assertEqual(st, 200, body)
        asg = [v for (p, s), v in self.table.items.items() if s.startswith("ASG#")]
        titles = {a["title"] for a in asg}
        self.assertIn("10/19 Reading Journal", titles)
        self.assertNotIn("Old term homework", titles)
        j = next(a for a in asg if a["title"] == "10/19 Reading Journal")
        self.assertEqual((j["dueDate"], j["dueTime"], j["courseId"]), ("2026-10-19", "17:00", "c0000210"))
        # poller path with the same real table
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = sync_blackboard.process_batch(5, {"fetch": lambda u, **kw: self.text}, now=self.now + 7200)
        self.assertEqual((r["ok"], r["failed"]), (1, 0), buf.getvalue())
        self.assertNotIn("SECRETTOKEN", buf.getvalue())

    def test_auto_import_through_strict_table(self):
        self.table.items.pop((f"USER#{ME}", "COURSE#c0000210"))
        self.rules = {**feedsync.load_rules(), "autoImportClasses": True}
        st, body, _ = self.call("PUT", "/me/feed", {"url": URL})
        self.assertEqual(st, 200, body)
        self.assertEqual({c["code"] for c in body["importedClasses"]}, {"EN 210", "MIS 430"})
        self.now += 300
        st, body, _ = self.call("POST", "/me/feed/sync")
        self.assertEqual(st, 200, body)
        self.assertGreaterEqual(len([1 for (p, s) in self.table.items if s.startswith("ASG#")]), 4)

    def test_one_odd_event_cannot_fail_the_feed(self):
        orig = feedsync.classify
        calls = {"n": 0}

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise TypeError("boom")
            return orig(*a, **k)
        feedsync.classify = flaky
        self.addCleanup(setattr, feedsync, "classify", orig)
        self.assertEqual(self.call("PUT", "/me/feed", {"url": URL})[0], 200)
        self.now += 300
        st, body, _ = self.call("POST", "/me/feed/sync")
        self.assertEqual(st, 200, body)
        self.assertGreaterEqual(len([1 for (p, s) in self.table.items if s.startswith("ASG#")]), 1)

    def test_parse_garbage_values_skipped_not_fatal(self):
        evs, skipped = feedsync.parse_ics_ex(self.text, "America/Chicago")
        self.assertGreaterEqual(len(evs), 7)
        self.assertIsInstance(skipped, int)
        by = {e["title"]: e for e in evs}
        self.assertEqual(by["Weird date"]["dueDate"], None)
        self.assertTrue(by["Essay 2 – café résumé ☃"]["allDay"])
        self.assertEqual(by["No time zone info"]["dueTime"], "18:00")

    def test_dynamo_safe_and_safe_trace(self):
        d = feedsync.dynamo_safe({"a": 1.5, "b": {1, 2}, "c": (1, 2.0), "d": float("nan"), "e": None})
        self.assertEqual(d["a"], Decimal("1.5"))
        self.assertIsNone(d["d"])
        _check(d)
        try:
            raise ValueError("https://secret.example/token")
        except ValueError as e:
            t = feedsync.safe_trace(e)
        self.assertIn("ValueError at test_feed_real.py:", t)
        self.assertNotIn("secret", t)

    def test_unexpected_error_log_has_frames_not_messages(self):
        def boom(url, **kw):
            raise TypeError("leaky https://bb.example.edu/SECRETTOKEN123456")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = feed_api.handle({"body": json.dumps({"url": URL})}, ME, "/me/feed", "PUT", {"fetch": boom, "now": self.now})
        self.assertEqual(r["statusCode"], 500)
        out = buf.getvalue()
        self.assertIn("feed_api unexpected error: TypeError at test_feed_real.py:", out)
        self.assertIn("feed_api.py:", out)
        self.assertNotIn("SECRETTOKEN", out)
        self.assertNotIn("leaky", out)


if __name__ == "__main__":
    unittest.main()
