#!/usr/bin/env python3
"""Persistent browser profiles for takes that need a signed-in user.

USAGE
  browser_profile.py login NAME URL [--channel chrome]        # open a real window; sign in; close it to save
  browser_profile.py import NAME --from-chrome "Profile 1"    # copy cookies + site storage from a Chrome profile
  browser_profile.py check NAME URL [--expect-status-url URL] # headless: open URL with the profile, print title/status
  browser_profile.py list                                     # profiles and their Chrome sources
  browser_profile.py chrome-profiles                          # Chrome profiles on this machine (dir | name | account)
  browser_profile.py delete NAME

A profile is a Chromium user-data dir under ~/.cache/web-video/profiles/NAME (WEB_VIDEO_PROFILE_ROOT
overrides). record.py uses it with `profile: NAME` in the storyboard or `--profile NAME`.
Every profile made here carries a `web-video-profile.json` marker; `delete` and `import --replace`
only remove folders inside the profile root or folders with that marker. `login` also snapshots cookies
to web-video-state.json every 2 s, because Chromium drops session cookies when the window closes.

Why a copy and not the live Chrome profile: Chrome locks a profile while it runs, and Chrome 136+
refuses automation on its default user-data dir. `import` copies only cookies, site storage and the
encryption state into a separate dir. On macOS the copy decrypts with the same Keychain key because
the take runs the installed Chrome (channel chrome) without Playwright's mock keychain.
Treat a profile like a password: it holds live sessions. Delete it when the video is done.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import sys

CHANNELS = ("chrome", "chrome-beta", "msedge", "chromium")
# Files and folders that carry sign-in state. Caches, history, extensions, saved passwords ("Login Data")
# and autofill/payment data ("Web Data") stay behind: a take must never autofill personal data on camera.
IMPORT_ITEMS = ("Cookies", "Cookies-journal", "Network", "Local Storage", "Session Storage", "IndexedDB",
                "Service Worker", "Preferences", "Secure Preferences")
MARKER = "web-video-profile.json"
LEGACY_MARKER = "web-video-source.json"
MOCK_KEYCHAIN_FLAGS = ["--use-mock-keychain", "--password-store=basic"]
STATE = "web-video-state.json"   # storage_state snapshot: Chromium does not persist session cookies on close


def profile_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("WEB_VIDEO_PROFILE_ROOT") or pathlib.Path.home() / ".cache/web-video/profiles")


def resolve(profile: str) -> pathlib.Path:
    """A bare name maps into the profile root; anything with a separator is a path."""
    if os.sep in profile or "/" in profile or profile.startswith("~"):
        return pathlib.Path(profile).expanduser().resolve()
    if profile in (".", "..") or not profile.replace("-", "").replace("_", "").isalnum():
        raise SystemExit(f"error: profile name must be letters, digits, - or _: {profile!r}")
    return profile_root() / profile


def read_marker(path: pathlib.Path) -> dict:
    for name in (MARKER, LEGACY_MARKER):
        f = path / name
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                return {}
    return {}


def init_profile(path: pathlib.Path, source: str, keychain: str = "real", channel: str | None = None) -> pathlib.Path:
    """Create (or mark) a profile folder. keychain: 'real' for Chrome-imported or user sign-in profiles,
    'mock' for throwaway test profiles that must not touch the OS keychain."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    meta = {"source": source, "keychain": keychain, "created": dt.datetime.now().isoformat(timespec="seconds")}
    if channel:
        meta["channel"] = channel
    (path / MARKER).write_text(json.dumps(meta), encoding="utf-8")
    return path


