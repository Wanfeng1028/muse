# H3 视频交付总览 · Acheng Director 生产台

## 总控台

项目：SERIAL_TIDE_ARCHIVE
总时长：180 秒 · 24/1 fps
段落数量：12 · 模式：autonomous_file_batch
状态：机器检查不等于平台已上传或影像已生成；缺素材与合同缺项保持草案。

## 创作摘要

三集各一分钟的沿海调查样例。档案员梅林起初把制度认证当作真相；工务员柏保留旧案责任。两人用不同来源交叉核对潮汐记录，区分抄录事实与责任人身份，最终保留异议而非用新结论覆盖旧证据。八条线路在12个完整场次内交汇；这是跨集机制示例，不声称已制作长篇成片。

## 资产目录与提示词

以下是可直接交给画布 Agent 的独立资产图提示词。提示词文件是生成指令，不是已经生成的图片；状态为 PLANNED 时仍需先补齐真实参考素材。

| 资产 | 状态 | 用途 | 参考依赖 | 提示词文件 |
|---|---|---|---|---|
| Meilin · neutral_identity · v1.0 (`ART_MEI`) | PROMPT_READY | Create the single still specified in the complete prompt. | 无 | [asset_prompts/ART_MEI.image.txt](asset_prompts/ART_MEI.image.txt) |
| Bo · neutral_identity · v1.0 (`ART_BO`) | PROMPT_READY | Create the single still specified in the complete prompt. | 无 | [asset_prompts/ART_BO.image.txt](asset_prompts/ART_BO.image.txt) |
| 潮汐档案室·空间母图 · v1.0 (`ART_ARCHIVE`) | PROMPT_READY | Create the single still specified in the complete prompt. | 无 | [asset_prompts/ART_ARCHIVE.image.txt](asset_prompts/ART_ARCHIVE.image.txt) |
| 码头值班亭·空间母图 · v1.0 (`ART_DOCK`) | PROMPT_READY | Create the single still specified in the complete prompt. | 无 | [asset_prompts/ART_DOCK.image.txt](asset_prompts/ART_DOCK.image.txt) |
| 两份潮汐原件·道具基准 · v1.0 (`ART_LEDGER`) | PROMPT_READY | Create the single still specified in the complete prompt. | 无 | [asset_prompts/ART_LEDGER.image.txt](asset_prompts/ART_LEDGER.image.txt) |
| 潮汐表与航运单·道具基准 · v1.0 (`ART_TIDE`) | PROMPT_READY | Create the single still specified in the complete prompt. | 无 | [asset_prompts/ART_TIDE.image.txt](asset_prompts/ART_TIDE.image.txt) |
| 封存通知与异议·道具基准 · v1.0 (`ART_NOTICE`) | PROMPT_READY | Create the single still specified in the complete prompt. | 无 | [asset_prompts/ART_NOTICE.image.txt](asset_prompts/ART_NOTICE.image.txt) |
| 门槛沙袋·道具基准 · v1.0 (`ART_SANDBAG`) | PROMPT_READY | Create the single still specified in the complete prompt. | 无 | [asset_prompts/ART_SANDBAG.image.txt](asset_prompts/ART_SANDBAG.image.txt) |
| 铅笔纸签与独立比对页 · v1.0 (`ART_STATIONERY`) | PROMPT_READY | Create the single still specified in the complete prompt. | 无 | [asset_prompts/ART_STATIONERY.image.txt](asset_prompts/ART_STATIONERY.image.txt) |
| 第一集开场·原件对照 · v1.0 (`ART_KEYFRAME_01`) | PLANNED | Create the single still specified in the complete prompt. | Reference image 1: ART_MEI, Reference image 2: ART_BO, Reference image 3: ART_ARCHIVE, Reference image 4: ART_LEDGER, Reference image 5: ART_STATIONERY | [asset_prompts/ART_KEYFRAME_01.draft.txt](asset_prompts/ART_KEYFRAME_01.draft.txt) |
| 第二集开场·保留异议 · v1.0 (`ART_KEYFRAME_05`) | PLANNED | Create the single still specified in the complete prompt. | Reference image 1: ART_MEI, Reference image 2: ART_BO, Reference image 3: ART_ARCHIVE, Reference image 4: ART_LEDGER, Reference image 5: ART_NOTICE | [asset_prompts/ART_KEYFRAME_05.draft.txt](asset_prompts/ART_KEYFRAME_05.draft.txt) |
| 第三集开场·独立佐证 · v1.0 (`ART_KEYFRAME_09`) | PLANNED | Create the single still specified in the complete prompt. | Reference image 1: ART_MEI, Reference image 2: ART_BO, Reference image 3: ART_ARCHIVE, Reference image 4: ART_LEDGER, Reference image 5: ART_STATIONERY | [asset_prompts/ART_KEYFRAME_09.draft.txt](asset_prompts/ART_KEYFRAME_09.draft.txt) |

