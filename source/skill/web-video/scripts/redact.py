#!/usr/bin/env python3
"""Redact secrets from the HAR, the Playwright trace and the console log before sharing them.

USAGE
  redact.py RUN_DIR [--secret VALUE ...] [--extra-key NAME ...] [--extra-header NAME ...]
Writes net.redacted.har, trace.redacted.zip, console.redacted.json next to the originals
(originals are never shared; attach only the *.redacted.* files). Prints what was redacted.
Covers: every value the storyboard typed into a secret field (password inputs, selectors naming
password/token/otp...; Playwright traces record fill() values verbatim), --secret VALUE, auth/cookie headers, cookies, secret-looking query params, JSON/form fields such as
password/token/secret/otp/card/cvv, and Bearer/JWT-looking strings. It does NOT blur pixels in
screenshots or video frames: check those by eye (verify/contact.png).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse
import zipfile
from collections import Counter

MASK = "[REDACTED]"
HEADERS = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key", "x-auth-token",
           "x-csrf-token", "x-xsrf-token", "api-key"}
KEY_RE = re.compile(r"password|passwd|^pass$|^pwd$|secret|token|api[_-]?key|^session(_?id)?$|sessionid|^otp$|"
                    r"cvv|cvc|card[_-]?number|^ssn$|^auth$|credential|private[_-]?key|signature|^sig$", re.I)
TOKEN_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")


class Redactor:
    def __init__(self, extra_keys=(), extra_headers=(), literals=()):
        self.count = Counter()
        self.literals = sorted({x for x in literals if x and len(x) >= 3}, key=len, reverse=True)
        self.headers = HEADERS | {h.lower() for h in extra_headers}
        self.extra = [k.lower() for k in extra_keys]

    def secret_key(self, k: str) -> bool:
        return bool(KEY_RE.search(k)) or k.lower() in self.extra

    def url(self, u: str) -> str:
        try:
            parts = urllib.parse.urlsplit(u)
        except ValueError:
            return u
        if not parts.query:
            return u
        q = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        changed = False
        out = []
        for k, v in q:
            if self.secret_key(k) and v:
                out.append((k, MASK))
                changed = True
                self.count["query param"] += 1
            else:
                out.append((k, v))
        return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(out))) if changed else u

    def text(self, s: str) -> str:
        """A body or free text: JSON, form-encoded, or plain."""
        st = s.strip()
        if st[:1] in "{[":
            try:
                return json.dumps(self.walk(json.loads(st)), ensure_ascii=False)
            except ValueError:
                pass
        if "=" in s and "&" in s and " " not in st and len(s) < 100000:
            pairs = urllib.parse.parse_qsl(s, keep_blank_values=True)
            if pairs:
                red = [(k, MASK if self.secret_key(k) and v else v) for k, v in pairs]
                n = sum(1 for (k, v), (_, v2) in zip(pairs, red) if v != v2)
                if n:
                    self.count["form field"] += n
                    return urllib.parse.urlencode(red)
        new, n = TOKEN_RE.subn(lambda m: (m.group(1) or "") + MASK, s)
        self.count["token in text"] += n
        return new

    def walk(self, o):
        if isinstance(o, dict):
            if {"name", "value"} <= o.keys() and isinstance(o.get("name"), str):
                nm = o["name"].lower()
                if nm in self.headers or (self.secret_key(nm) and nm not in ("content-type", "content-length")):
                    self.count[f"header/cookie {nm}"] += 1
                    return {**o, "value": MASK}
            out = {}
            for k, v in o.items():
                if k == "cookies" and isinstance(v, list):
                    out[k] = [{**c, "value": MASK} if isinstance(c, dict) and "value" in c else c for c in v]
                    self.count["cookie"] += len(v)
                elif isinstance(v, str) and self.secret_key(k) and k not in ("mimeType", "_securityState"):
                    out[k] = MASK
                    self.count[f"field {k}"] += 1
                elif isinstance(v, str) and k == "url":
                    out[k] = self.url(v)
                elif isinstance(v, str) and k == "text":
                    out[k] = self.text(v)
                else:
                    out[k] = self.walk(v)
            return out
        if isinstance(o, list):
            return [self.walk(x) for x in o]
        if isinstance(o, str):
            new, n = TOKEN_RE.subn(lambda m: (m.group(1) or "") + MASK, o)
            self.count["token in text"] += n
            return new
        return o


def literal_pass(r: Redactor, data: bytes) -> bytes:
    """Replace known secret values anywhere (JSON-escaped forms included)."""
    for lit in r.literals:
        for form in {lit, json.dumps(lit)[1:-1]}:
            b = form.encode()
            n = data.count(b)
            if n:
                r.count["known secret value"] += n
                data = data.replace(b, MASK.encode())
    return data


def storyboard_secrets(run: pathlib.Path) -> list[str]:
    """Values the storyboard typed into secret fields (by selector name or recorded password inputs)."""
    sbp, evp = run / "storyboard.yaml", run / "events.json"
    if not sbp.exists():
        return []
    import yaml
    from record import is_secret, step_actions
    marked = set(json.loads(evp.read_text(encoding="utf-8")).get("secret_selectors", [])) if evp.exists() else set()
    out = []
    for step in (yaml.safe_load(sbp.read_text(encoding="utf-8")) or {}).get("steps", []):
        try:
            acts = step_actions(step)
        except (ValueError, KeyError):
            continue
        for verb, args in acts:
            if verb in ("fill", "type") and (args[0] in marked or is_secret(args[0], None)):
                out.append(args[1])
    return out


def redact_trace(r: Redactor, src: pathlib.Path, dst: pathlib.Path):
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            name = info.filename
            if name.endswith((".trace", ".network", ".stacks")):
                lines = []
                for line in data.decode("utf-8", "replace").splitlines():
                    try:
                        lines.append(json.dumps(r.walk(json.loads(line)), ensure_ascii=False))
                    except ValueError:
                        lines.append(r.text(line))
                data = ("\n".join(lines) + "\n").encode()
            elif name.startswith("resources/") and not name.endswith((".jpeg", ".jpg", ".png", ".webp", ".woff2")):
                try:
                    data = r.text(data.decode("utf-8")).encode()
                except UnicodeDecodeError:
                    pass
            zout.writestr(info, literal_pass(r, data))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=pathlib.Path)
    ap.add_argument("--secret", action="append", default=[], help="a literal value to mask everywhere")
    ap.add_argument("--extra-key", action="append", default=[])
    ap.add_argument("--extra-header", action="append", default=[])
    a = ap.parse_args()
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    r = Redactor(a.extra_key, a.extra_header, a.secret + storyboard_secrets(a.run))
    done = []
    har = a.run / "net.har"
    if har.exists():
        (a.run / "net.redacted.har").write_bytes(literal_pass(r, json.dumps(
            r.walk(json.loads(har.read_text(encoding="utf-8"))), ensure_ascii=False, indent=1).encode()))
        done.append("net.redacted.har")
    con = a.run / "console.json"
    if con.exists():
        (a.run / "console.redacted.json").write_bytes(literal_pass(r, json.dumps(
            r.walk(json.loads(con.read_text(encoding="utf-8"))), ensure_ascii=False, indent=1).encode()))
        done.append("console.redacted.json")
    tr = a.run / "trace.zip"
    if tr.exists():
        redact_trace(r, tr, a.run / "trace.redacted.zip")
        done.append("trace.redacted.zip")
    if not done:
        sys.exit("nothing to redact (no net.har, console.json or trace.zip)")
    print("wrote: " + ", ".join(done))
    for k, n in sorted(r.count.items()):
        if n:
            print(f"  {n:4} × {k}")
    print("Pixels are not redacted: check verify/contact.png and the trace screenshots by eye.")


if __name__ == "__main__":
    main()
