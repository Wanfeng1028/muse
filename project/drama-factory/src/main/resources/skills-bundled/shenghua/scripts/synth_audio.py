#!/usr/bin/env python3
"""Synthesize the sound design for a composition.

  synth_audio.py <cues.json> <duration> <work-dir> [--template ID] [--drop T] [--quiet A:B] [--no-music]
                 [--stop A:B] [--muffle A:B] [--stutter A:B]

Writes sfx.wav (every cue the timeline pushed) and music.wav (the theme's pad, bass, pluck and
pulse layers at its own tempo and key, drums from --drums-from onward). The chord order and pluck
pattern vary per video (the slug folder above work/). Without a kit audio block everything is generated
here, so there is nothing to license.

A work dir that is a chapter in ../../chapters.json (long form) gets its slice of one continuous bed: seeded
from the project, offset by the earlier chapters' durations, faded in only in the first chapter and out only
in the last, at one level across chapters, so the music runs on across every join.

The kit's audio block (work/kit/kit.json, installed by fill_template.py) can swap any cue for recorded
files, change its gain or mute it, replace the synth music with a track or none, and set the mix
levels. mix.json records those levels and the music file for mix-encode.sh and render-chunks.sh;
when work/words.js exists, pauses between words of DUCK_GAP_MIN or longer are recorded in its duck
array, so mix-audio.sh can swell the music into them.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000
LOOP_FADE = 2.0
# A pause this long between words is a breath the music can swell into (mix.json's duck array)
DUCK_GAP_MIN = 0.6
TEMPLATES_JSON = Path(__file__).resolve().parent.parent / "templates" / "templates.json"
rng = np.random.default_rng(7)


def t_axis(seconds):
    return np.arange(int(SR * seconds)) / SR


def smooth(x, width):
    return np.convolve(x, np.ones(width) / width, mode="same")


def envelope(n, attack, release):
    env = np.ones(n)
    a, r = max(1, int(SR * attack)), max(1, int(SR * release))
    env[:a] = np.linspace(0, 1, a)
    env[-r:] *= np.exp(-np.linspace(0, 6, r))
    return env


def note(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def place(buffer, sound, at, origin=0):
    # origin: the buffer's first sample on a longer clock, so a slice of the music bed places notes on the same samples as the whole
    start = int(at * SR) - origin
    if start < 0:
        sound, start = sound[-start:], 0
    if start >= len(buffer):
        return
    end = min(len(buffer), start + len(sound))
    buffer[start:end] += sound[: end - start]


def hit(power):
    t = t_axis(0.9)
    body = np.sin(2 * np.pi * np.cumsum(38 + 90 * np.exp(-t * 28)) / SR) * np.exp(-t * 5.5)
    click = rng.standard_normal(len(t)) * np.exp(-t * 60) * 0.5
    boom = smooth(rng.standard_normal(len(t)), 40) * np.exp(-t * 3) * 0.6
    return (body * 0.9 + click + boom) * 0.55 * power


def whoosh():
    t = t_axis(0.45)
    noise = rng.standard_normal(len(t))
    return (smooth(noise, 6) - smooth(noise, 60)) * np.sin(np.pi * t / t[-1]) ** 2 * 0.35


def riser(duration):
    t = t_axis(duration)
    k = t / duration
    noise = rng.standard_normal(len(t))
    tone = np.sin(2 * np.pi * np.cumsum(180 + 900 * k ** 2) / SR)
    return ((noise - smooth(noise, 45)) * 0.12 + tone * 0.08) * k ** 2


def down(duration):
    t = t_axis(duration)
    k = t / duration
    tone = np.sin(2 * np.pi * np.cumsum(700 * (1 - k) + 60) / SR)
    return tone * 0.12 * (1 - k) * np.sin(np.pi * np.minimum(k * 8, 1) / 2)


def repeated(sound, duration, interval, jitter):
    out = np.zeros(int(SR * duration) + SR // 10)
    position = 0.0
    while position < duration:
        place(out, sound() * (0.6 + 0.4 * rng.random()), position)
        position += interval + jitter * rng.random()
    return out


def key_click():
    t = t_axis(0.03)
    return rng.standard_normal(len(t)) * np.exp(-t * 250) * 0.12


def tick():
    t = t_axis(0.04)
    return np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 120) * 0.08


def pop():
    t = t_axis(0.12)
    return np.sin(2 * np.pi * np.cumsum(500 + 900 * np.exp(-t * 40)) / SR) * np.exp(-t * 35) * 0.12


def ding():
    t = t_axis(0.6)
    return (np.sin(2 * np.pi * 1318 * t) + 0.5 * np.sin(2 * np.pi * 1975 * t)) * np.exp(-t * 8) * 0.07


def stamp():
    t = t_axis(0.35)
    return smooth(rng.standard_normal(len(t)), 25) * np.exp(-t * 18) * 0.9


def error():
    t = t_axis(0.22)
    return np.sign(np.sin(2 * np.pi * 180 * t)) * np.exp(-t * 14) * 0.05


# The synth sound a recorded file stands in for; its peak is the level the file is matched to
REFERENCE = {
    "hit": lambda: hit(1), "whoosh": whoosh, "riser": lambda: riser(1.0), "down": lambda: down(0.6),
    "type": key_click, "tick": tick, "pop": pop, "ding": ding, "stamp": stamp, "error": error,
}


def decode(path):
    """Any audio file → mono float at SR. Plain WAV needs only the standard library."""
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as handle:
                if handle.getsampwidth() == 2 and handle.getframerate() == SR:
                    data = np.frombuffer(handle.readframes(handle.getnframes()), np.int16).astype(float) / 32768
                    return data.reshape(-1, handle.getnchannels()).mean(axis=1)
        except wave.Error:
            pass
    if not shutil.which("ffmpeg"):
        raise SystemExit(f"decoding {path} needs ffmpeg\nNext: install ffmpeg, or give the kit 16-bit {SR} Hz WAV files")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(float)


class Sounds:
    """Each cue's sound: the synth by default, or the kit's files in rotation, at the kit's gain."""

    def __init__(self, sfx_settings, work):
        self.settings = sfx_settings
        self.files = {}
        self.turn = {}
        for cue, setting in sfx_settings.items():
            if setting.get("files") and not setting.get("mute"):
                # Restoring rng's state keeps measuring the reference from shifting every synth cue's noise
                state = rng.bit_generator.state
                reference = float(np.max(np.abs(REFERENCE[cue]()))) or 1.0
                rng.bit_generator.state = state
                decoded = [decode(work / name) for name in setting["files"]]
                self.files[cue] = [clip / (np.max(np.abs(clip)) or 1.0) * reference for clip in decoded]

    def muted(self, cue):
        return self.settings.get(cue, {}).get("mute", False)

    def gain(self, cue):
        return self.settings.get(cue, {}).get("gain", 1)

    def recorded(self, cue):
        """The next file for this cue, or None when the cue stays synthesized."""
        if cue not in self.files:
            return None
        index = self.turn.get(cue, 0)
        self.turn[cue] = index + 1
        return self.files[cue][index % len(self.files[cue])]


