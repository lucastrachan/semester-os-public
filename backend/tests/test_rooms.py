import json
import unittest

import _market_fakes as mf
from _market_fakes import ME, OTHER, AUB, GT
import listings_api as L
import rooms_api as R
from lib import convos, rooms

ROOM = "ua.FA26.MIS405"


def ev(body=None, qs=None):
    return {"body": json.dumps(body) if body is not None else None, "queryStringParameters": qs,
            "requestContext": {"http": {"sourceIp": "203.0.113.5"}}}


def js(r):
    return json.loads(r["body"])


def add_course(db, sub, code="MIS 405", term="Fall 2026", title="Systems", cid="cccc0001", created="2026-08-20T10:00:00Z", **kw):
    db.put_item({"pk": f"USER#{sub}", "sk": f"COURSE#{cid}", "id": cid, "courseCode": code, "term": term, "title": title,
                 "createdAt": created, "status": "READY", **kw})


class Base(unittest.TestCase):
    def setUp(self):
        self.db = mf.world([L, R, rooms])
        add_course(self.db, ME)
        add_course(self.db, OTHER, code="mis405", term="FALL 2026", title="")
        add_course(self.db, AUB, code="MIS 405")

    def send(self, sub, text, rid=ROOM):
        return R.send_message(ev({"text": text}), sub, rid)

    def err(self, r, status, code):
        self.assertEqual((r["statusCode"], js(r).get("error")), (status, code), r["body"])

    def get(self, sub, rid=ROOM, **qs):
        return R.get_messages(ev(qs=qs or None), sub, rid)


class Membership(unittest.TestCase):
    def test_term_normalisation(self):
        self.assertEqual(rooms.norm_term("Fall 2026"), "FA26")
        self.assertEqual(rooms.norm_term("fall 26"), "FA26")
        self.assertEqual(rooms.norm_term("2026 Spring"), "SP26")
        self.assertEqual(rooms.norm_term("202640"), "202640")
        self.assertEqual(rooms.norm_term("", "2026-09-02T00:00:00Z"), "FA26")
        self.assertEqual(rooms.norm_term(None, "2027-02-02T00:00:00Z"), "SP27")
        self.assertEqual(rooms.norm_term("", "2026-06-20T00:00:00Z"), "SU26")
        self.assertEqual(rooms.norm_code("MIS 405"), "MIS405")
        self.assertEqual(rooms.norm_code(""), "")
        self.assertEqual(rooms.norm_code("Intro"), "")


class Rooms(Base):
    def test_list_auto_membership_same_campus_only(self):
        d = js(R.list_rooms(ev(), ME))
        self.assertEqual([r["id"] for r in d["rooms"]], [ROOM])
        r = d["rooms"][0]
        self.assertFalse(r["verified"])
        self.assertEqual((r["code"], r["title"], r["campus"]["shortName"], r["memberCount"]), ("MIS405", "Systems", "UA", 1))
        # the Auburn student with the same code is in a different room and cannot open the UA one
        self.assertEqual([x["id"] for x in js(R.list_rooms(ev(), AUB))["rooms"]], ["auburn.FA26.MIS405"])
        self.err(R.get_messages(ev(), AUB, ROOM), 404, "not_found")
        self.err(self.send(AUB, "hi all"), 404, "not_found")

    def test_member_count_and_term_split(self):
        R.list_rooms(ev(), ME)
        R.list_rooms(ev(), OTHER)
        R.list_rooms(ev(), OTHER)
        self.assertEqual(js(R.list_rooms(ev(), ME))["rooms"][0]["memberCount"], 2)
        add_course(self.db, ME, code="MIS405", term="Spring 2027", cid="cccc0002")
        self.assertEqual(sorted(r["id"] for r in js(R.list_rooms(ev(), ME))["rooms"]), [ROOM, "ua.SP27.MIS405"])

    def test_no_term_uses_created_date_and_unbuilt_class_has_no_room(self):
        add_course(self.db, GT, code="CS 101", term="", cid="cccc0009", created="2026-09-01T00:00:00Z")
        self.db.put_item({"pk": f"USER#{ME}", "sk": "COURSE#building1", "id": "building1", "courseCode": "", "term": ""})
        self.assertEqual([r["id"] for r in js(R.list_rooms(ev(), GT))["rooms"]], ["gatech.FA26.CS101"])
        self.assertEqual(len(js(R.list_rooms(ev(), ME))["rooms"]), 1)

    def test_deleted_class_removes_access(self):
        self.db.items.pop((f"USER#{ME}", "COURSE#cccc0001"))
        self.assertEqual(js(R.list_rooms(ev(), ME))["rooms"], [])
        self.err(self.send(ME, "anyone here?"), 404, "not_found")

    def test_bad_ids_are_404(self):
        for rid in ("../x", "ua.FA26.NOPE1", "nope"):
            self.err(R.get_messages(ev(), ME, rid), 404, "not_found")

    def test_banned_and_disabled_campus(self):
        self.db.put_item({"pk": "BANNED_USERS", "sk": f"U#{ME}", "reason": "x"})
        self.err(R.list_rooms(ev(), ME), 403, "account_restricted")
        self.err(self.send(ME, "hello there"), 403, "account_restricted")
        self.db.items.pop(("BANNED_USERS", f"U#{ME}"))
        self.db.update_item("TENANTS", "T#ua", {"disabled": True})
        self.err(R.list_rooms(ev(), ME), 403, "campus_disabled")

    def test_info(self):
        d = js(R.room_info(ev(), ME, ROOM))
        self.assertFalse(d["info"]["verified"])
        self.assertIn("not verified", d["info"]["notice"])
        self.assertTrue(d["info"]["safetyTips"])
        self.assertEqual(d["info"]["rules"]["maxChars"], 500)


