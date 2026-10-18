import boto3
import os
import time
from botocore.config import Config
from botocore.exceptions import ClientError, ReadTimeoutError

# Model IDs come from the environment (set in infra/stack.py); the defaults match the stack.
# Chosen from a live bake-off (see the internal planning notes, "MODEL DECISION"): the 100-requests-per-minute
# on-demand models, because the Claude profiles in this account are limited to 10 per minute.
# Claude profiles need the us./global. prefix (bare IDs are inference-profile only); these are on-demand.
MODEL_MAIN = os.environ.get("MODEL_MAIN", "zai.glm-5")
MODEL_FAST = os.environ.get("MODEL_FAST", "amazon.nova-lite-v1:0")


def _ids(env_name: str, default: str) -> list:
    return [m.strip() for m in os.environ.get(env_name, default).split(",") if m.strip()]


# Tried in order when a model is throttled, times out or is unavailable.
_FALLBACKS = {
    MODEL_MAIN: _ids("MODEL_MAIN_FALLBACKS",
                     "openai.gpt-oss-120b-1:0,mistral.mistral-large-3-675b-instruct,us.anthropic.claude-sonnet-4-6"),
    MODEL_FAST: _ids("MODEL_FAST_FALLBACKS", "zai.glm-5"),
}

_RETRYABLE_CODES = (
    "ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException", "ModelNotReadyException",
)
# API Lambda (29s): env sets BEDROCK_CHAIN_BUDGET_SECONDS=20 and BEDROCK_READ_TIMEOUT_SECONDS=8 in stack.py,
# which limits each attempt to 8s so 2 fallback attempts fit in the 20s budget.
# Worker Lambdas (120s): use higher values (60/90s budget, 100s read timeout) set per-function in stack.py.
_CHAIN_BUDGET_SECONDS = float(os.environ.get("BEDROCK_CHAIN_BUDGET_SECONDS", "18"))
_READ_TIMEOUT_SECONDS = int(os.environ.get("BEDROCK_READ_TIMEOUT_SECONDS", "25"))

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("REGION", "us-east-1"),
            # One attempt per model: the fallback chain below does the retrying, so a throttled model
            # can't burn the Lambda's time budget on backoff before the next model is tried.
            config=Config(retries={"max_attempts": 1}, read_timeout=_READ_TIMEOUT_SECONDS),
        )
    return _client


def converse(model_id: str, system: str, messages: list, tools: list = None, force_tool: str = None,
             max_tokens: int = 4096) -> dict:
    kwargs = {
        "modelId": model_id,
        "system": [{"text": system}],
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if tools:
        tool_config = {"tools": tools}
        if force_tool:
            tool_config["toolChoice"] = {"tool": {"name": force_tool}}
        kwargs["toolConfig"] = tool_config

    candidates = [model_id] + _FALLBACKS.get(model_id, [])
    last_err = None
    started = time.monotonic()
    for candidate in candidates:
        # Stop before attempting if remaining budget can't cover a full read timeout.
        # This prevents the first (or any) call from silently eating the Lambda's wall time.
        # (A worker whose read timeout is longer than its whole budget must still get its first attempt: only
        # skip when less than min(read timeout, 8 s) is left.)
        remaining = _CHAIN_BUDGET_SECONDS - (time.monotonic() - started)
        if remaining < min(_READ_TIMEOUT_SECONDS, 8):
            break
        t0 = time.monotonic()
        try:
            resp = client().converse(**{**kwargs, "modelId": candidate})
            print(f"bedrock chain: model={candidate} ms={int((time.monotonic()-t0)*1000)}")
            return resp
        except ClientError as e:
            code = e.response["Error"]["Code"]
            print(f"bedrock chain: model={candidate} ms={int((time.monotonic()-t0)*1000)} err={code}")
            if code in _RETRYABLE_CODES:
                last_err = e
                continue
            raise
        except ReadTimeoutError as e:
            print(f"bedrock chain: model={candidate} ms={int((time.monotonic()-t0)*1000)} err=ReadTimeoutError")
            last_err = e
    raise last_err or RuntimeError("bedrock: no budget remaining for any model attempt")


def extract_text(response: dict) -> str:
    for block in response.get("output", {}).get("message", {}).get("content", []):
        if "text" in block:
            return block["text"]
    return ""


def extract_tool_use(response: dict) -> tuple[str, str, dict] | None:
    """Returns (name, toolUseId, input) — toolUseId needed for toolResult blocks in Phase 4."""
    for block in response.get("output", {}).get("message", {}).get("content", []):
        if "toolUse" in block:
            t = block["toolUse"]
            return t["name"], t["toolUseId"], t["input"]
    return None
