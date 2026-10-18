"""Async worker: turns an uploaded or pasted material into searchable chunks plus a summary. Contract: MATERIALS_API.md.

Entry points (same pipeline):
  - S3 notification when a file lands at materials/{sub}/{courseId}/{matId}.{pdf|txt|docx|pptx|xlsx|odt|odp|ods|rtf|html|csv|json}
  - materials_api invokes it asynchronously for pasted text: {"sub", "courseId", "matId", "text"}
The key shape is fixed by materials_api; sub, class and material ids are taken from the key, and the material must
exist and still be waiting for exactly this upload (a duplicate or forged event is ignored). Nothing in a file is
executed or fetched. `deps` (tests): {"backend", "converse", "claim"(pk, sk)->bool, "read"(bucket, key, max)->bytes}.
"""
import html as _html
import io
import re
import traceback
import zipfile
from urllib.parse import unquote_plus

from lib import guard, materials, pdf

PDF_CAP = pdf.MAX_PDF_BYTES
DOC_CAP = 12 * 1024 * 1024

_MAX_ZIP_UNCOMPRESSED = 25 * 1024 * 1024
_MAX_ZIP_ENTRIES = 600
_MAX_ZIP_RATIO = 100
_SLIDE_CAP = 40

# Zip-based XML extraction patterns (no XML parser — avoids external entity expansion)
_WP_RE = re.compile(r"<w:p[ >].*?</w:p>", re.DOTALL)
_WT_RE = re.compile(r"<w:t(?:[^>]*)?>([^<]*)</w:t>")
_AP_RE = re.compile(r"<a:p[ >].*?</a:p>", re.DOTALL)
_AT_RE = re.compile(r"<a:t(?:[^>]*)?>([^<]*)</a:t>")
_SLIDE_FILE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_SI_RE = re.compile(r"<si>.*?</si>", re.DOTALL)
_T_IN_SI_RE = re.compile(r"<t(?:[^>]*)?>([^<]*)</t>")
_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*>", re.DOTALL)
_RTF_HEX_RE = re.compile(r"\\'([0-9a-fA-F]{2})")
_RTF_CTRL_RE = re.compile(r"\\[a-z]+(-?\d+)? ?")
_HTML_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</(script|style)>", re.DOTALL | re.IGNORECASE)
_HTML_NL_RE = re.compile(r"<(?:br|/p|/div|/h\d|/tr|/li|/blockquote)\b[^>]*>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n{3,}")


