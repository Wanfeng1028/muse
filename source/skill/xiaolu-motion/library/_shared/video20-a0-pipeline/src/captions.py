"""Main captions (C paper strip) from the corrected, re-timed text (04_captions/words_v2.json).

Step 1 (text) is done in words_v2.CORRECTED; step 2 here only breaks lines: no characters added, removed or changed
(punctuation becomes the strip boundary; 、 inside an enumeration and a space between 第X步 and its title stay).
Rules: one line per strip, <= 13 characters (a Latin word counts as its width in CJK cells, see cells()), semantic
breaks, no 1-2 character orphan strips, product / English words and quantity words never split.
[...] marks a keyword: Heavy + yellow marker block brushed left -> right starting at the keyword's first unit onset.

burn = False: the hook (shot 1, its big-type labels carry the sentence) and the IP intro (shot 6, the ip_intro
component writes the sentence itself); the three inserts have no presenter speech. A3's subtitle_owned ranges in shot 16
are applied at assembly time.
Outputs: 04_captions/captions_v2.json, captions_v2_full.srt, captions_v2_burn.srt, captions_v2_burn.ass
"""
import re
import sys

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from a0common import *  # noqa

STRIPS = [
    '不会剪辑也能做出这样的视频',
    '如果你想做[vlog]', '做[科普]', '或者做[不露脸]的视频',
    '但是你又[不想剪辑]', '或者说你也[不会剪辑]', '那你可以看看', '我这个[免费]的[开源]工具',
    '本期视频的所有工具', '都已经放入了[文档]里面',
    '我是小鹿', '一个很会玩AI的文科生',
    '这是[vlog]', '[转场]多一点', '[字幕做成贴纸]', '[时间]、[天气]、[心情]', '这些小卡片', '它会自己点缀上去',
    '而这是[科普]', '你讲到的原理会变成[图和动画]', '跟着你的内容一步步[画出来]',
    '如果你[不想露脸]', '其实也可以', '只要放上[字和动画]', '[配上你的解说]', '一条完整的视频[就出来了]',
    '而这些其实都是', '[同一套东西]做出来的', '它其实就是一个开源的', '[动效库]加[音效库]加[风格包]',
    '你只要把我这个skill', '[丢给]你的Agent', '就可以[直接来使用]',
    '而且使用的方法也[特别简单]', '总的来说就[四个步骤]',
    '第一步 [确认选题]', '把你拍的[素材]', '或者[想讲的内容]', '全部丢给Agent',
    '在这个阶段', 'AI会和你[不断打磨]', '你的[选题和想法]', '直到你[确认没有问题]之后', '再进行[下一步]',
    '第二步 [画面风格]', 'AI会给你出几张[风格图]', '比如[拼接]的、[胶片]的', '[杂志]的、[发布会]的等等',
    '你可以从里面[挑一个]', '你喜欢的风格',
    '之后Agent就会', '以这个[风格为标准]', '去把你的视频进行[包装]',
    '第三步 [分镜脚本]', '在这个步骤', 'Agent会按你的内容出[分镜]', '每一个画面放什么', '[怎么转场]、[配什么音效]',
    '先出几张[样片]给你看', '直到[确认没有问题]之后', '才会继续往下做',
    '第四步 [剪辑成片]', '完成前三步之后', 'Agent会进行视频的[剪辑]', '[动效音效]等包装', '完成后它会自己[检查一遍]',
    '如果出现[字压到脸上]', '或者说[挡住字幕]', '等影响观感的情况', 'Agent就会自己去', '[重新做一遍]',
    '所以啊 你前面看到的成片', '其实就是这[四个步骤]做出来的',
    '你只需要负责', '[创意]的部分以及拍摄', '[剪辑和包装]可以全部', '交给你的Agent去完成',
    '目前这个工具是[第一版]', '动效模板、风格包', '还在不断地打磨添加', '那如果你也想用这个工具', '去做一个自己的账号',
    '探索人生的[第二曲线]', '欢迎[点赞][收藏][评论]加[关注]', '那我们下一期视频', '再讲一点[不一样的AI]',
]
NO_BURN_SHOTS = ('01', '06')
LEAD = 0.07          # strip appears ~2 frames before the first syllable
HOLD = 0.30          # hold after the last syllable when a pause follows
JOIN_GAP = 0.60      # shorter gaps: the strip stays until the next one starts


def cells(txt):
    """display width in CJK cells: CJK = 1, Latin letters ~0.55 (Source Han Sans Medium 66 px), space = 0.5"""
    n = 0.0
    for m in re.finditer(r'[A-Za-z]+|.', txt):
        g = m.group(0)
        n += 0.55 * len(g) if g[0].isascii() and g[0].isalpha() else (0.5 if g == ' ' else 1.0)
    return n


def parse(strip):
    """-> (plain text, units list, keyword unit ranges [(i0, i1)])"""
    plain = strip.replace('[', '').replace(']', '')
    units, kws, open_ = [], [], None
    for m in re.finditer(r'\[|\]|[A-Za-z]+|.', strip):
        g = m.group(0)
        if g == '[':
            open_ = len(units)
        elif g == ']':
            kws.append((open_, len(units) - 1))
        elif g in ('、', ' '):
            continue
        else:
            units.append(g)
    return plain, units, kws


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def ass_time(t):
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f'{h}:{m:02d}:{s:02d}.{cs:02d}'


