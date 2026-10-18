# Semester OS: Mobile design (Designer) — native app, Expo / React Native

Companion to `DESIGN.md`. **Same brand, different body.** The app shares colours, the class palette, tone and the "calm OS" idea with the website, but uses each platform's own components, navigation and motion. Nothing here is a port of the web CSS.

Platform: Luca hasn't said iPhone or Android. Design for **both with `Platform.select`**, iOS first in the examples. Anything marked (iOS) / (Android) differs; unmarked is shared.

## 1. Shared tokens (import, don't retype)

Source of truth: `web/src/styles/color.ts` (pure TypeScript, no DOM, no React). Mobile copies or aliases it as `shared/tokens.ts`. It exports:

| Export | Use |
|---|---|
| `CLASS_PALETTE` | The 8 class colours in order. Assign `course.color` from it. |
| `deriveTheme(hex, 'light'\|'dark')` | `{ accent, accentInk, accentTint, accentStrong }`, AA-checked. Use for the campus colour (any `#RRGGBB`). |
| `classThemes(scheme)` | All 8 derived themes, indexed like the palette. |
| `NEUTRAL_TOKENS[scheme]` | `bg surface surface2 ink muted border borderStrong`. |
| `contrast(a, b)`, `isHex`, `classIndexFromHex` | Helpers. |

Mapping to RN: build one `Theme` object `{ ...NEUTRAL_TOKENS[scheme], ...deriveTheme(hex, scheme) }` and provide it through context. `useColorScheme()` picks the scheme. Never hard-code a hex in a component.

Same rules as web: **fills** use `accent` with `accentInk` on top; **accent-coloured text, icons and strokes** use `accentStrong`; soft backgrounds use `accentTint`. Raw `accent` as a thin line can be under 3:1 (amber).

## 2. Per-class theming on mobile

Entering a class (or a master handoff) swaps the context theme to that class's derived colours.
- **Animate** colour change over ~350ms with Reanimated `interpolateColor` on the few big surfaces (header, tab-bar tint, primary button, chat bubbles). Everything else can switch instantly; the eye follows the big shapes. No layout changes.
- **Reduce Motion** (`AccessibilityInfo.isReduceMotionEnabled`): switch instantly, no slide.
- **System chrome follows the class:** `StatusBar` style from contrast of the header colour, (Android) navigation-bar colour, iOS tab/large-title tint. Use `accentStrong` for tints on a neutral background and `accent` + `accentInk` where the header itself is filled.
- Leaving the class restores the campus theme.
- Everywhere a class appears (agent card, calendar row, deadline chip, book match, activity row) wrap it in a small `<ThemeProvider value={classTheme(i)}>` so it uses that class's colour regardless of the screen theme (same idea as `data-theme` on web).

## 3. Navigation and structure (native idiom, not the web sidebar)

- **Bottom tabs, 5 max:** Today, Agents, Calendar, Books, More (Tutoring, Settings, Admin entry live under More). Expo Router `(tabs)` with native stack inside each.
- **iOS:** large collapsing titles, swipe-back, translucent tab bar (blur), SF Symbols via `expo-symbols`. **Android:** Material 3 style top app bar, system back, solid tab bar with an indicator pill, Material icons.
- The class agent page is a **pushed stack screen** (not a tab) with its own scrollable top tabs: Chat, Materials, Deadlines, Blackboard, Books, Memory, Syllabus (see section 12). Whole screen themed to the class.
- Master chat on Today is a **bottom sheet** (3 snap points: peek input, half, full) with a composer pinned above the keyboard. No docked web-style chat bar.
- Respect safe areas everywhere; use `KeyboardAvoidingView` (iOS `padding`, Android `height`).

## 4. Component list