def _check_zip(data: bytes, fmt: str = "file") -> zipfile.ZipFile:
    """Open and validate a zip file against safety limits. Raises MaterialError on violations."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        raise materials.MaterialError(400, "unreadable",
                                      f"Couldn't read that {fmt}. Try saving as PDF, or paste the text.")
    infos = z.infolist()
    if len(infos) > _MAX_ZIP_ENTRIES:
        z.close()
        raise materials.MaterialError(400, "unreadable",
                                      "That file has too many internal entries and can't be processed.")
    total = 0
    for info in infos:
        if info.flag_bits & 0x1:
            z.close()
            raise materials.MaterialError(400, "unreadable",
                                          "Password-protected files can't be read. Remove the password, or paste the text.")
        if info.compress_size > 0 and info.file_size > _MAX_ZIP_RATIO * info.compress_size:
            z.close()
            raise materials.MaterialError(400, "unreadable",
                                          "That file appears to be corrupted or invalid.")
        total += info.file_size
        if total > _MAX_ZIP_UNCOMPRESSED:
            z.close()
            raise materials.MaterialError(400, "unreadable",
                                          "That file's content is too large to process. Try splitting it into smaller files, or paste the text.")
    return z


def _strip_doctype(xml: str) -> str:
    return _DOCTYPE_RE.sub("", xml)


def _extract_docx(data: bytes) -> str:
    """Plain text from .docx (regex, entity-safe). Raises MaterialError on failure."""
    z = _check_zip(data, "Word document")
    try:
        if "word/document.xml" not in z.namelist():
            raise materials.MaterialError(400, "unreadable",
                                          "Couldn't read that Word document. Try saving it as a PDF, or paste the text.")
        xml = _strip_doctype(z.read("word/document.xml").decode("utf-8", errors="replace"))
    finally:
        z.close()
    parts = []
    for para in _WP_RE.findall(xml):
        line = _html.unescape("".join(_WT_RE.findall(para)))
        if line.strip():
            parts.append(line.strip())
    if not parts:
        raise materials.MaterialError(400, "unreadable",
                                      "Couldn't read that Word document. Try saving it as a PDF, or paste the text.")
    return "\n".join(parts)


def _extract_pptx(data: bytes) -> str:
    """Plain text from .pptx (regex, entity-safe, capped at _SLIDE_CAP slides). Raises MaterialError on failure."""
    z = _check_zip(data, "slide deck")
    try:
        slide_names = sorted(
            (n for n in z.namelist() if _SLIDE_FILE_RE.match(n)),
            key=lambda n: int(_SLIDE_FILE_RE.match(n).group(1))
        )[:_SLIDE_CAP]
        parts = []
        for name in slide_names:
            xml = _strip_doctype(z.read(name).decode("utf-8", errors="replace"))
            for para in _AP_RE.findall(xml):
                line = _html.unescape("".join(_AT_RE.findall(para)))
                if line.strip():
                    parts.append(line.strip())
    finally:
        z.close()
    if not parts:
        raise materials.MaterialError(400, "unreadable",
                                      "Couldn't read that slide deck. Try exporting as PDF, or paste the text.")
    return "\n".join(parts)


def _extract_xlsx(data: bytes) -> str:
    """Plain text from .xlsx (shared strings + sheet cells, regex). Raises MaterialError on failure."""
    z = _check_zip(data, "spreadsheet")
    try:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            xml = _strip_doctype(z.read("xl/sharedStrings.xml").decode("utf-8", errors="replace"))
            shared = [_html.unescape("".join(_T_IN_SI_RE.findall(si))) for si in _SI_RE.findall(xml)]
        sheet_names = sorted(n for n in z.namelist() if re.match(r"^xl/worksheets/sheet\d+\.xml$", n))
        rows = []
        for name in sheet_names:
            xml = _strip_doctype(z.read(name).decode("utf-8", errors="replace"))
            for m in re.finditer(r"<c\b([^>]*)>(.*?)</c>", xml, re.DOTALL):
                attrs, inner = m.group(1), m.group(2)
                if 't="s"' in attrs or "t='s'" in attrs:
                    v_m = re.search(r"<v>(\d+)</v>", inner)
                    if v_m:
                        idx = int(v_m.group(1))
                        if 0 <= idx < len(shared) and shared[idx].strip():
                            rows.append(shared[idx].strip())
                inline = re.search(r"<is>.*?<t(?:[^>]*)?>([^<]*)</t>.*?</is>", inner, re.DOTALL)
                if inline:
                    v = _html.unescape(inline.group(1)).strip()
                    if v:
                        rows.append(v)
    finally:
        z.close()
    if not rows:
        raise materials.MaterialError(400, "unreadable",
                                      "Couldn't read that spreadsheet. Try saving as PDF or CSV, or paste the text.")
    return "\n".join(rows)


def _extract_odf(data: bytes, label: str) -> str:
    """Plain text from ODT/ODP/ODS (content.xml text nodes, regex). Raises MaterialError on failure."""
    z = _check_zip(data, label)
    try:
        if "content.xml" not in z.namelist():
            raise materials.MaterialError(400, "unreadable",
                                          f"Couldn't read that {label}. Try saving as PDF, or paste the text.")
        xml = _strip_doctype(z.read("content.xml").decode("utf-8", errors="replace"))
    finally:
        z.close()
    parts = []
    for m in re.finditer(r"<text:[ph][^>]*>(.*?)</text:[ph]>", xml, re.DOTALL):
        inner = _HTML_TAG_RE.sub(" ", m.group(1))
        text = _html.unescape(inner).strip()
        if text:
            parts.append(text)
    if not parts:
        raise materials.MaterialError(400, "unreadable",
                                      f"Couldn't read that {label}. Try saving as PDF, or paste the text.")
    return "\n".join(parts)


def _extract_rtf(data: bytes) -> str:
    """Plain text from RTF (strip control words). Raises MaterialError on failure."""
    try:
        text = data.decode("latin-1", errors="replace")
    except Exception:
        raise materials.MaterialError(400, "unreadable",
                                      "Couldn't read that RTF file. Try saving as PDF or plain text.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _RTF_HEX_RE.sub(lambda m: chr(int(m.group(1), 16)), text)
    # Remove {\* ...} ignored-destination groups
    for _ in range(8):
        text = re.sub(r"\{\\[*][^{}]*\}", "", text)
    text = re.sub(r"\\par\b\s*", "\n", text)
    text = re.sub(r"\\pard?\b\s*", "", text)
    text = _RTF_CTRL_RE.sub("", text)
    text = re.sub(r"\\.", "", text)   # remove remaining \X sequences
    text = text.replace("{", "").replace("}", "")
    text = _WS_RE.sub("\n\n", text).strip()
    if not text:
        raise materials.MaterialError(400, "unreadable",
                                      "Couldn't read that RTF file. Try saving as PDF or plain text.")
    return text


def _extract_html(data: bytes) -> str:
    """Plain text from HTML (strip tags). Raises MaterialError on failure."""
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        raise materials.MaterialError(400, "unreadable",
                                      "Couldn't read that HTML file. Try pasting the text instead.")
    text = _HTML_SCRIPT_RE.sub("", text)
    text = _HTML_NL_RE.sub("\n", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _html.unescape(text)
    text = _WS_RE.sub("\n\n", text).strip()
    if not text:
        raise materials.MaterialError(400, "unreadable",
                                      "Couldn't read that HTML file. Try pasting the text instead.")
    return text


def _default_deps() -> dict:
    import os
    import boto3
    from lib import bedrock, db

    s3 = boto3.client("s3", region_name=os.environ.get("REGION", "us-east-1"))

    def converse(system, messages, tools, force_tool, max_tokens):
        return bedrock.converse(bedrock.MODEL_MAIN, system, messages, tools=tools, force_tool=force_tool, max_tokens=max_tokens)

    return {"backend": db, "converse": converse, "claim": db.claim_upload,
            "read": lambda bucket, key, cap: s3.get_object(Bucket=bucket, Key=key)["Body"].read(cap + 1)}


def handler(event, context, deps: dict | None = None):
    deps = deps or _default_deps()
    if event.get("Records"):
        return _handle_s3(event["Records"][0]["s3"], deps)
    sub, cid, mid = event.get("sub"), event.get("courseId"), event.get("matId")
    if not (isinstance(sub, str) and materials.valid_id(cid) and materials.valid_id(mid)):
        return {"ok": False, "reason": "bad event"}
    return process(sub, cid, mid, deps, text=event.get("text") or "")


_ZIP_EXTS = frozenset({"docx", "pptx", "xlsx", "odt", "odp", "ods"})


def _handle_s3(rec: dict, deps: dict) -> dict:
    key = unquote_plus(rec["object"]["key"])
    m = materials.KEY_RE.match(key)
    if not m:
        print("ignoring unexpected key shape")
        return {"ok": False, "reason": "unexpected key"}
    sub, cid, mid, ext = m.groups()
    v = materials.view(sub, deps["backend"])
    item = materials.get_item(v, cid, mid)
    if not item or item.get("s3Key") != key or item.get("ext") != ext:
        return {"ok": False, "reason": "no such material"}
    if not deps["claim"](f"USER#{sub}", f"MAT#{cid}#{mid}"):
        return {"ok": False, "reason": "no pending upload for this material"}
    cap = PDF_CAP if ext == "pdf" else (DOC_CAP if ext in _ZIP_EXTS else materials.MAX_TEXT_FILE_BYTES)
    if int(rec["object"].get("size", 0) or 0) > cap:
        materials.mark_error(v, cid, mid, "That file is too large. PDFs, Word docs and slide decks can be up to 12 MB; text files up to 500 KB.")
        return {"ok": False}
    try:
        data = deps["read"](rec["bucket"]["name"], key, cap)
    except Exception as e:  # noqa: BLE001
        print(f"material read failed: {type(e).__name__}")
        materials.mark_error(v, cid, mid, "I couldn't read that upload. Try again.")
        return {"ok": False}
    return process(sub, cid, mid, deps, data=data, ext=ext)


def _pages(data: bytes):
    try:
        from pypdf import PdfReader
        return min(len(PdfReader(io.BytesIO(data)).pages), pdf.MAX_PAGES)
    except Exception:  # noqa: BLE001
        return None


_LEGACY_EXTS = {"doc": "Word (.doc)", "ppt": "PowerPoint (.ppt)", "xls": "Excel (.xls)"}


def extract(data: bytes, ext: str) -> tuple:
    """(text, pages) from file bytes. Raises materials.MaterialError with a message safe to show."""
    if ext == "pdf":
        try:
            text = pdf.extract_text(data)
        except pdf.PdfError as e:
            raise materials.MaterialError(400, "unreadable", str(e).replace(
                "Upload the syllabus as a PDF, or paste the text.", "Upload a PDF, or paste the text."))
        return text, _pages(data)
    if ext == "docx":
        return _extract_docx(data), None
    if ext == "pptx":
        return _extract_pptx(data), None
    if ext == "xlsx":
        return _extract_xlsx(data), None
    if ext in ("odt", "odp", "ods"):
        label = {"odt": "document", "odp": "presentation", "ods": "spreadsheet"}[ext]
        return _extract_odf(data, label), None
    if ext == "rtf":
        return _extract_rtf(data), None
    if ext == "html":
        return _extract_html(data), None
    if ext in _LEGACY_EXTS:
        raise materials.MaterialError(400, "unsupported_format",
                                      f"This is an older {_LEGACY_EXTS[ext]} file. "
                                      f"Open it and save as PDF, then upload the PDF.")
    # csv, json, txt, md — plain text
    if len(data) > materials.MAX_TEXT_FILE_BYTES:
        raise materials.MaterialError(400, "too_large", "That text file is larger than 500 KB.")
    head = data[:4096]
    if b"\x00" in head or head.startswith((b"%PDF", b"PK\x03\x04", b"\x7fELF", b"MZ")):
        raise materials.MaterialError(400, "unreadable", "That file doesn't look like plain text. Paste the text instead.")
    return data.decode("utf-8", errors="replace"), None


def process(sub: str, cid: str, mid: str, deps: dict, text: str = "", data: bytes | None = None, ext: str | None = None) -> dict:
    v = materials.view(sub, deps["backend"])
    item = materials.get_item(v, cid, mid)
    if not item or item.get("status") != "processing":
        return {"ok": False, "reason": "nothing to process"}
    try:
        pages = None
        if data is not None:
            text, pages = extract(data, ext or item.get("ext") or "txt")
        clean = guard.clean_text(text, materials.MAX_TEXT_PER_MATERIAL + 1)
        truncated = len(clean) > materials.MAX_TEXT_PER_MATERIAL
        clean = clean[:materials.MAX_TEXT_PER_MATERIAL].strip()
        if len(clean) < materials.MIN_TEXT_CHARS:
            raise materials.MaterialError(400, "empty", "I couldn't find readable text in that. If it's a scan, paste the text instead.")
        if materials.class_chars(v, cid, exclude=mid) + len(clean) > materials.MAX_TEXT_PER_CLASS:
            raise materials.MaterialError(409, "class_text_full", "This class has reached its materials limit. Delete one to add another.")
        chunks = materials.chunk_text(clean)
        materials.store_chunks(v, cid, mid, chunks)
        summary = materials.summarize(clean, deps["converse"])
        v.update(f"MAT#{cid}#{mid}", {"status": "ready", "summary": summary, "pages": pages, "chars": len(clean),
                                      "chunkCount": len(chunks), "truncated": truncated, "error": "", "awaitingUpload": False})
        materials.refresh_count(v, cid)
        materials.log_activity(v, cid, f"Read {item.get('title', 'a material')}: {len(chunks)} searchable sections")
        return {"ok": True, "chunks": len(chunks)}
    except materials.MaterialError as e:
        _fail(v, cid, mid, e.message)
    except Exception:  # noqa: BLE001
        print("process_material failed:")
        traceback.print_exc()
        _fail(v, cid, mid, "Something went wrong while reading that. Try again in a minute.")
    return {"ok": False}


def _fail(v, cid: str, mid: str, message: str) -> None:
    for c in v.query(f"CHUNK#{cid}#{mid}#"):   # no half-indexed material
        v.delete(c["sk"])
    materials.mark_error(v, cid, mid, message)
    materials.log_activity(v, cid, message)
