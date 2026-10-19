#!/usr/bin/env python3
"""Build a single-file HTML timeline editor for adjusting video cut points.

Usage:
    python3 build_editor.py <video_path> <transcript_json> <cuts_json> <output_html>

The generated HTML embeds the video reference, the Whisper transcript and the
current cut list. Open it in a browser, drag the keep-bands to adjust the
segments, preview the result, then save the cuts back through the companion
server (or export them as a file).
"""
import json
import os
import sys
from pathlib import Path


USAGE = __doc__


def _die(msg=None):
    if msg:
        print(msg, file=sys.stderr)
    print(USAGE, file=sys.stderr)
    sys.exit(1)


def _coerce_segments(cuts_input):
    """Accept either {"segments": [...]} or a bare list of segments."""
    if isinstance(cuts_input, dict):
        raw = cuts_input.get("segments", [])
    else:
        raw = cuts_input
    out = []
    for entry in raw:
        out.append({"start": float(entry["start"]), "end": float(entry["end"])})
    return out


def _collect_transcript(transcript):
    segments = transcript.get("segments", [])
    rows = []
    for s in segments:
        rows.append({
            "start": s.get("start", 0),
            "end": s.get("end", 0),
            "text": s.get("text", ""),
        })
    return segments, rows


def _total_duration(segments):
    if not segments:
        return 0
    return max((float(s.get("end", 0)) for s in segments), default=0)


