"""Marketplace v2 read endpoints: 'For you' and tutors for a class. Contract: MARKETPLACE_V2_API.md.

Everything is computed at read time (no fan-out writes). Only available, unflagged, unexpired listings from other
people on the student's campus or visible open campuses are returned. Seller identity is never exposed.
"""
from lib import limits, market, matching, util

import books_api
import listings_api as L

MAX_FOR_YOU = 20
PER_WANTED = 3
MAX_TUTORS = 20
SECTION_CAP = 8
TUTORS_PER_CLASS = 3
_ID_RE = L._ID_RE


def _candidates(sub: str, tenants: dict, own_id: str):
    out = []
    for tid in [own_id] + [t for t in tenants if t != own_id]:
        out.extend(i for i in L.gsi_query("gsi1", f"TENANT#{tid}#LISTINGS")
                   if L.shown_to_others(i) and L.is_offer(i) and i.get("sellerSub") != sub)
    return out


def _wanted_score(w: dict, it: dict):
    """(matchType, score) when listing `it` answers the wanted post `w`, else None."""
    if market.canon_category(w.get("category")) != market.canon_category(it.get("category")):
        return None
    if w.get("price") is not None and it.get("price") is not None and float(it["price"]) > float(w["price"]):
        return None
    if w.get("isbn") and w.get("isbn") == it.get("isbn"):
        return ("isbn", 1.0)
    def titles(x):
        out = [x]
        if market.canon_category(x.get("category")) == "tickets" and (x.get("ticket") or {}).get("event"):
            out.append({**x, "title": x["ticket"]["event"]})
        return out
    s = max([matching.is_title_match(a, b) or 0 for a in titles(w) for b in titles(it)] or [0])
    return ("title", s) if s else None


@L.handled
def for_you(event: dict, sub: str):
    sdb, profile, tenant = L.viewer(sub)
    limits.check_user(L._table(), sub, "books")
    own_id = tenant["id"]
    tenants = L.visible_tenants(tenant)
    items, used = [], {own_id}
    pool = _candidates(sub, tenants, own_id)

    wanted = [i for i in (L.db.get_item(f"LISTING#{p['id']}", "META") for p in sdb.query("LISTING#") if _ID_RE.match(str(p.get("id"))))
              if i and i.get("sellerSub") == sub and market.kind_of(i) == "wanted" and i.get("status", "available") == "available"]
    if wanted:
        for w in wanted:
            found = []
            for it in pool:
                m = _wanted_score(w, it)
                if m:
                    found.append((0 if it.get("tenantId") == own_id else 1, -m[1], float(it.get("price") or 0), m, it))
            found.sort(key=lambda r: r[:3])
            for _, _, _, (kind, score), it in found[:PER_WANTED]:
                used.add(it.get("tenantId"))
                items.append({"reason": "wanted", "wantedId": w["id"], "wantedTitle": L._s(w.get("title"), 160),
                              "courseCode": None, "bookTitle": None, "matchType": kind, "score": round(score, 2),
                              "listing": L.view(it, tenants, own_id, sub)})

    books = books_api.compute(sub, sdb, tenant)
    for course in books["courses"]:
        for book in course["books"]:
            if book["required"] and book["matches"]:
                top = book["matches"][0]
                used.add(top["listing"]["campus"]["id"])
                items.append({"reason": "class_book", "wantedId": None, "wantedTitle": None, "courseCode": course["courseCode"],
                              "bookTitle": book["title"], "matchType": top["matchType"], "score": top["score"], "listing": top["listing"]})
    items = items[:MAX_FOR_YOU]
    courses = sorted((c for c in sdb.query("COURSE#") if not c.get("archived")), key=lambda c: c.get("createdAt", ""))[:books_api.MAX_COURSES]
    sections = _sections(sub, tenants, own_id, courses, books, pool)
    shown = {i["listing"]["campus"]["id"] for i in items} | {e["listing"]["campus"]["id"] for sec in sections for e in sec["listings"]} | {own_id}
    return util.ok({"items": items, "sections": sections, "campuses": L.campuses_info(tenants, shown, own_id)})