### 可复制资产提示词

#### Meilin · neutral_identity · v1.0 · PROMPT_READY

完整文件：[asset_prompts/ART_MEI.image.txt](asset_prompts/ART_MEI.image.txt)

独立上传卡：[ART_MEI.asset-upload.md](ART_MEI.asset-upload.md)

### Meilin · neutral_identity · v1.0 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：character · 状态版本：neutral_identity / 未指定

[完整提示词/草案](<asset_prompts/ART_MEI.image.txt>) · SHA-256：7f57dec6a5e408d915b75169571a82c57c496491108ba61e0562feb88ba25b3d

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


```text
This is the Meilin character identity asset in the approved neutral_identity state. Create one clean four-view character turnaround board for this single subject, arranged left to right: 1) full-body front view, 2) full-body back view, 3) full-body side profile, 4) front-facing head-and-shoulders face close-up. Keep the same proportions, costume, hairstyle, facial features, neutral standing pose, lighting and background across the three full-body views; use the fourth panel only for the straight-on face. Do not render the character name or state as visible text, and do not add panel letters, labels, logos, extra people or extra limbs. Create a neutral full-body live-action character reference. Meilin is a 32-year-old woman with a narrow oval face, straight black eyebrows and chin-length dark hair tucked behind her left ear. She wears a faded blue cotton jacket, cream shirt and dark straight trousers; her hands are uninjured. Use one broad upper-left light with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

#### Bo · neutral_identity · v1.0 · PROMPT_READY

完整文件：[asset_prompts/ART_BO.image.txt](asset_prompts/ART_BO.image.txt)

独立上传卡：[ART_BO.asset-upload.md](ART_BO.asset-upload.md)

### Bo · neutral_identity · v1.0 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：character · 状态版本：neutral_identity / 未指定

[完整提示词/草案](<asset_prompts/ART_BO.image.txt>) · SHA-256：1a6a86e6cae6a8a9855379177725836eaf509eada63782fb632a9234a7c2d4aa

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


```text
This is the Bo character identity asset in the approved neutral_identity state. Create one clean four-view character turnaround board for this single subject, arranged left to right: 1) full-body front view, 2) full-body back view, 3) full-body side profile, 4) front-facing head-and-shoulders face close-up. Keep the same proportions, costume, hairstyle, facial features, neutral standing pose, lighting and background across the three full-body views; use the fourth panel only for the straight-on face. Do not render the character name or state as visible text, and do not add panel letters, labels, logos, extra people or extra limbs. Create a neutral full-body live-action character reference. Bo is a 40-year-old man with a broad face, short salt-and-pepper hair and a small pale scar on his left cheek. He wears a brown canvas vest over a rolled-sleeve gray shirt and dark work trousers; his hands are uninjured. Use one broad upper-left light with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

#### 潮汐档案室·空间母图 · v1.0 · PROMPT_READY

完整文件：[asset_prompts/ART_ARCHIVE.image.txt](asset_prompts/ART_ARCHIVE.image.txt)

独立上传卡：[ART_ARCHIVE.asset-upload.md](ART_ARCHIVE.asset-upload.md)

### 潮汐档案室·空间母图 · v1.0 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ART_ARCHIVE.image.txt>) · SHA-256：76535a520447b0a9c378b9da7e1a148045e4343bc4979382135adbed82a44824

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


