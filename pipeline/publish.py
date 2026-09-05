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

Two things were tried and abandoned before landing on the design below --
recorded here so nobody re-discovers them the hard way:

  The GitHub relay (2026-09-04/05): a real post's rendered image was pushed
  to drafts/<format>/<slug>/NN.ext in this repo, and a github-upload-sql
  command built the net.http_post call pointing the Edge Function at that
  file's raw.githubusercontent.com URL. It worked end-to-end on a real
  post, but needed a dedicated SSH deploy key, a macOS launchd job polling
  for pending commits, and a repo-scoped read token on the Edge Function --
  a lot of standing infrastructure just to avoid retyping base64. Torn
  down 2026-09-05.

  Make.com as the relay (2026-09-05, same day): the plan that replaced the
  GitHub relay was to have Make.com's webhook receive the rendered bytes
  directly and call the Edge Function itself. It was never built --
  reachability testing that same day found that NO Claude-driven shell
  (this cloud sandbox, or a Mac linked via the device bridge) can reach
  Make's webhook host, or any third-party host, at all: outbound network
  from any Claude-controlled shell is restricted to a small allowlist
  (package registries, Anthropic's own API hosts, private IP ranges) that
  doesn't include Make, Supabase's own REST endpoint, or anything else
  third-party. Google Drive and Dropbox connectors were checked too, as a
  possible "upload here, hand Make the URL" step -- both would still
  require the image's base64 as an inline tool-call argument (neither has
  a local-file-path upload option), so neither reduces the cost this was
  meant to avoid, and Dropbox can't even take binary content or produce a
  public link at all. NONE of this affects Make.com's other, separate job
  of actually posting a queued draft to Instagram later -- that's Make
  reading a public Supabase Storage URL with its own outbound connection,
  the opposite direction from what was tested and blocked here.

Where that leaves this script (settled 2026-09-05): there is no relay.
The orchestrating Claude session pays the token cost directly, via
`chunk-upload` below, delegated to a cheap subagent (Haiku) specifically
so that cost lands at Haiku's per-token rate and stays out of the main
run's own context window -- not because there's a way to avoid generating
the base64 as tool-call text. There isn't, with today's tools.

