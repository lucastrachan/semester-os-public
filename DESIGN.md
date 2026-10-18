# Semester OS: Design system (Designer)

Direction: **calm OS**. Modern, a little techy, generous whitespace. Mono type for system labels, window-style cards, one hue at a time (the campus colour, or the class colour in study mode). No campus logos or mascots: the wordmark is text, "Semester" plus an `OS` pill. The one character is the **agent robot family** (below), which Luca approved; it takes the campus or class colour and never uses school marks.

Files (all in `web/src/styles/`):

| File | Purpose |
|---|---|
| `index.css` | Entry point. `import './styles/index.css'` once in `main.tsx`, replacing `../index.css`. |
| `tokens.css` | Spec variables, type/space/radius/motion tokens, light and dark neutrals. |
| `themes.css` | **Generated.** 8 class themes (`data-theme="c0".."c7"`) in light and dark, plus status colours. |
| `base.css` | Reset, typography, focus ring, ambient background, utilities, reduced motion. |
| `components.css` | Every component class below. |
| `theme.ts` | `applyCampusTheme(hex)`, `applyClassTheme(index, campusHex)`, `deriveTheme`, `contrast`. |
| `preview.html` | Living style guide. Dev server: `/src/styles/preview.html` (add `?theme=c3`). |

## Spec variables

`--bg --surface --ink --muted --accent --accent-ink --accent-tint --border` all exist. Extra: `--accent-strong` (accent-coloured **text or lines** that must pass AA; use it instead of `--accent` for text), `--surface-2`, `--border-strong` (inputs), `--focus`, status tokens `--ok --warn --danger --info` (text) with `-tint`, `-fill`, `-fill-ink`.

Rule of thumb: **fill** with `--accent` and put `--accent-ink` on it. **Text or icons in the accent hue** use `--accent-strong`. Soft backgrounds use `--accent-tint`.

## Theming API (Builder: this is all you need)

```ts
import { applyCampusTheme, applyClassTheme, classIndexFromHex } from './styles/theme'
applyCampusTheme(tenant.theme.primary)          // home pages (any #RRGGBB, contrast-derived at runtime)
applyClassTheme(classIndexFromHex(course.color), tenant.theme.primary) // entering /class/:id or a handoff
applyClassTheme(null, tenant.theme.primary)     // leaving: back to campus
```

- It only sets `data-theme` on `<html>` (`campus`, or `c0`..`c7`). `--accent*` are registered with `@property`, so they **transition over 450ms** and every component follows. Colours only: no layout shift. Reduced motion: instant.
- **Local theming:** any element can carry `data-theme="c2"` to take that class colour regardless of the page theme. Use it on course chips, calendar events, timeline blocks, deadline chips, book cards and activity items so a class colour is consistent everywhere.
- Palette order = `CLASS_PALETTE` in `theme.ts` = spec section 10. Assign `color` from it at course creation; `classIndexFromHex` maps it back.
- No JS yet: `<html>` without `data-theme` uses the default indigo accent.

## Contrast (WCAG AA), verified numerically

Neutrals: ink 16.7:1 on bg; muted 5.8:1 (light) and 6.9 to 7.4:1 (dark) on bg/surface. Each theme is derived so that:
- `--accent-ink` on `--accent` is >= 4.5:1. White where it passes (indigo, rose, violet), otherwise `#10131A`: teal 4.96, amber 5.83, emerald 4.93, sky 4.54, orange 5.22.
- `--accent-strong` on bg, surface **and** tint is >= 4.65:1 in both schemes. It is darkened in light mode (amber `#A15804`, orange `#BB460A`, teal `#0A766D`) and lightened in dark mode (indigo `#847EED`, violet `#A171F2`).
- Status text colours use the same derivation.
- Raw `--accent` as a *line or icon* can be under 3:1 (amber on white is 2.9). That is why meaningful lines and focus rings use `--accent-strong`; raw accent is for fills with `--accent-ink`, and decoration.

Regenerating: the derivation lives in `theme.ts` (`deriveTheme`); `themes.css` was generated from the same algorithm. If the palette changes, tell Designer.

## Class names (for Builder)

**Shell**
`.app-shell > header.app-header (.brand [text "Semester" + span.brand-os "OS"], .campus-chip.badge) + nav.app-nav[aria-label] (a.nav-item[aria-current="page"] > svg.nav-icon + span.nav-label) + main.app-main > .page`. The same nav is the **bottom bar on mobile and a side rail at 960px+**. Max 5 items without `.nav-secondary` (extras show only on desktop). Add `<a class="skip-link" href="#main">`. `.page-head`, `.section-head`, `.eyebrow`, `.stack`, `.row`.

**Buttons:** `.btn-primary`, `.btn-ghost`, `.btn-danger`, `.btn-sm`, `.btn-block`, `.btn-icon`; `aria-busy="true"` shows a spinner. Legacy `.btn-ghost-sm .btn-approve .btn-reject` kept.

**Surfaces:** `.card`, `.card-accent`; `.window > .window-bar (.window-dots><i><i><i>, .window-title, badge) + .window-body + .window-foot`.

**Badges and chips:** `.badge[data-status="ready|building|syncing|error"]`, `.badge-ok/-warn/-danger/-info`, `.badge-count`, `.chip`, `.chip-outline`, `.chip-due[data-urgency="soon|overdue"]`, `.chip-action` (agent tool actions), `.tag`, `.tag-demo` ("Demo listing"), `.chip-row`.