```text
Create an unoccupied live-action environment reference. The harbor archive has a waist-high oak reading table, one frosted east window, a north shelf of cloth-bound ledgers and a west door. Soft window light falls across the table; the shelf remains in broad shadow. Use the stated world-space light source, keeping its direction consistent across the scene, with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

#### 码头值班亭·空间母图 · v1.0 · PROMPT_READY

完整文件：[asset_prompts/ART_DOCK.image.txt](asset_prompts/ART_DOCK.image.txt)

独立上传卡：[ART_DOCK.asset-upload.md](ART_DOCK.asset-upload.md)

### 码头值班亭·空间母图 · v1.0 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ART_DOCK.image.txt>) · SHA-256：701a7c87a54727aa5230065279ac25b35d489656f6d283fe92b863fc8a278406

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


```text
Create an unoccupied live-action environment reference. The dock watch hut has a fixed timber counter, an east window overlooking the tide gauge, a west door and a brass bell mounted on its north post. A waist-high manual-bypass cabinet below the east window bears an unbroken paper seal. Broad overcast daylight enters from the east; wet boards remain matte except at small puddles. Use the stated world-space light source, keeping its direction consistent across the scene, with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

#### 两份潮汐原件·道具基准 · v1.0 · PROMPT_READY

完整文件：[asset_prompts/ART_LEDGER.image.txt](asset_prompts/ART_LEDGER.image.txt)

独立上传卡：[ART_LEDGER.asset-upload.md](ART_LEDGER.asset-upload.md)

### 两份潮汐原件·道具基准 · v1.0 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ART_LEDGER.image.txt>) · SHA-256：d91a979b14a79c122c7218936ea646397d7e9075cd872e500329d2e097c32290

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


```text
Create a live-action reference of two cloth-bound tide ledgers lying open side by side, with cream paper and matching tiny ink notches in their right margins. Other writing is indistinct, with no invented readable text. Use one broad upper-left light with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

#### 潮汐表与航运单·道具基准 · v1.0 · PROMPT_READY

完整文件：[asset_prompts/ART_TIDE.image.txt](asset_prompts/ART_TIDE.image.txt)

独立上传卡：[ART_TIDE.asset-upload.md](ART_TIDE.asset-upload.md)

### 潮汐表与航运单·道具基准 · v1.0 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ART_TIDE.image.txt>) · SHA-256：e59a1ea965eb0d415bdf2b93acb4f6c13f257791a7558403a3a14082225a7791

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


```text
Create a live-action reference of a cream tide sheet and a separate shipping manifest lying flat side by side on aged timber. Show neat columns and small ink marks without invented legible writing. Use one broad upper-left light with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

#### 封存通知与异议·道具基准 · v1.0 · PROMPT_READY

完整文件：[asset_prompts/ART_NOTICE.image.txt](asset_prompts/ART_NOTICE.image.txt)

独立上传卡：[ART_NOTICE.asset-upload.md](ART_NOTICE.asset-upload.md)

### 封存通知与异议·道具基准 · v1.0 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ART_NOTICE.image.txt>) · SHA-256：4a60bb88b4b6fe5392f9622a37f3edcd34303eb587deab93e4392a044f005d8b

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


```text
Create a live-action prop reference of one cream closure notice and a separate written objection on an oak tabletop. Use visible ruled receipt fields and a small blue signature mark, with other writing indistinct and no invented legible text. Use one broad upper-left light with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

#### 门槛沙袋·道具基准 · v1.0 · PROMPT_READY

完整文件：[asset_prompts/ART_SANDBAG.image.txt](asset_prompts/ART_SANDBAG.image.txt)

独立上传卡：[ART_SANDBAG.asset-upload.md](ART_SANDBAG.asset-upload.md)

### 门槛沙袋·道具基准 · v1.0 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ART_SANDBAG.image.txt>) · SHA-256：e6929264dda171406f1503f72ed70504b4ed330474683f46ab7f9beb0f86151d

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


```text
Create a live-action prop reference of one squat tan canvas sandbag tied with dark cord. Its bottom flattens under its weight and its seams remain visible; the canvas has a few broad folds and no printed writing. Use one broad upper-left light with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

#### 铅笔纸签与独立比对页 · v1.0 · PROMPT_READY

完整文件：[asset_prompts/ART_STATIONERY.image.txt](asset_prompts/ART_STATIONERY.image.txt)

独立上传卡：[ART_STATIONERY.asset-upload.md](ART_STATIONERY.asset-upload.md)

### 铅笔纸签与独立比对页 · v1.0 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ART_STATIONERY.image.txt>) · SHA-256：14648ad4b5911772c5edecb47962a43934f05047c44ad888c76c07156b63b8f2

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


