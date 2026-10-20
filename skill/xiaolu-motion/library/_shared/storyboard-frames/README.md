# storyboard-frames

The storyboard-preview toolkit behind `SKILL.md`'s "第三步:分镜样帧" step: render a handful of individual
storyboard keyframes as PNG stills — a specific timestamp of the real presenter footage, composited with
the planned graphics for that shot — so a director/agent can approve composition, color, and timing
*before* committing to a full render. A second tool assembles a set of already-rendered stills into one
overview contact-sheet image for reviewing the whole storyboard at a glance.

This is macOS-only (one tool is a compiled Swift/Apple Vision binary) and is ported, with path patches,
from one real video's production pipeline (`05_visual/storyboard_v2/` in that project) — it is not a
polished, general-purpose library. See "What's project-specific vs. reusable" below before assuming it
drops into a different project unchanged.

**This toolkit does not read this repo's `timeline/schema.json` / `SCHEMA.md` storyboard format.** It
predates that schema and uses its own, older, unrelated input shape (a rough-cut edit-decision list plus
hardcoded per-shot Python functions — see "Quick start"). Don't assume compatibility with `timeline/resolve.py`
or anything else that consumes `schema.json`.

## What this is

Six files, three of which are runnable CLI steps and three of which are libraries the CLI steps import:

| File | Role | Depends on |
|---|---|---|
| `timeline.py` | **Frame-mapping authority.** Loads a rough-cut edit-decision list, splices in three "finished-demo" inserts, and exposes `v2_to_src()` / `src_to_v2()` / `rough_to_v2()` to convert between the final ("v2") timeline and source-footage frame numbers. Also holds `KEYFRAMES` — the hardcoded per-shot timestamps this whole toolkit renders. Not a CLI; everything else imports it. | Your cut-plan JSON, raw footage, demo clips (see env vars) |
| `extract_frames.py` | **Step 1 (CLI).** Pulls the exact source frames behind every keyframe in `timeline.KEYFRAMES`, plus a handful of demo-clip and title-card frames, via frame-exact `ffmpeg -ss` seeks. Then compiles (if needed) and runs `matte_still` on every extracted frame. Writes `_work/src_frames/`, `_work/assets/`, `_work/matte/`, `_work/faces.jsonl`. | `timeline.py`, `matte_still.swift`, `ffmpeg` |
| `matte_still.swift` | Compiled Vision helper. For each input PNG: `VNGeneratePersonSegmentationRequest` (person matte, written as a grayscale PNG) + `VNDetectFaceLandmarksRequest` (face box + outer-lip box, printed as one JSON line per frame). Pure `Vision`/`ImageIO`/`CoreVideo` — **no `AVFoundation`, no video decoding**; it only ever reads already-extracted PNG stills (ffmpeg does the video decoding, in `extract_frames.py`). Runnable standalone: `matte_still <outDir> <frame.png> ...`. | `swiftc` (Xcode CLT), Vision framework (macOS 12+) |
| `sb_lib.py` | **Drawing kit** ("paper craft" visual language): paper texture, torn-edge tape, pill/tag labels (`label`/`vlabel`), the paper-strip subtitle (`subtitle_c`), the bottom-right picture-in-picture frame (`pip_crop`/`pip_card`/`add_pip`), the 4-step progress bar (`step_bar`), a chapter tab, hand-drawn icons, stamps, curved arrows, and the `Frame` class that composites overlays onto a base image while recording each one's bounding box (so `Frame.check()` can flag a caption sitting on the face/lips, or two overlays overlapping). Canvas is fixed at 1080×1920. | Font files only (`XM_FONT_DIR`) |
| `render_v2.py` | **Step 2 (CLI).** For each requested shot key, builds one `Frame`, draws that shot's specific composition (this file *is* the storyboard: `shot01()`, `shot04()`, `shot07()`, …, `shotI1()`), runs `Frame.check()`, and saves `shot<key>.png` + appends to `_work/layout_report.json`. Usage: `python3 render_v2.py [keys...]` (no args = render every shot). | `sb_lib.py`, `timeline.py`, `_work/*` from step 1 |
| `make_board.py` | **Step 3 (CLI), optional.** Tiles a fixed list of shots (this video's 20, in timeline order) into one big captioned contact-sheet PNG (`storyboard_board_v2.png`), each tile labeled with shot number, time range, a "v2 新/沿用 v1" tag, and a one-line note. No args. | `sb_lib.py`, `timeline.py`, already-rendered `shot*.png`, plus two things *not* in this package (see below) |

Dependency order: `extract_frames.py` (needs `matte_still.swift` compiled) → `render_v2.py` (needs `timeline.py` + `sb_lib.py` + step 1's `_work/`) → `make_board.py` (needs step 2's `shot*.png` for every shot it lists).

## Quick start

This is a worked example of the storyboard-preview *technique*, not a turnkey "JSON in, stills out" tool.
Concretely, before anything here can even be *imported* (`timeline.py` reads its cut-plan JSON at module
load time), you need:

- A cut-plan JSON at `$XM_VIDEO_PROJECT_ROOT/02_cut_review/cut_plan_v1.json` shaped like
  `{"segments": [{"seg": ..., "src_in_frame": <int>, "src_out_frame": <int>}, ...]}` (a rough-cut
  edit-decision list — frame ranges of your source footage that survive the rough cut, in order).
- Your raw camera footage (`$XM_RAW_FOOTAGE`), a 30 fps CFR file.
- A word-level transcript TSV at `$XM_VIDEO_PROJECT_ROOT/01_transcript/source_words_pass1.tsv`
  (header line, then `start\tend\tprob\tword` per line, seconds in source-footage time).
- Your demo clips under `$XM_DEMOS_DIR` (`timeline.py`'s `INSERTS` list hardcodes three: `vlog/vlog_demo.mp4`,
  `kepu/kepu_demo.mp4`, `faceless/faceless_demo.mp4`, plus `faceless/filmstrip/frames/t<ss.s>s.jpg` stills).
- `render_v2.py`'s own shot functions and `timeline.KEY_ROUGH` are hand-written for **this one video's 20
  shots** — adapting this to a different video means editing those functions and timestamps directly, not
  passing in a different config file.

With real inputs in place:

```bash
cd src
export XM_VIDEO_PROJECT_ROOT=/path/to/your/video-production   # holds 01_transcript/, 02_cut_review/
export XM_RAW_FOOTAGE=/path/to/your/footage.mov
export XM_DEMOS_DIR=/path/to/your/demos

python3 extract_frames.py          # step 1: real frames + mattes + face/lip boxes -> _work/
python3 render_v2.py 1 4 7         # step 2: render just shots 1, 4 and 7 as shot1.png / shot4.png / shot7.png
python3 make_board.py              # step 3 (optional): tile rendered shots into one contact sheet
```

Valid keys for `render_v2.py` are whatever the `SHOTS` dict at the bottom of the file lists (currently
`1 4 7 9 10a 10b 11 13a 13b 14a 14b 15 16a 16b 18 I1 I2 I3`) — again, this one video's own shot numbers,
not a general scheme. `matte_still` compiles itself on first run of `extract_frames.py`; to run it by hand:

```bash
swiftc -O matte_still.swift -o matte_still
./matte_still out_dir frame1.png frame2.png ...
```

## Dependencies

- **macOS only**, and only where Vision's person-segmentation + face-landmarks requests are available
  (macOS 12+). `matte_still.swift` needs the Xcode command line tools (`swiftc`) to compile; it does not
  need Xcode itself or AVFoundation.
- Python: Pillow (`PIL`), `numpy`, `opencv-python` (`cv2`).
- `ffmpeg` / `ffprobe` on `PATH` (frame-exact extraction in `extract_frames.py`).
- Chinese fonts (see `XM_FONT_DIR` below) — `sb_lib.py` actually uses the `Medium`/`Heavy`/`Bold` weights
  of Source Han Sans SC only. Its `font()` helper also has a `weight == 'Kai'` branch that looks for
  `LXGWWenKai-Medium.ttf`, but none of these 6 files ever call it with `'Kai'`, so it's dead in practice —
  worth knowing if you extend this code, since this repo's `scripts/get_fonts.sh` only auto-fetches the
  *Regular* weight of LXGW WenKai, not Medium.

## Environment variables introduced by this patch

All five reuse names and defaults already established elsewhere in this repo's `library/_shared/` (setting
one of these covers this toolkit and those other batches together):

