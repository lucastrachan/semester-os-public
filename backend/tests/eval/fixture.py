"""Synthetic MIS 430-like course fixture for eval tests.

Seeded with:
  - MIS 430 course (id: "mis43001") with syllabus facts, policies, books, deadlines
  - EN 210 course  (id: "eng21001") for handoff/routing tests
  - Four ready materials: Syllabus, Project 1 Prompt, Chapter 5 Slides, Blackboard content index
  - Five deadlines for MIS 430
  - A student profile

The Blackboard content index lists five items NOT yet in the KB:
  Project 2 Prompt, Project 2 Submission, Final Exam Study Guide,
  Discussion 3: ERP Systems, Week 8 Lecture Recording
"""
import sys
from pathlib import Path

BACKEND = str(Path(__file__).resolve().parents[2])
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from _fakes import FakeDb  # noqa: E402
from lib import materials, tools_impl  # noqa: E402

SUB = "eval-user-mis430"
COURSE_ID = "mis43001"
ENG_ID = "eng21001"
TODAY_STR = "2026-10-17"

# ── index content ─────────────────────────────────────────────────────────────

INDEX_CONTENT = """\
Content > Project 2 Prompt [File] <https://bb.example.edu/mis430/proj2prompt>
Content > Project 2 Submission [Assignment] <https://bb.example.edu/mis430/proj2>
Content > Final Exam Study Guide [File] <https://bb.example.edu/mis430/examguide>
Content > Discussion 3: ERP Systems [Discussion] <https://bb.example.edu/mis430/disc3>
Content > Week 8 Lecture Recording [File] <https://bb.example.edu/mis430/week8>
"""

# ── material chunks ───────────────────────────────────────────────────────────

SYLLABUS_TEXT = (
    "MIS 430 Fall 2026 Syllabus. Instructor: Dr. Martinez. Office: Smith Hall 210. "
    "Office hours: Tuesday and Thursday 3-4pm. "
    "Course meets MWF 9-10am in Brown Hall 305. "
    "Grading: Exams 40%, Projects 35%, Homework 15%, Participation 10%. "
    "AI policy: No AI on graded work without prior instructor approval. "
    "Late policy: 10% penalty per day. Attendance is mandatory. "
    "Required textbook: MIS Essentials by Valacich, ISBN 9780134145167. "
    "Course covers systems analysis, database design, ERP systems, cybersecurity, and IT project management."
)

PROJECT1_TEXT = (
    "Project 1 Prompt — Analyzing a Business Process. Due: October 25, 2026. "
    "Worth 15% of your grade. "
    "You will select a real business process (e.g., order fulfillment, hiring) and model it using "
    "a flowchart and a narrative description. "
    "Deliverables: 1) Process flowchart (Visio or draw.io), 2) 3-page written analysis, "
    "3) Identification of at least two inefficiencies and proposed improvements. "
    "Submit as a single PDF to the Project 1 Submission link on Blackboard. "
    "Grading rubric: Clarity 25%, Accuracy 35%, Analysis depth 40%."
)

CHAPTER5_TEXT = (
    "Chapter 5: Database Normalization and ER Diagrams. "
    "Normalization is the process of organizing a relational database to reduce redundancy and "
    "improve data integrity. "
    "First Normal Form (1NF): every column must be atomic — no repeating groups or multi-valued attributes. "
    "Second Normal Form (2NF): must be in 1NF and every non-key attribute must depend on the whole primary key "
    "(eliminates partial dependencies). "
    "Third Normal Form (3NF): must be in 2NF and no transitive dependencies — non-key attributes must not "
    "depend on other non-key attributes. "
    "Entity-Relationship (ER) diagrams use entities, attributes, and relationships to model data. "
    "Cardinality (one-to-one, one-to-many, many-to-many) describes how many instances of one entity "
    "relate to instances of another. "
    "Boyce-Codd Normal Form (BCNF): stronger version of 3NF; every determinant must be a candidate key."
)


