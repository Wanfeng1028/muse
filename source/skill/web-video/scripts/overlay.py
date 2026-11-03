"""Overlay filter builders (captions, cards, bug panel, timestamp) and the SRT writer.

Not a CLI; edl.py imports it. Every text goes through a UTF-8 textfile with expansion=none,
so quotes, colons and Vietnamese diacritics never need escaping. ffmpeg runs with cwd = run dir,
so every path in a filter is relative and free of spaces.
"""
from __future__ import annotations

import pathlib
import textwrap
import urllib.parse

from common import FPS, font, link_or_copy

PANEL_W = 440          # bug-report side panel width
CAPTION_SIZE = 34
CARD_BG = "0x14213d"
PANEL_BG = "0x111827"


class Texts:
    """Writes text snippets to <run>/text/NN.txt and links the fonts there."""

    def __init__(self, run: pathlib.Path):
        self.dir = run / "text"
        self.dir.mkdir(exist_ok=True)
        self.n = 0
        for name, mono in (("font.ttf", False), ("mono.ttf", True)):
            link_or_copy(font(mono), self.dir / name)

    def file(self, text: str) -> str:
        self.n += 1
        p = self.dir / f"{self.n:02d}.txt"
        p.write_text(text, encoding="utf-8", newline="\n")   # CRLF would add blank lines in drawtext (Windows)
        return f"text/{p.name}"


def drawtext(tf: str, *, size: int, x: str, y: str, color="white", box: str | None = None,
             border=14, enable: str | None = None, mono=False, spacing=8) -> str:
    f = "text/mono.ttf" if mono else "text/font.ttf"
    s = (f"drawtext=fontfile={f}:textfile={tf}:expansion=none:fontsize={size}:fontcolor={color}"
         f":line_spacing={spacing}:x={x}:y={y}")
    if box:
        s += f":box=1:boxcolor={box}:boxborderw={border}"
    if enable:
        s += f":enable='{enable}'"
    return s


def between(a: float, b: float) -> str:
    return f"between(t,{a:.3f},{b:.3f})"


def caption_position(step_clicks: list[dict], h: int) -> str:
    """Put the caption on the half opposite the clicks of its step."""
    if any(c["y"] > h * 0.55 for c in step_clicks):
        return "top"
    return "bottom"


def caption_rect(text: str, pos: str, w: int, h: int) -> tuple[float, float, float, float]:
    tw = min(w, len(text) * CAPTION_SIZE * 0.55 + 32)
    th = CAPTION_SIZE + 32
    y = 46 if pos == "top" else h - 60 - th + 14
    return ((w - tw) / 2, y, tw, th)


def overlaps(r1, r2) -> bool:
    x1, y1, w1, h1 = r1
    x2, y2, w2, h2 = r2
    return x1 < x2 + w2 and x2 < x1 + w1 and y1 < y2 + h2 and y2 < y1 + h1


def caption_filter(T: Texts, text: str, a: float, b: float, pos: str) -> str:
    y = "60" if pos == "top" else "h-th-60"
    return drawtext(T.file(text), size=CAPTION_SIZE, x="(w-tw)/2", y=y, box="black@0.68", border=16,
                    enable=between(a, b))


def card(T: Texts, label: str, title: str, sub: str | None, w: int, h: int, dur: float) -> str:
    """A solid title card [label] of dur seconds, fade in/out."""
    parts = [f"color=c={CARD_BG}:s={w}x{h}:r={FPS}:d={dur:.2f}",
             drawtext(T.file(title), size=58, x="(w-tw)/2", y="(h-th)/2-30" if sub else "(h-th)/2")]
    if sub:
        parts.append(drawtext(T.file(sub), size=28, x="(w-tw)/2", y="(h/2)+40", color="0xcbd5e1"))
    parts += ["format=yuv420p", "setsar=1", f"fade=t=in:d=0.3", f"fade=t=out:st={dur - 0.35:.2f}:d=0.35"]
    return ",".join(parts) + f"[{label}]"


