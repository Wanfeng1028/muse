"""Check which video tools are available before starting a promo video.

Usage: python preflight.py [--need remotion,blender,ffmpeg,python] [--project film/]
Prints each tool with its version or MISSING. Exits 1 only when a tool group listed in --need is missing.
ffmpeg/ffprobe are found the same way the other scripts find them (env var, PATH, Remotion's bundled copy).
"""
import argparse, importlib, os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _media  # noqa: E402


def version(cmd, args):
    try:
        out = subprocess.run([cmd] + args, capture_output=True, timeout=30)
        raw = (out.stdout or out.stderr).decode("utf-8", errors="replace")
        lines = raw.strip().splitlines()
        return lines[0][:80] if lines else "found"
    except Exception as e:  # noqa: BLE001
        return f"found, version check failed: {e}"


def find_ff(name):
    try:
        return _media.tool(name)
    except SystemExit:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--need", default="", help="comma separated groups: remotion,blender,ffmpeg,python")
    ap.add_argument("--project", default=None)
    a = ap.parse_args()
    _media.set_project(a.project)
    need = {x.strip() for x in a.need.split(",") if x.strip()}

    rows = []
    node = shutil.which("node")
    rows.append(("node", "remotion", version(node, ["--version"]) if node else None))
    rows.append(("npx", "remotion", "found" if shutil.which("npx") else None))
    for n in ("ffmpeg", "ffprobe"):
        p = find_ff(n)
        rows.append((n, "ffmpeg", (version(p, ["-version"]) + f"  ({p})") if p else None))
    b = os.environ.get("BLENDER") if os.environ.get("BLENDER") and os.path.exists(os.environ["BLENDER"]) else shutil.which("blender")
    rows.append(("blender", "blender", version(b, ["--version"]) if b else None))
    for mod, label in (("numpy", "numpy"), ("PIL", "Pillow")):
        try:
            m = importlib.import_module(mod)
            rows.append((label, "python", getattr(m, "__version__", "found")))
        except ImportError:
            rows.append((label, "python", None))
    chrome = [p for p in ("C:/Program Files/Google/Chrome/Application/chrome.exe",
                          "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome") if os.path.exists(p)]
    rows.append(("chrome", "remotion", chrome[0] if chrome else "not found (Remotion downloads its own browser)"))

    missing = []
    for name, group, ver in rows:
        print(f"{name:10} [{group}] {ver if ver else 'MISSING'}")
        if ver is None and group in need:
            missing.append(name)
    if rows[0][2] is None or rows[1][2] is None:
        print("note: Remotion needs Node.js and npx. Remotion itself is installed per project.")
    if rows[2][2] is None:
        print("note: no runnable ffmpeg. Install it, or pass --project pointing at a Remotion project to use its copy.")
    if rows[4][2] is None:
        print("note: Blender is optional. Skip Blender shots, or use a portable Blender and set BLENDER.")
    if missing:
        print("FAIL: missing required tools: " + ", ".join(missing))
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()

