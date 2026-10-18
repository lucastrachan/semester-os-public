import json
import unittest

import _market_fakes as mf
from _market_fakes import ME, OTHER, AUB, GT, add_listing
import listings_api as L
import messages_api as M
from lib import convos

THIRD = "user-eeee-5555"


def ev(body=None, qs=None):
    return {"body": json.dumps(body) if body is not None else None, "queryStringParameters": qs,
            "requestContext": {"http": {"sourceIp": "203.0.113.5"}}}


def js(r):
    return json.loads(r["body"])


def today():
    return convos.now_dt().strftime("%Y%m%d")


class Base(unittest.TestCase):
    def setUp(self):
        self.db = mf.world([L, M])
        self.db.put_item({"pk": f"USER#{THIRD}", "sk": "PROFILE", "sub": THIRD, "email": "third@ua.edu", "tenantId": "ua",
                          "displayName": "Tess Third"})
        add_listing(self.db, "list0001", "ua", seller=OTHER, title="Calc book")

    def start(self, sub=ME, lid="list0001", text="Is this still available?"):
        return M.start_conversation(ev({"message": text}), sub, lid)

    def begin(self, **kw):
        r = self.start(**kw)
        self.assertEqual(r["statusCode"], 201, r["body"])
        return js(r)["conversation"]["id"]

    def send(self, sub, cid, text):
        return M.send_message(ev({"text": text}), sub, cid)

    def assert_err(self, r, status, code):
        self.assertEqual((r["statusCode"], js(r).get("error")), (status, code), r["body"])

    def reports(self):
        return [v for k, v in self.db.items.items() if k[0] == "REPORTS"]


class StartRules(Base):
    def test_start_creates_conversation(self):
        r = self.start()
        d = js(r)
        self.assertEqual(r["statusCode"], 201)
        self.assertTrue(d["created"])
        self.assertEqual(d["conversation"]["role"], "buyer")
        self.assertEqual(d["conversation"]["other"]["name"], "Seller")
        self.assertEqual([m["from"] for m in d["messages"]], ["me"])

    def test_own_listing(self):
        self.assert_err(self.start(sub=OTHER), 400, "own_listing")

    def test_missing_and_bad_ids(self):
        self.assert_err(self.start(lid="nope0000"), 404, "not_found")
        self.assert_err(self.start(lid="../x"), 404, "not_found")

    def test_demo_listing_starts_conversation(self):
        add_listing(self.db, "demo0001", "ua", demo=True)
        r = self.start(lid="demo0001")
        self.assertEqual(r["statusCode"], 201, r["body"])
        d = js(r)
        self.assertEqual(d["conversation"]["other"]["name"], "Demo seller (auto-reply)")

    def test_demo_listing_auto_reply_present(self):
        add_listing(self.db, "demo0001", "ua", demo=True)
        cid = js(self.start(lid="demo0001"))["conversation"]["id"]
        from lib import convos as cv
        msgs = cv.list_messages(cid)
        froms = [m["from"] for m in msgs]
        self.assertIn("seller", froms)  # auto-reply injected

    def test_invisible_listing_other_campus_closed_network(self):
        add_listing(self.db, "gt000001", "gatech", seller=GT)
        self.assert_err(self.start(lid="gt000001"), 404, "not_found")

    def test_other_campus_open_network_is_allowed(self):
        add_listing(self.db, "au000001", "auburn", seller=AUB)
        r = self.start(lid="au000001")
        self.assertEqual(r["statusCode"], 201, r["body"])
        self.assertEqual(js(r)["conversation"]["other"]["campus"]["shortName"], "AU")

    def test_sold_removed_flagged_listing(self):
        for lid, extra in (("sold0001", {"status": "sold"}), ("rem00001", {"status": "removed"}), ("flag0001", {"flagged": True})):
            add_listing(self.db, lid, "ua", seller=OTHER, **extra)
            self.assert_err(self.start(lid=lid), 404, "not_found")

    def test_banned_seller_looks_missing_and_banned_buyer_restricted(self):
        self.db.put_item({"pk": "BANNED_USERS", "sk": f"U#{OTHER}", "reason": "x"})
        self.assert_err(self.start(), 404, "not_found")
        self.db.items.pop(("BANNED_USERS", f"U#{OTHER}"))
        self.db.put_item({"pk": "BANNED_USERS", "sk": f"U#{ME}", "reason": "x"})
        self.assert_err(self.start(), 403, "account_restricted")

    def test_one_open_conversation_per_buyer_per_listing(self):
        cid = self.begin()
        r = self.start(text="Can you do 30 dollars?")
        d = js(r)
        self.assertEqual(r["statusCode"], 200)
        self.assertFalse(d["created"])
        self.assertEqual(d["conversation"]["id"], cid)
        self.assertEqual(len([1 for k in self.db.items if k[0].startswith("CONVO#") and k[1] == "META"]), 1)
        self.assertEqual(len(convos.list_messages(cid)), 2)

    def test_second_buyer_gets_own_conversation(self):
        self.assertNotEqual(self.begin(), self.begin(sub=THIRD))

    def test_closed_conversation_blocks_restart(self):
        cid = self.begin()
        convos.close_conversation(cid, "admin")
        self.assert_err(self.start(text="hello again friend"), 409, "conversation_closed")

    def test_listing_removed_later_closes(self):
        cid = self.begin()
        self.db.update_item("LISTING#list0001", "META", {"status": "removed"})
        self.assert_err(self.start(text="anyone there?"), 409, "conversation_closed")
        self.assert_err(self.send(ME, cid, "hello?"), 403, "conversation_closed")

    def test_listing_flagged_later_closes(self):
        cid = self.begin()
        self.db.update_item("LISTING#list0001", "META", {"flagged": True})
        c = js(M.get_conversation(ev(), ME, cid))["conversation"]
        self.assertEqual(c["closedReason"], "listing_flagged")
        self.assertFalse(c["canSend"])

    def test_campus_disabled_closes(self):
        add_listing(self.db, "au000001", "auburn", seller=AUB)
        cid = self.begin(lid="au000001")
        self.db.update_item("TENANTS", "T#auburn", {"disabled": True})
        c = js(M.get_conversation(ev(), ME, cid))["conversation"]
        self.assertEqual(c["closedReason"], "campus_unavailable")

    def test_blocked_seller_cannot_be_messaged(self):
        convos.block_user(OTHER, ME)
        self.assert_err(self.start(), 403, "cannot_message")

    def test_unknown_body_field_rejected(self):
        r = M.start_conversation(ev({"message": "hello there", "sellerSub": "x"}), ME, "list0001")
        self.assertEqual(r["statusCode"], 400)


