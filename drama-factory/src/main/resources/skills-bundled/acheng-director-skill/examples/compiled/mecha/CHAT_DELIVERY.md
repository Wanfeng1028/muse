# H3 视频交付总览 · Acheng Director 生产台

## 总控台

项目：EXAMPLE_MECHA
总时长：14 秒 · 24/1 fps
段落数量：1 · 模式：autonomous_file_batch
状态：机器检查不等于平台已上传或影像已生成；缺素材与合同缺项保持草案。

## 创作摘要

Forge试图穿过维修沟，Ward用盾面导走能量。护盾守住通路，Forge损失一发能量，浅层地面损伤成为下一轮站位限制。

叙事范围：战斗段落局部选择；不是完整人物成长五阶段

段落推进：
- MECHA_SEG01：[reference generation] The target video follows the blocking and order in <Picture 1>, first establishing the confrontation and then showing the attack, defense, material response and continuing recovery.

## 资产目录与提示词

以下是可直接交给画布 Agent 的独立资产图提示词。提示词文件是生成指令，不是已经生成的图片；状态为 PLANNED 时仍需先补齐真实参考素材。

| 资产 | 状态 | 用途 | 参考依赖 | 提示词文件 |
|---|---|---|---|---|
| Forge试图穿过维修沟，Ward用盾面导走能量 (`ASSET_01_MECHA`) | PROMPT_READY | Create one opening keyframe before the exchange. | 1 项 | [asset_prompts/ASSET_01_MECHA.image.txt](asset_prompts/ASSET_01_MECHA.image.txt) |

### 可复制资产提示词

#### Forge试图穿过维修沟，Ward用盾面导走能量 · PROMPT_READY

完整文件：[asset_prompts/ASSET_01_MECHA.image.txt](asset_prompts/ASSET_01_MECHA.image.txt)

独立上传卡：[ASSET_01_MECHA.asset-upload.md](ASSET_01_MECHA.asset-upload.md)

### Forge试图穿过维修沟，Ward用盾面导走能量 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ASSET_01_MECHA.image.txt>) · SHA-256：72c54a8e55e3f23e2934dd935b6dc19bcdd516ed5ef9293ac08286b4cd3cc61f

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

逐项上传实际图片；不上传 .image.txt，缺失槽位不重排编号。

| 槽位 | 实际图片/缺项 | 用途/对象 | 版本 | 必须保留 | 禁止继承 |
|---|---|---|---|---|---|
| 1 | [6cb5eee882c10bd974b970f53d456ffed1c03c8fa82f964ba6210b841d88d4f2.png](<references/6cb5eee882c10bd974b970f53d456ffed1c03c8fa82f964ba6210b841d88d4f2.png>) | composition / the confrontation between Forge and Ward | 未指定 | only Panel 01's left-right placement and ground line; the left block marked A denotes Forge, and the right block marked B denotes Ward | the grid, letters, panel numbers, gray block anatomy and flat diagram shading; produce one full-frame image |

下一步：核对模式和本卡槽位，在实际入口上传图片并复制完整提示词；生成后记录真实文件、版本和人工批准。


## 段落地图（分段地图）

| 段落 | 时间 | 时长 | H3模式 | 创作事件/意图 | 状态 |
|---|---|---:|---|---|---|
| MECHA_SEG01 | 0.000s–14.000s | 14s | Ref2VA | [reference generation] The target video follows the blocking and order in <Picture 1>, first establishing the confrontation and then showing the attack, defense, material response and continuing recovery. | READY_TO_UPLOAD |

## 每段上传参考助手

每张卡只覆盖一个 Segment；先看状态与实际文件，再按标签顺序上传。Subject 是内容对象，不是额外上传槽位。

**本段创作摘要：** [reference generation] The target video follows the blocking and order in <Picture 1>, first establishing the confrontation and then showing the attack, defense, material response and continuing recovery.

### MECHA_SEG01 · Ref2VA · 14 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](MECHA_SEG01.h3.txt) · [独立上传卡](MECHA_SEG01.upload.md)

绑定版本：`d7f6d326eaf56de8816bbda85c0560bf855ffa4828c5c914867db6b4da883edd` · 正文 SHA-256：`f2b02ba418dcc16267ddb5e26151b3d27309ee8cbc4e9003056e7827f8dab677`

参考图上传助手：每段是独立请求；按顺序上传实际媒体，不上传 `.image.txt` 或本卡。

| 顺序/标签 | 实际上传文件/状态 | 资产与版本 | 内容对象/说话人 | 用途与生效范围 | 必须保留 | 禁止继承 |
|---|---|---|---|---|---|---|
| 1 / `<Picture 1>` | [mecha-contact.png](<references/6cb5eee882c10bd974b970f53d456ffed1c03c8fa82f964ba6210b841d88d4f2.png>); BOUND_LOCAL; NOT_UPLOADED | 未绑定 / sha256:6cb5eee882c10bd974b970f53d456ffed1c03c8fa82f964ba6210b841d88d4f2 | 未绑定 | storyboard blocking and ordering only; FILM-S01-SH001 · 全局帧 0–168（末帧不含）; FILM-S01-SH002 · 全局帧 168–336（末帧不含） | <Picture 1> (planning reference for [Shot 1] and [Shot 2]): weak_reference - preserve the two figures' relative sides and the ordered action beats, while replacing schematic blocks with the described original character designs in a single full-screen view. | 未绑定 |

视频参考：未声明；不虚构 Video 标签。音频参考：未声明；不虚构 Audio 标签。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

## H3 正文文件

每个文件都是独立请求；请复制对应文件的完整正文，不把本页说明、manifest 或上传卡混入模型输入。

| 段落 | 状态 | 完整 H3/草案 | 独立上传卡 |
|---|---|---|---|
| MECHA_SEG01 | READY_TO_UPLOAD | [MECHA_SEG01.h3.txt](MECHA_SEG01.h3.txt) | [MECHA_SEG01.upload.md](MECHA_SEG01.upload.md) |

## 执行顺序与阻塞项

1. 待制作资产先按自己的上传卡上传实际参考图、提交完整资产提示词；生成后登记真实文件、版本、哈希并批准，再重新编译下游。已经批准且未变化的资产直接复用。
2. 打开每个 Segment 的上传卡，只上传该段表内的真实媒体，并在入口核对模式、时长和槽位编号。
3. 打开对应 H3 文件，复制完整正文提交；`CHAT_DELIVERY.md` 不替代 H3 正文文件。
4. 平台上传后另行保存入口回执；本地 `READY_TO_UPLOAD` 不等于平台已上传，`visual_status=UNVERIFIED` 不得升级。

当前阻塞：无机器识别阻塞；仍需实际平台上传回执和生成后人工画面验收。

自动文件模式：长 H3 正文留在独立文件；本页保留创作摘要、资产提示词、分段地图和每段上传助手，不能用总清单链接代替操作卡。

