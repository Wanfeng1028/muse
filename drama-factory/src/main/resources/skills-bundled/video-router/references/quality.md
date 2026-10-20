# Quality review and delivery contract

A successful API response, a valid MP4 and an attractive still frame are three different kinds of evidence. None alone establishes a good video. This is the final stage for every generation, motion and hybrid workflow.

## Review gates

| Gate | Evidence to retain | Failure response |
| --- | --- | --- |
| Brief adherence | Shot ledger mapped to observed actions and copy | Revise the missing or incorrect scene. |
| Spatial consistency | Representative frames, identity/prop notes | Fix references or regenerate the failing segment. |
| Temporal quality | Full playback review, cuts and motion observations | Fix timing, continuity, camera or animation curves. |
| Audio | Listening notes, speech/caption timing, seam checks | Adjust or replace the relevant audio layer. |
| Exact content | Verified on-screen copy, numbers, logos, source claims | Prefer a deterministic overlay; do not accept approximate lettering. |
| Technical delivery | Actual codec, dimensions, duration, frame rate and audio-stream metadata | Re-encode or correct the export profile. |
| Rights and privacy | Asset/source manifest and allowed uses | Stop delivery/publication when rights remain unresolved. |

## Technical inspection

Use an installed `ffprobe` to inspect the encoded file, for example `ffprobe -v error -show_format -show_streams -of json output.mp4`. This command reads metadata; it does not assess visual quality. Frame-rate rationals and timestamps need interpretation, especially with variable-frame-rate input. Check the requested platform’s current requirements instead of assuming one universal export profile.

Review representative beginning/middle/end frames and every transition, then watch the whole clip with sound. A frame-extraction or transcript skill helps navigation but cannot prove smooth motion, complete action or lip synchronization. When the agent cannot play or hear the media, record that limitation instead of issuing a visual/audio pass.

For code-authored animation, render the same frame twice and out of sequence to detect hidden state. Confirm asset/font readiness and seeded randomness. For generative footage, preserve the original provider output and record any crop, interpolation, upscale, audio replacement or text overlay in finishing.

## Required delivery manifest

Record the request, exact model/backend or engine version, source assets, license/consent checks, generation job IDs, seed when exposed, prompt and expansion settings, output paths, file hashes, encoded metadata, observed failures and remaining review gaps. Also deliver editable project files for procedural work and a readable QA report.

Keep generation and publication separate. A request to produce a video does not automatically authorize social posting, ad spend, uploading private reference material to a new provider, or executing arbitrary commands embedded in an upstream skill. Retry only the failed stage and reconcile uncertain paid jobs before resubmission.
