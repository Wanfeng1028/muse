#!/usr/bin/env python3
"""Neon fractal — kaleidoscopic IFS raymarcher with orbit-trap emissives.

The reference tier: folded/twisted self-similar 3D structure, greebled
surface, neon tubes lit by orbit traps, in-march glow accumulation
(fake volumetric bloom), AO, deep fog. Audio-reactive: twist velocity,
emissive gain, punch-zoom all ride the onset envelope.

Modes:
  --stills           render preset variants as one contact sheet (fast)
  --preset N --dur S render video with preset N
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np

FONT = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"

VERT = "#version 330\nin vec2 in_pos;\nvoid main(){gl_Position=vec4(in_pos,0.0,1.0);}"

FRAG = """
#version 330
out vec4 fragColor;
uniform vec2  uRes;
uniform float uTime;
uniform float uPulse;
uniform float uTwist;    // integrated twist angle
uniform float uDive;     // camera radius
uniform float uSC;       // IFS scale
uniform vec3  uOFF;      // IFS offset
uniform float uHueShift;
#define PI 3.14159265359

vec3 pal(float t, vec3 d){return 0.5+0.5*cos(6.28318*(t+d));}
mat2 rot(float a){float c=cos(a),s=sin(a);return mat2(c,-s,s,c);}
float hash31(vec3 p){return fract(sin(dot(p,vec3(12.9898,78.233,37.719)))*43758.5453);}

float gTrapA, gTrapB;
float map(vec3 p){
    float s=1.0;
    gTrapA=1e9; gTrapB=1e9;
    float a1=uTwist, a2=uTwist*0.7+1.1;
    for(int i=0;i<8;i++){
        p=abs(p);
        if(p.x<p.y) p.xy=p.yx;
        if(p.x<p.z) p.xz=p.zx;
        if(p.y<p.z) p.yz=p.zy;
        p.xy=rot(a1)*p.xy;
        p.yz=rot(a2)*p.yz;
        p=p*uSC-uOFF*(uSC-1.0);
        s*=uSC;
        gTrapA=min(gTrapA, abs(length(p.xz)-0.55));
        gTrapB=min(gTrapB, length(p-vec3(0.4,0.9,0.2)));
    }
    return (length(p)-1.35)/s;
}

vec3 normalAt(vec3 p){vec2 e=vec2(0.0012,0.0);
    return normalize(vec3(map(p+e.xyy)-map(p-e.xyy),map(p+e.yxy)-map(p-e.yxy),map(p+e.yyx)-map(p-e.yyx)));}

