# Semester OS: slide deck visual system (Designer)

Content is written by Planner; this folder is only the look. `deck.css` + `layouts.html` are the whole system: copy a layout from `layouts.html`, replace the placeholder text. Preview all 13 layouts: serve `design/` (`python -m http.server`) and open `deck/layouts.html`.

## Format
- **1920 x 1080** (16:9), one `<section class="slide">` per slide. Export to PDF with Chrome print (`@page` is 1920x1080, no margins, backgrounds on); the PDF is the safe fallback if the projector is unknown.
- **Dark by default** (matches the product). `class="slide slide--light"` or `deck-light` gives the light version for print or a bright room.
- Keep the **footer** on content slides (product name left, slide number right). No footer on cover and closing.

## Colour
- Background `#0B0D11`, surface `#13161C`, ink `#ECEEF3`, muted `#98A0B0` (all AA, muted 7.4:1).
- **One accent per slide.** Brand indigo is the default (`--accent` for fills with white text; `--accent-strong` for accent text and lines). To tell a story about one class, set `data-theme="c0".."c7"` on that slide, the same eight class colours as the app, with dark text where white would fail (teal, amber, emerald, sky, orange).
- Use class colours together only on the agent roster or a "one tutor per class" slide. Status colours (`--ok`, `--warn`, `--danger`) only for status.
- Never put text on a photo or gradient without a solid surface behind it.

## Type (px at 1920 wide)
| Role | Size | Notes |
|---|---|---|
| Eyebrow | 28 mono, uppercase, +0.1em | accent text; one per slide, above the title |
| Title | 88 heavy (800), tight tracking | max 2 lines; `title--xl` 128 for dividers and cover |
| Subtitle | 44 medium, muted | one sentence |
| Body | 36 (never below 32) | max 3 to 5 lines per block |
| Caption | 26 muted | sources, units |
| Big number | 168 mono heavy | a number plus one short label, up to 3 per slide |
Rules: one idea per slide; titles are claims ("Every school is data, not code"), not labels; no paragraphs; at most 5 bullets (use `ul.points`).

## Layouts (in `layouts.html`)
1 cover · 2 section divider · 3 statement · 4 title + bullets · 5 two columns (before/after) · 6 big numbers · 7 agent roster (Chief of Staff + one tutor per class, robots tinted by class colour) · 8 phone mockup + text · 9 desktop mockup (full width) · 10 architecture page · 11 roadmap · 12 judging-criteria map (table) · 13 closing (links, QR).

## Screenshots and frames
- **Capture** the live app in dark mode with real demo data (no real student names or emails; the only addresses allowed anywhere are the two Luca emails, demo data uses `student@example.edu`). Desktop at 1440 x 900, phone at 390 x 844 (device frame already applied: do not capture the OS status bar of a real phone).
- **Desktop** goes in `.frame-desktop` (window bar with the three dots and a mono title like `mis430.agent`), **phone** in `.frame-phone`. Use `object-position: top`. Never stretch; crop instead.
- Theme the screenshot slide to the class colour shown in it (`data-theme`).
- Add a one-line caption under a screenshot that says what to look at ("Handoff banner: the app re-themes to the class").

## Charts
Horizontal bars with direct labels (`.bars`), one accent, mono numbers right-aligned, no gridlines, no 3D, no legend when labels fit. Max 6 bars. For before/after use two bars in muted vs accent.

## Architecture (draw.io) slides
- Export each draw.io **page** as SVG (preferred) or PNG at 2x, one page per slide, max about 12 nodes per page: split by layer (clients / edge / compute / data / AI) rather than shrinking.
- Place it inside `.diagram` (a light card, so the draw.io colours stay true on the dark slide). Title is the takeaway; the eyebrow says "Architecture · 2 of 3". Under it, the legend as `pill`s that match the draw.io colours.
- Text inside the diagram must be readable at slide size: node labels at least 20px after scaling. If not, zoom into a region on a second slide.

## Speaker notes convention
Put notes inside the slide, hidden on screen and print:
```html
<aside class="notes">
  Time: 0:30 (running 2:15)
  Say: one or two sentences, in plain words.
  Show: what is on screen / what to click.
  Next: the sentence that hands off to the next slide.
</aside>
```
At most 80 words per slide. The demo slide's notes list the exact click path and the fallback ("if Wi-Fi fails, play the backup recording at 00:00"). Total time is written on the first slide's notes.

## Accessibility
Contrast is built in; minimum body 32px; every image has `alt`; do not rely on colour alone (pair status colour with a word or icon); no animation except simple fades (keep Reduce Motion in mind for any web deck).

## Assets
Logo and cover: `../logo/` (`semester-os-cover.svg`, lockups on dark/light, `png/cover-1920x1080.png`). Robots: `../robots/` (inline them to colour them; `<img>` cannot take `currentColor`).
