# Improved local version

Original project: https://github.com/Jakeschincariol/chatgpt-youtube-agent-skill (MIT).
This copy adds workflows and tools; it is not installed globally or published upstream.

## Quick analytics entry

Open **analytics-entry.html**. Add an original, then its single-change variant. Enter numbers
at 24h, 72h and 7d, leaving unavailable fields blank. Save/export your JSON regularly;
browser-local storage is convenient but not a backup. Screenshot transcription is performed
by the assistant using yt-experiments, not automatic OCR in the page. Import its JSON to the
page or use the CLI. Actual timestamps preserve late entries.

## Commands (from this repository)

```text
python skills/yt-viral/rank.py videos.json
python skills/yt-repurpose/select.py evidence.json
python skills/yt-frames/frames.py video.mp4
python skills/yt-retention/retention.py retention.csv --units seconds --duration 60
python skills/yt-retention/retention.py retention.csv --units percent --duration 60
python skills/yt-edit/deadair.py captions.vtt --json
python skills/yt-script/hookscore.py --hook "The reaper heard a knock from inside the empty coffin." --kind story --json
python skills/yt-experiments/tracker.py add original-1 --platform TikTok --profile reaper --posted-at 2026-10-03T18:00:00+01:00 --change original --credits 0
python skills/yt-experiments/tracker.py add opening-1 --platform TikTok --profile reaper --posted-at 2026-10-04T18:00:00+01:00 --change "new opening only" --credits 0 --original-id original-1
python skills/yt-experiments/tracker.py observe original-1 --checkpoint 24h --at 2026-10-04T18:00:00+01:00 --metrics '{"views":100,"shares":3}' --source manual
python skills/yt-experiments/tracker.py compare original-1 opening-1
python -m unittest discover -s tests -v
```

Ranking JSON is a list with `platform`, `profile`, `format`, `views`, `duration_seconds`,
`age_hours`, and optional `shares`, `average_watch_seconds`. Use actual observation ages,
not present-day ages paired with older view counts. Minimum cohort is 4 including the target;
length/age similarity is within a factor of 1.5. Fall back progressively to same-profile
any-format data; mark weak evidence even when a provisional ranking is possible.
Keep platforms separate. Missing or invalid required inputs are reported as skipped.

Retention CSV defaults to headers `position,retention`; configure actual header names via
`--time-column` and `--retention-column`. Positions must increase. Retention is percent, may
exceed 100 due to replays. Non-numeric summaries and invalid rows are reported. Purely numeric
summary rows that look valid cannot be distinguished automatically: inspect skipped rows and
verify the selected columns. Time units are never guessed.

Frame inspection alone needs optional OpenCV 4.x and NumPy (see its requirements.txt). Face and cut results are
approximate measurements, not editorial verdicts. Other new helpers use the standard library.

Tests include a synthetic overlapping auto-caption-style VTT and a public YouTube rolling
auto-caption regression fixture from sabbaken/vtt-to-text, with provenance and MIT licence.
No user caption export was supplied. Review proposed cuts against your own media before editing.
