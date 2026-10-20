# Sound

Recorded or licensed audio only: never default to synthesized beeps or procedural jingles.

## Licences (recorded in `library/catalog.json` per asset)

- **Mixkit music** (Free License): social posts, YouTube, ads; not TV/radio broadcast, CDs/DVDs, games or music-only remixes. Editing a track under a film is fine. YouTube Content ID claims: forward to team@mixkit.co.
- **Mixkit SFX** (Free License): any video use, no attribution.
- **Kenney packs**: CC0.
- Downloads: `studio.py fetch` uses plain HTTP with a browser User-Agent. Chrome's ad blocker blocks assets.mixkit.co, so don't try to fetch through the browser. Pexels refuses non-browser downloads.

## Choosing the track

1. `studio.py search music <category>` (house, downtempo, hip-hop, corporate, cinematic…), then `fetch music <id>` for 3–4 candidates. Fetching measures each one.
2. Read the bar-loudness map from `measure`: an intro, a build, a drop (+6 dB or more), a groove, a breakdown (−8 dB or so), a return. Tracks that sit flat are hard to cut a story to.
3. Map the chain onto the sections: the problem over the sparse intro or build; the turn on the drop; the quiet or shaping part on the breakdown; the punchline on the return; the handoff on the ring-out.
4. **The film runs at the track's measured bpm.** Set `K.setup({bpm})` to the catalog value exactly (`library` prints it, e.g. 134.003); never time-stretch the song. The film's length is a whole number of bars.

`measure` corrects the downbeat automatically: product-film's `beats.py` found Cat Walk's grid perfectly but put the downbeat two beats early, and section changes happen on downbeats. It prints the shift; if it's non-zero on a track with a loose grid (spread over ~6 ms), confirm by ear before trusting it.

## sound.py

```python
m = A.Mix(Path(__file__).parent); b = m.b
m.music("mixkit-371", [(7, 10), (11, 15), (15, 21), (31, 33), (47, 49), (59, 61)])   # song bars → film bars, back to back
m.bed("mixkit-1213", [(b(7), b(13, 1.5), 1.0)], gain=0.55)                           # forest bed under the walk
m.put(A.asset("mixkit-1113"), b(0, 1), 0.5)                                           # a click on a tab, on its beat
steps = A.single_hits("mixkit-1230", "mixkit-1214")                                    # single footsteps from recordings
m.put(A.asset("impactSoft_heavy_003"), b(7) + 0.22, 0.7)                              # a lid shutting (Kenney)
m.master()                                                                             # two-pass loudnorm −14 LUFS / −1.5 dBTP
```

- `put` lands each clip's measured peak on the cue, so a sound is on the frame even when the file starts with silence.
- One sound per meaningful event, not every animation. Music gain ~0.8; cues 0.2–0.6; beds 0.4–0.6.
- The last ~1.4 s of the music fades (`m.music(..., fade_out=1.4)`) and `master()` fades the final 0.8 s, so the final card sits on a fade. End on a ring-out segment, or pass `fade_out=0` if the card needs full level.
- Every cue time reads the same constants as the picture (`b(bar, beat)` and the film's named times). Move a picture event and move its cue.
- Vary repeated sounds: cycle a list of footsteps or taps, jitter gain ±15%, alternate the pan.
- The sound palette is part of the ledger row: the next film uses different foley, not the same clicks.

## Long-form UI sounds

The channel owner's rule (2026-10-15): professional sounds only, free and cleared for commercial use, recorded or AI-generated. Record the licence in `catalog.json` for every clip; a clip without one doesn't ship.

`longform.py mix` places UI sounds from the timeline (longform.md, UI sounds). To replace a drawn kind with recordings: fetch 2–4 clips per kind (`studio.py fetch sfx <id>`; search words: buzz "phone vibration", ping "message notification" or "soft notification", pin "paper" or "pin board", thud "stamp" or "rubber stamp"), then add `"role": "<kind>"` to each clip's entry under `sfx` in `catalog.json`. Pick short single hits (under about 0.6 s, since the transient is searched for in the first 0.6 s), or cut them first. Mixkit can't be reached from the cloud container or the desktop app's shell; fetch on the owner's Mac through a Remote Control session and stage the files into the container.

Clips found elsewhere (Openverse, Freesound, a pack) come in as a staged folder: `<dir>/<kind>/<file>.wav` plus `manifest.json`, a list of {kind, file, source, upstream, title, creator, licence, licence_url, source_page, duration_s, attribution}, and optionally earshot's `ranking.json`. `studio.py import-sfx <dir>` copies them to `<library>/sfx/<source>/<kind>/` and catalogues each with its licence, creator, attribution and earshot score as a candidate for its kind (`"candidates": [<kind>]`; a file staged under two kinds is one entry with both). It refuses any licence marked NC, ND or SA, and any clip whose source or licence says it was generated in code (a synthesised beep is a drawn sound, which the owner ruled out). A candidate is not played until it has the role, so `studio.py audition` builds a page with every candidate per kind (publish it as a private artifact), the owner picks by ear, and `studio.py role <id> <kind>` (or `--clear`) records the pick. `--roles N` on import gives earshot's top N the role straight away as a provisional pick; earshot is a first pass, not a judge (it heard ping winners as a "success chime"). Mix cuts a recording to the time its kind may ring (`SFX_MAX` in longform.py: buzz 0.9 s, ping 1.2 s, pin 0.4 s, thud 0.8 s, whoosh 1.0 s) with a short fade, so a 3 s vibration loop plays as one buzz. The drama foley kinds have their own limits (gavel 3 s, glass-break and door 2 s, slap and paper-slap 0.8 s; the rest 1 to 3 s). Ambience kinds such as rain-glass and crowd-murmur are played as a segment's `bed`, looped and never cut (longform.md). There is no code-drawn fallback for any foley kind: a kind with no recorded clip stays silent. The audition page plays the whole file.

Every clip mix plays is written to `out/sounds_used.json`. `longform.py credits <film>` turns it into `out/credits.txt`, the attribution lines for every CC BY clip, for the video description. It stops on a used clip with no licence. CC0, Mixkit and Kenney need no line.

A clip with `"role": "whoosh"` plays at each chapter start by default (`--whoosh <id|file>` picks another, `--no-whoosh` turns it off). `pop` clips are catalogued but nothing in the timeline places them yet.

Still open for long-form sound, in order: drama foley (slap, gavel, glass, door) for the K-drama channel; a sound for counters and bars landing; checking each sound's level against the bed so none masks a word; varied clips per film so one channel's films don't share every click.

## Where sounds came from so far

| Event | Asset |
|---|---|
| tab/mouse clicks | mixkit-1113, mixkit-2997, mixkit-1111 |
| key presses, typing, backspace | mixkit-2541, mixkit-2531, mixkit-2539 |
| forest bed, footsteps | mixkit-1213, mixkit-1230, mixkit-1214 |
| whooshes | mixkit-1490, mixkit-1489 |
| siren, horn, crowd | mixkit-1652, mixkit-1654, mixkit-3022 |
| soft/wood/heavy impacts | Kenney impact-sounds (impactSoft_*, impactWood_*) |
