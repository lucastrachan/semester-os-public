# Semester OS pitch deck

13 slides, 1920x1080, dark theme, built on `design/deck/deck.css` (copied to `deck/deck.css`). Self-contained: no network needed.

## Present
- Open `deck/index.html` in Chrome or Edge, press **F** for fullscreen.
- Keys: Right / Space / PageDown next, Left / PageUp / Backspace back, Home / End. Clicking the right or left half of the screen also moves.
- Speaker notes with timings (5 min pitch + 3 min demo): open `deck/index.html?notes=1` on the second screen. Slide 5, 6 and 7 are the demo slides; the notes hold the click path and fallbacks.
- Jump to a slide: `index.html#7`.

## Re-export the PDF
Edit `deck/tools/template.html` (the source), then run `python -I deck/tools/build.py` (inlines the robots and fills the counts), then:

```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="C:\Users\lucas\semesteros\deck\semester-os-deck.pdf" "file:///C:/Users/lucas/semesteros/deck/index.html"
```
The PDF has one page per slide (13). Check the page count after exporting.

## Slides
1 Title, 2 Problem, 3 Idea (need-first), 4 Agents, 5 Demo 1 (Study hub mockup), 6 Demo 2 (handoff mockup), 7 Marketplace mockup, 8 Any campus, 9 Security + admin mockup, 10 Architecture (SVG), 11 Rubric map, 12 Real vs demo, 13 Close.

## Claims to re-check on demo day
- **Counts** (verified at build time, 2026-10-17): 251 verified school colours (`backend/data/school_colors.json`), 2,246 schools (`backend/data/us_schools.json`), 510 backend tests (`python -I -m unittest discover -s backend/tests` printed OK). Re-run and edit slide 11 (`{{TESTS}}` in build.py) if they change.
- **Live vs coded** (slides 10 and 12, from `docs/ARCHITECTURE.md`, checked 13:2x): anything marked "deploy pending" (any-.edu campus creation, colour worker, Blackboard sync, EventBridge, KMS, listing chat, memory/materials, admin colour review). Move items to Live only after verifying; update the legend date on slide 10.
- **Model chain** (slide 10): GLM-5, gpt-oss-120b, Mistral Large 3, Claude Sonnet 4.6, Nova Lite fast (from `DECISIONS.md` and `infra/stack.py`).
- **Demo URL** on slide 13: https://<deployed-host-1> still serves the student site.
- **Mockups** (slides 5, 6, 7, 9) are HTML recreations with demo data, labelled "Mockup". The "Using: Lecture 4.pdf" chips need materials retrieval, which was not deployed at 13:2x; remove or relabel if it is still off.
- "Ticket resale capped at face value by default", "no payments", "Expo app" (never run on a device) are from the specs; confirm before speaking to them.
- Team line: "Team: luca (solo)" on slide 1.
- Real screenshots can replace any mockup: put an image in `.frame-desktop` instead of `.app`.

## Blackboard-import copy flag
Slide 1, 2, 3 and 5 copy that says "Connect Blackboard" is behind a flag. When the backend import is live run: python -I deck/tools/build.py --import-live (or set import_live to true in deck/tools/flags.json), then re-export the PDF. The "Checked <date time>" stamp on slides 10 and 12 is generated at build time; the live/pending split on slides 10 and 12 comes from the Planner status note (not verified with aws calls).

Update: the import flag stays OFF. Blackboard calendar export cannot identify the class per deadline, so slides say classes come from syllabi and the calendar adds deadlines; the browser extension is shown as roadmap (prototype).

Icons: the architecture slide uses the official AWS Architecture Icons (aws.amazon.com/architecture/icons) and Simple Icons (CC0, simple-icons 13.15.0), copied to deck/assets/icons and inlined by deck/tools/arch.py at build time. Mistral, Z.ai GLM and Amazon Nova are text badges (no icon available). AWS icons are used to depict AWS services only.

## Structure (updated)
Core pitch (4 minutes, timed notes): slides 1-10 = Title+QR, Problem, Idea, Live demo (handoff), Marketplace, Criteria, Architecture, Security, Real vs roadmap, Closing+QR. Slide 11 = Appendix divider; 12-14 = Appendix (agents, Study hub, any campus) for Q&A. The PDF is in the same order (14 pages). Slide order is set by deck/tools/restructure.py (already applied; edit template.html directly from now on).

## Pivot refresh (Designer, 2026-10-17)
Copy now says Blackboard connect is the browser helper (one click, "prototype": load unpacked) instead of the calendar link. Slide 5 marketplace mockup shows listing pictures (illustrations on demo listings, assets/market/). Slide 12 lists listing pictures, one-click import and real first and last names as "coded, deploy pending"; student photo uploads, store release of the helper, Canvas and payments stay roadmap. PDF rebuilt: 14 pages. Move items to Live only after verifying.
