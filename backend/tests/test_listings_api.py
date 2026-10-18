import json
import unittest

import _market_fakes as mf
from _market_fakes import ME, OTHER, AUB, GT, add_listing
import listings_api as L
from lib import limits

REAL_GSI = L.gsi_query


def ev(body=None, qs=None):
    return {"body": json.dumps(body) if body is not None else None, "queryStringParameters": qs,
            "requestContext": {"http": {"sourceIp": "203.0.113.5"}}}


def js(r):
    return json.loads(r["body"])


GOOD = {"title": "Principles of Marketing 17th ed", "price": 45, "condition": "Like new", "category": "textbooks"}


class Base(unittest.TestCase):
    def setUp(self):
        self.db = mf.world([L])
        # seeded demo listings, in the exact layout scripts/seed.py writes
        add_listing(self.db, "demo0001", "ua", demo=True, created="2026-09-01T00:00:00Z")
        add_listing(self.db, "demo0002", "ua", title="Mini-fridge 3.2 cu ft", author=None, isbn=None, price=60, category="dorm",
                    demo=True, created="2026-09-02T00:00:00Z")
        add_listing(self.db, "demo0003", "auburn", price=30, condition="Acceptable", demo=True, created="2026-09-03T00:00:00Z")
        add_listing(self.db, "demo0004", "gatech", title="Introduction to Algorithms (CLRS) 4th ed", author="Cormen et al",
                    isbn="9780262046305", price=55, demo=True, created="2026-09-04T00:00:00Z")
        add_listing(self.db, "off00001", "offline", isbn="9781285741550", price=10, created="2026-09-05T00:00:00Z")
        add_listing(self.db, "spam0001", "spam", isbn="9781285741550", price=5, created="2026-09-06T00:00:00Z")

    def listing_ids(self, sub=ME, **qs):
        r = L.list_listings(ev(qs=qs or None), sub)
        self.assertEqual(r["statusCode"], 200, r["body"])
        return [x["id"] for x in js(r)["listings"]]

    def create(self, sub=ME, **over):
        r = L.create_listing(ev({**GOOD, **over}), sub)
        return r, (js(r).get("listing") or {})


class SeededData(Base):
    def test_demo_listings_render_with_tag_and_no_seller_identity(self):
        r = L.list_listings(ev(), ME)
        body = r["body"]
        data = js(r)
        self.assertEqual(sorted(l["id"] for l in data["listings"]), ["demo0001", "demo0002"])
        fridge = next(l for l in data["listings"] if l["id"] == "demo0002")
        self.assertTrue(fridge["demo"])
        self.assertEqual((fridge["sellerName"], fridge["author"], fridge["isbn"], fridge["price"]), ("Demo seller", "", None, 60))
        self.assertEqual(fridge["campus"], {"id": "ua", "name": "The University of Alabama", "shortName": "UA"})
        self.assertTrue(fridge["onYourCampus"])
        self.assertFalse(fridge["mine"])
        for secret in ("sellerSub", "@ua.edu", "sam1@", ME, "domains", "gsi1pk"):
            self.assertNotIn(secret, body)
        self.assertEqual(data["campus"]["pickupSpots"], ["Student Center", "Gorgas Library"])
        self.assertIn("never through this app", data["safety"])

    def test_demo_listings_cannot_be_edited_or_reported_by_owner_logic(self):
        r = L.update_listing(ev({"price": 1}), ME, "demo0001")
        self.assertEqual(r["statusCode"], 404)
        self.assertEqual(self.db.items[("LISTING#demo0001", "META")]["price"], 35)


