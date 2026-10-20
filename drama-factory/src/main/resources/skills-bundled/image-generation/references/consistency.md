# Consistency

Cast, drift checks, palette, style across a set, world and props, across providers.

Contents
1. Consistency playbook

---

## Consistency playbook

**Cast.**
- Generate one character sheet first. Characters full body, evenly spaced, nothing overlapping, plain white, even light, front three-quarter view. Approve it before any scene.
- Per character, write a locked descriptor string covering: age, skin as a name, hair (length, texture, style), each garment with colour name, and one signature item. Paste it verbatim into every prompt that shows the character.
- Repitis worked with one shared sheet of three people.
- One pipeline goes further: separate files per view (face, full front, full back), one character per sheet, and the first approved frontal face as the ONLY identity reference ever. Identity never passes through intermediate scene images, so drift can't compound. Prefer this when a character appears in more than 15 shots or in image-to-video.
- For lip-sync, include at least two open-mouth expressions on the sheet.
- Generate an outfit change as identity anchor + outfit reference (flat lay or headless).

**Drift checks.**
- After each batch, make a contact sheet of every image with that character, next to the sheet.
- Compare, in order: silhouette and proportions, skin tone, hair, garment colours and brightness, signature item, then face.
- Thresholds from one pipeline: more than 15% drift on any axis is P0; 5-15% re-rolls only that shot, at most twice; persistent drift escalates.
- Watch adjacent characters converging. Repitis asked for Papá with "light brown skin" and Mamá with "warm brown skin"; they came out the same tone. If the difference matters, make it big and repeat it in every prompt.
- Never use a rejected image as a reference. Mark rejects in the filename or move them to `raw/`.

**Palette.**
- Give every colour a name plus a hex value, and add the forbidden neighbour ("cool off-white, never cream or beige").
- Hex values are hints, not guarantees. Models anchor to the reference image's brightness more than to a hex code: "DARK CHARCOAL #3A3A3D" rendered light grey from a brightly lit reference. Make the reference itself carry the right values.
- Expect strays and decide early whether to accept or fix them. Repitis accepted greys outside the palette on wolf/rat/donkey.
- FLUX.2 honours hex when you tie it to an object ("the mug in color #FF0000"). FLUX 3 prefers colour words. Recraft takes RGB in `controls.colors`.
- To force exact brand colours, recolour flat regions in post (vector or per-pixel mapping); don't regenerate.

**Style across 20-50 images.**
- Use the same suffix, model and quality tier, and the same backdrop line.
- Generate in this order: environments, then props, then characters, then scene stills, so later images can cite earlier ones.
- Keep the aspect ratio constant within a series.
- Re-check the whole set side by side before animating anything.
- Expect texture creep. "No paper grain texture" still produced a faint fibre texture on gpt-image-2. If it's consistent, accept it as the look.

**World and props.**
- Make empty-set reference plates (about 3) and a prop sheet. Pass them as numbered references with roles ("Image 2: the kitchen, for layout and lighting only").
- Keep counts and states explicit: which hand holds the phone, lamp on or off, the notebook open.
- Keep surfaces that will carry real UI or text blank and flat in the image: "The phone screen is a plain light rectangle with nothing on it", "the card is plain white with nothing on it". This let Repitis composite the real card face and the real app.

**Across providers.** If a second provider is unavoidable (for example a 21:9 plate from Gemini), pass the approved
images from the first provider as style references, restate the suffix, and grade both to a shared target in post.
Don't mix providers within one character.
