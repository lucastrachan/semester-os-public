import re
import unittest
from datetime import datetime, timezone

from _fakes import FakeDb  # noqa: F401  (sets sys.path)
from lib import ics

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def unfold(s: str) -> list:
    return s.replace("\r\n ", "").split("\r\n")


def asg(**kw):
    base = {"id": "ab12cd34", "title": "Quiz 3", "type": "quiz", "dueDate": "2026-11-05", "dueTime": None,
            "done": False, "sequence": 2, "updatedAt": "2026-10-02T10:00:00Z"}
    base.update(kw)
    return base


def render(*items, course=None, tz="America/Chicago"):
    evs = [ics.assignment_event(a, course, tz, NOW) for a in items]
    return ics.build_calendar([e for e in evs if e])


class Folding(unittest.TestCase):
    def test_short_line_untouched(self):
        self.assertEqual(ics.fold("SUMMARY:hi"), "SUMMARY:hi")

    def test_ascii_fold_at_75_octets_and_roundtrip(self):
        line = "DESCRIPTION:" + "a" * 400
        out = ics.fold(line)
        parts = out.split("\r\n")
        self.assertTrue(all(len(p.encode()) <= 75 for p in parts))
        self.assertTrue(all(p.startswith(" ") for p in parts[1:]))
        self.assertEqual(out.replace("\r\n ", ""), line)

    def test_multibyte_never_split(self):
        line = "SUMMARY:" + "é€😀" * 80
        out = ics.fold(line)
        parts = out.split("\r\n")
        self.assertTrue(all(len(p.encode()) <= 75 for p in parts))
        for p in parts:
            p.encode("utf-8")  # every piece is valid on its own
        self.assertEqual(out.replace("\r\n ", ""), line)

    def test_exactly_75_not_folded(self):
        line = "X" * 75
        self.assertEqual(ics.fold(line), line)
        self.assertEqual(len(ics.fold("X" * 76).split("\r\n")), 2)


