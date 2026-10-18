"""scripts/seed_popular.py against a fake in-memory table. No AWS."""
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_spec = importlib.util.spec_from_file_location("seed_popular", BACKEND.parent / "scripts" / "seed_popular.py")
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)

import listings_api  # noqa: E402
from lib import market, matching  # noqa: E402
from tests._fakes import FakeClientError  # noqa: E402


class _Client:
    def __init__(self, table):
        self.t = table

    def transact_write_items(self, TransactItems):
        puts = [ti["Put"]["Item"] for ti in TransactItems]
        if any((p["pk"], p["sk"]) in self.t.items for p in puts):
            raise FakeClientError("TransactionCanceledException")
        self.t.transactions += 1
        for p in puts:
            self.t.items[(p["pk"], p["sk"])] = p


class FakeTable:
    name = "fake"

    def __init__(self):
        self.items, self.transactions = {}, 0
        self.meta = type("M", (), {"client": _Client(self)})()

    def get_item(self, Key):
        it = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": it} if it else {}

    def put_item(self, Item, ConditionExpression=None):
        k = (Item["pk"], Item["sk"])
        if ConditionExpression == "attribute_not_exists(pk)" and k in self.items:
            raise FakeClientError("ConditionalCheckFailedException")
        self.items[k] = dict(Item)


def tenants(t):
    return [v for (p, _), v in t.items.items() if p == "TENANTS"]


def listings(t):
    return [v for (p, _), v in t.items.items() if p.startswith("LISTING#")]


@pytest.fixture(scope="module")
def schools():
    return sp.school_list()


def test_school_count_and_aliases(schools):
    roots = [s[0] for s in schools]
    assert len(roots) == 249 and len(set(roots)) == 249
    assert "washington.edu" not in roots and "indiana.edu" not in roots


def test_tenant_shape_matches_get_me():
    colors, reg = sp.load_json("school_colors.json"), sp.load_json("us_schools.json")
    tenant, ptrs = sp.build_tenant("lsu.edu", colors["lsu.edu"], reg.get("lsu.edu"))
    get_me_keys = {"pk", "sk", "id", "name", "shortName", "domains", "theme", "colorSource", "colorStatus", "timezone",
                   "lms", "tutoringResources", "pickupSpots", "categories", "openToNetwork", "createdBy", "createdAt",
                   "updatedAt"}
    assert set(tenant) == get_me_keys | {"seeded", "timezoneSource"}
    assert "autoCreated" not in tenant and tenant["seeded"] is True
    assert tenant["id"] == "lsu-edu" and tenant["sk"] == "T#lsu-edu"
    assert tenant["colorSource"] == "verified-table" and tenant["colorStatus"] == "verified"
    assert tenant["theme"] == {"primary": "#461D7C", "ink": "#FFFFFF"}
    assert tenant["timezone"] == "America/Chicago" and tenant["timezoneSource"] == "seed-estimate"
    assert tenant["lms"] == {"type": "other", "connector": "none"}
    assert tenant["openToNetwork"] is True and tenant["domains"] == reg["lsu.edu"]["domains"]
    assert ptrs == [{"pk": "DOMAIN#lsu.edu", "sk": "MAP", "tenantId": "lsu-edu"}]


def test_helpers_match_api_module():
    import api
    for root, c in sp.load_json("school_colors.json").items():
        assert sp.short_name(c["name"]) == api._short_name(c["name"])
        assert sp.tenant_id_from_root(root) == api._tenant_id_from_root(root)


def test_alias_pointers():
    colors, reg = sp.load_json("school_colors.json"), sp.load_json("us_schools.json")
    _, ptrs = sp.build_tenant("uw.edu", colors["uw.edu"], reg["uw.edu"])
    assert {p["pk"] for p in ptrs} == {"DOMAIN#uw.edu", "DOMAIN#washington.edu"}
    assert {p["tenantId"] for p in ptrs} == {"uw-edu"}


