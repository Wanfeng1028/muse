#!/usr/bin/env python3
"""Mandala — polar-symmetry relief-lit kaleidoscope, audio-reactive.

Construction (the teachable part):
  1. Polar coordinates: everything is drawn in (radius, angle) space.
  2. Sector fold: angle mirrored into N wedges -> instant kaleidoscope.
  3. Ring bands: radius quantized into rings, each ring gets its own
     motif (diamonds / beads / petals / zigzag) and its own motif count.
  4. Relief lighting: the pattern is treated as a HEIGHT MAP and lit
     with screen-space derivatives -> the embossed, woven, physical look
     that separates rich mandalas from flat ones.
  5. Music: a light-wave rolls outward from the center on onsets,
     rotation drifts with energy, slight punch-zoom on hits.

Usage:
  render_mandala.py --still --out mandala.png
  render_mandala.py --audio song.mp3 --start 81.92 --dur 15 --out mandala.mp4
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
uniform float uPulse;
uniform float uFlow;   // integrated energy: drives drift + the beat wave
#define PI 3.14159265359
#define SECTORS 12.0

float hash11(float p){return fract(sin(p*127.1)*43758.5453);}

// mandala palette: deep blue / purple / pink / gold / cream
vec3 ringColor(float ri, float v){
    float fam=mod(ri,2.0);
    if(fam<1.0){
        vec3 deep=vec3(0.10,0.14,0.42), mid=vec3(0.45,0.22,0.62), hot=vec3(0.88,0.36,0.63);
        return mix(deep, mix(mid,hot,smoothstep(0.5,1.0,v)), smoothstep(0.1,0.9,v));
    } else {
        vec3 shadow=vec3(0.35,0.22,0.10), gold=vec3(0.91,0.70,0.29), cream=vec3(0.96,0.89,0.76);
        return mix(shadow, mix(gold,cream,smoothstep(0.6,1.0,v)), smoothstep(0.05,0.85,v));
    }
}

// pattern height at polar point; ri = ring index (for motif choice)
float motif(vec2 c, float ri){
    float m=mod(ri,4.0);
    if(m<1.0){                               // concentric diamonds
        float d=abs(c.x)+abs(c.y);
        return (0.5+0.5*cos(d*14.0))*(1.0-smoothstep(0.40,0.5,d));
    } else if(m<2.0){                        // beads with inner rings
        float d=length(c*vec2(1.15,1.0));
        return (0.5+0.5*cos(d*16.0))*(1.0-smoothstep(0.30,0.46,d));
    } else if(m<3.0){                        // petals / leaves
        float d=length(vec2(c.x*2.1,c.y*1.05));
        return (0.55+0.45*cos(c.y*7.0))*(1.0-smoothstep(0.30,0.44,d));
    } else {                                 // zigzag stripes
        return 0.5+0.5*cos((c.x*2.0+abs(c.y))*14.0);
    }
}

float height(vec2 uv){
    float r=length(uv)+1e-4;
    float a=atan(uv.y,uv.x);
    a+=uTime*0.04;                            // slow global rotation
    float sec=2.0*PI/SECTORS;
    a=mod(a,sec); a=abs(a-sec*0.5);           // mirrored sector fold
    float ring=r*4.2-uFlow*0.10;              // wide rings, slow outward drift
    float ri=floor(ring), rf=fract(ring)-0.5;
    // 1-2 motifs per mirrored wedge: the 12-fold fold supplies the rest
    float nm=floor(1.0+2.0*hash11(ri));
    float th=a/sec*nm+ri*0.5;
    vec2 c=vec2(fract(th)-0.5, rf);
    float h=motif(c,ri);
    h+=0.06*sin(r*90.0)*sin(th*24.0);         // fine weave texture
    // center rosette: petaled sun medallion instead of a flat disc
    float aFull=atan(uv.y,uv.x)+uTime*0.04;
    float rose=(0.5+0.5*cos(r*60.0))*(0.6+0.4*cos(aFull*12.0));
    float cz=1.0-smoothstep(0.06,0.16,r);
    h=mix(h,rose,cz);
    return h;
}

void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
    uv*=(1.0-0.05*uPulse);                    // punch-zoom on hits
    float h=height(uv);
    // relief lighting from screen-space slope of the height field
    float K=6.0;
    vec3 n=normalize(vec3(-dFdx(h)*K*uRes.y, -dFdy(h)*K*uRes.y, 1.0));
    vec3 ldir=normalize(vec3(-0.45,0.55,0.75));
    float dif=max(dot(n,ldir),0.0)*0.85+0.15;
    float spec=pow(max(dot(reflect(-ldir,n),vec3(0.0,0.0,1.0)),0.0),24.0);

    float r=length(uv);
    float ring=r*4.2-uFlow*0.10;
    vec3 col=ringColor(floor(ring), h)*dif + vec3(1.0,0.92,0.75)*spec*0.55;

    // the beat wave: a ring of light rolling outward from the center
    float wavePos=mod(uFlow*0.55,2.2);
    float wave=exp(-abs(r-wavePos)*7.0)*uPulse;
    col*=1.0+0.85*wave;
    col+=vec3(1.0,0.9,0.7)*wave*0.15;

    col*=1.0-0.45*dot(uv,uv);                 // vignette
    col=clamp(col,0.0,1.0);
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
    ap.add_argument("--still", action="store_true")
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--start", type=float, default=81.92)
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
    # render 2x supersampled; downscale on output (kills pattern aliasing)
    w, h = ((540, 960) if args.still else (args.w, args.h))
    rw, rh = w * 2, h * 2
    fbo = ctx.framebuffer(color_attachments=[ctx.texture((rw, rh), 3)])
    fbo.use()
    prog["uRes"].value = (float(rw), float(rh))

    if args.still:
        prog["uTime"].value = 5.0
        prog["uPulse"].value = 0.5
        prog["uFlow"].value = 6.0
        vao.render()
        img = np.flipud(np.frombuffer(fbo.read(components=3), dtype=np.uint8).reshape(rh, rw, 3))
        from PIL import Image
        args.out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(img).resize((w, h), Image.LANCZOS).save(args.out)
        print(f"STILL {args.out}")
        return

    assert args.audio
    env = onset_env(args.audio, args.start, args.dur, args.fps)
    n = len(env)
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
    for i in range(n):
        p = float(env[i])
        flow += dt * (0.5 + 1.6 * p)
        prog["uTime"].value = i * dt
        prog["uPulse"].value = min(p, 1.0)
        prog["uFlow"].value = flow
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