| Component | Native behaviour |
|---|---|
| `AgentCard` | Rounded 16 card with a 4pt class-colour top edge, name, role, status pill, "knows" counts. Not a faux desktop window: the "window" motif stays web-only. Tap opens the class. Building state shows a vertical `PipelineStepper`. |
| `SystemStatus` | A grouped list ("Agents running") in iOS inset-grouped / Material list style: LED dot, name, last run time. This is the mobile version of the web status panel. |
| `StatusPill` | Text + dot for Ready / Building / Syncing / Error, tinted from status colours. Never colour alone. |
| `BriefingCard` | Greeting, classes today with prep chips, due soon, priorities (numbered), warnings. One vertical scroll. |
| `Timeline` | Hour-labelled column; class blocks use tint fill + 4pt left bar in the class colour; study blocks dashed; deadlines solid fill with `accentInk`. Current-time line in danger colour. |
| `ChatBubble` + `Composer` | User bubble `accent`/`accentInk`; agent bubble `surface` with border. Typing indicator (3 dots), no token streaming (API is non-streaming). Tool-action chips under agent bubbles. |
| `HandoffBanner` | Slides down from the top of the chat: "Switching you to your MIS 405 tutor — reason" plus **Undo**. Auto-themes after 1.2s unless undone. Announce via `accessibilityLiveRegion` / `AccessibilityInfo.announceForAccessibility`. |
| `QuizCard` | One question per screen, large tap rows (min 48pt), correct/wrong colours plus icon, explanation slides in, score ring at the end. |
| `FlashDeck` | Full-width card; **tap to flip** (Reanimated rotateY), **swipe right = known, left = review** with a card fly-off. Reduce Motion: cross-fade. |
| `CalendarAgenda` | Default is an agenda list grouped by day, class-coloured rows. Month view is a compact dot grid that filters the agenda. Swipe a deadline to mark done; long-press for edit/move. "Add to my calendar" button uses `expo-calendar`. |
| `BookMatchRow` | Title, price in mono, condition, campus tag (your campus first), "Demo listing" tag. |
| `Skeleton` | Shimmering placeholders matching the final layout (Reanimated); static under Reduce Motion. |
| `EmptyState` | Icon tile + title + one-line help + a single primary button. |
| `Toast` | Non-blocking banner at the top (iOS) / snackbar at the bottom (Android); errors say what happened and what to try. |
| `BootScreen` | Optional: while the first `/me` loads, a dark screen with 3–4 mono lines ("mounting campus theme", "waking chief-of-staff") then a quick fade. It's the web boot idea, kept short (under 1.2s, skipped if data is cached). |

## 5. Type, space, shape

- **Type:** system font (San Francisco / Roboto) so it respects the OS and **Dynamic Type / font scale**. Use mono (`Menlo` on iOS, `monospace` on Android) only for small system labels, prices and times. Never lock `allowFontScaling`; test at 1.3x.
- **Scale (pt):** caption 12, footnote 13, body 16, callout 17, title 22, large title 30 (iOS collapses it). Weights 400/600/700.
- **Space:** 4pt grid; screen padding 16; card padding 16; list row min height 48.
- **Shape:** card radius 16, control radius 12, pills fully round. Hairline borders (`StyleSheet.hairlineWidth`) in `border`. Shadows only on iOS floating things (sheets, toasts); Android uses elevation/Material surfaces.
- **Touch targets:** >= 44pt iOS / 48dp Android.

## 6. Motion and haptics

Haptics (`expo-haptics`), **only at meaningful moments**: 
- Quiz right answer: success notification. Wrong: warning notification (soft). 
- Flashcard swipe commit: light impact. 
- Handoff themed into a class: one light impact when the colour lands. 
- Mark deadline done: success; delete/destructive confirm: warning. 
- Tab change / ordinary taps: none (the OS already does it).

Motion: springs for sheets and card flips (damping ~20), 200–350ms for colour. Everything honours Reduce Motion. No decorative looping animation except the build-pipeline spinner and the typing dots.

## 7. Accessibility

- Contrast comes from `deriveTheme`; do not tint text arbitrarily.
- Every control has `accessibilityRole` + label; status pills expose text ("Building, step 3 of 5"). Calendar events read "MIS 405 Quiz 3, due Friday".
- Screen readers: handoff and toast announcements; quiz results announced.
- Focus order follows reading order; sheets trap focus; swipe gestures always have a button alternative (mark done, known/review buttons).
- Dark mode via `useColorScheme()`; test every class colour in both.

