#!/usr/bin/env python3
"""
Local dev/test harness for Stage 1's rotation logic (assign.py) across a
simulated multi-post batch -- NOT the real orchestrator.

Why this isn't "the pipeline" end to end: Stage 2 (write the content),
Stage 3 (subagent fact-check), and Stage 5 (vision check) all need an
actual Claude session in the loop, and Stage 8's uploads need Claude's MCP
tool access (see publish.py's docstring) -- none of that is something a
plain Python script can do standalone. The real run sequence lives in
RUNBOOK.md and is walked by the Claude session driving the scheduled task,
calling assign.py / checks.py / publish.py by name at the right points.

What this script IS for: sanity-checking that Stage 1's rotation behaves
the way pipeline-plan.md says it should over a run of N posts, without
needing Supabase or a live Claude call. It starts from real history (or
none, for a from-scratch dry run) and simulates each pick feeding into the
next one's "recent post", the same way real posts landing in outreach_drafts
would.

Usage:
    python3 run.py --format single_image --count 5
    python3 run.py --format slideshow --count 8 --history shaped_history.json
    python3 run.py --format single_image --count 3 --topics ../topics.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assign import assign_single_image, assign_slideshow  # noqa: E402

EMPTY_HISTORY = {
    "last_feature": None,
    "last_layout": None,
    "used_topics": [],
    "archetype_counts": {},
    "recent_by_feature": {},
    "recent_all": [],
}


def simulate(fmt, count, history, topics_doc):
    history = dict(history)  # local mutable copy; don't touch the caller's
    results = []

    for _ in range(count):
        if fmt == "single_image":
            pick = assign_single_image(history)
            history["last_feature"] = pick["feature"]
            history["last_layout"] = pick["layout"]
        else:
            pick = assign_slideshow(history, topics_doc)
            history.setdefault("used_topics", [])
            if pick["topic"] not in history["used_topics"]:
                history["used_topics"].append(pick["topic"])
            counts = dict(history.get("archetype_counts", {}))
            counts[pick["archetype"]] = counts.get(pick["archetype"], 0) + 1
            history["archetype_counts"] = counts

        results.append(pick)

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--format", required=True, choices=["single_image", "slideshow"])
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--history", help="shaped-history JSON from history.py; omit for a from-scratch dry run")
    parser.add_argument(
        "--topics",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "topics.json"),
        help="path to topics.json (only needed for --format slideshow)",
    )
    args = parser.parse_args()

    if args.history:
        with open(args.history) as f:
            history = json.load(f)
    else:
        history = EMPTY_HISTORY

    topics_doc = None
    if args.format == "slideshow":
        with open(args.topics) as f:
            topics_doc = json.load(f)

    results = simulate(args.format, args.count, history, topics_doc)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
