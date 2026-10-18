"""POST /courses/import (browser extension) with the Decimal-returning, float-rejecting fake table. Synthetic data only."""
import unittest

import _fakes  # noqa: F401
import courses_api
import feed_api
from lib import feedsync
from test_feed import ME, OTHER, Env, ics, vevent

ID = "202640-EN-210-010"


def klass(code="EN 210", ident=ID, asg=None, **kw):
    return {"identifier": ident, "code": code, "section": "010", "term": "202640", "title": "American Literature",
            "instructor": "Dr. Jane Rivera",
            "assignments": asg if asg is not None else [
                {"title": "Reading Journal 1", "dueDate": "2026-10-19", "dueTime": "17:00", "tz": "CDT"},
                {"title": "Midterm Exam", "dueDate": "2026-11-05", "dueTime": "23:59", "tz": "CST"},
                {"title": "Quiz 3", "dueDate": "2026-11-09", "dueTime": None, "tz": ""}], **kw}


class Import(Env):
    def setUp(self):
        super().setUp()
        self.db.items = {k: v for k, v in self.db.items.items() if not k[1].startswith("COURSE#")}

    def imp(self, classes, sub=ME, source="blackboard"):
        return self.call("POST", "/courses/import", {"source": source, "classes": classes}, sub=sub)

    def courses(self, sub=ME):
        return [v for (p, s), v in self.db.items.items() if p == f"USER#{sub}" and s.startswith("COURSE#")]

    def test_creates_class_and_assignments(self):
        st, body, _ = self.imp([klass()])
        self.assertEqual(st, 201, body)
        (c,) = body["created"]
        self.assertEqual(set(c), {"id", "courseCode", "title", "color", "assignmentsAdded"})
        self.assertEqual((c["courseCode"], c["title"], c["assignmentsAdded"]), ("EN 210", "American Literature", 3))
        self.assertEqual((body["updated"], body["skipped"]), ([], 0))
        course = self.courses()[0]
        self.assertEqual((course["status"], course["source"], course["bbIdentifier"], course["section"], course["term"], course["instructor"]),
                         ("READY", "blackboard", ID, "010", "202640", "Dr. Jane Rivera"))
        self.assertTrue(all(s["state"] == "done" for s in course["pipeline"]))
        asg = {a["title"]: a for a in self.assignments()}
        j = asg["Reading Journal 1"]
        self.assertEqual((j["source"], j["dateSource"], j["type"], j["dueDate"], j["dueTime"], j["courseId"]),
                         ("blackboard", "stated", "reading", "2026-10-19", "17:00", c["id"]))     # CDT 17:00 is 17:00 in Chicago
        self.assertEqual((asg["Midterm Exam"]["type"], asg["Midterm Exam"]["dueTime"]), ("exam", "23:59"))   # CST label in Chicago winter
        self.assertEqual((asg["Quiz 3"]["type"], asg["Quiz 3"]["dueTime"]), ("quiz", None))
        self.assertEqual(course["knows"]["assignmentsCount"], 3)

    def test_time_zone_label_is_converted_to_the_campus_zone(self):
        self.db.items[("TENANTS", "T#t1")]["timezone"] = "America/New_York"
        self.imp([klass(asg=[{"title": "A", "dueDate": "2026-10-19", "dueTime": "17:00", "tz": "CDT"},
                             {"title": "B", "dueDate": "2026-10-19", "dueTime": "23:30", "tz": "PDT"}])])
        asg = {a["title"]: a for a in self.assignments()}
        self.assertEqual((asg["A"]["dueDate"], asg["A"]["dueTime"]), ("2026-10-19", "18:00"))
        self.assertEqual((asg["B"]["dueDate"], asg["B"]["dueTime"]), ("2026-10-20", "02:30"))

    def test_idempotent_reimport_updates_never_duplicates(self):
        self.imp([klass()])
        st, body, _ = self.imp([klass(asg=[{"title": "Reading Journal 1", "dueDate": "2026-10-19", "dueTime": "17:00", "tz": "CDT"},
                                           {"title": "New essay", "dueDate": "2026-11-20", "dueTime": "12:00", "tz": "CST"}])])
        self.assertEqual(st, 200)
        self.assertEqual(body["created"], [])
        self.assertEqual((body["updated"][0]["assignmentsAdded"], body["updated"][0]["assignmentsUpdated"]), (1, 0))
        self.assertEqual(len(self.courses()), 1)
        self.assertEqual(len(self.assignments()), 4)
        self.assertEqual(self.imp([klass()])[1]["updated"][0]["assignmentsAdded"], 0)
        self.assertEqual(len(self.assignments()), 4)

    def test_student_edits_win(self):
        self.imp([klass()])
        by = {a["title"]: a for a in self.assignments()}
        j = by["Reading Journal 1"]
        key = (f"USER#{ME}", f"ASG#{j['courseId']}#{j['id']}")
        self.db.items[key].update(title="My renamed journal", dueDate="2026-10-25", dateSource="manual", done=True)
        body = self.imp([klass()])[1]
        self.assertEqual((body["updated"][0]["assignmentsAdded"], len(self.assignments())), (0, 3))     # no duplicate of the edited item
        a = self.db.items[key]
        self.assertEqual((a["title"], a["dueDate"], a["dateSource"], a["done"]), ("My renamed journal", "2026-10-25", "manual", True))
        # an instructor-moved, untouched item follows the new date
        q = by["Quiz 3"]
        body = self.imp([klass(asg=[{"title": "Quiz 3", "dueDate": "2026-11-12", "dueTime": "09:00", "tz": "CST"}])])[1]
        self.assertEqual(body["updated"][0]["assignmentsUpdated"], 1)
        qkey = (f"USER#{ME}", f"ASG#{q['courseId']}#{q['id']}")
        moved = self.db.items[qkey]
        self.assertEqual((moved["dueDate"], moved["dueTime"], moved["dateSource"], moved["sequence"]), ("2026-11-12", "09:00", "stated", 1))
        # a manual date on a moved item: not overwritten, not duplicated
        self.db.items[qkey].update(dateSource="manual")
        self.imp([klass(asg=[{"title": "Quiz 3", "dueDate": "2026-11-30", "dueTime": None, "tz": ""}])])
        self.assertEqual(len([a for a in self.assignments() if a["title"] == "Quiz 3"]), 1)
        self.assertEqual(self.db.items[qkey]["dueDate"], "2026-11-12")

    def test_existing_class_with_same_code_is_adopted(self):
        self.course("c0000210", "EN 210", "")
        self.db.put_item({"pk": f"USER#{ME}", "sk": "ASG#c0000210#syl00001", "id": "syl00001", "courseId": "c0000210", "title": "Midterm exam",
                          "dueDate": "2026-11-05", "source": "syllabus", "dateSource": "stated"})
        st, body, _ = self.imp([klass()])
        self.assertEqual((st, body["created"]), (200, []))
        self.assertEqual(body["updated"][0]["id"], "c0000210")
        self.assertEqual(body["updated"][0]["assignmentsAdded"], 2)                 # the midterm already existed
        c = self.db.items[(f"USER#{ME}", "COURSE#c0000210")]
        self.assertEqual((c["bbIdentifier"], c["instructor"], c["title"]), (ID, "Dr. Jane Rivera", "American Literature"))
        self.assertEqual(len(self.courses()), 1)

    def test_validation_caps_and_cleaning(self):
        for body in ({"source": "blackboard"}, {"source": "blackboard", "classes": []},
                     {"source": "blackboard", "classes": [klass()] * 13}, {"source": "blackboard", "classes": ["x"]},
                     {"source": "blackboard", "classes": [{**klass(), "evil": 1}]},
                     {"source": "blackboard", "classes": [klass(asg=[{"title": "x", "dueDate": "2026-10-19", "extra": 1}])]},
                     {"source": "blackboard", "classes": [klass(asg=[{"title": "x", "dueDate": "2026-10-19"}] * 201)]},
                     {"source": "blackboard", "classes": [klass()], "x": 1}):
            self.assertEqual(self.call("POST", "/courses/import", body)[0], 400, str(body)[:80])
        hostile = [{"title": "<script>alert(1)</script>Paper‮\n" + "x" * 300, "dueDate": "2026-10-20", "dueTime": "09:00", "tz": "CDT"},
                   {"title": "bad date", "dueDate": "2026-02-30"}, {"title": "bad time", "dueDate": "2026-10-20", "dueTime": "25:61"},
                   {"title": "far", "dueDate": "2031-01-01"}, {"title": "", "dueDate": "2026-10-20"}, {"title": 5, "dueDate": "2026-10-20"}]
        st, body, _ = self.imp([klass(code="nonsense", ident=""), {**klass(), "identifier": "bad", "code": "ACC 100"},
                                klass(code="MIS 405", ident="202640-MIS-405-001", asg=hostile)])
        self.assertEqual(body["skipped"], 1)                                          # "nonsense" has no usable code
        self.assertEqual({c["courseCode"] for c in body["created"]}, {"ACC 100", "MIS 405"})
        mis = next(c for c in body["created"] if c["courseCode"] == "MIS 405")
        self.assertEqual(mis["assignmentsAdded"], 1)
        t = next(a["title"] for a in self.assignments() if a["courseId"] == mis["id"])
        self.assertNotIn("<", t)
        self.assertNotIn("\n", t)
        self.assertNotIn("‮", t)
        self.assertLessEqual(len(t), 160)

    def test_delete_tombstone_and_explicit_reimport(self):
        self.imp([klass()])
        course = self.courses()[0]
        self.assertTrue(feedsync.tombstone_course(ME, self.db, course))
        self.assertIn((f"USER#{ME}", f"FEEDSKIP#{ID}"), self.db.items)
        del self.db.items[(f"USER#{ME}", f"COURSE#{course['id']}")]
        st, body, _ = self.imp([klass()])
        self.assertEqual((st, len(body["created"])), (201, 1))                       # explicit re-import re-creates it
        self.assertNotIn((f"USER#{ME}", f"FEEDSKIP#{ID}"), self.db.items)
        self.assertFalse(feedsync.tombstone_course(ME, self.db, {"source": "syllabus", "bbIdentifier": ID}))

    def test_course_presenter_exposes_source_and_needs_syllabus(self):
        self.imp([klass()])
        v = courses_api._present(self.courses()[0])
        self.assertEqual((v["source"], v["needsSyllabus"]), ("blackboard", True))
        self.assertTrue(feedsync.needs_syllabus({"source": "blackboard"}))
        c = {**self.courses()[0], "summary": "Intro"}
        self.assertFalse(courses_api._present(c)["needsSyllabus"])
        self.assertEqual(courses_api._present({"id": "x", "status": "READY", "createdAt": "2026-01-01T00:00:00Z"})["source"], "syllabus")

    def test_isolation_and_unassigned_replaced(self):
        self.connect(ics(vevent("a", "EN 210 Essay", "20261110T170000Z")))
        self.sync()
        self.assertEqual(len(self.call("GET", "/feed/unassigned")[1]["unassigned"]), 1)
        self.imp([klass(asg=[])])
        self.assertEqual(self.call("GET", "/feed/unassigned")[1]["unassigned"], [])      # feed events re-placed into the new class
        self.assertEqual(self.courses(OTHER), [])
        self.assertEqual(self.imp([klass()], sub=OTHER)[0], 201)
        self.assertEqual(len(self.courses()), 1)
        self.assertIsNone(feed_api.handle({}, ME, "/courses/import", "GET", self.deps))


