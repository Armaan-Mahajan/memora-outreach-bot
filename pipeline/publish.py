#!/usr/bin/env python3
"""
Stage 8 -- Publish to the queue. Prepares SQL; does NOT execute it.

This is deliberate, not a limitation to work around: MCP tool access (the
execute_sql call that actually talks to Supabase) belongs to the
orchestrating Claude session, not to a plain Python subprocess -- the same
reason history.py doesn't query Supabase directly either. What this script
does is the part that's genuinely mechanical: building the exact SQL text.

Why SQL at all for a file upload: see pipeline-plan.md's "Getting bytes into
Storage from the cloud" section. The cloud sandbox's shell cannot reach
Supabase Storage directly (egress is blocked -- confirmed twice now, once
in the 2026-09-04 capability test and once by a direct curl retest against
the exact same project this session), so uploads go through the
`upload-asset` Edge Function via pg_net's net.http_post, itself triggered
through execute_sql -- which IS proxied outside the sandbox's blocked
egress.

TWO upload commands exist here, and which one to use is NOT a style choice:

  upload-sql: the whole image's base64 in ONE net.http_post call, as a
    single literal in the query text. Only safe for genuinely tiny payloads
    (a test fixture, a few hundred bytes) -- see below for why.

  chunk-upload: for any real rendered image. Use this one by default.

Why chunk-upload exists, not just a size optimization: the orchestrating
Claude session builds a tool call's arguments as its own generated text, so
a giant base64 literal has to pass through the model's own context/output
to get from "a file on disk" to "the query parameter of an execute_sql
call." That's two separate failures waiting to happen, both confirmed live
on 2026-09-04, not theoretical: (1) a single dense-text tool result (a
Read, a cat) truncates well below what a real ~100-300KB rendered JPEG's
base64 needs -- tens of thousands of tokens for one image, and the
truncation caps hit long before that; and (2) even within size limits, a
model hand-relaying a 150,000+ character literal can introduce a
transcription error -- confirmed live too: the first real attempt at this
failed with a Postgres "unterminated quoted string" error from exactly
this kind of slip. That one failed loudly. A single flipped base64
character elsewhere in the string would NOT fail loudly -- it would upload
a silently corrupted image. That's not a risk to route around with bigger
chunks; it's a reason to never trust an unverified hand-relayed payload at
all.

chunk-upload's fix: split the base64 into chunks small enough that each one
individually is trivial to relay correctly (default 15,000 chars -- comfortably
inside a single Read call, confirmed), insert them into a small scratch
table across several small `execute_sql` calls, then have Postgres itself
-- not Claude -- verify the assembled string's SHA-256 against a hash
computed locally (by this script, from the original file, before anything
was relayed) BEFORE triggering the actual upload. A mismatch means a relay
error happened somewhere in the chunks and the run must stop and retry
that chunk, not proceed. The final upload trigger references the
already-assembled value from the table, so it stays small regardless of
image size -- the huge literal only ever exists as several small, verified
pieces.

Credentials are never hardcoded here -- this file goes into a git repo.
Pass them as arguments or set the environment variables named below.

Usage:

  1. Prepare a chunked upload (writes small SQL files to --out-dir, never
     prints the payload itself):
       python3 publish.py chunk-upload \\
         --supabase-url "$SUPABASE_URL" --anon-key "$SUPABASE_ANON_KEY" \\
         --format single_image --slug my-post-slug --index 1 \\
         --image output/stat-hero/my-post-slug.jpg --out-dir /tmp/upload_chunks
     Then, in order, each via execute_sql:
       a. Read and run 00_create_table.sql (idempotent -- safe every time).
       b. Read and run each 01_chunk_NNNN.sql file, in order.
       c. Read and run 02_verify.sql. It returns {hash_matches, actual_hash}.
          hash_matches MUST be true (compare against manifest.json's
          expected_sha256) before continuing -- if false, something got
          corrupted in relay; delete the chunks for this upload_id (see
          manifest.json) and redo step (b), do not proceed to (d).
       d. Read and run 03_trigger.sql. Returns a request_id.
          Check net._http_response for that id -- confirm status_code=200
          and the body contains "ok":true before treating the image as
          uploaded.
       e. Read and run 04_cleanup.sql to drop this upload's chunk rows.
     manifest.json (in --out-dir) carries {upload_id, num_chunks,
     expected_sha256, path, public_url, bytes}. public_url is what goes
     into insert-sql's --asset-urls below.

  2. One call per image, always safe regardless of size (no payload in the
     query at all): build via chunk-upload above, or for a genuinely tiny
     fixture only:
       python3 publish.py upload-sql \\
         --supabase-url "$SUPABASE_URL" --anon-key "$SUPABASE_ANON_KEY" \\
         --format single_image --slug my-post-slug --index 1 \\
         --image output/stat-hero/my-post-slug.jpg
     Prints one JSON object: {"path": ..., "public_url": ..., "sql": ...}.

  3. Once every upload is confirmed 200 OK:
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
DEFAULT_CHUNK_SIZE = 15000


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


def cmd_upload_sql(args):
    supabase_url = args.supabase_url or os.environ.get("SUPABASE_URL")
    anon_key = args.anon_key or os.environ.get("SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        print(
            "Need --supabase-url/--anon-key or SUPABASE_URL/SUPABASE_ANON_KEY env vars.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(args.image, "rb") as f:
        image_bytes = f.read()
    b64 = base64.b64encode(image_bytes).decode()

    ext = os.path.splitext(args.image)[1].lstrip(".").lower() or "jpg"
    content_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    filename = f"{args.index:02d}.{ext}"
    path = f"{args.format}/{args.slug}/{filename}"
    public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{args.bucket}/{path}"

    body = {
        "bucket": args.bucket,
        "path": path,
        "contentType": content_type,
        "data_base64": b64,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {anon_key}",
        "apikey": anon_key,
    }

    sql = (
        "select net.http_post(\n"
        f"  url := {sql_string(f'{supabase_url.rstrip(chr(47))}/functions/v1/upload-asset')},\n"
        f"  headers := {sql_string(json.dumps(headers))}::jsonb,\n"
        f"  body := {sql_string(json.dumps(body))}::jsonb,\n"
        "  timeout_milliseconds := 15000\n"
        ") as request_id;"
    )

    print(json.dumps({"path": path, "public_url": public_url, "bytes": len(image_bytes), "sql": sql}, indent=2))


def cmd_chunk_upload(args):
    supabase_url = args.supabase_url or os.environ.get("SUPABASE_URL")
    anon_key = args.anon_key or os.environ.get("SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        print(
            "Need --supabase-url/--anon-key or SUPABASE_URL/SUPABASE_ANON_KEY env vars.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(args.image, "rb") as f:
        image_bytes = f.read()
    b64 = base64.b64encode(image_bytes).decode()
    expected_sha256 = hashlib.sha256(b64.encode()).hexdigest()

    ext = os.path.splitext(args.image)[1].lstrip(".").lower() or "jpg"
    content_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    filename = f"{args.index:02d}.{ext}"
    path = f"{args.format}/{args.slug}/{filename}"
    public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{args.bucket}/{path}"

    upload_id = f"{args.slug}-{args.index:02d}-{int(time.time())}"
    chunk_size = args.chunk_size
    chunks = [b64[i : i + chunk_size] for i in range(0, len(b64), chunk_size)]

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
            "  encode(digest(assembled, 'sha256'), 'hex') as actual_hash\n"
            "from (\n"
            "  select string_agg(chunk, '' order by idx) as assembled\n"
            f"  from _pipeline_upload_chunks where upload_id = {sql_string(upload_id)}\n"
            ") s;"
        )

    body_no_data = {
        "bucket": args.bucket,
        "path": path,
        "contentType": content_type,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {anon_key}",
        "apikey": anon_key,
    }
    # body is built server-side via jsonb concatenation so the assembled
    # base64 (verified in step 02, above) never has to be re-embedded as a
    # literal here -- this call stays small no matter how big the image is.
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
        "chunk_size": chunk_size,
        "expected_sha256": expected_sha256,
        "path": path,
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

    up = sub.add_parser("upload-sql", help="build the net.http_post SQL for one rendered image")
    up.add_argument("--supabase-url", help="e.g. https://xxxx.supabase.co (or set SUPABASE_URL)")
    up.add_argument("--anon-key", help="legacy anon JWT (or set SUPABASE_ANON_KEY) -- never hardcode this")
    up.add_argument("--bucket", default=DEFAULT_BUCKET)
    up.add_argument("--format", required=True, choices=["single_image", "slideshow", "reel"])
    up.add_argument("--slug", required=True)
    up.add_argument("--index", type=int, default=1, help="slide number, 1-based (single_image is always 1)")
    up.add_argument("--image", required=True, help="path to the rendered JPEG")
    up.set_defaults(func=cmd_upload_sql)

    chunk = sub.add_parser("chunk-upload", help="build a verified, size-safe chunked upload -- use this for real images")
    chunk.add_argument("--supabase-url", help="e.g. https://xxxx.supabase.co (or set SUPABASE_URL)")
    chunk.add_argument("--anon-key", help="legacy anon JWT (or set SUPABASE_ANON_KEY) -- never hardcode this")
    chunk.add_argument("--bucket", default=DEFAULT_BUCKET)
    chunk.add_argument("--format", required=True, choices=["single_image", "slideshow", "reel"])
    chunk.add_argument("--slug", required=True)
    chunk.add_argument("--index", type=int, default=1, help="slide number, 1-based (single_image is always 1)")
    chunk.add_argument("--image", required=True, help="path to the rendered JPEG")
    chunk.add_argument("--out-dir", required=True, help="directory to write the chunk SQL files + manifest.json to")
    chunk.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="base64 chars per chunk (default 15000, safely under one Read call)")
    chunk.set_defaults(func=cmd_chunk_upload)

    ins = sub.add_parser("insert-sql", help="build the outreach_drafts INSERT SQL")
    ins.add_argument("--format", required=True, choices=["single_image", "slideshow", "reel"])
    ins.add_argument("--feature", help="one of agent/flashcards/quizzes/mora; omit for slideshows to default to the 'general' sentinel (or 'agent' automatically for archetype agent-output)")
    ins.add_argument("--topic", help="slideshow topic slug, from topics.json")
    ins.add_argument("--archetype", required=True, choices=["micro-lesson", "technique", "agent-output", "feature-highlight"])
    ins.add_argument("--layout", help="single-image layout name; omit for slideshows")
    ins.add_argument("--content", required=True, help="path to the rendered content JSON")
    ins.add_argument("--caption", help="overrides content.json's caption field if given")
    ins.add_argument("--hashtags", nargs="*", help="overrides content.json's hashtags field if given")
    ins.add_argument("--asset-urls", nargs="+", required=True, help="public_url values from upload-sql, in slide order")
    ins.add_argument("--notes", help="Stage 3/7 flags to seed the notes column with")
    ins.set_defaults(func=cmd_insert_sql)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
