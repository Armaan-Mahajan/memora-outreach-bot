# Slideshow (carousel) post templates

Content-first carousels: plain `#171717` ground, Geist, one accent used
sparingly, no diagrams. The value is the explanation, not the decoration —
if a slide's design is doing the heavy lifting, the content underneath
isn't strong enough.

## Files

- `template.html` — page shell and all slide-type styles. `{{SLIDES}}` is
  replaced with the generated slide markup.
- `content-example.json` — a full worked deck (Le Chatelier's principle).
  This is the shape the bot fills in per post.
- `render_slideshow.py` — reads a content JSON, builds every slide into one
  page (one KaTeX init and one font load, so slides can't drift visually
  from each other), then screenshots each slide element to
  `output/<slug>/01.jpg`, `02.jpg`, … at 1080×1350.
- `assets/` — self-contained, because the render environment has no network
  access: Geist variable font, the app's `social-media-logo-inverted.png`,
  and KaTeX (css, js, `mhchem` for chemistry, `auto-render`, plus its woff2
  fonts).

## Run it

```
python3 render_slideshow.py content-example.json
```

## Instagram's actual limits (checked against Meta's own docs)

- **JPEG only.** The Content Publishing API does not accept PNG, so the
  renderer emits JPEG at quality 95. Don't "improve" this back to PNG.
- **8 MB per image.** Slides land around 80–150 KB, so there's no real risk,
  but the renderer asserts it rather than assuming.
- **Aspect ratio 4:5 to 1.91:1.** 1080×1350 is exactly 4:5 — the tallest
  ratio Instagram accepts, so it's the most feed real estate available.
  Anything taller is rejected outright, so this is a floor, not a
  preference.
- **Width 320–1440px.** 1080 sits comfortably inside; wider gets scaled down.
- **sRGB.** Other colour spaces get converted automatically.
- **10 items max per carousel**, and every slide is cropped to match the
  *first* one's aspect ratio — so the cover must be 4:5 or the whole deck
  gets cropped to whatever it is. All slide types render at the same size,
  which keeps this safe by construction.

## Deck shape

Cover, 3–6 content slides, closer. Let the content decide the length — a
technique post lands in 3, a concept explanation usually needs 5–6. Don't
pick the number first and pad or rush to hit it.

## Slide types

- **cover** — `eyebrow`, `title`, `sub`. The only slide that appears in
  feed, so it gets the visual weight: a subtle gradient ground plus a
  bottom-anchored, large-type composition. Keep the gradient restrained — a
  wash, not a blob; the first attempt was roughly 2.5x this strength and
  read badly. One cover template, reused, so all variation between posts
  lives in the words.
- **body** — `heading`, optional `math` (array of display blocks), `text`.
  Heading pinned to the top, the rest centred below it, so headings land in
  the same place on every slide and swiping feels steady.
- **list** — `heading` plus `items`. Same ground, gradient dot markers.
- **closer** — `heading`, `text`, `cta`. Same subtle gradient ground as the
  cover, logo given room. The CTA says "Link in bio" because Instagram
  carousels can't hold clickable links.

## Math

Everything remotely mathematical or chemical gets typeset, even where
Unicode would do — formality is the point. Inline math goes in any text
field as `$...$`; display blocks go in the slide's `math` array. `mhchem`
is loaded, so `\ce{N2 + 3H2 <=> 2NH3}` works, as do `\Delta H`, units like
`\mathrm{kJ\,mol^{-1}}`, and `K_c` expressions.

Don't overdo it — prose stays prose. Math is for the actual chemistry and
equations, not for decorating ordinary sentences.

**No diagrams or graphs.** A wrong diagram is confidently wrong and slips
through review because it looks like a diagram, and drawing one stacks two
independent failure points (reason about the relationship, then encode it
in coordinates). Typed math has one, and a wrong equation is visible at a
glance. If a topic can't be taught without a diagram, pick another topic.

`render_slideshow.py` raises rather than rendering a slide containing a
KaTeX error, so a broken expression fails the run instead of shipping.

## Text fitting

Text fields support `**bold**` for emphasis. Content length varies per
slide, so after layout the renderer shrinks any slide whose content
overflows its frame, measured from the rendered box rather than guessed
from character count. It scales the whole content block (including KaTeX)
down in small steps to a floor, so a long slide gets tighter rather than
clipped.

## Progress bar

Mirrors the flashcard viewer's `ProgressBar.tsx` — muted rounded track,
`primary → secondary` gradient fill — with the numeric label dropped, since
Instagram already draws position dots under a carousel. Absent on the
cover (nothing read yet), full on the closer.

## Self-checks the renderer runs

The generator is an LLM writing into templates it can't see, so the render
step has to catch its own mistakes rather than trusting that the markup did
what was intended. Every run asserts, and raises rather than shipping:

- **KaTeX errors** — a broken expression fails the run instead of rendering
  a slide with red error text on it.
- **Element collisions** — the visible text elements are checked against the
  corner logo and progress bar. This is the failure that actually happened
  during design (cover text landing on the logo, heading touching the bar),
  and text-fitting alone doesn't catch it, because nothing overflows. Note
  it compares the *leaf* text elements, not the `.content` container, whose
  box extends into the padding and would false-positive on every slide.
- **File size** against Instagram's 8 MB per-image limit.

Worth extending as new failure modes turn up — cheap deterministic checks
beat a vision pass for anything that can be expressed as a measurement, and
a run that fails loudly is always better than a draft that quietly looks
broken in the queue.

## Guardrails

- No user-count or scale claims, no manufactured urgency, no fabricated
  testimonials or stats.
- Micro-lesson decks teach real curriculum content under Memora's name, so
  accuracy matters more here than anywhere else in the account. Stick to
  stable, well-established topics, avoid anything where curricula
  meaningfully disagree, and verify every factual claim before rendering.
- The closer makes the scale argument (a syllabus becomes a whole course),
  not a quality claim the deck itself has already demonstrated.
