#!/usr/bin/env python3
"""Procedural dream-portal tunnel renderer — volumetric GLSL, audio-reactive.

A curving tunnel of molten embers (spiral arms of clumpy fire noise around
the wall), white-hot spark specks flying past, and an iridescent core "eye"
at the end of the tunnel. Over the clip the palette morphs from golden fire
to cosmic purple/blue and the core collapses into a dark event-horizon disc
with a hot rim. Rendered headless via moderngl piped into ffmpeg.

Audio reactivity (librosa onset envelope):
  - ember emission surges on hits
  - camera speed surges on hits (integrated, stays smooth)
  - core flares on hits

Usage:
  render_dream_portal.py --audio song.wav --start 116.22 --dur 12 \
      --out outputs/procedural/dream_portal_poc.mp4 [--fps 30] [--w 1080 --h 1920]
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
uniform float uPhase;   // 0..1 across the clip (fire -> cosmic morph)

#define PI 3.14159265359

float hash13(vec3 p) {
    p = fract(p * 0.1031);
    p += dot(p, p.zyx + 31.32);
    return fract((p.x + p.y) * p.z);
}

float vnoise(vec3 p) {
    vec3 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float n000 = hash13(i);
    float n100 = hash13(i + vec3(1, 0, 0));
    float n010 = hash13(i + vec3(0, 1, 0));
    float n110 = hash13(i + vec3(1, 1, 0));
    float n001 = hash13(i + vec3(0, 0, 1));
    float n101 = hash13(i + vec3(1, 0, 1));
    float n011 = hash13(i + vec3(0, 1, 1));
    float n111 = hash13(i + vec3(1, 1, 1));
    return mix(mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),
               mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y), f.z);
}

// rotate domain between octaves so value-noise cells never line up
const mat3 ROT = mat3( 0.60, -0.72,  0.34,
                       0.72,  0.48, -0.50,
                       0.20,  0.50,  0.84);

float fbm(vec3 p) {
    float a = 0.5, s = 0.0;
    for (int i = 0; i < 4; i++) {
        s += a * vnoise(p);
        p = ROT * p * 2.23 + vec3(11.3, 7.7, 5.1);
        a *= 0.5;
    }
    return s;
}

// curving tunnel axis
vec2 path(float z) {
    return vec2(0.85 * sin(z * 0.115), 0.65 * cos(z * 0.094));
}

// golden fire ramp: deep red -> orange -> gold -> white
vec3 firePal(float t) {
    t = clamp(t, 0.0, 1.0);
    return vec3(pow(t, 0.55), pow(t, 1.7), pow(t, 3.6)) * 1.25;
}

// cosmic ramp: deep violet -> magenta -> ice blue -> white
vec3 cosmicPal(float t) {
    t = clamp(t, 0.0, 1.0);
    vec3 c = vec3(pow(t, 1.9) * 0.95, pow(t, 2.6) * 0.75, pow(t, 0.7)) * 1.2;
    c += pow(t, 2.0) * vec3(0.35, 0.0, 0.28);   // magenta lift
    return c;
}

// ember + spark density around the tunnel wall; temp is 0..1 heat
float density(vec3 p, out float temp) {
    vec2 q = p.xy - path(p.z);
    float r = length(q);
    float ang = atan(q.y, q.x);
    float R = 1.55;

    float shell = exp(-pow((r - R) * 3.4, 2.0));
    // spiral ember arms winding along z, slowly rotating
    float arms = pow(0.5 + 0.5 * sin(ang * 5.0 + p.z * 2.2 - uTime * 1.1), 1.8);
    arms = 0.2 + 0.8 * arms;
    // clumpy advected noise makes the arms read as ember clouds
    float n = fbm(vec3(q * 2.1, p.z * 1.1) + vec3(0.0, 0.0, -uTime * 0.55));
    n = pow(max(n - 0.36, 0.0) * 2.1, 1.6);
    // high-frequency detail breaks the blobs into filaments
    float det = vnoise(vec3(q * 6.5, p.z * 3.2) + vec3(0.0, 0.0, -uTime * 1.1));
    float d = shell * arms * n * (0.5 + 1.3 * det) * 3.4;

    temp = clamp(1.12 - (r / R) * 0.72, 0.05, 1.0) * (0.65 + 0.7 * det);
    return d;
}

// round ember bokeh streaming radially outward (screen-space parallax layer)
vec3 sparkLayer(vec2 uv, float scale, float speed, float seed, float morphMix) {
    float ang = atan(uv.y, uv.x) + seed;   // rotate seam per layer
    float r = length(uv) + 0.06;
    // cells in (angle, inverse-radius) space; camera motion pushes dots outward
    float row = floor(1.4 / r - uCamZ * speed);
    // per-ring angular offset so rings never align into circular seams
    vec2 pc = vec2(ang / 6.2832 * scale + hash13(vec3(row, seed, 5.0)) * 17.3,
                   1.4 / r - uCamZ * speed);
    vec2 cell = floor(pc), f = fract(pc);
    float h1 = hash13(vec3(cell, seed));
    float h2 = hash13(vec3(cell, seed + 40.0));
    // keep centers well inside the cell so elongated dots never truncate at edges
    vec2 o = vec2(0.3 + 0.4 * h1, 0.34 + 0.32 * h2);
    vec2 dv = f - o;
    dv.y *= 0.5;               // elongate along the radial streak direction
    float dot2 = exp(-dot(dv, dv) * 120.0);
    // sparse field: most cells stay dark, a few burn bright
    float tw = pow(hash13(vec3(cell, seed + 80.0)), 5.0) * 2.4;
    // dimmer near screen center so sparks don't sit on the core
    float fade = smoothstep(0.05, 0.30, length(uv));
    vec3 col = mix(vec3(1.0, 0.72, 0.35), vec3(0.75, 0.62, 1.0), morphMix);
    return dot2 * tw * fade * col;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;
    float cr = cos(uRoll), sr = sin(uRoll);
    uv = mat2(cr, -sr, sr, cr) * uv;

    float cz = uCamZ;
    vec3 ro = vec3(path(cz) * 0.82 + 0.14 * vec2(cos(uTime * 0.33), sin(uTime * 0.26)), cz);
    vec3 target = vec3(path(cz + 2.4) * 0.92, cz + 2.4);
    vec3 fwd = normalize(target - ro);
    vec3 right = normalize(cross(fwd, vec3(0.0, 1.0, 0.0)));
    vec3 up = cross(right, fwd);
    vec3 rd = normalize(uv.x * right + uv.y * up + 1.12 * fwd);

    float morph = smoothstep(0.58, 0.92, uPhase);   // fire -> cosmic
    float hole = smoothstep(0.72, 0.96, uPhase);    // core collapses to event horizon

    // volumetric march with absorption so near walls occlude the deep tunnel
    vec3 acc = vec3(0.0);
    float T = 1.0;
    float t = 0.25;
    float emit = (0.44 + 0.34 * uPulse);
    for (int i = 0; i < 64; i++) {
        vec3 p = ro + rd * t;
        float temp;
        float d = density(p, temp);
        if (d > 0.001) {
            vec3 col = mix(firePal(temp), cosmicPal(temp), morph);
            float dt = 0.05 + t * 0.028;
            acc += col * d * T * dt * emit;
            T *= exp(-d * dt * 1.7);
            if (T < 0.02) break;
        }
        t += 0.05 + t * 0.028;
        if (t > 11.0) break;
    }

    // the core "eye": where does the ray sit relative to the axis, far ahead
    vec3 pf = ro + rd * 7.5;
    float rf = length(pf.xy - path(pf.z));
    float g = exp(-rf * rf * 9.5);
    // iridescent opal tint swirling around the eye
    float angF = atan(pf.y - path(pf.z).y, pf.x - path(pf.z).x);
    vec3 irid = 0.55 + 0.45 * cos(vec3(0.0, 2.1, 4.2) + angF * 2.0 + uTime * 0.7);
    vec3 coreCol = mix(vec3(1.0, 0.88, 0.66) * 1.7, irid * 1.2, 0.22);
    coreCol = mix(coreCol, vec3(0.72, 0.5, 1.05) * 1.4, morph);
    // wide warm halo around the tight core
    float halo = exp(-rf * rf * 1.6);
    float flare = 0.55 + 0.65 * uPulse;
    // open core fades out as the event horizon forms; a hot rim replaces it
    float rim = smoothstep(0.12, 0.42, g) * (1.0 - smoothstep(0.55, 0.9, g));
    vec3 rimCol = mix(vec3(1.0, 0.55, 0.2), vec3(1.0, 0.45, 0.75), morph);
    acc += g * (1.0 - hole) * coreCol * flare * T;
    acc += halo * (1.0 - hole) * mix(vec3(1.0, 0.5, 0.14), vec3(0.8, 0.4, 1.0), morph) * flare * 0.35 * T;
    acc += hole * rim * rimCol * 1.6 * flare * T;
    // the dark disc eats light behind it
    acc *= 1.0 - hole * smoothstep(0.5, 0.95, g) * 0.92;
    // starfield inside the horizon
    float stars = pow(max(vnoise(vec3(uv * 26.0, uTime * 0.12)) - 0.78, 0.0), 2.0) * 24.0;
    acc += hole * smoothstep(0.55, 0.95, g) * stars * vec3(0.8, 0.85, 1.0);

    // ember bokeh streaming past the camera, three parallax depths
    float sparkAmp = 0.5 + 0.5 * uPulse;
    acc += sparkLayer(uv, 14.0, 0.55, 3.0, morph) * 1.0 * sparkAmp;
    acc += sparkLayer(uv, 24.0, 0.95, 17.0, morph) * 0.7 * sparkAmp;
    acc += sparkLayer(uv, 38.0, 1.55, 29.0, morph) * 0.45 * sparkAmp;

    // tonemap + saturation lift + gamma (house style)
    vec3 col = acc * 1.35 / (1.0 + acc);
    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    col = clamp(mix(vec3(luma), col, 1.28), 0.0, 1.0);
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
    ap.add_argument("--dur", type=float, default=12.0)
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
        cam_z += dt * (1.15 + 1.0 * p)      # speed surge on hits
        roll += dt * 0.09
        prog["uTime"].value = i * dt
        prog["uCamZ"].value = cam_z
        prog["uPulse"].value = min(p, 1.0)
        prog["uRoll"].value = roll
        prog["uPhase"].value = i / max(n - 1, 1)
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
