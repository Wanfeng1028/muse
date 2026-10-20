# Prompting

Prompt anatomy, locked style suffixes, edit prompts, negatives per model, style recipes per format.

Contents
1. Prompt anatomy
2. Style-system recipes

---

## Prompt anatomy

### 1.1 Order and content (works across OpenAI, Gemini, FLUX, Seedream)

Write natural sentences, not tag soup. OpenAI's own guide: "organize the prompt as scene, subject, details, and
constraints, using labeled sections" for complex requests, and any format (paragraph, labelled lines, JSON) is fine
if it is easy to maintain. BFL and Google both say sentences that state relationships beat keyword lists.

| Block | What to write | Example |
|---|---|---|
| Use / asset type | what the image is for | "Cutout illustration for a 16:9 motion-graphics film" |
| Subject | who/what, with the locked descriptor | "Tomás, a five-year-old boy, warm brown skin, short dark wavy hair, sky-blue t-shirt, navy shorts, tomato-red sneakers" |
| Action / pose | verbs, gaze, hands, contact | "holds a blank white card up with both hands, looking at it, mouth open as if reading aloud" |
| Setting | only what the shot needs | "Only the three characters and two stools; no walls, no floor" |
| Composition | framing, placement, margin | "full body, feet included, centred, 10% empty margin on every side" |
| Camera | height, distance, lens feel | "eye level, medium-wide, no perspective distortion" |
| Light | direction and quality | "soft key light from upper left, no rim light" |
| Style / medium | the locked suffix | (see 1.2) |
| Palette | names plus hex, and the forbidden drift | "light areas cool off-white #F3F6FB, never cream or beige" |
| Constraints | the specific exclusions | "No text, no letters, no numbers, no logos, no border, no watermark" |

Length: no vendor publishes a hard optimum. Shipped Repitis prompts were about 230 words with the suffix and worked
on gpt-image-2. One skill pack suggests 100-180 words for ideation, 180-320 for complex scenes, 90-200 for
edits. OpenAI's edits endpoint accepts prompts of up to 32,000 characters, so length isn't the constraint. Clarity is.
Midjourney is the exception: "Short and simple prompts typically generate the best images".

### 1.2 Locked style suffix template

```
Style: <medium and construction, e.g. "Flat cut-paper collage. Built from overlapping pieces of matte coloured paper
with crisp, clean scissor-cut edges. Depth comes only from flat shapes overlapping each other">: no gradients, no
shading, no bevels, no soft 3D, no drop shadows, no outlines. <Face grammar, e.g. "small dark dot eyes, short
paper-strip eyebrows, a simple small mouth shape that shows the emotion">. Palette: <name #HEX, name #HEX, ...>;
<skin rule>; <light-area rule>. Light from <direction>. No text, no letters, no numbers, no logos, no border.
<Backdrop line: "Plain flat solid pure white (#FFFFFF) background with nothing on it, no floor shadow." OR
"Transparent background." (only with background=transparent on a model that supports it)>
```
Send as `"<subject prompt>\n\nStyle: <suffix> <backdrop>"` (what `gen_image.py` does). Never edit the suffix
mid-project; if you must, bump a style version and regenerate the set or accept the seam knowingly.

### 1.3 Edit prompt template (references and changes)

```
Image 1: identity and outfit reference for <names> (the cast sheet). Image 2: layout reference (pose only, ignore its
style). Edit: <the new scene, one change at a time>. Keep exactly: <face shapes, hair, outfit pieces and colours,
proportions, palette, line style>. Change only: <pose, expression, framing>. Do not add: <new characters, props,
text>. <Locked style suffix>
```
OpenAI: "Identify each input by number and purpose", "say 'change only X' and list the details to preserve",
"restate critical constraints if the result drifts". Responses-tool tip: say "edit the first image by adding
this element from the second image" rather than "combine/merge". Name what each reference must NOT control
(a style reference must never override identity).

### 1.4 Negative constraints per model

