"""Auto-import of class agents from the connected feed (synthetic identifiers only)."""
import unittest

import feed_api
from lib import feedsync, tutor
from test_feed import Env, ME, OTHER, ics, vevent
from test_feed_ua import ua
from test_tutor import Script, call as tutor_call, chat, seed as tutor_seed, text as tutor_text


def feed_for(*classes, extra=()):
    evs = []
    for i, (dept, num, sec, term) in enumerate(classes):
        evs.append(vevent(f"u{i}a", f"Quiz {i}", "20261106T055900Z", desc=ua(term, dept, num, sec, nid=str(100 + i))))
        evs.append(vevent(f"u{i}b", f"Paper {i}", "20261110T055900Z", desc=ua(term, dept, num, sec, nid=str(100 + i))))
    return ics(*evs, *extra)


class AutoImport(Env):
    def setUp(self):
        super().setUp()
        self.db.items = {k: v for k, v in self.db.items.items() if not k[1].startswith("COURSE#")}   # a brand-new student
        self.on = {**feedsync.load_rules(), "autoImportClasses": True}   # auto-import is OFF by default
        self.rules = self.on

    def courses(self, sub=ME):
        return {v["courseCode"]: v for (p, s), v in self.db.items.items() if p == f"USER#{sub}" and s.startswith("COURSE#")}

    def test_put_creates_ready_classes_and_reports_them(self):
        self.feed = feed_for(("MIS", "430", "001", "202640"), ("EN", "210", "010", "202640"), ("ACC", "100", "001", "202530"))
        body = self.connect()
        got = {c["code"]: c for c in body["importedClasses"]}
        self.assertEqual(set(got), {"MIS 430", "EN 210"})                 # the old term is never imported
        self.assertEqual(got["EN 210"]["section"], "010")
        c = self.courses()["MIS 430"]
        self.assertEqual((c["status"], c["source"], c["term"], c["section"], c["feedIdentifier"]), ("READY", "feed", "202640", "001", "202640-MIS-430-001"))
        self.assertTrue(all(s["state"] == "done" for s in c["pipeline"]))
        self.assertEqual(c["pipeline"][0]["detail"], "Imported from Blackboard")
        self.assertEqual(c["knows"]["newItemsCount"], 0)
        self.assertNotEqual(c["color"], self.courses()["EN 210"]["color"])
        acts = [v["text"] for (p, s), v in self.db.items.items() if s.startswith("ACT#")]
        self.assertIn("Imported 2 classes from Blackboard", acts)
        self.assertEqual(got["MIS 430"]["courseId"], c["id"])

    def test_sync_places_the_parked_events_into_the_new_classes(self):
        self.feed = feed_for(("MIS", "430", "001", "202640"))
        self.connect()
        s = self.sync()
        self.assertEqual(s["added"], 2)
        self.assertEqual(s["importedClasses"], [])                         # already imported at save time
        cid = self.courses()["MIS 430"]["id"]
        asg = self.assignments()
        self.assertEqual({a["courseId"] for a in asg}, {cid})
        self.assertTrue(all(a["source"] == "feed" and a["dateSource"] == "feed" for a in asg))
        self.assertEqual(self.db.items[(f"USER#{ME}", f"COURSE#{cid}")]["knows"]["assignmentsCount"], 2)
        self.assertEqual(self.call("GET", "/feed/unassigned")[1]["unassigned"], [])

    def test_sync_itself_imports_for_the_poller_path(self):
        self.rules = {**feedsync.load_rules(), "autoImportClasses": False}
        self.connect(feed_for(("MIS", "430", "001", "202640"), ("EN", "210", "010", "202640")))
        self.assertEqual(self.courses(), {})
        self.rules = self.on
        s = self.sync()
        self.assertEqual({c["code"] for c in s["importedClasses"]}, {"MIS 430", "EN 210"})
        self.assertEqual(len(self.assignments()), 4)

    def test_existing_class_is_not_duplicated(self):
        self.course("c0000430", "MIS 430", "Systems Analysis")
        self.connect(feed_for(("MIS", "430", "001", "202640")))
        self.assertEqual(len(self.courses()), 1)
        self.assertEqual(self.sync()["added"], 2)

    def test_caps_per_run_and_per_student(self):
        many = [("DEP", str(100 + i), "001", "202640") for i in range(25)]
        self.connect(feed_for(*many))
        self.assertEqual(len(self.courses()), 12)                          # per run
        s = self.sync()
        self.assertEqual(len(s["importedClasses"]), 8)                     # per student: 20 in total
        self.assertEqual(len(self.courses()), 20)
        self.assertEqual(self.sync()["importedClasses"], [])
        self.assertEqual(len(self.courses()), 20)

    def test_deleted_class_is_never_recreated(self):
        self.connect(feed_for(("MIS", "430", "001", "202640"), ("EN", "210", "010", "202640")))
        gone = self.courses()["MIS 430"]
        del self.db.items[(f"USER#{ME}", f"COURSE#{gone['id']}")]          # student deletes the class (no hook called)
        s = self.sync()
        self.assertEqual(s["importedClasses"], [])
        self.assertNotIn("MIS 430", self.courses())
        self.assertIn((f"USER#{ME}", "FEEDSKIP#202640-MIS-430-001"), self.db.items)
        self.assertEqual(self.sync()["importedClasses"], [])
        self.assertEqual(set(self.courses()), {"EN 210"})
        # even a different section of the same class in the same term stays skipped
        self.feed = feed_for(("MIS", "430", "002", "202640"), ("EN", "210", "010", "202640"))
        self.assertEqual(self.sync()["importedClasses"], [])

    def test_delete_hook_writes_tombstone_only_for_feed_classes(self):
        self.connect(feed_for(("MIS", "430", "001", "202640")))
        c = self.courses()["MIS 430"]
        self.assertTrue(feedsync.tombstone_course(ME, self.db, c))
        self.assertIn((f"USER#{ME}", "FEEDSKIP#202640-MIS-430-001"), self.db.items)
        self.assertFalse(feedsync.tombstone_course(ME, self.db, {"id": "x", "source": "syllabus", "courseCode": "MIS 1"}))

    def test_users_are_isolated_and_flag_disables(self):
        self.connect(feed_for(("MIS", "430", "001", "202640")))
        self.assertEqual(self.courses(OTHER), {})
        self.rules = {**feedsync.load_rules(), "autoImportClasses": False}
        self.db.items = {k: v for k, v in self.db.items.items() if not k[1].startswith("COURSE#")}
        self.assertEqual(self.connect()["importedClasses"], [])

    def test_off_by_default(self):
        self.assertFalse(feedsync.load_rules()["autoImportClasses"])
        self.rules = None
        self.assertEqual(self.connect(feed_for(("MIS", "430", "001", "202640")))["importedClasses"], [])
        self.assertEqual(self.courses(), {})

    def test_no_identifier_feed_imports_nothing(self):
        body = self.connect(ics(vevent("a", "Reading", "20261106T055900Z")))
        self.assertEqual(body["importedClasses"], [])
        self.assertEqual(self.courses(), {})


