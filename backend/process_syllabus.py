"""Async worker: turns a syllabus (pasted text or an uploaded PDF) into a READY class agent.

Two entry points, same pipeline:
  - api.py invokes it asynchronously with {"sub", "courseId", "text"} (paste path).
  - S3 invokes it when a PDF lands under syllabi/{sub}/{courseId}.pdf (upload path).
The API returns immediately (HTTP API integrations time out at ~30s) and the UI polls
GET /courses/{id} for pipeline progress.
"""
import os
import re
import traceback
from datetime import datetime
from urllib.parse import unquote_plus
from zoneinfo import ZoneInfo

import boto3

from lib import agents, db, extract, pdf, util

# Cognito subs are UUIDs; the key layout is fixed by courses_api.create_course.
_KEY_RE = re.compile(r"^syllabi/([0-9a-f\-]{36})/([a-z0-9]{8})\.pdf$")
_s3 = None


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=os.environ.get("REGION", "us-east-1"))
    return _s3


def _today(sub: str):
    """Today's date in the student's campus timezone (falls back to the server's local date)."""
    tz = "America/Chicago"
    try:
        profile = db.get_item(f"USER#{sub}", "PROFILE") or {}
        tenant = db.get_item("TENANTS", f"T#{profile.get('tenantId', '')}") or {}
        tz = tenant.get("timezone") or tz
        return datetime.now(ZoneInfo(tz)).date()
    except Exception:
        return datetime.now().date()


def handler(event, context):
    if event.get("Records"):  # S3 upload notification
        return _handle_s3(event["Records"][0]["s3"])
    return build_course(event["sub"], event["courseId"], text=event.get("text") or "")


def _handle_s3(s3_record: dict):
    key = unquote_plus(s3_record["object"]["key"])
    m = _KEY_RE.match(key)
    if not m:
        print(f"ignoring unexpected key shape: {key[:80]}")
        return {"ok": False, "reason": "unexpected key"}
    sub, course_id = m.groups()
    # Only a course that is waiting for exactly this upload may be built; a duplicate S3 event is ignored.
    if not db.claim_upload(f"USER#{sub}", f"COURSE#{course_id}"):
        return {"ok": False, "reason": "no pending upload for this course"}
    bucket = s3_record["bucket"]["name"]
    size = s3_record["object"].get("size", 0)
    if size > pdf.MAX_PDF_BYTES:
        return _fail_by_id(sub, course_id, "That PDF is larger than 10 MB. Try a smaller file or paste the text.")
    data = _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read(pdf.MAX_PDF_BYTES + 1)
    return build_course(sub, course_id, pdf_bytes=data)


def build_course(sub: str, course_id: str, text: str = "", pdf_bytes: bytes | None = None):
    pk, sk = f"USER#{sub}", f"COURSE#{course_id}"
    course = db.get_item(pk, sk)
    if not course:
        return {"ok": False, "reason": "course not found"}
    pipeline = course["pipeline"]

    try:
        agents.set_step(pipeline, "read_syllabus", "running")
        agents.save_pipeline(sub, course_id, pipeline)
        today = _today(sub)
        if pdf_bytes is not None:
            data, used_text = extract.extract_syllabus_pdf(pdf_bytes, today)
            read_detail = (f"PDF, {len(used_text):,} characters" if used_text
                           else "Scanned PDF, read as an image")
        else:
            data = extract.extract_syllabus(text, today)
            read_detail = f"{len(text):,} characters"
        agents.set_step(pipeline, "read_syllabus", "done", read_detail)
        agents.set_step(pipeline, "extract_dates", "done",
                        f"{len(data['assignments'])} items, "
                        f"{sum(1 for a in data['assignments'] if a['dueDate'])} with dates")
        agents.set_step(pipeline, "build_calendar", "running")
        agents.save_pipeline(sub, course_id, pipeline)

        now = agents.now_iso()
        dated = 0
        for a in data["assignments"]:
            asg_id = util.short_id()
            dated += 1 if a["dueDate"] else 0
            db.put_item(util.to_dynamo({
                "pk": pk, "sk": f"ASG#{course_id}#{asg_id}",
                "id": asg_id, "courseId": course_id, "title": a["title"], "type": a["type"],
                "dueDate": a["dueDate"], "dueTime": a["dueTime"], "weight": a["weightPercent"],
                "dueText": a["dueText"], "dateSource": a["dateSource"],  # "stated" | "resolved" (estimated) | None
                "notes": a["notes"], "done": False, "source": "syllabus", "createdAt": now,
            }))
        agents.set_step(pipeline, "build_calendar", "done", f"{dated} dated deadlines added")
        agents.set_step(pipeline, "match_books", "done",
                        f"{len(data['books'])} books found (marketplace matching comes later)")
        agents.set_step(pipeline, "tutor_ready", "done", "Course facts saved")

        agents.save_pipeline(
            sub, course_id, pipeline, status="READY",
            courseCode=data["courseCode"], title=data["title"], instructor=data["instructor"],
            term=data["term"], officeHours=data["officeHours"], summary=data["summary"],
            meetings=data["meetings"], books=data["books"], grading=data["grading"],
            policies=data["policies"],
            knows={**course["knows"], "assignmentsCount": len(data["assignments"]), "lastUpdatedAt": now},
        )
        agents.log_activity(sub, course_id, "built",
                            f"{data['courseCode'] or 'New class'} agent is ready: {len(data['assignments'])} items, "
                            f"{len(data['books'])} books")
        return {"ok": True}

    except (extract.ExtractionError, pdf.PdfError) as e:
        _fail(sub, course_id, pipeline, str(e))
    except Exception:
        print("process_syllabus failed:")
        traceback.print_exc()
        _fail(sub, course_id, pipeline,
              "Something went wrong while building this class. Try again in a minute, or paste the text instead.")
    return {"ok": False}


def _fail_by_id(sub: str, course_id: str, message: str):
    course = db.get_item(f"USER#{sub}", f"COURSE#{course_id}")
    if course:
        _fail(sub, course_id, course["pipeline"], message)
    return {"ok": False}


def _fail(sub: str, course_id: str, pipeline: list, message: str) -> None:
    marked = False
    for step in pipeline:
        if step["state"] == "running":
            step["state"], step["detail"] = "error", message
            marked = True
    if not marked:  # failed before any step ran (e.g. rejected upload): mark the first step
        pipeline[0]["state"], pipeline[0]["detail"] = "error", message
    agents.save_pipeline(sub, course_id, pipeline, status="ERROR", error=message)
    agents.log_activity(sub, course_id, "error", message)
