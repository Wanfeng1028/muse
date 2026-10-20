# Case studies

Two real films made with this method, and the feedback loops that shaped the skill.
The Connectra feedback is reconstructed from its commit messages and README, which say what each cut
changed. The Heli feedback is quoted from the owner. The full concept docs, narration scripts and copy are in `references/connectra/` and `references/heli/`.

## Connectra: v1 → v4 (one person, a fleet of machines, any AI agent)

| Cut | What it was | Feedback / problem | What changed |
|---|---|---|---|
| v1 | First Remotion draft. Dark, 7 scenes, 50 s, generic components. | Looked generic and AI-made: fake metrics, chips, gratuitous checkmarks, made-up UI. | → v2 |
| v2 | Same beats, components rebuilt from the real desktop app (`App.tsx`/`styles.css`) and the website panels, with the product's own icon set and no emoji. | Faithful but still dark. The dark terminal look read as slop. | → v3 as a new composition |
| v3 | Light editorial cut: warm paper, near-black ink, huge type, soft shadows, slow camera, an isometric fleet of minis, one violet accent. Then a sound version: ElevenLabs "George" (`eleven_multilingual_v2`), synthesized score + SFX, -16 LUFS master. | Labels too faint, fleet labels and terminals overlapping, the approval panel had a dark code block, stacked badges and nested borders, and the narration sounded read. | → v4 |
| v4 | Krehel UI rules applied. AA contrast tokens (ink3 3.2:1 → 6.3:1). The fleet ring was rebuilt from pure geometry with an overlap checker (`check-fleet.ts`). A calm light approval card with one filled button. A conversational script voiced by "Liam" on `eleven_v4` with audio tags and stitching, and the music re-ducked to 0.085. | Accepted as the reference style for Connectra. | |

Lessons:
- Rebuild the real UI; don't decorate a generic one.
- Light themes win; dark code blocks inside light UI are a slop tell on their own.
- Contrast has to be measured, not eyeballed. "Slightly faint" grey labels fail AA and look cheap.
- Overlaps only show up mid-animation, so check geometry in code and look at dense audit sheets.
- Narration: an expressive model plus audio tags plus a conversational rewrite beat a "storyteller"
  voice reading formal copy.

## Heli-Harness: v1 → v2 (a harness for AI coding CLIs)

| Cut | What it was | Feedback | What changed |
|---|---|---|---|
| v1 | Dark "night flight deck". The story was governance: one rulebook, the agent asks, the human grants, a hard floor of never-run commands. Real hook/CLI output from a sandbox. Voice "Chris" on `eleven_v4`. | **Loved:** the voice (Chris) and the storytelling mood and pacing. **Rejected:** the content ("Heli is not just push-blocking") and the dark style ("instantly reads as AI slop"). Two scenes were too dense. | → v2, new composition, v1 kept |
| v2 | "Switch tools. Keep the thread." A fix starts in Claude Code, two attempts fail, Codex opens the next day blank. Heli's task record (`current-task.md`) is injected at SessionStart in every CLI. The skills (verify-premise, fix-loop) and the two-strike hook stop a third blind patch. "Done" needs recorded passing evidence. Governance became one supporting beat. Light "clear air" theme: cool white, navy ink, cobalt from the repo hero image, light terminal panes, Schibsted Grotesk + JetBrains Mono, a 2 px "thread" motif. Same voice and delivery, new conversational script. | (pending) | |

Lessons:
- The most technical or security-flavoured feature is rarely the story. Ask "what does this make
  easier every day?" and build the film around that.
- Keep what was praised exactly as it was (voice, delivery settings, pacing), and change only the axes
  that were criticised.
- STT caught a pronunciation problem nobody could hear: "Heli" alone was transcribed as "Healy" in two
  takes. The line was rewritten so the bare name never appears.
- Fewer elements per frame: start a lone panel centred, then slide it aside when its partner arrives.
  Don't leave half the frame empty waiting for it.
- A render that is backgrounded in an agent shell can be killed when the call returns. Render in the
  foreground with a long timeout and check that the log is still growing.
