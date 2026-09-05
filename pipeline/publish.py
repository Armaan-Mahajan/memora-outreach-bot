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

THREE upload-related commands exist here:

  github-upload-sql: the real path for every actual post. The rendered
    image is committed and pushed to drafts/<format>/<slug>/NN.ext in this
    repo FIRST (a plain `git add && git commit && git push` -- git streams
    the file from disk over its own connection, so the bytes never pass
    through the orchestrator's context at all). This command then builds a
    net.http_post call whose body is just {bucket, path, source_url} --
    source_url pointing at that file's raw.githubusercontent.com URL. The
    Edge Function fetches it server-side (Supabase's infra has normal
    internet access) and writes it to Storage. Nothing but a short URL
    string ever touches the orchestrating model's context.

  upload-sql: the same net.http_post shape, but with the image's raw
    base64 inlined into the call as data_base64 instead of a source_url.
    Only for genuinely tiny fixtures (a test image a few hundred bytes) --
    for anything real, the orchestrator would have to read and retype the
    entire base64 payload as its own tool-call text to get here, which is
    exactly the slow, expensive, silently-corruptible failure mode
    github-upload-sql exists to avoid. Do not reach for this for a real
    rendered post.

  insert-sql: queues the actual outreach_drafts row once every image for
    a post is confirmed uploaded (200 OK, checked via net._http_response).

Credentials are never hardcoded here -- this file goes into a git repo.
Pass them as arguments or set the environment variables named below.

Usage, real posts (three steps):

  1. Commit and push the rendered image(s) to drafts/, e.g.:
       git add drafts/single_image/my-post-slug/01.jpg
       git commit -m "Add my-post-slug draft"
       git push

  2. One call per image, in slide order:
       python3 publish.py github-upload-sql \\
         --supabase-url "$SUPABASE_URL" --anon-key "$SUPABASE_ANON_KEY" \\
         --repo Armaan-Mahajan/memora-outreach-bot \\
         --format single_image --slug my-post-slug --index 1 \\
         --image output/stat-hero/my-post-slug.jpg
     Prints one JSON object: {"repo_path", "source_url", "public_url", "sql"}.
     The orchestrator runs `sql` via execute_sql for each image, then checks
     net._http_response for that request's status_code (200) and that the
     body's "ok" is true before continuing -- do not build the insert below
     on an unconfirmed upload. A non-200/non-ok response usually means the
     push in step 1 hasn't landed yet, or the repo path is wrong.

  3. Once every upload is confirmed:
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
DEFAULT_REPO = "Armaan-Mahajan/memora-outreach-bot"
DEFAULT_BRANCH = "main"


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


def cmd_github_upload_sql(args):
    supabase_url, anon_key = _resolve_creds(args)

    bytes_len = os.path.getsize(args.image)
    _, content_type, storage_path = _image_meta(args.image, args.format, args.slug, args.index)
    repo_path = f"drafts/{storage_path}"
    source_url = f"https://raw.githubusercontent.com/{args.repo}/{args.branch}/{repo_path}"
    public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{args.bucket}/{storage_path}"

    body = {
        "bucket": args.bucket,
        "path": storage_path,
        "contentType": content_type,
        "source_url": source_url,
    }
    sql = _net_http_post_sql(supabase_url, anon_key, body)

    print(json.dumps({
        "repo_path": repo_path,
        "source_url": source_url,
        "storage_path": storage_path,
        "public_url": public_url,
        "bytes": bytes_len,
        "sql": sql,
    }, indent=2))


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

    gh = sub.add_parser("github-upload-sql", help="build the net.http_post SQL for an image already pushed to drafts/ -- use this for real posts")
    gh.add_argument("--supabase-url", help="e.g. https://xxxx.supabase.co (or set SUPABASE_URL)")
    gh.add_argument("--anon-key", help="legacy anon JWT (or set SUPABASE_ANON_KEY) -- never hardcode this")
    gh.add_argument("--bucket", default=DEFAULT_BUCKET)
    gh.add_argument("--repo", default=DEFAULT_REPO, help="owner/repo on GitHub, e.g. Armaan-Mahajan/memora-outreach-bot")
    gh.add_argument("--branch", default=DEFAULT_BRANCH)
    gh.add_argument("--format", required=True, choices=["single_image", "slideshow", "reel"])
    gh.add_argument("--slug", required=True)
    gh.add_argument("--index", type=int, default=1, help="slide number, 1-based (single_image is always 1)")
    gh.add_argument("--image", required=True, help="local path to the rendered JPEG (must already be pushed to the matching drafts/ path)")
    gh.set_defaults(func=cmd_github_upload_sql)

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
    ins.add_argument("--asset-urls", nargs="+", required=True, help="public_url values from upload-sql/github-upload-sql, in slide order")
    ins.add_argument("--notes", help="Stage 3/7 flags to seed the notes column with")
    ins.set_defaults(func=cmd_insert_sql)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
