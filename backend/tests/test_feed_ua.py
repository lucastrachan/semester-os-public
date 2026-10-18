"""UA Blackboard identifiers, current-term filter, time zone labels and detected classes (all synthetic strings)."""
import unittest

import feed_api
from lib import feedsync
from test_feed import CRLF, ME, OTHER, Env, ics, vevent


def ua(term, dept, num, sec="001", nid="123456"):
    return f"Due date: 11/5/26, 11:59 PM (CST) ∙ {nid}.{term}: {term}-{dept}-{num}-{sec}"


class Identifiers(Env):
    def setUp(self):
        super().setUp()
        self.rules = {**feedsync.load_rules(), "autoImportClasses": False}   # these tests cover parking; auto-import is in test_feed_auto
        self.course("c0000430", "MIS 430", "Systems Analysis")

    def test_find_identifiers_formats_and_non_matches(self):
        f = feedsync.find_identifiers
        a = f({"title": "Quiz 3", "description": ua("202640", "MIS", "430")})
        self.assertEqual([(i["term"], i["code"], i["section"], i["identifier"]) for i in a],
                         [("202640", "MIS 430", "001", "202640-MIS-430-001")])
        self.assertEqual(f({"title": "202640-mis-430-001 Quiz"})[0]["code"], "MIS 430")
        self.assertEqual(f({"categories": ["202630-ACC-100-L01"]})[0]["section"], "L01")
        for text in ("Due 2026-11-05-ab", "1234567-MIS-430-001", "202640-MIS-430-0011234567", "123456-7-8-9", "no ids here"):
            self.assertEqual(f({"title": text}), [], text)

    def test_identifier_match_is_high_confidence_and_picks_the_right_class(self):
        rules = feedsync.load_rules()
        idx = feedsync.CourseIndex([{"id": "c0000430", "courseCode": "MIS 430"}, {"id": "c0000405", "courseCode": "MIS 405"}], rules)
        r = feedsync.classify({"title": "Quiz 3", "description": ua("202640", "MIS", "430"), "categories": [], "uid": "u"}, idx, rules)
        self.assertEqual((r["courseId"], r["reason"]), ("c0000430", "identifier"))
        self.assertGreaterEqual(r["confidence"], 0.98)
        r = feedsync.classify({"title": "202640-MIS-430-001 Project", "description": "", "categories": [], "uid": "u"}, idx, rules)
        self.assertEqual(r["courseId"], "c0000430")

    def test_sync_matches_without_any_other_evidence(self):
        self.connect(ics(vevent("a", "Reading response", "20261106T055900Z", desc=ua("202640", "MIS", "430"))))
        self.sync()
        (a,) = self.assignments()
        self.assertEqual((a["courseId"], a["dueDate"], a["dueTime"]), ("c0000430", "2026-11-05", "23:59"))

    def test_old_term_events_never_create_anything(self):
        feed = ics(vevent("n", "New quiz", "20261106T055900Z", desc=ua("202640", "MIS", "430")),
                   vevent("o1", "Old quiz", "20261020T055900Z", desc=ua("202530", "MIS", "430", nid="99999")),
                   vevent("o2", "Old other", "20261021T055900Z", desc=ua("202530", "ACC", "100", nid="99998")),
                   vevent("p", "Past term really old", "20240101T055900Z", desc=ua("202330", "MIS", "430")))
        self.connect(feed)
        s = self.sync()
        self.assertEqual((s["added"], s["unassigned"]), (1, 0))
        self.assertEqual([a["title"] for a in self.assignments()], ["New quiz"])
        self.assertEqual(len(self.feed_rows()), 1)   # old-term events are not even cached
        self.assertEqual(self.call("GET", "/feed/unassigned")[1]["unassigned"], [])
        courses = [k for k in self.db.items if k[0] == f"USER#{ME}" and k[1].startswith("COURSE#")]
        self.assertEqual(len(courses), 3)            # the 2 from setUp plus MIS 430: no class was created

    def test_unadded_current_term_class_is_parked_then_placed_when_added(self):
        self.connect(ics(vevent("n", "Quiz", "20261106T055900Z", desc=ua("202640", "MIS", "430")),
                         vevent("x", "Midterm", "20261108T055900Z", desc=ua("202640", "FIN", "999", nid="777"))))
        s = self.sync()
        self.assertEqual((s["added"], s["unassigned"]), (1, 0))
        self.assertEqual(self.call("GET", "/feed/unassigned")[1]["unassigned"], [])
        self.assertEqual(self.call("GET", "/me/feed")[1]["counts"]["unassigned"], 0)
        self.course("c0000999", "FIN 999", "Finance")
        s = self.sync()
        self.assertEqual(s["added"], 1)
        self.assertEqual({a["courseId"] for a in self.assignments()}, {"c0000430", "c0000999"})

    def test_timezone_abbreviation_tzid_and_text_fallback(self):
        rules = feedsync.load_rules()

        def p(text, tz="America/Chicago"):
            return {e["title"]: e for e in feedsync.parse_ics(text, tz, rules)}
        floating = ics(vevent("a", "Cst", "20261106T235900", desc="Due date: 11/6/26, 11:59 PM (CST)"),
                       vevent("b", "Cdt", "20261015T235900", desc="Due date: 10/15/26, 11:59 PM (CDT)"))
        by = p(floating)
        self.assertEqual((by["Cst"]["dueDate"], by["Cst"]["dueTime"]), ("2026-11-06", "23:59"))
        self.assertEqual((by["Cdt"]["dueDate"], by["Cdt"]["dueTime"]), ("2026-10-15", "23:59"))
        ny = p(floating, "America/New_York")       # the label is honoured, not assumed
        self.assertEqual((ny["Cdt"]["dueDate"], ny["Cdt"]["dueTime"]), ("2026-10-16", "00:59"))
        self.assertEqual((ny["Cst"]["dueDate"], ny["Cst"]["dueTime"]), ("2026-11-07", "00:59"))
        win = p(ics(vevent("w", "Win", "20261106T235900").replace("DTSTART:", "DTSTART;TZID=Central Standard Time:")), "America/New_York")
        self.assertEqual((win["Win"]["dueDate"], win["Win"]["dueTime"]), ("2026-11-07", "00:59"))
        nodate = p(CRLF.join(["BEGIN:VCALENDAR", "BEGIN:VEVENT", "UID:z", "SUMMARY:No start",
                              "DESCRIPTION:Due date: 11/5/26\\, 11:59 PM (CST)", "END:VEVENT", "END:VCALENDAR"]))
        self.assertEqual((nodate["No start"]["dueDate"], nodate["No start"]["dueTime"]), ("2026-11-05", "23:59"))
        garbage = p(ics(vevent("g", "Bad", "notadate", desc="Due date: 2/30/26, 1:00 PM (CST)")))
        self.assertIsNone(garbage["Bad"]["dueDate"])