def fit(sound, duration, end_aligned):
    """Crop a recorded riser to end on its cue, or a recorded down-sweep to stop with it."""
    length = int(SR * duration)
    if duration <= 0 or len(sound) <= length:
        return sound
    if end_aligned:
        return sound[-length:]
    fade = min(length, SR // 20)
    out = sound[:length].copy()
    out[length - fade:] *= np.linspace(1, 0, fade)
    return out


def build_sfx(cues, samples, sounds):
    sfx = np.zeros(samples)
    unknown = set()
    for cue in cues:
        kind, at, duration = cue["type"], cue["t"], cue.get("dur", 0)
        if kind not in REFERENCE:
            unknown.add(kind)
            continue
        if sounds.muted(kind):
            continue
        gain = sounds.gain(kind)
        if kind in ("type", "tick"):
            if kind == "type" and duration <= 0.05:
                continue
            unit = (lambda: sounds.recorded(kind)) if kind in sounds.files else (key_click if kind == "type" else tick)
            interval, jitter = (0.055, 0.04) if kind == "type" else (0.07, 0)
            place(sfx, repeated(unit, duration, interval, jitter) * gain, at)
            continue
        recorded = sounds.recorded(kind)
        if recorded is not None:
            if kind == "riser":
                recorded = fit(recorded, duration, end_aligned=True)
                at += max(0.0, duration - len(recorded) / SR)
            elif kind == "down":
                recorded = fit(recorded, duration, end_aligned=False)
            sound = recorded * (cue.get("power", 1) if kind == "hit" else 1)
        elif kind == "hit":
            sound = hit(cue.get("power", 1))
        elif kind in ("riser", "down"):
            sound = riser(duration) if kind == "riser" else down(duration)
        else:
            sound = REFERENCE[kind]()
        place(sfx, sound * gain, at)
    return sfx, unknown



def pulse_note(midi, seconds):
    t = t_axis(seconds)
    saw = sum(np.sin(2 * np.pi * note(midi) * k * t) / k for k in range(1, 7))
    return saw * np.exp(-t * 18) * 0.05


def build_music(duration, samples, drums_from, drop, quiet, profile, music_rng, offset=0.0, fades=(True, True)):
    beat = 60 / profile["bpm"]
    bar = beat * 4
    root, layers = profile["root"], profile["layers"]
    rotation = int(music_rng.integers(0, 4))
    progression = profile["progression"][rotation:] + profile["progression"][:rotation]
    pluck_order = [int(i) for i in music_rng.permutation(3)]
    # One fixed noise burst for every hat, so any slice of the bed renders the same samples as the whole
    hat_noise = np.random.default_rng(11).standard_normal(int(SR * 0.05))
    music = np.zeros(samples)
    origin = int(round(offset * SR))
    # Bars sit on the bed's own clock; the bar before the window still rings into it
    for b in range(max(0, int(offset // bar) - 1), int((offset + duration) / bar) + 2):
        start = b * bar
        offsets = progression[b % 4]
        chord = [root + o for o in offsets]
        if "pad" in layers:
            pad_t = t_axis(bar + 0.5)
            pad = sum(
                np.sin(2 * np.pi * note(m) * 2 ** (d / 12) * pad_t) + 0.3 * np.sin(4 * np.pi * note(m) * 2 ** (d / 12) * pad_t)
                for m in chord for d in (-0.12, 0.0, 0.12)
            ) / 9
            place(music, pad * envelope(len(pad_t), 0.6, 0.8) * 0.16, start, origin)
        if "bass" in layers:
            bass_t = t_axis(bar)
            place(music, np.sin(2 * np.pi * note(root + offsets[0] - 12) * bass_t) * envelope(len(bass_t), 0.05, 0.4) * 0.14, start, origin)
        if "pluck" in layers:
            for i in range(8):
                pluck_t = t_axis(0.25)
                place(music, np.sin(2 * np.pi * note(chord[pluck_order[i % 3]] + 12) * pluck_t) * np.exp(-pluck_t * 14) * 0.05, start + i * beat / 2, origin)
        if "pulse" in layers:
            for i in range(8):
                place(music, pulse_note(root + offsets[0], beat / 2), start + i * beat / 2, origin)
        # Drums from 0 were already playing before this slice: the last bar's hits ring on across a chapter join
        if drums_from is not None and (drums_from <= 0 or start - offset >= drums_from):
            for i in range(4):
                kick_t = t_axis(0.3)
                place(music, np.sin(2 * np.pi * np.cumsum(50 + 120 * np.exp(-kick_t * 30)) / SR) * np.exp(-kick_t * 9) * 0.2, start + i * beat, origin)
                hat_t = t_axis(0.05)
                place(music, (hat_noise - smooth(hat_noise, 4)) * np.exp(-hat_t * 90) * 0.03, start + i * beat + beat / 2, origin)

    return music * music_gain(duration, samples, quiet, drop, fades)


def music_gain(duration, samples, quiet, drop, fades=(True, True)):
    t = np.arange(samples) / SR
    gain = np.ones(samples)
    if fades[0]:
        gain *= np.clip(t / 1.5, 0, 1)
    if fades[1]:
        gain *= np.clip((duration - t) / 1.2, 0, 1)
    for a, b in quiet:
        gain[(t > a) & (t < b)] *= 0.55
    if drop is not None:
        # Silence right before the final slam makes the punchline land harder
        gain[(t > drop - 0.3) & (t < drop)] = 0.0
        gain[t >= drop] *= 1.25
    return gain


def trim_silence(track):
    """The track without its silent lead-in and fade-out tail, so a loop never dips between repeats."""
    window = SR // 10
    loudness = np.sqrt(np.convolve(track ** 2, np.ones(window) / window, mode="same"))
    # -30 dB under the track's loudest tenth of a second: a fade-out or room tone, not music
    playing = np.flatnonzero(loudness > loudness.max() * 0.03)
    return track[playing[0]:playing[-1] + 1] if len(playing) else track


def track_music(track, duration, samples, quiet, drop, offset=0.0, fades=(True, True)):
    """The kit's own music track, looped to the video's length from offset seconds in, under the same fades and drop."""
    track = trim_silence(track)
    # Each repeat starts as the last one's final seconds fade out, so the loop has no seam
    fade = min(int(LOOP_FADE * SR), len(track) // 4)
    unit = track[:len(track) - fade].copy()
    if fade:
        ramp = np.linspace(0, 1, fade)
        unit[:fade] = track[:fade] * ramp + track[-fade:] * (1 - ramp)
    origin = int(round(offset * SR))
    start = origin % len(unit)
    music = np.tile(unit, (start + samples) // len(unit) + 2)[start:start + samples]
    # The first play starts clean: nothing before it to fade out of
    clean = max(0, min(samples, fade - origin))
    music[:clean] = track[origin:origin + clean]
    return music * music_gain(duration, samples, quiet, drop, fades)


def tape_stop(music, a, b):
    """The music winds down like a stopped tape at a, stays silent, and restarts at b."""
    start, end = int(a * SR), min(len(music), int(b * SR))
    wind = min(int(0.6 * SR), end - start)
    if wind <= 0:
        return music
    n = np.arange(wind)
    # Speed falls linearly from 1 to 0, so the read position is the integral of that ramp
    position = start + n - n * n / (2 * wind)
    music[start:start + wind] = np.interp(position, np.arange(len(music)), music)
    music[start + wind:end] = 0.0
    fade = min(int(0.03 * SR), len(music) - end)
    if fade > 0:
        music[end:end + fade] *= np.linspace(0, 1, fade)
    return music


def muffle(music, a, b):
    """The music sits behind a low-pass between a and b, as if through a wall, and sweeps open into b."""
    start, end = int(a * SR), min(len(music), int(b * SR))
    if end <= start:
        return music
    sweep = min(int(0.4 * SR), end - start)
    cutoff = np.full(end - start, 350.0)
    cutoff[-sweep:] = np.geomspace(350.0, 16000.0, sweep)
    alpha = 1 - np.exp(-2 * np.pi * cutoff / SR)
    out = music[start:end].copy()
    state = out[0]
    for i in range(len(out)):
        state += alpha[i] * (out[i] - state)
        out[i] = state
    music[start:end] = out
    return music


def stutter(music, a, b, beat):
    """One beat from a repeats until b, like a stuck record; the music carries on from b."""
    start, end = int(a * SR), min(len(music), int(b * SR))
    length = max(1, int(beat * SR))
    if end - start <= length or start + length > len(music):
        return music
    slice_ = music[start:start + length].copy()
    edge = min(int(0.005 * SR), length // 4)
    if edge:
        slice_[:edge] *= np.linspace(0, 1, edge)
        slice_[-edge:] *= np.linspace(1, 0, edge)
    music[start:end] = np.tile(slice_, (end - start) // length + 1)[:end - start]
    return music


def story_moments(music, stops, muffles, stutters, beat):
    """Music that acts out the script: tape stops, muffled stretches and stuck loops, applied after the bed is built."""
    for a, b in muffles:
        music = muffle(music, a, b)
    for a, b in stutters:
        music = stutter(music, a, b, beat)
    for a, b in stops:
        music = tape_stop(music, a, b)
    return music


def duck_gaps(words, duration, minimum=DUCK_GAP_MIN):
    """[start, end] pauses of at least `minimum` seconds between consecutive words, clamped to [0, duration]."""
    gaps = []
    for (_, end), (start, _) in zip(words, words[1:]):
        if start - end < minimum:
            continue
        a, b = max(0.0, min(duration, end)), max(0.0, min(duration, start))
        if b > a:
            gaps.append([round(a, 3), round(b, 3)])
    return gaps


def build_duck_expr(gaps, music_level, ramp=0.15):
    """ffmpeg volume expression swells the bed toward full level inside each gap.

    Each gap is its own additive window — nesting the whole expression per gap
    doubles it (2^N), which blew past ARG_MAX on a real 17-gap mix.
    """
    try:
        music = float(music_level)
    except (TypeError, ValueError):
        return None
    if not gaps or not 0 < music < 1:
        return None
    boost = min(1.0 / music, 2.0)
    windows = []
    for pair in gaps:
        try:
            a, b = float(pair[0]), float(pair[1])
        except (TypeError, ValueError, IndexError):
            continue
        if b - a < 2 * ramp:
            continue
        windows.append(
            f"if(lt(t,{a:.3f}),0,"
            f"if(lt(t,{a + ramp:.3f}),(t-{a:.3f})/{ramp},"
            f"if(lt(t,{b - ramp:.3f}),1,"
            f"if(lt(t,{b:.3f}),({b:.3f}-t)/{ramp},0))))"
        )
    if not windows:
        return None
    return f"1+{boost - 1:.4f}*(" + "+".join(windows) + ")"


def parse_words_js(text):
    """Sorted (start, end) pairs from words.js — JS, not JSON, so the assignment wrapper is stripped first."""
    match = re.search(r"=\s*(\[.*\])\s*;?\s*$", text, re.S)
    if not match:
        return None
    try:
        phrases = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    words = [word for phrase in phrases if isinstance(phrase, list) for word in phrase
             if isinstance(word, dict)
             and isinstance(word.get("s"), (int, float)) and isinstance(word.get("e"), (int, float))]
    return sorted((float(word["s"]), float(word["e"])) for word in words)


def parse_range(flag, value):
    """'A:B' → (A, B) seconds, or None after printing the problem and the fix."""
    parts = value.split(":")
    try:
        a, b = (float(part) for part in parts) if len(parts) == 2 else (None, None)
    except ValueError:
        a = b = None
    if a is None or b <= a:
        print(f"{flag} must be A:B with A < B in seconds, got: {value}", file=sys.stderr)
        print(f"Next: pass a range like {flag} 2.5:4.0", file=sys.stderr)
        return None
    return a, b


def chapter_position(work):
    """Where a long-form chapter's music sits in the whole bed, or None for a work dir that is no chapter."""
    work = work.resolve()
    project = work.parent.parent
    manifest = project / "chapters.json"
    if not manifest.is_file():
        return None
    try:
        chapters = json.loads(manifest.read_text(encoding="utf-8")).get("chapters") or []
    except json.JSONDecodeError as error:
        raise SystemExit(f"{manifest} is not valid JSON: {error}\nNext: fix chapters.json and re-run")
    works = [(project / entry.get("work", f"{entry.get('dir', '')}/work")).resolve() for entry in chapters]
    if work not in works:
        return None
    index = works.index(work)
    offset = 0.0
    for entry, earlier in zip(chapters[:index], works[:index]):
        try:
            offset += float(json.loads((earlier / "render.json").read_text(encoding="utf-8"))["duration"])
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            raise SystemExit(f"chapter \"{entry.get('title', earlier.parent.name)}\" has no duration in {earlier / 'render.json'}\n"
                             "Next: run fill_template.py on every earlier chapter first; the music picks up where they end")
    own = work / "render.json"
    duration = float(json.loads(own.read_text(encoding="utf-8"))["duration"]) if own.is_file() else None
    return {"project": project, "offset": offset, "number": index + 1, "of": len(chapters), "duration": duration}


def kit_audio(work):
    """The audio block fill_template.py installed with the kit, or the defaults for a work dir without one."""
    try:
        audio = json.loads((work / "kit" / "kit.json").read_text(encoding="utf-8")).get("audio")
    except (OSError, json.JSONDecodeError):
        audio = None
    return audio or {"music": "synth", "levels": {"music": 0.22, "sfx": 0.5}, "sfx": {}}


def write_wav(path, data, peak=None):
    # A chapter passes the whole bed's peak, so every chapter's music.wav sits at the same level
    peak = peak or np.max(np.abs(data)) or 1.0
    pcm = (np.clip(data / peak * 0.9, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cues", type=Path)
    parser.add_argument("duration", type=float)
    parser.add_argument("work", type=Path)
    parser.add_argument("--template", default="kinetic", help="theme id whose music profile to use")
    parser.add_argument("--drop", type=float, default=None, help="time of the final slam")
    parser.add_argument("--drums-from", type=float, default=None, help="bring drums in at this time")
    parser.add_argument("--quiet", action="append", default=[], help="A:B range where music sits lower")
    parser.add_argument("--no-music", action="store_true")
    parser.add_argument("--stop", action="append", default=[], help="A:B tape-stop at A, silence, music back at B")
    parser.add_argument("--muffle", action="append", default=[], help="A:B music behind a wall, sweeping open at B")
    parser.add_argument("--stutter", action="append", default=[], help="A:B one beat from A loops until B")
    args = parser.parse_args()

    if not args.cues.is_file():
        print(f"No such cues file: {args.cues}", file=sys.stderr)
        print("Next: run render.js cues first", file=sys.stderr)
        return 1

    templates = json.loads(TEMPLATES_JSON.read_text())["templates"]
    profiles = {entry["id"]: entry["music"] for entry in templates}
    if args.template not in profiles:
        print(f"Unknown template: {args.template} (valid: {', '.join(profiles)})", file=sys.stderr)
        print("Next: pass the same --template id you gave fill_template.py", file=sys.stderr)
        return 1
    profile = profiles[args.template]

    chapter = chapter_position(args.work)
    if chapter and chapter["duration"] is not None and abs(chapter["duration"] - args.duration) > 0.001:
        print(f"duration {args.duration} differs from this chapter's {chapter['duration']} in render.json", file=sys.stderr)
        print(f"Next: pass {chapter['duration']}, the duration fill_template.py printed, so the next chapter's music starts where this one ends", file=sys.stderr)
        return 1

    samples = int(SR * args.duration)
    cues = json.loads(args.cues.read_text())
    audio = kit_audio(args.work)
    sfx, unknown = build_sfx(cues, samples, Sounds(audio["sfx"], args.work))
    write_wav(args.work / "sfx.wav", sfx)
    written = ["sfx.wav"]
    music_source = "none" if args.no_music else audio["music"]

    if music_source != "none":
        ranges = {}
        for flag in ("quiet", "stop", "muffle", "stutter"):
            ranges[flag] = [parse_range(f"--{flag}", value) for value in getattr(args, flag)]
            if None in ranges[flag]:
                return 1
        quiet = ranges["quiet"]
        offset = chapter["offset"] if chapter else 0.0
        fades = (not chapter or chapter["number"] == 1, not chapter or chapter["number"] == chapter["of"])
        peak = None
        if music_source == "synth":
            resolved_work = args.work.resolve()
            seed_key = chapter["project"].name if chapter else f"{resolved_work.parent.name}/{resolved_work.name}"
            seed = int.from_bytes(hashlib.sha256(seed_key.encode()).digest()[:8], "big")
            music = build_music(args.duration, samples, args.drums_from, args.drop, quiet, profile, np.random.default_rng(seed), offset, fades)
            if chapter:
                # Four bars of the full bed with drums, plus the drop's 1.25 boost: the level every chapter shares
                reference = 4 * 4 * 60 / profile["bpm"]
                peak = 1.25 * np.max(np.abs(build_music(reference, int(SR * reference), 0, None, [], profile, np.random.default_rng(seed), 0.0, (False, False))))
        else:
            track = decode(args.work / music_source)
            if not len(track):
                raise SystemExit(f"{args.work / music_source} decoded to no audio\nNext: check the file plays, or set audio.music to synth")
            music = track_music(track, args.duration, samples, quiet, args.drop, offset, fades)
            if chapter:
                peak = 1.25 * np.max(np.abs(track))
        music = story_moments(music, ranges["stop"], ranges["muffle"], ranges["stutter"], 60 / profile["bpm"])
        write_wav(args.work / "music.wav", music, peak)
        written.append("music.wav")

    # The mix scripts read this, so a stale music.wav from an earlier run never sneaks into a --no-music mix
    mix = {**audio["levels"], "music_file": "music.wav" if music_source != "none" else None}
    if chapter and music_source != "none":
        mix["music_offset"] = round(chapter["offset"], 4)
    words_path = args.work / "words.js"
    if words_path.is_file():
        gaps = duck_gaps(parse_words_js(words_path.read_text(encoding="utf-8")) or [], args.duration)
        if gaps:
            mix["duck"] = gaps
    (args.work / "mix.json").write_text(json.dumps(mix, indent=2) + "\n", encoding="utf-8")

    tempo = {"none": "", "synth": f" · {args.template} {profile['bpm']} bpm"}.get(music_source, f" · kit track {Path(music_source).name}")
    if chapter and music_source != "none":
        minutes, seconds = divmod(chapter["offset"], 60)
        tempo += f" · chapter {chapter['number']}/{chapter['of']}, music from {int(minutes)}:{seconds:05.2f}"
    tuned = sorted(cue for cue, setting in audio["sfx"].items() if setting.get("files") or setting.get("mute") or setting.get("gain", 1) != 1)
    if tuned:
        tempo += f" · kit sounds: {', '.join(tuned)}"
    print(f"{len(cues)} cues · {args.duration:.1f}s{tempo} → {' + '.join(written)}")
    if unknown:
        print(f"  ignored unknown cue types: {', '.join(sorted(unknown))}")
    print("Next: run render-frames.sh, then mix-encode.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
