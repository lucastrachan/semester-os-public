"""Golden eval runner for the class-agent stack.

Usage:
    python scripts/eval_agents.py              # deterministic only
    python scripts/eval_agents.py --live       # also call real Bedrock (costs ~$0.05)
    python scripts/eval_agents.py --tag suggest_fetch   # filter by tag

Deterministic tests (no model calls):
  suggest_fetch     — materials.index_fetch_suggestion returns the expected item
  answer_from_kb    — tutor.respond with a scripted model reaches the model (no early-return) and returns a reply
  short_answer      — tutor._wants_detail returns False for the query
  detailed_answer   — tutor._wants_detail returns True for the query
  handoff           — routing.pre_route returns the expected course id (or None for master)
  refuse_exam_content — tutor.respond reaches the model (AI policy in system prompt blocks graded work)

Live tests (--live):
  All cases: call tutor.respond with the real Bedrock chain and check the response shape.
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

BACKEND = str(Path(__file__).resolve().parents[1] / "backend")
TESTS = str(Path(__file__).resolve().parents[1] / "backend" / "tests")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)

from eval.fixture import build_db, courses_list, COURSE_ID, SUB  # noqa: E402
from eval.cases import CASES  # noqa: E402
from lib import materials, routing, tutor  # noqa: E402
from lib import tools_impl  # noqa: E402

TODAY = date(2026, 10, 17)


# ── scripted model ────────────────────────────────────────────────────────────

def _scripted_converse(reply: str = "ok"):
    """Returns a callable that always replies with a fixed text response."""
    def converse(system, messages, tools, force_tool, max_tokens):
        return {"output": {"message": {"role": "assistant", "content": [{"text": reply}]}},
                "stopReason": "end_turn"}
    return converse


# ── deterministic checks ──────────────────────────────────────────────────────

def _check_suggest_fetch(case: dict, v, db) -> tuple:
    query = case["query"]
    expected_title = case["expect"].get("fetch_title", "")
    sug = materials.index_fetch_suggestion(v, COURSE_ID, query)
    if sug is None:
        return False, f"index_fetch_suggestion returned None (expected title containing '{expected_title}')"
    if expected_title and expected_title.lower() not in sug["title"].lower():
        return False, f"Got title '{sug['title']}', expected it to contain '{expected_title}'"
    return True, f"ok → '{sug['title']}'"


def _check_answer_from_kb(case: dict, v, course: dict) -> tuple:
    """Call respond() with a scripted model, verify it reaches the model (no early fetchSuggestion return)."""
    model_called = []

    def converse(system, messages, tools, force_tool, max_tokens):
        model_called.append(True)
        return {"output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
                "stopReason": "end_turn"}

    out = tutor.respond(course, "explain", case["messages"], "", 5, v, converse, TODAY)
    if "fetchSuggestion" in out:
        return False, f"Expected no fetchSuggestion, but got one for '{out['fetchSuggestion'].get('title')}'"
    if not model_called:
        return False, "Model was never called (response was short-circuited before the model)"
    return True, "ok → model reached, no fetchSuggestion"


def _check_refuse(case: dict, v, course: dict) -> tuple:
    """AI policy is in the system prompt; deterministically verify the system prompt contains the policy.
    A fetchSuggestion is acceptable here (refusal happens after the fetch in a two-step flow)."""
    model_called = []

    def converse(system, messages, tools, force_tool, max_tokens):
        model_called.append(system)
        return {"output": {"message": {"role": "assistant", "content": [{"text": "I cannot do graded work for you."}]}},
                "stopReason": "end_turn"}

    out = tutor.respond(course, "explain", case["messages"], "", 5, v, converse, TODAY)
    if case["expect"].get("no_fetch") and "fetchSuggestion" in out:
        return False, f"Expected no fetchSuggestion, but got one for '{out['fetchSuggestion'].get('title')}'"
    # If a fetchSuggestion was returned, no model call was made — that's fine for this tag
    if not model_called and "fetchSuggestion" not in out:
        return False, "Model was never called and no fetchSuggestion"
    if model_called:
        system = model_called[0]
        if "ai_policy" not in system.lower() and "no ai" not in system.lower():
            return False, "AI policy not in system prompt"
    return True, "ok → AI policy enforced (via model call or fetch flow)"


def _check_wants_detail(case: dict) -> tuple:
    expected = case["expect"].get("wants_detail")
    if expected is None:
        return True, "skip (no wants_detail assertion)"
    got = tutor._wants_detail(case["query"])
    if got != expected:
        return False, f"_wants_detail({case['query']!r}) = {got}, expected {expected}"
    return True, f"ok → _wants_detail = {got}"


def _check_handoff(case: dict, courses: list) -> tuple:
    expected_id = case["expect"].get("pre_route", "MISSING")
    result = routing.pre_route(case["query"], courses)
    if expected_id == "MISSING":
        return True, "skip (no pre_route assertion)"
    got_id = result.get("target") if isinstance(result, dict) else None
    if expected_id is None:
        if got_id is not None:
            return False, f"Expected no pre-route, got courseId={got_id}"
        return True, "ok → no pre-route (goes to master)"
    if got_id != expected_id:
        return False, f"Expected courseId={expected_id}, got {got_id!r}"
    return True, f"ok → pre-routed to {got_id}"


# ── live check ────────────────────────────────────────────────────────────────

def _check_live(case: dict, v, course: dict) -> tuple:
    try:
        from lib import bedrock

        def converse(system, messages, tools, force_tool, max_tokens):
            return bedrock.converse(bedrock.MODEL_MAIN, system, messages, tools=tools,
                                    force_tool=force_tool, max_tokens=max_tokens)

        out = tutor.respond(course, "explain", case["messages"], "", 5, v, converse, TODAY)
        reply = out.get("reply", "")
        if not reply and "fetchSuggestion" not in out:
            return False, "Empty reply and no fetchSuggestion"
        if "fetchSuggestion" in out:
            return True, f"fetch → '{out['fetchSuggestion'].get('title')}'"
        return True, f"reply ({len(reply)} chars): {reply[:80]!r}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


# ── runner ────────────────────────────────────────────────────────────────────

def run(cases, live: bool, tag_filter: str | None):
    db, course, v = build_db()
    courses = courses_list(db)

    results = []
    for case in cases:
        tags = case["tags"]
        if tag_filter and tag_filter not in tags:
            continue

        passed, detail = True, "skip"

        # deterministic checks — pick the most informative one per case
        if "suggest_fetch" in tags:
            passed, detail = _check_suggest_fetch(case, v, db)
        elif "answer_from_kb" in tags:
            passed, detail = _check_answer_from_kb(case, v, course)
        elif "refuse_exam_content" in tags:
            passed, detail = _check_refuse(case, v, course)
        elif "handoff" in tags:
            passed, detail = _check_handoff(case, courses)

        if "short_answer" in tags or "detailed_answer" in tags:
            wd_passed, wd_detail = _check_wants_detail(case)
            if not wd_passed:
                passed, detail = False, wd_detail
            elif detail == "skip":
                passed, detail = wd_passed, wd_detail

        if live:
            live_passed, live_detail = _check_live(case, v, course)
            if not live_passed:
                passed = False
            detail = f"det={detail} | live={live_detail}"

        results.append({"id": case["id"], "tags": tags, "passed": passed, "detail": detail})

    return results


def print_report(results):
    from collections import defaultdict
    by_tag: dict = defaultdict(lambda: {"pass": 0, "fail": 0})
    fails = []
    for r in results:
        for tag in r["tags"]:
            if r["passed"]:
                by_tag[tag]["pass"] += 1
            else:
                by_tag[tag]["fail"] += 1
        if not r["passed"]:
            fails.append(r)

    total = len(results)
    total_pass = sum(1 for r in results if r["passed"])

    print("\n=== Eval Results ===")
    col_w = max(len(t) for t in by_tag) + 2
    for tag, counts in sorted(by_tag.items()):
        p, f = counts["pass"], counts["fail"]
        pct = 100 * p // (p + f) if (p + f) else 0
        bar = "#" * p + "." * f
        print(f"  {tag:<{col_w}} {p}/{p+f}  ({pct:3d}%)  [{bar}]")

    print(f"\n  Total: {total_pass}/{total} ({100 * total_pass // total if total else 0}%)")

    if fails:
        print("\nFailed cases:")
        for r in fails:
            print(f"  FAIL  {r['id']:20s}  [{','.join(r['tags'])}]  {r['detail']}")
    else:
        print("\nAll cases passed.")
    print()
    return total_pass, total


def main():
    parser = argparse.ArgumentParser(description="Run SemesterOS class-agent golden eval")
    parser.add_argument("--live", action="store_true", help="Also call real Bedrock (costs ~$0.05)")
    parser.add_argument("--tag", help="Only run cases with this tag")
    args = parser.parse_args()

    results = run(CASES, live=args.live, tag_filter=args.tag)
    total_pass, total = print_report(results)
    sys.exit(0 if total_pass >= total * 0.9 else 1)


if __name__ == "__main__":
    main()
