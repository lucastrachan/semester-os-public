import unittest
from datetime import datetime, timezone

import _market_fakes as mf
from _market_fakes import ME, OTHER
from lib import convos


class Text(unittest.TestCase):
    def test_validate_message(self):
        self.assertEqual(convos.validate_message("  Is this still\tavailable?  "), "Is this still available?")
        self.assertEqual(convos.validate_message("a​‮b"), "ab")
        self.assertEqual(convos.validate_message("one\n\n\n\n\ntwo"), "one\n\ntwo")
        for bad in ("", "   ", None, 5, ["x"], "x" * 1001, "see https://evil.example", "www.evil.example", "http://x.y", "mailto:a@b.c",
                    "go to //evil.example/pay", "javascript:alert(1)", "data:text/html,x", "ftp://x.y/z", "![img](//evil.example/a.png)"):
            with self.assertRaises(convos.MsgError, msg=repr(bad)) as cm:
                convos.validate_message(bad)
            self.assertEqual(cm.exception.status, 400)
        self.assertEqual(len(convos.validate_message("x" * 1000)), 1000)

    def test_preview(self):
        self.assertEqual(convos.preview("short"), "short")
        p = convos.preview("word " * 50)
        self.assertEqual(len(p), 80)
        self.assertTrue(p.endswith("…"))
        self.assertNotIn("\n", convos.preview("a\nb"))

    def test_text_hash_ignores_case_and_spacing(self):
        self.assertEqual(convos.text_hash("Hello   THERE"), convos.text_hash("hello there"))


class Rules(unittest.TestCase):
    META = {"status": "open"}

    def test_closed_reason_order(self):
        ok = {"status": "available"}
        self.assertIsNone(convos.closed_reason(self.META, ok, True))
        self.assertEqual(convos.closed_reason({"status": "closed", "closedReason": "blocked"}, ok, True), "blocked")
        self.assertEqual(convos.closed_reason({"status": "closed"}, ok, True), "admin")
        self.assertEqual(convos.closed_reason(self.META, None, True), "listing_removed")
        self.assertEqual(convos.closed_reason(self.META, {"status": "removed"}, True), "listing_removed")
        self.assertEqual(convos.closed_reason(self.META, {"status": "available", "flagged": True}, True), "listing_flagged")
        self.assertEqual(convos.closed_reason(self.META, ok, False), "campus_unavailable")
        self.assertIsNone(convos.closed_reason(self.META, {"status": "sold"}, True))   # sold items can still be discussed

    def test_participant_role(self):
        meta = {"buyerSub": ME, "sellerSub": OTHER}
        self.assertEqual((convos.participant_role(meta, ME), convos.participant_role(meta, OTHER)), ("buyer", "seller"))
        self.assertIsNone(convos.participant_role(meta, "user-zzzz-9999"))
        self.assertIsNone(convos.participant_role(None, ME))
        self.assertIsNone(convos.participant_role({"buyerSub": None, "sellerSub": None}, None))


