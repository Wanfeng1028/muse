#!/usr/bin/env python3
"""Neon cathedral — Mandelbox tunnel flythrough with layered glow systems.

The reference tier ("fractalicious eye massage"): a box-folding fractal
(Mandelbox) carved with a cylindrical bore and tiled along z, so the
camera flies forever through terraced machined-cathedral chambers.
On top, SEPARATE animated emitter families, each its own color system:

  rings     - blue/cyan halo circles at intervals down the tunnel
  bolt      - yellow-green energy filament wiggling along the axis
  arcs      - orange rotating partial rings
  surface   - multi-hue orbit-trap neon on the fractal walls
  core      - golden reactor glow always ahead of the camera
  sparks    - drifting point glows in the open air

Our twist - each family listens to a different part of the song:
  rings flare on ONSETS - bolt rides the HIGHS - core breathes on BASS -
  camera speed surges on onsets - arc rotation rides accumulated energy.

Usage:
  render_neon_cathedral.py --stills --out stills.png
  render_neon_cathedral.py --preset 1 --audio song.mp3 --start 81.92 \
      --dur 15 --fps 60 --out cathedral.mp4
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
uniform float uCamZ;
uniform float uPulse;   // onset envelope
uniform float uBass;    // low-band energy
uniform float uHigh;    // high-band energy
uniform float uFlow;    // integrated energy
uniform float uScale;   // mandelbox scale
uniform float uBore;    // tunnel bore radius
#define PI 3.14159265359
#define ZTILE 3.4

float hash11(float p){return fract(sin(p*127.1)*43758.5453);}
float hash31(vec3 p){return fract(sin(dot(p,vec3(12.9898,78.233,37.719)))*43758.5453);}
vec3 pal(float t){return 0.5+0.5*cos(6.28318*(t+vec3(0.0,0.33,0.67)));}
mat2 rot(float a){float c=cos(a),s=sin(a);return mat2(c,-s,s,c);}

float gTrap;
// machined cathedral tunnel: 8 radial wedges, terraced walls, rib arches.
// uScale = terrace depth multiplier, uBore = wall radius.
float map(vec3 p){
    float r=length(p.xy);
    float ang=atan(p.y,p.x);
    float sec=2.0*PI/8.0;
    float a=mod(ang,sec)-sec*0.5;              // wedge fold
    // three interleaved terrace systems (machined steps)
    float t1=abs(fract(p.z*1.35)-0.5);
    float t2=abs(fract(a*3.0/sec)-0.5);
    float t3=abs(fract(r*2.6+p.z*0.35)-0.5);
    float ter=0.0;
    ter+=0.11*smoothstep(0.18,0.50,t1);
    ter+=0.08*smoothstep(0.22,0.50,t2);
    ter+=0.05*smoothstep(0.20,0.50,t3);
    ter*=uScale;
    // rib arches: pillars at wedge centers, repeating along z
    float zt=abs(fract(p.z*0.60)-0.5);
    float rib=0.14*smoothstep(0.13,0.0,abs(a))*smoothstep(0.34,0.05,zt)*uScale;
    // neon circuit-lines trace the terrace edges
    gTrap=min(abs(t1-0.18)*0.9, min(abs(t2-0.22)*1.1, abs(t3-0.20)*1.3));
    float wall=(uBore-ter-rib)-r;   // air inside the bore, solid beyond
    return wall*0.5;
}

vec3 normalAt(vec3 p){vec2 e=vec2(0.0016,0.0);
    return normalize(vec3(map(p+e.xyy)-map(p-e.xyy),map(p+e.yxy)-map(p-e.yxy),map(p+e.yyx)-map(p-e.yyx)));}

void main(){
    vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
    uv*=(1.0-0.05*uPulse);
    // gentle sway + roll, off-axis look like the reference
    float rl=0.06*sin(uTime*0.23);
    uv=rot(rl)*uv;
    vec3 ro=vec3(0.10*sin(uTime*0.40),0.07*cos(uTime*0.31),uCamZ);
    vec2 look=vec2(0.10*sin(uTime*0.19),0.05*cos(uTime*0.26));
    vec3 rd=normalize(vec3(uv+look,1.15));

    float t=0.0; bool hit=false; int steps=0;
    vec3 glow=vec3(0.0);
    float trapAtHit=0.0;
    vec3 pHit=vec3(0.0);
    for(int i=0;i<100;i++){
        steps=i;
        vec3 p=ro+rd*t;
        float d=map(p);

        /* ---- layered emitter systems, accumulated volumetrically ---- */
        float rr=length(p.xy);
        // RINGS (blue/cyan family) - flare on onsets
        float ringL=1.7;
        float zr=mod(p.z,ringL)-ringL*0.5;
        float ringId=floor(p.z/ringL);
        float dRing=length(vec2(rr-uBore*0.82,zr));
        vec3 ringCol=pal(0.52+0.14*hash11(ringId));
        glow+=ringCol*exp(-dRing*26.0)*0.016*(0.5+2.6*uPulse);
        // BOLT (yellow-green filament) - rides the highs
        vec2 wig=0.16*vec2(sin(p.z*2.1+uTime*3.1),cos(p.z*1.7+uTime*2.4));
        float dAxis=length(p.xy-wig);
        glow+=vec3(0.75,1.0,0.25)*exp(-dAxis*20.0)*0.011*(0.25+2.2*uHigh);
        // ARCS (orange partial rings) - rotation rides energy
        float ang=atan(p.y,p.x);
        float win=smoothstep(0.55,0.95,sin(ang*2.0+uFlow*1.2+ringId*2.2));
        glow+=vec3(1.0,0.45,0.12)*exp(-dRing*30.0)*win*0.014*(0.4+1.4*uPulse);
        // CORE (golden reactor, always ahead) - breathes on bass
        float dCore=length(p-vec3(0.0,0.0,uCamZ+6.5));
        glow+=vec3(1.0,0.82,0.30)*exp(-dCore*dCore*1.1)*0.012*(0.3+2.4*uBass);
        // SPARKS (drifting motes)
        vec3 q=p*1.4; vec3 qf=fract(q)-0.5; vec3 qi=floor(q);
        float hs=hash31(qi);
        float dSpark=length(qf-0.35*vec3(sin(uTime*0.8+hs*6.28),cos(uTime*0.6+hs*9.4),sin(uTime*0.7+hs*3.1)));
        glow+=pal(hs)*exp(-dSpark*34.0)*0.006*step(0.82,hs);

        if(d<0.0011*t){hit=true;trapAtHit=gTrap;pHit=p;break;}
        t+=d*0.85;
        if(t>10.0)break;
    }

    vec3 col=vec3(0.010,0.007,0.016);
    if(hit){
        vec3 n=normalAt(pHit);
        // machined mauve walls with fine terrace greeble
        float gre=0.70+0.15*sin(pHit.z*60.0)*sin(pHit.x*55.0)+0.15*sin((pHit.x+pHit.y+pHit.z)*110.0);
        vec3 alb=vec3(0.34,0.26,0.40)*gre;
        float ao=clamp(1.0-float(steps)/100.0*1.5,0.06,1.0);
        float dif=max(dot(n,normalize(vec3(0.4,0.65,-0.35))),0.0)*0.8+0.10;
        // headlight so near walls read
        float head=max(dot(n,-rd),0.0)*0.35;
        float rim=pow(1.0-max(dot(n,-rd),0.0),3.0);
        col=alb*(dif+head)*ao+alb*rim*0.4;
        // surface neon: SPARSE circuit lines - most walls stay machined grey
        vec3 cell=floor(pHit*1.1);
        float lit=step(0.60,hash31(cell));         // ~40% of cells emit
        float hue=hash31(cell+3.0);
        col+=pal(hue)*exp(-trapAtHit*45.0)*(1.5+2.2*uPulse)*ao*lit;
        col*=exp(-t*0.42);
    }
    col+=glow;
    col*=1.0-0.5*dot(uv,uv);
    col=1.0-exp(-col*1.5);
    float luma=dot(col,vec3(0.299,0.587,0.114));
    col=clamp(mix(vec3(luma),col,1.30),0.0,1.0);
    col=pow(col,vec3(0.4545));
    fragColor=vec4(col,1.0);
}
"""