def test_full_run_counts_and_idempotency(schools):
    t = FakeTable()
    st = sp.run(sp.Store(t, sleep=lambda s: None), schools, False, log=lambda *_: None)
    assert st["tenants"] == 249 and st["skipped_tenants"] == 0
    assert st["pointers"] == 251
    assert 249 * 3 <= st["listings"] <= sp.MAX_TOTAL_LISTINGS and not st["listing_cap_hit"]
    assert t.transactions == 249
    snapshot = {k: dict(v) for k, v in t.items.items()}
    st2 = sp.run(sp.Store(t, sleep=lambda s: None), schools, False, log=lambda *_: None)
    assert (st2["tenants"], st2["pointers"], st2["listings"]) == (0, 0, 0)
    assert st2["skipped_tenants"] == 249 and st2["skipped_listings"] == st["listings"]
    assert t.items == snapshot


def test_existing_untouched_and_no_listings_for_them(schools):
    t = FakeTable()
    ua = {"pk": "TENANTS", "sk": "T#ua", "id": "ua", "name": "The University of Alabama", "theme": {"primary": "#9E1B32"}}
    t.items[("TENANTS", "T#ua")] = dict(ua)
    t.items[("DOMAIN#ua.edu", "MAP")] = {"pk": "DOMAIN#ua.edu", "sk": "MAP", "tenantId": "ua"}
    auto = {"pk": "TENANTS", "sk": "T#lsu-edu", "id": "lsu-edu", "autoCreated": True, "name": "LSU auto"}
    t.items[("TENANTS", "T#lsu-edu")] = dict(auto)
    before = {k: dict(v) for k, v in t.items.items()}
    st = sp.run(sp.Store(t), schools, False, log=lambda *_: None)
    assert st["skipped_tenants"] == 2 and st["tenants"] == 247
    for k, v in before.items():
        assert t.items[k] == v
    assert ("DOMAIN#lsu.edu", "MAP") not in t.items
    assert not [l for l in listings(t) if l["tenantId"] in ("ua", "lsu-edu")]


def test_dry_run_writes_nothing(schools):
    t = FakeTable()
    st = sp.run(sp.Store(t), schools, True, log=lambda *_: None)
    assert t.items == {} and st["tenants"] == 249 and st["listings"] > 0


def test_only_subset():
    t = FakeTable()
    sub = [s for s in sp.school_list() if s[0] in ("ua.edu", "lsu.edu")]
    st = sp.run(sp.Store(t), sub, False, log=lambda *_: None)
    assert st["tenants"] == 2 and len(tenants(t)) == 2


def test_listings_valid_and_capped(schools):
    t = FakeTable()
    sp.run(sp.Store(t), schools, False, log=lambda *_: None)
    per = {}
    ids = set()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for it in listings(t):
        per[it["tenantId"]] = per.get(it["tenantId"], 0) + 1
        assert it["demo"] is True and it["sellerName"] == "Demo seller" and it["status"] == "available"
        assert "sellerSub" not in it and it["id"] not in ids
        ids.add(it["id"])
        assert it["pk"] == f"LISTING#{it['id']}" and sp.listing_id  # id shape
        assert len(it["id"]) == 8 and it["id"].isalnum() and it["id"] == it["id"].lower()
        assert it["gsi1pk"] == f"TENANT#{it['tenantId']}#LISTINGS" and it["gsi1sk"] == it["createdAt"]
        if it.get("isbn"):
            assert matching.to_isbn13(it["isbn"]) == it["isbn"]
            assert it["gsi2pk"] == f"ISBN#{it['isbn']}" and it["gsi2sk"] == f"{it['tenantId']}#{it['id']}"
        else:
            assert "gsi2pk" not in it
        assert it["category"] in market.CATEGORIES
        assert it["price"] <= listings_api.MAX_PRICE and isinstance(it["price"], int)
        assert not listings_api._LINK_RE.search(it["title"] + it["description"])
        assert "Demo listing" in it["description"]
        assert (datetime.fromisoformat(now.replace("Z", "+00:00")) - datetime.fromisoformat(
            it["createdAt"].replace("Z", "+00:00"))).days <= 10
        if it["category"] == "tickets":
            tk = it["ticket"]
            assert tk["eventAt"] > now and it["price"] <= tk["faceValue"] and not tk["externalLink"]
            assert (datetime.fromisoformat(tk["eventAt"].replace("Z", "+00:00")) - datetime.now(timezone.utc)).days <= 60
        if it["kind"] == "service":
            assert it["category"] == "tutoring" and it["price"] <= listings_api.MAX_RATE
    assert min(per.values()) >= 3 and max(per.values()) <= 5 and len(per) == 249
    assert len(listings(t)) <= 1200
    assert any(l["isbn"] for l in listings(t) if "isbn" in l)


