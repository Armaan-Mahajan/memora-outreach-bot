# validate_capture.py <plan_dir> — the recording script must drive only the local demo app, with steps the runner knows,
# starting where the reel's type lives (APP-MAP.md).
import json, os, re, sys
d = sys.argv[1]; plan = json.load(open(os.path.join(d, 'plan.json'))); problems = []
try: cap = json.load(open(os.path.join(d, 'capture.json')))
except Exception as e: sys.exit(f'CAPTURE INVALID\n  - capture.json: {e}')
ALLOWED_TOP = {'name', 'start_url', 'viewport', 'speed', 'steps', 'hide'}
for k in cap:
    if k not in ALLOWED_TOP: problems.append(f'capture.json: key "{k}" not allowed (no base / account overrides)')
if cap.get('name') != plan['slug']: problems.append(f'capture.json name must be the plan slug "{plan["slug"]}"')
# where each reel type may start (the planner navigates from there by clicking, like a person would)
START = {'agent': ['/agent'], 'quiz': ['/quizzes'], 'flashcards': ['/flashcards'],
         'autopilot': ['/autopilot', '/dashboard'], 'overview': ['/', '/dashboard'],
         'adaptive': ['/autopilot', '/flashcards/decks', '/quizzes', '/dashboard']}
feat = plan.get('feature')
if feat not in START: problems.append(f'plan.feature must be one of {", ".join(START)}')
su = cap.get('start_url', '')
if not (isinstance(su, str) and su.startswith('/') and not su.startswith('//')): problems.append('start_url must be a path on the demo app, e.g. "/quizzes/ai-gen"')
elif feat in START and not any(su == x or (x != '/' and su.startswith(x)) for x in START[feat]):
    problems.append(f'start_url "{su}" does not fit a {feat} reel (start at one of: {", ".join(START[feat])})')
if cap.get('viewport', {'w': 1320, 'h': 860}) != {'w': 1320, 'h': 860}: problems.append('viewport must stay 1320×860 (the camera and window are built for it)')
FIELDS = {'pause': {'ms'}, 'speed': {'k'}, 'mark': set(), 'hover': {'target'}, 'click': {'target'}, 'type': {'text'}, 'wait': {'for'}, 'press': {'key'}, 'scroll': {'ms'}}
steps = cap.get('steps', [])
if not 3 <= len(steps) <= 120: problems.append(f'{len(steps)} steps (3-120)')
typed = 0
for i, s in enumerate(steps):
    k = s.get('do')
    if k not in FIELDS: problems.append(f'step {i + 1}: unknown action "{k}" (allowed: {", ".join(FIELDS)})'); continue
    for f in FIELDS[k]:
        if f not in s: problems.append(f'step {i + 1} ({k}): needs "{f}"')
    if 'mark' in s and not re.fullmatch(r'[a-z][a-z0-9_]*', str(s['mark'])): problems.append(f'step {i + 1}: mark "{s["mark"]}" must be lowercase_with_underscores')
    if 'as' in s and not re.fullmatch(r'[a-z][a-z0-9_]*', str(s['as'])): problems.append(f'step {i + 1}: "as" must be lowercase_with_underscores')
    if k == 'scroll' and not (('dy' in s) ^ (s.get('to') in ('top', 'bottom'))): problems.append(f'step {i + 1}: scroll needs "dy" (pixels) or "to": "top" | "bottom"')
    if k == 'pause' and not 0 <= s.get('ms', 0) <= 5000: problems.append(f'step {i + 1}: pause over 5 s')
    if k == 'speed':
        if s.get('k') not in ('fast', 'normal'): problems.append(f'step {i + 1}: speed k must be "fast" or "normal"')
        if 'x' in s and not (isinstance(s['x'], (int, float)) and 1.5 <= s['x'] <= 12): problems.append(f'step {i + 1}: speed x must be 1.5-12')
    if k == 'type': typed += len(s.get('text', ''))
    if 'box' in s and not ('mark' in s and isinstance(s['box'], dict) and {'css', 'role', 'text'} & set(s['box'])):
        problems.append(f'step {i + 1}: "box" needs a "mark" on the same step and a target (css, role+name or text)')
    if 'expect_url' in s and not str(s['expect_url']).startswith('/'): problems.append(f'step {i + 1}: expect_url must be an app path')
    t = s.get('target') or (s.get('for') if isinstance(s.get('for'), dict) else None)
    if isinstance(t, dict) and not ({'css', 'role', 'text'} & set(t) or {'url', 'load', 'enabled'} & set(t)): problems.append(f'step {i + 1}: target needs css, role+name, or text')
if typed > 180: problems.append(f'{typed} characters typed (max 180: typing is slow on camera)')
fast = [s.get('k') for s in steps if s.get('do') == 'speed']
if fast and fast[-1] == 'fast': problems.append('a `speed: fast` stretch is never ended with `speed: normal`')
if problems: print('CAPTURE INVALID'); [print('  - ' + p) for p in problems]; sys.exit(1)
print(f'capture ok ({len(steps)} steps)')
