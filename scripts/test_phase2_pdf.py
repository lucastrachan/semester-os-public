#!/usr/bin/env python3
"""Offline tests for the PDF upload path (Phase 2, slice 2). No AWS calls.

Run from the repo root:  python -I scripts/test_phase2_pdf.py
Reuses the in-memory fake db and fake Bedrock helpers from scripts/test_phase2.py.
"""
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_phase2 as t  # noqa: E402  (patches lib.db with the in-memory fake on import)

from lib import agents, bedrock, db, extract, pdf  # noqa: E402
import courses_api  # noqa: E402
import process_syllabus  # noqa: E402

SUB = "0123abcd-0123-4abc-8def-0123456789ab"
LONG_LINES = [
    "MIS 405 Systems Analysis Fall 2026 syllabus",
    "Exam 1 is on October 29.",
    "Homework 3 is due the Friday after Exam 1.",
    "Required book: Fake Book by A. Author.",
    "Office hours Tuesday 2 to 4 in Room 12, instructor Dr. Test.",
    "Late work loses ten percent per day.",
]


def make_pdf(lines) -> bytes:
    """A minimal one-page PDF with a real text layer (Helvetica); no PDF-writing library needed."""
    nl = chr(10)
    stream = "BT /F1 11 Tf 40 760 Td 14 TL " + " ".join(
        "(" + line.replace("(", "").replace(")", "") + ") Tj T*" for line in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>{nl}stream{nl}{stream}{nl}endstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = "%PDF-1.4" + nl, []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj{nl}{o}{nl}endobj{nl}"
    xref = len(out)
    out += f"xref{nl}0 {len(objs) + 1}{nl}0000000000 65535 f {nl}" + "".join(f"{o:010d} 00000 n {nl}" for o in offsets)
    out += f"trailer{nl}<< /Size {len(objs) + 1} /Root 1 0 R >>{nl}startxref{nl}{xref}{nl}%%EOF"
    return out.encode("latin-1")


class FakeS3:
    def __init__(self, data):
        self.data, self.posts, self.deleted = data, [], []

    def get_object(self, **kw):
        return {"Body": io.BytesIO(self.data)}

    def generate_presigned_post(self, **kw):
        self.posts.append(kw)
        return {"url": "https://bucket.s3.amazonaws.com/", "fields": {"key": kw["Key"], **kw["Fields"]}}

    def delete_object(self, **kw):
        self.deleted.append(kw)


def record(key, size=1000):
    return {"Records": [{"s3": {"bucket": {"name": "b"}, "object": {"key": key, "size": size}}}]}


def test_pdf_text_extraction_and_errors():
    text = pdf.extract_text(make_pdf(LONG_LINES))
    assert "Exam 1 is on October 29" in text and len(text) >= pdf.MIN_USEFUL_CHARS, text
    for bad, expect in [(b"not a pdf", "isn't a PDF"), (b"%PDF" + b"x" * (pdf.MAX_PDF_BYTES + 1), "10 MB"),
                        (b"%PDF-1.4 garbage", "couldn't read")]:
        try:
            pdf.extract_text(bad)
            raise AssertionError("expected PdfError")
        except pdf.PdfError as e:
            assert expect in str(e), str(e)


def test_pdf_text_path_sends_text_not_document():
    seen = {}

    def fake(model, system, messages, **k):
        seen["model"], seen["content"] = model, messages[0]["content"]
        return t.tool_resp(t.GOOD)
    bedrock.converse = fake
    data, used = extract.extract_syllabus_pdf(make_pdf(LONG_LINES), t.TODAY)
    assert data["courseCode"] == "MIS 405" and "Exam 1" in used
    assert seen["model"] == bedrock.MODEL_MAIN and all("document" not in b for b in seen["content"])


def test_scanned_pdf_falls_back_to_document_model():
    seen = {}

    def fake(model, system, messages, **k):
        seen["model"], seen["content"] = model, messages[0]["content"]
        return t.tool_resp(t.GOOD)
    bedrock.converse = fake
    scanned = make_pdf(["x"])  # a valid PDF with almost no text layer
    data, used = extract.extract_syllabus_pdf(scanned, t.TODAY)
    doc = seen["content"][0]["document"]
    assert used == "" and seen["model"] == bedrock.MODEL_FAST
    assert doc["format"] == "pdf" and doc["source"]["bytes"] == scanned


def test_upload_flow_end_to_end():
    t.STORE.clear()
    t.COUNTERS.clear()
    os.environ["UPLOAD_BUCKET"] = "b"
    fs3 = FakeS3(make_pdf(LONG_LINES))
    courses_api._s3 = fs3
    process_syllabus._s3 = fs3

    def ev(body):
        return {"body": json.dumps(body)}

    for bad in ({"filename": "a.txt", "contentType": "text/plain"}, {"filename": "a.pdf", "contentType": "image/png"}):
        assert courses_api.create_course(ev(bad), SUB)["statusCode"] == 400
    r = courses_api.create_course(ev({"filename": "My Syllabus.pdf", "contentType": "application/pdf"}), SUB)
    body = json.loads(r["body"])
    assert r["statusCode"] == 201 and "awaitingUpload" not in body["course"]
    cid = body["course"]["id"]
    post = fs3.posts[0]
    assert post["Key"] == f"syllabi/{SUB}/{cid}.pdf", "the key comes from the token, not from the request"
    assert ["content-length-range", 1, 10 * 1024 * 1024] in post["Conditions"] and post["ExpiresIn"] <= 300

    bedrock.converse = lambda *a, **k: t.tool_resp(t.GOOD)  # the file arrives and the worker builds the class
    assert process_syllabus.handler(record(f"syllabi/{SUB}/{cid}.pdf"), None) == {"ok": True}
    c = db.get_item(f"USER#{SUB}", f"COURSE#{cid}")
    assert c["status"] == "READY" and c["pipeline"][0]["detail"].startswith("PDF,")
    # a duplicate S3 event, a bad key and a key for a course that isn't waiting are all ignored
    assert process_syllabus.handler(record(f"syllabi/{SUB}/{cid}.pdf"), None)["ok"] is False
    assert process_syllabus.handler(record("syllabi/../../x.pdf"), None)["ok"] is False
    assert process_syllabus.handler(record(f"syllabi/{SUB}/zzzzzzzz.pdf"), None)["ok"] is False
    # deleting the class removes the uploaded file too
    assert courses_api.delete_course(SUB, cid)["statusCode"] == 200
    assert fs3.deleted == [{"Bucket": "b", "Key": f"syllabi/{SUB}/{cid}.pdf"}]


def test_oversize_and_stale_uploads():
    t.STORE.clear()
    c = agents.create_course(SUB, awaiting_upload=True)
    r = process_syllabus.handler(record(f"syllabi/{SUB}/{c['id']}.pdf", size=50 * 1024 * 1024), None)
    got = db.get_item(f"USER#{SUB}", f"COURSE#{c['id']}")
    assert r["ok"] is False and got["status"] == "ERROR" and "10 MB" in got["error"]
    # an upload that never arrives is reported as failed after the grace period
    stale = agents.create_course(SUB, awaiting_upload=True)
    old = (datetime.now(timezone.utc) - timedelta(seconds=courses_api.UPLOAD_GRACE_SECONDS + 5))
    db.update_item(f"USER#{SUB}", f"COURSE#{stale['id']}", {"createdAt": old.isoformat().replace("+00:00", "Z")})
    view = json.loads(courses_api.get_course(SUB, stale["id"])["body"])["course"]
    assert view["status"] == "ERROR" and view["pipeline"][0]["state"] == "error" and "awaitingUpload" not in view


if __name__ == "__main__":
    print("Phase 2 PDF offline tests")
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            t.run(name, fn)
    print("all passed")
