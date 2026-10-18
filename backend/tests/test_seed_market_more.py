"""scripts/seed_market_more.py against a strict fake table. No AWS."""
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
for p in (str(BACKEND), str(BACKEND.parent / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import seed_market_more as mm  # noqa: E402
import seed_market_rich as mr  # noqa: E402
import seed_popular as sp  # noqa: E402
import listings_api  # noqa: E402
from lib import matching  # noqa: E402
from tests.test_seed_market_rich import StrictTable, MANIFEST as RICH_MANIFEST  # noqa: E402

MANIFEST = {**RICH_MANIFEST, "fallback-tickets": "Tickets", "fallback-tutoring": "Tutoring"}


def world(only=None):
    t = StrictTable()
    roots = {r for _, r in mm.TARGETS}
    sp.run(sp.Store(t), [s for s in sp.school_list() if s[0] in roots and s[0] not in ("ua.edu", "auburn.edu", "gatech.edu")],
           False, log=lambda *_: None)
    for tid, spots in (("ua", ["Gorgas Library", "Student center"]), ("auburn", ["Haley Center"]), ("gatech", ["Student Center"])):
        t.items[("TENANTS", f"T#{tid}")] = {"pk": "TENANTS", "sk": f"T#{tid}", "id": tid, "name": tid, "pickupSpots": spots,
                                            "categories": ["textbooks", "other"], "openToNetwork": True}
    return t


def mine(t):
    return [v for (p, _), v in t.items.items() if p.startswith("LISTING#") and mm.listing_id(v["tenantId"], "x") != v["id"]
            and v["id"] in IDS]


IDS = set()


def test_counts_idempotent_and_valid():
    t = world()
    st = mm.run(sp.Store(t), mm.TARGETS, False, MANIFEST, log=lambda *_: None)
    assert st["campuses"] == 45 and st["missing_campuses"] == 0 and st["dropped_by_cap"] == 0
    snap = {k: dict(v) for k, v in t.items.items()}
    st2 = mm.run(sp.Store(t), mm.TARGETS, False, MANIFEST, log=lambda *_: None)
    assert st2["tickets"] == st2["tutoring"] == 0 and st2["skipped"] == st["tickets"] + st["tutoring"] and t.items == snap
    now = datetime.now(timezone.utc)
    per = {}
    for (pk, _), it in t.items.items():
        if not pk.startswith("LISTING#") or it["id"] not in {mm.listing_id(i["tenantId"], k) for i in [it] for k in
                                                              [f"{a}:{b}" for a in "tuwx" for b in [x[0] for x in mm.EVENTS] + [x[0] for x in mm.TUTORS]]}:
            continue
        per.setdefault(it["tenantId"], []).append(it)
        assert it["demo"] is True and it["sellerName"] == "Demo seller" and "Demo listing" in it["description"]
        assert not listings_api._LINK_RE.search(it["title"] + it["description"])
        age = now - datetime.fromisoformat(it["createdAt"].replace("Z", "+00:00"))
        assert 0 <= age.days <= 12
        spots = t.items[("TENANTS", f"T#{it['tenantId']}")]["pickupSpots"]
        assert not it["pickupSpot"] or it["pickupSpot"] in spots
        if it["category"] == "tickets":
            tk = it["ticket"]
            d = (datetime.fromisoformat(tk["eventAt"].replace("Z", "+00:00")) - now).days
            assert 2 <= d <= 60 and tk["transferMethod"] == "official_app" and not tk["externalLink"]
            if it["kind"] == "sell":
                assert it["price"] <= tk["faceValue"] and 1 <= tk["quantity"] <= 4
            assert it["images"] and it["images"][0]["url"].startswith("/demo/market/")
        else:
            assert it["category"] == "tutoring" and it["tutoring"]["courseCodes"]
            if it["kind"] == "service":
                assert 0 <= it["price"] <= 45
    assert len(per) == 45
    for tid, items in per.items():
        sell_t = [i for i in items if i["category"] == "tickets" and i["kind"] == "sell"]
        wt = [i for i in items if i["category"] == "tickets" and i["kind"] == "wanted"]
        tu = [i for i in items if i["kind"] == "service"]
        assert 8 <= len(sell_t) <= 14 and len(wt) == 2 and 10 <= len(tu) <= 16
        assert len({i["tutoring"]["courseCodes"][0] for i in tu}) == len(tu)


def test_total_per_campus_under_cap_with_existing():
    t = world()
    mr.run(sp.Store(t), mr.TARGETS, False, MANIFEST, log=lambda *_: None)
    mm.run(sp.Store(t), mm.TARGETS, False, MANIFEST, log=lambda *_: None)
    count = {}
    for (pk, _), it in t.items.items():
        if pk.startswith("LISTING#"):
            count[it["tenantId"]] = count.get(it["tenantId"], 0) + 1
    assert max(count.values()) <= mm.MAX_PER_CAMPUS


def test_ua_required_tutors():
    ua = world().items[("TENANTS", "T#ua")]
    items, _ = mm.build_items(ua, "ua.edu", MANIFEST)
    codes = {c for i in items if i["kind"] == "service" for c in i["tutoring"]["courseCodes"]}
    assert set(mm.UA_REQUIRED) <= codes
    assert any(i["kind"] == "wanted" and i["category"] == "tutoring" for i in items)


def test_cap_drops_extras(monkeypatch):
    ua = world().items[("TENANTS", "T#ua")]
    monkeypatch.setattr(mm, "existing_estimate", lambda r, t: 50)
    items, dropped = mm.build_items(ua, "ua.edu", MANIFEST)
    assert len(items) == 10 and dropped > 0
    monkeypatch.setattr(mm, "existing_estimate", lambda r, t: 60)
    assert mm.build_items(ua, "ua.edu", MANIFEST)[0] == []


def test_ids_distinct_from_other_scripts_and_dry_run():
    t = world()
    other = {mr.listing_id(tid, g) for tid, _ in mr.TARGETS for g in mr.CORE + mr.EXTRAS}
    other |= {sp.listing_id(tid, s) for tid, _ in mm.TARGETS for s in range(5)}
    items = []
    for tid, root in mm.TARGETS:
        items += mm.build_items(t.items[("TENANTS", f"T#{tid}")], root, MANIFEST)[0]
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)) and not set(ids) & other
    before = dict(t.items)
    mm.run(sp.Store(t), mm.TARGETS, True, MANIFEST, log=lambda *_: None)
    assert t.items == before


def test_no_manifest_no_images():
    ua = world().items[("TENANTS", "T#ua")]
    assert all(i["images"] == [] for i in mm.build_items(ua, "ua.edu", None)[0])
