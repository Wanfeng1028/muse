"""storyboard_board_v2.png: the whole v2 storyboard in time order (new v2 frames + v1 frames of unchanged shots),
each tile captioned with shot number, time, new / kept, and a one-line note."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sb_lib import font, YELLOW, paper
from timeline import KEYFRAMES, V1_REUSE, rough_to_v2, fmt, insert_range, TOTAL_S

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT.parent / 'storyboard_v1'

IP_TILE = ROOT.parent / 'ip_intro/filmstrip/9x16_f56.png'


def rng(a, b):
    """rough-time range -> v2 range string"""
    return f'{fmt(rough_to_v2(a))}–{fmt(rough_to_v2(b))}'


def irng(key):
    a, b = insert_range(key)
    return f'{fmt(a)}–{fmt(b)}'


# (tile id, shot label, shot range in v2 time, frame time or None, new?, note)
T = [
    ('1', '1', rng(0, 2.40), KEYFRAMES['1'], True, '钩子：6 张卡快闪（成片画面已换成真成片），「这样的视频」落定'),
    ('I1', '2 插①', irng('vlog'), KEYFRAMES['I1'], True, '说完「vlog」停下，放 vlog 成片 3.0 s：「我的一天」开场'),
    ('I2', '2 插②', irng('kepu'), KEYFRAMES['I2'], True, '「做科普」后放科普成片 3.33 s：所以抬头看…蓝光'),
    ('I3', '2 插③', irng('faceless'), KEYFRAMES['I3'], True, '「不露脸的视频」后放不露脸成片 2.9 s：剪辑网感'),
    ('v1:03', '3', rng(7.1333, 10.25), rough_to_v2(V1_REUSE[3]), False, '两侧竖贴纸：全片只在这里用'),
    ('4', '4', rng(10.25, 12.8333), KEYFRAMES['4'], True, '改：头顶一张票根，「免费」「开源」依次盖章'),
    ('ip', '6', rng(15.8333, 18.4667), None, True, 'ip_intro 组件（已做好，2.633 s）：全屏大头贴，不出口播'),
    ('7', '7', rng(18.4667, 26.2667), KEYFRAMES['7'], True, 'vlog 讲解：真成片卡片 + 右下人像框'),
    ('9', '9', rng(32.7333, 40.4333), KEYFRAMES['9'], True, '不露脸讲解：框合上，「配上你的解说」就弹回'),
    ('10a', '10', rng(41.5667, 43.1167), KEYFRAMES['10a'], True, '全屏纸盒①：三段真成片小画面飞进同一个盒子'),
    ('10b', '10', rng(45.2667, 48.2667), KEYFRAMES['10b'], True, '全屏纸盒②：打开成三格，依次亮起'),
    ('11', '11', rng(48.4333, 52.4333), KEYFRAMES['11'], True, '改：真人全屏，合上的纸盒丢给「你的 Agent」'),
    ('v1:12', '12', rng(52.4333, 56.50), rough_to_v2(V1_REUSE[12]), False, '大号 4 + 顶部步骤条出现'),
    ('13a', '13', rng(56.50, 70.8667), KEYFRAMES['13a'], True, 'STEP 1 全屏对话框：逐字打「vlog、科普、不露脸各放一段」'),
    ('13b', '13', rng(56.50, 70.8667), KEYFRAMES['13b'], True, '「确认」发出，盖确认章；人在右下小框'),
    ('14a', '14', rng(70.8667, 83.5667), KEYFRAMES['14a'], True, 'STEP 2 桌面发牌：四张风格卡，「拼贴」翻起打勾'),
    ('14b', '14', rng(83.5667, 88.6667), KEYFRAMES['14b'], True, '拼贴风格从上往下刷过出镜者：上=包装后，下=原样'),
    ('15', '15', rng(88.6667, 103.90), KEYFRAMES['15'], True, 'STEP 3 胶片灯箱：当前格=出镜者实拍，其余格是分镜'),
    ('16a', '16', rng(103.90, 123.00), KEYFRAMES['16a'], True, 'STEP 4 自检：字幕故意压嘴，红框打叉「压到脸」'),
    ('16b', '16', rng(103.90, 123.00), KEYFRAMES['16b'], True, '字幕滑到安全区，框变绿勾；「重新做一遍」接倒带'),
    ('18', '18', rng(128.0333, 135.7667), KEYFRAMES['18'], True, '左右分屏：你=创意+拍摄 ｜ Agent=剪辑+包装'),
    ('v1:20', '20', rng(147.10, 152.6667), rough_to_v2(V1_REUSE[20]), False, '点赞 / 收藏 / 评论 / 关注 + 眨眼大头贴收尾'),
]

TW, TH = 360, 640
GAP, M = 26, 44
COLS = 8
CAP = 196


def wrap(txt, f, width):
    import re
    toks = re.findall(r'[A-Za-z0-9.:/+-]+|.', txt)
    lines, cur = [], ''
    for tk in toks:
        if f.getlength(cur + tk) > width and cur:
            lines.append(cur)
            cur = tk.lstrip()
        else:
            cur += tk
    if cur:
        lines.append(cur)
    return lines


def main():
    rows = (len(T) + COLS - 1) // COLS
    Wb = 2 * M + COLS * TW + (COLS - 1) * GAP
    head = 170
    Hb = head + rows * (TH + CAP) + (rows - 1) * GAP + 80
    board = Image.new('RGB', (Wb, Hb), (26, 25, 23))
    d = ImageDraw.Draw(board)
    d.text((M, 30), f'视频20 · 分镜 v2（静帧，按时间顺序）  总长 {fmt(TOTAL_S)}', font=font('Heavy', 46), fill=(255, 255, 255))
    d.text((M, 98), '时间 = v2 时间线（粗剪 + 三段真成片插入，见 storyboard.md）；黄标「v2 新」= 这次改的镜，灰标「沿用 v1」= 没动的镜，时间已按插入后重算；'
                     '成片画面全部取自三条真成片，镜 6 取自 ip_intro 组件', font=font('Medium', 24), fill=(196, 192, 184))
    d.text((M, 132), f'没出样帧的段：镜 2 三段真人口播（0:02.40–{irng("vlog")[:7]}、{irng("vlog")[8:]}–{irng("kepu")[:7]}、{irng("kepu")[8:]}–{irng("faceless")[:7]}），镜 5、8、17、19（见 storyboard.md）', font=font('Medium', 24),
           fill=(150, 146, 138))
    fN, fB = font('Medium', 23), font('Heavy', 30)
    for i, (tid, shot, rng, t, new, note) in enumerate(T):
        r, c = divmod(i, COLS)
        x = M + c * (TW + GAP)
        y = head + r * (TH + CAP + GAP)
        if tid == 'ip':
            im = Image.open(IP_TILE).convert('RGB').resize((TW, TH), Image.LANCZOS)
        elif tid.startswith('v1:'):
            im = Image.open(V1 / f'shot{tid[3:]}.png').convert('RGB').resize((TW, TH), Image.LANCZOS)
        else:
            im = Image.open(ROOT / f'shot{tid}.png').convert('RGB').resize((TW, TH), Image.LANCZOS)
        board.paste(im, (x, y))
        d.rectangle((x - 1, y - 1, x + TW, y + TH), outline=(70, 68, 64), width=1)
        chip = f'镜 {shot}'
        cw = fB.getlength(chip) + 24
        d.rounded_rectangle((x, y + TH + 14, x + cw, y + TH + 58), radius=10, fill=YELLOW if new else (120, 116, 108))
        d.text((x + cw / 2, y + TH + 36), chip, font=fB, fill=(20, 20, 20), anchor='mm')
        tag = 'v2 新' if new else '沿用 v1'
        d.text((x + cw + 12, y + TH + 36), f'帧 {fmt(t)}' if t is not None else '组件', font=font('Bold', 24), fill=(255, 255, 255),
               anchor='lm')
        tf = font('Bold', 20)
        tw_ = tf.getlength(tag) + 16
        d.rounded_rectangle((x + TW - tw_, y + TH + 20, x + TW, y + TH + 52), radius=8,
                            outline=YELLOW if new else (120, 116, 108), width=2)
        d.text((x + TW - tw_ / 2, y + TH + 36), tag, font=tf, fill=YELLOW if new else (170, 166, 158), anchor='mm')
        d.text((x, y + TH + 80), f'时段 {rng}', font=font('Medium', 21), fill=(150, 146, 138), anchor='lm')
        for k, line in enumerate(wrap(note, fN, TW)[:3]):
            d.text((x, y + TH + 104 + k * 32), line, font=fN, fill=(228, 224, 216))
    out = ROOT / 'storyboard_board_v2.png'
    board.save(out, optimize=True)
    print(out, board.size)


if __name__ == '__main__':
    main()
