"""Kokoro-82M-v1.1-zh 配音：Apache-2.0，可商用，CPU 可跑，成本 0

为什么用它（替代 MiniMax / edge-tts）：
  · MiniMax 音色设计按次收费，2 段音频约 20 元，做短剧不可持续
  · edge-tts 免费但只有 14 个中文音色，且多为播报腔
  · Kokoro-82M-v1.1-zh：**103 个现成音色**（55 中文女声 zf_* + 45 中文男声 zm_*），
    每个音色都是独立 .pt 文件可直接下载；Apache-2.0 可商用；82M 参数，CPU 约 2-3 秒/句

安装（一次性）：
  set HF_ENDPOINT=https://hf-mirror.com          # 国内直连 HF 不通，必须走镜像
  python -m pip install torch -i https://pypi.tuna.tsinghua.edu.cn/simple
  python -m pip install kokoro "misaki[zh]" soundfile

用法:
  python tts-kokoro.py <lines.json> <outDir>
lines.json:
  [{ "file":"line06.mp3", "text":"记账。", "voice":"zm_013", "speed":0.9 }]

音色选择（务必实测 F0，别靠名字）：
  中老年男性 100–125 Hz  →  zm_098(101) zm_013(103) zm_014(103) zm_034(106)
                             zm_029(107) zm_015(110) zm_033(110) zm_064(110)
  青年男性   130–165 Hz  →  zm_012 zm_030 zm_062 zm_081 zm_100
  少年       200+ Hz     →  zm_020(207) zm_041(204)
  童声/少女  290–325 Hz  →  zf_074(324) zf_017(312) zf_072(312) zf_038(308) zf_092(300)
  成熟女性   145–200 Hz  →  zf_079(146) zf_046(162) zf_019(163) zf_094(183)

⚠️ 「像不像人、有没有播报腔」指标测不出来，必须人耳试听。
   建议先批量生成候选样本（见 .probe/kokoro-scan.py 的做法）让人挑。
"""
import os, sys, json
os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
import numpy as np
import soundfile as sf

REPO = 'hexgrad/Kokoro-82M-v1.1-zh'
SR = 24000


def main():
    lines = json.load(open(sys.argv[1], encoding='utf8'))
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)

    from kokoro import KModel, KPipeline
    import torch
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = KModel(repo_id=REPO).to(dev).eval()
    zh = KPipeline(lang_code='z', repo_id=REPO, model=model)

    for L in lines:
        try:
            speed = L.get('speed', 1.0)
            wav = next(zh(L['text'], voice=L['voice'], speed=speed)).audio
            x = wav.numpy() if hasattr(wav, 'numpy') else np.asarray(wav)
            path = os.path.join(outdir, L['file'])
            if path.lower().endswith('.mp3'):
                tmp = path[:-4] + '.wav'
                sf.write(tmp, x, SR)
                os.system(f'ffmpeg -hide_banner -loglevel error -y -i "{tmp}" -b:a 128k "{path}"')
                os.remove(tmp)
            else:
                sf.write(path, x, SR)
            print(f"OK   {L['file']}  {len(x)/SR:.2f}s  voice={L['voice']}")
        except Exception as e:
            print(f"ERR  {L['file']}  {e}")


if __name__ == '__main__':
    main()