## 8. What stays web-only

Command palette (Ctrl/Cmd+K), split-pane study mode, hover states, drag-and-drop upload, the "window" title-bar motif, subscribe-URL panel as the primary calendar action (the app writes to the phone calendar instead, but still shows the URL under Settings).

## 9. Handoff to the Mobile agent

1. Copy `web/src/styles/color.ts` to `shared/tokens.ts` (or alias it) and build `ThemeProvider` from section 1.
2. Build in this order: theme + tabs shell, auth, Agents (cards + stepper), Today (briefing + timeline + chat sheet), class study mode (themed), calendar agenda, books.
3. Ask Designer in the internal planning notes for specifics (icons, empty-state copy, exact spacing) rather than guessing. I'll review screenshots from `npx expo start` if you post them or give me a web preview (`npx expo start --web`).

Open question for Luca: **iPhone or Android?** I'll fine-tune the iOS/Material details for whichever is the demo device.

## 10. Auto-campus (school screen and signup header)

- **Colour:** copy `autoThemeFromName`, `CAMPUS_PALETTE` and `normalizeSchoolName` from `web/src/styles/color.ts` into `shared/tokens.ts` with the rest (still pure TypeScript). Use `deriveTheme(hex, scheme)` for the theme, as for any campus.
- **Signup screen:** title "Sign up for your school" under a large title; as the email domain stops changing (debounce ~400ms) resolve it. While resolving show a skeleton pill in the title; when resolved, animate the screen's accent (header tint, primary button, input focus ring) to the school colour over ~350ms (instant under Reduce Motion) and change the title to "Sign up for {school}". Unknown: keep neutral, show an inline "We don't know this school yet" with a "Request it" link. Announce the result with `AccessibilityInfo.announceForAccessibility`. Keep the title area a fixed height so the form doesn't move. Light haptic when a school resolves.
- **School screen (first tab after sign-in):** large-title school name on a tinted hero card (4pt accent edge, `accentTint` to surface gradient), domain chips, an "Auto-created" pill when it applies, and a one-line note "Placeholder colour, not the school's official brand". Below, an inset-grouped list "What's set up" (timezone, LMS, tutoring, pickup spots, marketplace); unset rows are muted with a trailing chevron and the action ("Suggest a pickup spot"). Then numbered "Next steps" rows with a check when done.
- **Empty states:** one muted line each, never fake data; demo items keep the "Demo" tag.

## 11. Review of the built app (Designer, read-only, from the code; nothing was run on a device)

Scope: `mobile/app`, `mobile/src`, `shared/`. Ranked by impact. "File" paths are under `mobile/` unless noted. **Not verified:** everything visual and behavioural (no device or simulator run), real keyboard and sheet behaviour, Dynamic Type at large sizes, TalkBack/VoiceOver output, Android predictive back.

### What is right (keep)
- `shared/tokens.ts` is a faithful copy of `web/src/styles/color.ts`: same palette, `deriveTheme`, `NEUTRAL_TOKENS`, `CAMPUS_PALETTE`, `normalizeSchoolName`, `autoThemeFromName`. Only cosmetic difference: the accent-strip regex uses literal combining characters instead of `̀-ͯ` (same behaviour). Add a golden test so they cannot drift: `autoThemeFromName("The University of Alabama") === "#C2410C"`, `"Auburn University" === "#9E1B32"`, `"Georgia Institute of Technology" === "#0E7490"`, `"MIT" === "#A16207"`.
- Theme architecture (`ThemeProvider`, `ClassTheme` wrapper, class colour set on focus and cleared on leave) matches section 2. Dark mode follows `useColorScheme`. Robots are used with `color={t.accent}` and the right state variants.
- Native idiom is real: per-platform stack options (iOS large titles, Material app bar), haptics in 13 places, `announceForAccessibility` on handoff and school resolve, swipe-to-complete and 44pt checkbox on Calendar, bottom sheet for the master chat with interactive keyboard handling, `useReducedMotion` in skeletons, `maxFontSizeMultiplier` caps, safe areas and `KeyboardAvoidingView` on auth.
- Status colours pass AA: danger 6.0:1 / success 5.2:1 on the light bg, 8.5:1 / 10.4:1 on dark.