def test_all_book_isbns_checksum_valid():
    for title, _, _, isbn, _, _ in sp.BOOKS:
        assert matching.to_isbn13(isbn) == isbn, title


def test_validator_accepts_every_spec_for_seeded_tenant():
    colors, reg = sp.load_json("school_colors.json"), sp.load_json("us_schools.json")
    for root in ("ua.edu", "villanova.edu", "mit.edu"):
        tenant, _ = sp.build_tenant(root, colors[root], reg.get(root))
        for spec in sp.listing_specs(root):
            spec = dict(spec)
            if "ticket" in spec:
                spec["ticket"] = {k: v for k, v in spec["ticket"].items() if k != "_daysAhead"}
                spec["ticket"]["eventAt"] = "2099-01-01T19:00:00Z"
                with pytest.raises(listings_api._Bad):   # too far away: the validator really is applied
                    listings_api.validate_fields(spec, tenant, partial=False)
                continue
            listings_api.validate_fields(spec, tenant, partial=False)


def test_rerun_after_partial_failure_fills_listings(schools):
    t = FakeTable()
    sub = [s for s in schools if s[0] == "lsu.edu"]
    sp.run(sp.Store(t), sub, False, log=lambda *_: None)
    victim = next(k for k in t.items if k[0].startswith("LISTING#"))
    del t.items[victim]
    st = sp.run(sp.Store(t), sub, False, log=lambda *_: None)
    assert st["listings"] == 1 and st["tenants"] == 0


def test_transact_new_no_double_serialization():
    """transact_new must pass plain Python items to meta.client (NOT TypeSerializer wire format).
    Stubber intercepts pre-HTTP-serialization; items must arrive as plain Python, not {'S':...} dicts."""
    import boto3
    from botocore.stub import Stubber

    resource = boto3.resource("dynamodb", region_name="us-east-1")
    tbl = resource.Table("test-table")

    tenant = {"pk": "TENANTS", "sk": "T#uab-edu", "id": "uab-edu", "seeded": True}
    ptr = {"pk": "DOMAIN#uab.edu", "sk": "MAP", "tenantId": "uab-edu"}
    expected_items = [
        {"Put": {"TableName": "test-table",
                 "Item": {"pk": "TENANTS", "sk": "T#uab-edu", "id": "uab-edu", "seeded": True},
                 "ConditionExpression": "attribute_not_exists(pk)"}},
        {"Put": {"TableName": "test-table",
                 "Item": {"pk": "DOMAIN#uab.edu", "sk": "MAP", "tenantId": "uab-edu"},
                 "ConditionExpression": "attribute_not_exists(pk)"}},
    ]
    with Stubber(tbl.meta.client) as stub:
        stub.add_response("transact_write_items", {}, expected_params={"TransactItems": expected_items})
        store = sp.Store(tbl, sleep=lambda s: None)
        result = store.transact_new([tenant, ptr])
    assert result is True


def test_transact_put_items_no_double_serialization():
    """db.transact_put_items must pass plain Python items to meta.client (NOT TypeSerializer wire format)."""
    import boto3
    import os
    from botocore.stub import Stubber
    os.environ.setdefault("TABLE_NAME", "test-table")
    import lib.db as db_mod

    resource = boto3.resource("dynamodb", region_name="us-east-1")
    tbl = resource.Table("test-table")
    db_mod._table = tbl

    campus = {"pk": "TENANTS", "sk": "T#test-edu", "name": "Test U", "openToNetwork": True}
    ptr = {"pk": "DOMAIN#test.edu", "sk": "MAP", "tenantId": "test-edu"}
    expected_items = [
        {"Put": {"TableName": "test-table",
                 "Item": {"pk": "TENANTS", "sk": "T#test-edu", "name": "Test U", "openToNetwork": True},
                 "ConditionExpression": "attribute_not_exists(pk)"}},
        {"Put": {"TableName": "test-table",
                 "Item": {"pk": "DOMAIN#test.edu", "sk": "MAP", "tenantId": "test-edu"}}},
    ]
    try:
        with Stubber(tbl.meta.client) as stub:
            stub.add_response("transact_write_items", {}, expected_params={"TransactItems": expected_items})
            db_mod.transact_put_items([(campus, "attribute_not_exists(pk)"), (ptr, None)])
    finally:
        db_mod._table = None
