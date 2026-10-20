"""旁白稿 → TTS 生成 → 时长实测（拆书片「密度流 + 旁白」形态的第 1 步）。

用法：
    # 1. 生成 script.json 模板
    python narration.py init --script audio/script.json

    # 2. 只估时长，不出音频（改稿时快速迭代）
    python narration.py plan --script audio/script.json

    # 3. 生成音频 + 实测时长（出 audio/narration/vo_XX.mp3 + audio/timing.json）
    python narration.py run --script audio/script.json

设计要点（都是踩出来的）：
- **每段旁白时长必须 <= 该镜窗口**，否则声画对不上。超窗直接 exit 1。
- **每段余量必须 >= 0.4s**，否则呼吸停顿就爆窗（0.4s 以下提示「紧」但仍算通过）。
- edge-tts **无逐词时间戳**，只能做「整段对位」：段落在镜内居中铺开。
  想要字幕跟读（逐词高亮），必须换付费 API（火山/阿里云有 word-level timestamp）。
- edge-tts 输出 **24kHz 单声道 mp3**，混音前必须重采样（见 mix_audio.py）。

script.json 格式：
{
  "voice": "zh-CN-YunyangNeural",
  "rate": "+18%",
  "pitch": "+0Hz",
  "total": 60,
  "segments": [
    {"id": "s1", "window": [0.6, 9.4], "text": "..."},
    ...
  ]
}
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys

DEFAULT_VOICE = "zh-CN-YunyangNeural"
DEFAULT_RATE = "+18%"
DEFAULT_PITCH = "+0Hz"

# 本机实测语速（+18% 后）：云扬 ≈ 4.3–4.6 字/秒。保守按 4.4 估。
CHARS_PER_SEC = 4.4
MIN_MARGIN = 0.4

VOICE_HINTS = {
    "zh-CN-YunyangNeural": "云扬 · 男 · 新闻专业感（知识拆书推荐）",
    "zh-CN-XiaoxiaoNeural": "晓晓 · 女 · 温暖治愈",
    "zh-CN-YunxiNeural": "云希 · 男 · 活泼",
    "zh-CN-XiaoyiNeural": "晓伊 · 女 · 甜美",
    "zh-CN-YunjianNeural": "云健 · 男 · 沉稳",
}


def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


async def synth(text, out_path, voice, rate, pitch):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await comm.save(out_path)


def load_script(path):
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    s.setdefault("voice", DEFAULT_VOICE)
    s.setdefault("rate", DEFAULT_RATE)
    s.setdefault("pitch", DEFAULT_PITCH)
    s.setdefault("total", 60)
    return s


def cmd_init(a):
    """写一个 script.json 模板。"""
    if os.path.exists(a.script):
        print(f"{a.script} 已存在，未覆盖。")
        return 0
    d = os.path.dirname(os.path.abspath(a.script))
    os.makedirs(d, exist_ok=True)
    tpl = {
        "voice": DEFAULT_VOICE,
        "rate": DEFAULT_RATE,
        "pitch": DEFAULT_PITCH,
        "total": 60,
        "segments": [
            {"id": "s1", "window": [0.6, 9.4], "text": "第一镜旁白，写在这里。"},
            {"id": "s2", "window": [9.8, 20.6], "text": "第二镜旁白，写在这里。"},
        ],
    }
    with open(a.script, "w", encoding="utf-8") as f:
        json.dump(tpl, f, ensure_ascii=False, indent=1)
    print(f"已写模板 {a.script}\n音色候选：")
    for v, d2 in VOICE_HINTS.items():
        print(f"  {v:<26}{d2}")
    return 0


def run(a):
    s = load_script(a.script)
    voice, rate, pitch = s["voice"], s["rate"], s["pitch"]
    total = s["total"]

    print(f"音色 {voice}（{VOICE_HINTS.get(voice, '自定义')}） / 语速 {rate}\n")
    print(f"{'镜':<5}{'窗口':<15}{'可用':<8}{'字数':<6}{'实测':<9}{'余量':<9}{'状态'}")
    print("-" * 66)

    timing = {}
    ok = True
    for seg in s["segments"]:
        sid = seg["id"]
        t0, t1 = seg["window"]
        text = seg["text"]
        win = t1 - t0
        nchar = len(text)
        out_mp3 = f"audio/narration/vo_{sid}.mp3"

        if a.mode == "plan":
            dur = nchar / CHARS_PER_SEC
            status = "(估)"
        else:
            os.makedirs("audio/narration", exist_ok=True)
            asyncio.run(synth(text, out_mp3, voice, rate, pitch))
            dur = ffprobe_duration(out_mp3)
            status = "(实测)"

        margin = win - dur
        if margin < 0:
            flag, ok = "超窗!", False
        elif margin < MIN_MARGIN:
            flag = "紧"
        else:
            flag = "OK"
        print(f"{sid:<5}{t0}–{t1}s{'':<6}{win:<8.1f}{nchar:<6}{dur:<9.2f}{margin:<9.2f}{flag} {status}")

        timing[sid] = {
            "window": [t0, t1], "chars": nchar,
            "vo_dur": round(dur, 3), "margin": round(margin, 3),
            "vo_file": out_mp3 if a.mode == "run" else None,
            "text": text,
        }

    total_vo = sum(v["vo_dur"] for v in timing.values())
    print("-" * 66)
    print(f"旁白总时长 {total_vo:.2f}s / 片长 {total}s（占比 {total_vo/total*100:.0f}%）")

    if a.mode == "run":
        out = a.out or "audio/timing.json"
        d = os.path.dirname(os.path.abspath(out))
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"voice": voice, "rate": rate, "pitch": pitch,
                       "total": total, "segments": timing},
                      f, ensure_ascii=False, indent=1)
        print(f"已写 {out}")

    if not ok:
        print("\n有段落超窗 —— 必须改稿或改窗口。")
        print("提示：60s 内「卡片越多」与「旁白越长」互斥。按 4.4 字/秒算，"
              "全片旁白字数上限 ≈ 片长 × 4.4 × 0.8。")
        return 1
    print("\n全部段落均在窗口内。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="旁白稿 → TTS → 时长实测")
    sub = ap.add_subparsers(dest="mode", required=True)

    p1 = sub.add_parser("init", help="生成 script.json 模板")
    p1.add_argument("--script", default="audio/script.json")
    p1.set_defaults(func=cmd_init)

    for m, h in [("plan", "只估时长不出音频"), ("run", "生成音频并实测")]:
        p = sub.add_parser(m, help=h)
        p.add_argument("--script", default="audio/script.json")
        p.add_argument("--out", default=None, help="timing.json 输出路径")
        p.set_defaults(func=run)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
