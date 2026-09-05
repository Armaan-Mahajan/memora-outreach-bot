#!/usr/bin/env python3
"""
Stage 0/1 support: shape raw outreach_drafts rows into the specific facts
assign.py (rotation) and Stage 2 (content-writing) actually need.

This script does NOT talk to Supabase itself -- MCP tool access (the
execute_sql call that fetches these rows) is a property of the orchestrating
Claude session, not of a plain Python subprocess, the same reason publish.py
below emits SQL for Claude to run rather than running it. The orchestrator's
job is:

    1. select id, format, feature, topic, archetype, layout, headline,
       caption, status, created_at from outreach_drafts
       order by created_at desc limit 20;
    2. save that result as JSON (a list of row objects)
    3. python3 pipeline/history.py <that-file.json>

Usage:
    python3 history.py <raw_history.json>

Output (stdout): a JSON object --
{
  "last_feature": str | null,        # feature on the single most recent row
  "last_layout": str | null,         # layout on the single most recent row
  "used_topics": [str, ...],         # every distinct topic slug in history
  "archetype_counts": {archetype: int, ...},
  "recent_by_feature": {feature: [{"headline", "caption", "created_at"}, ...]}
                                      # up to 15 most recent per feature, for
                                      # Stage 2's "don't repeat this angle"
                                      # context
  "recent_all": [{"headline", "caption", "created_at"}, ...]
                                      # up to 40 most recent overall, across
                                      # both formats -- what Stage 7's
                                      # checks.py hashes against
}
"""
import json
import sys
from collections import defaultdict

MAX_RECENT_PER_FEATURE = 15
MAX_RECENT_ALL = 40


def shape(rows):
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

    return {
        "last_feature": last_feature,
        "last_layout": last_layout,
        "used_topics": used_topics,
        "archetype_counts": dict(archetype_counts),
        "recent_by_feature": dict(recent_by_feature),
        "recent_all": recent_all,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 history.py <raw_history.json>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        raw_rows = json.load(f)

    print(json.dumps(shape(raw_rows), indent=2))