# ── Recommended for your classes (sections) ───────────────────────────────────

# Deterministic suggestions by class type: (department prefixes, title keywords, category, listing-title words or None, label)
_SUPPLY_RULES = (
    ({"MIS", "CS", "CSE", "IT", "CIS", "ECE", "EE", "INFO", "DS"}, {"computer", "information", "programming", "software", "data", "network"},
     "electronics", None, "electronics"),
    ({"MATH", "STAT", "ENGR", "ME", "CE", "PHYS", "ECON", "MAT"}, {"calculus", "statistics", "algebra", "engineering", "physics", "econometrics"},
     "supplies", {"calculator", "graphing", "ti"}, "calculators"),
    ({"CHEM", "BIO", "BSC", "PHYS", "GEOL"}, {"chemistry", "biology", "lab", "laboratory", "anatomy", "physiology"},
     "supplies", {"lab", "goggles", "coat", "safety", "dissection", "notebook"}, "lab supplies"),
    ({"ART", "ARH", "DSN", "DES"}, {"art", "drawing", "painting", "design", "sculpture", "studio"},
     "supplies", {"paint", "sketch", "brush", "drawing", "pencil", "canvas", "art", "easel", "marker"}, "art supplies"),
)


def _term_start(now=None) -> bool:
    """Start of a term (August, September, January, February): the time students need dorm basics."""
    from datetime import datetime, timezone
    return (now or datetime.now(timezone.utc)).month in (8, 9, 1, 2)


def _dept(code: str) -> str:
    return str(code or "").split(" ")[0].upper()


def _title_words(it: dict) -> set:
    return set(matching.title_tokens(it.get("title"))) | set(matching.title_tokens(it.get("tradeFor")))


