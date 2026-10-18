# Auto-campus: every school works from the first signup

Owner: Planner. Status: spec v1, 2026-10-17. Requested by Luca: "whatever email signs up, it figures out the school, opens that school's own page, and no school needs to be added by hand."

## Idea in one line

A verified email at a known school domain **is** the campus verification. If the school has no campus yet, the first verified student creates it automatically, themed and ready. Manual "request your school" stays only as a fallback for domains we don't know.

## Why this is feasible (checked 2026-10-17)

- A public dataset of universities and their email domains exists: `Hipo/university-domains-list`, file `world_universities_and_domains.json`. I downloaded it: 10,268 institutions worldwide, **2,349 in the US, 2,328 of those with a `.edu` domain**. Fields: `name`, `country`, `domains[]`, `web_pages[]`, `alpha_two_code`, `state-province` (mostly empty). No US domain is shared by two institutions.
- **Check its license before we ship it** (repo license not verified yet) and credit it in the README.
- It has NO brand colour, NO timezone and (mostly) NO state, so those are generated (below).

## Flow

1. **Resolve while typing (optional but nice).** Signup page calls `GET /public/resolve?domain=ua.edu` (public, rate-limited). If the domain is a live campus or in the registry, the page shows "Sign up for University of X" in that school's colours. Unknown domain: show the "request your school" link.
2. **Pre-signup (Cognito trigger).** Allow the signup if the email's domain matches a live campus OR a registry entry. Matching is by suffix (`students.x.edu` -> `x.edu`), using the registry, not "last two labels" (that breaks `.ac.uk`, `.edu.au`). Free-mail domains can never match. Reject otherwise with the existing friendly message and `/request` link. **The pre-signup trigger must NOT create anything**: the person is not verified yet, and creating campuses for unverified attempts would let anyone mint junk campuses.
3. **Email code verification** (unchanged). This is what proves the person controls an address at that school.
4. **First authenticated `/me`.** If the user's domain has no campus yet but is in the registry, create the campus now, using a **conditional put** so two simultaneous first-signups cannot overwrite each other (the second one reads the winner). Then create the profile as today.
5. **Open the school's page.** After sign-in the student lands on their dedicated school page (`/campus`, themed), showing the school name, what is configured, and the next steps (add classes, tutoring and pickup spots when known). The app (Expo) does the same on its first tab.

## What gets generated for a new campus

| Field | Source |
|---|---|
| `id` | slug of the registry name; unique, never reused |
| `name`, `domains` | registry entry (all domains of that institution) |
| `shortName` | initials, like the admin approve flow does now |
| `theme.primary` | deterministic colour from the school name (hash to a curated palette of ~12 hues with AA text contrast; `deriveTheme` computes ink). It is a placeholder, not the school's real brand. Admin can override |
| `timezone` | the browser/device IANA timezone sent by the first student, validated with `zoneinfo`; fallback `America/New_York`. Admin can override |
| `lms` | `{type: "other", connector: "none"}` until configured |
| `tutoringResources`, `pickupSpots` | empty, with an empty state that invites additions (admin edits first; student suggestions can come later) |
| `categories` | the default marketplace categories |
| `openToNetwork` | true (listings always show the campus name) |
| `autoCreated`, `createdBy`(hash only, no email), `createdAt` | for audit |

## Rules and safeguards

- Registry data is public school info; the resolve endpoint reveals nothing private. Still rate-limit it (per IP) and return nothing for unknown domains except "not found".
- **Verification email cap.** Cognito's default sender allows 50 emails a day per account, and anyone can trigger signup emails for other people's addresses at any school. Plan: move Cognito to SES in production mode (needs one AWS support form) before any public launch, and add a per-IP signup throttle in front of Cognito if possible. For the hackathon demo, pre-create demo accounts.
- Admin site gets a **Campuses** view: auto-created badge, edit name/colour/timezone, disable a campus or block a domain (kill switch for abuse). Disabled campuses cannot sign in; existing data is kept.
- Keep `POST /public/campus-request` for domains not in the registry; admin approval creates the campus as it does now.
- No emails in tenant records or logs.

## Ownership

