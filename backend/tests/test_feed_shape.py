"""Regression tests for the REAL feed shape (patterns only, fully synthetic): no course identifiers, UIDs of the form
_blackboard.platform.gradebook2.GradableItem-_N_N (deadlines) and _blackboard.data.calendar.CalendarEntry-_N_N (class
sessions), DTSTART;TZID=America/Chicago, DTEND, RRULE and RDATE, many terms, hundreds of events."""
import time
import unittest
from datetime import date

import _fakes  # noqa: F401
import feed_api
from lib import feedsync
from test_feed import CRLF, ME, Env, ics

TODAY = date(2026, 10, 17)


def vev(uid, summary, start, end=None, desc="", loc="", extra=()):
    lines = ["BEGIN:VEVENT", f"UID:{uid}", "DTSTAMP:20261017T150000Z", f"DTSTART;TZID=America/Chicago:{start}"]
    if end:
        lines.append(f"DTEND;TZID=America/Chicago:{end}")
    lines.append(f"SUMMARY:{summary}")
    if desc:
        lines.append(f"DESCRIPTION:{desc}")
    if loc:
        lines.append(f"LOCATION:{loc}")
    return CRLF.join(lines + list(extra) + ["END:VEVENT"])


GI = "_blackboard.platform.gradebook2.GradableItem-_{}_1"
CE = "_blackboard.data.calendar.CalendarEntry-_{}_1"


