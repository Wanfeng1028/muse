# Pitfalls and fixes (each of these happened once)

| Pitfall | Symptom | Fix |
|---|---|---|
| **Stitched story** | The goal is about metric A, the hypotheses about B, the PR about C. Reviewers call it "stitched from unrelated captures". | Pick ONE outcome thread. Rewrite every overlay, label, lane name and chip to belong to it. Re-capture the typed goal to match. |
| **Demo numbers read as proof** | A fictional tenant's "+15%" headline is in focus one second before the "In production" proof section. | Frame tight, or mask with spotlight dimming or blur. Demo numbers never get focus rings or headline type. |
| **Readable off-story text in UI shots** | The real UI shows task names from a different project right under the hero card. | Frame tighter (within the 2.2× zoom limit), or blur and gradient-mask everything below the card. Overlay a rebuilt house-style label that ties the card to the story. |
| **Click with no payoff** | The cursor clicks "Accept" and nothing changes. | Morph the button to "✓ Accepted", flip the status label, fade the alternative button, and move the cursor away. |
| **Double-exposed text at transitions** | Cross-dissolves layer the outgoing caption over the incoming one. Fixed caption bands garble ("03 — EXPLORES IN ·METRIC GOAL"). | Use the dip hand-off in `Main.tsx`: the outgoing layer blurs out before the boundary, and a shared base backdrop shows through. XFADE only between scenes with the same background. |
| **Brightness collapse** | The frame mean drops from 30 to 9 in 3 frames at a section change, which reads as a glitch. | Use a longer ease-out (12 frames) on the outgoing scene, and a base backdrop under every scene. |
| **Detached punctuation after pills** | `[days].` renders as "days ." | The template's `Words` tokenizer attaches trailing punctuation to the pill token. |
| **Over-zoomed captures** | UI looks soft at 3×. | 2× DPR captures stay crisp up to ~2.2× of the 1920 viewport. Capture a tighter state instead of zooming. |
| **Tiny UI text** | A 13 px UI label is the story beat and unreadable at 1080p. | Push in until key UI text is ≥ 20 px on screen, or add a callout chip in house style with the number. |
| **Grade overcorrected** | Asked to make the dawn "paler, cooler", `saturate(0.19)` turned a golden painting grey. | Check grades at full resolution. Keep gentle saturation (~0.55) and warm highlights; brighten via exposure, not desaturation. |
| **Synth score too bright** | Octave bands are +6–10 dB above a pro mix in 1–10 kHz and −4–8 dB below it in 80–320 Hz. | Use `band-match.py` against a reference, then add shelf/peak EQ on the master until bands are within ±4 dB. |
| **Onset "misses" in dense grooves** | The verification report says a soft tick is off by 23 ms. | Check the *placement* error. If it is 0.00, the miss is masking in the detector, not a sync bug. |
| **Interrupted agents** | Workflow agents return "[Request interrupted]" and get retried; long ones never finish. | Keep agent tasks ≤ 15–20 min. Make them resumable ("continue from existing files"), with progress saved to files. |
| **Agents reading huge images** | A storyboard agent opens 26 × 4K PNGs and takes 20+ minutes. | Give contact sheets plus rects JSON. Tell agents to open at most a few full-res captures. |
| **One broken scene breaks every render** | A builder's half-written file kills other builders' bundles. | Isolated entry points (`src/entries/SNN.tsx`) and the per-scene stills tool. |
| **Hidden-tab apps** | A headless/background tab app defers loading content. | The capture script forces `document.visibilityState = 'visible'` and dispatches `visibilitychange`. |
| **SPA with lazy/virtualised content** | Text dumps miss content that only renders when scrolled into view. | Scroll in steps and accumulate per-block text; capture tall pages as multiple scrolled states. |
| **Low-res customer logos** | A 276-px PNG is upscaled next to a 220 px number. | Render logos at native size or smaller, tinted with `filter: brightness(0) invert(1)`, or ask for SVGs. |
| **Synth "reverse cymbal ending on the drop" vs "silence before the drop"** | The two storyboard requirements conflict. | Keep ~0.1 s of true digital silence, then a quiet ~0.14 s reverse-cymbal "inhale" that ends exactly on the downbeat. |
