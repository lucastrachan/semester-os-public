#!/usr/bin/env python3
"""
Seed a campus for every popular school in backend/data/school_colors.json, plus a few clearly
labelled demo marketplace listings per campus.

Idempotent and non-destructive:
  * a campus (TENANTS/T#<id> + DOMAIN#<root>/MAP) is written in ONE transaction, both items conditional on
    attribute_not_exists(pk). Anything that already exists (UA, Auburn, Georgia Tech, auto-created campuses)
    is skipped and never modified.
  * demo listings use deterministic ids and a conditional put, so a re-run creates nothing new and never
    resurrects a listing someone sold or removed. They are only written for campuses this script seeded
    (`seeded: true`), never for pre-existing campuses.

Usage:
  python scripts/seed_popular.py --dry-run            # reads the table, prints counts, writes nothing
  python scripts/seed_popular.py                      # does the writes
  python scripts/seed_popular.py --only ua.edu,lsu.edu
  python scripts/seed_popular.py --dry-run --assume-empty   # no AWS at all (pretend the table is empty)
Reads TABLE_NAME from env or cdk-outputs.json (same as scripts/seed.py).
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from lib import market, matching                    # noqa: E402
from lib.color_utils import ink as _ink             # noqa: E402

SEEDED_BY = "seed-popular"
MAX_PER_CAMPUS = 5
MAX_TOTAL_LISTINGS = 1200
SEEDED_PICKUP_SPOTS = ["Main library entrance", "Student center", "Campus bookstore entrance"]
SEEDED_CATEGORIES = list(market.CATEGORIES)   # every marketplace category incl. tickets and tutoring

# Two entries of school_colors.json are the same school under a second domain. They get no campus of their
# own; their domain just points at the main campus (extra pointer, written only when that campus is seeded).
ALIAS_ROOTS = {"washington.edu": "uw.edu", "indiana.edu": "iu.edu"}


# ── Timezones (estimate by campus location; admin console can correct) ────────

_CENTRAL = """ua auburn uab samford southalabama aamu alasu uah una shc lsu olemiss msstate uark missouri tamu utexas ou
vanderbilt illinois uiowa umn unl northwestern wisc baylor uh iastate ku k-state okstate tcu ttu rice tulane uic uchicago
depaul luc niu siu usm mtsu tnstate apsu tntech utm rhodes louisiana latech uno ulm mcneese unt utsa utdallas uta utrgv
txstate smu sfasu tsu pvamu trinity acu uca astate ualr mnsu usd und ndsu sdstate wichita nsula mc alcorn uwf valpo
austincc lonestar dcccd""".split()
_MOUNTAIN = "colorado utah usu byu weber uwyo colostate unm nmsu mines montana umt boisestate isu".split()
_PHOENIX = "arizona asu".split()
_PACIFIC = """uoregon oregonstate wsu uw wwu seattleu pdx stanford berkeley ucla usc ucsd uci ucdavis ucsb ucr ucsc sdsu
sjsu csun fullerton csusb fresnostate csuchico caltech scu lmu pepperdine calpoly ucsf usfca unlv unr uidaho""".split()


def _tz_table() -> dict:
    t = {}
    for names, tz in ((_CENTRAL, "America/Chicago"), (_MOUNTAIN, "America/Denver"),
                      (_PHOENIX, "America/Phoenix"), (_PACIFIC, "America/Los_Angeles")):
        for n in names:
            t[n + ".edu"] = tz
    t["hawaii.edu"] = "Pacific/Honolulu"
    return t


_TZ = _tz_table()
# Unsure: the registry entry for hawaii.edu is the whole UH System (Honolulu zone chosen); uidaho.edu is
# Moscow, Idaho (Pacific). Everything not listed above defaults to America/New_York.
LOW_CONFIDENCE_TZ = {"hawaii.edu", "uidaho.edu", "und.edu", "sdstate.edu"}


def timezone_for(root: str) -> str:
    return _TZ.get(root, "America/New_York")


# ── Sports (ticket listings) ──────────────────────────────────────────────────

FOOTBALL = set((
    "ua auburn uga ufl utk uky lsu olemiss msstate uark missouri tamu utexas ou sc clemson fsu miami duke unc ncsu "
    "virginia vt wfu gatech louisville nd pitt syr illinois iu uiowa umd umich msu umn unl northwestern osu uoregon psu "
    "purdue rutgers ucla usc uw wisc arizona asu baylor uc colorado uh iastate ku k-state okstate tcu ttu ucf utah wvu "
    "oregonstate wsu stanford berkeley boisestate colostate unlv unm byu temple usf vanderbilt"
).split())
BASKETBALL = set("villanova uconn georgetown butler udayton depaul luc".split())
FOOTBALL = {n + ".edu" for n in FOOTBALL}
BASKETBALL = {n + ".edu" for n in BASKETBALL}


# ── Name helpers: identical behaviour to backend/api.py ───────────────────────

def short_name(name: str) -> str:
    stop = {"of", "the", "at", "in", "and", "for", "a", "an"}
    words = name.split()
    initials = "".join(w[0].upper() for w in words if w.lower() not in stop and w[0].isalpha())
    return initials[:4] if initials else name[:4].upper()


def tenant_id_from_root(root: str) -> str:
    return root.replace(".", "-")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── Data loading ──────────────────────────────────────────────────────────────

def load_json(name: str) -> dict:
    with open(BACKEND / "data" / name, encoding="utf-8") as f:
        return json.load(f)


def school_list(colors: dict = None, registry: dict = None) -> list:
    """[(root, colour_entry, registry_entry_or_None)] in file order, aliases removed."""
    colors = colors if colors is not None else load_json("school_colors.json")
    registry = registry if registry is not None else load_json("us_schools.json")
    return [(r, c, registry.get(r)) for r, c in colors.items() if r not in ALIAS_ROOTS]


# ── Record builders ───────────────────────────────────────────────────────────

def build_tenant(root: str, color_entry: dict, reg_entry, created_at: str = None) -> tuple:
    """(tenant_item, [pointer_items]). Same field set as api.get_me's lazy creation (+ seed markers)."""
    now = created_at or now_iso()
    tid = tenant_id_from_root(root)
    name = (reg_entry or {}).get("name") or color_entry["name"]
    primary = color_entry["primary"]
    tenant = {
        "pk": "TENANTS",
        "sk": f"T#{tid}",
        "id": tid,
        "name": name,
        "shortName": short_name(name),
        "domains": list(reg_entry["domains"]) if reg_entry and reg_entry.get("domains") else [root],
        "theme": {"primary": primary, "ink": _ink(primary)},
        "colorSource": "verified-table",
        "colorStatus": "verified",
        "timezone": timezone_for(root),
        "timezoneSource": "seed-estimate",
        "lms": {"type": "other", "connector": "none"},
        "tutoringResources": [],
        "pickupSpots": list(SEEDED_PICKUP_SPOTS),
        "categories": list(SEEDED_CATEGORIES),
        "openToNetwork": True,
        "seeded": True,
        "createdBy": SEEDED_BY,
        "createdAt": now,
        "updatedAt": now,
    }
    pointers = [{"pk": f"DOMAIN#{root}", "sk": "MAP", "tenantId": tid}]
    for alias, target in ALIAS_ROOTS.items():
        if target == root:
            pointers.append({"pk": f"DOMAIN#{alias}", "sk": "MAP", "tenantId": tid})
    return tenant, pointers