class Scopes(Base):
    def test_campus_vs_network_and_open_tenant_rules(self):
        self.assertEqual(sorted(self.listing_ids()), ["demo0001", "demo0002"])
        net = self.listing_ids(scope="network")
        self.assertEqual(sorted(net), ["demo0001", "demo0002", "demo0003"])
        for hidden in ("demo0004", "off00001", "spam0001"):        # not open / disabled / blocked domain
            self.assertNotIn(hidden, net)

    def test_closed_campus_students_still_see_their_own_in_network_scope(self):
        add_listing(self.db, "gt000001", "gatech", created="2026-10-02T00:00:00Z")
        ids = self.listing_ids(sub=GT, scope="network")
        self.assertIn("gt000001", ids)
        self.assertIn("demo0001", ids)               # they can see open campuses
        self.assertNotIn("gt000001", self.listing_ids(sub=ME, scope="network"))   # but others cannot see theirs

    def test_on_your_campus_flag_and_campus_names(self):
        data = js(L.list_listings(ev(qs={"scope": "network"}), ME))
        flags = {l["id"]: l["onYourCampus"] for l in data["listings"]}
        self.assertEqual(flags, {"demo0001": True, "demo0002": True, "demo0003": False})
        self.assertEqual(data["campuses"]["auburn"]["name"], "Auburn University")
        self.assertEqual(data["campuses"]["auburn"]["pickupSpots"], ["Haley Center"])

    def test_scope_and_param_validation(self):
        for qs in ({"scope": "world"}, {"limit": "0"}, {"limit": "x"}, {"limit": "999"}, {"isbn": "123"}, {"before": "yesterday"},
                   {"q": "x" * 81}):
            self.assertEqual(L.list_listings(ev(qs=qs), ME)["statusCode"], 400, qs)

    def test_no_profile_and_disabled_campus(self):
        self.assertEqual(L.list_listings(ev(), "user-zzzz-9999")["statusCode"], 404)
        self.assertEqual(L.list_listings(ev(), "x")["statusCode"], 401)
        self.db.update_item("TENANTS", "T#ua", {"disabled": True})
        r = L.list_listings(ev(), ME)
        self.assertEqual((r["statusCode"], js(r)["error"]), (403, "campus_disabled"))
        self.assertEqual(L.create_listing(ev(GOOD), ME)["statusCode"], 403)

    def test_blocking_a_domain_later_hides_that_campus(self):
        self.db.put_item({"pk": "BLOCKED_DOMAINS", "sk": "D#auburn.edu"})
        self.assertNotIn("demo0003", self.listing_ids(scope="network"))

    def test_network_cap_prefers_recently_active_campuses(self):
        """With >MAX_NETWORK_TENANTS open campuses, sort by lastListingAt so active ones are shown."""
        # Add 60 extra open campuses to exceed the cap of 50
        for i in range(60):
            tid = f"extra{i:03d}"
            ts = f"2026-0{(i % 9) + 1:01d}-{(i % 28) + 1:02d}T12:00:00Z"
            self.db.put_item({"pk": "TENANTS", "sk": f"T#{tid}", "id": tid, "name": f"Extra U {i}",
                              "shortName": f"EU{i}", "domains": [f"extra{i}.edu"], "openToNetwork": True,
                              "pickupSpots": [], "categories": ["textbooks", "other"],
                              "lastListingAt": ts})
            add_listing(self.db, f"ext{i:05d}", tid, created=ts)

        # The campus with the latest lastListingAt should appear; lexicographically-first ones may not
        latest_tid = f"extra{max(range(60), key=lambda i: f'2026-0{(i % 9) + 1:01d}-{(i % 28) + 1:02d}T12:00:00Z'):03d}"
        ids = self.listing_ids(scope="network")
        # own campus always present
        self.assertIn("demo0001", ids)
        self.assertIn("demo0002", ids)
        # total tenants queried is bounded (MAX_NETWORK_TENANTS)
        tenants_represented = {self.db.items.get(("LISTING#" + lid, "META"), {}).get("tenantId") for lid in ids}
        tenants_represented.discard(None)
        self.assertLessEqual(len(tenants_represented), L.MAX_NETWORK_TENANTS)
        # the campus with the newest lastListingAt must be in the result
        self.assertIn(f"ext{max(range(60), key=lambda i: f'2026-0{(i % 9) + 1:01d}-{(i % 28) + 1:02d}T12:00:00Z'):05d}", ids)

    def test_create_listing_updates_tenant_last_listing_at(self):
        """Creating a listing sets lastListingAt on the tenant record."""
        before = self.db.items.get(("TENANTS", "T#ua"), {}).get("lastListingAt")
        self.create(sub=ME)
        after = self.db.items.get(("TENANTS", "T#ua"), {}).get("lastListingAt")
        self.assertIsNotNone(after)
        if before:
            self.assertGreaterEqual(after, before)


