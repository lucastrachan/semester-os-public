"""Tests for auto-campus: registry lookup, pre_signup gate, lazy campus creation, demo accounts."""
import sys
from pathlib import Path
import pytest

BACKEND = str(Path(__file__).resolve().parents[1])
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from lib.registry import edu_root, is_edu, lookup
from tests._fakes import FakeDb, FakeClientError


# ── edu_root / is_edu ──────────────────────────────────────────────────────────

def test_edu_root_simple():
    assert edu_root("ua.edu") == "ua.edu"

def test_edu_root_subdomain():
    assert edu_root("students.ua.edu") == "ua.edu"
    assert edu_root("alumni.crimson.ua.edu") == "ua.edu"

def test_edu_root_non_edu():
    assert edu_root("gmail.com") is None
    assert edu_root("example.ac.uk") is None
    assert edu_root("localhost") is None

def test_is_edu():
    assert is_edu("ua.edu")
    assert is_edu("mail.mit.edu")
    assert not is_edu("gmail.com")


# ── Registry lookup ────────────────────────────────────────────────────────────

def test_lookup_known_school():
    entry = lookup("ua.edu")
    assert entry is not None
    assert "University of Alabama" in entry["name"]

def test_lookup_subdomain_resolves():
    # Students subdomain should resolve the same school as the root
    entry_root = lookup("ua.edu")
    entry_sub = lookup("students.ua.edu")
    assert entry_root == entry_sub

def test_lookup_unknown_edu():
    # Made-up school — not in registry but still .edu
    entry = lookup("unknownxyz99999.edu")
    assert entry is None

def test_lookup_non_edu_returns_none():
    assert lookup("gmail.com") is None
    assert lookup("example.com") is None


# ── pre_signup gate ────────────────────────────────────────────────────────────

def _make_event(email: str, name: str = "Test User") -> dict:
    return {"request": {"userAttributes": {"email": email, "name": name}}}


class FakeTable:
    def __init__(self, items=None):
        self._items = items or {}

    def get_item(self, Key):
        return {"Item": self._items.get((Key["pk"], Key["sk"]))}


def _presignup(email: str, table_items: dict = None, name: str = "Test User"):
    import importlib, os
    from unittest.mock import patch, MagicMock
    os.environ["TABLE_NAME"] = "test"

    fake_table = FakeTable(table_items or {})
    fake_dynamo = MagicMock()
    fake_dynamo.Table.return_value = fake_table

    import pre_signup
    importlib.reload(pre_signup)
    with patch.object(pre_signup, "boto3") as mock_boto:
        mock_boto.resource.return_value = fake_dynamo
        return pre_signup.handler(_make_event(email, name), None)


def test_presignup_allows_edu():
    result = _presignup("student@ua.edu")
    assert result["request"]["userAttributes"]["email"] == "student@ua.edu"

def test_presignup_rejects_non_edu():
    with pytest.raises(Exception, match="Semester OS supports US colleges"):
        _presignup("user@gmail.com")

def test_presignup_rejects_non_edu_ac_uk():
    with pytest.raises(Exception, match="Semester OS supports US colleges"):
        _presignup("user@ox.ac.uk")

def test_presignup_allows_demo_account():
    items = {("DEMOACCT#demo@gmail.com", "MAP"): {"pk": "DEMOACCT#demo@gmail.com", "sk": "MAP", "tenantId": "ua-edu"}}
    result = _presignup("demo@gmail.com", table_items=items)
    assert result is not None

def test_presignup_rejects_blocked_domain():
    items = {("BLOCKED_DOMAINS", "D#ua.edu"): {"pk": "BLOCKED_DOMAINS", "sk": "D#ua.edu"}}
    with pytest.raises(Exception, match="temporarily paused"):
        _presignup("student@ua.edu", table_items=items)

def test_presignup_case_insensitive_demo():
    items = {("DEMOACCT#demo@example.com", "MAP"): {"pk": "DEMOACCT#demo@example.com", "sk": "MAP", "tenantId": "ua-edu"}}
    result = _presignup("DEMO@EXAMPLE.COM", table_items=items)
    assert result is not None


# ── api._derive_color / _ink / _short_name ─────────────────────────────────────

