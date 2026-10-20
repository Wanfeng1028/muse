"""Render a declarative score against a project's timeline.

    python audio/render.py <projectDir> <score.py>

The score module declares EVENTS, BED, and SILENCE. Cue names are resolved
against <projectDir>/public/timeline.json at load time. A missing cue is an
error that names it.

Writes <projectDir>/audio/score_raw.wav, loudness-normalizes to
<projectDir>/public/score.wav at exactly total/fps seconds, re-zeroes every
silence window, and writes <projectDir>/audio/cues_report.txt.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from synth import SR, db, declick, drone, note_hz, place, reverb, tape

# Bus returns, matching the mix the droid film was balanced at.
ROOM_RETURN = 0.85
PLATE_RETURN = 0.9
BUS_DRIVE = 1.15
HEADROOM_DB = -8.0
END_FADE_S = 0.15
IN_FADE_S = 0.01


def load_timeline(project: Path):
    path = project / "public" / "timeline.json"
    with path.open("r", encoding="utf-8") as f:
        tl = json.load(f)
    fps = int(tl["fps"])
    total = int(tl["total"])
    scenes = []
    for s in tl["scenes"]:
        scenes.append({
            "id": s["id"],
            "from": int(s["from"]),
            "dur": int(s["dur"]),
            "name": s.get("name", s["id"]),
        })
    cues = tl["cues"]
    return fps, total, scenes, cues


def scene_index(scenes):
    return {s["id"]: s for s in scenes}


def cue_frame(cues, scene_id, spec):
    """Resolve a cue spec to a scene-local frame.

    spec is a name ('meterFull'), a name plus index ('chips[2]'), or an int
    frame offset. Raises KeyError naming the scene and the cue.
    """
    if isinstance(spec, int):
        return spec, str(spec)
    text = str(spec)
    name, index = text, None
    if text.endswith("]") and "[" in text:
        name, rest = text[:-1].split("[", 1)
        index = int(rest)
    scene_cues = cues.get(scene_id)
    if scene_cues is None or name not in scene_cues:
        known = sorted(scene_cues) if scene_cues else []
        raise KeyError(
            f"unknown cue {scene_id}.{text} "
            f"(scene cues: {', '.join(known) if known else 'scene not in timeline'})"
        )
    value = scene_cues[name]
    if index is None:
        if isinstance(value, list):
            raise KeyError(
                f"cue {scene_id}.{name} has {len(value)} frames; use {name}[0]..{name}[{len(value) - 1}]"
            )
        return int(value), name
    if not isinstance(value, list):
        raise KeyError(f"cue {scene_id}.{name} is a single frame, not a list; drop the index")
    if index < 0 or index >= len(value):
        raise KeyError(f"cue {scene_id}.{name}[{index}] is out of range (0..{len(value) - 1})")
    return int(value[index]), f"{name}[{index}]"


def abs_sample(scenes, fps, scene_id, frame):
    scene = scenes[scene_id]
    t = (scene["from"] + frame) / fps
    return int(round(t * SR)), t


def resolve_events(events, cues, scenes, fps):
    """Turn declarative events into placed voices. Validates every cue first.

    An optional trailing delay_s shifts a voice off its cue. A strum of five
    plucks on one cue uses 0, 0.035, 0.070. Two different voices on one cue
    stay together unless the score asks otherwise.
    """
    resolved = []
    for i, event in enumerate(events):
        try:
            scene_id, spec, fn, kwargs, bus, gain_db, pan, delay_s = _unpack(event)
        except ValueError as e:
            raise SystemExit(f"event {i}: {e}") from None
        try:
            frame, label = cue_frame(cues, scene_id, spec)
        except KeyError as e:
            raise SystemExit(f"event {i}: {e}") from None
        sample, t = abs_sample(scenes, fps, scene_id, frame)
        delay = int(round(delay_s * SR))
        resolved.append({
            "scene": scene_id,
            "label": f"{scene_id}.{label}",
            "frame": frame,
            "sample": sample + delay,
            # The report names the cue. A scrape 140 ms early is still chipLand,
            # and printing the shifted time makes the cue look wrong.
            "time": t,
            "delay": delay_s,
            "fn": fn,
            "kwargs": kwargs or {},
            "bus": bus,
            "gain": db(gain_db),
            "pan": pan,
        })
    resolved.sort(key=lambda e: (e["sample"], e["label"]))
    return resolved


def _unpack(event):
    if not isinstance(event, (tuple, list)) or len(event) < 3:
        raise ValueError("expected (scene, cue, fn, kwargs, bus, gain_db, pan, delay_s)")
    scene_id, spec, fn = event[0], event[1], event[2]
    kwargs = event[3] if len(event) > 3 else {}
    bus = event[4] if len(event) > 4 else "dry"
    gain_db = event[5] if len(event) > 5 else 0.0
    pan = event[6] if len(event) > 6 else 0.0
    delay_s = event[7] if len(event) > 7 else 0.0
    if bus not in ("dry", "room", "plate"):
        raise ValueError(f"bus must be dry, room, or plate, got {bus!r}")
    if not callable(fn):
        raise ValueError(f"sound for {scene_id}.{spec} is not callable")
    return scene_id, spec, fn, kwargs, bus, float(gain_db), float(pan), float(delay_s)


def bed_spans(bed, scenes, cues, fps, n, split_at=None):
    """One span per scene, in timeline order. A scene missing from `bed` is silent.

    split_at: optional {scene_id: cue_spec} to cut that scene's chord into two
    halves. The score then uses keys '<id>' and '<id>+' in `bed`.
    """
    spans = []
    for scene in scenes:
        sid = scene["id"]
        a = int(round(scene["from"] / fps * SR))
        b = int(round((scene["from"] + scene["dur"]) / fps * SR))
        b = min(b, n)
        cut = (split_at or {}).get(sid)
        if cut is not None:
            frame, _ = cue_frame(cues, sid, cut)
            mid, _ = abs_sample({sid: scene}, fps, sid, frame)
            spans.append((a, mid, sid))
            spans.append((mid, b, sid + "+"))
        else:
            spans.append((a, b, sid))
    return spans


def render_events(resolved, n, rng):
    dry = np.zeros((n, 2))
    room = np.zeros((n, 2))
    plate = np.zeros((n, 2))
    buses = {"dry": dry, "room": room, "plate": plate}
    rendered = []
    for e in resolved:
        audio = e["fn"](rng=rng, **e["kwargs"]) if _takes_rng(e["fn"]) else e["fn"](**e["kwargs"])
        if audio is not None:
            place(buses[e["bus"]], e["sample"], np.asarray(audio, dtype=np.float64),
                  gain=e["gain"], pan=e["pan"])
        rendered.append((e, audio))
    return dry, room, plate, rendered


def _takes_rng(fn):
    """A voice that accepts rng gets the score generator. Others are pure."""
    code = getattr(fn, "__code__", None)
    if code is None:
        return False
    return "rng" in code.co_varnames[:code.co_argcount + code.co_kwonlyargcount]


def zero_window(buf, a, b, fade):
    a = int(np.clip(a, 0, buf.shape[0]))
    b = int(np.clip(b, 0, buf.shape[0]))
    if fade > 0 and a - fade > 0:
        ramp = np.linspace(1.0, 0.0, fade)[:, None]
        buf[a - fade:a] *= ramp
    buf[a:b] = 0.0
    return a, b


def smooth_steps(bus, threshold=0.04):
    """Round isolated sample-to-sample steps. Those are what a 4x true-peak
    meter hears as overs after loudnorm raises the gain."""
    kernel = np.array([0.25, 0.5, 0.25])
    for _ in range(2):
        d = np.diff(bus, axis=0, prepend=bus[:1])
        steep = np.max(np.abs(d), axis=1) > threshold
        if not np.any(steep):
            return
        for ch in range(bus.shape[1]):
            smoothed = np.convolve(bus[:, ch], kernel, mode="same")
            bus[steep, ch] = smoothed[steep]


def write_wav_24(path, audio, sr=SR):
    audio = np.clip(np.asarray(audio, dtype=np.float64), -1.0, 1.0)
    if audio.ndim == 1:
        audio = np.column_stack([audio, audio])
    pcm = np.round(audio * (2 ** 23 - 1)).astype(np.int32)
    u = pcm.reshape(-1).view(np.uint32)
    b = np.empty(u.size * 3, dtype=np.uint8)
    b[0::3] = (u & 0xFF).astype(np.uint8)
    b[1::3] = ((u >> 8) & 0xFF).astype(np.uint8)
    b[2::3] = ((u >> 16) & 0xFF).astype(np.uint8)
    data = b.tobytes()
    channels = 2
    bits = 24
    block = channels * bits // 8
    import struct
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt " + struct.pack("<I", 16)
    header += struct.pack("<HHIIHH", 1, channels, sr, sr * block, block, bits)
    header += b"data" + struct.pack("<I", len(data))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(header)
        f.write(data)


def read_wav_f32(path):
    raw = subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path),
         "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
        capture_output=True,
    )
    if raw.returncode != 0:
        raise RuntimeError(raw.stderr.decode("utf-8", "replace")[-1000:])
    return np.frombuffer(raw.stdout, dtype=np.float32).reshape(-1, 2).astype(np.float64)


def loudnorm(src, dst):
    """Two-pass loudnorm, I=-14 LUFS, TP=-1 dBTP, linear gain."""
    p1 = subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-i", str(src),
         "-af", "loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    text = p1.stderr
    start, end = text.rfind("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError("loudnorm pass 1 returned no JSON:\n" + text[-1500:])
    measured = json.loads(text[start:end + 1])
    filt = (
        "loudnorm=I=-14:TP=-1.0:LRA=11:"
        f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true:print_format=summary"
    )
    p2 = subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-i", str(src), "-af", filt,
         "-ar", str(SR), "-c:a", "pcm_s24le", str(dst)],
        capture_output=True, text=True,
    )
    if p2.returncode != 0:
        raise RuntimeError("loudnorm pass 2 failed:\n" + p2.stderr[-1500:])
    return measured


def rezero(path, windows):
    """Force each [start, end) sample span to digital zero and rewrite."""
    audio = read_wav_f32(path)
    for a, b in windows:
        a = int(np.clip(a, 0, audio.shape[0]))
        b = int(np.clip(b, 0, audio.shape[0]))
        audio[a:b] = 0.0
    write_wav_24(path, audio, SR)
    return audio


def load_score(path: Path):
    spec = importlib.util.spec_from_file_location("score", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import score {path}")
    mod = importlib.util.module_from_spec(spec)
    # The score imports synth by name. Put this file's directory on the path.
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    spec.loader.exec_module(mod)
    return mod


def _silence_point(spec, cues, scenes, fps):
    """(scene, cue) or (scene, cue, frame_offset).

    The offset is for a hit that lives on the cue and must finish before the
    zero region opens. It is not a way to name an unlisted frame.
    """
    if not isinstance(spec, (tuple, list)) or len(spec) not in (2, 3):
        raise SystemExit(f"silence point must be (scene, cue) or (scene, cue, offset), got {spec!r}")
    sid, cue = spec[0], spec[1]
    offset = int(spec[2]) if len(spec) == 3 else 0
    try:
        frame, label = cue_frame(cues, sid, cue)
    except KeyError as e:
        raise SystemExit(f"silence window: {e}") from None
    sample, t = abs_sample(scenes, fps, sid, frame + offset)
    shown = f"{sid}.{label}" + (f"{offset:+d}f" if offset else "")
    return sample, t, shown


def silence_windows(specs, cues, scenes, fps):
    """(scene, start_cue, end_cue), same scene.

    Or a pair of points, (scene, cue) or (scene, cue, frame_offset), when the
    window crosses a scene boundary or must open after a short hit on the cue.
    """
    windows = []
    for spec in specs:
        if (
            isinstance(spec, (tuple, list)) and len(spec) == 3
            and isinstance(spec[0], str) and not isinstance(spec[1], (tuple, list))
        ):
            start = (spec[0], spec[1])
            end = (spec[0], spec[2])
        elif isinstance(spec, (tuple, list)) and len(spec) == 2:
            start, end = spec
        else:
            raise SystemExit(
                f"SILENCE entry must be (scene, start_cue, end_cue) "
                f"or ((scene, cue), (scene, cue)), got {spec!r}"
            )
        a, ta, la = _silence_point(start, cues, scenes, fps)
        b, tb, lb = _silence_point(end, cues, scenes, fps)
        if b < a:
            raise SystemExit(f"silence window {la} .. {lb} ends before it starts")
        windows.append((a, b, ta, tb, f"{la} .. {lb}"))
    return windows


def write_report(path, resolved, windows, audio, duration, seed, bed):
    lines = [
        f"sr={SR} duration={duration:.3f}s channels=2 seed={seed}",
        "",
    ]
    for a, b, ta, tb, label in windows:
        sl = audio[a:b]
        maxabs = float(np.max(np.abs(sl))) if sl.size else 0.0
        lines.append(
            f"silence {label}: {ta:.4f}s .. {tb:.4f}s "
            f"(samples {a}:{b}) maxabs={maxabs:.3e}"
        )
    lines.append("")
    lines.append(f"{'time':>8}  {'cue':<24} {'frame':>6}  bus  gain_db  pan")
    for e, _audio in resolved:
        delay = e["delay"]
        extra = f"  {delay:+.3f}s" if delay else ""
        lines.append(
            f"{e['time']:8.4f}  {e['label']:<24} {e['frame']:6d}  "
            f"{e['bus']:<5} {20 * np.log10(max(e['gain'], 1e-9)):7.2f}  {e['pan']:+.2f}{extra}"
        )
    if bed:
        lines.append("")
        lines.append("bed:")
        for sid, notes in bed.items():
            shown = ", ".join(_fmt_note(n) for n in notes) if notes else "none"
            lines.append(f"  {sid}  {shown}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt_note(item):
    from synth import note_name
    return note_name(item)


def render(project: Path, score_path: Path):
    t0 = time.perf_counter()
    project = project.resolve()
    score = load_score(score_path.resolve())
    fps, total, scenes, cues = load_timeline(project)
    by_id = scene_index(scenes)
    duration = total / fps
    n = int(round(duration * SR))

    events = getattr(score, "EVENTS", [])
    bed = getattr(score, "BED", {})
    silence = getattr(score, "SILENCE", [])
    seed = int(getattr(score, "SEED", 1))
    split_at = getattr(score, "BED_SPLIT", None)

    resolved = resolve_events(events, cues, by_id, fps)
    windows = silence_windows(silence, cues, by_id, fps)

    rng = np.random.default_rng(seed)
    dry, room_send, plate_send, rendered = render_events(resolved, n, rng)

    spans = bed_spans(bed, scenes, cues, fps, n, split_at=split_at)
    if bed:
        dry += drone(bed, spans, n)

    room = reverb(room_send, "room") if np.any(room_send) else np.zeros((n, 2))
    plate = reverb(plate_send, "plate") if np.any(plate_send) else np.zeros((n, 2))
    bus = dry + room * ROOM_RETURN + plate * PLATE_RETURN
    bus = tape(bus, BUS_DRIVE)

    end_fade = min(n, int(END_FADE_S * SR))
    if end_fade > 1:
        bus[-end_fade:] *= np.linspace(1.0, 0.0, end_fade)[:, None]
    in_fade = min(n, int(IN_FADE_S * SR))
    if in_fade > 1:
        bus[:in_fade] *= np.linspace(0.0, 1.0, in_fade)[:, None]

    smooth_steps(bus)

    peak = float(np.max(np.abs(bus))) if bus.size else 0.0
    if peak > 0:
        bus *= min(1.0, db(HEADROOM_DB) / peak)

    # Fade into each silence window so the cut is not a tick, then zero it.
    # The window itself stays digital zero through loudnorm (re-zeroed after).
    fade = int(0.02 * SR)
    for a, b, *_ in windows:
        zero_window(bus, a, b, fade)

    audio_dir = project / "audio"
    raw = audio_dir / "score_raw.wav"
    out = project / "public" / "score.wav"
    report = audio_dir / "cues_report.txt"
    write_wav_24(raw, bus, SR)

    out.parent.mkdir(parents=True, exist_ok=True)
    loudnorm(raw, out)
    final = rezero(out, [(a, b) for a, b, *_ in windows])
    if final.shape[0] != n:
        raise SystemExit(
            f"normalized length {final.shape[0]} samples, expected {n} "
            f"({duration:.3f}s at {SR} Hz)"
        )
    write_report(report, [(e, a) for e, a in rendered], windows, final, duration, seed, bed)

    elapsed = time.perf_counter() - t0
    print(f"wrote {raw}")
    print(f"wrote {out}  ({n} samples, {duration:.3f}s)")
    print(f"wrote {report}")
    print(f"render {elapsed:.2f}s")
    return elapsed


def main(argv):
    if len(argv) != 3:
        raise SystemExit("usage: python audio/render.py <projectDir> <score.py>")
    render(Path(argv[1]), Path(argv[2]))


if __name__ == "__main__":
    main(sys.argv)
