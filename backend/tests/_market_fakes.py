"""Fakes and fixtures shared by the marketplace tests. No AWS."""
import re

from _fakes import FakeClientError, FakeDb

ME = "user-aaaa-1111"        # UA student, display name "Sam Student"
OTHER = "user-bbbb-2222"     # UA student whose displayName is the default (email local part)
AUB = "user-cccc-3333"       # Auburn student
GT = "user-dddd-4444"        # student of a campus that is NOT open to the network

TENANTS = {
    "ua": {"name": "The University of Alabama", "shortName": "UA", "domains": ["ua.edu"], "openToNetwork": True,
           "pickupSpots": ["Student Center", "Gorgas Library"], "categories": ["textbooks", "dorm", "electronics", "other"]},
    "auburn": {"name": "Auburn University", "shortName": "AU", "domains": ["auburn.edu"], "openToNetwork": True,
               "pickupSpots": ["Haley Center"], "categories": ["textbooks", "dorm", "other"]},
    "gatech": {"name": "Georgia Tech", "shortName": "GT", "domains": ["gatech.edu"], "openToNetwork": False,
               "pickupSpots": [], "categories": ["textbooks", "electronics", "other"]},
    "offline": {"name": "Offline College", "shortName": "OC", "domains": ["offline.edu"], "openToNetwork": True,
                "disabled": True, "pickupSpots": [], "categories": ["textbooks", "other"]},
    "spam": {"name": "Spam U", "shortName": "SU", "domains": ["students.spam.edu"], "openToNetwork": True,
             "pickupSpots": [], "categories": ["textbooks", "other"]},
}


class FakeTable:
    name = "app"

    def __init__(self, items):
        self.items = items
        self.counters = {}

    def put_item(self, Item, ConditionExpression=None):
        k = (Item["pk"], Item["sk"])
        if ConditionExpression and "attribute_not_exists" in ConditionExpression and k in self.items:
            raise FakeClientError("ConditionalCheckFailedException")
        self.items[k] = dict(Item)

    def update_item(self, Key, UpdateExpression, ConditionExpression=None, ExpressionAttributeNames=None,
                    ExpressionAttributeValues=None, ReturnValues=None):
        vals, names = ExpressionAttributeValues or {}, ExpressionAttributeNames or {}
        k = (Key["pk"], Key["sk"])
        if UpdateExpression.startswith("ADD"):          # limits.py counter
            row = self.counters.setdefault(k, {})
            if "n" in row and not row["n"] < vals[":limit"]:
                raise FakeClientError("ConditionalCheckFailedException")
            row["n"] = row.get("n", 0) + vals[":one"]
            return {"Attributes": {"n": row["n"]}}
        item = self.items.get(k)
        for part in (ConditionExpression or "").split(" AND "):
            part = part.strip()
            ok = True
            if part == "attribute_exists(pk)":
                ok = item is not None
            elif part == "sellerSub = :owner":
                ok = item is not None and item.get("sellerSub") == vals[":owner"]
            elif part == "msgCount < :max":
                ok = item is not None and item.get("msgCount", 0) < vals[":max"]
            elif part:
                raise AssertionError(f"fake does not understand condition {part!r}")
            if not ok:
                raise FakeClientError("ConditionalCheckFailedException")
        if item is None:
            item = self.items.setdefault(k, {"pk": k[0], "sk": k[1]})
        tokens = re.split("(?<![A-Za-z])(SET|ADD|REMOVE)(?![A-Za-z])", UpdateExpression)
        for kind, body in zip(tokens[1::2], tokens[2::2]):
            for piece in filter(None, (x.strip() for x in body.split(","))):
                if kind == "SET":
                    n, v = piece.split(" = ")
                    item[names.get(n, n)] = vals[v]
                elif kind == "ADD":
                    n, v = piece.split(" ")
                    item[names.get(n, n)] = item.get(names.get(n, n), 0) + vals[v]
                else:
                    item.pop(names.get(piece, piece), None)
        return {}


class Db(FakeDb):
    def __init__(self):
        super().__init__()
        self._table = FakeTable(self.items)

    def table(self):
        return self._table

    def get_item(self, pk, sk):
        """A copy, like DynamoDB: callers must not see later in-place updates through an old read."""
        item = self.items.get((pk, sk))
        return dict(item) if item is not None else None

    def incr_counter(self, pk, sk, ttl):
        row = self.items.setdefault((pk, sk), {"pk": pk, "sk": sk, "n": 0})
        row["n"] += 1
        return row["n"]


def fake_gsi_query(db):
    def q(index, pk_value, newest_first=True, limit=200):
        a = {"gsi1": ("gsi1pk", "gsi1sk"), "gsi2": ("gsi2pk", "gsi2sk")}[index]
        rows = [dict(v) for v in db.items.values() if v.get(a[0]) == pk_value and v["pk"].startswith("LISTING#") and v["sk"] == "META"]
        rows.sort(key=lambda r: r.get(a[1], ""), reverse=newest_first)
        return rows[:limit]
    return q


def world(modules):
    """Build a fresh fake world and point every module in `modules` at it. Returns the Db."""
    db = Db()
    from lib import convos
    for mod in list(modules) + [convos]:
        mod.db = db
        mod._table = lambda db=db: db.table()
        if hasattr(mod, "gsi_query"):
            mod.gsi_query = fake_gsi_query(db)
    for tid, t in TENANTS.items():
        db.put_item({"pk": "TENANTS", "sk": f"T#{tid}", "id": tid, **t})
    db.put_item({"pk": "BLOCKED_DOMAINS", "sk": "D#spam.edu", "domain": "spam.edu"})
    for sub, tid, name, email in ((ME, "ua", "Sam Student", "sam1@ua.edu"), (OTHER, "ua", "other.person", "other.person@ua.edu"),
                                  (AUB, "auburn", "Ann Tiger", "ann@auburn.edu"), (GT, "gatech", "Gus Tech", "gus@gatech.edu")):
        db.put_item({"pk": f"USER#{sub}", "sk": "PROFILE", "sub": sub, "email": email, "tenantId": tid, "displayName": name})
    return db


def add_listing(db, lid, tenant="ua", seller=None, title="Calculus: Early Transcendentals 8th ed", author="James Stewart",
                isbn="9781285741550", price=35, condition="Good", category="textbooks", created="2026-10-01T10:00:00Z",
                demo=False, **extra):
    """Writes a listing item in the exact layout seed.py uses (plus the new optional fields)."""
    item = {"pk": f"LISTING#{lid}", "sk": "META", "id": lid, "tenantId": tenant, "title": title, "author": author, "isbn": isbn,
            "price": price, "condition": condition, "category": category, "status": "available", "createdAt": created,
            "gsi1pk": f"TENANT#{tenant}#LISTINGS", "gsi1sk": created, **extra}
    if demo:
        item["demo"] = True
    if seller:
        item["sellerSub"], item["sellerName"] = seller, "Seller"
    if isbn:
        item["gsi2pk"], item["gsi2sk"] = f"ISBN#{isbn}", f"{tenant}#{lid}"
    db.put_item(item)
    return item
