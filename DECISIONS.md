# Decisions

## CORS
Using `*` for HTTP API CORS origins during the hackathon. Post-hackathon: tighten to the CloudFront URL.

## sync_blackboard concurrency
No `reserved_concurrent_executions` on the SyncBlackboard Lambda. The account limit is 10 total concurrent executions; CloudFormation requires the unreserved pool to be ≥ 10, so reserving any capacity rolls back the stack. Overlap protection comes from the design instead: EventBridge fires one invocation every 15 minutes, the handler caps its batch at 25 students and has a 120s timeout, and a single run completes well within the 15-minute window. Two invocations cannot meaningfully race because each student's sync row has a `lastCheckedAt` guard.

## Models
- MODEL_MAIN: `zai.glm-5` — extraction, tutoring, briefing, planning (100 rpm on-demand; Claude profiles in this account are capped at 10 rpm)
- MODEL_FAST: `amazon.nova-lite-v1:0` — routing, classification, color detection
- Fallback chains: MODEL_MAIN → `openai.gpt-oss-120b-1:0, mistral.mistral-large-3-675b-instruct, us.anthropic.claude-sonnet-4-6`; MODEL_FAST → `zai.glm-5`
- Chosen in a live bake-off logged in the internal planning notes "MODEL DECISION". The previous entries (Sonnet 4.6 / Haiku 4.5) were the initial defaults before the bake-off ran.

## Config delivery
`config.json` is written by `scripts/deploy.py` after CDK outputs are available, then synced to S3 with the static assets. The frontend fetches it at runtime — no VITE_ env vars need to be baked into the build.

## CloudFront cache
CACHING_DISABLED for fast iteration during the hackathon. Phase 10: switch to a real cache policy.

## Lambda runtime
Python 3.12 (Lambda runtime). Local Python is 3.14 — no conflict since CDK specifies the runtime separately.

## daily_run (scheduled briefings and plans)
`backend/daily_run.py` stays a documented stub. The handoff's cut list says to keep on-demand regeneration, and `GET /briefing/today` already generates the briefing when it is missing. A nightly run would need a scheduled Lambda, an index to list users (today that would be a table scan), a per-run cap and a Bedrock rate budget; design it only if on-demand proves too slow.
