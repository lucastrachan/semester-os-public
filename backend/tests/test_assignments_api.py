import json
import unittest
from datetime import date

from _fakes import FakeCounterTable, FakeDb
import assignments_api as api

ME = "user-aaaa-1111"
OTHER = "user-bbbb-2222"


class Db(FakeDb):
    def incr_counter(self, pk, sk, ttl):
        row = self.items.setdefault((pk, sk), {"pk": pk, "sk": sk, "n": 0})
        row["n"] += 1
        return row["n"]


def ev(body=None, qs=None):
    return {"body": json.dumps(body) if body is not None else None, "queryStringParameters": qs}


def js(resp):
    return json.loads(resp["body"])


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Db()
        self.counter = FakeCounterTable()
        api.db = self.db
        api._table = lambda: self.counter
        api._today = lambda: date(2026, 10, 17)
        for sub, cid, code, color in ((ME, "course01", "MIS 405", "#0D9488"), (OTHER, "course02", "ACC 100", "#E11D48")):
            self.db.put_item({"pk": f"USER#{sub}", "sk": f"COURSE#{cid}", "id": cid, "courseCode": code, "color": color})
        self.good = {"courseId": "course01", "title": "Quiz 3", "type": "quiz", "dueDate": "2026-11-05"}

    def create(self, **over):
        r = api.create_assignment(ev({**self.good, **over}), ME)
        return r, (js(r).get("assignment") or {})


class Create(Base):
    def test_create_and_shape(self):
        r, a = self.create(dueTime="14:30", weight=10, notes="Ch 1-3")
        self.assertEqual(r["statusCode"], 201)
        self.assertEqual((a["source"], a["dateSource"], a["sequence"], a["done"]), ("manual", "manual", 0, False))
        self.assertEqual((a["courseCode"], a["courseColor"]), ("MIS 405", "#0D9488"))
        self.assertRegex(a["id"], r"^[a-z0-9]{8}$")
        self.assertIn((f"USER#{ME}", f"ASG#course01#{a['id']}"), self.db.items)  # stored under the caller's key only

    def test_undated_item_has_no_date_source(self):
        _, a = self.create(dueDate=None)
        self.assertIsNone(a["dueDate"])
        self.assertIsNone(a["dateSource"])

    def test_validation(self):
        bad = [
            {"title": ""}, {"title": "x" * 161}, {"title": 5}, {"type": "nope"}, {"type": None},
            {"dueDate": "2026-02-30"}, {"dueDate": "11/05/2026"}, {"dueDate": "2030-01-01"},
            {"dueTime": "25:00"}, {"dueTime": "9:00"}, {"dueDate": None, "dueTime": "09:00"},
            {"weight": 101}, {"weight": -1}, {"weight": True}, {"weight": "10"}, {"notes": "n" * 401},
            {"courseId": "../etc"}, {"courseId": None}, {"unknown": 1}, {"done": True},
        ]
        for over in bad:
            r, _ = self.create(**over)
            self.assertEqual(r["statusCode"], 400, over)

    def test_invalid_json_and_non_object(self):
        self.assertEqual(api.create_assignment({"body": "{nope"}, ME)["statusCode"], 400)
        self.assertEqual(api.create_assignment({"body": "[1]"}, ME)["statusCode"], 400)

    def test_text_is_cleaned(self):
        _, a = self.create(title="Quiz‮​ 3\x00", notes="a​b")
        self.assertEqual(a["title"], "Quiz 3")
        self.assertEqual(a["notes"], "ab")

    def test_other_users_course_is_404(self):
        r, _ = self.create(courseId="course02")
        self.assertEqual(r["statusCode"], 404)
        self.assertFalse([k for k in self.db.items if k[1].startswith("ASG#")])

    def test_per_course_cap(self):
        api.MAX_PER_COURSE = 2
        try:
            self.create(); self.create()
            r, _ = self.create()
            self.assertEqual(r["statusCode"], 409)
        finally:
            api.MAX_PER_COURSE = 400

    def test_rate_limit(self):
        codes = [self.create()[0]["statusCode"] for _ in range(32)]
        self.assertEqual(codes[0], 201)
        self.assertIn(429, codes)

    def test_bad_sub_is_unauthorized(self):
        self.assertEqual(api.create_assignment(ev(self.good), "x")["statusCode"], 401)


class ListIt(Base):
    def setUp(self):
        super().setUp()
        self.a1 = self.create(title="Exam", dueDate="2026-11-05", dueTime="09:00")[1]
        self.a2 = self.create(title="Paper", dueDate="2026-10-20")[1]
        self.a3 = self.create(title="Reading", dueDate=None)[1]
        api.update_assignment(ev({"done": True}), ME, self.a2["id"])
        # someone else's item must never appear
        self.db.put_item({"pk": f"USER#{OTHER}", "sk": "ASG#course02#zzzzzzz9", "id": "zzzzzzz9", "courseId": "course02",
                          "title": "Theirs", "dueDate": "2026-11-05"})

    def titles(self, qs=None):
        r = api.list_assignments(ev(qs=qs), ME)
        self.assertEqual(r["statusCode"], 200)
        return [a["title"] for a in js(r)["assignments"]]

    def test_sorted_dated_first_undated_last_and_isolated(self):
        self.assertEqual(self.titles(), ["Paper", "Exam", "Reading"])

    def test_range_filters_exclude_undated_unless_asked(self):
        self.assertEqual(self.titles({"from": "2026-11-01", "to": "2026-11-30"}), ["Exam"])
        self.assertEqual(self.titles({"from": "2026-11-01", "undated": "include"}), ["Exam", "Reading"])
        self.assertEqual(self.titles({"to": "2026-10-31"}), ["Paper"])

    def test_done_filter_and_course_filter(self):
        self.assertEqual(self.titles({"done": "true"}), ["Paper"])
        self.assertEqual(self.titles({"done": "false"}), ["Exam", "Reading"])
        self.assertEqual(len(self.titles({"courseId": "course01"})), 3)

    def test_bad_queries(self):
        for qs in ({"from": "nope"}, {"from": "2026-12-01", "to": "2026-11-01"}, {"done": "maybe"}, {"courseId": "x y"}):
            self.assertEqual(api.list_assignments(ev(qs=qs), ME)["statusCode"], 400, qs)
        self.assertEqual(api.list_assignments(ev(qs={"courseId": "course02"}), ME)["statusCode"], 404)