```text
Create a live-action prop reference of one short wooden pencil, two narrow cream paper markers and one loose comparison sheet with two ruled columns. Keep the paper matte and the graphite tip dark; marks are indistinct without invented readable words. Use one broad upper-left light with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

#### 第一集开场·原件对照 · v1.0 · PLANNED

完整文件：[asset_prompts/ART_KEYFRAME_01.draft.txt](asset_prompts/ART_KEYFRAME_01.draft.txt)

独立上传卡：[ART_KEYFRAME_01.asset-upload.md](ART_KEYFRAME_01.asset-upload.md)

### 第一集开场·原件对照 · v1.0 · 资产图上传卡

状态：PLANNED · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ART_KEYFRAME_01.draft.txt>) · SHA-256：77909e33761fa12820091fc5ffb0815b56bdcf55638e460224802e52b2d707ad

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

逐项上传实际图片；不上传 .image.txt，缺失槽位不重排编号。

| 槽位 | 实际图片/缺项 | 用途/对象 | 版本 | 必须保留 | 禁止继承 |
|---|---|---|---|---|---|
| 1 | 待提供：ART_MEI；生成并批准后重新编译 | identity / Meilin the adult archive clerk | v1.0 | her face, hair, adult proportions and blue cotton jacket | unrelated pose, crop and lighting; use the target composition described below |
| 2 | 待提供：ART_BO；生成并批准后重新编译 | identity / Bo the adult dock mechanic | v1.0 | his face, cheek scar and brown canvas vest | unrelated pose, crop and lighting; use the target composition described below |
| 3 | 待提供：ART_ARCHIVE；生成并批准后重新编译 | scene / the archive room | v1.0 | the oak table, east window, north shelf and west door | unrelated pose, crop and lighting; use the target composition described below |
| 4 | 待提供：ART_LEDGER；生成并批准后重新编译 | composition / the two original ledgers | v1.0 | the two cloth bindings and matching ink notches | unrelated pose, crop and lighting; use the target composition described below |
| 5 | 待提供：ART_STATIONERY；生成并批准后重新编译 | composition / the pencil and paper markers | v1.0 | the short wooden pencil and narrow cream paper markers | source background and camera position |

下一步：先补齐缺项或修复正文合同，再重新导出到新目录；当前草案不可提交。


```text
DRAFT — required references or standalone prompt contract is unresolved.

Reference image 1 supplies identity guidance for Meilin the adult archive clerk. Preserve her face, hair, adult proportions and blue cotton jacket. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 2 supplies identity guidance for Bo the adult dock mechanic. Preserve his face, cheek scar and brown canvas vest. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 3 supplies scene guidance for the archive room. Preserve the oak table, east window, north shelf and west door. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 4 supplies composition guidance for the two original ledgers. Preserve the two cloth bindings and matching ink notches. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 5 supplies composition guidance for the pencil and paper markers. Preserve the short wooden pencil and narrow cream paper markers. Do not inherit source background and camera position.