- `XM_VIDEO_PROJECT_ROOT` (`timeline.py`) — root of your own video-production working directory (the one
  holding `01_transcript/`, `02_cut_review/`, etc.). Defaults to `.`.
- `XM_RAW_FOOTAGE` (`timeline.py`) — your own camera source file, replacing a hardcoded
  `~/Downloads/copy_*.MOV`. Defaults to `raw_footage.mov`.
- `XM_DEMOS_DIR` (`timeline.py`; `render_v2.py`'s `FACELESS_FRAMES` derives from it) — directory holding
  the vlog/kepu/faceless demo clips and the faceless demo's pre-extracted filmstrip stills. Defaults to
  `../demos`.
- `XM_SCRATCH_DIR` (`render_v2.py`, `extract_frames.py`) — scratch directory for intermediate style-sample
  and title-card assets (originally a Claude session's own temp scratchpad — always ephemeral, never meant
  to be a stable path). Defaults to `/tmp/xm_scratch`.
- `XM_FONT_DIR` (`sb_lib.py`) — directory containing the font files `label()`/`subtitle_c()`/etc. render
  text with. Defaults to this repo's own `fonts/` (resolved relative to this file's own location, verified
  to land on a real, existing `fonts/SourceHanSansSC-Medium.otf` when imported directly).

## What's project-specific vs. reusable

