"""Scheduled Blackboard feed poller (Phase 6). Contract and infra notes: FEED_API.md.

An EventBridge schedule (rate(15 minutes), reserved concurrency 1) invokes handler(). Each run takes a capped batch of due
students from the FEEDUSER#{shard} index items (16 Query calls, no table scan) and runs feedsync.sync_user for each, one
try/except per student so a single bad feed never stops the batch. Logs hold counts only: never URLs, event text or subs.
"""
import time

from lib import feedsync, redact

redact.install()

DEFAULT_LIMIT = 25
BUDGET_SECONDS = 100          # stop starting new students after this (Lambda timeout is 120 s)
SUCCESS_INTERVAL = 3600
MAX_BACKOFF = 24 * 3600


def _due(backend, now: float) -> list:
    rows = []
    for shard in range(feedsync.SHARDS):
        for it in backend.query_pk(f"FEEDUSER#{shard}", "U#"):
            if int(it.get("nextSyncAt") or 0) <= now and isinstance(it.get("sub"), str):
                rows.append(it)
    rows.sort(key=lambda r: int(r.get("nextSyncAt") or 0))
    return rows


def _backoff(failures: int) -> int:
    return min(MAX_BACKOFF, 900 * 2 ** min(failures, 8))


def process_batch(limit: int = DEFAULT_LIMIT, deps: dict | None = None, now: float | None = None) -> dict:
    d = dict(deps or {})
    if d.get("backend") is None:
        from lib import db
        d["backend"] = db
    backend = d["backend"]
    t0 = time.time()
    t = now if now is not None else t0
    out = {"due": 0, "processed": 0, "ok": 0, "failed": 0, "skipped": 0}
    due = _due(backend, t)
    out["due"] = len(due)
    for row in due[:max(0, int(limit))]:
        if now is None and time.time() - t0 > BUDGET_SECONDS:
            out["skipped"] += 1
            continue
        sub = row["sub"]
        failures = int(row.get("failures") or 0)
        try:
            feedsync.sync_user(sub, d, now=now)
            jitter = feedsync.shard_of(sub) * 20   # spreads students inside the hour, deterministic
            feedsync.index_put(backend, sub, t + SUCCESS_INTERVAL + jitter, 0)
            out["ok"] += 1
        except feedsync.NotConnected:
            feedsync.index_delete(backend, sub)    # feed was removed: drop the stale index item
        except feedsync.FeedError:
            feedsync.index_put(backend, sub, t + _backoff(failures), failures + 1)
            out["failed"] += 1
        except Exception as e:  # noqa: BLE001
            print(f"sync_blackboard student failed: {feedsync.safe_trace(e)}")
            feedsync.index_put(backend, sub, t + _backoff(failures), failures + 1)
            out["failed"] += 1
        out["processed"] += 1
    return out


def handler(event, context):
    try:
        limit = int(event.get("limit", DEFAULT_LIMIT)) if isinstance(event, dict) else DEFAULT_LIMIT
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    result = process_batch(max(1, min(limit, 200)))
    print(f"sync_blackboard: {result}")
    return result
