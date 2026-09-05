# Single-image feature-highlight cards

Code-rendered templates for the lowest-production-difficulty post format:
one static image, one hook. No Canva, no design tool — HTML/CSS rendered to
JPEG by headless Chromium, so the bot can produce these unattended.

## Why multiple layouts

Slideshows can get away with one reusable template because the slide
content does the heavy lifting — see `../slideshow/README.md`. A
single-image card *is* the whole post, so one fixed template used for
every card would make the feed monotonous fast, which defeats the format's
job (stopping a scroll). The fix isn't giving the content-writing step
freedom to invent arbitrary layouts, though — that would break every
reliability mechanism this project depends on (a collision/overflow check
needs to know what it's checking against, a vision pass is only cheap to
judge against a small number of known shapes) and hands the generator a
second job, visual design, on top of the one it's already not great at.

Instead, variety lives one level up: a small, hand-built library of
**layouts**, each independently verified once, and the *choice* of which
layout to use becomes a deterministic rotation decision (same rotation
layer that already picks feature/topic/archetype in the pipeline plan) —
not something either the LLM or a human picks per post. The content-writing
step's job stays exactly as scoped as it's always been: fill in a known
schema.

## The seven layouts

| Layout | Composition | Natural fit |
| --- | --- | --- |
| `flow-outline` | Syllabus → Agent → Course flow diagram + a generated-outline preview panel | Agent (the one layout still tied to specific hardcoded flow-diagram content) |
| `stat-hero` | Oversized numeral + headline, vertically centered | Generic "why Memora" claims |
| `quote-callout` | One big typographic statement, no panel at all | A sharp one-liner / hook post |
| `comparison` | Two-column "old way / with Memora" split | Generic persuasion, pain-point-led |
| `chat-mockup` | Stylized Mora conversation, user + Mora bubbles | Mora |
| `flashcard-mockup` | Stylized flashcard stack with a front-side question | Flashcards |
| `checklist` | Vertical benefit checklist, hero-sized (distinct from `flow-outline`'s compact outline panel) | Generic tips / "why students switch" posts |

Each is a fully self-contained `template.html` — no shared includes, so no
build step — but all seven share identical CSS for the brand shell (header
with logo/wordmark/badge, footer with CTA + "Link in bio", background
glow, Geist font). Only the `.hero` zone between them differs per layout.
Copy-paste the shell verbatim into any future layout to keep that
consistent.

## Files

- `layouts/<name>/template.html` — the layout. Brand chrome is fixed;
  copy is `{{PLACEHOLDER}}` tokens filled in per post. Every layout tags
  its primary variable-length text `id="headline"`, whatever its semantic
  role (headline, quote, comparison title, ...), so the renderer's
  auto-fit can hook into all of them the same way.
- `layouts/<name>/content-example.json` — the content for that layout's
  example render. This is the shape the bot fills in per post. Copy is
  pulled from `claude-knowledge/brand-voice.md` and
  `claude-knowledge/memora-overview.md` (real site copy, real feature
  descriptions), not invented — e.g. "adapt to what you already know" is
  Flashcards' actual description, "graded instantly" is Quizzes'.
- `render.py` — reads a layout name + content JSON, substitutes into that
  layout's `template.html`, and screenshots to `output/<layout>/<slug>.jpg`
  at 1080×1350 (Instagram's 4:5 feed size). `python3 render.py --all`
  renders every layout's own example in one go.
- `assets/` — shared across all layouts: `social-media-logo-inverted.png`
  and the Geist variable-weight font, self-contained since the render
  environment has no network access.
- `output/<layout>/` — rendered JPEGs land here, one subfolder per layout.

## Run it

```
python3 render.py <layout-name> <content-file.json>
python3 render.py --all
```

Requires `pip install playwright` and a Chromium install (`playwright
install chromium`), or point `PLAYWRIGHT_BROWSERS_PATH` at one that
already exists.

## Adding a new layout

1. `mkdir layouts/<name>`, write `template.html` (copy the shared shell
   CSS from any existing layout verbatim, then build a `.hero` for the new
   composition) and a `content-example.json`.
2. If the content has any array field (a list of items, messages, etc.),
   register a small builder function for it in `render.py`'s
   `LIST_FIELDS`/`LAYOUTS` config — everything else (plain strings)
   substitutes automatically.
3. Add an entry to `LAYOUTS` in `render.py` with `fit_max_lines` and
   `fit_min_px` tuned to that layout's base headline size.
4. Render, look at it, adjust. Don't ship a layout that hasn't been looked
   at, same rule as every other format in this project.

## Self-checks the renderer runs

- **Headline auto-fit** — shrinks `#headline`'s font-size until it wraps
  within its layout's line budget, measured from the rendered box height
  rather than assumed from character count. A fixed size that looks right
  for one headline can overflow to an orphaned extra line for another.
- **Hero overflow** — after the headline fit, the whole `.hero` zone is
  checked against its allotted space (between header and footer) and
  shrunk via zoom if anything still overflows — icons, panels, and chat
  bubbles included, not just text. If it's still overflowing at the zoom
  floor, the render raises rather than shipping a card with content
  spilling off the canvas.
- **File size** against Instagram's 8 MB per-image limit.

No dedicated element-collision check, unlike the slideshow renderer: there's
no absolutely-positioned chrome floating over content here (no corner logo
or progress bar overlay) — everything is in normal flex flow, so overflow
is the failure mode that actually applies, not overlap.

## Icon convention (for this and future layouts)

AI-generation features get a sparkle mark; Mora, since it's the chatbot
rather than a generator, gets a chat bubble instead. Reuse these exact
paths so the icon language stays consistent across posts and layouts:

Sparkle (Agent, Flashcards, Quizzes — anything that *generates* content):
```html
<svg viewBox="0 0 24 24" fill="#ffffff" stroke="none">
  <path d="M10.5 3 L12.7 10.3 L20 12.5 L12.7 14.7 L10.5 22 L8.3 14.7 L1 12.5 L8.3 10.3 Z"/>
  <path d="M19 2.5 L19.9 4.9 L22.3 5.8 L19.9 6.7 L19 9.1 L18.1 6.7 L15.7 5.8 L18.1 4.9 Z" opacity="0.85"/>
</svg>
```

Chat bubble (Mora only — used as the avatar in `chat-mockup`):
```html
<svg viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
</svg>
```

## Guardrails baked into every layout

- No user-count or scale claims anywhere in the layout — Memora is
  pre-launch at ~86 registered users, and the site itself says "Public
  release soon."
- No countdown/urgency elements, no fabricated testimonials or stats.
- Feature claims are grounded in what the product actually does (see
  `claude-knowledge/memora-overview.md`) — e.g. don't claim Quizzes
  "adapt" the way Flashcards explicitly do; Quizzes' real claim is instant
  grading, including AI grading of open-ended answers.
- Tone shifts a notch more peer-to-peer than the site's own SaaS-style
  copy, per `outreach-bot-brief.md` — "a sharp peer talking to another
  student under deadline pressure," not marketing copy.