def build_db() -> "tuple[FakeDb, dict, tools_impl.guard.UserScopedDB]":
    """Seed and return (db, course_dict, scoped_view)."""
    db = FakeDb()
    pk = f"USER#{SUB}"

    # ── student profile ──────────────────────────────────────────────────────
    db.put_item({"pk": pk, "sk": "PROFILE", "calToken": "EVALTESTTOKEN0000000000"})

    # ── MIS 430 course ───────────────────────────────────────────────────────
    course = {
        "pk": pk, "sk": f"COURSE#{COURSE_ID}", "id": COURSE_ID, "status": "READY",
        "courseCode": "MIS 430", "title": "Management Information Systems",
        "instructor": "Dr. Martinez", "term": "Fall 2026",
        "meetings": "MWF 9-10am, Brown Hall 305",
        "officeHours": "Tue/Thu 3-4pm, Smith Hall 210",
        "summary": ("Covers systems analysis, database design, ERP systems, "
                    "cybersecurity fundamentals, and IT project management."),
        "grading": {"exams": "40%", "projects": "35%", "homework": "15%", "participation": "10%"},
        "books": [{"title": "MIS Essentials", "author": "Valacich",
                   "isbn": "9780134145167", "required": True}],
        "policies": {
            "ai": "No AI on graded work without prior instructor approval.",
            "late": "10% per day late.",
            "attendance": "mandatory",
            "other": "",
        },
        "knows": {"materialsCount": 4},
    }
    db.put_item(course)

    # ── EN 210 course (for routing tests) ───────────────────────────────────
    db.put_item({
        "pk": pk, "sk": f"COURSE#{ENG_ID}", "id": ENG_ID, "status": "READY",
        "courseCode": "EN 210", "title": "College Writing",
        "instructor": "Prof. Adams", "term": "Fall 2026",
        "policies": {"ai": "", "late": "", "attendance": "", "other": ""},
    })

    # ── MIS 430 deadlines ────────────────────────────────────────────────────
    for asg_id, title, atype, due in [
        ("disc3asg1", "Discussion 3: ERP Systems", "homework", "2026-10-20"),
        ("proj1asg1", "Project 1", "project", "2026-10-25"),
        ("exam2asg1", "Exam 2", "exam", "2026-11-10"),
        ("proj2asg1", "Project 2", "project", "2026-11-15"),
        ("finalasg1", "Final Exam", "exam", "2026-12-15"),
    ]:
        db.put_item({"pk": pk, "sk": f"ASG#{COURSE_ID}#{asg_id}",
                     "id": asg_id, "courseId": COURSE_ID, "title": title,
                     "type": atype, "dueDate": due, "dueTime": None,
                     "dateSource": "stated", "done": False, "source": "syllabus"})

    # ── Materials ────────────────────────────────────────────────────────────
    def add_mat(mat_id, title, text):
        db.put_item({"pk": pk, "sk": f"MAT#{COURSE_ID}#{mat_id}",
                     "id": mat_id, "courseId": COURSE_ID, "title": title,
                     "kind": "text", "status": "ready", "summary": text[:120].replace("\n", " "),
                     "chars": len(text), "chunkCount": 1, "pages": None,
                     "addedAt": "2026-10-01T00:00:00Z", "error": "", "awaitingUpload": False})
        db.put_item({"pk": pk, "sk": f"CHUNK#{COURSE_ID}#{mat_id}#0",
                     "materialId": mat_id, "courseId": COURSE_ID, "n": 0, "text": text})

    add_mat("syl00001", "MIS 430 Fall 2026 Syllabus", SYLLABUS_TEXT)
    add_mat("pr100001", "Project 1 Prompt", PROJECT1_TEXT)
    add_mat("ch500001", "Chapter 5 Slides", CHAPTER5_TEXT)
    add_mat("idx00001", "Blackboard content index", INDEX_CONTENT)

    v = tools_impl.scoped_view(SUB, db)
    return db, course, v


def courses_list(db) -> list:
    """Minimal course dicts for routing.pre_route."""
    return [
        {"id": COURSE_ID, "status": "READY", "courseCode": "MIS 430",
         "title": "Management Information Systems", "instructor": "Dr. Martinez"},
        {"id": ENG_ID, "status": "READY", "courseCode": "EN 210",
         "title": "College Writing", "instructor": "Prof. Adams"},
    ]
