"""Class agent (course record) helpers: creation, build pipeline, activity feed (handoff section 7.1)."""
import time
from datetime import datetime, timezone

from . import db, util

# Class colours, assigned in order at creation and never changed (handoff section 10).
PALETTE = ["#4F46E5", "#0D9488", "#D97706", "#E11D48", "#059669", "#0284C7", "#7C3AED", "#EA580C"]

PIPELINE_STEPS = [
    ("read_syllabus", "Reading syllabus"),
    ("extract_dates", "Finding dates and deadlines"),
    ("build_calendar", "Building calendar"),
    ("match_books", "Matching books"),
    ("tutor_ready", "Tutor ready"),
]

ACTIVITY_TTL_SECONDS = 30 * 24 * 3600


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_pipeline() -> list:
    return [{"key": k, "label": label, "state": "pending", "detail": ""} for k, label in PIPELINE_STEPS]


def set_step(pipeline: list, key: str, state: str, detail: str = "") -> list:
    for step in pipeline:
        if step["key"] == key:
            step["state"], step["detail"] = state, detail
    return pipeline


def create_course(sub: str, awaiting_upload: bool = False) -> dict:
    """Write a BUILDING course record and return it. The colour is the next free slot in the palette.
    With awaiting_upload the class waits for a PDF to land in S3 before the worker builds it."""
    existing = db.query_pk(f"USER#{sub}", "COURSE#")
    course_id = util.short_id()
    now = now_iso()
    course = {
        "pk": f"USER#{sub}", "sk": f"COURSE#{course_id}",
        "id": course_id, "status": "BUILDING",
        "color": PALETTE[len(existing) % len(PALETTE)],
        "createdAt": now, "updatedAt": now,
        "pipeline": new_pipeline(),
        "courseCode": "", "title": "", "instructor": "", "term": "", "officeHours": "", "summary": "",
        "meetings": [], "books": [], "grading": [],
        "policies": {"late": "", "attendance": "", "ai": "", "other": ""},
        "knows": {"materialsCount": 0, "assignmentsCount": 0, "lastUpdatedAt": now,
                  "lastFeedCheckAt": None, "newItemsCount": 0},
    }
    if awaiting_upload:
        course["awaitingUpload"] = True
        course["pipeline"][0]["detail"] = "Waiting for upload"
    db.put_item(course)
    return course


def save_pipeline(sub: str, course_id: str, pipeline: list, **fields) -> None:
    db.update_item(f"USER#{sub}", f"COURSE#{course_id}",
                   util.to_dynamo({"pipeline": pipeline, "updatedAt": now_iso(), **fields}))


def log_activity(sub: str, agent_id: str, kind: str, text: str) -> None:
    ts = now_iso()
    db.put_item({
        "pk": f"USER#{sub}", "sk": f"ACT#{ts}#{util.short_id(4)}",
        "agentId": agent_id, "kind": kind, "text": text[:300],
        "ttl": int(time.time()) + ACTIVITY_TTL_SECONDS,
    })


def public_view(item: dict) -> dict:
    """The course as the API returns it: no DynamoDB keys."""
    return {k: v for k, v in item.items() if k not in ("pk", "sk", "awaitingUpload")}
