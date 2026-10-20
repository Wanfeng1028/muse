# video:hf-motion — Help

Render a parameterized HyperFrames motion graphic from a named recipe. Same
skeleton, swap the content: the recipe fixes the scenes, motion and beat grid;
the parameters supply every word, number and colour.

## Arguments

| # | Name | Default | Description |
|---|------|---------|-------------|
| 1 | `<recipe>` or `-h`/`--help`/`help` | — | Recipe name. Omitted: list recipes and ask. Implemented: `launch-film` (27 s, 1440x1440, 120 BPM, 9..12 `photos=`), `ui-morph` (14 s loop, 1440x1440, music, Latin text), `intro-kinetic` (15 s kinetic-typography self-intro), `pixel-dissolve` (6 s word swap through a seeded pixel dissolve), `circle-pop` (6 s scene change through a popping circle that becomes scene B), `screen-dive` (6 s camera dive into a drawn laptop's screen), `text-sandwich` (6 s pass of the user's character image between the letters of a word), `letter-flythrough` (6 s fly-through into the hole of a big letter). Planned, not implemented: see `references/recipes/README.md` |
| 2.. | `key=value` | recipe defaults | Overrides one top-level key of the recipe's `CONFIG` block. Numbers parse as numbers; lists split on `\|` (commas are legal inside an item); `[word]` inside a label or finale line marks the accent colour. Unknown keys are rejected. Per-recipe keys and limits: `references/recipes/<recipe>.md` |
| - | `--out <dir>` | `./<recipe>` | Project directory to create. Must not exist or be empty |

With no `key=value` at all, a recipe reproduces its verified reference
render; `intro-kinetic` reproduces the original verified
video (the original author's own values). Use that only for the author; for
anyone else every fact must come from them.

## Usage

- `/video:hf-motion` — list recipes (implemented and planned) and ask which one.
- `/video:hf-motion intro-kinetic name=홍길동 team=가나다팀 years=12` — fill
  three keys, keep the rest, confirm the full table, then scaffold → verify → render.
- `/video:hf-motion intro-kinetic 'tools=Notion Kit|Daily Log' 'flash=습관|기록|성장' 'finale=평범한 직장인이 알려주는|[돈과 시간]을 버는|[작은 습관] 하나' bpm=116`
  — variable counts; scene lengths and the total follow (29 beats at 116 BPM = 15.0 s).
- `/video:hf-motion intro-kinetic --out ~/videos/hong-intro subsTarget=123000` —
  custom project dir; the counter lands on `12만 3천`.
- `/video:hf-motion pixel-dissolve 'textA=작년의 나' 'textB=올해의 나' pixelSize=24` —
  6 s swap with a finer grid; same seeded cell order on every render.
- `/video:hf-motion circle-pop 'textA=기획서' 'textB=런칭 완료' popOrigin=0.15,0.8 popColor=charcoal` —
  6 s change; the circle pops from the lower left and becomes scene B.
- `/video:hf-motion screen-dive 'screenText=새로운 화면' diveAt=1.5 diveDur=3` —
  6 s dive into the laptop screen; the text ends full-frame with no bezel.
- `/video:hf-motion text-sandwich word=MOTION characterImage=./alex.png direction=rtl` —
  6 s sandwich with your own image (copied into the project, never bundled); a
  missing image stops the scaffold before anything is written.
- `/video:hf-motion letter-flythrough letters=OK 'nextText=다음 장면'` —
  6 s fly-through into the hole of the "O"; a target letter with no hole is refused.
- `/video:hf-motion -h` — print this help.

## Trigger phrases

The frontmatter `description` names every implemented recipe and keeps two broad
phrases; these per-recipe phrases also route here:

| Recipe | Phrases |
|--------|---------|
| `intro-kinetic` | "자기소개 모션그래픽 만들어줘", "intro-kinetic 레시피로 영상 뽑아줘", "이름만 바꿔서 같은 인트로 영상", "make my kinetic intro video" |
| `pixel-dissolve` | "pixel-dissolve 문구 전환" |
| `circle-pop` | "circle-pop 원 팝 전환 영상" |
| `screen-dive` | "노트북 화면 줌인" |
| `text-sandwich` | "텍스트 샌드위치 영상" |
| `letter-flythrough` | "글자 구멍 속으로 줌인" |
| `ui-morph` | "UI 모션 루프 영상" |
| `launch-film` | "키노트 런치 필름" |

## The scripts it runs

| Script | Does |
|--------|------|
| `scripts/find-hf-plugin.sh` | Prints the official hyperframes plugin root (the dir holding `skills/hyperframes/scripts/plugin-cli.mjs`); exit 1 with install instructions when absent |
| `scripts/scaffold.mjs <recipe> <dir> [k=v ...] [--update] [--no-music]` | Copies the template, rewrites `CONFIG`, writes the static timing attributes, copies GSAP + SFX from the hyperframes plugin, writes `package.json` / `meta.json`, copies a recipe's user asset (refusing, with nothing written, when it is unreadable), generates the music bed (recipes that have one) and any recipe-generated file (`letter-flythrough`'s `glyphs.js`). Prints a `verify-render args:` line for Step 6. `--list` prints implemented recipes |
| `scripts/verify-render.py <mp4> --duration S [--bpm N] [--width W --height H]` | Post-render gate: h264 WxH (default 1920x1080) @ 30 fps, duration; with `--bpm` also aac, audio peak, kick grid |

## Environment

| Variable | Default | Effect |
|---|---|---|
| `HF_PLUGIN_ROOT` | unset | Explicit official-plugin root. When set and wrong, discovery fails rather than falling through |
| `CLAUDE_CONFIG_DIR` | unset | Searched first: `$CLAUDE_CONFIG_DIR/plugins/cache/hyperframes/hyperframes/<newest>` |
| `CLAUDE_PLUGIN_ROOT` | set by Claude Code | This plugin's root. Other harnesses: export it (see SKILL.md Prologue) |

Tools needed on `PATH`: `node` 22+ (with `npx`), `python3` + `numpy`, `ffmpeg`,
`ffprobe`. The first CLI call downloads the pinned `hyperframes` package via
`npx`, so network access is required once per version.

## What this skill will NOT do

- Render before you confirm the parameter table.
- Invent a name, number, employer or claim. Missing facts are asked for.
- Run a planned recipe, or bend an implemented one into it.
- Call `npx hyperframes` directly or run `skills update` — the official plugin
  launcher pins the CLI to the installed plugin version.
