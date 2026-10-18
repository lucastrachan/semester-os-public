# Semester OS admin console (Admin agent)

A separate staff site with its own Cognito login. No admin key exists anywhere.

## What exists

| Piece | File |
|---|---|
| CDK construct `AdminSite` (staff pool, client, group, authorizer, `/admin/*` routes, S3, CloudFront, headers) | `infra/admin_site.py` |
| Admin handlers (group check, validation, audit log) | `backend/admin_api.py` |
| Vite + React app | `admin/` (imports `../web/src/styles/index.css`, theme `data-theme="ops"`) |
| Create a staff user (Luca runs) | `scripts/create_admin_user.py` |
| Build + upload the admin site (Luca runs) | `scripts/deploy_admin.py` |
| Offline tests | `scripts/test_admin_api.py` |

## Security design

- Staff pool is separate from the student pool: no self sign-up, password 12+ with upper, lower, digit, symbol, **TOTP MFA required** (no SMS), no email account recovery (another admin resets access), user-existence errors hidden, `admins` group.
- App client has no secret, SRP only, no OAuth flows; ID and access tokens last 30 minutes, refresh 8 hours, token revocation on.
- API Gateway: a dedicated JWT authorizer (staff pool issuer, admin client audience) on `/admin/{proxy+}`. A student token has a different issuer and audience, so it is rejected there. `admin_api.py` then re-checks that the issuer is the staff pool and that `cognito:groups` contains `admins` (403 otherwise). **It fails closed**: if `ADMIN_USER_POOL_ID` is missing from the Lambda environment every admin request gets 500 (`AdminSite` sets the variable; never remove it).
- The app sends the **ID token** as `Authorization: Bearer ...` (the authorizer accepts the client id as `aud` for ID tokens; the ID token also carries the email and groups). Tokens are kept in sessionStorage, and the console signs out after 15 idle minutes.
- Separate origin: own private S3 bucket (block all public access, SSL only, origin access control) and own CloudFront distribution. Headers: HSTS (2 years, preload), nosniff, X-Frame-Options DENY, Referrer-Policy no-referrer, `X-Robots-Tag: noindex`, `Cache-Control: no-store`, strict CSP: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https://*.execute-api.<region>.amazonaws.com https://cognito-idp.<region>.amazonaws.com; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`. No inline scripts or styles in the app.
- **CSP pinning.** `connect-src` allows exactly the API origin once `adminApiOrigin` is known. First deploy: the value does not exist yet, so the construct falls back to `https://*.execute-api.<region>.amazonaws.com` and prints a CDK warning. After the first deploy: add `"adminApiOrigin": "<ApiUrl output, no trailing slash>"` to the `context` block of `cdk.json` (it is a public URL, not a secret; or pass `-c adminApiOrigin=...`) and run `scripts/deploy.py` again. It is a plain string, so there is no CloudFormation cycle. `scripts/deploy_admin.py` checks the live CSP (read-only HEAD request) and prints this exact instruction while it is still unpinned. Also sent: COOP and CORP `same-origin`, Permissions-Policy.
- **Audit log** (`pk=ADMIN_AUDIT`, `sk=<ISO time>#<id>`, 90-day `ttl`): admin email and sub, action, target, small detail, source IP and a length-capped user agent. No tokens. Actions: `campus.create|edit|disable|enable`, `domain.block|unblock`, `campus.color.approve|set`, `campus.marketplace`, `listing.hide|unhide`, `conversation.close`, `user.ban|unban`, `report.resolve`, **`report.list`** (reads of reported messages), `demo.add|remove`, `audit.read`, and **`admin.denied`** (wrong issuer or not in `admins`; route and reason, no token). Every change is written in the **same DynamoDB transaction** as its audit item (both or neither); reads fail if their audit write fails. A ban also removes the user's listings and closes their chats afterwards, outside the transaction (safe to repeat). Campus requests were removed (AUTO_CAMPUS addendum v2): campuses are created automatically or directly by an admin.
- Campus creation validates server side: `^#[0-9a-fA-F]{6}$` colour, timezone through `zoneinfo`, free-mail domains blocked, LMS type, https links, and writes the tenant and every `DOMAIN#` map in **one DynamoDB transaction with `attribute_not_exists(pk)`**, so nothing is ever overwritten (409). `ink` is computed from luminance.
- **Admin-provided text is untrusted for every consumer** (student web app, Expo app, tutor prompts, calendar names). On write, `clean_text` strips control, format (bidi overrides, zero-width), surrogate and separator characters, collapses whitespace and caps length (name 120, short name 40, tutoring description 400, pickup spot 120, reason 200). Tutoring `url` must be a plain `https://` address with a host, no credentials, no spaces, at most 300 characters; `http://`, `javascript:` and `user:pass@` are rejected. Consumers must still render these fields as text only (never HTML), wrap them in the prompt-untrusted wrapper when used in prompts, escape them in iCal, show links with `rel="noopener noreferrer"`, and the mobile app must re-check `https://` before opening.