def main():
    W2 = load_json(CAPS / 'words_v2.json')
    U = W2['units']
    k = 0
    rows = []
    for st in STRIPS:
        plain, us, kws = parse(st)
        seg = U[k:k + len(us)]
        got = [u['w'] for u in seg]
        assert got == us, (st, got)
        assert cells(plain) <= 13.0, (st, cells(plain))
        k += len(us)
        s0, e0 = seg[0]['s'], seg[-1]['e']
        shot = shot_at(int(s0 * FPS))[0]
        rows.append(dict(text=plain, markup=st, cells=round(cells(plain), 2), units=[seg[0]['i'], seg[-1]['i']],
                         speech_s=s0, speech_e=e0, shot=shot, burn=shot not in NO_BURN_SHOTS,
                         keywords=[dict(text=''.join(us[a:b + 1]), s=seg[a]['s'], e=seg[b]['e'], f0=seg[a]['f0'],
                                        brush_frames=int(min(12, max(6, round((seg[b]['e'] - seg[a]['s']) * FPS)))))
                                   for a, b in kws]))
    assert k == len(U), (k, len(U))
    # display times
    ins = [(a / FPS, b / FPS) for a, b, _, _ in insert_frames().values()]
    for i, r in enumerate(rows):
        start = r['speech_s'] - LEAD
        if i and rows[i - 1]['end'] > start:
            start = rows[i - 1]['end']
        nxt = rows[i + 1]['speech_s'] - LEAD if i + 1 < len(rows) else None
        end = r['speech_e'] + HOLD
        if nxt is not None and nxt - r['speech_e'] < JOIN_GAP:
            end = nxt
        elif nxt is not None:
            end = min(end, nxt)
        for a, b in ins:                                  # never run into an insert
            if start < a < end:
                end = a
        sh_ = [s for s in SHOTS if s[0] == r['shot']][0]
        if r['burn']:                                     # nor into a non-burn shot (1, 6)
            for s in SHOTS:
                if s[0] in NO_BURN_SHOTS and start < s[1] / FPS < end:
                    end = s[1] / FPS
                if s[0] in NO_BURN_SHOTS and start < s[2] / FPS < end and s[1] / FPS <= start:
                    start = s[2] / FPS
        r['start'], r['end'] = round(start, 3), round(end, 3)
        r['f0'], r['f1'] = int(round(start * FPS)), int(round(end * FPS))
    # keep frame ranges disjoint after rounding
    for a, b in zip(rows, rows[1:]):
        b['f0'] = max(b['f0'], a['f1'])
    for r in rows:
        assert r['f1'] > r['f0'], r
    save_json(CAPS / 'captions_v2.json', dict(
        version='1.0', clock='v2', fps=FPS, source=str(CAPS / 'words_v2.json'), rules=__doc__.strip(),
        style=dict(name='C 纸条', font='SourceHanSansSC-Medium 66 px (keywords SourceHanSansSC-Heavy)', color='#141414',
                   strip='white rounded rect r=16, alpha 245, soft shadow', marker='#FFD60A, brushed left->right at the keyword onset',
                   centre_y=1368, bottom_max=1424, drawn_by='05_visual/storyboard_v2/src/sb_lib.py subtitle_c geometry'),
        uncertain=W2['uncertain'], strips=rows))

    def write_srt(path, sel):
        out = []
        for n, r in enumerate([r for r in rows if sel(r)], 1):
            out.append(f"{n}\n{srt_time(r['f0'] / FPS)} --> {srt_time(r['f1'] / FPS)}\n{r['text']}\n")
        Path(path).write_text('\n'.join(out), encoding='utf-8')
    write_srt(CAPS / 'captions_v2_full.srt', lambda r: True)
    write_srt(CAPS / 'captions_v2_burn.srt', lambda r: r['burn'])
    # ASS: editable approximation of the C strip (opaque white box, black Medium text, keywords Heavy on yellow box)
    hdr = """[Script Info]
Title: 视频20 主字幕（C 纸条，可编辑近似；成片烧录版以 PIL 渲染为准）
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: C,Source Han Sans SC Medium,66,&H00141414,&H00141414,&H00FFFFFF,&H64000000,0,0,0,0,100,100,2,0,3,20,0,2,40,40,{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""".replace('{mv}', str(1920 - 1424 + 20))
    ev = []
    for r in rows:
        if not r['burn']:
            continue
        txt = r['markup']
        txt = re.sub(r'\[([^\]]+)\]', r'{\\fnSource Han Sans SC Heavy\\3c&H0AD6FF&}\1{\\fnSource Han Sans SC Medium\\3c&HFFFFFF&}', txt)
        ev.append(f"Dialogue: 0,{ass_time(r['f0'] / FPS)},{ass_time(r['f1'] / FPS)},C,,0,0,0,,{txt}")
    (CAPS / 'captions_v2_burn.ass').write_text(hdr + '\n'.join(ev) + '\n', encoding='utf-8')
    nb = sum(r['burn'] for r in rows)
    print(len(rows), 'strips,', nb, 'burned; max cells', max(r['cells'] for r in rows),
          '; min shown', min(r['f1'] - r['f0'] for r in rows), 'frames')
    for r in rows:
        print(f"{'B' if r['burn'] else '-'} {fmt(r['f0'] / FPS)}-{fmt(r['f1'] / FPS)} ({r['f1'] - r['f0']:3d}f) {r['markup']}")


if __name__ == '__main__':
    main()
