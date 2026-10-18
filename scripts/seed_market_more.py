#!/usr/bin/env python3
"""
Lots more demo TICKET and TUTORING listings for the 15 rich campuses plus 30 more big ones.

Per campus: 8-14 ticket listings for sale (+2 wanted), 10-16 tutors (+3 wanted tutoring requests).
Every item is demo: true, seller 'Demo seller', labelled "Demo listing", validated by the API's own
validate_fields, deterministic id (prefix 'seed-market-more'), conditional put (re-runs create nothing).
Never touches tenants; a campus with no tenant record is skipped. The 60-listing campus cap is counted against
the demo listings other seed scripts place there (a deterministic estimate); extras that would exceed it are dropped.

Usage:
  python scripts/seed_market_more.py --dry-run [--assume-empty]
  python scripts/seed_market_more.py
  python scripts/seed_market_more.py --only ua.edu,lsu.edu
"""
import argparse
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
sys.path.insert(0, str(HERE))

import seed_market_rich as mr          # noqa: E402
import seed_popular as sp              # noqa: E402
from lib import market                 # noqa: E402

ID_PREFIX = "seed-market-more"
MAX_PER_CAMPUS = 60
DEMO_NOTE = mr.DEMO_NOTE

OTHERS = ["umich.edu", "wisc.edu", "purdue.edu", "iu.edu", "uiowa.edu", "ku.edu", "ou.edu", "lsu.edu", "fsu.edu",
          "clemson.edu", "uky.edu", "utk.edu", "sc.edu", "unc.edu", "ncsu.edu", "vt.edu", "virginia.edu", "umd.edu",
          "pitt.edu", "uc.edu", "uh.edu", "usf.edu", "fiu.edu", "ucla.edu", "usc.edu", "uw.edu", "unl.edu",
          "iastate.edu", "byu.edu", "baylor.edu"]
TARGETS = mr.TARGETS + [(sp.tenant_id_from_root(r), r) for r in OTHERS]


# ── Tickets ───────────────────────────────────────────────────────────────────
# key, event label, venue, image slug, face range
EVENTS = [
    ("football", "Home football game", "Campus stadium", "ticket-football", (30, 80)),
    ("mbb", "Home men's basketball game", "Campus arena", "ticket-basketball", (20, 60)),
    ("wbb", "Home women's basketball game", "Campus arena", "ticket-basketball", (10, 30)),
    ("volleyball", "Home volleyball match", "Campus arena", "fallback-tickets", (8, 20)),
    ("baseball", "Home baseball game", "Campus ballpark", "fallback-tickets", (8, 18)),
    ("softball", "Home softball game", "Campus softball field", "fallback-tickets", (5, 12)),
    ("soccer", "Home soccer match", "Campus soccer stadium", "fallback-tickets", (8, 18)),
    ("gym", "Home gymnastics meet", "Campus arena", "fallback-tickets", (10, 25)),
    ("concert", "Campus concert", "Campus arena", "ticket-concert", (35, 90)),
    ("festival", "Campus music festival", "Campus lawn", "ticket-concert", (30, 75)),
    ("comedy", "Comedy night", "Student center", "ticket-concert", (10, 25)),
    ("theatre", "Theatre showcase", "Campus theatre", "ticket-concert", (8, 20)),
    ("dance", "Dance showcase", "Student center", "ticket-concert", (8, 20)),
    ("homecoming", "Homecoming concert", "Campus arena", "ticket-concert", (25, 60)),
    ("movie", "Movie night", "Student center", "ticket-concert", (3, 8)),
]
SECTIONS = ["General admission", "Student section", "Lower level", "Upper level", "Floor"]
TICKET_DESC = [
    "Can't make it anymore and want it to go to a student fan. At or below face value, sent through the official app.",
    "Plans changed, so these are looking for a good home. Face value or less, transferred in the official app.",
    "Won't be able to go that night. Selling at or under face value through the official app.",
]


def _h(*p):
    return sp._h(*p)


def _bt(lo, hi, *seed):
    return sp._between(lo, hi, *seed)


def _events_for(root):
    ev = list(EVENTS)
    if root not in sp.FOOTBALL:
        ev = [e for e in ev if e[0] != "football"]
    return sorted(ev, key=lambda e: _h(root, "ev", e[0]))


