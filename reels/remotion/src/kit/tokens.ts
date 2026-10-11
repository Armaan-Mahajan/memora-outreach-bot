// Brand tokens + frame geometry shared by every reel. Generated reel code should use these, not invent colors.
export const FPS = 30;
export const FRAME = { w: 1080, h: 1920 };
// Instagram overlays its own UI: keep text out of the top ~220 px and bottom ~330 px (caption, buttons, username).
export const SAFE = { top: 220, bottom: 1590, left: 60, right: 1020 };
export const C = {
  bg: '#000000', ground: '#0a0a0c', panel: '#141418', panelHi: '#1c1c21', line: '#27272a', lineSoft: '#ffffff1f',
  text: '#fafafa', textSoft: '#e4e4e7', muted: '#a1a1aa', faint: '#52525b',
  violet: '#8b5cf6', violetL: '#a78bfa', blue: '#3b82f6', blueL: '#60a5fa', green: '#34d399', red: '#f87171',
};
export const GRAD = `linear-gradient(90deg, ${C.violetL}, ${C.blueL})`;
export const FONT = 'Geist, sans-serif';
// Type scale (px at 1080 wide). Headlines 72–96, body 44–56, labels 26–32. Nothing under 26 px: it's unreadable on a phone.
export const TYPE = { hero: 96, h1: 80, h2: 64, body: 50, small: 36, label: 28 };
