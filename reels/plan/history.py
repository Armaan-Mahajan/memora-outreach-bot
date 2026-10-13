#!/usr/bin/env python3
"""
Reel history: what's been sent and posted, so posted content never repeats (REELS-RUNBOOK.md, stages 3, 9 and "After review").

Like pipeline/history.py, this never talks to Supabase itself. The routine runs two SELECTs with its Supabase connector, saves
each result as a JSON array of row objects, and passes the files in:

  reels.json   select run_date, reel_no, slug, reel_type, topic, topic_subject, topic_level, hook, format_summary, vo_text,
                      status, caption, created_at
               from outreach_reels order by created_at desc limit 400;
  drafts.json  select topic, headline, caption, created_at from outreach_drafts
               where created_at > now() - interval '120 days' order by created_at desc;

Subcommands:
  assign        today's reel types and topics (deterministic; don't override it)
                  history.py assign --reels reels.json --drafts drafts.json --topics topics.json --date 2026-10-14 [--n 3]
  check-plan    a plan's hook and voiceover against earlier reels of its type; exit 1 if it repeats one
                  history.py check-plan <plan_dir> <assignment.json>
  check-caption a caption against recent reel and single-image captions; prints flags (exit 0), rewrite if flagged
                  history.py check-caption <caption.txt> <assignment.json>

Rules (why each exists):
  - Types: the 3 types sent least recently (ties in TYPES order), so all six come round every two days.
  - Topics (agent / quiz / flashcards reels): never a topic posted (approved reel, or any single-image/slideshow draft) in the
    last 90 days, never one sent for review in the last 14 days (approved or not); least recently used first, never-used
    first of all, then topics.json order; levels alternate (upper / younger, "both" fits either); no two reels today share a
    subject, and subjects used in the last 3 days go last.
  - Angles: a plan fails if its hook matches an earlier reel's hook (normalized) or its voiceover shares too many words with
    an earlier reel of the same type (Jaccard ≥ 0.6 on word sets). Posted reels count for a year, unposted ones for 30 days.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

TYPES = ['agent', 'adaptive', 'quiz', 'overview', 'flashcards', 'autopilot']
TOPIC_LED = {'agent', 'quiz', 'flashcards'}
POSTED_TOPIC_DAYS, SENT_TOPIC_DAYS, RECENT_SUBJECT_DAYS = 90, 14, 3
POSTED_ANGLE_DAYS, SENT_ANGLE_DAYS = 365, 30
VO_SIMILARITY, HOOK_SIMILARITY, CAPTION_SIMILARITY = 0.6, 0.7, 0.6
RECENT_PER_TYPE = 15

STOP = set('a an the and or but of to in on at for with from by is are was be it its this that these those you your i my we our '
           'just so then than as into up out about how what why when it\'s'.split())


def day(s):
    return dt.date.fromisoformat(str(s)[:10]) if s else None


def norm(text):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', (text or '').lower())).strip()


def words(text):
    return {w for w in norm(text).split() if w not in STOP and len(w) > 1}


def jaccard(a, b):
    A, B = words(a), words(b)
    return len(A & B) / len(A | B) if A and B else 0.0


def load(p):
    if not p or not os.path.exists(p) or not open(p).read().strip(): return []
    d = json.load(open(p))
    return d if isinstance(d, list) else d.get('rows', d.get('result', []))


# ── assign ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def assign(args):
    today = dt.date.fromisoformat(args.date)
    reels, drafts = load(args.reels), load(args.drafts)
    topics = [t for t in json.load(open(args.topics))['topics'] if t.get('archetype') != 'technique']
    by_slug = {t['slug']: t for t in topics}

    # types: least recently sent first
    last_sent = {t: None for t in TYPES}
    for r in reels:
        d = day(r.get('run_date'))
        if r.get('reel_type') in last_sent and d and (last_sent[r['reel_type']] is None or d > last_sent[r['reel_type']]):
            last_sent[r['reel_type']] = d
    order = sorted(TYPES, key=lambda t: (last_sent[t] or dt.date.min, TYPES.index(t)))
    types = sorted(order[:args.n], key=TYPES.index)

    # topic usage
    last_posted, last_sent_topic, recent_subjects = {}, {}, set()
    def bump(m, k, d):
        if k and d and (k not in m or d > m[k]): m[k] = d
    for r in reels:
        d = day(r.get('run_date'))
        bump(last_sent_topic, r.get('topic'), d)
        if r.get('status') == 'approved': bump(last_posted, r.get('topic'), d)
        if d and (today - d).days <= RECENT_SUBJECT_DAYS and r.get('topic_subject'): recent_subjects.add(r['topic_subject'])
    for r in drafts:   # single-image / slideshow posts count as posted
        bump(last_posted, r.get('topic'), day(r.get('created_at')))
    def eligible(t):
        lp, ls = last_posted.get(t['slug']), last_sent_topic.get(t['slug'])
        return not (lp and (today - lp).days < POSTED_TOPIC_DAYS) and not (ls and (today - ls).days < SENT_TOPIC_DAYS)
    def lru_key(t):
        used = max([d for d in (last_posted.get(t['slug']), last_sent_topic.get(t['slug'])) if d] or [dt.date.min])
        return (used, t['subject'] in recent_subjects, topics.index(t))
    pool = sorted([t for t in topics if eligible(t)], key=lru_key)

    # level to start from: the opposite of the most recent topic-led reel's level
    last_level = next((r.get('topic_level') for r in sorted(reels, key=lambda r: str(r.get('created_at') or ''), reverse=True)
                       if r.get('reel_type') in TOPIC_LED and r.get('topic_level') in ('upper', 'younger')), None)
    want = 'younger' if last_level == 'upper' else 'upper'

    out, used_subjects, problems = [], set(), []
    for i, ty in enumerate(types, 1):
        entry = {'reel_no': i, 'type': ty, 'slug_prefix': f'r{i}-', 'topic': None}
        if ty in TOPIC_LED:
            pick = (next((t for t in pool if t['subject'] not in used_subjects and t.get('level') in (want, 'both')), None)
                    or next((t for t in pool if t['subject'] not in used_subjects), None))
            if not pick:
                problems.append(f'reel {i} ({ty}): no eligible topic left in topics.json — add topics or relax the windows')
            else:
                pool.remove(pick); used_subjects.add(pick['subject'])
                entry['topic'] = {k: pick.get(k) for k in ('slug', 'subject', 'topic', 'level', 'safe_for', 'notes')}
                lvl = pick.get('level'); want = 'younger' if (lvl == 'upper' or (lvl == 'both' and want == 'upper')) else 'upper'
        out.append(entry)

    recent = {t: [] for t in TYPES}
    for r in sorted(reels, key=lambda r: str(r.get('created_at') or ''), reverse=True):
        t = r.get('reel_type')
        if t in recent and len(recent[t]) < RECENT_PER_TYPE:
            recent[t].append({k: r.get(k) for k in ('run_date', 'status', 'topic', 'hook', 'format_summary')})
    result = {'date': args.date, 'reels': out, 'problems': problems,
              'recent_by_type': {t: recent[t] for t in types},     # read these before planning: take a different angle
              # for the checks (check-plan / check-caption):
              '_history': [{k: r.get(k) for k in ('run_date', 'reel_type', 'status', 'hook', 'vo_text', 'caption', 'slug', 'topic')} for r in reels],
              '_draft_captions': [{'headline': r.get('headline'), 'caption': r.get('caption'), 'created_at': r.get('created_at')} for r in drafts[:60]]}
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False, default=str)
    print(file=sys.stderr)
    for e in out:
        print(f"  reel {e['reel_no']}: {e['type']}" + (f" — {e['topic']['topic']} ({e['topic']['subject']}, {e['topic']['level']})" if e['topic'] else ''), file=sys.stderr)
    for p in problems: print('  PROBLEM: ' + p, file=sys.stderr)
    return 1 if problems else 0


# ── check-plan ───────────────────────────────────────────────────────────────────────────────────────────────────────
def check_plan(args):
    plan = json.load(open(os.path.join(args.plan_dir, 'plan.json')))
    A = json.load(open(args.assignment))
    today = dt.date.fromisoformat(A['date'])
    problems = []
    slug = plan.get('slug', '')
    m = re.match(r'r(\d+)-', slug)
    entry = next((e for e in A['reels'] if m and e['reel_no'] == int(m.group(1))), None)
    if not entry: problems.append(f'slug "{slug}" must start with r<n>- for one of today\'s reels ({", ".join(e["slug_prefix"] for e in A["reels"])})')
    else:
        if plan.get('feature') != entry['type']: problems.append(f'reel {entry["reel_no"]} is assigned type "{entry["type"]}", the plan says "{plan.get("feature")}"')
        if entry['topic'] and (plan.get('topic') or {}).get('slug') != entry['topic']['slug']:
            problems.append(f'reel {entry["reel_no"]} is assigned topic "{entry["topic"]["slug"]}": set plan.topic.slug to it (and teach that topic)')
    hook = plan.get('hook') or ''
    vo = ' '.join(l.get('text', '') for l in (plan.get('vo') or {}).get('lines', []))
    for r in A.get('_history', []):
        d = day(r.get('run_date'))
        if not d or r.get('slug') == slug and d == today: continue
        window = POSTED_ANGLE_DAYS if r.get('status') == 'approved' else SENT_ANGLE_DAYS
        if (today - d).days > window: continue
        label = f'{r.get("run_date")} {r.get("reel_type")} reel ({r.get("status")})'
        if hook and r.get('hook') and (norm(hook) == norm(r['hook']) or jaccard(hook, r['hook']) >= HOOK_SIMILARITY):
            problems.append(f'hook repeats the {label}: "{r["hook"]}" — find a different hook')
        if r.get('reel_type') == plan.get('feature') and r.get('vo_text'):
            s = jaccard(vo, r['vo_text'])
            if s >= VO_SIMILARITY: problems.append(f'voiceover is {s:.0%} the same words as the {label} — take a different angle, not a rewording')
    if problems:
        print('REPEATS AN EARLIER REEL'); [print('  - ' + p) for p in problems]; return 1
    print('history ok (no repeat of an earlier reel)')
    return 0


# ── check-caption ────────────────────────────────────────────────────────────────────────────────────────────────────
def check_caption(args):
    cap = open(args.caption_file).read()
    A = json.load(open(args.assignment))
    flags = []
    first = norm(cap.split('\n')[0])
    for r in [x for x in A.get('_history', []) if x.get('caption')] + A.get('_draft_captions', []):
        other = r.get('caption') or ''
        if not other: continue
        s = jaccard(cap, other)
        if s >= CAPTION_SIMILARITY or (first and first == norm(other.split('\n')[0])):
            flags.append({'against': other.split('\n')[0][:90], 'score': round(s, 2)})
    print(json.dumps({'flagged': bool(flags), 'similar_to': flags}, indent=1, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('assign'); a.add_argument('--reels'); a.add_argument('--drafts'); a.add_argument('--topics', required=True)
    a.add_argument('--date', required=True); a.add_argument('--n', type=int, default=3)
    c = sub.add_parser('check-plan'); c.add_argument('plan_dir'); c.add_argument('assignment')
    k = sub.add_parser('check-caption'); k.add_argument('caption_file'); k.add_argument('assignment')
    args = ap.parse_args()
    return {'assign': assign, 'check-plan': check_plan, 'check-caption': check_caption}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
