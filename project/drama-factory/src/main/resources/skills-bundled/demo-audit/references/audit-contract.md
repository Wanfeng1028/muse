# Audit contract

## Evidence to inspect

Review the actual rendered video and audio, not only a plan or generated report. Bind the audit to the exact plan, approval, and media hashes. Record sampled timecodes, frames or evidence references, speech segments, and the finding each sample supports. Do not retain sensitive text from the screen when a safe locator or state description is enough.

Sample at regular intervals and around each visible click, typing action, drag, important state change, scene seam, and final idle tail. Check the first and last scene boundaries closely. Compare the final third with the earlier portion for rising speech or action density, shortened result holds, or lost orientation.

## Independent semantic checks

- Does the opening orient the viewer and does the ending resolve its promise?
- Does each spoken claim match the visible product state and current evidence?
- Does every active action have nearby spoken purpose or consequence, without robotic control-label repetition?
- Does the action produce the promised result? Is the result still readable after the action?
- Do captions match the canonical spoken words and remain readable?
- Are cursor movement, typing pace, transitions, and viewport behavior natural and accessible?
- Is private information absent from the screen, audio, captions, logs, and exported artifacts?

## Findings and severity

For each finding, include a stable ID, severity, timestamp or scene, observed evidence, expected proof, and earliest owning input. Use `P0` for exposed secrets/private data, misleading proof, or other immediate stop conditions. Use `P1` for a broken required action, unsupported claim, missing narration coverage, unreadable proof, or stale approval. These findings require operator review; they are not waivable by a writer or automated summary. Lower-priority polish must not hide unresolved P0/P1 issues.

Return `pass`, `revise`, or `inconclusive`. Missing evidence, an unreadable frame, inaudible speech, or a hash mismatch is inconclusive until the evidence is repaired. Never infer a pass from file existence, exit status, or a preview label.

## Fail early in rehearsal

Every timing and capture check here should also run in a cheap silent rehearsal before any voice is generated, with the same thresholds and a safety margin. If the audit fails an active action planned after the scene's narration ends, the rehearsal must fail it too, not warn. When an audit finding could have been caught without voice and the rehearsal missed it, fix the rehearsal as well as the plan. See [demo-production-pipeline](../../demo-production-pipeline/SKILL.md).

## Bounded repair and report

Fix the earliest artifact responsible, regenerate only affected descendants, and audit the replacement against all open findings. Stop at the first pass or after six review rounds. If the sixth remains non-passing, report the unresolved findings and stop; do not conceal them with edits or optimistic wording.

The final report names the exact input hashes, reviewer independence, verdict, sampled coverage, closed findings with evidence, remaining findings, operator decisions needed, and publication readiness. Keep the report concise and free of private values.