class Storage(unittest.TestCase):
    def setUp(self):
        self.db = mf.world([])
        self.cid = "conv0001"
        self.meta = {"pk": f"CONVO#{self.cid}", "sk": "META", "id": self.cid, "listingId": "list0001", "buyerSub": ME, "sellerSub": OTHER,
                     "status": "open", "msgCount": 0, "createdAt": "2026-10-01T00:00:00Z"}
        self.db.put_item(self.meta)
        for sub, role in ((ME, "buyer"), (OTHER, "seller")):
            self.db.put_item({"pk": f"USER#{sub}", "sk": f"CONV#{self.cid}", "id": self.cid, "role": role, "unread": 0})
        self.db.put_item({"pk": f"USER#{ME}", "sk": "CVLK#list0001", "cid": self.cid})
        self.db.put_item({"pk": "LISTING#list0001", "sk": f"CONV#{self.cid}", "cid": self.cid})

    def ptr(self, sub):
        return self.db.items[(f"USER#{sub}", f"CONV#{self.cid}")]

    def test_append_updates_conversation_and_both_inboxes(self):
        m = convos.append_message(self.cid, self.meta, "buyer", "Hello there", unread_for=("seller",))
        self.assertEqual((m["from"], m["text"]), ("buyer", "Hello there"))
        self.assertEqual(self.db.items[(f"CONVO#{self.cid}", "META")]["msgCount"], 1)
        self.assertEqual((self.ptr(OTHER)["unread"], self.ptr(ME)["unread"]), (1, 0))
        self.assertEqual((self.ptr(ME)["lastFrom"], self.ptr(OTHER)["lastPreview"]), ("buyer", "Hello there"))
        convos.append_message(self.cid, self.meta, "seller", "Yes it is", unread_for=("buyer",))
        self.assertEqual((self.ptr(OTHER)["unread"], self.ptr(ME)["unread"]), (1, 1))
        convos.mark_read(OTHER, self.cid)
        self.assertEqual(self.ptr(OTHER)["unread"], 0)

    def test_ttl_is_90_days_after_the_message(self):
        m = convos.append_message(self.cid, self.meta, "buyer", "x y z")
        days = (m["ttl"] - datetime.now(timezone.utc).timestamp()) / 86400
        self.assertTrue(89.9 < days < 90.1)
        self.assertEqual(self.ptr(ME)["ttl"], m["ttl"])
        self.assertEqual(self.db.items[("LISTING#list0001", f"CONV#{self.cid}")]["ttl"], m["ttl"])

    def test_message_cap_is_enforced_by_a_conditional_write(self):
        old = convos.MAX_MESSAGES
        convos.MAX_MESSAGES = 2
        try:
            convos.append_message(self.cid, self.meta, "buyer", "one")
            convos.append_message(self.cid, self.meta, "seller", "two")
            with self.assertRaises(convos.MsgError) as cm:
                convos.append_message(self.cid, self.meta, "buyer", "three")
            self.assertEqual((cm.exception.status, cm.exception.code), (409, "conversation_full"))
            self.assertEqual(len(convos.list_messages(self.cid)), 2)
        finally:
            convos.MAX_MESSAGES = old

    def test_messages_sort_by_time_and_cursor_strips_prefix(self):
        for t in ("a1", "b2", "c3"):
            convos.append_message(self.cid, self.meta, "buyer", t + " text")
        msgs = convos.list_messages(self.cid)
        self.assertEqual([m["text"] for m in msgs], ["a1 text", "b2 text", "c3 text"])
        self.assertFalse(convos.message_cursor(msgs[0]["sk"]).startswith("MSG#"))
        v = convos.message_view(msgs[0], "buyer")
        self.assertEqual((v["from"], set(v)), ("me", {"id", "from", "text", "at"}))
        self.assertEqual(convos.message_view(msgs[0], "seller")["from"], "them")
        self.assertEqual(convos.message_view({**msgs[0], "from": "system"}, "seller")["from"], "system")

    def test_spam_and_daily_caps(self):
        for _ in range(convos.SPAM_REPEATS_PER_DAY):
            convos.check_spam(ME, "Is this still available? I can pick up today")
        with self.assertRaises(convos.MsgError) as cm:
            convos.check_spam(ME, "is this still AVAILABLE?  I can pick up today")
        self.assertEqual(cm.exception.code, "spam")
        for _ in range(10):
            convos.check_spam(ME, "ok thanks")                              # short texts are exempt
        convos.check_spam(OTHER, "Is this still available? I can pick up today")   # per user
        for _ in range(3):
            convos.daily_cap(ME, "msgs", 3, "cap")
        with self.assertRaises(convos.MsgError) as cm:
            convos.daily_cap(ME, "msgs", 3, "cap")
        self.assertEqual(cm.exception.code, "daily_cap")

    def test_close_blocks_and_flags_both_pointers(self):
        self.assertTrue(convos.close_conversation(self.cid, "blocked", blocked_by=ME))
        meta = self.db.items[(f"CONVO#{self.cid}", "META")]
        self.assertEqual((meta["status"], meta["closedReason"], meta["blockedBy"]), ("closed", "blocked", ME))
        self.assertEqual((self.ptr(ME)["status"], self.ptr(OTHER)["closedReason"]), ("closed", "blocked"))
        self.assertFalse(convos.close_conversation("gone0000", "admin"))
        convos.block_user(ME, OTHER)
        self.assertTrue(convos.is_blocked(ME, OTHER))
        self.assertFalse(convos.is_blocked(OTHER, ME))                       # blocks are one directional
        self.assertNotIn(OTHER, [k[1] for k in self.db.items if k[0] == f"USER#{ME}"][0])  # only a hash is stored

    def test_sold_notice_goes_to_open_chats_once(self):
        self.assertEqual(convos.notify_listing_sold("list0001"), 1)
        self.assertEqual(convos.notify_listing_sold("list0001"), 0)
        msgs = convos.list_messages(self.cid)
        self.assertEqual([(m["from"], m["text"]) for m in msgs], [("system", convos.SOLD_NOTICE)])
        self.assertEqual((self.ptr(ME)["unread"], self.ptr(OTHER)["unread"]), (1, 0))

    def test_sold_notice_skips_closed_chats(self):
        convos.close_conversation(self.cid, "blocked", blocked_by=ME)
        self.assertEqual(convos.notify_listing_sold("list0001"), 0)

    def test_delete_user_data_removes_chats_for_both_and_bookkeeping(self):
        convos.append_message(self.cid, self.meta, "buyer", "hello world!")
        convos.block_user(ME, "user-zzzz-9999")
        convos.daily_cap(ME, "msgs", 100, "x")
        convos.check_spam(ME, "a long enough message text here")
        self.assertEqual(convos.delete_user_data(ME), 1)
        left = [k for k in self.db.items if self.cid in k[0] or self.cid in k[1] or k[0] == f"USER#{ME}" and k[1].startswith(("CVLK", "BLOCK", "CAP", "SPAM", "CONV"))]
        self.assertEqual(left, [])
        self.assertIsNone(self.db.get_item(f"USER#{OTHER}", f"CONV#{self.cid}"))
        self.assertIsNotNone(self.db.get_item(f"USER#{ME}", "PROFILE"))        # the profile is somebody else's job
        self.assertEqual(convos.delete_user_data(ME), 0)


if __name__ == "__main__":
    unittest.main()
