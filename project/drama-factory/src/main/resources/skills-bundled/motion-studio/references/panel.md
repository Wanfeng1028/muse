# Blind read and review panel

## Blind read (every film, the ship gate)

1. `studio.py blindpack <film>` builds `review/blind-read/round-N/`: one still per bar from the encoded film, `onscreen-text.md` (every caption and `K.label`), and `prompt.md` (from `prompts/blind-read.md`).
2. Dispatch one or two readers who see only that folder. They must be fresh (no memory of the source or this conversation):
   - Claude: `Agent` (general-purpose, a fresh subagent), prompt: "Everything you may use is in `<packet>`. Read prompt.md first … do not open anything outside that folder or search the web … return the answer in the format prompt.md specifies."
   - A second model via Codex CLI (optional): `cd <packet> && codex exec -s read-only --skip-git-repo-check -C <packet> $(for f in frames/*.png; do printf -- "-i %s " "$f"; done) -o answer.md - < prompt.md`
3. Compare each reader's **thesis** and **chain** to the contract. Pass = the thesis matches and the chain has every step. Their "confusions" list is a fix list whether or not the thesis passed.
4. Fix, render a new final, build a **new** packet (round N+1), and use a **new** reader: a reader who has seen round N isn't blind. (`blindpack --redo` rebuilds the latest round only if no reader has seen it.)
5. Record each round's reader, thesis and verdict, and what was fixed, in the storyboard.

On Walk to Digest v3 the first two readers passed the thesis, and both independently flagged that talk → text was never shown. That fix (his real transcript line becoming a strip) is the kind of thing only a blind read finds.

## Review panel (on request, or a first cut of a new kind of film)

Three independent reviewers in parallel, then synthesis:

| Reviewer | How | Prompt |
|---|---|---|
| Motion-design reviewer (e.g. Codex CLI) | `codex exec -s read-only --skip-git-repo-check -C <film> -i review/<contact>.png -i review/<scenes>.png -o review/reviewer-motion.md - < review/prompt-reviewer-motion.md` | `prompts/reviewer-motion.md` |
| Creative-director reviewer | same, `-o review/reviewer-creative.md`, prompt `prompts/reviewer-creative.md` | three storyboard variants, captions, a music and foley brief |
| Advisor | `Agent` (a different model from the builder if available); ask for the engine/audio/feasibility view and the risks for a one-session build | written per film |

- Which models fill these seats is in the house notes if there are any. Copy `prompts/reviewer-motion.md` and `prompts/reviewer-creative.md` into the film's `review/` as `prompt-reviewer-*.md`.
- Each film needs its own `review/brief-context.md` (what the film is, house rules, the toolbox, the author's complaint if any): start from `prompts/brief-context.EXAMPLE-walk-to-digest.md`. Reviewers are told they're read-only.
- Synthesis: a decision table in `review/plan.md` (decision, who proposed it, who dissented). Name the conflicts; don't average them.
- **Check every accepted cut against the contract.** The v2 panel cut the diagnosis and promoted the anecdote, each for good pacing reasons, and the film lost its point. A reviewer cut to the argument chain goes to the user.
- Send the merged plan back to the advisor for one tie-break pass before building.
- Costs: a high-effort reviewer takes 5–10 min; an advisor with tool use ~15–20 min. Run them in the background while doing something else useful (fetching audio, scaffolding).
