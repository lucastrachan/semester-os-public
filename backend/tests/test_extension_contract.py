"""Contract test: parse.js (browser extension) → POST /courses/import (backend).

Runs parse.js with node to generate realistic extension output from synthetic Blackboard
deadline text, then drives the backend import handler with that payload and verifies the
field names, TZ conversion, and term-filter behaviour match exactly.

Skipped when node is not on PATH (CI without Node, developer machines without node).
"""
import json
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

import _fakes  # noqa: F401
import feed_api
from test_feed import ME, Env

ROOT = Path(__file__).resolve().parents[2]
PARSE_JS = ROOT / "extension" / "parse.js"

_NODE_AVAILABLE = None


def _node():
    global _NODE_AVAILABLE
    if _NODE_AVAILABLE is None:
        try:
            r = subprocess.run(["node", "--version"], capture_output=True, timeout=5)
            _NODE_AVAILABLE = r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            _NODE_AVAILABLE = False
    return _NODE_AVAILABLE


def _run_parse(bb_text: str, courses: list) -> dict:
    """Run parse.js via node and return buildImport() output."""
    script = textwrap.dedent(f"""
        var SOSParse = require({json.dumps(str(PARSE_JS))});
        var text = {json.dumps(bb_text)};
        var courses = {json.dumps(courses)};
        var deadlines = SOSParse.parseDeadlines(text);
        process.stdout.write(JSON.stringify(SOSParse.buildImport(courses, deadlines)));
    """)
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, f"node exited {r.returncode}: {r.stderr}"
    return json.loads(r.stdout)


# Synthetic Blackboard deadline text with two terms: 202520 (old) and 202640 (current).
# The extension should keep only the newest term.
BB_TEXT = "\n".join([
    # ── old term (202520) ────────────────────────────────────────────────
    "Old Essay",
    "Due date: 4/15/25, 11:59 PM (CDT) . 40541.202520: 202520-EN-210-010",
    # ── current term (202640) ────────────────────────────────────────────
    "Reading Journal 1",
    "Due date: 10/19/26, 5:00 PM (CDT) . 40541.202640: 202640-EN-210-010",
    "Midterm Exam",
    "Due date: 11/5/26, 11:59 PM (CST) . 40541.202640: 202640-EN-210-010",
    "Problem Set 3",
    "Due date: 10/20/26, 9:00 AM (CDT) . 40541.202640: 202640-CS-315-001",
])

BB_COURSES = [
    {"identifier": "202640-EN-210-010", "title": "American Literature", "instructor": "Dr. Rivera"},
    {"identifier": "202640-CS-315-001", "title": "Algorithms", "instructor": "Dr. Smith"},
    # old term course present in the course list too — must be filtered out
    {"identifier": "202520-EN-210-010", "title": "Old Lit"},
]


@unittest.skipUnless(_node(), "node not available")
class ExtensionContract(Env):
    """parse.js output → /courses/import round-trip."""

    def setUp(self):
        super().setUp()
        # Remove any pre-seeded courses so we get a clean import
        self.db.items = {k: v for k, v in self.db.items.items() if not k[1].startswith("COURSE#")}

    def _parsed(self):
        return _run_parse(BB_TEXT, BB_COURSES)

    def test_parse_js_output_shape(self):
        """buildImport returns exactly {source, classes} with the right field names."""
        out = self._parsed()
        self.assertEqual(out["source"], "blackboard")
        classes = out["classes"]
        self.assertEqual(len(classes), 2)    # old term excluded
        en = next(c for c in classes if c["identifier"] == "202640-EN-210-010")
        cs = next(c for c in classes if c["identifier"] == "202640-CS-315-001")

        # Class keys are exactly what _IMPORT_CLASS_KEYS expects
        allowed = {"identifier", "code", "section", "term", "title", "instructor", "assignments"}
        self.assertFalse(set(en) - allowed, f"unexpected class keys: {set(en) - allowed}")

        # Assignment keys are exactly what _IMPORT_ASG_KEYS expects
        allowed_asg = {"title", "dueDate", "dueTime", "tz"}
        for asg in en["assignments"] + cs["assignments"]:
            self.assertFalse(set(asg) - allowed_asg, f"unexpected asg keys: {set(asg) - allowed_asg}")

        # TZ labels are uppercase (CDT/CST)
        for asg in en["assignments"]:
            self.assertRegex(asg["tz"], r"^[A-Z]{2,5}$", "tz must be uppercase abbreviation")

    def test_term_filter_newest_only(self):
        """buildImport discards old terms; only 202640 courses reach the backend."""
        out = self._parsed()
        terms = {c["term"] for c in out["classes"]}
        self.assertEqual(terms, {"202640"})

    def test_import_succeeds_end_to_end(self):
        """parse.js output can be sent to the backend without modification."""
        out = self._parsed()
        st, body, _ = self.call("POST", "/courses/import", out, sub=ME)
        self.assertEqual(st, 201, body)
        created_codes = {c["courseCode"] for c in body["created"]}
        self.assertEqual(created_codes, {"EN 210", "CS 315"})

    def test_tz_labels_converted_to_campus_zone(self):
        """CDT/CST from parse.js are correctly converted to the tenant's timezone."""
        # Campus is America/Chicago (UA). CDT offset -5h, CST offset -6h.
        # CDT 17:00 in Chicago is still 17:00 (same offset in Chicago at DST time).
        # CST 23:59 in Chicago is still 23:59 (same offset in Chicago in winter).
        out = self._parsed()
        st, body, _ = self.call("POST", "/courses/import", out, sub=ME)
        self.assertEqual(st, 201)
        asg = {a["title"]: a for a in self.assignments()}
        rj = asg.get("Reading Journal 1")
        mt = asg.get("Midterm Exam")
        self.assertIsNotNone(rj, "Reading Journal 1 not imported")
        self.assertIsNotNone(mt, "Midterm Exam not imported")
        self.assertEqual((rj["dueDate"], rj["dueTime"]), ("2026-10-19", "17:00"))
        self.assertEqual((mt["dueDate"], mt["dueTime"]), ("2026-11-05", "23:59"))

    def test_repeated_import_is_idempotent(self):
        """Sending the same parse.js output twice does not duplicate courses or assignments."""
        out = self._parsed()
        self.call("POST", "/courses/import", out, sub=ME)
        st2, body2, _ = self.call("POST", "/courses/import", out, sub=ME)
        self.assertEqual(st2, 200)
        self.assertEqual(body2["created"], [])
        courses = [v for (p, s), v in self.db.items.items() if p == f"USER#{ME}" and s.startswith("COURSE#")]
        self.assertEqual(len(courses), 2)


if __name__ == "__main__":
    unittest.main()
