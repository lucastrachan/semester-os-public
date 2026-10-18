# Submission form text (draft for Luca)

Claims below were checked against the final deploy (verified live 2026-10-17, 4:16 PM). Honest lines to keep: checkout and orders are simulated, the browser helper is installed unpacked (not in the Chrome Web Store), demo data is labelled.

## Form fields (in the organisers' order)

1. **Team name:** luca
2. **Members:** Luca Strachan
3. **Project name:** Semester OS
4. **Track:** Track 01: Multi-Campus Marketplace (Luca to confirm the exact track label on the form)
5. **Short description:** paste the 50-word text below (or the 150-word one if the box allows)
6. **GitHub / demo link:** demo `https://<deployed-host-1>`; GitHub `<GITHUB URL, add after the repo is made public from a fresh squashed repo>`

## 50-word description

Semester OS is a need-first campus marketplace inside a chief-of-staff for college. Upload a syllabus and a dedicated AI agent builds for each class, with deadlines, tutoring and the books you need matched across campuses. Any verified .edu email creates its school's themed campus automatically.

## 150-word description

Most campus marketplaces make you browse. Semester OS flips that: your syllabus tells the app what you need. Upload it and a dedicated AI agent is built for that class, with its own memory, materials, deadlines and calendar feed. One click in Blackboard with our browser helper (prototype) brings in your classes and deadlines. A general agent plans your day and hands you to the right class agent automatically, with Undo. The marketplace sits inside this: required books are matched across your campus and other campuses, with tutors, tickets, supplies and trades in the same place, with an in-app checkout and orders (simulated: no real money moves).

It is multi-tenant by design. A verified .edu email is the campus verification, and the first student at a school creates its themed campus with no manual setup; an admin console with its own MFA-protected login handles review and moderation. It runs on AWS serverless (Cognito, Lambda, DynamoDB, Bedrock with a model fallback chain) with a web app and an Expo app, and security in layers. Listings carry pictures and sign-up uses real first and last names. The Blackboard helper is installed unpacked today (not yet in the Chrome Web Store), checkout is simulated, and demo data is labelled.

## How it was built (optional field)

A solo project by Luca Strachan: he set the product direction and made the decisions, and worked with AI coding agents that wrote and reviewed code in assigned areas. Demo marketplace data (including its illustrations, drawn for the project) is labelled as demo, and the README lists honestly what is live, in progress and planned.
