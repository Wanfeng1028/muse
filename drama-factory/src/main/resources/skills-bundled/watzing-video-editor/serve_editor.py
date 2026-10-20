#!/usr/bin/env python3
"""Local HTTP server for the video editor pages.

Serves the project root so the browser can fetch source/<video>.mp4 and
editor/<name>.html. Adds a POST /api/save endpoint that writes a cuts JSON
back to disk (path validated to stay within the project root).

Usage:
    python3 serve_editor.py                # serves project root on :8765
    python3 serve_editor.py --port 9000
    python3 serve_editor.py --root /some/dir

The project root defaults to the directory containing this script.
"""
import argparse
import http.server
import json
import os
import re
import socketserver
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 8765


def make_handler(root: Path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def end_headers(self):
            # Avoid stale editor HTML during iteration
            self.send_header("Cache-Control", "no-store")
            # Advertise range support so browsers will use it for video seeking
            self.send_header("Accept-Ranges", "bytes")
            super().end_headers()

        def do_GET(self):
            # HTTP Range support — browsers need 206 Partial Content to scrub video.
            # Falls through to default behavior when no Range header is present.
            range_header = self.headers.get("Range")
            if not range_header:
                return super().do_GET()
            path = self.translate_path(self.path)
            if not os.path.isfile(path):
                return super().do_GET()
            try:
                size = os.path.getsize(path)
                m = re.match(r"bytes=(\d+)-(\d*)", range_header)
                if not m:
                    self.send_error(416, "Invalid Range header")
                    return
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
                end = min(end, size - 1)
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                length = end - start + 1
                ctype = self.guess_type(path)
                with open(path, "rb") as f:
                    f.seek(start)
                    self.send_response(206)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.send_header("Content-Length", str(length))
                    self.end_headers()
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(64 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            if self.path != "/api/save":
                self.send_error(404, "Not found")
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as e:
                self._json(400, {"ok": False, "error": f"bad JSON: {e}"})
                return
            rel = payload.get("path")
            data = payload.get("data")
            if not rel or data is None:
                self._json(400, {"ok": False, "error": "expected {path, data}"})
                return
            try:
                target = (root / rel).resolve()
                target.relative_to(root)  # raises if outside
            except ValueError:
                self._json(403, {"ok": False, "error": "path outside project root"})
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(data, indent=2))
            print(f"saved {rel} ({len(json.dumps(data))} bytes)", flush=True)
            self._json(200, {"ok": True, "path": rel})

        def _json(self, status, body):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):
            # Quieter than default
            if "/api/" in (args[0] if args else ""):
                sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), make_handler(root)) as httpd:
        print(f"video-editor server: http://localhost:{args.port}/  (root: {root})")
        print(f"open editors at:    http://localhost:{args.port}/editor/<name>.html")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nshutting down")


if __name__ == "__main__":
    main()
