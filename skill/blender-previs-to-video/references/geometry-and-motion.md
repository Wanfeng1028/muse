# Action-critical geometry and motion

## Hands and contact

- Establish handedness, palm/back orientation, wrist direction, visible fingers and which surface receives contact. A front-covering hand and a rear supporting hand must occupy different sides of the device.
- Represent one connected palm and five anatomically proportioned fingers. Simple ellipsoids and short rounded segments are sufficient when their silhouette and joint direction are credible. Extend a reach by moving the palm/arm before stretching a finger.
- For a grip, specify which fingers are in front, behind and around an edge. Do not infer a front-facing palm merely because fingers are visible. Inspect both the camera view and a useful side view if contact is ambiguous.
- Keep finger lengths stable through a gesture. Two opposing thumb/index L shapes can imply a rectangle with gaps; do not connect fingertips unless the intended gesture does.
- Avoid rings, fused loops and excessive seams from overlapping primitives when they read as anatomy. Union or smooth only as needed while preserving distinct finger silhouettes. A prettier surface does not fix an incorrect joint or grip.
- Preserve supporting contacts while the object moves. Shared parent transforms work for rigid grips; animated contact points or constraints suit a fingertip following a rotating panel. Verify release timing before the hand withdraws.
- Remove hands or change a difficult action only when the user has chosen or authorized that creative change.

## Products and visible surfaces

Model topology before decoration: rigid slabs, hinged leaves, hinge axis, front/outer cover, inner display and rear-camera housing. Keep each visual feature attached to its physical surface throughout rotation or folding.

Map an appearance sheet's views to one object explicitly. A front/back sheet does not request two phones; an open foldable's outer surface pair is not its inner display. Minimal camera markers can help disambiguate a rear surface, but should not become extra lenses in the final identity.

Use deliberate screen placeholders. If the final screen content is specified, hand off the image and the surface assignment. Do not add decorative dots, flowers or arbitrary proxy marks unless they are intended to survive. If content is intentionally left to the model, record that as a creative choice rather than a reliability rule.

## Motion

Give important movements appropriate acceleration, deceleration and settling. Avoid speed discontinuities at intermediate keys unless a snap is intended. Preserve requested cut timing, holds and fast actions rather than smoothing every shot into slow motion.

If human micro-movement is desired, distinguish subtle hand steadiness from camera shake and from unwanted animation jitter. Move the supporting hand and held object coherently so their contact does not slide. Keep amplitude subordinate to the main action and inspect the render; a formula is not evidence that motion looks human. Unsupported packshot objects need not inherit hand motion.

Choose motion amplitudes and easing for the current action; respect stylized/mechanical motion when the user requests it.

## Review and preservation

Choose review frames around action changes: initial silhouette, approach, contact, hinge midpoint, release, overlap, rotation edge-on and final pose. Check the newly exposed rear and inner surfaces as well as the initial front. Also check that every visible background, prop and effect proxy is either intended as final appearance or listed as a placeholder with a replacement source.

Use numeric verification where it answers a real failure risk: rigid finger lengths, a tracked contact point, panel angle limits, interpolation overshoot, exported frame counts, or preservation of an approved earlier segment. Explain the limit of each check. A contact-point error near zero does not prove that the entire mesh is collision-free.

For a continuation, keep source absolute times and local clip times in the manifest. The first frame of the submitted continuation has local time zero regardless of its time in the full source. Frame boundaries should be explicit about zero/one indexing and inclusive/exclusive ends.
