# Song Analysis & Cut Grids

How a song becomes editing intelligence: beat grid, energy, sections, cut priorities, viral window, and the onset-locked cut grid. Everything here is librosa end to end — no aubio.

Bundled implementations: `scripts/choose_viral_window.py` (§2) and `scripts/build_onset_cut.py` (§3) in this skill. The full-song analysis producer (§1) is bundled in the companion `song-edit-analysis` skill as `scripts/analyze_song_for_editing.py`.

## 1. Full-song analysis (run once per song)

`analyze_song_for_editing.py <audio> --out <dir> [--sr 44100]` — librosa + sklearn. Core recipe:

- `librosa.load(sr=44100, mono=True)`; `beat.beat_track(hop_length=512, trim=False)` for tempo + beat times.
- Onset envelope `onset_strength`, normalized with a robust 5th–95th percentile min-max to [0,1].
- `rms` (frame_length 2048), `spectral_centroid`, `spectral_contrast`, `chroma_cqt`, `mfcc(13)`.
- Band energies from a 4096-pt STFT: **low 20–160 Hz, mid 160–2500 Hz, high 2500–12000 Hz**.
- Aggregate every feature per beat (mean over the beat interval; onset takes the per-beat MAX).

**Composite energy** (load-bearing):

```
energy = 0.45*rms + 0.25*low + 0.15*high + 0.15*onset      (each robust-normalized)
energy_smooth = median_filter(energy, size=5)
labels: >=0.78 peak | >=0.60 high | >=0.42 medium | >=0.24 low | else very low
```

**Per-beat cut priority** (drives which beats deserve cuts):

```
cut_priority = 0.40*transient + 0.25*energy + 0.20*(beat_in_bar==1) + 0.15*bass
recommended_cut: primary >=0.74 | secondary >=0.55 | hold
```

Bars estimated 4/4: `bar = beat//4 + 1`, `beat_in_bar = beat%4 + 1`.

**Sections**: KMeans (k=2..7, best silhouette) over `[energy_smooth, bass, high, brightness, onset, chroma(12), mfcc[:6], contrast(7)]` StandardScaler'd; labels median-filtered (5); boundaries on label change with min gap 4 beats. Each section gets a character description, footage-fit prose, and a cut strategy.

**Outputs** (per song, prefixed `{slug}_`): `_beats.csv` (the workhorse — every beat with all features + cut_priority + recommended_cut), `_cut_markers_30fps.csv` (non-hold beats with 30fps timecode — this is what renderers consume), `_sections.csv`, `_phrases.csv` (8-beat phrases), `_energy_timeline.png`, `_editing_guide.md` (human brief), `_agent_footage_brief.json` (structured selection spec for a downstream agent: sections with energy_level 1-5, clip_length_beats, cut_density, footage_types, selection/transition instructions), `_analysis.json`.

Energy ladder → clip length: L1 = 4-8 beats (atmosphere/holds) … L5 = 0.5-1 beat (peak, strongest footage, maximum density).

## 2. Viral window selection (which 15–30s of the song)

`choose_viral_window.py --audio X --transcript whisper.json --tiktok-start SEC --durations 15,22,30 --top 3`. Signals (SR 22050, hop 512):

- **Repetition** ("chorus-ness"): beat-synced chroma → cosine self-similarity matrix, zero the diagonal + first 8 off-diagonals (kills trivial neighbor similarity), row-mean, normalize. High = this harmony recurs = chorus.
- **Energy rise**: `post_mean(4s) − pre_mean(4s)` at each beat — finds build→drop.
- **Loop seam**: cosine similarity of `[chroma+mfcc]` 1s after the window end vs 1s after the start. High = invisible loop.
- **Lyric**: reward a transcript phrase starting within `[start−0.5, start+3.0]`, boosted by emotional-word count (love, miss, alone, heart, night, run, hold, you…).
- **Artist prior**: the artist's own TikTok start time, if known.

