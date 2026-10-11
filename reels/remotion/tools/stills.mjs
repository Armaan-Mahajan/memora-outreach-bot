// stills.mjs <slug> <outDir> [chromeExecutable] — bundle once, then render one still per timeline segment
// (at 60% into each) plus the first frame after every voiceover line starts, for the planner's visual check.
import { bundle } from '@remotion/bundler';
import { selectComposition, renderStill } from '@remotion/renderer';
import fs from 'fs'; import path from 'path'; import url from 'url';
const [slug, outDir, chrome] = process.argv.slice(2);
const root = path.join(path.dirname(url.fileURLToPath(import.meta.url)), '..');
const R = JSON.parse(fs.readFileSync(path.join(root, 'src', 'reels', slug, 'resolved.json'), 'utf8'));
fs.mkdirSync(outDir, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.join(root, 'src', 'index.ts'), publicDir: path.join(root, 'public') });
const browserExecutable = chrome || null;
const comp = await selectComposition({ serveUrl, id: slug, inputProps: { R }, browserExecutable });
const shots = R.segments.map(s => ({ name: `seg-${s.id}`, t: s.start + 0.6 * (s.end - s.start) }));
for (const s of shots) {
  const frame = Math.min(comp.durationInFrames - 1, Math.round(s.t * 30));
  await renderStill({ composition: comp, serveUrl, frame, output: path.join(outDir, `${s.name}.jpg`), imageFormat: 'jpeg', jpegQuality: 85, inputProps: { R }, browserExecutable });
  console.log(`  still ${s.name} @ ${(frame / 30).toFixed(2)}s`);
}