class Idor(Base):
    def setUp(self):
        super().setUp()
        self.cid = self.begin()

    def test_participants_can_get(self):
        for sub in (ME, OTHER):
            self.assertEqual(M.get_conversation(ev(), sub, self.cid)["statusCode"], 200)

    def test_outsiders_get_standard_404_everywhere(self):
        missing = M.get_conversation(ev(), THIRD, "zzzzzzzz")
        for sub in (THIRD, AUB, GT):
            checks = [
                M.get_conversation(ev(), sub, self.cid),
                self.send(sub, self.cid, "let me in please"),
                M.block_conversation(ev(), sub, self.cid),
                M.report_conversation(ev({"reason": "spam"}), sub, self.cid),
            ]
            for r in checks:
                self.assert_err(r, 404, "not_found")
            self.assertEqual(checks[0]["body"], missing["body"])
        self.assertEqual(len(convos.list_messages(self.cid)), 1)
        self.assertEqual(self.db.items[("CONVO#" + self.cid, "META")]["status"], "open")
        self.assertEqual(self.reports(), [])

    def test_bad_ids_are_404(self):
        for bad in ("", "short", "UPPERCASE", "../../etc", "a" * 9, None):
            self.assert_err(M.get_conversation(ev(), ME, bad), 404, "not_found")

    def test_empty_or_odd_sub_never_matches(self):
        meta = self.db.items[("CONVO#" + self.cid, "META")]
        self.assertIsNone(convos.participant_role(meta, ""))
        self.assertIsNone(convos.participant_role(meta, None))

    def test_list_only_shows_own(self):
        self.assertEqual(len(js(M.list_conversations(ev(), THIRD))["conversations"]), 0)
        self.assertEqual(len(js(M.list_conversations(ev(), OTHER))["conversations"]), 1)


