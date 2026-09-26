#!/usr/bin/env python3
"""
Stage 1 -- Plan the batch (deterministic). Picks what a single post should be about: never a judgement call, always derivable from topics.json + recent history, so the same inputs always produce the same assignment. See RUNBOOK.md's Stage 1 for the full reasoning.

Two format shapes, each with its own rotation axis:

  single_image -- archetype is always "feature-highlight". Rotates through Memora's four core features (agent, flashcards, quizzes, mora), never repeating the immediately previous one, then assigns a layout: the feature's natural layout if it has one (agent->flow-outline, flashcards->flashcard-mockup, mora->chat-mockup), otherwise one of the four generic layouts (stat-hero, quote-callout, comparison, checklist), rotating so the same generic layout doesn't repeat back-to-back.

  slideshow -- pulls from topics.json. Never repeats a topic until every topic in the list has been used once, judged against history's all-time `topic_usage` (Stage 0's second query), not just the 20-row window. Weights the two archetypes topics.json carries toward micro-lessons (ARCHETYPE_WEIGHTS, 3:1 -- micro-lessons are the lead format, technique tips are supporting volume) by picking whichever is furthest below its share of recent history, then round-robins across subjects within that archetype -- the subject whose last use is oldest goes next (never-used subjects first, ties alphabetical), and within it the alphabetically-first unused topic. So consecutive micro-lessons never share a subject while another one still has topics left. Once the whole list is exhausted it recycles in true least-recently-used order rather than erroring.

KNOWN GAP, not yet wired in: "agent-output" is a fourth archetype in the decided vocabulary (micro-lesson | technique | agent-output | feature-highlight) -- a slideshow built from a real generated course's actual data rather than a topics.json entry. It needs live course-generation output as its input, not a rotation pick, so it doesn't fit this script's job and isn't implemented here. Roadmap item, not an oversight.

reel is out of scope for this script entirely -- Reels run on the separate local pipeline (screen-recording), not this cloud batch planner.

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

# Target share of slideshows per archetype: 3 micro-lessons for every technique tip (Armaan's call, 2026-09-26). Micro-lessons are the lead format -- they teach real curriculum content, which demonstrates the product's quality by existing; technique decks are safe but generic, since every study account posts them.
ARCHETYPE_WEIGHTS = {"micro-lesson": 3, "technique": 1}


def load_json(path):
    with open(path) as f:
        return json.load(f)


def assign_single_image(history):
    last_feature = history.get("last_feature")
    last_layout = history.get("last_layout")

    # Rotate features: walk FEATURES starting just after the last one used, so the cycle is stable and reproducible rather than "anything but the last one" (which would let feature N and N+2 be the same forever).
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
    all_topics = topics_doc["topics"]
    subject_of = {t["slug"]: t["subject"] for t in all_topics}
    archetype_counts = history.get("archetype_counts", {})

    # When each topic was last used. topic_usage (Stage 0's all-time query, via history.py --topic-usage) is the real record. used_topics only covers the 20-row window -- kept as a fallback for history files made without --topic-usage, where recency is unknown ("" for everything).
    usage = history.get("topic_usage")
    if usage is not None:
        last_used = {u["topic"]: (u.get("last_used") or "") for u in usage if u.get("topic")}
    else:
        last_used = {slug: "" for slug in history.get("used_topics", [])}

    # Most recent use of each subject, for the round-robin below. Timestamps come from one query, so they compare correctly as strings.
    subject_last_used = {}
    for slug, ts in last_used.items():
        subject = subject_of.get(slug)
        if subject is not None and ts > subject_last_used.get(subject, ""):
            subject_last_used[subject] = ts

    unused = [t for t in all_topics if t["slug"] not in last_used]
    exhausted = not unused
    pool = unused if unused else all_topics

    # Weighted spread across archetype: prefer whichever archetype is furthest below its target share (recent count divided by its weight), ties broken by the fixed order in SLIDESHOW_ARCHETYPES so the outcome never depends on dict ordering. With 3:1 weights this settles into micro, micro, micro, technique.
    def archetype_sort_key(archetype):
        return (archetype_counts.get(archetype, 0) / ARCHETYPE_WEIGHTS[archetype], SLIDESHOW_ARCHETYPES.index(archetype))

    preferred_order = sorted(SLIDESHOW_ARCHETYPES, key=archetype_sort_key)

    chosen = None
    for archetype in preferred_order:
        candidates = [t for t in pool if t.get("archetype") == archetype]
        if not candidates:
            continue
        # Subject round-robin: the subject whose most recent use is oldest (never-used first, ties alphabetical).
        subject = min({t["subject"] for t in candidates}, key=lambda s: (subject_last_used.get(s, ""), s))
        in_subject = [t for t in candidates if t["subject"] == subject]
        # Within it: fresh pool -> every last_used is "", so this is simply the lowest slug; exhausted pool -> the least recently used topic.
        chosen = min(in_subject, key=lambda t: (last_used.get(t["slug"], ""), t["slug"]))
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
