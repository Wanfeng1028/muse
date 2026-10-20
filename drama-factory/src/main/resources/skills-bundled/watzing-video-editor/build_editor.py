#!/usr/bin/env python3
"""Generate a static HTML editor page for adjusting video cut points.

Usage:
    python3 build_editor.py <video_path> <transcript_json> <cuts_json> <output_html>

The output is a single self-contained HTML file with the video, transcript, and
proposed segments embedded. Open it in a browser, adjust segment start/end times
visually, then click "Export cuts.json" to download the updated cut list.
"""
import json
import os
import sys
from pathlib import Path

if len(sys.argv) != 5:
    print(__doc__, file=sys.stderr)
    sys.exit(1)

video_path = Path(sys.argv[1]).resolve()
transcript = json.loads(Path(sys.argv[2]).read_text())
cuts_input = json.loads(Path(sys.argv[3]).read_text())
output_html = Path(sys.argv[4]).resolve()

video_src = os.path.relpath(video_path, output_html.parent)
segments = transcript.get("segments", [])
duration = max((s.get("end", 0) for s in segments), default=0)

cuts_list = cuts_input.get("segments", cuts_input) if isinstance(cuts_input, dict) else cuts_input

data = {
    "source": str(video_path),
    "video_src": video_src,
    "duration": duration,
    "segments": [{"start": float(c["start"]), "end": float(c["end"])} for c in cuts_list],
    "transcript": [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segments],
    # Save endpoint writes the cuts back to this path (relative to project root)
    "save_path": f"tmp/{video_path.stem}_cuts.json",
}

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Video Editor</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, system-ui, sans-serif; margin: 0; background: #0e0e0e; color: #e0e0e0; font-size: 14px; }
  header { padding: 12px 20px; background: #1a1a1a; border-bottom: 1px solid #2a2a2a; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
  header h1 { margin: 0; font-size: 16px; font-weight: 500; }
  .stats { color: #888; font-size: 12px; }
  .stats span { color: #4caf50; font-family: monospace; }
  main { padding: 20px; max-width: 1400px; margin: 0 auto; }

  video { width: 100%; max-height: 50vh; background: black; border-radius: 4px; display: block; }

  .timeline-wrap { margin: 20px 0; }
  .timeline-scroll {
    overflow-x: auto; overflow-y: hidden;
    background: #1a1a1a; border-radius: 4px;
  }
  .timeline-scroll::-webkit-scrollbar { height: 10px; }
  .timeline-scroll::-webkit-scrollbar-track { background: #0e0e0e; }
  .timeline-scroll::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
  .timeline {
    position: relative; height: 56px;
    cursor: pointer; user-select: none;
    /* width set via JS based on zoom */
  }
  .keep-band {
    position: absolute; top: 6px; bottom: 18px;
    background: rgba(76, 175, 80, 0.35);
    border: 1px solid #4caf50;
    border-radius: 3px; cursor: grab;
  }
  .keep-band:active { cursor: grabbing; }
  .keep-band:hover { background: rgba(76, 175, 80, 0.55); }
  .keep-band.selected { background: rgba(255, 152, 0, 0.45); border-color: #ff9800; }
  .keep-band-label {
    position: absolute; top: 1px; left: 10px; font-size: 10px; color: white;
    text-shadow: 0 1px 2px rgba(0,0,0,0.8); pointer-events: none; font-weight: 600;
  }
  .resize-handle {
    position: absolute; top: 0; bottom: 0; width: 8px;
    cursor: ew-resize; background: rgba(255,255,255,0.0);
  }
  .resize-handle:hover { background: rgba(255,255,255,0.25); }
  .resize-handle.left { left: 0; border-radius: 3px 0 0 3px; }
  .resize-handle.right { right: 0; border-radius: 0 3px 3px 0; }
  .playhead {
    position: absolute; top: 0; bottom: 0; width: 2px;
    background: #ff5722; pointer-events: none; z-index: 10;
  }
  .timeline-tick { position: absolute; top: 0; bottom: 14px; width: 1px; background: #2a2a2a; }
  .timeline-tick-label {
    position: absolute; bottom: 1px; font-size: 9px; color: #555;
    font-family: monospace; transform: translateX(2px);
  }
  .timeline-toolbar {
    display: flex; align-items: center; justify-content: space-between;
    margin-top: 6px; gap: 12px; flex-wrap: wrap;
  }
  .help { color: #555; font-size: 11px; }
  .zoom-controls { display: flex; align-items: center; gap: 4px; }
  .zoom-controls button {
    padding: 4px 10px; font-size: 13px; min-width: 30px;
  }
  .zoom-level { color: #888; font-family: monospace; font-size: 11px; min-width: 50px; text-align: center; }

  .controls { display: flex; gap: 8px; margin: 16px 0; flex-wrap: wrap; align-items: center; }
  button {
    background: #2a2a2a; color: #e0e0e0; border: 1px solid #3a3a3a;
    padding: 8px 14px; border-radius: 4px; cursor: pointer;
    font-size: 13px; font-family: inherit;
  }
  button:hover { background: #3a3a3a; }
  button.primary { background: #2e7d32; border-color: #4caf50; color: white; }
  button.primary:hover { background: #388e3c; }
  button.danger { background: transparent; border-color: #d32f2f; color: #ef5350; padding: 4px 8px; font-size: 12px; }
  button.danger:hover { background: rgba(211, 47, 47, 0.15); }

  .segments { background: #1a1a1a; border-radius: 4px; overflow: hidden; }
  .segment {
    display: grid;
    grid-template-columns: 32px 110px 110px 70px 1fr 80px 32px;
    gap: 10px; padding: 10px 14px; align-items: center;
    border-bottom: 1px solid #232323;
  }
  .segment:last-child { border-bottom: none; }
  .segment.selected { background: rgba(255, 152, 0, 0.08); }
  .segment.playing { background: rgba(76, 175, 80, 0.1); }
  .seg-num { font-weight: 600; color: #4caf50; font-family: monospace; text-align: center; }
  .seg-time {
    background: #0e0e0e; color: #e0e0e0;
    border: 1px solid #2a2a2a; padding: 6px 8px; border-radius: 3px;
    font-family: monospace; font-size: 13px; width: 100%;
  }
  .seg-time:focus { outline: none; border-color: #4caf50; }
  .seg-dur { color: #888; font-family: monospace; font-size: 12px; text-align: right; }
  .seg-text { color: #888; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .transcript {
    margin-top: 24px; padding: 16px 20px; background: #1a1a1a;
    border-radius: 4px; font-size: 13px; line-height: 1.8;
    max-height: 320px; overflow-y: auto;
  }
  .ts-segment { display: inline; }
  .ts-time { color: #555; font-family: monospace; font-size: 11px; margin-right: 4px; }
  .ts-segment.in-keep .ts-text { color: #4caf50; }
  .ts-segment.out-keep .ts-text { color: #666; }
  .ts-text { cursor: pointer; padding: 0 2px; border-radius: 2px; }
  .ts-text:hover { background: rgba(255,255,255,0.1); }

  .toast {
    position: fixed; bottom: 24px; right: 24px;
    background: #2e7d32; color: white; padding: 12px 20px;
    border-radius: 4px; opacity: 0; transition: opacity 0.3s;
    pointer-events: none; z-index: 100;
  }
  .toast.show { opacity: 1; }
  .kbd-help { color: #555; font-size: 11px; margin-left: auto; }
  .kbd-help code { background: #2a2a2a; padding: 1px 5px; border-radius: 2px; color: #aaa; font-size: 11px; }
</style>
</head>
<body>
<header>
  <h1 id="title">Video Editor</h1>
  <div class="stats">
    Source: <span id="src-dur">--</span> &middot; Kept: <span id="kept-dur">--</span> (<span id="kept-pct">--</span>) &middot; Segments: <span id="seg-count">--</span>
  </div>
</header>
<main>
  <video id="player" controls></video>

  <div class="timeline-wrap">
    <div class="timeline-scroll" id="timeline-scroll">
      <div class="timeline" id="timeline"></div>
    </div>
    <div class="timeline-toolbar">
      <div class="help">Drag a band to move it. Drag its left/right edge to resize. Click empty area to seek.</div>
      <div class="zoom-controls">
        <button id="zoom-out" title="Zoom out">&minus;</button>
        <span class="zoom-level" id="zoom-level">100%</span>
        <button id="zoom-in" title="Zoom in">+</button>
        <button id="zoom-reset" title="Fit to window">Fit</button>
      </div>
    </div>
  </div>

  <div class="controls">
    <button class="primary" id="preview-final">&#9654; Preview Final</button>
    <button id="add-segment">+ Add segment at current time</button>
    <button id="set-start">Set selected start = current time</button>
    <button id="set-end">Set selected end = current time</button>
    <button id="undo" disabled>&#x21A9; Undo</button>
    <button class="primary" id="save" style="margin-left: auto;">&#x1F4BE; Save</button>
    <button id="export" title="Download as file (no server needed)">&#x2B07; Export</button>
  </div>
  <div class="kbd-help">
    Keys: <code>Space</code> play/pause &middot; <code>&larr;</code>/<code>&rarr;</code> seek 1s (Shift = 0.1s) &middot;
    <code>I</code> or <code>&#8984;&lt;</code> set start &middot; <code>O</code> or <code>&#8984;&gt;</code> set end &middot;
    <code>&#8984;Z</code> undo &middot; <code>&#8984;S</code> save &middot; <code>&#8984;</code>+scroll to zoom
  </div>

  <div class="segments" id="segments" style="margin-top: 12px;"></div>

  <div class="transcript" id="transcript"></div>
</main>
<div class="toast" id="toast"></div>
<script>
const DATA = __DATA__;

let segments = DATA.segments.map(function(s) { return { start: +s.start, end: +s.end }; });
let selectedIdx = -1;
let previewQueue = null;
let segmentEndStop = null;
let history = [];
let zoomLevel = 1;
let dragState = null;
const HISTORY_MAX = 100;
const MIN_SEG_DUR = 0.05;

function snapshot() {
  history.push({
    segments: segments.map(function(s) { return { start: s.start, end: s.end }; }),
    selectedIdx: selectedIdx
  });
  if (history.length > HISTORY_MAX) history.shift();
  updateUndoButton();
}

function undo() {
  if (history.length === 0) return;
  const prev = history.pop();
  segments = prev.segments.map(function(s) { return { start: s.start, end: s.end }; });
  selectedIdx = prev.selectedIdx;
  updateUndoButton();
  renderAll();
  showToast('Undone (' + history.length + ' more)');
}

function updateUndoButton() {
  const btn = document.getElementById('undo');
  if (btn) btn.disabled = history.length === 0;
}

const player = document.getElementById('player');
player.src = DATA.video_src;

const fmt = function(s) {
  if (isNaN(s) || s === null) return '--:--';
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(2);
  return m + ':' + (sec.length < 5 ? '0' + sec : sec);
};

const sortSegs = function() { segments.sort(function(a, b) { return a.start - b.start; }); };

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function() { t.classList.remove('show'); }, 2000);
}

function totalKept() {
  return segments.reduce(function(sum, s) { return sum + Math.max(0, s.end - s.start); }, 0);
}

function findText(start, end) {
  return DATA.transcript
    .filter(function(t) { return t.end > start && t.start < end; })
    .map(function(t) { return t.text.trim(); })
    .join(' ')
    .slice(0, 200);
}

function renderStats() {
  document.getElementById('src-dur').textContent = fmt(DATA.duration);
  const kept = totalKept();
  document.getElementById('kept-dur').textContent = fmt(kept);
  document.getElementById('kept-pct').textContent = (kept / DATA.duration * 100).toFixed(0) + '%';
  document.getElementById('seg-count').textContent = segments.length;
  document.getElementById('title').textContent = 'Video Editor — ' + DATA.source.split('/').pop();
}

function renderTimeline() {
  const tl = document.getElementById('timeline');
  tl.style.width = (zoomLevel * 100) + '%';
  tl.innerHTML = '';

  // Tick density scales with zoom so labels stay readable
  const baseInterval = DATA.duration > 600 ? 60 : (DATA.duration > 120 ? 30 : 10);
  const tickInterval = Math.max(1, baseInterval / Math.pow(2, Math.floor(Math.log2(zoomLevel))));
  for (let t = 0; t <= DATA.duration; t += tickInterval) {
    const tick = document.createElement('div');
    tick.className = 'timeline-tick';
    tick.style.left = (t / DATA.duration * 100) + '%';
    tl.appendChild(tick);
    const label = document.createElement('div');
    label.className = 'timeline-tick-label';
    label.style.left = (t / DATA.duration * 100) + '%';
    const m = Math.floor(t / 60), sec = Math.floor(t % 60);
    label.textContent = m + ':' + (sec < 10 ? '0' + sec : sec);
    tl.appendChild(label);
  }

  segments.forEach(function(seg, i) {
    const band = document.createElement('div');
    band.className = 'keep-band' + (i === selectedIdx ? ' selected' : '');
    band.style.left = (seg.start / DATA.duration * 100) + '%';
    band.style.width = ((seg.end - seg.start) / DATA.duration * 100) + '%';
    band.dataset.idx = i;

    const leftHandle = document.createElement('div');
    leftHandle.className = 'resize-handle left';
    const rightHandle = document.createElement('div');
    rightHandle.className = 'resize-handle right';
    const label = document.createElement('div');
    label.className = 'keep-band-label';
    label.textContent = i + 1;
    band.appendChild(leftHandle);
    band.appendChild(rightHandle);
    band.appendChild(label);

    band.addEventListener('mousedown', function(e) {
      if (e.button !== 0) return;
      let type = 'move';
      if (e.target === leftHandle) type = 'start';
      else if (e.target === rightHandle) type = 'end';
      dragState = {
        type: type, idx: i,
        startX: e.clientX,
        startSeg: { start: seg.start, end: seg.end },
        innerWidth: tl.offsetWidth,
        moved: false,
        snapshotTaken: false
      };
      e.preventDefault();
      e.stopPropagation();
    });
    // Block the click event from reaching the timeline's seek handler —
    // covers the band body, the label, and both resize handles.
    band.addEventListener('click', function(e) { e.stopPropagation(); });

    tl.appendChild(band);
  });

  const ph = document.createElement('div');
  ph.className = 'playhead';
  ph.id = 'playhead';
  ph.style.left = (player.currentTime / DATA.duration * 100) + '%';
  tl.appendChild(ph);
}

function renderSegments() {
  const container = document.getElementById('segments');
  container.innerHTML = '';
  segments.forEach(function(seg, i) {
    const dur = seg.end - seg.start;
    const text = findText(seg.start, seg.end);
    const div = document.createElement('div');
    div.className = 'segment' + (i === selectedIdx ? ' selected' : '');
    div.innerHTML =
      '<div class="seg-num">' + (i + 1) + '</div>' +
      '<input class="seg-time" data-field="start" data-idx="' + i + '" value="' + seg.start.toFixed(2) + '">' +
      '<input class="seg-time" data-field="end" data-idx="' + i + '" value="' + seg.end.toFixed(2) + '">' +
      '<div class="seg-dur">' + dur.toFixed(2) + 's</div>' +
      '<div class="seg-text" title="' + text.replace(/"/g, '&quot;') + '">' + (text || '&mdash;') + '</div>' +
      '<button data-action="play" data-idx="' + i + '">&#9654; Play</button>' +
      '<button class="danger" data-action="delete" data-idx="' + i + '">&#x2715;</button>';
    container.appendChild(div);
  });

  container.querySelectorAll('input.seg-time').forEach(function(inp) {
    inp.addEventListener('change', function(e) {
      const idx = +e.target.dataset.idx;
      const field = e.target.dataset.field;
      const val = parseFloat(e.target.value);
      if (!isNaN(val) && segments[idx][field] !== val) {
        snapshot();
        segments[idx][field] = val;
        sortSegs();
        renderAll();
      }
    });
    inp.addEventListener('focus', function(e) {
      selectSegment(+e.target.dataset.idx);
    });
  });

  container.querySelectorAll('button[data-action]').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      const idx = +e.target.dataset.idx;
      const action = e.target.dataset.action;
      if (action === 'play') playSegment(idx);
      else if (action === 'delete') deleteSegment(idx);
    });
  });
}

function renderTranscript() {
  const container = document.getElementById('transcript');
  container.innerHTML = '';
  DATA.transcript.forEach(function(t) {
    const inKeep = segments.some(function(s) { return t.end > s.start && t.start < s.end; });
    const span = document.createElement('span');
    span.className = 'ts-segment ' + (inKeep ? 'in-keep' : 'out-keep');
    const m = Math.floor(t.start / 60), sec = Math.floor(t.start % 60);
    const tStr = m + ':' + (sec < 10 ? '0' + sec : sec);
    span.innerHTML = '<span class="ts-time">[' + tStr + ']</span><span class="ts-text"> ' + t.text.trim() + '</span> ';
    span.querySelector('.ts-text').addEventListener('click', function() {
      player.currentTime = t.start;
      player.play();
    });
    container.appendChild(span);
  });
}

function renderAll() { renderStats(); renderTimeline(); renderSegments(); renderTranscript(); }

function selectSegment(i) { selectedIdx = i; renderTimeline(); renderSegments(); }

function playSegment(idx) {
  selectSegment(idx);
  const seg = segments[idx];
  player.currentTime = seg.start;
  segmentEndStop = { endTime: seg.end };
  previewQueue = null;
  player.play();
}

function deleteSegment(idx) {
  if (!confirm('Delete segment ' + (idx + 1) + '?')) return;
  snapshot();
  segments.splice(idx, 1);
  if (selectedIdx === idx) selectedIdx = -1;
  else if (selectedIdx > idx) selectedIdx--;
  renderAll();
}

function addSegment() {
  snapshot();
  const t = player.currentTime;
  const newSeg = { start: Math.max(0, t - 1), end: Math.min(DATA.duration, t + 1) };
  segments.push(newSeg);
  sortSegs();
  selectedIdx = segments.indexOf(newSeg);
  renderAll();
}

function setSelectedStart() {
  if (selectedIdx < 0) { showToast('Select a segment first'); return; }
  const v = +player.currentTime.toFixed(2);
  if (segments[selectedIdx].start === v) return;
  snapshot();
  segments[selectedIdx].start = v;
  sortSegs(); renderAll();
}

function setSelectedEnd() {
  if (selectedIdx < 0) { showToast('Select a segment first'); return; }
  const v = +player.currentTime.toFixed(2);
  if (segments[selectedIdx].end === v) return;
  snapshot();
  segments[selectedIdx].end = v;
  sortSegs(); renderAll();
}

function previewFinal() {
  if (segments.length === 0) return;
  sortSegs();
  previewQueue = { idx: 0 };
  segmentEndStop = null;
  player.currentTime = segments[0].start;
  player.play();
}

function buildCutsPayload() {
  sortSegs();
  return {
    source: DATA.source,
    duration: DATA.duration,
    segments: segments.map(function(s) {
      return { start: +s.start.toFixed(2), end: +s.end.toFixed(2) };
    })
  };
}

function exportJSON() {
  const out = buildCutsPayload();
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = DATA.source.split('/').pop().replace(/\.[^.]+$/, '') + '_cuts.json';
  a.click();
  URL.revokeObjectURL(url);
  showToast('Exported ' + a.download);
}

function saveJSON() {
  const out = buildCutsPayload();
  fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: DATA.save_path, data: out })
  }).then(function(r) {
    if (!r.ok) return r.text().then(function(t) { throw new Error(t || ('HTTP ' + r.status)); });
    return r.json();
  }).then(function(j) {
    showToast('Saved to ' + (j.path || DATA.save_path));
  }).catch(function(err) {
    showToast('Save failed: ' + err.message + ' (try Export instead)');
  });
}

function setZoom(z) {
  zoomLevel = Math.max(1, Math.min(32, z));
  document.getElementById('zoom-level').textContent = Math.round(zoomLevel * 100) + '%';
  renderTimeline();
}

function applyDrag(e) {
  if (!dragState) return;
  const dx = e.clientX - dragState.startX;
  if (!dragState.moved && Math.abs(dx) < 3) return;
  if (!dragState.moved) {
    dragState.moved = true;
    if (!dragState.snapshotTaken) { snapshot(); dragState.snapshotTaken = true; }
  }
  const dt = (dx / dragState.innerWidth) * DATA.duration;
  const orig = dragState.startSeg;
  const seg = segments[dragState.idx];
  if (dragState.type === 'move') {
    const dur = orig.end - orig.start;
    let newStart = Math.max(0, Math.min(DATA.duration - dur, orig.start + dt));
    seg.start = newStart;
    seg.end = newStart + dur;
  } else if (dragState.type === 'start') {
    seg.start = Math.max(0, Math.min(orig.end - MIN_SEG_DUR, orig.start + dt));
  } else if (dragState.type === 'end') {
    seg.end = Math.max(orig.start + MIN_SEG_DUR, Math.min(DATA.duration, orig.end + dt));
  }
  renderTimeline();
  // update only this row's input fields without rebuilding the whole list
  const sList = document.getElementById('segments');
  const startInput = sList.querySelector('input[data-field="start"][data-idx="' + dragState.idx + '"]');
  const endInput = sList.querySelector('input[data-field="end"][data-idx="' + dragState.idx + '"]');
  if (startInput) startInput.value = seg.start.toFixed(2);
  if (endInput) endInput.value = seg.end.toFixed(2);
}

function endDrag() {
  if (!dragState) return;
  const wasMove = dragState.moved;
  const idx = dragState.idx;
  dragState = null;
  if (!wasMove) {
    // Treat as click: select + play the segment (auto-pauses at its end)
    playSegment(idx);
  } else {
    sortSegs();
    renderAll();
  }
}

window.addEventListener('mousemove', applyDrag);
window.addEventListener('mouseup', endDrag);

player.addEventListener('timeupdate', function() {
  const ph = document.getElementById('playhead');
  if (ph) ph.style.left = (player.currentTime / DATA.duration * 100) + '%';

  if (segmentEndStop && player.currentTime >= segmentEndStop.endTime) {
    player.pause();
    segmentEndStop = null;
  }

  if (previewQueue) {
    const cur = segments[previewQueue.idx];
    if (cur && player.currentTime >= cur.end) {
      previewQueue.idx++;
      if (previewQueue.idx >= segments.length) {
        player.pause();
        previewQueue = null;
      } else {
        player.currentTime = segments[previewQueue.idx].start;
      }
    }
  }
});

document.getElementById('timeline').addEventListener('click', function(e) {
  if (e.target.classList.contains('keep-band') || e.target.classList.contains('keep-band-label')) return;
  const rect = e.currentTarget.getBoundingClientRect();
  const pct = (e.clientX - rect.left) / rect.width;
  player.currentTime = Math.max(0, Math.min(DATA.duration, pct * DATA.duration));
});

document.getElementById('preview-final').addEventListener('click', previewFinal);
document.getElementById('add-segment').addEventListener('click', addSegment);
document.getElementById('export').addEventListener('click', exportJSON);
document.getElementById('save').addEventListener('click', saveJSON);
document.getElementById('set-start').addEventListener('click', setSelectedStart);
document.getElementById('set-end').addEventListener('click', setSelectedEnd);
document.getElementById('undo').addEventListener('click', undo);
document.getElementById('zoom-in').addEventListener('click', function() { setZoom(zoomLevel * 2); });
document.getElementById('zoom-out').addEventListener('click', function() { setZoom(zoomLevel / 2); });
document.getElementById('zoom-reset').addEventListener('click', function() { setZoom(1); });

// Cmd/Ctrl + scroll on timeline to zoom
document.getElementById('timeline-scroll').addEventListener('wheel', function(e) {
  if (!(e.metaKey || e.ctrlKey)) return;
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.25 : 0.8;
  setZoom(zoomLevel * factor);
}, { passive: false });

document.addEventListener('keydown', function(e) {
  // Undo works even from inputs
  if ((e.metaKey || e.ctrlKey) && e.code === 'KeyZ' && !e.shiftKey) {
    e.preventDefault();
    undo();
    return;
  }
  // Save
  if ((e.metaKey || e.ctrlKey) && e.code === 'KeyS') {
    e.preventDefault();
    saveJSON();
    return;
  }
  // Set selected segment start/end to current playhead (Cmd/Ctrl + < or >)
  if ((e.metaKey || e.ctrlKey) && e.code === 'Comma') {
    e.preventDefault();
    setSelectedStart();
    return;
  }
  if ((e.metaKey || e.ctrlKey) && e.code === 'Period') {
    e.preventDefault();
    setSelectedEnd();
    return;
  }
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.code === 'Space') { e.preventDefault(); player.paused ? player.play() : player.pause(); }
  else if (e.code === 'ArrowLeft') { e.preventDefault(); player.currentTime = Math.max(0, player.currentTime - (e.shiftKey ? 0.1 : 1)); }
  else if (e.code === 'ArrowRight') { e.preventDefault(); player.currentTime = Math.min(DATA.duration, player.currentTime + (e.shiftKey ? 0.1 : 1)); }
  else if (e.code === 'KeyI') setSelectedStart();
  else if (e.code === 'KeyO') setSelectedEnd();
});

renderAll();
</script>
</body>
</html>
"""

html = TEMPLATE.replace("__DATA__", json.dumps(data))
output_html.parent.mkdir(parents=True, exist_ok=True)
output_html.write_text(html)
print(f"Wrote {output_html}")