| Agent | Task |
|---|---|
| Builder | `scripts/build_school_registry.py` (download the Hipo list, keep US `.edu` first, write `backend/data/us_schools.json`, attribution in README); registry loader with suffix lookup (`lib/registry.py`); `pre_signup.py` uses it; `GET /public/resolve`; lazy conditional campus creation in `/me` (accept optional `tz` in the body); remove the "last two labels" normalisation; tests for suffix matching, the race, and free-mail rejection; update `API.md` |
| Designer | `autoThemeFromName(name)`: a pure function next to `color.ts` returning a palette colour that passes AA (no DOM); the themed school page and the "Sign up for University of X" header treatment |
| Mobile | Signup screen resolves the domain as the user types and themes itself; first tab opens the school page; send `tz` (`Intl.DateTimeFormat().resolvedOptions().timeZone`) with `/me` |
| Admin | Campuses view with auto-created badge, edit, disable, block domain, plus audit entries |
| Security | Review the pre-signup and resolve design for abuse (enumeration, signup email flooding, race), add the rate limit on `/public/resolve`, check the domain match code |
| Planner | Review, then update the demo script: sign up with a school that was never configured and watch its campus appear |

## Decisions already made (Planner, within Luca's goal; tell Planner if you disagree)

- US `.edu` first (2,246 schools); other countries later with the same mechanism.
- Auto-created campuses default to `openToNetwork: true`.
- Colours are generated placeholders, not real branding (no logos or mascots).
- The seeded campuses (UA, Auburn, Georgia Tech) stay as curated examples with real data.

---

## Addendum v2 (Luca, 2026-10-17): no more campus requests

Luca: "we don't have any campus request anymore; every campus we have colours for is built, and for those we don't, an agent searches for their colours once they sign in."

**Decisions (Planner, executive):**
1. **The "request your school" flow is removed.** Remove `POST /public/campus-request`, the `/request` web page, the app's request link, and the admin "Campus requests" queue.
2. **Any `.edu` domain is accepted.** `.edu` is restricted to accredited US institutions, so a verified `.edu` email is itself proof of a real school. The Hipo registry (2,246 schools) supplies the official name when it knows the domain; for an unknown `.edu` the name comes from the school's own homepage (og:site_name or title) via the colour worker below, with the domain as a temporary name. For `.edu`, the registrable domain is the last two labels (`students.x.edu` -> `x.edu`).
3. **Non-`.edu` emails are rejected** at pre-signup with a friendly message: "Semester OS supports US colleges (.edu email addresses) for now." International schools can be added later by extending the registry.
4. **Colours, in priority order:** (a) `backend/data/school_colors.json` (verified from official sources); (b) the **colour finder worker**, started once, asynchronously, when a campus is created without a verified colour; (c) the generated placeholder palette until (b) finishes or if it fails.
5. **Colour finder worker** (new Lambda or async invoke of an existing one, Builder builds it): fetches ONLY `https://www.<school domain>` (and the bare domain) through `safe_fetch` (SSRF-safe, size cap, no redirects off the same registrable domain), extracts candidates (CSS custom properties and `theme-color` meta, favicon dominant colour is optional), treats the page text as untrusted (guard.wrap_untrusted), asks MODEL_FAST/MODEL_MAIN to choose the primary brand colour from the candidates with a one-line reason, then validates in CODE: `#RRGGBB`, not near-white or near-black, contrast computed, saturation above a floor. Stores `theme.primary`, `colorSource: "autodetected"`, `colorConfidence`, and `colorStatus: "needs_review"`; never overwrites a verified colour. On any failure it leaves the placeholder and records `colorStatus: "placeholder"`. Limits: once per campus, per-day cap on worker runs, kill switch. (Honest expectation: in a 25-school probe only 4 homepages exposed a `theme-color`, so many results will be low-confidence; hence the review step.)
6. **Admin review:** the admin site's Campuses view shows `needs_review` campuses with the detected colour, source and confidence; an admin can approve or set a colour (hex validated server-side).
7. **Background coverage:** a research agent extends `school_colors.json` for more schools (largest US universities first), so fewer campuses depend on the worker.

**Task changes per agent:** Builder (remove campus-request route and queue; any-.edu pre-signup; lazy create in /me; colour worker; resolve endpoint returns the best known name/colour and `colorStatus`); Designer (remove `/request` page and links; unknown-school state now means "not a .edu address"; show a gentle 'colours are being detected' note when `colorStatus` is placeholder); Mobile (same; remove the request link); Admin (drop the Campus requests tab and routes once Builder removes the public form; add the colour review to Campuses); Security (review the worker for SSRF/prompt injection; verify no public write endpoint remains).