def _sections(sub: str, tenants: dict, own_id: str, courses: list, books: dict, pool: list) -> list:
    own_pool = [i for i in pool if i.get("tenantId") == own_id]
    view = lambda it: L.view(it, tenants, own_id, sub)
    seen: set = set()
    sections = []

    def entry(it, reason, **extra):
        seen.add(it["id"])
        return {"reason": reason, "listing": view(it), **extra}

    def add(sec_id, title, reason, entries, **extra):
        if entries:
            sections.append({"id": sec_id, "title": title, "reason": reason, "listings": entries[:SECTION_CAP], **extra})

    # 1. Books you need (required first, then recommended), campus first and cheapest first (the match order already is)
    book_entries, ids = [], set()
    for want_required in (True, False):
        for course in books["courses"]:
            for book in course["books"]:
                if book["required"] != want_required or not book["matches"]:
                    continue
                top = book["matches"][0]["listing"]
                if top["id"] in ids:
                    continue
                ids.add(top["id"])
                code = course["courseCode"] or course["title"]
                book_entries.append({"reason": f"{'Required' if want_required else 'Recommended'} for {code}", "bookTitle": book["title"],
                                     "courseCode": course["courseCode"], "listing": top})
    for e in book_entries[:SECTION_CAP]:
        seen.add(e["listing"]["id"])
    add("books", "Books you need", "From your class syllabi", book_entries)

    # 2. Tutors for your classes (top 3 per class, campus first)
    tutor_entries = []
    for course in courses:
        code = matching.normalize_course_code(course.get("courseCode"))
        if not code:
            continue
        mine = [i for i in pool if market.kind_of(i) == "service" and market.canon_category(i.get("category")) == "tutoring"
                and i["id"] not in seen
                and code in ({matching.normalize_course_code(c) for c in ((i.get("tutoring") or {}).get("courseCodes") or [])}
                             | {matching.normalize_course_code(i.get("courseCode"))})]
        mine.sort(key=lambda i: (i.get("tenantId") != own_id, float(i.get("price") or 0), str(i.get("createdAt", ""))))
        tutor_entries += [entry(i, f"Tutor for {code}", courseCode=code) for i in mine[:TUTORS_PER_CLASS]]
    add("tutors", "Tutors for your classes", "Students offering help with your classes", tutor_entries)

    # 3. Classmates selling: listings tagged with one of the student's course codes on the same campus
    codes = {matching.normalize_course_code(c.get("courseCode")) for c in courses if c.get("courseCode")}
    mates = []
    for it in sorted(own_pool, key=lambda i: str(i.get("createdAt", "")), reverse=True):
        code = matching.normalize_course_code(it.get("courseCode"))
        if code in codes and it["id"] not in seen and market.kind_of(it) != "service":
            mates.append(entry(it, f"Tagged for {code} on your campus", courseCode=code))
    add("classmates", "Classmates selling", "Listed on your campus for your classes", mates)

    # 4. Supplies by class type (suggestions)
    sugg, rules = [], []
    for course in courses:
        code = matching.normalize_course_code(course.get("courseCode"))
        words = set(matching.title_tokens(course.get("title")))
        for depts, kws, cat, title_words, label in _SUPPLY_RULES:
            if _dept(code) in depts or words & kws:
                rules.append((code, cat, title_words, label))
    if _term_start():
        rules.append(("", "dorm", None, "dorm basics"))
    done = set()
    for code, cat, title_words, label in rules:
        if (cat, label) in done:
            continue
        done.add((cat, label))
        for it in sorted(own_pool, key=lambda i: (float(i.get("price") or 0), str(i.get("createdAt", "")))):
            if it["id"] in seen or market.kind_of(it) == "service" or market.canon_category(it.get("category")) != cat:
                continue
            if title_words and not (_title_words(it) & title_words):
                continue
            reason = f"Suggested for {code}: {label}" if code else f"Suggested at the start of term: {label}"
            sugg.append(entry(it, reason, suggestion=True))
            if len(sugg) >= SECTION_CAP * 2:
                break
    add("supplies", "Supplies for your classes", "Suggestions based on the kind of classes you take", sugg, suggestion=True)

    # 5. Ticket and trade highlights on the student's campus
    hl = []
    for it in sorted(own_pool, key=lambda i: str(i.get("createdAt", "")), reverse=True):
        if it["id"] in seen:
            continue
        if market.canon_category(it.get("category")) == "tickets":
            hl.append(entry(it, "Tickets on your campus"))
        elif market.kind_of(it) == "trade":
            hl.append(entry(it, "Open to a trade on your campus"))
    add("highlights", "Tickets and trades", "Fresh on your campus", hl)
    return sections


@L.handled
def tutors_for_course(event: dict, sub: str, course_id: str):
    sdb, profile, tenant = L.viewer(sub)
    if not _ID_RE.match(course_id or ""):
        raise L._Bad(404, "not_found", "Class not found")
    course = sdb.get(f"COURSE#{course_id}")
    if not course:
        raise L._Bad(404, "not_found", "Class not found")
    code = matching.normalize_course_code(course.get("courseCode"))
    own_id = tenant["id"]
    tenants = L.visible_tenants(tenant)
    found = []
    if code:
        for it in _candidates(sub, tenants, own_id):
            if market.kind_of(it) != "service" or market.canon_category(it.get("category")) != "tutoring":
                continue
            tags = {matching.normalize_course_code(c) for c in ((it.get("tutoring") or {}).get("courseCodes") or [])}
            tags.add(matching.normalize_course_code(it.get("courseCode")))
            if code in tags:
                found.append(it)
    found.sort(key=lambda i: (i.get("tenantId") != own_id, float(i.get("price") or 0), str(i.get("createdAt", ""))))
    found = found[:MAX_TUTORS]
    return util.ok({"course": {"id": course.get("id"), "courseCode": L._s(course.get("courseCode"), 24), "title": L._s(course.get("title"), 160)},
                    "tutors": [L.view(i, tenants, own_id, sub) for i in found],
                    "campuses": L.campuses_info(tenants, {i.get("tenantId") for i in found} | {own_id}, own_id)})
