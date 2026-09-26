#!/usr/bin/env python3
"""
Stage 0/1 support: shape raw outreach_drafts rows into the specific facts assign.py (rotation) and Stage 2 (content-writing) actually need.

This script does NOT talk to Supabase itself -- MCP tool access (the execute_sql call that fetches these rows) is a property of the orchestrating Claude session, not of a plain Python subprocess, the same reason publish.py emits SQL for Claude to run rather than running it. The orchestrator's job is:

    1. select id, format, feature, topic, archetype, layout, headline, caption, status, created_at from outreach_drafts order by created_at desc limit 20;
    2. select topic, max(created_at) as last_used from outreach_drafts where topic is not null group by topic;
    3. save each result as JSON (a list of row objects)
    4. python3 pipeline/history.py <query-1-file.json> --topic-usage <query-2-file.json>

Query 2 exists because query 1's 20-row window only remembers the last handful of slideshows -- on its own, Stage 1 would start re-picking topics after about eight decks no matter how long topics.json is.

Usage:
    python3 history.py <raw_history.json> [--topic-usage <topic_usage.json>]

Output (stdout): a JSON object --
{
  "last_feature": str | null,  # feature on the single most recent row
  "last_layout": str | null,  # layout on the single most recent row
  "used_topics": [str, ...],  # every distinct topic slug in history
  "archetype_counts": {archetype: int, ...},
  "recent_by_feature": {feature: [{"headline", "caption", "created_at"}, ...]}  # up to 15 most recent per feature, for Stage 2's "don't repeat this angle" context
  "recent_all": [{"headline", "caption", "created_at"}, ...]  # up to 40 most recent overall, across both formats -- what Stage 7's checks.py hashes against
  "topic_usage": [{"topic", "last_used"}, ...]  # only with --topic-usage: EVERY slideshow topic ever queued, most recent first -- what assign.py rotates against
}
"""
import argparse
import json
from collections import defaultdict

MAX_RECENT_PER_FEATURE = 15
MAX_RECENT_ALL = 40


def shape(rows, topic_usage=None):
    rows_by_recency = sorted(rows, key=lambda r: r.get("created_at") or "", reverse=True)

    last_feature = None
    last_layout = None
    for row in rows_by_recency:
        if row.get("format") == "single_image":
            last_feature = row.get("feature")
            last_layout = row.get("layout")
            break

    used_topics = sorted({row["topic"] for row in rows if row.get("topic")})

    archetype_counts = defaultdict(int)
    for row in rows:
        if row.get("archetype"):
            archetype_counts[row["archetype"]] += 1

    recent_by_feature = defaultdict(list)
    for row in rows_by_recency:
        feature = row.get("feature")
        if not feature or len(recent_by_feature[feature]) >= MAX_RECENT_PER_FEATURE:
            continue
        recent_by_feature[feature].append(
            {
                "headline": row.get("headline"),
                "caption": row.get("caption"),
                "created_at": row.get("created_at"),
            }
        )

    recent_all = [
        {
            "headline": row.get("headline"),
            "caption": row.get("caption"),
            "created_at": row.get("created_at"),
        }
        for row in rows_by_recency[:MAX_RECENT_ALL]
    ]

    result = {
        "last_feature": last_feature,
        "last_layout": last_layout,
        "used_topics": used_topics,
        "archetype_counts": dict(archetype_counts),
        "recent_by_feature": dict(recent_by_feature),
        "recent_all": recent_all,
    }

    if topic_usage is not None:
        # Timestamps all come from the same query, so they share one text format and compare correctly as strings.
        result["topic_usage"] = sorted(
            ({"topic": r["topic"], "last_used": r.get("last_used") or ""} for r in topic_usage if r.get("topic")),
            key=lambda r: r["last_used"],
            reverse=True,
        )

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("raw_history", help="query 1's result (the 20 most recent rows), saved as JSON")
    parser.add_argument("--topic-usage", help="query 2's result (every topic ever used, with its last use), saved as JSON")
    args = parser.parse_args()

    with open(args.raw_history) as f:
        raw_rows = json.load(f)

    topic_usage = None
    if args.topic_usage:
        with open(args.topic_usage) as f:
            topic_usage = json.load(f)

    print(json.dumps(shape(raw_rows, topic_usage), indent=2))
