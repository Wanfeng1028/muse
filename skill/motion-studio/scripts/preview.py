"""The studio preview: a localhost server for scrubbing, playing and annotating a film.

Serves preview.html at "/" (the Browser pane only accepts an origin), the film's folder tree under /w/,
and a small API:
  GET  /api/info            film name, film URL, mix URL (out/mix.wav if present)
  GET  /api/mtime           newest mtime of the film's sources and mix: the page polls it to hot-reload
  GET  /api/notes           notes.json
  POST /api/notes           {"t": 12.3, "text": "hard cut here"} -> appends an open note
Files are served with byte ranges, so the audio element can seek (python's http.server cannot).
"""
import json
import mimetypes
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
WATCH = ("*.html", "*.js", "*.css", "*.json", "*.svg", "*.png", "*.jpg")


def notes_path(film):
    return film / "notes.json"


def load_notes(film):
    p = notes_path(film)
    return json.loads(p.read_text()) if p.exists() else {"notes": []}


def save_notes(film, data):
    notes_path(film).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def make_handler(film: Path):
    root = film.parent            # films may reference siblings (e.g. ../sources/), so serve the parent tree
    base = f"/w/{film.name}/"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _file(self, path: Path):
            if not path.is_file():
                return self.send_error(404)
            size = path.stat().st_size
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            rng = self.headers.get("Range")
            start, end = 0, size - 1
            m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                else:
                    start = size - int(m.group(2))
                end = min(end, size - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            with open(path, "rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                return self._file(HERE / "preview.html")
            if path == "/api/info":
                mix = film / "out" / "mix.wav"
                return self._json({"film": film.name, "url": base + "film.html", "mix": base + "out/mix.wav" if mix.exists() else None})
            if path == "/api/mtime":
                files = [p for pat in WATCH for p in film.glob(pat) if p.name != "notes.json"] + [film / "out" / "mix.wav"]   # notes must not reload the film
                return self._json({"mtime": max((p.stat().st_mtime for p in files if p.exists()), default=0)})
            if path == "/api/notes":
                return self._json(load_notes(film))
            if path.startswith("/w/"):
                target = (root / path[3:]).resolve()
                if root.resolve() not in target.parents and target != root.resolve():
                    return self.send_error(403)
                return self._file(target)
            self.send_error(404)

        def do_POST(self):
            if self.path != "/api/notes":
                return self.send_error(404)
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            text = str(body.get("text", "")).strip()
            if not text:
                return self._json({"error": "empty note"}, 400)
            data = load_notes(film)
            note = {"id": 1 + max((n["id"] for n in data["notes"]), default=0), "t": round(float(body.get("t", 0)), 3),
                    "where": body.get("where", ""), "text": text, "status": "open", "created": time.strftime("%Y-%m-%d %H:%M:%S")}
            data["notes"].append(note)
            save_notes(film, data)
            return self._json(note)

    return Handler


def serve(film: Path, port: int = 4173):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(film))
    print(f"motion-studio preview for {film.name}: http://localhost:{port}", flush=True)
    server.serve_forever()


def list_notes(film: Path, show_all=False):
    notes = load_notes(film)["notes"]
    for n in notes:
        if show_all or n["status"] == "open":
            reply = f"  -> {n['reply']}" if n.get("reply") else ""
            print(f"#{n['id']} [{n['status']}] t={n['t']:.2f}s {n.get('where', '')}: {n['text']}{reply}")
    if not any(n["status"] == "open" for n in notes):
        print("no open notes")


def resolve_note(film: Path, note_id: int, reply: str):
    data = load_notes(film)
    for n in data["notes"]:
        if n["id"] == note_id:
            n["status"], n["reply"], n["resolved"] = "done", reply, time.strftime("%Y-%m-%d %H:%M:%S")
            save_notes(film, data)
            return n
    raise SystemExit(f"no note #{note_id}")
