# Marketplace v2 backend contract — owner: Admin/marketplace module agent

Status: spec for the internal planning notes. **Additive to MARKETPLACE_API.md** (everything there still holds unless this file says otherwise). Coded and tested offline, not deployed, not wired. Errors are `{ "error": code, "message": text }`. JWT (student pool) on every route. Designer and Mobile: code against these shapes.

## 1. What changes in the Listing object

New fields on every listing (old listings that lack them read as `kind: "sell"`, `images: []`, nulls):

```
{
  ...everything in MARKETPLACE_API.md...,
  kind: "sell" | "trade" | "free" | "wanted" | "service",
  category: "books" | "supplies" | "electronics" | "dorm" | "clothing" | "tickets" | "tutoring" | "rides" | "other",
  tradeFor: "" ,                       // kind trade: what the seller wants (<= 120 chars); "" otherwise
  acceptCash: false,                   // kind trade: also accepts cash (then `price` is the cash price)
  ticket: null | { event, eventAt, venue, section, quantity, faceValue, transferMethod, externalLink },
  tutoring: null | { subjects: ["Calculus I"], courseCodes: ["MATH 125"], mode, availability, standing },
  expired: false,                      // tickets only: the event has passed (hidden from others; owner still sees it)
  images: []                           // photos phase later; always an empty array for now
}
```
- `category` is now this fixed list. The legacy value `textbooks` is accepted as input and in filters and is returned as `books`. `price` is a number in US dollars (see per kind rules). `condition` may be `""` where it does not apply.
- `kind` values: `sell` (for sale), `trade` (swap), `free` (giveaway, price is 0), `wanted` (a "looking for" post, price = optional budget), `service` (tutoring, price = hourly rate, 0 = free).
- `status` stays `available | sold | removed`. `sold` also means "traded", "given away", "found one" or "not offering any more": the UI should label the button by kind ("Mark done").
- Never present: seller sub or email (unchanged). `sellerName` stays a first name only.

### Per-kind and per-category rules (POST /listings and PATCH)

| Rule | Detail |
|---|---|
| `kind` | optional on create, default `sell`. **Cannot be changed** by PATCH. |
| `sell` | `price` required, 0 to 1000 (0 still means free, as before; new clients should prefer kind `free`) |
| `free` | `price` must be absent or 0; stored as 0 |
| `trade` | `tradeFor` required (3-120 chars). `acceptCash` optional boolean (default false). `price` optional (0 to 1000); required > 0 if `acceptCash` is true |
| `wanted` | `price` optional (the budget, 0-1000, absent = no budget); `condition` optional; `description` encouraged. Wanted posts are hidden from the default browse (see GET /listings) |
| `service` | category must be `tutoring`; `price` = hourly rate (0-200, 0 = free); `tutoring` object required. Category `tutoring` requires kind `service` or `wanted` |
| `condition` | required (one of New, Like new, Good, Acceptable) for kinds sell, trade, free in the goods categories (books, supplies, electronics, dorm, clothing, other); optional (or `""`) for tickets, tutoring, rides and wanted |
| `books` | `isbn`, `author`, `edition`, `courseCode` as before |
| `category` | must be enabled for the seller's campus (see section 5). `category` can be changed by PATCH, but never to or from `tickets` or `tutoring` |
| Links | still rejected in every text field. The only link allowed is `ticket.externalLink` |
| Text | every field goes through `guard.clean_text` on write and on read |

**`ticket`** (category `tickets`; required for kinds sell, trade and free; optional for wanted, where only `event` is used). Body shape and returned shape are the same:
```
ticket: {
  event: "Alabama vs Tennessee",          // required, 3-120
  eventAt: "2026-10-24T19:00:00Z",         // required, ISO 8601 UTC with Z, must be in the future, at most 400 days ahead
  venue: "Bryant-Denny Stadium",           // required, 2-120
  section: "Section 12, row F" | "",       // optional, <= 40
  quantity: 2,                             // integer 1-10
  faceValue: 45,                           // price printed on one ticket, 0-1000 (required except for wanted)
  transferMethod: "official_app" | "mobile_wallet" | "will_call" | "other",   // required (except wanted)
  externalLink: "https://..." | ""         // optional, https only, no credentials, <= 300 chars; shown as "Open in official ticket app"
}
```
`price` is **per ticket**. With the campus switch `ticketPriceCap` on (the default), `price` may not exceed `ticket.faceValue` (`400 validation_error`, message "Tickets can't be listed above face value ($45)."). Free and wanted tickets are exempt. Prices above face value are accepted when the campus has turned the cap off. The cap is re-checked on every PATCH (and an edit of `faceValue` cannot be used to dodge it).
**Past events:** once `eventAt` is in the past the listing is hidden from every browse, search and chat start (read time, nothing is written) and the owner sees it with `expired: true` in `scope=mine`. The UI should show the safety banner: "No payments happen here. Transfer tickets only through the official channel. Never pay or send tickets outside it."
We do not integrate with MyTickets or any ticketing service; `externalLink` is a plain https link-out only.