class Validation(Base):
    def setUp(self):
        super().setUp()
        self.cid = self.begin()

    def test_empty_whitespace_nonstring(self):
        for t in ("", "   \n ", None, 5, ["x"]):
            self.assert_err(self.send(ME, self.cid, t), 400, "validation_error")

    def test_length(self):
        self.assertEqual(self.send(ME, self.cid, "a" * 1000)["statusCode"], 201)
        self.assert_err(self.send(ME, self.cid, "b" * 1001), 400, "validation_error")

    def test_links_rejected(self):
        for t in ("see http://evil.example/x", "https://x.co", "go to www.evil.com now", "mail me mailto:a@b.c",
                  "javascript:alert(1)", "visit evil.com//path", "look at //evil.com"):
            self.assert_err(self.send(ME, self.cid, t), 400, "validation_error")

    def test_plain_text_with_dots_ok(self):
        self.assertEqual(self.send(ME, self.cid, "Meet at 3.30 pm, the book is 8.5 inches.")["statusCode"], 201)

    def test_control_chars_cleaned(self):
        r = self.send(ME, self.cid, "hi\x00 there\x07 friend")
        self.assertEqual(js(r)["message"]["text"], "hi there friend")

    def test_repeat_of_own_previous_message_rejected(self):
        self.send(ME, self.cid, "Sounds good see you")
        self.assert_err(self.send(ME, self.cid, "sounds   GOOD see you"), 400, "validation_error")
        self.assertEqual(self.send(OTHER, self.cid, "Sounds good see you")["statusCode"], 201)

    def test_spam_guard(self):
        txt = "Hi, is this still available today?"
        codes = []
        for i in range(5):
            codes.append(self.send(ME, self.cid, txt)["statusCode"])
            self.send(ME, self.cid, f"another distinct message number {i}")
        self.assertEqual(codes[:3], [201, 201, 201])
        self.assertIn(429, codes)

    def test_bad_cursor_and_limits(self):
        self.assert_err(M.get_conversation(ev(qs={"after": "garbage"}), ME, self.cid), 400, "validation_error")
        self.assert_err(M.get_conversation(ev(qs={"limit": "0"}), ME, self.cid), 400, "validation_error")
        self.assert_err(M.get_conversation(ev(qs={"limit": "abc"}), ME, self.cid), 400, "validation_error")

    def test_conversation_full(self):
        self.db.update_item("CONVO#" + self.cid, "META", {"msgCount": convos.MAX_MESSAGES})
        self.assert_err(self.send(ME, self.cid, "one more"), 409, "conversation_full")


class Caps(Base):
    def test_daily_message_cap(self):
        cid = self.begin()
        self.db.put_item({"pk": f"USER#{ME}", "sk": "CAP#msgs#" + today(), "n": M.MAX_MESSAGES_PER_DAY})
        self.assert_err(self.send(ME, cid, "over the cap"), 429, "daily_cap")

    def test_daily_new_conversation_cap(self):
        self.db.put_item({"pk": f"USER#{ME}", "sk": "CAP#convs#" + today(), "n": M.MAX_NEW_CONVOS_PER_DAY})
        self.assert_err(self.start(), 429, "daily_cap")

    def test_cap_boundary_allows_last(self):
        self.db.put_item({"pk": f"USER#{ME}", "sk": "CAP#convs#" + today(), "n": M.MAX_NEW_CONVOS_PER_DAY - 1})
        self.assertEqual(self.start()["statusCode"], 201)

    def test_per_minute_rate_limit(self):
        cid = self.begin()
        codes = [self.send(ME, cid, f"distinct message {i} about the book")["statusCode"] for i in range(40)]
        self.assertIn(429, codes)


