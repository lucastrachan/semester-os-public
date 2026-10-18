"""Add demo textbook listings for the books named in the student's real syllabi (UA: EN 210, MGT 488, MIS 460).

Print books only (no Access Granted codes, no e-books). Every listing is `demo: true`, seller 'Demo seller', labelled
'Demo listing'. Deterministic ids and conditional puts: safe to re-run. Default is a dry run; --apply writes.
"""
import argparse
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import boto3

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend" / "vendor"))
import listings_api  # noqa: E402

TABLE = "SemesterOS-AppTable815C50BC-1329F05K3G6QJ"
FALLBACK = {"url": "/demo/market/fallback-books.svg", "alt": "Textbook"}

BOOKS = [
    # code, title, author, edition, isbn, new price
    ("EN 210", "Behind a Mask", "Louisa May Alcott", "", "9780688151324", 16),
    ("EN 210", "My Antonia (Norton Critical Editions)", "Willa Cather", "", "9780393967906", 22),
    ("EN 210", "The Awakening", "Kate Chopin", "", "9780393617313", 12),
    ("EN 210", "Daisy Miller and Other Tales", "Henry James", "", "9780141389776", 11),
    ("EN 210", "The Namesake", "Jhumpa Lahiri", "", "9780358062684", 17),
    ("EN 210", "Annihilation", "Jeff VanderMeer", "10th Anniversary", "9781250824042", 18),
    ("MGT 488", "Cybersecurity For Dummies", "Joseph Steinberg", "3rd", "9781394318728", 23),
    ("MGT 488", "Cybersecurity All-in-One For Dummies", "Joseph Steinberg et al.", "1st", "9781394152858", 29),
    ("MGT 488", "A Leader's Guide to Cybersecurity", "Parenty and Domet", "", "9781633697997", 19),
    ("MIS 460", "Fundamentals of Information Systems Security", "David Kim and Michael Solomon", "5th", "9781284310580", 85),
]
CONDITIONS = ["Like new", "Good", "Good", "Acceptable"]
CAMPUSES = ["ua", "auburn", "gatech"]


def _h(*parts):
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest(), 16)


def build(tenant, now):
    tid = tenant["id"]
    spots = tenant.get("pickupSpots") or tenant.get("pickup_spots") or ["Student center"]
    items = []
    for n, (code, title, author, edition, isbn, new_price) in enumerate(BOOKS):
        for copy in range(2 if tid == "ua" else 1):
            cond = CONDITIONS[_h(tid, n, copy, "c") % len(CONDITIONS)]
            price = max(5, int(new_price * (0.45 + (_h(tid, n, copy, "p") % 25) / 100)))
            spec = {"kind": "sell", "category": "books", "title": title, "author": author, "edition": edition,
                    "isbn": isbn, "price": price, "condition": cond, "courseCode": code,
                    "description": f"Used for {code}. Demo listing.",
                    "pickupSpot": spots[_h(tid, n, copy, "s") % len(spots)]}
            fields = listings_api.validate_fields(spec, tenant, partial=False)
            created = (now - timedelta(days=_h(tid, n, copy, "d") % 9, hours=_h(tid, n, copy, "h") % 23)).strftime("%Y-%m-%dT%H:%M:%SZ")
            lid = "sb" + hashlib.sha256(f"seed-syllabus|{tid}|{n}|{copy}".encode()).hexdigest()[:10]
            item = {"pk": f"LISTING#{lid}", "sk": "META", "id": lid, "tenantId": tid, "sellerName": "Demo seller",
                    "title": fields["title"], "author": fields.get("author", ""), "edition": fields.get("edition", ""),
                    "isbn": fields["isbn"], "price": fields["price"], "condition": fields.get("condition", ""),
                    "category": "books", "courseCode": fields.get("courseCode", ""),
                    "description": fields.get("description", ""), "pickupSpot": fields.get("pickupSpot", ""),
                    "status": "available", "createdAt": created, "updatedAt": created, "kind": "sell",
                    "images": [FALLBACK], "demo": True,
                    "gsi1pk": f"TENANT#{tid}#LISTINGS", "gsi1sk": created,
                    "gsi2pk": f"ISBN#{fields['isbn']}", "gsi2sk": f"{tid}#{lid}"}
            items.append(item)
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
    now = datetime.now(timezone.utc)
    total = written = 0
    for tid in CAMPUSES:
        tenant = table.get_item(Key={"pk": "TENANTS", "sk": f"T#{tid}"}).get("Item")
        if not tenant:
            print("skip (no tenant):", tid)
            continue
        tenant = {k: v for k, v in tenant.items()}
        tenant["id"] = tid
        items = build(tenant, now)
        total += len(items)
        if args.apply:
            for it in items:
                try:
                    table.put_item(Item=it, ConditionExpression="attribute_not_exists(pk)")
                    written += 1
                except table.meta.client.exceptions.ConditionalCheckFailedException:
                    pass
        print(f"{tid}: {len(items)} listings")
    print(f"total planned {total}; written {written}" + ("" if args.apply else " (dry run; pass --apply)"))


if __name__ == "__main__":
    main()
