# BRIEF.md template

Copy this to `BRIEF.md` at the project root and fill every section. Every later agent (critics, builders, composer, reviewers) reads it.

Be concrete: give exact hex values, exact file names and exact numbers with sources. Delete the guidance text in *italics*.

---

# <Company> — <length> launch film: production brief

## Deliverable
- **Length and format:** <60.0 s>, 1920×1080, 30 fps, H.264 MP4 + AAC. Also a 4K master and a poster frame.
- **Audio:** <Music only — no voiceover | VO script attached>. All story is told through on-screen type, product UI and motion graphics.
- **Build:** Remotion project at `<path>/video`. Assets live in `video/public/`.
- **Score:** <original, synthesized, composed to the edit | licensed track `<file>`> on a **<120> BPM grid**. 1 beat = <0.5> s (<15> frames), 1 bar = <2> s, 1 phrase = <8> s.
- **Audience:** <persona(s)>. *Write what they're skeptical of and what they're allergic to (e.g. buzzwords, vague AI claims).*

## What <Company> is (positioning; follow strictly)
- **Live site headline (verbatim):** "<…>"
- **Sub-headline (verbatim):** "<…>"
- **Frame:** *One paragraph: what the product does, for whom, and the outcome it moves.*
- **On-message:** *Phrases and ideas to use (from intake #8 and the site).*
- **Off-message, never use:** *Phrases to avoid; framings the company has retired; superlatives you can't prove.*
- **Footer/brand lines (verbatim):** "<…>"

## The one story
- **Outcome thread followed end to end:** <e.g. "Impression-to-stream +2pp on the home shelf">
- **Goal → approach → result chain:** *How the product gets there, in the product's own steps (3–4 steps), with the on-screen artefact for each step.*

## Copy bank (verbatim from the site/product)
- *Pillar titles and one-liners, step descriptions, product UI labels worth quoting, numbers shown on the site (with the page URL).*

## Proof (real; OK to headline)
| Customer / source | Claim (exact) | Source URL or approval | Logo file |
|---|---|---|---|
| <Customer A> | <+43% notification CTR> | <url> | `public/site/customer-a.png` |

**Caution:** *List any demo/sandbox tenants and their fictional numbers. They may appear inside UI shots but never as headline type or as a customer result.*

## Product UI captures (`video/public/shots/`, 3840×2160 = 2× of a 1920×1080 viewport, each with `<name>.rects.json`)
| file | what it shows (key UI text, where the story beat is) |
|---|---|
| `home_top.png` | *…* |
| `goal_blank.png` / `goal_typed.png` | *the input before/after typing the goal (identical geometry → typing wipe)* |

**Product UI look:** *app chrome colour, panel radius/border, UI font, label style, primary button colour, status colours.*

## Website captures and imagery (`video/public/site/`)
- *Section screenshots: what each shows. Photography or illustrations usable as backgrounds (check licence). Logo files (mark, wordmark, SVG path availability). Customer logos (resolution).*

## Brand system (from the site CSS and `brand.json`)
- **Fonts:** sans <…>, mono <…>, display/serif <…> (Google Fonts name or file).
- **Palette (dark):**
  - page <#…>
  - surface <#…>
  - border <#…>
  - text <#…>
  - muted <#…>
  - brand <#…>
  - accent <#…>
  - status: good <#…>, warn <#…>, bad <#…>
- **Motifs:** *e.g. hairline and dashed connectors, dot grids, uppercase mono micro-labels, photography treatment.*

## Reference film(s): learn from, don't copy
- **What works:** *motifs, type behaviour, pacing moments.*
- **What to beat:** *length, missing real product, missing proof or CTA, etc.*

## Technical constraints
- **Stack:** Remotion 4, React 19, TypeScript. Composition 1920×1080 @ 30 fps, <1800> frames.
- **Fonts:** via `@remotion/google-fonts` (or local `@font-face`).
- **Images:** use `<Img src={staticFile(...)}/>`. Camera moves are CSS transforms driven by `useCurrentFrame()`.
- **Determinism:** no CSS transitions or animations, no `Math.random`.
