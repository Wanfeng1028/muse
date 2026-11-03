"""样片动作音效 (motion family): five effects, one per visual action, built from
one synth palette so they read as a family:

    air     band-passed noise swish (same SVF / Q / air layer everywhere)
    crystal FM 1:2 crystal pluck + FM 1:1 celesta, tuned to D major pentatonic
    body    pitched sine thump (D3 / D2 region) + sub
    space   the same synthetic plate / hall impulse responses

| id     | action                        | sync (30 fps)                                          |
|--------|-------------------------------|--------------------------------------------------------|
| enter  | 元素入场 (slide / scale in)    | whoosh type: starts 3-4 frames before the element moves |
| land   | 落定 / 圆窗落位                 | impact type: transient on the landing frame            |
| push   | 推近 (camera push-in)          | whoosh type: starts 3 frames before the push; dur = push + lead, peak at the end |
| reveal | 揭示 / 墨入纸转场               | anchor (0.35 s) on the frame the ink touches / new image appears |
| hit    | L3 强调落地                    | impact type: transient on the emphasis landing frame   |

``pitch`` transposes the whole family together (keep one value per video so the
tonal parts agree with the ident and with each other).
"""
import numpy as np

from . import instruments as ins
from .dsp import SR, TWOPI, smp, midi, semis, noise, bpf, lp, hp, stereo, rc_ramp, add_at, att_curve as _att
from .sfx import SfxSpec, register, _space

ROOT = 'D'


def _m(name, pitch):
    return midi(name) + pitch


def _air(dur, f_lo, f_hi, peak, pan0, pan1, seed, bright, shape='swell'):
    return ins.whoosh(dur, f_lo, min(f_hi * 2 ** (bright - 0.5), 12000.0), shape, q=1.1, pan0=pan0, pan1=pan1,
                      seed=seed, lowmix=0.3, fade_out=0.006, peak=peak, air=0.2 * bright)


def _body(f0, dur=0.3, decay=0.09, drop=0.5):
    n = smp(dur)
    t = np.arange(n) / SR
    f = f0 * (1 + drop * np.exp(-t / 0.012))
    y = np.sin(TWOPI * np.cumsum(f) / SR) * _att(t, 0.0012) * np.exp(-t / decay)
    y[-smp(0.01):] *= rc_ramp(smp(0.01))[::-1]
    return y


class _Tl:
    def __init__(self, total):
        self.out = np.zeros((2, smp(total)))

    def add(self, sig, t, pan=0.0, gain=1.0):
        st = stereo(sig, pan) if sig.ndim == 1 else sig
        add_at(self.out, st * gain, smp(t))


# ----------------------------------------------------------------------------
def _enter(rng, seed, pitch=0.0, bright=0.5, dur=0.30, travel=0.3):
    r = semis(pitch)
    tl = _Tl(dur + 0.6)
    tl.add(_air(dur, 900 * r, 4200 * r, 0.8, -travel, travel, seed * 7 + 101, bright) * 0.9, 0.0)
    tl.add(ins.crystal_pluck(_m('A6', pitch), 0.30, 0.6, 2.0, 0.6 + 0.6 * bright, seed=seed + 1, decay=0.12),
           dur - 0.01, pan=travel * 0.6)
    y = _space(tl.out, 0.15, 'plate', tail=0.0)
    return y


def _land(rng, seed, pitch=0.0, bright=0.5):
    r = semis(pitch)
    tl = _Tl(0.9)
    tl.add(_body(147.0 * r, 0.35, 0.09), 0.0)
    tl.add(_body(73.4 * r, 0.40, 0.14, drop=0.3) * 0.5, 0.0)
    n = smp(0.06)
    t = np.arange(n) / SR
    puff = bpf(noise(n, seed * 11 + 5), 400 * r, 2500 * r * 2 ** (bright - 0.5)) * _att(t, 0.0006) * np.exp(-t / 0.012)
    tl.add(puff * 0.45, 0.0)
    tl.add(ins.crystal_pluck(_m('D5', pitch), 0.28, 0.6, 2.0, 0.5 + 0.5 * bright, seed=seed + 2, decay=0.16), 0.0)
    tl.add(ins.crystal_pluck(_m('D5', pitch), 0.06, 0.4, 2.0, 0.4, seed=seed + 3, decay=0.1), 0.085, pan=0.15)
    return _space(tl.out, 0.15, 'plate', tail=0.0)


