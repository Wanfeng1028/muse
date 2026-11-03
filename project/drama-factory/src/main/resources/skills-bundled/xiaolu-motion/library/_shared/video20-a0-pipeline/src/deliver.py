"""Phase 2: accept A1-A3 segments, mix, render, deliver candidates, QA.  Each heavy step runs through
with_heavy_lock.py (2 slots machine-wide, CPU budget 4 threads per task).
usage: python3 deliver.py accept | sfx | mix | render | package | qa | report | all
Outputs (07_delivery/): 视频20_候选_v1_含BGM.mp4, 视频20_候选_v1_无BGM.mp4, 视频20_候选_v1_手机预览.mp4, 视频20_候选_v1.srt/.ass,
QA_REPORT.md (+ a0/qa/*.json evidence)."""
import json
import re
import subprocess
import sys

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from a0common import *  # noqa

HERE = Path(__file__).resolve().parent
LOCK = [sys.executable, str(HERE / 'with_heavy_lock.py')]
DEL = VP / '07_delivery'
TAG = '视频20_候选_v1'
WORKV = A0 / 'work/cand_v1_video.mp4'
SFXJ = A0 / 'work/sfx_merged_cand_v1.json'
PLATFORMS = ['剪映', 'CapCut', 'Claude', 'Codex', 'GitHub', 'Github', '小红书', '抖音', 'TikTok', '快手', 'B站', 'bilibili', 'YouTube',
             '微信', '视频号', 'ChatGPT', 'OpenAI', 'Gemini', 'Cursor', '豆包', 'Kimi', 'Premiere', 'Final Cut', 'Anthropic']


def run(cmd, heavy=False):
    cmd = [str(c) for c in cmd]
    print('>>', ' '.join(cmd)[:160], flush=True)
    subprocess.run((LOCK + cmd) if heavy else cmd, check=True)


def accept():
    rows = []
    for sid, a, b, owner in SHOTS:
        if owner == 'A0':
            continue
        d = SHOTS_DIR / f's{sid}'
        ok = (d / 'DONE.json').exists() and (d / 'segment.mp4').exists()
        row = dict(shot=sid, owner=owner, frames_expected=b - a, delivered=ok)
        if ok:
            done = load_json(d / 'DONE.json')
            n = int(subprocess.run(['ffprobe', '-v', 'error', '-count_packets', '-select_streams', 'v:0', '-show_entries',
                                    'stream=nb_read_packets', '-of', 'csv=p=0', str(d / 'segment.mp4')], capture_output=True,
                                   text=True).stdout)
            pr = ffprobe_json(d / 'segment.mp4')
            v = [s for s in pr['streams'] if s['codec_type'] == 'video'][0]
            row.update(frames=n, sha_ok=done.get('sha256') == sha256(d / 'segment.mp4'), audio_streams=sum(
                s['codec_type'] == 'audio' for s in pr['streams']), spec=f"{v['width']}x{v['height']} {v['pix_fmt']} {v.get('color_range')} "
                f"{v.get('color_space')} {v['r_frame_rate']} {v.get('profile')}", qa=done.get('qa'))
            row['ok'] = row['frames'] == row['frames_expected'] and row['sha_ok'] and row['audio_streams'] == 0
            row['sync'] = sync_check(d / 'segment.mp4', a, b)
            row['ok'] = row['ok'] and all(x['best'] == 0 for x in row['sync'] if x['meaningful'])
        rows.append(row)
    save_json(A0 / 'qa/accept_segments.json', rows)
    for r in rows:
        print(r)
    return all(r.get('ok') for r in rows)


def _gray(path, f, start_frame_offset=0):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '4', '-ss', f'{(f - 0.5) / FPS:.6f}', '-i', str(path), '-frames:v', '1',
                          '-vf', 'scale=270:480:flags=area,format=gray', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    import numpy as np
    return np.frombuffer(raw, np.uint8).reshape(480, 270).astype(float)