class Filters(Base):
    def test_q_category_course_isbn(self):
        self.assertEqual(self.listing_ids(q="fridge"), ["demo0002"])
        self.assertEqual(self.listing_ids(q="calc stew"), ["demo0001"])
        self.assertEqual(self.listing_ids(category="dorm"), ["demo0002"])
        add_listing(self.db, "course01", "ua", title="Stats", isbn=None, courseCode="MIS 405", created="2026-10-03T00:00:00Z")
        self.assertEqual(self.listing_ids(courseCode="mis405"), ["course01"])
        self.assertEqual(self.listing_ids(courseCode="MIS-405"), ["course01"])

    def test_isbn_filter_uses_index_and_respects_visibility(self):
        self.assertEqual(self.listing_ids(isbn="978-1-285-74155-0"), ["demo0001"])                      # campus
        self.assertEqual(sorted(self.listing_ids(isbn="9781285741550", scope="network")), ["demo0001", "demo0003"])
        self.assertEqual(self.listing_ids(isbn="978-0-262-04630-5"), [])  # a closed campus's book: nothing

    def test_pagination(self):
        for i in range(5):
            add_listing(self.db, f"page000{i}", "ua", title=f"Item {i}", isbn=None, created=f"2026-10-0{i + 1}T00:00:00Z")
        r = js(L.list_listings(ev(qs={"limit": "3"}), ME))
        self.assertEqual([l["id"] for l in r["listings"]], ["page0004", "page0003", "page0002"])
        self.assertEqual(r["nextBefore"], "2026-10-03T00:00:00Z")
        r2 = js(L.list_listings(ev(qs={"limit": "3", "before": r["nextBefore"]}), ME))
        self.assertEqual([l["id"] for l in r2["listings"]], ["page0001", "page0000", "demo0002"])
        r3 = js(L.list_listings(ev(qs={"limit": "3", "before": r2["nextBefore"]}), ME))
        self.assertEqual([l["id"] for l in r3["listings"]], ["demo0001"])
        self.assertIsNone(r3["nextBefore"])