def test_derive_color_deterministic():
    from api import _derive_color
    assert _derive_color("University of Alabama") == _derive_color("University of Alabama")
    assert _derive_color("University of Alabama") != _derive_color("Auburn University")

def test_ink_dark_primary():
    from api import _ink
    assert _ink("#1F3A93") == "#FFFFFF"  # dark blue -> white text

def test_ink_bright_primary():
    from api import _ink
    # wichita.edu uses yellow (#FFD700, lum ~198) -> dark text
    assert _ink("#FFD700") == "#000000"

def test_short_name_filters_stop_words():
    from api import _short_name
    assert _short_name("University of Alabama") == "UA"
    assert _short_name("Massachusetts Institute of Technology") == "MIT"

def test_tenant_id_from_root():
    from api import _tenant_id_from_root
    assert _tenant_id_from_root("ua.edu") == "ua-edu"
    assert _tenant_id_from_root("mit.edu") == "mit-edu"


# ── lazy campus creation race condition ────────────────────────────────────────

def _jwt_event(sub: str, email: str, name: str = None) -> dict:
    claims = {"sub": sub, "email": email}
    if name is not None:
        claims["name"] = name
    return {
        "rawPath": "/me",
        "requestContext": {"http": {"method": "GET"}, "authorizer": {"jwt": {"claims": claims}}},
        "queryStringParameters": None,
        "body": None,
    }


def test_race_condition_second_signup_reads_winner(monkeypatch):
    """Second signup at an already-created campus finds the existing campus."""
    import api as api_mod

    fake = FakeDb()
    fake.put_item({
        "pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu",
        "name": "The University of Alabama",
        "theme": {"primary": "#9E1B32", "ink": "#FFFFFF"},
        "colorStatus": "verified", "autoCreated": True,
        "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
    })
    fake.put_item({"pk": "DOMAIN#ua.edu", "sk": "MAP", "tenantId": "ua-edu"})

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "put_item", fake.put_item)

    import calendar_api
    monkeypatch.setattr(calendar_api, "new_token", lambda: "testtoken123")

    resp = api_mod.get_me(_jwt_event("sub-B", "student2@ua.edu"), "sub-B")
    assert resp["statusCode"] == 200
    body = __import__("json").loads(resp["body"])
    assert body["tenant"]["id"] == "ua-edu"


def test_race_condition_transact_fails_reads_winner(monkeypatch):
    """When transact_put_items fails (race), the loser reads the winner's campus."""
    import api as api_mod

    fake = FakeDb()
    fake.put_item({
        "pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu",
        "name": "The University of Alabama",
        "theme": {"primary": "#9E1B32", "ink": "#FFFFFF"},
        "colorStatus": "verified", "autoCreated": True,
        "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
    })

    call_count = {"n": 0}
    def fake_get_item(pk, sk):
        if pk == "DOMAIN#ua.edu" and sk == "MAP":
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # not yet created (triggers create path)
            return {"pk": "DOMAIN#ua.edu", "sk": "MAP", "tenantId": "ua-edu"}  # winner wrote it
        return fake.get_item(pk, sk)

    def raise_transact(items):
        raise FakeClientError("TransactionCanceledException")

    monkeypatch.setattr(api_mod.db, "get_item", fake_get_item)
    monkeypatch.setattr(api_mod.db, "put_item", fake.put_item)
    monkeypatch.setattr(api_mod.db, "transact_put_items", raise_transact)

    import calendar_api
    monkeypatch.setattr(calendar_api, "new_token", lambda: "testtoken456")

    resp = api_mod.get_me(_jwt_event("sub-C", "student3@ua.edu"), "sub-C")
    assert resp["statusCode"] == 200
    body = __import__("json").loads(resp["body"])
    assert body["tenant"]["id"] == "ua-edu"


def test_non_edu_get_me_returns_403(monkeypatch):
    import api as api_mod
    fake = FakeDb()
    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "put_item", fake.put_item)

    resp = api_mod.get_me(_jwt_event("sub-X", "user@gmail.com"), "sub-X")
    assert resp["statusCode"] == 403
    import json
    body = json.loads(resp["body"])
    assert body["error"] == "account_not_enabled"


