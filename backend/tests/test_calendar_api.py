import unittest

from _fakes import FakeCounterTable, FakeDb
import calendar_api as cal
from lib import limits

SUB = "user-aaaa-1111"
OTHER = "user-bbbb-2222"
TOKEN = "a1b2c3d4e5f6g7h8i9j0k1l2"      # a 24-char token from the first profile format


class Db(FakeDb):
    def incr_counter(self, pk, sk, ttl):
        row = self.items.setdefault((pk, sk), {"pk": pk, "sk": sk, "n": 0})
        row["n"] += 1
        return row["n"]


def feed_event(token, ip="203.0.113.5"):
    return {"rawPath": f"/cal/{token}.ics", "requestContext": {"http": {"sourceIp": ip}}}


def rotate_event():
    return {"requestContext": {"http": {"sourceIp": "203.0.113.5"}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Db()
        self.counter = FakeCounterTable()
        cal.db = self.db
        cal._table = lambda: self.counter
        db = self.db
        db.put_item({"pk": "TENANTS", "sk": "T#ua-edu", "timezone": "America/Chicago"})
        for sub, tok in ((SUB, TOKEN), (OTHER, "zzzz9999yyyy8888xxxx7777")):
            db.put_item({"pk": f"USER#{sub}", "sk": "PROFILE", "sub": sub, "email": "secret@ua.edu", "tenantId": "ua-edu", "calToken": tok})
            db.put_item({"pk": f"CAL#{tok}", "sk": "MAP", "sub": sub})
        db.put_item({"pk": f"USER#{SUB}", "sk": "COURSE#course01", "id": "course01", "courseCode": "MIS 405", "color": "#0D9488"})
        db.put_item({"pk": f"USER#{SUB}", "sk": "ASG#course01#ab12cd34", "id": "ab12cd34", "courseId": "course01", "title": "Quiz 3",
                     "type": "quiz", "dueDate": "2026-11-05", "dueTime": "14:30", "sequence": 3, "updatedAt": "2026-10-02T10:00:00Z"})
        db.put_item({"pk": f"USER#{OTHER}", "sk": "ASG#course02#cd34ef56", "id": "cd34ef56", "courseId": "course02", "title": "Other secret",
                     "type": "exam", "dueDate": "2026-11-06"})


class Feed(Base):
    def test_valid_token_returns_calendar(self):
        r = cal.get_feed(feed_event(TOKEN))
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(r["headers"]["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn("private", r["headers"]["Cache-Control"])
        body = r["body"]
        self.assertIn("SUMMARY:[MIS 405] Quiz 3", body)
        self.assertIn("DTEND:20261105T203000Z", body)      # campus timezone from the tenant
        self.assertIn("SEQUENCE:3", body)
        self.assertNotIn("Other secret", body)             # only this user's items
        self.assertNotIn(TOKEN, body)
        self.assertNotIn("secret@ua.edu", body)             # no profile data leaks into the file

    def test_feed_is_deterministic(self):
        self.assertEqual(cal.get_feed(feed_event(TOKEN))["body"], cal.get_feed(feed_event(TOKEN))["body"])

    def test_done_items_leave_the_feed(self):
        self.db.update_item(f"USER#{SUB}", "ASG#course01#ab12cd34", {"done": True})
        self.assertNotIn("BEGIN:VEVENT", cal.get_feed(feed_event(TOKEN))["body"])

    def test_study_blocks_included(self):
        self.db.put_item({"pk": f"USER#{SUB}", "sk": "STUDY#course01#st000001", "id": "st000001", "courseId": "course01",
                          "start": "2026-11-04T19:00:00", "end": "2026-11-04T20:00:00", "focus": "Ch 4"})
        self.assertIn("Study: Ch 4", cal.get_feed(feed_event(TOKEN))["body"])

    def test_malformed_and_unknown_tokens_are_404(self):
        for t in ("short", "UPPERCASE0000000000000000", "a" * 100, "has space 123456789012345678", "..%2f..", "a1b2c3d4e5f6g7h8i9j0k1l3"):
            r = cal.get_feed(feed_event(t))
            self.assertEqual(r["statusCode"], 404, t)
        self.assertEqual(cal.get_feed({"rawPath": "/cal/notics", "requestContext": {}})["statusCode"], 404)
        self.assertEqual(cal.get_feed({"rawPath": "/cal/" + TOKEN + ".ics/extra", "requestContext": {}})["statusCode"], 404)

    def test_deleted_user_is_404_not_500(self):
        self.db.delete_item(f"USER#{SUB}", "PROFILE")        # profile gone, CAL map left behind
        self.assertEqual(cal.get_feed(feed_event(TOKEN))["statusCode"], 404)
        self.db.items.clear()                                 # everything gone
        self.assertEqual(cal.get_feed(feed_event(TOKEN))["statusCode"], 404)

    def test_map_pointing_at_a_user_with_a_different_token_is_404(self):
        self.db.put_item({"pk": "CAL#oldtoken0000000000000000", "sk": "MAP", "sub": SUB})
        self.assertEqual(cal.get_feed(feed_event("oldtoken0000000000000000"))["statusCode"], 404)

    def test_missing_tenant_falls_back_not_crashes(self):
        self.db.delete_item("TENANTS", "T#ua-edu")
        self.assertEqual(cal.get_feed(feed_event(TOKEN))["statusCode"], 200)

    def test_per_ip_limit_counts_misses_only(self):
        per_hour, _ = limits.IP_LIMITS.get("cal_miss", limits.IP_LIMITS["default"])
        for _ in range(per_hour + 20):                          # successful refreshes never count
            self.assertEqual(cal.get_feed(feed_event(TOKEN))["statusCode"], 200)
        codes = [cal.get_feed(feed_event("nope" * 8))["statusCode"] for _ in range(per_hour + 1)]
        self.assertEqual(codes[0], 404)
        self.assertEqual(codes[-1], 429)
        self.assertEqual(cal.get_feed(feed_event("nope" * 8, ip="198.51.100.7"))["statusCode"], 404)  # other client unaffected
        self.assertEqual(cal.get_feed(feed_event(TOKEN))["statusCode"], 200)                          # valid token still works


class Rotate(Base):
    def test_rotation_invalidates_old_token_and_new_one_works(self):
        r = cal.rotate_token(rotate_event(), SUB)
        self.assertEqual(r["statusCode"], 200)
        import json
        out = json.loads(r["body"])
        new = out["calToken"]
        self.assertRegex(new, r"^[a-z0-9]{32}$")
        self.assertEqual(out["calendarPath"], f"/cal/{new}.ics")
        self.assertEqual(cal.get_feed(feed_event(TOKEN))["statusCode"], 404)
        self.assertEqual(cal.get_feed(feed_event(new))["statusCode"], 200)
        self.assertIsNone(self.db.get_item(f"CAL#{TOKEN}", "MAP"))
        self.assertEqual(self.db.get_item(f"USER#{SUB}", "PROFILE")["calToken"], new)
        self.assertEqual(self.db.get_item(f"CAL#{new}", "MAP")["sub"], SUB)

    def test_rotation_leaves_other_users_alone(self):
        cal.rotate_token(rotate_event(), SUB)
        self.assertEqual(cal.get_feed(feed_event("zzzz9999yyyy8888xxxx7777"))["statusCode"], 200)

    def test_tokens_are_random_and_long(self):
        toks = {cal.new_token() for _ in range(200)}
        self.assertEqual(len(toks), 200)
        self.assertTrue(all(len(t) == 32 for t in toks))

    def test_rotate_without_profile_is_404(self):
        self.db.delete_item(f"USER#{SUB}", "PROFILE")
        self.assertEqual(cal.rotate_token(rotate_event(), SUB)["statusCode"], 404)

    def test_bad_sub_is_401(self):
        self.assertEqual(cal.rotate_token(rotate_event(), "x")["statusCode"], 401)

    def test_daily_rotation_cap(self):
        codes = [cal.rotate_token(rotate_event(), SUB)["statusCode"] for _ in range(cal.ROTATIONS_PER_DAY + 2)]
        self.assertEqual(codes[:cal.ROTATIONS_PER_DAY], [200] * cal.ROTATIONS_PER_DAY)
        self.assertEqual(codes[-1], 429)


if __name__ == "__main__":
    unittest.main()
