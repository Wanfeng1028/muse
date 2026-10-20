#!/usr/bin/env python3
"""Install the web-video skill for Claude Code and the `web-video` command (macOS, Windows, Linux).

USAGE
  python install.py              # skill -> ~/.claude/skills/web-video (copy) + `web-video` command
  python install.py --link       # link instead of copy (symlink, or junction on Windows): edits in this repo go live
  python install.py --deps       # also: pip install -r requirements.txt and playwright install chromium
  python install.py --tts        # also: local Vietnamese voice (~200 MB into ~/.cache/web-video)
  python install.py --uninstall  # remove the skill copy/link and the command (keeps ~/.cache/web-video)

Run it with the Python you want the scripts to use; the `web-video` command remembers that interpreter.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import platform
import shutil
import stat
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent
TARGET = pathlib.Path.home() / ".claude" / "skills" / "web-video"
BIN = pathlib.Path.home() / ".local" / "bin"
IGNORE = shutil.ignore_patterns(".git", ".github", "video-out", "__pycache__", "*.pyc", ".venv", "venv",
                                ".DS_Store", "discover.json")
WINDOWS = os.name == "nt"


def is_ours(p: pathlib.Path) -> bool:
    sk = p / "SKILL.md"
    return sk.exists() and "name: web-video" in sk.read_text(encoding="utf-8", errors="replace")[:300]


def remove_target():
    if TARGET.is_symlink() or (WINDOWS and TARGET.exists() and os.path.realpath(TARGET) != str(TARGET)):
        os.unlink(TARGET) if not WINDOWS else os.rmdir(TARGET)        # symlink / junction only, not its content
    elif TARGET.exists():
        if not is_ours(TARGET):
            sys.exit(f"{TARGET} exists and is not the web-video skill; move it away first")
        shutil.rmtree(TARGET)


def install_skill(link: bool):
    if TARGET.resolve() == REPO:
        print(f"skill: this repo already is {TARGET}")
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    remove_target()
    if link:
        if WINDOWS:
            subprocess.run(["cmd", "/c", "mklink", "/J", str(TARGET), str(REPO)], check=True,
                           capture_output=True)
        else:
            os.symlink(REPO, TARGET, target_is_directory=True)
        print(f"skill: linked {TARGET} -> {REPO}")
    else:
        shutil.copytree(REPO, TARGET, ignore=IGNORE)
        print(f"skill: copied to {TARGET}")


def install_cli():
    BIN.mkdir(parents=True, exist_ok=True)
    entry = TARGET / "scripts" / "web_video.py"
    sh = BIN / "web-video"
    for old in (sh, BIN / "web-video.cmd"):
        if old.is_symlink() or old.exists():
            old.unlink()                     # never write through an old symlink
    sh.write_text(f'#!/bin/sh\nexec "{pathlib.Path(sys.executable).as_posix()}" "{entry.as_posix()}" "$@"\n',
                  encoding="utf-8", newline="\n")
    sh.chmod(sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    made = [sh]
    if WINDOWS:
        cmd = BIN / "web-video.cmd"
        cmd.write_text(f'@echo off\r\n"{sys.executable}" "{entry}" %*\r\n', encoding="utf-8")
        made.append(cmd)
    print("command: " + ", ".join(str(m) for m in made))
    on_path = any(pathlib.Path(p).resolve() == BIN.resolve() for p in os.environ.get("PATH", "").split(os.pathsep) if p)
    if not on_path:
        print(f"note: {BIN} is not on PATH. Add it:")
        if WINDOWS:
            print('  PowerShell: [Environment]::SetEnvironmentVariable("Path", '
                  '[Environment]::GetEnvironmentVariable("Path","User") + ";$HOME\\.local\\bin", "User")')
        else:
            print('  echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.zshrc   # or ~/.bashrc')


def install_deps():
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(REPO / "requirements.txt")], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    if not shutil.which("ffmpeg"):
        hint = {"Darwin": "brew install ffmpeg-full (plain `ffmpeg` 8+ lacks drawtext)",
                "Windows": "winget install Gyan.FFmpeg"}.get(
            platform.system(), "sudo apt install ffmpeg")
        print(f"ffmpeg not found: {hint}  (then open a new terminal)")


def uninstall():
    if TARGET.exists() or TARGET.is_symlink():
        if TARGET.resolve() == REPO and not TARGET.is_symlink():
            print(f"skill: {TARGET} is this repo itself; not deleting it")
        else:
            remove_target()
            print(f"removed {TARGET}")
    for f in (BIN / "web-video", BIN / "web-video.cmd"):
        if f.exists():
            f.unlink()
            print(f"removed {f}")
    print("kept ~/.cache/web-video (voice model); delete it by hand if you want the space back")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--link", action="store_true")
    ap.add_argument("--deps", action="store_true")
    ap.add_argument("--tts", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()
    if a.uninstall:
        return uninstall()
    if a.deps:
        install_deps()
    install_skill(a.link)
    install_cli()
    if a.tts:
        subprocess.run([sys.executable, str(TARGET / "scripts" / "install_tts.py")], check=True)
    print("done. In Claude Code ask: \"quay video hướng dẫn tính năng X\" / \"record a bug repro\"; "
          "in a terminal: web-video help")


if __name__ == "__main__":
    main()
