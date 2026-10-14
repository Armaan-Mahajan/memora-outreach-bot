// check.mjs — can this session actually make an ElevenLabs voiceover? Run by plan.sh before any recording time is spent.
// It makes one real text-to-speech request ("Hi.", a few characters of credit) with the same client and endpoint as
// tts.mjs, so a pass here means the voiceover step will authenticate too. In the routine the key is a network secret the
// agent proxy adds to api.elevenlabs.io requests (ELEVENLABS_API_KEY stays unset); locally ELEVENLABS_API_KEY is sent.
// Prints only the HTTP status and ElevenLabs' own error code and message, never the key.
// Exit 0 = works · 2 = ElevenLabs refused (auth, permissions, quota: not worth retrying) · 1 = network problem.
import fs from 'fs';

const cfg = JSON.parse(fs.readFileSync(new URL('../config.json', import.meta.url), 'utf8'));
const voice = cfg.voices[0];
const model = cfg.voice_model || 'eleven_v4';
const API = process.env.ELEVENLABS_API_BASE || 'https://api.elevenlabs.io/v1';
const headers = { 'content-type': 'application/json' };
if (process.env.ELEVENLABS_API_KEY) headers['xi-api-key'] = process.env.ELEVENLABS_API_KEY;

let r;
try {
  r = await fetch(`${API}/text-to-speech/${voice.id}?output_format=mp3_22050_32`, {
    method: 'POST', headers, body: JSON.stringify({ text: 'Hi.', model_id: model }) });
} catch (e) {
  console.log(`elevenlabs check: network error (${e.cause?.code || e.message})`);
  process.exit(1);
}
if (r.ok) { await r.arrayBuffer(); console.log(`elevenlabs check: ok (HTTP ${r.status}, voice ${voice.name}, ${model})`); process.exit(0); }

let code = '', message = '';
const body = await r.text();
try { const d = JSON.parse(body).detail; code = d?.status || d?.code || ''; message = d?.message || (typeof d === 'string' ? d : ''); }
catch { message = body.slice(0, 200); }
console.log(`elevenlabs check: HTTP ${r.status}${code ? ` ${code}` : ''}${message ? `: ${message.slice(0, 240)}` : ''}`);
console.log(`elevenlabs check: key sent by this script: ${process.env.ELEVENLABS_API_KEY ? 'yes (ELEVENLABS_API_KEY)' : 'no (relying on the network secret)'}`);
process.exit(r.status === 401 || r.status === 403 || r.status === 402 ? 2 : 1);
