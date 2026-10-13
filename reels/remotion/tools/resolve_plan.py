# resolve_plan.py <plan_dir> <capture_out_dir> <tts_dir>
#
# Turns a planner-written reel plan + the real recording into the exact clock the reel's code renders against:
#   src/reels/<slug>/resolved.json   segments (reel seconds), recording clip slice per footage segment, event marks, placed voiceover
#   src/reels/<slug>/*.tsx            the plan's own Remotion code, copied in
#   public/reels/<slug>/clip.mp4, vo/  media
#
# Anchors (used by footage segments and voiceover lines) name a moment in the RECORDING:
#   rec_start | rec_end | <event type> | click:<target>   optionally  #<n> (n-th occurrence, 1-based)  and  +<s> / -<s>
#   e.g. "rec_start+0.5", "results_open+2", "click:generate-0.4", "click:sidebar#2"
# Voiceover line timing (exactly one of):
#   "at": "seg:<id>+<s>"        seconds after segment <id> starts
#   "at": "ev:<anchor>"         when that recording moment is on screen (must fall inside a footage segment)
#   "end": "end-<s>"            the line ENDS <s> seconds before the timeline's end
# Overlapping lines are pushed later (0.15 s gap). Every reel keeps >= TAIL s of picture after the last word:
# if the voice runs long, the last segment is held (footage freezes on its last frame) by up to MAX_HOLD s, else this fails.
import json, os, re, shutil, subprocess, sys

TAIL, MAX_HOLD, GAP = 1.0, 3.0, 0.15
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

def die(msg): sys.exit(f'resolve_plan: {msg}')

plan_dir, cap_dir, tts_dir = sys.argv[1:4]
plan = json.load(open(os.path.join(plan_dir, 'plan.json')))
slug = plan['slug']
if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,60}', slug): die(f'slug "{slug}" must be lowercase letters, digits and hyphens')
ev_doc = json.load(open(os.path.join(cap_dir, 'events.json')))
evs = ev_doc['events']
t0 = next(e['t'] for e in evs if e['type'] == 'rec_start'); t_end = next(e['t'] for e in evs if e['type'] == 'rec_end')
clip_dur = t_end - t0

def anchor(spec):
    m = re.fullmatch(r'(click:[a-z0-9_]+|[a-z0-9_]+)(?:#(\d+))?([+-]\d+(?:\.\d+)?)?', spec.strip())
    if not m: die(f'bad anchor "{spec}"')
    name, nth, off = m.group(1), int(m.group(2) or 1), float(m.group(3) or 0)
    if name.startswith('click:'): hits = [e for e in evs if e['type'] == 'click' and e.get('target') == name[6:]]
    else: hits = [e for e in evs if e['type'] == name]
    if len(hits) < nth: die(f'anchor "{spec}": the recording has {len(hits)} "{name}" event(s); known: ' +
                            ', '.join(sorted({("click:" + e["target"]) if e["type"] == "click" and e.get("target") else e["type"] for e in evs})))
    return hits[nth - 1]['t'] - t0 + off

# ── segments ──
segs, t, ids = [], 0.0, set()
for s in plan['timeline']:
    sid = s['id']
    if not re.fullmatch(r'[a-z][a-z0-9_]*', sid) or sid in ids: die(f'segment id "{sid}" must be unique, lowercase, start with a letter')
    ids.add(sid)
    if s['kind'] == 'scene':
        d = float(s['dur'])
        if not 0.4 <= d <= 15: die(f'scene "{sid}" dur {d}s outside 0.4-15 s')
        segs.append({'id': sid, 'kind': 'scene', 'start': round(t, 3), 'end': round(t + d, 3)}); t += d
    elif s['kind'] == 'footage':
        a, b = max(0.0, anchor(s['from'])), min(clip_dur, anchor(s['to']))
        if b - a < 0.5: die(f'footage "{sid}" is {b - a:.2f}s long ({s["from"]} → {s["to"]})')
        # "max": the segment may take at most this many reel seconds — a longer slice plays faster (frames dropped) to fit
        mx = s.get('max'); rate = 1.0
        if mx is not None:
            if not 1 <= float(mx) <= 30: die(f'footage "{sid}" max {mx}s outside 1-30 s')
            rate = max(1.0, (b - a) / float(mx))
            if rate > 6: die(f'footage "{sid}" is {b - a:.1f}s of recording for max {mx}s: {rate:.1f}x would be a blur (max 6x) — record it faster (speed x) or shorten the slice')
        seg = {'id': sid, 'kind': 'footage', 'start': round(t, 3), 'end': round(t + (b - a) / rate, 3), 'clipIn': round(a, 3), 'clipOut': round(b, 3)}
        if rate > 1: seg['rate'] = round(rate, 4)
        segs.append(seg); t += (b - a) / rate
    else: die(f'segment "{sid}" kind must be scene or footage')
total = t
if not any(s['kind'] == 'footage' for s in segs): die('the timeline shows no app footage: every reel must show the real app')

def clip_to_reel(ct):
    for s in segs:
        if s['kind'] == 'footage' and s['clipIn'] - 1e-6 <= ct <= s['clipOut'] + 1e-6: return s['start'] + (ct - s['clipIn']) / s.get('rate', 1)
    return None