Create one live-action medium two-shot before any gesture begins. Meilin is a 32-year-old woman with a narrow oval face, straight black eyebrows and chin-length dark hair tucked behind her left ear. She wears a faded blue cotton jacket, cream shirt and dark straight trousers; her hands are uninjured. Bo is a 40-year-old man with a broad face, short salt-and-pepper hair and a small pale scar on his left cheek. He wears a brown canvas vest over a rolled-sleeve gray shirt and dark work trousers; his hands are uninjured. The harbor archive has a waist-high oak reading table, one frosted east window, a north shelf of cloth-bound ledgers and a west door. Soft window light falls across the table; the shelf remains in broad shadow. Meilin stands left and Bo right, both looking down at two open ledgers lying flat between them. Their hands rest separately on the table edge. Use the stated world-space light source, keeping its direction consistent across the scene, with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text. A short wooden pencil and two narrow cream paper markers lie beside the original ledgers.
```

#### 第二集开场·保留异议 · v1.0 · PLANNED

完整文件：[asset_prompts/ART_KEYFRAME_05.draft.txt](asset_prompts/ART_KEYFRAME_05.draft.txt)

独立上传卡：[ART_KEYFRAME_05.asset-upload.md](ART_KEYFRAME_05.asset-upload.md)

### 第二集开场·保留异议 · v1.0 · 资产图上传卡

状态：PLANNED · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ART_KEYFRAME_05.draft.txt>) · SHA-256：6c7625fe4c4de584aa3ff95c4f9c964b99971a8e46a8a161b26846406713e39f

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

逐项上传实际图片；不上传 .image.txt，缺失槽位不重排编号。

| 槽位 | 实际图片/缺项 | 用途/对象 | 版本 | 必须保留 | 禁止继承 |
|---|---|---|---|---|---|
| 1 | 待提供：ART_MEI；生成并批准后重新编译 | identity / Meilin the adult archive clerk | v1.0 | her face, hair, adult proportions and blue cotton jacket | unrelated pose, crop and lighting; use the target composition described below |
| 2 | 待提供：ART_BO；生成并批准后重新编译 | identity / Bo the adult dock mechanic | v1.0 | his face, cheek scar and brown canvas vest | unrelated pose, crop and lighting; use the target composition described below |
| 3 | 待提供：ART_ARCHIVE；生成并批准后重新编译 | scene / the archive room | v1.0 | the oak table, east window, north shelf and west door | unrelated pose, crop and lighting; use the target composition described below |
| 4 | 待提供：ART_LEDGER；生成并批准后重新编译 | composition / the two original ledgers | v1.0 | the two cloth bindings and matching ink notches | unrelated pose, crop and lighting; use the target composition described below |
| 5 | 待提供：ART_NOTICE；生成并批准后重新编译 | composition / the closure notice and objection | v1.0 | their paper format and ruled receipt fields | unrelated pose, crop and lighting; use the target composition described below |

下一步：先补齐缺项或修复正文合同，再重新导出到新目录；当前草案不可提交。


```text
DRAFT — required references or standalone prompt contract is unresolved.

Reference image 1 supplies identity guidance for Meilin the adult archive clerk. Preserve her face, hair, adult proportions and blue cotton jacket. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 2 supplies identity guidance for Bo the adult dock mechanic. Preserve his face, cheek scar and brown canvas vest. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 3 supplies scene guidance for the archive room. Preserve the oak table, east window, north shelf and west door. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 4 supplies composition guidance for the two original ledgers. Preserve the two cloth bindings and matching ink notches. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 5 supplies composition guidance for the closure notice and objection. Preserve their paper format and ruled receipt fields. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Create one live-action medium two-shot before any gesture begins. Meilin is a 32-year-old woman with a narrow oval face, straight black eyebrows and chin-length dark hair tucked behind her left ear. She wears a faded blue cotton jacket, cream shirt and dark straight trousers; her hands are uninjured. Bo is a 40-year-old man with a broad face, short salt-and-pepper hair and a small pale scar on his left cheek. He wears a brown canvas vest over a rolled-sleeve gray shirt and dark work trousers; his hands are uninjured. The harbor archive has a waist-high oak reading table, one frosted east window, a north shelf of cloth-bound ledgers and a west door. Soft window light falls across the table; the shelf remains in broad shadow. Meilin stands left and Bo right, both looking down at two open ledgers lying flat between them. Their hands rest separately on the table edge. A closure notice and separate written objection lie beside the ledgers, with the receipt line visible. Use the stated world-space light source, keeping its direction consistent across the scene, with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

#### 第三集开场·独立佐证 · v1.0 · PLANNED

完整文件：[asset_prompts/ART_KEYFRAME_09.draft.txt](asset_prompts/ART_KEYFRAME_09.draft.txt)

独立上传卡：[ART_KEYFRAME_09.asset-upload.md](ART_KEYFRAME_09.asset-upload.md)

### 第三集开场·独立佐证 · v1.0 · 资产图上传卡

状态：PLANNED · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ART_KEYFRAME_09.draft.txt>) · SHA-256：c8ca1d9f6f9d92aea77928c7726e62766a34220ff3fd93257a5dd7dc0551bb2c

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

逐项上传实际图片；不上传 .image.txt，缺失槽位不重排编号。

