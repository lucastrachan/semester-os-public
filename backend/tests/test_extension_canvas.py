"""Contract test: extension/parse.js Canvas mapping -> POST /courses/import (synthetic Canvas API JSON, no real Canvas).

Skipped when node is not on PATH. Separate from test_extension_contract.py (owned by the Builder)."""
import json
import subprocess
import textwrap
import unittest
from pathlib import Path

import _fakes  # noqa: F401
from test_feed import ME, Env

ROOT = Path(__file__).resolve().parents[2]
PARSE_JS = ROOT / "extension" / "parse.js"


def _node():
    try:
        return subprocess.run(["node", "--version"], capture_output=True, timeout=5).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


COURSES = [
    {"id": 101, "course_code": "MIS 430 001", "name": "Systems Analysis", "term": {"id": 7, "start_at": "2026-08-17T00:00:00Z"},
     "teachers": [{"display_name": "Dr. Test Teacher"}]},
    {"id": 102, "course_code": "ACC301-002", "name": "Accounting II", "term": {"id": 7, "start_at": "2026-08-17T00:00:00Z"}},
    {"id": 55, "course_code": "OLD 100", "name": "Old class", "term": {"id": 3, "start_at": "2026-01-10T00:00:00Z"}},
]
ASSIGNMENTS = {
    "101": [
        {"name": "Reading Journal 1", "due_at": "2026-10-19T22:00:00Z"},
        {"name": "Reading Journal 1", "due_at": "2026-10-19T22:00:00Z"},   # duplicate: dropped
        {"name": "No due date", "due_at": None},                          # dropped
    ],
    "102": [{"name": "Midterm", "due_at": "2026-11-05T05:59:00Z"}],
}


def _run():
    script = textwrap.dedent(f"""
        var P = require({json.dumps(str(PARSE_JS))});
        var out = {{ out: P.buildCanvasImport({json.dumps(COURSES)}, {json.dumps(ASSIGNMENTS)}),
                    codes: ['MIS 430 001', 'MIS430-001', 'ACC-301', 'Intro to Art'].map(P.parseCanvasCode) }};
        process.stdout.write(JSON.stringify(out));
    """)
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@unittest.skipUnless(_node(), "node not available")
class ExtensionCanvasContract(Env):
    def setUp(self):
        super().setUp()
        self.db.items = {k: v for k, v in self.db.items.items() if not k[1].startswith("COURSE#")}

    def test_mapping_shape_and_term_filter(self):
        res = _run()
        out = res["out"]
        self.assertEqual(set(out), {"source", "classes"})
        self.assertEqual(len(out["classes"]), 2)  # old term dropped
        mis = next(c for c in out["classes"] if c["code"] == "MIS 430")
        self.assertEqual(mis["identifier"], "canvas:101")
        self.assertEqual(mis["section"], "001")
        self.assertEqual(mis["instructor"], "Dr. Test Teacher")
        self.assertFalse(set(mis) - {"identifier", "code", "section", "term", "title", "instructor", "assignments"})
        self.assertEqual(mis["assignments"], [{"title": "Reading Journal 1", "dueDate": "2026-10-19", "dueTime": "22:00", "tz": "UTC"}])
        self.assertEqual([c["code"] for c in res["codes"]], ["MIS 430", "MIS 430", "ACC 301", "INTRO TO ART"])

    def test_import_converts_utc_to_campus_time(self):
        out = _run()["out"]
        st, body, _ = self.call("POST", "/courses/import", out, sub=ME)
        self.assertIn(st, (200, 201), body)
        asg = {a["title"]: a for a in self.assignments()}
        # 22:00 UTC on Oct 19 is 17:00 CDT in Chicago; 05:59 UTC on Nov 5 is 23:59 CST on Nov 4.
        self.assertEqual((asg["Reading Journal 1"]["dueDate"], asg["Reading Journal 1"]["dueTime"]), ("2026-10-19", "17:00"))
        self.assertEqual((asg["Midterm"]["dueDate"], asg["Midterm"]["dueTime"]), ("2026-11-04", "23:59"))


if __name__ == "__main__":
    unittest.main()
