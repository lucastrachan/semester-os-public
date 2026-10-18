"""Class materials routes. Contract: MATERIALS_API.md.

handle(event, sub, path, method, deps=None) returns a response dict, or None when the path is not one of its own.
`deps` (tests): {"backend", "table", "s3", "invoke", "bucket", "now"}; `invoke(payload: dict)` starts process_material.
"""
import json
import os
import re
from datetime import datetime, timezone

from lib import classdata, guard, limits, materials, util

_COLL_RE = re.compile(r"^/courses/([a-z0-9]{8})/materials$")
_TEXT_RE = re.compile(r"^/courses/([a-z0-9]{8})/materials/text$")
_ONE_RE = re.compile(r"^/courses/([a-z0-9]{8})/materials/([A-Za-z0-9_\-]{1,40})$")
PDF_MAX_BYTES = 12 * 1024 * 1024
_DOC_MAX_BYTES = 12 * 1024 * 1024
_TYPES = {
    "application/pdf": ("pdf", "pdf", (".pdf",), PDF_MAX_BYTES),
    "text/plain": ("text", "txt", (".txt", ".md"), materials.MAX_TEXT_FILE_BYTES),
    "text/csv": ("text", "csv", (".csv",), materials.MAX_TEXT_FILE_BYTES),
    "application/json": ("text", "json", (".json",), materials.MAX_TEXT_FILE_BYTES),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ("docx", "docx", (".docx",), _DOC_MAX_BYTES),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ("pptx", "pptx", (".pptx",), _DOC_MAX_BYTES),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ("xlsx", "xlsx", (".xlsx",), _DOC_MAX_BYTES),
    "application/vnd.oasis.opendocument.text": ("odt", "odt", (".odt",), _DOC_MAX_BYTES),
    "application/vnd.oasis.opendocument.presentation": ("odp", "odp", (".odp",), _DOC_MAX_BYTES),
    "application/vnd.oasis.opendocument.spreadsheet": ("ods", "ods", (".ods",), _DOC_MAX_BYTES),
    "application/rtf": ("rtf", "rtf", (".rtf",), _DOC_MAX_BYTES),
    "text/rtf": ("rtf", "rtf", (".rtf",), _DOC_MAX_BYTES),
    "text/html": ("html", "html", (".html", ".htm"), _DOC_MAX_BYTES),
}
_LEGACY_TYPES = {
    "application/msword": "Word (.doc)",
    "application/vnd.ms-powerpoint": "PowerPoint (.ppt)",
    "application/vnd.ms-excel": "Excel (.xls)",
}


def _default_deps() -> dict:
    import boto3
    from botocore.config import Config
    from lib import db

    region = os.environ.get("REGION", "us-east-1")

    def invoke(payload: dict) -> None:
        boto3.client("lambda", region_name=region).invoke(
            FunctionName=os.environ["PROCESS_MATERIAL_FN"], InvocationType="Event", Payload=json.dumps(payload).encode())

    return {"backend": db, "table": None, "invoke": invoke, "bucket": os.environ.get("UPLOAD_BUCKET"),
            "s3": boto3.client("s3", region_name=region, config=Config(signature_version="s3v4"))}


def _is_own(method: str, path: str) -> bool:
    if _COLL_RE.match(path):
        return method in ("GET", "POST")
    if _TEXT_RE.match(path):
        return method == "POST"
    return bool(_ONE_RE.match(path)) and method == "DELETE"


def _body(event: dict) -> dict:
    limits.check_body_size(event)
    try:
        data = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        raise materials.MaterialError(400, "bad_request", "Invalid JSON")
    if not isinstance(data, dict):
        raise materials.MaterialError(400, "bad_request", "Body must be a JSON object")
    return data


def handle(event: dict, sub: str, path: str, method: str, deps: dict | None = None):
    method = (method or "").upper()
    if not _is_own(method, path):
        return None
    try:
        deps = deps or _default_deps()
        backend = deps["backend"]
        table = deps.get("table") or (backend.table() if hasattr(backend, "table") else None)
        m = _TEXT_RE.match(path) or _COLL_RE.match(path) or _ONE_RE.match(path)
        course_id = m.group(1)
        v = materials.view(sub, backend)
        limits.check_user(table, sub, "default")
        if not v.get(f"COURSE#{course_id}"):
            return util.error(404, "not_found", "Class not found")
        now = deps.get("now") or datetime.now(timezone.utc)
        if m.re is _ONE_RE:
            return _delete(v, sub, course_id, m.group(2), deps)
        if m.re is _TEXT_RE:
            return _paste(event, v, sub, course_id, table, deps)
        if method == "GET":
            items = sorted(materials.list_items(v, course_id), key=lambda i: i.get("addedAt", ""), reverse=True)
            return util.ok({"materials": [materials.public(i, now) for i in items], "limit": materials.MAX_MATERIALS,
                            "notice": materials.NOTICE})
        return _start_upload(event, v, sub, course_id, table, deps)
    except limits.LimitError as e:
        return limits.error_response(e)
    except materials.MaterialError as e:
        return util.error(e.status, e.code, e.message)
    except Exception as e:  # noqa: BLE001  (includes guard.ScopeError)
        print(f"materials_api unexpected error: {type(e).__name__}")
        return util.error(500, "internal_error", "An internal error occurred")


