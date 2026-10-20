# Delivery checks

Run these after the semantic checks in [the audit contract](audit-contract.md), against the exact rendered file and the channel named in the brief. Repair a failure at its owning input and render again; re-encoding a reviewed video changes the hash its review is bound to. They catch problems that course platforms and accessibility reviewers reject even when every action and claim is correct. The defaults below come from published platform and accessibility guidance; when the destination publishes its own specification, that specification wins.

The runtime does not yet normalize loudness, produce sidecar captions, or emit chapters. Measure these here instead of assuming them, and record each measurement with the media hash.

## Picture

- **Size and shape.** Course platforms expect at least 1280×720 and exactly 16:9. The runtime renders at the plan's viewport size with a device scale factor of 1, so the viewport sets the delivered resolution.
- **Legibility at the smallest screen.** Scale sampled frames down to phone size (about 640×360) and confirm that the proof, labels, and values are still readable. At 1080p, essential text smaller than about 16 px (1.5% of the frame height) is too small; prefer a 1280×720 viewport or larger app text over a larger viewport with small text.
- **Nothing happens.** Watch the video with the sound off. The screen should carry the lesson; a long stretch where the frame does not change while narration continues means the scene is talking instead of showing. Hold a finished result long enough to read, but flag a frozen frame longer than about 8 seconds. `ffmpeg -i render/demo.mp4 -vf freezedetect=d=8 -map 0:v -f null -` lists candidates.
- **Flashes.** Use the conservative sufficient rule: no content flashes more than three times in any one-second period, regardless of area. WCAG exceptions require checking the general/red-flash thresholds or measuring the combined flashing-area limit; this checklist does not evaluate those exceptions. See [WCAG 2.3.1](https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html). Check rapid toasts, flickering loaders, and zoom or transition effects.

## Sound (narrated mode)

Captioned mode has no audio track; skip this section for it.

- **Loudness.** Measure with `ffmpeg -hide_banner -nostats -i render/demo.mp4 -af ebur128=peak=true:framelog=quiet -f null -` and read `I:` (integrated) and `Peak:` from the summary's true-peak section. Project default, not a platform target: −16 LUFS integrated (±1 LU) with true peak at or below −1 dBTP. The tolerance may extend beyond EBU R128 s2's conditional interim range; this is not an EBU conformance check. Lessons in one series should sit within 1 LU of each other; volume that jumps between lessons is a listed rejection reason.
- **Both channels.** Speech must be present in both left and right channels. The per-channel RMS levels from `-af astats` should match closely; a silent channel is a defect.
- **Dead air.** Flag silence longer than about 5 seconds (`-af silencedetect=noise=-45dB:d=5`). In supplied human recordings, also flag filler words, false starts, and long pauses; trim them rather than speeding up the voice.
- **Clarity.** Synthetic speech must pronounce every product name, acronym, and term in the brief's pronunciation list correctly. Listen to each one.

## Captions

Check the cues as delivered, both the burned-in captions and any sidecar file:

- No more than 42 characters per line and 2 lines per cue.
- No more than about 20 characters per second of display time.
- Break lines at phrase boundaries, after punctuation or before a conjunction or preposition, not between an article and its noun.
- Timing follows the speech rather than an even split across the scene.

The runtime's burned-in captions split each scene's text into fixed 14-word chunks spread evenly over the scene. These chunks often exceed the line limit; report it rather than calling the captions readable.

## Deliverables the channel needs

Derive these from the canonical spoken text and the scene timing in `render/timeline.json`, and check them against the final video hash:

- **Sidecar captions** (WebVTT or SRT) whose words match the canonical narration exactly.
- **Descriptive transcript:** the spoken words plus each visible result the audio does not state, in scene order. Publish it with or directly beneath the video. When narration already states every essential visible result, no separate audio description is needed.
- **Chapters** from scene titles: the first at `00:00`, at least three, ascending, each at least 10 seconds long.
- **Title and summary:** a task-shaped title ("How to share a read-only chart") and a one- or two-sentence summary that names the outcome.
- **Disclosure:** when the channel requires it, state that the voice is synthetic or that AI assisted production.

## Length

For course or tutorial lessons, use about six minutes as an educational-video planning guide, not a universal duration target or automatic rejection threshold. [Guo et al.'s MOOC study](https://up.csail.mit.edu/other-pubs/las2014-pguo-engagement.pdf) recommends short instructional chunks; it does not set a minimum or a marketing-video length. For other demos, compare duration with the approved brief and destination. If a course or tutorial lesson runs longer than about six minutes, consider a split at a meaningful task boundary. Do not shorten holds or speed up speech to fit.

## Severity

Use `P1` when a delivery problem makes required proof unreadable or inaudible, drops a channel, breaks the flash limit, or misses a hard requirement of the named channel. Use `P2` for other measurements outside their target. Report the measured value, the target, and the command or sample that produced it.
