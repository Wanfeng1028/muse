#!/usr/bin/env python3
"""Footage FX — real clips through the audio-reactive shader machine.

Instead of generating the image from math, the GPU warps REAL footage:
  beat_kaleido  - the clip folded into a live kaleidoscope, punch on hits
  echo_trails   - video feedback: ghosts of the last frames trail motion
  time_ripple   - per-pixel time travel: rings of the image play at
                  different delays from a 24-frame history buffer
  prism_glitch  - RGB channel splits + slice displacement on onsets
  neon_halftone - the clip re-rendered as glowing print dots on black

One continuous source clip + one continuous stretch of the song;
treatment switches every 3 bars. Every treatment reads the onset
envelope, so the warp itself is beat-locked.

Usage:
  footage_fx.py --src clip.mp4 --src-start 20 --audio song.mp3 \
      --start 81.92 --out outputs/procedural/footage_fx
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np

FONT = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"
BPM = 143.55
BAR = 4 * 60.0 / BPM
HIST = 24
MODES = ["beat_kaleido", "echo_trails", "time_ripple", "prism_glitch", "neon_halftone"]

VERT = "#version 330\nin vec2 in_pos;\nvoid main(){gl_Position=vec4(in_pos,0.0,1.0);}"

FRAG = """
#version 330
out vec4 fragColor;
uniform vec2  uRes;
uniform float uTime;
uniform float uPulse;
uniform float uFlow;
uniform int   uMode;
uniform int   uHead;          // newest layer in the history ring
uniform sampler2D uSrc;       // current source frame
uniform sampler2D uPrev;      // previous OUTPUT frame (feedback)
uniform sampler2DArray uHist; // last 24 source frames
#define PI 3.14159265359

float hash21(vec2 p){p=fract(p*vec2(123.34,456.21)); p+=dot(p,p+45.32); return fract(p.x*p.y);}
mat2 rot(float a){float c=cos(a),s=sin(a);return mat2(c,-s,s,c);}

vec3 src(vec2 uv01){return texture(uSrc, vec2(uv01.x, 1.0-uv01.y)).rgb;}
vec3 hist(vec2 uv01, float back){
    float layer=mod(float(uHead)-back+float("""+str(HIST)+""".0), """+str(HIST)+""".0);
    return texture(uHist, vec3(uv01.x, 1.0-uv01.y, layer)).rgb;
}

