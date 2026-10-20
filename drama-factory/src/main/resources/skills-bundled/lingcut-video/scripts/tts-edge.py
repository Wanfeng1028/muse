"""edge-tts 配音：免费、无需 API key（替代 MiniMax，成本 0）

为什么换掉 MiniMax：
  音色设计按次收费，实测 2 段音频花了约 20 元，做短剧不可持续。
  edge-tts 走微软 Edge 的公开神经语音接口，14 个中文音色，免费无限次。

用法:
  python tts-edge.py <lines.json> <outDir>
lines.json:
  [{ "file":"line05.mp3", "text":"我没有钱。", "voice":"zh-CN-XiaoyiNeural",
     "rate":"-12%", "pitch":null }]

推荐音色（实测 F0 标注，供年龄/性别匹配参考）：
  zh-CN-YunjianNeural  ♂ F0≈115-127Hz  成年男声，低沉，适合中老年男性
  zh-CN-YunxiNeural    ♂ F0≈157-178Hz  青年男声
  zh-CN-YunxiaNeural   ♂ 少年
  zh-CN-YunyangNeural  ♂ 新闻播报腔（要避开）
  zh-CN-XiaoxiaoNeural ♀ 成年女声
  zh-CN-XiaoyiNeural   ♀ F0≈326Hz  少女/童声，适合小女孩
  zh-CN-liaoning-XiaobeiNeural  东北方言女声（最口语）
  zh-CN-shaanxi-XiaoniNeural    陕西方言女声
  zh-HK-* 粤语 / zh-TW-* 台湾国语

⚠️ 「播报腔」无法用指标判断，必须人耳试听。生成候选样本让人挑。
"""
import asyncio, json, os, sys
import edge_tts


async def main():
    lines = json.load(open(sys.argv[1], encoding='utf8'))
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    for L in lines:
        kw = {}
        if L.get('rate'):  kw['rate'] = L['rate']
        if L.get('pitch'): kw['pitch'] = L['pitch']
        path = os.path.join(outdir, L['file'])
        try:
            await edge_tts.Communicate(L['text'], L['voice'], **kw).save(path)
            size = os.path.getsize(path)
            print(f"OK   {L['file']}  {size//1024}KB  {L['voice']}")
        except Exception as e:
            print(f"ERR  {L['file']}  {e}")


asyncio.run(main())