class Patch(Base):
    def setUp(self):
        super().setUp()
        self.a = self.create(dueDate="2026-11-05", dueTime="09:00")[1]
        self.id = self.a["id"]

    def patch(self, body, sub=ME, asg_id=None):
        return api.update_assignment(ev(body), sub, asg_id or self.id)

    def test_edit_bumps_sequence_and_marks_manual(self):
        r = self.patch({"dueDate": "2026-11-06"})
        a = js(r)["assignment"]
        self.assertEqual((r["statusCode"], a["dueDate"], a["dateSource"], a["sequence"]), (200, "2026-11-06", "manual", 1))
        a = js(self.patch({"title": "Quiz 4"}))["assignment"]
        self.assertEqual((a["title"], a["sequence"]), ("Quiz 4", 2))

    def test_syllabus_date_becomes_manual_when_changed(self):
        self.db.put_item({"pk": f"USER#{ME}", "sk": "ASG#course01#syll0001", "id": "syll0001", "courseId": "course01",
                          "title": "HW", "type": "homework", "dueDate": "2026-11-10", "dateSource": "resolved", "source": "syllabus"})
        a = js(self.patch({"dueDate": "2026-11-11"}, asg_id="syll0001"))["assignment"]
        self.assertEqual((a["dateSource"], a["source"]), ("manual", "syllabus"))
        a = js(self.patch({"notes": "x"}, asg_id="syll0001"))["assignment"]
        self.assertEqual(a["dateSource"], "manual")  # unchanged by a non-date edit

    def test_non_date_edit_keeps_date_source(self):
        self.db.put_item({"pk": f"USER#{ME}", "sk": "ASG#course01#syll0002", "id": "syll0002", "courseId": "course01",
                          "title": "HW", "type": "homework", "dueDate": "2026-11-10", "dateSource": "resolved"})
        a = js(self.patch({"done": True}, asg_id="syll0002"))["assignment"]
        self.assertEqual((a["dateSource"], a["done"], a["sequence"]), ("resolved", True, 1))

    def test_noop_does_not_bump(self):
        a = js(self.patch({"title": self.a["title"]}))["assignment"]
        self.assertEqual(a["sequence"], 0)

    def test_clear_date_clears_time(self):
        a = js(self.patch({"dueDate": None}))["assignment"]
        self.assertEqual((a["dueDate"], a["dueTime"], a["dateSource"]), (None, None, None))

    def test_time_needs_date(self):
        self.patch({"dueDate": None})
        self.assertEqual(self.patch({"dueTime": "10:00"})["statusCode"], 400)
        self.assertEqual(self.patch({"dueDate": "2026-11-05", "dueTime": "10:00"})["statusCode"], 200)

    def test_validation_and_unknown_fields(self):
        for body in ({}, {"courseId": "course02"}, {"id": "x"}, {"title": ""}, {"dueDate": "2026-02-31"}, {"done": "yes"},
                     {"weight": 500}, {"type": "nope"}, {"notes": None}):
            self.assertEqual(self.patch(body)["statusCode"], 400, body)

    def test_mark_done_and_back(self):
        self.assertTrue(js(self.patch({"done": True}))["assignment"]["done"])
        self.assertFalse(js(self.patch({"done": False}))["assignment"]["done"])

    def test_other_users_item_and_unknown_ids_are_404(self):
        self.db.put_item({"pk": f"USER#{OTHER}", "sk": "ASG#course02#theirs01", "id": "theirs01", "courseId": "course02", "title": "T"})
        self.assertEqual(self.patch({"title": "mine now"}, asg_id="theirs01")["statusCode"], 404)
        self.assertEqual(self.db.items[(f"USER#{OTHER}", "ASG#course02#theirs01")]["title"], "T")
        self.assertEqual(self.patch({"title": "x"}, sub=OTHER)["statusCode"], 404)  # my id, their session
        for bad in ("nope", "../x", "ABCDEFGH", "toolongid1"):
            self.assertEqual(self.patch({"title": "x"}, asg_id=bad)["statusCode"], 404)

    def test_weight_float_and_clear(self):
        self.assertEqual(js(self.patch({"weight": 12.5}))["assignment"]["weight"], 12.5)
        self.assertIsNone(js(self.patch({"weight": None}))["assignment"]["weight"])


if __name__ == "__main__":
    unittest.main()
