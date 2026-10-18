"""scripts/seed_market_rich.py against a strict fake table. No AWS."""
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND.parent / "scripts"
for p in (str(BACKEND), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import seed_market_rich as mr  # noqa: E402
import seed_popular as sp  # noqa: E402
import listings_api  # noqa: E402
from lib import market, matching  # noqa: E402
from tests.test_seed_popular import FakeTable  # noqa: E402


class StrictTable(FakeTable):
    """Rejects floats and empty strings in keys, like DynamoDB."""

    def put_item(self, Item, ConditionExpression=None):
        def walk(v):
            assert not isinstance(v, float), f"float in item: {v}"
            if isinstance(v, dict):
                [walk(x) for x in v.values()]
            if isinstance(v, list):
                [walk(x) for x in v]
        walk(Item)
        if Item["pk"].startswith("LISTING#"):
            assert Item["gsi1pk"] and Item["gsi1sk"]
        return super().put_item(Item, ConditionExpression)


MANIFEST = {s: f"alt {s}" for s in mr.DEFAULT_ALT}


def world():
    t = StrictTable()
    sp.run(sp.Store(t), [s for s in sp.school_list() if s[0] in {r for _, r in mr.TARGETS if r not in ("ua.edu", "auburn.edu", "gatech.edu")}],
           False, log=lambda *_: None)
    # curated campuses as seed.py writes them (narrow categories, real pickup spots)
    for tid, name, spots, cats in (
            ("ua", "The University of Alabama", ["The Ferguson Center (Ferg)", "Gorgas Library"], ["textbooks", "dorm", "electronics", "clothing", "tickets", "other"]),
            ("auburn", "Auburn University", ["Haley Center", "RBD Library"], ["textbooks", "dorm", "electronics", "clothing", "tickets", "other"]),
            ("gatech", "Georgia Institute of Technology", ["Student Center"], ["textbooks", "dorm", "electronics", "lab supplies", "tickets", "other"])):
        t.items[("TENANTS", f"T#{tid}")] = {"pk": "TENANTS", "sk": f"T#{tid}", "id": tid, "name": name, "pickupSpots": spots,
                                            "categories": cats, "openToNetwork": True}
    return t


def rich(t):
    return [v for (p, _), v in t.items.items() if p.startswith("LISTING#") and v["id"] in {
        mr.listing_id(tid, g) for tid, _ in mr.TARGETS for g in mr.CORE + mr.EXTRAS}]


def test_counts_and_idempotency():
    t = world()
    before = len(t.items)
    st = mr.run(sp.Store(t), mr.TARGETS, False, MANIFEST, log=lambda *_: None)
    assert st["campuses"] == 15 and st["missing_campuses"] == 0
    assert 15 * 16 <= st["listings"] <= 15 * 20
    assert len(t.items) == before + st["listings"]
    snap = {k: dict(v) for k, v in t.items.items()}
    st2 = mr.run(sp.Store(t), mr.TARGETS, False, MANIFEST, log=lambda *_: None)
    assert st2["listings"] == 0 and st2["skipped_listings"] == st["listings"] and t.items == snap


def test_no_collision_with_seed_popular_and_tenants_untouched():
    t = world()
    sp_ids = {sp.listing_id(sp.tenant_id_from_root(r), s) for _, r in mr.TARGETS for s in range(5)}
    rich_ids = {mr.listing_id(tid, g) for tid, _ in mr.TARGETS for g in mr.CORE + mr.EXTRAS}
    assert not sp_ids & rich_ids
    tenants_before = {k: dict(v) for k, v in t.items.items() if k[0] == "TENANTS"}
    mr.run(sp.Store(t), mr.TARGETS, False, MANIFEST, log=lambda *_: None)
    assert {k: v for k, v in t.items.items() if k[0] == "TENANTS"} == tenants_before


def test_dry_run_and_missing_campus():
    t = StrictTable()
    st = mr.run(sp.Store(t), mr.TARGETS, True, MANIFEST, log=lambda *_: None)
    assert t.items == {} and st["missing_campuses"] == 15 and st["listings"] == 0
    st = mr.run(sp.EmptyStore(), mr.TARGETS, True, MANIFEST, assume_empty=True, log=lambda *_: None)
    assert st["campuses"] == 15 and st["listings"] >= 240


def test_every_item_valid_and_diverse():
    t = world()
    mr.run(sp.Store(t), mr.TARGETS, False, MANIFEST, log=lambda *_: None)
    now = datetime.now(timezone.utc)
    by_campus = {}
    for it in rich(t):
        by_campus.setdefault(it["tenantId"], []).append(it)
        assert it["demo"] is True and it["sellerName"] == "Demo seller" and "sellerSub" not in it
        assert "Demo listing" in it["description"] and it["status"] == "available"
        assert it["gsi1pk"] == f"TENANT#{it['tenantId']}#LISTINGS" and it["gsi1sk"] == it["createdAt"]
        age = now - datetime.fromisoformat(it["createdAt"].replace("Z", "+00:00"))
        assert 0 <= age.days <= 12
        assert not listings_api._LINK_RE.search(it["title"] + it["description"])
        if it.get("isbn"):
            assert matching.to_isbn13(it["isbn"]) == it["isbn"] and it["gsi2pk"] == f"ISBN#{it['isbn']}"
        if it["kind"] == "free":
            assert it["price"] == 0
        if it["kind"] == "trade":
            assert it["tradeFor"]
        if it["category"] == "tickets":
            tk = it["ticket"]
            d = (datetime.fromisoformat(tk["eventAt"].replace("Z", "+00:00")) - now).days
            assert 0 <= d <= 60 and it["price"] <= tk["faceValue"] and tk["transferMethod"] == "official_app" and not tk["externalLink"]
        if it["kind"] == "service":
            assert 15 <= it["price"] <= 40 and it["tutoring"]["courseCodes"]
        if it["pickupSpot"]:
            spots = t.items[("TENANTS", f"T#{it['tenantId']}")]["pickupSpots"]
            assert it["pickupSpot"] in spots
        for img in it["images"]:
            assert img["url"].startswith("/demo/market/") and img["url"].endswith(".svg") and img["alt"]
    assert len(by_campus) == 15
    for tid, items in by_campus.items():
        assert 16 <= len(items) <= 20 <= mr.MAX_PER_CAMPUS
        assert {i["kind"] for i in items} == set(market.KINDS)
        assert set(market.CATEGORIES) <= {i["category"] for i in items}
        assert {"MIS 405", "MIS 430"} & {i["courseCode"] for i in items}


def test_images_follow_manifest():
    tenant = world().items[("TENANTS", "T#ua")]
    items = mr.build_items(tenant, "ua.edu", MANIFEST)
    assert sum(1 for i in items if i["images"]) >= len(items) - 2   # only the ride post has no picture
    assert mr.build_items(tenant, "ua.edu", None)[0]["images"] == []
    partial = mr.build_items(tenant, "ua.edu", {"textbook-mis": "MIS book"})
    assert all(i["images"] == [] or i["images"][0]["url"] == "/demo/market/textbook-mis.svg" for i in partial)


def test_manifest_parsing_shapes(tmp_path):
    assert mr.parse_manifest({"bike": {"alt": "A bike", "file": "bike.svg"}}) == {"bike": "A bike"}
    assert mr.parse_manifest({"bike": "A bike"}) == {"bike": "A bike"}
    assert mr.parse_manifest([{"slug": "bike", "alt": "A bike"}, {"file": "monitor.svg", "alt": "M"}]) == {"bike": "A bike", "monitor": "M"}
    assert mr.parse_manifest({"images": [{"slug": "bike", "alt": "A bike"}]}) == {"bike": "A bike"}
    assert mr.parse_manifest("junk") == {} and mr.parse_manifest(None) == {}
    assert mr.load_manifest(tmp_path / "nope.json") is None
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"bike": "A bike"}))
    assert mr.load_manifest(p) == {"bike": "A bike"}


def test_all_slugs_known():
    for group in mr.G.values():
        if isinstance(group, list):
            for v in group:
                assert v["slug"] is None or v["slug"] in mr.DEFAULT_ALT