class Create(Base):
    def test_create_shape_and_storage(self):
        r, l = self.create(author="Kotler & Armstrong", isbn="978-0-13-449251-3", courseCode="mis405",
                           description="Barely used.\nNo highlighting.", pickupSpot="student center", edition="17th")
        self.assertEqual(r["statusCode"], 201, r["body"])
        self.assertEqual((l["status"], l["demo"], l["mine"], l["onYourCampus"], l["sellerName"]), ("available", False, True, True, "Sam S."))
        self.assertEqual((l["isbn"], l["courseCode"], l["pickupSpot"], l["price"]), ("9780134492513", "MIS 405", "Student Center", 45))
        meta = self.db.items[(f"LISTING#{l['id']}", "META")]
        self.assertEqual((meta["sellerSub"], meta["tenantId"]), (ME, "ua"))
        self.assertEqual((meta["gsi1pk"], meta["gsi2pk"], meta["gsi2sk"]), ("TENANT#ua#LISTINGS", "ISBN#9780134492513", f"ua#{l['id']}"))
        self.assertIn((f"USER#{ME}", f"LISTING#{l['id']}"), self.db.items)
        self.assertNotIn("sellerSub", json.dumps(l))

    def test_isbn10_is_converted_and_listing_without_isbn_has_no_gsi2(self):
        _, l = self.create(isbn="0-306-40615-2")
        self.assertEqual(l["isbn"], "9780306406157")
        _, l2 = self.create(title="Desk lamp", category="dorm", price=0)
        self.assertEqual((l2["isbn"], l2["price"]), (None, 0))
        meta = self.db.items[(f"LISTING#{l2['id']}", "META")]
        self.assertNotIn("gsi2pk", meta)
        self.assertNotIn("isbn", meta)

    def test_campus_comes_from_profile_never_the_request(self):
        for field in ("tenantId", "sellerSub", "status", "demo", "id"):
            r, _ = self.create(**{field: "ua" if field != "demo" else True})
            self.assertEqual(r["statusCode"], 400, field)
        _, l = self.create(sub=AUB, category="textbooks")
        self.assertEqual(l["campus"]["id"], "auburn")

    def test_validation(self):
        bad = [{"title": "ab"}, {"title": "x" * 161}, {"title": 7}, {"price": -1}, {"price": 1001}, {"price": "5"}, {"price": True},
               {"price": None}, {"condition": "Great"}, {"condition": None}, {"category": "weapons"}, {"category": None},
               {"isbn": "9781285741551"}, {"isbn": 5}, {"description": "d" * 501}, {"pickupSpot": "Behind the dumpster"},
               {"author": "a" * 121}, {"description": "see https://evil.example/pay"}, {"description": "go to www.evil.example"},
               {"title": "Buy at javascript:alert(1)"}, {"description": "visit //evil.example"}]
        for over in bad:
            r, _ = self.create(**over)
            self.assertEqual(r["statusCode"], 400, over)
        self.assertEqual(L.create_listing({"body": "{nope"}, ME)["statusCode"], 400)
        self.assertEqual(L.create_listing({"body": "[]"}, ME)["statusCode"], 400)
        self.assertFalse([k for k in self.db.items if k[0].startswith("LISTING#") and k[0] not in
                          {"LISTING#demo0001", "LISTING#demo0002", "LISTING#demo0003", "LISTING#demo0004", "LISTING#off00001", "LISTING#spam0001"}])

    def test_text_is_cleaned_and_price_rounded(self):
        _, l = self.create(title="Quiz‮​ Book\x00", description="a​b", price=12.349)
        self.assertEqual((l["title"], l["description"], l["price"]), ("Quiz Book", "ab", 12.35))

    def test_seller_name_never_exposes_email(self):
        _, l = self.create(sub=OTHER)
        self.assertEqual(l["sellerName"], "Student")      # displayName equals the email local part
        self.assertEqual(L.seller_name({"displayName": "a@b.com"}), "Student")
        self.assertEqual(L.seller_name({"displayName": "Luca Strachan", "email": "pat@ua.edu"}), "Luca S.")
        self.assertEqual(L.seller_name({}), "Student")

    def test_daily_cap_rate_limit_and_active_cap(self):
        codes = [self.create(title=f"Book number {i}")[0]["statusCode"] for i in range(L.DAILY_LISTINGS + 2)]
        self.assertEqual(codes[:L.DAILY_LISTINGS], [201] * L.DAILY_LISTINGS)
        self.assertEqual(codes[-1], 429)
        self.assertEqual(js(self.create()[0])["error"], "daily_cap")

    def test_active_cap(self):
        for i in range(L.MAX_ACTIVE):
            self.db.put_item({"pk": f"USER#{AUB}", "sk": f"LISTING#act{i:05d}", "id": f"act{i:05d}", "status": "available"})
        r, _ = self.create(sub=AUB)
        self.assertEqual((r["statusCode"], js(r)["error"]), (409, "limit"))
        self.db.update_item(f"USER#{AUB}", "LISTING#act00000", {"status": "sold"})   # a sold one frees a slot
        self.assertEqual(self.create(sub=AUB)[0]["statusCode"], 201)

    def test_per_minute_write_limit(self):
        per_min = limits.USER_LIMITS["default"][0]
        L.DAILY_LISTINGS = 10_000
        try:
            codes = [self.create(title=f"Lot {i} of books")[0]["statusCode"] for i in range(per_min + 3)]
        finally:
            L.DAILY_LISTINGS = 10
        self.assertIn(429, codes)


class Mine(Base):
    def test_mine_scope(self):
        _, a = self.create(title="My book one")
        _, b = self.create(title="My book two")
        L.update_listing(ev({"status": "sold"}), ME, b["id"])
        _, c = self.create(title="My book three")
        L.update_listing(ev({"status": "removed"}), ME, c["id"])
        mine = js(L.list_listings(ev(qs={"scope": "mine"}), ME))["listings"]
        self.assertEqual(sorted(m["title"] for m in mine), ["My book one", "My book two"])
        self.assertTrue(all(m["mine"] for m in mine))
        self.assertEqual(js(L.list_listings(ev(qs={"scope": "mine"}), OTHER))["listings"], [])


