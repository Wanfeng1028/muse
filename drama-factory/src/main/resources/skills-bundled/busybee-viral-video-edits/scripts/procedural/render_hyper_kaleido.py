#!/usr/bin/env python3
"""Hyper Kaleido — beat-scripted kaleidoscope tunnel, the "sicker" mandala.

Reference: Leodigiart-style FB kaleidoscope reels (flat mandala, slow color
drift, no beat lock). This one keeps the relief-lit embossed look from
render_mandala.py and adds everything the reference lacks:

  1. Log-polar TUNNEL: rings live in log(r) space and scroll toward the
     viewer, so the mandala has depth — you fall into it.
  2. Multi-band drive: onsets -> shockwave + punch-zoom + rotation kicks,
     bass RMS -> breathing, energy -> tunnel speed.
  3. Beat-scripted timeline: fold count MORPHS at the song's section
     boundaries (drop / breakdown / second drop), palette rotates with it.
  4. True chromatic aberration: the field is shaded 3x with radially
     offset uv per channel; fringe amount spikes on hits.
  5. Relief lighting + specular + film grain for the physical look.

Usage:
  render_hyper_kaleido.py --still --t 3.0 --out still.png
  render_hyper_kaleido.py --audio mushroom_drift.mp3 --start 81.92 --dur 22 \
      --out hyper_kaleido.mp4
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
uniform float uFlow;     // integrated tunnel scroll
uniform float uRot;      // integrated rotation (kicked by onsets)
uniform float uFoldA;    // fold count A
uniform float uFoldB;    // fold count B
uniform float uFoldMix;  // 0..1 morph between folds
uniform float uPal;      // palette rotation
uniform float uAir;      // 1 = airy breakdown look, 0 = dense drop look
#define PI 3.14159265359

float hash11(float p){return fract(sin(p*127.1)*43758.5453);}
float hash21(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}

// iq cosine palette tuned psychedelic: ink blue -> UV violet -> magenta -> amber
vec3 pal(float t){
    return vec3(0.52,0.42,0.48) + vec3(0.48,0.42,0.45)*cos(2.0*PI*(vec3(1.0,0.94,0.82)*t + vec3(0.62,0.36,0.13)));
}

float motif(vec2 c, float ri){
    float m=mod(ri,5.0);
    if(m<1.0){                               // concentric diamonds
        float d=abs(c.x)+abs(c.y);
        return (0.5+0.5*cos(d*14.0))*(1.0-smoothstep(0.40,0.5,d));
    } else if(m<2.0){                        // beads
        float d=length(c*vec2(1.15,1.0));
        return (0.5+0.5*cos(d*16.0))*(1.0-smoothstep(0.30,0.46,d));
    } else if(m<3.0){                        // petals
        float d=length(vec2(c.x*2.1,c.y*1.05));
        return (0.55+0.45*cos(c.y*7.0))*(1.0-smoothstep(0.30,0.44,d));
    } else if(m<4.0){                        // gill fins (mushroom): thin radial ridges
        return (0.5+0.5*cos(c.x*34.0))*(1.0-smoothstep(0.32,0.5,abs(c.y)*1.6));
    } else {                                 // zigzag
        return 0.5+0.5*cos((c.x*2.0+abs(c.y))*14.0);
    }
}

// height of the kaleido tunnel for one fold count
float heightN(vec2 uv, float N, out float ringIdx){
    float r=length(uv)+1e-4;
    float aFull=atan(uv.y,uv.x)+uRot;
    // scallop: rings are star-shaped, not circles -> the kaleido silhouette
    r*=1.0+0.085*cos(aFull*N)*smoothstep(0.04,0.30,r);
    float a=aFull;
    float sec=2.0*PI/N;
    a=mod(a,sec); a=abs(a-sec*0.5);          // mirrored wedge
    float lr=log(r);                          // log-polar: proper tunnel depth
    float ring=lr*2.5+uFlow;                  // + : cells scroll toward viewer
    float ri=floor(ring), rf=fract(ring)-0.5;
    ringIdx=ri;
    float nm=floor(1.0+2.0*hash11(mod(ri,64.0)));
    float th=a/sec*nm+ri*0.5;
    vec2 c=vec2(fract(th)-0.5, rf);
    float h=motif(c,ri);
    h+=0.05*sin(lr*46.0)*sin(th*22.0);        // fine weave
    return h;
}

float height(vec2 uv, out float ringIdx){
    float riA, riB;
    float hA=heightN(uv,uFoldA,riA);
    float hB=heightN(uv,uFoldB,riB);
    ringIdx=mix(riA,riB,step(0.5,uFoldMix));
    float h=mix(hA,hB,uFoldMix);
    // spore core: petaled medallion breathing with bass
    float r=length(uv);
    float aFull=atan(uv.y,uv.x)+uRot*1.6;
    float pet=10.0;
    float rose=(0.5+0.5*cos(r*(52.0-14.0*uBass)))*(0.55+0.45*cos(aFull*pet));
    float cz=1.0-smoothstep(0.05,0.15+0.05*uBass,r);
    return mix(h,rose,cz);
}

vec3 shade(vec2 uv){
    float ri;
    float h=height(uv,ri);
    float K=6.0;
    vec3 n=normalize(vec3(-dFdx(h)*K*uRes.y, -dFdy(h)*K*uRes.y, 1.0));
    vec3 ldir=normalize(vec3(-0.45,0.55,0.75));
    float dif=max(dot(n,ldir),0.0)*0.85+0.15;
    float spec=pow(max(dot(reflect(-ldir,n),vec3(0.0,0.0,1.0)),0.0),24.0);

    float r=length(uv);
    // three ring families: deep ink relief / gilded relief / NEON (self-lit)
    float fam=mod(ri,3.0);
    vec3 base=pal(ri*0.09+uPal);
    vec3 gold=mix(vec3(0.30,0.18,0.07), mix(vec3(0.91,0.70,0.29),vec3(0.97,0.90,0.75),
               smoothstep(0.6,1.0,h)), smoothstep(0.05,0.85,h));
    vec3 ink=mix(base*0.05, base*(0.45+0.85*h), smoothstep(0.10,0.95,h));
    vec3 col=ink;
    if(fam>=1.0&&fam<2.0) col=mix(ink,gold,0.6-0.3*uAir);
    col=col*dif + vec3(1.0,0.92,0.75)*spec*(0.45+0.4*uBass);
    if(fam>=2.0){
        // neon tube ring: emissive, breathes with bass, ignores most shading
        vec3 neon=pal(ri*0.13+uPal+0.5);
        col=ink*dif*0.35 + neon*pow(h,2.6)*(1.5+1.6*uBass);
    }
    // airy breakdown: moonlit pale glow, still dark-backed
    col=mix(col, vec3(0.55,0.78,0.85)*pow(h,1.8)*(1.1+0.6*uBass), uAir*0.5);

    // shockwave: ring of light rolling outward on hits
    float wavePos=mod(uFlow*0.42,2.4);
    float wave=exp(-abs(r-wavePos)*6.0)*uPulse;
    col*=1.0+0.95*wave;
    col+=pal(uPal+0.45)*wave*0.22;

    // bass bloom in the core
    col+=pal(uPal+0.1)*exp(-r*5.5)*uBass*0.55;
    return col;
}

void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
    uv*=(1.0-0.055*uPulse-0.028*uBass);       // punch-zoom + bass breath
    // true chromatic aberration: per-channel radial scale, spikes on hits
    float ca=0.0016+0.0075*uPulse*uPulse;
    vec3 col;
    col.r=shade(uv*(1.0-ca)).r;
    col.g=shade(uv).g;
    col.b=shade(uv*(1.0+ca)).b;

    col*=1.0-0.62*smoothstep(0.15,1.0,dot(uv,uv));  // deep vignette
    // saturation punch
    float luma=dot(col,vec3(0.299,0.587,0.114));
    col=clamp(mix(vec3(luma),col,1.32),0.0,4.0);
    // soft highlight rolloff instead of hard clip
    col=col/(1.0+0.18*col);
    // film grain
    float g=hash21(gl_FragCoord.xy+fract(uTime)*vec2(31.7,17.3))-0.5;
    col+=g*0.025;
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

    # bass: RMS of a 150 Hz low-pass (single-pole applied twice)
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


def timeline(n: int, fps: int, script: list[dict]):
    """Piecewise fold/palette/tunnel schedule -> per-frame arrays.

    script: list of {t, fold, pal, air, tunnel, glide} keyframes; fold morphs
    over `glide` seconds after each keyframe, everything else eases the same.
    """
    tf = np.arange(n) / fps
    foldA = np.full(n, script[0]["fold"], dtype=np.float64)
    foldB = np.full(n, script[0]["fold"], dtype=np.float64)
    mix = np.zeros(n)
    palv = np.full(n, script[0]["pal"], dtype=np.float64)
    air = np.full(n, script[0]["air"], dtype=np.float64)
    tun = np.full(n, script[0]["tunnel"], dtype=np.float64)
    for k0, k1 in zip(script, script[1:]):
        seg = tf >= k1["t"]
        g = max(k1.get("glide", 0.15), 1e-3)
        u = smoothstep(k1["t"], k1["t"] + g, tf)
        foldA[seg] = k0["fold"]
        foldB[seg] = k1["fold"]
        mix[seg] = u[seg]
        palv[seg] = (k0["pal"] + (k1["pal"] - k0["pal"]) * u)[seg]
        air[seg] = (k0["air"] + (k1["air"] - k0["air"]) * u)[seg]
        tun[seg] = (k0["tunnel"] + (k1["tunnel"] - k0["tunnel"]) * u)[seg]
    # collapse finished morphs so the next segment starts clean
    done = mix >= 0.999
    foldA[done] = foldB[done]
    mix[done] = 0.0
    return foldA, foldB, mix, palv, air, tun


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--still", action="store_true")
    ap.add_argument("--t", type=float, default=3.0, help="still: seconds into window")
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--start", type=float, default=81.92)
    ap.add_argument("--dur", type=float, default=22.0)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    args = ap.parse_args()

    # beat-scripted timeline for mushroom_drift @ 81.92 (t = sec into window):
    # 0.79 drop1 / 6.07 breakdown / 8.89 drop2 / 19.84 tail
    SCRIPT = [
        {"t": 0.00, "fold": 6.0,  "pal": 0.00, "air": 0.0, "tunnel": 0.35},
        {"t": 0.79, "fold": 12.0, "pal": 0.33, "air": 0.0, "tunnel": 1.00, "glide": 0.14},
        {"t": 6.07, "fold": 8.0,  "pal": 0.62, "air": 1.0, "tunnel": 0.42, "glide": 0.45},
        {"t": 8.89, "fold": 16.0, "pal": 0.95, "air": 0.0, "tunnel": 1.15, "glide": 0.14},
        {"t": 19.84, "fold": 12.0, "pal": 1.20, "air": 0.25, "tunnel": 0.50, "glide": 0.8},
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

    def set_frame(i, dt, pulse, bass, flow, rot, fA, fB, mx, pv, av):
        prog["uTime"].value = i * dt
        prog["uPulse"].value = float(min(pulse, 1.0))
        prog["uBass"].value = float(min(bass, 1.0))
        prog["uFlow"].value = float(flow)
        prog["uRot"].value = float(rot)
        prog["uFoldA"].value = float(fA)
        prog["uFoldB"].value = float(fB)
        prog["uFoldMix"].value = float(mx)
        prog["uPal"].value = float(pv)
        prog["uAir"].value = float(av)

    if args.still:
        n = int(args.t * args.fps) + 1
        fA, fB, mx, pv, av, tun = timeline(n, args.fps, SCRIPT)
        i = n - 1
        # plausible mid-song state for art direction
        set_frame(i, 1.0 / args.fps, 0.55, 0.6, args.t * 0.9, args.t * 0.1,
                  fA[i], fB[i], mx[i], pv[i], av[i])
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
    fA, fB, mx, pv, av, tun = timeline(n, args.fps, SCRIPT)
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
        flow += dt * tun[i] * (0.45 + 1.15 * float(energy[i]))
        rot += dt * (0.05 + 0.55 * float(pulse[i]) * 0.5)
        set_frame(i, dt, pulse[i], bass[i], flow, rot, fA[i], fB[i], mx[i], pv[i], av[i])
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