void main(){
    vec2 uv01=gl_FragCoord.xy/uRes;
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;   // centered
    vec3 col=vec3(0.0);

    if(uMode==0){
        // BEAT KALEIDO: fold the clip into 6 mirrored wedges
        float zoom=1.0-0.10*uPulse;
        vec2 c=uv*zoom;
        float r=length(c)+1e-4, a=atan(c.y,c.x)+uFlow*0.06;
        float sec=2.0*PI/6.0; a=mod(a,sec); a=abs(a-sec*0.5);
        vec2 suv=vec2(cos(a),sin(a))*r*0.85+0.5;
        suv=clamp(suv,0.0,1.0);
        col=src(suv);
        col*=1.0+0.25*uPulse;                     // beat brightness kiss
    } else if(uMode==1){
        // ECHO TRAILS: screen-blend the zoomed previous output
        vec2 puv=(uv01-0.5)*0.992+0.5;            // trails drift outward
        puv=rot(0.0025)* (puv-0.5)+0.5;
        vec3 prev=texture(uPrev, puv).rgb*0.90;
        vec3 now=src(uv01)*(0.60+0.40*uPulse);    // hits stamp fresh frames
        col=max(now, prev);                       // decaying light trails
    } else if(uMode==2){
        // TIME RIPPLE: concentric rings sample different moments
        float r=length(uv);
        float wave=0.5+0.5*sin(r*9.0-uTime*2.2);
        float back=wave*float("""+str(HIST)+""".0-1.0)*(0.4+0.6*uPulse);
        col=hist(uv01, back);
        // seam shimmer where time bends hardest
        float bend=abs(cos(r*9.0-uTime*2.2));
        col+=vec3(0.4,0.7,1.0)*pow(1.0-bend,6.0)*0.25*uPulse;
    } else if(uMode==3){
        // PRISM GLITCH: slice displacement + RGB split on onsets
        float band=floor(uv01.y*22.0);
        float tick=floor(uTime*7.0);
        float shift=(hash21(vec2(band,tick))-0.5)*0.12*step(0.35,uPulse)*uPulse;
        vec2 g=vec2(uv01.x+shift, uv01.y);
        float d=0.004+0.010*uPulse;
        col.r=src(vec2(g.x+d, g.y)).r;
        col.g=src(g).g;
        col.b=src(vec2(g.x-d, g.y)).b;
    } else {
        // NEON HALFTONE: the clip as glowing print dots
        vec2 grid=vec2(72.0,128.0);
        vec2 cell=floor(uv01*grid)/grid+0.5/grid;
        float luma=dot(src(cell),vec3(0.299,0.587,0.114));
        vec2 f=fract(uv01*grid)-0.5;
        float dd=length(f);
        float radius=0.62*sqrt(luma)*(1.0+0.25*uPulse);
        float dot_=smoothstep(radius,radius-0.14,dd);
        vec3 ink=mix(vec3(0.0,0.9,1.0),vec3(1.0,0.35,0.85),luma); // cyan->pink
        col=ink*dot_*(0.75+0.6*uPulse);
    }

    col*=1.0-0.35*dot(uv,uv);
    col=clamp(col,0.0,1.0);
    col=pow(col,vec3(1.18));                      // contrast floor (bright sources)
    col=pow(col,vec3(0.4545));
    fragColor=vec4(col,1.0);
}
"""


def onset_env(audio: Path, start: float, dur: float, fps: int) -> np.ndarray:
    import librosa
    y, sr = librosa.load(str(audio), sr=22050, mono=True,
                         offset=max(0.0, start - 1.0), duration=dur + 2.0)
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    tt = librosa.times_like(env, sr=sr, hop_length=512) - (1.0 if start >= 1.0 else 0.0)
    n = int(round(dur * fps))
    e = np.interp(np.arange(n) / fps, tt, env)
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
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--src-start", type=float, default=0.0)
    ap.add_argument("--audio", type=Path, required=True)
    ap.add_argument("--start", type=float, default=81.92)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--bars", type=int, default=3)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    args = ap.parse_args()

    w, h = args.w, args.h
    seg_dur = args.bars * BAR
    total = seg_dur * len(MODES)
    env = onset_env(args.audio, args.start, total, args.fps)
    nseg = int(round(seg_dur * args.fps))

    import moderngl
    ctx = moderngl.create_standalone_context()
    prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
    quad = ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], dtype="f4").tobytes())
    vao = ctx.vertex_array(prog, [(quad, "2f", "in_pos")])
    src_tex = ctx.texture((w, h), 3)
    hist_tex = ctx.texture_array((w, h, HIST), 3)
    fbos = [ctx.framebuffer(color_attachments=[ctx.texture((w, h), 3)]) for _ in range(2)]
    prog["uRes"].value = (float(w), float(h))
    src_tex.use(0); prog["uSrc"].value = 0
    prog["uPrev"].value = 1
    hist_tex.use(2); prog["uHist"].value = 2

    # continuous source decode: cover-crop to 1080x1920, rgb24 pipe
    dec = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", f"{args.src_start:.2f}", "-i", str(args.src),
         "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},fps={args.fps}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)

    args.out.mkdir(parents=True, exist_ok=True)
    frame_bytes = w * h * 3
    head = 0
    segfiles = []
    for k, mode in enumerate(MODES):
        seg = args.out / f"seg_{k:02d}_{mode}.silent.mp4"
        segfiles.append(seg)
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
             "-r", str(args.fps), "-i", "-",
             "-vf", f"vflip,drawtext=fontfile='{FONT}':text='{mode.replace('_',' ')}':"
                    f"fontsize=34:fontcolor=white@0.55:x=(w-text_w)/2:y=h-140",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", str(seg)], stdin=subprocess.PIPE)
        prog["uMode"].value = k
        for i in range(nseg):
            raw = dec.stdout.read(frame_bytes)
            if len(raw) < frame_bytes:
                raw = raw.ljust(frame_bytes, b"\0")
            src_tex.write(raw)
            head = (head + 1) % HIST
            hist_tex.write(raw, viewport=(0, 0, head, w, h, 1))
            gi = min(k * nseg + i, len(env) - 1)
            p = float(env[gi])
            prog["uTime"].value = (k * nseg + i) / args.fps
            prog["uPulse"].value = min(p, 1.0)
            prog["uFlow"].value = (k * nseg + i) / args.fps * 0.8
            prog["uHead"].value = head
            cur, prev = fbos[i % 2], fbos[(i + 1) % 2]
            prev.color_attachments[0].use(1)
            cur.use()
            vao.render()
            enc.stdin.write(cur.read(components=3))
        enc.stdin.close()
        enc.wait()
        print(f"look {mode} done")
    dec.terminate()

    concat = args.out / "concat.txt"
    concat.write_text("".join(f"file '{s.resolve()}'\n" for s in segfiles))
    final = args.out / "footage_fx_sampler.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(concat),
         "-ss", f"{args.start:.3f}", "-t", f"{total:.3f}", "-i", str(args.audio),
         "-af", f"afade=t=in:st=0:d=0.05,afade=t=out:st={total - 0.25:.3f}:d=0.25",
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(final)], check=True)
    print(f"BUILT {final} ({len(MODES)} treatments x {seg_dur:.2f}s)")


if __name__ == "__main__":
    main()
