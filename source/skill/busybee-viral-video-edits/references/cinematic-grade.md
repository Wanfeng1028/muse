# The Cinematic Craft Layer & Grade

The calibrated register for edits that must read as S-tier videography: "taken seriously, not laughed at, but not playing it so safe it is boring."

## The calibration (both failure directions are real)

- Effect-forward chaos with mismatched shots → rejected (reads as FX demo, not cinema).
- Pure restraint — soft washed grade, one gentle effect — → rejected as "washed out and really boring."
- **The working formula: RICH dense grade + ONE hard reality-bend per shot.** True blacks, contrast S-curve, saturated committed palette, no milky shadow lift — and then one loud matte/scene-anchored effect per shot, switching on the beat grid. "Insane FX, just not cheesy or corny."

The craft layer runs on EVERY shot identically (this is what makes 13+ shots read as one film); the signature effect changes per shot (one mode per shot, exactly one use of the biggest effect, on the drop).

## The grade recipe (exact, from the proven pipeline)

Apply in linear light, in this order:

1. Linearize: `pow(c, 2.2)`; exposure `exp2(uExpo + flash*exp(-frame/4))` — drop hits are an exposure pop that decays, never a white flash.
2. **Halation**: 10-tap golden-angle disc blur of highlights above threshold 0.42, tinted to the palette (e.g. warm pink `vec3(1.0, 0.58, 0.66)`), gain ramped per shot.
3. **ACES tonemap** (Narkowicz): `(x*(2.51x+0.03))/(x*(2.43x+0.59)+0.14)` on `col*1.12`.
4. **Split-tone**: shadow floor tinted toward the palette (`+vec3(...)*pow(1-l, 2)`, tiny values ~0.02), warm highlight rolloff (`mix(1, vec3(1.03,0.99,0.965), smoothstep(0.55,1,l))`), +6% saturation.
5. Gamma out `pow(c, 1/2.2)`.
6. **2-octave film grain**: hash noise at scales /1.5 and /4.0, amplitudes 0.020 + 0.010, weighted toward shadows. (Viewers PREFER grain — never denoise it away; blockiness/banding/upscale-blur are the real penalties.)
7. **Vignette** `*(1 - 0.20*d2)`.
8. **Letterbox**: soft-edged bars (~140px at 1920 tall), title drawn INSIDE the bottom bar (thin tracking-spaced type, ~26px, white@0.72, fade in 0.6s / out 1.0s).

Plus hair-thin lens chromatic aberration growing toward corners: offset `= uv_from_center * d2 * 0.0022`.

For ffmpeg-only builds, the cheap house grade approximation: `eq=contrast=1.05:saturation=1.08-1.10, vignette=PI/4.6-4.8, noise=alls=5-6:allf=t+u`, with palette-tinted `color=0xFFE9C8` fade-alpha "ember" flash overlays on chosen beats.

## Camera: matte-centroid push-ins

Every shot breathes like it was dollied. Read the subject matte at the segment midpoint, threshold >0.4, compute the normalized centroid (clamp x∈[0.35,0.65], y∈[0.38,0.62] so reframes stay tasteful), and zoom toward it: `suv = center + (uv - center)/zoom` with zoom eased `z0→z1` by smoothstep. Add a small vertical `shift` for reframing. Beat pops: decayed zoom kicks on accented onsets.

## Structure spine (what every cinematic cut shares)

- Cuts authored in beats on the song's grid; assert the drop lands on its bar (±0.02s).
- 4 bars of setup before the chorus/drop; the drop gets the single loudest treatment (echo-bloom trails + exposure pop + flash≈0.55).
- Escalation choreography keyed to (bar, beat-in-bar) anchors: cold-open strobe on the riser's real onsets → inhale (stillness) → possession (transform every beat from the drop) → double-time (half-beat, with 2-frame reality stutters on the "&") → **the gasp** (one dead-still beat, e.g. black silhouette) → overload → release with a wink (2-frame callback). Stillness placed against density is what makes density land.
- Loop seam: return the photometric engine to its frame-0 state over the last ~22 frames so the video loops invisibly.
- Transitions: bloom-throughs (the scene's own highlights flare into the next shot), never stock wipes.

## Iteration case studies (the ladder that produced these rules)

**Dreamcatcher v1→v5** (same window, escalating integration):
- v1 Festival Transmission: 22-shot montage unified by ONE breathing photometric engine (full-band + bass RMS followers, energy-weighted beat pulses driving punch-zoom/bloom/chroma). Proved "many shots read as one world."
- v2 Styleflash: post-pass over v1's finished mp4 with per-frame Vision mattes — subject-only style flashes (pixel/vector/paper) on onsets. First matte-confined FX. Deriving onsets from the finished video's own audio = perfect sync by construction.
- v3 A/B Flush: formalized the reusable pipeline (clean `base.mp4` → mattes on the base → per-frame effects table → mux). A/B pixel-swap snaps; copies split 1→2→4 stepping on beats then swirl inward, strength hopping per onset.
- v4 Glass: same base + mattes + timeline, ONLY the effects logic swapped (36-cell Voronoi shard refraction, shards crack/fall on beats, reassembly snapping tighter per onset). Iteration = swap effect logic on stable infrastructure.
- v5 Shapeshift (culmination): ONE locked still plate, background never changes, only the subject transforms — ~25 style renderers (day_sky, paper, chrome, gold, pixels, thermal, halftone, negative, glitch, cloud, lava, hologram, neon, blueprint, silhouette, real…) composited through the feathered matte, choreographed to full song structure with the escalation spine above.

**With U v4→v7** (the register calibration):
- v4 pure restraint → REJECTED (washed out, boring).
- v5 Lucid: rich grade + 9-style flicker bank → the formula clicks. Client picked one 2s moment (beat-stamp frozen copies → pixel swap with trails) as THE direction.
- v6 Multitude: that moment becomes the whole-cut language — stamps persist across cuts (dimmed ~0.5/cut), natural ghosts in verse → style-bank clones every half-beat from the drop, army decays so she ends alone. Best-received.
- v7 Wallwalk: 20s narrative (absorb-into-wall → cutout pasted across walls as mural/paper/pixel/polygon/glass materials → exit). Lesson: narrative one-concept pieces need dual-source paste machinery + a materials bank.

**Run to U portal arc** (cutaway → integrated): v1 alternated tunnel segments with stills (rejected direction); v3 re-rendered the tunnel on the exact edit window so pulses matched cuts but still alternated (transitional); the integrated build put the portal IN every shot (sky screen-blend growing 150→900px, pond reflection, matte rim-light, edge-wrap light bleed, dolly-through entry, silhouette inside the tunnel) — and the final form fused footage and tunnel in one shader (portal_weave). The client's verdict escalated the integrated-FX rule to absolute.

The generalizable loop: keep infrastructure stable, iterate ONLY the effect language; ship numbered versions; let the client point at seconds they love; make that moment the next version's whole language.
