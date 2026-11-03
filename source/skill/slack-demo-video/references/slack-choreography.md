# Slack choreography

Keep the workspace rail, selected channel, channel header, message author, attachment, reply affordance, and thread panel recognizable. Use stable layout geometry; names are short enough to fit without shrinking all type. Match real supplied references where useful, but replace private workspace/customer content with approved synthetic data.

The bundled timing is deliberately slower than machine execution:

| Frame / time | State |
| --- | --- |
| 16 / 0.53 s | Request begins typing in full-width channel composer |
| 126 / 4.2 s | Send press; message and attachment appear |
| 164 / 5.47 s | Cursor selects the reply affordance |
| 168 / 5.6 s | Thread panel slides in; channel reflows |
| 207 / 6.9 s | Scout acknowledges the request |
| 239 / 7.97 s | Native progress rows begin |
| 363 / 12.1 s | Draft is ready for review |
| 429 / 14.3 s | Cursor presses approval |
| 465 / 15.5 s | Save completes; progress collapses |
| 501 / 16.7 s | Saved Page result with sections, fields, and action buttons |
| 609 / 20.3 s | Morgan replies; thread scrolls |
| 714 / 23.8 s | Jules replies; thread scrolls again |
| 797 / 26.57 s | Reactions arrive; hold through frame 929 |

Change both the schedule and the review-frame list when revising timing. Keep the composition long enough for a readable final hold. Clean and branded modes use the same logical geometry, transformed with the whole UI.

For Block Kit-style output, use a heading/section for the result, two-column fields for compact metadata, a divider between content groups, actions for a decision, and a context line or separate receipt for the destination. These are mock visual components. Validate actual Block Kit payloads separately if implementing a real bot; this template supplies no API payload or execution.

Cursor movement ends before the click. Cursor targets are declared in `slackGeometry`. Check them against the rendered controls after changing copy or layout, including the full-width send control and thread reflow. The click should cause a pressed state, followed by saving, followed by the receipt. Keep the cursor away from copy during reading holds. Do not move it to irrelevant controls to fill time.

Use event-gated mounting instead of transparent messages that reserve layout height. At the longest state, confirm the conversation and reactions fit. If more replies are needed, deliberately scroll or reflow the mock UI with frame-based offsets; do not let the last block silently disappear offscreen.

## Match the native reference

Keep the dark desktop chrome, narrow app rail, workspace sidebar, channel tabs, date separator, compact timestamps, APP badge, mention styling, Markdown attachment, formatting toolbar, and separate thread composer. Open the thread after the click rather than displaying an empty thread at frame zero. Match the source reference’s density and spacing before enlarging components for readability; large generic cards are not a substitute for native Slack structure.

Result blocks sit directly on the message surface. Use a thread scroll to keep later messages visible, with the composer pinned outside the scrolling viewport. Keep typing indicators and reactions restrained. Compare the new stills side by side with the supplied reference; do not declare visual parity from compilation alone.
