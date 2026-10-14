// http.mjs — a fetch()-shaped wrapper around curl, used for every ElevenLabs request.
//
// Why curl and not Node's built-in fetch: in the cloud routine the ElevenLabs key is a network secret that the session's
// agent proxy adds to requests for api.elevenlabs.io. curl sends its requests through that proxy (it honours HTTPS_PROXY),
// so the key gets attached. Node's built-in fetch ignores HTTPS_PROXY and reached ElevenLabs by another route with no key
// on it (confirmed 2026-10-14: same request, curl HTTP 200, fetch 401 needs_authorization). Locally ELEVENLABS_API_KEY is
// passed as a header instead, and curl behaves the same either way.
//
// Returns { ok, status, text(), json(), arrayBuffer() } like fetch. A transport failure (DNS, refused, timeout) throws an
// Error whose .cause.code says what happened, which is what tts.mjs's retry loop expects from fetch.
import { spawn } from 'child_process';

export function curlFetch(url, { method = 'GET', headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const args = ['-sS', '-X', method, '--max-time', '180', '-o', '-', '-w', '\n%{http_code}'];
    for (const [k, v] of Object.entries(headers)) args.push('-H', `${k}: ${v}`);
    if (body !== undefined) args.push('--data-binary', '@-');
    args.push(url);
    const p = spawn('curl', args, { stdio: ['pipe', 'pipe', 'pipe'] });
    const out = [], err = [];
    p.stdout.on('data', d => out.push(d));
    p.stderr.on('data', d => err.push(d));
    p.on('error', e => reject(Object.assign(new Error(`curl could not start: ${e.message}`), { cause: { code: e.code } })));
    p.on('close', code => {
      if (code !== 0) {
        const msg = Buffer.concat(err).toString().trim();
        return reject(Object.assign(new Error(msg || `curl exited ${code}`), { cause: { code: `curl exit ${code}` } }));
      }
      const all = Buffer.concat(out);
      const nl = all.lastIndexOf(10);                     // the status code is on the last line (-w '\n%{http_code}')
      const status = parseInt(all.subarray(nl + 1).toString(), 10) || 0;
      const payload = all.subarray(0, nl);
      resolve({
        ok: status >= 200 && status < 300, status,
        text: async () => payload.toString('utf8'),
        json: async () => JSON.parse(payload.toString('utf8')),
        arrayBuffer: async () => payload.buffer.slice(payload.byteOffset, payload.byteOffset + payload.length),
      });
    });
    if (body !== undefined) p.stdin.end(body); else p.stdin.end();
  });
}