Anchors = top-4 repetition peaks + top-4 energy-rise beats + the prior, each snapped to the bar downbeat at/just before it (hook lands early). Score per (anchor × duration):

```
score = 0.26*energy + 0.20*repetition + 0.18*max(rise,0)*2.0 + 0.16*lyric + 0.12*loop_seam + 0.08*prior
```

Keep top windows overlapping <50% with each other. Output JSON+CSV with per-window component scores and the lyric line.

## 3. The onset-locked cut grid (v2 — the preferred cut engine)

Feedback-driven rule: cut on EVERY moment the song enables — hold when sparse, burst when busy. Never insert off-grid filler cuts; never skip sub-threshold onsets because a density preset said so.

```python
y, sr  = librosa.load(audio, sr=22050, mono=True)     # 22050 for all onset/FX work; 44100 only for the full-song analysis
env    = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
onsets = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=512,
                                    backtrack=False, delta=0.02, units="time")
```

- `delta=0.02` = catch everything — use for high-energy/drop lanes with a deep shot pool; use 0.03–0.04 when the lane wants moderate density or the pool is shallow.
- **Perceptual floor**: merge onsets closer than `MIN_GAP = 0.13s` (~4 frames @30), keeping the stronger. Iterate left→right comparing each onset against the last KEPT one (greedy), so chains like 0/0.10/0.20s resolve deterministically.
- **Quantize to frames**: `int(round((t - t0) * FPS))`; force a cut at frame 0; drop cuts within 2 frames of the end.
- **Accents**: onsets in the top quartile of strength (`np.percentile(strengths, 75)`) get a punch-in zoom.
- Needs deep shot pools (~60+ usable shots per video) or the rotation repeats visibly.
- Reference scale: a busy drop window yields ~63 cuts at 0.238s average.

## 4. Beat math and snapping (exact conventions)

- Fixed grid: `BEAT = 60/BPM`; `beats→frames = int(round(b * BEAT * FPS))`.
- **Snap estimated beats to real transients**: for each CSV beat time find the nearest detected onset; replace if within 0.06s (transients sit up to ~35ms off a steady-tempo grid).
- For style-switch/transform moments use **floor, not round** — `int(np.floor((t-t0)*FPS + 1e-6))` — so the change lands on the frame *containing* the transient, never after it.
- Assert your plan: e.g. the drop shot must land on its bar boundary within 0.02s. Author cut plans in beats, verify in seconds.

## 5. Envelope followers (drive continuous FX, not cuts)

The shared audio-reactivity core used by every renderer:

```python
y, sr = librosa.load(AUDIO, sr=22050, mono=True, offset=max(0, start-1.0), duration=dur+2.0)
env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
tt  = librosa.times_like(env, sr=sr, hop_length=512) - (1.0 if start >= 1 else 0)
e   = np.interp(np.arange(n_frames)/fps, tt, env)
e  /= np.percentile(e, 95) + 1e-6                 # normalize to 95th pct
# one-pole peak-hold: fast attack, exponential decay
decay = math.exp(-1/(fps*TAU))                    # TAU = 0.22–0.25 s
acc = 0; out[i] = acc = max(e[i], acc*decay)
np.clip(out, 0, 1.5)
```

The 1s pre-roll (`offset=start-1`) is subtracted back out so times align to the window. Beat *pulses* (punch-zoom/bloom/chroma pumps) are per-beat decays: `pulse += amp * exp(-(t-t_beat)/0.16)` with amp energy-weighted. Attack/release smoothing for RMS followers: `acc = x + (acc-x)*(a if x>acc else r)` with `a,r = exp(-1/(FPS*t_attack)), exp(-1/(FPS*t_release))`.

**Sync by construction**: any procedural/FX render must be generated against the exact same `--start/--dur` window (and, when applicable, the same `--cuts` list) as the edit, so FX pulses and cut boundaries share one envelope. Never render FX on a different window and hope it lines up.
