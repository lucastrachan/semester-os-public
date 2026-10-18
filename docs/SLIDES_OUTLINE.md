# Semester OS: slide deck outline (draft v1, Planner)

Status: draft from the handoff rubric; to be adjusted to the organisers' exact instruction text (Luca to provide) and to what is really deployed on demo day. Visual system: `design/deck/` (13 layouts). Diagrams: `docs/architecture.drawio` (5 pages). Demo script: `docs/DEMO_SCRIPT.md`.

Track: HackBama_01, Track 1 (College of Engineering): **Multi-Campus Marketplace**. Prompt in short: "A Craigslist clone won't cut it. Show an idea nobody has tried on campus yet." Weighted most: **innovation**. Rubric called out: multi-tenant, campus-verified, cross-campus, actually works, plus functionality, new-campus deploy, polish; extra awards Best Frontend, Best MVP.

## One-sentence pitch
"Upload your syllabi. Get a dedicated AI agent for every class, a calendar that updates itself, and a marketplace that already knows which books you need."

## The idea nobody has tried (innovation, 30 seconds)
**A need-first marketplace.** Every other campus marketplace asks you to browse. In Semester OS the syllabus tells the app what you need, so the marketplace comes to you: required books matched across your campus and other campuses, tutors for the class you are struggling in, tickets and supplies in the same place. The marketplace is the transaction layer inside a bigger product: a chief-of-staff for college.

## Slides (about 12, 5-6 minutes with the live demo; trim to the allowed time)

| # | Slide | Content | Visual | Rubric item served |
|---|---|---|---|---|
| 1 | Title | Semester OS, tagline, team name + members, track | logo cover (design/logo cover) | polish |
| 2 | The problem | Students juggle syllabi, Blackboard, calendars, textbooks, and hunt a marketplace for each; nothing connects | one cluttered phone/desktop collage | innovation |
| 3 | The idea | Need-first: the syllabus drives everything, including the marketplace | simple flow: syllabus -> agent -> calendar -> books | innovation |
| 4 | Meet the agents | One agent per class (own memory, materials, Blackboard checks, deadlines, books) + a general help agent that hands you to the right class automatically | agent roster layout with the robots | functionality, innovation |
| 5 | Live demo 1 | Sign up with a school email: the campus appears with its colours; drop a syllabus: the class agent builds itself | screen recording / live | multi-tenant, campus-verified, actually works |
| 6 | Live demo 2 | Ask about MIS 430 in the general agent: automatic handoff, re-theme, answers from the class materials; quiz mode | live | functionality, polish |
| 7 | Marketplace | Books matched from your syllabus, cross-campus listings, tutors, tickets, trades; in-app chat; no payments, campus pickup spots | marketplace screenshots | cross-campus, innovation (the track) |
| 8 | Any campus, instantly | Multi-tenant: any .edu email creates its campus (251 verified brand colours, generated otherwise, colour finder, admin review); new-campus deploy needs no code | architecture page 3 (auto-campus) | multi-tenant, new-campus deploy |
| 9 | Trust and security in layers | Campus-verified (email code), separate staff pool with TOTP, prompt-injection defences, tool gating, SSRF-safe fetch, audit log, CSP | security layers page | campus-verified, actually works |
| 10 | Architecture | AWS serverless: CloudFront, API Gateway + JWT, Lambda, DynamoDB, Bedrock multi-model chain, S3, KMS, EventBridge; scalable by design | architecture.drawio overview | actually works (scalable system design) |
| 11 | Real vs demo, honestly | What is live, what is demo data (labelled), what is roadmap (LMS scan/extension, photos, payments) | deployed-vs-planned legend | credibility |
| 12 | What's next + thanks | Roadmap: Canvas/Blackboard connect, extension, listing photos, more countries; team, links (GitHub, demo) | closing layout | polish |

## Story beats to rehearse
1. Open with the student's pain in one sentence, then straight into the product (the organisers said a working demo beats a pretty slide).
2. The 'wow' moment is the handoff: ask a topic question in the general agent and watch it switch to MIS 430 with the class colour and material chips.
3. The multi-tenant proof: show a brand-new school email creating its campus live (use a demo account if no spare .edu inbox).
4. Close the loop with the marketplace: the required book from the syllabus shows up with a match from another campus.

## Facts to verify before they go on a slide (do not state until checked)
- Which ticketing service the campus uses and whether linking is allowed (MyTickets is unverified).
- That each claim marked deployed in `docs/architecture.drawio` is true on demo day.
- Team name and members (Luca to provide), project name, short description, GitHub and demo links (repo is private until Luca makes it public from a fresh, squashed repo).
- Numbers quoted (251 verified school colours, 2,246 schools in the registry, 3 Bedrock model families, test counts) must be re-counted the day of the demo.

## Backup plan
Screen recording of the full demo path (record once everything is deployed); seeded demo data labelled 'Demo listing'; a phone/desktop screenshot set per slide in case Wi-Fi or Bedrock fails.


## Current deck (15 pages, rebuilt 2026-10-17; this supersedes the draft table above)
1 Cover (QR) / 2 Problem / 3 Idea (need-first) / 4 One click: Scan my classes (Blackboard, Canvas supported, courses + due dates + class pages, progress bar, daily re-scan of new items only, never passwords) / 5 Handoff demo (Today agent opens the right class in Study) / 6 Marketplace (For sale | Tickets | Tutoring, pictures, one-row recommendations from your syllabus, simulated in-app checkout and Orders) / 7 Judging criteria / 8 Architecture (AWS serverless, Bedrock multi-model) / 9 Security layers (incl. checkout is simulated) / 10 The team: "Just me and my Claude agents" / 11 Close (try it now, QR; honest notes: demo listings labelled, checkout simulated, helper installed unpacked) / 12 Appendix divider / 13 Agents (+ archive and restore, real names and 12 robot avatars, class chats and messages) / 14 Study hub / 15 Any campus (249 campuses, brand colours). The dedicated "Real vs demo" slide was removed at Luca's request; honest labels live on the marketplace slide and the closing slide.
The helper is installed unpacked today: that note lives on the closing slide, not on the cover.


## Final deck (11 slides, no appendix; supersedes the lists above)
1 Cover / 2 Just me and my Claude agents / 3 Too many tools, and none of them talk / 4 Your syllabus decides what you need / 5 Press Scan. Every class becomes an agent. / 6 An agent for every class / 7 A marketplace that comes to you / 8 Any campus, instantly / 9 Safe by design / 10 Serverless on AWS / 11 Try it now (QR, honest line, likely questions in the notes). Time budget about 4:50.

Update: a criteria slide ("What the judges asked for, shown") was added as slide 11; "Try it now" is slide 12 (12 slides total).