class Blocking(Base):
    def test_block_closes_for_both_and_prevents_new(self):
        cid = self.begin()
        self.assertEqual(js(M.block_conversation(ev(), OTHER, cid)), {"blocked": True})
        self.assertEqual(M.block_conversation(ev(), OTHER, cid)["statusCode"], 200)  # idempotent
        for sub in (ME, OTHER):
            c = js(M.get_conversation(ev(), sub, cid))["conversation"]
            self.assertEqual((c["status"], c["closedReason"], c["canSend"]), ("closed", "blocked", False))
        self.assert_err(self.send(ME, cid, "why?"), 403, "conversation_closed")
        self.assert_err(self.send(OTHER, cid, "go away"), 403, "conversation_closed")
        add_listing(self.db, "list0002", "ua", seller=OTHER)
        self.assert_err(self.start(lid="list0002"), 403, "cannot_message")
        add_listing(self.db, "list0003", "ua", seller=ME)
        self.assertEqual(self.start(sub=OTHER, lid="list0003")["statusCode"], 201)

    def test_closed_view_does_not_say_who_blocked(self):
        cid = self.begin()
        M.block_conversation(ev(), ME, cid)
        for sub in (ME, OTHER):
            body = M.get_conversation(ev(), sub, cid)["body"]
            self.assertNotIn("blockedBy", body)

    def test_inbox_shows_closed(self):
        cid = self.begin()
        M.block_conversation(ev(), OTHER, cid)
        d = js(M.list_conversations(ev(qs={"status": "closed"}), ME))
        self.assertEqual([c["id"] for c in d["conversations"]], [cid])
        self.assertEqual(js(M.list_conversations(ev(qs={"status": "open"}), ME))["conversations"], [])


class Reports(Base):
    def test_evidence_is_last_ten_messages(self):
        cid = self.begin()
        for i in range(14):
            self.send(OTHER if i % 2 else ME, cid, f"message number {i} here")
        r = M.report_conversation(ev({"reason": "harassment", "note": "rude"}), ME, cid)
        self.assertEqual(js(r), {"reported": True})
        self.assertEqual(len(self.reports()), 1)
        rep = self.reports()[0]
        self.assertEqual(len(rep["evidence"]), 10)
        self.assertEqual(rep["evidence"][-1]["text"], "message number 13 here")
        self.assertEqual((rep["kind"], rep["status"], rep["reportedSub"], rep["reporterRole"]), ("conversation", "open", OTHER, "buyer"))

    def test_one_report_per_person(self):
        cid = self.begin()
        M.report_conversation(ev({"reason": "spam"}), ME, cid)
        M.report_conversation(ev({"reason": "scam"}), ME, cid)
        self.assertEqual([v["reason"] for v in self.reports()], ["spam"])
        M.report_conversation(ev({"reason": "scam"}), OTHER, cid)
        self.assertEqual(len(self.reports()), 2)

    def test_validation(self):
        cid = self.begin()
        self.assert_err(M.report_conversation(ev({"reason": "bogus"}), ME, cid), 400, "validation_error")
        self.assert_err(M.report_conversation(ev({}), ME, cid), 400, "validation_error")
        self.assert_err(M.report_conversation(ev({"reason": "spam", "note": "x" * 300}), ME, cid), 400, "validation_error")
        self.assertEqual(self.reports(), [])

    def test_report_daily_cap(self):
        cid = self.begin()
        self.db.put_item({"pk": f"USER#{ME}", "sk": "CAP#msgreports#" + today(), "n": M.MAX_REPORTS_PER_DAY})
        self.assert_err(M.report_conversation(ev({"reason": "spam"}), ME, cid), 429, "daily_cap")

    def test_report_works_on_closed_conversation(self):
        cid = self.begin()
        M.block_conversation(ev(), ME, cid)
        self.assertEqual(M.report_conversation(ev({"reason": "spam"}), ME, cid)["statusCode"], 200)


class SoldNotice(Base):
    def test_sold_notice_once_to_buyer(self):
        cid = self.begin()
        self.assertEqual(convos.notify_listing_sold("list0001"), 1)
        self.assertEqual(convos.notify_listing_sold("list0001"), 0)
        for sub in (ME, OTHER):
            last = js(M.get_conversation(ev(), sub, cid))["messages"][-1]
            self.assertEqual((last["from"], last["text"]), ("system", convos.SOLD_NOTICE))

    def test_sold_through_listing_update(self):
        cid = self.begin()
        r = L.update_listing(ev({"status": "sold"}), OTHER, "list0001")
        self.assertEqual(r["statusCode"], 200, r["body"])
        d = js(M.get_conversation(ev(), ME, cid))
        self.assertEqual(d["messages"][-1]["from"], "system")
        self.assertEqual(d["conversation"]["listing"]["status"], "sold")

    def test_closed_conversation_gets_no_notice(self):
        cid = self.begin()
        convos.close_conversation(cid, "blocked", blocked_by=OTHER)
        self.assertEqual(convos.notify_listing_sold("list0001"), 0)


