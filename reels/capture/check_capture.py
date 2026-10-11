# check_capture.py <capture_out_dir> — stepped capture: every frame is exactly 1/30 s, so smoothness holds by construction.
# Check the recording itself: the clip has the expected frame count, and the page wasn't frozen (a stuck page reuses nearly every frame).
import json, subprocess, sys
d = sys.argv[1]; c = json.load(open(f'{d}/capture.json'))
n = int(subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                        '-of', 'csv=p=0', f'{d}/clip.mp4'], capture_output=True, text=True).stdout.strip() or 0)
print(f"  {d.rstrip('/').rsplit('/', 1)[-1]}: {c['clip_s']}s, {c['frames']} frames ({c['screenshots']} screenshots, {c['reused']} reused), "
      f"slowest screenshot {c['slowest_screenshot_ms']} ms, recorded in {c['real_s']}s")
problems = []
if abs(n - c['frames']) > 1: problems.append(f'clip has {n} frames, recorder wrote {c["frames"]}')
if c['frames'] > 90 and c['screenshots'] < 0.1 * c['frames']: problems.append('the page barely changed (frozen page?)')
for p in problems: print('  PROBLEM:', p)
sys.exit(1 if problems else 0)
