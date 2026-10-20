# Rights rules for 24fps material

Source: https://24fps.dev/rights. Check it for changes before relying on this copy.

## Clips (https://24fps.dev/c/{slug})

- **Open-licensed clips** (creator published them under MIT, Apache-2.0, CC BY or CC0): a short preview loop, the full prompt, and the code linked with its licence. `get_source` returns `available: true` and an attribution line. Keep that attribution.
- **All other clips** (shared publicly on X or listed in a community collection): a still, a link to the original, the prompt in full if it is 280 characters or less (otherwise an excerpt and a link to the post). `get_source` returns `available: false`. Do not request the source yourself; tell the user they can ask the creator through the clip page.
- Always credit the creator by handle and link the clip page. Never rehost a third-party clip or its video.
- Clips are labelled with the model their creator reported. Nothing in the library is owned by 24fps, and it is not sold as training data.

## Editor presets (https://24fps.dev/video-editor)

- Presets are original recreations of editing techniques and are MIT, as is the engine at https://24fps.dev/editor/engine.js. Credit line: "24fps.dev/video-editor".
- Fonts are Google Fonts under open licences. Sound-design cues name a type of sound, not a file.

## Open-source catalogue (https://24fps.dev/video-editor/open-source)

- Each row shows its own licence and links to the code.
- Copy code only from MIT, Apache-2.0, BSD or OFL rows, and keep the licence and any NOTICE file.
- Remotion-licensed rows and rows with no licence stated are link-only. Recreate the idea; do not paste their source.
- Some rows bundle fonts or sounds with their own licences (for example Remotion sound effects, where each sound has its own licence). Check the item before shipping it.

## Creators

Creators can claim or remove their work at https://24fps.dev/submit. Removal takes up to 2 working days.
