# H3 视频交付总览 · Acheng Director 生产台

## 总控台

项目：EXAMPLE_ANIMATED_PHONE
总时长：10 秒 · 24/1 fps
段落数量：1 · 模式：autonomous_file_batch
状态：机器检查不等于平台已上传或影像已生成；缺素材与合同缺项保持草案。

## 创作摘要

陈千语在电话中从轻笑转为确信，以手势和尾部余势承接跨切镜的同一句台词；电话始终留在左耳。

段落推进：
- ANIME_PHONE_SEG01：[keyframe completion + reference generation] The target video starts from <Picture 1> and follows Chen Qianyu's smug phone performance through a hard cut to her back view.

## 资产目录与提示词

以下是可直接交给画布 Agent 的独立资产图提示词。提示词文件是生成指令，不是已经生成的图片；状态为 PLANNED 时仍需先补齐真实参考素材。

| 资产 | 状态 | 用途 | 参考依赖 | 提示词文件 |
|---|---|---|---|---|
| 陈千语·办公室电话戏 · laughing-open · v1.1 (`ASSET_ANIME_PHONE`) | PROMPT_READY | Create one opening keyframe before the exchange. | 无 | [asset_prompts/ASSET_ANIME_PHONE.image.txt](asset_prompts/ASSET_ANIME_PHONE.image.txt) |

### 可复制资产提示词

#### 陈千语·办公室电话戏 · laughing-open · v1.1 · PROMPT_READY

完整文件：[asset_prompts/ASSET_ANIME_PHONE.image.txt](asset_prompts/ASSET_ANIME_PHONE.image.txt)

独立上传卡：[ASSET_ANIME_PHONE.asset-upload.md](ASSET_ANIME_PHONE.asset-upload.md)

### 陈千语·办公室电话戏 · laughing-open · v1.1 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / laughing-open

[完整提示词/草案](<asset_prompts/ASSET_ANIME_PHONE.image.txt>) · SHA-256：e5fc6003f9200f9d8ae458326cecb1a639c22a735a88a5859773ff0e2cf8e384

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


## 段落地图（分段地图）

| 段落 | 时间 | 时长 | H3模式 | 创作事件/意图 | 状态 |
|---|---|---:|---|---|---|
| ANIME_PHONE_SEG01 | 0.000s–10.000s | 10s | Ref2VA | [keyframe completion + reference generation] The target video starts from <Picture 1> and follows Chen Qianyu's smug phone performance through a hard cut to her back view. | DRAFT_MISSING_REFERENCES |

## 每段上传参考助手

每张卡只覆盖一个 Segment；先看状态与实际文件，再按标签顺序上传。Subject 是内容对象，不是额外上传槽位。

**本段创作摘要：** [keyframe completion + reference generation] The target video starts from <Picture 1> and follows Chen Qianyu's smug phone performance through a hard cut to her back view.

### ANIME_PHONE_SEG01 · Ref2VA · 10 秒

提交状态：DRAFT_MISSING_REFERENCES · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](ANIME_PHONE_SEG01.h3.draft.txt) · [独立上传卡](ANIME_PHONE_SEG01.upload.md)

绑定版本：`bbfe17d564960bfdd0008e5994e8c380e96ecfb7a14c0bf28348c4039218356f` · 正文 SHA-256：`5d246a7ac2d03004b6b20fe7c5374a02c126347de2905b480ddf7bb708da2776`

参考图上传助手：每段是独立请求；按顺序上传实际媒体，不上传 `.image.txt` 或本卡。

| 顺序/标签 | 实际上传文件/状态 | 资产与版本 | 内容对象/说话人 | 用途与生效范围 | 必须保留 | 禁止继承 |
|---|---|---|---|---|---|---|
| 1 / `<Picture 1>` | 待生成/待绑定：media/PENDING-anime-phone-approved.png; PLANNED_OR_CONFLICTED; NOT_UPLOADED | 未绑定 / planned-v1 | <Subject 1> = CHAR_QIAN (S1); <Subject 2> = S01 (非说话人) | first-frame composition and pose anchor; FILM-S01-SH001 · 全局帧 0–120（末帧不含）; FILM-S01-SH002 · 全局帧 120–240（末帧不含）；构图锚点仅 FILM-S01-SH001 | approved character identity and office layout across both shots; opening pose only in Shot 1 | source pose after the opening, future gestures, captions and unrelated characters |

视频参考：未声明；不虚构 Video 标签。音频参考：未声明；不虚构 Audio 标签。

Subject 是内容对象，不是新增上传槽位；一份素材可承载多个对象，同一对象可用多个来源。
- 阻塞：<Picture 1>: missing or empty reference media: PENDING-anime-phone-approved.png
- 阻塞：h3_schema: missing reference file: media/PENDING-anime-phone-approved.png

下一步：补齐上述素材、版本或合同缺项后重新编译到新目录；保留创作全文，不改名冒充正式稿，不切换 T2VA。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

## H3 正文文件

每个文件都是独立请求；请复制对应文件的完整正文，不把本页说明、manifest 或上传卡混入模型输入。

| 段落 | 状态 | 完整 H3/草案 | 独立上传卡 |
|---|---|---|---|
| ANIME_PHONE_SEG01 | DRAFT_MISSING_REFERENCES | [ANIME_PHONE_SEG01.h3.draft.txt](ANIME_PHONE_SEG01.h3.draft.txt) | [ANIME_PHONE_SEG01.upload.md](ANIME_PHONE_SEG01.upload.md) |

## 执行顺序与阻塞项

1. 待制作资产先按自己的上传卡上传实际参考图、提交完整资产提示词；生成后登记真实文件、版本、哈希并批准，再重新编译下游。已经批准且未变化的资产直接复用。
2. 打开每个 Segment 的上传卡，只上传该段表内的真实媒体，并在入口核对模式、时长和槽位编号。
3. 打开对应 H3 文件，复制完整正文提交；`CHAT_DELIVERY.md` 不替代 H3 正文文件。
4. 平台上传后另行保存入口回执；本地 `READY_TO_UPLOAD` 不等于平台已上传，`visual_status=UNVERIFIED` 不得升级。

当前阻塞：
- ANIME_PHONE_SEG01：<Picture 1>: missing or empty reference media: PENDING-anime-phone-approved.png
- ANIME_PHONE_SEG01：h3_schema: missing reference file: media/PENDING-anime-phone-approved.png
- ANIME_PHONE_SEG01：<Picture 1> 待真实素材绑定

自动文件模式：长 H3 正文留在独立文件；本页保留创作摘要、资产提示词、分段地图和每段上传助手，不能用总清单链接代替操作卡。

