#!/usr/bin/env python3
"""
Stage 7 -- Duplicate backstop (deterministic). The last line of defense
against posting the same content twice, after Stage 1's rotation (never
assigns the same feature/topic back-to-back or repeats a topic) and Stage
2's own instruction (don't repeat the last ~10-15 headlines/captions for
this feature). This stage exists for what those two miss: near-identical
phrasing that rotation wouldn't catch because the *assignment* was fine, the
*words* just happened to converge.

Two checks, both against history.py's "recent_all" list:
  1. Exact-match hash on a normalized headline (lowercased, punctuation
     stripped, whitespace collapsed) -- catches literal repeats and
     near-trivial rewordings.
  2. A cheap token-overlap similarity score (Jaccard over word sets) on the
     combined headline+caption text -- catches paraphrased repeats that
     share most of their substance but no exact string.

**Flags, never auto-blocks** (per pipeline-plan.md): a false positive that
silently kills a good post is worse than one that arrives with a note on
it. This script's exit code is always 0 on a successful run; the caller
(the orchestrator) is expected to read the `flagged` field and route
accordingly -- write it into the draft's `notes` column, not reject the
post.

Usage:
    python3 checks.py <candidate_content.json> <shaped_history.json>

candidate_content.json needs at least "headline" and optionally "caption"
(matching the format's content-example.json shape).

Output (stdout): a JSON object --
{
  "flagged": bool,
  "exact_hash_match": bool,
  "similarity_flags": [{"against_headline": str, "score": float}, ...],
                        # entries scoring above SIMILARITY_THRESHOLD
  "note": str | null    # human-readable summary for the notes column, or
                         # null if nothing was flagged
}
"""
import hashlib
import json
import re
import sys

SIMILARITY_THRESHOLD = 0.6


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def hash_headline(headline: str) -> str:
    return hashlib.sha256(normalize(headline).encode()).hexdigest()


def jaccard_similarity(a: str, b: str) -> float:
    tokens_a = set(normalize(a).split())
    tokens_b = set(normalize(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def run_checks(candidate: dict, recent_all: list) -> dict:
    headline = candidate.get("headline", "")
    caption = candidate.get("caption", "")
    candidate_text = f"{headline} {caption}".strip()
    candidate_hash = hash_headline(headline) if headline else None

    exact_hash_match = False
    similarity_flags = []

    for past in recent_all:
        past_headline = past.get("headline") or ""
        past_caption = past.get("caption") or ""
        if not past_headline:
            continue

        if candidate_hash and hash_headline(past_headline) == candidate_hash:
            exact_hash_match = True

        past_text = f"{past_headline} {past_caption}".strip()
        score = jaccard_similarity(candidate_text, past_text)
        if score >= SIMILARITY_THRESHOLD:
            similarity_flags.append({"against_headline": past_headline, "score": round(score, 2)})

    flagged = exact_hash_match or bool(similarity_flags)

    note = None
    if exact_hash_match:
        note = "Duplicate backstop: headline normalizes identically to a past post."
    elif similarity_flags:
        top = max(similarity_flags, key=lambda f: f["score"])
        note = (
            f"Duplicate backstop: {round(top['score'] * 100)}% word-overlap with a past "
            f"post ('{top['against_headline']}') -- review before approving."
        )

    return {
        "flagged": flagged,
        "exact_hash_match": exact_hash_match,
        "similarity_flags": similarity_flags,
        "note": note,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 checks.py <candidate_content.json> <shaped_history.json>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        candidate = json.load(f)
    with open(sys.argv[2]) as f:
        history = json.load(f)

    print(json.dumps(run_checks(candidate, history.get("recent_all", [])), indent=2))