**Reusable as general-purpose building blocks:**
- `sb_lib.py`'s drawing primitives — paper texture, tape, `label`/`vlabel`, `subtitle_c`, the PiP frame
  helpers, `step_bar`, `chapter_tab`, icons, `stamp`, `arrow`, and the `Frame` compositor/overlap-checker —
  are generic "paper craft" visual-language building blocks with no video-specific assumptions baked in
  (only the fixed 1080×1920 canvas — see below).
- `matte_still.swift` is a genuinely generic person-matte + face/lip-box tool for any PNG.
- The three-stage shape itself (extract real frames -> render individual keyframe stills -> assemble a
  contact sheet) is a reusable technique, independent of this specific code.

**Project-specific — expect to rewrite, not just reconfigure:**
- `render_v2.py`'s entire shot table (`shot01`, `shot04`, `shot07`, `shot09`, `shot10a`/`10b`, `shot11`,
  `shot13a`/`13b`, `shot14a`/`14b`, `shot15`, `shot16a`/`16b`, `shot18`, `shotI1`/`I2`/`I3`) is hand-tuned to
  this one video's 20 shots: specific Chinese subtitle text, specific hand-placed coordinates/rotations/colors,
  and specific asset filenames (`card01.png`, `kepu_0513.png`, the `vlog_open` collage JPEG, etc.) from that
  video's own production, none of which are included here. This is not parametrized by any config or JSON —
  adapting it to a new video means editing these functions directly.
- `timeline.py`'s `KEY_ROUGH` dict (per-shot timestamps) and `INSERTS` list (the three demo-insert cut
  points, lengths, filenames and captions) are specific to this one video's edit.
- The 1080×1920 (9:16) canvas is hardcoded (`sb_lib.W, H = 1080, 1920`); this repo's own storyboard schema
  also allows 1080×1440 (3:4), but nothing here is parametrized by canvas size.
- `sb_lib.py`'s color palette (`INK`/`PAPER`/`CARD`/`KRAFT`/`YELLOW`/`RED`/`GREEN`/`BLUE`/`GREY`) is plain
  hardcoded constants, not driven by this repo's `styles/*.json` token system the way `components/*.js` is —
  this toolkit predates and bypasses that system entirely.
- `make_board.py` additionally assumes two sibling inputs this package does not ship: a `storyboard_v1/`
  directory one level above (`V1 = ROOT.parent / 'storyboard_v1'`, for the "沿用 v1" reused-shot tiles) and
  `ip_intro/filmstrip/9x16_f56.png` (`IP_TILE = ROOT.parent / 'ip_intro/filmstrip/9x16_f56.png'`) for its one
  `ip_intro`-component tile. Both are plain `Path(__file__)`-relative expressions rather than personal
  absolute paths, so they were left as-is — but you'll need to supply your own equivalents, or delete those
  rows from `make_board.py`'s `T` table, before running it standalone.
- Shot numbering and the "STEP 1/2/3/4" labels throughout reflect this one video's specific script structure.

## Relationship to other copies of this code in this repo

This repo already has related, differently-scoped copies of some of these ideas:

- `library/_shared/video20-a0-shots/` and `library/_shared/video20-a3-shots/` import `timeline.py` and
  `sb_lib.py` **read-only, directly from the original `05_visual/storyboard_v2/src/` location** (via
  `$XM_VIDEO_PROJECT_ROOT`), treating that location as the single frame-mapping authority for the actual
  shot-rendering pipeline rather than copying it in. This toolkit deliberately does the opposite — it ships
  its own standalone, patched copies so the storyboard-preview workflow doesn't need the rest of the
  `video20-a*-shots` pipeline present. That means these copies are an independent snapshot: if the original
  project's `timeline.py`/`sb_lib.py` change later, these will not track those changes automatically.
- `library/_shared/video20-a1-shots/src/sb_lib.py` and `library/_shared/paper-craft-components/src/sb_lib.py`
  are two more verbatim copies of `sb_lib.py` (not `timeline.py`), kept for shot-batch and
  concept-documentation purposes respectively.
- `library/_shared/video20-a3-shots/src/a3common.py` separately copies a handful of small helpers out of
  `render_v2.py` verbatim (`pill`, `badge`, `hud_brackets`, `glow`, `scissors`, `check_chip`) rather than
  importing the whole module (to avoid pulling in its keyframe caches). This package ships the complete,
  original `render_v2.py` instead, including its full storyboard-preview shot table.

Found in passing while verifying this port, out of scope for this change (this change only touches
`library/_shared/storyboard-frames/`): both `library/_shared/video20-a1-shots/src/sb_lib.py:16` and
`library/_shared/paper-craft-components/src/sb_lib.py:16` still contain the original, unpatched
`FONTS = Path(os.path.expanduser('~/Projects/xiaolu-motion/fonts'))`, even though
`paper-craft-components/README.md` currently describes both source copies as "already confirmed clean of
personal paths." It isn't a literal home-directory or username string (it's a `~`-relative `expanduser` call), but it's the
same personal/project-specific-path problem this patch fixes elsewhere — left unfixed here since it's outside
this change's file ownership.
