# validate_content.py <plan_dir>
#
# A plan may bring its own demo content — what the app "generates" on camera — in content/. All optional:
#   content/flashcards.json  {"pack": {...}}   one flashcard pack (demo-recording-mode-v2's demo-content/flashcards.json format)
#   content/quiz.json        {"pack": {...}}   one multiple-choice pack (demo-content/quiz.json mcqPacks format)
#   content/course.json      {...}             a whole Agent course (demo-content/course.json format): 7-9 nodes, authored
#                                               content for at least the first 3; expected_tokens / structure.error optional
# install_content.py puts them into the demo build before recording: a pack is placed FIRST in its list, so a prompt
# that contains one of its `match` fragments picks it; a course replaces the demo course.
# Without content/, the reel uses the demo build's own seeded content (APP-MAP.md lists what exists).
import json, os, re, sys

plan_dir = sys.argv[1]
cdir = os.path.join(plan_dir, 'content')
problems = []
BANNED = re.compile(r"\b(?:AP|IB|DP|GCSE|IGCSE|A-Levels?|CBSE|ICSE|MYP|FRQ|SAT|ACT)\b")      # the demo content test's rule
URGENCY = re.compile(r"\bstreak|don't break|you missed|falling behind|hurry|last chance|only \d+ days? left|act now\b", re.I)
s = lambda x, n=1: isinstance(x, str) and len(x.strip()) >= n

def text_rules(obj, where):
    t = json.dumps(obj, ensure_ascii=False)
    m = BANNED.search(t)
    if m: problems.append(f'{where}: no curriculum names inside generated content (found "{m.group(0)}") — they may appear only in the typed prompt')
    if URGENCY.search(t): problems.append(f'{where}: no streak / guilt / urgency copy')

def pack_head(p, where):
    if not (s(p.get('key'), 2) and re.fullmatch(r'[a-z0-9-]+', p['key'])): problems.append(f'{where}.key: lowercase letters, digits, hyphens')
    if not s(p.get('title'), 3): problems.append(f'{where}.title missing')
    if not (isinstance(p.get('keywords'), list) and p['keywords']): problems.append(f'{where}.keywords: a non-empty list')
    m = p.get('match')
    if not (isinstance(m, list) and m and all(s(x, 3) and x == x.lower() for x in m)): problems.append(f'{where}.match: a non-empty list of lowercase fragments (3+ chars)')

def card_ok(c, where):
    if not (s(c.get('front'), 3) and s(c.get('back'), 1)): problems.append(f'{where}: front and back required')
    elif len(c['front']) > 300 or len(c['back']) > 600: problems.append(f'{where}: too long for a card (front ≤ 300, back ≤ 600 chars)')

def mcq_ok(q, where):
    if not s(q.get('question'), 5): problems.append(f'{where}: question text missing')
    a = q.get('answers')
    if not (isinstance(a, list) and 2 <= len(a) <= 6 and all(s(x) for x in a) and len(set(a)) == len(a)): problems.append(f'{where}: answers must be 2-6 different, non-empty strings')
    ca = q.get('correct_answers')
    if not (isinstance(ca, list) and ca and all(isinstance(i, int) and 0 <= i < len(a or []) for i in ca)): problems.append(f'{where}: correct_answers must index answers')
    if not s(q.get('explanation'), 5): problems.append(f'{where}: explanation missing')

found = sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []
for f in found:
    path = os.path.join(cdir, f)
    if f not in ('flashcards.json', 'quiz.json', 'course.json'): problems.append(f'content/{f}: unknown file (allowed: flashcards.json, quiz.json, course.json)'); continue
    try: d = json.load(open(path))
    except Exception as e: problems.append(f'content/{f}: not valid JSON ({e})'); continue
    text_rules({k: v for k, v in d.items() if k != 'original_prompt'} if isinstance(d, dict) else d, f'content/{f}')   # the prompt is what's typed: curriculum names allowed there
    if f == 'flashcards.json':
        p = d.get('pack') if isinstance(d, dict) else None
        if not isinstance(p, dict): problems.append('content/flashcards.json: must be {"pack": {...}}'); continue
        pack_head(p, 'flashcards.pack')
        cards = p.get('cards') or []
        if not 6 <= len(cards) <= 30: problems.append(f'flashcards.pack has {len(cards)} cards (6-30)')
        for i, c in enumerate(cards): card_ok(c, f'flashcards.pack.cards[{i}]')
        if 'generateCard' in p: card_ok(p['generateCard'], 'flashcards.pack.generateCard')
    if f == 'quiz.json':
        p = d.get('pack') if isinstance(d, dict) else None
        if not isinstance(p, dict): problems.append('content/quiz.json: must be {"pack": {...}}'); continue
        pack_head(p, 'quiz.pack')
        qs = p.get('questions') or []
        if not 5 <= len(qs) <= 20: problems.append(f'quiz.pack has {len(qs)} questions (5-20)')
        for i, q in enumerate(qs): mcq_ok(q, f'quiz.pack.questions[{i}]')
        if 'generateQuestion' in p: mcq_ok(p['generateQuestion'], 'quiz.pack.generateQuestion')
    if f == 'course.json':
        st = d.get('structure') or {}
        nodes = st.get('nodes', [])
        if not s(d.get('course_title'), 3) or st.get('course_title') != d.get('course_title'): problems.append('course_title missing or differs from structure.course_title')
        if not s(d.get('original_prompt'), 5): problems.append('course.original_prompt missing')
        if st.get('error', None) is not None: problems.append('structure.error must be null (or left out: install sets it)')
        # a real Agent outline: 7-9 nodes, even if the reel only opens the first few (later nodes generate in parallel,
        # so the build takes no longer; nodes without authored content get a key-concept outline from the demo app)
        if not 7 <= len(nodes) <= 9: problems.append(f'course has {len(nodes)} nodes (7-9: plan a full course; author content for the ones the reel opens)')
        nc = d.get('node_content', {})
        bad = [k for k in nc if not (k.isdigit() and int(k) < len(nodes))]
        if bad: problems.append(f'node_content keys {bad} are not node positions ("0" … "{len(nodes) - 1}")')
        missing = [str(i) for i in range(min(3, len(nodes))) if str(i) not in nc]
        if missing: problems.append(f'node_content needs authored content for at least the first 3 nodes (missing {missing})')
        B = chr(96) * 3
        for ni, n in enumerate(nodes):
            subs = n.get('subnodes', []) if isinstance(n, dict) else []
            if not isinstance(n, dict) or not s(n.get('title'), 3) or not 1 <= len(subs) <= 4: problems.append(f'node {ni + 1}: title + 1-4 subnodes required')
            for si, sn in enumerate(subs):
                if not (s(sn.get('title'), 3) and isinstance(sn.get('key_concepts'), list) and sn['key_concepts'] and all(s(x) for x in sn['key_concepts'])):
                    problems.append(f'subnode {ni + 1}.{si + 1}: title + non-empty key_concepts (strings) required')
                et = sn.get('expected_tokens')   # optional: install fills 600 (the app's schema needs an integer >= 1; it's never shown)
                if et is not None and not (isinstance(et, int) and not isinstance(et, bool) and et >= 1): problems.append(f'subnode {ni + 1}.{si + 1}: expected_tokens must be an integer >= 1 (or left out)')
            if str(ni) not in nc: continue
            md = nc[str(ni)]
            parts = md.split('---BREAK SUBNODE---')
            if len(parts) != len(subs): problems.append(f'node {ni + 1}: {len(parts)} sections split by ---BREAK SUBNODE--- but {len(subs)} subnodes')
            for si, (part, sn) in enumerate(zip(parts, subs)):
                want = f'<subnode_title>{{{ni + 1}.{si + 1}: {sn.get("title")}}}</subnode_title>'
                if want not in part: problems.append(f'node {ni + 1} section {si + 1}: needs the heading "## {want}"')
                if len(part.strip()) < 300: problems.append(f'subnode {ni + 1}.{si + 1}: content is too thin (< 300 chars)')
            for kind, body in re.findall(B + r'(flashcard_deck|mcq_quiz)\n(.*?)\n' + B, md, re.S):
                try:
                    j = json.loads(body)
                    if kind == 'flashcard_deck': [card_ok(c, f'node {ni + 1} flashcard_deck') for c in j['cards']]
                    else: [mcq_ok(q, f'node {ni + 1} mcq_quiz') for q in j['questions']]
                except Exception as e: problems.append(f'node {ni + 1}: {kind} block is not valid JSON ({e})')
        es = d.get('editedStructure')
        if es is not None and [n.get('title') for n in es.get('nodes', [])[:len(nodes)]] != [n.get('title') for n in nodes]:
            problems.append('editedStructure must start with the same nodes as structure (or be left out)')

# a custom pack only shows up if the prompt typed on camera contains one of its match fragments
cap_path = os.path.join(plan_dir, 'capture.json')
cap = json.load(open(cap_path)) if os.path.exists(cap_path) else {}
typed = ' '.join(st.get('text', '') for st in cap.get('steps', []) if st.get('do') == 'type').lower()
for f, label in (('flashcards.json', 'flashcards'), ('quiz.json', 'quiz')):
    if f in found:
        try: m = json.load(open(os.path.join(cdir, f)))['pack'].get('match', [])
        except Exception: continue
        if m and not any(x in typed for x in m): problems.append(f'{label} pack: nothing typed in capture.json contains one of its match fragments {m[:5]} — the app would pick a different pack')

if problems:
    print('CONTENT PROBLEMS:'); [print('  -', p) for p in problems]; sys.exit(1)
print(f'content ok: {", ".join(found) or "none (uses the demo build’s own content)"}')
