# install_content.py <plan_dir> <memora-web dir>
# Puts a plan's content/ into the demo build (call after resetting demo-content/ to its committed state):
#   flashcards.json / quiz.json: the plan's pack goes FIRST in packs / mcqPacks (replacing any pack with the same key),
#   so a typed prompt matching its `match` fragments picks it.  course.json: replaces the demo course.
import json, os, sys

plan_dir, mw = sys.argv[1:3]
cdir, dc = os.path.join(plan_dir, 'content'), os.path.join(mw, 'demo-content')
if not os.path.isdir(cdir): print('  content: demo build defaults'); sys.exit(0)
for f in sorted(os.listdir(cdir)):
    src = json.load(open(os.path.join(cdir, f)))
    if f in ('flashcards.json', 'quiz.json'):
        target = os.path.join(dc, f); base = json.load(open(target)); key = 'packs' if f == 'flashcards.json' else 'mcqPacks'
        pack = src['pack']; base[key] = [pack] + [p for p in base[key] if p.get('key') != pack['key']]
        json.dump(base, open(target, 'w'), indent=1, ensure_ascii=False); print(f'  content: {f} pack "{pack["key"]}" installed first')
    elif f == 'course.json':
        src.setdefault('status', 'complete'); src.setdefault('editedStructure', src['structure'])
        for st in (src['structure'], src['editedStructure']):      # the app's schema needs these; the planner needn't write them
            st['error'] = None; st.setdefault('course_title', src['course_title'])
            for n in st['nodes']:
                for sn in n['subnodes']: sn.setdefault('expected_tokens', 600)
        json.dump(src, open(os.path.join(dc, f), 'w'), indent=1, ensure_ascii=False); print(f'  content: course "{src["course_title"]}" installed')
