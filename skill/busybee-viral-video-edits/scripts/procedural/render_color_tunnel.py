#!/usr/bin/env python3
"""Procedural color-tunnel renderer — raymarched GLSL, audio-reactive.

A tunnel of glossy spheres in twisted spiral arms, full rainbow hue sweep
around the axis, camera flying into the vortex. Rendered headless via
moderngl (Metal-backed GL) piped straight into ffmpeg.

Audio reactivity (all from the librosa onset envelope):
  - sphere radius pulses on hits
  - camera speed surges on hits (integrated, so motion stays smooth)
  - specular glow lifts on hits

Usage:
  render_color_tunnel.py --audio song.mp3 --start 81.92 --dur 15 \
      --out outputs/procedural/color_tunnel.mp4 [--fps 30] [--w 1080 --h 1920]
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np

VERT = """
#version 330
in vec2 in_pos;
void main() { gl_Position = vec4(in_pos, 0.0, 1.0); }
"""

FRAG = """
#version 330
out vec4 fragColor;
uniform vec2  uRes;
uniform float uTime;    // seconds since window start
uniform float uCamZ;    // integrated camera distance
uniform float uPulse;   // onset envelope 0..1
uniform float uRoll;    // slow camera roll

#define PI 3.14159265359
#define ARMS 14.0
#define CELL 0.62
#define TUNR 1.0

vec3 hsv2rgb(vec3 c) {
    vec3 p = abs(fract(c.xxx + vec3(0.0, 2.0/3.0, 1.0/3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

// distance to the twisted sphere lattice; also outputs world angle for hue
float map(vec3 p, out float outAng) {
    float r = length(p.xy);
    float ang = atan(p.y, p.x);
    outAng = ang;
    float twist = 0.55 + 0.08 * sin(uTime * 0.23);
    float a = ang - p.z * twist;
    float sector = 2.0 * PI / ARMS;
    a = mod(a, sector) - sector * 0.5;
    float zc = mod(p.z, CELL) - CELL * 0.5;
    float rad = 0.34 * (1.0 + 0.20 * uPulse);
    return length(vec3(r - TUNR, a * TUNR, zc)) - rad;
}

vec3 normalAt(vec3 p) {
    float dummy; vec2 e = vec2(0.0015, 0.0);
    return normalize(vec3(
        map(p + e.xyy, dummy) - map(p - e.xyy, dummy),
        map(p + e.yxy, dummy) - map(p - e.yxy, dummy),
        map(p + e.yyx, dummy) - map(p - e.yyx, dummy)));
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;
    float cr = cos(uRoll), sr = sin(uRoll);
    uv = mat2(cr, -sr, sr, cr) * uv;

    vec3 ro = vec3(0.16 * cos(uTime * 0.31), 0.16 * sin(uTime * 0.24), uCamZ);
    vec3 rd = normalize(vec3(uv * 1.15, 1.0));

    float t = 0.0, ang = 0.0;
    float d = 0.0;
    bool hit = false;
    for (int i = 0; i < 96; i++) {
        vec3 p = ro + rd * t;
        d = map(p, ang);
        if (d < 0.0012 * t) { hit = true; break; }
        t += d * 0.85;
        if (t > 14.0) break;
    }

    vec3 col = vec3(0.0);
    if (hit) {
        vec3 p = ro + rd * t;
        vec3 n = normalAt(p);
        // hue: pure angle sweep around the tunnel + slow rotation
        float hue = fract(ang / (2.0 * PI) + uTime * 0.03);
        vec3 base = hsv2rgb(vec3(hue, 1.0, 1.0));
        base *= base;                          // deepen saturation
        vec3 ldir = normalize(vec3(0.4, 0.6, -0.5));
        float dif = max(dot(n, ldir), 0.0);
        dif = dif * dif * 0.9 + 0.10;          // dark ambient, punchy falloff
        vec3 h = normalize(ldir - rd);
        float spec = pow(max(dot(n, h), 0.0), 64.0) * (2.0 + 1.6 * uPulse);
        float fre = pow(1.0 - max(dot(n, -rd), 0.0), 3.0) * 0.35;
        col = base * dif + vec3(spec) + base * fre;
        // depth fog to black (the vortex mouth)
        col *= exp(-t * 0.22);
    }
    // subtle center glow breathing with the music
    float cg = exp(-length(uv) * 6.0) * 0.05 * (1.0 + 2.0 * uPulse);
    col += vec3(cg);
    // tonemap + saturation lift + gamma
    col = col * 1.35 / (1.0 + col);
    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    col = clamp(mix(vec3(luma), col, 1.3), 0.0, 1.0);
    col = pow(col, vec3(0.4545));
    fragColor = vec4(col, 1.0);
}
"""


def onset_env(audio: Path, start: float, dur: float, fps: int) -> np.ndarray:
    import librosa
    y, sr = librosa.load(str(audio), sr=22050, mono=True,
                         offset=max(0.0, start - 1.0), duration=dur + 2.0)
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    tt = librosa.times_like(env, sr=sr, hop_length=512) - (1.0 if start >= 1.0 else 0.0)
    n = int(round(dur * fps))
    frames_t = np.arange(n) / fps
    e = np.interp(frames_t, tt, env)
    e = e / (np.percentile(e, 95) + 1e-6)
    # fast attack, ~0.22s decay so hits feel percussive
    out = np.zeros_like(e)
    decay = np.exp(-1.0 / (fps * 0.22))
    acc = 0.0
    for i, v in enumerate(e):
        acc = max(v, acc * decay)
        out[i] = acc
    return np.clip(out, 0.0, 1.6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", type=Path, required=True)
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--dur", type=float, default=15.0)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    args = ap.parse_args()

    import moderngl
    ctx = moderngl.create_standalone_context()
    prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
    quad = ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], dtype="f4").tobytes())
    vao = ctx.vertex_array(prog, [(quad, "2f", "in_pos")])
    fbo = ctx.framebuffer(color_attachments=[ctx.texture((args.w, args.h), 3)])
    fbo.use()
    prog["uRes"].value = (float(args.w), float(args.h))

    env = onset_env(args.audio, args.start, args.dur, args.fps)
    n = len(env)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    silent = args.out.with_suffix(".silent.mp4")

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{args.w}x{args.h}",
         "-r", str(args.fps), "-i", "-",
         "-vf", "vflip", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)

    cam_z, roll = 0.0, 0.0
    dt = 1.0 / args.fps
    for i in range(n):
        p = float(env[i])
        cam_z += dt * (1.35 + 1.1 * p)      # speed surge on hits
        roll += dt * 0.10
        prog["uTime"].value = i * dt
        prog["uCamZ"].value = cam_z
        prog["uPulse"].value = min(p, 1.0)
        prog["uRoll"].value = roll
        vao.render()
        ff.stdin.write(fbo.read(components=3))
        if i % 120 == 0:
            print(f"frame {i}/{n}")
    ff.stdin.close()
    ff.wait()

    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(silent),
         "-ss", f"{args.start:.3f}", "-t", f"{args.dur:.3f}", "-i", str(args.audio),
         "-af", f"afade=t=in:st=0:d=0.05,afade=t=out:st={args.dur - 0.25:.3f}:d=0.25",
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(args.out)], check=True)
    silent.unlink()
    print(f"BUILT {args.out}")


if __name__ == "__main__":
    main()