def _push(rng, seed, pitch=0.0, bright=0.5, dur=0.7):
    r = semis(pitch)
    tl = _Tl(dur + 0.35)
    tl.add(_air(dur, 300 * r, 2400 * r, 0.88, -0.2, -0.6, seed * 7 + 111, bright) * 0.7, 0.0)
    tl.add(_air(dur, 310 * r, 2500 * r, 0.88, 0.2, 0.6, seed * 7 + 113, bright) * 0.7, 0.0)
    rs = ins.riser(dur, 146.8 * r, seed=seed * 7 + 117, vel=0.35, octaves=0.5, fc_end=2500 + 2500 * bright)
    tl.add(rs, 0.0)
    y = _space(tl.out, 0.2, 'plate', tail=0.0)
    return y


REVEAL_MARK = 0.35


def _reveal(rng, seed, pitch=0.0, bright=0.5, dur=1.8):
    r = semis(pitch)
    M = REVEAL_MARK
    tl = _Tl(M + dur)
    pre = ins.whoosh(M, 500 * r, 3000 * r * 2 ** (bright - 0.5), 'reverse', q=0.9, pan0=-0.5, pan1=0.0,
                     seed=seed * 7 + 121, lowmix=0.5, fade_out=0.004, air=0.05 * bright)
    pre += ins.whoosh(M, 520 * r, 3100 * r * 2 ** (bright - 0.5), 'reverse', q=0.9, pan0=0.5, pan1=0.0,
                      seed=seed * 7 + 123, lowmix=0.5, fade_out=0.004, air=0.05 * bright)
    tl.add(pre * 0.35, 0.0)
    # ink bloom: band-passed noise, slow bloom, centre sinking (spreading / softening)
    n = smp(dur)
    t = np.arange(n) / SR
    fc = (2200 * r) * (0.45 + 0.55 * np.exp(-t / 0.5))
    from .dsp import svf
    for ch, sd in enumerate((131, 137)):
        ink = lp(hp(svf(noise(n, seed * 7 + sd), fc, 0.8, 'bp'), 150.0, 2), 5500.0, 2)
        ink *= (1 - np.exp(-t / 0.05)) * np.exp(-t / (0.28 * dur))
        ink[-smp(0.05):] *= rc_ramp(smp(0.05))[::-1]
        buf = np.zeros((2, n))
        buf[ch] = ink
        tl.add(buf * 0.5, M)
    tl.add(ins.celesta(_m('D6', pitch), 0.35 + 0.15 * bright, 1.6, seed=seed + 4), M, pan=-0.15)
    tl.add(ins.crystal_pluck(_m('A5', pitch), 0.25, 1.6, 2.0, 0.6 + 0.4 * bright, seed=seed + 5, decay=0.5),
           M + 0.03, pan=0.2)
    tl.add(ins.sub_bass(_m('D2', pitch), 0.6, 0.18, att=0.12, rel=0.5), M)
    for j in range(9):
        tg = M + 0.05 + 1.0 * (j / 9) ** 1.3 + rng.uniform(0, 0.02)
        nm = [_m(x, pitch) for x in ('D6', 'E6', 'F#6', 'A6', 'B6', 'D7')][int(rng.integers(6))]
        tl.add(ins.grain(440.0 * 2 ** ((nm - 69) / 12), float(rng.uniform(0.05, 0.14)),
                         0.05 * np.exp(-(tg - M) / 0.8)), tg, pan=float(rng.uniform(-0.8, 0.8)))
    return _space(tl.out, 0.35, 'hall', tail=0.0)


def _hit(rng, seed, pitch=0.0, bright=0.5):
    r = semis(pitch)
    tl = _Tl(1.4)
    tl.add(_body(110.0 * r, 0.5, 0.13, drop=0.6), 0.0)
    tl.add(ins.boom(62 * r, 44 * r, 0.9, 0.6, glide_tau=0.12, decay=0.28), 0.0)
    n = smp(0.03)
    t = np.arange(n) / SR
    crack = bpf(noise(n, seed * 11 + 7), 1000 * r, 6000 * r * 2 ** (bright - 0.5)) * _att(t, 0.0003) * np.exp(-t / 0.006)
    tl.add(crack * 0.5, 0.0)
    b = 0.7 + 0.6 * bright
    tl.add(ins.crystal_pluck(_m('D6', pitch), 0.55, 1.2, 2.0, b, seed=seed + 6, decay=0.35), 0.0, pan=-0.12)
    tl.add(ins.crystal_pluck(_m('A6', pitch), 0.40, 1.2, 2.0, b, seed=seed + 7, decay=0.35), 0.006, pan=0.12)
    tl.add(ins.bell(_m('F#6', pitch), 0.18 + 0.1 * bright, 1.3, index=1.5, decay=0.3), 0.0)
    return _space(tl.out, 0.22, 'plate', tail=0.0)