class Patch(Base):
    def setUp(self):
        super().setUp()
        self.l = self.create(isbn="9780134492513")[1]
        self.id = self.l["id"]

    def patch(self, body, sub=ME, lid=None):
        return L.update_listing(ev(body), sub, lid or self.id)

    def test_owner_edits_and_marks_sold(self):
        r = self.patch({"price": 40, "condition": "Good"})
        self.assertEqual((r["statusCode"], js(r)["listing"]["price"], js(r)["listing"]["condition"]), (200, 40, "Good"))
        self.assertEqual(self.db.items[(f"LISTING#{self.id}", "META")]["price"], 40)
        self.assertIn(self.id, self.listing_ids(sub=OTHER))
        r = self.patch({"status": "sold"})
        self.assertEqual(js(r)["listing"]["status"], "sold")
        self.assertNotIn(self.id, self.listing_ids(sub=OTHER))           # hidden from others
        self.assertNotIn(self.id, self.listing_ids(sub=ME))              # and from the public lists
        self.assertEqual(self.db.items[(f"USER#{ME}", f"LISTING#{self.id}")]["status"], "sold")
        self.assertEqual(js(self.patch({"status": "available"}))["listing"]["status"], "available")

    def test_idor_other_user_cannot_edit_or_mark_sold_or_remove(self):
        before = dict(self.db.items[(f"LISTING#{self.id}", "META")])
        for body in ({"price": 1}, {"status": "removed"}, {"status": "sold"}, {"title": "hijacked"}):
            r = self.patch(body, sub=OTHER)
            self.assertEqual((r["statusCode"], js(r)["error"]), (404, "not_found"), body)
            r = self.patch(body, sub=AUB)
            self.assertEqual(r["statusCode"], 404)
        self.assertEqual(self.db.items[(f"LISTING#{self.id}", "META")], before)

    def test_database_level_owner_guard(self):
        with self.assertRaises(L._Bad) as cm:
            L._update_item(f"LISTING#{self.id}", "META", {"price": 1}, [], OTHER)
        self.assertEqual(cm.exception.status, 404)
        self.assertEqual(self.db.items[(f"LISTING#{self.id}", "META")]["price"], 45)

    def test_unknown_malformed_ids(self):
        for bad in ("nope", "ABCDEFGH", "../../x", "toolongid12"):
            self.assertEqual(self.patch({"price": 1}, lid=bad)["statusCode"], 404)
        self.assertEqual(self.patch({"price": 1}, lid="zzzzzzzz")["statusCode"], 404)

    def test_forbidden_fields_and_validation(self):
        for body in ({}, {"tenantId": "auburn"}, {"sellerSub": OTHER}, {"id": "x"}, {"demo": True}, {"flagged": False},
                     {"status": "hidden"}, {"price": -5}, {"isbn": "123"}, {"category": "weapons"}, {"title": ""},
                     {"description": "http://evil.example"}):
            self.assertEqual(self.patch(body)["statusCode"], 400, body)

    def test_isbn_edit_keeps_index_in_sync(self):
        r = self.patch({"isbn": "9781285741550"})
        meta = self.db.items[(f"LISTING#{self.id}", "META")]
        self.assertEqual((meta["isbn"], meta["gsi2pk"], meta["gsi2sk"]), ("9781285741550", "ISBN#9781285741550", f"ua#{self.id}"))
        self.assertIn(self.id, self.listing_ids(isbn="9781285741550"))
        self.assertNotIn(self.id, self.listing_ids(isbn="9780134492513"))
        r = self.patch({"isbn": None})
        meta = self.db.items[(f"LISTING#{self.id}", "META")]
        self.assertTrue(all(k not in meta for k in ("isbn", "gsi2pk", "gsi2sk")))
        self.assertIsNone(js(r)["listing"]["isbn"])

    def test_noop_changes_nothing(self):
        before = self.db.items[(f"LISTING#{self.id}", "META")]["updatedAt"]
        self.patch({"price": 45})
        self.assertEqual(self.db.items[(f"LISTING#{self.id}", "META")]["updatedAt"], before)


