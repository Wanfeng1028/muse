#!/usr/bin/env python3
"""Write the hand-off text for a run, and log the run in the per-video project.md.

USAGE
  report.py RUN_DIR [--video final.mp4]
feature-demo -> RUN_DIR/summary.txt  (title, duration, numbered steps, file, suggested client message)
bug-report   -> RUN_DIR/bug-report.md (status placeholder, env, versions, steps, expected/actual,
                console errors, failing requests, bug timestamp, attachments)
Both: appends one line to ../project.md (the folder for this video slug).
The bug-report status is never guessed: the script writes a suggestion; you set the final value.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_json, load_storyboard, probe_summary, run_paths  # noqa: E402

STATUSES = ("confirmed", "partially confirmed", "not reproduced", "blocked")


def mmss(t: float) -> str:
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


def failing_requests(har: pathlib.Path) -> list[str]:
    if not har.exists():
        return []
    out = []
    for e in json.loads(har.read_text(encoding="utf-8")).get("log", {}).get("entries", []):
        st = e.get("response", {}).get("status", 0)
        if st >= 400 or st == 0:
            body = (e.get("response", {}).get("content", {}).get("text") or "")[:200].replace("\n", " ")
            out.append(f"{st} {e['request']['method']} {e['request']['url'].split('?')[0]}" + (f" → {body}" if body else ""))
    return out


def client_message(sb: dict, steps: list[str], dur: float | None) -> str:
    title = sb.get("title", "the new feature")
    d = f"{dur:.0f}" if dur else "?"
    if str(sb.get("lang", "en")).startswith("vi"):
        return (f"Gửi anh/chị video ngắn ({d} giây) hướng dẫn \"{title}\", gồm {len(steps)} bước: "
                + "; ".join(steps) + ". Anh/chị cần chỉnh gì cứ phản hồi nhé.")
    return (f"Here is a short video ({d} s) showing \"{title}\" in {len(steps)} steps: "
            + "; ".join(steps) + ". Reply with any question or change.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=pathlib.Path)
    ap.add_argument("--video", default=None)
    a = ap.parse_args()
    p = run_paths(a.run)
    sb = load_storyboard(p["storyboard"])
    plan = load_json(p["edl"]) if p["edl"].exists() else {}
    meta = load_json(p["meta"]) if p["meta"].exists() else {}
    video = a.run / a.video if a.video else next((p[k] for k in ("final", "edited", "draft") if p[k].exists()), None)
    dur = probe_summary(video)["duration"] if video else None
    intro = plan.get("intro", 0.0)
    steps = [c["text"] for c in plan.get("captions", [])] or [s["caption"] for s in sb["steps"] if not s.get("hidden")]

    if sb["mode"] == "feature-demo":
        lines = [sb.get("title", "Feature walkthrough"), "",
                 f"Video: {video.name if video else '(not rendered)'}" + (f" · {dur:.0f} s" if dur else ""), "",
                 "Steps:"] + [f"  {i}. {s}" for i, s in enumerate(steps, 1)] + [
                 "", "Suggested message to the client:", "  " + client_message(sb, steps, dur)]
        out = a.run / "summary.txt"
        out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    else:
        bug = sb.get("bug", {})
        ev = load_json(p["events"]) if p["events"].exists() else {"events": []}
        errors = [e for e in ev["events"] if e["kind"] == "error"]
        bug_ev = next((e for e in ev["events"] if e["kind"] == "bug"), None)
        if meta.get("status") == "aborted":
            suggest = f"blocked (take aborted at step {meta.get('failed_step')})"
        elif bug_ev and errors:
            suggest = f"confirmed? bug step reached with {len(errors)} error event(s); check the video matches ACTUAL"
        elif bug_ev:
            suggest = "confirmed or not reproduced: bug step reached, no errors logged; decide from the video"
        else:
            suggest = "not reproduced or blocked: bug step not reached"
        cons = [f"- `{e.get('source')}` {e.get('text') or ''}".rstrip() for e in errors if e["source"] != "http"]
        reqs = failing_requests(p["har"])
        bug_t = (intro + plan["bug"]["t_body"]) if plan.get("bug") else None
        att = [x for x in ("final.mp4", "trace.redacted.zip", "net.redacted.har", "console.redacted.json")
               if (a.run / x).exists()]
        missing_redacted = not (a.run / "trace.redacted.zip").exists()
        md = [f"# {sb.get('title', 'Bug')}", "",
              f"**Status:** TODO: one of {', '.join(STATUSES)}  ",
              f"_suggested: {suggest}_", "",
              f"**Environment:** {bug.get('env', 'TODO')}  ",
              f"**Reporter version:** {bug.get('reporter_version', 'TODO')} · "
              f"**Tested version:** {bug.get('tested_version', 'TODO')}  ",
              f"**URL:** {sb['url']} · recorded {meta.get('started_at', '?')} with Playwright {meta.get('playwright', '?')}",
              "", "## Steps to reproduce", ""] + [f"{i}. {s}" for i, s in enumerate(steps, 1)] + [
              "", "## Expected", "", bug.get("expected", "TODO"), "",
              "## Actual", "", bug.get("actual", "TODO"), "",
              "## Evidence", "",
              f"- Video: `{video.name if video else '-'}`" + (f", bug at **{mmss(bug_t)}** (red box, frozen 2 s)"
                                                              if bug_t is not None else ""),
              "- Failing requests:" if reqs else "- Failing requests: none recorded"] + [
              f"  - `{r}`" for r in reqs[:10]] + [
              "- Console errors:" if cons else "- Console errors: none recorded"] + [f"  {c}" for c in cons[:10]] + [
              "", "## Attachments", ""] + [f"- {x}" for x in att] + [
              "", "Open the trace: `npx playwright show-trace trace.redacted.zip`"]
        if missing_redacted:
            md += ["", "> Run redact.py before attaching trace/HAR/console files."]
        out = a.run / "bug-report.md"
        out.write_text("\n".join(md) + "\n", encoding="utf-8")

    proj = a.run.parent / "project.md"
    if not proj.exists():
        proj.write_text(f"# {sb.get('title', a.run.parent.name)}\n\nmode: {sb['mode']} · url: {sb['url']}\n\n"
                        "## Runs\n\n", encoding="utf-8")
    warn = "; ".join(plan.get("warnings", [])) or "none"
    with proj.open("a", encoding="utf-8") as f:
        f.write(f"- {dt.date.today()} {a.run.name}: {dur and round(dur, 1)} s, offset {plan.get('offset')} s, "
                f"status {meta.get('status')}, warnings: {warn}\n")
    print(f"wrote {out}\nappended {proj}")


if __name__ == "__main__":
    main()
