import json
import unittest

import _market_fakes as mf
from _market_fakes import ME, OTHER, AUB, GT, add_listing
import books_api as B
import listings_api as L


def ev():
    return {"requestContext": {"http": {"sourceIp": "203.0.113.5"}}}


def js(r):
    return json.loads(r["body"])


CALC = {"title": "Calculus: Early Transcendentals", "author": "Stewart", "edition": "8th", "isbn": "978-1-285-74155-0", "required": True}
MKT = {"title": "Principles of Marketing", "author": "Kotler, Armstrong", "edition": "17th", "isbn": "", "required": True}
OPT = {"title": "Study Guide", "author": "", "edition": "", "isbn": "", "required": False}


class Base(unittest.TestCase):
    def setUp(self):
        self.db = mf.world([L, B])
        self.db.put_item({"pk": f"USER#{ME}", "sk": "COURSE#course01", "id": "course01", "courseCode": "MATH 125", "title": "Calc I",
                          "color": "#0D9488", "createdAt": "2026-10-01T00:00:00Z", "books": [OPT, CALC, MKT]})
        self.db.put_item({"pk": f"USER#{ME}", "sk": "COURSE#course02", "id": "course02", "courseCode": "NEW 100",
                          "createdAt": "2026-10-02T00:00:00Z", "books": []})

    def matches(self, sub=ME):
        r = B.get_matches(ev(), sub)
        self.assertEqual(r["statusCode"], 200, r["body"])
        return js(r)

    def book(self, data, course=0, title="Calculus: Early Transcendentals"):
        return next(b for b in data["courses"][course]["books"] if b["title"] == title)

    def ids(self, book):
        return [(m["matchType"], m["listing"]["id"]) for m in book["matches"]]


class Order(Base):
    def test_isbn_first_then_title_on_campus_then_title_on_network(self):
        add_listing(self.db, "isbn_net", "auburn", price=10, created="2026-10-02T00:00:00Z")                            # isbn, other campus (cheap)
        add_listing(self.db, "isbn_own", "ua", price=50, created="2026-10-03T00:00:00Z")                                # isbn, own campus
        add_listing(self.db, "title_own", "ua", isbn=None, price=20, title="Calculus Early Transcendentals 8th ed", created="2026-10-04T00:00:00Z")
        add_listing(self.db, "title_net", "auburn", isbn=None, price=5, title="Calculus: Early Transcendentals (8th ed)", created="2026-10-05T00:00:00Z")
        b = self.book(self.matches())
        self.assertEqual(self.ids(b), [("isbn", "isbn_own"), ("isbn", "isbn_net"), ("title", "title_own"), ("title", "title_net")])
        self.assertEqual(b["bestPrice"], 5)
        self.assertEqual(b["bestOnYourCampus"], 20)

    def test_cheaper_first_within_a_group(self):
        add_listing(self.db, "own_b", "ua", price=40, created="2026-10-01T00:00:00Z")
        add_listing(self.db, "own_a", "ua", price=25, created="2026-10-02T00:00:00Z")
        self.assertEqual([i for _, i in self.ids(self.book(self.matches()))], ["own_a", "own_b"])

    def test_seeded_demo_listings_match_and_carry_the_demo_tag(self):
        add_listing(self.db, "demo0001", "ua", demo=True)
        add_listing(self.db, "demo0002", "ua", title="Principles of Marketing 17th ed", author="Kotler & Armstrong",
                    isbn="9780134492513", price=45, condition="Like new", demo=True)
        add_listing(self.db, "demo0003", "auburn", price=30, condition="Acceptable", demo=True)
        data = self.matches()
        calc, mkt = self.book(data), self.book(data, title="Principles of Marketing")
        self.assertEqual(self.ids(calc), [("isbn", "demo0001"), ("isbn", "demo0003")])
        self.assertEqual(self.ids(mkt), [("title", "demo0002")])               # syllabus had no ISBN: matched by title
        m0 = calc["matches"][0]
        self.assertEqual((m0["score"], m0["listing"]["demo"], m0["listing"]["onYourCampus"], m0["listing"]["price"],
                          m0["listing"]["condition"]), (1.0, True, True, 35, "Good"))
        self.assertFalse(calc["matches"][1]["listing"]["onYourCampus"])
        self.assertEqual(calc["matches"][1]["listing"]["campus"]["name"], "Auburn University")
        self.assertEqual(data["campuses"]["auburn"]["pickupSpots"], ["Haley Center"])
        self.assertEqual(data["pickupSpots"], ["Student Center", "Gorgas Library"])

    def test_isbn10_on_the_syllabus_matches_a_13_digit_listing(self):
        add_listing(self.db, "tenten", "ua", isbn="9780306406157", title="Some Other Title", author="X")
        self.db.update_item(f"USER#{ME}", "COURSE#course01", {"books": [{"title": "Whatever", "isbn": "0-306-40615-2", "required": True}]})
        data = self.matches()
        self.assertEqual(self.ids(data["courses"][0]["books"][0]), [("isbn", "tenten")])


