#!/usr/bin/env python3
"""Check everything the skill needs and print how to fix what is missing.

Usage: python3 revisar_entorno.py
"""
import platform
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comun import openai_key

SYSTEM = platform.system()  # Darwin / Windows / Linux
ok = True


def report(name, good, fix=""):
    global ok
    print(f"{'OK ' if good else 'FALTA'}  {name}")
    if not good:
        ok = False
        if fix:
            print(f"       → {fix}")


report("Python 3.9 o superior", sys.version_info >= (3, 9),
       "instala Python desde https://www.python.org/downloads/")

ffmpeg_fix = {
    "Darwin": "brew install ffmpeg   (si no tienes Homebrew: https://brew.sh)",
    "Windows": "winget install --id Gyan.FFmpeg  y luego cierra y abre la terminal",
    "Linux": "sudo apt install ffmpeg",
}.get(SYSTEM, "instala ffmpeg desde https://ffmpeg.org/download.html")
report("ffmpeg y ffprobe", bool(shutil.which("ffmpeg") and shutil.which("ffprobe")), ffmpeg_fix)

pip = "py -m pip" if SYSTEM == "Windows" else "python3 -m pip"
try:
    import requests  # noqa: F401
    report("librería requests", True)
except ImportError:
    report("librería requests", False, f"{pip} install requests")

try:
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
        report("Playwright + Chromium", True)
    except Exception:  # noqa: BLE001 — any launch failure means the same fix
        report("Playwright + Chromium", False, "python3 -m playwright install chromium")
except ImportError:
    report("Playwright + Chromium", False,
           f"{pip} install playwright  y luego  python3 -m playwright install chromium")

if openai_key():
    print("OK     OPENAI_API_KEY (para la voz)")
else:
    print("AVISO  sin OPENAI_API_KEY: los videos saldrán sin voz.\n"
          "       → para tener voz, crea ~/.claude/.env con la línea  OPENAI_API_KEY=sk-...")

print("\nTodo listo." if ok else "\nArregla lo que falta y vuelve a correr este script.")
sys.exit(0 if ok else 1)
