# Placeholder music bed + UI sound effects, synthesised (no licensing question).
# The real bed will come from a free library later; SFX may stay synthesised.
import numpy as np, wave, os
SR = 48000; rng = np.random.default_rng(7); OUT = os.path.join(os.path.dirname(__file__), '..', 'public', 'audio'); os.makedirs(OUT, exist_ok=True)
def save(name, x, peak=0.89):
    x = np.atleast_2d(x); x = np.vstack([x, x]) if x.shape[0] == 1 else x
    x = x / (np.max(np.abs(x)) + 1e-9) * peak
    with wave.open(os.path.join(OUT, name), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((x.T * 32767).astype('<i2').tobytes())
def lpf(x, fc, o=2):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR); X /= np.sqrt(1 + (f / fc) ** (2 * o)); return np.fft.irfft(X, len(x))
def hpf(x, fc, o=2):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR) + 1e-9; X /= np.sqrt(1 + (fc / f) ** (2 * o)); return np.fft.irfft(X, len(x))
n2f = lambda n: 440 * 2 ** ((n - 69) / 12)
# bed: soft pad + gentle pluck arpeggio, 40 s, lowpassed so it never fights the voice
dur = 40; t = np.arange(SR * dur) / SR; L = np.zeros_like(t); R = np.zeros_like(t)
chords = [[48, 55, 59, 62, 64], [45, 52, 55, 60, 64], [41, 48, 52, 57, 60], [43, 50, 55, 59, 62]]
beat = 60 / 88; clen = 8 * beat
for k in range(int(dur / clen) + 1):
    ch = chords[k % 4]; s0 = k * clen; m = (t >= s0) & (t < s0 + clen + 2); tt = t[m] - s0
    env = np.minimum(1, tt / 1.5) * np.clip((clen + 2 - tt) / 2, 0, 1)
    for j, n in enumerate(ch):
        f = n2f(n); ph = rng.random() * 6.28
        v = (np.sin(2 * np.pi * f * tt + ph) + 0.3 * np.sin(4 * np.pi * f * tt + ph)) * env * 0.16
        w = np.sin(2 * np.pi * f * 1.004 * tt + ph + 1) * env * 0.10
        L[m] += v + (w if j % 2 else 0); R[m] += v + (0 if j % 2 else w)
    for i in range(16):
        n = ch[[0, 2, 4, 3, 1, 4, 2, 3][i % 8]] + 12; st = s0 + i * beat / 2; mm = (t >= st) & (t < st + 1.4); tt = t[mm] - st
        p = np.sin(2 * np.pi * n2f(n) * tt) * np.exp(-tt * 4) * 0.08; pan = 0.5 + 0.3 * np.sin(i * 1.3); L[mm] += p * (1 - pan); R[mm] += p * pan
L = hpf(lpf(L, 2200), 90); R = hpf(lpf(R, 2200), 90); fade = np.minimum(1, t / 2) * np.minimum(1, (dur - t) / 3)
save('bed.wav', np.vstack([L * fade, R * fade]), 0.7)
ex = lambda n, tau: np.exp(-np.arange(n) / SR / tau)
n = int(SR * .06); tt = np.arange(n) / SR
save('click.wav', hpf(lpf(rng.standard_normal(n), 5000), 800) * ex(n, .004) + .5 * np.sin(2 * np.pi * 1500 * tt) * ex(n, .008))
n = int(SR * .045); tt = np.arange(n) / SR
save('key.wav', hpf(lpf(rng.standard_normal(n), 3500), 600) * ex(n, .003) + .25 * np.sin(2 * np.pi * 700 * tt) * ex(n, .005), 0.8)
n = int(SR * 1.8); tt = np.arange(n) / SR
save('done.wav', sum(np.sin(2 * np.pi * n2f(m) * np.clip(tt - d, 0, None)) * np.exp(-np.clip(tt - d, 0, None) * 2.8) * (tt >= d) * a for m, d, a in ((76, 0, 1), (83, .09, .8), (88, .18, .5))), 0.8)
print('audio ok')
# soft keys v3: phone-speaker-audible but soft — mid "tap" (380-520 Hz body) + band-limited 900-2600 Hz click, no hiss above 3 kHz
for v in range(4):
    r = np.random.default_rng(100 + v); n = int(SR * .06); tt = np.arange(n) / SR
    body = np.sin(2 * np.pi * (390 + 40 * v) * tt) * ex(n, .007)
    top = lpf(hpf(r.standard_normal(n), 900), 2400 + 100 * v) * ex(n, .0022) * .7
    x = lpf(body * .8 + top, 3000); x *= np.minimum(1, tt / .0006)
    save(f'softkey{v+1}.wav', x, 0.7)
