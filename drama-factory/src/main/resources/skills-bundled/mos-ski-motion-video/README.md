# Motion Video: a Claude Code skill

Product presentations, launch reels, feature demos and event promos as motion graphics, all
rendered from code. Give Claude a Figma link (or a product URL) and a goal. It pulls the real
design tokens and layers, plans a shot list on a beat grid, animates in Remotion with springs and
a "jitter" kit (on-twos timing, boil, snaps with motion blur, montage bursts, impact shakes), adds
synthesized clicks, whooshes and music, and critiques its own frames until every score is 8+.

## Install
1. Clone this repo into your Claude Code skills folder (available in all your projects):
   ```
   git clone https://github.com/mos-ski/motion-video-skill ~/.claude/skills/motion-video
   ```
   Or clone it into a single project's `.claude/skills/motion-video` instead.
2. Requirements: **ffmpeg 6+**, **Node 18+**, **Python 3.9+**. On **macOS 13 (Ventura) or 14**,
   pin Remotion to `4.0.438` in `studio/package.json` (newer releases ship binaries that need
   macOS 15 and crash while encoding).
3. In the folder where you want to make videos, either ask Claude to "set up the motion video
   skill", or run it yourself:
   ```
   bash ~/.claude/skills/motion-video/scripts/setup.sh          # add --beats to measure music tracks
   ```
   This creates `studio/` (a Remotion project with the motion engine and an example reel),
   `.motion/venv` (numpy + scipy for sound), and `references/`, `demos/`, `work/`, `output/`,
   `sfx/`, `music/`.
4. Optional: connect the **Figma MCP** in Claude Code so Claude can read Figma links directly.
   Drop licensed sound effects into `sfx/` (`cash.wav`, `money.wav`, or any type name to override
   the synthesized ones) and music into `music/`.

Preview the example reel: `cd studio && npx remotion studio src/index.ts`.

## How to get great results
The agent is only as good as what you give it. Do these before you ask for a video:

1. **Collect references of the motion you want.** Save motion graphics you like from Pinterest,
   Instagram, X, Dribbble, YouTube, anywhere, and put the clips in `references/`. Pick pieces in
   the style, pace and standard you want to reach. Five to ten good clips beat fifty random ones.
   The agent watches them frame by frame and writes down the style before it plans anything.
2. **Give it demo footage of your product.** If your product needs showing in action, make short
   prototype recordings of the key flows in Jitter, After Effects, Rive, Canva or as a Figma
   prototype, screen-record them, and drop them in `demos/`. The agent cuts them into the film
   instead of guessing how your product moves.
3. **Point it at your Figma, frame by frame.** Connect the Figma MCP, or paste links to the exact
   frames (right-click a frame → Copy link to selection). Say which frame shows which step: "the
   onboarding flow is this frame, the dashboard is this one". The agent must not design screens
   from scratch. If a scene has no Figma frame, recording or screenshot, it will ask you.
4. **Be strict about slop.** No sparkles ✨, no emoji, no glowing orbs, and **no icons** unless
   they come from your own Figma or icon set. AI picks icons that don't fit your brand, so the
   skill bans them unless you supply them. If you spot slop in a draft, say so and it gets cut.
5. **Tell a story: problem → solution → demo → CTA.** Every video follows this arc. Open on the
   pain your user feels, introduce your product as the answer, show it working (using your demos
   and Figma screens), and end on one clear call to action. Give the agent the problem in your
   customer's words, and it writes the script before the shot list.
6. **Vary the voiceover.** If a video has narration, don't use the same voice every time. Switch
   between male and female voices and accents (American, British, ...) to suit the audience. Bring
   recorded voiceovers, generate them with a TTS service, or use a local model such as Kokoro
   (voices like `af_heart`, `am_michael`, `bf_emma`, `bm_george`). The agent keeps a log so it
   doesn't reuse the last voice.

A project folder ready to go looks like this:
```
references/   clips of the motion style you want (private study only: never put in the film)
demos/        your prototype or product screen recordings
sfx/ music/   licensed sound effects and tracks (optional)
```

## Use
> Make a 20s product video from this Figma: <link>. The style I want is in references/, the
> onboarding demo is demos/onboarding.mp4. Problem: "freelancers lose hours chasing invoices".
> 16:9 and 9:16, CTA "Try it free", British female voiceover.

> Make a 15s launch reel for <product URL>. Calm premium, vertical only, use music/track.mp3.

Claude will ask for anything missing, study your references, write the script, show you a shot
list to approve, build the film, check its own frames over several rounds, add voice and sound,
and deliver one MP4 per format in `output/`.

## Inside
```
SKILL.md                       the pipeline Claude follows
reference/motion-language.md   jitter kit + product presentation patterns
reference/patterns.md          what strong reference pieces do (techniques only)
reference/craft.md             render contract, briefs, shot-list gate, critique loop
reference/figma.md             Figma link → tokens + animatable layers
engine/                        Remotion project: src/motion/lib.ts (springs, track, jitter
                               helpers), ExampleReel.tsx, register.tsx
reference/style-study.md       how the agent turns references/ into a style note
scripts/setup.sh               one-time project setup
scripts/motion.py              beats, sfx + music synthesis, mix, contact sheets, QA
templates/                     shot list and SFX events examples
```

## Licence
The skill is MIT licensed (see `LICENSE`).
Remotion is free for individuals and small teams; larger companies need a Remotion company
licence (see remotion.dev/license). Only use music and sound effects you have the rights to.