class DetectedClasses(Env):
    def setUp(self):
        super().setUp()
        self.rules = {**feedsync.load_rules(), "autoImportClasses": False}

    def feed_with_classes(self):
        return ics(vevent("a", "Quiz 1", "20261106T055900Z", desc=ua("202640", "MIS", "430")),
                   vevent("b", "Quiz 2", "20261110T055900Z", desc=ua("202640", "MIS", "430")),
                   vevent("c", "Exam", "20261112T055900Z", desc=ua("202640", "ACC", "100", "002", nid="55")),
                   vevent("d", "Old", "20261020T055900Z", desc=ua("202530", "BUS", "300", nid="44")),
                   vevent("e", "No identifier", "20261113T055900Z"))

    def test_classes_after_save_before_any_class_exists(self):
        self.db.items = {k: v for k, v in self.db.items.items() if not k[1].startswith("COURSE#")}
        self.connect(self.feed_with_classes())
        st, body, _ = self.call("GET", "/me/feed/classes")
        self.assertEqual(st, 200)
        self.assertEqual(body["term"], "202640")
        self.assertEqual(body["classes"], [
            {"code": "ACC 100", "section": "002", "term": "202640", "identifier": "202640-ACC-100-002", "eventCount": 1, "matchedCourseId": None},
            {"code": "MIS 430", "section": "001", "term": "202640", "identifier": "202640-MIS-430-001", "eventCount": 2, "matchedCourseId": None}])

    def test_matched_course_id_follows_classes_and_refresh_after_sync(self):
        self.connect(self.feed_with_classes())
        got = {c["code"]: c["matchedCourseId"] for c in self.call("GET", "/me/feed/classes")[1]["classes"]}
        self.assertEqual(got, {"ACC 100": "c0000002", "MIS 430": None})
        self.course("c0000430", "MIS 430", "Systems Analysis")
        self.sync()
        got = {c["code"]: c["matchedCourseId"] for c in self.call("GET", "/me/feed/classes")[1]["classes"]}
        self.assertEqual(got, {"ACC 100": "c0000002", "MIS 430": "c0000430"})

    def test_not_connected_isolation_and_no_url(self):
        self.assertEqual(self.call("GET", "/me/feed/classes")[1], {"connected": False, "term": None, "classes": [], "suggested": []})
        self.connect(self.feed_with_classes())
        self.assertEqual(self.call("GET", "/me/feed/classes", sub=OTHER)[1]["classes"], [])
        self.assertNotIn("SECRETTOKEN", self.call("GET", "/me/feed/classes")[2]["body"])
        self.assertIsNone(feed_api.handle({}, ME, "/me/feed/classes", "POST", self.deps))


if __name__ == "__main__":
    unittest.main()