**`tutoring`** (kind `service`; optional shape for wanted tutoring posts):
```
tutoring: {
  subjects: ["Calculus I", "Statistics"],   // 1-5 items, each 2-60 chars
  courseCodes: ["MATH 125"],                // 0-5 items, normalised like courseCode ("math125" -> "MATH 125")
  mode: "in_person" | "online" | "both",
  availability: "Weeknights after 6" ,      // <= 200 chars, plain text
  standing: "" | "freshman" | "sophomore" | "junior" | "senior" | "graduate"
}
```
`price` is the hourly rate. The top-level `courseCode` field also works for tutoring and is merged into the tag set. Tutors are matched to a class by any of `tutoring.courseCodes` or `courseCode`. Pickup spots apply to `in_person` and `both`.

### Caps and limits (same style as before)
Unchanged: 40 active listings, 10 new listings a day, writes rate limited. New: at most **10 active `wanted`** posts, **10 active `tickets`** listings, **3 active `tutoring`** listings per student (`409 limit`).

## 2. GET /listings (extended, same response shape plus `kind`-aware fields)

New or changed query parameters (all optional, combine with AND):
- `kind=sell|trade|free|wanted|service`. **Without `kind` the browse shows `sell`, `trade`, `free` and `service`; `wanted` posts only appear with `kind=wanted`** (and in `scope=mine`).
- `category` (the list above; `textbooks` works as `books`).
- `priceMin`, `priceMax` (numbers 0-1000; listings with no price are excluded when either is set).
- `condition` (one of the four; listings without a condition are excluded).
- `courseCode` (as before; also matches `tutoring.courseCodes`).
- `scope=campus|network|mine`, `q`, `isbn`, `limit`, `before` as before. `q` now also searches `tradeFor`, `ticket.event`, `ticket.venue`, `tutoring.subjects` and `tutoring.courseCodes`.
Expired tickets are never returned except in `scope=mine`. Errors: `400 validation_error` for a bad kind/category/price/condition.
Response additions: `campus.categories: ["books", ...]` (the categories this campus has enabled, so the UI builds its filter and create form), `campus.ticketPriceCap: true|false`, `kinds: ["sell","trade","free","wanted","service"]`.

## 3. GET /listings/for-you ("For you" strip, computed at read time, no writes)

Matches for **your own active `wanted` posts** and **required books of your classes**. Rate limited like `/books/matches`. Never includes your own listings, only available, unflagged, unexpired listings on your campus and visible open campuses. Wanted posts, trades and tickets match by title words and (for tickets) event name.
```
200 {
  items: [ {
    reason: "wanted" | "class_book",
    wantedId: "ab12cd34",            // reason wanted: your wanted post
    wantedTitle: "Calculus book",    // reason wanted
    courseCode: "MATH 125",          // reason class_book
    bookTitle: "Calculus ...",       // reason class_book
    matchType: "isbn" | "title",
    score: 0.9,
    listing: Listing
  } ],                               // at most 20, wanted matches first, then class books; your campus first, cheaper first
  campuses: {...}
}
```
A wanted post matches a listing when the category is the same, the kind is not `wanted`, the title-word score is at least the books threshold (0.75; for wanted books the ISBN equal also counts) and `price <= wanted.price` when the wanted post has a budget. At most 3 matches per wanted post, 1 per required book (the best).

### 3b. Recommended for your classes (`sections`, additive in the same response)

