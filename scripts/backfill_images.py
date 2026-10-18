"""Give demo listings without a picture one of the illustrated SVGs (web/public/demo/market).

Only touches listings with demo=true and an empty `images`. Idempotent. Default is a dry run; --apply writes.
"""
import argparse
import json
import pathlib
import sys

import boto3
from boto3.dynamodb.conditions import Attr

TABLE = "SemesterOS-AppTable815C50BC-1329F05K3G6QJ"
MANIFEST = pathlib.Path(__file__).resolve().parent.parent / "web" / "public" / "demo" / "market" / "manifest.json"

# first match wins (lowercase substring of the title)
RULES = [
    ("usb-c", "usb-c-hub"), ("monitor", "monitor"), ("football", "ticket-football"),
    ("basketball", "ticket-basketball"), ("concert", "ticket-concert"), ("microwave", "microwave"),
    ("mini fridge", "mini-fridge"), ("mini-fridge", "mini-fridge"),
    ("tutoring", None),  # decided by subject below
    ("graphing", "calculator-graphing"), ("scientific calc", "calculator-scientific"),
    ("goggles", "lab-goggles"), ("desk lamp", "desk-lamp"), ("lamp", "desk-lamp"),
    ("campbell biology", "textbook-chem"), ("chemistry", "textbook-chem"),
    ("statistics", "textbook-stats"), ("economics", "textbook-econ"),
    ("python crash", "textbook-cs"), ("algorithms", "textbook-cs"), ("c programming", "textbook-cs"),
    ("clean code", "textbook-cs"), ("calculus", "textbook-calc"),
    ("information systems", "textbook-mis"), ("marketing", "textbook-econ"),
    ("headphone", "headphones"), ("laptop stand", "laptop-stand"), ("laptop", "laptop"),
    ("hoodie", "hoodie"), ("jersey", "jersey"), ("bike", "bike"), ("notebook", "notebook-set"),
]
TUTOR = [("calculus", "tutor-math"), ("statistics", "tutor-math"), ("math", "tutor-math"),
         ("programming", "tutor-cs"), ("computer", "tutor-cs"), ("chemistry", "tutor-business"),
         ("economics", "tutor-business"), ("business", "tutor-business")]


def slug_for(title):
    t = (title or "").lower()
    for needle, slug in RULES:
        if needle in t:
            if slug is None:
                return next((s for k, s in TUTOR if k in t), "tutor-math")
            return slug
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
    kw = dict(FilterExpression=Attr("pk").begins_with("LISTING#") & Attr("sk").eq("META") & Attr("demo").eq(True),
              ProjectionExpression="pk,sk,title,images")
    r = table.scan(**kw)
    items = r["Items"]
    while "LastEvaluatedKey" in r:
        r = table.scan(ExclusiveStartKey=r["LastEvaluatedKey"], **kw)
        items += r["Items"]
    todo, unmatched, written = 0, {}, 0
    for it in items:
        if it.get("images"):
            continue
        slug = slug_for(it.get("title"))
        if not slug or slug not in manifest:
            unmatched[it.get("title")] = unmatched.get(it.get("title"), 0) + 1
            continue
        todo += 1
        if args.apply:
            image = [{"url": f"/demo/market/{slug}.svg", "alt": manifest[slug]["alt"]}]
            table.update_item(Key={"pk": it["pk"], "sk": it["sk"]},
                              UpdateExpression="SET images = :i",
                              ConditionExpression="attribute_exists(pk) AND (attribute_not_exists(images) OR size(images) = :z)",
                              ExpressionAttributeValues={":i": image, ":z": 0})
            written += 1
    print(f"demo listings scanned: {len(items)}; to update: {todo}; written: {written}")
    print("no matching picture:", unmatched)
    if not args.apply:
        print("dry run; pass --apply to write")


if __name__ == "__main__":
    sys.exit(main())
