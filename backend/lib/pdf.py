"""PDF -> text with pure-Python pypdf (vendored in backend/vendor; installed by scripts/deploy.py).

The 100-requests-per-minute models reject PDF document blocks, so text is extracted here first.
A scanned PDF (little or no text layer) returns very little; the caller then falls back to a model
that accepts PDF input (see extract.extract_syllabus_pdf).
"""
import io
import os
import sys

_VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_PAGES = 40
MIN_USEFUL_CHARS = 200  # below this the PDF is probably scanned images


class PdfError(Exception):
    """Message is safe to show to the student."""


def extract_text(data: bytes) -> str:
    if len(data) > MAX_PDF_BYTES:
        raise PdfError("That PDF is larger than 10 MB. Try a smaller file or paste the text instead.")
    if not data.startswith(b"%PDF"):
        raise PdfError("That file isn't a PDF. Upload the syllabus as a PDF, or paste the text.")
    from pypdf import PdfReader  # imported late so a missing vendor dir fails with a clear error, not at import
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfError("That PDF is password protected. Remove the password or paste the text instead.")
        pages = reader.pages[:MAX_PAGES]
        return "\n".join((p.extract_text() or "") for p in pages).strip()
    except PdfError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError):
        raise PdfError("I couldn't read that PDF. Try re-exporting it, or paste the text instead.")
