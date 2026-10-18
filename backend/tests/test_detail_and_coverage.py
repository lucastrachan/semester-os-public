import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib import limits, tutor  # noqa: E402


class DetailIntent(unittest.TestCase):
    def test_walkthrough_phrases(self):
        for q in ["im not sure walk me throughe verythign", "wlak me through project 2s objectives",
                  "can you explain project 1", "give me everything about the lab"]:
            self.assertTrue(tutor._wants_detail(q), q)

    def test_plain_questions_stay_short(self):
        for q in ["whats due", "who is the instructor", "when is the exam"]:
            self.assertFalse(tutor._wants_detail(q), q)

    def test_detail_keeps_numbered_steps_and_longer_cap(self):
        reply = "Project 2 has five objectives:\n1. a\n2. b\n3. c\nDone."
        self.assertEqual(tutor._sanitize_reply(reply, detailed=True), reply)
        self.assertNotIn("1. a", tutor._sanitize_reply(reply, detailed=False))

    def test_detail_token_cap(self):
        self.assertEqual(limits.max_output_tokens("chat_detail"), 900)
        self.assertEqual(limits.max_output_tokens("chat_moderate"), 700)
        self.assertEqual(limits.max_output_tokens("chat"), 500)


class QuestionCoversMaterial(unittest.TestCase):
    def test_typo_and_number_suffix(self):
        self.assertTrue(tutor._question_covers("wlak me through project 2s objectives",
                                               ["Project 2 Objectives", "Project 1 Prompt (2).docx"]))

    def test_wrong_number_does_not_cover(self):
        self.assertFalse(tutor._question_covers("tell me about project 1", ["Project 2 Objectives"]))

    def test_single_shared_word_never_covers(self):
        self.assertFalse(tutor._question_covers("tell me about the project", ["Secure Mobile Van Project"]))


if __name__ == "__main__":
    unittest.main()