def test_demo_account_non_edu_allowed(monkeypatch):
    import api as api_mod, json

    fake = FakeDb()
    fake.put_item({"pk": "DEMOACCT#demo@gmail.com", "sk": "MAP", "tenantId": "ua-edu"})
    fake.put_item({
        "pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu",
        "name": "University of Alabama Demo", "theme": {"primary": "#9E1B32", "ink": "#FFFFFF"},
        "colorStatus": "verified",
    })

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "put_item", fake.put_item)
    monkeypatch.setattr(api_mod.db, "table", lambda: type("T", (), {"put_item": lambda self, **kw: None})())

    import calendar_api
    monkeypatch.setattr(calendar_api, "new_token", lambda: "demotoken")

    resp = api_mod.get_me(_jwt_event("sub-demo", "demo@gmail.com"), "sub-demo")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["tenant"]["id"] == "ua-edu"


def test_banned_user_returns_403(monkeypatch):
    import api as api_mod

    fake = FakeDb()
    fake.put_item({"pk": "BANNED_USERS", "sk": "U#banned-sub", "reason": "abuse"})

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    resp = api_mod.get_me(_jwt_event("banned-sub", "student@ua.edu"), "banned-sub")
    assert resp["statusCode"] == 403
    import json
    assert json.loads(resp["body"])["error"] == "account_restricted"


def test_get_me_disabled_tenant_returns_403(monkeypatch):
    """Demo account whose campus is disabled gets 403 campus_disabled."""
    import api as api_mod, json

    fake = FakeDb()
    fake.put_item({"pk": "DEMOACCT#demo@gmail.com", "sk": "MAP", "tenantId": "ua-edu"})
    fake.put_item({
        "pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu",
        "name": "University of Alabama Demo",
        "theme": {"primary": "#9E1B32", "ink": "#FFFFFF"},
        "disabled": True,
    })

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    resp = api_mod.get_me(_jwt_event("sub-demo2", "demo@gmail.com"), "sub-demo2")
    assert resp["statusCode"] == 403
    assert json.loads(resp["body"])["error"] == "campus_disabled"


def test_get_me_edu_disabled_tenant_returns_403(monkeypatch):
    """Existing .edu campus that is disabled returns 403 campus_disabled."""
    import api as api_mod, json

    fake = FakeDb()
    fake.put_item({"pk": "DOMAIN#ua.edu", "sk": "MAP", "tenantId": "ua-edu"})
    fake.put_item({
        "pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu",
        "name": "University of Alabama",
        "disabled": True,
    })

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    resp = api_mod.get_me(_jwt_event("sub-Y", "student@ua.edu"), "sub-Y")
    assert resp["statusCode"] == 403
    assert json.loads(resp["body"])["error"] == "campus_disabled"


def test_get_me_blocked_domain_returns_403(monkeypatch):
    """Blocked root domain returns 403 domain_paused."""
    import api as api_mod, json

    fake = FakeDb()
    fake.put_item({"pk": "BLOCKED_DOMAINS", "sk": "D#ua.edu"})

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    resp = api_mod.get_me(_jwt_event("sub-Z", "student@ua.edu"), "sub-Z")
    assert resp["statusCode"] == 403
    assert json.loads(resp["body"])["error"] == "domain_paused"


# ── resolve_domain checks ──────────────────────────────────────────────────────

def _resolve_event(domain: str) -> dict:
    return {
        "rawPath": "/public/resolve",
        "requestContext": {"http": {"method": "GET", "sourceIp": "127.0.0.1"}},
        "queryStringParameters": {"domain": domain},
        "body": None,
    }


def _noop_check_ip(*a, **kw):
    pass


def test_resolve_domain_blocked_returns_404(monkeypatch):
    """Blocked domain returns 404, not school info."""
    import api as api_mod, json

    fake = FakeDb()
    fake.put_item({"pk": "BLOCKED_DOMAINS", "sk": "D#ua.edu"})

    monkeypatch.setattr(api_mod.limits, "check_ip", _noop_check_ip)
    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    resp = api_mod.resolve_domain(_resolve_event("ua.edu"))
    assert resp["statusCode"] == 404


