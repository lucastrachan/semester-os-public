#!/usr/bin/env python3
"""
Read-only probes after a deploy. Prints PASS/FAIL lines.

Usage:
  python scripts/post_deploy_check.py
  python scripts/post_deploy_check.py --since 2026-10-17T15:00:00Z   # custom start time for CloudWatch check
  python scripts/post_deploy_check.py --skip-cloudwatch               # skip CW (no creds needed)

Exit code 0 = all probes passed, non-zero = at least one failed.
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_PATH = ROOT / "cdk-outputs.json"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

_failures = []


def _check(name: str, ok: bool, detail: str = ""):
    tag = PASS if ok else FAIL
    line = f"  [{tag}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    if not ok:
        _failures.append(name)
    return ok


def _load_outputs():
    if not OUTPUTS_PATH.exists():
        sys.exit("ERROR: cdk-outputs.json not found. Run a deploy first.")
    data = json.loads(OUTPUTS_PATH.read_text())
    api_url = table_name = log_group = None
    for stack_output in data.values():
        api_url = api_url or stack_output.get("ApiUrl")
        table_name = table_name or stack_output.get("TableName")
        log_group = log_group or stack_output.get("LambdaLogGroup")
    if not api_url:
        sys.exit("ERROR: ApiUrl not found in cdk-outputs.json")
    return api_url.rstrip("/"), table_name, log_group


def _get(url: str, headers=None, method="GET") -> tuple:
    """Returns (status_code, body_bytes, response_headers)."""
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return 0, str(e).encode(), {}


def probe_public_tenants(api_url: str):
    status, body, _ = _get(f"{api_url}/public/tenants")
    ok = status == 200
    count = 0
    if ok:
        try:
            count = len(json.loads(body).get("tenants", []))
        except Exception:
            ok = False
    _check("GET /public/tenants → 200", ok, f"status={status}")
    _check("Tenant count ≥ 1", count >= 1, f"count={count}")
    return count


def probe_unauthenticated_401(api_url: str):
    status, _, _ = _get(f"{api_url}/me")
    _check("GET /me without JWT → 401", status == 401, f"status={status}")


def probe_cors_preflight(api_url: str):
    headers = {
        "Origin": "https://app.semesteros.com",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    }
    status, _, resp_headers = _get(f"{api_url}/me", headers=headers, method="OPTIONS")
    # API GW HTTP API responds 200 or 204 for OPTIONS with CORS configured
    ok_status = status in (200, 204)
    _check("OPTIONS /me preflight → 200/204", ok_status, f"status={status}")
    acao = resp_headers.get("access-control-allow-origin") or resp_headers.get("Access-Control-Allow-Origin", "")
    _check("CORS Allow-Origin present", bool(acao), f"value={acao!r}")


def probe_resolve(api_url: str):
    status, body, _ = _get(f"{api_url}/public/resolve?domain=ua.edu")
    ok = status == 200
    if ok:
        try:
            j = json.loads(body)
            ok = "name" in j or "tenantId" in j
        except Exception:
            ok = False
    _check("GET /public/resolve?domain=ua.edu → 200 with data", ok, f"status={status}")


def probe_cloudwatch_errors(log_group: str, since_iso: str):
    try:
        import boto3
    except ImportError:
        print(f"  [{SKIP}] CloudWatch error count — boto3 not available")
        return
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    try:
        cw = boto3.client("logs", region_name=region)
        since_ms = int(datetime.fromisoformat(since_iso.replace("Z", "+00:00")).timestamp() * 1000)
        resp = cw.filter_log_events(
            logGroupName=log_group,
            startTime=since_ms,
            filterPattern='"ERROR" OR "error" OR "Traceback"',
            limit=20,
        )
        events = resp.get("events", [])
        count = len(events)
        _check(f"CloudWatch errors since {since_iso} → 0", count == 0, f"found {count} error log line(s)")
        if events:
            for e in events[:5]:
                print(f"      {e.get('message', '')[:120]}")
    except Exception as exc:
        print(f"  [{SKIP}] CloudWatch error count — {exc}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default=None, help="ISO timestamp: start of deploy window for CloudWatch check")
    ap.add_argument("--skip-cloudwatch", action="store_true", help="Skip the CloudWatch errors probe")
    args = ap.parse_args()

    api_url, table_name, log_group = _load_outputs()
    since = args.since or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"\nSemesterOS post-deploy check")
    print(f"  API:   {api_url}")
    print(f"  Table: {table_name or '(unknown)'}")
    print(f"  Since: {since}\n")

    count = probe_public_tenants(api_url)
    probe_unauthenticated_401(api_url)
    probe_cors_preflight(api_url)
    probe_resolve(api_url)

    if not args.skip_cloudwatch and log_group:
        probe_cloudwatch_errors(log_group, since)
    elif not args.skip_cloudwatch and not log_group:
        print(f"  [{SKIP}] CloudWatch — LambdaLogGroup not in cdk-outputs.json")

    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print(f"All probes passed. Tenants in registry: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
