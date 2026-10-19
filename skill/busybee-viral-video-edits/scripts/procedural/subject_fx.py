#!/usr/bin/env python3
"""Subject FX — effects dialed onto a specific person via per-frame mattes.

Requires a prepared segment (1080x1920@30) and a directory of per-frame
person mattes (proposal_%06d.png from generate_local_person_matte.swift).

Six subject-aware treatments, 3 bars each, continuous audio:
  world_ripple    - the WORLD time-ripples, the skater stays crisp
  echo_clones     - tinted onion-skin ghosts of the skater trail behind,
                    background untouched, ghost strength rides the beat
  neon_rim        - pulsing neon outline traced around the skater,
                    world dimmed to make them the light source
  bg_kaleido      - the world folds into a kaleidoscope, skater rides it
  subject_prism   - the skater RGB-splits and glitches on hits, world intact
  subject_kaleido - the skater folds into a kaleidoscope of THEMSELVES
                    (their own pixels, mirrored into wedges); the world
                    is untouched. The inverse of bg_kaleido.

Usage:
  subject_fx.py --segment work/segment2.mp4 --mattes work/mattes2 \
      --audio song.mp3 --start 81.92 --out outputs/procedural/subject_fx

Renders all modes as a labeled sampler reel. For production use of ONLY one
look (e.g. just subject_kaleido), don't reorder or trim MODES — the shader's
`uMode==N` branches are hardcoded to these exact positions (subject_kaleido
is the final `else`, i.e. index 5). Instead, write your own render loop that
imports this module's VERT/FRAG/onset_env/HIST and pins
`prog["uMode"].value` to the fixed index of the look you want for every
frame, rather than looping over MODES.
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
MODES = ["world_ripple", "echo_clones", "neon_rim", "bg_kaleido", "subject_prism", "subject_kaleido"]

VERT = "#version 330\nin vec2 in_pos;\nvoid main(){gl_Position=vec4(in_pos,0.0,1.0);}"

FRAG = """
#version 330
out vec4 fragColor;
uniform vec2  uRes;
uniform float uTime;
uniform float uPulse;
uniform float uFlow;
uniform int   uMode;
uniform int   uHead;
uniform sampler2D uSrc;
uniform sampler2D uMatte;
uniform sampler2DArray uHist;   // past source frames
uniform sampler2DArray uMhist;  // past mattes
#define PI 3.14159265359
#define NH """ + str(HIST) + """.0

float hash21(vec2 p){p=fract(p*vec2(123.34,456.21)); p+=dot(p,p+45.32); return fract(p.x*p.y);}
vec3 pal(float t){return 0.5+0.5*cos(6.28318*(t+vec3(0.0,0.33,0.67)));}
mat2 rot(float a){float c=cos(a),s=sin(a);return mat2(c,-s,s,c);}

vec2 flipv(vec2 uv01){return vec2(uv01.x, 1.0-uv01.y);}
vec3 src(vec2 uv01){return texture(uSrc, flipv(uv01)).rgb;}
float matte(vec2 uv01){return smoothstep(0.30,0.70, texture(uMatte, flipv(uv01)).r);}
float layerOf(float back){return mod(float(uHead)-back+NH, NH);}
vec3 hist(vec2 uv01, float back){return texture(uHist, vec3(flipv(uv01), layerOf(back))).rgb;}
float mhist(vec2 uv01, float back){return smoothstep(0.30,0.70, texture(uMhist, vec3(flipv(uv01), layerOf(back))).r);}