class Exclusions(Base):
    def test_never_matches_own_hidden_or_unavailable_listings(self):
        add_listing(self.db, "mine0001", "ua", seller=ME)
        add_listing(self.db, "sold0001", "ua", status="sold", seller=OTHER)
        add_listing(self.db, "gone0001", "ua", status="removed", seller=OTHER)
        add_listing(self.db, "flag0001", "ua", flagged=True, seller=OTHER)
        add_listing(self.db, "good0001", "ua", seller=OTHER)
        self.assertEqual(self.ids(self.book(self.matches())), [("isbn", "good0001")])

    def test_closed_disabled_and_blocked_campuses_are_not_matched(self):
        add_listing(self.db, "gt000001", "gatech")
        add_listing(self.db, "off00001", "offline")
        add_listing(self.db, "spam0001", "spam")
        add_listing(self.db, "t_gt", "gatech", isbn=None, title="Calculus: Early Transcendentals 8th ed")
        self.assertEqual(self.book(self.matches())["matches"], [])

    def test_closed_campus_students_still_find_open_campus_listings_and_their_own(self):
        self.db.put_item({"pk": f"USER#{GT}", "sk": "COURSE#gtcourse", "id": "gtcourse", "courseCode": "MATH 1", "createdAt": "x", "books": [CALC]})
        add_listing(self.db, "gt000001", "gatech", price=20)
        add_listing(self.db, "ua000001", "ua", price=30)
        b = self.book(self.matches(sub=GT), title=CALC["title"])
        self.assertEqual({i for _, i in self.ids(b)}, {"gt000001", "ua000001"})
        self.assertEqual(b["bestOnYourCampus"], 20)
        self.assertEqual(self.ids(self.book(self.matches(), title=CALC["title"])), [("isbn", "ua000001")])   # UA student cannot see GT

    def test_wrong_edition_or_unrelated_titles_do_not_match(self):
        add_listing(self.db, "ed9", "ua", isbn=None, title="Calculus: Early Transcendentals 9th ed", author="James Stewart")
        add_listing(self.db, "short", "ua", isbn=None, title="Calculus", author="James Stewart")
        add_listing(self.db, "lamp", "ua", isbn=None, title="Desk lamp", author=None, category="dorm")
        self.assertEqual(self.book(self.matches())["matches"], [])

    def test_a_listing_is_never_listed_twice_for_a_book(self):
        add_listing(self.db, "dup00001", "ua")        # matches by ISBN and by title
        self.assertEqual(self.ids(self.book(self.matches())), [("isbn", "dup00001")])

    def test_disabled_own_campus_is_403_and_no_profile_404(self):
        self.db.update_item("TENANTS", "T#ua", {"disabled": True})
        self.assertEqual(B.get_matches(ev(), ME)["statusCode"], 403)
        self.assertEqual(B.get_matches(ev(), "user-zzzz-9999")["statusCode"], 404)
        self.assertEqual(B.get_matches(ev(), "x")["statusCode"], 401)


class Shape(Base):
    def test_required_first_courses_without_books_and_cap(self):
        data = self.matches()
        self.assertEqual([b["title"] for b in data["courses"][0]["books"]], [CALC["title"], MKT["title"], OPT["title"]])
        self.assertEqual([b["required"] for b in data["courses"][0]["books"]], [True, True, False])
        self.assertEqual(data["courses"][1]["books"], [])
        self.assertEqual((data["courses"][0]["courseCode"], data["courses"][0]["color"]), ("MATH 125", "#0D9488"))
        for i in range(8):
            add_listing(self.db, f"many000{i}", "ua", price=10 + i, created=f"2026-10-0{i + 1}T00:00:00Z")
        b = self.book(self.matches())
        self.assertEqual(len(b["matches"]), B.MAX_MATCHES_PER_BOOK)
        self.assertEqual(b["bestPrice"], 10)

    def test_no_identity_leaks(self):
        add_listing(self.db, "leak0001", "ua", seller=OTHER, sellerName="Student")
        body = B.get_matches(ev(), ME)["body"]
        for secret in ("sellerSub", OTHER, "@ua.edu", "gsi2pk", "domains"):
            self.assertNotIn(secret, body)

    def test_other_users_courses_are_not_read(self):
        self.db.put_item({"pk": f"USER#{AUB}", "sk": "COURSE#augcourse", "id": "augcourse", "courseCode": "AUB 1", "createdAt": "x", "books": [MKT]})
        self.assertEqual([c["courseId"] for c in self.matches()["courses"]], ["course01", "course02"])

    def test_listing_text_is_cleaned_on_the_way_out(self):
        add_listing(self.db, "dirty001", "ua", title="Calculus: Early Transcendentals 8th ed‮​", description="x​y")
        m = self.book(self.matches())["matches"][0]["listing"]
        self.assertNotIn("‮", m["title"])
        self.assertEqual(m["description"], "xy")


if __name__ == "__main__":
    unittest.main()
