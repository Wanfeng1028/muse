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
| 港湾中的两座巨体以列车和云带确立尺度 | asset | ready-to-submit-not-generated | 1 张 | Create one opening keyframe before the exchange. |

## 逐项交付

### 港湾中的两座巨体以列车和云带确立尺度

用途：Create one opening keyframe before the exchange.
生成模式：GENERATE
提交状态：ready-to-submit-not-generated
上传：图1 references/028eee66c71c1f4148764ce5ed3c3d9d6d48570af091ff710b53346509c68826.png（composition）

参考图上传助手：严格按下表顺序上传；文件名不能替代实际文件，说明文字不要粘进图像提示词。

| 槽位 | 实际上传文件 | 用途 | 必须保留 | 禁止继承 |
|---:|---|---|---|---|
| 1 | [references/028eee66c71c1f4148764ce5ed3c3d9d6d48570af091ff710b53346509c68826.png](references/028eee66c71c1f4148764ce5ed3c3d9d6d48570af091ff710b53346509c68826.png) | composition | only Panel 01's left-right placement and ground line; the left block marked A denotes Aer, and the right block marked B denotes Stone Sentinel | the grid, letters, panel numbers, gray block anatomy and flat diagram shading; produce one full-frame image |

上传顺序：先上传槽位 1，再按 2、3……递增；上传完成后确认提示词中的 `Reference image N` 与槽位一一对应。
提交前检查：所有文件可打开、顺序正确、只继承表中“必须保留”内容，并把姿态/构图/光线按本次正文重建。

#### 复制：港湾中的两座巨体以列车和云带确立尺度（完整正文）

完整文件：[下载/打开 ASSET_03_COLOSSAL.image.txt](ASSET_03_COLOSSAL.image.txt)

```text
Reference image 1 supplies composition guidance for the confrontation between Aer and Stone Sentinel. Preserve only Panel 01's left-right placement and ground line; the left block marked A denotes Aer, and the right block marked B denotes Stone Sentinel. Do not inherit the grid, letters, panel numbers, gray block anatomy and flat diagram shading; produce one full-frame image.

Create one cel-shaded harbor confrontation keyframe with a 180-meter winged bronze guardian at left and a 160-meter stone sentinel at right. The maintenance train touches the guardian's ankle platform at the same depth, while a cloud shelf crosses the upper torso and the wing shadow spans multiple warehouse roofs. Keep one clear vertical silhouette and let the left wing leave the frame. Use a distant causeway observer and a 50 mm equivalent lens; retain the harbor horizon and usable railway route. Low east sunlight defines three large value masses. Bronze panels receive narrow directional highlights, the intact stone shield ribs show broad matte planes and clear edge thickness. The train doors remain legible scale modules; distant roof details merge into lower-contrast atmosphere. Capture the grounded opening stance before the attack; the forearm channel is unlit and no energy has been emitted. Avoid miniature tilt-shift blur, repeated ornamental texture and disconnected load-bearing structure.
```

## 使用顺序

1. 先按 `UPLOAD.md` 生成并批准依赖资产。
2. 角色身份资产默认使用四视图基准板；状态版本单独保留，不覆盖身份基准。
3. 复制对应 `.image.txt` 全文到 GPT Image 2/2.5；不要把本页说明或 `index.json` 一起提交。

