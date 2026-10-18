# Semester OS architecture (companion to `architecture.drawio`)

## Open the diagram

1. Go to https://app.diagrams.net (or install the draw.io desktop app).
2. File > Open from > Device, pick `docs/architecture.drawio`. The file is plain uncompressed XML, so it also diffs in git.
3. Five tabs at the bottom are the five pages. Export for slides with File > Export as > PNG or SVG (tick "Include a copy of my diagram" only if you want it editable later; use a transparent background for dark slides).

## Icons and status legend

AWS services use the draw.io AWS Architecture Icons (aws4 library, built in; no plugin needed). Bedrock model providers are shown as badges (Z.ai, OpenAI, Mistral AI, Anthropic, Amazon). To export for slides: File > Export as > SVG (best for slides) or PNG.

| Border | Meaning |
|---|---|
| Green solid | DEPLOYED: seen in the real AWS account (stack `SemesterOS`, us-east-1, `UPDATE_COMPLETE`) |

## Pages

1. **System overview**: clients (student web, admin site, browser helper extension), CloudFront + S3 for both sites, the HTTP API with its student and staff JWT authorizers, the Lambdas, both Cognito pools, the DynamoDB table, S3 upload bucket, Bedrock with the model chain, KMS, EventBridge and the school registry.
2. **Agents**: the general agent, the router and handoff, one agent per class, the tool gate, and what each class agent owns (memory, history, materials, Blackboard feed, deadlines, books).
3. **Auto-campus and auth**: email -> `.edu` rule -> Cognito code -> first `/me` creates the campus -> verified colour table -> colour worker -> admin review.
4. **Security layers**: edge, identity, limits, data isolation, model safety, network and secrets, logging.
5. **Data model**: DynamoDB item types and keys, as the code writes them.

## What is really deployed (re-checked 2026-10-17, read-only)

- Live: both CloudFront sites, the HTTP API with student and staff JWT authorizers, Lambdas `api`, `process_syllabus`, `pre_signup`, `process_material`, colour worker and `sync_blackboard` (EventBridge `rate(15 minutes)`), a KMS key for feed URLs, DynamoDB with `gsi1` and `gsi2`, the upload bucket, both Cognito pools and the Bedrock chain. Features live: any-.edu auto-campus, colour worker, Blackboard feed sync, materials, history, memory, messages and grouped inbox, marketplace v2 and recommendations.
- Not built: real payments, student photo uploads, the helper in the Chrome Web Store.

## Ten things a judge should remember

1. **Multi-tenant by design.** One deployment serves every school; the campus comes from the verified email, never from the request.
2. **Campus-verified.** A `.edu` email plus Cognito's email code is the verification; no manual school setup.
3. **Auto-campus.** The first verified student at a school creates its themed campus; colours come from a verified table, else a worker detects them, else a safe placeholder.
4. **Cross-campus.** Listings and book matches search across schools, always labelled with the campus name.
5. **Need-first, not browse-first.** The syllabus builds a class agent, and the class tells the app which books you need.
6. **One agent per class**, plus a general agent that hands you to the right class on its own, with Undo.
7. **Actually works.** Real Cognito, real DynamoDB, real Bedrock, a live site; the status colours say honestly what is still pending.
8. **Security in layers.** Untrusted-data wrapping, a tool gate, user-scoped data access, limits and a kill switch, SSRF-safe fetching, redacted logs, a separate staff pool with TOTP and an audit log.
9. **Resilient AI.** A four-model fallback chain (GLM-5, gpt-oss-120b, Mistral Large 3, Claude Sonnet 4.6) with Nova Lite for fast tasks; no single model outage stops the app.
10. **Three clients, one brain.** The student web app, the browser helper (Chrome extension) and an admin console share one API contract.
