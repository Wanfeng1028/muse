// Assemble the film: pacing warp → VO tempo-fit → SFX → music → loudnorm → concat → final MP4.
//
// INPUT   $TIMING (timing.json), $RENDERS/NN_<id>.mp4 (one clip per scene, from render_all.sh),
//         $VO (voiceover.mp3 on the ORIGINAL timeline), $MUSIC (one bed), $SFXDIR (the sfx palette)
// OUTPUT  $MIX/warped_${VER}/NN_<id>.mp4, vo_warped.wav, sfx_stem.wav, music_stem.wav,
//         mix_final_${VER}.m4a, and $OUTDIR/<NAME>_${VER}_final.mp4
//
//   node build_mix.mjs stems   # audio only on the NOMINAL timeline — iterate on sound, no video needed
//   node build_mix.mjs warp    # warp whatever scene renders exist (skips already-warped)
//   node build_mix.mjs final   # warp all, MEASURE the warped lengths, build audio to those exact
//                              # lengths (no drift), concat, mux
//
// env: FILM_ROOT · TIMING · RENDERS (default $FILM_ROOT/renders_${VER}) · MIX (default $FILM_ROOT/audio/mix)
//      VO · MUSIC · SFXDIR · VER · NAME (output basename) · OUTDIR · TAIL_CLIP (a supplied end card to append)
//
// Two rules worth repeating:
//  - Always delete a scene's WARPED clip when you delete its render. A stale warped clip has the wrong
//    length, so this script tempo-shifts that scene's VO to match it and nothing errors.
//  - SFX are authored in ORIGINAL time and mapped through W(t). Retime the film and the sound follows.

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';

const ROOT    = process.env.FILM_ROOT || process.cwd();
const VER     = process.env.VER || 'v1';
const NAME    = process.env.NAME || 'film';
const TIMING  = process.env.TIMING  || path.join(ROOT, 'audio/timing.json');
const MIX     = process.env.MIX     || path.join(ROOT, 'audio/mix');
const RENDERS = process.env.RENDERS || path.join(ROOT, `renders_${VER}`);
const SFXDIR  = process.env.SFXDIR  || path.join(ROOT, 'audio/sfx');
const VOFILE  = process.env.VO      || path.join(ROOT, 'audio/voiceover.mp3');
const MUSIC   = process.env.MUSIC   || path.join(MIX, 'music.mp3');
const OUTDIR  = process.env.OUTDIR  || path.join(ROOT, 'Versions');
const TAIL_CLIP = process.env.TAIL_CLIP || '';        // an externally supplied end card, appended hard-cut
const TAIL_DUR  = TAIL_CLIP ? +(process.env.TAIL_DUR || 5.0) : 0;
const WDIR = path.join(MIX, `warped_${VER}`);
const FPS = +(process.env.FPS || 30), W_PX = +(process.env.W || 2560), H_PX = +(process.env.H || 1440);

const T = JSON.parse(fs.readFileSync(TIMING, 'utf8'));
const SC = T.scenes;
fs.mkdirSync(MIX, { recursive: true });

const sh = c => execSync(c, { stdio: ['ignore', 'pipe', 'inherit'], shell: '/bin/bash', maxBuffer: 1 << 26 }).toString();
const probe = f => +sh(`ffprobe -v error -show_entries format=duration -of csv=p=0 "${f}"`).trim();
const has = id => SC.some(s => s.id === id);
const S = id => SC.find(s => s.id === id);
const cue = (id, k) => {                               // cue time in ORIGINAL global time
  const s = S(id); if (!s) throw new Error('no scene ' + id);
  const c = s.cues.find(x => x.key === k); if (!c) throw new Error('no cue ' + id + '/' + k);
  return s.start + c.at;
};
const name = i => `${String(i).padStart(2, '0')}_${SC[i].id}.mp4`;
const srcPath = s => s.startsWith('/') ? s : path.join(SFXDIR, s);

// ---------------------------------------------------------------- 1. pacing
// One nominal speed factor per scene. Typical shape: the opening runs a little hot, the brand beat
// sits at 1.0 so it can breathe, chapters shave 5%, title cards and the close stay at 1.0.
const CHAPTERS = new Set(SC.map(s => s.id).filter(id => /^ch\d/.test(id)));
const OPENING  = new Set(['hook', 'problem', 'threats', 'stall', 'lines']);
const speed = s => OPENING.has(s.id) ? 1.08 : CHAPTERS.has(s.id) ? 1.05 : 1.0;