### High
1. **Removed web page still referenced.** `app/(auth)/sign-up.tsx:87,93-94` and `app/(tabs)/today/index.tsx:61` offer "Request your school" and link to `${webUrl}/request`, which no longer exists (campus requests were removed). `src/auth/cognito.ts:58` (`isUnknownCampus`) assumes the old message. *Fix:* unknown domain means ".edu only": show "Semester OS supports US colleges (.edu email addresses) for now." with no button; replace the Today `noCampus` text the same way.
2. **Placeholder colour is never mentioned.** `src/resolve.ts` ignores `colorStatus`; the sign-up hint and the school screen (`app/(tabs)/today/school.tsx`) should show the gentle note when it is `placeholder`/`needs_review` (parse `colorStatus` from resolve and tenant, fall back to `autoCreated`).
3. **Class chat feels like a web embed, not a chat screen.** `src/components/Tutor.tsx` renders the conversation in a `maxHeight: 420` nested `ScrollView` inside the page `ScrollView`, so the composer scrolls away and nested scrolling fights the page; `app/(tabs)/agents/[id].tsx` also uses `keyboardVerticalOffset={96}` (a guess; large titles vary). *Fix:* make Chat its own full-height surface (FlatList with the composer pinned above the keyboard and safe area, `useHeaderHeight()` for the offset), or push chat as a dedicated stack screen.
4. **Chat history is lost** when you leave the class (state is local). Persist per class (AsyncStorage now, server history when `HISTORY_API.md` lands), same as web's sessionStorage.
5. **Touch targets under 44pt:** `[id].tsx` segmented items (`minHeight: 40`) and the Tutor mode tabs (`Tutor.tsx`, `minHeight: 40`). Raise to 44.
6. **Class Deadlines tab cannot mark done** (`[id].tsx` `Deadlines`), while the Calendar tab can. Reuse the Calendar row (swipe + checkbox + "Estimated" pill); show undated items in a "Needs a date" group; show weight.

### Medium
7. **Theme change is instant.** Section 2 asks for a ~350ms colour interpolation on header, tab bar tint, primary button and chat bubbles (`interpolateColor`, skipped under Reduce Motion). Today `ThemeProvider` just swaps. The handoff "colour lands" moment (`MasterSheet.enterClass`) is the place it matters most.
8. **Agents tab still shows placeholder system agents** (`app/(tabs)/agents/index.tsx` `SYSTEM_AGENTS`, all "Coming soon", even Chief of Staff although the master chat works). Superseded by the internal planning notes: remove them, add the general agent entry (see the new Study spec).
9. **Agents load failure has no retry:** a muted footnote "Pull down to retry". Use `ErrorNote` plus a "Try again" button.
10. **Briefing polish** (`src/components/BriefingCard.tsx`): due dates show raw ISO ("2026-10-19"); show "Tomorrow"/weekday with an overdue/soon badge like web. Warnings are 13pt footnotes; use body size, they are the most important text. Classes today could use the hour-labelled timeline from section 4.
11. **Raw error text:** `[id].tsx` and Calendar show `e.message` (can be "Network request failed"); map to friendly strings like `tutorError`/`masterError`.
12. **Pipeline rows are icon-only for state** (`[id].tsx` building card): add `accessibilityLabel="Read syllabus, done"` per row and a "Paste text instead" action on ERROR.
13. **Master sheet:** peek snap `16%` can clip on small phones or large font sizes (use a fixed minimum in points); the rate-limit cooldown is a hard-coded 15s instead of `Retry-After`; the sheet needs an explicit close/collapse control for non-gesture users; verify it sits above the tab bar on Android.
14. **Auth Android keyboard:** `AuthScreen` uses `behavior="height"` on Android; with `adjustResize` that can double-adjust. Prefer `behavior` undefined on Android and verify on a device.

