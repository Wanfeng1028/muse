"""Generate a 15s, 120 BPM synthetic promo track (no copyright, no external samples).

Kick on every beat, hi-hat on every half-beat, bass pulse every 2 beats.
Last 4s (CTA hold) drops the hi-hat for a calmer tail.
Uses only Python stdlib (wave/math/random) so it runs anywhere.

Output: assets/bgm.wav (44100 Hz, 16-bit stereo)
"""
import math, random, struct, wave, os

SR = 44100
DUR = 15.0
BPM = 120.0
BEAT = 60.0 / BPM          # 0.5 s per beat
N = int(SR * DUR)

random.seed(7)

def kick(t):
    """Decaying 55 Hz sine, 0.28 s."""
    if t < 0 or t > 0.28:
        return 0.0
    return math.sin(2 * math.pi * 55 * t) * math.exp(-9 * t)

def hat(t):
    """Short noise burst, 0.035 s."""
    if t < 0 or t > 0.035:
        return 0.0
    return (random.random() * 2 - 1) * math.exp(-60 * t)

def bass(t):
    """Low pulse 110 Hz, 0.42 s, softer."""
    if t < 0 or t > 0.42:
        return 0.0
    return math.sin(2 * math.pi * 110 * t) * math.exp(-7 * t) * 0.5

def sample(t):
    beat_pos = t / BEAT
    bi = int(beat_pos)                    # beat index 0..29
    frac = beat_pos - bi
    v = 0.0
    # kick every beat
    v += kick(t - bi * BEAT) * 0.95
    # bass every 2 beats
    if bi % 2 == 0:
        v += bass(t - bi * BEAT) * 0.55
    # hi-hat every half beat, except during the 11-15s CTA tail
    if t < 11.0:
        half = int(beat_pos * 2)
        ht = t - half * (BEAT / 2)
        v += hat(ht) * 0.22
    return v

left = bytearray()
right = bytearray()
for i in range(N):
    t = i / SR
    s = sample(t)
    # gentle stereo widening: tiny delay on the right channel
    s_r = sample(t + 0.0008)
    vl = max(-1.0, min(1.0, s))
    vr = max(-1.0, min(1.0, s_r))
    left += struct.pack('<h', int(vl * 32767))
    right += struct.pack('<h', int(vr * 32767))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'bgm.wav')
os.makedirs(os.path.dirname(out), exist_ok=True)
with wave.open(out, 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(bytes(left + right))
print(f'wrote {out}  ({DUR}s, {BPM} BPM, stereo)')