class Messaging(Base):
    def test_send_read_and_privacy(self):
        r = self.send(ME, "Does anyone have notes for chapter 3?")
        self.assertEqual(r["statusCode"], 201, r["body"])
        m = js(r)["message"]
        self.assertEqual(m["from"], "me")
        self.assertRegex(m["name"], r"^Classmate \d{4}$")
        d = js(self.get(OTHER))
        self.assertEqual([x["from"] for x in d["messages"]], ["them"])
        blob = r["body"] + json.dumps(d)
        for secret in (ME, "sam1@ua.edu", "Sam", "senderHash"):
            self.assertNotIn(secret, blob)

    def test_unread_and_mark_read_and_polling(self):
        R.list_rooms(ev(), OTHER)
        self.send(ME, "first message here")
        self.send(ME, "second message here")
        lst = js(R.list_rooms(ev(), OTHER))
        self.assertEqual((lst["rooms"][0]["unread"], lst["unreadTotal"]), (2, 2))
        self.assertEqual(lst["rooms"][0]["lastMessage"]["from"], "them")
        d = js(self.get(OTHER))
        self.assertEqual(len(d["messages"]), 2)
        self.assertEqual(js(R.list_rooms(ev(), OTHER))["unreadTotal"], 0)
        self.send(ME, "third message here")
        d2 = js(self.get(OTHER, after=d["nextCursor"]))
        self.assertEqual([m["text"] for m in d2["messages"]], ["third message here"])
        self.assertEqual(js(self.get(OTHER, after=d2["nextCursor"]))["messages"], [])
        self.err(self.get(OTHER, after="garbage"), 400, "validation_error")

    def test_validation(self):
        bad = ["", "   ", "x" * 501, "see https://evil.example", "go to site.com", "mail me sam@example.com", "hey @everyone",
               "call 205-555-0142 now", "my id is 12345678", "<b>hi</b>", "![x](y)", "what the fuck", "my password is hunter2"]
        for t in bad:
            self.err(self.send(ME, t), 400, "validation_error")
        self.err(R.send_message(ev({"text": 5}), ME, ROOM), 400, "validation_error")
        self.err(R.send_message(ev({"text": "hi there", "x": 1}), ME, ROOM), 400, "validation_error")
        self.assertEqual(self.send(ME, "Exam is 2026-10-20 at 12:30 in room 214, ch. 3 and 4").get("statusCode"), 201)
        self.assertEqual(self.send(ME, "x" * 500)["statusCode"], 201)

    def test_repeat_and_spam(self):
        self.assertEqual(self.send(ME, "anyone want to study together?")["statusCode"], 201)
        self.err(self.send(ME, "Anyone want to study  together?"), 400, "validation_error")
        for i in range(2):
            self.send(ME, "same long spam text here" )
            self.send(OTHER, "filler number %d" % i)
            self.send(ME, "something different %d please" % i)
        self.send(OTHER, "ok")

    def test_spam_guard_across_day(self):
        for i in range(3):
            self.send(ME, "buy my essays buy my essays")
            self.send(ME, "break up the repeat %d ok" % i)
        r = self.send(ME, "buy my essays buy my essays")
        self.err(r, 429, "spam")

    def test_rate_limit_per_minute(self):
        codes = [self.send(ME, "message number %d here" % i)["statusCode"] for i in range(14)]
        self.assertEqual(codes[:12], [201] * 12)
        self.assertEqual(codes[12], 429)
        self.assertEqual(js(self.send(ME, "one more message ok")).get("error"), "rate_limited")

    def test_trim_cap(self):
        old = rooms.MAX_ROOM_MESSAGES
        rooms.MAX_ROOM_MESSAGES = 5
        try:
            for i in range(8):
                rooms.add_message(ROOM, ME, "Classmate 0001", f"msg {i}")
            self.assertEqual([m["text"] for m in rooms.list_messages(ROOM)], [f"msg {i}" for i in range(3, 8)])
        finally:
            rooms.MAX_ROOM_MESSAGES = old

    def test_ttl_is_60_days(self):
        item = rooms.add_message(ROOM, ME, "Classmate 0001", "hello")
        self.assertAlmostEqual(item["ttl"] - convos.now_dt().timestamp(), 60 * 86400, delta=60)

    def test_closed_room(self):
        self.send(ME, "before the close")
        rooms.close_room(ROOM, "admin", "abuse")
        self.err(self.send(ME, "after the close"), 403, "room_closed")
        d = js(self.get(ME))
        self.assertEqual(len(d["messages"]), 1)
        self.assertEqual((d["room"]["closed"], d["room"]["canSend"]), (True, False))
        rooms.reopen_room(ROOM)
        self.assertEqual(self.send(ME, "back again now")["statusCode"], 201)