def test_resolve_domain_disabled_tenant_falls_back_to_registry(monkeypatch):
    """Disabled campus behaves as if not live; returns registry data instead."""
    import api as api_mod, json

    fake = FakeDb()
    fake.put_item({"pk": "DOMAIN#ua.edu", "sk": "MAP", "tenantId": "ua-edu"})
    fake.put_item({
        "pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu",
        "name": "University of Alabama",
        "theme": {"primary": "#9E1B32", "ink": "#FFFFFF"},
        "colorStatus": "verified",
        "disabled": True,
    })

    monkeypatch.setattr(api_mod.limits, "check_ip", _noop_check_ip)
    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    resp = api_mod.resolve_domain(_resolve_event("ua.edu"))
    # Should fall through to registry (school is in registry) and return 200
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "University of Alabama" in body["name"]


def test_resolve_domain_rate_limited(monkeypatch):
    """resolve_domain raises RateLimited when check_ip raises it."""
    import api as api_mod
    from lib.limits import RateLimited

    def fake_check_ip(*a, **kw):
        raise RateLimited("Too many requests.", 60)

    monkeypatch.setattr(api_mod.limits, "check_ip", fake_check_ip)
    with pytest.raises(RateLimited):
        api_mod.resolve_domain(_resolve_event("ua.edu"))


# ── color_worker uses lib.bedrock.converse ────────────────────────────────────

# ── pre_signup name requirement ────────────────────────────────────────────────

def test_presignup_requires_name():
    with pytest.raises(Exception, match="full name"):
        _presignup("student@ua.edu", name="")

def test_presignup_rejects_single_char_name():
    with pytest.raises(Exception, match="full name"):
        _presignup("student@ua.edu", name="A")

def test_presignup_rejects_email_like_name():
    with pytest.raises(Exception, match="full name"):
        _presignup("student@ua.edu", name="user@school.edu")

def test_presignup_accepts_real_name():
    result = _presignup("student@ua.edu", name="Luca Strachan")
    assert result is not None

def test_presignup_demo_requires_name():
    items = {("DEMOACCT#demo@gmail.com", "MAP"): {"pk": "DEMOACCT#demo@gmail.com", "sk": "MAP"}}
    with pytest.raises(Exception, match="full name"):
        _presignup("demo@gmail.com", table_items=items, name="")


# ── displayName from name claim ────────────────────────────────────────────────

def test_get_me_uses_name_claim_on_first_signup(monkeypatch):
    """New user gets firstName/lastName/displayName from JWT name claim."""
    import api as api_mod, json, calendar_api

    fake = FakeDb()
    fake.put_item({"pk": "DOMAIN#ua.edu", "sk": "MAP", "tenantId": "ua-edu"})
    fake.put_item({"pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu", "name": "University of Alabama",
                   "theme": {"primary": "#9E1B32", "ink": "#FFFFFF"}, "colorStatus": "verified",
                   "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z"})

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "put_item", fake.put_item)
    monkeypatch.setattr(calendar_api, "new_token", lambda: "caltoken123")

    resp = api_mod.get_me(_jwt_event("sub-name", "luca@ua.edu", name="Luca Strachan"), "sub-name")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["profile"]["firstName"] == "Luca"
    assert body["profile"]["lastName"] == "Strachan"
    assert body["profile"]["displayName"] == "Luca Strachan"
    assert body["needsName"] is False


def test_get_me_no_name_claim_leaves_name_empty(monkeypatch):
    """No name claim → firstName is '', needsName is True."""
    import api as api_mod, json, calendar_api

    fake = FakeDb()
    fake.put_item({"pk": "DOMAIN#ua.edu", "sk": "MAP", "tenantId": "ua-edu"})
    fake.put_item({"pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu", "name": "University of Alabama",
                   "theme": {"primary": "#9E1B32", "ink": "#FFFFFF"}, "colorStatus": "verified",
                   "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z"})

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "put_item", fake.put_item)
    monkeypatch.setattr(calendar_api, "new_token", lambda: "caltoken456")

    resp = api_mod.get_me(_jwt_event("sub-noname", "noname@ua.edu"), "sub-noname")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["profile"]["firstName"] == ""
    assert body["needsName"] is True


