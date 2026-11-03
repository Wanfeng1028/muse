#!/usr/bin/env python3
"""Hyper Space Jump — infinite-zoom starburst tunnel (Justtripit reference).

Reference: "Hyper Space Jump" FB reel (Justtripit, #opticalart): alternating
electric-blue and fire starburst bands blasting outward from an op-art
concentric-ring core, full-frame radial light-speed streaks, continuous
zoom-into-the-tunnel. This build adds the house multi-band audio drive:

  1. Log-polar band field: color bands are uniform in log(r) and scroll
     outward, so they nest infinitely toward the center — the op-art iris
     is the same field compressing below pixel scale, crossfaded to an
     explicit ring pattern at the core.
  2. Radial streaks: periodic 1D value-noise fbm along angle, per-band
     offset, displacing the band edges outward for the flame-tip look.
  3. Multi-band drive: onsets -> punch-zoom + white-hot streak flash +
     flow/rotation kicks + chromatic fringe; bass -> core bloom + inner
     edge heat; energy -> tunnel speed.
  4. Beat-scripted timeline: palette set A (blue/fire) morphs to set B
     (violet/gold overdrive) at the second drop; breakdown goes airy
     deep-space (dim, teal-violet, slow).
  5. Emissive-only shading (no relief — reference is pure light on black).

Usage:
  render_hyper_space_jump.py --still --t 3.0 --out still.png
  render_hyper_space_jump.py --audio mushroom_drift.mp3 --start 61.637 \
      --dur 26.35 --out hyper_space_jump.mp4
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np

VERT = "#version 330\nin vec2 in_pos;\nvoid main(){gl_Position=vec4(in_pos,0.0,1.0);}"

FRAG = """
#version 330
out vec4 fragColor;
uniform vec2  uRes;
uniform float uTime;
uniform float uPulse;    // onset envelope, fast attack
uniform float uBass;     // bass RMS, smoothed
uniform float uFlow;     // integrated tunnel scroll (band units)
uniform float uRot;      // integrated rotation (kicked by onsets)
uniform float uPal;      // 0 = classic blue/fire, 1 = violet/gold overdrive
uniform float uAir;      // 1 = airy breakdown grade
uniform float uStreak;   // streak contrast gain
#define PI 3.14159265359

float hash11(float p){return fract(sin(p*127.1)*43758.5453);}
float hash21(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}

// periodic 1D value noise (lattice wrapped so the angular seam is invisible)
float vnoise(float x, float period){
    float i=floor(x), f=fract(x);
    float u=f*f*(3.0-2.0*f);
    return mix(hash11(mod(i,period)), hash11(mod(i+1.0,period)), u);
}

// radial light-speed streaks: fbm along angle, decorrelated per band ring
float streaks(float a, float ri, float r){
    float x=a/(2.0*PI);
    float s=0.55*vnoise(x*160.0+hash11(ri)*160.0,160.0)
           +0.30*vnoise(x*331.0+hash11(ri+7.0)*331.0,331.0)
           +0.15*vnoise(x*641.0+hash11(ri+13.0)*641.0,641.0)
                 *smoothstep(0.02,0.06,r);   // finest octave aliases at core
    return s;
}

vec3 grad4(float t, vec3 c0, vec3 c1, vec3 c2, vec3 c3){
    t=clamp(t,0.0,1.0)*3.0;
    if(t<1.0) return mix(c0,c1,t);
    if(t<2.0) return mix(c1,c2,t-1.0);
    return mix(c2,c3,t-2.0);
}

