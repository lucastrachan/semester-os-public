import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib import materials as mat  # noqa: E402
from lib import tools_impl  # noqa: E402

LINKS = [
    {"title": "LTI Link, Access Granted Course Materials", "url": "https://bb.example/ultra/courses/_1_1/lti", "path": "Start"},
    {"title": "Text Document, Kleopatra Lab: Part 1", "url": "https://bb.example/ultra/courses/_1_1/doc/a", "path": "Labs"},
    {"title": "Labs", "url": "https://bb.example/ultra/courses/_1_1/folder/b", "path": ""},
    {"title": "Text Document, Class Subnet Activity", "url": "https://bb.example/ultra/courses/_1_1/doc/c", "path": "Participation"},
]


def run(title, query):
    ctx = {"course_id": "abcd1234", "query": query}
    with mock.patch.object(mat, "_index_links_for_course", return_value=LINKS), \
            mock.patch.object(mat, "list_items", return_value=[]):
        res, _ = tools_impl.request_content({"courseId": "abcd1234", "title": title}, None, ctx)
    return res, ctx


class RequestContentGuard(unittest.TestCase):
    def test_generic_titles(self):
        for t in ("LTI Link, Access Granted Course Materials", "Labs", "Welcome Video", "Course Materials",
                  "Text Document, Simple Syllabus"):
            self.assertTrue(mat.is_generic_link_title(t), t)
        self.assertFalse(mat.is_generic_link_title("Text Document, Kleopatra Lab: Part 1"))

    def test_model_cannot_fetch_generic_item_for_kleopatra_question(self):
        res, ctx = run("LTI Link, Access Granted Course Materials", "walk me through the kleopatra one")
        self.assertEqual(res.get("code"), "generic_item")
        self.assertNotIn("pending_content", ctx)

    def test_model_cannot_fetch_unrelated_item(self):
        res, ctx = run("Text Document, Class Subnet Activity", "walk me through the kleopatra one")
        self.assertEqual(res.get("code"), "not_relevant")
        self.assertNotIn("pending_content", ctx)

    def test_matching_item_is_allowed(self):
        res, ctx = run("Text Document, Kleopatra Lab: Part 1", "walk me through the kleopatra lab")
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(ctx["pending_content"]["title"], "Text Document, Kleopatra Lab: Part 1")

    # ── edge cases ────────────────────────────────────────────────────────────

    def test_is_generic_none_does_not_crash(self):
        """is_generic_link_title(None) must return True or False, not raise."""
        result = mat.is_generic_link_title(None)
        self.assertIsInstance(result, bool)

    def test_is_generic_empty_string_does_not_crash(self):
        result = mat.is_generic_link_title("")
        self.assertIsInstance(result, bool)

    def test_request_content_none_title_returns_not_found(self):
        """Model sending title=null must get a not_found error, not a crash."""
        ctx = {"course_id": "abcd1234", "query": "kleopatra"}
        with mock.patch.object(mat, "_index_links_for_course", return_value=LINKS), \
                mock.patch.object(mat, "list_items", return_value=[]):
            res, _ = tools_impl.request_content({"courseId": "abcd1234", "title": None}, None, ctx)
        self.assertIn(res.get("code"), ("not_found", "no_index"))
        self.assertNotIn("pending_content", ctx)

    def test_request_content_empty_query_still_blocks_generic(self):
        """Generic items must still be rejected even when ctx has no query."""
        ctx = {"course_id": "abcd1234", "query": ""}
        with mock.patch.object(mat, "_index_links_for_course", return_value=LINKS), \
                mock.patch.object(mat, "list_items", return_value=[]):
            res, _ = tools_impl.request_content({"courseId": "abcd1234",
                                                  "title": "LTI Link, Access Granted Course Materials"},
                                                 None, ctx)
        self.assertEqual(res.get("code"), "generic_item")
        self.assertNotIn("pending_content", ctx)

    def test_request_content_empty_query_allows_specific_item(self):
        """When no student query is available, a specific (non-generic) item should be allowed."""
        ctx = {"course_id": "abcd1234", "query": ""}
        with mock.patch.object(mat, "_index_links_for_course", return_value=LINKS), \
                mock.patch.object(mat, "list_items", return_value=[]):
            res, _ = tools_impl.request_content({"courseId": "abcd1234",
                                                  "title": "Text Document, Kleopatra Lab: Part 1"},
                                                 None, ctx)
        self.assertTrue(res.get("ok"), res)

    def test_non_ascii_query_does_not_crash(self):
        """Non-ASCII characters in the query must not raise, and must not allow an unrelated item."""
        ctx = {"course_id": "abcd1234", "query": "klèopatra résumé"}
        with mock.patch.object(mat, "_index_links_for_course", return_value=LINKS), \
                mock.patch.object(mat, "list_items", return_value=[]):
            res, _ = tools_impl.request_content({"courseId": "abcd1234",
                                                  "title": "Text Document, Class Subnet Activity"},
                                                 None, ctx)
        self.assertIsInstance(res, dict)
        self.assertNotIn("pending_content", ctx)


if __name__ == "__main__":
    unittest.main()
