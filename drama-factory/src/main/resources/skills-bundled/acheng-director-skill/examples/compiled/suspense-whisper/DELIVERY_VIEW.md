# H3 视频交付总览 · Acheng Director 生产台

## 总控台

项目：EXAMPLE_SUSPENSE_WHISPER
总时长：10 秒 · 24/1 fps
段落数量：1 · 模式：autonomous_file_batch
状态：机器检查不等于平台已上传或影像已生成；缺素材与合同缺项保持草案。

## 创作摘要

宁月停止呼吸和转头，只用眼睛核对玻璃倒影；倒影延迟抬手，手电光始终留在地面。

## 资产目录与提示词

以下是可直接交给画布 Agent 的独立资产图提示词。提示词文件是生成指令，不是已经生成的图片；状态为 PLANNED 时仍需先补齐真实参考素材。

| 资产 | 状态 | 用途 | 参考依赖 | 提示词文件 |
|---|---|---|---|---|
| 废档案室·延迟倒影 · listening-still · v1.0 (`ASSET_SUSPENSE_ARCHIVE`) | PROMPT_READY | Create one opening keyframe before the exchange. | 无 | [asset_prompts/ASSET_SUSPENSE_ARCHIVE.image.txt](asset_prompts/ASSET_SUSPENSE_ARCHIVE.image.txt) |

### 可复制资产提示词

#### 废档案室·延迟倒影 · listening-still · v1.0 · PROMPT_READY

完整文件：[asset_prompts/ASSET_SUSPENSE_ARCHIVE.image.txt](asset_prompts/ASSET_SUSPENSE_ARCHIVE.image.txt)

独立上传卡：[ASSET_SUSPENSE_ARCHIVE.asset-upload.md](ASSET_SUSPENSE_ARCHIVE.asset-upload.md)

### 废档案室·延迟倒影 · listening-still · v1.0 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / listening-still

[完整提示词/草案](<asset_prompts/ASSET_SUSPENSE_ARCHIVE.image.txt>) · SHA-256：b898bbb324cbf43fa950f79e438e29fcda5fb1ed2cbb2dc5aa6f60c8a45304b0

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


```text
Create a low-key live-action suspense keyframe in an abandoned archive. Ning Yue, an adult archivist in a dark raincoat with tied black hair, stands beside a glass records room holding a small flashlight low in her right hand. Tall metal shelves, dusty tile, a dead emergency light and a narrow doorway beam create clear depth. Her shoulders are held still while the glass reflection is subtly delayed and its hand remains down. Use one practical flashlight beam with readable falloff and quiet shadow planes. Keep the reflection behind the glass, never as a second physical person in the room. Avoid captions, horror typography, duplicate bodies and a bright fantasy glow.
```

## 段落地图（分段地图）

| 段落 | 时间 | 时长 | H3模式 | 创作事件/意图 | 状态 |
|---|---|---:|---|---|---|
| SUSPENSE_SEG01 | 0.000s–10.000s | 10s | I2VA | 见完整 H3 正文 | DRAFT_MISSING_REFERENCES |

## 每段上传参考助手

每张卡只覆盖一个 Segment；先看状态与实际文件，再按标签顺序上传。Subject 是内容对象，不是额外上传槽位。

### SUSPENSE_SEG01 · I2VA · 10 秒

提交状态：DRAFT_MISSING_REFERENCES · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SUSPENSE_SEG01.h3.draft.txt) · [独立上传卡](SUSPENSE_SEG01.upload.md)

绑定版本：`0de2bb927100f76588be86b209cea898be3fac307510be12ab16a089ebbf73d7` · 正文 SHA-256：`f2735a5d3940903155fd3a194898ffcdd73bbe061029acf344e711d57062f2ec`

参考图上传助手：每段是独立请求；按顺序上传实际媒体，不上传 `.image.txt` 或本卡。

| 顺序/标签 | 实际上传文件/状态 | 资产与版本 | 内容对象/说话人 | 用途与生效范围 | 必须保留 | 禁止继承 |
|---|---|---|---|---|---|---|
| 1 / `<Picture 1>` | 待生成/待绑定：media/PENDING-suspense-archive-approved.png; PLANNED_OR_CONFLICTED; NOT_UPLOADED | S01 / planned-v1 | S01 | opening composition anchor; FILM-S01-SH001 · 全局帧 0–120（末帧不含） | approved opening stance, archive geometry and low flashlight placement | later reflected-hand motion and any unrelated figure or environment |

视频参考：未声明；不虚构 Video 标签。音频参考：未声明；不虚构 Audio 标签。

- 阻塞：<Picture 1>: missing or empty reference media: PENDING-suspense-archive-approved.png
- 阻塞：h3_schema: missing reference file: media/PENDING-suspense-archive-approved.png

下一步：补齐上述素材、版本或合同缺项后重新编译到新目录；保留创作全文，不改名冒充正式稿，不切换 T2VA。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

## H3 正文文件

每个文件都是独立请求；请复制对应文件的完整正文，不把本页说明、manifest 或上传卡混入模型输入。

| 段落 | 状态 | 完整 H3/草案 | 独立上传卡 |
|---|---|---|---|
| SUSPENSE_SEG01 | DRAFT_MISSING_REFERENCES | [SUSPENSE_SEG01.h3.draft.txt](SUSPENSE_SEG01.h3.draft.txt) | [SUSPENSE_SEG01.upload.md](SUSPENSE_SEG01.upload.md) |

## 执行顺序与阻塞项

1. 待制作资产先按自己的上传卡上传实际参考图、提交完整资产提示词；生成后登记真实文件、版本、哈希并批准，再重新编译下游。已经批准且未变化的资产直接复用。
2. 打开每个 Segment 的上传卡，只上传该段表内的真实媒体，并在入口核对模式、时长和槽位编号。
3. 打开对应 H3 文件，复制完整正文提交；`CHAT_DELIVERY.md` 不替代 H3 正文文件。
4. 平台上传后另行保存入口回执；本地 `READY_TO_UPLOAD` 不等于平台已上传，`visual_status=UNVERIFIED` 不得升级。

当前阻塞：
- SUSPENSE_SEG01：<Picture 1>: missing or empty reference media: PENDING-suspense-archive-approved.png
- SUSPENSE_SEG01：h3_schema: missing reference file: media/PENDING-suspense-archive-approved.png
- SUSPENSE_SEG01：<Picture 1> 待真实素材绑定

自动文件模式：长 H3 正文留在独立文件；本页保留创作摘要、资产提示词、分段地图和每段上传助手，不能用总清单链接代替操作卡。

