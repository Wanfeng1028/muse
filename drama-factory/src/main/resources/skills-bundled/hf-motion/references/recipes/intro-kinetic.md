# Recipe: intro-kinetic

A 15 s kinetic-typography self-introduction, 1920x1080 @ 30 fps, cut on a
120 BPM grid. Paper / charcoal / one accent colour, one Korean display face
(NanumSquare ac ExtraBold). Default `CONFIG` = the original author's values
and reproduces the verified render frame for frame.

## Parameters

Every key is a top-level `CONFIG` key; pass it as `key=value`.

| Key | Type | Default | Limit / note |
|-----|------|---------|--------------|
| `title` | text | `윤병우 자기소개` | document title only (not on screen); when `name=` is passed without `title=`, it becomes `<name> 자기소개` |
| `name` | text | `윤병우` | scene 1 slam, 300 px; shrinks to fit 1600 px |
| `team` | text | `AX/PI팀` | scene 1 subtitle |
| `employer` | text | `삼성 시니어 엔지니어` | scene 2 title line |
| `years` | integer | `23` | 0..999, counted up from 0 |
| `yearsUnit` | text | `년차` | unit after the number |
| `subsLabel` | text | `유튜브 구독자` | scene 3 title line |
| `subsTarget` | integer | `195000` | count-up target |
| `subsFormat` | `ko` \| `comma` | `ko` | `ko` shows 만/천 (needs >= 1000; `123000` -> `12만 3천`); `comma` shows `123,000` |
| `subsDisplay` | text | empty | optional final text after the count lands (e.g. `12.3만+`); empty = formatted target |
| `toolsLabel` | text | `직접 만든 [AI] 도구` | `[...]` = accent colour |
| `tools` | list | `AutoKliq\|Second Brain` | **1..3** items; even items slide in, odd items slam in accent; 3 items drop to 170 px |
| `flash` | list | `시간\|돈\|감정\|자유` | **2..8** words, one per beat; backgrounds cycle accent / paper / charcoal |
| `finale` | list | `실리콘밸리 개발자가 알려주는\|[시간, 돈, 감정]에서\|[자유]로워지는 법` | **1..4** lines, one every two beats; first line is the small lead when there are 2+; `[...]` = accent |
| `paper` | `#rrggbb` | `#f2eee6` | light |
| `charcoal` | `#rrggbb` | `#1e1e1e` | dark |
| `red` | `#rrggbb` | `#e5322d` | accent; must keep 3:1 contrast on both others (the scaffold refuses otherwise) |
| `bpm` | number | `120` | **90..150** |

## Timeline (beats; `B = 60 / bpm`, T/F/L = item counts)

| Scene | Length (beats) | Default (s) | On the beats |
|-------|----------------|-------------|--------------|
| s1 name | 4 | 0.0-2.0 | 0 name slam + shake · 1 bar · 2 subtitle · bar fills frame into the cut |
| t12 | 0.5 | 2.0-2.25 | red panel lifts away |
| s2 employer + years | 4 | 2.0-4.0 | 0 title · 0.5 number row · 1 count (0.9 s) · 2 unit + pulse · paper iris into the cut |
| s3 subscribers | 4 | 4.0-6.0 | 0 title · 1 count (1.0 s) · 3 pulse · charcoal block rises into the cut |
| s4 tools | 2 + 2T | 6.0-9.0 | 0 label · 2, 4, 6 tools · accent bar sweeps into the cut |
| s5 flash | F | 9.0-11.0 | one word per beat · charcoal slab drops into the cut |
| s6 finale | 2L + 2 | 11.0-15.0 | 0, 2, 4, 6 lines · hold |

Total = `16 + 2T + F + 2L` beats (default 30 = 15.0 s). Covers always end on
the cut (`sceneEnd - 0.25 s`, flash slab `- 0.2 s`); entrance tween lengths are
fixed in seconds. SFX: impact at 0 and at the finale, whoosh 0.3 s before each
of the four cuts into s2..s5. Music: kick every beat, booms on beat 0 and the
finale, kick/clap/bass dropped on the beat before the finale, stabs silent and
a noise riser across s5, chord on the finale impact, 0.5 s fade.

## Adapting scene count and duration

- More or fewer tools / flash words / finale lines: pass the list; the scaffold
  recomputes every scene window, the total and the music bed.
- A target length: pick counts and `bpm` so `(16 + 2T + F + 2L) * 60 / bpm`
  lands where you want, e.g. T=2, F=3, L=3 is 29 beats -> `bpm=116` gives 15.0 s.
- Root `data-duration` and `<audio>` timing are read by the engine **before
  scripts run** (the producer parses `<audio data-start>` from the HTML text),
  so they are static attributes the scaffold writes. Never edit them by hand.
- Fixed scenes (s1-s3 lengths, the 4 whooshes) are part of the skeleton.
  Changing those is a template change in this repo, not a parameter.

## Known pitfalls (from the original build)

- **CDN GSAP fails behind the corporate proxy.** The template loads
  `assets/vendor/gsap.min.js`; the scaffold copies it from the official
  hyperframes plugin. Never switch back to a CDN URL.
- **Korean tofu.** The face is bundled (`assets/fonts/NanumSquare_acEB.ttf`,
  SIL OFL 1.1, licence beside it) and `snapshot` must report `Fonts: 1 loaded`.
  A system fallback font renders differently in render vs preview.
- **Lint sub-composition warnings are accepted** (see `verification.md`): the
  recipe is a single file on purpose so one `CONFIG` drives everything.
- **Flash panels stack.** Each word's panel hides the previous one on its beat;
  without that, `check` reports `content_overlap` and a 1:1 contrast failure.
- **Contrast is not audited under a moving cover.** Each scene-exit panel
  (bar, lift, iris, block, sweep, slab) sets `data-layout-ignore` on the
  scene's text while it is mid-move: check's contrast pass takes the median
  pixel of the text box, so text half under the paper iris read as paper on
  paper (`#s2-title` / `#s2-unit 1:1` at `bpm=132`, t=3.662s). Holds are
  audited as usual.
- **Mask reveal infos.** `container_overflow` on `.mask` children during the
  slide-in is the effect, not a bug.
- **Width fit is estimated**, not measured (per-glyph em widths), and only
  shrinks. Very long words still need a look at the snapshot.