class Settings(Base):
    def test_mute_leave_rejoin(self):
        R.list_rooms(ev(), OTHER)
        self.send(ME, "hello classmates")
        self.assertEqual(js(R.room_action(ev(), OTHER, ROOM, "mute"))["muted"], True)
        r = js(R.list_rooms(ev(), OTHER))["rooms"][0]
        self.assertEqual((r["muted"], r["unread"]), (True, 0))
        R.room_action(ev(), OTHER, ROOM, "unmute")
        self.assertEqual(js(R.list_rooms(ev(), OTHER))["rooms"][0]["unread"], 1)
        n = js(R.list_rooms(ev(), ME))["rooms"][0]["memberCount"]
        self.assertEqual(js(R.room_action(ev(), OTHER, ROOM, "leave"))["left"], True)
        self.assertEqual(js(R.list_rooms(ev(), OTHER))["rooms"], [])
        self.assertEqual(js(R.list_rooms(ev(), OTHER, ))["rooms"], [])
        self.assertEqual(len(js(R.list_rooms(ev(qs={"includeLeft": "true"}), OTHER))["rooms"]), 0 + 1)
        self.err(self.get(OTHER), 403, "room_left")
        self.err(self.send(OTHER, "i left already"), 403, "room_left")
        self.assertEqual(js(R.list_rooms(ev(), ME))["rooms"][0]["memberCount"], max(1, n - 1))
        R.room_action(ev(), OTHER, ROOM, "rejoin")
        self.assertEqual(self.send(OTHER, "i am back again")["statusCode"], 201)

    def test_actions_need_membership(self):
        self.err(R.room_action(ev(), GT, ROOM, "leave"), 404, "not_found")


class Nickname(Base):
    def test_default_stable_and_never_identifying(self):
        a = js(R.get_nickname(ev(), ME))
        self.assertTrue(a["isDefault"])
        self.assertRegex(a["nickname"], r"^Classmate \d{4}$")
        self.assertEqual(a, js(R.get_nickname(ev(), ME)))

    def test_set_clean_and_reset(self):
        r = js(R.patch_nickname(ev({"nickname": "  Study   Bee  "}), ME))
        self.assertEqual((r["nickname"], r["isDefault"], r["avatar"]), ("Study Bee", False, None))
        self.assertEqual(js(self.send(ME, "hello from the bee")).get("message", {}).get("name"), "Study Bee")
        self.assertEqual(js(R.patch_nickname(ev({"nickname": ""}), ME))["isDefault"], True)

    def test_avatar_set_and_returned_in_messages(self):
        R.patch_nickname(ev({"nickname": "Bee Cee", "avatar": "robot-05"}), ME)
        r = js(R.get_nickname(ev(), ME))
        self.assertEqual(r["avatar"], "robot-05")
        msg = js(self.send(ME, "hi with avatar")).get("message", {})
        self.assertEqual(msg["avatar"], "robot-05")
        self.assertIsNotNone(msg["userId"])

    def test_invalid_avatar_rejected(self):
        self.err(R.patch_nickname(ev({"avatar": "robot-99"}), ME), 400, "validation_error")
        self.err(R.patch_nickname(ev({"avatar": "shark"}), ME), 400, "validation_error")

    def test_rejected_nicknames(self):
        for n in ("a", "x" * 25, "sam@example.com", "<script>", "12345678", "fuck you", "site.com", "Sam 1234567", 5):
            self.err(R.patch_nickname(ev({"nickname": n}), ME), 400, "validation_error")
        self.err(R.patch_nickname(ev({}), ME), 400, "validation_error")


