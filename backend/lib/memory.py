"""Class memory: short factual notes the class agent keeps about the student for ONE class. Contract: MEMORY_API.md.

Items: pk USER#{sub}, sk MEM#{courseId}#{noteId}: {id, courseId, text, createdAt, source}. At most 40 notes, 280
characters each, one line. Notes are DATA: they reach a model only through prompt_block (untrusted wrapper), and the
only model-side write is the validated `remember` tool. Text that looks like a link, an email, a phone or ID number,
a secret, markup or an instruction is rejected, not repaired.

All functions take a guard.UserScopedDB whose allow-list includes MEM (and COURSE where noted).
"""
import re
from datetime import datetime, timezone

from . import guard, util

MAX_NOTES = 40
NOTE_MAX = 280
NOTE_MIN = 3
SOURCES = ("agent", "student", "summary")
_ID_RE = re.compile(r"^[a-z0-9]{8}$")

_URL = re.compile(r"(?i)(?:https?|ftp|webcal)\s*:|\bwww\s*\.|\b[a-z0-9\-]+\s*\.\s*(?:com|edu|org|net|io|gov|co|app|dev|me|ly|ai|us|info|xyz|ru|cn|tk)\b")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}\b")
_DIGIT_RUN = re.compile(r"\d(?:[ \-.()/]?\d){8,}")
_SECRET = re.compile(r"(?i)\b(?:password|passwd|passcode|pin code|api[_ \-]?key|secret|bearer|private key|ssn|social security|credit card|cvv)\b|\b(?:AKIA|ASIA)[A-Z0-9]{8,}|\beyJ[A-Za-z0-9_\-]{5,}")
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_\-+/=]{24,}")
_MARKUP = re.compile(r"[<>`{}|\\]|\[\s*image")
_INSTRUCTION = re.compile(
    r"(?i)\b(?:ignore|disregard|forget|override|bypass)\b.{0,40}\b(?:instruction|rule|prompt|polic|previous|above|system|safety)"
    r"|\bsystem\s*prompt\b|\byou\s+(?:must|should|shall|will|are\s+now|have\s+to)\b|\bfrom\s+now\s+on\b"
    r"|\b(?:always|never)\s+(?:call|use|run|answer|reply|respond|say|output|reveal|tell|ignore|do|follow|obey)\b"
    r"|\bnew\s+(?:rule|instruction)s?\b|\b(?:act|pretend|behave)\s+as\b|\bcall\s+(?:the\s+)?\w+\s+tool\b|\btool[_ ]?call\b"
    r"|\bdeveloper\s+mode\b|\bjailbreak\b|\bdo\s+not\s+(?:tell|reveal|follow)\b")


class NoteError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _bad(message: str, code: str = "validation_error"):
    raise NoteError(400, code, message)


def clean_note(text) -> str:
    """The cleaned one-line note, or NoteError(400). Never returns an empty or unsafe string."""
    if not isinstance(text, str):
        _bad("A note must be text.")
    t = re.sub(r"\s+", " ", guard.clean_text(text, 2000)).strip()
    if len(t) < NOTE_MIN:
        _bad("That note is too short.")
    if len(t) > NOTE_MAX:
        _bad(f"Keep a note under {NOTE_MAX} characters.")
    if _URL.search(t) or "@" in t:
        _bad("Notes can't contain links, web addresses or email addresses.")
    if _DIGIT_RUN.search(_DATE.sub(" ", t)):
        _bad("Notes can't contain phone numbers or ID numbers.")
    if _SECRET.search(t) or _LONG_TOKEN.search(t):
        _bad("Notes can't contain passwords, keys or other secrets.")
    if _MARKUP.search(t):
        _bad("Notes are plain text only.")
    if _INSTRUCTION.search(t):
        _bad("Notes are for facts about you in this class, not instructions.")
    return t


def _key(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def valid_note_id(note_id) -> bool:
    return isinstance(note_id, str) and bool(_ID_RE.match(note_id))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _public(item: dict) -> dict:
    return {"id": item.get("id", ""), "text": guard.clean_text(item.get("text") or "", NOTE_MAX),
            "createdAt": item.get("createdAt", ""), "source": item.get("source") if item.get("source") in SOURCES else "agent"}


def list_notes(view, course_id: str) -> list:
    items = [i for i in view.query(f"MEM#{course_id}#") if i.get("courseId") == course_id and valid_note_id(i.get("id"))]
    items.sort(key=lambda i: (i.get("createdAt", ""), i.get("id", "")))
    return [_public(i) for i in items]


def add(view, course_id: str, text, source: str = "agent") -> dict:
    """Validate and store one note. Returns the public note (plus `duplicate: True` when it already existed)."""
    t = clean_note(text)
    existing = list_notes(view, course_id)
    for n in existing:
        if _key(n["text"]) == _key(t):
            return {**n, "duplicate": True}
    if len(existing) >= MAX_NOTES:
        raise NoteError(409, "memory_full", f"Memory is full ({MAX_NOTES} notes). Delete some in the Memory tab.")
    nid = util.short_id()
    item = {"id": nid, "courseId": course_id, "text": t, "createdAt": _now(), "source": source if source in SOURCES else "agent"}
    view.put(f"MEM#{course_id}#{nid}", item)
    return _public(item)


def get(view, course_id: str, note_id: str):
    if not valid_note_id(note_id):
        return None
    item = view.get(f"MEM#{course_id}#{note_id}")
    return item if item and item.get("courseId") == course_id else None


def update(view, course_id: str, note_id: str, text) -> dict:
    item = get(view, course_id, note_id)
    if not item:
        raise NoteError(404, "not_found", "Note not found")
    t = clean_note(text)
    for n in list_notes(view, course_id):
        if n["id"] != note_id and _key(n["text"]) == _key(t):
            raise NoteError(409, "duplicate", "You already have that note.")
    view.update(f"MEM#{course_id}#{note_id}", {"text": t})
    return _public({**item, "text": t})


def delete(view, course_id: str, note_id: str) -> None:
    if not get(view, course_id, note_id):
        raise NoteError(404, "not_found", "Note not found")
    view.delete(f"MEM#{course_id}#{note_id}")


def clear(view, course_id: str) -> int:
    items = view.query(f"MEM#{course_id}#")
    for i in items:
        view.delete(i["sk"])
    return len(items)


def prompt_block(view, course_id: str, nonce: str) -> str:
    """The notes as one untrusted block for the tutor's system prompt."""
    notes = list_notes(view, course_id)
    text = "\n".join(f"- {n['text']}" for n in notes) or "(no notes yet)"
    return guard.wrap_untrusted("student_memory", text, nonce, max_len=MAX_NOTES * (NOTE_MAX + 4))
