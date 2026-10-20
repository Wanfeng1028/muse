#!/usr/bin/env python3
"""Tiny invoice app used by selftest.sh and the example storyboards. Stdlib only.

USAGE
  server.py [PORT]   # default 8765; test login: demo@example.com / demo-pass
Bug on purpose: saving an invoice with amount > 1000 returns HTTP 500 and the UI spins forever.
"""
import http.server
import json
import pathlib
import socketserver
import sys

HERE = pathlib.Path(__file__).resolve().parent
INVOICES = [{"id": 1, "customer": "Acme Co", "amount": 420}, {"id": 2, "customer": "Globex", "amount": 75}]


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def authed(self):
        return "session=demo-session-token" in (self.headers.get("Cookie") or "")

    def do_GET(self):
        if self.path.startswith("/login"):
            return self.send(200, (HERE / "login.html").read_text())
        if self.path.startswith("/api/me"):
            return self.send(200 if self.authed() else 401, '{"ok":%s}' % ("true" if self.authed() else "false"),
                             "application/json")
        if self.path.startswith("/api/invoices"):
            return self.send(200, json.dumps(INVOICES), "application/json")
        if not self.authed():
            return self.send(302, "", headers={"Location": "/login"})
        return self.send(200, (HERE / "index.html").read_text())

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode()
        if self.path == "/api/login":
            data = json.loads(body or "{}")
            if data.get("email") == "demo@example.com" and data.get("password") == "demo-pass":
                return self.send(200, '{"ok":true}', "application/json",
                                 {"Set-Cookie": "session=demo-session-token; Path=/; HttpOnly"})
            return self.send(401, '{"error":"bad credentials"}', "application/json")
        if self.path == "/api/invoices":
            data = json.loads(body or "{}")
            if float(data.get("amount") or 0) > 1000:
                return self.send(500, '{"error":"amount overflow in tax calc"}', "application/json")
            inv = {"id": len(INVOICES) + 1, "customer": data.get("customer"), "amount": float(data["amount"])}
            INVOICES.append(inv)
            return self.send(201, json.dumps(inv), "application/json")
        self.send(404, "not found", "text/plain")


class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"fixture app on http://localhost:{port}", flush=True)
    S(("127.0.0.1", port), H).serve_forever()
