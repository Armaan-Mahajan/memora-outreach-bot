# Memora Instagram outreach bot — working brief

Current focus of the Memora HQ project. This is a living document — update it as decisions get made instead of leaving them as open questions forever.

## Objective

Build an AI system that runs Memora's Instagram presence with as little manual work as possible: it researches and drafts posts, writes captions, directs visuals, picks hashtags, and proposes a posting cadence — to a quality bar where a human's only remaining job is a yes/no before something goes live, not a rewrite.

## Starting point

- Memora has **no existing social media presence**. No account is linked anywhere in the codebase or site footer. This is a from-zero build: account creation, handle, bio, and initial aesthetic all need deciding before any posting cadence starts.
- Social-specific logo assets already exist in the app repo (see brand-voice.md) — a head start on visual identity, not a finished one.
- Platform choice for this first phase: **Instagram**. Other platforms (TikTok, X) were deliberately deferred, not ruled out — revisit once Instagram is running.

## Autonomy model

Nearly fully autonomous by design, with a single human approval gate before publishing:

- The bot is expected to do the actual creative work — hook, caption, visual direction, hashtags — well enough that approval is a stamp, not an edit pass. If a human keeps having to rewrite drafts substantially, that's a signal to raise the bot's bar, not to accept more manual editing as normal.
- The approval step exists specifically because the audience skews to minors and the brand is young and easy to damage — not because the content quality is expected to need heavy correction.
- The approval mechanism itself (review queue, email, a small dashboard, something else) is **not yet decided** — see open questions.

## Audience & tone constraints

Same user base as the product: 13-18 year-olds across a global mix of curricula (see memora-overview.md), which shapes both content and compliance:

- Content should feel like a sharp peer talking to another student under deadline pressure — not SaaS marketing copy, and not forced slang either.
- Because the audience is minor-heavy, content needs to hold up under Instagram/Meta's stricter policies for platforms reaching under-18 users: no manufactured urgency or countdown pressure, no dark patterns, no claims that can't be backed up, nothing that turns a data-collection ask (email capture, DM-to-unlock) into engagement bait. A useful gut check: would a parent or teacher watching over a student's shoulder be fine with this post.
- Lead with real differentiation — Memora Agent (syllabus → full interactive course) is the "available only on Memora" feature and the strongest hook. Flashcards, quizzes, and Mora are the everyday, lower-commitment hooks (exam-cramming moments, quick wins).
- Stay honest about scale. Memora is pre-launch; content should read as an authentic, early, building-in-public story rather than imply an established brand.

## A possible technical pattern (precedent already exists)

Memora already runs one Claude-driven automation: a monthly growth report (in `memora-growth`, see its RUNBOOK.md if deeper detail is ever needed) that pulls Search Console + Supabase data via MCP connectors, builds a PDF, and emails it — with strict rules baked in (single fixed recipient, one PII-bearing file that never leaves the machine, "stop and report" the instant something looks wrong rather than improvising). The outreach bot should inherit that same discipline: capable of posting nothing rather than posting something wrong, off-brand, or non-compliant.

A parallel shape for the outreach bot: a scheduled task drafts a batch of posts → writes them to a review queue → notifies the human approver → on approval, publishes via the Instagram Graph API (or a scheduler product with an API, e.g. Buffer/Later/Publer) rather than a raw browser-automation posting step. Nothing here is committed yet — it's a starting shape to argue with, not a spec.

## Suggested timing

Two different clocks, worth separating.

**Build.** There's no big block to wait for, and there doesn't need to be. The real school-year break (after 10th grade) already happened before DP1 started on 15th July — from here it's term time, and Q1 summatives plus a first SAT attempt (22nd August) just wrapped up. The actual resource is weekly, not seasonal: weekdays during term are committed to studying, weekends are free, so the build happens in a standing Saturday/Sunday rhythm across the whole DP1 year rather than a single sprint. Slower per week than a dedicated block, but it can start immediately — this weekend — instead of waiting for December. Worth using the current lull (right after SAT + Q1) to kick off the slowest-moving piece first: Meta Business/Instagram API verification runs on its own external review clock, so starting it now costs nothing and keeps it from becoming a late bottleneck.

**Release.** The single best top-of-funnel window for a study app is back-to-school (roughly early August to mid-September), and it has essentially closed for this cycle by the time a quality system could ship. The next strong anchor is January: New Year's-resolution energy, the start of second semester for most of Memora's curricula, and close enough to the May exam season (IB, AP, GCSE/A-Level) to build momentum ahead of it. Suggested sequence: post quietly from November/December to season the account and build a content backlog — a brand-new account's early posts typically get less reach than one with some history — then push publicly in January. A second wave in March-April, closer to exam crunch, gives a natural reason for higher-urgency content once an audience already exists.

One wrinkle: NSW HSC and VCE (both Southern Hemisphere) run on the opposite calendar — their back-to-school is also January, which conveniently overlaps with the plan above, and their exam season is October-November, a good window for Southern-Hemisphere-specific content while the Northern Hemisphere majority is mid-term and lower-urgency.

If this cycle is missed, the next real back-to-school anchor is August 2027.

## Open questions to resolve before/while building

- **Account setup**: what handle, what bio, does it link to a Facebook Page/Meta Business account (required for Graph API access)?
- **Approval mechanism**: how does the human actually see and approve a draft before it posts?
- **Posting infrastructure**: direct Graph API integration vs. a third-party scheduler with API access?
- **Visual production**: AI-generated images/video, template-based graphics built from the existing brand assets, or a mix?
- **Cadence and volume**: how many posts/week is sustainable and worth measuring?
- **Attribution**: memora-growth currently tracks only organic search and sign-ups — there's no UTM or social-referral tracking yet, so social-driven sign-ups aren't measurable until that's built. Decide whether that's a prerequisite or a fast-follow.
- **Paid vs. organic**: this brief assumes organic content; paid ads bring additional Meta policy obligations for youth-reaching ads if that's ever in scope.
