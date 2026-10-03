// tts.mjs — generate the voiceover for a reel with ElevenLabs, with per-character timings for captions.
// Run on your own machine so the API key never leaves it:
//   cd ~/Documents/Projects/Memora/reel-lab
//   node tts.mjs vo-script.json        (key read from reel-lab/.env: ELEVENLABS_API_KEY=sk_...)
// Output: out/vo/<name>/line-<n>.mp3 + line-<n>.json (text, model, alignment) + manifest.json
// Needs Node 18+ (built-in fetch). No npm packages.
import fs from 'fs';

// Key comes from the environment or from reel-lab/.env (ELEVENLABS_API_KEY=...). It is never printed.
if (!process.env.ELEVENLABS_API_KEY && fs.existsSync(new URL('./.env', import.meta.url))) {
  for (const line of fs.readFileSync(new URL('./.env', import.meta.url), 'utf8').split('\n')) {
    const m = line.match(/^\s*([A-Z_]+)\s*=\s*['"]?([^'"\s]+)['"]?\s*$/); if (m && !process.env[m[1]]) process.env[m[1]] = m[2]; } }
const KEY = process.env.ELEVENLABS_API_KEY;
if (!KEY) { console.error('No ELEVENLABS_API_KEY: put it in reel-lab/.env (see the comment at the top).'); process.exit(1); }
const script = JSON.parse(fs.readFileSync(process.argv[2] || 'vo-script.json', 'utf8'));
const API = 'https://api.elevenlabs.io/v1';
const H = { 'xi-api-key': KEY, 'content-type': 'application/json' };

// Resolve the voice: use the given id; if it doesn't exist, look it up by name among your voices.
async function resolveVoice() {
  if (script.voice_id) { const r = await fetch(`${API}/voices/${script.voice_id}`, { headers: H }); if (r.ok) return script.voice_id; }
  const r = await fetch(`${API}/voices`, { headers: H });
  if (!r.ok) throw new Error(`voice lookup failed: ${r.status} ${await r.text()}`);
  const v = (await r.json()).voices.find(v => v.name.toLowerCase().startsWith(script.voice_name.toLowerCase()));
  if (!v) throw new Error(`no voice named ${script.voice_name} in your account`);
  return v.voice_id;
}

const voiceId = await resolveVoice();
const out = `out/vo/${script.name}`; fs.mkdirSync(out, { recursive: true });
const manifest = { name: script.name, voice_id: voiceId, voice_name: script.voice_name, lines: [] };
let chars = 0;
for (const [i, line] of script.lines.entries()) {
  let done = false;
  for (const model of script.models) {            // first model that works wins
    const r = await fetch(`${API}/text-to-speech/${voiceId}/with-timestamps?output_format=mp3_44100_128`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ text: line.text, model_id: model, voice_settings: script.voice_settings }) });
    if (!r.ok) { console.log(`  line ${i + 1}: ${model} → ${r.status} ${(await r.text()).slice(0, 160)}`); continue; }
    const j = await r.json();
    fs.writeFileSync(`${out}/line-${i + 1}.mp3`, Buffer.from(j.audio_base64, 'base64'));
    fs.writeFileSync(`${out}/line-${i + 1}.json`, JSON.stringify({ text: line.text, at: line.at, model, alignment: j.alignment }, null, 1));
    manifest.lines.push({ n: i + 1, at: line.at, model, file: `line-${i + 1}.mp3` });
    chars += line.text.length; done = true;
    console.log(`  line ${i + 1}: ok with ${model} (${line.text.length} chars)`); break;
  }
  if (!done) { console.error(`line ${i + 1} failed on every model — stopping.`); process.exit(1); }
}
fs.writeFileSync(`${out}/manifest.json`, JSON.stringify(manifest, null, 1));
console.log(`done → reel-lab/${out}  (${chars} characters sent)`);
