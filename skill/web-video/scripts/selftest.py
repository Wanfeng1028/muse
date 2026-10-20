#!/usr/bin/env python3
"""End-to-end self-test on the bundled fixture app (macOS, Windows, Linux).

USAGE
  selftest.py [WORKDIR] [--no-tts] [--quick]
Runs unit tests and lint, then for both modes: rehearse, record, (narration), edit final, verify,
export, redact, report; then a signed-in take through a persistent browser profile (browser_profile.py).
--quick runs only the feature-demo pass. Default WORKDIR: a new temp folder.
Narration runs only when the Piper voice is installed (install_tts.py) or on macOS (`say`).
Exit code 1 on the first failing stage.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable


def run(args, cwd=None, capture=False):
    r = subprocess.run([str(a) for a in args], cwd=cwd, text=True, encoding="utf-8", errors="replace",
                       capture_output=capture)
    if r.returncode != 0:
        if capture:
            print(r.stdout[-3000:], r.stderr[-3000:], sep="\n", file=sys.stderr)
        sys.exit(f"selftest FAILED at: {' '.join(str(a) for a in args[:3])} …")
    return r


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def profile_pass(work: pathlib.Path, port: int):
    """Sign in once into a throwaway profile, then record without a login step."""
    print("== profile (signed-in take)", flush=True)
    os.environ["WEB_VIDEO_PROFILE_ROOT"] = str(work / "profiles")
    sys.path.insert(0, str(HERE))
    import yaml
    import browser_profile as bp
    from playwright.sync_api import sync_playwright
    base = f"http://localhost:{port}"
    bp.init_profile(bp.resolve("selftest"), "selftest", keychain="mock", channel="chromium")
    with sync_playwright() as pw:
        ctx = bp.open_context(pw, "selftest", None, headless=True)
        page = ctx.new_page()
        page.goto(base + "/login")
        page.fill("#email", "demo@example.com")
        page.fill("#password", "demo-pass")
        page.click('[data-testid="sign-in"]')
        page.wait_for_url(base + "/")
        bp.save_state(ctx, bp.resolve("selftest"))   # what `login` does while the window is open
        ctx.close()
    run([PY, HERE / "browser_profile.py", "check", "selftest", base + "/", "--expect-status-url", base + "/api/me"],
        capture=True)
    sb = yaml.safe_load((ROOT / "assets" / "examples" / "bug-report.yaml").read_text(encoding="utf-8"))
    sb["url"] = base
    sb["steps"] = [{"caption": "Mở danh sách", "do": "goto /"}] + [s for s in sb["steps"] if not s.get("hidden")]
    sbf = work / "profile-take.yaml"
    sbf.write_text(yaml.safe_dump(sb, allow_unicode=True, sort_keys=False), encoding="utf-8")
    run([PY, HERE / "record.py", sbf, "--rehearse", "--profile", "selftest"], cwd=work, capture=True)
    out = run([PY, HERE / "record.py", sbf, "--slug", "profile-take", "--root", work / "video-out",
               "--profile", "selftest"], cwd=work, capture=True).stdout
    rdir = pathlib.Path(next(l.split("run dir: ", 1)[1].strip() for l in out.splitlines() if l.startswith("run dir: ")))
    run([PY, HERE / "edl.py", rdir, "--render", "draft"], capture=True)
    v = subprocess.run([PY, HERE / "verify.py", rdir], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if v.returncode != 0:
        sys.exit(f"verify failed for the profile take: see {rdir / 'verify' / 'report.md'}")
    run([PY, HERE / "browser_profile.py", "delete", "selftest"], capture=True)
    print("profile take OK", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", nargs="?", type=pathlib.Path)
    ap.add_argument("--no-tts", action="store_true")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    work = (a.workdir or pathlib.Path(tempfile.mkdtemp(prefix="web-video-selftest-"))).resolve()
    work.mkdir(parents=True, exist_ok=True)
    os.environ["PYTHONIOENCODING"] = "utf-8"

    print("== unit tests", flush=True)
    run([PY, "-m", "unittest", "discover", "-s", ROOT / "tests", "-q"])
    print("== lint", flush=True)
    run([PY, HERE / "lint_skill.py", ROOT])

    sys.path.insert(0, str(HERE))
    from install_tts import installed as piper_ok
    tts = not a.no_tts and (piper_ok() or (platform.system() == "Darwin" and shutil.which("say")))

    port = free_port()
    log = open(work / "fixture-server.log", "w", encoding="utf-8")
    server = subprocess.Popen([PY, ROOT / "assets" / "fixture" / "server.py", str(port)], stdout=log, stderr=log)
    try:
        deadline = time.time() + 60                      # cold CI runners can take a while to start Python
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), 0.5).close()
                break
            except OSError:
                if server.poll() is not None or time.time() > deadline:
                    log.flush()
                    sys.exit("fixture server did not start:\n" + (work / "fixture-server.log").read_text(encoding="utf-8"))
                time.sleep(0.2)
        for mode in ("feature-demo",) if a.quick else ("feature-demo", "bug-report"):
            print(f"== {mode}", flush=True)
            sb = work / f"{mode}.yaml"
            text = (ROOT / "assets" / "examples" / f"{mode}.yaml").read_text(encoding="utf-8")
            text = text.replace("http://localhost:8765", f"http://localhost:{port}")
            if mode == "feature-demo":      # a video of project X uses X's design: draft the theme from the app
                run([PY, HERE / "theme.py", "init", "--repo", ROOT / "assets" / "fixture",
                     "--out", work / "theme.yaml", "--force"], capture=True)
                text += "\ntheme: theme.yaml\ntheme_label: Selftest\n"
            sb.write_text(text, encoding="utf-8")
            run([PY, HERE / "record.py", sb, "--rehearse"], cwd=work, capture=True)
            out = run([PY, HERE / "record.py", sb, "--slug", mode, "--root", work / "video-out"],
                      cwd=work, capture=True).stdout
            rd = next((l.split("run dir: ", 1)[1].strip() for l in out.splitlines() if l.startswith("run dir: ")), "")
            rdir = pathlib.Path(rd)
            if not rdir.is_dir():
                sys.exit("record did not report a run dir")
            if mode == "feature-demo" and tts:
                run([PY, HERE / "tts.py", rdir], capture=True)
            variants = [["--no-theme"], []] if mode == "feature-demo" else [[]]
            for extra in variants:          # feature-demo: plain captions first, then the project theme
                run([PY, HERE / "edl.py", rdir, "--render", "final", *extra])
                v = subprocess.run([PY, HERE / "verify.py", rdir, "--video", "edited.mp4"], capture_output=True,
                                   text=True, encoding="utf-8", errors="replace")
                print("\n".join(l for l in v.stdout.splitlines() if l.startswith(("FAIL", "WARN", "contact"))))
                if v.returncode != 0:
                    sys.exit(f"verify failed ({' '.join(extra) or 'themed'}): see {rdir / 'verify' / 'report.md'}")
            run([PY, HERE / "export.py", rdir / "edited.mp4", rdir / "final.mp4"])
            if mode == "bug-report":
                run([PY, HERE / "redact.py", rdir], capture=True)
            run([PY, HERE / "report.py", rdir], capture=True)
        if not a.quick:
            profile_pass(work, port)
    finally:
        server.terminate()
        log.close()
    print(f"selftest OK ({'with' if tts else 'without'} narration). Videos: {work / 'video-out'}")


if __name__ == "__main__":
    main()