| 槽位 | 实际图片/缺项 | 用途/对象 | 版本 | 必须保留 | 禁止继承 |
|---|---|---|---|---|---|
| 1 | 待提供：ART_MEI；生成并批准后重新编译 | identity / Meilin the adult archive clerk | v1.0 | her face, hair, adult proportions and blue cotton jacket | unrelated pose, crop and lighting; use the target composition described below |
| 2 | 待提供：ART_BO；生成并批准后重新编译 | identity / Bo the adult dock mechanic | v1.0 | his face, cheek scar and brown canvas vest | unrelated pose, crop and lighting; use the target composition described below |
| 3 | 待提供：ART_ARCHIVE；生成并批准后重新编译 | scene / the archive room | v1.0 | the oak table, east window, north shelf and west door | unrelated pose, crop and lighting; use the target composition described below |
| 4 | 待提供：ART_LEDGER；生成并批准后重新编译 | composition / the two original ledgers | v1.0 | the two cloth bindings and matching ink notches | unrelated pose, crop and lighting; use the target composition described below |
| 5 | 待提供：ART_STATIONERY；生成并批准后重新编译 | composition / the independent comparison sheet | v1.0 | its two ruled columns and short wooden pencil | unrelated pose, crop and lighting; use the target composition described below |

下一步：先补齐缺项或修复正文合同，再重新导出到新目录；当前草案不可提交。


