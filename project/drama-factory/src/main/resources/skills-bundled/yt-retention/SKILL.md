---
name: yt-retention
description: Analyse explicitly labelled retention data or readable analytics screenshots to locate sampled drop intervals and propose a pacing or opening experiment.
---

For CSV run `python retention.py data.csv --units seconds --duration 60`, or
`--units percent --duration 60`. Units are mandatory; percent positions need duration.
Default headers are `position,retention`; specify real names with `--time-column` and
`--retention-column`. Inspect rejected rows and column semantics. Numeric summary rows
that resemble measurements cannot be detected reliably; do not claim perfect cleaning.

The output measures loss in percentage points over the first 30 seconds (or available
shorter window), and drop intervals. Sampled curves do not identify exact exit seconds.
`--transcript` adds nearby speech, but inspect frames for visual causes too. No universal
healthy threshold or automatic diagnosis from curve shape. Use profile/format baselines.
For a known 0:02 problem, consider a first-two-seconds-only experiment via yt-repurpose.

TikTok/Instagram screenshot-only data can be entered manually via yt-experiments. Record
only visible values, time and source; mark ambiguous readings uncertain. Do not require a
downloadable file to provide useful advice. Name the strongest supported finding and one
change; distinguish measurements, hypotheses and missing evidence.
