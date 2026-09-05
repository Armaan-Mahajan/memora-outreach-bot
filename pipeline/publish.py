#!/usr/bin/env python3
"""
Stage 8 -- Publish to the queue. Prepares SQL; does NOT execute it.

This is deliberate, not a limitation to work around: MCP tool access (the
execute_sql call that actually talks to Supabase) belongs to the
orchestrating Claude session, not to a plain Python subprocess -- the same
reason history.py doesn't query Supabase directly either. What this script
does is the part that's genuinely mechanical: building the exact SQL text,
so the orchestrator never hand-assembles a query.

Why SQL at all for a file upload: see pipeline-plan.md's "Getting bytes into
Storage from the cloud" section. The cloud sandbox's shell cannot reach
Supabase Storage directly (egress is blocked), so uploads go through the
`upload-asset` Edge Function via pg_net's net.http_post, itself triggered
through execute_sql -- which IS proxied outside the sandbox's blocked
egress.

Image delivery used to run through this repo: a real post's rendered image
was pushed to drafts/<format>/<slug>/NN.ext, and a github-upload-sql
command here built the net.http_post call pointing the Edge Function at
that file's raw.githubusercontent.com URL. It worked, but existed purely
to get bytes past a wall (git streams from disk, no LLM retyping) and
needed a whole side apparatus to stay unattended: a dedicated SSH deploy
key, a macOS job polling for pending commits, and a repo-scoped read token
on the Edge Function. Removed 2026-09-05 -- Make.com now receives the
rendered bytes directly over a webhook (streamed from disk, same property
git had) and calls the Edge Function itself with the bytes inlined, since
the cost that ruled out inlining was always about the orchestrating model
retyping a big string, not about the mechanism. One fewer credential, one
fewer moving part, and image delivery no longer has anything to do with
this repo. See pipeline-plan.md for the full history of why this changed.

TWO upload-related commands remain here:

  upload-sql: net.http_post with the image's raw base64 inlined as
    data_base64. Still fine for genuinely tiny fixtures (a test image a
    few hundred bytes) and for manual debugging -- for a real post, Make's
    webhook relay is the actual path now, not this script.

  insert-sql: queues the actual outreach_drafts row once every image for
    a post is confirmed uploaded (200 OK, checked via net._http_response,
    or whatever confirmation Make's relay returns).

Credentials are never hardcoded here -- this file goes into a git repo.
Pass them as arguments or set the environment variables named below.

Usage:

  python3 publish.py insert-sql \\
    --format single_image --feature agent --layout flow-outline \\
    --archetype feature-highlight \\
    --content content.json --asset-urls url1 [url2 ...] \\
    --notes "optional Stage 3/7 flags"

  Prints one JSON object: {"sql": "insert into outreach_drafts ... ;"}.
  The orchestrator runs this once via execute_sql to actually queue the
  draft. format/feature/archetype/layout/topic map straight onto the
  outreach_drafts columns -- format must be exactly one of
  single_image / slideshow / reel (the table's CHECK constraint; note
  the underscore, not a hyphen), and format + feature are NOT NULL on
  the real table (confirmed 2026-09-04's capability test).
"""
import argparse
import base64
import json
import os
import sys

DEFAULT_BUCKET = "outreach-assets"


def sql_string(value) -> str:
    """A Postgres single-quoted string literal, or NULL for None."""
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def sql_text_array(values) -> str:
    if not values:
        return "ARRAY[]::text[]"
    return "ARRAY[" + ", ".join(sql_string(v) for v in values) + "]::text[]"


def sql_jsonb(obj) -> str:
    if obj is None:
        return "NULL"
    return sql_string(json.dumps(obj)) + "::jsonb"


def _resolve_creds(args):
    supabase_url = args.supabase_url or os.environ.get("SUPABASE_URL")
    anon_key = args.anon_key or os.environ.get("SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        print(
            "Need --supabase-url/--anon-key or SUPABASE_URL/SUPABASE_ANON_KEY env vars.",
            file=sys.stderr,
        )
        sys.exit(1)
    return supabase_url, anon_key


def _image_meta(image_path, format_, slug, index):
    ext = os.path.splitext(image_path)[1].lstrip(".").lower() or "jpg"
    content_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    filename = f"{index:02d}.{ext}"
    storage_path = f"{format_}/{slug}/{filename}"
    return ext, content_type, storage_path


