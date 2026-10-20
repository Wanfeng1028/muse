# Visual review

Inspect actual output, not just the source or a successful typecheck.

- **Hierarchy:** At reduced size, can the viewer identify the request, the action, and the result? Enlarge the UI itself if not.
- **Bounds:** Check longest text, button labels, active states, badges, cursor extents, and all edges during entrance/exit. Overflow clipping can conceal a layout mistake.
- **Causality:** Does the pointer arrive before the press? Does success follow approval? Is the visible result consistent with the input?
- **State:** No empty author rows, preallocated invisible cards, stale video frames, accidental flashes, or scroll positions that hide the current action.
- **Consistency:** Shared padding, baseline, radii, borders, typography, asset scale, and theme across scenes. The user's chosen product theme wins over the reference's background.
- **Geometry:** Lines touch their actual ports. Pulses follow the wire. Shared buses don't form a crooked staircase. Remove legends that repeat labels.
- **Timing:** Hold long enough to read the result. Check the whole clip at normal speed; stills cannot reveal jitter or awkward pacing.
- **Representation:** Actual recordings and illustrated UI are labeled accurately in the delivery notes. No invented task outputs presented as live evidence.
- **Media:** Probe width/height, duration, frame rate, and codec; decode the full exported file. Container resolution does not establish source detail.

For an editor handoff, include the raw UI/assets and source, not only a flattened movie. State the dependency install and render command, edited timings, and any speed changes. Keep private data and unrelated project files out of the package.
