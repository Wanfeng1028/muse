# Checklist: anti-slop and review

Run this on every cut before you show it. Each "no" is either fixed or written into the delivery notes.

## Story and honesty
- [ ] One tagline, written before the visuals, used as the climax title and on the end card.
- [ ] The story is about the user's pain going away, not a feature tour. Governance and security are one
      beat at most, unless they are the product.
- [ ] Every feature on screen has a source (file, function or command) in the concept doc's table.
- [ ] Every command/output string is verbatim from a sandbox run. Omissions are marked "…" and excerpts
      are labelled.
- [ ] Nothing invented: no fake metrics, star counts, logos, customers, "10x", or capabilities the product
      lacks.
- [ ] Fictional parts (demo repo, test names, data) are listed in the concept doc.
- [ ] The facts you couldn't verify (not run, code-read only, version mismatches) are listed for the user.

## Frame density
- [ ] One idea per frame. At most ~3 blocks on screen (title + 1-2 panels).
- [ ] No frame needs more than ~25 words of prose to be understood, and terminal panes stay under
      ~12 visible lines.
- [ ] Each hold is long enough to read: ≥ 1.5 s after the last line appears, and the narration says it
      while (or just after) it's on screen.
- [ ] No half-empty frames. If a panel enters later, start the first one centred and slide it over.

## Look (slop tells)
- [ ] Light theme unless the brand is genuinely dark. No dark code blocks inside light windows.
- [ ] Palette from the product's own brand/hero/app tokens. Exactly one accent, used sparingly.
- [ ] Distinct from the user's other films (compare palette, type, motif).
- [ ] No glow, no decorative gradients, no emoji, no "✨", no gratuitous checkmarks, no pill/badge piles,
      no uniform card grids, no nested borders/boxes.
- [ ] Shadow rings instead of borders, concentric radii (outer = inner + padding), spacing over
      dividers, one filled primary button per panel (Krehel skills).
- [ ] Real typography pairing, titles with `text-wrap: balance`, weight ≥ 400 under 18 px, tabular
      numbers.
- [ ] Ligatures off in every monospace element (`->`, `!=`, `--`, `>=` render as typed).
- [ ] Motion: ease-out entrances, slow camera, crossfades. No bouncy springs on everything, and nothing
      flies across other content.

## Contrast and layout
- [ ] `npm run check:contrast` passes. Every text colour is AA (4.5:1) on every surface it sits on,
      including tinted highlight backgrounds. Labels and metadata are not faint grey.
- [ ] `npm run check:layout` passes: safe area, min gap, mono fit, title fit, no scrolling panes.
- [ ] Audit contact sheets reviewed: no overlaps mid-animation, nothing cropped, no blank frames, no text
      collisions during slides or crossfades.
- [ ] Highlight tints don't include leading/trailing spaces, and wrapped lines don't start with a space.

## Sound
- [ ] Narration is conversational (contractions, short phrases, second person) and doesn't just read out
      the screen.
- [ ] Every line ends inside its scene with air before the cut, and the timeline is fitted to the
      measured takes.
- [ ] STT transcript of every take matches the script. The product name is recognised; if not, the line
      is rewritten.
- [ ] Prosody check: no flat takes; the pick per line is recorded in the manifest.
- [ ] Music is ducked ~12 dB under speech, and SFX are subtle and tied to on-screen events.
- [ ] Master: I = -16 ±0.5 LUFS, true peak ≤ -1.5 dBTP, and the limiter is active on < ~10% of samples.
- [ ] Credits: voice name/model/plan, music source, fonts, icons, Remotion licence, and attribution on the
      end card if the plan requires it.

## File
- [ ] `ffprobe`: duration as planned (40-60 s), 1920×1080, 60/1 fps, `yuv420p`, h264 + AAC 48 kHz.
- [ ] Rendered from PNG frames with CRF 18. Old versions are still renderable from their own compositions.
- [ ] No secrets in the repo (`rg -i "api[_-]?key|secret|token|sk-|xi-api"` before every commit), and
      no large media committed unless intended.

## Delivery notes
- [ ] MP4 path, key stills, tagline, per-scene summary, narration text, features-shown table with
      sources.
- [ ] Unverified facts, fictional parts, weak spots, characters/credits used, licence limits.
- [ ] "Nobody has listened to this yet", if that's true.