PRESETS = [
    # (terrace depth, wall radius)
    (1.00, 1.05),
    (1.40, 1.15),
    (0.75, 0.95),
    (1.80, 1.30),
]


def envelopes(audio: Path, start: float, dur: float, fps: int):
    """Onset pulse + bass/high band energies, all attack-decay smoothed."""
    import librosa
    y, sr = librosa.load(str(audio), sr=22050, mono=True,
                         offset=max(0.0, start - 1.0), duration=dur + 2.0)
    off = 1.0 if start >= 1.0 else 0.0
    n = int(round(dur * fps))
    ft = np.arange(n) / fps

    def smooth(e, decay_s):
        out = np.zeros_like(e)
        decay = np.exp(-1.0 / (fps * decay_s))
        acc = 0.0
        for i, v in enumerate(e):
            acc = max(v, acc * decay)
            out[i] = acc
        return np.clip(out, 0.0, 1.5)

    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    tt = librosa.times_like(env, sr=sr, hop_length=512) - off
    pulse = np.interp(ft, tt, env / (np.percentile(env, 95) + 1e-6))

    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    st = librosa.times_like(S[0], sr=sr, hop_length=512) - off
    bass = S[freqs < 150].mean(axis=0)
    high = S[freqs > 4000].mean(axis=0)
    bass = np.interp(ft, st, bass / (np.percentile(bass, 95) + 1e-6))
    high = np.interp(ft, st, high / (np.percentile(high, 95) + 1e-6))
    return smooth(pulse, 0.20), smooth(bass, 0.30), smooth(high, 0.12)


