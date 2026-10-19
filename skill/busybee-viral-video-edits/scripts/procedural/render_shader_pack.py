#!/usr/bin/env python3
"""Procedural shader pack — six audio-reactive looks, one sampler reel.

Each look is a self-contained GLSL fragment shader sharing the same
uniforms: uRes, uTime, uPulse (onset envelope), uFlow (beat-integrated
motion). Renders headless via moderngl, 3 bars per look, concatenated
over one continuous stretch of the song.

Usage:
  render_shader_pack.py --audio song.mp3 --start 81.92 \
      --out outputs/procedural/pack [--which kaleido_fold] [--bars 3]
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np

FONT = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"
BPM = 143.55
BAR = 4 * 60.0 / BPM

VERT = "#version 330\nin vec2 in_pos;\nvoid main(){gl_Position=vec4(in_pos,0.0,1.0);}"

COMMON = """
#version 330
out vec4 fragColor;
uniform vec2  uRes;
uniform float uTime;
uniform float uPulse;
uniform float uFlow;
#define PI 3.14159265359
vec3 pal(float t, vec3 a, vec3 b, vec3 c, vec3 d){return a+b*cos(6.28318*(c*t+d));}
float hash21(vec2 p){p=fract(p*vec2(123.34,456.21)); p+=dot(p,p+45.32); return fract(p.x*p.y);}
vec2 hash22(vec2 p){float n=hash21(p); return vec2(n, hash21(p+n));}
float vnoise(vec2 p){vec2 i=floor(p),f=fract(p); f=f*f*(3.0-2.0*f);
 float a=hash21(i),b=hash21(i+vec2(1,0)),c=hash21(i+vec2(0,1)),d=hash21(i+vec2(1,1));
 return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);}
float fbm(vec2 p){float v=0.0,amp=0.5; for(int i=0;i<5;i++){v+=amp*vnoise(p); p=p*2.03+vec2(17.3,9.1); amp*=0.5;} return v;}
"""

SHADERS = {}

SHADERS["kaleido_fold"] = COMMON + """
void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
    uv*=(1.0-0.10*uPulse);                      // punch-zoom on hits
    float a=atan(uv.y,uv.x+1e-5), r=length(uv)+1e-4;
    float N=8.0; a=mod(a,2.0*PI/N); a=abs(a-PI/N);
    vec2 p=vec2(cos(a),sin(a))*r*3.0;
    float w=fbm(p*1.6+vec2(uFlow*0.4,0.0)+fbm(p+uFlow*0.15)*1.5);
    vec3 col=pal(w+r*0.7-uFlow*0.05, vec3(0.5),vec3(0.5),vec3(1.0),vec3(0.0,0.33,0.67));
    col*=0.30+1.5*pow(w,2.0);
    col*=exp(-r*0.9);
    col+=vec3(1.0,0.8,0.6)*uPulse*exp(-r*3.0)*0.4;
    col=clamp(col,0.0,1.0); col=pow(col,vec3(0.4545));
    fragColor=vec4(col,1.0);
}
"""

SHADERS["liquid_chrome"] = COMMON + """
float smin(float a,float b,float k){float h=clamp(0.5+0.5*(b-a)/k,0.0,1.0);return mix(b,a,h)-k*h*(1.0-h);}
float map(vec3 p){
    float d=1e9;
    for(int i=0;i<5;i++){
        float fi=float(i);
        vec3 c=vec3(sin(uTime*0.7+fi*2.1), cos(uTime*0.9+fi*1.7), 0.4*sin(uTime*0.5+fi*2.9));
        c*=0.75+0.25*sin(fi*3.7+uTime*0.6);
        d=smin(d, length(p-c)-(0.40+0.10*sin(fi*5.0+uTime*1.3)), 0.42+0.22*uPulse);
    }
    return d;
}
vec3 normalAt(vec3 p){vec2 e=vec2(0.002,0.0);
    return normalize(vec3(map(p+e.xyy)-map(p-e.xyy),map(p+e.yxy)-map(p-e.yxy),map(p+e.yyx)-map(p-e.yyx)));}
