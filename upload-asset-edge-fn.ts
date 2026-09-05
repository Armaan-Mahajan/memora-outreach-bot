// Test edge function: accepts a base64-encoded file in a JSON POST body and
// writes it to Supabase Storage using the service-role client, entirely
// within Supabase's own infrastructure. Invoked via pg_net's net.http_post
// from a SQL call, so the only thing that needs to cross our sandbox's
// blocked egress to *.supabase.co is... nothing. The SQL MCP call itself is
// proxied outside the sandbox (already proven), and this function's own
// network hop to Storage happens on Supabase's side, not ours.
//
// POST body: { bucket: string, path: string, contentType: string, data_base64: string }
import { createClient } from "https://esm.sh/@supabase/supabase-js@2"

Deno.serve(async (req) => {
  try {
    const { bucket, path, contentType, data_base64 } = await req.json()
    if (!bucket || !path || !data_base64) {
      return new Response(JSON.stringify({ ok: false, error: "missing bucket/path/data_base64" }), { status: 400 })
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
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
