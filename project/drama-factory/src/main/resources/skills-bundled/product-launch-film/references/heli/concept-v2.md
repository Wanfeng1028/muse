# Heli-Harness — launch film v2 concept

**Tagline:** Switch tools. Keep the thread.

**One line:** Heli-Harness keeps one work record per task and hands it to whichever coding agent you open
next. Its skills and hooks stop agents from guessing, and from claiming "done" without evidence.

## Why v2

KJ's notes on v1: loved the voice (Chris) and the pacing. Rejected the dark "night flight deck" look, which
read as AI slop, and the content, because Heli is more than push-blocking. v2 keeps the voice and the
storytelling rhythm. It moves the story to what makes a developer's day easier. Governance becomes one
supporting beat.

## Audience

Developers who use more than one AI coding CLI (Claude Code, Codex, Grok Build, OpenCode, Kimi Code CLI, Pi)
on the same codebase and lose context every time they switch. Also tech leads who want agents to follow
evidence rules instead of guessing.

## Strongest idea

The task state lives with the workspace, not inside one agent's chat. Every supported host's SessionStart hook
injects the same bound task state into the new session. The PreToolUse hook then enforces what that state
says. For example, after two failed attempts it denies further edits until the record is updated.

## Visual identity: "clear air"

- **Palette.** Cool white `#f3f5f9` background, white panels, navy ink `#0e1530`, and one Heli cobalt
  `#2443d6`. All are taken from the repo hero image (`assets/heli-harness-hero.png`: navy wordmark,
  cobalt-and-white helicopter).
- **Decision colours.** Deny `#b42318` and allow `#0b6e3e`, used only where Heli makes a decision.
- **Contrast.** Every text colour is at least 5.0:1 on every surface (WCAG AA).
- **Type.** Schibsted Grotesk (titles, UI) and JetBrains Mono with ligatures off (all CLI and hook text).
  The grotesk is distinct from Connectra's editorial serif and from v1's IBM Plex.
- **Motif: the thread.** A single 2 px cobalt line.
  - S1: it leaves the Claude Code pane and stops short of Codex.
  - S2: it is the left rule of the record.
  - S3 and S6: it joins the host chips.
  - S7: it underlines the tagline.
- **Restraint.** No grid, no glow, no gradients, no emoji, no pills except the host chips, and no invented
  metrics. At most three blocks per frame. Text density is roughly half of v1.
- **Layout.** All geometry is in `src/v2/layout.ts` and checked by `npm run check:layout:v2`: safe area,
  32 px minimum gaps, monospace fit, no pane scrolls.

## Storyboard (57.0 s, 1080p60)

