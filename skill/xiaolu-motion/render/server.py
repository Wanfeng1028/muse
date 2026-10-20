"""Local HTTP server for the headless page: serves engine/ components/ styles/ and the
resolved font files, and receives POSTed raw frames (handed to a callback, usually
written straight into an ffmpeg stdin pipe).

Adapted from 《在我开口之前》 tools/render.py (Sink).
"""
import http.server
import sys
import threading
from pathlib import Path

from .common import REPO

SERVE_DIRS = ("engine", "components", "styles")
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
        ".json": "application/json", ".ttf": "font/ttf", ".otf": "font/otf", ".css": "text/css"}


class Sink:
    def __init__(self, fonts=None):
        self.handler = None
        self.fonts = {f["key"]: f["path"] for f in (fonts or [])}
        srv = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, data=b"", ctype="application/octet-stream"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if data:
                    self.wfile.write(data)

            def do_GET(self):
                path = self.path.split("?")[0]
                if path.startswith("/font/"):
                    fp = srv.fonts.get(path[len("/font/"):])
                    if not fp:
                        return self._send(404)
                    fp = Path(fp)
                else:
                    rel = path.lstrip("/")
                    if not rel.split("/")[0] in SERVE_DIRS:
                        return self._send(403)
                    fp = (REPO / rel).resolve()
                    if REPO.resolve() not in fp.parents:
                        return self._send(403)
                if not fp.is_file():
                    return self._send(404)
                self._send(200, fp.read_bytes(), MIME.get(fp.suffix, "application/octet-stream"))

            def do_POST(self):
                n = int(self.headers.get("Content-Length", "0"))
                data = self.rfile.read(n)
                code = 200
                try:
                    srv.handler(self.path, data)
                except Exception as e:  # noqa: BLE001
                    print("sink error:", repr(e), file=sys.stderr)
                    code = 500
                self._send(code)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}"

    def close(self):
        self.httpd.shutdown()
