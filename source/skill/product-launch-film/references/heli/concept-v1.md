# Heli-Harness: launch film concept (v1)

## What Heli is (from the repo, v0.10.4)
Heli-Harness (`heli`, MIT, github.com/KJ-AIML/heli-harness, npm `heli-harness`) is a small
**governance kernel for coding agents**. You install it once per machine (`heli setup`, `heli host install all`)
and link each project (`heli link` → a committed `.heli/`). Its hooks then sit in front of the tools of the
agents you already use: Claude Code, Codex, Grok Build, OpenCode, Kimi Code CLI and Pi are `runtime=enforced`;
Cursor is `plugin-wired`. Every guarded tool call gets one normalized decision from the same policy.

Things the film shows, all taken from real output (captured in a throwaway sandbox HOME, see "Sources"):
- A PreToolUse hook **denies `git push`** without scoped authority. The reason tells the agent to ask the user
  to run `heli grant issue --action git.push --scope once` in their own terminal.
- **Agents cannot approve themselves.** An agent-run `heli grant issue` is hard-denied (rule
  `heli-privileged-command`, tier T6), and `heli grant issue` only runs in an interactive terminal.
- **Scoped grants are consumed.** After a `--scope once` grant, the first push is allowed, and then
  `heli grant list` prints "No active scoped grants." A second push is denied again.
- **A built-in T6 floor**: `git reset --hard`, `rm -rf` in any spelling and similar rules are a
  "hard deny; scoped grants, YOLO and HELI_ALLOW_COMMAND do not override it."
- Command tiers T0–T6 (read-only inspection … destructive/secret-bearing/outside-root).
- `heli host status`, including its honest footer: "Installation state is not runtime proof."

Heli is not an agent runtime or a sandbox, and the film doesn't claim it is.

**Who it's for:** developers and small teams who run several coding agents on real repos and want the risky
moves (push, publish, destructive deletes) gated in one place.

**The single strongest idea:** *the agent can ask, but only a human can grant, and every grant is scoped and
used up.* It's the same rulebook in every host.

## Tagline
**Let your agents move fast. Keep the keys.**
(Supporting line, from the repo: "Portable governance for coding agents.")

## Visual mood: "night flight deck"
Connectra v4 was warm paper, editorial and light. Heli is the opposite: a terminal-forward, instrument-panel
dark.
- Background ink `#0a0d13`, panels `#10141c`/`#161b25`, hairline shadow rings instead of borders.
- Type is IBM Plex Sans (display/UI) and JetBrains Mono (all CLI output). Both differ from Connectra's
  Inter/Geist.
- One brand accent: **Heli blue**, taken from the helicopter in `assets/heli-harness-hero.png`. Text uses
  `#8fa3ff` and the rule/fill uses `#4f6bff`.
- Three decision colours, used only for decisions: allow `#5ed39b`, ask/grant `#f0b54a`, deny `#ff7b72`.
- Every text colour is measured ≥ 5.8:1 on every surface (WCAG AA).
- Motion is calm and mechanical: typed commands, output line by line, and a single "hook" rule that a tool
  call stops against. There's no glow, no gradients, no emoji and no fake metrics.
- The doctor's "✅" stays out; the `host status` "✓" marks are real CLI glyphs.

## Storyboard (60 fps, 3420 frames = 57 s)
| # | Frames | Scene | On screen |
|---|---|---|---|
| 1 | 0–400 | **Problem** | Headline "Your agents can push, publish and delete." A coding-agent terminal runs `git push`, `npm publish` and `rm -rf build` unchecked. Host names fade in: "Each host, its own rules." |
| 2 | 400–960 | **One rulebook** | Terminal: `npm install -g heli-harness`, `heli setup`, `heli link`, `heli host install all`, with real output lines (`- claude: installed/verified` …). |
| 3 | 960–1500 | **Stopped at the hook** | Agent transcript: "Ship the fix to main." → `Bash git push origin main` hits the PreToolUse rule → **deny**. The real reason types out, and the `heli grant issue …` span highlights. |
| 4 | 1500–2130 | **Agents ask. You grant.** | Split view, agent vs. your terminal. The agent tries `heli grant issue` → T6 hard deny. You run it → "Issued grant heli-grant-…". The push is allowed. `heli grant list` → "No active scoped grants." |
| 5 | 2130–2620 | **Hard lines** | T0–T6 tier ladder from `command-tiers.md`. `git reset --hard` and `rm -rf` are denied with the real T6 text; "do not override it" highlights. |
| 6 | 2620–3030 | **Every host** | Real-format `heli host status` output. Rows highlight in sync with the VO, and the "not runtime proof" footer stays visible. |
| 7 | 3030–3420 | **Close** | Wordmark "Heli-Harness", tagline, `npm install -g heli-harness`, github.com/KJ-AIML/heli-harness · MIT. |

## Narration (ElevenLabs "Chris", eleven_v4, audio tags)
1. [dry] Your agents can push, publish, and wipe a folder. Each one with its own rules.
2. [confident] Heli-Harness gives them one rulebook. Install it once, link your project, and it hooks into the agents you already use.
3. So an agent tries to push? Stopped, right at the hook. And it tells the agent exactly why, and who gets to say yes.
4. [matter-of-fact] That’s you. In your own terminal. The agent can’t grant itself anything. It tried. Allow once, and once means once.
5. [firm] Some lines don’t move at all. Hard resets. Recursive deletes. No grant, no YOLO gets past those.
6. Claude Code, Codex, Grok Build, OpenCode, Kimi. One set of rules.
7. [warm, confident] Heli-Harness. Let your agents move fast, and keep the keys.

## Sources
- README.md, docs/architecture/governance-model.md, `.heli-harness/safety/command-tiers.md` + `command-rules.json`,
  docs/ADAPTER_SUPPORT_MATRIX.md, lib/cli/host.mjs, CHANGELOG v0.10.4.
- The CLI and hook output was captured by running a copy of the repo with `HOME=/tmp/hs/home` against a scratch git
  repo. `heli --version` → 0.10.4. The hook was fed Claude-style PreToolUse JSON. The real `~/.heli` and the heli
  repos weren't touched.
- Demo names (`acme/api`, `/Users/kj/code/api`, grant/workspace ids) come from that sandbox run or are
  placeholders; the ids are real sandbox ids.
