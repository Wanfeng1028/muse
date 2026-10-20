# Remotion Studio workflow

Resolve `gtm-os` at the repository root or inside this installed skill at `assets/gtm-os`. Read its README, then initialize an isolated deliverable with `tools/init-project.py`. Run `npm ci`, `npm run typecheck`, and `npm run studio` from the copied `05_Code` directory. Select the intended composition in Studio's sidebar rather than editing an unused historical scene file.

| Composition | Source / story | Duration at 30 fps |
| --- | --- | --- |
| Launch | `src/Root.tsx` | 24 s |
| UiMockup | `src/UiMockup.tsx` | 12 s |
| DiagramLoop | `src/Diagram.tsx` | 8 s |
| SlackThread | `src/SlackThread.tsx`, `src/slack-story.ts` | 31 s |
| OpenMuseLaunch | `src/ProductLaunch.tsx`, `src/product-stories.ts` | 36 s |
| OpenDotsLaunch | `src/ProductLaunch.tsx`, `src/product-stories.ts` | 32 s |

`compositions.json` supplies metadata to both Studio registration and export verification. `remotion.config.ts` supplies CLI defaults. The product recipes share layouts but have separate beat content in `product-stories.ts`. Keep `framesPerBeat × beat count` equal to registry duration when changing timing. Update review frames to include both sides of each scene boundary plus critical action/result states.

`npm run review -- OpenMuseLaunch OpenDotsLaunch` renders stills into a unique ignored review directory. Inspect those files, then render the full film with `npm run render:openmuse` or `npm run render:opendots`. Use `node render.mjs OpenMuseLaunch out/revision-2.mp4 1` for another output name, or scale `2` for a direct 4K render. Existing exports are protected. The render wrapper verifies dimensions, duration, frame rate, and full decode.

Frames are local to each Sequence. Keep state derived from `useCurrentFrame()` and avoid timers, network data, wall-clock animation, or random values without a fixed deterministic source. Review by seeking as well as playing. Keep imported media local and document it in `public/asset-manifest.csv`.

The bundled films are silent illustrations. Their captions and neutral CTA placeholders are part of the template's honest representation. Before making a public product film, replace placeholder URLs, validate product claims against current evidence, and decide where the illustration disclosure belongs in the film and handoff.

Official references: [configuration](https://www.remotion.dev/docs/config), [compositions](https://www.remotion.dev/docs/composition), and [still rendering](https://www.remotion.dev/docs/cli/still).
