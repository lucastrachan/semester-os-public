# Semester OS API contract

Owner: Builder. Rules (from the internal planning notes): changes are **additive only** (add fields, never rename or remove). A breaking change is announced in the internal planning notes first. An endpoint's entry is added in the same step that ships it.

Base URL: `apiUrl` in `web/public/config.json`. All bodies are JSON.
Errors always look like `{ "error": "<code>", "message": "<human text>" }`.

## Auth

| Kind | How | Used by |
|---|---|---|
| Public | no header | `/public/*`, `/cal/*` |
| User | `Authorization: Bearer <Cognito ID token>` (the **ID** token, not the access token) | everything else |
| Admin | `Authorization: Bearer <admin-pool Cognito ID token>` (separate Cognito user pool; see ADMIN.md) | `/admin/*` |

The user and the campus always come from the token, never from the request. A missing or invalid token on a user route returns `401 unauthorized`.

## Live today

### `GET /public/tenants` (public)
Returns `200 { "tenants": [Tenant] }`.

`Tenant`:
```
id, name, shortName,
domains: [string],
theme: { primary, accent, ink },        // hex colours
timezone,                               // IANA, e.g. "America/Chicago"
lms: { type, connector },               // e.g. { "type": "canvas", "connector": "pending_admin_approval" }
tutoringResources: [{ name, description, url }],
pickupSpots: [string],
categories: [string],
openToNetwork: boolean,
createdAt
```

### `GET /public/resolve?domain=` (public)
Resolves a .edu domain to its school name and theme colors before signup.
- `200 { found: true, name, theme: { primary, ink }, colorStatus: "verified" | "placeholder" }`
- `404 not_found`: not a .edu domain, blocked, or unknown
- Rate-limited per IP (60/hour, 300/day)

### `GET /me` and `POST /me` (user)
Both return the user's campus and profile; `POST` optionally accepts `{ tz }` to set timezone on first call.
- `200 { profile, tenant, calendarPath }`
- `403 account_not_enabled`: non-.edu with no demo account configured
- `403 domain_paused`: domain is temporarily blocked
- `403 campus_disabled`: campus exists but is disabled
- `403 account_restricted`: banned user

`profile`: `{ sub, email, tenantId, displayName, calToken, prefs: { wakeHour, sleepHour, studyBlockMinutes }, feed, createdAt, updatedAt }`.
`calToken` is a secret (used for the calendar feed URL). Never log it.

### `GET /cal/{token}.ics` (public)
Returns the user's deadline calendar as iCalendar. Token comes from `profile.calToken` (rotate with `POST /me/calendar-token/rotate`).

### Admin routes (see ADMIN.md for full list)
Require an admin-pool Cognito ID token. Documented in `ADMIN.md`; managed through the admin console deployed at its own CloudFront URL.

## Coded, not deployed yet (Phase 2, slice 1: tested offline, goes live with the next deploy)

All need the user token. A user only ever sees their own classes. Course ids are 8 characters, `[a-z0-9]`.

### `POST /courses`
Two ways to call it.

**Paste text:** body `{ "text": "<pasted syllabus text>" }` (50 to 60,000 characters).
- `202 { course }` with `course.status = "BUILDING"`. The class is built in the background.

**Upload a PDF:** body `{ "filename": "syllabus.pdf", "contentType": "application/pdf" }` (the filename must end in `.pdf`).
- `201 { course, upload: { url, fields } }`. The browser then sends the file straight to S3 as a **multipart form POST** to `upload.url`, with every entry of `upload.fields` as a form field **first** and the file as the last field named `file` (max 10 MB, PDF only, link valid for 5 minutes). S3 then starts the build; no further API call is needed.
- A PDF whose upload never arrives is reported as `status: "ERROR"` after 10 minutes. A PDF that is password protected, not a real PDF or over 10 MB ends in `ERROR` with a student-readable `error`.
- Scanned PDFs (no text layer) are read as images by a vision-capable model and may be less accurate.

Either way: **poll `GET /courses/{id}`** every 2 seconds until `status` is `READY` or `ERROR`.
- `400 validation_error` (too short, or not a PDF), `400 too_long`, `429 daily_cap` (10 new classes per user per day, text and PDF together)

### `GET /courses`
`200 { courses: [Course] }`, oldest first.

### `GET /courses/{id}`
`200 { course: Course, assignments: [Assignment] }` (assignments sorted by due date; undated last). `404 not_found` if the id isn't yours.

### `DELETE /courses/{id}`
Deletes the class and its assignments. `200 { deleted: id }`, `404 not_found`.

`Course`:
```
id, status: "BUILDING" | "READY" | "ERROR",
color,                                  // hex from the 8-colour palette, fixed at creation
createdAt, updatedAt,
pipeline: [{ key, label, state: "pending" | "running" | "done" | "error", detail }],
        // keys in order: read_syllabus, extract_dates, build_calendar, match_books, tutor_ready
courseCode, title, instructor, term, officeHours, summary,        // "" until READY
meetings: [{ days: ["Mon","Wed"], start: "09:00", end: "09:50", location }],
books: [{ title, author, edition, isbn, required, notes }],
grading: [{ item, percent }],
policies: { late, attendance, ai, other },
knows: { materialsCount, assignmentsCount, lastUpdatedAt, lastFeedCheckAt, newItemsCount },
error?: string                          // only when status is "ERROR": text safe to show the student
```
`Assignment`: `{ id, courseId, title, type, dueDate: "YYYY-MM-DD" | null, dueText, dateSource: "stated" | "resolved" | null, dueTime: "HH:MM" | null, weight, notes, done, source: "syllabus", createdAt }`.
`type` is one of `exam, quiz, homework, project, paper, reading, other`. A `null` `dueDate` means the syllabus didn't give a date; the reason is in `notes`.
`dueText` is the syllabus's own words for the due date (for example "the Friday after Exam 1"). `dateSource` says where `dueDate` came from: `"stated"` (the syllabus gave a calendar date), `"resolved"` (worked out in code from other items' dates, so **show it as estimated** until the student confirms), or `null` (no date). Added in slice 2; older items may lack both fields.

## Feature-module routes (full shapes in per-module files)

Each module's `handle(event, sub, path, method)` is called before the generic `/courses/{id}` handlers; it returns `None` for paths it does not own.

| Module | File | Owned paths |
|---|---|---|
| History / Opening | `HISTORY_API.md` | `GET /courses/{id}/chat/history`, `GET /courses/{id}/opening`, `GET /chat/master/history` |
| Memory | `MEMORY_API.md` | `GET|POST|PATCH|DELETE /courses/{id}/memory/*` |
| Materials | `MATERIALS_API.md` | `GET|POST|DELETE /courses/{id}/materials`, `POST /courses/{id}/materials/text` |
| Blackboard feed | `FEED_API.md` | `PUT|GET|DELETE /me/feed`, `POST /me/feed/sync`, `GET|POST /courses/{id}/feed*`, `GET /feed/unassigned`, `POST /feed/unassigned/{uid}/assign|dismiss`, `POST /feed/seen` |
| Master / Agents | `MASTER_API.md` | `GET /briefing/today`, `POST /briefing/regenerate`, `POST /chat/master`, `GET /agents`, `GET /activity` |

## Not live yet (planned)

`PATCH /me`, `/tutoring`.