# Textbooks: ISBN-13s verified by checksum at build time (an invalid one is left blank, never written).
BOOKS = [
    ("Principles of Economics", "N. Gregory Mankiw", "8th ed", "9781305585126", "ECON 101", (35, 75)),
    ("Calculus: Early Transcendentals", "James Stewart", "8th ed", "9781285741550", "MATH 151", (30, 70)),
    ("Chemistry: The Central Science", "Brown, LeMay, Bursten", "15th ed", "9780134414232", "CHEM 101", (40, 90)),
    ("Campbell Biology", "Urry et al", "12th ed", "9780135188743", "BIOL 101", (45, 95)),
    ("Python Crash Course", "Eric Matthes", "3rd ed", "9781718502703", "CS 101", (20, 35)),
    ("OpenIntro Statistics", "Diez, Cetinkaya-Rundel, Barr", "4th ed", "9781943450077", "STAT 201", (10, 30)),
    ("Clean Code", "Robert C. Martin", "1st ed", "9780132350884", "CS 201", (20, 40)),
    ("The C Programming Language", "Kernighan & Ritchie", "2nd ed", "9780131103627", "CS 211", (25, 50)),
    ("Introduction to Algorithms", "Cormen et al", "4th ed", "9780262046305", "CS 301", (45, 85)),
    ("Chemistry", "Zumdahl & DeCoste", "10th ed", "9781305957404", "CHEM 111", (40, 85)),
]
# (title, category, (lo, hi), description)
SUPPLIES = [
    ("TI-84 Plus CE graphing calculator", "supplies", (55, 90), "Works great, includes cable and cover."),
    ("Scientific calculator (Casio fx-115ES PLUS)", "supplies", (8, 18), "Allowed on most exams."),
    ("Lab goggles, splash-proof", "supplies", (4, 10), "Used for one semester of chemistry lab."),
]
DORM = [
    ("Mini fridge, 3.2 cu ft", "dorm", (40, 80), "Clean and cold, fits under a loft bed."),
    ("LED desk lamp with USB port", "dorm", (6, 16), "Three brightness levels."),
    ("Microwave, 700W", "dorm", (20, 40), "Compact, good for dorm rooms."),
]
ELECTRONICS = [
    ("USB-C hub, 7-in-1", "electronics", (12, 30), "HDMI, USB-A, SD card reader."),
    ("24-inch 1080p monitor", "electronics", (45, 95), "HDMI cable included."),
]
TUTORING = [
    ("Calculus tutoring", "Calculus", "MATH 101", (15, 30)),
    ("General chemistry tutoring", "General Chemistry", "CHEM 101", (15, 30)),
    ("Intro economics tutoring", "Microeconomics", "ECON 101", (15, 28)),
    ("Intro programming tutoring", "Programming", "CS 101", (18, 35)),
    ("Statistics tutoring", "Statistics", "STAT 201", (15, 30)),
]
CONDITION_CHOICES = ["Like new", "Good", "Good", "Acceptable"]
DEMO_NOTE = "Demo listing for illustration. Not a real item."


