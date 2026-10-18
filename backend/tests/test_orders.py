"""Tests for Orders feature: POST /listings/{id}/orders, PATCH, GET."""
import json
import unittest

import _fakes
import listings_api
import orders_api
from lib import limits as _real_limits

ME = "user-buyer-0001"
SELLER = "user-seller-0001"
LID = "lst00001"   # normal sell listing
DLID = "dmo00001"  # demo listing
OTHER = "user-other-0002"


def ev(body=None, qs=None):
    return {"body": json.dumps(body) if body is not None else None, "queryStringParameters": qs or {}}


def js(resp):
    return json.loads(resp["body"])


class OrderDb(_fakes.FakeDb):
    def table(self):
        return None


def _make_base_db():
    fdb = OrderDb()
    # Buyer profile
    fdb.put_item({"pk": f"USER#{ME}", "sk": "PROFILE", "sub": ME,
                  "firstName": "Ava", "lastName": "Torres", "displayName": "Ava T.",
                  "tenantId": "t1", "email": "ava@ua.edu"})
    # Seller profile
    fdb.put_item({"pk": f"USER#{SELLER}", "sk": "PROFILE", "sub": SELLER,
                  "firstName": "Ben", "lastName": "Kim", "displayName": "Ben K.",
                  "tenantId": "t1", "email": "student@example.edu"})
    # Other user
    fdb.put_item({"pk": f"USER#{OTHER}", "sk": "PROFILE", "sub": OTHER,
                  "firstName": "Cara", "lastName": "Lee", "displayName": "Cara L.",
                  "tenantId": "t1", "email": "student2@example.edu"})
    # Normal sell listing
    fdb.put_item({"pk": f"LISTING#{LID}", "sk": "META", "id": LID,
                  "title": "Calculus Book", "price": "25.00", "category": "textbooks",
                  "kind": "sell", "status": "available", "tenantId": "t1",
                  "sellerSub": SELLER, "sellerName": "Ben K.", "demo": False,
                  "images": ["https://cdn.example.com/img1.jpg"]})
    # Demo listing
    fdb.put_item({"pk": f"LISTING#{DLID}", "sk": "META", "id": DLID,
                  "title": "Demo Chair", "price": "10.00", "category": "furniture",
                  "kind": "sell", "status": "available", "tenantId": "t1",
                  "sellerSub": "demo-seller-sys", "sellerName": "SemOS Demo",
                  "demo": True, "images": []})
    return fdb


TENANT = {"id": "t1", "name": "UA", "openToNetwork": True}


def _patch(target, attr, value, restore_on=None):
    """Helper to swap a module attribute and return the old value."""
    old = getattr(target, attr)
    setattr(target, attr, value)
    return old


class Base(unittest.TestCase):
    def setUp(self):
        self.db = _make_base_db()
        orders_api.db = self.db
        listings_api.db = self.db
        # Bypass rate limits
        self._real_check_user = orders_api.limits.check_user
        orders_api.limits.check_user = lambda *a, **kw: None
        # Bypass viewer (returns fake profile + tenant for any sub)
        self._real_viewer = listings_api.viewer
        listings_api.viewer = lambda sub: (None, self.db.get_item(f"USER#{sub}", "PROFILE"), TENANT)
        self._real_visible = listings_api.visible_tenants
        listings_api.visible_tenants = lambda t: {"t1": t}

    def tearDown(self):
        orders_api.limits.check_user = self._real_check_user
        listings_api.viewer = self._real_viewer
        listings_api.visible_tenants = self._real_visible


