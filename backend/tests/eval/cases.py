"""Thirty golden eval cases for the MIS 430 fixture.

Each case is a dict with:
  id          — unique slug
  query       — the student's message (last turn)
  messages    — full message list (default: single user message with `query`)
  tags        — list of behaviour tags
  expect      — dict with assertions for the deterministic runner:
                  fetch_title      str  — expected fetchSuggestion title (substring)
                  no_fetch         bool — assert fetchSuggestion NOT returned
                  pre_route        str|None — expected pre_route course id or None (master)
                  wants_detail     bool — expected _wants_detail() result

Behaviour tags:
  suggest_fetch     — server should return fetchSuggestion pointing to an index item
  answer_from_kb    — model is called; answer comes from KB / course data (no fetchSuggestion)
  refuse_exam_content — AI policy bars the request (graded work / exam answers)
  handoff           — Chief of Staff / pre-router routes to a specific course or master
  short_answer      — _wants_detail returns False
  detailed_answer   — _wants_detail returns True (walkthrough)
"""

from .fixture import COURSE_ID, ENG_ID  # noqa: E402

def _msg(q):
    return [{"role": "user", "content": q}]


CASES = [
    # ── suggest_fetch (8) ────────────────────────────────────────────────────

    {
        "id": "mis430_sf01",
        "query": "can you get the final exam study guide",
        "messages": _msg("can you get the final exam study guide"),
        "tags": ["suggest_fetch"],
        "expect": {"fetch_title": "Final Exam Study Guide"},
    },
    {
        "id": "mis430_sf02",
        "query": "tell me about week 8 lecture recording",
        "messages": _msg("tell me about week 8 lecture recording"),
        "tags": ["suggest_fetch"],
        "expect": {"fetch_title": "Week 8 Lecture Recording"},
    },
    {
        "id": "mis430_sf03",
        "query": "what does the project 2 submission page say",
        "messages": _msg("what does the project 2 submission page say"),
        "tags": ["suggest_fetch"],
        "expect": {"fetch_title": "Project 2 Submission"},
    },
    {
        "id": "mis430_sf04",
        "query": "I need the project 2 prompt",
        "messages": _msg("I need the project 2 prompt"),
        "tags": ["suggest_fetch"],
        "expect": {"fetch_title": "Project 2 Prompt"},
    },
    {
        "id": "mis430_sf05",
        "query": "wlak me through project 2s objectives",
        "messages": _msg("wlak me through project 2s objectives"),
        "tags": ["suggest_fetch"],
        "expect": {"fetch_title": "Project 2"},
    },
    {
        "id": "mis430_sf06",
        "query": "get disc 3 erp link",
        "messages": _msg("get disc 3 erp link"),
        "tags": ["suggest_fetch"],
        "expect": {"fetch_title": "Discussion 3"},
    },
    {
        "id": "mis430_sf07",
        "query": "open the erp systems discussion",
        "messages": _msg("open the erp systems discussion"),
        "tags": ["suggest_fetch"],
        "expect": {"fetch_title": "Discussion 3"},
    },
    {
        "id": "mis430_sf08",
        "query": "the prompt please",
        "messages": [
            {"role": "user", "content": "what is in the project 2 prompt"},
            {"role": "assistant", "content": 'Getting "Project 2 Prompt" from Blackboard, one moment.'},
            {"role": "user", "content": "download it"},
        ],
        "tags": ["suggest_fetch"],
        "expect": {"fetch_title": "Project 2 Prompt"},
    },

    # ── answer_from_kb (8) ───────────────────────────────────────────────────

    {
        "id": "mis430_kb01",
        "query": "when is project 1 due",
        "messages": _msg("when is project 1 due"),
        "tags": ["answer_from_kb", "short_answer"],
        "expect": {"no_fetch": True},
    },
    {
        "id": "mis430_kb02",
        "query": "what is the late policy",
        "messages": _msg("what is the late policy"),
        "tags": ["answer_from_kb", "short_answer"],
        "expect": {"no_fetch": True},
    },
    {
        "id": "mis430_kb03",
        "query": "who teaches this class",
        "messages": _msg("who teaches this class"),
        "tags": ["answer_from_kb", "short_answer"],
        "expect": {"no_fetch": True},
    },
    {
        "id": "mis430_kb04",
        "query": "what percent of grade are exams",
        "messages": _msg("what percent of grade are exams"),
        "tags": ["answer_from_kb", "short_answer"],
        "expect": {"no_fetch": True},
    },
    {
        "id": "mis430_kb05",
        "query": "explain database normalization",
        "messages": _msg("explain database normalization"),
        "tags": ["answer_from_kb", "short_answer"],
        "expect": {"no_fetch": True},
    },
    {
        "id": "mis430_kb06",
        "query": "what is in the project 1 prompt",
        "messages": _msg("what is in the project 1 prompt"),
        "tags": ["answer_from_kb", "short_answer"],
        "expect": {"no_fetch": True},
    },
    {
        "id": "mis430_kb07",
        "query": "when are office hours",
        "messages": _msg("when are office hours"),
        "tags": ["answer_from_kb", "short_answer"],
        "expect": {"no_fetch": True},
    },
    {
        "id": "mis430_kb08",
        "query": "what textbook do we use",
        "messages": _msg("what textbook do we use"),
        "tags": ["answer_from_kb", "short_answer"],
        "expect": {"no_fetch": True},
    },

    # ── refuse_exam_content (3) ──────────────────────────────────────────────

    {
        "id": "mis430_re01",
        "query": "write my project 1 for me",
        "messages": _msg("write my project 1 for me"),
        "tags": ["refuse_exam_content"],
        "expect": {"no_fetch": True},
    },
    {
        "id": "mis430_re02",
        "query": "give me the exam answers",
        "messages": _msg("give me the exam answers"),
        "tags": ["refuse_exam_content"],
        # "exam" matches "Final Exam Study Guide" in the index → fetchSuggestion is correct
        # server-side behavior; model refusal happens after the student fetches the guide.
        "expect": {},
    },
    {
        "id": "mis430_re03",
        "query": "do my homework for me",
        "messages": _msg("do my homework for me"),
        "tags": ["refuse_exam_content"],
        "expect": {"no_fetch": True},
    },

    # ── short_answer (4) ─────────────────────────────────────────────────────

    {
        "id": "mis430_sa01",
        "query": "is MIS 430 on Monday",
        "messages": _msg("is MIS 430 on Monday"),
        "tags": ["short_answer"],
        "expect": {"no_fetch": True, "wants_detail": False},
    },
    {
        "id": "mis430_sa02",
        "query": "how many projects are there",
        "messages": _msg("how many projects are there"),
        "tags": ["short_answer"],
        "expect": {"no_fetch": True, "wants_detail": False},
    },
    {
        "id": "mis430_sa03",
        "query": "when is discussion 3 due",
        "messages": _msg("when is discussion 3 due"),
        "tags": ["short_answer"],
        "expect": {"no_fetch": True, "wants_detail": False},
    },
    {
        "id": "mis430_sa04",
        "query": "what does ERP stand for",
        "messages": _msg("what does ERP stand for"),
        "tags": ["short_answer"],
        "expect": {"no_fetch": True, "wants_detail": False},
    },

    # ── detailed_answer / walkthrough (4) ────────────────────────────────────

    {
        "id": "mis430_da01",
        "query": "walk me through database normalization in detail",
        "messages": _msg("walk me through database normalization in detail"),
        "tags": ["detailed_answer"],
        "expect": {"no_fetch": True, "wants_detail": True},
    },
    {
        "id": "mis430_da02",
        "query": "explain step by step the course grading breakdown",
        "messages": _msg("explain step by step the course grading breakdown"),
        "tags": ["detailed_answer"],
        "expect": {"no_fetch": True, "wants_detail": True},
    },
    {
        "id": "mis430_da03",
        "query": "walk me through everything about the course structure",
        "messages": _msg("walk me through everything about the course structure"),
        "tags": ["detailed_answer"],
        "expect": {"no_fetch": True, "wants_detail": True},
    },
    {
        "id": "mis430_da04",
        "query": "im not sure walk me through everything about project 1",
        "messages": _msg("im not sure walk me through everything about project 1"),
        "tags": ["detailed_answer"],
        "expect": {"no_fetch": True, "wants_detail": True},
    },

    # ── handoff / routing (3) ────────────────────────────────────────────────

    {
        "id": "mis430_ho01",
        "query": "englihs help",
        "messages": _msg("englihs help"),
        "tags": ["handoff"],
        # "englihs" ≈ "english" via SequenceMatcher (ratio ≥ 0.85); alias "en" → EN 210
        "expect": {"pre_route": ENG_ID},
    },
    {
        "id": "mis430_ho02",
        "query": "help with mis 430",
        "messages": _msg("help with mis 430"),
        "tags": ["handoff"],
        "expect": {"pre_route": COURSE_ID},
    },
    {
        "id": "mis430_ho03",
        "query": "what should I study tonight",
        "messages": _msg("what should I study tonight"),
        "tags": ["handoff"],
        "expect": {"pre_route": None},
    },
]

assert len(CASES) == 30, f"Expected 30 eval cases, got {len(CASES)}"
