"""CI-style check: every Lambda in infra/stack.py that sets Bedrock env vars must satisfy
BEDROCK_CHAIN_BUDGET_SECONDS >= min(BEDROCK_READ_TIMEOUT_SECONDS, 8).

This guards against a class of bug where a worker Lambda's budget < read_timeout causes
the pre-attempt check in bedrock.py (`remaining < min(read_timeout, 8)`) to skip every
Bedrock call silently (e.g. budget=60, read_timeout=100: old code checked 60 < 100 = True
and skipped all syllabus processing and material summarisation).
"""
import os
import re
import unittest

_STACK_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "infra", "stack.py")
)


def _environment_blocks(text: str) -> list:
    """Extract the text of each environment={...} block in the CDK stack file."""
    blocks = []
    for m in re.finditer(r"environment\s*=\s*\{", text):
        start = m.end()
        depth, i = 1, start
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        blocks.append(text[start : i - 1])
    return blocks


class TestStackBedrockEnvConfig(unittest.TestCase):
    """Read infra/stack.py and verify Bedrock env invariants for every Lambda."""

    def setUp(self):
        with open(_STACK_PATH) as f:
            self._stack = f.read()

    def test_every_lambda_budget_exceeds_min_read_timeout(self):
        """BEDROCK_CHAIN_BUDGET_SECONDS >= min(BEDROCK_READ_TIMEOUT_SECONDS, 8) for every Lambda.

        Ensures every Lambda has enough budget for at least one Bedrock attempt window.
        Regression: worker Lambdas (budget=60, read_timeout=100) previously failed this
        check (old code: remaining < read_timeout) and silently skipped all model calls.
        """
        violations = []
        for block in _environment_blocks(self._stack):
            budget_m = re.search(r'"BEDROCK_CHAIN_BUDGET_SECONDS"\s*:\s*"(\d+)"', block)
            timeout_m = re.search(r'"BEDROCK_READ_TIMEOUT_SECONDS"\s*:\s*"(\d+)"', block)
            if not budget_m or not timeout_m:
                continue
            budget = int(budget_m.group(1))
            read_timeout = int(timeout_m.group(1))
            required = min(read_timeout, 8)
            if budget < required:
                violations.append(
                    f"BEDROCK_CHAIN_BUDGET_SECONDS={budget} < min(READ_TIMEOUT={read_timeout}, 8)={required}"
                )
        self.assertEqual(
            violations, [],
            "Lambda env violates Bedrock budget invariant:\n" + "\n".join(violations),
        )

    def test_every_lambda_with_read_timeout_also_sets_budget(self):
        """Any Lambda that overrides BEDROCK_READ_TIMEOUT_SECONDS must also set BEDROCK_CHAIN_BUDGET_SECONDS.

        A custom read timeout without an explicit budget falls back to the code default (18s),
        which may be too short for worker Lambdas and hides a misconfiguration.
        """
        missing = []
        for block in _environment_blocks(self._stack):
            has_timeout = bool(re.search(r'"BEDROCK_READ_TIMEOUT_SECONDS"', block))
            has_budget = bool(re.search(r'"BEDROCK_CHAIN_BUDGET_SECONDS"', block))
            if has_timeout and not has_budget:
                # Extract Lambda id for a helpful message
                snippet = block[:120].replace("\n", " ")
                missing.append(f"Lambda env sets READ_TIMEOUT but not BUDGET: {snippet!r}")
        self.assertEqual(missing, [], "\n".join(missing))
