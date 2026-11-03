#!/usr/bin/env python3
"""xlaudio command line.

  python3 cli.py list                                   ids by family
  python3 cli.py sfx hit -o hit.wav [--seed 3] [-p pitch=2 -p bright=0.7]
  python3 cli.py cues storyboard.json --duration 42.5 -o sfx_track.wav [--log cues_log.json]
  python3 cli.py mix --voice v.wav --bgm path/to/your_bgm.mp3 \\
                     [--sfx sfx_track.wav] -o final.wav [--bgm-start 12] [--duck-db -6] [--release-ms 600]
  python3 cli.py score -o bed.wav --duration 30 [--bpm 120 --key "D minor" --energy 0:0.3,16:0.9
                       --section drums_in=8 --section drop=16 --loop]
  python3 cli.py grid --bpm 120 --fps 30 --bars 8 [--jianying-beat file.beat]
  python3 cli.py analyze file.wav                        ebur128 + checks + spectrogram/levels png
  python3 cli.py catalog                                 regenerate sfx/CATALOG.md
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import xlaudio as xa  # noqa: E402


def _val(s):
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            pass
    return s


def cmd_list(a):
    for fam in ('motion', 'ident', 'sfx'):
        print('[%s]' % fam, ' '.join(xa.list_sfx(fam)))


def cmd_sfx(a):
    params = dict(kv.split('=', 1) for kv in (a.param or []))
    params = {k: _val(v) for k, v in params.items()}
    y = xa.render_sfx(a.id, seed=a.seed, **params)
    xa.write_wav(a.out, y, bits=24)
    print('%s: %.3f s -> %s' % (a.id, y.shape[1] / xa.SR, a.out))


def cmd_cues(a):
    y, log = xa.render_cues(a.cues, a.duration, out_path=a.out, return_log=True)
    if a.log:
        with open(a.log, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=1)
    print('%d cues -> %s (%.2f s)' % (len(log), a.out, y.shape[1] / xa.SR))


def cmd_mix(a):
    rep = xa.mix_with_voice(os.path.expanduser(a.voice), os.path.expanduser(a.bgm) if a.bgm else None,
                            a.sfx, a.out, target_lufs=a.target, bgm_start=a.bgm_start, bgm_rel_lu=a.bgm_rel_lu,
                            duck_db=a.duck_db, release_ms=a.release_ms, attack_ms=a.attack_ms, hold_ms=a.hold_ms,
                            bgm_fit=a.bgm_fit, report_path=a.out.rsplit('.', 1)[0] + '.mix_report.json')
    o = rep['output']
    print('-> %s  I=%.1f LUFS  TP=%.1f dBTP  LRA=%.1f LU  (voice in I=%.1f TP=%.1f)' % (
        a.out, o['I_LUFS'], o['TP_dBTP'], o['LRA_LU'], rep['voice_in']['I_LUFS'], rep['voice_in']['TP_dBTP']))


def cmd_score(a):
    from xlaudio.score import render_score
    energy = None
    if a.energy:
        energy = [tuple(float(x) for x in p.split(':')) for p in a.energy.split(',')]
    sections = {k: _val(v) for k, v in (s.split('=', 1) for s in (a.section or []))}
    r = render_score(a.preset, duration=a.duration, bpm=a.bpm, key=a.key, energy=energy, sections=sections,
                     loop=a.loop, seed=a.seed, target_lufs=a.target)
    r.save(a.out)
    print('-> %s (+ .json bar grid), %.2f s, %d bars' % (a.out, r.audio.shape[1] / xa.SR, len(r.meta['bars'])))


def cmd_grid(a):
    if a.jianying_beat:
        bm = xa.load_jianying_beat(a.jianying_beat, fps=a.fps)
        print(json.dumps(dict(tempo=bm.tempo(), beats=bm.table()[: a.bars * 4]), indent=1))
        return
    g = xa.BeatGrid(a.bpm, a.beats_per_bar, a.offset, a.fps)
    print(json.dumps(dict(bpm=g.bpm, bar_s=g.bar_s, beat_s=g.beat_s, frame_error_ms=g.frame_error_ms(),
                          frame_locked_bpms=[x['bpm'] for x in xa.frame_locked_bpms(a.fps, 60, 180)],
                          beats=g.table(g.bar_time(a.bars))), ensure_ascii=False, indent=1))


def cmd_analyze(a):
    from xlaudio import analysis as an
    r = an.analyze(a.wav, a.wav.rsplit('.', 1)[0], os.path.basename(a.wav))
    print(json.dumps({k: r[k] for k in ('ffmpeg', 'own_meter', 'pass', 'clicks')}, indent=1, default=float))


def _range(p):
    d, lo, hi, note = p
    if lo is None:
        return '%s（默认 %s）' % (note, d)
    return '%s..%s（默认 %s）' % (lo, hi, d)


def cmd_catalog(a):
    from xlaudio.sfx import catalog_rows
    L = []
    A = L.append
    A('# 音效与声音标识清单（CATALOG）')
    A('')
    A('> 本文件由 `python3 cli.py catalog` 从代码里的注册表生成，改音效请改 `xlaudio/*.py` 再重新生成，不要手改。')
    A('> 全部声音由 Python 代码合成（振荡器、FM、加法合成、滤波噪声、合成冲激响应），无采样、无音色库、无 AI 音乐服务，'
      '无第三方授权问题。48 kHz 立体声，同一组 (id, 参数, seed) 每次渲染逐采样一致。')
    A('')
    A('## 怎么用')
    A('')
    A('```python')
    A('import xlaudio as xa')
    A("y = xa.render_sfx('hit', seed=0, pitch=0, bright=0.6)        # (2, n) float64, 48 kHz")
    A("track = xa.render_cues([{'id': 'enter', 'at': 3.20, 'align': 'motion'},")
    A("                        {'id': 'land',  'at': 3.70},")
    A("                        {'id': 'reveal', 'at': 8.00, 'align': 'anchor', 'gain_db': -2}], duration=42.5)")
    A('```')
    A('')
    A('cue 字段与分镜 JSON 的 `sfx` 字段一致：`id`、`at`（秒）、`gain_db`、`pan`（-1..1）、`params`；可选 `seed`、`align`、'
      '`fps`，也接受 `frame` 代替 `at`。')
    A('')
    A('**对位规则（30 fps）**')
    A('')
    A('- whoosh 型（enter、push、whoosh_*）：声音比画面动作开始提前 3–4 帧。写 `align: "motion"`，`at` 填动作开始的时间，'
      '渲染器按各音效的 `lead_frames` 自动提前（enter 3.5 帧、push 3 帧、whoosh_fast 3.5 帧、whoosh_mid 5 帧、whoosh_slow 10 帧）。')
    A('- impact 型（land、hit、impact_*、stamp、tock、clack）：瞬态与落定同帧。`at` 填落定那一帧，`align` 用默认的 `start`（或 `motion`，提前量为 0）。')
    A('- 有锚点的（reveal、ident_*）：写 `align: "anchor"`，`at` 填需要对齐的那一帧（墨迹触纸 / Logo 落定 / 剪辑点），'
      '锚点之前的预备声会自动排在前面。')
    A('- 结尾对齐的（riser、reverse_whoosh）：写 `align: "end"`，声音的结尾正好落在 `at`。')
    A('- `align: "peak"`：把最响的 10 ms 对准 `at`，适合手动对 whoosh。')
    A('')
    A('**参考电平**：`gain_db = 0` 时，每个音效已归一到下表的参考值（短促瞬态用真峰值 TP，持续声用 400 ms 最大瞬时响度 '
      'M-max），按“人声 −16 LUFS”设计；`mix_with_voice` 母带阶段整体平移，比例不变。需要更响或更轻就调 `gain_db`。')
    A('')
    A('**通用参数**：`pitch` 半音（整族一起移调时每个视频用同一个值）、`bright` 0..1 亮度、`dur` 秒、`seed` 随机种子（只影响噪声类细节）。')
    A('')
    titles = {'motion': '1. 样片动作音效（5 个，同一音色家族）', 'ident': '2. 声音标识（两音动机，3 个候选 × 片头 / 转场两版）',
              'sfx': '3. 通用音效库（保留，不再扩充）'}
    for fam in ('motion', 'ident', 'sfx'):
        rows = catalog_rows(fam)
        A('## ' + titles[fam])
        A('')
        if fam == 'motion':
            A('共同的合成材料：带通噪声“空气声” + crystal FM 拨弦 / celesta（D 大调五声音阶）+ 正弦鼓体与次低频 + 同一套合成板式 / 大厅混响。')
            A('')
        if fam == 'ident':
            A('三个候选各是一个“短拾音 → 长落点”的两音动机。片头版保留完整尾音，转场版把两音间隔收紧到 90 ms、尾巴缩短并加一道快速空气声，'
              '音程和音色不变，所以两处听起来是同一个品牌。等用户试听后选定一个。')
            A('')
        A('| id | 用途 | 对位规则 | 锚点 / 提前 | 参考电平 | 默认时长 | 参数 |')
        A('|---|---|---|---|---|---|---|')
        for r in rows:
            spec = xa.get_spec(r['id'])
            prm = '；'.join('`%s` %s' % (k, _range(v)) for k, v in r['params'].items())
            anc = r['anchor'] + ('' if not spec.lead_frames else '，提前 %.1f 帧' % spec.lead_frames)
            if r['anchor'] == 'mark' and spec.mark_s is not None:
                try:
                    from xlaudio.sfx import _resolve
                    anc = 'mark @ %.2f s' % spec.mark_s(_resolve(spec, {})) + (
                        '' if not spec.lead_frames else '，提前 %.1f 帧' % spec.lead_frames)
                except Exception:
                    pass
            A('| `%s` | %s | %s | %s | %s | %.2f s | %s |' % (r['id'], r['purpose'], r['sync'], anc, r['ref'],
                                                             r['default_len'], prm))
        A('')
        A('合成方式：')
        A('')
        for r in rows:
            A('- `%s`：%s' % (r['id'], r['notes']))
        A('')
    A('## 试听')
    A('')
    A('`examples/out/sfx_sampler.wav`：按上面的顺序，每个 id 两个变体（默认参数 seed 0；第二组参数 seed 1），间隔 0.5 s，'
      '保持参考电平。时间点见 `examples/out/sfx_sampler.cues.json`。')
    path = os.path.join(HERE, 'sfx', 'CATALOG.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    print('->', path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list').set_defaults(fn=cmd_list)
    p = sub.add_parser('sfx')
    p.add_argument('id')
    p.add_argument('-o', '--out', required=True)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('-p', '--param', action='append', help='name=value')
    p.set_defaults(fn=cmd_sfx)
    p = sub.add_parser('cues')
    p.add_argument('cues')
    p.add_argument('--duration', type=float, required=True)
    p.add_argument('-o', '--out', required=True)
    p.add_argument('--log')
    p.set_defaults(fn=cmd_cues)
    p = sub.add_parser('mix')
    p.add_argument('--voice', required=True)
    p.add_argument('--bgm')
    p.add_argument('--sfx')
    p.add_argument('-o', '--out', required=True)
    p.add_argument('--target', type=float, default=-14.0)
    p.add_argument('--bgm-start', type=float, default=0.0)
    p.add_argument('--bgm-rel-lu', type=float, default=-6.0)
    p.add_argument('--bgm-fit', choices=['trim', 'loop'], default='trim')
    p.add_argument('--duck-db', type=float, default=-6.0)
    p.add_argument('--attack-ms', type=float, default=60.0)
    p.add_argument('--hold-ms', type=float, default=250.0)
    p.add_argument('--release-ms', type=float, default=600.0)
    p.set_defaults(fn=cmd_mix)
    p = sub.add_parser('score')
    p.add_argument('-o', '--out', required=True)
    p.add_argument('--preset', default='coldlight_ambient')
    p.add_argument('--duration', type=float, default=30.0)
    p.add_argument('--bpm', type=float)
    p.add_argument('--key')
    p.add_argument('--energy', help='t:e,t:e,...')
    p.add_argument('--section', action='append', help='name=seconds or name=bar:N')
    p.add_argument('--loop', action='store_true')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--target', type=float, default=-14.0)
    p.set_defaults(fn=cmd_score)
    p = sub.add_parser('grid')
    p.add_argument('--bpm', type=float, default=120.0)
    p.add_argument('--fps', type=float, default=30.0)
    p.add_argument('--beats-per-bar', type=int, default=4)
    p.add_argument('--offset', type=float, default=0.0)
    p.add_argument('--bars', type=int, default=4)
    p.add_argument('--jianying-beat')
    p.set_defaults(fn=cmd_grid)
    p = sub.add_parser('analyze')
    p.add_argument('wav')
    p.set_defaults(fn=cmd_analyze)
    sub.add_parser('catalog').set_defaults(fn=cmd_catalog)
    a = ap.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