| # | Time | Scene | What you see | Source of the on-screen text |
|---|------|-------|--------------|------------------------------|
| 1 | 0.0–8.3 | New tool. Blank slate. | Claude Code pane (Monday): "Fix the login timeout on slow networks." Two Edit + `npm test -- auth` cycles, both failing. Codex opens (Tuesday) to an empty prompt. The cobalt thread stops short. | Demo transcript (generic agent pane, not a host's real UI) |
| 2 | 8.3–15.3 | One task. One record. | `heli task create fix-login-timeout …` and its real output. Then `tasks/fix-login-timeout/current-task.md` (excerpt). "What changed / what failed / next smallest step" light up in time with the narration. | `lib/cli/task.mjs` (captured), `.heli-harness/templates/current-task.md` field names |
| 3 | 15.3–25.0 | The next agent starts with the record → Switch tools. Keep the thread. | Host rail: Claude Code → Codex → Grok Build → OpenCode → Kimi Code CLI, joined by the thread. The pane shows the real SessionStart `additionalContext`, including "Bound task state from tasks/fix-login-timeout/current-task.md". The header changes per host. | Captured from `adapters/codex-plugin/hooks/heli-session-start.mjs` (and grok-plugin, identical) |
| 4 | 25.0–36.7 | Agents don't guess. | Two rule cards, verbatim: `verify-premise` "Do not implement if the premise is false or unclear." and `fix-loop` "After two failed implementation attempts on the same issue, stop coding and write diagnosis." Codex tries a third `apply_patch` and gets the real PreToolUse deny. | `.heli-harness/skills/*/SKILL.md`; deny captured from the codex-plugin PreToolUse hook |
| 5 | 36.7–44.0 | Done means verified. | `heli task complete` → `VERIFICATION_EVIDENCE_REQUIRED`. Then `heli diagnosis record … --type run --json '{"runId":"auth-tests","status":"passed"}'` and `heli task complete` → "marked complete (revision 2)". | Captured. The diagnosis JSON output is shown folded to one line. |
| 6 | 44.0–51.8 | One rulebook. You hold the keys. | Rail of six hosts lit at once. `git push origin main` → deny "Ask the user to run `heli grant issue …` in their own terminal". `rm -rf build` → T6 hard deny. | v1 captures (claude-plugin PreToolUse) |
| 7 | 51.8–57.0 | Close | Wordmark, "Switch tools. Keep the thread.", `npm install -g heli-harness`, github.com/KJ-AIML/heli-harness · MIT, "Narration voice: ElevenLabs". | — |

## Narration (ElevenLabs "Chris", eleven_v4, stability 0.4, similarity 0.75, speaker boost, stitched)

1. [casual] You start a fix in Claude Code. Two tries, no luck. Next morning you open Codex... and it's starting from zero.
2. [confident] Heli-Harness keeps a work record for the task: what changed, what failed, and the next smallest step.
3. So when Codex starts, it gets that record, first thing. Same in Grok Build, OpenCode, Kimi. Switch tools, keep the thread.
4. [matter-of-fact] And it won't let agents guess. Check the claim before you fix it. Two failed fixes? Stop and diagnose. Codex tries a third patch anyway... and the hook says no.
5. Same with "done." No passing check, no complete. Record the run, and now it closes.
6. Underneath, one rulebook for every agent. A push waits for your grant, and some commands never run at all.
7. [warm, confident] Heli-Harness. Switch tools, keep the thread.

Line 3 originally named "Heli" mid-sentence. Speech-to-text heard it as "Healy" twice, so the line was
rewritten without the name. Every "Heli-Harness" at the start of a sentence transcribed correctly.

## Sound

- **Score.** Original synthesized score, `scripts/make-audio-v2.py`, 104 BPM, D major / B minor: bell-piano
  chords, a plucked eighth-note figure, a quiet shaker and a soft sub.
  - The arrangement is fullest for the switch and held back for the evidence gate.
  - It resolves to Dmaj9 on the close.
- **SFX.** tick, deny, allow, thread (a soft upward glide when the line draws), bloom, air. Each SFX is tied
  to an on-screen event.
- **Mix.** Music ducks under the VO. Mastered to −16 LUFS integrated with a true-peak ceiling (`scripts/master-audio.mjs`).

## How the demo was captured (all real CLI output)

```bash
# sandbox: copy of heli-harness at HEAD 3d0d234, HOME=/tmp/hs2/home
heli install /tmp/hs2/shop                      # embedded parent workspace (concurrent mode)
heli task create fix-login-timeout --title 'Fix login timeout on slow networks' --repo api
heli task claim fix-login-timeout --mode write --host claude
#   (current-task.md then filled as the Claude session would leave it: 2 failed attempts, blocked)
heli task release fix-login-timeout             # Claude session hands off
heli task claim fix-login-timeout --mode write --host codex
#   SessionStart JSON -> adapters/codex-plugin/hooks/heli-session-start.mjs  (and grok-plugin)
#   PreToolUse apply_patch JSON -> adapters/codex-plugin/hooks/heli-pre-tool-use.mjs  (deny)
heli diagnosis init fix-login-timeout --json '{"symptom":…,"closestProvenBoundary":…}'
heli task complete fix-login-timeout            # VERIFICATION_EVIDENCE_REQUIRED
heli diagnosis record fix-login-timeout --type run --json '{"runId":"auth-tests","status":"passed"}'
heli task complete fix-login-timeout            # marked complete (revision 2)
```

Raw outputs are in `docs/captures-v2/`. The only edit to on-screen text is the localised path
(`/private/tmp/hs2/shop` → `~/code/shop`).

## Honesty notes

- **Mode.** The full task-state injection ("Bound task state from …current-task.md") is what the hook emits in
  an **embedded / parent-workspace** install (`heli install <path>`). A **linked** v0.10 project (`heli link`)
  gets a shorter SessionStart block, "Heli Linked Session … Work record: fix-login-timeout". The agent then
  reads the record with `heli task show`. The film uses the parent-workspace flow, and it doesn't show any
  install command other than `npm install -g`.
- **Handoff.** The film doesn't show the `release` / `claim` (or `HELI_SESSION_ID`) step. The two-strike deny
  needs a bound session.
- **Completion gate.** `heli task complete` only blocks on missing verification while a diagnosis is active on
  the task, as it was in this demo. A task with no diagnosis completes without one.
- **Other hosts.** For OpenCode and Kimi, the identical context comes from source (`opencode-plugin/heli-harness.js`
  and `kimi-plugin/hooks/heli-session-start.mjs` call the same `buildSessionContext`). I only executed the
  Codex and Grok hooks. Pi's adapter (an external package) wasn't executed and isn't in the switch rail. Pi
  appears only on the rules rail (runtime enforced per `docs/ADAPTER_SUPPORT_MATRIX.md`).
- **Demo content.** The api repo, `src/auth/client.ts`, the jest-style failure lines and the 10s→30s patch are
  demo content. Agent panes are generic, not any host's real UI.