def ticket_bodies(root, tenant, now):
    """[(key, body, slug)] sale listings then 2 wanted posts."""
    spots = [str(s) for s in (tenant.get("pickupSpots") or [])]
    evs = _events_for(root)
    n_sell = min(8 + _h(root, "tn") % 7, len(evs))
    out = []
    for key, label, venue, slug, (flo, fhi) in evs[:n_sell]:
        face = _bt(flo, fhi, root, key, "face")
        when = (now + timedelta(days=_bt(3, 58, root, key, "days"))).replace(
            hour=(18, 19, 20)[_h(root, key, "hr") % 3], minute=0, second=0, microsecond=0)
        title = f"{label} ticket" if not label.startswith("Campus") else f"{label} ticket"
        body = {"kind": "sell", "title": title, "category": "tickets",
                "price": max(1, face - _bt(0, max(1, face // 5), root, key, "disc")),
                "description": f"{TICKET_DESC[_h(root, key, 'd') % 3]} {DEMO_NOTE}",
                "ticket": {"event": label, "eventAt": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "venue": venue,
                           "section": SECTIONS[_h(root, key, "sec") % len(SECTIONS)],
                           "quantity": 1 + _h(root, key, "q") % 4, "faceValue": face, "transferMethod": "official_app"}}
        if _h(root, key, "row") % 2:
            body["ticket"]["section"] = f"{body['ticket']['section']}, row {_bt(2, 30, root, key, 'r')}"[:40]
        if spots:
            body["pickupSpot"] = spots[_h(root, key, "spot") % len(spots)]
        out.append((f"t:{key}", body, slug))
    wants = [e for e in evs if e[0] not in {k for k, *_ in evs[:n_sell]}] or evs[-2:]
    wants = sorted(evs, key=lambda e: _h(root, "want", e[0]))[:2]
    for key, label, venue, slug, (flo, fhi) in wants:
        when = (now + timedelta(days=_bt(5, 55, root, key, "wdays"))).replace(hour=19, minute=0, second=0, microsecond=0)
        out.append((f"w:{key}", {
            "kind": "wanted", "title": f"Looking for {label.lower()} tickets", "category": "tickets",
            "price": _bt(max(flo, 5), max(fhi, 6), root, key, "wp"),
            "description": f"Hoping to find a student selling at or below face value, transfer through the official app. {DEMO_NOTE}",
            "ticket": {"event": label, "eventAt": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "venue": venue,
                       "quantity": 1 + _h(root, key, "wq") % 2, "transferMethod": "official_app"}}, slug))
    return out


# ── Tutoring ──────────────────────────────────────────────────────────────────
# course, related codes, subject, department, focus, slug, rate range
TUTORS = [
    ("MATH 125", [], "Calculus I", "math", "limits, derivatives and the chain rule", "tutor-math", (15, 30)),
    ("MATH 126", ["MATH 125"], "Calculus II", "math", "integration techniques and series", "tutor-math", (15, 32)),
    ("MATH 227", [], "Multivariable Calculus", "math", "partial derivatives and multiple integrals", "tutor-math", (18, 35)),
    ("STAT 200", [], "Statistics", "stats", "hypothesis tests and regression", "tutor-math", (15, 30)),
    ("CS 101", [], "Intro Programming", "computer science", "Python basics and debugging", "tutor-cs", (15, 35)),
    ("CS 201", ["CS 101"], "Data Structures", "computer science", "linked lists, trees and Big-O", "tutor-cs", (20, 40)),
    ("MIS 205", [], "Business Information Systems", "MIS", "Excel, databases and course projects", "tutor-business", (15, 30)),
    ("MIS 301", [], "Systems Analysis", "MIS", "process diagrams and requirements write-ups", "tutor-business", (18, 35)),
    ("MIS 405", ["MIS 301"], "Management Information Systems", "MIS", "SQL, data modeling and case write-ups", "tutor-business", (20, 40)),
    ("MIS 430", [], "Database Management", "MIS", "normalization, joins and ER diagrams", "tutor-business", (20, 42)),
    ("MIS 460", [], "Systems Development", "MIS", "project planning and design documents", "tutor-business", (20, 45)),
    ("ACC 201", [], "Financial Accounting", "accounting", "journal entries and financial statements", "tutor-business", (18, 35)),
    ("ACC 202", ["ACC 201"], "Managerial Accounting", "accounting", "cost behavior and budgeting", "tutor-business", (18, 35)),
    ("ECON 110", [], "Microeconomics", "economics", "supply and demand and elasticity", "tutor-business", (15, 30)),
    ("ECON 111", [], "Macroeconomics", "economics", "GDP, inflation and monetary policy", "tutor-business", (15, 30)),
    ("CHEM 101", [], "General Chemistry", "chemistry", "stoichiometry and the periodic table", "fallback-tutoring", (15, 32)),
    ("CHEM 102", ["CHEM 101"], "General Chemistry II", "chemistry", "equilibrium and acids and bases", "fallback-tutoring", (15, 32)),
    ("PHYS 101", [], "Physics I", "physics", "kinematics and Newton's laws", "tutor-math", (18, 38)),
    ("PHYS 102", ["PHYS 101"], "Physics II", "physics", "circuits and electromagnetism", "tutor-math", (18, 38)),
    ("BIO 101", [], "Biology", "biology", "cell biology and genetics", "fallback-tutoring", (12, 28)),
    ("ENG 101", [], "English Composition", "English", "thesis statements and revising essays", "fallback-tutoring", (12, 25)),
    ("ENG 102", ["ENG 101"], "Writing and Research", "English", "research papers and citations", "fallback-tutoring", (12, 25)),
    ("EN 210", [], "Literature", "English", "close reading and essay structure", "fallback-tutoring", (12, 28)),
    ("SPAN 101", [], "Beginning Spanish", "Spanish", "conversation practice and verb conjugation", "fallback-tutoring", (12, 25)),
    ("PSYC 101", [], "Intro Psychology", "psychology", "exam prep and key study terms", "fallback-tutoring", (12, 25)),
    ("MGT 300", [], "Management", "management", "case studies and team projects", "tutor-business", (15, 30)),
    ("MGT 488", [], "Strategic Management", "management", "strategy frameworks and case analysis", "tutor-business", (20, 40)),
    ("FIN 301", [], "Corporate Finance", "finance", "time value of money and valuation", "tutor-business", (20, 45)),
    ("MKT 300", [], "Marketing", "marketing", "market research and campaign write-ups", "tutor-business", (15, 30)),
]
UA_REQUIRED = ["MIS 405", "MIS 430", "MIS 460", "MGT 488", "EN 210", "ACC 201"]
BIOS = [
    "I took {c} last year and finished with an A. I can help with {f}.",
    "Upper-level {d} student, happy to go over {f} before exams.",
    "I like explaining {f} in plain language and working practice problems together.",
    "Got through {c} with lots of study-group practice. I can help with {f} and check your homework.",
]
AVAIL = ["Weeknights 6-9 PM, library 2nd floor", "Mondays and Wednesdays after 4 PM", "Weekends 1-5 PM, student center",
         "Tuesdays and Thursdays 5-8 PM", "Sunday afternoons and weeknights after 7", "Flexible, message me a time",
         "Weekday mornings before 11", "Evenings by video call"]
STANDING = ("sophomore", "junior", "senior", "graduate")


def tutor_bodies(root, tenant):
    spots = [str(s) for s in (tenant.get("pickupSpots") or [])]
    codes = {t[0]: t for t in TUTORS}
    order = sorted(TUTORS, key=lambda t: _h(root, "tu", t[0]))
    n = 10 + _h(root, "tun") % 7
    chosen = []
    if root == "ua.edu":
        chosen = [codes[c] for c in UA_REQUIRED]
    for t in order:
        if len(chosen) >= n:
            break
        if t not in chosen:
            chosen.append(t)
    out = []
    for course, related, subject, dept, focus, slug, (lo, hi) in chosen:
        mode = ("in_person", "online", "both")[_h(root, course, "mode") % 3]
        free = _h(root, course, "free") % 8 == 0
        price = 0 if free else _bt(lo, hi, root, course, "rate")
        body = {"kind": "service", "category": "tutoring",
                "title": (f"Free peer help: {course}" if free else f"{course} tutoring ({subject})")[:160],
                "price": price,
                "description": BIOS[_h(root, course, "bio") % 4].format(c=course, d=dept, f=focus) + f" {DEMO_NOTE}",
                "tutoring": {"subjects": [subject], "courseCodes": [course] + related, "mode": mode,
                             "availability": AVAIL[_h(root, course, "av") % len(AVAIL)],
                             "standing": STANDING[_h(root, course, "st") % 4]}}
        if spots and mode != "online":
            body["pickupSpot"] = spots[_h(root, course, "spot") % len(spots)]
        out.append((f"u:{course}", body, slug))
    wants = sorted(TUTORS, key=lambda t: _h(root, "tw", t[0]))
    picked = []
    for t in wants:
        if t[0] not in {c[0] for c in chosen} and len(picked) < 3:
            picked.append(t)
    if root == "ua.edu":
        picked = [codes["MIS 405"], codes["ACC 202"], codes["CS 101"]]
    for course, related, subject, dept, focus, slug, (lo, hi) in picked:
        out.append((f"x:{course}", {
            "kind": "wanted", "category": "tutoring", "title": f"Need a {course} tutor", "price": _bt(lo, hi, root, course, "wr"),
            "description": f"Looking for someone who has taken {course} and can help with {focus}. {DEMO_NOTE}",
            "tutoring": {"subjects": [subject], "courseCodes": [course], "mode": "both",
                         "availability": "Evenings, flexible", "standing": ""}}, slug))
    return out


# ── Items ─────────────────────────────────────────────────────────────────────

def listing_id(tid, key):
    return hashlib.sha1(f"{ID_PREFIX}|{tid}|{key}".encode()).hexdigest()[:8]


def existing_estimate(root, tid):
    """Demo listings other seed scripts place on this campus (upper bound, deterministic)."""
    n = len(mr.planned_groups(root)) if root in {r for _, r in mr.TARGETS} else 0
    if tid not in {t for t, _ in mr.CURATED}:
        n += len(sp.listing_specs(root))
    return n


def build_items(tenant, root, manifest, now=None, validate=True):
    now = now or datetime.now(timezone.utc)
    api = sp._validator() if validate else None
    vt = {**tenant, "categories": list(market.CATEGORIES)}
    tid = tenant["id"]
    plan = ticket_bodies(root, tenant, now) + tutor_bodies(root, tenant)
    sells = [p for p in plan if p[0][0] in "tu"]
    wants = [p for p in plan if p[0][0] in "wx"]
    ordered = sells + wants
    budget = MAX_PER_CAMPUS - existing_estimate(root, tid)
    dropped = max(0, len(ordered) - max(budget, 0))
    ordered = ordered[:max(budget, 0)]
    items = []
    for key, body, slug in ordered:
        fields = api.validate_fields(body, vt, partial=False) if api else dict(body)
        created = (now - timedelta(hours=_bt(1, 12 * 24 - 1, tid, key, "age"), minutes=_bt(0, 59, tid, key, "m"))
                   ).strftime("%Y-%m-%dT%H:%M:%SZ")
        lid = listing_id(tid, key)
        item = {
            "pk": f"LISTING#{lid}", "sk": "META", "id": lid, "tenantId": tid, "sellerName": "Demo seller",
            "title": fields["title"], "author": fields.get("author", ""), "edition": fields.get("edition", ""),
            "isbn": fields.get("isbn"), "price": fields.get("price"), "condition": fields.get("condition", ""),
            "category": fields["category"], "courseCode": fields.get("courseCode", ""),
            "description": fields.get("description", ""), "pickupSpot": fields.get("pickupSpot", ""),
            "status": "available", "createdAt": created, "updatedAt": created, "kind": fields["kind"],
            "images": mr.image_for(slug, manifest), "demo": True,
            "gsi1pk": f"TENANT#{tid}#LISTINGS", "gsi1sk": created,
        }
        for k in ("tradeFor", "acceptCash", "ticket", "tutoring"):
            if fields.get(k) not in (None, "", False):
                item[k] = fields[k]
        if item["price"] is None:
            item.pop("price")
        item.pop("isbn")
        items.append(item)
    return items, dropped


def run(store, targets, dry_run, manifest, assume_empty=False, now=None, log=print):
    now = now or datetime.now(timezone.utc)
    st = {"campuses": 0, "missing_campuses": 0, "tickets": 0, "tutoring": 0, "skipped": 0, "dropped_by_cap": 0}
    for n, (tid, root) in enumerate(targets, 1):
        tenant = mr.synthetic_tenant(tid, root) if assume_empty else store.get("TENANTS", f"T#{tid}")
        if not tenant:
            st["missing_campuses"] += 1
            log(f"[{n}/{len(targets)}] {root}: campus {tid} not found, skipped")
            continue
        items, dropped = build_items(tenant, root, manifest, now)
        st["campuses"] += 1
        st["dropped_by_cap"] += dropped
        made = 0
        for it in items:
            if dry_run:
                exists = (not assume_empty) and store.get(it["pk"], it["sk"])
            else:
                exists = not store.put_new(it)
            if exists:
                st["skipped"] += 1
            else:
                made += 1
                st["tickets" if it["category"] == "tickets" else "tutoring"] += 1
        log(f"[{n}/{len(targets)}] {root}: {'would create' if dry_run else 'created'} {made} of {len(items)}")
    return st


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--assume-empty", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--manifest", default=str(mr.MANIFEST_PATH))
    a = ap.parse_args(argv)
    if a.assume_empty and not a.dry_run:
        print("ERROR: --assume-empty only works with --dry-run")
        return 2
    targets = TARGETS
    if a.only:
        want = [x.strip().lower() for x in a.only.split(",") if x.strip()]
        bad = [w for w in want if w not in {r for _, r in TARGETS}]
        if bad:
            print(f"ERROR: not a target campus: {', '.join(bad)}")
            return 2
        targets = [t for t in TARGETS if t[1] in want]
    manifest = mr.load_manifest(Path(a.manifest))
    print(f"Manifest: {len(manifest)} slugs" if manifest is not None else "WARNING: manifest not found, NO images")
    store = sp.EmptyStore() if a.assume_empty else sp.Store(sp.get_table())
    st = run(store, targets, a.dry_run, manifest, a.assume_empty)
    verb = "Would create" if a.dry_run else "Created"
    print(f"\n{verb}: {st['tickets']} ticket + {st['tutoring']} tutoring listings on {st['campuses']} campuses")
    print(f"Skipped: {st['skipped']} existing, {st['missing_campuses']} campuses not found, {st['dropped_by_cap']} dropped by the cap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
