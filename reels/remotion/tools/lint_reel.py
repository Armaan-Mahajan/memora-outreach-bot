# lint_reel.py <plan_dir> — rules every planner-written reel must pass before it's rendered.
# Full creative freedom inside these lines; the lines are about determinism, safety, and the project's non-negotiables.
import json, os, re, sys
plan_dir = sys.argv[1]; problems = []
plan = json.load(open(os.path.join(plan_dir, 'plan.json')))
files = {f: open(os.path.join(plan_dir, f)).read() for f in os.listdir(plan_dir) if f.endswith(('.tsx', '.ts'))}
if 'Reel.tsx' not in files: problems.append('Reel.tsx is missing (it must default-export the reel component)')
ALLOWED_IMPORTS = re.compile(r"^(react|remotion|\.\./\.\./kit|\./[A-Za-z0-9_\-]+|\./content/[A-Za-z0-9_\-]+\.json)$")
BANNED = [  # (pattern, why)
    (r'\bfetch\s*\(|XMLHttpRequest|WebSocket|navigator\.|document\.cookie|localStorage|sessionStorage', 'no network or browser storage'),
    (r'\beval\s*\(|new\s+Function\s*\(|\bimport\s*\(', 'no eval / dynamic code'),
    (r'Math\.random|Date\.now|new\s+Date\s*\(|performance\.now', 'not deterministic (use rand(seed) and frame time from useT())'),
    (r'setTimeout|setInterval|requestAnimationFrame|useEffect|useLayoutEffect', 'no timers/effects: everything must be a pure function of the frame'),
    (r'https?://', 'no external URLs (fonts, images, data must come from the kit or staticFile)'),
    (r'\brequire\s*\(|process\.|child_process|\bfs\b', 'no Node APIs'),
    (r'dangerouslySetInnerHTML', 'no raw HTML injection'),
]
for name, src in files.items():
    for m in re.finditer(r"""(?:import|export)\s[^;]*?from\s+['"]([^'"]+)['"]|import\s+['"]([^'"]+)['"]""", src):
        mod = m.group(1) or m.group(2)
        if not ALLOWED_IMPORTS.match(mod): problems.append(f'{name}: import "{mod}" not allowed (react, remotion, ../../kit, local ./files only)')
    for pat, why in BANNED:
        for m in re.finditer(pat, src): problems.append(f'{name}: "{m.group(0)}" — {why}')
reel = files.get('Reel.tsx', '')
if 'export default' not in reel: problems.append('Reel.tsx: needs `export default` of the reel component')
if 'ReelShell' not in reel: problems.append('Reel.tsx: must wrap everything in <ReelShell R={R}> (voice, music, captions)')
code = ''.join(files.values())
lit = lambda sid: re.search(r"""['"`]%s['"`]""" % re.escape(sid), code)   # the id as a string literal anywhere (attribute, array, map…)
if plan['timeline'] and '<Seg' not in code: problems.append('no <Seg R={R} id="…"> in the code: every timeline segment renders inside one')
if any(s['kind'] == 'footage' for s in plan['timeline']) and '<AppWindow' not in code: problems.append('no <AppWindow> in the code: footage segments must show the recording')
for s in plan['timeline']:
    if not lit(s['id']):
        what = 'footage segment' if s['kind'] == 'footage' else 'segment'
        problems.append(f'{what} "{s["id"]}" never appears in the code: render it with <Seg R={{R}} id="{s["id"]}">' +
                        (f'<AppWindow R={{R}} id="{s["id"]}" /></Seg>' if s['kind'] == 'footage' else '…</Seg>') + ' (a variable id is fine if the literal is listed somewhere, e.g. an array of ids)')
# words a minor-heavy audience must never see from us (project content rules): no fake urgency, no user counts
copy = ' '.join(re.findall(r'>([^<>{}]{3,})<', ''.join(files.values()))) + ' ' + json.dumps(plan.get('vo', {}).get('lines', []))
for pat, why in [(r'\b(only|just)\s+\d+\s+(spots?|left|hours?)\b|\blimited time\b|\bact now\b|\bhurry\b|\btoday only\b', 'manufactured urgency'),
                 (r'\b\d[\d,]*\+?\s+(users|students|learners|people)\b|\bthousands of\b|\bmillions of\b', 'user/scale counts are never mentioned')]:
    for m in re.finditer(pat, copy, re.I): problems.append(f'copy: "{m.group(0)}" — {why}')
# the ending: the voice says a sign-up line, never the address; the address is on screen (REELS-RUNBOOK.md, content rules)
vo_text = ' '.join(l.get('text', '') for l in plan.get('vo', {}).get('lines', []))
for m in re.finditer(r'the[\s-]*memora\s*(?:\.|dot)\s*com|memora\s*(?:\.|dot)\s*com|\bwww\.', vo_text, re.I):
    problems.append(f'voiceover says "{m.group(0)}" — never read the address out; close on a sign-up line ("Sign up free.") and show the-memora.com on the last screen')
if not re.search(r'>[^<{}]*the-memora\.com[^<{}]*<|[\'"`]the-memora\.com[\'"`]\s*\}?\s*<', ''.join(files.values())) and not re.search(r'>\s*\{\s*[\'"`]the-memora\.com', ''.join(files.values())):
    problems.append('the last screen must show the address: put the-memora.com as on-screen text in the outro (e.g. <div>the-memora.com</div>)')
if problems:
    print('LINT FAILED'); [print('  - ' + p) for p in problems]; sys.exit(1)
print(f'lint ok ({len(files)} file(s))')
