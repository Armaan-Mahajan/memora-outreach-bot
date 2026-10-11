# validate_plan.py <plan_dir> <config.json> — the plan.json shape every reel needs (REELS-RUNBOOK.md, "Reel types").
import json, os, re, sys
d, cfg = sys.argv[1], json.load(open(sys.argv[2])); problems = []
try: p = json.load(open(os.path.join(d, 'plan.json')))
except Exception as e: sys.exit(f'PLAN INVALID\n  - plan.json: {e}')
slug = os.path.basename(os.path.normpath(d))
if p.get('slug') != slug: problems.append(f'slug "{p.get("slug")}" must equal the folder name "{slug}"')
if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,60}', slug): problems.append('slug: lowercase letters, digits, hyphens (3-61 chars)')
TYPES = {'agent', 'quiz', 'flashcards', 'autopilot', 'overview', 'adaptive'}
if p.get('feature') not in TYPES: problems.append(f'feature must be one of {sorted(TYPES)}')
t = p.get('topic')
if not (isinstance(t, dict) and isinstance(t.get('topic'), str) and t['topic'].strip()): problems.append('topic: {"topic": "...", "level": "..."} required')
sec = p.get('seconds')
if not (isinstance(sec, list) and len(sec) == 2 and all(isinstance(x, (int, float)) for x in sec) and 15 <= sec[0] < sec[1] <= 60):
    problems.append('seconds: [min, max] target within 15-60')
tl = p.get('timeline')
if not (isinstance(tl, list) and tl): problems.append('timeline: a non-empty list of segments')
vo = p.get('vo') or {}
roster = [v['name'] for v in cfg.get('voices', [])]
if vo.get('voice') not in roster: problems.append(f'vo.voice must be one of the roster: {roster}')
lines = vo.get('lines') or []
if not 2 <= len(lines) <= 10: problems.append(f'vo.lines: {len(lines)} lines (2-10)')
for i, l in enumerate(lines):
    if not (isinstance(l, dict) and isinstance(l.get('text'), str) and l['text'].strip()): problems.append(f'vo.lines[{i}]: text required'); continue
    if sum(k in l for k in ('at', 'end')) != 1: problems.append(f'vo.lines[{i}]: exactly one of "at" / "end"')
total = sum(len(l.get('text', '')) for l in lines if isinstance(l, dict))
if total > 600: problems.append(f'voiceover is {total} characters (max 600: it must fit the reel)')
if problems: print('PLAN INVALID'); [print('  - ' + x) for x in problems]; sys.exit(1)
print(f'plan ok ({p["feature"]}, voice {vo["voice"]}, {len(lines)} lines, {total} chars)')