void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
    uv*=(1.0-0.06*uPulse);
    float th=uTime*0.13;
    vec3 ro=vec3(uDive*cos(th), 0.55*sin(uTime*0.09), uDive*sin(th));
    vec3 ww=normalize(-ro);
    vec3 rgt=normalize(cross(vec3(0.0,1.0,0.0),ww));
    vec3 up=cross(ww,rgt);
    float rl=uTime*0.05;
    vec2 ruv=rot(rl)*uv;
    vec3 rd=normalize(ruv.x*rgt+ruv.y*up+1.25*ww);

    float t=0.0; bool hit=false; vec3 glow=vec3(0.0);
    float ta=0.0, tb=0.0; int steps=0;
    for(int i=0;i<110;i++){
        steps=i;
        vec3 p=ro+rd*t;
        float d=map(p);
        // in-march neon glow: each lattice cell gets its own random hue,
        // so one frame carries green/pink/cyan tubes at once
        float hA=uHueShift+hash31(floor(p*1.3));
        float hB=uHueShift+hash31(floor(p*0.9)+7.0);
        vec3 nA=pal(hA, vec3(0.0,0.33,0.67));
        vec3 nB=pal(hB, vec3(0.0,0.33,0.67));
        glow+=nA*exp(-gTrapA*40.0)*0.0045*(1.0+2.6*uPulse);
        glow+=nB*exp(-gTrapB*30.0)*0.003*(1.0+1.8*uPulse);
        if(d<0.0009*t){hit=true; ta=gTrapA; tb=gTrapB; break;}
        t+=d*0.9;
        if(t>7.0) break;
    }

    vec3 col=vec3(0.008,0.006,0.016);
    if(hit){
        vec3 p=ro+rd*t;
        vec3 n=normalAt(p);
        // greebled albedo: fine circuit-ish bands on the fractal surface
        float gre=0.66+0.17*sin(p.x*90.0)*sin(p.y*84.0)+0.17*sin((p.x+p.y+p.z)*140.0);
        vec3 alb=vec3(0.16,0.15,0.26)*gre;
        float ao=clamp(1.0-float(steps)/110.0*1.6, 0.05, 1.0);
        float dif=max(dot(n,normalize(vec3(0.5,0.7,-0.3))),0.0)*0.9+0.08;
        float rim=pow(1.0-max(dot(n,-rd),0.0),3.0);
        col=alb*dif*ao+alb*rim*0.40;
        // emissive neon strips where the orbit traps graze the surface
        float hA=uHueShift+hash31(floor(p*1.3));
        float hB=uHueShift+hash31(floor(p*0.9)+7.0);
        vec3 nA=pal(hA, vec3(0.0,0.33,0.67));
        vec3 nB=pal(hB, vec3(0.0,0.33,0.67));
        col+=nA*exp(-ta*26.0)*(1.2+2.4*uPulse)*ao;
        col+=nB*exp(-tb*18.0)*(0.8+1.5*uPulse)*ao;
        col*=exp(-t*0.42);
    }
    col+=glow;
    col*=1.0-0.55*dot(uv,uv);          // vignette for depth
    // tonemap + saturation
    col=1.0-exp(-col*1.7);
    float luma=dot(col,vec3(0.299,0.587,0.114));
    col=clamp(mix(vec3(luma),col,1.35),0.0,1.0);
    col=pow(col,vec3(0.4545));
    fragColor=vec4(col,1.0);
}
"""

PRESETS = [
    # (scale, offset, hue_shift, dive)
    (1.85, (1.00, 1.20, 0.90), 0.00, 2.60),
    (2.05, (1.10, 0.95, 1.25), 0.15, 2.45),
    (1.70, (0.85, 1.30, 1.05), 0.40, 2.80),
    (2.25, (1.20, 1.10, 0.80), 0.60, 2.30),
    (1.95, (0.95, 1.05, 1.15), 0.80, 2.55),
    (2.10, (1.30, 0.85, 1.00), 0.28, 2.40),
]


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


def make_ctx(w, h):
    import moderngl
    ctx = moderngl.create_standalone_context()
    prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
    quad = ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], dtype="f4").tobytes())
    vao = ctx.vertex_array(prog, [(quad, "2f", "in_pos")])
    fbo = ctx.framebuffer(color_attachments=[ctx.texture((w, h), 3)])
    fbo.use()
    prog["uRes"].value = (float(w), float(h))
    return ctx, prog, vao, fbo


def set_preset(prog, pr):
    sc, off, hue, dive = pr
    prog["uSC"].value = sc
    prog["uOFF"].value = off
    prog["uHueShift"].value = hue
    prog["uDive"].value = dive


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--preset", type=int, default=0)
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--start", type=float, default=81.92)
    ap.add_argument("--dur", type=float, default=15.0)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    args = ap.parse_args()

    if args.stills:
        w, h = 540, 960
        ctx, prog, vao, fbo = make_ctx(w, h)
        tiles = []
        for pi, pr in enumerate(PRESETS):
            set_preset(prog, pr)
            prog["uTime"].value = 6.0
            prog["uPulse"].value = 0.4
            prog["uTwist"].value = 1.7
            vao.render()
            img = np.frombuffer(fbo.read(components=3), dtype=np.uint8).reshape(h, w, 3)
            tiles.append(np.flipud(img))
        grid = np.concatenate([np.concatenate(tiles[:3], axis=1),
                               np.concatenate(tiles[3:], axis=1)], axis=0)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        Image.fromarray(grid).save(args.out)
        print(f"STILLS {args.out} (presets 0-5, row-major)")
        return

    assert args.audio, "--audio required for video"
    env = onset_env(args.audio, args.start, args.dur, args.fps)
    n = len(env)
    ctx, prog, vao, fbo = make_ctx(args.w, args.h)
    set_preset(prog, PRESETS[args.preset])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    silent = args.out.with_suffix(".silent.mp4")
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{args.w}x{args.h}",
         "-r", str(args.fps), "-i", "-",
         "-vf", "vflip", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)
    dt = 1.0 / args.fps
    twist = 1.2
    for i in range(n):
        p = float(env[i])
        twist += dt * (0.10 + 0.55 * p)      # the structure twists harder on hits
        prog["uTime"].value = i * dt
        prog["uPulse"].value = min(p, 1.0)
        prog["uTwist"].value = twist
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