## Wiring for Builder (small, mechanical; Admin did not touch these files)

### `infra/stack.py`

1. Top: `from admin_site import AdminSite` (app.py already puts `infra/` on `sys.path`).
2. After `http_api` and `api_fn` exist (after the route block), add:

```python
admin_site = AdminSite(self, "AdminSite", http_api=http_api, api_fn=api_fn)
```

3. **Delete** the `("AdminRoutes", "/admin/{proxy+}")` entry from the public routes loop (the construct adds an authorised `/admin/{proxy+}`; leaving both gives two integrations on the same path).
4. **Delete** `"ADMIN_KEY": self.node.try_get_context("adminKey") or ""` from `api_fn` environment, and `"adminKey"` from `cdk.json`. (`AdminSite` adds `ADMIN_USER_POOL_ID` to `api_fn` itself.)
5. CORS (recommended): remove `x-admin-key` from `allow_headers` and, after `admin_site` and `distribution` both exist, override the API's CORS list with an escape hatch (this avoids a CloudFormation cycle that building `http_api` after `AdminSite` would cause):

```python
from aws_cdk import aws_apigatewayv2 as apigw  # already imported
cfn_api = http_api.node.default_child
cfn_api.cors_configuration = apigw.CfnApi.CorsProperty(
    allow_origins=[f"https://{distribution.distribution_domain_name}", admin_site.url],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["authorization", "content-type"],
    max_age=3600,
)
```

   If the mobile app calls the API, native fetch has no Origin header, so CORS does not affect it. Keep `http_api` created without `cors_preflight` in that case, or leave `["*"]` until this is tested.

The construct creates these CloudFormation outputs (stack-level ids): `AdminUserPoolId`, `AdminClientId`, `AdminBucketName`, `AdminDistributionId`, `AdminSiteUrl`.

### `backend/api.py`

1. `import admin_api` at the top.
2. At the top of the `try:` in `handler`, before the public routes:

```python
if path.startswith("/admin/"):
    return admin_api.handle(event) or util.error(404, "not_found", "Route not found")
```

3. Delete `admin_list_requests`, `admin_action_request`, `_check_admin`, `_AdminForbidden` (and its `except` branch), `_derive_short_name` (if unused) and the `hmac` import. (The public campus-request route is removed by Builder under AUTO_CAMPUS addendum v2.)
4. `lib/util.normalize_domain` keeps the last two labels; `admin_api` keys `DOMAIN#` maps with it so the signup gate matches. Multi-part TLDs (`.ac.uk`) still need the fix Planner noted.

### Lambda note

`admin_api` uses `zoneinfo`. If the Python 3.12 Lambda runtime lacks tz data, valid names will be rejected with "Unknown timezone". If that happens, `pip install tzdata -t backend/vendor` (pure Python) and add `vendor` to the path. Check once after deploy by creating a campus with `America/Chicago`.

### Later cleanup

Remove `web/src/pages/AdminPage.tsx` and the `/admin` route in the student web app, plus the `x-admin-key` mention in `API.md`, README and `DECISIONS.md`. New admin API is documented below.

## Admin API (all need the staff ID token, `admins` group)

- `GET /admin/me` returns `{ email, groups }`
- `GET /admin/overview` returns `{ campuses, demoCampuses, colorReviews, openReports, demoAccounts }`
- `GET /admin/campuses` returns `{ campuses[] }`
- `POST /admin/campuses` creates a campus directly (201 `{ tenantId }`)
- `POST /admin/campuses/{id}/color/approve` and `POST /admin/campuses/{id}/color {color}`: colour review for auto-created campuses
- `POST /admin/campuses/{id}/marketplace {categories?, ticketPriceCap?}`: enabled marketplace categories and the ticket face-value cap (MARKETPLACE_V2_API.md)
- `GET /admin/reports?status=open|resolved|all`, `POST /admin/reports/{id}/resolve`, `POST /admin/listings/{id}/hide|unhide`, `POST /admin/conversations/{id}/close`, `POST /admin/users/{sub}/ban|unban` (MESSAGES_API.md)
- `GET|POST /admin/demo-accounts`, `DELETE /admin/demo-accounts/{emailHash}`: test students (`DEMOACCT#{email}` / `MAP`)
- `GET /admin/audit` returns the latest 100 entries