PAGE_SHELL = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Cut Timeline Editor</title>
<style>
  :root {
    --bg: #101114;
    --panel: #191b1f;
    --panel-2: #212429;
    --line: #2b2f36;
    --text: #e6e7e9;
    --muted: #8a8f98;
    --accent: #4caf50;
    --accent-2: #ff9800;
    --danger: #ef5350;
    --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    font-family: -apple-system, system-ui, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
  }
  header {
    display: flex; flex-wrap: wrap; gap: 12px;
    justify-content: space-between; align-items: center;
    padding: 12px 20px;
    background: var(--panel);
    border-bottom: 1px solid var(--line);
  }
  header h1 { font-size: 16px; margin: 0; font-weight: 500; }
  .stats { font-size: 12px; color: var(--muted); }
  .stats b { color: var(--accent); font-family: var(--mono); font-weight: 600; }
  main { max-width: 1400px; margin: 0 auto; padding: 20px; }
  video { display: block; width: 100%; max-height: 50vh; background: #000; border-radius: 4px; }

  .tl-scroller { overflow-x: auto; overflow-y: hidden; background: var(--panel); border-radius: 4px; margin-top: 20px; }
  .tl-scroller::-webkit-scrollbar { height: 10px; }
  .tl-scroller::-webkit-scrollbar-track { background: var(--bg); }
  .tl-scroller::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
  .tl { position: relative; height: 56px; user-select: none; cursor: pointer; }

  .tick { position: absolute; top: 0; bottom: 14px; width: 1px; background: var(--line); }
  .tick-label { position: absolute; bottom: 1px; font-family: var(--mono); font-size: 9px; color: #555; transform: translateX(2px); }

  .band {
    position: absolute; top: 6px; bottom: 18px;
    background: rgba(76, 175, 80, 0.32);
    border: 1px solid var(--accent);
    border-radius: 3px;
    cursor: grab;
  }
  .band:hover { background: rgba(76, 175, 80, 0.5); }
  .band:active { cursor: grabbing; }
  .band.is-selected { background: rgba(255, 152, 0, 0.42); border-color: var(--accent-2); }
  .band .label {
    position: absolute; top: 1px; left: 10px;
    font-size: 10px; font-weight: 600; color: #fff;
    text-shadow: 0 1px 2px rgba(0,0,0,0.85);
    pointer-events: none;
  }
  .handle { position: absolute; top: 0; bottom: 0; width: 8px; cursor: ew-resize; background: transparent; }
  .handle:hover { background: rgba(255,255,255,0.25); }
  .handle.l { left: 0; border-radius: 3px 0 0 3px; }
  .handle.r { right: 0; border-radius: 0 3px 3px 0; }

  .playhead { position: absolute; top: 0; bottom: 0; width: 2px; background: #ff5722; pointer-events: none; z-index: 10; }

  .tl-tools { display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; align-items: center; margin-top: 6px; }
  .hint { font-size: 11px; color: #555; }
  .zoom { display: flex; align-items: center; gap: 4px; }
  .zoom button { min-width: 30px; padding: 4px 10px; font-size: 13px; }
  .zoom .lvl { font-family: var(--mono); font-size: 11px; color: var(--muted); min-width: 50px; text-align: center; }

  .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 16px 0; }
  button {
    background: var(--panel-2); color: var(--text);
    border: 1px solid #363a42; padding: 8px 14px; border-radius: 4px;
    font-size: 13px; font-family: inherit; cursor: pointer;
  }
  button:hover { background: #2d3138; }
  button:disabled { opacity: 0.4; cursor: default; }
  button.primary { background: #2e7d32; border-color: var(--accent); color: #fff; }
  button.primary:hover { background: #388e3c; }
  button.danger { background: transparent; border-color: #d32f2f; color: var(--danger); padding: 4px 8px; font-size: 12px; }
  button.danger:hover { background: rgba(211,47,47,0.15); }

  .rows { background: var(--panel); border-radius: 4px; overflow: hidden; margin-top: 12px; }
  .row {
    display: grid;
    grid-template-columns: 32px 110px 110px 70px 1fr 80px 32px;
    gap: 10px; align-items: center;
    padding: 10px 14px;
    border-bottom: 1px solid #232323;
  }
  .row:last-child { border-bottom: none; }
  .row.is-selected { background: rgba(255, 152, 0, 0.08); }
  .row .num { font-family: var(--mono); font-weight: 600; color: var(--accent); text-align: center; }
  .row input {
    width: 100%; padding: 6px 8px; font-family: var(--mono); font-size: 13px;
    background: var(--bg); color: var(--text);
    border: 1px solid var(--line); border-radius: 3px;
  }
  .row input:focus { outline: none; border-color: var(--accent); }
  .row .dur { font-family: var(--mono); font-size: 12px; color: var(--muted); text-align: right; }
  .row .txt { font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .transcript {
    margin-top: 24px; padding: 16px 20px;
    background: var(--panel); border-radius: 4px;
    font-size: 13px; line-height: 1.8;
    max-height: 320px; overflow-y: auto;
  }
  .ts { display: inline; }
  .ts .t { font-family: var(--mono); font-size: 11px; color: #555; margin-right: 4px; }
  .ts.kept .x { color: var(--accent); }
  .ts.cut .x { color: #666; }
  .ts .x { padding: 0 2px; border-radius: 2px; cursor: pointer; }
  .ts .x:hover { background: rgba(255,255,255,0.1); }

  .keys { margin-left: auto; font-size: 11px; color: #555; }
  .keys code { background: var(--panel-2); padding: 1px 5px; border-radius: 2px; color: #aaa; font-size: 11px; }

  .toast {
    position: fixed; bottom: 24px; right: 24px;
    background: #2e7d32; color: #fff;
    padding: 12px 20px; border-radius: 4px;
    opacity: 0; transition: opacity 0.3s;
    pointer-events: none; z-index: 100;
  }
  .toast.show { opacity: 1; }
</style>
</head>
<body>
<header>
  <h1 id="doc-title">Cut Timeline Editor</h1>
  <div class="stats">
    Source <b id="stat-src">--</b>
    &middot; Kept <b id="stat-kept">--</b>
    &middot; <b id="stat-pct">--</b>
    &middot; Segments <b id="stat-count">--</b>
  </div>
</header>
<main>
  <video id="player" controls preload="metadata"></video>

  <div class="tl-scroller" id="tl-scroller">
    <div class="tl" id="tl"></div>
  </div>
  <div class="tl-tools">
    <div class="hint">Drag a band to shift it. Grab its left/right edge to trim. Click empty space to seek.</div>
    <div class="zoom">
      <button id="zoom-out" title="Zoom out">&minus;</button>
      <span class="lvl" id="zoom-lvl">100%</span>
      <button id="zoom-in" title="Zoom in">+</button>
      <button id="zoom-fit" title="Reset zoom">Fit</button>
    </div>
  </div>

  <div class="actions">
    <button class="primary" id="btn-preview">&#9654; Preview Final</button>
    <button id="btn-add">+ Add segment at playhead</button>
    <button id="btn-set-start">Set start = playhead</button>
    <button id="btn-set-end">Set end = playhead</button>
    <button id="btn-undo" disabled>&#x21A9; Undo</button>
    <button class="primary" id="btn-save" style="margin-left:auto;">&#x1F4BE; Save</button>
    <button id="btn-export" title="Download as file (no server needed)">&#x2B07; Export</button>
  </div>
  <div class="keys">
    Keys: <code>Space</code> play/pause &middot; <code>&larr;</code>/<code>&rarr;</code> seek 1s (Shift 0.1s) &middot;
    <code>I</code> start &middot; <code>O</code> end &middot;
    <code>&#8984;Z</code> undo &middot; <code>&#8984;S</code> save &middot; <code>&#8984;</code>+scroll zoom
  </div>

  <div class="rows" id="rows"></div>
  <div class="transcript" id="transcript"></div>
</main>
<div class="toast" id="toast"></div>
<script>
"use strict";

var DATA = __DATA__;
var MIN_DUR = 0.05;
var UNDO_LIMIT = 100;

var bands = DATA.segments.map(function (s) {
  return { start: Number(s.start), end: Number(s.end) };
});
var selected = -1;
var undoStack = [];
var zoom = 1;
var drag = null;
var stopAtEnd = null;
var preview = null;

var player = document.getElementById("player");
player.src = DATA.video_src;

function fmtTime(sec) {
  if (sec === null || sec === undefined || isNaN(sec)) return "--:--";
  var m = Math.floor(sec / 60);
  var s = (sec % 60).toFixed(2);
  return m + ":" + (s.length < 5 ? "0" + s : s);
}

function sortBands() {
  bands.sort(function (a, b) { return a.start - b.start; });
}

function toast(msg) {
  var el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(function () { el.classList.remove("show"); }, 2000);
}

function pushUndo() {
  undoStack.push({
    bands: bands.map(function (s) { return { start: s.start, end: s.end }; }),
    selected: selected
  });
  if (undoStack.length > UNDO_LIMIT) undoStack.shift();
  document.getElementById("btn-undo").disabled = undoStack.length === 0;
}

function popUndo() {
  if (!undoStack.length) return;
  var snap = undoStack.pop();
  bands = snap.bands.map(function (s) { return { start: s.start, end: s.end }; });
  selected = snap.selected;
  document.getElementById("btn-undo").disabled = undoStack.length === 0;
  renderAll();
  toast("Undone");
}

function keptSeconds() {
  return bands.reduce(function (acc, s) { return acc + Math.max(0, s.end - s.start); }, 0);
}

function textFor(start, end) {
  var parts = [];
  for (var i = 0; i < DATA.transcript.length; i++) {
    var t = DATA.transcript[i];
    if (t.end > start && t.start < end) parts.push(t.text.trim());
  }
  return parts.join(" ").slice(0, 200);
}

function renderHeader() {
  document.getElementById("stat-src").textContent = fmtTime(DATA.duration);
  var kept = keptSeconds();
  document.getElementById("stat-kept").textContent = fmtTime(kept);
  var pct = DATA.duration > 0 ? (kept / DATA.duration * 100) : 0;
  document.getElementById("stat-pct").textContent = pct.toFixed(0) + "%";
  document.getElementById("stat-count").textContent = bands.length;
  var name = DATA.source.split("/").pop();
  document.getElementById("doc-title").textContent = "Cut Timeline Editor — " + name;
}

function renderTimeline() {
  var tl = document.getElementById("tl");
  tl.style.width = (zoom * 100) + "%";
  tl.innerHTML = "";

  var base;
  if (DATA.duration > 600) base = 60;
  else if (DATA.duration > 120) base = 30;
  else base = 10;
  var step = Math.max(1, base / Math.pow(2, Math.floor(Math.log2(zoom))));

  for (var t = 0; t <= DATA.duration; t += step) {
    var tick = document.createElement("div");
    tick.className = "tick";
    tick.style.left = (t / DATA.duration * 100) + "%";
    tl.appendChild(tick);

    var lbl = document.createElement("div");
    lbl.className = "tick-label";
    lbl.style.left = (t / DATA.duration * 100) + "%";
    var mm = Math.floor(t / 60), ss = Math.floor(t % 60);
    lbl.textContent = mm + ":" + (ss < 10 ? "0" + ss : ss);
    tl.appendChild(lbl);
  }

  bands.forEach(function (seg, i) {
    var band = document.createElement("div");
    band.className = "band" + (i === selected ? " is-selected" : "");
    band.style.left = (seg.start / DATA.duration * 100) + "%";
    band.style.width = ((seg.end - seg.start) / DATA.duration * 100) + "%";
    band.dataset.idx = i;

    var hl = document.createElement("div");
    hl.className = "handle l";
    var hr = document.createElement("div");
    hr.className = "handle r";
    var lab = document.createElement("div");
    lab.className = "label";
    lab.textContent = String(i + 1);

    band.appendChild(hl);
    band.appendChild(hr);
    band.appendChild(lab);

    band.addEventListener("mousedown", function (ev) {
      if (ev.button !== 0) return;
      var mode = "move";
      if (ev.target === hl) mode = "start";
      else if (ev.target === hr) mode = "end";
      drag = {
        mode: mode,
        idx: i,
        x0: ev.clientX,
        orig: { start: seg.start, end: seg.end },
        width: tl.offsetWidth,
        moved: false,
        snapshot: false
      };
      ev.preventDefault();
      ev.stopPropagation();
    });
    band.addEventListener("click", function (ev) { ev.stopPropagation(); });

    tl.appendChild(band);
  });

  var ph = document.createElement("div");
  ph.className = "playhead";
  ph.id = "playhead";
  ph.style.left = (player.currentTime / DATA.duration * 100) + "%";
  tl.appendChild(ph);
}

function renderRows() {
  var box = document.getElementById("rows");
  box.innerHTML = "";
  bands.forEach(function (seg, i) {
    var dur = seg.end - seg.start;
    var txt = textFor(seg.start, seg.end);
    var row = document.createElement("div");
    row.className = "row" + (i === selected ? " is-selected" : "");
    row.innerHTML =
      '<div class="num">' + (i + 1) + '</div>' +
      '<input data-field="start" data-idx="' + i + '" value="' + seg.start.toFixed(2) + '">' +
      '<input data-field="end" data-idx="' + i + '" value="' + seg.end.toFixed(2) + '">' +
      '<div class="dur">' + dur.toFixed(2) + 's</div>' +
      '<div class="txt" title="' + txt.replace(/"/g, "&quot;") + '">' + (txt || "&mdash;") + '</div>' +
      '<button data-action="play" data-idx="' + i + '">&#9654; Play</button>' +
      '<button class="danger" data-action="del" data-idx="' + i + '">&#x2715;</button>';
    box.appendChild(row);
  });

  box.querySelectorAll("input").forEach(function (inp) {
    inp.addEventListener("change", function (ev) {
      var idx = Number(ev.target.dataset.idx);
      var field = ev.target.dataset.field;
      var v = parseFloat(ev.target.value);
      if (!isNaN(v) && bands[idx][field] !== v) {
        pushUndo();
        bands[idx][field] = v;
        sortBands();
        renderAll();
      }
    });
    inp.addEventListener("focus", function (ev) {
      selected = Number(ev.target.dataset.idx);
      renderTimeline();
      renderRows();
    });
  });

  box.querySelectorAll("button[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function (ev) {
      var idx = Number(ev.target.dataset.idx);
      var act = ev.target.dataset.action;
      if (act === "play") playSegment(idx);
      else if (act === "del") deleteSegment(idx);
    });
  });
}

function renderTranscript() {
  var box = document.getElementById("transcript");
  box.innerHTML = "";
  DATA.transcript.forEach(function (t) {
    var kept = bands.some(function (s) { return t.end > s.start && t.start < s.end; });
    var span = document.createElement("span");
    span.className = "ts " + (kept ? "kept" : "cut");
    var m = Math.floor(t.start / 60), s = Math.floor(t.start % 60);
    var ts = m + ":" + (s < 10 ? "0" + s : s);
    span.innerHTML = '<span class="t">[' + ts + ']</span><span class="x"> ' + t.text.trim() + '</span> ';
    span.querySelector(".x").addEventListener("click", function () {
      player.currentTime = t.start;
      player.play();
    });
    box.appendChild(span);
  });
}

function renderAll() {
  renderHeader();
  renderTimeline();
  renderRows();
  renderTranscript();
}

function playSegment(idx) {
  selected = idx;
  renderTimeline();
  renderRows();
  var seg = bands[idx];
  player.currentTime = seg.start;
  preview = null;
  stopAtEnd = { end: seg.end };
  player.play();
}

function deleteSegment(idx) {
  if (!confirm("Delete segment " + (idx + 1) + "?")) return;
  pushUndo();
  bands.splice(idx, 1);
  if (selected === idx) selected = -1;
  else if (selected > idx) selected--;
  renderAll();
}

function addSegment() {
  pushUndo();
  var t = player.currentTime;
  var seg = { start: Math.max(0, t - 1), end: Math.min(DATA.duration, t + 1) };
  bands.push(seg);
  sortBands();
  selected = bands.indexOf(seg);
  renderAll();
}

function setStart() {
  if (selected < 0) { toast("Select a segment first"); return; }
  var v = Number(player.currentTime.toFixed(2));
  if (bands[selected].start === v) return;
  pushUndo();
  bands[selected].start = v;
  sortBands();
  renderAll();
}

function setEnd() {
  if (selected < 0) { toast("Select a segment first"); return; }
  var v = Number(player.currentTime.toFixed(2));
  if (bands[selected].end === v) return;
  pushUndo();
  bands[selected].end = v;
  sortBands();
  renderAll();
}

function previewFinal() {
  if (!bands.length) return;
  sortBands();
  preview = { idx: 0 };
  stopAtEnd = null;
  player.currentTime = bands[0].start;
  player.play();
}

function payload() {
  sortBands();
  return {
    source: DATA.source,
    duration: DATA.duration,
    segments: bands.map(function (s) {
      return { start: Number(s.start.toFixed(2)), end: Number(s.end.toFixed(2)) };
    })
  };
}

function exportJSON() {
  var out = payload();
  var blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = DATA.source.split("/").pop().replace(/\.[^.]+$/, "") + "_cuts.json";
  a.click();
  URL.revokeObjectURL(url);
  toast("Exported " + a.download);
}

function saveJSON() {
  var out = payload();
  fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: DATA.save_path, data: out })
  }).then(function (r) {
    if (!r.ok) {
      return r.text().then(function (txt) { throw new Error(txt || ("HTTP " + r.status)); });
    }
    return r.json();
  }).then(function (j) {
    toast("Saved to " + (j.path || DATA.save_path));
  }).catch(function (err) {
    toast("Save failed: " + err.message + " (try Export instead)");
  });
}

function setZoom(z) {
  zoom = Math.max(1, Math.min(32, z));
  document.getElementById("zoom-lvl").textContent = Math.round(zoom * 100) + "%";
  renderTimeline();
}

function applyDrag(ev) {
  if (!drag) return;
  var dx = ev.clientX - drag.x0;
  if (!drag.moved && Math.abs(dx) < 3) return;
  if (!drag.moved) {
    drag.moved = true;
    if (!drag.snapshot) { pushUndo(); drag.snapshot = true; }
  }
  var dt = (dx / drag.width) * DATA.duration;
  var seg = bands[drag.idx];
  var orig = drag.orig;

  if (drag.mode === "move") {
    var dur = orig.end - orig.start;
    var ns = Math.max(0, Math.min(DATA.duration - dur, orig.start + dt));
    seg.start = ns;
    seg.end = ns + dur;
  } else if (drag.mode === "start") {
    seg.start = Math.max(0, Math.min(orig.end - MIN_DUR, orig.start + dt));
  } else {
    seg.end = Math.max(orig.start + MIN_DUR, Math.min(DATA.duration, orig.end + dt));
  }

  renderTimeline();

  var sIn = document.querySelector('input[data-field="start"][data-idx="' + drag.idx + '"]');
  var eIn = document.querySelector('input[data-field="end"][data-idx="' + drag.idx + '"]');
  if (sIn) sIn.value = seg.start.toFixed(2);
  if (eIn) eIn.value = seg.end.toFixed(2);
}

function finishDrag() {
  if (!drag) return;
  var moved = drag.moved;
  var idx = drag.idx;
  drag = null;
  if (!moved) {
    playSegment(idx);
  } else {
    sortBands();
    renderAll();
  }
}

window.addEventListener("mousemove", applyDrag);
window.addEventListener("mouseup", finishDrag);

player.addEventListener("timeupdate", function () {
  var ph = document.getElementById("playhead");
  if (ph) ph.style.left = (player.currentTime / DATA.duration * 100) + "%";

  if (stopAtEnd && player.currentTime >= stopAtEnd.end) {
    player.pause();
    stopAtEnd = null;
  }

  if (preview) {
    var cur = bands[preview.idx];
    if (cur && player.currentTime >= cur.end) {
      preview.idx++;
      if (preview.idx >= bands.length) {
        player.pause();
        preview = null;
      } else {
        player.currentTime = bands[preview.idx].start;
      }
    }
  }
});

document.getElementById("tl").addEventListener("click", function (ev) {
  if (ev.target.classList.contains("band") || ev.target.classList.contains("label")) return;
  var rect = ev.currentTarget.getBoundingClientRect();
  var pct = (ev.clientX - rect.left) / rect.width;
  player.currentTime = Math.max(0, Math.min(DATA.duration, pct * DATA.duration));
});

document.getElementById("btn-preview").addEventListener("click", previewFinal);
document.getElementById("btn-add").addEventListener("click", addSegment);
document.getElementById("btn-export").addEventListener("click", exportJSON);
document.getElementById("btn-save").addEventListener("click", saveJSON);
document.getElementById("btn-set-start").addEventListener("click", setStart);
document.getElementById("btn-set-end").addEventListener("click", setEnd);
document.getElementById("btn-undo").addEventListener("click", popUndo);
document.getElementById("zoom-in").addEventListener("click", function () { setZoom(zoom * 2); });
document.getElementById("zoom-out").addEventListener("click", function () { setZoom(zoom / 2); });
document.getElementById("zoom-fit").addEventListener("click", function () { setZoom(1); });

document.getElementById("tl-scroller").addEventListener("wheel", function (ev) {
  if (!(ev.metaKey || ev.ctrlKey)) return;
  ev.preventDefault();
  var f = ev.deltaY < 0 ? 1.25 : 0.8;
  setZoom(zoom * f);
}, { passive: false });

document.addEventListener("keydown", function (ev) {
  if ((ev.metaKey || ev.ctrlKey) && ev.code === "KeyZ" && !ev.shiftKey) {
    ev.preventDefault();
    popUndo();
    return;
  }
  if ((ev.metaKey || ev.ctrlKey) && ev.code === "KeyS") {
    ev.preventDefault();
    saveJSON();
    return;
  }
  if ((ev.metaKey || ev.ctrlKey) && ev.code === "Comma") {
    ev.preventDefault();
    setStart();
    return;
  }
  if ((ev.metaKey || ev.ctrlKey) && ev.code === "Period") {
    ev.preventDefault();
    setEnd();
    return;
  }
  if (ev.target.tagName === "INPUT" || ev.target.tagName === "TEXTAREA") return;

  if (ev.code === "Space") {
    ev.preventDefault();
    if (player.paused) player.play(); else player.pause();
  } else if (ev.code === "ArrowLeft") {
    ev.preventDefault();
    player.currentTime = Math.max(0, player.currentTime - (ev.shiftKey ? 0.1 : 1));
  } else if (ev.code === "ArrowRight") {
    ev.preventDefault();
    player.currentTime = Math.min(DATA.duration, player.currentTime + (ev.shiftKey ? 0.1 : 1));
  } else if (ev.code === "KeyI") {
    setStart();
  } else if (ev.code === "KeyO") {
    setEnd();
  }
});

renderAll();
</script>
</body>
</html>
"""


def main():
    if len(sys.argv) != 5:
        _die()

    video_path = Path(sys.argv[1]).resolve()
    transcript = json.loads(Path(sys.argv[2]).read_text())
    cuts_input = json.loads(Path(sys.argv[3]).read_text())
    output_html = Path(sys.argv[4]).resolve()

    transcript_segments, transcript_rows = _collect_transcript(transcript)
    duration = _total_duration(transcript_segments)
    cuts = _coerce_segments(cuts_input)

    video_src = os.path.relpath(video_path, output_html.parent)

    data = {
        "source": str(video_path),
        "video_src": video_src,
        "duration": duration,
        "segments": cuts,
        "transcript": transcript_rows,
        "save_path": "tmp/%s_cuts.json" % video_path.stem,
    }

    html = PAGE_SHELL.replace("__DATA__", json.dumps(data))
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html)
    print("Wrote %s" % output_html)


if __name__ == "__main__":
    main()
