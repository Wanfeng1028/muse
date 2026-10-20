---
name: yt-experiments
description: Track originals and single-change social video experiments, generation credits, and manually entered or screenshot-derived analytics at 24 hours, 72 hours and 7 days.
---

Use [manual entry page](assets/analytics-entry.html) for quick manual entry or `tracker.py` for validated
records. See [usage reference](references/usage.md) for commands. Every variant links one original on the same
platform/profile and changes one thing: opening only, restyle, or mashup. Record total
generation credits, including retries; zero is allowed, unknown cost must be clarified.

Checkpoints are fixed at 24h, 72h and 168h after each upload. Store actual observation time
and timezone, never pretend a late observation was taken at the due time. Compare the same
checkpoint only when both observations are within the chosen tolerance (default 2h) and
their actual ages differ by no more than that tolerance. Otherwise report unmatched data.

Manual input is a first-class source. For screenshots, transcribe only clearly readable
values; store filename/reference and actual capture time. Mark ambiguous readings uncertain
and exclude them from conclusions. Do not require retention exports from TikTok/Instagram.
Record views, shares, saves, likes, comments, average watch seconds, completion percent and
2-second retention where available; absent values are missing, not zero. Ask only for numbers
needed for the comparison. The manual page imports/exports the tracker's JSON store.

Report profile-specific matched-age results and extra views per credit, with evidence size
and uncertainties. A single repost is an observational test, not proof of causation. Do not
schedule reminders or post content unless the user requests those actions.