def _h(*parts) -> int:
    return int(hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest(), 16)


def _between(lo: int, hi: int, *seed) -> int:
    return lo + _h(*seed) % (hi - lo + 1)


def listing_id(tenant_id: str, slot: int) -> str:
    return hashlib.sha1(f"seed-popular|{tenant_id}|{slot}".encode()).hexdigest()[:8]


def listing_specs(root: str) -> list:
    """Create-request bodies (what POST /listings would receive) for one campus, 3 to 5 of them."""
    n = _h(root, "pick")
    specs = []

    title, author, edition, isbn, course, (lo, hi) = BOOKS[n % len(BOOKS)]
    body = {"kind": "sell", "title": title, "author": author, "edition": edition, "category": "books",
            "courseCode": course, "price": _between(lo, hi, root, "book"),
            "condition": CONDITION_CHOICES[_h(root, "c0") % 4], "description": DEMO_NOTE,
            "pickupSpot": SEEDED_PICKUP_SPOTS[0]}
    if matching.to_isbn13(isbn) == isbn:
        body["isbn"] = isbn
    specs.append(body)

    pool = SUPPLIES + ELECTRONICS
    t, cat, (lo, hi), desc = pool[(n >> 3) % len(pool)]
    specs.append({"kind": "sell", "title": t, "category": cat, "price": _between(lo, hi, root, "s1"),
                  "condition": CONDITION_CHOICES[_h(root, "c1") % 4], "description": f"{desc} {DEMO_NOTE}",
                  "pickupSpot": SEEDED_PICKUP_SPOTS[1]})

    pool = DORM + ELECTRONICS
    t, cat, (lo, hi), desc = pool[(n >> 6) % len(pool)]
    if t == specs[1]["title"]:
        t, cat, (lo, hi), desc = DORM[(n >> 9) % len(DORM)]
    specs.append({"kind": "sell", "title": t, "category": cat, "price": _between(lo, hi, root, "s2"),
                  "condition": CONDITION_CHOICES[_h(root, "c2") % 4], "description": f"{desc} {DEMO_NOTE}",
                  "pickupSpot": SEEDED_PICKUP_SPOTS[2]})

    t, subject, course, (lo, hi) = TUTORING[(n >> 12) % len(TUTORING)]
    specs.append({"kind": "service", "title": t, "category": "tutoring", "price": _between(lo, hi, root, "rate"),
                  "description": f"Tutoring by an upper-level student. {DEMO_NOTE}",
                  "tutoring": {"subjects": [subject], "courseCodes": [course],
                               "mode": ("both", "in_person", "online")[_h(root, "mode") % 3],
                               "availability": "Weekday evenings",
                               "standing": ("junior", "senior", "graduate")[_h(root, "st") % 3]}})

    if root in FOOTBALL or root in BASKETBALL:
        sport, venue = ("football", "Campus stadium") if root in FOOTBALL else ("basketball", "Campus arena")
        face = _between(25, 60, root, "face")
        specs.append({"kind": "sell", "title": f"Home {sport} game ticket", "category": "tickets",
                      "price": max(1, face - _between(0, 10, root, "disc")), "description": DEMO_NOTE,
                      "pickupSpot": SEEDED_PICKUP_SPOTS[1],
                      "ticket": {"event": f"Home {sport} game", "venue": venue, "section": "General admission",
                                 "quantity": 2, "faceValue": face, "transferMethod": "official_app",
                                 "_daysAhead": _between(7, 45, root, "days")}})
    return specs[:MAX_PER_CAMPUS]