Campus body: `{ name, shortName?, domains[], themeColor "#RRGGBB", timezone, lmsType "blackboard_ultra|canvas|other", tutoringResources[{name,description,url}], pickupSpots[], openToNetwork }`.

## Auto-campus: what the admin site needs from Builder (see AUTO_CAMPUS.md)

Admin side is done (Campuses view: auto-created badge, edit, disable/enable, blocked domains, all audited). Extra admin routes:

- `PATCH /admin/campuses/{id}` edits name, shortName, themeColor, timezone, lmsType, tutoringResources, pickupSpots, openToNetwork (same validation as create; domains are not editable; the stored `ink` is recomputed from luminance)
- `POST /admin/campuses/{id}/disable` body `{ reason? }`, and `POST /admin/campuses/{id}/enable`
- `GET|POST /admin/blocked-domains`, `DELETE /admin/blocked-domains/{domain}`

Fields and data Builder must read or write (the admin site only displays or sets them):

| Item | Used for |
|---|---|
| `TENANTS / T#{id}` `autoCreated: true` | Builder sets it when `/me` lazily creates a campus; admin shows the "auto-created" badge. Also store `lms: {type: "other", connector: "none"}`, no emails in the record |
| `TENANTS / T#{id}` `disabled: true`, `disabledReason`, `disabledAt` | Admin sets and clears. **Builder: `/me` must return 403 (code `campus_disabled`, friendly message) when the tenant is disabled, and lazy creation must never recreate or re-enable a disabled campus.** Data stays |
| `BLOCKED_DOMAINS / D#{domain}` (item with `domain`, `reason`) | Kill switch. **Builder: `pre_signup.py` and `/me` must reject an email whose domain or any parent suffix has a `get_item("BLOCKED_DOMAINS", "D#" + suffix)` hit**, before registry or campus matching; lazy auto-creation must also skip blocked domains; `/public/resolve` should answer "not found" for them. `admin_api._is_blocked(domain)` is a reference implementation (checks every suffix); the pre-signup role already has table read access |
| `ADMIN_AUDIT / <ISO>#<id>` | Written by `admin_api` only (90 day ttl). Actions: `campus.create`, `campus.edit`, `campus.disable`, `campus.enable`, `domain.block`, `domain.unblock`, `campus.color.*`, `campus.marketplace`, `listing.hide|unhide`, `conversation.close`, `user.ban|unban`, `report.*`, `demo.*` |

Existing students of a campus that gets disabled keep a valid session until the next `/me`; the 403 there is what locks them out.

## Luca's steps (nobody else runs these)

1. After Builder wires and `python scripts/deploy.py` has created the stack: `python scripts/create_admin_user.py you@example.com` (add `--print-password` to avoid email).
2. `python scripts/deploy_admin.py`, open the printed `AdminSiteUrl`, sign in with the temporary password, choose a new password, scan the QR code, enter the code.
3. The student `scripts/deploy.py` does not upload the admin site; run `deploy_admin.py` after admin code changes.

## Verified offline

`npx tsc --noEmit` and `npm run build` in `admin/`, `py_compile` on all Python, `python -I scripts/test_admin_api.py`, and a CDK synth of `AdminSite` in a scratch stack.


## Break-glass admin access

`account_recovery` is off for the staff pool, so a lost password or authenticator cannot be fixed by the user. Procedure:

1. Keep at least **two** admin accounts: your daily one and a break-glass one (own email, strong unique password and its own authenticator enrolment, stored offline, used only in emergencies and after use the password is rotated). Both are created with `scripts/create_admin_user.py`.
2. Lost authenticator or password for an account: the other admin (or Luca with AWS credentials) runs `aws cognito-idp admin-set-user-mfa-preference` / `admin-reset-user-password` / `admin-set-user-password` against the staff pool (pool id is the `AdminUserPoolId` output), or deletes the user and re-runs `create_admin_user.py` so the person re-enrols a new authenticator. Anyone who can do this holds AWS credentials for the account, so keep that group tiny.
3. Everyone locked out: only Luca with AWS credentials can recover, using the same commands; the pool has `RemovalPolicy.RETAIN` so it survives stack changes.
4. Review `ADMIN_AUDIT` (Audit log tab) after any break-glass use; the `admin.denied` entries show failed attempts.
