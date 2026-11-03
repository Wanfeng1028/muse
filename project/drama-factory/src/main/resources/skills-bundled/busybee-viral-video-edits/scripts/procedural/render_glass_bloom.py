#!/usr/bin/env python3
"""Glass bloom — log-polar liquid-glass kaleidoscope with chromatic dispersion.

The three tricks this look is made of:
  1. LOG-POLAR SPACE: the pattern lives in (angle, log radius). Cells
     self-shrink toward the center forever, and "zoom" is just a slide
     along one axis -> the endless bloom into the middle.
  2. SMOOTH VORONOI AS GLASS: exp-smoothed voronoi distance becomes a
     height field of soft bubble-cells, relief-lit like curved glass.
  3. CHROMATIC DISPERSION: the shading is computed three times at three
     slightly different zooms - one per color channel - so highlights
     fringe into rainbows exactly like light through a prism/oil slick.

Audio: bloom speed rides energy, dispersion amount and sparkle flare on
onsets (the glass "splits light harder" on every hit).

Usage:
  render_glass_bloom.py --still --out glass.png
  render_glass_bloom.py --audio song.mp3 --start 81.92 --dur 15 --out glass.mp4
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
uniform float uFlow;
#define PI 3.14159265359
#define WEDGES 10.0

vec2 hash22(vec2 p){
    p=vec2(dot(p,vec2(127.1,311.7)),dot(p,vec2(269.5,183.3)));
    return fract(sin(p)*43758.5453);
}
vec3 pal(float t){return 0.5+0.5*cos(6.28318*(t+vec3(0.0,0.33,0.67)));}

// distance to nearest cell point + its id (plain F1 voronoi)
float glassField(vec2 p, out vec2 id){
    vec2 i=floor(p), f=fract(p);
    float best=1e9; id=vec2(0.0);
    for(int y=-1;y<=1;y++)for(int x=-1;x<=1;x++){
        vec2 g=vec2(float(x),float(y));
        vec2 o=hash22(i+g);
        o=0.5+0.4*sin(uTime*0.35+6.28318*o);
        vec2 dv=g+o-f;
        float d=dot(dv,dv);
        if(d<best){best=d; id=i+g;}
    }
    return sqrt(best);
}

// the whole lit scene as luminance-ish value, at a given radial zoom.
// called once per color channel with a slightly different zoom.
float shade(vec2 uv, float zoom, out vec2 id){
    uv*=zoom;
    float r=length(uv)+1e-5;
    float a=atan(uv.y,uv.x);
    float sec=2.0*PI/WEDGES;
    a=mod(a,sec); a=abs(a-sec*0.5);          // kaleidoscope fold
    // log-polar: self-similar toward center; uFlow slides = infinite bloom
    vec2 p=vec2(a*7.0, log(r)*3.2-uFlow*0.55);
    // space-filling glass domes: every pixel is on the nearest bubble
    float v=glassField(p,id);
    float h=clamp(1.0-(v*1.45)*(v*1.45),0.0,1.0);
    h=pow(h,0.8);
    vec2 id2; h+=0.10*(1.0-clamp(glassField(p*2.1+7.0,id2)*1.8,0.0,1.0));
    // relief normal from screen-space slope
    float K=5.0;
    vec3 n=normalize(vec3(-dFdx(h)*K*uRes.y,-dFdy(h)*K*uRes.y,1.0));
    vec3 ldir=normalize(vec3(-0.4,0.6,0.72));
    float dif=max(dot(n,ldir),0.0);
    float spec=pow(max(dot(reflect(-ldir,n),vec3(0.0,0.0,1.0)),0.0),60.0);
    // crevice shadowing: bright inside the bubbles, dark seams between
    float depth=smoothstep(0.02,0.45,h);
    return (dif*1.0+0.10)*mix(0.10,1.0,depth)+spec*(2.2+2.6*uPulse)*depth;
}

void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
    uv*=(1.0-0.045*uPulse);
    // chromatic dispersion: per-channel zoom offset, flaring on hits
    float disp=0.006*(1.0+1.8*uPulse);
    vec2 idr,idg,idb;
    float sr=shade(uv,1.0,idr);
    float sg=shade(uv,1.0+disp,idg);
    float sb=shade(uv,1.0+2.0*disp,idb);
    vec3 col=vec3(sr,sg,sb);
    // pearl base + faint per-cell tint (steel blue / amber accents)
    vec3 tint=mix(vec3(0.88,0.92,1.0), pal(fract(dot(idg,vec2(0.13,0.29)))), 0.32);
    col*=tint;
    col=pow(col,vec3(1.45));                  // deepen: glass needs dark to shine
    // center light: the bloom emanates from a bright core
    float r=length(uv);
    col+=vec3(1.0,0.97,0.9)*exp(-r*5.5)*0.10*(1.0+1.4*uPulse);
    col*=1.0-0.5*dot(uv,uv);
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
    w, h = ((540, 960) if args.still else (args.w, args.h))
    rw, rh = w * 2, h * 2
    fbo = ctx.framebuffer(color_attachments=[ctx.texture((rw, rh), 3)])
    fbo.use()
    prog["uRes"].value = (float(rw), float(rh))

    if args.still:
        prog["uTime"].value = 5.0
        prog["uPulse"].value = 0.5
        prog["uFlow"].value = 8.0
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
        flow += dt * (0.55 + 1.5 * p)
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