class BlockReport(Base):
    def setUp(self):
        super().setUp()
        self.mid = js(self.send(OTHER, "annoying message text"))["message"]["id"]
        self.mine = js(self.send(ME, "my own message text"))["message"]["id"]

    def test_block_hides_sender_only_for_blocker(self):
        self.assertEqual(js(R.block_sender(ev({"messageId": self.mid}), ME, ROOM)), {"blocked": True})
        self.assertEqual([m["from"] for m in js(self.get(ME))["messages"]], ["me"])
        self.assertEqual(len(js(self.get(OTHER))["messages"]), 2)

    def test_block_errors(self):
        self.err(R.block_sender(ev({"messageId": self.mine}), ME, ROOM), 400, "validation_error")
        self.err(R.block_sender(ev({"messageId": "2026-01-01T00:00:00Z#zzzz"}), ME, ROOM), 400, "validation_error")
        self.err(R.block_sender(ev({"messageId": self.mid}), AUB, ROOM), 404, "not_found")

    def test_report_goes_to_admin_queue_with_evidence(self):
        r = R.report_room(ev({"reason": "harassment", "note": "rude", "messageId": self.mid}), ME, ROOM)
        self.assertEqual(js(r), {"reported": True})
        rep = [v for k, v in self.db.items.items() if k[0] == "REPORTS"]
        self.assertEqual(len(rep), 1)
        q = rep[0]
        self.assertEqual((q["kind"], q["status"], q["reason"], q["roomId"]), ("room", "open", "harassment", ROOM))
        self.assertEqual([e["text"] for e in q["evidence"]], ["annoying message text", "my own message text"])
        self.assertRegex(q["id"], r"^[a-z]{4,12}\.[a-z0-9]{8}\.[0-9a-f]{16}$")   # admin resolve route pattern
        self.assertNotIn(ME, json.dumps(q.get("evidence")))
        R.report_room(ev({"reason": "spam"}), ME, ROOM)
        self.assertEqual(len([1 for k in self.db.items if k[0] == "REPORTS"]), 1)

    def test_report_validation(self):
        self.err(R.report_room(ev({"reason": "nope"}), ME, ROOM), 400, "validation_error")
        self.err(R.report_room(ev({"reason": "spam", "note": "x" * 300}), ME, ROOM), 400, "validation_error")
        self.err(R.report_room(ev({"reason": "spam"}), AUB, ROOM), 404, "not_found")


class Router(Base):
    def test_handle(self):
        self.assertEqual(R.handle(ev(), ME, "/rooms", "GET")["statusCode"], 200)
        self.assertEqual(R.handle(ev({"text": "hello router"}), ME, f"/rooms/{ROOM}/messages", "POST")["statusCode"], 201)
        self.assertEqual(R.handle(ev(), ME, f"/rooms/{ROOM}/messages", "GET")["statusCode"], 200)
        self.assertEqual(R.handle(ev(), ME, f"/rooms/{ROOM}/mute", "POST")["statusCode"], 200)
        self.assertEqual(R.handle(ev(), ME, "/me/nickname", "GET")["statusCode"], 200)
        self.assertIsNone(R.handle(ev(), ME, "/courses", "GET"))
        self.assertIsNone(R.handle(ev(), ME, f"/rooms/{ROOM}/mute", "GET"))
        self.assertIsNone(R.handle(ev(), ME, "/rooms/bad", "GET"))

    def test_delete_user_data(self):
        R.patch_nickname(ev({"nickname": "Bee Bee"}), ME)
        R.list_rooms(ev(), ME)
        self.assertGreaterEqual(rooms.delete_user_data(ME), 2)
        self.assertIsNone(self.db.get_item(f"USER#{ME}", "NICK"))


if __name__ == "__main__":
    unittest.main()
