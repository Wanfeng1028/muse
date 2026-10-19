#!/usr/bin/env python3
"""Portal Weave — real footage and the dream-portal tunnel fused in ONE shader pass.

Not an overlay: every frame is composed in a single GLSL program that
samples the base cut (real clips, pre-assembled) and the volumetric ember
tunnel together, sharing one palette, one tonemap, one particle field.

Integration (all driven by uPhi 0..1 "immersion" + the onset envelope):
  - footage graded toward the ember palette; shadows go violet as phi rises
  - heat-shimmer displacement of the world from the tunnel's own noise field
  - ember light-wrap spilling from the portal onto the scene edges
  - shared spark bokeh streaming over world and tunnel alike
  - beat cuts land as in-shader warp punches (zoom + chromatic split)
  - tunnel walls swallow the periphery as phi rises; the world stays visible
    through the portal bore, then falls into the purple event horizon

Phi curves: ramp (steady descent), breath (energy-following), rush (hot start).

Usage:
  render_portal_weave.py --base basecut.mp4 --audio song.wav --start 108.47 \
      --dur 15 --cuts "1.72,3.44,5.15" --phi ramp --out weave.mp4
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
uniform float uTime;
uniform float uCamZ;
uniform float uPulse;   // onset envelope 0..1
uniform float uRoll;
uniform float uPhi;     // immersion 0..1
uniform float uCut;     // seconds since last cut
uniform sampler2D uSrc; // base-cut frame (real footage)

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

vec2 path(float z) {
    return vec2(0.85 * sin(z * 0.115), 0.65 * cos(z * 0.094));
}

vec3 firePal(float t) {
    t = clamp(t, 0.0, 1.0);
    return vec3(pow(t, 0.55), pow(t, 1.7), pow(t, 3.6)) * 1.25;
}

vec3 cosmicPal(float t) {
    t = clamp(t, 0.0, 1.0);
    vec3 c = vec3(pow(t, 1.9) * 0.95, pow(t, 2.6) * 0.75, pow(t, 0.7)) * 1.2;
    c += pow(t, 2.0) * vec3(0.35, 0.0, 0.28);
    return c;
}

float density(vec3 p, out float temp) {
    vec2 q = p.xy - path(p.z);
    float r = length(q);
    float ang = atan(q.y, q.x);
    float R = 1.55;
    float shell = exp(-pow((r - R) * 3.4, 2.0));
    float arms = pow(0.5 + 0.5 * sin(ang * 5.0 + p.z * 2.2 - uTime * 1.1), 1.8);
    arms = 0.2 + 0.8 * arms;
    float n = fbm(vec3(q * 2.1, p.z * 1.1) + vec3(0.0, 0.0, -uTime * 0.55));
    n = pow(max(n - 0.36, 0.0) * 2.1, 1.6);
    float det = vnoise(vec3(q * 6.5, p.z * 3.2) + vec3(0.0, 0.0, -uTime * 1.1));
    float d = shell * arms * n * (0.5 + 1.3 * det) * 3.4;
    temp = clamp(1.12 - (r / R) * 0.72, 0.05, 1.0) * (0.65 + 0.7 * det);
    return d;
}

vec3 sparkLayer(vec2 uv, float scale, float speed, float seed, float morphMix) {
    float ang = atan(uv.y, uv.x) + seed;
    float r = length(uv) + 0.06;
    float row = floor(1.4 / r - uCamZ * speed);
    vec2 pc = vec2(ang / 6.2832 * scale + hash13(vec3(row, seed, 5.0)) * 17.3,
                   1.4 / r - uCamZ * speed);
    vec2 cell = floor(pc), f = fract(pc);
    float h1 = hash13(vec3(cell, seed));
    float h2 = hash13(vec3(cell, seed + 40.0));
    vec2 o = vec2(0.3 + 0.4 * h1, 0.34 + 0.32 * h2);
    vec2 dv = f - o;
    dv.y *= 0.5;
    float dot2 = exp(-dot(dv, dv) * 120.0);
    float tw = pow(hash13(vec3(cell, seed + 80.0)), 5.0) * 2.4;
    float fade = smoothstep(0.05, 0.30, length(uv));
    vec3 col = mix(vec3(1.0, 0.72, 0.35), vec3(0.75, 0.62, 1.0), morphMix);
    return dot2 * tw * fade * col;
}

vec3 world(vec2 uv01, float morph) {
    // roll a fraction of the tunnel roll into the footage so both move together
    vec2 c = uv01 - 0.5;
    float wr = uRoll * 0.3;
    c = mat2(cos(wr), -sin(wr), sin(wr), cos(wr)) * c;
    // warp punch on cuts: zoom + radial chromatic split
    float k = exp(-uCut * 8.0);
    float zoom = 1.07 + 0.06 * k + 0.02 * uPhi;
    // heat shimmer from the tunnel's own noise field
    vec2 shim = vec2(
        fbm(vec3(uv01 * 3.1, uTime * 0.55)) - 0.5,
        fbm(vec3(uv01 * 3.1 + 7.7, uTime * 0.55)) - 0.5)
        * (0.004 + 0.016 * uPhi) * (0.5 + 0.9 * uPulse);
    float ca = 0.0035 * k + 0.0022 * uPhi;
    vec2 base = c / zoom + 0.5 + shim;
    vec2 dir = normalize(c + 1e-6);
    vec3 w;
    w.r = texture(uSrc, vec2(base.x, 1.0 - base.y) + dir * ca).r;
    w.g = texture(uSrc, vec2(base.x, 1.0 - base.y)).g;
    w.b = texture(uSrc, vec2(base.x, 1.0 - base.y) - dir * ca).b;
    // grade: golden lift rising with phi, shadows drift violet
    float luma = dot(w, vec3(0.299, 0.587, 0.114));
    w = mix(w, w * vec3(1.14, 1.02, 0.80), 0.12 + 0.30 * morph);
    w += pow(1.0 - luma, 2.2) * vec3(0.10, 0.02, 0.16) * uPhi;
    // linearize: footage is sRGB, but the composite + tonemap happen in linear
    return pow(max(w, 0.0), vec3(2.2)) * 1.4;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;
    vec2 uv01 = gl_FragCoord.xy / uRes;
    float cr = cos(uRoll), sr = sin(uRoll);
    vec2 tuv = mat2(cr, -sr, sr, cr) * uv;

    float morph = smoothstep(0.55, 0.90, uPhi);
    float hole = smoothstep(0.80, 0.97, uPhi);

    // tunnel march (identical field to the dream-portal renderer)
    float cz = uCamZ;
    vec3 ro = vec3(path(cz) * 0.82 + 0.14 * vec2(cos(uTime * 0.33), sin(uTime * 0.26)), cz);
    vec3 target = vec3(path(cz + 2.4) * 0.92, cz + 2.4);
    vec3 fwd = normalize(target - ro);
    vec3 right = normalize(cross(fwd, vec3(0.0, 1.0, 0.0)));
    vec3 up = cross(right, fwd);
    vec3 rd = normalize(tuv.x * right + tuv.y * up + 1.12 * fwd);

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

    vec3 pf = ro + rd * 7.5;
    float rf = length(pf.xy - path(pf.z));
    float g = exp(-rf * rf * 9.5);
    float halo = exp(-rf * rf * 2.4);

    // the real world, graded into the same universe; daylight sinks toward
    // portal-dusk as immersion rises so the embers glow against it
    vec3 w = world(uv01, morph);
    w *= mix(1.0, 0.32, smoothstep(0.25, 0.82, uPhi));

    // volumetric composite: the world is seen THROUGH the tunnel medium.
    // Its emission fades in with phi; the march's own transmittance dims the
    // world where the ember walls thicken. The bore protects the subject.
    float bore = exp(-dot(uv, uv) * (2.6 + 2.2 * uPhi));
    float tunnelVis = 0.15 + 1.25 * uPhi;
    float through = mix(1.0, max(T, bore * 0.85), uPhi * 0.95);
    vec3 col = acc * tunnelVis + w * through;
    // finale: the world falls into the horizon disc
    col = mix(col, mix(acc, w, smoothstep(0.35, 0.75, g)), hole);

    // ember light-wrap: portal light spills onto the world's edges
    float edge = 1.0 - bore;
    vec3 wrapCol = mix(vec3(1.0, 0.55, 0.18), vec3(0.65, 0.42, 1.0), morph);
    col += wrapCol * edge * (0.03 + 0.12 * uPhi) * (0.6 + 0.9 * uPulse) * through;

    // core glow + halo breathe over everything (subtle until immersion rises)
    float flare = (0.55 + 0.65 * uPulse) * (0.2 + 0.8 * uPhi);
    vec3 coreCol = mix(vec3(1.0, 0.88, 0.66) * 1.7,
                       vec3(0.72, 0.5, 1.05) * 1.4, morph);
    col += g * (1.0 - hole) * coreCol * flare * (1.0 - through * 0.55);
    col += halo * (1.0 - hole) * mix(vec3(1.0, 0.5, 0.14), vec3(0.8, 0.4, 1.0), morph)
           * flare * 0.18 * (1.0 - through * 0.4);
    // event horizon: dark disc rim, world dims inside as it crosses over
    float rim = smoothstep(0.12, 0.42, g) * (1.0 - smoothstep(0.55, 0.9, g));
    col += hole * rim * mix(vec3(1.0, 0.55, 0.2), vec3(1.0, 0.45, 0.75), morph) * 1.6 * flare;
    col *= 1.0 - hole * smoothstep(0.5, 0.95, g) * 0.55;

    // one shared spark field over world and tunnel alike
    float sparkAmp = (0.30 + 0.55 * uPhi) * (0.55 + 0.55 * uPulse);
    col += sparkLayer(uv, 14.0, 0.55, 3.0, morph) * 1.0 * sparkAmp;
    col += sparkLayer(uv, 24.0, 0.95, 17.0, morph) * 0.7 * sparkAmp;
    col += sparkLayer(uv, 38.0, 1.55, 29.0, morph) * 0.45 * sparkAmp;

    // shared tonemap = shared film response
    col = col * 1.35 / (1.0 + col);
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


def phi_curve(mode: str, env: np.ndarray, fps: int) -> np.ndarray:
    n = len(env)
    tt = np.arange(n) / max(n - 1, 1)
    if mode == "ramp":
        phi = tt ** 1.15
    elif mode == "breath":
        smooth = np.convolve(np.minimum(env, 1.0), np.ones(fps) / fps, mode="same")
        phi = 0.62 * tt + 0.30 * smooth
    elif mode == "rush":
        phi = np.minimum(1.0, 0.30 + 0.62 * tt + 0.22 * np.minimum(env, 1.0))
    else:
        raise ValueError(mode)
    # every version lands the event-horizon finale
    floor = np.clip((tt - 0.86) / 0.12, 0.0, 1.0) * 0.97
    return np.clip(np.maximum(phi, floor), 0.0, 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--audio", type=Path, required=True)
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--dur", type=float, required=True)
    ap.add_argument("--cuts", type=str, default="")
    ap.add_argument("--phi", choices=["ramp", "breath", "rush"], default="ramp")
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
    src_tex = ctx.texture((args.w, args.h), 3)
    src_tex.use(0)
    prog["uSrc"].value = 0

    env = onset_env(args.audio, args.start, args.dur, args.fps)
    phi = phi_curve(args.phi, env, args.fps)
    cuts = sorted(float(c) for c in args.cuts.split(",") if c.strip())
    n = len(env)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    silent = args.out.with_suffix(".silent.mp4")

    dec = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(args.base),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{args.w}x{args.h}",
         "-r", str(args.fps), "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{args.w}x{args.h}",
         "-r", str(args.fps), "-i", "-",
         "-vf", "vflip", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)

    frame_bytes = args.w * args.h * 3
    cam_z, roll = 0.0, 0.0
    dt = 1.0 / args.fps
    last = np.zeros(frame_bytes, dtype=np.uint8).tobytes()
    for i in range(n):
        raw = dec.stdout.read(frame_bytes)
        if raw and len(raw) == frame_bytes:
            last = raw
        src_tex.write(last)
        p = float(env[i])
        tnow = i * dt
        cam_z += dt * (1.15 + 1.0 * p)
        roll += dt * 0.09
        past = [tnow - c for c in cuts if c <= tnow + 1e-6]
        since = min(past) if past else 99.0
        prog["uTime"].value = tnow
        prog["uCamZ"].value = cam_z
        prog["uPulse"].value = min(p, 1.0)
        prog["uRoll"].value = roll
        prog["uPhi"].value = float(phi[i])
        prog["uCut"].value = since
        vao.render()
        enc.stdin.write(fbo.read(components=3))
        if i % 120 == 0:
            print(f"frame {i}/{n} phi={phi[i]:.2f}")
    dec.stdout.close()
    enc.stdin.close()
    dec.wait()
    enc.wait()

    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(silent),
         "-ss", f"{args.start:.3f}", "-t", f"{args.dur:.3f}", "-i", str(args.audio),
         "-af", f"afade=t=in:st=0:d=0.05,afade=t=out:st={args.dur - 0.25:.3f}:d=0.25",
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
         "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(args.out)],
        check=True)
    silent.unlink()
    print(f"BUILT {args.out}")


if __name__ == "__main__":
    main()