class TutorWithoutSyllabus(unittest.TestCase):
    def feed_course(self, **extra):
        return {"source": "feed", "courseCode": "MIS 430", "title": "MIS 430", "summary": "", "grading": [], "meetings": [],
                "policies": {"late": "", "attendance": "", "ai": "", "other": ""}, "books": [], "officeHours": "", **extra}

    def system(self, extra):
        db = tutor_seed(course_extra=extra)
        m = Script(tutor_text("I have the deadlines but no syllabus yet."))
        st, out, _ = tutor_call(db, m, chat("what is the grading policy?"))
        self.assertEqual(st, 200)
        return m.calls[0]["system"], out

    def test_imported_class_without_syllabus_gets_the_degrade_rule(self):
        system, out = self.system({**self.feed_course(), "books": [], "policies": {"ai": "", "late": "", "attendance": "", "other": ""}})
        self.assertIn("NO syllabus facts yet", system)
        self.assertIn("suggest uploading the syllabus", system)
        self.assertIn("deadlines but no syllabus", out["reply"])

    def test_rule_absent_for_normal_classes_and_after_a_syllabus(self):
        system, _ = self.system({})
        self.assertNotIn("NO syllabus facts", system)
        system, _ = self.system({**self.feed_course(), "summary": "Intro to systems", "books": [],
                                 "policies": {"ai": "", "late": "", "attendance": "", "other": ""}})
        self.assertNotIn("NO syllabus facts", system)
        self.assertTrue(tutor.has_syllabus_facts({"source": "syllabus"}))
        self.assertFalse(tutor.has_syllabus_facts(self.feed_course()))

    def test_all_modes_work_without_a_syllabus(self):
        db = tutor_seed(course_extra={**self.feed_course(), "books": [], "policies": {"ai": "", "late": "", "attendance": "", "other": ""}})
        for mode in ("explain", "cram"):
            m = Script(tutor_text("ok"))
            st, out, _ = tutor_call(db, m, chat("help me plan", mode=mode))
            self.assertEqual(st, 200, mode)


if __name__ == "__main__":
    unittest.main()