_PP = (0.0, -12.0, 12.0, 'semitones (whole family, default key D)')
_PB = (0.5, 0.0, 1.0, '0 dark .. 1 bright')

register(SfxSpec(
    id='enter', fn=_enter, family='motion', anchor='mark', mark_s=lambda p: p['dur'], lead_frames=3.5,
    ref=('tp', -15.0),
    purpose='元素入场：卡片 / 文字 / 图标滑入、缩放进入',
    sync='whoosh 型：声音比元素开始移动提前 3–4 帧（align=motion 自动提前 3.5 帧）；dur = 入场动画时长 + 提前量，'
         '结尾的晶体轻音落在元素到位那一帧',
    params={'pitch': _PP, 'bright': _PB, 'dur': (0.30, 0.15, 0.8, 'swish length up to the arrival (s)'),
            'travel': (0.3, -1.0, 1.0, 'pan sweep, + = L->R')},
    notes='上扬空气声（900→4200 Hz 带通噪声，峰值在 80%）+ 到位时的 A6 晶体轻拨 + 板式混响。'))
register(SfxSpec(
    id='land', fn=_land, family='motion', anchor='start', lead_frames=0.0, ref=('tp', -12.0),
    purpose='落定：圆窗落位、卡片放下、元素停稳',
    sync='impact 型：与落定（位移结束、回弹之前）同帧，align=start 或 motion（提前量 0）',
    params={'pitch': _PP, 'bright': _PB},
    notes='D3 正弦鼓体（下滑 1.5×→1×）+ D2 次低频 + 25 ms 气流噪声 + D5 晶体轻拨与 85 ms 后的微弱回弹。'))
register(SfxSpec(
    id='push', fn=_push, family='motion', anchor='mark', mark_s=lambda p: p['dur'], lead_frames=3.0,
    ref=('mmax', -24.0),
    purpose='推近：镜头推进、画面放大到细节',
    sync='whoosh 型：比推镜开始提前 3 帧（align=motion）；dur = 推镜时长 + 3 帧，声音在推到位时到达峰值',
    params={'pitch': _PP, 'bright': _PB, 'dur': (0.7, 0.3, 2.0, 'seconds (push time + lead)')},
    notes='两路向外展开的空气声（300→2400 Hz，峰值 88%）+ D3 起半个八度上升的滤波锯齿 + 板式混响。'))
register(SfxSpec(
    id='reveal', fn=_reveal, family='motion', anchor='mark', mark_s=lambda p: REVEAL_MARK, lead_frames=0.0,
    ref=('mmax', -22.0),
    purpose='揭示 / 墨入纸转场：新画面像墨一样晕开出现',
    sync='锚点在 0.35 s：align=anchor 对准墨迹触纸 / 新画面开始出现的那一帧（之前 0.35 s 是吸入式预备）',
    params={'pitch': _PP, 'bright': _PB, 'dur': (1.8, 0.8, 4.0, 'bloom length after the anchor (s)')},
    notes='反向汇聚的预备气声 → 带通噪声“晕开”（中心频率下沉）+ D6 celesta + A5 晶体 + 高音颗粒 + D2 轻底，大厅混响。'))
register(SfxSpec(
    id='hit', fn=_hit, family='motion', anchor='start', lead_frames=0.0, ref=('tp', -9.0),
    purpose='L3 强调落地：关键结论 / 大字 / 数字砸下来',
    sync='impact 型：与强调元素落地同帧；需要蓄力时，在同一帧再放一个 reverse_whoosh（align=end）',
    params={'pitch': _PP, 'bright': _PB},
    notes='110 Hz 鼓体 + 62→44 Hz boom + 6 ms 噪声脆击 + D6/A6 晶体双音 + F#6 轻钟，板式混响。'))