void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
    vec3 ro=vec3(0.0,0.0,-3.2), rd=normalize(vec3(uv,1.4));
    float t=0.0; bool hit=false;
    for(int i=0;i<80;i++){float d=map(ro+rd*t); if(d<0.002){hit=true;break;} t+=d; if(t>9.0)break;}
    vec3 col=vec3(0.012,0.01,0.02);
    if(hit){
        vec3 p=ro+rd*t, n=normalAt(p), r=reflect(rd,n);
        col=pal(r.y*0.55+r.x*0.2+uFlow*0.02, vec3(0.45),vec3(0.55),vec3(1.0),vec3(0.0,0.12,0.24));
        float fre=pow(1.0-max(dot(n,-rd),0.0),3.0);
        col=col*(0.35+0.65*fre)+vec3(1.0)*pow(max(dot(r,normalize(vec3(0.5,0.8,-0.3))),0.0),48.0)*(1.5+1.5*uPulse);
        col*=exp(-t*0.10);
    }
    col=clamp(col,0.0,1.0); col=pow(col,vec3(0.4545));
    fragColor=vec4(col,1.0);
}
"""

SHADERS["neon_voronoi"] = COMMON + """
void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y*3.5;
    uv+=vec2(uFlow*0.30, uFlow*0.12);
    vec2 i=floor(uv), f=fract(uv);
    float F1=8.0, F2=8.0; vec2 id=vec2(0.0);
    for(int y=-1;y<=1;y++)for(int x=-1;x<=1;x++){
        vec2 g=vec2(float(x),float(y));
        vec2 o=hash22(i+g); o=0.5+0.45*sin(uTime*0.8+6.28318*o);
        vec2 dv=g+o-f; float d=dot(dv,dv);
        if(d<F1){F2=F1;F1=d;id=i+g;} else if(d<F2){F2=d;}
    }
    float edge=sqrt(F2)-sqrt(F1);
    vec3 cellc=pal(hash21(id)+uFlow*0.03, vec3(0.5),vec3(0.5),vec3(1.0),vec3(0.0,0.33,0.67));
    float glow=exp(-edge*9.0);
    vec3 col=cellc*0.05 + cellc*glow*(1.1+2.2*uPulse);
    col+=vec3(1.0)*exp(-edge*30.0)*0.35*(1.0+uPulse);
    col=clamp(col,0.0,1.0); col=pow(col,vec3(0.4545));
    fragColor=vec4(col,1.0);
}
"""

SHADERS["hyperspace"] = COMMON + """
void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y+1e-4;
    float a=atan(uv.y,uv.x), r=length(uv);
    float streak=0.0;
    for(int l=0;l<3;l++){
        float fl=float(l);
        float n=vnoise(vec2(a*(18.0+6.0*fl)+fl*7.0, 0.9/(r+0.06)-uFlow*(2.2+0.9*fl)));
        streak+=pow(n,7.0)*(0.6+0.4*fl);
    }
    streak*=smoothstep(0.02,0.35,r)*2.6;
    vec3 tint=pal(a/(2.0*PI)+uFlow*0.02, vec3(0.6),vec3(0.4),vec3(1.0),vec3(0.0,0.33,0.67));
    vec3 col=vec3(0.55,0.7,1.0)*streak + tint*streak*0.45;
    col+=vec3(0.8,0.9,1.0)*exp(-r*13.0)*(0.5+1.6*uPulse);
    col=clamp(col,0.0,1.0); col=pow(col,vec3(0.4545));
    fragColor=vec4(col,1.0);
}
"""

SHADERS["synthwave_grid"] = COMMON + """
void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
    float horizon=0.10;
    vec3 col;
    if(uv.y<horizon){
        float z=1.4/(horizon-uv.y);
        float x=uv.x*z;
        float zz=z+uFlow*3.0;
        float lx=abs(fract(x*0.8)-0.5), lz=abs(fract(zz*0.6)-0.5);
        float line=max(smoothstep(0.06,0.0,lx), smoothstep(0.06,0.0,lz));
        line*=exp(-z*0.10);
        col=vec3(0.05,0.01,0.10)+vec3(1.0,0.25,0.75)*line*(0.9+1.6*uPulse);
        col+=vec3(0.35,0.05,0.5)*exp(-z*0.30);
    } else {
        col=mix(vec3(0.10,0.02,0.18), vec3(0.01,0.01,0.05), smoothstep(horizon,0.9,uv.y));
        vec2 sp=uv-vec2(0.0,0.46);
        float d=length(sp);
        float R=0.30+0.015*uPulse;
        float sun=smoothstep(R,R-0.008,d);
        float bands=mix(1.0, step(0.42,fract(uv.y*20.0)), smoothstep(0.52,0.18,uv.y));
        sun*=bands;
        vec3 sc=mix(vec3(1.0,0.22,0.55), vec3(1.0,0.85,0.25), smoothstep(0.18,0.62,uv.y));
        col=mix(col, sc, sun);
        col+=sc*exp(-d*4.0)*0.25*(1.0+1.2*uPulse);
        float st=pow(hash21(floor(uv*vec2(240.0,140.0))),60.0);
        st*=0.5+0.5*sin(uTime*3.0+hash21(floor(uv*vec2(240.0,140.0)))*40.0);
        col+=vec3(st)*(1.0-sun)*smoothstep(horizon+0.1,0.5,uv.y);
        col+=vec3(1.0,0.3,0.8)*exp(-abs(uv.y-horizon)*40.0)*0.35;
    }
    col=clamp(col,0.0,1.0); col=pow(col,vec3(0.4545));
    fragColor=vec4(col,1.0);
}
"""

SHADERS["ink_marble"] = COMMON + """
void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y*1.8;
    vec2 q=vec2(fbm(uv+vec2(uFlow*0.18,0.0)), fbm(uv+vec2(3.7,8.2)-uFlow*0.12));
    vec2 s=vec2(fbm(uv+3.5*q+vec2(1.2,7.3)), fbm(uv+3.5*q+vec2(6.1,2.4)));
    float v=fbm(uv+3.2*s);
    vec3 col=pal(v*1.4+q.x*0.5-uFlow*0.03, vec3(0.5),vec3(0.5),vec3(1.0),vec3(0.10,0.45,0.80));
    col*=0.22+1.7*pow(v,1.6);
    col+=vec3(0.9,0.95,1.0)*pow(s.x,7.0)*(0.35+1.3*uPulse);
    col*=0.85+0.30*uPulse;
    col=clamp(col,0.0,1.0); col=pow(col,vec3(0.4545));
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