class OrderCreate(Base):
    def _create(self, sub=ME, lid=LID, body=None):
        if body is None:
            body = {"method": "pickup"}
        return orders_api.create_order(ev(body), sub, lid)

    def test_create_success_fields(self):
        r = self._create()
        self.assertEqual(r["statusCode"], 200)
        o = js(r)["order"]
        self.assertEqual(o["status"], "paid")
        self.assertEqual(o["role"], "buying")
        self.assertEqual(o["amountCents"], 2500)
        self.assertEqual(o["method"], "pickup")
        self.assertTrue(o["demo"])
        self.assertIn("id", o)
        self.assertEqual(o["listing"]["title"], "Calculus Book")
        self.assertEqual(o["listing"]["image"], "https://cdn.example.com/img1.jpg")
        self.assertEqual(o["counterpart"]["name"], "Ben K.")
        self.assertIn("paid", [t["status"] for t in o["timeline"]])

    def test_listing_becomes_pending(self):
        self._create()
        listing = self.db.get_item(f"LISTING#{LID}", "META")
        self.assertEqual(listing["status"], "pending")

    def test_buyer_pointers_stored(self):
        r = self._create()
        oid = js(r)["order"]["id"]
        ptrs = self.db.query_pk(f"USER#{ME}", "ORDER#buying#")
        self.assertTrue(any(p["orderId"] == oid for p in ptrs))

    def test_seller_pointer_stored(self):
        r = self._create()
        oid = js(r)["order"]["id"]
        ptrs = self.db.query_pk(f"USER#{SELLER}", "ORDER#selling#")
        self.assertTrue(any(p["orderId"] == oid for p in ptrs))

    def test_seller_cannot_order_own_listing(self):
        r = self._create(sub=SELLER)
        self.assertEqual(r["statusCode"], 400)
        self.assertEqual(js(r)["error"], "own_listing")

    def test_duplicate_rejected_when_listing_pending(self):
        self._create()  # first order makes listing pending
        r = self._create()  # second attempt
        self.assertEqual(r["statusCode"], 404)  # listing not available -> 404

    def test_wanted_listing_rejected(self):
        self.db.put_item({"pk": "LISTING#wnt00001", "sk": "META", "id": "wnt00001",
                          "title": "Want notebook", "kind": "wanted", "status": "available",
                          "tenantId": "t1", "sellerSub": SELLER})
        r = self._create(lid="wnt00001")
        self.assertEqual(r["statusCode"], 400)
        self.assertEqual(js(r)["error"], "not_orderable")

    def test_missing_method_rejected(self):
        r = self._create(body={"note": "please"})
        self.assertEqual(r["statusCode"], 400)
        self.assertEqual(js(r)["error"], "validation_error")

    def test_invalid_listing_id_is_404(self):
        r = orders_api.create_order(ev({"method": "pickup"}), ME, "not-valid")
        self.assertEqual(r["statusCode"], 404)

    def test_note_stored(self):
        r = self._create(body={"method": "ship", "note": "pls wrap carefully"})
        self.assertEqual(js(r)["order"]["note"], "pls wrap carefully")


class OrderFlow(Base):
    def setUp(self):
        super().setUp()
        r = orders_api.create_order(ev({"method": "pickup"}), ME, LID)
        self.oid = js(r)["order"]["id"]

    def _patch(self, sub, action):
        return orders_api.patch_order(ev({"action": action}), sub, self.oid)

    def test_seller_marks_handed_over(self):
        r = self._patch(SELLER, "handed_over")
        self.assertEqual(r["statusCode"], 200)
        o = js(r)["order"]
        self.assertEqual(o["status"], "handed_over")
        statuses = [t["status"] for t in o["timeline"]]
        self.assertIn("handed_over", statuses)

    def test_buyer_receives_after_handover(self):
        self._patch(SELLER, "handed_over")
        r = self._patch(ME, "received")
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(js(r)["order"]["status"], "completed")
        listing = self.db.get_item(f"LISTING#{LID}", "META")
        self.assertEqual(listing["status"], "sold")

    def test_buyer_cancel_before_handover(self):
        r = self._patch(ME, "cancel")
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(js(r)["order"]["status"], "refunded")
        listing = self.db.get_item(f"LISTING#{LID}", "META")
        self.assertEqual(listing["status"], "available")

    def test_seller_decline_refunds(self):
        r = self._patch(SELLER, "decline")
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(js(r)["order"]["status"], "refunded")
        listing = self.db.get_item(f"LISTING#{LID}", "META")
        self.assertEqual(listing["status"], "available")

    def test_buyer_cannot_mark_handed_over(self):
        r = self._patch(ME, "handed_over")
        self.assertEqual(r["statusCode"], 403)

    def test_seller_cannot_cancel(self):
        r = self._patch(SELLER, "cancel")
        self.assertEqual(r["statusCode"], 403)

    def test_buyer_cannot_receive_before_handover(self):
        r = self._patch(ME, "received")
        self.assertEqual(r["statusCode"], 409)

    def test_third_party_sees_404(self):
        r = orders_api.patch_order(ev({"action": "cancel"}), OTHER, self.oid)
        self.assertEqual(r["statusCode"], 404)

    def test_cannot_cancel_after_handover(self):
        self._patch(SELLER, "handed_over")
        r = self._patch(ME, "cancel")
        self.assertEqual(r["statusCode"], 409)

    def test_invalid_action_rejected(self):
        r = orders_api.patch_order(ev({"action": "delete"}), ME, self.oid)
        self.assertEqual(r["statusCode"], 400)