vec3 field(vec2 uv){
    float r=length(uv)+1e-5;
    float a=atan(uv.y,uv.x)+uRot;
    float lr=log(r);

    // one band period = wide starburst field + black moat + fire ring + moat
    const float BF=1.15;                      // band pairs per log-unit
    float band=lr*BF-uFlow;
    float ri=floor(band);
    float st=streaks(a,ri,r);
    float x=fract(band+(st-0.5)*0.13);        // streak-ragged edges / flame tips

    float stv=mix(0.06,1.0,pow(clamp(st,0.0,1.0),1.5+0.7*uStreak));
    vec3 col=vec3(0.0);
    if(x<0.52){                               // wide starburst field (blue -> violet)
        float t=x/0.52;
        vec3 A=grad4(t, vec3(0.75,0.93,1.00), vec3(0.22,0.58,1.00),
                        vec3(0.04,0.20,0.88), vec3(0.00,0.02,0.22));
        vec3 B=grad4(t, vec3(0.90,0.82,1.00), vec3(0.55,0.32,1.00),
                        vec3(0.26,0.05,0.82), vec3(0.04,0.00,0.18));
        float env=mix(1.0,0.45,t)*smoothstep(0.0,0.035,t)*(1.0-smoothstep(0.90,1.0,t));
        col=mix(A,B,uPal)*stv*env*1.5;
        col+=vec3(0.90,0.98,1.0)*pow(1.0-t,7.0)*stv*(0.55+0.6*uBass); // hot inner rim
    }else if(x>=0.60&&x<0.86){                // fire ring accent (fire -> gold/magenta)
        float t=(x-0.60)/0.26;
        vec3 A=grad4(t, vec3(1.00,0.98,0.75), vec3(1.00,0.78,0.10),
                        vec3(0.98,0.33,0.02), vec3(0.30,0.01,0.00));
        vec3 B=grad4(t, vec3(1.00,0.99,0.88), vec3(1.00,0.83,0.25),
                        vec3(1.00,0.22,0.50), vec3(0.25,0.00,0.20));
        float env=smoothstep(0.0,0.06,t)*(1.0-smoothstep(0.45,1.0,t));
        col=mix(A,B,uPal)*stv*env*2.0;
        col+=vec3(1.0,0.90,0.55)*pow(1.0-t,6.0)*stv*(0.7+0.9*uBass);
    }
    // airy breakdown grade: dim pale deep-space ice
    float lum=dot(col,vec3(0.299,0.587,0.114));
    col=mix(col, vec3(0.55,0.75,0.95)*lum*1.25, uAir*0.6);

    // white-hot streak flash on hits (only where already lit)
    col+=vec3(1.0,0.97,0.90)*pow(stv,3.0)*lum*uPulse*1.2;

    // op-art iris: explicit concentric rings crossfaded in at the core
    float irisMix=1.0-smoothstep(0.010,0.048,r);
    if(irisMix>0.001){
        float ringT=0.5+0.5*cos(r*(2.0*PI/0.009)-uFlow*2.0);
        vec3 hot=mix(vec3(0.95,0.98,1.00),
                     mix(vec3(0.35,0.65,1.0),vec3(0.75,0.45,1.0),uPal),0.35);
        vec3 irisCol=mix(vec3(0.01,0.01,0.05), hot, pow(ringT,3.0));
        irisCol*=smoothstep(0.0035,0.0060,r);          // dark pupil
        irisCol+=vec3(1.0)*exp(-abs(r-0.0068)*900.0)*0.7; // pupil rim
        col=mix(col,irisCol,irisMix);
    }

    // bass bloom radiating from the core
    col+=mix(vec3(0.35,0.55,1.0),vec3(0.9,0.55,1.0),uPal)
         *exp(-r*6.5)*uBass*0.45*(1.0-irisMix*0.6);
    return col;
}

