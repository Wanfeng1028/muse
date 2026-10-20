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
| Forge试图穿过维修沟，Ward用盾面导走能量 | asset | ready-to-submit-not-generated | 1 张 | Create one opening keyframe before the exchange. |

## 逐项交付

### Forge试图穿过维修沟，Ward用盾面导走能量

用途：Create one opening keyframe before the exchange.
生成模式：GENERATE
提交状态：ready-to-submit-not-generated
上传：图1 references/6cb5eee882c10bd974b970f53d456ffed1c03c8fa82f964ba6210b841d88d4f2.png（composition）

参考图上传助手：严格按下表顺序上传；文件名不能替代实际文件，说明文字不要粘进图像提示词。

| 槽位 | 实际上传文件 | 用途 | 必须保留 | 禁止继承 |
|---:|---|---|---|---|
| 1 | [references/6cb5eee882c10bd974b970f53d456ffed1c03c8fa82f964ba6210b841d88d4f2.png](references/6cb5eee882c10bd974b970f53d456ffed1c03c8fa82f964ba6210b841d88d4f2.png) | composition | only Panel 01's left-right placement and ground line; the left block marked A denotes Forge, and the right block marked B denotes Ward | the grid, letters, panel numbers, gray block anatomy and flat diagram shading; produce one full-frame image |

上传顺序：先上传槽位 1，再按 2、3……递增；上传完成后确认提示词中的 `Reference image N` 与槽位一一对应。
提交前检查：所有文件可打开、顺序正确、只继承表中“必须保留”内容，并把姿态/构图/光线按本次正文重建。

#### 复制：Forge试图穿过维修沟，Ward用盾面导走能量（完整正文）

完整文件：[下载/打开 ASSET_01_MECHA.image.txt](ASSET_01_MECHA.image.txt)

```text
Reference image 1 supplies composition guidance for the confrontation between Forge and Ward. Preserve only Panel 01's left-right placement and ground line; the left block marked A denotes Forge, and the right block marked B denotes Ward. Do not inherit the grid, letters, panel numbers, gray block anatomy and flat diagram shading; produce one full-frame image.

Create one live-action mechanical confrontation frame inside the repair hangar: Forge at left with broad ochre shoulder plates and square visor, Ward at right with overlapping dark plates and silver visor, its left shield facing Forge's right forearm emitter. Preserve both eight-meter body proportions, the service trench between them, the two human-sized doors and the world-east maintenance lamp. Use a 35 mm equivalent view from the south platform with both soles and the shield contact plane visible. Painted steel stays matte across broad panels, worn shield edges show narrow metal highlights, and ceramic joints remain darker with visible thickness. The east lamp passes through localized oil haze onto the upper armor edges, with weak concrete bounce preserving the shadow-side structure. Concentrate detail at the shield bevel and actuator joints; combine distant trusses into broad quiet forms. Avoid disconnected joints, tiled micro-panels and uniform plastic gloss.
```

## 使用顺序

1. 先按 `UPLOAD.md` 生成并批准依赖资产。
2. 角色身份资产默认使用四视图基准板；状态版本单独保留，不覆盖身份基准。
3. 复制对应 `.image.txt` 全文到 GPT Image 2/2.5；不要把本页说明或 `index.json` 一起提交。

