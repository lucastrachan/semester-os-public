"""Tests for bedrock.py fallback chain and budget logic."""
import importlib
import sys
import time
import unittest
from botocore.exceptions import ClientError, ReadTimeoutError


def _throttle_error():
    return ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "Converse",
    )


def _timeout_error():
    return ReadTimeoutError(endpoint_url="https://bedrock.amazonaws.com")


def _make_response(text="ok"):
    return {
        "output": {"message": {"content": [{"text": text}]}},
        "stopReason": "end_turn",
    }


class FakeClient:
    """Records calls and raises errors from a script of (error_or_None, delay_s) pairs."""

    def __init__(self, script):
        # script: list of (exception|None, sleep_seconds)
        self._script = list(script)
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs.get("modelId"))
        if not self._script:
            return _make_response()
        exc, sleep = self._script.pop(0)
        if sleep:
            time.sleep(sleep)
        if exc:
            raise exc
        return _make_response()


class BedrockChainTests(unittest.TestCase):
    def setUp(self):
        # Force fresh module import so module-level globals reset between tests.
        for mod_name in list(sys.modules):
            if "bedrock" in mod_name and "test" not in mod_name:
                del sys.modules[mod_name]

    def _load(self, env_overrides=None):
        import os
        env_overrides = env_overrides or {}
        defaults = {
            "BEDROCK_CHAIN_BUDGET_SECONDS": "20",
            "BEDROCK_READ_TIMEOUT_SECONDS": "8",
            "MODEL_MAIN": "model-main",
            "MODEL_FAST": "model-fast",
            "MODEL_MAIN_FALLBACKS": "model-fb1,model-fb2",
            "MODEL_FAST_FALLBACKS": "model-fast-fb1",
        }
        for k, v in {**defaults, **env_overrides}.items():
            os.environ[k] = v
        import lib.bedrock as bedrock
        return bedrock

    def _patch_client(self, bedrock, fake_client):
        bedrock._client = fake_client

    def test_success_on_first_attempt(self):
        b = self._load()
        fc = FakeClient([(None, 0)])
        self._patch_client(b, fc)
        resp = b.converse("model-main", "sys", [{"role": "user", "content": [{"text": "hi"}]}])
        self.assertEqual(b.extract_text(resp), "ok")
        self.assertEqual(fc.calls, ["model-main"])

    def test_fallback_on_throttle(self):
        b = self._load()
        fc = FakeClient([(_throttle_error(), 0), (None, 0)])
        self._patch_client(b, fc)
        resp = b.converse("model-main", "sys", [{"role": "user", "content": [{"text": "hi"}]}])
        self.assertEqual(b.extract_text(resp), "ok")
        self.assertEqual(fc.calls, ["model-main", "model-fb1"])

    def test_fallback_on_timeout(self):
        b = self._load()
        fc = FakeClient([(_timeout_error(), 0), (None, 0)])
        self._patch_client(b, fc)
        resp = b.converse("model-main", "sys", [{"role": "user", "content": [{"text": "hi"}]}])
        self.assertEqual(fc.calls, ["model-main", "model-fb1"])

    def test_all_fallbacks_fail_raises(self):
        b = self._load()
        fc = FakeClient([
            (_throttle_error(), 0),
            (_throttle_error(), 0),
            (_throttle_error(), 0),
        ])
        self._patch_client(b, fc)
        with self.assertRaises(ClientError):
            b.converse("model-main", "sys", [{"role": "user", "content": [{"text": "hi"}]}])

    def test_budget_check_skips_attempt_when_insufficient(self):
        """With a 1s budget and 8s read timeout, even the first attempt is skipped."""
        b = self._load({"BEDROCK_CHAIN_BUDGET_SECONDS": "1", "BEDROCK_READ_TIMEOUT_SECONDS": "8"})
        fc = FakeClient([])
        self._patch_client(b, fc)
        with self.assertRaises(RuntimeError, msg="bedrock: no budget remaining"):
            b.converse("model-main", "sys", [{"role": "user", "content": [{"text": "hi"}]}])
        self.assertEqual(fc.calls, [])  # no model was even tried

    def test_worker_config_read_timeout_longer_than_budget_still_attempts(self):
        """Worker Lambdas run with budget 60 s and read timeout 100 s: the first attempt must still happen
        (regression: a check of remaining < read_timeout skipped every attempt, so syllabus and material
        processing always failed)."""
        b = self._load({"BEDROCK_CHAIN_BUDGET_SECONDS": "60", "BEDROCK_READ_TIMEOUT_SECONDS": "100"})
        fc = FakeClient([(None, 0)])
        self._patch_client(b, fc)
        resp = b.converse("model-main", "sys", [{"role": "user", "content": [{"text": "hi"}]}])
        self.assertEqual(b.extract_text(resp), "ok")
        self.assertEqual(fc.calls, ["model-main"])

    def test_budget_check_skips_second_attempt_when_tight(self):
        """First attempt consumes most of budget; second is skipped rather than timing out."""
        b = self._load({"BEDROCK_CHAIN_BUDGET_SECONDS": "10", "BEDROCK_READ_TIMEOUT_SECONDS": "8"})
        # First call takes 3s then throttles — 10 - 3 = 7s left, which is < 8s, so no second attempt.
        fc = FakeClient([(_throttle_error(), 3)])
        self._patch_client(b, fc)
        with self.assertRaises(ClientError):
            b.converse("model-main", "sys", [{"role": "user", "content": [{"text": "hi"}]}])
        self.assertEqual(len(fc.calls), 1)

    def test_non_retryable_error_raises_immediately(self):
        b = self._load()
        non_retryable = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "bad input"}}, "Converse"
        )
        fc = FakeClient([(non_retryable, 0), (None, 0)])
        self._patch_client(b, fc)
        with self.assertRaises(ClientError) as ctx:
            b.converse("model-main", "sys", [{"role": "user", "content": [{"text": "hi"}]}])
        self.assertEqual(ctx.exception.response["Error"]["Code"], "ValidationException")
        self.assertEqual(len(fc.calls), 1)  # no fallback attempted

    def test_fast_model_fallback_chain(self):
        b = self._load()
        fc = FakeClient([(_throttle_error(), 0), (None, 0)])
        self._patch_client(b, fc)
        resp = b.converse("model-fast", "sys", [{"role": "user", "content": [{"text": "hi"}]}])
        self.assertEqual(fc.calls, ["model-fast", "model-fast-fb1"])

    def test_unknown_model_has_no_fallback(self):
        b = self._load()
        fc = FakeClient([(_throttle_error(), 0)])
        self._patch_client(b, fc)
        with self.assertRaises(ClientError):
            b.converse("unknown-model", "sys", [{"role": "user", "content": [{"text": "hi"}]}])
        self.assertEqual(fc.calls, ["unknown-model"])  # only one attempt, no fallbacks

    def test_tools_passed_through(self):
        b = self._load()
        received_kwargs = {}

        class CapturingClient(FakeClient):
            def converse(self, **kwargs):
                received_kwargs.update(kwargs)
                return super().converse(**kwargs)

        fc = CapturingClient([(None, 0)])
        self._patch_client(b, fc)
        tools = [{"toolSpec": {"name": "mytool", "description": "test", "inputSchema": {"json": {}}}}]
        b.converse("model-main", "sys", [{"role": "user", "content": [{"text": "hi"}]}], tools=tools)
        self.assertIn("toolConfig", received_kwargs)

    def tearDown(self):
        import os
        for k in ("BEDROCK_CHAIN_BUDGET_SECONDS", "BEDROCK_READ_TIMEOUT_SECONDS",
                  "MODEL_MAIN", "MODEL_FAST", "MODEL_MAIN_FALLBACKS", "MODEL_FAST_FALLBACKS"):
            os.environ.pop(k, None)
        for mod_name in list(sys.modules):
            if "bedrock" in mod_name and "test" not in mod_name:
                del sys.modules[mod_name]


if __name__ == "__main__":
    unittest.main()
