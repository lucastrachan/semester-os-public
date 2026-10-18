"""Shared fakes for the tests. No AWS, no network."""
import sys
from pathlib import Path

BACKEND = str(Path(__file__).resolve().parents[1])
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class FakeDb:
    """Same function names as lib/db.py, backed by a dict."""

    def __init__(self):
        self.items = {}

    def get_item(self, pk, sk):
        return self.items.get((pk, sk))

    def put_item(self, item):
        self.items[(item["pk"], item["sk"])] = dict(item)

    def update_item(self, pk, sk, updates):
        self.items.setdefault((pk, sk), {"pk": pk, "sk": sk}).update(updates)
        return self.items[(pk, sk)]

    def delete_item(self, pk, sk):
        self.items.pop((pk, sk), None)

    def query_pk(self, pk, sk_prefix=None):
        return [v for (p, s), v in self.items.items() if p == pk and (not sk_prefix or s.startswith(sk_prefix))]


class FakeClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeCounterTable:
    """Implements just the conditional ADD that limits.py uses."""

    def __init__(self):
        self.rows = {}

    def update_item(self, Key, UpdateExpression, ConditionExpression, ExpressionAttributeNames,
                    ExpressionAttributeValues, ReturnValues):
        k = (Key["pk"], Key["sk"])
        row = self.rows.setdefault(k, {})
        if "n" in row and not row["n"] < ExpressionAttributeValues[":limit"]:
            raise FakeClientError("ConditionalCheckFailedException")
        row["n"] = row.get("n", 0) + ExpressionAttributeValues[":one"]
        row.setdefault("ttl", ExpressionAttributeValues[":ttl"])
        return {"Attributes": {"n": row["n"]}}
