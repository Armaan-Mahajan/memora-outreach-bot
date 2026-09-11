# Memora — product overview

Reference doc for the Memora HQ Claude Project. Reflects the codebase and legal docs as of 2026-08-28. Update this when something here goes stale rather than letting conversations quietly drift from it.

## What it is

Memora is an AI-powered study platform for high school students. It started as an MYP (IB Middle Years Programme) Personal Project and grew from there. Live at **the-memora.com**; still described on its own landing page as "Public release soon!" — it's in beta, not a public launch.

## Where it stands (August 2026)

- Growth so far has been entirely organic — no paid acquisition, no social presence yet.
- Built and run by Armaan, solo.
- Main app repo: `Armaan-Mahajan/memora-web`. A separate private growth dashboard repo (`Armaan-Mahajan/memora-growth`) tracks search performance and sign-ups monthly at growth.the-memora.com (password-gated, not public).

## Who it's for

High schoolers, roughly ages 13-18, across a genuinely global mix of curricula — the product's curriculum picker lists IB MYP, IB DP, AP, AQA, CBSE, CXC, Edexcel, French Baccalauréat, German Abitur, ICSE, NSW HSC, Pearson Cambridge IGCSE, VCE, and WJEC. This is not a US-only or English-curriculum-only product. Terms of Service set **13 as the minimum age** to hold an account.

## Core features

- **Flashcards** — AI-generated cards that adapt to what the student already knows.
- **Quizzes** — MCQ, short-answer/open-ended, true/false; graded instantly, including AI grading of open-ended responses.
- **Mora** — Memora's AI tutor. A chat interface with a canvas: diagramming (Mermaid, including AI diagram repair), math rendering (KaTeX), file upload, and a "flow" of chat nodes rather than a flat thread.
- **Memora Agent** — the flagship, most differentiated feature. A student uploads a syllabus and the Agent generates a full structured interactive course: modules and subtopics, with flashcards and quizzes embedded directly into each node. Marketed on the site as "Available only on Memora." This is the feature to lead with in anything competitive or differentiating.
- **Syllabus / curriculum organization** — subjects and topics structured against the student's selected curriculum board.
- **Dashboard** — a home view across a student's courses, flashcard decks, quizzes, and flows.

## Business model

Credit-based freemium, billed via **Gumroad** (not Stripe) — Memora never sees payment card details, only what Gumroad reports.

| Tier | Price | AI credits | Agent uses |
|---|---|---|---|
| Free | $0 | 1,500/week | 8/month |
| Plus | $4/mo ($3.30/mo yearly) | 4,000/week | 40/month |
| Pro | $10/mo ($8.30/mo yearly) | 10,000/week | 100/month |

Credits reset weekly; Agent uses reset monthly. Subscriptions can also be activated via redeemed Gumroad license keys, tracked server-side with expiration handling.

## Tech stack

Next.js 16 / React 19 app, Supabase (auth, Postgres, storage), OpenAI API for generation, Tailwind + Radix UI + Framer Motion for the frontend, deployed on Vercel. The growth dashboard is a separate, smaller Next.js app fed by a monthly GitHub Actions job pulling Google Search Console + Supabase data.

## Legal / trust notes relevant to outreach

- Minimum account age is 13 (stated in Terms of Service).
- Privacy Policy is explicit that Memora never stores payment info (Gumroad-only) and that the growth dashboard publishes aggregate counts only — no user identifiers, no study content, no per-feature usage.
- No social media accounts are linked anywhere in the current codebase or site footer — Memora has no existing public social presence to build on or stay consistent with. Dedicated social-media logo assets already exist though (`social-media-logo.png` / `social-media-logo-inverted.png` in the app's public assets), suggesting this was anticipated but not yet acted on.