**Forms:** `.field > label + input/select/textarea + .hint`, `.field.has-error` or `aria-invalid="true"` plus `.field-error`, `.field-row`, `.check`, `.color-row`, `.dropzone` (+ `.is-over`), `.segmented`, `.tabs > .tab[aria-selected]`.

**Agents:** `.agent-grid > article.window.agent-card[data-theme="cN"] > .agent-swatch + .window-bar + .window-body (.agent-name, .agent-role, .knows > div > b + span, .agent-meta)`. Build pipeline: `ol.stepper > li.step[data-state="pending|running|done|error"] > .step-dot + text (+ .step-detail)`. System status: `.window.sys-panel > .sys-row > .led[data-state="ok|busy|idle|error"] + (.sys-name, .sys-detail) + .sys-time`. Activity: `.activity > .activity-item[data-theme] > .activity-dot + text + .activity-time`.

**Today:** `.briefing`, `.briefing-greeting`, `.briefing-grid`, `.briefing-block > h3`, `ol.priority-list`, `.warning`. Timeline: `.timeline > .tl-item > .tl-time + .tl-block[data-theme][data-kind="class|study|deadline|break"] > .tl-title + .tl-sub`; `.tl-now` for the current-time line.

**Chat:** `.chat > .chat-log (.msg.msg-user / .msg.msg-agent > .msg-meta, .msg-actions, .typing > i*3) + form.chat-composer`; `.chat-dock` (sticky above the mobile nav); `.handoff-banner > text + strong + button.btn-ghost-sm "Undo"` (`role="status"`).

**Study:** `.quiz-progress[style=--value:40%]`, `.quiz-options > button.quiz-option[data-state="correct|wrong"][aria-pressed]`, `.quiz-explain`, `.score`; `.flashcard[.is-flipped] > .flashcard-inner > .flashcard-face.flashcard-front + .flashcard-back` (reduced motion swaps faces without rotating).

**Calendar:** `.cal-grid > .cal-dow + .cal-cell[data-outside][data-today] > .cal-date + button.cal-event[data-theme]`; `.agenda-day`, `.copy-field`.

**Books:** `.book-card`, `.listing[data-here="true"]`, `.price`.

**Feedback:** `.skeleton-line(.short)`, `.skeleton-block` (put `aria-busy="true"` on the container); `.empty > .empty-art + .empty-title + .empty-body + CTA`; `.progress[style=--value]`; **boot loader** `.boot > .window.boot-window > .window-body > .boot-lines > .boot-line[style="--i:N"][data-state="ok"] + .boot-bar > i` (lines type in 280ms apart; last line gets a blinking cursor); **toasts** `.toast-region[aria-live="polite"] > .toast[data-kind="error|success|info"][role="alert" for errors] > .toast-title + .toast-body + button[aria-label="Dismiss"]`.

**Existing markup keeps working** (`.landing`, `.campus-list`, `.form-page`, `.request-form`, `.field`, `.success-card`, `.admin-*`, `.group-*`, `.req-*`, `.stat`, `.empty-state`, `.err`, `.muted`, `.back-link`, `.hero-actions`). Hard-coded colours from `index.css` became tokens.

## Accessibility and motion

- Focus: `:focus-visible` 2px ring in `--accent-strong` with offset. Inputs also get a tint halo.
- Touch targets >= 44px on buttons, nav, tabs; 36px for `.btn-sm`.
- `prefers-reduced-motion`: all transitions and animations collapse, shimmer disappears, flashcards swap instead of flip, boot lines show instantly, theme change is instant. Nothing is conveyed by motion alone.
- `prefers-color-scheme` drives light and dark; `color-scheme: light dark` is set. `forced-colors` keeps borders and focus.
- Status is never colour-only: badges carry text, steps carry glyphs, LEDs sit next to labels.

## Requests for Builder (markup only)