// segment table: {s, f (audio tempo factor), w0 (warped start), len (warped length)}
let SEG = [], TOTAL_W = 0;
function setSegments(lens) {
  SEG = []; let acc = 0;
  SC.forEach((s, i) => {
    const len = lens ? lens[i] : s.dur / speed(s);
    SEG.push({ s, f: s.dur / len, w0: acc, len });
    acc += len;
  });
  TOTAL_W = +acc.toFixed(3);
}
const W = t => {                                       // original time → warped time
  for (const g of SEG) {
    const a = g.s.start, b = a + g.s.dur;
    if (t < b || g === SEG[SEG.length - 1]) return g.w0 + Math.max(0, t - a) / g.f;
  }
  return TOTAL_W;
};

// ---------------------------------------------------------------- 2. SFX table
// Keep the palette small and physical. Nothing on a transition that has no cause in the picture;
// no whooshes, no riser synths.
function buildEvents() {
  const EV = [];
  const add  = (t, src, vol, dur, note) => EV.push({ t: +W(t).toFixed(3), src, vol, dur, note });
  const TAP   = (t, v = .26, n = 'tap')   => add(t, 'pop.mp3', v, .5, n);            // a card lands
  const CLICK = (t, n = 'click')          => add(t, 'click.mp3', .34, .35, n);       // an allowed cursor action
  const TICK  = (t, v = .20, n = 'tick')  => add(t, 'typewriter.mp3', v, .22, n);    // typing / pipeline step

  // --- opening: typing in the composer, the cards landing on their words
  if (has('hook')) { const p = cue('hook', 'open') + .15; for (let i = 0; i < 11; i++) TICK(p + i * .085, .22, 'type'); }
  if (has('intro')) add(cue('intro', 'name') + .78, 'impact-soft.mp3', .55, 1.6, 'lockup lands');

  // --- chapters: one tap per zoom cue, a click per real interaction
  for (const id of [...CHAPTERS]) {
    if (!has(id)) continue;
    for (const c of S(id).cues) TAP(S(id).start + c.at + .3, .22, `${id} ${c.key}`);
  }

  // --- close
  if (has('close')) add(S('close').start + 1.85, 'impact-low.mp3', .42, 1.5, 'logo reveal');

  EV.sort((a, b) => a.t - b.t);
  fs.writeFileSync(path.join(MIX, 'sfx_events.json'), JSON.stringify({ total: TOTAL_W, events: EV }, null, 1));
  console.log('sfx events', EV.length);
  return EV;
}

// ---------------------------------------------------------------- 3. VO warp
// Slice the VO per scene and atempo each slice to EXACTLY its segment length. Seams sit at scene
// cuts, where the voice is silent, so the joins are inaudible.
function buildVO() {
  const parts = []; let fc = '';
  SEG.forEach((g, i) => {
    const a = g.s.start, b = a + g.s.dur, f = +g.f.toFixed(6);
    fc += `[0:a]atrim=${a}:${b},asetpts=PTS-STARTPTS` +
          (Math.abs(f - 1) > 1e-6 ? `,atempo=${f}` : '') +
          `,atrim=0:${g.len.toFixed(6)},apad=whole_dur=${g.len.toFixed(6)}[p${i}];`;
    parts.push(`[p${i}]`);
  });
  fc += `${parts.join('')}concat=n=${SEG.length}:v=0:a=1[out]`;
  sh(`ffmpeg -y -loglevel error -i "${VOFILE}" -filter_complex "${fc}" -map "[out]" -ar 48000 -ac 2 "${MIX}/vo_warped.wav"`);
  console.log('vo_warped.wav', probe(`${MIX}/vo_warped.wav`).toFixed(3), 'target', TOTAL_W);
}