def _start_upload(event, v, sub, course_id, table, deps) -> dict:
    data = _body(event)
    filename, ctype, title = data.get("filename"), data.get("contentType"), data.get("title")
    # Legacy format: give a helpful error before the generic validation check
    if isinstance(ctype, str) and ctype in _LEGACY_TYPES:
        raise materials.MaterialError(400, "unsupported_format",
                                      f"This is an older {_LEGACY_TYPES[ctype]} file. "
                                      f"Open it and save as PDF, then upload the PDF.")
    if isinstance(filename, str) and "." in filename:
        _ext = filename.lower().rsplit(".", 1)[-1]
        if _ext in ("doc", "ppt", "xls"):
            _label = {"doc": "Word (.doc)", "ppt": "PowerPoint (.ppt)", "xls": "Excel (.xls)"}[_ext]
            raise materials.MaterialError(400, "unsupported_format",
                                          f"This is an older {_label} file. Open it and save as PDF, then upload the PDF.")
    spec = _TYPES.get(ctype) if isinstance(ctype, str) else None
    if not isinstance(filename, str) or not 1 <= len(filename) <= 200 or spec is None \
            or not filename.lower().endswith(spec[2]):
        raise materials.MaterialError(400, "validation_error",
                                      "Accepted: PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), "
                                      "OpenDocument (.odt/.odp/.ods), RTF, HTML, CSV, JSON, or plain text (.txt, .md). "
                                      "Or paste the text.")
    if title is not None and not isinstance(title, str):
        raise materials.MaterialError(400, "validation_error", "title must be text")
    kind, ext, _, max_bytes = spec
    limits.check_user(table, sub, "material")
    item = materials.create_pending(v, course_id, kind, title or materials.title_from_filename(filename), filename, ext, True, sub, now=deps.get("now"))
    upload = deps["s3"].generate_presigned_post(
        Bucket=deps["bucket"], Key=item["s3Key"], Fields={"Content-Type": ctype},
        Conditions=[{"Content-Type": ctype}, ["content-length-range", 1, max_bytes]], ExpiresIn=300)
    materials.log_activity(v, course_id, f"Waiting for {item['title']} to upload")
    return util.ok({"material": materials.public(item, deps.get("now")), "upload": upload}, 201)


def _paste(event, v, sub, course_id, table, deps) -> dict:
    data = _body(event)
    title, text = data.get("title"), data.get("text")
    if not isinstance(title, str) or not isinstance(text, str):
        raise materials.MaterialError(400, "validation_error", "Give the notes a title and some text.")
    if len(text) > materials.MAX_PASTE_CHARS:
        raise materials.MaterialError(413, "too_large", f"That's too long. Keep pasted text under {materials.MAX_PASTE_CHARS:,} characters.")
    clean = guard.clean_text(text, materials.MAX_PASTE_CHARS)
    if not materials.clean_title(title, "") or len(clean.strip()) < 20:
        raise materials.MaterialError(400, "validation_error", "Give the notes a title and at least a few sentences of text.")
    limits.check_user(table, sub, "material")
    # Replace-by-title: if a material with the same title already exists, delete it first.
    # This lets the extension re-upload "Blackboard content index" without duplicating.
    clean_t = materials.clean_title(title)
    for existing in materials.list_items(v, course_id):
        if materials.clean_title(existing.get("title")) == clean_t:
            key = materials.delete_material(v, course_id, existing["id"])
            if key and deps.get("s3") is not None and deps.get("bucket"):
                try:
                    deps["s3"].delete_object(Bucket=deps["bucket"], Key=key)
                except Exception:  # noqa: BLE001
                    pass
            break
    item = materials.create_pending(v, course_id, "paste", title, "", None, False, sub, now=deps.get("now"))
    try:
        deps["invoke"]({"sub": sub, "courseId": course_id, "matId": item["id"], "text": clean})
    except Exception as e:  # noqa: BLE001
        print(f"process_material invoke failed: {type(e).__name__}")
        materials.mark_error(v, course_id, item["id"], "I couldn't start reading that. Try again in a minute.")
        return util.error(503, "busy", "I couldn't start reading that. Try again in a minute.")
    materials.log_activity(v, course_id, f"Reading {item['title']}")
    return util.ok({"material": materials.public(item)}, 202)


def _delete(v, sub, course_id, mat_id, deps) -> dict:
    key = materials.delete_material(v, course_id, mat_id)
    if key and deps.get("s3") is not None and deps.get("bucket"):
        try:
            deps["s3"].delete_object(Bucket=deps["bucket"], Key=key)
        except Exception as e:  # noqa: BLE001  (the record is gone; the lifecycle rule is the backstop)
            print(f"material file delete failed: {type(e).__name__}")
    materials.log_activity(v, course_id, "Removed a material")
    return util.ok({"deleted": mat_id})