def test_get_me_refreshes_missing_firstname(monkeypatch):
    """Returning user with no firstName gets it set from name claim."""
    import api as api_mod, json

    fake = FakeDb()
    fake.put_item({"pk": "DOMAIN#ua.edu", "sk": "MAP", "tenantId": "ua-edu"})
    fake.put_item({"pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu", "name": "University of Alabama",
                   "theme": {"primary": "#9E1B32", "ink": "#FFFFFF"}, "colorStatus": "verified",
                   "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z"})
    fake.put_item({"pk": "USER#sub-refresh", "sk": "PROFILE", "sub": "sub-refresh",
                   "email": "luca@ua.edu", "tenantId": "ua-edu",
                   "firstName": "", "lastName": "", "displayName": "",
                   "calToken": "tok", "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z"})

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "update_item", fake.update_item)

    resp = api_mod.get_me(_jwt_event("sub-refresh", "luca@ua.edu", name="Luca Strachan"), "sub-refresh")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["profile"]["firstName"] == "Luca"
    assert body["profile"]["displayName"] == "Luca Strachan"


def test_patch_me_firstName_lastName(monkeypatch):
    """PATCH /me {firstName, lastName} stores both and derives displayName."""
    import api as api_mod, json

    fake = FakeDb()
    fake.put_item({"pk": "USER#sub-patch", "sk": "PROFILE", "sub": "sub-patch",
                   "email": "luca@ua.edu", "tenantId": "ua-edu",
                   "firstName": "", "lastName": "", "displayName": "",
                   "calToken": "tok", "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z"})

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "update_item", fake.update_item)
    monkeypatch.setattr(api_mod.limits, "check_user", lambda *a, **kw: None)

    event = {
        "rawPath": "/me", "requestContext": {"http": {"method": "PATCH"},
        "authorizer": {"jwt": {"claims": {"sub": "sub-patch", "email": "luca@ua.edu"}}}},
        "queryStringParameters": None, "body": json.dumps({"firstName": "Luca", "lastName": "Strachan"}),
    }
    resp = api_mod.patch_me(event, "sub-patch")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["profile"]["firstName"] == "Luca"
    assert body["profile"]["lastName"] == "Strachan"
    assert body["profile"]["displayName"] == "Luca Strachan"


def test_patch_me_displayName_splits(monkeypatch):
    """PATCH /me {displayName} is split on first space for backward compat."""
    import api as api_mod, json

    fake = FakeDb()
    fake.put_item({"pk": "USER#sub-dp", "sk": "PROFILE", "sub": "sub-dp",
                   "email": "luca@ua.edu", "tenantId": "ua-edu",
                   "firstName": "", "lastName": "", "displayName": "",
                   "calToken": "tok", "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z"})

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "update_item", fake.update_item)
    monkeypatch.setattr(api_mod.limits, "check_user", lambda *a, **kw: None)

    event = {
        "rawPath": "/me", "requestContext": {"http": {"method": "PATCH"},
        "authorizer": {"jwt": {"claims": {"sub": "sub-dp", "email": "luca@ua.edu"}}}},
        "queryStringParameters": None, "body": json.dumps({"displayName": "Luca Strachan"}),
    }
    resp = api_mod.patch_me(event, "sub-dp")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["profile"]["firstName"] == "Luca"
    assert body["profile"]["lastName"] == "Strachan"


def test_patch_me_rejects_empty_firstname(monkeypatch):
    import api as api_mod, json
    fake = FakeDb()
    fake.put_item({"pk": "USER#sub-rej", "sk": "PROFILE", "sub": "sub-rej", "email": "x@ua.edu",
                   "firstName": "", "lastName": "", "displayName": "", "calToken": "t",
                   "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z"})
    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.limits, "check_user", lambda *a, **kw: None)
    event = {"rawPath": "/me", "requestContext": {"http": {"method": "PATCH"}, "authorizer": {"jwt": {"claims": {"sub": "sub-rej", "email": "x@ua.edu"}}}}, "queryStringParameters": None, "body": json.dumps({"displayName": "A"})}
    resp = api_mod.patch_me(event, "sub-rej")
    assert resp["statusCode"] == 400