`GET /listings/for-you` also returns `sections` next to `items` and `campuses` (both unchanged). Sections are computed at read time from the student's class syllabi (course codes, titles, books); empty sections are omitted, so a student with no classes gets `sections: []` (plus the highlights section if the campus has any).
```
200 {
  items: [...], campuses: {...},                       // as in section 3
  sections: [ {
    id: "books" | "tutors" | "classmates" | "supplies" | "highlights",   // in this order
    title: "Books you need",
    reason: "From your class syllabi",                 // one line for the section header
    suggestion: true,                                  // only on "supplies": show a "Suggestions" label
    listings: [ {                                      // at most 8 per section
      reason: "Required for MIS 405",                  // per-listing reason text, plain text
      listing: Listing,
      courseCode?: "MIS 405", bookTitle?: "...",       // books / tutors / classmates entries
      suggestion?: true                                // supplies entries
    } ]
  } ]
}
```
- **books** ("Books you need"): required books first ("Required for MIS 405"), then optional ones ("Recommended for MIS 405"); each entry is the best match for that book (your campus first, cheapest first).
- **tutors** ("Tutors for your classes"): up to 3 tutoring listings per class ("Tutor for MATH 125"), your campus first, then open campuses, cheaper first.
- **classmates** ("Classmates selling"): listings on **your campus** tagged with one of your course codes via `courseCode` ("Tagged for MIS 405 on your campus").
- **supplies** ("Supplies for your classes", `suggestion: true`): a fixed mapping from the class department or title words to categories: computing (MIS, CS, IT, ECE, data/software words) -> electronics; math, stats, engineering, physics, economics -> calculators (supplies whose title mentions a calculator); chemistry, biology, lab -> lab supplies (title words such as lab, goggles, coat); art and design -> art supplies; plus dorm basics (category dorm) in August, September, January and February. Your campus only, cheapest first. Reasons read "Suggested for MATH 125: calculators" or "Suggested at the start of term: dorm basics".
- **highlights** ("Tickets and trades"): tickets (not expired) and trade listings on your campus, newest first ("Tickets on your campus", "Open to a trade on your campus").
- A listing appears in only one section (first match wins, in the order above). Never included: your own listings, flagged, sold, removed, expired, wanted posts, listings of closed or disabled campuses. Seller identity is never present.

## 4. GET /courses/{id}/tutors (tutors for a class)

`{id}` is one of the caller's courses (else `404 not_found`). Returns tutoring listings (`kind: service`, `category: tutoring`) tagged with the class, your campus first then open campuses, cheaper first; never your own, never flagged.
```
200 { course: { id, courseCode, title }, tutors: [Listing], campuses: {...} }
```
At most 20. Use `POST /listings/{id}/conversations` ("Request a session") to contact a tutor.

## 5. Per-campus marketplace settings (admin only)

Stored on the tenant: `categories` (enabled categories, the same field as before) and `ticketPriceCap` (boolean, default true when missing). A campus's `categories` may use the old name `textbooks`; it is read as `books`. Defaults when a tenant has none: all nine categories.
Admin route (staff token, audited in the same transaction):
`POST /admin/campuses/{id}/marketplace` body `{ categories?: ["books","tickets",...], ticketPriceCap?: true|false }` -> `200 { tenantId, categories, ticketPriceCap }`. `categories` must be 1 to 9 known values (no duplicates, `books` always kept). `400 validation_error` otherwise, `404` unknown campus. Turning a category off hides no existing listings; it only blocks new ones.
`GET /admin/campuses` already returns these fields (`categories`, `ticketPriceCap`).

## 6. Item layout additions (DynamoDB, same single table)

Listing META gets: `kind, tradeFor, acceptCash, ticket{event,eventAt,venue,section,quantity,faceValue,transferMethod,externalLink}, tutoring{subjects,courseCodes,mode,availability,standing}, images: []`, and `category` stored canonical (`books`). The owner pointer `USER#{sub}/LISTING#{id}` also stores `kind` and `category` (for the per-kind caps). No new indexes; for-you and tutors read the existing `gsi1` per campus.

## 7. Wiring for Builder (Admin did not touch api.py or stack.py)

```python
import market_api
...
# protected section, BEFORE the generic /listings/{id} patterns so "for-you" is not read as an id:
if path == "/listings/for-you" and method == "GET":
    return market_api.for_you(event, sub)
m = re.fullmatch(r"/courses/([a-z0-9]{8})/tutors", path)
if m and method == "GET":
    return market_api.tutors_for_course(event, sub, m.group(1))
```
Existing `/listings` routes need no change (same functions, extended). The admin route needs no wiring. Seed script: demo listings stay valid (no `kind` = sell, `textbooks` is read as `books`).
Tests: `python -I -m unittest discover -s backend/tests` (`test_market_v2.py`) and `python -I scripts/test_admin_api.py`.