void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
    uv*=(1.0-0.060*uPulse-0.022*uBass);       // punch-zoom + bass breath
    float ca=0.0018+0.0080*uPulse*uPulse;     // fringe spikes on hits
    vec3 col;
    col.r=field(uv*(1.0-ca)).r;
    col.g=field(uv).g;
    col.b=field(uv*(1.0+ca)).b;

    col*=1.0+0.40*uPulse;                     // hit flash
    col*=1.0-0.52*smoothstep(0.22,1.10,dot(uv,uv));  // vignette
    float luma=dot(col,vec3(0.299,0.587,0.114));
    col=clamp(mix(vec3(luma),col,1.34),0.0,4.0);     // saturation punch
    col=col/(1.0+0.18*col);                   // soft highlight rolloff
    float g=hash21(gl_FragCoord.xy+fract(uTime)*vec2(31.7,17.3))-0.5;
    col+=g*0.022;                             // film grain
    col=clamp(col,0.0,1.0);
    col=pow(col,vec3(0.4545));
    fragColor=vec4(col,1.0);
}
"""


def envelopes(audio: Path, start: float, dur: float, fps: int):
    """Per-frame onset pulse, bass RMS, and overall energy envelopes."""
    import librosa
    pad = 1.0 if start >= 1.0 else 0.0
    y, sr = librosa.load(str(audio), sr=22050, mono=True,
                         offset=start - pad, duration=dur + 2.0)
    hop = 512
    n = int(round(dur * fps))
    tf = np.arange(n) / fps

    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    tt = librosa.times_like(env, sr=sr, hop_length=hop) - pad
    e = np.interp(tf, tt, env)
    e = e / (np.percentile(e, 95) + 1e-6)
    pulse = np.zeros_like(e)
    decay = np.exp(-1.0 / (fps * 0.20))
    acc = 0.0
    for i, v in enumerate(e):
        acc = max(v, acc * decay)
        pulse[i] = acc
    pulse = np.clip(pulse, 0.0, 1.5)

    a = np.exp(-2.0 * np.pi * 150.0 / sr)
    lo = y.copy()
    for _ in range(2):
        out = np.empty_like(lo)
        z = 0.0
        for i, v in enumerate(lo):
            z = (1 - a) * v + a * z
            out[i] = z
        lo = out
    rms = librosa.feature.rms(y=lo, frame_length=2048, hop_length=hop)[0]
    tr = librosa.times_like(rms, sr=sr, hop_length=hop) - pad
    b = np.interp(tf, tr, rms)
    b = b / (np.percentile(b, 97) + 1e-6)
    bass = np.zeros_like(b)
    dk = np.exp(-1.0 / (fps * 0.12))
    acc = 0.0
    for i, v in enumerate(b):
        acc = max(v, acc * dk)
        bass[i] = acc
    bass = np.clip(bass, 0.0, 1.2)

    rms_a = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    energy = np.interp(tf, librosa.times_like(rms_a, sr=sr, hop_length=hop) - pad, rms_a)
    energy = np.clip(energy / (np.percentile(energy, 95) + 1e-6), 0.0, 1.3)
    return pulse, bass, energy


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0 + 1e-9), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def timeline(n: int, fps: int, script: list[dict], keys=("pal", "air", "tunnel", "streak")):
    """Piecewise scalar schedule -> per-frame arrays, eased over `glide` sec."""
    tf = np.arange(n) / fps
    out = {k: np.full(n, script[0][k], dtype=np.float64) for k in keys}
    for k0, k1 in zip(script, script[1:]):
        seg = tf >= k1["t"]
        g = max(k1.get("glide", 0.15), 1e-3)
        u = smoothstep(k1["t"], k1["t"] + g, tf)
        for k in keys:
            out[k][seg] = (k0[k] + (k1[k] - k0[k]) * u)[seg]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--still", action="store_true")
    ap.add_argument("--t", type=float, default=3.0, help="still: seconds into window")
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--start", type=float, default=61.637)
    ap.add_argument("--dur", type=float, default=26.35)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    args = ap.parse_args()

    # beat-scripted timeline for mushroom_drift @ 61.637 (t = sec into window):
    # 0.00 drop-in S17 / 4.46 peak run S18-S23 / 16.61 breakdown S24 /
    # 21.88 second jump S25 (hardest section, 10 primary cuts) / end 26.35 = S25 out
    SCRIPT = [
        {"t": 0.00,  "pal": 0.00, "air": 0.0, "tunnel": 1.00, "streak": 0.85},
        {"t": 4.46,  "pal": 0.12, "air": 0.0, "tunnel": 1.30, "streak": 1.00, "glide": 0.40},
        {"t": 16.61, "pal": 0.35, "air": 1.0, "tunnel": 0.35, "streak": 0.55, "glide": 0.80},
        {"t": 21.88, "pal": 1.00, "air": 0.0, "tunnel": 1.55, "streak": 1.15, "glide": 0.15},
    ]

    import moderngl
    ctx = moderngl.create_standalone_context()
    prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
    quad = ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], dtype="f4").tobytes())
    vao = ctx.vertex_array(prog, [(quad, "2f", "in_pos")])
    w, h = ((540, 960) if args.still else (args.w, args.h))
    rw, rh = w * 2, h * 2
    fbo = ctx.framebuffer(color_attachments=[ctx.texture((rw, rh), 3)])
    fbo.use()
    prog["uRes"].value = (float(rw), float(rh))

    def set_frame(i, dt, pulse, bass, flow, rot, pal, air, streak):
        prog["uTime"].value = i * dt
        prog["uPulse"].value = float(min(pulse, 1.0))
        prog["uBass"].value = float(min(bass, 1.0))
        prog["uFlow"].value = float(flow)
        prog["uRot"].value = float(rot)
        prog["uPal"].value = float(pal)
        prog["uAir"].value = float(air)
        prog["uStreak"].value = float(streak)

    if args.still:
        n = int(args.t * args.fps) + 1
        tl = timeline(n, args.fps, SCRIPT)
        i = n - 1
        # plausible mid-song state for art direction
        set_frame(i, 1.0 / args.fps, 0.55, 0.6, args.t * 0.9, args.t * 0.04,
                  tl["pal"][i], tl["air"][i], tl["streak"][i])
        vao.render()
        img = np.flipud(np.frombuffer(fbo.read(components=3), dtype=np.uint8).reshape(rh, rw, 3))
        from PIL import Image
        args.out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(img).resize((w, h), Image.LANCZOS).save(args.out)
        print(f"STILL {args.out}")
        return

    assert args.audio
    pulse, bass, energy = envelopes(args.audio, args.start, args.dur, args.fps)
    n = len(pulse)
    tl = timeline(n, args.fps, SCRIPT)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    silent = args.out.with_suffix(".silent.mp4")
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{rw}x{rh}",
         "-r", str(args.fps), "-i", "-",
         "-vf", f"vflip,scale={w}:{h}:flags=lanczos",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)
    dt = 1.0 / args.fps
    flow = 0.0
    rot = 0.0
    for i in range(n):
        flow += dt * tl["tunnel"][i] * (0.35 + 0.75 * float(energy[i]) + 0.90 * float(pulse[i]) ** 2)
        rot += dt * (0.03 + 0.22 * float(pulse[i]))
        set_frame(i, dt, pulse[i], bass[i], flow, rot,
                  tl["pal"][i], tl["air"][i], tl["streak"][i])
        vao.render()
        ff.stdin.write(fbo.read(components=3))
        if i % 150 == 0:
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
