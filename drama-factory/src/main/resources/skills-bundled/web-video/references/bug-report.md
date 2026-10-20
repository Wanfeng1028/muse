# Bug report mode

Goal: a developer understands the bug in under 60 seconds and can open the trace to debug it.

## Reproduction discipline

1. Write the storyboard from the reporter's steps exactly; note their version/build.
2. `record.py --rehearse` first. It prints whether the `bug: true` step was reached and which errors fired.
3. Once it reproduces, **stop changing variables**: record the take with the same storyboard.
4. If it does not reproduce, try at most **2** justified variations (other data, viewport, user role, build), each written down. Then stop and report `not reproduced` with what you tried.
5. A step that cannot run (login broken, environment down, missing data) means `blocked`, not `not reproduced`.

## Status vocabulary (you set it; report.py only suggests)

| Status | Meaning |
|---|---|
| `confirmed` | reproduced on the tested version; the video shows the actual behaviour |
| `partially confirmed` | some of the reported behaviour reproduced, or only under extra conditions (say which) |
| `not reproduced` | steps ran, the failure did not appear (list variations tried) |
| `blocked` | could not reach the step (say why) |

Always state reporter version vs tested version; a mismatch is the first thing a developer asks about.

## bug-report.md template (report.py fills it)

```markdown
# <title>

**Status:** <confirmed | partially confirmed | not reproduced | blocked>
**Environment:** <browser, viewport, OS, env>
**Reporter version:** <build> · **Tested version:** <build>
**URL:** <url> · recorded <time> with Playwright <version>

## Steps to reproduce
1. ...

## Expected
...

## Actual
...

## Evidence
- Video: final.mp4, bug at **00:07.03** (red box, frozen 2 s)
- Failing requests: `500 POST /api/invoices → {"error":"..."}`
- Console errors: ...

## Attachments
- final.mp4, trace.redacted.zip, net.redacted.har, console.redacted.json
Open the trace: `npx playwright show-trace trace.redacted.zip`
```

Keep "Actual" factual (what the screen and network show), not a guess at the cause. If you looked at the code and have a hypothesis, add a separate "Notes" section marked as a hypothesis.

## Evidence files

- `trace.zip`: DOM snapshots before/after each action, console, network, filmstrip. The single most useful file for a developer. `trace.playwright.dev` opens it locally in the browser.
- `net.har`: `jq -r '.log.entries[]|select(.response.status>=400 or .response.status==0)|[.response.status,.request.method,.request.url]|@tsv' net.har`
- `console.json`: every message with its time on the event clock.
- Run `redact.py` first and attach only the `*.redacted.*` files. Redaction covers headers, cookies, secret fields, typed secrets; it does not blur pixels, so look at the contact sheet for tokens or personal data on screen.

## Posting

Only after an explicit yes from the user, and only where they said:
```bash
gh --version        # --attach needs gh >= 2.99 and github.com (not GHES)
gh issue comment <n> --body-file RUN/bug-report.md --attach RUN/final.mp4
```
Older gh or another tracker: give the user the folder path and the text; they drag the files in. Size limits: `references/export.md`.