class Report(Base):
    def setUp(self):
        super().setUp()
        self.id = self.create(sub=ME)[1]["id"]

    def report(self, sub, reason="spam", lid=None, **extra):
        return L.report_listing(ev({"reason": reason, **extra}), sub, lid or self.id)

    def test_report_idempotent_and_flags_at_threshold(self):
        self.assertEqual(js(self.report(OTHER, note="looks fake"))["reported"], True)
        self.report(OTHER)                                        # repeat: counted once
        self.assertEqual(len(self.db.query_pk(f"LISTING#{self.id}", "REPORT#")), 1)
        self.report(AUB)
        self.assertNotIn("flagged", self.db.items[(f"LISTING#{self.id}", "META")])
        add_listing(self.db, "x", "ua")       # unrelated
        self.db.put_item({"pk": "USER#user-eeee-5555", "sk": "PROFILE", "sub": "user-eeee-5555", "email": "e@ua.edu", "tenantId": "ua", "displayName": "Eve Ua"})
        self.report("user-eeee-5555")
        self.assertTrue(self.db.items[(f"LISTING#{self.id}", "META")]["flagged"])
        self.assertNotIn(self.id, self.listing_ids(sub=OTHER))     # hidden from others once flagged
        mine = js(L.list_listings(ev(qs={"scope": "mine"}), ME))["listings"]
        self.assertTrue(mine[0]["flagged"])                        # owner still sees it

    def test_reporter_is_stored_as_a_hash_only(self):
        self.report(OTHER, note="x")
        sks = [k[1] for k in self.db.items if k[0] == f"LISTING#{self.id}" and k[1].startswith("REPORT#")]
        self.assertEqual(len(sks), 1)
        self.assertNotIn(OTHER, json.dumps(self.db.items[(f"LISTING#{self.id}", sks[0])]) + sks[0])
        self.assertIn("ttl", self.db.items[(f"LISTING#{self.id}", sks[0])])

    def test_rules(self):
        self.assertEqual(self.report(ME)["statusCode"], 400)                       # own listing
        self.assertEqual(self.report(OTHER, reason="rude")["statusCode"], 400)
        self.assertEqual(self.report(OTHER, note="n" * 201)["statusCode"], 400)
        self.assertEqual(self.report(OTHER, lid="zzzzzzzz")["statusCode"], 404)
        self.assertEqual(self.report(OTHER, lid="BAD")["statusCode"], 404)
        self.assertEqual(self.report(OTHER, lid="spam0001")["statusCode"], 404)   # listing on a blocked campus
        self.assertEqual(self.report(ME, lid="demo0004")["statusCode"], 404)      # and on a campus that is not open
        self.assertEqual(self.report(OTHER, extra=1)["statusCode"], 400)

    def test_daily_cap(self):
        codes = []
        for i in range(L.DAILY_REPORTS + 2):
            other = f"zzzz{i:04d}"
            self.db.put_item({"pk": f"USER#user-r{i:04d}", "sk": "PROFILE"})
            lid = f"rep{i:05d}"
            add_listing(self.db, lid, "ua", seller=AUB, created="2026-10-02T00:00:00Z")
            codes.append(self.report(OTHER, lid=lid)["statusCode"])
        self.assertIn(429, codes)


class RealGsiQuery(unittest.TestCase):
    def test_follows_pagination_filters_non_listings_and_targets_the_index(self):
        calls = []

        class T:
            def query(self, **kw):
                calls.append(dict(kw))
                if "ExclusiveStartKey" not in kw:
                    return {"Items": [{"pk": "LISTING#a", "sk": "META"}, {"pk": "USER#x", "sk": "PROFILE"}], "LastEvaluatedKey": {"k": 1}}
                return {"Items": [{"pk": "LISTING#b", "sk": "META"}, {"pk": "LISTING#b", "sk": "REPORT#1"}]}

        L._table = lambda: T()
        items = REAL_GSI("gsi1", "TENANT#ua#LISTINGS")
        self.assertEqual([i["pk"] for i in items], ["LISTING#a", "LISTING#b"])
        self.assertEqual([c["IndexName"] for c in calls], ["gsi1", "gsi1"])
        self.assertFalse(calls[0]["ScanIndexForward"])
        self.assertEqual(len(REAL_GSI("gsi2", "ISBN#1", limit=1)), 1)
        with self.assertRaises(KeyError):
            REAL_GSI("gsi9", "x")


if __name__ == "__main__":
    unittest.main()
