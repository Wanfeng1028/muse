#!/usr/bin/env python3
"""Local static server with a cuts-save API for the video editor pages.

Serves a project root directory over HTTP on 127.0.0.1 so the browser can
load source/<video>.mp4 and editor/<name>.html. Adds Range support for video
seeking and a POST /api/save endpoint that writes a cuts JSON file back to
disk (path is validated to remain inside the project root).

Usage:
    python3 serve_editor.py                 # project root, port 8765
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


CHUNK = 64 * 1024
RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")
DEFAULT_PORT = 8765
DEFAULT_ROOT = Path(__file__).resolve().parent


def _parse_range(header, size):
    """Return (start, end) inclusive, or None if the range is unusable."""
    m = RANGE_RE.match(header)
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else size - 1
    if end >= size:
        end = size - 1
    if start >= size or start > end:
        return None
    return start, end


def build_handler(root: Path):
    root = root.resolve()

    class EditorHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        # ----- helpers -----------------------------------------------------

        def _write_json(self, status, body):
            blob = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw or b"{}")

        # ----- response tweaks ---------------------------------------------

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("Accept-Ranges", "bytes")
            super().end_headers()

        # ----- GET (with Range) --------------------------------------------

        def do_GET(self):
            range_header = self.headers.get("Range")
            if not range_header:
                return super().do_GET()

            path = self.translate_path(self.path)
            if not os.path.isfile(path):
                return super().do_GET()

            try:
                size = os.path.getsize(path)
                span = _parse_range(range_header, size)
                if span is None:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.end_headers()
                    return

                start, end = span
                length = end - start + 1

                self.send_response(206)
                self.send_header("Content-Type", self.guess_type(path))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header(
                    "Content-Range", "bytes %d-%d/%d" % (start, end, size)
                )
                self.send_header("Content-Length", str(length))
                self.end_headers()

                with open(path, "rb") as fh:
                    fh.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = fh.read(min(CHUNK, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        # ----- POST /api/save ----------------------------------------------

        def do_POST(self):
            if self.path != "/api/save":
                self.send_error(404, "Not found")
                return

            try:
                payload = self._read_body()
            except json.JSONDecodeError as exc:
                self._write_json(400, {"ok": False, "error": "bad JSON: %s" % exc})
                return

            rel = payload.get("path")
            data = payload.get("data")
            if not rel or data is None:
                self._write_json(
                    400, {"ok": False, "error": "expected {path, data}"}
                )
                return

            try:
                target = (root / rel).resolve()
                target.relative_to(root)
            except ValueError:
                self._write_json(
                    403, {"ok": False, "error": "path outside project root"}
                )
                return

            target.parent.mkdir(parents=True, exist_ok=True)
            encoded = json.dumps(data, indent=2)
            target.write_text(encoded)
            print("saved %s (%d bytes)" % (rel, len(encoded)), flush=True)
            self._write_json(200, {"ok": True, "path": rel})

        # ----- quieter logging ---------------------------------------------

        def log_message(self, fmt, *args):
            first = args[0] if args else ""
            if "/api/" in str(first):
                sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    return EditorHandler


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="video editor local server")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    return ap.parse_args(argv)


def main():
    args = parse_args()
    root = args.root.resolve()

    socketserver.TCPServer.allow_reuse_address = True
    handler = build_handler(root)

    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        print("video-editor server: http://localhost:%d/  (root: %s)"
              % (args.port, root))
        print("open editors at:     http://localhost:%d/editor/<name>.html"
              % args.port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nshutting down")


if __name__ == "__main__":
    main()
