# 资产交付总览

这是给人阅读的导航页；模型只接收各资产 `.image.txt` 或 `.draft.txt` 的完整正文。

## 总控台

资产数量：1
可提交提示词：1
待参考图草案：0
状态：已编译但未调用图像模型。真实身份一致性、画面质量和文字伪影仍需生图后人工检查。

## 资产目录

| 资产 | 类型 | 状态 | 参考图 | 用途 |
|---|---|---|---|---|
| 陈千语·办公室电话戏 · laughing-open · v1.1 | asset | ready-to-submit-not-generated | 无需参考图 | Create one opening keyframe before the exchange. |

## 逐项交付

### 陈千语·办公室电话戏 · laughing-open · v1.1

用途：Create one opening keyframe before the exchange.
生成模式：GENERATE
提交状态：ready-to-submit-not-generated
上传：无需参考图；这是单项独立资产，按完整正文生成。

参考图上传助手：无需上传参考图；可直接复制完整提示词生成。

#### 复制：陈千语·办公室电话戏 · laughing-open · v1.1（完整正文）

完整文件：[下载/打开 ASSET_ANIME_PHONE.image.txt](ASSET_ANIME_PHONE.image.txt)

```text
Create a clean 2D cel-animation character-and-environment keyframe of Chen Qianyu beside a dark office chair near a wide glass window. She has dark horn ornaments, long black hair with one teal streak, red eyes, a white and sky-blue outfit, blue gloves, black knee boots and a long tail. Her left hand holds a phone to her left ear; her eyes are closed in a broad laugh and her free right hand hangs loose. The futuristic office contains two screens, a glossy dark floor with white and yellow guide lines, a rear corridor doorway and stacked crates. The bright green cliff and hanging vines outside the window provide the only saturated background color. Use painted backgrounds, clean linework, flat cel shading and a readable close composition. Keep one complete character, one phone and one tail; avoid extra text, captions, duplicate limbs or a second phone voice.
```

## 使用顺序

1. 先按 `UPLOAD.md` 生成并批准依赖资产。
2. 角色身份资产默认使用四视图基准板；状态版本单独保留，不覆盖身份基准。
3. 复制对应 `.image.txt` 全文到 GPT Image 2/2.5；不要把本页说明或 `index.json` 一起提交。