class OrderDemo(Base):
    def setUp(self):
        super().setUp()
        r = orders_api.create_order(ev({"method": "pickup"}), ME, DLID)
        self.oid = js(r)["order"]["id"]

    def test_demo_listing_shows_handed_over_at_read_time(self):
        o = js(orders_api.get_order(ev(), ME, self.oid))["order"]
        self.assertEqual(o["status"], "handed_over")

    def test_demo_buyer_can_confirm_received(self):
        r = orders_api.patch_order(ev({"action": "received"}), ME, self.oid)
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(js(r)["order"]["status"], "completed")
        listing = self.db.get_item(f"LISTING#{DLID}", "META")
        self.assertEqual(listing["status"], "sold")

    def test_demo_buyer_cannot_cancel(self):
        # eff_status is handed_over, so cancel (which requires eff_status == paid) is rejected
        r = orders_api.patch_order(ev({"action": "cancel"}), ME, self.oid)
        self.assertEqual(r["statusCode"], 409)


class OrderList(Base):
    def setUp(self):
        super().setUp()
        # Create two orders: ME buys LID, OTHER buys a second listing
        self.db.put_item({"pk": "LISTING#lst00002", "sk": "META", "id": "lst00002",
                          "title": "Chair", "price": "15.00", "kind": "sell",
                          "status": "available", "tenantId": "t1",
                          "sellerSub": SELLER, "sellerName": "Ben K.", "demo": False, "images": []})
        orders_api.create_order(ev({"method": "pickup"}), ME, LID)
        orders_api.create_order(ev({"method": "ship"}), OTHER, "lst00002")

    def test_list_buying_returns_my_orders(self):
        r = orders_api.list_orders(ev(qs={"role": "buying"}), ME)
        self.assertEqual(r["statusCode"], 200)
        orders = js(r)["orders"]
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["listing"]["title"], "Calculus Book")
        self.assertEqual(orders[0]["role"], "buying")

    def test_list_selling_returns_seller_orders(self):
        r = orders_api.list_orders(ev(qs={"role": "selling"}), SELLER)
        self.assertEqual(r["statusCode"], 200)
        orders = js(r)["orders"]
        self.assertEqual(len(orders), 2)
        for o in orders:
            self.assertEqual(o["role"], "selling")

    def test_list_wrong_role_rejected(self):
        r = orders_api.list_orders(ev(qs={"role": "watching"}), ME)
        self.assertEqual(r["statusCode"], 400)

    def test_list_default_role_is_buying(self):
        r = orders_api.list_orders(ev(), ME)
        orders = js(r)["orders"]
        self.assertEqual(len(orders), 1)


class OrderGet(Base):
    def setUp(self):
        super().setUp()
        r = orders_api.create_order(ev({"method": "pickup"}), ME, LID)
        self.oid = js(r)["order"]["id"]

    def test_buyer_can_get(self):
        r = orders_api.get_order(ev(), ME, self.oid)
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(js(r)["order"]["role"], "buying")

    def test_seller_can_get(self):
        r = orders_api.get_order(ev(), SELLER, self.oid)
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(js(r)["order"]["role"], "selling")

    def test_third_party_gets_404(self):
        r = orders_api.get_order(ev(), OTHER, self.oid)
        self.assertEqual(r["statusCode"], 404)

    def test_invalid_id_is_404(self):
        r = orders_api.get_order(ev(), ME, "not-valid")
        self.assertEqual(r["statusCode"], 404)


if __name__ == "__main__":
    unittest.main()