def _validator():
    """listings_api.validate_fields when importable (it is inside this repo), else None."""
    try:
        import listings_api
        return listings_api
    except Exception as e:  # pragma: no cover
        print(f"WARNING: listings_api not importable ({e}); skipping validator check")
        return None


def build_listings(tenant: dict, root: str, now: datetime = None, validate: bool = True) -> list:
    """Full listing items for one campus, laid out exactly like listings_api.create_listing (no sellerSub,
    `demo: true`, seller 'Demo seller'). Every body is checked by the API's own validator."""
    now = now or datetime.now(timezone.utc)
    api = _validator() if validate else None
    tid = tenant["id"]
    specs = listing_specs(root)
    items = []
    for slot, spec in enumerate(specs):
        spec = json.loads(json.dumps(spec))
        if "ticket" in spec:
            days = spec["ticket"].pop("_daysAhead")
            event_at = (now + timedelta(days=days)).replace(hour=19, minute=0, second=0, microsecond=0)
            spec["ticket"]["eventAt"] = event_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        fields = api.validate_fields(spec, tenant, partial=False) if api else dict(spec)
        # createdAt spread over the last 10 days (deterministic offset per listing)
        offset = timedelta(days=_between(0, 9, tid, slot, "d"), hours=_between(0, 23, tid, slot, "h"),
                           minutes=_between(0, 59, tid, slot, "m"))
        created = (now - offset).strftime("%Y-%m-%dT%H:%M:%SZ")
        lid = listing_id(tid, slot)
        item = {
            "pk": f"LISTING#{lid}", "sk": "META", "id": lid, "tenantId": tid,
            "sellerName": "Demo seller",
            "title": fields["title"], "author": fields.get("author", ""), "edition": fields.get("edition", ""),
            "isbn": fields.get("isbn"), "price": fields.get("price"), "condition": fields.get("condition", ""),
            "category": fields["category"], "courseCode": fields.get("courseCode", ""),
            "description": fields.get("description", ""), "pickupSpot": fields.get("pickupSpot", ""),
            "status": "available", "createdAt": created, "updatedAt": created,
            "kind": fields["kind"], "images": [], "demo": True,
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
    return items


# ── Store: thin wrapper so tests can swap in a fake table ─────────────────────

THROTTLE = {"ProvisionedThroughputExceededException", "ThrottlingException", "RequestLimitExceeded",
            "InternalServerError", "ServiceUnavailable", "TransactionInProgressException"}


def _code(e: Exception) -> str:
    return (getattr(e, "response", None) or {}).get("Error", {}).get("Code", "")


def _retry(fn, attempts: int = 6, sleep=time.sleep):
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            if _code(e) in THROTTLE and i < attempts - 1:
                sleep(min(0.25 * 2 ** i, 4))
                continue
            raise


class Store:
    """get / conditional put / one transaction over a boto3 Table-like object."""

    def __init__(self, table, sleep=time.sleep):
        self.table, self.sleep = table, sleep

    def get(self, pk: str, sk: str):
        return _retry(lambda: self.table.get_item(Key={"pk": pk, "sk": sk}), sleep=self.sleep).get("Item")

    def put_new(self, item: dict) -> bool:
        """Conditional put. False when the item already exists."""
        try:
            _retry(lambda: self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)"),
                   sleep=self.sleep)
            return True
        except Exception as e:
            if _code(e) == "ConditionalCheckFailedException":
                return False
            raise

    def transact_new(self, items: list) -> bool:
        """All items written atomically, each conditional on not existing. False when any already exists."""
        payload = [{"Put": {"TableName": self.table.name,
                            "Item": it,
                            "ConditionExpression": "attribute_not_exists(pk)"}} for it in items]
        for i in range(6):
            try:
                self.table.meta.client.transact_write_items(TransactItems=payload)
                return True
            except Exception as e:
                c = _code(e)
                if c == "TransactionCanceledException":
                    if any(self.get(it["pk"], it["sk"]) for it in items):
                        return False                       # a conflict because something exists
                    if i < 5:
                        self.sleep(min(0.25 * 2 ** i, 4))   # cancelled for another reason (throttle/conflict)
                        continue
                if c in THROTTLE and i < 5:
                    self.sleep(min(0.25 * 2 ** i, 4))
                    continue
                raise
        return False


