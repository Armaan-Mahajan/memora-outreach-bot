#!/usr/bin/env python3
"""
SQL for the outreach_reels history table (memora-outreach Supabase). Like pipeline/publish.py, this only prints SQL; the routine
runs it with its Supabase connector (execute_sql). Never hand-write these statements: captions and voice lines contain
apostrophes, and the quoting here is what keeps them intact.

  reel_sql.py sent <plans_dir> <summary.json>
      after stage 9: one row per delivered reel (status 'sent'). Re-running for the same date/reel number replaces the row.
  reel_sql.py verdict <date> <verdict.json>
      after Armaan's review. verdict.json:
        {"approved": [{"reel_no": 1, "caption": "...", "hashtags": ["#studytok", ..., "#memora"]}], "rejected": [2, 3]}
"""
import json
import os
import sys


def q(v):
    return 'NULL' if v is None else "'" + str(v).replace("'", "''") + "'"


def arr(vals):
    return "ARRAY[" + ", ".join(q(v) for v in vals) + "]::text[]" if vals else "'{}'::text[]"


def sent(plans_dir, summary_path):
    S = json.load(open(summary_path))
    date = S.get('date')
    if not date: sys.exit('summary.json has no date (run plan.sh finish first)')
    rows = []
    for r in S.get('reels', []):
        name = r.get('delivered_as')
        if not name: continue
        no = int(name.rsplit('reel ', 1)[1].split('.')[0])
        p = json.load(open(os.path.join(plans_dir, r['reel'], 'plan.json')))
        t = p.get('topic') or {}
        vo = ' '.join(l.get('text', '') for l in (p.get('vo') or {}).get('lines', []))
        rows.append('(' + ', '.join([q(date), str(no), q(name), q(p['slug']), q(p['feature']),
                                     q(t.get('slug')), q(t.get('subject')), q(t.get('level')), q((p.get('vo') or {}).get('voice')),
                                     q(p.get('hook')), q(p.get('format')), q(vo), q(r.get('seconds'))]) + ')')
    if not rows: sys.exit('no delivered reels in summary.json')
    print('insert into public.outreach_reels (run_date, reel_no, file_name, slug, reel_type, topic, topic_subject, topic_level, '
          'voice, hook, format_summary, vo_text, seconds)\nvalues\n  ' + ',\n  '.join(rows) +
          '\non conflict (run_date, reel_no) do update set file_name = excluded.file_name, slug = excluded.slug, '
          'reel_type = excluded.reel_type, topic = excluded.topic, topic_subject = excluded.topic_subject, '
          'topic_level = excluded.topic_level, voice = excluded.voice, hook = excluded.hook, '
          'format_summary = excluded.format_summary, vo_text = excluded.vo_text, seconds = excluded.seconds, status = \'sent\', '
          'caption = null, hashtags = \'{}\', decided_at = null\nreturning run_date, reel_no, reel_type, topic, status;')


def verdict(date, verdict_path):
    V = json.load(open(verdict_path))
    stmts = []
    for a in V.get('approved', []):
        tags = a.get('hashtags') or []
        if len(tags) != 5 or tags[-1].lower() != '#memora': sys.exit(f'reel {a.get("reel_no")}: exactly 5 hashtags, the last one #memora')
        if not (a.get('caption') or '').strip(): sys.exit(f'reel {a.get("reel_no")}: caption missing')
        stmts.append(f"update public.outreach_reels set status = 'approved', caption = {q(a['caption'])}, hashtags = {arr(tags)}, "
                     f"decided_at = now() where run_date = {q(date)} and reel_no = {int(a['reel_no'])};")
    for n in V.get('rejected', []):
        stmts.append(f"update public.outreach_reels set status = 'rejected', caption = null, hashtags = '{{}}', decided_at = now() "
                     f"where run_date = {q(date)} and reel_no = {int(n)};")
    if not stmts: sys.exit('verdict.json lists no reels')
    print('\n'.join(stmts) + f"\nselect reel_no, reel_type, status from public.outreach_reels where run_date = {q(date)} order by reel_no;")


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'sent': sent(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 4 and sys.argv[1] == 'verdict': verdict(sys.argv[2], sys.argv[3])
    else: sys.exit(__doc__)
