#!/usr/bin/env python3
"""
Backfill displayName for user profiles that have none (or still use the email prefix).

Default: dry-run only (prints what would change).
Pass --apply to write the changes.

Sets displayName = "Luca Strachan" for any profile whose displayName is missing or equals
the email prefix (email.split('@')[0]), then refreshes sellerName on that user's listings.

Usage:
  python scripts/backfill_names.py           # dry-run
  python scripts/backfill_names.py --apply   # write changes
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

BACKFILL_FIRST = "Luca"
BACKFILL_LAST = "Strachan"
BACKFILL_NAME = f"{BACKFILL_FIRST} {BACKFILL_LAST}"


def get_table():
    table_name = os.environ.get("TABLE_NAME")
    if not table_name:
        outputs_path = ROOT / "cdk-outputs.json"
        if outputs_path.exists():
            with open(outputs_path) as f:
                data = json.load(f)
            for stack_output in data.values():
                table_name = stack_output.get("TableName")
                if table_name:
                    break
    if not table_name:
        sys.exit("ERROR: TABLE_NAME not found")
    import boto3
    return boto3.resource("dynamodb", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")).Table(table_name)


def scan_profiles(table):
    """Yield all USER#*/PROFILE items."""
    kwargs = {
        "FilterExpression": "sk = :sk AND begins_with(pk, :pk)",
        "ExpressionAttributeValues": {":sk": "PROFILE", ":pk": "USER#"},
    }
    while True:
        resp = table.scan(**kwargs)
        yield from resp.get("Items", [])
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def mask_email(email: str) -> str:
    parts = email.split("@")
    local = parts[0]
    return f"{local[:2]}***@{parts[1]}" if len(local) > 2 else f"***@{parts[1]}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = ap.parse_args(argv)

    table = get_table()
    print(f"Table: {table.name}")
    if not args.apply:
        print("DRY RUN (pass --apply to write)\n")

    profiles_backfilled = 0
    listings_updated = 0

    for profile in scan_profiles(table):
        email = profile.get("email", "")
        sub = profile.get("sub") or profile["pk"].replace("USER#", "")
        email_prefix = email.split("@")[0] if email else ""
        current_name = profile.get("displayName", "")

        needs_backfill = not profile.get("firstName") or not current_name or current_name == email_prefix
        if not needs_backfill:
            continue

        profiles_backfilled += 1
        print(f"  Profile {mask_email(email) if email else sub}: "
              f"displayName={current_name!r} -> {BACKFILL_NAME!r}")

        if args.apply:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            table.update_item(
                Key={"pk": profile["pk"], "sk": "PROFILE"},
                UpdateExpression="SET firstName = :f, lastName = :l, displayName = :n, updatedAt = :t",
                ExpressionAttributeValues={":f": BACKFILL_FIRST, ":l": BACKFILL_LAST, ":n": BACKFILL_NAME, ":t": now},
            )

        # Refresh sellerName on this user's listings
        listing_resp = table.scan(
            FilterExpression="sellerSub = :s AND begins_with(pk, :pk)",
            ExpressionAttributeValues={":s": sub, ":pk": "LISTING#"},
        )
        for listing in listing_resp.get("Items", []):
            if listing.get("sellerName") != BACKFILL_NAME:
                listings_updated += 1
                print(f"    Listing {listing['pk']}: sellerName {listing.get('sellerName')!r} -> {BACKFILL_NAME!r}")
                if args.apply:
                    table.update_item(
                        Key={"pk": listing["pk"], "sk": listing["sk"]},
                        UpdateExpression="SET sellerName = :n",
                        ExpressionAttributeValues={":n": BACKFILL_NAME},
                    )

    verb = "Would update" if not args.apply else "Updated"
    print(f"\n{verb}: {profiles_backfilled} profiles, {listings_updated} listings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
