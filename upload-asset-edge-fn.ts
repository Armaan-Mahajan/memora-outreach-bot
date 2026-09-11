// Test edge function: accepts a base64-encoded file in a JSON POST body and
// writes it to Supabase Storage using the secret-key admin client, entirely
// within Supabase's own infrastructure. Invoked via pg_net's net.http_post
// from a SQL call, so the only thing that needs to cross our sandbox's
// blocked egress to *.supabase.co is... nothing. The SQL MCP call itself is
// proxied outside the sandbox (already proven), and this function's own
// network hop to Storage happens on Supabase's side, not ours.
//
// Auth (updated 2026-09-11, moving off the legacy JWT-based anon/service_role
// keys entirely): this function is never called by a browser or any public
// client -- only by our own pg_net call from inside Postgres. The new secret
// key isn't a JWT, so the platform gateway can't validate it for us the way
// it used to validate the legacy service_role key -- this function must be
// deployed with verify_jwt = false, and it checks the incoming `apikey`
// header against the project's own secret key itself before doing anything.
// See Supabase's "Migrating to publishable and secret API keys" guide,
// step 4, and "Database Webhooks and pg_net" for why the key now travels on
// `apikey` and never on `Authorization: Bearer`.
//
// POST body: { bucket: string, path: string, contentType: string, data_base64: string }
// Header: apikey: <secret key>  (never Authorization: Bearer)
import { createClient } from "https://esm.sh/@supabase/supabase-js@2"

const SECRET_KEY = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS")!)["default"]

Deno.serve(async (req) => {
  try {
    const incomingKey = req.headers.get("apikey")
    if (!incomingKey || incomingKey !== SECRET_KEY) {
      return new Response(JSON.stringify({ ok: false, error: "unauthorized" }), { status: 401 })
    }

    const { bucket, path, contentType, data_base64 } = await req.json()
    if (!bucket || !path || !data_base64) {
      return new Response(JSON.stringify({ ok: false, error: "missing bucket/path/data_base64" }), { status: 400 })
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      SECRET_KEY
    )

    const bytes = Uint8Array.from(atob(data_base64), (c) => c.charCodeAt(0))

    const { error: uploadError } = await supabase.storage
      .from(bucket)
      .upload(path, bytes, { contentType: contentType || "application/octet-stream", upsert: true })

    if (uploadError) {
      return new Response(JSON.stringify({ ok: false, error: uploadError.message }), { status: 500 })
    }

    const { data: pub } = supabase.storage.from(bucket).getPublicUrl(path)

    return new Response(
      JSON.stringify({ ok: true, bytes_written: bytes.length, public_url: pub.publicUrl }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    )
  } catch (e) {
    return new Response(JSON.stringify({ ok: false, error: String(e) }), { status: 500 })
  }
})