```text
DRAFT — required references or standalone prompt contract is unresolved.

Reference image 1 supplies identity guidance for Meilin the adult archive clerk. Preserve her face, hair, adult proportions and blue cotton jacket. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 2 supplies identity guidance for Bo the adult dock mechanic. Preserve his face, cheek scar and brown canvas vest. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 3 supplies scene guidance for the archive room. Preserve the oak table, east window, north shelf and west door. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 4 supplies composition guidance for the two original ledgers. Preserve the two cloth bindings and matching ink notches. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Reference image 5 supplies composition guidance for the independent comparison sheet. Preserve its two ruled columns and short wooden pencil. Do not inherit unrelated pose, crop and lighting; use the target composition described below.

Create one live-action medium two-shot before any gesture begins. Meilin is a 32-year-old woman with a narrow oval face, straight black eyebrows and chin-length dark hair tucked behind her left ear. She wears a faded blue cotton jacket, cream shirt and dark straight trousers; her hands are uninjured. Bo is a 40-year-old man with a broad face, short salt-and-pepper hair and a small pale scar on his left cheek. He wears a brown canvas vest over a rolled-sleeve gray shirt and dark work trousers; his hands are uninjured. The harbor archive has a waist-high oak reading table, one frosted east window, a north shelf of cloth-bound ledgers and a west door. Soft window light falls across the table; the shelf remains in broad shadow. Meilin stands left and Bo right, both looking down at two open ledgers lying flat between them. Their hands rest separately on the table edge. A separate two-column comparison sheet lies beside both original ledgers, its edge aligned with them. Use the stated world-space light source, keeping its direction consistent across the scene, with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

## 段落地图（分段地图）

| 段落 | 时间 | 时长 | H3模式 | 创作事件/意图 | 状态 |
|---|---|---:|---|---|---|
| SERIAL_SEG_01 | 0.000s–15.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| SERIAL_SEG_02 | 15.000s–30.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| SERIAL_SEG_03 | 30.000s–45.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| SERIAL_SEG_04 | 45.000s–60.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| SERIAL_SEG_05 | 60.000s–75.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| SERIAL_SEG_06 | 75.000s–90.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| SERIAL_SEG_07 | 90.000s–105.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| SERIAL_SEG_08 | 105.000s–120.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| SERIAL_SEG_09 | 120.000s–135.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| SERIAL_SEG_10 | 135.000s–150.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| SERIAL_SEG_11 | 150.000s–165.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| SERIAL_SEG_12 | 165.000s–180.000s | 15s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |

## 每段上传参考助手

每张卡只覆盖一个 Segment；先看状态与实际文件，再按标签顺序上传。Subject 是内容对象，不是额外上传槽位。

### SERIAL_SEG_01 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_01.h3.txt) · [独立上传卡](SERIAL_SEG_01.upload.md)

绑定版本：`5896d29895008d30e6445de5777a356b5b918878980393fab21b15061dc35ac5` · 正文 SHA-256：`4622a7b68ad48d63bc5c3329306f59a8053ae0789e588b86df4a921d94f9821f`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### SERIAL_SEG_02 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_02.h3.txt) · [独立上传卡](SERIAL_SEG_02.upload.md)

绑定版本：`d6a7086c89360edf99cc8715dce0b949b9d4a1604ec7ed1bbd059d6dbdfe9636` · 正文 SHA-256：`596e8c22bb73f697d674680c5a87f17a116ef8325f78e09009f88672970c1362`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### SERIAL_SEG_03 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_03.h3.txt) · [独立上传卡](SERIAL_SEG_03.upload.md)

绑定版本：`547d9270705666df8c75bc221c19bd78b529f17bb477030409da04ead79fb345` · 正文 SHA-256：`f0446e8a48ed05bc151a89dd7cf64d89f864a493b6569c745c5f832712db905d`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### SERIAL_SEG_04 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_04.h3.txt) · [独立上传卡](SERIAL_SEG_04.upload.md)

绑定版本：`646f4f14fc5e09b9067fb84482ca5a7572512a16d52db7dfe4d762e3115002a1` · 正文 SHA-256：`d9a11aa752c186a1fc4bfc887e9353db60a540e7c26f0f043e32360800b83d0b`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### SERIAL_SEG_05 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_05.h3.txt) · [独立上传卡](SERIAL_SEG_05.upload.md)

绑定版本：`efb2302a1537d3d7f73437ceb069d89f3c766f7e5bbc874706c2b42807d75035` · 正文 SHA-256：`60c445d475dfa9cd4249e10c21199457795f70356b0835f5ed901f29dd32e959`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### SERIAL_SEG_06 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_06.h3.txt) · [独立上传卡](SERIAL_SEG_06.upload.md)

绑定版本：`cb28106b1ff99a1e3a2215abeeae9bbb744c9cb9f67bc72c55e0fe287b8e75e3` · 正文 SHA-256：`83cbf49465b924671ce575c7e74eb52396e478fd3c7201989a97220597ba8f3c`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### SERIAL_SEG_07 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_07.h3.txt) · [独立上传卡](SERIAL_SEG_07.upload.md)

绑定版本：`8e19b594b1c48c6b9259ab70d4ccd2ce4b9894a70fbf6248660cc6bd62d310c1` · 正文 SHA-256：`8660ae5fe599aa11e4dd2d73fea63d4cdab314f5e1838ec3b0c74055d778267d`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### SERIAL_SEG_08 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_08.h3.txt) · [独立上传卡](SERIAL_SEG_08.upload.md)

绑定版本：`e5c52a0d36caa48b70f5ea3b28c38f850e5467627ce6f3b84556b246e95c4e0c` · 正文 SHA-256：`76afdbd83227e8e74385986cc8163ef8725c8ba6b031e8d23691da0d784a3981`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### SERIAL_SEG_09 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_09.h3.txt) · [独立上传卡](SERIAL_SEG_09.upload.md)

绑定版本：`e5266e226d8baf50650ab5a150d8de1a0ebfdffa81a0da012597375bd632c8be` · 正文 SHA-256：`3e9538c68bad0b6d907e651754f725b230700a1f94d5d770577b33965e0f16aa`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### SERIAL_SEG_10 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_10.h3.txt) · [独立上传卡](SERIAL_SEG_10.upload.md)

绑定版本：`8203f1a97ee141df2e3e9c9737fdb92f644a3daad172de7da475401dd14906a9` · 正文 SHA-256：`2a7a6e83510eabccdbc3937cdace92747997d4138185f7d19dcd92bceeaf5596`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### SERIAL_SEG_11 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_11.h3.txt) · [独立上传卡](SERIAL_SEG_11.upload.md)

绑定版本：`0313df9b4ce959ab0780264521bd06a42c7b954344b6d6775aee87d24905d7b4` · 正文 SHA-256：`cece2f392fbfdd2bf4537d92fe122c7d0a952348e3b54293209db041811312c6`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### SERIAL_SEG_12 · T2VA · 15 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](SERIAL_SEG_12.h3.txt) · [独立上传卡](SERIAL_SEG_12.upload.md)

绑定版本：`1aa76d2af7718706563fe9358405731e1d4918237b8aaef73783d757521543e3` · 正文 SHA-256：`ea9b6fffe75aa0f4851e41bda4096ab876776c2f8b307840899c663ffa7f8c43`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

## H3 正文文件

每个文件都是独立请求；请复制对应文件的完整正文，不把本页说明、manifest 或上传卡混入模型输入。

| 段落 | 状态 | 完整 H3/草案 | 独立上传卡 |
|---|---|---|---|
| SERIAL_SEG_01 | READY_TO_UPLOAD | [SERIAL_SEG_01.h3.txt](SERIAL_SEG_01.h3.txt) | [SERIAL_SEG_01.upload.md](SERIAL_SEG_01.upload.md) |
| SERIAL_SEG_02 | READY_TO_UPLOAD | [SERIAL_SEG_02.h3.txt](SERIAL_SEG_02.h3.txt) | [SERIAL_SEG_02.upload.md](SERIAL_SEG_02.upload.md) |
| SERIAL_SEG_03 | READY_TO_UPLOAD | [SERIAL_SEG_03.h3.txt](SERIAL_SEG_03.h3.txt) | [SERIAL_SEG_03.upload.md](SERIAL_SEG_03.upload.md) |
| SERIAL_SEG_04 | READY_TO_UPLOAD | [SERIAL_SEG_04.h3.txt](SERIAL_SEG_04.h3.txt) | [SERIAL_SEG_04.upload.md](SERIAL_SEG_04.upload.md) |
| SERIAL_SEG_05 | READY_TO_UPLOAD | [SERIAL_SEG_05.h3.txt](SERIAL_SEG_05.h3.txt) | [SERIAL_SEG_05.upload.md](SERIAL_SEG_05.upload.md) |
| SERIAL_SEG_06 | READY_TO_UPLOAD | [SERIAL_SEG_06.h3.txt](SERIAL_SEG_06.h3.txt) | [SERIAL_SEG_06.upload.md](SERIAL_SEG_06.upload.md) |
| SERIAL_SEG_07 | READY_TO_UPLOAD | [SERIAL_SEG_07.h3.txt](SERIAL_SEG_07.h3.txt) | [SERIAL_SEG_07.upload.md](SERIAL_SEG_07.upload.md) |
| SERIAL_SEG_08 | READY_TO_UPLOAD | [SERIAL_SEG_08.h3.txt](SERIAL_SEG_08.h3.txt) | [SERIAL_SEG_08.upload.md](SERIAL_SEG_08.upload.md) |
| SERIAL_SEG_09 | READY_TO_UPLOAD | [SERIAL_SEG_09.h3.txt](SERIAL_SEG_09.h3.txt) | [SERIAL_SEG_09.upload.md](SERIAL_SEG_09.upload.md) |
| SERIAL_SEG_10 | READY_TO_UPLOAD | [SERIAL_SEG_10.h3.txt](SERIAL_SEG_10.h3.txt) | [SERIAL_SEG_10.upload.md](SERIAL_SEG_10.upload.md) |
| SERIAL_SEG_11 | READY_TO_UPLOAD | [SERIAL_SEG_11.h3.txt](SERIAL_SEG_11.h3.txt) | [SERIAL_SEG_11.upload.md](SERIAL_SEG_11.upload.md) |
| SERIAL_SEG_12 | READY_TO_UPLOAD | [SERIAL_SEG_12.h3.txt](SERIAL_SEG_12.h3.txt) | [SERIAL_SEG_12.upload.md](SERIAL_SEG_12.upload.md) |

## 执行顺序与阻塞项

1. 待制作资产先按自己的上传卡上传实际参考图、提交完整资产提示词；生成后登记真实文件、版本、哈希并批准，再重新编译下游。已经批准且未变化的资产直接复用。
2. 打开每个 Segment 的上传卡，只上传该段表内的真实媒体，并在入口核对模式、时长和槽位编号。
3. 打开对应 H3 文件，复制完整正文提交；`CHAT_DELIVERY.md` 不替代 H3 正文文件。
4. 平台上传后另行保存入口回执；本地 `READY_TO_UPLOAD` 不等于平台已上传，`visual_status=UNVERIFIED` 不得升级。

当前阻塞：
- 资产 ART_KEYFRAME_01：先按独立上传卡补齐参考素材或正文合同；不可提交草案
- 资产 ART_KEYFRAME_05：先按独立上传卡补齐参考素材或正文合同；不可提交草案
- 资产 ART_KEYFRAME_09：先按独立上传卡补齐参考素材或正文合同；不可提交草案

自动文件模式：长 H3 正文留在独立文件；本页保留创作摘要、资产提示词、分段地图和每段上传助手，不能用总清单链接代替操作卡。