def get_table():
    table_name = os.environ.get("TABLE_NAME")
    if not table_name:
        outputs_path = ROOT / "cdk-outputs.json"
        if not outputs_path.exists():
            sys.exit("ERROR: TABLE_NAME not set and cdk-outputs.json not found. Run deploy first.")
        table_name = json.loads(outputs_path.read_text()).get("SemesterOS", {}).get("TableName")
        if not table_name:
            sys.exit("ERROR: TableName not found in cdk-outputs.json")
    import boto3
    return boto3.resource("dynamodb", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")).Table(table_name)


# ── Runner ────────────────────────────────────────────────────────────────────

class EmptyStore:
    """--dry-run --assume-empty: pretends nothing exists. No AWS."""

    def get(self, pk, sk):
        return None


def run(store, schools: list, dry_run: bool, now: datetime = None, log=print) -> dict:
    now = now or datetime.now(timezone.utc)
    stats = {"schools": len(schools), "tenants": 0, "pointers": 0, "listings": 0,
             "skipped_tenants": 0, "skipped_listings": 0, "listing_cap_hit": False}
    total_planned = 0
    for n, (root, color_entry, reg_entry) in enumerate(schools, 1):
        tenant, pointers = build_tenant(root, color_entry, reg_entry, created_at=now_iso())
        existing = store.get("TENANTS", tenant["sk"])
        ptr_exists = any(store.get(p["pk"], p["sk"]) for p in pointers[:1])
        seeded_here = False
        if existing or ptr_exists:
            stats["skipped_tenants"] += 1
            seeded_here = bool(existing and existing.get("seeded") is True)
            log(f"[{n}/{len(schools)}] {root}: exists, skipped" + (" (seeded earlier, checking listings)" if seeded_here else ""))
        elif dry_run:
            stats["tenants"] += 1
            stats["pointers"] += len(pointers)
            seeded_here = True
            log(f"[{n}/{len(schools)}] {root}: would create campus {tenant['id']}")
        else:
            ok = store.transact_new([tenant, pointers[0]])
            if not ok:
                stats["skipped_tenants"] += 1
                log(f"[{n}/{len(schools)}] {root}: created by someone else meanwhile, skipped")
            else:
                stats["tenants"] += 1
                stats["pointers"] += 1
                seeded_here = True
                for extra in pointers[1:]:
                    if store.put_new(extra):
                        stats["pointers"] += 1
                log(f"[{n}/{len(schools)}] {root}: created campus {tenant['id']}")
        if not seeded_here:
            continue
        # Listings only for campuses this script owns (seeded: true)
        tenant_for_listings = existing if existing else tenant
        items = build_listings({**tenant_for_listings}, root, now)
        for it in items:
            if total_planned >= MAX_TOTAL_LISTINGS:
                stats["listing_cap_hit"] = True
                break
            total_planned += 1
            if dry_run:
                if existing and store.get(it["pk"], it["sk"]):
                    stats["skipped_listings"] += 1
                else:
                    stats["listings"] += 1
            elif store.put_new(it):
                stats["listings"] += 1
            else:
                stats["skipped_listings"] += 1
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="read-only: print counts, write nothing")
    ap.add_argument("--only", default="", help="comma-separated root domains, e.g. ua.edu,lsu.edu")
    ap.add_argument("--assume-empty", action="store_true", help="with --dry-run: do not touch AWS at all")
    args = ap.parse_args(argv)

    schools = school_list()
    if args.only:
        wanted = [x.strip().lower() for x in args.only.split(",") if x.strip()]
        known = {s[0] for s in schools}
        bad = [w for w in wanted if w not in known]
        if bad:
            print(f"ERROR: not in school_colors.json (or an alias): {', '.join(bad)}")
            return 2
        schools = [s for s in schools if s[0] in wanted]
    if args.assume_empty and not args.dry_run:
        print("ERROR: --assume-empty only works with --dry-run")
        return 2

    if args.assume_empty:
        store = EmptyStore()
    else:
        table = get_table()
        print(f"Table: {table.name}")
        store = Store(table)
    print(("DRY RUN (no writes). " if args.dry_run else "") + f"{len(schools)} schools\n")
    st = run(store, schools, args.dry_run)
    verb = "Would create" if args.dry_run else "Created"
    print(f"\n{verb}: {st['tenants']} campuses, {st['pointers']} domain pointers, {st['listings']} demo listings")
    print(f"Skipped (already exist): {st['skipped_tenants']} campuses, {st['skipped_listings']} listings")
    if st["listing_cap_hit"]:
        print(f"NOTE: stopped at the {MAX_TOTAL_LISTINGS}-listing safety cap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
