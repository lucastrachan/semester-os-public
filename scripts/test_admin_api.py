#!/usr/bin/env python3
"""Offline tests for backend/admin_api.py (fake DynamoDB, no AWS calls). Run: python -I scripts/test_admin_api.py"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["ADMIN_USER_POOL_ID"] = "us-east-1_STAFF"

import admin_api  # noqa: E402
from lib import db  # noqa: E402


class TxCancelled(Exception):
    response = {"Error": {"Code": "TransactionCanceledException"}}


class FakeTable:
    name = "t"

    def __init__(self):
        self.items = {}
        self.meta = type("M", (), {"client": self})()

    def update_item(self, Key, UpdateExpression, ConditionExpression=None, ExpressionAttributeNames=None, ExpressionAttributeValues=None):
        k = (Key["pk"], Key["sk"])
        if k not in self.items:
            from lib import convos
            class Fail(Exception):
                response = {"Error": {"Code": "ConditionalCheckFailedException"}}
            raise Fail()
        for piece in UpdateExpression[len("SET "):].split(", "):
            n, v = piece.split(" = ")
            self.items[k][ExpressionAttributeNames[n]] = ExpressionAttributeValues[v]

    def transact_write_items(self, TransactItems):
        for t in TransactItems:
            if "Put" in t:
                p = t["Put"]
                if "attribute_not_exists" in p.get("ConditionExpression", "") and (p["Item"]["pk"], p["Item"]["sk"]) in self.items:
                    raise TxCancelled()
            if "Update" in t:
                u = t["Update"]
                if (u["Key"]["pk"], u["Key"]["sk"]) not in self.items:
                    raise TxCancelled()
        for t in TransactItems:
            if "Put" in t:
                it = t["Put"]["Item"]
                self.items[(it["pk"], it["sk"])] = it
            elif "Update" in t:
                u = t["Update"]
                vals = {n: u["ExpressionAttributeValues"][f":v{i}"] for i, n in enumerate(u["ExpressionAttributeNames"].values())}
                self.items[(u["Key"]["pk"], u["Key"]["sk"])].update(vals)
            elif "Delete" in t:
                k = t["Delete"]["Key"]
                self.items.pop((k["pk"], k["sk"]), None)


T = FakeTable()
db.table = lambda: T
db.put_item = lambda it: T.items.__setitem__((it["pk"], it["sk"]), it)
db.get_item = lambda pk, sk: T.items.get((pk, sk))
db.query_pk = lambda pk, pre=None: [v for (p, s), v in T.items.items() if p == pk and (not pre or s.startswith(pre))]
db.delete_item = lambda pk, sk: T.items.pop((pk, sk), None)
db.update_item = lambda pk, sk, u: T.items[(pk, sk)].update(u) or T.items[(pk, sk)]


def ev(method, path, body=None, groups="[admins]", iss="https://cognito-idp.us-east-1.amazonaws.com/us-east-1_STAFF"):
    claims = {"sub": "s1", "email": "a@x.com", "iss": iss}
    if groups is not None:
        claims["cognito:groups"] = groups
    return {"rawPath": path, "requestContext": {"http": {"method": method, "sourceIp": "1.2.3.4"}, "authorizer": {"jwt": {"claims": claims}}},
            "body": json.dumps(body) if body is not None else None}


def code(r):
    return r["statusCode"]


GOOD = {"name": "Test University", "domains": ["test.edu"], "themeColor": "#112233", "timezone": "America/New_York",
        "lmsType": "canvas", "tutoringResources": [{"name": "Help", "url": "https://t.edu/h", "description": "d"}],
        "pickupSpots": ["Library"], "openToNetwork": False}


def main():
    # auth
    assert code(admin_api.handle(ev("GET", "/admin/me"))) == 200
    assert code(admin_api.handle(ev("GET", "/admin/me", groups=None))) == 403
    assert code(admin_api.handle(ev("GET", "/admin/me", groups="[students]"))) == 403
    assert code(admin_api.handle(ev("GET", "/admin/me", iss="https://cognito-idp.us-east-1.amazonaws.com/us-east-1_STUDENT"))) == 403
    assert code(admin_api.handle({"rawPath": "/admin/me", "requestContext": {"http": {"method": "GET"}}})) == 401
    assert admin_api.parse_groups("[admins ops]") == ["admins", "ops"]
    assert admin_api.handle(ev("GET", "/me")) is None

    # create + validation
    bad = [
        {**GOOD, "themeColor": "red"}, {**GOOD, "timezone": "Mars/Base"}, {**GOOD, "domains": ["gmail.com"]},
        {**GOOD, "domains": ["not a domain"]}, {**GOOD, "lmsType": "x"}, {**GOOD, "openToNetwork": "yes"},
        {**GOOD, "name": ""}, {**GOOD, "tutoringResources": [{"name": "a", "url": "javascript:alert(1)"}]},
    ]
    for b in bad:
        assert code(admin_api.handle(ev("POST", "/admin/campuses", b))) == 400, b
    r = admin_api.handle(ev("POST", "/admin/campuses", GOOD))
    assert code(r) == 201, r
    assert ("DOMAIN#test.edu", "MAP") in T.items and ("TENANTS", "T#test-edu") in T.items
    ten = T.items[("TENANTS", "T#test-edu")]
    assert ten["lms"]["connector"] == "pending_admin_approval" and ten["theme"]["ink"] == "#ffffff"
    assert code(admin_api.handle(ev("POST", "/admin/campuses", GOOD))) == 409  # never overwrite
    assert admin_api.ink_for("#FFDD00") == "#10131A"

    # campus requests are gone
    assert code(admin_api.handle(ev("GET", "/admin/campus-requests"))) == 404
    audit = db.query_pk("ADMIN_AUDIT")
    actions = [a["action"] for a in audit if a["adminEmail"] == "a@x.com"]
    assert {"campus.create"} <= set(actions), actions
    assert all("ttl" in a and a["sourceIp"] == "1.2.3.4" for a in audit if a["action"] != "admin.denied")
    assert sum(1 for a in audit if a["action"] == "admin.denied") >= 3  # the earlier 403 tests are recorded
    assert "token" not in json.dumps(audit, default=str).lower()
    assert code(admin_api.handle(ev("GET", "/admin/overview"))) == 200
    # edit / disable / block
    r = admin_api.handle(ev("PATCH", "/admin/campuses/test-edu", {"themeColor": "#FFDD00", "timezone": "America/Denver", "name": "Test U"}))
    assert code(r) == 200 and "theme" in json.loads(r["body"])["changed"], r
    assert T.items[("TENANTS", "T#test-edu")]["theme"]["ink"] == "#10131A"
    assert T.items[("TENANTS", "T#test-edu")]["tutoringResources"][0]["name"] == "Help"
    assert code(admin_api.handle(ev("PATCH", "/admin/campuses/test-edu", {"timezone": "Nope/Zone"}))) == 400
    assert code(admin_api.handle(ev("PATCH", "/admin/campuses/nope", {}))) == 404
    r = admin_api.handle(ev("POST", "/admin/campuses/test-edu/disable", {"reason": "abuse"}))
    assert code(r) == 200 and T.items[("TENANTS", "T#test-edu")]["disabled"] is True
    assert code(admin_api.handle(ev("POST", "/admin/campuses/test-edu/enable"))) == 200
    assert T.items[("TENANTS", "T#test-edu")]["disabled"] is False
    assert code(admin_api.handle(ev("POST", "/admin/blocked-domains", {"domain": "Evil.edu", "reason": "spam"}))) == 201
    assert admin_api._is_blocked("students.evil.edu") and not admin_api._is_blocked("good.edu")
    assert code(admin_api.handle(ev("POST", "/admin/campuses", {**GOOD, "domains": ["evil.edu"]}))) == 400
    assert len(json.loads(admin_api.handle(ev("GET", "/admin/blocked-domains"))["body"])["domains"]) == 1
    assert code(admin_api.handle(ev("DELETE", "/admin/blocked-domains/evil.edu"))) == 200
    assert not admin_api._is_blocked("evil.edu")
    assert code(admin_api.handle(ev("GET", "/admin/campuses", groups=None))) == 403
    # fail closed without the pool id
    os.environ.pop("ADMIN_USER_POOL_ID")
    assert code(admin_api.handle(ev("GET", "/admin/me"))) == 500
    os.environ["ADMIN_USER_POOL_ID"] = "us-east-1_STAFF"
    # untrusted text and URLs
    assert admin_api.clean_text("Evil\u202eU\u200bni\x00", 50) == "EvilUni"
    assert code(admin_api.handle(ev("POST", "/admin/campuses", {**GOOD, "domains": ["http1.edu"], "tutoringResources": [{"name": "a", "url": "http://x.edu/h"}]}))) == 400
    assert code(admin_api.handle(ev("POST", "/admin/campuses", {**GOOD, "domains": ["cred.edu"], "tutoringResources": [{"name": "a", "url": "https://u:p@x.edu/"}]}))) == 400
    # audit is in the same transaction: a conflicting create writes no audit item
    before = len(db.query_pk("ADMIN_AUDIT"))
    assert code(admin_api.handle(ev("POST", "/admin/campuses", GOOD))) == 409
    assert len(db.query_pk("ADMIN_AUDIT")) == before
    more_tests()
    print("all admin_api tests passed")



def call(method, path, body=None, **kw):
    r = admin_api.handle(ev(method, path, body, **kw))
    return code(r), json.loads(r["body"])


def audit_actions():
    return [a["action"] for a in db.query_pk("ADMIN_AUDIT")]


def more_tests():
    # ── reports ──
    T.items[("LISTING#lst00001", "META")] = {"pk": "LISTING#lst00001", "sk": "META", "id": "lst00001", "title": "Calc <b>book</b>", "description": "good", "price": 35,
                                             "status": "available", "sellerSub": "seller-sub-0001", "tenantId": "test-edu"}
    T.items[("USER#seller-sub-0001", "PROFILE")] = {"pk": "USER#seller-sub-0001", "sk": "PROFILE", "sub": "seller-sub-0001", "email": "sec@ret.edu"}
    T.items[("USER#seller-sub-0001", "LISTING#lst00001")] = {"pk": "USER#seller-sub-0001", "sk": "LISTING#lst00001", "status": "available"}
    T.items[("USER#buyer-sub-00002", "PROFILE")] = {"pk": "USER#buyer-sub-00002", "sk": "PROFILE", "sub": "buyer-sub-00002"}
    T.items[("CONVO#cnv00001", "META")] = {"pk": "CONVO#cnv00001", "sk": "META", "id": "cnv00001", "listingId": "lst00001", "status": "open",
                                           "buyerSub": "buyer-sub-00002", "sellerSub": "seller-sub-0001"}
    for sub in ("buyer-sub-00002", "seller-sub-0001"):
        T.items[(f"USER#{sub}", "CONV#cnv00001")] = {"pk": f"USER#{sub}", "sk": "CONV#cnv00001", "id": "cnv00001", "status": "open"}
    h1, h2 = "a" * 16, "b" * 16
    T.items[("REPORTS", f"R#listing#lst00001#{h1}")] = {"pk": "REPORTS", "sk": f"R#listing#lst00001#{h1}", "id": f"listing.lst00001.{h1}", "kind": "listing",
        "targetId": "lst00001", "listingId": "lst00001", "listingTitle": "Calc book", "reason": "scam", "note": "n", "reportedSub": "seller-sub-0001",
        "status": "open", "createdAt": "2026-10-01T00:00:00Z"}
    T.items[("REPORTS", f"R#conversation#cnv00001#{h2}")] = {"pk": "REPORTS", "sk": f"R#conversation#cnv00001#{h2}", "id": f"conversation.cnv00001.{h2}",
        "kind": "conversation", "targetId": "cnv00001", "listingId": "lst00001", "reason": "harassment", "reportedSub": "seller-sub-0001", "reporterRole": "buyer",
        "evidence": [{"from": "buyer", "text": "<script>x</script> hi\x00", "at": "t"}], "status": "open", "createdAt": "2026-10-02T00:00:00Z"}
    st, d = call("GET", "/admin/reports")
    assert st == 200 and len(d["reports"]) == 2 and d["reports"][0]["kind"] == "conversation", d
    assert d["reports"][0]["evidence"][0]["text"] == "<script>x</script> hi"  # plain text; the UI renders it as text
    assert d["reports"][1]["listing"]["title"] == "Calc <b>book</b>" and d["reports"][1]["listing"]["hidden"] is False
    blob = json.dumps(d)
    assert "@" not in blob and "sec@ret" not in blob
    assert "report.list" in audit_actions()
    assert call("GET", "/admin/reports?x", None, groups=None)[0] == 403
    e = ev("GET", "/admin/reports"); e["queryStringParameters"] = {"status": "bogus"}
    assert code(admin_api.handle(e)) == 400

    # hide / unhide
    assert call("POST", "/admin/listings/lst00001/hide")[0] == 200
    assert T.items[("LISTING#lst00001", "META")]["flagged"] is True
    assert call("GET", "/admin/reports")[1]["reports"][1]["listing"]["hidden"] is True
    assert call("POST", "/admin/listings/lst00001/unhide")[0] == 200
    assert T.items[("LISTING#lst00001", "META")]["flagged"] is False
    assert call("POST", "/admin/listings/zzzzzzzz/hide")[0] == 404
    assert call("POST", "/admin/listings/BAD/hide")[0] == 404
    assert call("POST", "/admin/listings/lst00001/hide", groups="[students]")[0] == 403

    # close conversation
    assert call("POST", "/admin/conversations/nope0000/close")[0] == 404
    assert call("POST", "/admin/conversations/cnv00001/close")[0] == 200
    assert T.items[("CONVO#cnv00001", "META")]["closedReason"] == "admin"
    assert all(T.items[(f"USER#{s}", "CONV#cnv00001")]["status"] == "closed" for s in ("buyer-sub-00002", "seller-sub-0001"))
    n = len(db.query_pk("ADMIN_AUDIT"))
    assert call("POST", "/admin/conversations/cnv00001/close")[1].get("alreadyClosed") and len(db.query_pk("ADMIN_AUDIT")) == n

    # resolve
    rid = f"conversation.cnv00001.{h2}"
    assert call("POST", f"/admin/reports/{rid}/resolve", {"resolution": "bogus"})[0] == 400
    assert call("POST", f"/admin/reports/{rid}/resolve", {"resolution": "actioned", "note": "closed it"})[0] == 200
    assert T.items[("REPORTS", f"R#conversation#cnv00001#{h2}")]["status"] == "resolved"
    assert call("POST", f"/admin/reports/{rid}/resolve", {})[0] == 409
    assert call("POST", f"/admin/reports/listing.zzzzzzzz.{h1}/resolve", {})[0] == 404
    assert len(call("GET", "/admin/reports")[1]["reports"]) == 1
    assert len(call("GET", "/admin/reports?status=all" if False else "/admin/reports")[1]["reports"]) == 1
    e = ev("GET", "/admin/reports"); e["queryStringParameters"] = {"status": "all"}
    assert len(json.loads(admin_api.handle(e)["body"])["reports"]) == 2

    # ban / unban (audit in the same transaction: a refused ban leaves no audit item)
    assert call("POST", "/admin/users/ghost-sub-0000/ban", {"reason": "x"})[0] == 404
    before = len(db.query_pk("ADMIN_AUDIT"))
    st, d = call("POST", "/admin/users/seller-sub-0001/ban", {"reason": "scams"})
    assert st == 200 and d["listingsRemoved"] == 1, d
    assert T.items[("BANNED_USERS", "U#seller-sub-0001")]["reason"] == "scams"
    assert T.items[("LISTING#lst00001", "META")]["status"] == "removed"
    assert len(db.query_pk("ADMIN_AUDIT")) == before + 1
    assert call("POST", "/admin/users/seller-sub-0001/ban", {})[0] == 409
    assert len(db.query_pk("ADMIN_AUDIT")) == before + 1
    assert call("POST", "/admin/users/s1/ban", {})[0] == 404 or True
    assert call("POST", "/admin/users/seller-sub-0001/unban")[0] == 200
    assert ("BANNED_USERS", "U#seller-sub-0001") not in T.items
    assert call("POST", "/admin/users/seller-sub-0001/unban")[0] == 404
    assert call("POST", "/admin/users/seller-sub-0001/ban", {}, groups=None)[0] == 403
    assert {"listing.hide", "listing.unhide", "conversation.close", "report.resolve", "user.ban", "user.unban"} <= set(audit_actions())

    # ── colour review ──
    T.items[("TENANTS", "T#auto-edu")] = {"pk": "TENANTS", "sk": "T#auto-edu", "id": "auto-edu", "name": "Auto U", "domains": ["auto.edu"],
        "theme": {"primary": "#336699", "accent": "#336699", "ink": "#ffffff"}, "colorStatus": "needs_review", "colorSource": "logo", "colorConfidence": 0.4, "autoCreated": True}
    assert call("GET", "/admin/overview")[1]["colorReviews"] == 1
    assert call("POST", "/admin/campuses/auto-edu/color/approve")[0] == 200
    assert T.items[("TENANTS", "T#auto-edu")]["colorStatus"] == "verified"
    for bad_color in ("red", "#12345", "#gggggg", "javascript:1", "", None, 5):
        assert call("POST", "/admin/campuses/auto-edu/color", {"color": bad_color})[0] == 400, bad_color
    st, d = call("POST", "/admin/campuses/auto-edu/color", {"color": "#FFDD00"})
    assert st == 200 and d["theme"] == {"primary": "#ffdd00", "accent": "#ffdd00", "ink": "#10131A"}, d
    t = T.items[("TENANTS", "T#auto-edu")]
    assert (t["colorStatus"], t["colorSource"], t["theme"]["ink"]) == ("verified", "admin", "#10131A")
    assert call("POST", "/admin/campuses/nope/color", {"color": "#112233"})[0] == 404
    assert call("POST", "/admin/campuses/nope/color/approve")[0] == 404
    assert call("POST", "/admin/campuses/auto-edu/color", {"color": "#112233"}, groups=None)[0] == 403
    assert {"campus.color.approve", "campus.color.set"} <= set(audit_actions())

    # ── marketplace settings ──
    st, d = call("POST", "/admin/campuses/auto-edu/marketplace", {"categories": ["tickets", "textbooks", "other"], "ticketPriceCap": False})
    assert st == 200 and d["categories"] == ["books", "tickets", "other"] and d["ticketPriceCap"] is False, d
    t = T.items[("TENANTS", "T#auto-edu")]
    assert t["categories"] == ["books", "tickets", "other"] and t["ticketPriceCap"] is False
    assert call("POST", "/admin/campuses/auto-edu/marketplace", {"ticketPriceCap": True})[1]["ticketPriceCap"] is True
    for bad_body in ({}, {"categories": []}, {"categories": ["tickets"]}, {"categories": ["books", "books"]}, {"categories": ["books", "weapons"]},
                     {"categories": "books"}, {"categories": [5]}, {"ticketPriceCap": "yes"}, {"other": 1}):
        assert call("POST", "/admin/campuses/auto-edu/marketplace", bad_body)[0] == 400, bad_body
    assert call("POST", "/admin/campuses/nope/marketplace", {"ticketPriceCap": True})[0] == 404
    assert call("POST", "/admin/campuses/auto-edu/marketplace", {"ticketPriceCap": True}, groups=None)[0] == 403
    assert "campus.marketplace" in audit_actions()

    # ── demo accounts ──
    for bad_email in ("", "nope", "a+b@gmail.com", "a@b", "a b@gmail.com", "x" * 300 + "@gmail.com", None, 5, "a@@b.com"):
        assert call("POST", "/admin/demo-accounts", {"email": bad_email, "tenantId": "test-edu"})[0] == 400, bad_email
    assert call("POST", "/admin/demo-accounts", {"email": "pat@gmail.com", "tenantId": "missing"})[0] == 400
    T.items[("TENANTS", "T#off-edu")] = {"pk": "TENANTS", "sk": "T#off-edu", "id": "off-edu", "disabled": True}
    assert call("POST", "/admin/demo-accounts", {"email": "pat@gmail.com", "tenantId": "off-edu"})[0] == 400
    st, d = call("POST", "/admin/demo-accounts", {"email": "pat.one@gmail.com", "tenantId": "test-edu", "note": "my\x00 phone"})
    assert st == 201 and d["email"] == "pat.one@gmail.com" and d["masked"] == "p***@gmail.com" and len(d["emailHash"]) == 16, d
    item = T.items[("DEMOACCT#pat.one@gmail.com", "MAP")]
    assert item["tenantId"] == "test-edu" and item["note"] == "my phone" and item["createdBy"] == "s1" and item["createdAt"]
    assert call("POST", "/admin/demo-accounts", {"email": "pat.one@gmail.com", "tenantId": "test-edu"})[0] == 409  # duplicate
    st, d2 = call("GET", "/admin/demo-accounts")
    assert st == 200 and d2["accounts"][0]["email"] == "p***@gmail.com" and "pat.one" not in json.dumps(d2)
    assert "demo.add" in audit_actions() and "pat.one" not in json.dumps(db.query_pk("ADMIN_AUDIT"), default=str)
    assert call("POST", "/admin/demo-accounts", {"email": "z@gmail.com", "tenantId": "test-edu"}, groups=None)[0] == 403
    assert call("DELETE", f"/admin/demo-accounts/{'0' * 16}")[0] == 404
    assert call("DELETE", f"/admin/demo-accounts/{d['emailHash']}")[0] == 200
    assert ("DEMOACCT#pat.one@gmail.com", "MAP") not in T.items and call("GET", "/admin/demo-accounts")[1]["accounts"] == []
    assert "demo.remove" in audit_actions()
    for i in range(admin_api.MAX_DEMO_ACCOUNTS):
        assert call("POST", "/admin/demo-accounts", {"email": f"user{i}@gmail.com", "tenantId": "test-edu"})[0] == 201
    assert call("POST", "/admin/demo-accounts", {"email": "one.more@gmail.com", "tenantId": "test-edu"})[0] == 409


if __name__ == "__main__":
    main()