class Structure(unittest.TestCase):
    def test_header_and_endings(self):
        out = render(asg())
        self.assertTrue(out.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"))
        self.assertTrue(out.endswith("END:VCALENDAR\r\n"))
        self.assertNotIn("\n", out.replace("\r\n", ""))  # only CRLF line breaks
        for needle in ("X-WR-CALNAME:Semester OS", "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H",
                       "PRODID:", "METHOD:PUBLISH"):
            self.assertIn(needle, out)

    def test_uid_sequence_stamp_are_stable_item_values(self):
        lines = unfold(render(asg()))
        self.assertIn("UID:ab12cd34@semesteros", lines)
        self.assertIn("SEQUENCE:2", lines)
        self.assertIn("DTSTAMP:20261002T100000Z", lines)
        self.assertEqual(render(asg()), render(asg()))  # unchanged data -> byte-identical feed

    def test_all_day_when_no_time(self):
        lines = unfold(render(asg()))
        self.assertIn("DTSTART;VALUE=DATE:20261105", lines)
        self.assertIn("DTEND;VALUE=DATE:20261106", lines)

    def test_all_day_month_end(self):
        lines = unfold(render(asg(dueDate="2026-12-31")))
        self.assertIn("DTEND;VALUE=DATE:20270101", lines)

    def test_timed_event_ends_at_due_time_in_utc(self):
        lines = unfold(render(asg(dueTime="14:30")))  # Nov 5 2026: Chicago is CST (UTC-6)
        self.assertIn("DTSTART:20261105T200000Z", lines)
        self.assertIn("DTEND:20261105T203000Z", lines)

    def test_dst_summer_vs_winter(self):
        summer = unfold(render(asg(dueDate="2026-07-01", dueTime="14:30")))   # CDT, UTC-5
        self.assertIn("DTEND:20260701T193000Z", summer)
        spring_day = unfold(render(asg(dueDate="2026-03-08", dueTime="12:00")))  # the day clocks spring forward
        self.assertIn("DTEND:20260308T170000Z", spring_day)
        fall_day = unfold(render(asg(dueDate="2026-11-01", dueTime="12:00")))     # the day clocks fall back
        self.assertIn("DTEND:20261101T180000Z", fall_day)

    def test_dst_gap_and_overlap_do_not_crash(self):
        for d, t in (("2026-03-08", "02:30"), ("2026-11-01", "01:30")):
            out = render(asg(dueDate=d, dueTime=t))
            self.assertIn("DTEND:", out)

    def test_other_timezones(self):
        out = unfold(render(asg(dueDate="2026-11-05", dueTime="09:00"), tz="Asia/Tokyo"))
        self.assertIn("DTEND:20261105T000000Z", out)
        out = unfold(render(asg(dueDate="2026-11-05", dueTime="09:00"), tz="Not/AZone"))  # falls back, never crashes
        self.assertTrue(any(l.startswith("DTEND:") for l in out))

    def test_course_prefix(self):
        lines = unfold(render(asg(), course={"courseCode": "MIS 405"}))
        self.assertIn("SUMMARY:[MIS 405] Quiz 3", lines)
        self.assertIn("SUMMARY:Quiz 3", unfold(render(asg())))

    def test_skips_done_undated_bad_date_and_bad_id(self):
        out = render(asg(done=True), asg(id="aaaaaaa1", dueDate=None), asg(id="aaaaaaa2", dueDate="2026-13-45"),
                     asg(id="bad id\r\n", title="x"))
        self.assertNotIn("BEGIN:VEVENT", out)

    def test_resolved_date_is_flagged_estimated(self):
        out = "\n".join(unfold(render(asg(dateSource="resolved", weight=10, notes="Bring a calculator"))))
        self.assertIn("estimated", out)
        self.assertIn("Weight: 10% of grade", out)
        self.assertIn("Bring a calculator", out)

    def test_study_block(self):
        ev = ics.study_event({"id": "st000001", "start": "2026-11-04T19:00:00", "end": "2026-11-04T20:00:00", "focus": "Ch 4"},
                             {"courseCode": "MIS 405"}, "America/Chicago", NOW)
        lines = unfold(ics.build_calendar([ev]))
        self.assertIn("DTSTART:20261105T010000Z", lines)  # 19:00 CST
        self.assertIn("SUMMARY:[MIS 405] Study: Ch 4", lines)
        self.assertIsNone(ics.study_event({"id": "st000002", "start": "bad", "end": "x"}, None, "UTC", NOW))
        self.assertIsNone(ics.study_event({"id": "st000003", "start": "2026-11-04T19:00:00", "end": "2026-11-04T19:01:00"}, None, "UTC", NOW))


class Injection(unittest.TestCase):
    EVIL = [
        "Quiz\r\nATTENDEE:mailto:evil@example.com",
        "Quiz\nBEGIN:VALARM\nACTION:PROCEDURE\nEND:VALARM",
        "Quiz\rURL:https://evil.example/x",
        "Quiz ATTENDEE:mailto:x@y.z",
        "Quiz ORGANIZER:mailto:x@y.z",
        "Quiz\x85ATTENDEE:x",
        "Quiz; X-EVIL=1, ATTENDEE:x \\ end",
        "‮Quiz​⁦hidden",
    ]

    def test_no_value_can_add_a_property(self):
        for evil in self.EVIL:
            for field in ("title", "notes"):
                a = asg(title="ok", notes="")
                a[field] = evil
                raw = render(a, course={"courseCode": evil})
                lines = unfold(raw)
                for l in lines:
                    self.assertFalse(re.match(r"^(ATTENDEE|ORGANIZER|URL|ACTION|BEGIN:VALARM)", l), (evil, l))
                self.assertEqual(sum(1 for l in lines if l == "BEGIN:VEVENT"), 1)
                for bad in (" ", " ", "\x85", "‮", "​", "\r\r"):
                    self.assertNotIn(bad, raw)
                # no lone CR or LF anywhere outside CRLF
                self.assertIsNone(re.search(r"(?<!\r)\n|\r(?!\n)", raw), evil)

    def test_special_characters_are_escaped(self):
        lines = unfold(render(asg(title="A, B; C \\ D")))
        self.assertIn("SUMMARY:A\\, B\\; C \\\\ D", lines)

    def test_calendar_name_is_escaped_too(self):
        out = ics.build_calendar([], name="Evil\r\nATTENDEE:x")
        self.assertNotIn("\r\nATTENDEE", out)

    def test_description_newlines_are_the_escaped_sequence(self):
        out = unfold(render(asg(type="quiz", weight=5, notes="line1\nline2")))
        desc = [l for l in out if l.startswith("DESCRIPTION:")][0]
        self.assertIn("\\n", desc)
        self.assertNotIn("\n", desc)


if __name__ == "__main__":
    unittest.main()
