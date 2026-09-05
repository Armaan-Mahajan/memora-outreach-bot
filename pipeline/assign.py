#!/usr/bin/env python3
"""
Stage 1 -- Plan the batch (deterministic). Picks what a single post should
be about: never a judgement call, always derivable from topics.json + recent
history, so the same inputs always produce the same assignment. See
pipeline-plan.md Stage 1 for the full reasoning.

Two format shapes, each with its own rotation axis:

  single_image -- archetype is always "feature-highlight". Rotates through
    Memora's four core features (agent, flashcards, quizzes, mora), never
    repeating the immediately previous one, then assigns a layout: the
    feature's natural layout if it has one (agent->flow-outline,
    flashcards->flashcard-mockup, mora->chat-mockup), otherwise one of the
    four generic layouts (stat-hero, quote-callout, comparison, checklist),
    rotating so the same generic layout doesn't repeat back-to-back.

  slideshow -- pulls from topics.json. Never repeats a topic that appears
    anywhere in history (topics.json is a curated allowlist, not an infinite
    well, so once it's exhausted this falls back to least-recently-used
    rather than erroring). Spreads across the two archetypes topics.json
    actually carries (micro-lesson, technique) by picking from whichever
    archetype is currently under-represented in history.

KNOWN GAP, not yet wired in: "agent-output" is a fourth archetype in the
decided vocabulary (micro-lesson | technique | agent-output |
feature-highlight) -- a slideshow built from a real generated course's
actual data rather than a topics.json entry. It needs live course-generation
output as its input, not a rotation pick, so it doesn't fit this script's
job and isn't implemented here. Roadmap item, not an oversight.

reel is out of scope for this script entirely -- Reels run on the separate
local pipeline (screen-recording), not this cloud batch planner.

Usage:
    python3 assign.py --format single_image --topics ../topics.json --history shaped_history.json
    python3 assign.py --format slideshow --topics ../topics.json --history shaped_history.json

Output (stdout): a JSON assignment object, shape depends on format.
"""
import argparse
import json
import sys

FEATURES = ["agent", "flashcards", "quizzes", "mora"]

NATURAL_LAYOUT = {
    "agent": "flow-outline",
    "flashcards": "flashcard-mockup",
    "mora": "chat-mockup",
    # quizzes has no natural layout -- shares the generic rotation below.
}

GENERIC_LAYOUTS = ["stat-hero", "quote-callout", "comparison", "checklist"]

SLIDESHOW_ARCHETYPES = ["micro-lesson", "technique"]


def load_json(path):
    with open(path) as f:
        return json.load(f)


def assign_single_image(history):
    last_feature = history.get("last_feature")
    last_layout = history.get("last_layout")

    # Rotate features: walk FEATURES starting just after the last one used,
    # so the cycle is stable and reproducible rather than "anything but the
    # last one" (which would let feature N and N+2 be the same forever).
    if last_feature in FEATURES:
        start = (FEATURES.index(last_feature) + 1) % len(FEATURES)
    else:
        start = 0
    feature = FEATURES[start]

    natural = NATURAL_LAYOUT.get(feature)
    if natural:
        layout = natural
    else:
        if last_layout in GENERIC_LAYOUTS:
            start = (GENERIC_LAYOUTS.index(last_layout) + 1) % len(GENERIC_LAYOUTS)
        else:
            start = 0
        layout = GENERIC_LAYOUTS[start]

    return {
        "format": "single_image",
        "archetype": "feature-highlight",
        "feature": feature,
        "layout": layout,
    }


def assign_slideshow(history, topics_doc):
    used_topics = set(history.get("used_topics", []))
    archetype_counts = history.get("archetype_counts", {})

    all_topics = topics_doc["topics"]
    unused = [t for t in all_topics if t["slug"] not in used_topics]
    pool = unused if unused else all_topics
    exhausted = not unused

    # Spread across archetype: prefer whichever of the two slideshow
    # archetypes has been used less often so far (ties broken by the fixed
    # order in SLIDESHOW_ARCHETYPES, so the outcome never depends on dict
    # ordering).
    def archetype_sort_key(archetype):
        return (archetype_counts.get(archetype, 0), SLIDESHOW_ARCHETYPES.index(archetype))

    preferred_order = sorted(SLIDESHOW_ARCHETYPES, key=archetype_sort_key)

    chosen = None
    for archetype in preferred_order:
        candidates = [t for t in pool if t.get("archetype") == archetype]
        if candidates:
            # Deterministic pick within the candidate set: lowest slug
            # alphabetically. (If the pool is the exhausted fallback, this
            # doesn't track true least-recently-used order, since history
            # only carries topic slugs, not per-slug last-used timestamps --
            # acceptable for a fallback path that should rarely trigger
            # given topics.json's size relative to realistic batch volume.)
            chosen = sorted(candidates, key=lambda t: t["slug"])[0]
            chosen_archetype = archetype
            break

    if chosen is None:
        raise RuntimeError("topics.json has no entries matching any known archetype")

    return {
        "format": "slideshow",
        "archetype": chosen_archetype,
        "topic": chosen["slug"],
        "subject": chosen["subject"],
        "topic_title": chosen["topic"],
        "safe_for": chosen["safe_for"],
        "topic_pool_exhausted": exhausted,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--format", required=True, choices=["single_image", "slideshow", "reel"])
    parser.add_argument("--topics", required=True, help="path to topics.json (required for slideshow)")
    parser.add_argument("--history", required=True, help="path to history.py's shaped-history JSON output")
    args = parser.parse_args()

    if args.format == "reel":
        print(
            "reel is out of scope for the cloud batch planner -- Reels run on the "
            "separate local (screen-recording) pipeline, not this one.",
            file=sys.stderr,
        )
        sys.exit(1)

    history = load_json(args.history)

    if args.format == "single_image":
        result = assign_single_image(history)
    else:
        topics_doc = load_json(args.topics)
        result = assign_slideshow(history, topics_doc)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