// ---------------------------------------------------------------- 4. SFX stem
function buildSFX(EV) {
  const inputs = EV.map(e => `-i "${srcPath(e.src)}"`).join(' ');
  let fc = `[0:a]atrim=0:${TOTAL_W}[base];`;
  const lab = ['[base]'];
  EV.forEach((e, i) => {
    const d = Math.round(e.t * 1000);
    fc += `[${i + 1}:a]atrim=0:${e.dur},afade=t=out:st=${Math.max(0, e.dur - .12).toFixed(3)}:d=0.12,` +
          `volume=${e.vol},adelay=${d}|${d}[e${i}];`;
    lab.push(`[e${i}]`);
  });
  fc += `${lab.join('')}amix=inputs=${lab.length}:duration=first:normalize=0[out]`;
  sh(`ffmpeg -y -loglevel error -f lavfi -i "anullsrc=r=48000:cl=stereo" ${inputs} ` +
     `-filter_complex "${fc}" -map "[out]" -t ${TOTAL_W} "${MIX}/sfx_stem.wav"`);
  console.log('sfx_stem.wav');
}

// ---------------------------------------------------------------- 5. music
// A bed with a known BPM and first-beat phase, offset so a beat lands on ANCHOR (the moment the
// picture asks for one), low-passed and quiet until then, then opened, and sidechained under the voice.
const BPM = +(process.env.BPM || 120);
const BEAT = 60 / BPM, PHASE = +(process.env.MUSIC_PHASE || 0.5);
function buildMusic() {
  const ANCHOR = has('intro') ? W(cue('intro', 'name') + .78) : 0;   // put a beat here
  const k = Math.ceil((ANCHOR - PHASE) / BEAT);
  const SS = +((PHASE + k * BEAT) - ANCHOR).toFixed(3);              // trim offset that lands the beat
  const A = ANCHOR + .3, B = A - .6;                                 // crossfade window into the open bed
  const fc =
    `[0:a]atrim=${SS}:${SS + A},asetpts=PTS-STARTPTS,lowpass=f=900,volume=0.62[a];` +
    `[1:a]atrim=${SS + B}:${SS + TOTAL_W + 1},asetpts=PTS-STARTPTS[b];` +
    `[a][b]acrossfade=d=0.6:c1=tri:c2=tri[m];` +
    `[m]atrim=0:${TOTAL_W},afade=t=in:st=0:d=1.2,afade=t=out:st=${TOTAL_W - 3.4}:d=3.4[mm];` +
    `[2:a]aformat=sample_rates=48000:channel_layouts=stereo[vo];` +
    `[mm]aformat=sample_rates=48000:channel_layouts=stereo[mf];` +
    `[mf][vo]sidechaincompress=threshold=0.012:ratio=12:attack=20:release=500:makeup=1:level_sc=1[out]`;
  sh(`ffmpeg -y -loglevel error -i "${MUSIC}" -i "${MUSIC}" -i "${MIX}/vo_warped.wav" ` +
     `-filter_complex "${fc}" -map "[out]" -t ${TOTAL_W} "${MIX}/music_stem.wav"`);
  console.log('music_stem.wav  offset', SS, 'anchor at', ANCHOR.toFixed(2));
}

// ---------------------------------------------------------------- 6. master
const MUSIC_VOL = +(process.env.MUSIC_VOL || 0.40), SFX_VOL = 1.0, VO_VOL = 1.0;
function mixAudio(out) {
  const raw = out.replace(/\.m4a$/, '_raw.wav');
  sh(`ffmpeg -y -loglevel error -i "${MIX}/vo_warped.wav" -i "${MIX}/music_stem.wav" -i "${MIX}/sfx_stem.wav" ` +
     `-filter_complex "[0:a]volume=${VO_VOL}[v];[1:a]volume=${MUSIC_VOL}[m];[2:a]volume=${SFX_VOL}[s];` +
     `[v][m][s]amix=inputs=3:duration=first:normalize=0[out]" -map "[out]" -t ${TOTAL_W} "${raw}"`);
  // TWO-PASS loudnorm (one pass is dynamic and pumps): measure, then apply linearly.
  const m = execSync(`ffmpeg -i "${raw}" -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null - 2>&1`,
                     { shell: '/bin/bash', maxBuffer: 1 << 26 }).toString();
  const a0 = m.lastIndexOf('{'), b0 = m.indexOf('}', a0);
  const j = JSON.parse(m.slice(a0, b0 + 1));
  sh(`ffmpeg -y -loglevel error -i "${raw}" -af "loudnorm=I=-16:TP=-1.5:LRA=11:` +
     `measured_I=${j.input_i}:measured_TP=${j.input_tp}:measured_LRA=${j.input_lra}:` +
     `measured_thresh=${j.input_thresh}:offset=${j.target_offset}:linear=true` +
     (TAIL_DUR ? `,apad=pad_dur=${TAIL_DUR}` : '') + `" -ar 48000 -c:a aac -b:a 256k "${out}"`);
  console.log('mix →', out, '(input', j.input_i, 'LUFS → -16)');
}