### Low
15. Hard-coded hex: `app/(tabs)/calendar/index.tsx:47` (use `t.success` ink via `deriveTheme`/`accentInk`), `src/calendar/phone.ts:36` (device calendar colour fixed indigo; use the campus accent).
16. `T kind="label"` marks every eyebrow as a header; fine for screen sections, noisy if used inside cards.
17. Missing vs web: delete class, study-hours (read-only on web), tutoring resources, Blackboard feed UI. Not blockers.
18. iOS vs Android: the custom segmented control could be the native `SegmentedControl` on iOS (and Material segmented buttons on Android); not required.

## 12. Agents v2 on the phone (Study tab, class agent, handoff)

Tabs: **Today · Study · Calendar · Books · Settings** (rename the Agents tab to Study). Remove the Calendar Sync / Planner / Books agent rows entirely.
- **Study tab:** a "Chief of Staff" row at the top (robot, one line, tap opens the Today sheet), then one card per class: tutor robot tinted with `ClassTheme`, code and title, status pill, three stat chips (deadlines, materials, new from Blackboard), "Checked Blackboard 12m ago" or "Blackboard not connected", build stepper text while building. Tap opens the class agent. Pull to refresh; poll every 2s while building; failure shows `ErrorNote` plus a Try again button.
- **Class agent screen:** large title is the course code; iOS segmented control for Chat's mode (Explain, Quiz, Cards, Cram), scrollable top tabs for the seven sections. The whole app re-themes to the class colour with the 350ms colour interpolation (instant under Reduce Motion).
  - **Chat** is a full-height surface: FlatList of bubbles, composer pinned above the keyboard and the safe area (`useHeaderHeight()` for the offset), the agent's opening message as the first bubble with its name, quick-action chips as a horizontal scroller above the composer (tap sends the prompt, or switches to Quiz/Cards), action chips with Undo, typing indicator, light haptic on send and on a correct quiz answer. History persists per class (AsyncStorage now, server history later).
  - **Materials:** document picker (PDF, text), per-file progress row, summary, swipe to delete; copyright reminder: only your own course materials.
  - **Deadlines:** the Calendar row component (checkbox, swipe to complete, "Estimated" pill, "from Blackboard" tag); undated items in "Needs a date".
  - **Blackboard:** status card with "Check now" (cooldown), "Is this {class}?" one-tap rows, "From Blackboard" list with a New pill; not connected links to Settings. Say plainly: dates and events only.
  - **Books:** syllabus books with Required/Optional and a button to the Books tab.
  - **Memory:** list of notes; swipe to delete, tap to edit, "Clear all memory" with confirmation.
- **Handoff from the Today sheet:** banner at the top of the sheet in the target class colour, class robot, "Switching you to your MIS 430 agent", the reason, material chips ("Using: Lecture 4.pdf"), Undo. Light haptic when the colour lands (after ~1.2s), announce with `announceForAccessibility`, then "Open MIS 430 agent" pushes the class screen.
- **Blackboard link in Settings:** a card with a secure text field (secureTextEntry) for the secret calendar link, masked display after saving, Check now, Disconnect.
- **Unassigned inbox:** an inset-grouped list with class chips per item (likeliest first), reachable from Calendar.

## 13. LMS onboarding on the phone