CANVAS_ID = "canvas:eng210_sp26"


def canvas_klass(code="EN 210", ident=CANVAS_ID, **kw):
    return {"identifier": ident, "code": code, "section": "001", "term": "202640", "title": "American Literature",
            "instructor": "Dr. Jane Rivera",
            "assignments": kw.pop("asg", [
                {"title": "Discussion Post 1", "dueDate": "2026-10-20", "dueTime": "23:59", "tz": "UTC"},
            ]), **kw}


class CanvasImport(Env):
    def setUp(self):
        super().setUp()
        self.db.items = {k: v for k, v in self.db.items.items() if not k[1].startswith("COURSE#")}

    def imp(self, classes, sub=ME, source="canvas"):
        return self.call("POST", "/courses/import", {"source": source, "classes": classes}, sub=sub)

    def courses(self, sub=ME):
        return [v for (p, s), v in self.db.items.items() if p == f"USER#{sub}" and s.startswith("COURSE#")]

    def test_canvas_source_creates_course_with_canvas_source(self):
        st, body, _ = self.imp([canvas_klass()])
        self.assertEqual(st, 201, body)
        course = self.courses()[0]
        self.assertEqual(course["source"], "canvas")
        self.assertEqual(course["bbIdentifier"], CANVAS_ID)

    def test_canvas_identifier_stored_as_bbIdentifier(self):
        self.imp([canvas_klass()])
        course = self.courses()[0]
        self.assertTrue(course["bbIdentifier"].startswith("canvas:"))
        self.assertEqual(course["bbIdentifier"], CANVAS_ID)

    def test_canvas_assignments_have_canvas_source(self):
        self.imp([canvas_klass()])
        asgs = self.assignments()
        self.assertTrue(all(a["source"] == "canvas" for a in asgs))

    def test_canvas_pipeline_labels_say_canvas(self):
        self.imp([canvas_klass()])
        course = self.courses()[0]
        self.assertIn("Canvas", course["pipeline"][0]["detail"])
        self.assertIn("Canvas", course["pipeline"][1]["detail"])

    def test_canvas_idempotent_reimport(self):
        self.imp([canvas_klass()])
        st, body, _ = self.imp([canvas_klass(asg=[
            {"title": "Discussion Post 1", "dueDate": "2026-10-20", "dueTime": "23:59", "tz": "UTC"},
            {"title": "Final Project", "dueDate": "2026-12-10", "dueTime": "17:00", "tz": "UTC"},
        ])])
        self.assertEqual(st, 200)
        self.assertEqual(body["created"], [])
        self.assertEqual(len(self.courses()), 1)
        self.assertEqual(len(self.assignments()), 2)

    def test_canvas_mixed_case_identifier_normalised(self):
        st, body, _ = self.imp([canvas_klass(ident="canvas:ENG210_SP26")])
        self.assertEqual(st, 201, body)
        course = self.courses()[0]
        self.assertEqual(course["bbIdentifier"], "canvas:eng210_sp26")

    def test_blackboard_source_still_works_backward_compat(self):
        st, body, _ = self.call("POST", "/courses/import",
                                {"source": "blackboard", "classes": [klass()]}, sub=ME)
        self.assertEqual(st, 201, body)
        course = self.courses()[0]
        self.assertEqual(course["source"], "blackboard")
        self.assertEqual(course["bbIdentifier"], ID)

    def test_invalid_source_rejected(self):
        self.assertEqual(self.call("POST", "/courses/import",
                                   {"source": "moodle", "classes": [canvas_klass()]})[0], 400)


if __name__ == "__main__":
    unittest.main()
