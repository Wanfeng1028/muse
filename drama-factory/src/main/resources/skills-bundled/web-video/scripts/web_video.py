#!/usr/bin/env python3
"""web-video: one command for the whole pipeline (macOS, Windows, Linux). install.py puts it on PATH.

USAGE
  web-video new feature-demo|bug-report [FILE]   copy an example storyboard (default: storyboard.yaml)
  web-video discover STORYBOARD                  list selectors before each step
  web-video rehearse STORYBOARD                  run all steps without video, fail loudly
  web-video record STORYBOARD --slug NAME        real take -> video-out/NAME/vN/ (prints the run dir)
  web-video tts RUN [--voice ngoclan]            narration (feature-demo), local Vietnamese voice
  web-video edit RUN [--render draft|final]      auto-edit (edl.py); --edit-only FILE --out DIR for old recordings
  web-video verify RUN [--video edited.mp4]      checks + verify/contact.png
  web-video export RUN [--max-mb 9] [--gif]      RUN/edited.mp4 -> RUN/final.mp4 (+ final.gif)
  web-video redact RUN                           mask secrets in trace/HAR/console
  web-video report RUN                           summary.txt or bug-report.md
  web-video calibrate RUN [--set S]              show or set the video/event clock offset
  web-video make STORYBOARD --slug NAME          rehearse, record, tts, edit, verify, export, (redact), report
  web-video profile login|import|check|list|delete ...   signed-in browser profile for --profile NAME
  web-video install-tts | selftest | lint | path | help
Extra flags go to the underlying script (`web-video <command> --help`).
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

S = pathlib.Path(__file__).resolve().parent
ROOT = S.parent
PY = sys.executable
SCRIPT = {"discover": "record.py", "rehearse": "record.py", "record": "record.py", "tts": "tts.py",
          "edit": "edl.py", "verify": "verify.py", "redact": "redact.py", "report": "report.py",
          "calibrate": "calibrate.py", "install-tts": "install_tts.py", "selftest": "selftest.py",
          "profile": "browser_profile.py"}


def call(script: str, *args) -> int:
    return subprocess.run([PY, str(S / script), *map(str, args)]).returncode


def make(args: list[str]) -> int:
    if not args:
        sys.exit("web-video make STORYBOARD --slug NAME")
    sb, rest = args[0], args[1:]
    browser = [x for i, x in enumerate(rest) if x in ("--profile", "--channel")
               or (i and rest[i - 1] in ("--profile", "--channel"))]
    if call("record.py", sb, "--rehearse", *browser):
        return 2
    r = subprocess.run([PY, str(S / "record.py"), sb, *rest], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    run = next((l.split("run dir: ", 1)[1].strip() for l in r.stdout.splitlines() if l.startswith("run dir: ")), "")
    if r.returncode != 0 or not run:
        return r.returncode or 1
    import yaml
    mode = yaml.safe_load(pathlib.Path(sb).read_text(encoding="utf-8"))["mode"]
    if mode == "feature-demo" and "--no-tts" not in rest:
        call("tts.py", run)
    if call("edl.py", run, "--render", "final"):
        return 1
    if call("verify.py", run, "--video", "edited.mp4"):
        print(f"verify reported failures: open {run}/verify/report.md", file=sys.stderr)
    call("export.py", pathlib.Path(run) / "edited.mp4", pathlib.Path(run) / "final.mp4")
    if mode == "bug-report":
        call("redact.py", run)
    call("report.py", run)
    print(f"done: {run}/final.mp4  (look at {run}/verify/contact.png)")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    cmd, args = (argv[0], argv[1:]) if argv else ("help", [])
    if cmd in ("help", "-h", "--help"):
        print(__doc__.split("USAGE", 1)[1].rstrip())
        return 0
    if cmd == "path":
        print(ROOT)
        return 0
    if cmd == "lint":
        return call("lint_skill.py", ROOT)
    if cmd == "new":
        if not args or args[0] not in ("feature-demo", "bug-report"):
            sys.exit("web-video new feature-demo|bug-report [FILE]")
        out = pathlib.Path(args[1] if len(args) > 1 else "storyboard.yaml")
        if out.exists():
            sys.exit(f"{out} exists; not overwriting")
        shutil.copy(ROOT / "assets" / "examples" / f"{args[0]}.yaml", out)
        print(f"wrote {out} (edit url, title, steps; quote actions containing #)")
        return 0
    if cmd == "export":
        if not args:
            sys.exit("web-video export RUN [--max-mb N] [--gif]")
        run, rest = pathlib.Path(args[0]), args[1:]
        if "--gif" in rest:
            rest.remove("--gif")
            rest += ["--gif", str(run / "final.gif")]
        return call("export.py", run / "edited.mp4", run / "final.mp4", *rest)
    if cmd == "make":
        return make(args)
    if cmd in SCRIPT:
        extra = {"discover": ["--discover"], "rehearse": ["--rehearse"]}.get(cmd, [])
        return call(SCRIPT[cmd], *args, *extra)
    print(f"unknown command: {cmd}\n", file=sys.stderr)
    print(__doc__.split("USAGE", 1)[1].rstrip(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
