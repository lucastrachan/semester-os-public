import json
import unittest
from datetime import datetime, timedelta, timezone

import _market_fakes as mf
from _market_fakes import ME, OTHER, AUB, GT, add_listing
import books_api as B
import listings_api as L
import market_api as MA
import messages_api as M
from lib import market


orig_term_start = MA._term_start


def ev(body=None, qs=None):
    return {"body": json.dumps(body) if body is not None else None, "queryStringParameters": qs,
            "requestContext": {"http": {"sourceIp": "203.0.113.5"}}}


def js(r):
    return json.loads(r["body"])


def when(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ticket(**over):
    return {"event": "Alabama vs Tennessee", "eventAt": when(10), "venue": "Bryant-Denny Stadium", "section": "Sec 12",
            "quantity": 2, "faceValue": 45, "transferMethod": "official_app", **over}


def tutoring(**over):
    return {"subjects": ["Calculus I"], "courseCodes": ["math125"], "mode": "both", "availability": "Weeknights", "standing": "junior", **over}


class Base(unittest.TestCase):
    def setUp(self):
        self.db = mf.world([L, B, MA, M])
        for tid in ("ua", "auburn", "gatech"):
            self.db.update_item("TENANTS", f"T#{tid}", {"categories": list(market.CATEGORIES)})

    def post(self, sub=ME, **body):
        return L.create_listing(ev(body), sub)

    def make(self, sub=ME, **body):
        r = self.post(sub, **body)
        self.assertEqual(r["statusCode"], 201, r["body"])
        return js(r)["listing"]

    def bad(self, sub=ME, code=400, **body):
        r = self.post(sub, **body)
        self.assertEqual(r["statusCode"], code, r["body"])
        return js(r)

    def browse(self, sub=ME, **qs):
        r = L.list_listings(ev(qs=qs or None), sub)
        self.assertEqual(r["statusCode"], 200, r["body"])
        return js(r)


class Kinds(Base):
    def test_default_kind_is_sell_and_old_bodies_work(self):
        l = self.make(title="Desk lamp", price=5, condition="Good", category="dorm")
        self.assertEqual((l["kind"], l["images"], l["ticket"], l["tutoring"], l["expired"]), ("sell", [], None, None, False))

    def test_textbooks_alias_is_returned_as_books(self):
        l = self.make(title="Calc textbook", price=5, condition="Good", category="textbooks")
        self.assertEqual(l["category"], "books")
        self.assertEqual(len(self.browse(category="textbooks")["listings"]), 1)
        self.assertEqual(len(self.browse(category="books")["listings"]), 1)

    def test_bad_kind_and_category(self):
        self.bad(title="Thing here", price=5, condition="Good", category="dorm", kind="auction")
        self.bad(title="Thing here", price=5, condition="Good", category="weapons")

    def test_free(self):
        l = self.make(title="Free futon", kind="free", condition="Acceptable", category="dorm")
        self.assertEqual((l["kind"], l["price"]), ("free", 0))
        self.bad(title="Free futon", kind="free", price=5, condition="Good", category="dorm")

    def test_trade(self):
        self.bad(title="Swap my calculator", kind="trade", condition="Good", category="electronics")  # tradeFor missing
        l = self.make(title="Swap my calculator", kind="trade", tradeFor="a scientific calculator", condition="Good", category="electronics")
        self.assertEqual((l["tradeFor"], l["acceptCash"], l["price"]), ("a scientific calculator", False, 0))
        self.bad(title="Swap two", kind="trade", tradeFor="anything useful", acceptCash=True, condition="Good", category="electronics")
        l2 = self.make(title="Swap three", kind="trade", tradeFor="anything useful", acceptCash=True, price=20, condition="Good", category="electronics")
        self.assertTrue(l2["acceptCash"])
        self.bad(title="Not a trade", price=5, tradeFor="x y z", condition="Good", category="dorm")  # tradeFor on a sell

    def test_wanted_needs_no_price_or_condition_and_is_hidden_from_default_browse(self):
        w = self.make(title="Looking for Calculus book", kind="wanted", category="books")
        self.assertEqual((w["kind"], w["price"], w["condition"]), ("wanted", None, ""))
        self.make(sub=OTHER, title="Desk lamp", price=5, condition="Good", category="dorm")
        titles = [x["title"] for x in self.browse(sub=OTHER)["listings"]]
        self.assertEqual(titles, ["Desk lamp"])
        self.assertEqual([x["title"] for x in self.browse(sub=OTHER, kind="wanted")["listings"]], ["Looking for Calculus book"])
        self.assertEqual(len(self.browse(scope="mine")["listings"]), 1)
        wb = self.make(title="Wanted with budget", kind="wanted", category="books", price=30)
        self.assertEqual(wb["price"], 30)

    def test_sell_needs_condition_for_goods_only(self):
        self.bad(title="Desk lamp", price=5, category="dorm")
        l = self.make(title="Intro to Ruby tutor", kind="service", price=15, category="tutoring", tutoring=tutoring())
        self.assertEqual(l["condition"], "")

    def test_kind_cannot_change(self):
        l = self.make(title="Desk lamp", price=5, condition="Good", category="dorm")
        r = L.update_listing(ev({"kind": "free"}), ME, l["id"])
        self.assertEqual(r["statusCode"], 400)
        self.assertEqual(L.update_listing(ev({"kind": "sell", "price": 7}), ME, l["id"])["statusCode"], 200)

    def test_unknown_fields_still_rejected(self):
        self.bad(title="Desk lamp", price=5, condition="Good", category="dorm", sellerSub="x")

    def test_links_still_rejected(self):
        self.bad(title="Desk lamp", price=5, condition="Good", category="dorm", description="see http://x.example")
        self.bad(title="Swap", kind="trade", tradeFor="visit www.evil.com", condition="Good", category="dorm")


class Tickets(Base):
    def test_create_and_view(self):
        l = self.make(title="2 tickets UA vs Tennessee", kind="sell", category="tickets", price=40, ticket=ticket())
        self.assertEqual(l["ticket"]["faceValue"], 45)
        self.assertEqual((l["ticket"]["quantity"], l["ticket"]["transferMethod"], l["ticket"]["externalLink"]), (2, "official_app", ""))
        self.assertFalse(l["expired"])

    def test_price_cap_at_face_value(self):
        r = self.bad(title="Tickets", category="tickets", price=60, ticket=ticket())
        self.assertIn("face value", r["message"])
        self.make(title="Tickets at face", category="tickets", price=45, ticket=ticket())
        self.bad(title="Tickets", category="tickets", price=45.01, ticket=ticket())

    def test_cap_switch_off_allows_markup(self):
        self.db.update_item("TENANTS", "T#ua", {"ticketPriceCap": False})
        self.make(title="Tickets marked up", category="tickets", price=200, ticket=ticket())
        self.assertFalse(self.browse()["campus"]["ticketPriceCap"])

    def test_patch_cannot_dodge_the_cap(self):
        l = self.make(title="Tickets", category="tickets", price=40, ticket=ticket())
        self.assertEqual(L.update_listing(ev({"price": 50}), ME, l["id"])["statusCode"], 400)
        self.assertEqual(L.update_listing(ev({"price": 45}), ME, l["id"])["statusCode"], 200)
        self.assertEqual(L.update_listing(ev({"ticket": ticket(faceValue=10)}), ME, l["id"])["statusCode"], 400)

    def test_required_fields_and_validation(self):
        self.bad(title="Tickets", category="tickets", price=10)                                   # no ticket object
        self.bad(title="Tickets", category="tickets", price=10, ticket={**ticket(), "transferMethod": "venmo"})
        self.bad(title="Tickets", category="tickets", price=10, ticket=ticket(quantity=0))
        self.bad(title="Tickets", category="tickets", price=10, ticket=ticket(quantity=11))
        self.bad(title="Tickets", category="tickets", price=10, ticket=ticket(eventAt=when(-1)))
        self.bad(title="Tickets", category="tickets", price=10, ticket=ticket(eventAt=when(500)))
        self.bad(title="Tickets", category="tickets", price=10, ticket=ticket(eventAt="tomorrow"))
        self.bad(title="Tickets", category="tickets", price=10, ticket={**ticket(), "extra": 1})
        self.bad(title="Tickets", category="dorm", price=10, condition="Good", ticket=ticket())  # ticket on a non-ticket category

    def test_external_link_https_only(self):
        l = self.make(title="Tickets", category="tickets", price=10, ticket=ticket(externalLink="https://tickets.example.edu/t/123"))
        self.assertEqual(l["ticket"]["externalLink"], "https://tickets.example.edu/t/123")
        for bad in ("http://x.edu/a", "javascript:alert(1)", "https://u:p@x.edu/", "https://nodot/", "//x.edu/a", "https://x.edu/a b"):
            self.bad(title="Tickets", category="tickets", price=10, ticket=ticket(externalLink=bad))

    def test_past_event_is_hidden_and_owner_sees_expired(self):
        l = self.make(title="Tickets", category="tickets", price=10, ticket=ticket())
        self.assertEqual(len(self.browse(sub=OTHER)["listings"]), 1)
        self.db.update_item(f"LISTING#{l['id']}", "META", {"ticket": {**ticket(), "eventAt": when(-1)}})
        self.assertEqual(self.browse(sub=OTHER)["listings"], [])
        mine = self.browse(scope="mine")["listings"]
        self.assertTrue(mine[0]["expired"])
        # chat cannot start on it
        r = M.start_conversation(ev({"message": "still have them?"}), OTHER, l["id"])
        self.assertEqual(r["statusCode"], 404)

    def test_wanted_ticket_needs_only_event(self):
        l = self.make(title="Need tickets", kind="wanted", category="tickets", ticket={"event": "Alabama vs LSU"})
        self.assertEqual(l["ticket"]["event"], "Alabama vs LSU")

    def test_category_cannot_change_to_or_from_tickets(self):
        l = self.make(title="Tickets", category="tickets", price=10, ticket=ticket())
        self.assertEqual(L.update_listing(ev({"category": "other", "condition": "Good"}), ME, l["id"])["statusCode"], 400)

    def test_active_ticket_cap(self):
        for i in range(10):
            self.make(title=f"Tickets number {i}", category="tickets", price=10, ticket=ticket(event=f"Game {i} home"))
        self.bad(code=409, title="Tickets eleven", category="tickets", price=10, ticket=ticket())


class Tutoring(Base):
    def test_create_and_view(self):
        l = self.make(title="Calc tutor", kind="service", category="tutoring", price=15, tutoring=tutoring())
        self.assertEqual(l["kind"], "service")
        self.assertEqual(l["tutoring"]["courseCodes"], ["MATH 125"])
        self.assertEqual((l["tutoring"]["mode"], l["tutoring"]["standing"]), ("both", "junior"))

    def test_rules(self):
        self.bad(title="Calc tutor", kind="service", category="tutoring", price=15)                              # no tutoring
        self.bad(title="Calc tutor", kind="service", category="dorm", price=15, condition="Good", tutoring=tutoring())
        self.bad(title="Calc tutor", kind="sell", category="tutoring", price=15, tutoring=tutoring())
        self.bad(title="Calc tutor", kind="service", category="tutoring", price=500, tutoring=tutoring())      # rate cap
        self.bad(title="Calc tutor", kind="service", category="tutoring", price=15, tutoring=tutoring(mode="telepathy"))
        self.bad(title="Calc tutor", kind="service", category="tutoring", price=15, tutoring=tutoring(subjects=[]))
        self.bad(title="Calc tutor", kind="service", category="tutoring", price=15, tutoring=tutoring(availability="see http://x.example"))
        self.bad(title="Calc tutor", kind="service", category="tutoring", price=15, tutoring={**tutoring(), "extra": 1})
        self.make(title="Free tutor", kind="service", category="tutoring", price=0, tutoring=tutoring())

    def test_active_cap(self):
        for i in range(3):
            self.make(title=f"Tutor number {i}", kind="service", category="tutoring", price=10, tutoring=tutoring())
        self.bad(code=409, title="Tutor four", kind="service", category="tutoring", price=10, tutoring=tutoring())

    def test_tutors_for_course(self):
        self.db.put_item({"pk": f"USER#{ME}", "sk": "COURSE#course01", "id": "course01", "courseCode": "MATH 125", "title": "Calc I", "createdAt": "x"})
        self.make(sub=AUB, title="Auburn calc tutor", kind="service", category="tutoring", price=5, tutoring=tutoring())
        a = self.make(sub=OTHER, title="UA calc tutor", kind="service", category="tutoring", price=20, tutoring=tutoring())
        self.make(sub=OTHER, title="Stats tutor", kind="service", category="tutoring", price=10, tutoring=tutoring(courseCodes=["STAT 200"]))
        self.make(sub=OTHER, title="Wanted calc help", kind="wanted", category="tutoring", price=5, tutoring=tutoring())
        self.make(sub=ME, title="My own tutoring", kind="service", category="tutoring", price=5, tutoring=tutoring())
        gt = self.make(sub=GT, title="GT tutor", kind="service", category="tutoring", price=5, tutoring=tutoring())  # closed network
        r = MA.tutors_for_course(ev(), ME, "course01")
        self.assertEqual(r["statusCode"], 200, r["body"])
        d = js(r)
        self.assertEqual([t["title"] for t in d["tutors"]], ["UA calc tutor", "Auburn calc tutor"])  # campus first
        self.assertEqual(d["course"]["courseCode"], "MATH 125")
        self.assertNotIn(gt["id"], r["body"])
        self.assertEqual(a["id"], d["tutors"][0]["id"])

    def test_tutors_unknown_or_others_course_is_404(self):
        self.db.put_item({"pk": f"USER#{OTHER}", "sk": "COURSE#course99", "id": "course99", "courseCode": "MATH 125", "createdAt": "x"})
        self.assertEqual(MA.tutors_for_course(ev(), ME, "course99")["statusCode"], 404)
        self.assertEqual(MA.tutors_for_course(ev(), ME, "../x")["statusCode"], 404)

    def test_courseCode_filter_matches_tutoring_tags(self):
        self.make(title="Calc tutor", kind="service", category="tutoring", price=15, tutoring=tutoring())
        self.assertEqual(len(self.browse(sub=OTHER, courseCode="MATH125")["listings"]), 1)
        self.assertEqual(self.browse(sub=OTHER, courseCode="ENG 101")["listings"], [])


class Filters(Base):
    def setUp(self):
        super().setUp()
        self.make(title="Cheap lamp", price=5, condition="Good", category="dorm")
        self.make(title="Nice chair", price=40, condition="New", category="dorm")
        self.make(title="Swap lamp", kind="trade", tradeFor="a desk", condition="Good", category="dorm")
        self.make(title="Calc tutor", kind="service", price=15, category="tutoring", tutoring=tutoring(subjects=["Statistics"]))
        self.make(title="Free futon", kind="free", condition="Acceptable", category="dorm")

    def titles(self, **qs):
        return sorted(x["title"] for x in self.browse(sub=OTHER, **qs)["listings"])

    def test_kind(self):
        self.assertEqual(self.titles(kind="free"), ["Free futon"])
        self.assertEqual(self.titles(kind="trade"), ["Swap lamp"])
        self.assertEqual(len(self.titles()), 5)

    def test_category_price_condition(self):
        self.assertEqual(self.titles(category="tutoring"), ["Calc tutor"])
        self.assertEqual(self.titles(priceMin="10", priceMax="40"), ["Calc tutor", "Nice chair"])
        self.assertEqual(self.titles(priceMax="5", category="dorm"), ["Cheap lamp", "Free futon", "Swap lamp"])
        self.assertEqual(self.titles(condition="New"), ["Nice chair"])

    def test_text_search_covers_new_fields(self):
        self.assertEqual(self.titles(q="desk"), ["Swap lamp"])        # tradeFor
        self.assertEqual(self.titles(q="stat"), ["Calc tutor"])       # tutoring subject

    def test_bad_filters(self):
        for qs in ({"kind": "x"}, {"category": "x"}, {"priceMin": "a"}, {"priceMax": "9999"}, {"priceMin": "10", "priceMax": "5"}, {"condition": "Mint"}):
            r = L.list_listings(ev(qs=qs), OTHER)
            self.assertEqual(r["statusCode"], 400, qs)

    def test_response_lists_enabled_categories_and_kinds(self):
        d = self.browse()
        self.assertEqual(d["kinds"], list(market.KINDS))
        self.assertIn("books", d["campus"]["categories"])
        self.assertNotIn("textbooks", d["campus"]["categories"])

    def test_disabled_category_blocks_new_listings_only(self):
        self.db.update_item("TENANTS", "T#ua", {"categories": ["books", "other"]})
        self.bad(title="Lamp again", price=5, condition="Good", category="dorm")
        self.assertEqual(len(self.titles()), 5)


class WantedCapAndNoLeaks(Base):
    def test_wanted_cap(self):
        for i in range(10):
            self.make(title=f"Wanted thing {i}", kind="wanted", category="other")
        self.bad(code=409, title="Wanted eleven", kind="wanted", category="other")

    def test_no_seller_identity_in_any_v2_response(self):
        self.make(sub=OTHER, title="Calc tutor", kind="service", category="tutoring", price=5, tutoring=tutoring())
        self.make(sub=OTHER, title="Tickets", category="tickets", price=5, ticket=ticket())
        body = L.list_listings(ev(), ME)["body"]
        for secret in ("sellerSub", OTHER, "@ua.edu", "other.person"):
            self.assertNotIn(secret, body)


class ForYou(Base):
    def setUp(self):
        super().setUp()
        self.db.put_item({"pk": f"USER#{ME}", "sk": "COURSE#course01", "id": "course01", "courseCode": "MATH 125", "title": "Calc I",
                          "createdAt": "2026-10-01T00:00:00Z",
                          "books": [{"title": "Calculus: Early Transcendentals", "author": "Stewart", "edition": "8th", "isbn": "978-1-285-74155-0", "required": True},
                                    {"title": "Optional Study Guide", "required": False}]})

    def items(self):
        r = MA.for_you(ev(), ME)
        self.assertEqual(r["statusCode"], 200, r["body"])
        return js(r)["items"]

    def test_empty(self):
        self.assertEqual(self.items(), [])

    def test_class_book_match_and_optional_books_ignored(self):
        add_listing(self.db, "book0001", "ua", seller=OTHER, price=30)
        add_listing(self.db, "book0002", "ua", seller=OTHER, title="Optional Study Guide", isbn=None, price=3)
        it = self.items()
        self.assertEqual([(i["reason"], i["listing"]["id"], i["courseCode"]) for i in it], [("class_book", "book0001", "MATH 125")])

    def test_wanted_post_matches_listings_with_budget_and_category(self):
        w = self.make(title="Desk lamp", kind="wanted", category="dorm", price=10)
        add_listing(self.db, "lamp0001", "ua", seller=OTHER, title="Desk lamp", isbn=None, price=8, category="dorm")
        add_listing(self.db, "lamp0002", "ua", seller=OTHER, title="Desk lamp", isbn=None, price=25, category="dorm")        # over budget
        add_listing(self.db, "lamp0003", "ua", seller=OTHER, title="Desk lamp", isbn=None, price=5, category="electronics")  # wrong category
        add_listing(self.db, "lamp0004", "ua", seller=OTHER, title="Desk lamp", isbn=None, price=5, category="dorm", status="sold")
        add_listing(self.db, "lamp0005", "ua", seller=OTHER, title="Desk lamp", isbn=None, price=5, category="dorm", flagged=True)
        add_listing(self.db, "lamp0006", "ua", seller=OTHER, title="Desk lamp", isbn=None, price=5, category="dorm", kind="wanted")
        it = [i for i in self.items() if i["reason"] == "wanted"]
        self.assertEqual([i["listing"]["id"] for i in it], ["lamp0001"])
        self.assertEqual((it[0]["wantedId"], it[0]["wantedTitle"]), (w["id"], "Desk lamp"))

    def test_wanted_ticket_matches_by_event_and_never_own_or_expired(self):
        self.make(title="Need tickets", kind="wanted", category="tickets", ticket={"event": "Alabama vs Tennessee"})
        self.make(sub=OTHER, title="2 seats Saturday", category="tickets", price=40, ticket=ticket())
        mine = self.make(title="My own seats", category="tickets", price=40, ticket=ticket())
        old = self.make(sub=AUB, title="Old tickets", category="tickets", price=40, ticket=ticket())
        self.db.update_item(f"LISTING#{old['id']}", "META", {"ticket": {**ticket(), "eventAt": when(-2)}})
        got = {i["listing"]["title"] for i in self.items()}
        self.assertEqual(got, {"2 seats Saturday"})
        self.assertNotIn(mine["id"], json.dumps(self.items()))

    def test_network_visibility_and_campus_first(self):
        self.make(title="Desk lamp", kind="wanted", category="dorm")
        add_listing(self.db, "lamp_au1", "auburn", seller=AUB, title="Desk lamp", isbn=None, price=1, category="dorm")
        add_listing(self.db, "lamp_ua1", "ua", seller=OTHER, title="Desk lamp", isbn=None, price=9, category="dorm")
        add_listing(self.db, "lamp_gt1", "gatech", seller=GT, title="Desk lamp", isbn=None, price=1, category="dorm")
        ids = [i["listing"]["id"] for i in self.items()]
        self.assertEqual(ids, ["lamp_ua1", "lamp_au1"])

    def test_no_leaks_and_banned(self):
        self.make(title="Desk lamp", kind="wanted", category="dorm")
        add_listing(self.db, "lamp_ua1", "ua", seller=OTHER, title="Desk lamp", isbn=None, price=9, category="dorm")
        body = MA.for_you(ev(), ME)["body"]
        for secret in ("sellerSub", OTHER, "@ua.edu"):
            self.assertNotIn(secret, body)
        self.db.put_item({"pk": "BANNED_USERS", "sk": f"U#{ME}", "reason": "x"})
        self.assertEqual(MA.for_you(ev(), ME)["statusCode"], 403)


class BooksUnaffected(Base):
    def test_wanted_posts_never_match_class_books(self):
        self.db.put_item({"pk": f"USER#{ME}", "sk": "COURSE#course01", "id": "course01", "courseCode": "MATH 125", "title": "Calc I", "createdAt": "x",
                          "books": [{"title": "Calculus: Early Transcendentals", "author": "Stewart", "edition": "8th", "isbn": "978-1-285-74155-0", "required": True}]})
        add_listing(self.db, "wantbook", "ua", seller=OTHER, kind="wanted")
        d = js(B.get_matches(ev(), ME))
        self.assertEqual(d["courses"][0]["books"][0]["matches"], [])


class Sections(Base):
    def setUp(self):
        super().setUp()
        MA._term_start = lambda now=None: False
        self.addCleanup(lambda: setattr(MA, "_term_start", orig_term_start))
        self.db.put_item({"pk": f"USER#{ME}", "sk": "COURSE#course01", "id": "course01", "courseCode": "MIS 405", "title": "Systems Analysis",
                          "createdAt": "2026-10-01T00:00:00Z",
                          "books": [{"title": "Systems Analysis and Design", "author": "Dennis", "edition": "6th", "isbn": "", "required": True},
                                    {"title": "Database Concepts", "author": "Kroenke", "edition": "", "isbn": "", "required": False}]})
        self.db.put_item({"pk": f"USER#{ME}", "sk": "COURSE#course02", "id": "course02", "courseCode": "MATH 125", "title": "Calculus I",
                          "createdAt": "2026-10-02T00:00:00Z", "books": []})

    def sections(self):
        r = MA.for_you(ev(), ME)
        self.assertEqual(r["statusCode"], 200, r["body"])
        return {s["id"]: s for s in js(r)["sections"]}

    def test_empty_student_has_no_sections_and_old_keys_remain(self):
        d = js(MA.for_you(ev(), GT))
        self.assertEqual((d["items"], d["sections"]), ([], []))
        self.assertIn("campuses", d)

    def test_books_section_required_then_recommended_with_reasons(self):
        add_listing(self.db, "book_rec", "ua", seller=OTHER, title="Database Concepts 8th", author="Kroenke", isbn=None, price=10)
        add_listing(self.db, "book_req", "ua", seller=OTHER, title="Systems Analysis and Design 6th ed", author="Dennis", isbn=None, price=60)
        sec = self.sections()["books"]
        self.assertEqual([(e["listing"]["id"], e["reason"]) for e in sec["listings"]],
                         [("book_req", "Required for MIS 405"), ("book_rec", "Recommended for MIS 405")])
        self.assertEqual(sec["title"], "Books you need")

    def test_tutors_top_three_per_class(self):
        for i in range(5):
            self.make(sub=OTHER, title=f"Tutor {i} math", kind="service", category="tutoring", price=10 + i,
                      tutoring=tutoring(courseCodes=["MATH 125"])) if i < 3 else None
        self.make(sub=AUB, title="Auburn math tutor", kind="service", category="tutoring", price=1, tutoring=tutoring(courseCodes=["MATH 125"]))
        self.db.update_item(f"USER#{OTHER}", "PROFILE", {"displayName": "Other Person"})
        sec = self.sections()["tutors"]
        self.assertEqual(len(sec["listings"]), 3)
        self.assertEqual(sec["listings"][0]["reason"], "Tutor for MATH 125")
        self.assertTrue(all(e["listing"]["campus"]["id"] == "ua" for e in sec["listings"]))

    def test_classmates_same_campus_only_and_not_repeated(self):
        add_listing(self.db, "mate_own", "ua", seller=OTHER, title="MIS 405 notes bundle", isbn=None, price=5, category="other", courseCode="MIS 405")
        add_listing(self.db, "mate_aub", "auburn", seller=AUB, title="MIS notes", isbn=None, price=5, category="other", courseCode="MIS 405")
        add_listing(self.db, "mate_oth", "ua", seller=OTHER, title="Other class stuff", isbn=None, price=5, category="other", courseCode="ENG 101")
        sec = self.sections()["classmates"]
        self.assertEqual([(e["listing"]["id"], e["reason"]) for e in sec["listings"]], [("mate_own", "Tagged for MIS 405 on your campus")])

    def test_supplies_suggestions_by_class_type(self):
        add_listing(self.db, "elec_1", "ua", seller=OTHER, title="USB hub", isbn=None, price=8, category="electronics")
        add_listing(self.db, "calc_1", "ua", seller=OTHER, title="TI-84 graphing calculator", isbn=None, price=40, category="supplies")
        add_listing(self.db, "sup_x", "ua", seller=OTHER, title="Stapler", isbn=None, price=2, category="supplies")
        add_listing(self.db, "dorm_1", "ua", seller=OTHER, title="Mini fridge", isbn=None, price=50, category="dorm")
        sec = self.sections()["supplies"]
        got = {e["listing"]["id"]: e["reason"] for e in sec["listings"]}
        self.assertEqual(set(got), {"elec_1", "calc_1"})            # stapler is not a calculator; dorm only at term start
        self.assertEqual(got["calc_1"], "Suggested for MATH 125: calculators")
        self.assertTrue(sec["suggestion"] and all(e["suggestion"] for e in sec["listings"]))

    def test_dorm_basics_only_at_term_start(self):
        add_listing(self.db, "dorm_1", "ua", seller=OTHER, title="Mini fridge", isbn=None, price=50, category="dorm")
        self.assertNotIn("supplies", self.sections())
        MA._term_start = lambda now=None: True
        sec = self.sections()["supplies"]
        self.assertEqual(sec["listings"][0]["reason"], "Suggested at the start of term: dorm basics")

    def test_ticket_and_trade_highlights_own_campus_and_unexpired(self):
        self.make(sub=OTHER, title="Football seats", category="tickets", price=30, ticket=ticket())
        self.make(sub=OTHER, title="Swap my desk", kind="trade", tradeFor="a bookshelf", condition="Good", category="dorm")
        old = self.make(sub=OTHER, title="Old seats", category="tickets", price=30, ticket=ticket(event="Old game here"))
        self.db.update_item(f"LISTING#{old['id']}", "META", {"ticket": {**ticket(), "eventAt": when(-3)}})
        self.make(sub=AUB, title="Auburn seats", category="tickets", price=30, ticket=ticket(event="Auburn game"))
        sec = self.sections()["highlights"]
        self.assertEqual({e["listing"]["title"] for e in sec["listings"]}, {"Football seats", "Swap my desk"})

    def test_excludes_own_flagged_sold_and_never_leaks(self):
        add_listing(self.db, "mine_1", "ua", seller=ME, title="My notes", isbn=None, category="other", courseCode="MIS 405")
        add_listing(self.db, "flag_1", "ua", seller=OTHER, title="Flagged notes", isbn=None, category="other", courseCode="MIS 405", flagged=True)
        add_listing(self.db, "sold_1", "ua", seller=OTHER, title="Sold notes", isbn=None, category="other", courseCode="MIS 405", status="sold")
        add_listing(self.db, "ok_1", "ua", seller=OTHER, title="Good notes", isbn=None, category="other", courseCode="MIS 405")
        r = MA.for_you(ev(), ME)
        ids = [e["listing"]["id"] for s in js(r)["sections"] for e in s["listings"]]
        self.assertEqual(ids, ["ok_1"])
        for secret in ("sellerSub", OTHER, "@ua.edu", "sam1@"):
            self.assertNotIn(secret, r["body"])

    def test_section_caps(self):
        for i in range(12):
            add_listing(self.db, f"mate{i:04d}", "ua", seller=OTHER, title=f"Notes {i}", isbn=None, category="other", courseCode="MIS 405")
        self.assertEqual(len(self.sections()["classmates"]["listings"]), MA.SECTION_CAP)

    def test_candidates_called_once_even_with_wanted_post(self):
        self.make(title="Systems Analysis and Design 6e", kind="wanted", category="books")
        add_listing(self.db, "offer01", "ua", seller=OTHER, title="Systems Analysis and Design 6th", isbn=None, price=50)
        real_candidates = MA._candidates
        calls = []
        def counting(*args, **kwargs):
            calls.append(1)
            return real_candidates(*args, **kwargs)
        MA._candidates = counting
        try:
            r = MA.for_you(ev(), ME)
            self.assertEqual(r["statusCode"], 200, r["body"])
        finally:
            MA._candidates = real_candidates
        self.assertEqual(len(calls), 1, f"_candidates called {len(calls)} times, expected 1")


class PublicName(unittest.TestCase):
    def test_names(self):
        n = lambda name, email="sam1@ua.edu": market.public_name({"displayName": name, "email": email})
        self.assertEqual(n("Sam Student"), "Sam S.")
        self.assertEqual(n("  sam   van der berg "), "sam B.")
        self.assertEqual(n("Student, Sam"), "Sam S.")
        self.assertEqual(n("Sam"), "Sam")
        self.assertEqual(n("Sam Student Jr"), "Sam J.")
        for bad in ("", None, "sam1", "sam1@ua.edu", "x@y.com", "visit www.evil.com", "http://x.y", "12345"):
            self.assertEqual(n(bad), "Student", bad)
        self.assertEqual(market.public_name({}), "Student")
        self.assertEqual(market.public_name(None), "Student")
        self.assertNotIn("Student", n("Alexandria Constantinopoulos").split()[1:2] or [""])
        self.assertEqual(n("Alexandria Constantinopoulos"), "Alexandria C.")

    def test_listing_and_chat_use_it(self):
        db = mf.world([L, M])
        add = L.create_listing(ev({"title": "Desk lamp", "price": 5, "condition": "Good", "category": "dorm"}), ME)
        self.assertEqual(js(add)["listing"]["sellerName"], "Sam S.")
        db.update_item(f"USER#{ME}", "PROFILE", {"displayName": "sam1@ua.edu"})
        add2 = L.create_listing(ev({"title": "Desk lamp two", "price": 5, "condition": "Good", "category": "dorm"}), ME)
        self.assertEqual(js(add2)["listing"]["sellerName"], "Student")
        self.assertNotIn("sam1", add2["body"])


class Images(Base):
    def test_read_paths_return_clean_images(self):
        imgs = [{"url": "/demo/lamp.jpg", "alt": "A <b>lamp</b>\x00"}, "https://img.example.edu/a.png", "http://x.edu/a.png", "javascript:alert(1)",
                "//evil.com/x.png", "/demo/../etc/passwd", "/other/x.png", {"url": 5}, {"alt": "no url"}, "data:image/png;base64,AAAA",
                "https://u:p@x.edu/a.png", "/demo/a.png", "/demo/b.png", "/demo/c.png"]
        add_listing(self.db, "pic00001", "ua", seller=OTHER, title="Desk lamp", isbn=None, price=5, category="dorm", images=imgs)
        l = next(x for x in self.browse()["listings"] if x["id"] == "pic00001")
        self.assertEqual([i["url"] for i in l["images"]], ["/demo/lamp.jpg", "https://img.example.edu/a.png", "/demo/a.png", "/demo/b.png"])
        self.assertEqual(l["images"][0]["alt"], "A <b>lamp</b>")
        self.assertEqual(l["images"][1]["alt"], "")

    def test_default_is_empty_list_and_other_read_paths_use_it(self):
        add_listing(self.db, "pic00002", "ua", seller=OTHER, title="Desk lamp", isbn=None, price=5, category="dorm", images=["/demo/lamp.jpg"])
        self.make(sub=OTHER, title="Plain desk", price=5, condition="Good", category="dorm")
        self.make(title="Desk lamp", kind="wanted", category="dorm")
        d = js(MA.for_you(ev(), ME))
        got = [i["listing"]["images"] for i in d["items"]]
        self.assertEqual(got, [[{"url": "/demo/lamp.jpg", "alt": ""}]])
        self.assertEqual([x["images"] for x in self.browse()["listings"] if x["title"] == "Plain desk"], [[]])

    def test_users_cannot_set_images(self):
        self.bad(title="Desk lamp", price=5, condition="Good", category="dorm", images=["/demo/lamp.jpg"])
        l = self.make(title="Desk lamp", price=5, condition="Good", category="dorm")
        self.assertEqual(L.update_listing(ev({"images": [{"url": "https://x.edu/a.png"}]}), ME, l["id"])["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
