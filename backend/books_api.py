"""GET /books/matches (handoff section 7.8, Phase 8): the need-first half of the marketplace.

For every class, each syllabus book is matched to listings in this order:
  1. exact ISBN through GSI2 (your campus first, then visible open campuses)
  2. normalised title/author on the student's own campus
  3. normalised title/author on other campuses that are open to the network (not disabled, not blocked)
Matches are computed at read time (no fan-out writes). Your own listings are never shown as matches;
only available, unflagged listings. Contract: MARKETPLACE_API.md.
"""
from lib import db, limits, matching, util

import listings_api as L

MAX_MATCHES_PER_BOOK = 5
MAX_COURSES = 12


def _price_key(item: dict):
    p = item.get("price")
    return (float(p) if p is not None else 1e9, str(item.get("createdAt", "")))


def _cheapest(items):
    prices = [float(i["price"]) for i in items if i.get("price") is not None]
    if not prices:
        return None
    best = min(prices)
    return int(best) if best == int(best) else round(best, 2)


@L.handled
def get_matches(event: dict, sub: str):
    sdb, profile, tenant = L.viewer(sub)
    limits.check_user(L._table(), sub, "books")
    return util.ok(compute(sub, sdb, tenant))


def compute(sub: str, sdb, tenant: dict) -> dict:
    """The /books/matches payload (also used by the 'For you' strip)."""
    own_id = tenant["id"]
    tenants = L.visible_tenants(tenant)

    textbook_cache = {}   # tenantId -> available listings (fetched once per request, only if a title match is needed)
    isbn_cache = {}       # isbn13 -> available listings

    def candidates(tid):
        if tid not in textbook_cache:
            textbook_cache[tid] = [i for i in L.gsi_query("gsi1", f"TENANT#{tid}#LISTINGS")
                                   if L.shown_to_others(i) and L.is_offer(i) and i.get("sellerSub") != sub]
        return textbook_cache[tid]

    def by_isbn(isbn13):
        if isbn13 not in isbn_cache:
            isbn_cache[isbn13] = [i for i in L.gsi_query("gsi2", f"ISBN#{isbn13}")
                                  if i.get("tenantId") in tenants and L.shown_to_others(i) and L.is_offer(i)
                                  and i.get("sellerSub") != sub]
        return isbn_cache[isbn13]

    courses = sorted(sdb.query("COURSE#"), key=lambda c: c.get("createdAt", ""))[:MAX_COURSES]
    used_tenants = {own_id}
    out_courses = []
    for course in courses:
        books_out = []
        for book in sorted(course.get("books") or [], key=lambda b: not b.get("required", True)):
            if not isinstance(book, dict) or not book.get("title"):
                continue
            ranked, seen = [], set()

            isbn13 = matching.to_isbn13(book.get("isbn"))
            if isbn13:
                for it in by_isbn(isbn13):
                    seen.add(it["id"])
                    own = it.get("tenantId") == own_id
                    ranked.append((0 if own else 0.5, "isbn", 1.0, it))

            for tid in [own_id] + [t for t in tenants if t != own_id]:
                for it in candidates(tid):
                    if it["id"] in seen:
                        continue
                    s = matching.is_title_match(book, it)
                    if s is not None:
                        seen.add(it["id"])
                        ranked.append((1 if tid == own_id else 2, "title", s, it))

            ranked.sort(key=lambda r: (r[0], _price_key(r[3])))
            top = ranked[:MAX_MATCHES_PER_BOOK]
            used_tenants |= {r[3].get("tenantId") for r in top}
            books_out.append({
                "title": L._s(book.get("title"), 200), "author": L._s(book.get("author"), 120),
                "edition": L._s(book.get("edition"), 40), "isbn": book.get("isbn") or "",
                "required": book.get("required") is not False, "notes": L._s(book.get("notes"), 300),
                "matches": [{"matchType": kind, "score": score, "listing": L.view(it, tenants, own_id, sub)}
                            for _, kind, score, it in top],
                "bestPrice": _cheapest([r[3] for r in ranked]),
                "bestOnYourCampus": _cheapest([r[3] for r in ranked if r[3].get("tenantId") == own_id]),
            })
        out_courses.append({
            "courseId": course.get("id"), "courseCode": L._s(course.get("courseCode"), 24),
            "title": L._s(course.get("title"), 160), "color": course.get("color") or "", "books": books_out,
        })

    return {
        "courses": out_courses,
        "campuses": L.campuses_info(tenants, used_tenants, own_id),
        "pickupSpots": [L._s(p, 80) for p in (tenant.get("pickupSpots") or [])[:20]],
    }
