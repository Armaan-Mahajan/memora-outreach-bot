# place_vo.py <tts_out_dir> <footage_key> <events.json> <vo_script.json>
#   → public/vo/<footage>/line-N.mp3 + src/footage/<footage>/vo.json (word-timed captions)
# Line start times come from the recording itself: each line in the vo script names the event it narrates
# ("anchor": "viewer_open" / "click:generate", plus "offset"), or "end_at": "rec_end" to finish just before the end.
# Overlaps are pushed later (0.15 s gap). The reel always keeps TAIL s of picture after the last word: if the voice runs
# past rec_end - TAIL, vo.json gets "hold" seconds and the render freezes the recording's last frame for that long.
# More than MAX_HOLD means a script is genuinely too long → exits non-zero.
import json, os, sys, shutil, subprocess
src, name, evp, scp = sys.argv[1:5]
TAIL, MAX_HOLD = 1.0, 3.0
root = os.path.join(os.path.dirname(__file__), '..')
ev = json.load(open(evp))['events']; t0 = next(e['t'] for e in ev if e['type'] == 'rec_start'); end = next(e['t'] for e in ev if e['type'] == 'rec_end') - t0
def when(key):
    if key.startswith('click:'):
        hit = [e for e in ev if e['type'] == 'click' and e.get('target') == key[6:]]
    else:
        hit = [e for e in ev if e['type'] == key]
    if not hit: sys.exit(f'place_vo: event "{key}" not found in {evp}')
    return hit[0]['t'] - t0
script = json.load(open(scp)); man = json.load(open(f'{src}/manifest.json'))
os.makedirs(f'{root}/public/vo/{name}', exist_ok=True); os.makedirs(f'{root}/src/footage/{name}', exist_ok=True)
lines = []; prev_end = 0.0
for L, S in zip(man['lines'], script['lines']):
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f'{src}/{L["file"]}'], capture_output=True, text=True).stdout)
    at = (when(S['end_at']) + S['offset'] - dur) if 'end_at' in S else (when(S['anchor']) + S['offset'])
    at = round(max(at, prev_end + 0.15 if lines else at, 0.0), 3)
    j = json.load(open(f'{src}/line-{L["n"]}.json')); a = j['alignment']; words, cur, s0, pe = [], '', None, 0
    for c, s, e in zip(a['characters'], a['character_start_times_seconds'], a['character_end_times_seconds']):
        if c.isspace():
            if cur: words.append({'w': cur, 's': round(at + s0, 3), 'e': round(at + pe, 3)}); cur = ''
            continue
        if not cur: s0 = s
        cur += c; pe = e
    if cur: words.append({'w': cur, 's': round(at + s0, 3), 'e': round(at + pe, 3)})
    shutil.copy(f'{src}/{L["file"]}', f'{root}/public/vo/{name}/{L["file"]}')
    lines.append({'at': at, 'file': L['file'], 'dur': round(dur, 3), 'text': j['text'], 'words': words}); prev_end = at + dur
    print(f"  {at:5.1f}s → {at + dur:5.1f}s  {j['text']}")
hold = round(max(0.0, prev_end + TAIL - end), 3)
if hold > MAX_HOLD: sys.exit(f'place_vo: voiceover ends {prev_end:.2f}s, clip {end:.2f}s — would need a {hold:.1f}s end hold (max {MAX_HOLD}); shorten the script')
json.dump({'voice': man['voice_name'], 'hold': hold, 'lines': lines}, open(f'{root}/src/footage/{name}/vo.json', 'w'), indent=1)
print(f'  voice ends {prev_end:.2f}s, clip {end:.2f}s' + (f' → {hold:.2f}s end hold (reel {end + hold:.2f}s)' if hold else f' → {end - prev_end:.2f}s of picture after the last word'))