Same flow as the web (DESIGN.md "LMS onboarding"), as a full-screen stack after sign-up: **(1) "Which learning system does your school use?"** three large selectable rows (preselect from `tenant.lms.type`, "Your school" pill), the plain note that Semester OS never sees your school password; **(2) Connect** per choice:
- **Blackboard:** numbered steps with the confirmed menu path (Calendar > the gear icon, top right of the Calendar page > the three dots in the panel that opens > Share calendar > copy link). A phone shortcut: the Share sheet / clipboard button "Paste link" reading the clipboard only when the student taps it (never automatically). `secureTextEntry` field, big **Scan for classes** button, stepper rows (Checking your link, Reading your calendar, Matching deadlines) with `AccessibilityInfo.announceForAccessibility` on each stage and a light haptic when it finishes. The link is masked after saving.
- **Canvas:** the token guide, and while the backend is not live the button and field are disabled with "Canvas scanning is coming soon"; **do not ask for or send a token** until the contract exists (keep a single `CANVAS_SCAN_LIVE`-style switch).
- **Something else:** the document picker for syllabus PDFs, or pasted text.
**(3) Your classes:** class cards appear as they are built (tutor robot tinted with `ClassTheme`, status pill, stepper), the Unassigned inbox rows with class chips, "Add a class from its syllabus", then "Go to Study". Safe areas, keyboard avoidance (`useHeaderHeight`), Dynamic Type, 44pt targets, and Reduce Motion rules as in sections 2 to 7.

## 14. Marketplace v2, nav merge and campus badge on the phone

- **Tabs:** Today, Study, Marketplace, Calendar, Settings (rename Books to Marketplace; remove any Tutoring entry). Study gets a **Campus help** section (tenant tutoring resources as inset-grouped rows, https links open in the system browser; dashed empty state; "Find a peer tutor" jumps to Marketplace > Tutoring).
- **Campus badge:** in the header of Today and Study (large-title area on iOS, app bar on Android): a pill with a monogram tile in the campus colour (`deriveTheme(primary).accentInk` for the letters), short name, full name below it on wide screens; tap opens the school screen. No logos for now.
- **Marketplace screen:** large title "Marketplace"; a search field (native search bar on iOS); horizontal category chips; a "For you" horizontal carousel (required books with the cheapest match); a filter button opening a bottom sheet (type: For sale/Trade/Free/Wanted/Services, max price, condition, campus vs all open campuses). Cards stack in one column and mirror the web card types: basic, trade (Offering <-> Wants), ticket (dashed edge, event, date, section, price with face value, transfer method, safety banner, optional external https link), tutor (robot, rate, subjects, mode, "Request a session"). Message and Report in the card's overflow; the message composer opens as a bottom sheet; Report uses an action sheet. Sticky "Create listing" floating button; the form is a pushed screen with the same per-category fields as the web, `keyboardShouldPersistTaps="handled"`, date-time picker for events, light haptic on success.
- **My listings** and **Messages** as segmented sections at the top; unread count badge on the segment; polling intervals as in MESSAGES_API.md.
- Ticket safety copy and the "capped at face value" warning are mandatory on every ticket card and the ticket form.

**Copy and priority update (Luca):** Blackboard path wording is *Calendar, gear icon (Calendar Settings, top right), then the three dots (More options) in the panel, then Share calendar*. Navigation names in copy: Today, Study, Marketplace, Calendar, Settings; the campus badge opens the school screen. The primary onboarding and empty-state action is **"Connect Blackboard to import your classes"**; **"Upload a syllabus instead"** is a clearly secondary link/section.

**Correction (Luca): no automatic class import from Blackboard.** The calendar feed gives deadlines only. Onboarding: step 1 connect the calendar (gear icon > three dots > Share calendar), step 2 **add each class with its syllabus** (document picker, paste, or the sample), step 3 **sort deadlines**. The Unassigned inbox is the hero: deadlines grouped by title pattern ("Reading Journal x12"), one card per group with the next due date and a row of class chips; tapping a chip assigns the whole group (light haptic, then a toast "Added 12 deadlines"); "Not deadlines" dismisses. Empty states: Study "Add a class with its syllabus" primary, "Connect your Blackboard calendar" secondary; Today "Get started". Marketplace home gets a collapsible "Recommended for you" area (max 2 rows of small cards with a one-line reason) once the API shape arrives.

## Latest mobile notes
- Market cards: picture on top at 4:3 (tile at 16:7 when there is none), then badge, title, price, one meta line. Single column on phones.
- Onboarding "Connect Blackboard": big numbered steps, copyable helper folder path, 44 px buttons; class cards stack one per row.
- Sign-up: First name, Last name, school email, password, one field per row with visible labels and inline errors.
