import React from 'react'; import { Composition } from 'remotion'; import { Reel, FOOTAGE } from './Reel';
const dur = (f: string) => { const e = FOOTAGE[f].events.events; const t0 = e.find((x: any) => x.type === 'rec_start').t, t1 = e.find((x: any) => x.type === 'rec_end').t; return Math.floor((t1 - t0) * 30); };
// Full reels + 10 s frame-style previews (each frame paired with the content type it was designed for)
const PREVIEWS: [string, string][] = [['hook', 'agent'], ['browser', 'agent'], ['coldopen', 'agent'], ['steps', 'agent'],
  ['cinematic', 'agent'], ['prompt', 'agent'], ['challenge', 'quiz'], ['qhook', 'quiz'], ['stack', 'flash']];
export const Root: React.FC = () => <>
  <Composition id="Reel" component={Reel} durationInFrames={dur('agent')} fps={30} width={1080} height={1920} defaultProps={{ variant: 'browsersteps', footage: 'agent' }} />
  <Composition id="Quiz" component={Reel} durationInFrames={dur('quiz')} fps={30} width={1080} height={1920} defaultProps={{ variant: 'quizsteps', footage: 'quiz' }} />
  <Composition id="Flashcards" component={Reel} durationInFrames={dur('flash')} fps={30} width={1080} height={1920} defaultProps={{ variant: 'flashsteps', footage: 'flash' }} />
  <Composition id="Lesson" component={Reel} durationInFrames={dur('agent')} fps={30} width={1080} height={1920} defaultProps={{ variant: 'lesson', footage: 'agent' }} />
  <Composition id="Course" component={Reel} durationInFrames={dur('course')} fps={30} width={1080} height={1920} defaultProps={{ variant: 'coursesteps', footage: 'course' }} />
  <Composition id="CourseLesson" component={Reel} durationInFrames={dur('lesson')} fps={30} width={1080} height={1920} defaultProps={{ variant: 'lessonsteps', footage: 'lesson' }} />
  <Composition id="QuizFull" component={Reel} durationInFrames={dur('quizfull')} fps={30} width={1080} height={1920} defaultProps={{ variant: 'quizfullsteps', footage: 'quizfull' }} />
  <Composition id="FlashcardsFull" component={Reel} durationInFrames={dur('flashfull')} fps={30} width={1080} height={1920} defaultProps={{ variant: 'flashfullsteps', footage: 'flashfull' }} />
  {PREVIEWS.map(([v, f]) => <Composition key={v} id={`Preview-${v}`} component={Reel} durationInFrames={Math.min(300, dur(f))} fps={30} width={1080} height={1920} defaultProps={{ variant: v, footage: f }} />)}
</>;