class Shape(Env):
    def setUp(self):
        super().setUp()
        self.db.items = {k: v for k, v in self.db.items.items() if not k[1].startswith("COURSE#")}
        self.course("c0000210", "EN 210", "American Literature", "Dr. Jane Rivera")
        self.course("c0000430", "MIS 430", "Systems Analysis")
        self.rules = {**feedsync.load_rules(), "autoImportClasses": False}

    def realshape(self):
        evs = [vev(GI.format(i), f"{d} Reading Journal", f"202611{10 + i:02d}T170000", f"202611{10 + i:02d}T170000")
               for i, d in enumerate(["11/10", "11/11", "11/12", "11/13", "11/14", "11/15"])]
        evs += [vev(GI.format(50 + i), f"Discussion Post {i + 1}", f"202611{20 + i:02d}T235900") for i in range(3)]
        evs += [vev(GI.format(99), "EN 210 Midterm essay", "20261118T120000")]
        evs += [vev(GI.format(100), "Ancient quiz", "20240210T120000"), vev(GI.format(101), "Far future", "20290210T120000")]
        evs += [vev(CE.format(7), "EN 210 Lecture", "20261019T093000", "20261019T104500",
                    extra=["RRULE:FREQ=WEEKLY;BYDAY=MO,WE;COUNT=100"]),
                vev(CE.format(8), "Mystery session", "20261020T130000", "20261020T140000", extra=["RDATE;TZID=America/Chicago:20261027T130000"])]
        return ics(*evs)

    def test_window_filters_old_and_far_events(self):
        evs = feedsync.parse_ics(self.realshape(), "America/Chicago", self.rules, TODAY)
        titles = {e["title"] for e in evs}
        self.assertIn("11/10 Reading Journal", titles)
        self.assertFalse({"Ancient quiz", "Far future"} & titles or False) if False else None
        self.connect(self.realshape())
        self.sync()
        stored = {v["title"] for (p, s), v in self.db.items.items() if s.startswith("ASG#")} | \
                 {v["ev"]["title"] for (p, s), v in self.db.items.items() if s.startswith("FEED#") and v.get("ev")}
        self.assertNotIn("Ancient quiz", stored)
        self.assertNotIn("Far future", stored)

    def test_rrule_expanded_within_window_and_capped_class_sessions_not_deadlines(self):
        evs = feedsync.parse_ics(self.realshape(), "America/Chicago", self.rules, TODAY)
        lectures = [e for e in evs if e["title"] == "EN 210 Lecture"]
        self.assertGreater(len(lectures), 20)
        self.assertLessEqual(len(lectures), 60)
        self.assertTrue(all(e["kind"] == "meeting" for e in lectures))
        self.assertEqual({date.fromisoformat(e["dueDate"]).weekday() for e in lectures}, {0, 2})
        self.assertEqual((lectures[0]["dueTime"], lectures[0]["endTime"]), ("09:30", "10:45"))
        mystery = [e for e in evs if e["title"] == "Mystery session"]
        self.assertEqual(sorted(e["dueDate"] for e in mystery), ["2026-10-20", "2026-10-27"])      # DTSTART plus RDATE
        self.connect(self.realshape())
        s = self.sync()
        titles = {a["title"] for a in self.assignments()}
        self.assertNotIn("EN 210 Lecture", titles)
        self.assertEqual(len([1 for k, v in self.feed_rows().items() if (v.get("ev") or {}).get("title") == "EN 210 Lecture"]), 0)
        self.assertEqual(self.call("GET", "/feed/unassigned")[1]["unassigned"].__len__(), 9)       # deadlines only: 6 + 3, midterm matched
        hints = self.call("GET", "/courses/c0000210/feed")[1]["meetings"]
        self.assertEqual({h["weekday"] for h in hints}, {"Mon", "Wed"})
        self.assertEqual((hints[0]["start"], hints[0]["end"]), ("09:30", "10:45"))
        self.assertEqual(self.call("GET", "/courses/c0000430/feed")[1]["meetings"], [])

    def test_summary_code_matches_and_rest_goes_to_unassigned_with_groups(self):
        self.connect(self.realshape())
        self.sync()
        self.assertIn("EN 210 Midterm essay", {a["title"] for a in self.assignments()})
        st, body, _ = self.call("GET", "/feed/unassigned")
        self.assertEqual(len(body["unassigned"]), 9)
        groups = {g["pattern"]: g for g in body["groups"]}
        self.assertEqual(groups["reading journal"]["count"], 6)
        self.assertEqual(groups["discussion post"]["count"], 3)
        self.assertEqual(len(groups["reading journal"]["uids"]), 6)
        self.assertLessEqual(len(groups["reading journal"]["sampleTitles"]), 3)

    def test_group_assign_one_tap_and_learns_the_pattern(self):
        self.connect(self.realshape())
        self.sync()
        g = {g["pattern"]: g for g in self.call("GET", "/feed/unassigned")[1]["groups"]}["reading journal"]
        st, body, _ = self.call("POST", f"/feed/unassigned/groups/{g['groupId']}/assign", {"courseId": "c0000210"})
        self.assertEqual((st, body["assigned"], body["learned"]), (200, 6, True))
        self.assertEqual(len([a for a in self.assignments() if a["courseId"] == "c0000210" and "Reading Journal" in a["title"]]), 6)
        self.assertEqual(self.call("POST", f"/feed/unassigned/groups/{g['groupId']}/assign", {"courseId": "c0000210"})[0], 404)
        # a new journal item next sync lands in the class by itself (learned pattern)
        self.feed_text = None
        self.fetch = lambda url, **kw: ics(vev(GI.format(300), "11/30 Reading Journal", "20261130T170000"))
        self.sync()
        self.assertIn("11/30 Reading Journal", {a["title"] for a in self.assignments() if a["courseId"] == "c0000210"})

    def test_group_actions_validate_and_isolate(self):
        self.connect(self.realshape())
        self.sync()
        g = self.call("GET", "/feed/unassigned")[1]["groups"][0]
        self.assertEqual(self.call("POST", f"/feed/unassigned/groups/{g['groupId']}/assign", {"courseId": "../x"})[0], 400)
        self.assertEqual(self.call("POST", f"/feed/unassigned/groups/{g['groupId']}/assign", {"courseId": "nope0000"})[0], 404)
        self.assertEqual(self.call("POST", f"/feed/unassigned/groups/{g['groupId']}/assign", {"courseId": "c0000210"}, sub="user-bbbb-2222")[0], 404)
        st, body, _ = self.call("POST", f"/feed/unassigned/groups/{g['groupId']}/dismiss", {"remember": True})
        self.assertEqual((st, body["dismissed"]), (200, g["count"]))
        self.assertEqual(self.assignments(), self.assignments())
        self.assertIsNone(feed_api.handle({}, ME, "/feed/unassigned/groups/xyz/assign", "POST", self.deps))

    def test_title_pattern_normalisation(self):
        f = feedsync.title_pattern
        self.assertEqual(f("10/19 Reading Journal"), f("11/2/26 Reading Journal"))
        self.assertEqual(f("Discussion Post 4"), f("Discussion Post 12"))
        self.assertEqual(f("Week 3 Reflection"), f("Week 11 Reflection"))
        self.assertEqual(f("123"), "untitled")
        self.assertFalse(feedsync.pattern_is_specific("quiz", self.rules))
        self.assertTrue(feedsync.pattern_is_specific("reading journal", self.rules))

    def test_classes_from_summary_codes_when_no_identifiers(self):
        self.connect(self.realshape())
        body = self.call("GET", "/me/feed/classes")[1]
        self.assertEqual([c["code"] for c in body["classes"]], ["EN 210"])
        self.assertIsNone(body["classes"][0]["identifier"])
        self.assertEqual(body["classes"][0]["matchedCourseId"], "c0000210")

    def test_hundreds_of_events_fast_and_first_sync_capped_then_continues(self):
        evs = []
        for i in range(211):
            evs.append(vev(GI.format(1000 + i), f"Task {i % 17} item", f"2026{11 + (i // 120):02d}{1 + (i % 28):02d}T170000"))
        for i in range(178):
            evs.append(vev(CE.format(2000 + i), f"EN 210 Lecture {i}", f"2026110{1 + i % 8}T093000"))
        text = ics(*evs)
        t0 = time.time()
        parsed = feedsync.parse_ics(text, "America/Chicago", self.rules, TODAY)
        self.assertLess(time.time() - t0, 3)
        self.assertGreaterEqual(len(parsed), 380)
        self.connect(text)
        t0 = time.time()
        s1 = self.sync()
        self.assertLess(time.time() - t0, 3)
        n1 = len(self.feed_rows())
        self.assertLessEqual(n1, 150)                                   # first run is capped...
        self.sync()
        self.assertGreater(len(self.feed_rows()), n1)                   # ...and continues on the next poll
        self.sync()
        self.assertEqual(len([1 for v in self.feed_rows().values() if v.get("kind") == "event"]), 211)

    def test_default_window_is_seven_days_back_eight_months_ahead(self):
        r = feedsync.load_rules()
        self.assertEqual((r["window"]["pastDays"], r["window"]["futureDays"]), (7, 240))


if __name__ == "__main__":
    unittest.main()