def setu(prog, name, val):
    try:
        prog[name].value = val
    except KeyError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", type=Path, required=True)
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--which", type=str, default=None, help="single look; default all")
    ap.add_argument("--bars", type=int, default=3)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    args = ap.parse_args()

    names = [args.which] if args.which else list(SHADERS)
    seg_dur = args.bars * BAR
    total = seg_dur * len(names)
    env = onset_env(args.audio, args.start, total, args.fps)
    nseg = int(round(seg_dur * args.fps))

    import moderngl
    ctx = moderngl.create_standalone_context()
    quad = ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], dtype="f4").tobytes())
    fbo = ctx.framebuffer(color_attachments=[ctx.texture((args.w, args.h), 3)])
    fbo.use()
    args.out.mkdir(parents=True, exist_ok=True)

    dt = 1.0 / args.fps
    segfiles = []
    for k, name in enumerate(names):
        prog = ctx.program(vertex_shader=VERT, fragment_shader=SHADERS[name])
        vao = ctx.vertex_array(prog, [(quad, "2f", "in_pos")])
        setu(prog, "uRes", (float(args.w), float(args.h)))
        seg = args.out / f"seg_{k:02d}_{name}.silent.mp4"
        segfiles.append(seg)
        label = name.replace("_", " ")
        ff = subprocess.Popen(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{args.w}x{args.h}",
             "-r", str(args.fps), "-i", "-",
             "-vf", f"vflip,drawtext=fontfile='{FONT}':text='{label}':fontsize=34:"
                    f"fontcolor=white@0.55:x=(w-text_w)/2:y=h-140",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", str(seg)], stdin=subprocess.PIPE)
        flow = 0.0
        for i in range(nseg):
            gi = min(k * nseg + i, len(env) - 1)
            p = float(env[gi])
            flow += dt * (1.0 + 1.2 * p)
            setu(prog, "uTime", i * dt)
            setu(prog, "uPulse", min(p, 1.0))
            setu(prog, "uFlow", flow)
            vao.render()
            ff.stdin.write(fbo.read(components=3))
        ff.stdin.close()
        ff.wait()
        print(f"look {name} done")

    concat = args.out / "concat.txt"
    concat.write_text("".join(f"file '{s.resolve()}'\n" for s in segfiles))
    final = args.out / ("sampler.mp4" if not args.which else f"{args.which}_solo.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(concat),
         "-ss", f"{args.start:.3f}", "-t", f"{total:.3f}", "-i", str(args.audio),
         "-af", f"afade=t=in:st=0:d=0.05,afade=t=out:st={total - 0.25:.3f}:d=0.25",
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(final)], check=True)
    print(f"BUILT {final} ({len(names)} looks x {seg_dur:.2f}s)")


if __name__ == "__main__":
    main()
