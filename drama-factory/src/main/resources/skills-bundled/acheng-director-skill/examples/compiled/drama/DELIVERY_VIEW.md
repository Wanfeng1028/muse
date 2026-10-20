# H3 视频交付总览 · Acheng Director 生产台

## 总控台

项目：EXAMPLE_DRAMA
总时长：20 秒 · 24/1 fps
段落数量：2 · 模式：autonomous_file_batch
状态：机器检查不等于平台已上传或影像已生成；缺素材与合同缺项保持草案。

## 创作摘要

受伤的陆川一开始仍攥着钥匙；岑禾没有抢夺，只留出接收的手。陆川承认之前拒绝协作，并把钥匙交给她。岑禾以共同行动回应，右腕伤势没有因为情绪转变消失。

## 资产目录与提示词

以下是可直接交给画布 Agent 的独立资产图提示词。提示词文件是生成指令，不是已经生成的图片；状态为 PLANNED 时仍需先补齐真实参考素材。

| 资产 | 状态 | 用途 | 参考依赖 | 提示词文件 |
|---|---|---|---|---|
| 受伤的陆川一开始仍攥着钥匙；岑禾没有抢夺，只留出接收的手 (`ASSET_02_DRAMA`) | PROMPT_READY | Create one opening keyframe before the exchange. | 无 | [asset_prompts/ASSET_02_DRAMA.image.txt](asset_prompts/ASSET_02_DRAMA.image.txt) |

### 可复制资产提示词

#### 受伤的陆川一开始仍攥着钥匙；岑禾没有抢夺，只留出接收的手 · PROMPT_READY

完整文件：[asset_prompts/ASSET_02_DRAMA.image.txt](asset_prompts/ASSET_02_DRAMA.image.txt)

独立上传卡：[ASSET_02_DRAMA.asset-upload.md](ASSET_02_DRAMA.asset-upload.md)

### 受伤的陆川一开始仍攥着钥匙；岑禾没有抢夺，只留出接收的手 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ASSET_02_DRAMA.image.txt>) · SHA-256：bf7e27e294178f1976cb610afc9079d865ba092b2c2d5c9c827e2f3eff326d7d

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


```text
Lu Chuan is a 34-year-old man, 1.80 meters tall, with balanced adult proportions, naturally broad shoulders, a square jaw, short dark hair and a short scar above his right eyebrow. He wears a gray woven work jacket over a gray shirt and a functional waist belt. Cen He is a 32-year-old woman, 1.70 meters tall, with a lean adult build, oval face, dark almond-shaped eyes and dark hair tied low behind her head. She wears an olive canvas coat over a cream work shirt and dark straight trousers. Create one live-action medium-close two-person keyframe in the maintenance room. Lu Chuan, an adult man with a short scar above his right eyebrow and a gray woven work jacket, sits on the left; his bandaged right wrist rests on the desk, and his left hand holds one brass key. Cen He, an adult woman with tied dark hair and an olive coat, sits on the right with an empty palm held between them. Capture the single moment before Lu releases the key. Use a 65 mm equivalent lens from the south side, showing eyes, shoulders and both hands together. One east window casts soft directional light across their cheek planes; a weak wall reflection leaves the shadow side readable. Skin has broad soft highlights, cloth folds retain fibrous edges only near the hands, and the brass key catches a narrow highlight. The rear wall and key hook remain quiet low-frequency shapes. Preserve identity, hand ownership, the bandage and the room geometry. Avoid waxy faces, extra hands and ghost texture.
```

## 段落地图（分段地图）

| 段落 | 时间 | 时长 | H3模式 | 创作事件/意图 | 状态 |
|---|---|---:|---|---|---|
| DRAMA_SEG01 | 0.000s–10.000s | 10s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| DRAMA_SEG02 | 10.000s–20.000s | 10s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |

## 每段上传参考助手

每张卡只覆盖一个 Segment；先看状态与实际文件，再按标签顺序上传。Subject 是内容对象，不是额外上传槽位。

### DRAMA_SEG01 · T2VA · 10 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](DRAMA_SEG01.h3.txt) · [独立上传卡](DRAMA_SEG01.upload.md)

绑定版本：`bcb31862ae9d5cf759a3e71b2babf1c00ce86dcb5d5b115f3cb12d90cf421b96` · 正文 SHA-256：`c6de183de6e6d260c5d690d37325f31e12e051ca67660081f2d97208bab7fdbb`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### DRAMA_SEG02 · T2VA · 10 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](DRAMA_SEG02.h3.txt) · [独立上传卡](DRAMA_SEG02.upload.md)

绑定版本：`b7cecf72549105eca6adb6207a4a3db25aac32f862623574ba782ea14770c6f8` · 正文 SHA-256：`153fb4ca8aedad373a4349c5083e2aa19fda50011eb54484a7836d964b4d7b04`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

## H3 正文文件

每个文件都是独立请求；请复制对应文件的完整正文，不把本页说明、manifest 或上传卡混入模型输入。

| 段落 | 状态 | 完整 H3/草案 | 独立上传卡 |
|---|---|---|---|
| DRAMA_SEG01 | READY_TO_UPLOAD | [DRAMA_SEG01.h3.txt](DRAMA_SEG01.h3.txt) | [DRAMA_SEG01.upload.md](DRAMA_SEG01.upload.md) |
| DRAMA_SEG02 | READY_TO_UPLOAD | [DRAMA_SEG02.h3.txt](DRAMA_SEG02.h3.txt) | [DRAMA_SEG02.upload.md](DRAMA_SEG02.upload.md) |

## 执行顺序与阻塞项

1. 待制作资产先按自己的上传卡上传实际参考图、提交完整资产提示词；生成后登记真实文件、版本、哈希并批准，再重新编译下游。已经批准且未变化的资产直接复用。
2. 打开每个 Segment 的上传卡，只上传该段表内的真实媒体，并在入口核对模式、时长和槽位编号。
3. 打开对应 H3 文件，复制完整正文提交；`CHAT_DELIVERY.md` 不替代 H3 正文文件。
4. 平台上传后另行保存入口回执；本地 `READY_TO_UPLOAD` 不等于平台已上传，`visual_status=UNVERIFIED` 不得升级。

当前阻塞：无机器识别阻塞；仍需实际平台上传回执和生成后人工画面验收。

自动文件模式：长 H3 正文留在独立文件；本页保留创作摘要、资产提示词、分段地图和每段上传助手，不能用总清单链接代替操作卡。