void main(){
    vec2 uv01=gl_FragCoord.xy/uRes;
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
    float m=matte(uv01);
    vec3 col;

    if(uMode==0){
        // WORLD RIPPLE: background time-bends, subject stays now
        float r=length(uv);
        float wave=0.5+0.5*sin(r*8.0-uTime*2.1);
        vec3 bg=hist(uv01, wave*(NH-1.0)*(0.35+0.65*uPulse));
        float bend=abs(cos(r*8.0-uTime*2.1));
        bg+=vec3(0.4,0.7,1.0)*pow(1.0-bend,6.0)*0.20*uPulse;
        col=mix(bg, src(uv01), m);
    } else if(uMode==1){
        // ECHO CLONES: tinted ghosts of the subject at fixed lags
        col=src(uv01)*0.94;
        float lags[3]=float[3](6.0,13.0,20.0);
        float fades[3]=float[3](0.60,0.42,0.28);
        for(int k=0;k<3;k++){
            float gm=mhist(uv01, lags[k]);
            vec3 gc=hist(uv01, lags[k]);
            vec3 tint=pal(0.55+0.14*float(k)+uFlow*0.02);
            col=max(col, gc*tint*gm*fades[k]*(0.6+0.9*uPulse));
        }
        col=mix(col, src(uv01), m);              // live subject on top
    } else if(uMode==2){
        // NEON RIM: the subject becomes the light source
        vec2 e=vec2(3.0)/uRes;
        float gx=matte(uv01+vec2(e.x,0.0))-matte(uv01-vec2(e.x,0.0));
        float gy=matte(uv01+vec2(0.0,e.y))-matte(uv01-vec2(0.0,e.y));
        float edge=clamp(length(vec2(gx,gy))*2.2,0.0,1.0);
        // wider soft halo from dilated matte samples
        float halo=0.0;
        for(int k=0;k<6;k++){
            float aa=float(k)*PI/3.0;
            halo+=matte(uv01+vec2(cos(aa),sin(aa))*10.0/uRes.y);
        }
        halo=clamp(halo/6.0-m,0.0,1.0);
        vec3 base=src(uv01);
        float luma=dot(base,vec3(0.299,0.587,0.114));
        vec3 dimmed=mix(vec3(luma)*0.30, base*0.42, 0.4);
        vec3 neon=pal(0.58+0.10*sin(uFlow*0.7));
        col=mix(dimmed, base*1.05, m);
        col+=neon*edge*(1.6+2.6*uPulse);
        col+=neon*halo*(0.35+0.9*uPulse);
    } else if(uMode==3){
        // BG KALEIDO: world folds into a mandala, subject rides it
        float r=length(uv)+1e-4, a=atan(uv.y,uv.x)+uFlow*0.10;
        float sec=2.0*PI/6.0; a=mod(a,sec); a=abs(a-sec*0.5);
        vec2 suv=clamp(vec2(cos(a),sin(a))*r*0.85+0.5,0.0,1.0);
        vec3 bg=src(suv)*(0.9+0.2*uPulse);
        col=mix(bg, src(uv01), m);
    } else if(uMode==4){
        // SUBJECT PRISM: only the subject glitches, on the hits
        vec3 base=src(uv01);
        float band=floor(uv01.y*26.0);
        float tick=floor(uTime*7.0);
        float shift=(hash21(vec2(band,tick))-0.5)*0.10*step(0.30,uPulse)*uPulse;
        float d=0.005+0.016*uPulse;
        vec2 g=vec2(uv01.x+shift*m, uv01.y);
        vec3 split;
        split.r=src(vec2(g.x+d,g.y)).r;
        split.g=src(g).g;
        split.b=src(vec2(g.x-d,g.y)).b;
        col=mix(base, split, m);
        // white edge flash on hits
        vec2 e=vec2(3.0)/uRes;
        float edge=clamp(length(vec2(
            matte(uv01+vec2(e.x,0.0))-matte(uv01-vec2(e.x,0.0)),
            matte(uv01+vec2(0.0,e.y))-matte(uv01-vec2(0.0,e.y))))*2.0,0.0,1.0);
        col+=vec3(1.0)*edge*uPulse*0.8;
    } else {
        // SUBJECT KALEIDO: the person folds into a kaleidoscope of
        // themselves; the world stays untouched. Same fold math as
        // BG KALEIDO above, but the mix gates the OPPOSITE way — normal
        // world by default, kaleido fold only where the matte is lit.
        float zoom=1.0-0.08*uPulse;
        vec2 c=uv*zoom;
        float r=length(c)+1e-4, a=atan(c.y,c.x)+uFlow*0.08;
        float sec=2.0*PI/8.0; a=mod(a,sec); a=abs(a-sec*0.5);
        vec2 suv=clamp(vec2(cos(a),sin(a))*r*0.85+0.5,0.0,1.0);
        vec3 folded=src(suv)*(1.0+0.20*uPulse);
        col=mix(src(uv01), folded, m);
        // thin neon edge keeps the silhouette readable against real bg
        vec2 e=vec2(3.0)/uRes;
        float edge=clamp(length(vec2(
            matte(uv01+vec2(e.x,0.0))-matte(uv01-vec2(e.x,0.0)),
            matte(uv01+vec2(0.0,e.y))-matte(uv01-vec2(0.0,e.y))))*2.0,0.0,1.0);
        col+=pal(0.5+0.1*sin(uFlow*0.5))*edge*(0.4+0.6*uPulse);
    }

    col*=1.0-0.30*dot(uv,uv);
    col=clamp(col,0.0,1.0);
    col=pow(col,vec3(1.12));
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
    ap.add_argument("--segment", type=Path, required=True)
    ap.add_argument("--mattes", type=Path, required=True)
    ap.add_argument("--audio", type=Path, required=True)
    ap.add_argument("--start", type=float, default=81.92)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--bars", type=int, default=3)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    args = ap.parse_args()

    from PIL import Image
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
    mat_tex = ctx.texture((w, h), 1)
    hist_tex = ctx.texture_array((w, h, HIST), 3)
    mhist_tex = ctx.texture_array((w, h, HIST), 1)
    fbo = ctx.framebuffer(color_attachments=[ctx.texture((w, h), 3)])
    fbo.use()
    prog["uRes"].value = (float(w), float(h))
    src_tex.use(0); prog["uSrc"].value = 0
    mat_tex.use(1); prog["uMatte"].value = 1
    hist_tex.use(2); prog["uHist"].value = 2
    mhist_tex.use(3); prog["uMhist"].value = 3

    dec = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(args.segment),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)

    args.out.mkdir(parents=True, exist_ok=True)
    frame_bytes = w * h * 3
    head = 0
    frame_idx = 0
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
            mp = args.mattes / f"proposal_{frame_idx:06d}.png"
            if mp.exists():
                mdata = np.asarray(Image.open(mp).convert("L"), dtype=np.uint8).tobytes()
            else:
                mdata = b"\0" * (w * h)
            src_tex.write(raw)
            mat_tex.write(mdata)
            head = (head + 1) % HIST
            hist_tex.write(raw, viewport=(0, 0, head, w, h, 1))
            mhist_tex.write(mdata, viewport=(0, 0, head, w, h, 1))
            gi = min(k * nseg + i, len(env) - 1)
            p = float(env[gi])
            prog["uTime"].value = frame_idx / args.fps
            prog["uPulse"].value = min(p, 1.0)
            prog["uFlow"].value = frame_idx / args.fps * 0.8
            prog["uHead"].value = head
            vao.render()
            enc.stdin.write(fbo.read(components=3))
            frame_idx += 1
        enc.stdin.close()
        enc.wait()
        print(f"look {mode} done")
    dec.terminate()

    concat = args.out / "concat.txt"
    concat.write_text("".join(f"file '{s.resolve()}'\n" for s in segfiles))
    final = args.out / "subject_fx_sampler.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(concat),
         "-ss", f"{args.start:.3f}", "-t", f"{total:.3f}", "-i", str(args.audio),
         "-af", f"afade=t=in:st=0:d=0.05,afade=t=out:st={total - 0.25:.3f}:d=0.25",
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(final)], check=True)
    print(f"BUILT {final}")


if __name__ == "__main__":
    main()