def _net_http_post_sql(supabase_url, anon_key, body):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {anon_key}",
        "apikey": anon_key,
    }
    return (
        "select net.http_post(\n"
        f"  url := {sql_string(f'{supabase_url.rstrip(chr(47))}/functions/v1/upload-asset')},\n"
        f"  headers := {sql_string(json.dumps(headers))}::jsonb,\n"
        f"  body := {sql_string(json.dumps(body))}::jsonb,\n"
        "  timeout_milliseconds := 15000\n"
        ") as request_id;"
    )


def cmd_upload_sql(args):
    supabase_url, anon_key = _resolve_creds(args)

    with open(args.image, "rb") as f:
        image_bytes = f.read()
    b64 = base64.b64encode(image_bytes).decode()

    _, content_type, storage_path = _image_meta(args.image, args.format, args.slug, args.index)
    public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{args.bucket}/{storage_path}"

    body = {
        "bucket": args.bucket,
        "path": storage_path,
        "contentType": content_type,
        "data_base64": b64,
    }
    sql = _net_http_post_sql(supabase_url, anon_key, body)

    print(json.dumps({"path": storage_path, "public_url": public_url, "bytes": len(image_bytes), "sql": sql}, indent=2))


def cmd_insert_sql(args):
    with open(args.content) as f:
        content = json.load(f)

    # feature is NOT NULL on the real table (confirmed 2026-09-04), but
    # slideshow archetypes micro-lesson/technique aren't tied to any single
    # feature the way single-image cards are. Rather than stuffing a topic
    # slug into a column the dashboard may filter on as one of the four
    # real features (agent/flashcards/quizzes/mora), default to the
    # explicit sentinel "general" -- self-evidently not a real feature, so
    # it can't be mistaken for one. The one archetype that DOES have a real
    # feature tie-in, agent-output, should pass --feature agent explicitly.
    feature = args.feature or ("agent" if args.archetype == "agent-output" else "general")

    columns = {
        "format": sql_string(args.format),
        "feature": sql_string(feature),
        "status": sql_string("pending"),
        "headline": sql_string(content.get("headline") or content.get("quote")),
        "subhead": sql_string(content.get("subhead") or content.get("support")),
        "caption": sql_string(args.caption or content.get("caption")),
        "hashtags": sql_text_array(args.hashtags or content.get("hashtags") or []),
        "content_json": sql_jsonb(content),
        "asset_urls": sql_text_array(args.asset_urls),
        "topic": sql_string(args.topic),
        "archetype": sql_string(args.archetype),
        "layout": sql_string(args.layout),
        "notes": sql_string(args.notes),
    }

    col_names = ", ".join(columns.keys())
    col_values = ", ".join(columns.values())
    sql = f"insert into outreach_drafts ({col_names})\nvalues ({col_values})\nreturning id;"

    print(json.dumps({"sql": sql}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("upload-sql", help="build the net.http_post SQL with base64 inlined -- tiny test fixtures ONLY, never a real post")
    up.add_argument("--supabase-url", help="e.g. https://xxxx.supabase.co (or set SUPABASE_URL)")
    up.add_argument("--anon-key", help="legacy anon JWT (or set SUPABASE_ANON_KEY) -- never hardcode this")
    up.add_argument("--bucket", default=DEFAULT_BUCKET)
    up.add_argument("--format", required=True, choices=["single_image", "slideshow", "reel"])
    up.add_argument("--slug", required=True)
    up.add_argument("--index", type=int, default=1, help="slide number, 1-based (single_image is always 1)")
    up.add_argument("--image", required=True, help="path to the rendered JPEG")
    up.set_defaults(func=cmd_upload_sql)

    ins = sub.add_parser("insert-sql", help="build the outreach_drafts INSERT SQL")
    ins.add_argument("--format", required=True, choices=["single_image", "slideshow", "reel"])
    ins.add_argument("--feature", help="one of agent/flashcards/quizzes/mora; omit for slideshows to default to the 'general' sentinel (or 'agent' automatically for archetype agent-output)")
    ins.add_argument("--topic", help="slideshow topic slug, from topics.json")
    ins.add_argument("--archetype", required=True, choices=["micro-lesson", "technique", "agent-output", "feature-highlight"])
    ins.add_argument("--layout", help="single-image layout name; omit for slideshows")
    ins.add_argument("--content", required=True, help="path to the rendered content JSON")
    ins.add_argument("--caption", help="overrides content.json's caption field if given")
    ins.add_argument("--hashtags", nargs="*", help="overrides content.json's hashtags field if given")
    ins.add_argument("--asset-urls", nargs="+", required=True, help="public_url values -- from upload-sql, or from whatever Make.com's relay returns -- in slide order")
    ins.add_argument("--notes", help="Stage 3/7 flags to seed the notes column with")
    ins.set_defaults(func=cmd_insert_sql)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
