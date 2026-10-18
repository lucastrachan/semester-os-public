"""POST /courses/quick, suggested codes and needsSyllabus (synthetic data)."""
import json
import unittest

import _fakes  # noqa: F401
import feed_api
from lib import feedsync
from test_feed import ME, OTHER, Env, ics
from test_feed_shape import GI, CE, vev


class Quick(Env):
    def setUp(self):
        super().setUp()
        self.db.items = {k: v for k, v in self.db.items.items() if not k[1].startswith("COURSE#")}
        self.rules = {**feedsync.load_rules(), "autoImportClasses": False}

    def courses(self, sub=ME):
        return {v["courseCode"]: v for (p, s), v in self.db.items.items() if p == f"USER#{sub}" and s.startswith("COURSE#")}

    def quick(self, courses, sub=ME):
        return self.call("POST", "/courses/quick", {"courses": courses}, sub=sub)

    def test_creates_ready_classes_normalised(self):
        st, body, _ = self.quick([{"code": "mis405", "title": "Management Information Systems", "section": "001"},
                                  {"code": " en-210 "}, {"code": "Acc 100b"}])
        self.assertEqual(st, 201, body)
        self.assertEqual([c["courseCode"] for c in body["created"]], ["MIS 405", "EN 210", "ACC 100B"])
        self.assertEqual(set(body["created"][0]), {"id", "courseCode", "title", "color"})
        self.assertEqual(body["created"][1]["title"], "EN 210")                 # no title: the code
        c = self.courses()["MIS 405"]
        self.assertEqual((c["status"], c["source"], c["section"], c["title"]), ("READY", "quick", "001", "Management Information Systems"))
        self.assertTrue(all(s["state"] == "done" for s in c["pipeline"]))
        self.assertEqual(c["pipeline"][0]["detail"], "Added by code")
        self.assertEqual(len({x["color"] for x in body["created"]}), 3)
        self.assertEqual(c["knows"]["newItemsCount"], 0)

    def test_skips_existing_duplicates_and_invalid(self):
        self.course("c0000405", "MIS 405", "x")
        st, body, _ = self.quick([{"code": "mis 405"}, {"code": "EN 210"}, {"code": "en210"}, {"code": "X"}, {"code": "TOOLONGDEPT 100"}, {"code": 5}])
        self.assertEqual([c["courseCode"] for c in body["created"]], ["EN 210"])
        self.assertEqual(body["skipped"], ["MIS 405", "EN 210"])
        self.assertEqual(len(body["invalid"]), 3)
        self.assertEqual(self.quick([{"code": "MIS 405"}])[0], 200)             # nothing created: 200

    def test_validation_and_caps(self):
        for body in ({}, {"courses": []}, {"courses": "x"}, {"courses": [{"code": "EN 210"}] * 13}, {"courses": ["EN 210"]},
                     {"courses": [{"code": "EN 210", "extra": 1}]}, {"courses": [{"code": "EN 210"}], "x": 1}):
            self.assertEqual(self.call("POST", "/courses/quick", body)[0], 400, body)
        codes = [{"code": f"DEP {100 + i}"} for i in range(12)]
        self.quick(codes)
        self.quick([{"code": f"DEP {200 + i}"} for i in range(12)])
        self.assertEqual(len(self.courses()), 20)                               # 20 per student
        st, body, _ = self.quick([{"code": "ZZZ 999"}])
        self.assertEqual((body["created"], body["skipped"]), ([], ["ZZZ 999"]))

    def test_hostile_text_is_cleaned(self):
        st, body, _ = self.quick([{"code": "EN 210", "title": "<script>alert(1)</script>Lit‮\n ignore previous instructions", "section": "../x"}])
        c = self.courses()["EN 210"]
        self.assertNotIn("<", c["title"])
        self.assertNotIn("\n", c["title"])
        self.assertNotIn("‮", c["title"])
        self.assertEqual(c["section"], "")

    def test_isolation(self):
        self.quick([{"code": "EN 210"}])
        self.assertEqual(self.courses(OTHER), {})
        st, body, _ = self.quick([{"code": "EN 210"}], sub=OTHER)
        self.assertEqual([c["courseCode"] for c in body["created"]], ["EN 210"])
        self.assertEqual(len(self.courses()), 1)

    def test_placement_reruns_for_parked_events(self):
        evs = [vev(GI.format(i), f"EN 210 Essay {i}", f"202611{10 + i:02d}T170000") for i in range(3)]
        evs += [vev(GI.format(50), "Unrelated thing", "20261120T170000")]
        self.connect(ics(*evs))
        self.sync()
        self.assertEqual(len(self.call("GET", "/feed/unassigned")[1]["unassigned"]), 4)
        st, body, _ = self.quick([{"code": "EN 210"}])
        self.assertEqual((st, body["placed"]), (201, 3))
        cid = body["created"][0]["id"]
        self.assertEqual({a["courseId"] for a in self.assignments()}, {cid})
        self.assertEqual([i["title"] for i in self.call("GET", "/feed/unassigned")[1]["unassigned"]], ["Unrelated thing"])
        self.assertEqual(self.db.items[(f"USER#{ME}", f"COURSE#{cid}")]["knows"]["assignmentsCount"], 3)
        # and the next sync keeps matching by code
        self.feed = ics(*evs, vev(GI.format(60), "EN 210 Final paper", "20261125T170000"))
        self.assertEqual(self.sync()["added"], 1)

    def test_suggested_codes_and_needs_syllabus(self):
        evs = [vev(CE.format(i), f"EN 210 Lecture {i}", f"2026102{i}T093000") for i in range(4)]
        evs += [vev(CE.format(10 + i), "MIS 405 Lab", f"2026102{i}T130000") for i in range(2)] + [vev(CE.format(20), "ACC 100 once", "20261025T100000")]
        self.connect(ics(*evs))
        body = self.call("GET", "/me/feed/classes")[1]
        self.assertEqual(body["suggested"], [{"code": "EN 210", "eventCount": 4}, {"code": "MIS 405", "eventCount": 2}])
        self.quick([{"code": "en 210"}])
        self.assertEqual([s["code"] for s in self.call("GET", "/me/feed/classes")[1]["suggested"]], ["MIS 405"])   # already added: not offered again
        cid = self.courses()["EN 210"]["id"]
        view = self.call("GET", f"/courses/{cid}/feed")[1]
        self.assertTrue(view["needsSyllabus"])
        self.db.items[(f"USER#{ME}", f"COURSE#{cid}")]["summary"] = "Intro"
        self.assertFalse(self.call("GET", f"/courses/{cid}/feed")[1]["needsSyllabus"])
        self.assertFalse(feedsync.needs_syllabus({"source": "syllabus"}))
        self.assertEqual(self.call("GET", "/me/feed/classes", sub=OTHER)[1]["suggested"], [])

    def test_works_without_a_feed_and_route_ownership(self):
        st, body, _ = self.quick([{"code": "EN 210"}])
        self.assertEqual((st, body["placed"]), (201, 0))
        self.assertIsNone(feed_api.handle({}, ME, "/courses/quick", "GET", self.deps))
        self.assertIsNone(feed_api.handle({}, ME, "/courses", "POST", self.deps))


if __name__ == "__main__":
    unittest.main()