def save_state(ctx, path: pathlib.Path) -> bool:
    """Snapshot cookies (session cookies included) into the profile. Same sensitivity as the profile itself."""
    try:
        state = ctx.storage_state()
    except Exception:
        return False
    tmp = path / (STATE + ".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path / STATE)
    return True


def restore_state(ctx, path: pathlib.Path) -> int:
    """Re-add saved cookies that the browser dropped (session cookies). Returns how many were added."""
    f = path / STATE
    if not f.exists():
        return 0
    try:
        saved = json.loads(f.read_text(encoding="utf-8")).get("cookies", [])
    except ValueError:
        return 0
    have = {(c["name"], c["domain"], c["path"]) for c in ctx.cookies()}
    missing = [c for c in saved if (c["name"], c["domain"], c["path"]) not in have]
    if missing:
        ctx.add_cookies(missing)
    return len(missing)


def safe_to_remove(path: pathlib.Path) -> bool:
    """Only folders this tool manages: inside the profile root, or carrying our marker."""
    path = path.resolve()
    root = profile_root().resolve()
    if path == root or path == pathlib.Path.home().resolve() or len(path.parts) <= 2:
        return False
    return root in path.parents or (path / MARKER).exists() or (path / LEGACY_MARKER).exists()


def remove_profile(path: pathlib.Path):
    if not safe_to_remove(path):
        raise SystemExit(f"error: refusing to delete {path}: not a web-video profile "
                         f"(outside {profile_root()} and no {MARKER})")
    shutil.rmtree(path)


def chrome_user_data_dir() -> pathlib.Path:
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library/Application Support/Google/Chrome"
    if os.name == "nt":
        return pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data"
    return pathlib.Path.home() / ".config/google-chrome"


def chrome_profiles() -> list[tuple[str, str, str]]:
    state = chrome_user_data_dir() / "Local State"
    try:
        cache = json.loads(state.read_text(encoding="utf-8")).get("profile", {}).get("info_cache", {})
    except (OSError, ValueError):
        return []
    return sorted((d, v.get("name", ""), v.get("user_name", "")) for d, v in cache.items())


def launch_options(channel: str | None, *, interactive: bool, keychain: str = "real") -> dict:
    """Arguments for launch_persistent_context. A 'real' keychain profile drops Playwright's mock keychain
    so cookies copied from Chrome decrypt with the user's key; a 'mock' one keeps the defaults."""
    ignore = list(MOCK_KEYCHAIN_FLAGS) if keychain == "real" else []
    args = []
    if interactive:
        # Google sign-in refuses windows that announce automation.
        ignore.append("--enable-automation")
        args.append("--disable-blink-features=AutomationControlled")
    opts = {"ignore_default_args": ignore, "args": args}
    if channel and channel != "chromium":
        opts["channel"] = channel
    return opts


def default_channel() -> str | None:
    """Prefer installed Chrome: its Keychain/DPAPI key matches imported cookies."""
    candidates = {
        "darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        "win32": [os.path.join(os.environ.get(v, ""), "Google/Chrome/Application/chrome.exe")
                  for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")],
    }.get(sys.platform, ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"])
    return "chrome" if any(os.path.exists(p) for p in candidates) else None


def open_context(pw, profile: str, channel: str | None, *, headless: bool, interactive: bool = False, **ctx_kw):
    """Launch a persistent context for record.py and the commands below. Returns the context."""
    path = resolve(profile)
    if not path.exists():
        raise SystemExit(f"error: profile {profile!r} not found at {path}; run browser_profile.py login or import first")
    marker = read_marker(path)
    channel = channel or marker.get("channel") or default_channel()
    opts = launch_options(channel, interactive=interactive, keychain=marker.get("keychain", "real"))
    ctx = pw.chromium.launch_persistent_context(str(path), headless=headless, **opts, **ctx_kw)
    restore_state(ctx, path)
    return ctx


def cmd_login(a) -> int:
    from playwright.sync_api import sync_playwright
    path = resolve(a.name)
    if not read_marker(path):
        init_profile(path, "login")
    with sync_playwright() as pw:
        ctx = open_context(pw, a.name, a.channel, headless=False, interactive=True, no_viewport=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(a.url)
        print(f"Sign in in the browser window, then close the window to save profile {a.name!r}.", flush=True)
        closed = []
        ctx.on("close", lambda _: closed.append(True))
        while not closed:                        # snapshot every 2 s: after the window closes it is too late
            save_state(ctx, path)
            try:
                page.wait_for_timeout(2000) if not page.is_closed() else ctx.wait_for_event("close", timeout=2000)
            except Exception:
                if not ctx.pages:
                    break
            if not ctx.pages:
                break
            page = ctx.pages[0]
    print(f"saved profile: {path}")
    return 0


def cmd_import(a) -> int:
    source_root = chrome_user_data_dir()
    if a.from_chrome in ("", ".", "..") or any(c in a.from_chrome for c in "/\\"):
        raise SystemExit(f"error: --from-chrome takes a profile folder name such as 'Default' or 'Profile 1'")
    source = source_root / a.from_chrome
    if not (source / "Preferences").exists():
        known = ", ".join(f"{d} ({u or n})" for d, n, u in chrome_profiles()) or "none found"
        raise SystemExit(f"error: Chrome profile {a.from_chrome!r} not found in {source_root}. Known: {known}")
    target = resolve(a.name)
    if target.exists() and any(target.iterdir()) and not a.replace:
        raise SystemExit(f"error: {target} exists; pass --replace to overwrite it")
    if target.exists():
        remove_profile(target)
    init_profile(target, f"chrome:{a.from_chrome}")
    (target / "Default").mkdir(parents=True)
    # Local State holds the cookie encryption key wrapper (Windows) and profile metadata.
    shutil.copy2(source_root / "Local State", target / "Local State")
    copied = []
    for item in IMPORT_ITEMS:
        src = source / item
        if src.is_dir():
            shutil.copytree(src, target / "Default" / item, ignore=shutil.ignore_patterns("LOCK", "*.lock"))
            copied.append(item)
        elif src.is_file():
            shutil.copy2(src, target / "Default" / item)
            copied.append(item)
    print(f"imported {len(copied)} item(s) from Chrome {a.from_chrome!r} into {target}")
    print("Check it with: browser_profile.py check NAME URL. If the site shows you signed out, use browser_profile.py login.")
    return 0


def cmd_check(a) -> int:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = open_context(pw, a.name, a.channel, headless=not a.headed)
        page = ctx.new_page()
        response = page.goto(a.url)
        print(f"{a.url}: HTTP {response.status if response else '?'}  title={page.title()!r}")
        if a.expect_status_url:
            status = page.evaluate("u => fetch(u, {credentials: 'include'}).then(r => r.status)", a.expect_status_url)
            print(f"{a.expect_status_url}: HTTP {status}")
            ctx.close()
            return 0 if status == 200 else 1
        ctx.close()
    return 0


def cmd_list(_a) -> int:
    root = profile_root()
    for p in sorted(x for x in root.iterdir() if x.is_dir()) if root.exists() else []:
        m = read_marker(p)
        source = m.get("source") or (f"chrome:{m['chrome_profile']}" if m.get("chrome_profile") else "?")
        print(f"{p.name:24} {source:20} {m.get('keychain', 'real'):5} {p}")
    return 0


def cmd_chrome_profiles(_a) -> int:
    for d, name, user in chrome_profiles():
        print(f"{d:12} | {name:20} | {user}")
    return 0


def cmd_delete(a) -> int:
    path = resolve(a.name)
    if not path.exists():
        print(f"no profile at {path}")
        return 0
    remove_profile(path)
    print(f"deleted {path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("login")
    p.add_argument("name")
    p.add_argument("url")
    p.add_argument("--channel", choices=CHANNELS)
    p = sub.add_parser("import")
    p.add_argument("name")
    p.add_argument("--from-chrome", required=True, metavar="PROFILE_DIR")
    p.add_argument("--replace", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("name")
    p.add_argument("url")
    p.add_argument("--expect-status-url")
    p.add_argument("--channel", choices=CHANNELS)
    p.add_argument("--headed", action="store_true")
    sub.add_parser("list")
    sub.add_parser("chrome-profiles")
    p = sub.add_parser("delete")
    p.add_argument("name")
    a = ap.parse_args()
    return {"login": cmd_login, "import": cmd_import, "check": cmd_check, "list": cmd_list,
            "chrome-profiles": cmd_chrome_profiles, "delete": cmd_delete}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
