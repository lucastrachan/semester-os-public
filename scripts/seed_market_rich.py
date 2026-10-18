#!/usr/bin/env python3
"""
Rich demo marketplace data (all kinds, all categories, pictures) for UA, Auburn, Georgia Tech and the 12 biggest
seeded campuses. 16-20 listings per campus, every one `demo: true`, seller 'Demo seller', labelled "Demo listing".

Idempotent: deterministic ids (prefix 'seed-market-rich', distinct from seed_popular) and conditional puts.
Never touches tenants. A campus whose tenant record does not exist is skipped (run seed_popular.py first).
Never overwrites anything: an existing listing id is skipped.

Usage:
  python scripts/seed_market_rich.py --dry-run [--assume-empty]
  python scripts/seed_market_rich.py
  python scripts/seed_market_rich.py --only ua.edu,gatech.edu
Images: reads web/public/demo/market/manifest.json (slug -> alt). No manifest, or a slug missing from it: that
listing gets no image. (--images-without-manifest uses built-in alt texts instead.)
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(HERE))

import seed_popular as sp                      # noqa: E402
from lib import market, matching               # noqa: E402

ID_PREFIX = "seed-market-rich"
MAX_PER_CAMPUS = 60
MANIFEST_PATH = ROOT / "web" / "public" / "demo" / "market" / "manifest.json"
IMG_BASE = "/demo/market/"
DEMO_NOTE = "Demo listing: not a real item."

# (tenant id, root domain). Curated campuses have short ids; seeded ones use the root-derived id.
CURATED = [("ua", "ua.edu"), ("auburn", "auburn.edu"), ("gatech", "gatech.edu")]
BIGGEST = ["ucf.edu", "tamu.edu", "ufl.edu", "osu.edu", "utexas.edu", "asu.edu", "umn.edu", "psu.edu",
           "rutgers.edu", "illinois.edu", "msu.edu", "uga.edu"]
TARGETS = CURATED + [(sp.tenant_id_from_root(r), r) for r in BIGGEST]

DEFAULT_ALT = {
    "textbook-mis": "Information systems textbook", "textbook-calc": "Calculus textbook",
    "textbook-chem": "Chemistry textbook", "textbook-econ": "Economics textbook",
    "textbook-stats": "Statistics textbook", "textbook-cs": "Computer science textbook",
    "calculator-graphing": "Graphing calculator", "calculator-scientific": "Scientific calculator",
    "lab-goggles": "Lab safety goggles", "notebook-set": "Set of notebooks", "art-supplies": "Art supplies",
    "mini-fridge": "Mini fridge", "desk-lamp": "Desk lamp", "microwave": "Microwave oven",
    "mattress-topper": "Mattress topper", "bike": "Bicycle", "monitor": "Computer monitor",
    "laptop-stand": "Laptop stand", "usb-c-hub": "USB-C hub", "headphones": "Headphones", "laptop": "Laptop",
    "ticket-football": "Football game ticket", "ticket-basketball": "Basketball game ticket",
    "ticket-concert": "Concert ticket", "tutor-math": "Math tutoring", "tutor-cs": "Computer science tutoring",
    "tutor-business": "Business tutoring", "hoodie": "Hoodie", "jersey": "Game-day jersey",
    "trade-swap": "Two items being swapped",
}


# ── Manifest ──────────────────────────────────────────────────────────────────

def parse_manifest(data) -> dict:
    """{slug: alt} from whatever reasonable manifest shape the Designer wrote. Never raises."""
    out = {}

    def slug_of(s):
        s = str(s or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
        return s[:-4] if s.lower().endswith(".svg") else s

    def alt_of(v):
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return str(v.get("alt") or v.get("altText") or v.get("description") or v.get("title") or "")
        return ""

    try:
        if isinstance(data, dict):
            for key in ("images", "items", "slugs", "illustrations", "assets"):
                if isinstance(data.get(key), (list, dict)):
                    return parse_manifest(data[key])
            for k, v in data.items():
                if isinstance(v, (str, dict)) and (slug_of(k) in DEFAULT_ALT or (isinstance(v, dict) and v.get("alt"))):
                    out[slug_of(k)] = alt_of(v)
        elif isinstance(data, list):
            for e in data:
                if isinstance(e, dict):
                    s = slug_of(e.get("slug") or e.get("id") or e.get("name") or e.get("file") or e.get("url"))
                    if s:
                        out[s] = alt_of(e)
                elif isinstance(e, str):
                    out[slug_of(e)] = ""
    except Exception:
        return {}
    return {s: (a or DEFAULT_ALT.get(s, "")) for s, a in out.items()}


def load_manifest(path: Path = MANIFEST_PATH):
    """{slug: alt} or None when the file is missing/unreadable."""
    try:
        return parse_manifest(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def image_for(slug, manifest):
    if not slug or manifest is None or slug not in manifest:
        return []
    alt = (manifest[slug] or DEFAULT_ALT.get(slug, ""))[:120]
    return [{"url": f"{IMG_BASE}{slug}.svg", "alt": alt}]


# ── Catalog ───────────────────────────────────────────────────────────────────
# Each group is a list of variants; one variant is picked per campus. Variant = dict of create-body fields plus
# `slug` (image) and `price` as (lo, hi).

COND = ["Like new", "Good", "Good", "Acceptable"]


def _b(title, author, edition, isbn, course, slug, price, desc):
    return {"kind": "sell", "category": "books", "title": title, "author": author, "edition": edition, "isbn": isbn,
            "courseCode": course, "slug": slug, "price": price, "desc": desc}


def _book_variant(i):
    t, a, e, isbn, c, p = sp.BOOKS[i]
    return t, a, e, isbn, c, p


_BK = {b[0]: b for b in sp.BOOKS}


def _bk(title, course, slug, desc, price=None):
    t, a, e, isbn, _, p = _BK[title]
    return _b(t, a, e, isbn, course, slug, price or p, desc)


G = {
    "book_mis": [
        _b("Using MIS", "Kroenke & Boyle", "", "", "MIS 405", "textbook-mis", (30, 70),
           "Used it for MIS 405, some highlighting in the first few chapters."),
        _b("Information systems textbook for MIS 430", "", "", "", "MIS 430", "textbook-mis", (25, 60),
           "Covers the whole MIS 430 syllabus, clean pages and no missing chapters."),
    ],
    "book_stem": [
        _bk("Calculus: Early Transcendentals", "MATH 125", "textbook-calc", "Needed it for Calc 1 and 2, answers to odds in the back."),
        _bk("Chemistry: The Central Science", "CHEM 101", "textbook-chem", "Great for gen chem, no torn pages."),
        _bk("OpenIntro Statistics", "STAT 201", "textbook-stats", "Bought it for stats and barely cracked it open."),
        _bk("Chemistry", "CHEM 111", "textbook-chem", "Zumdahl for CHEM 111, a little shelf wear on the cover."),
    ],
    "book_other": [
        _bk("Principles of Economics", "ECON 201", "textbook-econ", "Mankiw for intro econ, I made a few notes in pencil."),
        _bk("Python Crash Course", "CS 101", "textbook-cs", "Perfect for intro programming, works as a beginner reference too."),
        _bk("Introduction to Algorithms", "CS 301", "textbook-cs", "The big algorithms book, hardcover and still solid."),
        _bk("Clean Code", "CS 201", "textbook-cs", "Great read for software classes, spine is still tight."),
    ],
    "book_extra": [
        _bk("The C Programming Language", "CS 211", "textbook-cs", "Classic K&R, small crease on the back cover."),
        _bk("OpenIntro Statistics", "STAT 201", "textbook-stats", "Second copy from a study group, same edition."),
    ],
    "sup_calc": [
        {"kind": "sell", "category": "supplies", "title": "TI-84 Plus CE graphing calculator", "slug": "calculator-graphing",
         "price": (55, 90), "desc": "Got me through two calculus classes, comes with the charging cable."},
        {"kind": "sell", "category": "supplies", "title": "TI-84 Plus graphing calculator", "slug": "calculator-graphing",
         "price": (40, 70), "desc": "Runs on AAA batteries, cover included. Allowed on most exams."},
    ],
    "sup_other": [
        {"kind": "sell", "category": "supplies", "title": "Casio fx-115ES PLUS scientific calculator", "slug": "calculator-scientific",
         "price": (8, 18), "desc": "Solid for chem and physics exams, hard cover included."},
        {"kind": "sell", "category": "supplies", "title": "Lab goggles, splash-proof", "slug": "lab-goggles",
         "price": (4, 10), "desc": "Used for one semester of chemistry lab, wiped down."},
        {"kind": "sell", "category": "supplies", "title": "5-subject notebook set", "slug": "notebook-set",
         "price": (5, 12), "desc": "Three spiral notebooks left, barely written in."},
        {"kind": "sell", "category": "supplies", "title": "Sketching and marker set", "slug": "art-supplies",
         "price": (12, 30), "desc": "Pencils, markers and a sketchpad from my design class."},
    ],
    "dorm_a": [
        {"kind": "sell", "category": "dorm", "title": "Mini fridge, 3.2 cu ft", "slug": "mini-fridge", "price": (40, 80),
         "desc": "Cold and quiet, fits under a lofted bed. Moving out so it has to go."},
        {"kind": "sell", "category": "dorm", "title": "Microwave, 700W", "slug": "microwave", "price": (20, 40),
         "desc": "Compact and works perfectly, I kept it clean."},
    ],
    "dorm_b": [
        {"kind": "sell", "category": "dorm", "title": "LED desk lamp with USB port", "slug": "desk-lamp", "price": (6, 16),
         "desc": "Three brightness levels and a USB port for charging."},
        {"kind": "sell", "category": "dorm", "title": "Twin XL mattress topper, 3 inch", "slug": "mattress-topper",
         "price": (20, 45), "desc": "Made the dorm bed way more comfortable, used one year with a cover."},
    ],
    "dorm_c": [
        {"kind": "sell", "category": "dorm", "title": "Mini fridge with freezer compartment", "slug": "mini-fridge",
         "price": (50, 90), "desc": "Small freezer on top, perfect for frozen meals."},
        {"kind": "sell", "category": "dorm", "title": "Twin XL mattress topper", "slug": "mattress-topper",
         "price": (15, 35), "desc": "Memory foam, a bit flat in one corner but still comfy."},
    ],
    "elec_a": [
        {"kind": "sell", "category": "electronics", "title": "24-inch 1080p monitor", "slug": "monitor", "price": (45, 95),
         "desc": "Great second screen for studying, HDMI cable included."},
        {"kind": "sell", "category": "electronics", "title": "Wireless over-ear headphones", "slug": "headphones",
         "price": (25, 60), "desc": "Good noise isolation for the library, new ear pads."},
    ],
    "elec_b": [
        {"kind": "sell", "category": "electronics", "title": "7-in-1 USB-C hub", "slug": "usb-c-hub", "price": (12, 30),
         "desc": "HDMI, USB-A and an SD reader. Works great with my laptop."},
        {"kind": "sell", "category": "electronics", "title": "Aluminum laptop stand", "slug": "laptop-stand", "price": (10, 25),
         "desc": "Folds flat for the backpack, adjustable height."},
    ],
    "elec_c": [
        {"kind": "sell", "category": "electronics", "title": "13-inch laptop, 8GB RAM, 256GB SSD", "slug": "laptop",
         "price": (180, 380), "desc": "Fine for classes and writing papers. Battery lasts a school day, charger included."},
        {"kind": "sell", "category": "electronics", "title": "Wireless earbuds with charging case", "slug": "headphones",
         "price": (20, 50), "desc": "Case holds a few extra charges, comes with extra tips."},
    ],
    "clothing": [
        {"kind": "sell", "category": "clothing", "title": "Campus hoodie, size M", "slug": "hoodie", "price": (15, 35),
         "desc": "Warm and soft, worn a handful of times."},
        {"kind": "sell", "category": "clothing", "title": "Game-day jersey, size L", "slug": "jersey", "price": (20, 45),
         "desc": "Worn to a few games, still looks great."},
    ],
    "bike": [
        {"kind": "sell", "category": "other", "title": "Commuter bike with lock", "slug": "bike", "price": (70, 160),
         "desc": "Great for getting across campus fast, just tuned up. U-lock included."},
    ],
    "tutor_a": [
        {"kind": "service", "category": "tutoring", "title": "Calculus tutoring", "slug": "tutor-math", "price": (15, 30),
         "tutoring": {"subjects": ["Calculus"], "courseCodes": ["MATH 125"], "availability": "Weekday evenings after 6"},
         "desc": "I got an A in Calc 1 and 2 and love breaking down limits and derivatives."},
        {"kind": "service", "category": "tutoring", "title": "Intro programming tutoring", "slug": "tutor-cs",
         "price": (18, 35),
         "tutoring": {"subjects": ["Programming"], "courseCodes": ["CS 101"], "availability": "Tuesdays and Thursdays, flexible weekends"},
         "desc": "Happy to help with Python basics, debugging and assignment questions."},
    ],
    "tutor_b": [
        {"kind": "service", "category": "tutoring", "title": "MIS and business tutoring", "slug": "tutor-business",
         "price": (20, 40),
         "tutoring": {"subjects": ["Management Information Systems"], "courseCodes": ["MIS 405", "MIS 430"],
                      "availability": "Evenings and Sunday afternoons"},
         "desc": "I took MIS 405 and MIS 430 and can help with projects, SQL and case write-ups."},
        {"kind": "service", "category": "tutoring", "title": "Accounting tutoring", "slug": "tutor-business",
         "price": (18, 35),
         "tutoring": {"subjects": ["Financial Accounting"], "courseCodes": ["ACC 201"],
                      "availability": "Weekday afternoons, library study rooms"},
         "desc": "Journal entries and financial statements explained step by step."},
    ],
    "trade": [
        {"kind": "trade", "category": "dorm", "title": "Trade: desk lamp for a power strip", "slug": "trade-swap",
         "price": 0, "tradeFor": "A surge-protected power strip", "cond": True,
         "desc": "I upgraded my setup and have a spare lamp. Would love a power strip."},
        {"kind": "trade", "category": "books", "title": "Trade: calculus book for a statistics book", "slug": "trade-swap",
         "price": 20, "tradeFor": "An intro statistics textbook", "cash": True, "cond": True, "course": "MATH 125",
         "desc": "Want to swap for a stats text, or I can take cash if you only have the cash."},
    ],
    "free": [
        {"kind": "free", "category": "supplies", "title": "Free: half-used spiral notebooks", "slug": "notebook-set", "price": 0,
         "desc": "Cleaning out my room, take them if you want them."},
        {"kind": "free", "category": "dorm", "title": "Free: old desk lamp, works fine", "slug": "desk-lamp", "price": 0,
         "desc": "Works fine, just not my style anymore. Come grab it."},
    ],
    "wanted_book": [
        {"kind": "wanted", "category": "books", "title": "Looking for MIS 405 textbook", "slug": "textbook-mis",
         "course": "MIS 405", "wprice": (25, 45),
         "desc": "Need the MIS 405 book for this semester. Fair price paid, will pick up on campus."},
        {"kind": "wanted", "category": "books", "title": "Looking for MIS 430 book", "slug": "textbook-mis",
         "course": "MIS 430", "wprice": (25, 45),
         "desc": "Starting MIS 430 soon and hoping to find a used copy."},
    ],
    "wanted_dorm": [
        {"kind": "wanted", "category": "dorm", "title": "Looking for a used mini fridge", "slug": "mini-fridge",
         "wprice": (30, 55), "desc": "Moving into a new room next week and need one."},
    ],
    "wanted_ride": [
        {"kind": "wanted", "category": "rides", "title": "Looking for a ride to the airport", "slug": None,
         "desc": "Heading out for break and splitting gas money if someone is going that way."},
    ],
    "ticket_game": "special",
    "ticket_concert": "special",
}

CORE = ["book_mis", "book_stem", "book_other", "sup_calc", "sup_other", "dorm_a", "elec_a", "clothing", "ticket_game",
        "ticket_concert", "tutor_a", "trade", "free", "wanted_book", "bike", "wanted_ride"]
EXTRAS = ["tutor_b", "dorm_b", "elec_b", "elec_c", "wanted_dorm", "dorm_c", "book_extra", "sup_other2"]


def _h(*p):
    return sp._h(*p)


def _bt(lo, hi, *seed):
    return sp._between(lo, hi, *seed)


def group_choice(root, group):
    if group == "sup_other2":
        pool = G["sup_other"]
        first = _h(root, "sup_other") % len(pool)
        return pool[(first + 1 + (_h(root, group) >> 5) % (len(pool) - 1)) % len(pool)]
    return G[group][_h(root, group) % len(G[group])]


def planned_groups(root: str) -> list:
    n = 16 + _h(root, "count") % 5        # 16..20
    extras = sorted(EXTRAS, key=lambda g: _h(root, "ex", g))
    return (CORE + extras)[:n]


def make_body(root: str, group: str, tenant: dict, now: datetime) -> tuple:
    """(create-request body, image slug)."""
    spots = [str(s) for s in (tenant.get("pickupSpots") or [])]
    spot = spots[_h(root, group, "spot") % len(spots)] if spots else ""
    if group in ("ticket_game", "ticket_concert"):
        if group == "ticket_game":
            football = root in sp.FOOTBALL or root not in sp.BASKETBALL
            sport = "football" if football else "basketball"
            event, venue, slug = f"Home {sport} game", ("Campus stadium" if football else "Campus arena"), f"ticket-{sport}"
            face = _bt(30, 70, root, group, "face")
            title = f"Home {sport} game ticket"
            days = _bt(7, 45, root, group, "days")
        else:
            event, venue, slug = "Campus concert", "Campus arena", "ticket-concert"
            face = _bt(35, 80, root, group, "face")
            title = "Campus concert ticket"
            days = _bt(10, 55, root, group, "days")
        event_at = (now + timedelta(days=days)).replace(hour=19, minute=0, second=0, microsecond=0)
        body = {"kind": "sell", "title": title, "category": "tickets", "price": max(1, face - _bt(0, 12, root, group, "d")),
                "description": f"Can't make it anymore and want it to go to a student fan. Sold at or below face value, "
                               f"transferred in the official app. {DEMO_NOTE}",
                "ticket": {"event": event, "eventAt": event_at.strftime("%Y-%m-%dT%H:%M:%SZ"), "venue": venue,
                           "section": "General admission", "quantity": 2, "faceValue": face,
                           "transferMethod": "official_app"}}
        if spot:
            body["pickupSpot"] = spot
        return body, slug

    v = group_choice(root, group)
    body = {"kind": v["kind"], "title": v["title"], "category": v["category"],
            "description": f"{v['desc']} {DEMO_NOTE}"}
    kind = v["kind"]
    if kind == "wanted":
        lo, hi = v.get("wprice", (0, 0))
        if hi:
            body["price"] = _bt(lo, hi, root, group, "p")
    elif kind == "free":
        body["price"] = 0
    elif kind == "service":
        lo, hi = v["price"]
        body["price"] = _bt(lo, hi, root, group, "p")
    elif kind == "trade":
        body["price"] = v["price"]
    else:
        lo, hi = v["price"]
        body["price"] = _bt(lo, hi, root, group, "p")
    if kind in ("sell", "trade", "free") and v["category"] in market.GOODS:
        body["condition"] = COND[_h(root, group, "c") % 4]
    if v.get("isbn") and matching.to_isbn13(v["isbn"]) == v["isbn"]:
        body["isbn"] = v["isbn"]
    if v.get("author"):
        body["author"] = v["author"]
    if v.get("edition"):
        body["edition"] = v["edition"]
    course = v.get("courseCode") or v.get("course")
    if course:
        body["courseCode"] = course
    if kind == "trade":
        body["tradeFor"] = v["tradeFor"]
        if v.get("cash"):
            body["acceptCash"] = True
    if kind == "service":
        t = v["tutoring"]
        body["tutoring"] = {"subjects": t["subjects"], "courseCodes": t["courseCodes"],
                            "mode": ("both", "in_person", "online")[_h(root, group, "mode") % 3],
                            "availability": t["availability"],
                            "standing": ("junior", "senior", "graduate")[_h(root, group, "st") % 3]}
    elif spot and kind != "wanted":
        body["pickupSpot"] = spot
    return body, v.get("slug")


def listing_id(tenant_id: str, group: str) -> str:
    return hashlib.sha1(f"{ID_PREFIX}|{tenant_id}|{group}".encode()).hexdigest()[:8]


def build_items(tenant: dict, root: str, manifest, now: datetime = None, validate: bool = True) -> list:
    """Items laid out exactly like listings_api.create_listing / seed_popular, plus `demo: true` and images."""
    now = now or datetime.now(timezone.utc)
    api = sp._validator() if validate else None
    # The campus may have a narrower category list (the curated ones do); the validator checks the rest of the
    # rules against the full category set so tickets/tutoring/supplies are accepted for demo content.
    vt = {**tenant, "categories": list(market.CATEGORIES)}
    tid = tenant["id"]
    items = []
    for group in planned_groups(root):
        body, slug = make_body(root, group, tenant, now)
        fields = api.validate_fields(body, vt, partial=False) if api else dict(body)
        created = (now - timedelta(hours=_bt(1, 12 * 24 - 1, tid, group, "age"), minutes=_bt(0, 59, tid, group, "m"))
                   ).strftime("%Y-%m-%dT%H:%M:%SZ")
        lid = listing_id(tid, group)
        item = {
            "pk": f"LISTING#{lid}", "sk": "META", "id": lid, "tenantId": tid, "sellerName": "Demo seller",
            "title": fields["title"], "author": fields.get("author", ""), "edition": fields.get("edition", ""),
            "isbn": fields.get("isbn"), "price": fields.get("price"), "condition": fields.get("condition", ""),
            "category": fields["category"], "courseCode": fields.get("courseCode", ""),
            "description": fields.get("description", ""), "pickupSpot": fields.get("pickupSpot", ""),
            "status": "available", "createdAt": created, "updatedAt": created, "kind": fields["kind"],
            "images": image_for(slug, manifest), "demo": True,
            "gsi1pk": f"TENANT#{tid}#LISTINGS", "gsi1sk": created,
        }
        for k in ("tradeFor", "acceptCash", "ticket", "tutoring"):
            if fields.get(k) not in (None, "", False):
                item[k] = fields[k]
        if item["price"] is None:
            item.pop("price")
        if item["isbn"]:
            item["gsi2pk"], item["gsi2sk"] = f"ISBN#{item['isbn']}", f"{tid}#{lid}"
        else:
            item.pop("isbn")
        items.append(item)
    assert len(items) <= MAX_PER_CAMPUS
    return items


def synthetic_tenant(tid: str, root: str) -> dict:
    colors, reg = sp.load_json("school_colors.json"), sp.load_json("us_schools.json")
    t, _ = sp.build_tenant(root, colors[root], reg.get(root))
    t["id"] = tid
    return t


def run(store, targets, dry_run, manifest, assume_empty=False, now=None, log=print) -> dict:
    now = now or datetime.now(timezone.utc)
    st = {"campuses": 0, "missing_campuses": 0, "listings": 0, "skipped_listings": 0, "with_images": 0}
    for n, (tid, root) in enumerate(targets, 1):
        tenant = synthetic_tenant(tid, root) if assume_empty else store.get("TENANTS", f"T#{tid}")
        if not tenant:
            st["missing_campuses"] += 1
            log(f"[{n}/{len(targets)}] {root}: campus {tid} not found, skipped (run seed_popular.py first)")
            continue
        items = build_items(tenant, root, manifest, now)
        st["campuses"] += 1
        made = 0
        for it in items:
            if dry_run:
                exists = (not assume_empty) and store.get(it["pk"], it["sk"])
                if exists:
                    st["skipped_listings"] += 1
                else:
                    st["listings"] += 1
                    made += 1
                    st["with_images"] += bool(it["images"])
            elif store.put_new(it):
                st["listings"] += 1
                made += 1
                st["with_images"] += bool(it["images"])
            else:
                st["skipped_listings"] += 1
        log(f"[{n}/{len(targets)}] {root}: {'would create' if dry_run else 'created'} {made} of {len(items)} listings")
    return st


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--assume-empty", action="store_true", help="with --dry-run: no AWS at all")
    ap.add_argument("--only", default="", help="comma-separated root domains, e.g. ua.edu,gatech.edu")
    ap.add_argument("--manifest", default=str(MANIFEST_PATH))
    ap.add_argument("--images-without-manifest", action="store_true")
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
    manifest = load_manifest(Path(a.manifest))
    if manifest is None:
        if a.images_without_manifest:
            manifest = dict(DEFAULT_ALT)
            print("No manifest found: using built-in alt texts")
        else:
            print("WARNING: manifest not found, listings get NO images")
    else:
        print(f"Manifest: {len(manifest)} slugs")
    store = sp.EmptyStore() if a.assume_empty else sp.Store(sp.get_table())
    st = run(store, targets, a.dry_run, manifest, a.assume_empty)
    verb = "Would create" if a.dry_run else "Created"
    print(f"\n{verb}: {st['listings']} listings on {st['campuses']} campuses ({st['with_images']} with images)")
    print(f"Skipped: {st['skipped_listings']} existing listings, {st['missing_campuses']} campuses not found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
