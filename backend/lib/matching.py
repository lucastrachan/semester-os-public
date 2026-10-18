"""Phase 8: pure matching helpers for the marketplace (no AWS, no I/O).

  * ISBN: normalise, validate the check digit, convert ISBN-10 to ISBN-13 (the form we index in GSI2).
  * Titles and authors: normalise, ignore edition words, score how likely a listing is the book a syllabus asks for.
  * Search: every typed word must prefix-match a word of the listing.
  * Course codes: "mis405", "MIS-405" and "MIS 405" are the same course.

The match order (exact ISBN through GSI2, then title/author in the student's tenant, then other open tenants)
lives in books_api.py; this module only decides whether and how well two records match.
"""
import re
import unicodedata

TITLE_MATCH_THRESHOLD = 0.75
EDITION_MISMATCH_FACTOR = 0.5
AUTHOR_CONFLICT_FACTOR = 0.6
AUTHOR_AGREE_BONUS = 0.15

_STOP = {"the", "a", "an", "of", "and", "with", "to", "for", "in", "on", "by", "edition", "ed", "et", "al", "ebook",
         "textbook", "paperback", "hardcover"}


# ── Text normalisation ────────────────────────────────────────────────────────

def _fold(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return unicodedata.normalize("NFKC", s).lower().replace("&", " and ")


_ED_PATTERNS = (
    re.compile(r"\b(\d{1,2})\s*(?:st|nd|rd|th)\b"),            # 8th, 17th
    re.compile(r"\b(\d{1,2})e\b"),                              # 17e
    re.compile(r"\bed(?:ition|\.)?\s*(\d{1,2})\b"),             # edition 8, ed. 8
)
_ED_WORDS = re.compile(r"\b(?:\d{1,2}\s*(?:st|nd|rd|th)|\d{1,2}e)\b|\bed(?:ition|\.)?(?:\s*\d{1,2})?\b")


def edition_of(*texts) -> int | None:
    """The edition number found in the first text that has one ("8th ed", "17e", "edition 4")."""
    for t in texts:
        f = _fold(t)
        for p in _ED_PATTERNS:
            m = p.search(f)
            if m:
                return int(m.group(1))
    return None


def title_tokens(title) -> list:
    """Words of a title with punctuation, stop words and edition markers removed."""
    f = _ED_WORDS.sub(" ", _fold(title))
    words = re.findall(r"[a-z0-9]+", f)
    return [w for w in words if w not in _STOP]


def author_tokens(author) -> set:
    """Surnames and names of an author string; initials and 'et al' are ignored."""
    words = re.findall(r"[a-z]+", _fold(author))
    return {w for w in words if len(w) >= 2 and w not in _STOP}


def _dice(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def score(book: dict, listing: dict) -> dict:
    """How well `listing` matches the syllabus `book` (both dicts with title, author, edition).
    Returns {score 0..1, editionMismatch bool}. Meant for titles only; ISBN matches are exact and handled elsewhere.
    """
    tb, tl = set(title_tokens(book.get("title"))), set(title_tokens(listing.get("title")))
    s = _dice(tb, tl)
    if s == 0:
        return {"score": 0.0, "editionMismatch": False}
    ab, al = author_tokens(book.get("author")), author_tokens(listing.get("author"))
    if ab and al:
        common = len(ab & al) / min(len(ab), len(al))
        if common == 0:
            s *= AUTHOR_CONFLICT_FACTOR
        elif common >= 0.5:
            s = min(1.0, s + AUTHOR_AGREE_BONUS * common)
    eb = edition_of(book.get("edition"), book.get("title"))
    el = edition_of(listing.get("edition"), listing.get("title"))
    mismatch = eb is not None and el is not None and eb != el
    if mismatch:
        s *= EDITION_MISMATCH_FACTOR
    return {"score": round(s, 3), "editionMismatch": mismatch}


def is_title_match(book: dict, listing: dict) -> float | None:
    """The score when the listing is an acceptable match for the book, else None."""
    r = score(book, listing)
    return r["score"] if r["score"] >= TITLE_MATCH_THRESHOLD else None


# ── Search ────────────────────────────────────────────────────────────────────

def haystack_tokens(listing: dict) -> list:
    t, tu = listing.get("ticket"), listing.get("tutoring")
    t = t if isinstance(t, dict) else {}
    tu = tu if isinstance(tu, dict) else {}
    cat = listing.get("category")
    parts = [listing.get("title"), listing.get("author"), listing.get("courseCode"), cat, "books" if cat == "textbooks" else None,
             listing.get("tradeFor"), t.get("event"), t.get("venue"),
             " ".join(str(x) for x in tu.get("subjects") or []), " ".join(str(x) for x in tu.get("courseCodes") or [])]
    return re.findall(r"[a-z0-9]+", _fold(" ".join(str(p) for p in parts if p)))


def search_match(q, listing: dict) -> bool:
    """True when every word typed in q is the start of some word in the listing. Empty q matches everything."""
    words = re.findall(r"[a-z0-9]+", _fold(q))
    if not words:
        return True
    hay = haystack_tokens(listing)
    return all(any(h.startswith(w) for h in hay) for w in words)


# ── ISBN ──────────────────────────────────────────────────────────────────────

def normalize_isbn(value) -> str:
    return re.sub(r"[^0-9Xx]", "", str(value or "")).upper()


def _isbn10_ok(s: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dX]", s):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(s))
    return total % 11 == 0


def _isbn13_check(first12: str) -> str:
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(first12))
    return str((10 - total % 10) % 10)


def _isbn13_ok(s: str) -> bool:
    return bool(re.fullmatch(r"97[89]\d{10}", s)) and _isbn13_check(s[:12]) == s[12]


def to_isbn13(value) -> str | None:
    """A valid ISBN-10 or ISBN-13 (hyphens and spaces allowed) as ISBN-13 digits, else None."""
    s = normalize_isbn(value)
    if len(s) == 10 and _isbn10_ok(s):
        core = "978" + s[:9]
        return core + _isbn13_check(core)
    if len(s) == 13 and _isbn13_ok(s):
        return s
    return None


# ── Course codes ──────────────────────────────────────────────────────────────

def normalize_course_code(value) -> str:
    """'mis405', 'MIS-405', 'mis 405' -> 'MIS 405'. Anything else is cleaned, upper-cased and capped."""
    s = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or "")).strip())
    m = re.fullmatch(r"([A-Za-z]{2,6})[\s\-_.]*(\d{2,4}[A-Za-z]?)", s)
    if m:
        return f"{m.group(1).upper()} {m.group(2).upper()}"
    return re.sub(r"[^A-Za-z0-9 \-]", "", s).upper()[:16]