| Model | Mechanism | Practice |
|---|---|---|
| OpenAI GPT Image | natural-language exclusions inside the prompt; no parameter | "State exclusions such as unwanted text, logos, or watermarks". Pair each negation with a positive. Prompt text beats API params: a described backdrop overrides `background=transparent` |
| Gemini image | none; "semantic negative prompts": describe the wanted scene positively | "an empty street" not "no cars" |
| FLUX 2/3 | none; "Include only what you want in the image" | avoid "no blur" phrasing; it can summon the thing |
| Midjourney | `--no` parameter; words "no cake" in the prompt can produce cake | always `--no` |
| Ideogram | `negative_prompt` on 3.0 only; none on 4.x | |
| Recraft | `negative_prompt` on V3 only | |
| Veo / video | describe absence positively ("a landscape with no buildings") | |

Hard constraints that keep failing: state them three ways (positive near the top, negation in the middle, scope rule at
the end). One practitioner reports about 50% compliance said once vs about 95% said three ways.

### 1.5 Style anchors, artists, and rewriters

- Anchor style with medium + construction + era/movement + palette + texture rules ("1960s Swiss poster, flat
  screenprint, two overprinted inks, visible registration offset"), or with your own reference images. Never name a
  living artist: OpenAI refuses living-artist styles (policy since DALL-E 3, repeated for GPT-4o images),
  it is ethically poor, and it weakens any indemnity claim ("knew or should have known" exclusion). Never name
  trademarked characters, mascots or studios' proprietary designs.
- Rewriters: the Responses image tool revises your prompt (read `revised_prompt`); FLUX.2 upsamples by default
  (`disable_pup: true` to stop); Ideogram `magic_prompt` defaults to auto; Recraft has an enhance call;
  Gemini "thinks". When exact wording, brand palette or blank props matter, turn rewriting off or use the Image API
  directly, and write locks as literal sentences the rewriter can't paraphrase away ("the card is plain white
  with nothing on it").

## Style-system recipes

| Format | Prompt pattern (what to lock) | What breaks | Fix |
|---|---|---|---|
| Kids / storybook | medium (cut paper, gouache, crayon), 4-7 shapes, limited palette with hex, face grammar (dot eyes, no nose lines), "friendly but not a cute mascot", "inanimate objects have no face" | objects grow faces; gendered nouns drawn as the wrong gender (profesor/médico came out as women); ambiguous subjects (potato read as a sponge); cream drift | subject overrides with physical traits and gender stated; "no face on objects"; "never cream or beige"; check at the size the child sees |
| Flat vector explainer | "flat vector illustration, geometric shapes, uniform stroke weight X or no strokes, 2-tone shading max, palette hex, isometric or straight-on view" | gradients and glossy highlights creep in; perspective inconsistency between props | Recraft vector + colour controls; state one view for all props; recolour in SVG |
| Editorial / collage | "paper collage of cut-out halftone photo fragments and flat colour shapes, visible cut edges, two-ink riso palette #.. #.., off-register" | photographic fragments of real people or brands; mushy halftone | describe anonymous or abstract fragments; generate fragments separately and collage in code |
| Photoreal (people, places, product context) | "real photograph, 35mm, natural window light from left, honest and unposed, visible skin texture, slight asymmetry"; avoid "studio, polished, cinematic" which collapse realism. OpenAI: say "photorealistic" explicitly; camera specs are appearance cues, not physics | plastic skin, extra fingers, perfect teeth, fake brand labels | anti-AI cues (pores, asymmetry); hands in simple poses or out of frame; never the real product; disclose (`legal.md`) |
| 3D / clay | "soft clay render, matte plasticine, visible finger marks, rounded forms, single softbox from upper left, shallow depth of field, pastel palette #.." | inconsistent material between shots; lighting changes per image | keep one lighting sentence verbatim; pass an approved render as material reference |
| UI-adjacent abstract (product launch backdrops) | "abstract shapes of <material: frosted glass panes, paper strips>, brand palette #.., large negative space at left for headline, no text, no interface, no icons" | fake UI, gibberish labels, icon soup | ask for materials and shapes only; real UI composited; keep negative space where type goes |
