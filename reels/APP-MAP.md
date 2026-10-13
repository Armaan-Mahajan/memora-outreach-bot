# APP-MAP — what the demo app shows, and how to drive it

The demo build (memora-web `demo-recording-mode-v2`) served at `http://localhost:3000` during recording. The account is the seeded demo
student, already signed in when recording starts. Everything here was checked against the build; if a selector below stops matching,
the recording step times out after 20 s and the reel is dropped — it never clicks something else.

Targets in `capture.json` are `{"css": "…"}`, `{"role": "button", "name": "<regex>"}` or `{"text": "…"}` (first match). Prefer the
`data-demo` hooks and link `href`s below; they don't change with copy edits.

## Pages

### Landing page `/` (signed in)
Long animated page, top to bottom:
1. Hero: **"Your notes in. A daily study plan out."** A week strip with day radios: `[role=radiogroup] [role=radio]` (Mon…; one says
   "Economics exam Thu", another "Physics exam Mon"). Hovering/clicking a day animates the bar chart and plan. Good hover material.
2. **"Memora Autopilot"** and its three steps: "Add your exams", "Do today's session", "See what's secure".
3. A flip card `[data-flipped]` (click flips it, a 3D animation).
4. **"What else?"**: Flashcards, Quizzes, Mora, Memora Agent.
5. **"Start with one exam."** final panel.
Links: "Go to Dashboard" → `/dashboard` · "Open Autopilot" / "Plan my exams" → `/autopilot` · "Try Agent" → `/agent` ·
"See plans and credits" → `/pricing`. Scroll with `{"do":"scroll","dy":…,"ms":…}` (smooth, on the recording clock).

### Dashboard `/dashboard`
"Your Dashboard". "Today: about 15 min" with a **Start** button (→ an Autopilot session). A "Dismiss update banner" button.
Lists the student's decks, quizzes, courses ("Photosynthesis in Depth") and Mora chats. "Exam Autopilot" link
(`{"role":"link","name":"^Exam Autopilot"}`) → `/autopilot`; section headers "Flashcards" / "Quizzes" / "Courses" / "Chats" link to their pages.
The course card does **not** navigate when clicked (use `/agent` instead); its card tilts on hover, so hover it only briefly.

### Autopilot `/autopilot`
Exactly **two** seeded exams, side by side (nothing below them — never frame "the next exam"): **"Physics test: forces and motion"** (in 5 days) and **"Biology exam: photosynthesis"** (in 12 days), each with
readiness counts, topic rows, and "Make" / "Mark covered" buttons. "Study time" with more/less buttons per day.
Material links: `a[href*='/flashcards/viewer/']` (first = "Forces and Motion" deck), `a[href*='/quizzes/viewer/']`
(first = "Forces and Motion: Explain It"), `/agent/viewer/…` ("Photosynthesis in Depth"). They sit below the fold; a click
scrolls them into view automatically.

### Autopilot session `/autopilot/session/<id>` (from Dashboard "Start")
`[data-demo=session-player]` with `data-demo-kind` = `flashcard` or `mcq`.
- flashcard: `[data-demo=session-show-answer]`, then `[data-demo=session-mark-yes]` / `-partly` / `-no`
- mcq: `[data-demo=session-option-0]`…, `[data-demo=session-check]`, `[data-demo=session-continue]`
- after the first answer `[data-demo=session-stop]` ("Stop here for today") → `[data-demo=session-summary]` with a "Back to Autopilot" link.

### Adaptive deck `/flashcards/viewer/<id>` (from the Autopilot material links)
Per card: click `[class*='flipCardInner']` (flip), then `{"role":"button","name":"^Correct"}` or `"^Incorrect"`, then next
`button:has(svg.lucide-chevron-right)` (not after the last card). When every card is marked, `button:has(svg.lucide-check)` is
enabled (`{"do":"wait","for":{"enabled":{"css":"button:has(svg.lucide-check)"}}}`); clicking it shows the results: "Review Complete" (wait on that text), the
percentage, "N out of 10 points", Correct / With Hints / Incorrect tiles, a Performance Summary, and an "Adaptive deck · Results saved" box with **"Rebuild deck now"**, "Study again", "Continue to Dashboard".
"Rebuild deck now" → "Rebuilding your deck…" → about 2–3 s later the summary (cards retired / reworded / added, with Retired,
Reworded and New sections) and "Undo rebuild", "Study the new version", "Continue to Dashboard". Wait on `{"text":"Undo rebuild"}`.
The Forces and Motion deck has 10 cards.

### Quiz viewer `/quizzes/viewer/<id>`
Multiple-choice viewer; it also ends in the adaptive rebuild panel. Not yet verified step by step: if a reel uses it, keep the
steps to what's on screen and expect the recording to fail fast if a guess is wrong.

### Generators (the existing reel formats)
- Agent `/agent`: textarea → Generate → outline (`/agent/…` outline, then course build) → course viewer. Content from `content/course.json`
  (7-9 nodes; the default demo course has 8, with authored content for nodes 1-3 and 7). The outline shows titles and subnodes
  only (no word estimates). The course viewer's sidebar lists every node; the existing scripts open nodes 1-3.
  The "Click to redirect" toast doesn't navigate on camera within the 4 s `expect_url` window (the runner then loads the link
  directly), so put `"cut": true` on that click (as `capture/reels/agent-course.json` does): everything from the click until the
  viewer has loaded is edited out. `"cut": true` works on any click that navigates.
- Flashcards `/flashcards/ai-gen`: textarea → "Generate … Flashcards" → `/flashcards/ai-gen/save` → study. Pack from `content/flashcards.json`.
- Quiz `/quizzes/ai-gen`: textarea → Generate → quiz. Pack from `content/quiz.json`.
The typed prompt must contain one of the pack's `match` fragments (validate_content.py checks this).
The four `capture/reels/*.json` scripts show working step sequences for these; read them before writing a new one.

## What's seeded vs. what a plan can change
- A plan can bring its own flashcard pack, MCQ pack, or Agent course (`content/`), which only matters for the generator pages.
- Autopilot exams, the adaptive deck, the rebuild result, dashboard items and the lander are **seeded** and fixed: Forces and
  Motion (physics) and Photosynthesis (biology). Autopilot / adaptive / overview reels talk about what's actually on screen,
  not the night's topic from topics.json.

## Timing notes
- `speed: fast` (x 1.5–12) compresses real waiting and repetitive actions; the edit shows a "Sped up" chip for exactly that stretch.
  Always close it with `speed: normal` before anything the viewer should read.
- `wait` with `"cut": true` drops dead time (blank page loads) from the clip entirely.
- Every step with `"mark": "name"` drops an event the plan's timeline and voice lines can anchor to; clicks drop `click:<as>`.