// ---------------------------------------------------------------- 7. video
function warpExisting(strict) {
  fs.mkdirSync(WDIR, { recursive: true });
  let n = 0;
  SC.forEach((s, i) => {
    const src = path.join(RENDERS, name(i)), out = path.join(WDIR, name(i));
    if (!fs.existsSync(src)) { if (strict) throw new Error('missing render ' + src); return; }
    if (fs.existsSync(out)) return;                   // delete the warped twin when you delete a render
    const f = speed(s), tmp = out + '.part.mp4';
    sh(`ffmpeg -y -loglevel error -i "${src}" -an -vf "setpts=PTS/${f},fps=${FPS}" ` +
       `-c:v libx264 -crf 17 -preset medium -pix_fmt yuv420p -g ${FPS} "${tmp}"`);
    fs.renameSync(tmp, out); n++;
    console.log('warped', s.id, f);
  });
  console.log('warped', n, 'new');
}

function buildFinal() {
  warpExisting(true);
  // MEASURE the warped lengths and rebuild the segment table from them: warping never lands exactly
  // on dur/f, and building the audio to nominal lengths drifts a frame or two per scene.
  const lens = SC.map((s, i) => probe(path.join(WDIR, name(i))));
  setSegments(lens);
  console.log('video-measured total', TOTAL_W, 'nominal', SC.reduce((a, s) => a + s.dur / speed(s), 0).toFixed(3));

  const EV = buildEvents(); buildVO(); buildSFX(EV); buildMusic();

  const tail = path.join(WDIR, 'zz_tail.mp4');
  if (TAIL_CLIP && !fs.existsSync(tail)) {
    sh(`ffmpeg -y -loglevel error -i "${TAIL_CLIP}" -an -vf "scale=${W_PX}:${H_PX}:flags=lanczos,fps=${FPS},format=yuv420p" ` +
       `-c:v libx264 -crf 17 -preset medium -pix_fmt yuv420p -g ${FPS} "${tail}"`);
  }
  // concat -c copy is only valid because every clip was encoded with identical settings
  fs.writeFileSync(path.join(WDIR, 'concat.txt'),
    SC.map((s, i) => `file '${path.join(WDIR, name(i))}'`).concat(TAIL_CLIP ? [`file '${tail}'`] : []).join('\n'));
  sh(`ffmpeg -y -loglevel error -f concat -safe 0 -i "${WDIR}/concat.txt" -c copy "${WDIR}/_video.mp4"`);
  console.log('video', probe(`${WDIR}/_video.mp4`), 'audio', TOTAL_W + TAIL_DUR);

  fs.mkdirSync(OUTDIR, { recursive: true });
  const m4a = path.join(MIX, `mix_final_${VER}.m4a`);
  mixAudio(m4a);
  const final = path.join(OUTDIR, `${NAME}_${VER}_final.mp4`);
  sh(`ffmpeg -y -loglevel error -i "${WDIR}/_video.mp4" -i "${m4a}" -c:v copy -c:a copy -shortest -movflags +faststart "${final}"`);
  console.log('→', final, probe(final));
}

const mode = process.argv[2] || 'stems';
if (mode === 'stems') { setSegments(null); const EV = buildEvents(); buildVO(); buildSFX(EV); buildMusic(); mixAudio(path.join(MIX, 'mix_preview.m4a')); }
else if (mode === 'warp')  { setSegments(null); warpExisting(false); }
else if (mode === 'final') { setSegments(null); buildFinal(); }
else { console.error('usage: build_mix.mjs stems|warp|final'); process.exit(1); }