def make_ctx(rw, rh):
    import moderngl
    ctx = moderngl.create_standalone_context()
    prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
    quad = ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], dtype="f4").tobytes())
    vao = ctx.vertex_array(prog, [(quad, "2f", "in_pos")])
    fbo = ctx.framebuffer(color_attachments=[ctx.texture((rw, rh), 3)])
    fbo.use()
    prog["uRes"].value = (float(rw), float(rh))
    return prog, vao, fbo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--preset", type=int, default=1)
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--start", type=float, default=81.92)
    ap.add_argument("--dur", type=float, default=15.0)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    args = ap.parse_args()

    if args.stills:
        w, h = 540, 960
        prog, vao, fbo = make_ctx(w, h)
        tiles = []
        for sc, bore in PRESETS:
            prog["uScale"].value = sc
            prog["uBore"].value = bore
            prog["uTime"].value = 4.0
            prog["uCamZ"].value = 2.2
            prog["uPulse"].value = 0.5
            prog["uBass"].value = 0.6
            prog["uHigh"].value = 0.5
            prog["uFlow"].value = 5.0
            vao.render()
            img = np.frombuffer(fbo.read(components=3), dtype=np.uint8).reshape(h, w, 3)
            tiles.append(np.flipud(img))
        grid = np.concatenate([np.concatenate(tiles[:2], axis=1),
                               np.concatenate(tiles[2:], axis=1)], axis=0)
        from PIL import Image
        args.out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(grid).save(args.out)
        print(f"STILLS {args.out} (presets 0-3, row-major)")
        return

    assert args.audio
    pulse, bass, high = envelopes(args.audio, args.start, args.dur, args.fps)
    n = len(pulse)
    w, h = args.w, args.h
    rw, rh = int(w * 1.5), int(h * 1.5)          # 1.5x supersample
    prog, vao, fbo = make_ctx(rw, rh)
    sc, bore = PRESETS[args.preset]
    prog["uScale"].value = sc
    prog["uBore"].value = bore

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
    cam_z, flow = 0.0, 0.0
    for i in range(n):
        p, b, hi = float(pulse[i]), float(bass[i]), float(high[i])
        cam_z += dt * (0.50 + 0.55 * p)
        flow += dt * (0.6 + 1.2 * p)
        prog["uTime"].value = i * dt
        prog["uCamZ"].value = cam_z
        prog["uPulse"].value = min(p, 1.0)
        prog["uBass"].value = min(b, 1.0)
        prog["uHigh"].value = min(hi, 1.0)
        prog["uFlow"].value = flow
        vao.render()
        ff.stdin.write(fbo.read(components=3))
        if i % 180 == 0:
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
    print(f"BUILT {args.out} ({args.fps}fps)")


if __name__ == "__main__":
    main()