def timestamp_filter() -> str:
    """Original recording time, burned in BEFORE any cut so freezes and speed-ups keep true time."""
    return ("drawtext=fontfile=text/mono.ttf:text='REC %{pts\\:hms}':fontsize=20:fontcolor=yellow"
            ":box=1:boxcolor=black@0.55:boxborderw=8:x=w-tw-14:y=14")


def wrap(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(str(text), width=width, break_long_words=True)) or " "


def bug_panel(T: Texts, *, w: int, h: int, title: str, steps: list[dict], bug_t: float | None,
              expected: str, actual: str, errors: list[dict], total: float) -> list[str]:
    """Filters (to chain after pad) drawing the right-hand panel. steps: [{text, a, b}] in body time."""
    x0 = w + 24
    out = [f"drawbox=x={w}:y=0:w={PANEL_W}:h={h}:color={PANEL_BG}:t=fill",
           drawtext(T.file(wrap(title, 30)), size=24, x=str(x0), y="22", color="white"),
           drawtext(T.file("STEPS"), size=16, x=str(x0), y="92", color="0x9ca3af")]
    y = 120
    for i, s in enumerate(steps, 1):
        line = wrap(f"{i}. {s['text']}", 34)
        nlines = line.count("\n") + 1
        lh = 26 * nlines
        out.append(f"drawbox=x={w + 12}:y={y - 6}:w={PANEL_W - 24}:h={lh + 8}:color=0x2563eb@0.85:t=fill"
                   f":enable='{between(s['a'], s['b'])}'")
        out.append(drawtext(T.file(line), size=19, x=str(x0), y=str(y), color="0xe5e7eb", spacing=6))
        y += lh + 12
    if bug_t is not None:
        y = max(y + 16, 400)
        en = between(bug_t, total + 1)
        out.append(drawtext(T.file("EXPECTED"), size=16, x=str(x0), y=str(y), color="0x4ade80", enable=en))
        exp = wrap(expected, 34)
        out.append(drawtext(T.file(exp), size=19, x=str(x0), y=str(y + 24), color="white", enable=en, spacing=6))
        y += 24 + 26 * (exp.count("\n") + 1) + 14
        out.append(drawtext(T.file("ACTUAL"), size=16, x=str(x0), y=str(y), color="0xf87171", enable=en))
        act = wrap(actual, 34)
        out.append(drawtext(T.file(act), size=19, x=str(x0), y=str(y + 24), color="white", enable=en, spacing=6))
    if errors:
        first = min(e["t_body"] for e in errors)
        lines = []
        for e in errors[:4]:
            if e["source"] == "http":
                path = urllib.parse.urlsplit(e.get("url") or "").path or "/"
                lines.append(f"HTTP {e.get('status')} {e.get('method', '')} {path if len(path) <= 34 else '…' + path[-33:]}")
            else:
                lines.append(f"{e['source']}: {str(e.get('text', ''))[:44]}")
        txt = "\n".join(wrap(l, 44) for l in lines)
        out.append(drawtext(T.file(txt), size=15, x=str(x0), y=f"h-th-20", color="0xfca5a5", mono=True,
                            enable=between(first, total + 1), spacing=5))
    return out


def bug_box(bbox: dict | None, a: float, b: float, w: int, h: int) -> list[str]:
    if not bbox:
        return []
    pad = 8
    x = max(0, int(bbox["x"] - pad))
    y = max(0, int(bbox["y"] - pad))
    bw = min(w - x, int(bbox["width"] + 2 * pad))
    bh = min(h - y, int(bbox["height"] + 2 * pad))
    en = between(a, b)
    ly = y - 34 if y > 40 else y + bh + 6
    return [f"drawbox=x={x}:y={y}:w={bw}:h={bh}:color=red:t=5:enable='{en}'",
            f"drawbox=x={x}:y={ly}:w=64:h=28:color=red:t=fill:enable='{en}'",
            f"drawtext=fontfile=text/font.ttf:text='BUG':fontsize=20:fontcolor=white:x={x + 12}:y={ly + 4}"
            f":enable='{en}'"]


def srt(captions: list[dict]) -> str:
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "\n".join(f"{n}\n{ts(c['a'])} --> {ts(c['b'])}\n{c['text']}\n" for n, c in enumerate(captions, 1))