THREE upload-related commands live here:

  chunk-upload: the real path for every actual post. Splits the image's
    base64 into small chunks, writes one `insert` statement per chunk (so
    no single execute_sql call carries more than --chunk-size characters),
    then a trigger statement whose body is assembled *inside Postgres* via
    string_agg over those chunk rows -- so the trigger call itself stays
    small no matter how big the image is. The chunk inserts are where the
    real token cost lives; nothing here reduces that, it only keeps any
    single call small and keeps the assembly verifiably correct (see
    02_verify.sql's hash check) rather than silently truncated.

  upload-sql: net.http_post with the image's raw base64 inlined directly
    as data_base64, no chunking. Only for genuinely tiny fixtures (a test
    image a few hundred bytes) or manual debugging -- never for a real
    rendered post, which chunk-upload exists for specifically.

  insert-sql: queues the actual outreach_drafts row once every image for
    a post is confirmed uploaded AND independently verified (200 OK +
    "ok":true, AND the storage object's byte size re-queried and compared
    -- see RUNBOOK.md Stage 9).

Credentials are never hardcoded here -- this file goes into a git repo.
Pass them as arguments or set the environment variables named below.

Usage, a real post (chunk-upload, one call per image, in slide order):

  python3 publish.py chunk-upload \\
    --supabase-url "$SUPABASE_URL" --anon-key "$SUPABASE_ANON_KEY" \\
    --format single_image --slug my-post-slug --index 1 \\
    --image output/stat-hero/my-post-slug.jpg --out-dir /tmp/upload-01

  Writes 00_create_table.sql, 01_chunk_0000.sql...01_chunk_NNNN.sql,
  02_verify.sql, 03_trigger.sql, 04_cleanup.sql, and manifest.json into
  --out-dir, and prints the manifest. Run each file's SQL via execute_sql
  IN ORDER (00, every 01_chunk in order, 02, then check 02's hash_matches
  is true before running 03). Run 04_cleanup.sql once 03's response is
  confirmed 200/ok, win or lose -- don't leave chunk rows behind.

  Then, once every image for the post is confirmed uploaded and verified
  (RUNBOOK.md Stage 9):

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
import hashlib
import json
import os
import sys
import time

DEFAULT_BUCKET = "outreach-assets"
DEFAULT_CHUNK_SIZE = 10000


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


def cmd_chunk_upload(args):
    supabase_url, anon_key = _resolve_creds(args)

    with open(args.image, "rb") as f:
        image_bytes = f.read()
    b64 = base64.b64encode(image_bytes).decode()
    expected_sha256 = hashlib.sha256(b64.encode()).hexdigest()

    _, content_type, storage_path = _image_meta(args.image, args.format, args.slug, args.index)
    public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{args.bucket}/{storage_path}"

    upload_id = f"{args.slug}-{args.index:02d}-{int(time.time())}"
    chunks = [b64[i : i + args.chunk_size] for i in range(0, len(b64), args.chunk_size)]

    os.makedirs(args.out_dir, exist_ok=True)

    with open(os.path.join(args.out_dir, "00_create_table.sql"), "w") as f:
        f.write(
            "create table if not exists _pipeline_upload_chunks (\n"
            "  upload_id text not null,\n"
            "  idx int not null,\n"
            "  chunk text not null,\n"
            "  primary key (upload_id, idx)\n"
            ");"
        )

    for i, chunk in enumerate(chunks):
        with open(os.path.join(args.out_dir, f"01_chunk_{i:04d}.sql"), "w") as f:
            f.write(
                "insert into _pipeline_upload_chunks (upload_id, idx, chunk) values "
                f"({sql_string(upload_id)}, {i}, {sql_string(chunk)});"
            )

    with open(os.path.join(args.out_dir, "02_verify.sql"), "w") as f:
        f.write(
            "select\n"
            f"  (encode(digest(assembled, 'sha256'), 'hex') = {sql_string(expected_sha256)}) as hash_matches,\n"
            "  encode(digest(assembled, 'sha256'), 'hex') as actual_hash,\n"
            "  length(assembled) as assembled_length\n"
            "from (\n"
            "  select string_agg(chunk, '' order by idx) as assembled\n"
            f"  from _pipeline_upload_chunks where upload_id = {sql_string(upload_id)}\n"
            ") s;"
        )

    body_no_data = {
        "bucket": args.bucket,
        "path": storage_path,
        "contentType": content_type,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {anon_key}",
        "apikey": anon_key,
    }
    # body is built server-side via jsonb concatenation so the assembled
    # base64 (verified in 02_verify.sql, above) never has to be re-embedded
    # as a literal here -- this call stays small no matter how big the
    # image is.
    with open(os.path.join(args.out_dir, "03_trigger.sql"), "w") as f:
        f.write(
            "select net.http_post(\n"
            f"  url := {sql_string(f'{supabase_url.rstrip(chr(47))}/functions/v1/upload-asset')},\n"
            f"  headers := {sql_string(json.dumps(headers))}::jsonb,\n"
            f"  body := ({sql_string(json.dumps(body_no_data))}::jsonb) || jsonb_build_object(\n"
            "    'data_base64',\n"
            "    (select string_agg(chunk, '' order by idx) from _pipeline_upload_chunks\n"
            f"     where upload_id = {sql_string(upload_id)})\n"
            "  ),\n"
            "  timeout_milliseconds := 20000\n"
            ") as request_id;"
        )

    with open(os.path.join(args.out_dir, "04_cleanup.sql"), "w") as f:
        f.write(f"delete from _pipeline_upload_chunks where upload_id = {sql_string(upload_id)};")

    manifest = {
        "upload_id": upload_id,
        "num_chunks": len(chunks),
        "chunk_size": args.chunk_size,
        "expected_sha256": expected_sha256,
        "path": storage_path,
        "public_url": public_url,
        "bytes": len(image_bytes),
    }
    with open(os.path.join(args.out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(json.dumps(manifest, indent=2))


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

    chunk = sub.add_parser("chunk-upload", help="the real path for a real post -- chunked base64, assembled server-side")
    chunk.add_argument("--supabase-url", help="e.g. https://xxxx.supabase.co (or set SUPABASE_URL)")
    chunk.add_argument("--anon-key", help="legacy anon JWT (or set SUPABASE_ANON_KEY) -- never hardcode this")
    chunk.add_argument("--bucket", default=DEFAULT_BUCKET)
    chunk.add_argument("--format", required=True, choices=["single_image", "slideshow", "reel"])
    chunk.add_argument("--slug", required=True)
    chunk.add_argument("--index", type=int, default=1, help="slide number, 1-based (single_image is always 1)")
    chunk.add_argument("--image", required=True, help="path to the rendered JPEG")
    chunk.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="base64 characters per insert statement")
    chunk.add_argument("--out-dir", required=True, help="directory to write the generated .sql files + manifest.json into")
    chunk.set_defaults(func=cmd_chunk_upload)

    up = sub.add_parser("upload-sql", help="build the net.http_post SQL with base64 inlined, no chunking -- tiny test fixtures ONLY, never a real post")
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
    ins.add_argument("--asset-urls", nargs="+", required=True, help="public_url values from chunk-upload's manifest.json, in slide order")
    ins.add_argument("--notes", help="Stage 3/7 flags to seed the notes column with")
    ins.set_defaults(func=cmd_insert_sql)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
