# Marketplace backend contract (Phase 8) — owner: Admin agent

Status: **coded and tested offline, not deployed, not wired.** Builder wires the routes (bottom). Mobile and Designer: code against these shapes. Errors are always `{ "error": code, "message": text }`. JWT (student pool) on every route here; there are no public marketplace routes, so no per-IP limit is needed (writes use the per-user limiter).

Principles: need-first (the Books view is the headline: syllabus books matched to listings, your campus first, then open campuses); campus-verified (tenant comes from the profile, never from the request); **no payments and no in-app messaging yet** (pickup happens at the campus spots listed here; the seller's email and id are never exposed, so buyer-seller contact needs a relay such as `POST /listings/{id}/contact`, a later decision; until then a seller may mention how to reach them in the description, but links are rejected); no images this phase; all listing text is untrusted user text (render as text only, wrap with `guard.wrap_untrusted` if it is ever put in a prompt).

## Listing object (what the API returns)

```
{
  id: "ab12cd34",
  title: "Calculus: Early Transcendentals 8th ed",
  author: "James Stewart" | "",
  isbn: "9781285741550" | null,       // always ISBN-13 digits (ISBN-10 input is converted)
  edition: "8th" | "",
  price: 35,                          // US dollars, 0 to 1000, at most 2 decimals. 0 = free
  condition: "New|Like new|Good|Acceptable",
  category: "textbooks",              // one of the seller campus's `categories`
  courseCode: "MIS 405" | "",
  description: "" ,                   // <= 500 chars, plain text, no links allowed
  pickupSpot: "" ,                    // one of the campus pickupSpots (when the campus lists any) or short free text
  status: "available|sold|removed",
  flagged: false,                     // true = hidden from others after reports (owner still sees it)
  demo: true | false,                 // seeded sample data: UI MUST show the "Demo listing" tag
  sellerName: "Sam",                  // short display name only. Never an email or id
  campus: { id: "ua", name: "The University of Alabama", shortName: "UA" },
  onYourCampus: true,
  mine: false,
  createdAt, updatedAt                // ISO UTC
}
```
Never present: seller sub, email, tenant domains, report details. Seeded demo listings have no seller, so nobody can edit them and `sellerName` is `"Demo seller"`.

Campus info for rendering is returned once per response in `campuses`:
`campuses: { "<id>": { id, name, shortName, pickupSpots: ["Student Center", ...], onYourCampus } }`.

## GET /listings

Query (all optional): `scope=campus` (default) | `network` | `mine`; `q` (words, all must prefix-match title, author, course code or category; max 80 chars); `isbn` (10 or 13 digits, hyphens allowed); `category`; `courseCode` (`MIS405`, `mis 405`, `MIS-405` all work); `limit` (default 30, max 60); `before` (an ISO `createdAt` from the previous page's last item, for the next page).

- `campus`: your campus only. `network`: your campus plus every other campus whose `openToNetwork` is true, that is not disabled, and none of whose domains is on the blocked list. `mine`: your own listings of any status except removed (including sold, flagged).
- Other people's `sold`, `removed` and `flagged` listings are never returned. Newest first.

`200 { listings: Listing[], campuses: {...}, campus: { id, name, shortName, pickupSpots }, safety: "Meet in a public, well-lit campus spot. Payment happens in person, never through this app.", nextBefore: "<createdAt>" | null }`
Errors: `400 validation_error` (bad isbn / scope / limit / before), `403 campus_disabled`, `403 no_campus`, `404 not_found` (no profile yet; call `/me` first).

## POST /listings

Body: `{ title (required, 3-160), price (required), condition (required), category (required), author?, isbn?, edition?, courseCode?, description?, pickupSpot? }`. Unknown fields rejected. The campus is the caller's; ISBN must have a valid check digit; description may not contain links (`http`, `www.`); category must be one of the campus categories (the message lists them).
`201 { listing }`. Errors: `400 validation_error`, `403 campus_disabled|no_campus`, `409 limit` (40 active listings), `429 rate_limited` (writes) or `429 daily_cap` (10 new listings per day).

## PATCH /listings/{id} (owner only)

Body: any of `title, author, isbn (null clears), edition, price, condition, category, courseCode, description, pickupSpot, status ("available"|"sold"|"removed")`. Marking `sold` hides it from everyone else; `removed` is the delete.
`200 { listing }`. A listing that is not yours (or does not exist, or is a demo listing) is `404 not_found`: the API never confirms that someone else's listing exists. `400 validation_error`, `429 rate_limited`.

## POST /listings/{id}/report

Body: `{ reason: "spam|scam|prohibited|wrong_info|other", note?: <=200 chars }`. One report per person per listing (repeats are accepted and ignored). Three distinct reporters flag the listing, which hides it from others. You cannot report your own listing.
`200 { reported: true }`. Errors: `404 not_found`, `400 validation_error`, `429 rate_limited` / `daily_cap` (20 reports a day).

## GET /books/matches

For each of the student's classes, its required (and optional) syllabus books with matching listings. Rate-limited like other heavy reads. Never lists your own listings; only `available`, unflagged listings on your campus or on visible open campuses.

```
200 { courses: [ {
  courseId, courseCode, title, color,
  books: [ {
    title, author, edition, isbn, required, notes,
    matches: [ {
      matchType: "isbn" | "title",        // isbn = exact ISBN via the ISBN index; title = normalised title/author match
      score: 1.0,                          // 1.0 for isbn, 0.6-1.0 for title
      listing: Listing                     // same object as above (price, condition, campus name, onYourCampus, demo, ...)
    } ],                                   // order: isbn matches (your campus first), then title matches on your campus, then title matches on other campuses; cheaper first inside a group
    bestPrice: 30 | null,                  // cheapest match
    bestOnYourCampus: 35 | null            // cheapest match on the student's own campus
  } ]
} ], campuses: {...}, pickupSpots: [...] }
```
`books` order: required first. `matches` has at most 5 entries per book. Courses still building (no books yet) return `books: []`.

## Item layout (DynamoDB single table)

| Item | pk | sk | Notes |
|---|---|---|---|
| Listing | `LISTING#{id}` | `META` | `id, tenantId, sellerSub (internal), sellerName, title, author, isbn, edition, price, condition, category, courseCode, description, pickupSpot, status, flagged?, demo?, createdAt, updatedAt`, `gsi1pk=TENANT#{tenantId}#LISTINGS`, `gsi1sk={createdAt}`, `gsi2pk=ISBN#{isbn13}` and `gsi2sk={tenantId}#{id}` (only when an ISBN exists) |
| Owner pointer | `USER#{sub}` | `LISTING#{id}` | `{id, createdAt}`; powers "mine", the 40-active cap and delete-my-data |
| Report | `LISTING#{id}` | `REPORT#{sha256(sub)[:16]}` | `{reason, note, createdAt, ttl 180 days}`; the reporter is stored only as a hash |
| Daily cap counter | `USER#{sub}` | `CAP#listings#{yyyymmdd}` / `CAP#reports#{yyyymmdd}` | counter with `ttl` |

Compatible with `scripts/seed.py` as it is today: seeded listings (`demo: true`, no `sellerSub`, no `updatedAt`, `condition` `Good|Like new|Acceptable`, int `price`) are read as is. Their `isbn` values are 13-digit and indexed in GSI2 already. Seeds may add `sellerName` / `description` / `courseCode` later; none is required.

Delete-my-data: delete `USER#{sub}` items as usual, then for every `LISTING#` pointer delete the `LISTING#{id}` items (META and REPORT#).

## Wiring for Builder (Admin did not touch api.py, stack.py or seed.py)

`backend/api.py`:
```python
import listings_api, books_api
...
# protected section, after `sub = _get_sub(event)`:
if path == "/listings" and method == "GET":
    return listings_api.list_listings(event, sub)
if path == "/listings" and method == "POST":
    return listings_api.create_listing(event, sub)
m = re.fullmatch(r"/listings/([a-z0-9]{8})", path)
if m and method == "PATCH":
    return listings_api.update_listing(event, sub, m.group(1))
m = re.fullmatch(r"/listings/([a-z0-9]{8})/report", path)
if m and method == "POST":
    return listings_api.report_listing(event, sub, m.group(1))
if path == "/books/matches" and method == "GET":
    return books_api.get_matches(event, sub)
```
`infra/stack.py`: the existing API role already has read/write on the table including its indexes (CDK `grant_read_write_data` covers `table/index/*`). No new routes (`/{proxy+}` JWT covers them). If you ever scope the IAM down, the code needs `dynamodb:Query` on `gsi1` and `gsi2`.

Tests: `python -I -m unittest discover -s backend/tests` from the repo root (`test_matching.py`, `test_listings_api.py`, `test_books_api.py`).
