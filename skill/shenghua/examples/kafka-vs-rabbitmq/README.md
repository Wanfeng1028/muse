# Worked example: Kafka vs RabbitMQ

This is a complete Step 4 shot list and Step 6 composition for the first 40 seconds of a tech explainer
voiceover. It has 17 shots and 63 sound cues, with no photos or clips. Copy the shape, not the words.

| File | What it is |
|---|---|
| `transcript.txt` | the phrase-level transcript (`transcribe.py --model small`) every time below is cut to |
| `shot-list.md` | the timed shot table, in the format Step 4 asks for |
| `shots.html` | three paste regions for the filled template in Step 6 |

## What it demonstrates

- **Cutting on the word.** Every shot starts on a word in `transcript.txt`. Every hit lands on the one
  word that carries its shot: "question" at 0.84, "them" at 5.16, "never" at 6.76, "detail" at 10.20,
  "decision" at 21.22 and "log?" at 39.56.
- **Pacing.** Shots run 1.2–3.7s, plus the outro hold. Every shot held longer than 3s keeps moving
  inside it:
  - 02: tokens fly to a consumer.
  - 07: a command types out.
  - 09: a progress line runs.
  - 10: a tree grows branch by branch.
  - 15: cards slide in to be struck.
- **Contrast.** The hook (01–08) uses fast cuts with hits. The promise (09) uses a `fade` and holds
  its hit until the last word. Then the pace picks up again into the title card.
- **Showing the idea, not the sentence.** The claim "RabbitMQ deletes on read, Kafka never does"
  becomes two diagrams in a row. Both show the same lane of tokens:
  - RabbitMQ loses a message to the consumer and gets a `DELETED` stamp.
  - Kafka keeps all four while an offset marker walks past them.
- **Block variety without third-party media.** The blocks used are kinetic slam, term pill, lane and
  tokens, stamp, duo cards, highlight box, hub-and-spoke diagram, terminal, strike-through, progress
  path, tree diagram, kinetic type with a bar motif, a riser into a title card, stacked slams and the
  outro.
- **Captions.** They are hidden with `NOCAP` wherever the same words are already on screen as a
  headline or stamp. They stay on over diagrams and terminals, which sit above y=1450, so the two never
  collide.
- **The ending.** The last word gets the biggest slam and an accent flash.
  `synth_audio.py --drop 39.56` cuts the music just before it. The outro holds for 2.5s after the last
  word, with the follow line. The outro reads the handle from `#sig`, so it follows the brand automatically.
- **Theme-proof markup.** Every colour is a theme token (`var(--body)`, `var(--panel)`,
  `var(--accent)`) or a template class. The same paste renders correctly with `--template brutalist`
  or `minimal`.

Details that are not in these 40 seconds are listed at the end of `shot-list.md`. They are split into
"from later in the script" and "invented illustration". Report yours the same way.

## Why each shot is where it is

| # | Cut on | Why |
|---|---|---|
| 01 | 0.00 | a two-word hook: slam the second word and hold through "If I told you" |
| 02 | "RabbitMQ" 2.32 | the claim needs a picture: the pill names it, a token flies to the consumer on "someone reads" (4.48), stamp on "them" |
| 03 | "and Kafka" 5.88 | same lane, opposite outcome; `whip` signals "now the other one"; stamp on "never" |
| 04 | "would" 7.86 | the question puts both options on screen, with a "?" slammed on "one" |
| 05 | "why" 9.50 | "one detail" is boxed on the word |
| 06 | "changes" 11.12 | the spokes draw out of the broker: one choice reaches every service |
| 07 | "Most" 13.60 | the lazy tutorial as a terminal that ends in "both work. the end." |
| 08 | "I'm" 17.00 | "call it a day" is struck right after it's said: a refusal reads as a strike-through |
| 09 | "By" 18.36 | a quiet promise: `fade`, a progress line runs to "decision", one hit there |
| 10 | "that" 21.82 | "explains every other difference" drawn as one root with five branches |
| 11–13 | 25.46, 27.32, 28.82 | three promises, three blocks: code, the words as type, a slam with a strike |
| 14 | "Let's" 30.26 | riser into the title card; a slam on each name |
| 15 | "Everyone" 33.26 | the cage match is set up, then struck out on "not" |
| 16 | "It's" 36.56 | a one-line beat before the payoff |
| 17 | "Do" 37.80 | QUEUE on "queue", LOG? on "log?", then hold for the outro |

## Reproduce it with your own 30–40 second clip

`SKILL_DIR` is the directory holding `SKILL.md`. Cut the clip at the end of a sentence.

```bash
work=~/shenghuas/my-example/work && mkdir -p "$work"
python3 SKILL_DIR/scripts/transcribe.py my-clip.wav --outdir "$work" --model small --vocab "Kafka, RabbitMQ, Spring Boot"
python3 SKILL_DIR/scripts/build_captions.py "$work"            # after writing fixes.json and keywords.json
python3 SKILL_DIR/scripts/fill_template.py "$work" 42.3 --template blueprint --brand SKILL_DIR/brand.example.json
```

`shots.html` has three regions. Each one opens with a `---- paste …` line and closes with
`---- end ----`. Copy only the lines between those two delimiters into `"$work"/index.html`:

1. **Markup:** goes between `<!-- BEGIN SHOTS -->` and `<!-- END SHOTS -->`.
2. **Timeline:** goes between `// BEGIN TIMELINE` and `// END TIMELINE`.
3. **NOCAP:** the `const NOCAP = …` line replaces the template's own `const NOCAP` line, which sits
   just below `// END TIMELINE`. Replace that line; don't add a second one.

Then write your own shot list from `transcript.txt` and re-time every number to your words, and
follow Steps 7–11. `render.js check` must report zero findings before you
render frames.

This example used these two files:

- `fixes.json`: `{ "Code,": "code,", "hand": "hand-waving.", "waving.": "" }`
- `keywords.json`: `["RabbitMQ@2.32", "Kafka@5.88", "architectural", "Spring@26.36", "Boot@26.64"]`