marks = {}
for e in evs:
    key = ('click:' + e['target']) if e['type'] == 'click' and e.get('target') else e['type']
    if key in marks: continue
    r = clip_to_reel(e['t'] - t0)
    if r is not None: marks[key] = round(r, 3)

# ── voiceover ──
man = json.load(open(os.path.join(tts_dir, 'manifest.json')))
script_lines = plan['vo']['lines']
if len(man['lines']) != len(script_lines): die('voiceover audio does not match the plan (line count) — re-run the voice step')
pub = os.path.join(ROOT, 'public', 'reels', slug); os.makedirs(os.path.join(pub, 'vo'), exist_ok=True)
lines, prev_end = [], None
for L, S in zip(man['lines'], script_lines):
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', os.path.join(tts_dir, L['file'])],
                               capture_output=True, text=True).stdout)
    if 'end' in S:
        m = re.fullmatch(r'end([+-]\d+(?:\.\d+)?)?', S['end']); at = total + float(m.group(1) or 0) - dur if m else die(f'bad end "{S["end"]}"')
    else:
        spec = S['at']
        if spec.startswith('seg:'):
            m = re.fullmatch(r'seg:([a-z][a-z0-9_]*)([+-]\d+(?:\.\d+)?)?', spec)
            sg = next((s for s in segs if m and s['id'] == m.group(1)), None)
            if not sg: die(f'voice line "{S["text"][:30]}…": unknown segment in "{spec}"')
            at = sg['start'] + float(m.group(2) or 0)
        elif spec.startswith('ev:'):
            at = clip_to_reel(anchor(spec[3:]))
            if at is None: die(f'voice line "{S["text"][:30]}…": "{spec}" is not on screen in any footage segment')
        else: die(f'voice line timing "{spec}" must start with seg: or ev:, or use "end"')
    at = max(0.0, at)
    if prev_end is not None: at = max(at, prev_end + GAP)
    j = json.load(open(os.path.join(tts_dir, f'line-{L["n"]}.json'))); a = j['alignment']; words, cur, s0, pe = [], '', None, 0
    for c, cs, ce in zip(a['characters'], a['character_start_times_seconds'], a['character_end_times_seconds']):
        if c.isspace():
            if cur: words.append({'w': cur, 's': round(at + s0, 3), 'e': round(at + pe, 3)}); cur = ''
            continue
        if not cur: s0 = cs
        cur += c; pe = ce
    if cur: words.append({'w': cur, 's': round(at + s0, 3), 'e': round(at + pe, 3)})
    shutil.copy(os.path.join(tts_dir, L['file']), os.path.join(pub, 'vo', L['file']))
    lines.append({'at': round(at, 3), 'dur': round(dur, 3), 'file': L['file'], 'text': j['text'], 'words': words}); prev_end = at + dur

hold = round(max(0.0, (prev_end or 0) + TAIL - total), 3)
if hold > MAX_HOLD: die(f'voiceover ends {prev_end:.2f}s but the timeline is {total:.2f}s — would need a {hold:.1f}s hold (max {MAX_HOLD}); shorten the script or lengthen the timeline')
if hold:
    segs[-1]['end'] = round(segs[-1]['end'] + hold, 3)
    if segs[-1]['kind'] == 'footage': segs[-1]['clipOut'] = round(segs[-1]['clipOut'] + hold * segs[-1].get('rate', 1), 3)

# ── write ──
shutil.copy(os.path.join(cap_dir, 'clip.mp4'), os.path.join(pub, 'clip.mp4'))
src = os.path.join(ROOT, 'src', 'reels', slug)
if os.path.isdir(src): shutil.rmtree(src)
os.makedirs(src)
for f in os.listdir(plan_dir):
    if f.endswith('.tsx') or f.endswith('.ts'): shutil.copy(os.path.join(plan_dir, f), os.path.join(src, f))
if os.path.isdir(os.path.join(plan_dir, 'content')): shutil.copytree(os.path.join(plan_dir, 'content'), os.path.join(src, 'content'))
resolved = {'slug': slug, 'dur': round(total + hold, 3), 'hold': hold, 'segments': segs,
            'footage': {'clip': f'reels/{slug}/clip.mp4', 'events': ev_doc, 'regions': plan.get('regions', {}), 'beats': plan.get('beats', []), 'clipDur': round(clip_dur, 3)},
            'marks': marks, 'vo': {'lines': lines}, 'voDir': f'reels/{slug}/vo/'}
json.dump(resolved, open(os.path.join(src, 'resolved.json'), 'w'), indent=1)
print(f'  {slug}: {len(segs)} segments, {total:.2f}s + {hold:.2f}s hold = {total + hold:.2f}s')
for s in segs: print(f'    {s["start"]:6.2f}–{s["end"]:6.2f}  {s["kind"]:7s} {s["id"]}' + (f'  (clip {s["clipIn"]:.2f}–{s["clipOut"]:.2f}' + (f', {s["rate"]:.2f}x' if s.get('rate') else '') + ')' if s['kind'] == 'footage' else ''))
for l in lines: print(f'    {l["at"]:6.2f}→{l["at"] + l["dur"]:6.2f}  "{l["text"]}"')