def test_patch_me_rejects_email_in_name(monkeypatch):
    import api as api_mod, json
    fake = FakeDb()
    fake.put_item({"pk": "USER#sub-em", "sk": "PROFILE", "sub": "sub-em", "email": "x@ua.edu",
                   "firstName": "", "lastName": "", "displayName": "", "calToken": "t",
                   "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z"})
    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.limits, "check_user", lambda *a, **kw: None)
    event = {"rawPath": "/me", "requestContext": {"http": {"method": "PATCH"}, "authorizer": {"jwt": {"claims": {"sub": "sub-em", "email": "x@ua.edu"}}}}, "queryStringParameters": None, "body": json.dumps({"firstName": "user@school"})}
    resp = api_mod.patch_me(event, "sub-em")
    assert resp["statusCode"] == 400


def _lms_profile(monkeypatch, sub="sub-lms"):
    import api as api_mod
    fake = FakeDb()
    fake.put_item({"pk": f"USER#{sub}", "sk": "PROFILE", "sub": sub, "email": "x@ua.edu",
                   "firstName": "Luca", "lastName": "S", "displayName": "Luca S", "calToken": "t",
                   "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z"})
    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "update_item", fake.update_item)
    monkeypatch.setattr(api_mod.db, "table", lambda: None)
    monkeypatch.setattr(api_mod.limits, "check_user", lambda *a, **kw: None)
    return api_mod, sub


def test_patch_me_lms_canvas(monkeypatch):
    import json
    api_mod, sub = _lms_profile(monkeypatch)
    event = {"rawPath": "/me", "requestContext": {"http": {"method": "PATCH"},
             "authorizer": {"jwt": {"claims": {"sub": sub, "email": "x@ua.edu"}}}},
             "queryStringParameters": None, "body": json.dumps({"lms": "canvas"})}
    resp = api_mod.patch_me(event, sub)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["profile"]["lms"] == "canvas"


def test_patch_me_lms_blackboard(monkeypatch):
    import json
    api_mod, sub = _lms_profile(monkeypatch, "sub-bb")
    event = {"rawPath": "/me", "requestContext": {"http": {"method": "PATCH"},
             "authorizer": {"jwt": {"claims": {"sub": sub, "email": "x@ua.edu"}}}},
             "queryStringParameters": None, "body": json.dumps({"lms": "blackboard"})}
    resp = api_mod.patch_me(event, sub)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["profile"]["lms"] == "blackboard"


def test_patch_me_lms_invalid_rejected(monkeypatch):
    import json
    api_mod, sub = _lms_profile(monkeypatch, "sub-inv")
    event = {"rawPath": "/me", "requestContext": {"http": {"method": "PATCH"},
             "authorizer": {"jwt": {"claims": {"sub": sub, "email": "x@ua.edu"}}}},
             "queryStringParameters": None, "body": json.dumps({"lms": "schoology"})}
    resp = api_mod.patch_me(event, sub)
    assert resp["statusCode"] == 400


def test_patch_me_lms_and_avatar_together(monkeypatch):
    import json
    api_mod, sub = _lms_profile(monkeypatch, "sub-combo")
    event = {"rawPath": "/me", "requestContext": {"http": {"method": "PATCH"},
             "authorizer": {"jwt": {"claims": {"sub": sub, "email": "x@ua.edu"}}}},
             "queryStringParameters": None, "body": json.dumps({"lms": "canvas", "avatar": "robot-03"})}
    resp = api_mod.patch_me(event, sub)
    assert resp["statusCode"] == 200
    profile = json.loads(resp["body"])["profile"]
    assert profile["lms"] == "canvas"
    assert profile["avatar"] == "robot-03"


# ── first-login / profile-deleted paths ───────────────────────────────────────

def test_new_edu_user_first_login_full_profile(monkeypatch):
    """Brand-new .edu user gets a full profile with firstName/lastName/needsName=False, no avatar set."""
    import api as api_mod, json, calendar_api

    fake = FakeDb()
    fake.put_item({"pk": "DOMAIN#ua.edu", "sk": "MAP", "tenantId": "ua-edu"})
    fake.put_item({
        "pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu",
        "name": "University of Alabama",
        "theme": {"primary": "#9E1B32", "ink": "#FFFFFF"},
        "colorStatus": "verified",
        "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
    })

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "put_item", fake.put_item)
    monkeypatch.setattr(calendar_api, "new_token", lambda: "newusertoken")

    resp = api_mod.get_me(_jwt_event("sub-new-edu", "newstudent@ua.edu", name="Alex Smith"), "sub-new-edu")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])

    profile = body["profile"]
    assert profile["firstName"] == "Alex"
    assert profile["lastName"] == "Smith"
    assert profile["displayName"] == "Alex Smith"
    assert profile.get("avatar") is None   # no avatar on first login
    assert profile.get("lms") is None       # no lms on first login
    assert body["needsName"] is False
    assert body["tenant"]["id"] == "ua-edu"
    assert "calendarPath" in body

    # Profile must have been persisted in DB
    stored = fake.get_item(f"USER#sub-new-edu", "PROFILE")
    assert stored is not None
    assert stored["firstName"] == "Alex"
    assert stored["tenantId"] == "ua-edu"


