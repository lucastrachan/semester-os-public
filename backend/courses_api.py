"""/courses routes (handoff section 9). Called from api.py with the authenticated `sub`."""
import json
import os
import re
import time
from datetime import datetime, timezone

import boto3
from botocore.config import Config

from lib import agents, classdata, db, extract, feedsync, pdf, util

DAILY_COURSE_CAP = 10  # per user per day: each course is a Bedrock call (handoff section 11 caps)
UPLOAD_GRACE_SECONDS = 600  # a PDF upload that hasn't arrived after this long is shown as failed
_ID_RE = re.compile(r"^[a-z0-9]{8}$")
_lambda = None
_s3 = None


def _lambda_client():
    global _lambda
    if _lambda is None:
        _lambda = boto3.client("lambda", region_name=os.environ.get("REGION", "us-east-1"))
    return _lambda


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=os.environ.get("REGION", "us-east-1"),
                           config=Config(signature_version="s3v4"))
    return _s3


def _over_daily_cap(sub: str) -> bool:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return db.incr_counter(f"USER#{sub}", f"CAP#courses#{day}", int(time.time()) + 2 * 86400) > DAILY_COURSE_CAP


def _present(course: dict) -> dict:
    """The course as the API shows it. An upload that never arrived is reported as failed, not 'building' forever."""
    view = agents.public_view(course)
    view["source"] = course.get("source") or "syllabus"
    view["needsSyllabus"] = feedsync.needs_syllabus(course)
    view["archived"] = bool(course.get("archived"))
    view["archivedAt"] = course.get("archivedAt") or None
    if course.get("awaitingUpload") and course.get("status") == "BUILDING":
        created = datetime.fromisoformat(course["createdAt"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - created).total_seconds() > UPLOAD_GRACE_SECONDS:
            msg = "The upload didn't finish. Try again, or paste the syllabus text instead."
            view["status"], view["error"] = "ERROR", msg
            view["pipeline"] = [dict(s) for s in view["pipeline"]]
            view["pipeline"][0].update(state="error", detail=msg)
    return view


def create_course(event: dict, sub: str):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return util.error(400, "bad_request", "Invalid JSON")

    if body.get("filename"):
        return _create_from_upload(body, sub)

    text = body.get("text")
    if not isinstance(text, str) or len(text.strip()) < 50:
        return util.error(400, "validation_error", "Paste the full syllabus text (at least a few sentences).")
    if len(text) > extract.MAX_INPUT_CHARS:
        return util.error(400, "too_long", f"That's too long. Keep it under {extract.MAX_INPUT_CHARS:,} characters.")
    if _over_daily_cap(sub):
        return util.error(429, "daily_cap", "You've added the maximum number of classes for today. Try again tomorrow.")

    course = agents.create_course(sub)
    _lambda_client().invoke(
        FunctionName=os.environ["PROCESS_SYLLABUS_FN"],
        InvocationType="Event",
        Payload=json.dumps({"sub": sub, "courseId": course["id"], "text": text}).encode(),
    )
    agents.log_activity(sub, course["id"], "started", "Building a new class agent from your syllabus")
    return util.ok({"course": agents.public_view(course)}, 202)


def _create_from_upload(body: dict, sub: str):
    """Make the class, then hand the browser a short-lived, size-limited S3 form to upload the PDF into.
    S3 notifies the worker when the file lands (see infra/stack.py)."""
    filename = str(body.get("filename", ""))
    if not filename.lower().endswith(".pdf") or body.get("contentType") != "application/pdf":
        return util.error(400, "validation_error", "Upload the syllabus as a PDF, or paste the text instead.")
    if _over_daily_cap(sub):
        return util.error(429, "daily_cap", "You've added the maximum number of classes for today. Try again tomorrow.")

    course = agents.create_course(sub, awaiting_upload=True)
    key = f"syllabi/{sub}/{course['id']}.pdf"  # the key is derived from the token, never from the request
    upload = _s3_client().generate_presigned_post(
        Bucket=os.environ["UPLOAD_BUCKET"], Key=key,
        Fields={"Content-Type": "application/pdf"},
        Conditions=[{"Content-Type": "application/pdf"}, ["content-length-range", 1, pdf.MAX_PDF_BYTES]],
        ExpiresIn=300,
    )
    agents.log_activity(sub, course["id"], "started", "Waiting for your syllabus PDF to upload")
    return util.ok({"course": agents.public_view(course), "upload": upload}, 201)


def list_courses(sub: str, event=None):
    qs = (event.get("queryStringParameters") or {}) if event else {}
    want_archived = qs.get("archived") == "true"
    items = db.query_pk(f"USER#{sub}", "COURSE#")
    items = [c for c in items if bool(c.get("archived")) == want_archived]
    items.sort(key=lambda c: c.get("createdAt", ""))
    return util.ok({"courses": [_present(c) for c in items]})


def get_course(sub: str, course_id: str):
    if not _ID_RE.match(course_id):
        return util.error(404, "not_found", "Class not found")
    course = db.get_item(f"USER#{sub}", f"COURSE#{course_id}")
    if not course:
        return util.error(404, "not_found", "Class not found")
    assignments = db.query_pk(f"USER#{sub}", f"ASG#{course_id}#")
    assignments.sort(key=lambda a: (a.get("dueDate") is None, a.get("dueDate") or "", a.get("title", "")))
    return util.ok({
        "course": _present(course),
        "assignments": [agents.public_view(a) for a in assignments],
    })


def patch_course(sub: str, course_id: str, event: dict):
    if not _ID_RE.match(course_id):
        return util.error(404, "not_found", "Class not found")
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        body = {}
    if not isinstance(body, dict) or set(body) - {"archived"}:
        return util.error(400, "validation_error", "Only 'archived' may be patched here")
    archived = body.get("archived")
    if not isinstance(archived, bool):
        return util.error(400, "validation_error", "archived must be true or false")
    course = db.get_item(f"USER#{sub}", f"COURSE#{course_id}")
    if not course:
        return util.error(404, "not_found", "Class not found")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updates: dict = {"archived": archived, "archivedAt": now if archived else None}
    updated = db.update_item(f"USER#{sub}", f"COURSE#{course_id}", updates)
    return util.ok({"course": _present(updated)})


def delete_course(sub: str, course_id: str):
    if not _ID_RE.match(course_id):
        return util.error(404, "not_found", "Class not found")
    pk = f"USER#{sub}"
    if not db.get_item(pk, f"COURSE#{course_id}"):
        return util.error(404, "not_found", "Class not found")
    try:   # remember that the student removed a class that Blackboard created (no silent re-creation)
        feedsync.tombstone_course(sub, db, db.get_item(pk, f"COURSE#{course_id}") or {})
    except Exception:  # noqa: BLE001
        pass
    # chat history, memory notes, materials (files, metadata, chunks); runs first because it reads the S3 keys
    classdata.purge_course(sub, course_id, db, _s3_client() if os.environ.get("UPLOAD_BUCKET") else None,
                           os.environ.get("UPLOAD_BUCKET"))
    db.delete_prefix(pk, f"ASG#{course_id}#")
    db.delete_prefix(pk, f"MAT#{course_id}#")
    db.delete_item(pk, f"COURSE#{course_id}")
    bucket = os.environ.get("UPLOAD_BUCKET")
    if bucket:  # delete-my-data: the uploaded PDF goes with the class (handoff section 11)
        _s3_client().delete_object(Bucket=bucket, Key=f"syllabi/{sub}/{course_id}.pdf")
    return util.ok({"deleted": course_id})
