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
| 废档案室·延迟倒影 · listening-still · v1.0 | asset | ready-to-submit-not-generated | 无需参考图 | Create one opening keyframe before the exchange. |

## 逐项交付

### 废档案室·延迟倒影 · listening-still · v1.0

用途：Create one opening keyframe before the exchange.
生成模式：GENERATE
提交状态：ready-to-submit-not-generated
上传：无需参考图；这是单项独立资产，按完整正文生成。

参考图上传助手：无需上传参考图；可直接复制完整提示词生成。

#### 复制：废档案室·延迟倒影 · listening-still · v1.0（完整正文）

完整文件：[下载/打开 ASSET_SUSPENSE_ARCHIVE.image.txt](ASSET_SUSPENSE_ARCHIVE.image.txt)

```text
Create a low-key live-action suspense keyframe in an abandoned archive. Ning Yue, an adult archivist in a dark raincoat with tied black hair, stands beside a glass records room holding a small flashlight low in her right hand. Tall metal shelves, dusty tile, a dead emergency light and a narrow doorway beam create clear depth. Her shoulders are held still while the glass reflection is subtly delayed and its hand remains down. Use one practical flashlight beam with readable falloff and quiet shadow planes. Keep the reflection behind the glass, never as a second physical person in the room. Avoid captions, horror typography, duplicate bodies and a bright fantasy glow.
```

## 使用顺序

1. 先按 `UPLOAD.md` 生成并批准依赖资产。
2. 角色身份资产默认使用四视图基准板；状态版本单独保留，不覆盖身份基准。
3. 复制对应 `.image.txt` 全文到 GPT Image 2/2.5；不要把本页说明或 `index.json` 一起提交。