def test_demo_account_profile_deleted_recreated(monkeypatch):
    """Demo account whose profile was deleted gets a fresh profile on next login."""
    import api as api_mod, json, calendar_api

    fake = FakeDb()
    # DEMOACCT map exists → campus resolution works
    fake.put_item({"pk": "DEMOACCT#demo@example.com", "sk": "MAP", "tenantId": "ua-edu"})
    fake.put_item({
        "pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu",
        "name": "University of Alabama Demo",
        "theme": {"primary": "#9E1B32", "ink": "#FFFFFF"},
        "colorStatus": "verified",
    })
    # No USER#sub-demo/PROFILE in DB (simulates deleted profile)

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "put_item", fake.put_item)
    monkeypatch.setattr(calendar_api, "new_token", lambda: "demotoken-new")

    resp = api_mod.get_me(_jwt_event("sub-demo-reset", "demo@example.com", name="Luca S"), "sub-demo-reset")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])

    profile = body["profile"]
    assert profile["tenantId"] == "ua-edu"
    assert profile["firstName"] == "Luca"
    assert profile["lastName"] == "S"
    assert profile["displayName"] == "Luca S"
    assert body["needsName"] is False
    assert body["tenant"]["id"] == "ua-edu"

    # Profile stored in DB
    stored = fake.get_item("USER#sub-demo-reset", "PROFILE")
    assert stored is not None
    assert stored["tenantId"] == "ua-edu"


def test_demo_account_profile_deleted_no_name_claim(monkeypatch):
    """Demo account with deleted profile and no name claim → needsName=True."""
    import api as api_mod, json, calendar_api

    fake = FakeDb()
    fake.put_item({"pk": "DEMOACCT#demo2@example.com", "sk": "MAP", "tenantId": "ua-edu"})
    fake.put_item({
        "pk": "TENANTS", "sk": "T#ua-edu", "id": "ua-edu",
        "name": "University of Alabama Demo",
        "theme": {"primary": "#9E1B32", "ink": "#FFFFFF"},
        "colorStatus": "verified",
    })

    monkeypatch.setattr(api_mod.db, "get_item", fake.get_item)
    monkeypatch.setattr(api_mod.db, "put_item", fake.put_item)
    monkeypatch.setattr(calendar_api, "new_token", lambda: "demotoken-noname")

    resp = api_mod.get_me(_jwt_event("sub-demo-noname", "demo2@example.com"), "sub-demo-noname")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["needsName"] is True
    assert body["profile"]["firstName"] == ""
    assert body["tenant"]["id"] == "ua-edu"


# ── color_worker uses lib.bedrock.converse ────────────────────────────────────

def test_color_worker_ask_model_uses_converse(monkeypatch):
    """_ask_model uses lib.bedrock.converse and extract_text, not invoke_model."""
    import color_worker
    from unittest.mock import MagicMock

    fake_bd = MagicMock()
    fake_bd.extract_text.return_value = "#9E1B32 0.9"
    fake_bd.converse.return_value = {"output": {"message": {"content": [{"text": "#9E1B32 0.9"}]}}}
    monkeypatch.setattr(color_worker, "bd", fake_bd)

    color, confidence = color_worker._ask_model("ua.edu", "University of Alabama", ["#9E1B32", "#FFFFFF"])
    assert color == "#9E1B32"
    assert abs(confidence - 0.9) < 0.01
    fake_bd.converse.assert_called_once()
    assert not hasattr(fake_bd, "invoke_model") or not fake_bd.invoke_model.called
