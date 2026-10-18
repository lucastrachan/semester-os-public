#!/usr/bin/env python3
"""
Seed campuses and demo listings. Idempotent — safe to run multiple times.
Usage:  python scripts/seed.py
Reads TABLE_NAME from env or cdk-outputs.json.
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import boto3
from boto3.dynamodb.conditions import Key


def get_table():
    table_name = os.environ.get("TABLE_NAME")
    if not table_name:
        outputs_path = ROOT / "cdk-outputs.json"
        if not outputs_path.exists():
            print("ERROR: TABLE_NAME not set and cdk-outputs.json not found. Run deploy first.")
            sys.exit(1)
        outputs = json.loads(outputs_path.read_text()).get("SemesterOS", {})
        table_name = outputs.get("TableName")
        if not table_name:
            print("ERROR: TableName not found in cdk-outputs.json")
            sys.exit(1)
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    dynamodb = boto3.resource("dynamodb", region_name=region)
    return dynamodb.Table(table_name)


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


CAMPUSES = [
    {
        "id": "ua",
        "name": "The University of Alabama",
        "shortName": "UA",
        "domains": ["ua.edu", "crimson.ua.edu"],
        "theme": {"primary": "#9E1B32", "accent": "#9E1B32", "ink": "#ffffff"},
        "timezone": "America/Chicago",
        "tutoringResources": [
            {
                "name": "Center for Academic Success",
                "description": "Free tutoring and academic coaching for UA students.",
                "url": "https://cas.ua.edu",
            }
        ],
        "pickupSpots": [
            "The Ferguson Center (Ferg)",
            "Gorgas Library",
            "Student Recreation Center",
            "Bryant-Denny Stadium North Gate",
        ],
        "lms": {"type": "blackboard_ultra", "connector": "ical_feed"},
        "categories": ["books", "supplies", "electronics", "dorm", "clothing", "tickets", "tutoring", "rides", "other"],
        "openToNetwork": True,
    },
    {
        "id": "auburn",
        "name": "Auburn University",
        "shortName": "AU",
        "domains": ["auburn.edu"],
        "theme": {"primary": "#0C2340", "accent": "#E87722", "ink": "#ffffff"},
        "timezone": "America/Chicago",
        "tutoringResources": [
            {
                "name": "Academic Support Center",
                "description": "Free tutoring and supplemental instruction.",
                "url": "https://asc.auburn.edu",
            }
        ],
        "pickupSpots": [
            "Haley Center",
            "RBD Library",
            "Auburn University Recreation & Wellness Center",
        ],
        "lms": {"type": "canvas", "connector": "pending_admin_approval"},
        "categories": ["books", "supplies", "electronics", "dorm", "clothing", "tickets", "tutoring", "rides", "other"],
        "openToNetwork": True,
    },
    {
        "id": "gatech",
        "name": "Georgia Institute of Technology",
        "shortName": "GT",
        "domains": ["gatech.edu"],
        "theme": {"primary": "#003057", "accent": "#B3A369", "ink": "#ffffff"},
        "timezone": "America/New_York",
        "tutoringResources": [
            {
                "name": "Center for Academic Success",
                "description": "Tutoring and academic support for GT students.",
                "url": "https://cas.gatech.edu",
            }
        ],
        "pickupSpots": [
            "Clough Undergraduate Learning Commons",
            "Student Center",
            "Campus Recreation Center",
        ],
        "lms": {"type": "canvas", "connector": "pending_admin_approval"},
        "categories": ["books", "supplies", "electronics", "dorm", "clothing", "tickets", "tutoring", "rides", "other"],
        "openToNetwork": True,
    },
]

DEMO_LISTINGS = [
    {"tenantId": "ua", "title": "Calculus: Early Transcendentals 8th ed", "author": "James Stewart",
     "isbn": "9781285741550", "price": 35, "condition": "Good", "category": "textbooks"},
    {"tenantId": "ua", "title": "Principles of Marketing 17th ed", "author": "Kotler & Armstrong",
     "isbn": "9780134492513", "price": 45, "condition": "Like new", "category": "textbooks"},
    {"tenantId": "ua", "title": "Mini-fridge — 3.2 cu ft", "price": 60, "condition": "Good",
     "category": "dorm"},
    {"tenantId": "auburn", "title": "Calculus: Early Transcendentals 8th ed", "author": "James Stewart",
     "isbn": "9781285741550", "price": 30, "condition": "Acceptable", "category": "textbooks"},
    {"tenantId": "gatech", "title": "Introduction to Algorithms (CLRS) 4th ed",
     "author": "Cormen et al", "isbn": "9780262046305", "price": 55, "condition": "Good",
     "category": "textbooks"},
    {"tenantId": "gatech", "title": "TI-89 Titanium graphing calculator", "price": 40,
     "condition": "Good", "category": "electronics"},
]


def seed_campus(table, campus: dict):
    t = campus
    created = now()
    existing = table.get_item(Key={"pk": "TENANTS", "sk": f"T#{t['id']}"}).get("Item")
    if existing:
        # Already seeded — update only the categories list (safe to re-run)
        table.update_item(
            Key={"pk": "TENANTS", "sk": f"T#{t['id']}"},
            UpdateExpression="SET categories = :c",
            ExpressionAttributeValues={":c": t["categories"]},
        )
        print(f"  [UPDATED categories] Tenant: {t['name']}")
        return
    # Tenant record
    table.put_item(Item={
        "pk": "TENANTS",
        "sk": f"T#{t['id']}",
        "id": t["id"],
        "name": t["name"],
        "shortName": t["shortName"],
        "domains": t["domains"],
        "theme": t["theme"],
        "timezone": t["timezone"],
        "lms": t["lms"],
        "tutoringResources": t["tutoringResources"],
        "pickupSpots": t["pickupSpots"],
        "categories": t["categories"],
        "openToNetwork": t["openToNetwork"],
        "createdAt": created,
    })
    print(f"  [OK] Tenant: {t['name']}")

    # Domain map items
    for domain in t["domains"]:
        parts = domain.lower().split(".")
        normalized = ".".join(parts[-2:]) if len(parts) >= 2 else domain
        table.put_item(Item={
            "pk": f"DOMAIN#{normalized}",
            "sk": "MAP",
            "tenantId": t["id"],
        })
        print(f"    -> Domain: {normalized}")


def seed_listing(table, listing: dict, idx: int):
    import secrets, string
    listing_id = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    created = now()
    tenant_id = listing["tenantId"]
    table.put_item(Item={
        "pk": f"LISTING#{listing_id}",
        "sk": "META",
        "id": listing_id,
        "tenantId": tenant_id,
        "title": listing["title"],
        "author": listing.get("author"),
        "isbn": listing.get("isbn"),
        "price": listing["price"],
        "condition": listing["condition"],
        "category": listing["category"],
        "status": "available",
        "demo": True,
        "createdAt": created,
        "gsi1pk": f"TENANT#{tenant_id}#LISTINGS",
        "gsi1sk": created,
        **({"gsi2pk": f"ISBN#{listing['isbn']}", "gsi2sk": f"{tenant_id}#{listing_id}"}
           if listing.get("isbn") else {}),
    })
    print(f"  [OK] Listing: {listing['title'][:50]} — ${listing['price']}")


def main():
    print("Connecting to DynamoDB...")
    table = get_table()
    print(f"Table: {table.name}\n")

    print("Seeding campuses...")
    for campus in CAMPUSES:
        seed_campus(table, campus)

    print("\nSeeding demo listings...")
    for i, listing in enumerate(DEMO_LISTINGS):
        seed_listing(table, listing, i)

    print(f"\nDone -- {len(CAMPUSES)} campuses, {len(DEMO_LISTINGS)} demo listings")


if __name__ == "__main__":
    main()


