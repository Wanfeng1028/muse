"""Shared helpers: OpenAI key lookup and ffmpeg calls."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def _read_env_file(path):
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def openai_key():
    """Look for the key in: env var -> ~/.claude/.env -> ./.env -> <skill>/.env."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    for p in (Path.home() / ".claude" / ".env", Path.cwd() / ".env", SKILL_DIR / ".env"):
        key = _read_env_file(p)
        if key:
            return key
    return None


def require_key():
    key = openai_key()
    if not key:
        sys.exit(
            "Falta OPENAI_API_KEY. Ponla en una variable de entorno o en ~/.claude/.env así:\n"
            "  OPENAI_API_KEY=sk-...\n"
        )
    return key


def require_ffmpeg():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("Falta ffmpeg. Corre scripts/revisar_entorno.py para ver cómo instalarlo.")


def ffmpeg(*args):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        sys.exit(f"ffmpeg falló:\n{' '.join(cmd)}\n{r.stderr}")


def duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=False,
    )
    return float(r.stdout.strip())