class Unread(Base):
    def test_counters_and_mark_read(self):
        cid = self.begin()
        self.assertEqual(js(M.unread_count(ev(), OTHER))["unread"], 1)
        self.assertEqual(js(M.unread_count(ev(), ME))["unread"], 0)
        self.send(OTHER, cid, "yes it is")
        self.send(OTHER, cid, "when can you meet")
        self.assertEqual(js(M.unread_count(ev(), ME))["unread"], 2)
        inbox = js(M.list_conversations(ev(), ME))
        self.assertEqual((inbox["unreadTotal"], inbox["conversations"][0]["unread"]), (2, 2))
        lm = inbox["conversations"][0]["lastMessage"]
        self.assertEqual((lm["from"], lm["text"]), ("them", "when can you meet"))
        d = js(M.get_conversation(ev(), ME, cid))
        self.assertEqual(d["conversation"]["unread"], 0)
        self.assertEqual(js(M.unread_count(ev(), ME))["unread"], 0)
        self.assertEqual(js(M.unread_count(ev(), OTHER))["unread"], 1)

    def test_own_messages_do_not_count(self):
        cid = self.begin()
        self.send(ME, cid, "also, I can pay cash")
        self.assertEqual(js(M.unread_count(ev(), ME))["unread"], 0)

    def test_cursor_polling(self):
        cid = self.begin()
        first = js(M.get_conversation(ev(), ME, cid))
        self.assertEqual(len(first["messages"]), 1)
        cur = first["nextCursor"]
        again = js(M.get_conversation(ev(qs={"after": cur}), ME, cid))
        self.assertEqual((again["messages"], again["nextCursor"]), ([], cur))
        self.send(OTHER, cid, "reply one")
        self.send(OTHER, cid, "reply two")
        new = js(M.get_conversation(ev(qs={"after": cur}), ME, cid))
        self.assertEqual([m["text"] for m in new["messages"]], ["reply one", "reply two"])
        self.assertEqual(new["nextCursor"], new["messages"][-1]["id"])
        self.assertEqual(js(M.get_conversation(ev(qs={"after": new["nextCursor"]}), ME, cid))["messages"], [])

    def test_first_fetch_returns_last_page_oldest_first(self):
        cid = self.begin()
        for i in range(6):
            self.send(ME if i % 2 else OTHER, cid, f"msg {i} text")
        d = js(M.get_conversation(ev(qs={"limit": "3"}), ME, cid))
        self.assertEqual([m["text"] for m in d["messages"]], ["msg 3 text", "msg 4 text", "msg 5 text"])


class NoLeaks(Base):
    def test_no_email_or_sub_in_any_response(self):
        r1 = self.start()
        cid = js(r1)["conversation"]["id"]
        bodies = [r1["body"],
                  self.send(OTHER, cid, "I can meet at the library")["body"],
                  self.send(ME, cid, "great see you then")["body"]]
        for sub in (ME, OTHER):
            bodies += [M.get_conversation(ev(), sub, cid)["body"], M.list_conversations(ev(), sub)["body"],
                       M.unread_count(ev(), sub)["body"]]
        bodies += [M.report_conversation(ev({"reason": "spam"}), ME, cid)["body"], M.block_conversation(ev(), OTHER, cid)["body"]]
        for b in bodies:
            for secret in ("@", ME, OTHER, "sam1", "other.person", "sellerSub", "buyerSub", "reportedSub", "email"):
                self.assertNotIn(secret, b, secret)

    def test_buyer_with_real_name_shows_first_name_only(self):
        cid = self.begin()
        c = js(M.get_conversation(ev(), OTHER, cid))["conversation"]
        self.assertEqual((c["other"]["name"], c["role"]), ("Sam S.", "seller"))


class Retention(Base):
    def test_delete_user_data_removes_chats_and_bookkeeping(self):
        cid = self.begin()
        self.send(OTHER, cid, "hello buyer here")
        self.assertEqual(convos.delete_user_data(ME), 1)
        self.assertIsNone(self.db.get_item("CONVO#" + cid, "META"))
        self.assertEqual(convos.list_messages(cid), [])
        self.assertIsNone(self.db.get_item(f"USER#{OTHER}", f"CONV#{cid}"))
        self.assertIsNone(self.db.get_item(f"USER#{ME}", "CVLK#list0001"))


if __name__ == "__main__":
    unittest.main()
