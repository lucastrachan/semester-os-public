import unittest

from _fakes import FakeDb  # noqa: F401  (sets sys.path)
from lib import matching as m


class Isbn(unittest.TestCase):
    def test_normalise_and_validate(self):
        self.assertEqual(m.normalize_isbn("978-1-285-74155-0"), "9781285741550")
        self.assertEqual(m.to_isbn13("978-1-285-74155-0"), "9781285741550")
        self.assertEqual(m.to_isbn13("9780134492513"), "9780134492513")
        self.assertEqual(m.to_isbn13("9780262046305"), "9780262046305")

    def test_isbn10_converts_to_13(self):
        self.assertEqual(m.to_isbn13("0-306-40615-2"), "9780306406157")
        self.assertEqual(m.to_isbn13("080442957X"), "9780804429573")

    def test_bad_checksums_and_shapes_rejected(self):
        for bad in ("9781285741551", "0306406153", "12345", "", None, "abcdefghij", "9791285741550X", "1" * 13):
            self.assertIsNone(m.to_isbn13(bad), bad)


class Titles(unittest.TestCase):
    def test_tokens_ignore_edition_punctuation_stopwords(self):
        self.assertEqual(m.title_tokens("Calculus: Early Transcendentals 8th ed"), ["calculus", "early", "transcendentals"])
        self.assertEqual(m.title_tokens("Principles of Marketing, 17e"), ["principles", "marketing"])
        self.assertEqual(m.title_tokens("Introduction to Algorithms (CLRS) Edition 4")[:2], ["introduction", "algorithms"])

    def test_edition_detection(self):
        self.assertEqual(m.edition_of("8th"), 8)
        self.assertEqual(m.edition_of("", "Principles of Marketing 17th ed"), 17)
        self.assertEqual(m.edition_of("Edition 4"), 4)
        self.assertEqual(m.edition_of("17e"), 17)
        self.assertIsNone(m.edition_of("Calculus"))

    def test_accents_ampersand_case(self):
        self.assertEqual(m.author_tokens("Kotler & Armstrong"), {"kotler", "armstrong"})
        self.assertEqual(m.author_tokens("Cormen et al"), {"cormen"})
        self.assertEqual(m.author_tokens("J. R. R. Tolkien"), {"tolkien"})
        self.assertEqual(m.title_tokens("Résumé Écrit"), ["resume", "ecrit"])


SEED = [
    {"title": "Calculus: Early Transcendentals 8th ed", "author": "James Stewart"},
    {"title": "Principles of Marketing 17th ed", "author": "Kotler & Armstrong"},
    {"title": "Introduction to Algorithms (CLRS) 4th ed", "author": "Cormen et al"},
]


class Score(unittest.TestCase):
    def test_seeded_listings_match_the_books_a_syllabus_names(self):
        books = [
            {"title": "Calculus: Early Transcendentals", "author": "Stewart", "edition": "8th"},
            {"title": "Principles of Marketing", "author": "Philip Kotler, Gary Armstrong", "edition": "17th"},
            {"title": "Introduction to Algorithms", "author": "Cormen, Leiserson, Rivest, Stein", "edition": "4"},
        ]
        for b, l in zip(books, SEED):
            self.assertIsNotNone(m.is_title_match(b, l), b["title"])

    def test_no_author_still_matches_on_title(self):
        self.assertIsNotNone(m.is_title_match({"title": "Principles of Marketing"}, SEED[1]))

    def test_different_edition_is_not_the_book(self):
        r = m.score({"title": "Calculus: Early Transcendentals", "edition": "9th"}, SEED[0])
        self.assertTrue(r["editionMismatch"])
        self.assertIsNone(m.is_title_match({"title": "Calculus: Early Transcendentals", "edition": "9th"}, SEED[0]))

    def test_unknown_edition_on_either_side_is_fine(self):
        self.assertIsNotNone(m.is_title_match({"title": "Calculus: Early Transcendentals"}, SEED[0]))

    def test_short_title_does_not_match_longer_one(self):
        self.assertIsNone(m.is_title_match({"title": "Calculus"}, SEED[0]))
        self.assertIsNone(m.is_title_match({"title": "Calculus", "author": "Stewart"}, SEED[0]))

    def test_volumes_and_numbers_matter(self):
        self.assertIsNone(m.is_title_match({"title": "Calculus 1"}, {"title": "Calculus 2"}))
        self.assertIsNotNone(m.is_title_match({"title": "Calculus 2"}, {"title": "CALCULUS, 2!"}))

    def test_same_title_different_author_is_penalised(self):
        s_same = m.score({"title": "Statistics", "author": "Moore"}, {"title": "Statistics", "author": "Moore"})["score"]
        s_diff = m.score({"title": "Statistics", "author": "Moore"}, {"title": "Statistics", "author": "Triola"})["score"]
        self.assertGreater(s_same, s_diff)
        self.assertLess(s_diff, m.TITLE_MATCH_THRESHOLD)

    def test_unrelated_and_empty(self):
        self.assertEqual(m.score({"title": "Organic Chemistry"}, SEED[0])["score"], 0.0)
        self.assertEqual(m.score({}, {}), {"score": 0.0, "editionMismatch": False})
        self.assertIsNone(m.is_title_match({"title": ""}, {"title": ""}))

    def test_score_range(self):
        for b in SEED:
            for l in SEED:
                s = m.score(b, l)["score"]
                self.assertTrue(0 <= s <= 1)


class Search(unittest.TestCase):
    L = {"title": "Calculus: Early Transcendentals 8th ed", "author": "James Stewart", "courseCode": "MATH 125", "category": "textbooks"}

    def test_prefix_words_all_required(self):
        self.assertTrue(m.search_match("calc", self.L))
        self.assertTrue(m.search_match("calc stew", self.L))
        self.assertFalse(m.search_match("calc physics", self.L))
        self.assertFalse(m.search_match("alculus", self.L))     # prefix, not substring
        self.assertTrue(m.search_match("", self.L))
        self.assertTrue(m.search_match("  !! ", self.L))

    def test_matches_category_and_code(self):
        self.assertTrue(m.search_match("textbooks", self.L))
        self.assertTrue(m.search_match("math 125", self.L))


class CourseCodes(unittest.TestCase):
    def test_forms(self):
        for raw in ("mis405", "MIS-405", "mis 405", " MIS   405 ", "MIS_405"):
            self.assertEqual(m.normalize_course_code(raw), "MIS 405", raw)
        self.assertEqual(m.normalize_course_code("CS 101L"), "CS 101L")
        self.assertEqual(m.normalize_course_code("<b>x</b>"), "BXB")  # junk is reduced, never passed through
        self.assertEqual(m.normalize_course_code(None), "")
        self.assertLessEqual(len(m.normalize_course_code("x" * 100)), 16)


if __name__ == "__main__":
    unittest.main()
