# Storyboard

`record.py`, `edl.py`, `tts.py` and `report.py` all read the same `storyboard.yaml`. It is validated on load; errors list every problem at once.

## Schema

```yaml
mode: feature-demo | bug-report     # required
url: http://localhost:3000          # required; relative `goto` paths join onto it
viewport: [1280, 720]               # even numbers; the video is recorded at this CSS-pixel size
lang: vi                            # caption language; picks the TTS voice (vi → Piper Ngọc Lan, else macOS say)
title: "Tạo hoá đơn mới"            # intro card (feature-demo) / panel title (bug-report)
subtitle: "Bản 2.3"                 # optional, intro card second line
outro: "Xong! Hoá đơn đã được lưu." # optional outro card (feature-demo)
storage_state: auth.json            # optional Playwright storage state, relative to the storyboard file
theme: theme.yaml                   # feature-demo: the project's theme (theme.py init --repo …); `clean` only as a fallback
theme_label: "Release 2.3"          # optional mono label on every themed frame
profile: demo                       # optional persistent profile (name or user-data dir); not with storage_state
channel: chrome                     # optional browser build for the profile: chrome | chrome-beta | msedge | chromium
bug:                                # bug-report only
  expected: "..."                   # required
  actual: "..."                     # required
  env: "Chrome 1280x720, staging"
  reporter_version: "build a1b2c3"
  tested_version: "build d4e5f6"
steps:
  - caption: "Bấm New invoice"      # required for visible steps, ≤ 12 words
    do: 'click [data-testid="new-invoice"]'   # one action or a list
    say: "Tạo hoá đơn chỉ với một nút."       # optional narration text (default: caption)
    wait: 700                       # ms to settle after the actions (default 700, hidden 0)
    hidden: false                   # true = executed but cut from the video (login, cookie banner, seeding)
    bug: false                      # bug-report: true on the step where the failure shows
    bug_target: "#save"             # optional element for the red box (default: last clicked element)
```

Limits enforced: max 8 visible steps (split longer flows into two videos), captions ≤ 12 words, bug-report needs `bug.expected`, `bug.actual` and one `bug: true` step.

## Actions

| Action | Example | What it does |
|---|---|---|
| `goto PATH\|URL` | `goto /invoices` | navigate, wait for `load` |
| `click SEL` | `click text=New invoice` | glide cursor, verify visible/in viewport/not covered, ripple, click |
| `check SEL` | `check #agree` | same as click |
| `hover SEL` | `hover nav >> text=Reports` | glide only |
| `type SEL \| TEXT` | `type #customer \| Globex` | click the field, type visibly (55 ms/char) |
| `fill SEL \| TEXT` | `fill #password \| secret` | instant fill (use in hidden steps and for secrets) |
| `press KEY` | `press Enter` | keyboard |
| `select SEL \| VALUE` | `select #due \| 14` | by value, then by label; the native list is not visible on video |
| `scroll PX\|SEL` | `scroll 600` / `scroll #pricing` | smooth wheel scroll |
| `wait MS` | `wait 1200` | pause (keep for animations you want seen) |
| `expect SEL` | `expect [data-testid=toast]` | wait until visible; marks a result moment (kept at 1x) |
| `expect_text SEL \| TEXT` | `expect_text .status \| Paid` | wait for text |
| `wait_url GLOB` | `wait_url **/dashboard` | wait for navigation |

Selectors are Playwright selectors (`css`, `text=`, `role=button[name="Save"]`, `[data-testid=x]`, `>>` chains). They must match exactly one element. Take them from `record.py --discover`; prefer `data-testid`, `id`, `name`, then visible text.

**YAML trap:** `#` after a space starts a comment. Quote every action containing `#`: `- 'fill #email | a@b.c'`. `record.py` detects the truncated line and says so.

Secrets: values typed into password inputs or selectors named like password/token/otp are masked in `events.json`, and `redact.py` removes them from trace/HAR. Better still, log in once and pass `storage_state`, or use a `profile` for SSO sites, so no password is typed during the take.

## Writing captions and narration

- feature-demo: say the benefit, not the mechanics. "Hoá đơn được lưu chỉ với một nút", not "Người dùng bấm Save". Step 1 is the hook, the last step shows the result.
- One idea per step; the caption is numbered automatically (`1. ...`).
- Narration text (`say:`) is spoken by a Vietnamese-only voice: write numbers freely (they are spelled out), but prefer Vietnamese UI labels over English words, or spell English phonetically ("đát-boóc").
- Narration about 3-4 words/s (`tts.py` prints the rate); a caption stays at least 0.3 s per word and 1.2 s minimum; `edl.py` adds holds when needed.
- bug-report: captions are the repro steps, literal and short ("Nhập số tiền 1500", "Bấm Save"). They appear in the side panel, not over the app.
- Show the final state long enough to read: end with an `expect` on the result and `wait: 1500`.

## Hidden steps

Use `hidden: true` for login, closing cookie banners, seeding data, resetting state. They run in every take and rehearsal but are cut from the video. Keep them at the start when possible; a hidden step in the middle becomes a hard cut.