1. `main.tsx`: import `./styles/index.css` and drop `index.css` when ready (I'll say so in the log).
2. `web/index.html` title: "Semester OS". Landing `<h1>`: `Semester <span class="brand-os">OS</span>`.
3. Call `applyCampusTheme` after `/me` or the tenant loads, and `applyClassTheme` in class study mode.
4. Optional: a boot screen using `.boot` while the first `/me` call loads.

## Not done / known limits

- Icons are not shipped; `preview.html` shows simple inline SVG `<symbol>` icons you can copy (`i-today`, `i-agents`, `i-cal`, `i-books`, `i-tutor`).
- Fonts are the system stack (`Inter` used if installed). No webfont to keep the first load fast.
- Verified in Chrome: dark (desktop, 390px frame) and light (desktop, amber theme) by eye, all themes numerically. Preview supports `?scheme=light|dark&theme=cN` to force a scheme.

## Agent robots (`design/robots/`)

Little friendly robots, one per agent, same family (rounded head, white face plate, ears, small body with a chest badge). Each has a distinct **topper** so it reads at 24px, not just at 96px.

| File | Agent | Topper / chest |
|---|---|---|
| `robot-chief-of-staff.svg` | Master / Chief of Staff | star / star |
| `robot-class-tutor.svg` | Class tutor (one base, tinted per class) | mortarboard / plus |
| `robot-calendar-sync.svg` | Calendar Sync | calendar ring tabs / calendar |
| `robot-planner.svg` | Planner | pencil / checklist |
| `robot-books.svg` | Books | open book / text lines |
| `robot-base.svg` | Generic agent (no accessory) | antenna / blank |
| `robot-state-building.svg` | State: building | dashed "loading" eyes, blue "..." badge |
| `robot-state-ready.svg` | State: ready | happy eyes, green check badge |
| `robot-state-error.svg` | State: error | worried eyes, red "!" badge |

`design/robots/preview.html` shows them at 96px and 24px on light and dark, plus the tutor in all 8 class colours (serve the folder, e.g. `python -m http.server`).

**Tinting.** The body, ears, antenna and toppers use `currentColor`; the face plate is fixed white and eyes/glyphs fixed `#10131A`, so the robot reads on any background and the face never loses contrast. Set the colour with CSS `color` or the RN `color` prop:

- Web (inline SVG, not `<img>`, because `<img>` blocks `currentColor`): `<svg style={{ color: 'var(--accent)' }}>`. Wrap in an element with `data-theme="cN"` to tint a tutor robot by class, or `color: var(--accent)` inside a themed page.
- React Native (`react-native-svg`, e.g. via `react-native-svg-transformer`): `<ClassTutorRobot color={theme.accent} width={48} height={48} />`.
- Use `accent` (not `accentStrong`) for the body: it is a fill, with a white plate for the face.
- State badges are fixed colours (sky `#0284C7`, emerald `#059669`, rose `#E11D48`) with a white glyph and ring, independent of theme. They are paired with a face change, so state is never colour-only.

**States wanted (delivered).** The three states above are on the base robot. Any agent robot can use them: show the agent's own robot normally, and swap to a state variant while building or on error, or overlay just the badge. Not drawn (could add): `syncing` (use `building`), `sleeping` (eyes closed, for paused agents).

**Motion (optional).** Building: bob the whole robot 2px, 1.2s ease; ready: one 200ms scale pop. Both off under `prefers-reduced-motion` / RN Reduce Motion.

Accessibility: each file has `role="img"`, a `<title>` and `aria-label`. When a robot sits next to the agent's name, hide it from screen readers (`aria-hidden`) so it is not read twice.

## Admin console and CSP notes

- **Admin look:** set `data-theme="ops"` on `<html>` (neutral slate, AA-checked, no campus colours) and import `web/src/styles/index.css`. Existing tokens and class names stay backward compatible: changes will be additive only (new tokens/classes), and I'll announce any rename in the log first. `.sys-panel`, `.led`, `.badge[data-status]`, `.group-card`, `.stat`, tables-as-lists and `.btn-*` suit an ops console.
- **Strict CSP (style-src without 'unsafe-inline'):** the stylesheet files themselves are static (`@import` same-origin, no data: URIs, no webfonts, no external URLs). `theme.ts` applies the campus theme through a constructed stylesheet (`adoptedStyleSheets`, CSSOM), which strict CSP allows; only very old browsers fall back to a `<style>` element (would need a nonce). `applyClassTheme` only sets a `data-theme` attribute. No inline scripts in the app styles. The documented `style="--value:40%"` / `style="--i:2"` patterns must be set through React's `style` prop (CSSOM, allowed), never as server-rendered `style="..."` attributes. `preview.html` is a dev-only page with inline script/style and is not shipped.

## Auto-campus: colour, school page, signup header

**`autoThemeFromName(name)`** (in `web/src/styles/color.ts`, pure, no DOM): maps a school name to one of 12 curated hues in `CAMPUS_PALETTE` (crimson, burnt orange, gold, olive, forest, teal, cyan, blue, navy, violet, magenta, rose).
- Deterministic: FNV-1a hash plus a murmur finalizer over `normalizeSchoolName(name)`, which lowercases, strips accents and punctuation, and drops filler words (the, of, at, and, in, for, university, college, institute, school), so "The University of Alabama" and "University of Alabama" match and the distinctive word decides. Same input gives the same colour on web and native.
- Even spread: 2,000 generated names landed 141 to 183 per hue.
- AA: every hue has white ink >= 4.9:1, and `deriveTheme` text colours pass in light and dark (checked for all 12 x 2 schemes: 0 failures). Use `deriveTheme(autoThemeFromName(name), scheme)` or `applyCampusTheme(autoThemeFromName(name))`.
- It's a **placeholder, not the school's brand**. Say so on the school page. Admin can override with a real colour (store as `theme.primary`).
- Known limit: two different schools can share a hue (12 hues). The name and domain are always shown with it, so it never identifies a school by colour alone.

**School page `/campus`** (Builder: markup). Call `applyCampusTheme(tenant.theme.primary)` so everything is already in the school's colour.
```
main.page
  section.campus-hero            name (h1.campus-name), .campus-meta > .chip x domains + .badge "Auto-created" (if autoCreated),
                                 p.campus-note "Placeholder colour. Not the school's official brand."
  section > .section-head h2 "What's set up" + .config-grid
      .config-item[data-state="set|empty"] > h3 (title + .badge) + .config-value | ul.config-list
        items: Timezone, LMS connector, Tutoring resources, Pickup spots, Marketplace (open to network)
        empty ones: data-state="empty" with one line + a CTA button ("Suggest a pickup spot"), dashed border, muted
  section > .section-head h2 "Next steps" + ol.next-steps
      li.next-step[data-done="true|false"] > div (.next-title + .muted line) + a.btn-primary.btn-sm
        suggested: Add your classes, Link your Blackboard calendar, Set your study hours, Find your books
```
Empty states: tutoring and pickup spots use `.config-item[data-state="empty"]` (not the big `.empty`), because the page has several. Wording: "No pickup spots yet. Be the first to suggest one." Never show fake data; seeded demo items keep the `.tag-demo` "Demo listing"/"Demo data" tag.

**Signup header** (Builder: `AuthPage`). Reserve the space so nothing jumps:
```
header.signup-header[data-state="idle|resolving|resolved|unknown"]
  h1 "Sign up for " + span.signup-campus  (school name; "your school" while idle/unknown)
  p.signup-hint[data-kind="ok|unknown"]   ("Found University of Alabama" / "We don't know this school yet. Request it")
```
- Debounce the resolve call (~400ms after the email domain stops changing). `idle`: "Sign up for your school". `resolving`: skeleton pill, no theme change. `resolved`: call `applyCampusTheme(color)` (the theme transitions over 450ms, instant under reduced motion) and put the school name in `.signup-campus`. `unknown`: `applyCampusTheme(undefined)` returns to the default, hint links to `/request`.
- Announce the result to screen readers (`aria-live="polite"` on `.signup-hint`).
- Leaving the page without signing in should restore the default theme.

## Calendar details (from CALENDAR_API.md)

- Wrap each calendar item in `data-theme` from `classIndexFromHex(assignment.courseColor)`.
- `dateSource: "resolved"` means the agent estimated the date: set `data-estimated="true"` on `.cal-event` / `.agenda-item` (dashed edge and a "~" prefix) and give it an accessible label "estimated date". `"manual"` and `"stated"` look solid.
- `done: true` gets `data-done="true"` (muted, strikethrough). Undated items go in a `.undated` section ("Needs a date") above or below the grid, never silently hidden.
- Agenda rows: `.agenda-item > .agenda-time + (.agenda-title + .agenda-note) + checkbox/button`. Mark-done is a real checkbox (optimistic update); 44px target.
- Subscribe panel: `.subscribe-panel > .copy-field (input readonly + .btn-ghost "Copy") + .secret-note "Anyone with this link can see your deadlines" + rotate button .btn-ghost`. The URL is a secret: show it masked (`.secret-mask`, dots) until the student presses "Show", and never in screenshots or logs.

## Website screens (design notes; desktop idiom per the internal planning notes section 1)

Shell for every signed-in route: `.app-shell` (header + side rail on desktop, bottom bar on mobile). Rail items: Today, Agents, Calendar, Books, then `.nav-secondary` Tutoring, Settings. Ctrl/Cmd+K opens the master chat as a centered command palette (window card, input first, Esc closes, focus trapped, returns focus).

### /agents (Agent Library) [SUPERSEDED by "Agents v2" below: no system-agent cards or status panel; route is /study]
- Top: page head "Your agents" + one primary button "Add a class". Below: `.agent-grid` of cards in API order: Chief of Staff, class agents, then system agents (Calendar Sync, Planner, Books) in a `.sys-panel` window "system status" rather than three more cards.
- Class card: `article.window.agent-card[data-theme]` (colour from `agent.color` via `classIndexFromHex`), tutor robot (`robot-class-tutor`, `color: var(--accent)`, 56px) in the window body next to name and role, `.badge[data-status]`, `.knows` (assignments, materials, new). Building or error: swap robot to `robot-state-building` / `robot-state-error` and show `ol.stepper` from `pipeline`; poll every 2s while any is building, stop at READY/ERROR. Primary action "Study mode" (ready only); error shows `course.error` with "Paste text instead".
- Chief of Staff card uses `robot-chief-of-staff`; Calendar Sync, Planner, Books use their robots in `.sys-row`. Status map: `ready/active` ok, `building` info pulse, `idle` muted, `not_connected` muted with "Connect" link, `coming_soon` muted, `error` danger.
- Right column (>= 1100px) or below the grid: `.activity` feed (limit 30), each item `data-theme` from its `agentId` course.
- Add class: `.dropzone` (multiple PDFs, drag over adds `.is-over`; click or keyboard opens the file picker) plus a "Paste text" tab (`textarea`, 50 to 60,000 chars with counter). Per-file progress rows with `.progress`. Daily cap (429 `daily_cap`) shows an error toast with the server message.
- Empty: `.empty` with robot-base, "Drop a syllabus and your first class agent builds in under a minute."

### /class/:id (study mode) [SUPERSEDED by "Agents v2" below: route is /study/:id, tabs changed]
- `applyClassTheme(index)` on enter and cleanup on leave. Header: robot, "MIS 405", title, instructor, `.badge`; back link to /agents.
- Split pane >= 960px: left the tutor (`.window` with `.tabs`: Tutor, Quiz, Cards, Cram), right a sticky column with Deadlines and Syllabus facts. Mobile: tabs scroll, side column becomes further tabs.
- Tutor tab: `.chat` with `.msg-agent` / `.msg-user`, typing indicator (replies take 4 to 25s), reply as plain text (light markdown only), actions as `.chip.chip-action` with an Undo `.btn-sm` when `undoable`; after any action refetch the course and flash the changed deadline row. Error mapping from TUTOR_API.md (429 disables Send until `Retry-After`).
- Quiz: one question per screen with `.quiz-*` classes, `short` questions reveal the model answer and let the student self-grade; final `.score`. Flashcards: `.flashcard` flip on click or Space, arrow keys move, "Known" / "Review" buttons (known set is client-only for now).
- Cram: shows the plan text, then a primary "Put these study blocks in my calendar" button which sends the explicit confirmation message the API expects ("yes, put those in my calendar"); result appears as an action chip.
- Deadlines: list sorted by date; `dateSource: "resolved"` shows the "~ estimated" badge; done items muted; checkbox with optimistic update. Syllabus facts: grading as a small bar list, policies (AI policy highlighted), office hours, books.

### /today
- `.briefing` window: greeting, classes today (timeline blocks with prep chips), due soon (`.chip-due` urgency from date), priorities (`.priority-list`), warnings (`.warning`). `source: "computed"` shows a small "Basic briefing (AI paused)" note, never an error. "Regenerate" button disabled on 429 until `Retry-After`.
- `.chat-dock` master chat. A handoff response shows `.handoff-banner` "Switching you to your MIS 405 tutor: reason" with Undo, then `applyClassTheme` and navigate to `/class/:id` after about 1.2s unless undone (Undo re-sends the same message with `target: "master"`). A `clarify` response renders option buttons.
- Empty (no classes): `.empty` with CTA to /agents.

### /calendar, /campus, signup header
See "Calendar details" and "Auto-campus" above.

### /books (marketplace)
- Per class `.book-card[data-theme]`: required books first, matches as `.listing` rows (campus first, then network, `.tag` campus name, `.price`, condition, `.tag-demo` for `demo: true`). Scope toggle `.segmented` Campus / Network. "List your copy" opens a form window; description is plain text, no links (the API rejects them). Report as an overflow menu action. Safety line from the API shown under the list. Listing chat (when live): a `.chat` window per conversation, plain text only, closed conversations disabled with the reason.

### Safety in the UI
Model and user text only as text nodes; no `dangerouslySetInnerHTML`; no remote images; links https only with `rel="noopener noreferrer"`; never render or log tokens, calendar URLs or emails of others.

### Backend gaps the screens would hit (reported to Planner)
1. No chat history endpoint: tutor and master chats vanish on reload. Design keeps the last conversation in `sessionStorage` per class; the server could add history later.
2. Flashcard "known" progress has no endpoint (client-only).
3. `GET /me` does not return `calendarPath` or tenant `autoCreated` yet (calendar subscribe panel and /campus badge need them).
4. `/agents` class entries carry only `courseCode` as name, no course title: the UI joins with `GET /courses`.
5. Not live yet: `/tutoring`, `PATCH /me`, `PUT/DELETE /me/feed`, `/feed/unassigned`, `/courses/{id}/materials`: Settings, Tutoring hub and materials upload have no API to build against.
6. Activity items carry `agentId` only (no colour): the UI looks it up from the course list.

### Listing chat (MESSAGES_API.md)
- Inbox: `/books` gets a "Messages" tab (badge `.badge-count` with `unreadTotal`). Rows reuse `.listing`: listing title, `other.name` + campus `.tag`, last-message preview (text only, 80 chars), time, unread dot.
- Thread: `.window` with title "{listing title}" and a price/status chip; `.chat` bubbles (`from: me` -> `.msg-user`, `them` -> `.msg-agent`, `system` -> centered muted `.eyebrow` line). Composer is plain text, 1000 chars with counter, no link or image controls; show the API's link-rejection message inline (`.field-error`), not as a toast.
- Closed conversations (`canSend: false`): composer replaced by a `.warning`-style note with the reason in plain words ("This listing was removed"); blocked is neutral ("This conversation is closed"), never saying who blocked.
- Always show the safety line ("Meet in a public, well-lit campus spot. Payment happens in person.") above the composer. Names are display names only; never show emails or ids.
- Mobile: the thread is a pushed screen; composer pinned above the keyboard, haptic light on send.

## Agents v2: Study tab, class agent hub, handoff (the internal planning notes)

One agent per class, plus one general agent. There are **no Calendar Sync, Planner or Books agents** and no system-status panel. (`.sys-panel`/`.sys-row`/`.led` classes still exist in `components.css` for the admin console; the student app doesn't use them. The calendar-sync, planner and books robots remain in `design/robots/` only for empty states such as the calendar and books pages.)

**Navigation (web and app):** Today (general agent) · Study · Calendar · Books (marketplace) · Settings. Campus and Tutoring are secondary items on desktop and are linked from Settings. Old `/agents`, `/onboarding` and `/class/:id` redirect to `/study` and `/study/:id`.

### /study
- Page head "Your class agents" + "Add a class" (drop PDFs or paste text; same `AddClass`).
- **General agent entry:** a `.window` with `robot-chief-of-staff`, "Chief of Staff", one line ("mention a class and I'll bring you to its agent with the material"), buttons "Ask now" (opens the Ctrl/Cmd+K chat via the `semester:open-chat` event) and "Today".
- **Class agent card** (`article.window.agent-card[data-theme]`): tutor robot (building/error variants), course code, title, instructor, `.badge` status, `.knows` = deadlines, materials, new from Blackboard, `.agent-meta` = "Checked Blackboard 12m ago" or "Blackboard not connected" plus "updated 5m ago", build `ol.stepper` while BUILDING (poll 2s), "Open agent" (-> `/study/:id`), Delete with confirm, "Paste text instead" on ERROR.
- Recent activity (`.activity`, per-class colour) when `/activity` has items. Empty state with the base robot and "Add your first class".

### /study/:id: the class agent hub
Header: robot, code and title, instructor, status badge, `.chip` row "N deadlines · N materials · N new from Blackboard". The whole UI is re-themed to the class colour (`applyClassTheme`). `.tabs` (scrollable): **Chat · Materials · Deadlines · Blackboard · Books · Memory · Syllabus**.
- **Chat (default):** `.segmented` mode switch (Explain, Quiz, Cards, Cram); the agent's **opening message** is the first `.msg-agent` bubble with the agent's name (computed from deadlines: "Exam 2 is in 6 days. Want a study plan, or should we practice first?"; replace with a server opening when `HISTORY_API.md` provides one); **quick-action chips** below ("Plan for Exam 2", "What's due this week?", "Quiz me", "Make flashcards", "How is my grade calculated?") that switch the mode and, for chat modes, send the prompt for the student; replies as plain text; action chips with Undo; cram confirm button; Retry-After cooldown; history kept per class in `sessionStorage` until server history exists.
- **Materials:** drop zone (PDF or text, 20 MB, "only add your own course materials"), list with status (Reading... / Ready / Failed), summary, remove. "Coming soon" empty state until the route exists.
- **Deadlines:** list with checkbox (optimistic), `~ estimated` badge for `dateSource: resolved`, "from Blackboard" for `feed`, urgency chips, "Needs a date" group.
- **Blackboard** (`FEED_API.md`): status card (Connected/Problem, last checked, "Check now" with cooldown), "Is this MIS 405?" one-tap assign for items whose top suggestion is this class, "From Blackboard (N)" list with a **New** badge (opening the tab calls `POST /feed/seen`); not connected shows "Connect in Settings". The honest limits line is always shown (dates and events only).
- **Books:** the syllabus books with Required/Optional and a link to the marketplace.
- **Memory:** every note the agent keeps, with Edit, Delete and "Clear all memory" (confirm). Explains that it only saves short facts about progress and preferences.
- **Syllabus:** summary, office hours, grading bars, AI policy highlighted, other policies.

### Settings and calendar additions
- Settings has the **Blackboard card** (`FeedCard`): password-type field for the secret link (never shown again, only the masked form), Connect, Check now with cooldown, Disconnect with confirm, honest limits and the exact path (Calendar > gear icon, top right > three dots in the panel > Share calendar).
- Calendar has the **Unassigned inbox** (`UnassignedInbox`): each item shows title, date and class chips with the likeliest pre-marked "(likely)"; one tap assigns and remembers; "Not a deadline" dismisses.

### The handoff moment (general agent -> class agent)
`.handoff-banner` appears in the master chat, locally themed in the target class colour: the class tutor robot, **"Switching you to your MIS 430 agent"**, the reason, and **material chips** ("Using: Lecture 4.pdf") from `handoff.materials`; Undo restores the campus theme and re-asks the master. After 1.2s the whole UI re-themes to the class colour (instant under Reduce Motion), the answer is labelled "MIS 430 agent", and an "Open MIS 430 agent" button goes to `/study/:id`. Announce the switch with `aria-live`. Leaving the chat returns to the campus theme.

## Logo (design/logo/)

**The mark:** a rounded "window" tile (the OS idea) with three title-bar dots and a bold **S** (Semester). Brand colour is indigo `#4F46E5` (white on it is 6.3:1). It sits in the same family as the robots: rounded, friendly, calm. The wordmark is **Semester** in heavy sans plus a mono **OS** pill, exactly as in the app header. Source of truth: `design/logo/build_logo.py` (edit and re-run to regenerate every SVG); `design/logo/preview.html` shows all variants.

| File | Use |
|---|---|
| `semester-os-mark.svg` | The mark in brand colour (default). |
| `semester-os-mark-tint.svg` | Tile follows `currentColor`, glyph stays white: tint with a campus or class colour (never use on a colour where white is under 4.5:1; amber/teal/emerald/sky/orange need the dark glyph, so use the mono or default mark there). |
| `semester-os-mark-mono.svg` / `-black.svg` / `-white.svg` | One colour with the S and dots cut out. `-mono` uses `currentColor`. For print, stamps, dark backgrounds. |
| `favicon.svg` | Tab icon: bolder S, no dots, readable at 16px. |
| `app-icon.svg` / `app-icon-maskable.svg` | Rounded app icon, and a full-bleed version with the glyph inside the 80% safe zone for Android/PWA maskable. |
| `semester-os-lockup.svg`, `-on-dark.svg`, `-mono.svg` | Horizontal: mark + wordmark. Use on light, on dark, or one colour (`currentColor`). |
| `semester-os-stacked.svg`, `-on-dark.svg` | Stacked, for square spaces. |
| `semester-os-cover.svg` | 1920 x 1080 cover: dark, lockup, tagline "Your college chief-of-staff", the five agent robots. |
| `png/` | Rendered exports: `favicon-16/32/48`, `apple-touch-icon-180`, `icon-192/512`, `icon-maskable-512`, `mark-512`, lockups (light/dark, 1440 wide), stacked, `cover-1920x1080`. |

**Usage rules**
- Clear space around the mark is at least 25% of the tile width. Minimum size: mark 16px (use `favicon.svg`), lockup 120px wide.
- Do not stretch, rotate, recolour the glyph, add shadows or put the mark on busy photos. Use the dark lockup on dark backgrounds, the mono version on a single-colour or photographic background.
- The mark stays brand indigo even when the app is themed to a campus or class colour; only the tinted variant takes another colour, and only for in-app decoration.
- The robots remain the **agent** icons; the mark is the **product** icon. Do not put a robot inside the tile.
- Text in the lockups is live `<text>` with a system font stack (Inter if installed, otherwise Segoe UI, SF, Roboto). For print or anything that must match exactly, use the PNG exports or convert to outlines in a vector editor first.
- Web wiring: `web/index.html` has the favicon, apple-touch-icon, `theme-color` (light and dark) and `manifest.webmanifest` (standalone PWA, maskable icon); the header shows the mark next to the wordmark. Files are in `web/public/`. Mobile: use `png/icon-512.png` / `icon-maskable-512.png` for the app icon and adaptive icon foreground, `png/mark-512.png` for the splash.

## Slide deck system (design/deck/)

`design/deck/deck.css` + `layouts.html` + `README.md`: 1920x1080 dark slides in the product's look (same tokens, class colours via `data-theme`, mono eyebrows, window-style screenshot frames). 13 layouts: cover, section, statement, title + bullets, two columns, big numbers, agent roster, phone mockup, desktop mockup, architecture page (draw.io on a light card), roadmap, judging-criteria map, closing. Rules in the README: one accent per slide, body never under 32px, titles are claims, speaker notes in a hidden `<aside class="notes">` (Time / Say / Show / Next, 80 words max), screenshots captured in dark mode with demo data only, charts as direct-labelled bars. Content is the Planner's; this is only the look.

App icons for the stores: `design/logo/png/icon-1024.png` (opaque square, iOS) and `icon-maskable-1024.png` (Android adaptive), from `app-icon-square.svg` and `app-icon-maskable.svg`.

## LMS onboarding: "Let's find your classes" (/onboarding, the internal planning notes Phase A)

Shown right after the first sign-up (confirm -> `/onboarding`), from the Today empty state, and from the Campus next steps. Never asks for an LMS password; says so in a note on the first screen: *"Semester OS never sees your school password. We only use a calendar link or a token you create yourself, and you can remove them any time in Settings."*

**Structure (one page, three stages shown as chips: 1 Choose, 2 Connect, 3 Your classes):**
1. **Which learning system does your school use?** Three radio cards: Blackboard, Canvas, Something else / not sure. Preselect from `tenant.lms.type` (`blackboard*` -> Blackboard, `canvas` -> Canvas, `other` -> Something else) with a "Your school" badge; the student can change it.
2. **Connect** (a `.window` panel per choice):
   - **Blackboard:** numbered guide with the confirmed menu path: *Calendar > the gear icon (Calendar Settings, top right of the Calendar page) > the three dots (More options) in the panel that opens > Share calendar > copy the link* (with a note that menu names can differ a little by school and that the link is dates and events only). A password-type field for the link, then the big **Scan for classes** button (`.btn-lg`): `PUT /me/feed` (the link is then only ever shown masked) then `POST /me/feed/sync`. Live progress as `ol.stepper`: Checking your link, Reading your calendar, Matching deadlines to classes (with "Found N deadlines, M waiting for a class"). Already connected: shows the masked link and a "Scan for classes" button that only syncs. Honest line: the calendar gives deadlines; add each class's syllabus to build its agent.
   - **Canvas:** guide for *Account > Settings > New access token* (name it "Semester OS"; some schools turn tokens off), a secure field and **Scan for classes**. **Coming soon:** while `CANVAS_SCAN_LIVE` is false (`web/src/lib/lms.ts`, the single place to wire the future contract) the field and button are disabled and **no token is requested or sent**; a note says to use syllabi for now.
   - **Something else:** the syllabus upload (`AddClass`: drop PDFs or paste text) is the whole path.
3. **Your classes:** cards appear as classes are found or built (robot, class colour, status, build stepper), then the **Unassigned inbox** (one tap to assign a Blackboard event to a class), and for Blackboard/Canvas an "Add a class from its syllabus" button that opens `AddClass`. "Go to Study" appears once at least one class exists.

States: the Blackboard panel shows a calm "isn't available yet" line when `/me/feed` is not deployed; errors use the API's friendly `message` (`feed_*` codes) and never raw text. Keyboard: the radio cards are real buttons with `role="radio"`; progress is `aria-live="polite"`.

## Marketplace v2, nav merge and campus badge (the internal planning notes)

**Navigation (web and app): Today · Study · Marketplace · Calendar · Settings.** The Tutoring tab is gone. Old `/tutoring` redirects to `/study`; old `/books` redirects to `/marketplace`. Study gains a **Campus help** section: the tenant's tutoring resources (name, description, https-only link with `rel="noopener noreferrer"`), a dashed "not set up yet" state when empty, and a "Find a peer tutor" button into the marketplace. AI tutors are the class agents.

**Campus badge** (`CampusBadge`, header, every signed-in page): a pill with a monogram tile in the **campus colour** (not the class colour; text colour from `deriveTheme(...).accentInk`), the short name in bold and the full name small (hidden on phones). Tapping opens `/campus`. **No school logos** (trademark): the monogram is 2-3 letters from the short name or the initials of the full name. A later admin-set `tenant.logoUrl` (https only, `object-fit: contain`, never fetched from the web) would replace the tile.

### /marketplace
- Head: "Buy, sell, trade, tutor" + **Create listing**. Tabs: **Browse · My listings · Messages (unread count)**. The safety line from the API is always shown.
- **For you** strip (when browsing without filters): your classes' required books with the cheapest match (`GET /books/matches`), one tap to message the seller; wanted-post and saved-search alerts are coming with the V2 API.
- **Search and filters** (sticky): text search, `My campus` / `All open campuses`, category chips (Books, Supplies, Electronics, Dorm, Clothing, Tickets, Tutoring, Rides, Other), type chips (For sale, Trade, Free, Wanted, Services), max price, Clear filters. Category and text go to the server; type and price are filtered in the client until the V2 API supports them.
- **Cards** (`.market-grid` of `.market-card`), chosen by category and kind: **basic** (title, author/edition, price, condition, campus, demo tag, pickup spot); **trade** (Offering <-> Wants, "also accepts cash"); **ticket** (dashed ticket edge, event, date, venue, section/row, quantity, price with "Face value $X" and an "Above face value" warning, transfer method, safety banner "capped at face value, official ticket app only, never send money first", optional "Open in the official ticket app" link, https only); **tutor** (profile card: robot, name, rate per hour, subjects/classes, mode, availability, meeting spot, "Request a session"). Every card has Message and Report; demo and own listings have no actions; all text is plain text.
- **Create/edit form** adapts to kind and category: kind segmented control, category chips, fields per type (books: author, ISBN; trade: wants + cash toggle; ticket: event, date/time, venue, section/row, quantity, face value, transfer method, optional official link; tutor: subjects, rate, mode, availability; wanted: max price). Until `MARKET_V2_LIVE` (in `web/src/lib/market.ts`) is true only plain for-sale and free listings in the campus's current categories are sent; the rest show "coming soon" and nothing unknown is posted. Edit sends only the fields the current API accepts.
- **My listings:** list with status, Edit, Mark sold, Remove. **Messages:** the per-listing chat inbox and threads (already built).
- Empty states: nothing listed ("Be the first"), no matches (Clear filters), no listings of mine.

**Backend fields the V2 UI needs** (for MARKETPLACE_V2_API.md): `kind`; `tradeFor`, `acceptsCash`; `ticket {eventName, eventAt, venue, section, row, quantity, faceValue, transferMethod, officialUrl}` with the face-value cap enforced server-side and past events hidden; `tutor {subjects[], rate, availability, mode}`; filters `kind`, `maxPrice`, `condition`, `courseCode`; wanted-post alerts for the "For you" strip; `tenant.logoUrl` (optional, admin-set, https).

**Copy rules (Luca, final):** the Blackboard path is always written as *Calendar, the gear icon (Calendar Settings, top right of the Calendar page), then the three dots (More options) in the panel that opens, then Share calendar*. Nav names in any instruction are exactly Today, Study, Marketplace, Calendar, Settings (there is no Tutoring or Books tab; the school badge in the header opens the school page). **Primary path is "Connect Blackboard to import your classes"; "Upload a syllabus instead" is the clearly secondary option** (onboarding: collapsed section below the Blackboard panel; Study and Today empty states: primary button "Connect Blackboard", secondary link "Upload a syllabus instead").

**Correction (Luca, from a real exported Blackboard calendar): the feed gives deadlines but does NOT say which class each belongs to, so there is NO automatic class import.** This replaces the earlier "Connect Blackboard to import your classes" copy:
- **Onboarding** (`/onboarding`): headline "Connect your Blackboard calendar to pull in every deadline". Steps: **1. Connect calendar** (guided panel, gear icon > three dots > Share calendar), **2. Add each class with its syllabus** (paste, upload, or "Try with a sample syllabus"; always visible, not a fallback), **3. Sort deadlines**. Never promise automatic class creation.
- **Unassigned inbox is the hero of the feed experience** (`UnassignedInbox hero`): "Sort your deadlines into classes". Deadlines are grouped by title pattern ("Reading Journal x12", numbers/dates stripped; uses the server's `groups` when `GET /feed/unassigned` sends them, otherwise grouped in the client), each group is one card with the next due date and one class chip per class: **one tap assigns the whole group** (the app assigns each item with `remember: true`, so the server also places look-alikes) and says "Added 12 deadlines to the class". "Not deadlines" dismisses a group. If no class exists yet it says to add a class with its syllabus first.
- **Empty states:** Study: "Add each class with its syllabus (paste it, upload it, or try the sample) ... Connect your Blackboard calendar to pull in every deadline" with primary **Add a class with its syllabus** and a link to connect the calendar. Today: "Add your first class" with **Get started**. Settings and the class Blackboard tab: "Connect your Blackboard calendar ... to pull in every deadline. Then sort them into your classes."
- **Marketplace (planned):** a calm "Recommended for you" area at the top of the Marketplace home replaces the "For you" strip: small cards with a one-line reason ("Required for MIS 405", "Tutor for your class", "Classmate selling"), at most 2 rows, collapsible; wired when the marketplace agent sends the response shape.

## Extension-first onboarding, names and market pictures (latest)

- **Onboarding = "Connect Blackboard".** Three big steps (install the browser helper, open Blackboard and click it, press "Scan my Blackboard") with a live status area that polls GET /courses every 2 s and shows class cards ("EN 210 · 14 deadlines") as they arrive. The old calendar-link and "other ways to add classes" flows live in two collapsibles. Classes with `needsSyllabus` show an "Add syllabus" nudge, never an error.
- **Helper hand-off.** The extension's site script posts `{source:'blackboard', type:'sending'|'done'|'failed', count?}` to the same window; AppShell shows a banner for it. The extension panel and popup share one look (`SOS` helpers in extension/common.js).
- **Names.** Sign-up asks for First name and Last name (1-40 characters each; letters, spaces, apostrophes, hyphens, periods) and sends Cognito `name` = "First Last". Greetings use the first name only and never an email or its prefix. When `needsName` is true a one-time "What should we call you?" card appears; Settings has "Your name" (PATCH /me {firstName, lastName}).
- **Market pictures.** Listings carry `images: [{url, alt}]`. Cards show a 4:3 thumbnail (lazy, skeleton shimmer, object-fit cover); the detail sheet shows a larger one; no picture means a category-coloured tile with an icon. Allowed sources: same-origin `/demo/...` paths or https URLs. The 30 demo illustrations are in `web/public/demo/market/` with a `manifest.json` (slug -> alt, category); `design/` keeps no source, the generator is a script, so edit the SVGs directly.
