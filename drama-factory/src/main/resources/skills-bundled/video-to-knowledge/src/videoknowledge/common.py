import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data, exclusive=False):
    path = Path(path)
    # Files are local artifacts, never raw downloader metadata/cookies.
    text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    with path.open('x' if exclusive else 'w', encoding='utf-8') as f:
        os.chmod(path, 0o600)
        f.write(text)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def category(error):
    text = str(error).lower()
    for name, patterns in [('authentication_or_access', ['403', '429', 'sign in', 'login', 'not available']),
                           ('no_video_formats', ['no video formats', 'requested format is not available']),
                           ('source_mismatch', ['wrong source','source mismatch','resource identity changed']),
                           ('unsupported_media_origin', ['unsupported media origin']),
                           ('transfer_limit', ['transfer limit','media exceeds']),
                           ('media_access_denied', ['media access denied','no complete mp4']),
                           ('browser_connection', ['browser_connect', 'extension disconnected', 'not connected']),
                           ('timeout', ['timed out', 'timeout'])]:
        if any(p in text for p in patterns):
            return name
    return 'backend_failure'


def command(argv, timeout=240):
    try:
        result = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError('timeout: ' + Path(str(argv[0])).name) from None
    if result.returncode:
        if Path(str(argv[0])).name in {'ffmpeg','ffprobe','whisper-cli'}:
            raise RuntimeError(Path(str(argv[0])).name+': '+result.stderr[-800:])
        # Do not persist stderr: it can contain signed CDN URLs or request tokens.
        raise RuntimeError(Path(str(argv[0])).name + ': ' + category(result.stderr+'\n'+result.stdout))
    return result.stdout


def inside(root, relative):
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('Artifact path escapes job directory')
    return path


def terms(text):
    tokens=set(re.findall(r'[a-z0-9]+', text.lower()))
    for word in re.findall(r'[\u4e00-\u9fff]+', text):
        tokens.update(word[i:i+2] for i in range(len(word)-1))
    return tokens