def sync_check(seg, a, b):
    """segment frames i in {0, 1/3, 2/3, last} vs plate frames a+i-1, a+i, a+i+1 (PSNR); best offset must be 0 when
    the frame still shows the live footage (best PSNR > 30 dB), otherwise the frame is fully graphic (not meaningful)"""
    import numpy as np
    n = b - a
    out = []
    for i in sorted({0, n // 3, 2 * n // 3, n - 1}):
        S = _gray(seg, i)
        ps = {}
        for dlt in (-1, 0, 1):
            if 0 <= a + i + dlt < TOTAL:
                P = _gray(LOCKED / 'plate_v2_video.mp4', a + i + dlt)
                m = ((S - P) ** 2).mean()
                ps[dlt] = 99.0 if m == 0 else round(float(10 * np.log10(255 ** 2 / m)), 1)
        best = max(ps, key=ps.get)
        out.append(dict(i=i, v2_frame=a + i, psnr=ps, best=best, meaningful=ps[best] > 30 and ps[best] - min(ps.values()) > 1.0))
    return out


def keyword_sfx_check(cues):
    """impact-type cues near a keyword onset: |offset| <= 2 frames"""
    W2 = load_json(CAPS / 'words_v2.json')
    impact = {'hit', 'stamp', 'pop_soft', 'pluck', 'impact_soft', 'impact_big', 'tock', 'clack', 'land', 'blip', 'bell',
              'tick', 'laser_zip', 'shimmer', 'glitch', 'ident_hop'}
    out = []
    for k in W2['keywords']:
        near = [c for c in cues if c['id'] in impact and abs(float(c['t']) - k['s']) <= 0.35]
        if not near:
            out.append(dict(shot=k['shot'], keyword=k['text'], onset=k['s'], cue=None))
            continue
        c = min(near, key=lambda c: abs(float(c['t']) - k['s']))
        off = round((float(c['t']) - k['s']) * FPS, 1)
        out.append(dict(shot=k['shot'], keyword=k['text'], onset=k['s'], cue=c['id'], cue_t=float(c['t']), source=c.get('source'),
                        offset_frames=off, ok=abs(off) <= 2))
    return out


def font_check():
    """every character A0 draws exists in the font it is drawn with (no tofu)"""
    from fontTools.ttLib import TTFont
    cm = {w: set(TTFont(str(FONTS / f'SourceHanSansSC-{w}.otf'), fontNumber=0, lazy=True).getBestCmap()) for w in ('Medium', 'Heavy', 'Bold')}
    texts = [r['text'] for r in load_json(CAPS / 'captions_v2.json')['strips']]
    texts += ['不会剪辑也能做出', '这样的视频', '成片 · vlog', '成片 · 科普', '成片 · 不露脸', '不想剪辑', '不会剪辑', '免费', '开源', 'OPEN',
              'SOURCE', '文档', '工具清单', '动效库', '音效库', '风格包', '个步骤', '4', '4 步', 'v1.0', '第一版', '第二曲线', '点赞', '收藏', '评论',
              '关注', '1 选题', '2 风格', '3 分镜', '4 成片', '此镜动效制作中']
    miss = sorted({ch for t in texts for ch in t if ch.strip() and not all(ord(ch) in cm[w] for w in cm)})
    return dict(strings=len(texts), missing=miss)


def ocr_platforms(video):
    """Apple Vision text recognition (xiaolu-motion qa/vision.py, read-only) every 0.5 s, windows of 100 frames"""
    sys.path.insert(0, str(XM))
    import os
    cwd = os.getcwd()
    os.chdir(XM)
    from qa.vision import analyze
    frames = list(range(0, TOTAL, 15))
    hits, n_lines = [], 0
    for i in range(0, len(frames), 100):
        r = analyze(str(video), frames[i:i + 100], faces=False, text=True)
        for fr in r['frames']:
            for t in fr.get('text', []) or []:
                s = t.get('text', '') if isinstance(t, dict) else str(t)
                n_lines += 1
                for p in PLATFORMS:
                    if p.lower() in s.lower():
                        hits.append(dict(frame=fr.get('frame', fr.get('n')), text=s, platform=p))
    os.chdir(cwd)
    return dict(frames=len(frames), lines=n_lines, hits=hits)


def main():
    step = sys.argv[1]
    steps = ['accept', 'sfx', 'mix', 'render', 'package', 'qa', 'report'] if step == 'all' else [step]
    for s in steps:
        if s == 'accept':
            assert accept(), 'segments missing or not acceptable'
        elif s == 'sfx':
            run([sys.executable, HERE / 'assemble_audio.py', 'sfx', SFXJ])
        elif s == 'mix':
            run([sys.executable, HERE / 'mix.py', 'programme', SFXJ], heavy=True)
        elif s == 'render':
            run([sys.executable, HERE / 'a0render.py', 'video', WORKV, '--workers', '2', '--crf', '16'], heavy=True)
        elif s == 'package':
            run([sys.executable, HERE / 'assemble_audio.py', 'mux', WORKV, AUDIO / 'mix_v2_bgm1.wav', DEL / f'{TAG}_含BGM.mp4'], heavy=True)
            run([sys.executable, HERE / 'assemble_audio.py', 'mux', WORKV, AUDIO / 'mix_v2_nobgm.wav', DEL / f'{TAG}_无BGM.mp4'], heavy=True)
            part = DEL / f'{TAG}_手机预览.mp4.partial'
            run(['ffmpeg', '-v', 'error', '-y', '-threads', '4', '-i', DEL / f'{TAG}_含BGM.mp4', '-vf', 'scale=720:1280:flags=lanczos',
                 '-c:v', 'libx264', '-preset', 'medium', '-b:v', '2000k', '-maxrate', '2400k', '-bufsize', '4800k', '-profile:v', 'high',
                 '-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
                 '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-f', 'mp4', part], heavy=True)
            Path(part).replace(DEL / f'{TAG}_手机预览.mp4')
            for ext in ('srt', 'ass'):
                src = CAPS / f'captions_v2_burn.{ext}'
                (DEL / f'{TAG}.{ext}').write_bytes(src.read_bytes())
        elif s == 'qa':
            cand = DEL / f'{TAG}_含BGM.mp4'
            run([sys.executable, HERE / 'qa_draft.py', cand, str(WORKV) + '.items.jsonl', A0 / 'qa/cand_v1_tech.json'], heavy=True)
            run([sys.executable, HERE / 'qa_draft.py', DEL / f'{TAG}_无BGM.mp4', '-', A0 / 'qa/cand_v1_nobgm_tech.json'], heavy=True)
            run([sys.executable, HERE / 'pixel_qa_v20.py', cand, CAPS / 'captions_v2_burn.srt', A0 / 'qa/pixel_v20'], heavy=True)
            cues = load_json(SFXJ)
            save_json(A0 / 'qa/cand_v1_extra.json', dict(keyword_sfx=keyword_sfx_check(cues), fonts=font_check()))
            # platform-name OCR comes out of the pixel QA pass (pixel_qa_v20.json -> ocr.platform_hits)
        elif s == 'report':
            print('write QA_REPORT.md from a0/qa/cand_v1_*.json (done by the A0 session, not automated)')


if __name__ == '__main__':
    main()
