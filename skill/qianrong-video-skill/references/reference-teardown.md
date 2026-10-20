# Reference teardown — learning from a big-company promo

When a film is "missing something" and you can't name it, stop guessing and **take a reference
apart**. A great reference doesn't tell you what to copy; it tells you **which dial the good films
share a setting on**, so you know which dial is wrong on yours.

## The method: many passes, one question each

Watching once and forming an impression fails because eyes and ears can only track one thing at a
time. Read the subtitles and you stop hearing the beat. So go back **many times**, and each pass
asks exactly one question and writes down exactly one column. Then join the columns on the timeline.

This is the "multi-pass" part — not watching repeatedly, but **returning with a different question
each time**.

| Pass | Watch/listen with… | Writes down |
|---|---|---|
| 1 · Structure | sound off, normal speed | shot count, what each shot does, how long each lasts |
| 2 · Words | paused, stepping | every line that appears, in time order |
| 3 · Motion | slow motion | how each element enters/exits, fast or slow |
| 4 · Music alone | **screen off or not looking** | where the beats and accents are |
| 5 · Density | normal speed, counting | how many things change per second |
| 6 · Sound layers | audio only | how many layers; when the music gets out of the way |

**Pass 4 must be done separately.** The most common reason a cut "feels off the beat" is that it was
aligned while also watching the picture. Do one pass with **only the music**.

## Then measure, don't just describe

Impressions can't be acted on. Turn each pass into a number and compare against your own film.

Two measurements proved decisive on a real project, both cheap to run:

**1. Cut density and shot length.** Detect cuts as spikes in frame-to-frame difference, then report
shots/second and the shot-length spread.

```bash
python3 - <<'PY'
import subprocess, numpy as np
FPS, W, H = 12, 192, 108
def frames(f):
    raw = subprocess.run(['ffmpeg','-v','error','-i',f,'-vf',f'fps={FPS},scale={W}:{H}',
                          '-pix_fmt','gray','-f','rawvideo','-'], capture_output=True).stdout
    n = len(raw)//(W*H)
    return np.frombuffer(raw, np.uint8)[:n*W*H].reshape(n,H,W).astype(np.float32)/255
for f in ['reference.mkv','ours.mp4']:
    fr = frames(f); d = np.abs(np.diff(fr,axis=0)).mean(axis=(1,2))
    t = max(d.mean()+2.5*d.std(), 0.06)
    idx = np.where(d > t)[0]
    bounds = [0]+list(idx+1)+[len(fr)]
    lens = np.array([(b-a)/FPS for a,b in zip(bounds[:-1],bounds[1:]) if b-a >= FPS*0.2])
    internal = np.mean([np.median(d[a:b]) for a,b in zip(bounds[:-1],bounds[1:]) if b-a >= FPS*0.2])
    print(f"{f}: shots={len(lens)} avg={lens.mean():.2f}s med={np.median(lens):.2f}s "
          f"cut_rate={len(idx)/(len(fr)/FPS):.2f}/s internal_motion={internal:.4f}")
PY
```

**2. How the music actually drives the cut.** Detect beats with `librosa.beat.beat_track` and
measure each cut's distance to the nearest beat.

```bash
python3 - <<'PY'
import subprocess, numpy as np, librosa, warnings; warnings.filterwarnings('ignore')
raw = subprocess.run(['ffmpeg','-v','error','-i','reference.mkv','-ac','1','-ar','22050',
                      '-f','f32le','-'], capture_output=True).stdout
y = np.frombuffer(raw, np.float32)
tempo, beats = librosa.beat.beat_track(y=y, sr=22050, units='time')
print('tempo', float(np.atleast_1d(tempo)[0]), 'beats', len(beats))
# reuse the cut times from measurement 1, then:
# errs = [min(abs(c-b) for b in beats) for c in cuts]
# onbeat = (np.array(errs) < 0.06).mean()
PY
```

## What the numbers actually said (a real result worth knowing)

Four films measured with the same script — three big-company reference films and one in-house
film that "felt like it was missing something":

| Film (AI software products) | Shots | Avg shot | Cut rate | **Internal motion** |
|---|---|---|---|---|
| Anthropic · Opus 4.6 launch | 14 | 2.78s | 0.46/s | 0.0130 |
| OpenAI · GPT-6 launch | 31 | **2.26s** | 0.43/s | 0.0282 |
| Anthropic · Fable 5.1 launch | 25 | 3.36s | 0.41/s | 0.0289 |
| Anthropic · Cowork | 9 | 7.55s | 0.23/s | 0.0017 |
| OpenAI · Codex CLI | 27 | 7.20s | 0.13/s | 0.0080 |
| **Our film** | 10 | **5.95s** | **0.22/s** | **0.0042** |

Note the split: two of the five have **long shots** (7.2–7.6s) like ours. Shot length alone is not
the discriminator — but look at what they do *inside* those long shots. It is still 2–4× our
internal motion. The pattern is the same as with hardware films.

Two things fall out immediately, and neither is a matter of taste:

1. **Our shots are 2–3× too long and there are too few of them.** The references cut 2–3× more
   often. "Fast and jumpy" is not a style choice here — it is a **count**.
2. **Our internal motion is ~10× lower.** This is the real answer to "the motion still feels
   weak". It is not that our effects are wrong; it is that **within a shot, almost nothing moves**.
   A long shot with almost no internal movement reads as a still, no matter how nice the still is.

And on the beat question, measured on the same five AI-product films (distance from each cut to the
nearest detected beat):

| Film | BPM | Cuts | Median distance | within ±60ms |
|---|---|---|---|---|
| Anthropic · Opus 4.6 | 152 | 18 | 80ms | 39% |
| OpenAI · GPT-6 | 136 | 30 | 91ms | 30% |
| OpenAI · Codex CLI | 112 | 26 | 120ms | 27% |
| Anthropic · Fable 5.1 | 123 | 35 | 162ms | 17% |
| Anthropic · Cowork | 74 | 16 | 149ms | 12% |
| **Our film** | 144 | 13 | **47ms** | **54%** |

**Ours is the most tightly snapped of the six — and it's the one that "feels off."** So the
assumption "every cut must land exactly on a beat" is backwards. Cutting on music means using the
music as a bed and hitting accents selectively; a film that snaps *every* boundary to the pulse
reads as mechanical, which the viewer reports as "the beat sync isn't quite right" even though it is
mathematically exact. **Loosen the snapping; spend precision only on the moments that matter.**

> Both conclusions are the opposite of what eyeballing suggested. That is the point of the method:
> the numbers move the fix from "add more animation" to "shorten the shots and give each one
> internal movement", which are different edits.

## Rules for using references

- **Take apart at least 3, not 1.** One reference teaches you that company's style; three teach you
  which settings everyone shares — those are the actual rules.
- **Match the medium.** Hardware films (cinematic lighting, camera moves, materials) teach shots and
  pacing but not software-UI language. For a software demo, include at least one software reference.
- **Use the official cut.** A company's own CDN/press asset, not a re-upload — re-uploads are
  compressed and re-timed, which corrupts exactly the measurements above.
- **Keep them out of the deliverable.** References are for learning. They do not go in your film and
  do not get redistributed.
