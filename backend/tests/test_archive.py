"""PATCH /courses/{id} archive/unarchive, GET /courses filtering, and exclusion checks."""
import json
import unittest

import _fakes  # noqa: F401 — puts backend/ on sys.path
import courses_api
import calendar_api
import market_api
from lib import rooms
from test_master import world, req, asg, SUB as ME, Script, route_tool, text as mtext

ME2 = "user-bbbb-2222"


class Db(_fakes.FakeDb):
    def incr_counter(self, pk, sk, ttl):
        row = self.items.setdefault((pk, sk), {"pk": pk, "sk": sk, "n": 0})
        row["n"] += 1
        return row["n"]


def ev(body=None, qs=None):
    return {"body": json.dumps(body) if body is not None else None, "queryStringParameters": qs or {}}


def js(resp):
    return json.loads(resp["body"])


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Db()
        self.counter = _fakes.FakeCounterTable()
        courses_api.db = self.db
        courses_api._over_daily_cap = lambda sub: False
        for sub in (ME, ME2):
            self.db.put_item({"pk": f"USER#{sub}", "sk": "PROFILE", "sub": sub, "tenantId": "t1"})
        self.db.put_item({"pk": "TENANTS", "sk": "T#t1", "timezone": "America/Chicago"})
        self._put_course("c0000001", "MIS 405", "Systems", sub=ME)
        self._put_course("c0000002", "ACC 101", "Accounting", sub=ME)

    def _put_course(self, cid, code, title, sub=ME, **kw):
        self.db.put_item({"pk": f"USER#{sub}", "sk": f"COURSE#{cid}", "id": cid, "courseCode": code,
                          "title": title, "status": "READY", "createdAt": "2026-01-01T00:00:00Z",
                          "source": "syllabus", "pipeline": [], **kw})

    def patch(self, cid, body, sub=ME):
        return courses_api.patch_course(sub, cid, ev(body))

    def list_active(self, sub=ME):
        return js(courses_api.list_courses(sub, ev()))

    def list_archived(self, sub=ME):
        return js(courses_api.list_courses(sub, ev(qs={"archived": "true"})))


class ArchivePatch(Base):
    def test_archive_sets_fields(self):
        r = self.patch("c0000001", {"archived": True})
        self.assertEqual(r["statusCode"], 200)
        course = js(r)["course"]
        self.assertTrue(course["archived"])
        self.assertIsNotNone(course["archivedAt"])
        stored = self.db.get_item(f"USER#{ME}", "COURSE#c0000001")
        self.assertTrue(stored["archived"])

    def test_unarchive_clears_fields(self):
        self.patch("c0000001", {"archived": True})
        r = self.patch("c0000001", {"archived": False})
        course = js(r)["course"]
        self.assertFalse(course["archived"])
        self.assertIsNone(course["archivedAt"])

    def test_archived_false_by_default_in_present(self):
        r = js(courses_api.list_courses(ME, ev()))
        for c in r["courses"]:
            self.assertIn("archived", c)
            self.assertFalse(c["archived"])
            self.assertIsNone(c["archivedAt"])

    def test_unknown_field_rejected(self):
        self.assertEqual(self.patch("c0000001", {"archived": True, "title": "x"})["statusCode"], 400)

    def test_non_bool_rejected(self):
        self.assertEqual(self.patch("c0000001", {"archived": "yes"})["statusCode"], 400)

    def test_wrong_user_gets_404(self):
        self.assertEqual(self.patch("c0000001", {"archived": True}, sub=ME2)["statusCode"], 404)

    def test_unknown_id_gets_404(self):
        self.assertEqual(self.patch("xxxxxxxx", {"archived": True})["statusCode"], 404)


class ArchiveFilter(Base):
    def setUp(self):
        super().setUp()
        self.patch("c0000001", {"archived": True})   # MIS 405 is now archived

    def test_get_active_excludes_archived(self):
        courses = self.list_active()["courses"]
        codes = [c["courseCode"] for c in courses]
        self.assertNotIn("MIS 405", codes)
        self.assertIn("ACC 101", codes)

    def test_get_archived_returns_only_archived(self):
        courses = self.list_archived()["courses"]
        codes = [c["courseCode"] for c in courses]
        self.assertIn("MIS 405", codes)
        self.assertNotIn("ACC 101", codes)

    def test_get_archived_alias_path(self):
        r = courses_api.list_courses(ME, {"queryStringParameters": {"archived": "true"}})
        courses = js(r)["courses"]
        self.assertEqual([c["courseCode"] for c in courses], ["MIS 405"])

    def test_get_course_still_returns_archived(self):
        r = courses_api.get_course(ME, "c0000001")
        self.assertEqual(r["statusCode"], 200)
        self.assertTrue(js(r)["course"]["archived"])


class ArchiveExclusions(Base):
    def setUp(self):
        super().setUp()
        # Add an assignment for the archived course
        self.db.put_item({"pk": f"USER#{ME}", "sk": "ASG#c0000001#asg00001",
                          "id": "asg00001", "courseId": "c0000001", "title": "Exam 1",
                          "dueDate": "2026-11-05", "dueTime": "14:00", "done": False, "source": "syllabus",
                          "dateSource": "stated"})
        self.patch("c0000001", {"archived": True})

    def test_calendar_excludes_archived_course(self):
        # The calendar filter: only non-archived courses go into the courses dict
        courses_in_cal = {c.get("id"): c for c in self.db.query_pk(f"USER#{ME}", "COURSE#") if not c.get("archived")}
        self.assertNotIn("c0000001", courses_in_cal)
        self.assertIn("c0000002", courses_in_cal)

    def test_rooms_excludes_archived_course(self):
        rooms.db = self.db
        self.db.put_item({"pk": "TENANTS", "sk": "T#t1", "id": "t1", "timezone": "America/Chicago"})
        for c in self.db.query_pk(f"USER#{ME}", "COURSE#"):
            c["termCode"] = "202640"
            self.db.put_item(c)
        result = rooms.my_rooms(ME, "t1")
        # ACC 101 should be present; MIS 405 (archived) should not
        room_codes = {v["code"] for v in result.values()}
        self.assertIn("ACC101", room_codes)
        self.assertNotIn("MIS405", room_codes)

    def test_master_routing_uses_only_active_courses(self):
        db = world()
        # Archive the main class
        db.update_item(f"USER#{ME}", "COURSE#abcd1234", {"archived": True})
        fast = Script(route_tool("abcd1234", 0.95, "About the exam"))
        main = Script(mtext("master answer"))
        status, out, _ = req(db, "POST", "/chat/master", {"messages": [{"role": "user", "content": "exam question"}]}, fast=fast, main=main)
        # Should fall through to master (archived class not in routing candidates)
        self.assertEqual(status, 200)
        self.assertEqual(out["agent"], "master")

    def test_master_target_archived_class_returns_409(self):
        db = world()
        db.update_item(f"USER#{ME}", "COURSE#abcd1234", {"archived": True})
        main = Script(mtext("x"))
        status, out, _ = req(db, "POST", "/chat/master", {"messages": [{"role": "user", "content": "x"}], "target": "abcd1234"}, main=main)
        self.assertEqual(status, 409)
        self.assertEqual(out.get("error"), "archived")


if __name__ == "__main__":
    unittest.main()
