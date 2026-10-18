# Judge guide: try Semester OS in 2 minutes

Live site: https://<deployed-host-1> (works on a phone or laptop).

You need a **.edu email** you can open (a verification code is sent to it). Verification emails use Cognito's default sender, so check spam if the code is slow. If you have no .edu address, ask the team for a demo account.

## The path

1. **Pick your school.** On the home page, search your school by name or email domain (like `ua.edu`). Any US college works: the first verified student at a school creates its themed campus, so the whole app re-colours to your school.
2. **Sign up.** Tap *Get started*. Enter your first name, last name, school email and a password (8+ characters, at least one number). Enter the 6-digit code from your email.
3. **Add a class.** On the onboarding screen, open **Other ways to add classes** and choose **Try with a sample syllabus** (a clearly fictional course), then add it. A class agent builds itself in about a minute: deadlines, grading policy, study blocks, required books. You can also upload your own syllabus PDF or paste its text.
4. **Meet your agents.** Open **Study**. Tap the class to chat with its agent and ask, for example, "What is due this month?" or "Make me a study plan for the next exam."
5. **Ask the general agent.** Tap **Ask** (top bar) and ask a question about a class, like "What should I read for my sample class this week?" The general agent hands you to that class agent with a banner and an **Undo**, and the app re-themes in the class colour.
6. **Browse the marketplace.** Open **Market**. Cards show demo listings with pictures (labelled *Demo listing*), always with their campus. Open one for details, try the filters, and see the "for you" suggestions that come from your classes. There are no payments in the app, and ticket resale is capped at face value by default.
7. **Calendar.** Open **Calendar** to see deadlines on your calendar; the subscribe link puts them in your phone's calendar.

## What is real and what is demo

- Marketplace listings and their illustrations are **demo data**, labelled as such. The sample syllabus is fictional.
- **Live today:** sign-up and school pages, syllabus processing, class agents and chat, calendar link.
- **Live (final deploy verified 4:16 PM, everything below works today):** master agent handoff, marketplace v2, listing chat, class group chats, auto-campus, the Blackboard import route, listing pictures, first and last names, robot avatars, the three-section marketplace and the simulated checkout and Orders.
- **Installed unpacked, not in the store:** the Blackboard browser helper (`extension/`, Chrome "Load unpacked", see `docs/EXTENSION.md`). It only works with a student's own Blackboard login, so it is shown in the deck rather than in this path.
- Simulated: in-app checkout and orders ("Semester OS Pay (demo)": no real money moves, no card fields).
- Not built: Canvas, real payments, student photo uploads, other countries.
