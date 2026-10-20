# Presenter mode — green-screen talks

Load this when the input is a to-camera video shot against a green screen (`style: presenter`). The
speaker is keyed out and stays on screen in the brand's background for the whole video, moving between
layouts while graphics build beside them. The core workflow in `SKILL.md` still runs every step; this
reference holds the presenter detail. The *Presenter* blocks in `scene-blocks.md` lay out each shot.

No green screen, or the keyer reports no usable screen? Fall back to `bookends`
(`references/face-bookends.md`).

---

## The brief: speaker position

Step 0's `position` input says where the speaker stands:

| `position` | What the edit does |
|---|---|
| `auto` (default) | you vary layouts under the pacing rules below |
| `bottom-right` / `bottom-left` | a `pip-br` / `pip-bl` corner bubble on every presenter shot |
| `left` / `right` | `split-left` / `split-right` on every presenter shot |
| `full` | `full` on every presenter shot |

Set it once in the composition, before the first `presenter()` call, and give presenter shots the
`auto` layout so the position wins; an explicit layout still overrides it for accents:

```js
presenterPosition("bottom-right");   // auto · bottom-right · bottom-left · left · right · full
presenter("auto", 10.3, 15.4);
presenter("close", 21.0, 23.5);      // close-ups and cutaways stay accents
```

**Pacing rules for `auto`:** the engine cycles split-left, pip-br, split-right, pip-bl, pip-tr,
pip-tl, so two presenter shots never share a layout back to back. Vary hold lengths (1–4s as usual),
and prefer a pip bubble over stepping the speaker out during most cutaways so they stay on screen.
Never fall into a fixed full → split → cutaway cycle.

## Keying (Step 2b)

```bash
python3 SKILL_DIR/scripts/key_greenscreen.py "$work" --preview 30 [--mask x,y,w,h …]
python3 SKILL_DIR/scripts/key_greenscreen.py "$work" [--mask x,y,w,h …] [--quality master]   # detached for long takes
```

- It measures the screen from the take and prints its colour and margin; a take with no usable
  screen fails with the reason, so fall back to `bookends`.
- **Look at `presenter-preview.png` first** and wait for a yes: hair, glasses and shoulders should
  have clean edges. `--over '#0b1410'` previews against a different background.
- With the vision setup (`setup.sh --vision`), the preview also flags a burned-in banner (a name
  tag) near the frame's edges and suggests a `--mask`; either way, a banner or logo burned into the
  recording needs a `--mask x,y,w,h` over it (repeatable, **source pixels** — masks are not affected
  by scaling or fps conversion). A mask that cuts a shoulder leaves a notch, which
  `presenterStyle({fade:"left"})` hides.
- **`--max-height <px>`** scales the take before keying (default 3840 = composition height × 2), so a
  4K take needs no manual ffmpeg downscale — never pre-scale the take yourself.
- **Any frame rate works:** every source is converted to 30 fps edit frames automatically. No user
  action; frame N of the edit is always `presenter/fNNNNN.webp`.
- Edge despill (green fringe removal) is automatic and needs no flag.
- With the vision setup, the speaker's face is measured across the take and recorded in `take.json`
  and `faces.js`, so presenter layouts frame an off-centre speaker. Everything works without it.
- The full run writes `presenter/fNNNNN.webp`, one per edit frame (~4 frames/s on 6 cores, so a
  6-minute take is about 45 minutes): tell the user, run it detached, and re-run the same command if
  it stops — it keys only frames whose WebP is missing or incomplete, and its workers stop when the
  parent dies, so a killed run never double-writes a frame.
- `--quality master` keeps full colour for the sharpest edges at about ten times the disk
  (`web`, the default, is ~70 KB/frame).

## Layouts (Step 4 and Step 6)

Every shot-list row names a layout:

| Layout | Use |
|---|---|
| `full` | the speaker centred, a tag or two-line headline beside their head |
| `split-left` (`split` is an alias) / `split-right` | speaker on one side, a panel building the point on the other; on tall and square canvases both stack the speaker at the bottom with the panel on top |
| `close` | punch in for a slam or a punchline, with a `hit()` on the key word |
| `pip-br` `pip-bl` `pip-tr` `pip-tl` | the speaker in a framed corner bubble in the kit's colours, over full-screen graphics — keep that corner clear |
| `cut` (`presenterOff(t)`) | a full-screen graphic, the speaker stepped out — prefer a pip bubble for most cutaways |
| `chapter("s12", t0, t1, "01", "Title")` | a chapter card for long talks; steps the speaker out for it |

Layouts are fractions of the frame, so the same shot list works on every canvas (landscape, vertical,
square, portrait). Where panels and headlines go for each layout — so they never cover the speaker —
is the layout table in the *Presenter blocks* section of `references/scene-blocks.md`. A layout may
hold 3–8s in a talk of several minutes as long as something in it moves; a Short still cuts every
1–4s.

Set the speaker's look once, then give every shot the layout from the shot list:

```js
presenterStyle({halo:true, fade:"left"});        // push:.03 adds a slow zoom, off by default: it softens footage
presenter("full", 0, 2.8);  shot("s01", 0, 2.8, "cut");
presenter("split", 2.8, 6.4); shot("s02", 2.8, 6.4); fromRight("#s02p", 2.85);
presenterOff(6.4);          shot("s03", 6.4, 10.3, "zoom");
chapter("s12", 58.0, 61.1, "01", "The patch was never<br>the bottleneck");
```

The *Presenter* blocks in `scene-blocks.md` show the panel, checklist, diagram and stamp pieces these
layouts use. `render.js check` (Step 7) flags any text sitting over the speaker's face.

---

## Failure states

| Symptom | Cause | Fix |
|---|---|---|
| `no screen to key` / `screen too dim or uneven to key` | not a green-screen take, or lit unevenly | use `bookends`, or re-light and re-record |
| A name banner in the keyed frame | burned into the recording | `--mask x,y,w,h` over it (the vision preview suggests one); source pixels |
| A notch in a shoulder | the mask cuts the speaker | widen the mask, or hide the edge with `presenterStyle({fade:"left"})` |
| Keying stopped part-way | time limit, killed shell | re-run the same command; it resumes |
| The speaker sits off-centre in layouts | an off-centre take, no vision setup | `setup.sh --vision`, then re-run the keyer so `faces.js` is written |
