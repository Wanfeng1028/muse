# H3 视频交付总览 · Acheng Director 生产台

## 总控台

项目：EXAMPLE_COMEDY_MISUNDERSTANDING
总时长：20 秒 · 24/1 fps
段落数量：2 · 模式：autonomous_file_batch
状态：机器检查不等于平台已上传或影像已生成；缺素材与合同缺项保持草案。

## 创作摘要

裴峻指着空伞钩质问陶林，红伞从梯后滚出；陶林指向伞再指天花板，试图保住无辜姿态。

## 资产目录与提示词

以下是可直接交给画布 Agent 的独立资产图提示词。提示词文件是生成指令，不是已经生成的图片；状态为 PLANNED 时仍需先补齐真实参考素材。

| 资产 | 状态 | 用途 | 参考依赖 | 提示词文件 |
|---|---|---|---|---|
| 红伞误会·工作坊 · v1.0 (`ASSET_COMEDY_UMBRELLA`) | PROMPT_READY | Create one opening keyframe before the exchange. | 无 | [asset_prompts/ASSET_COMEDY_UMBRELLA.image.txt](asset_prompts/ASSET_COMEDY_UMBRELLA.image.txt) |

### 可复制资产提示词

#### 红伞误会·工作坊 · v1.0 · PROMPT_READY

完整文件：[asset_prompts/ASSET_COMEDY_UMBRELLA.image.txt](asset_prompts/ASSET_COMEDY_UMBRELLA.image.txt)

独立上传卡：[ASSET_COMEDY_UMBRELLA.asset-upload.md](ASSET_COMEDY_UMBRELLA.asset-upload.md)

### 红伞误会·工作坊 · v1.0 · 资产图上传卡

状态：PROMPT_READY · NOT_UPLOADED · visual_status=UNVERIFIED

生成模式：GENERATE · 资产类型：未指定 · 状态版本：未指定 / 未指定

[完整提示词/草案](<asset_prompts/ASSET_COMEDY_UMBRELLA.image.txt>) · SHA-256：943450b7fa1c7e310debe1304b7e872de7f19a9b098c232de7ab43dfa4816ef6

本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。

本资产无需上传参考图；按完整正文制作，生成后仍需批准。

下一步：核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。


## 段落地图（分段地图）

| 段落 | 时间 | 时长 | H3模式 | 创作事件/意图 | 状态 |
|---|---|---:|---|---|---|
| COMEDY_SEG01 | 0.000s–10.000s | 10s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |
| COMEDY_SEG02 | 10.000s–20.000s | 10s | T2VA | 见完整 H3 正文 | READY_TO_UPLOAD |

## 每段上传参考助手

每张卡只覆盖一个 Segment；先看状态与实际文件，再按标签顺序上传。Subject 是内容对象，不是额外上传槽位。

### COMEDY_SEG01 · T2VA · 10 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](COMEDY_SEG01.h3.txt) · [独立上传卡](COMEDY_SEG01.upload.md)

绑定版本：`780800e92060768dc18dc288659aae737e5272ffa006ba2e000430f894390047` · 正文 SHA-256：`cadf5616f941a3f2c022db9cb6971db704d322f5ed69fd7068b487632fc6f44c`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

### COMEDY_SEG02 · T2VA · 10 秒

提交状态：READY_TO_UPLOAD · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED

[完整正文/草案](COMEDY_SEG02.h3.txt) · [独立上传卡](COMEDY_SEG02.upload.md)

绑定版本：`2341d1ce927d4821ac88439d32ab0a49284b20bca9d7a17804b1b8615d5851cc` · 正文 SHA-256：`85faa57da457fdfe3ec5adda3fc85648d6a25f35d4ab5cf1a948ec3937c61b07`

参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。


下一步：依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。
平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。

## H3 正文文件

每个文件都是独立请求；请复制对应文件的完整正文，不把本页说明、manifest 或上传卡混入模型输入。

| 段落 | 状态 | 完整 H3/草案 | 独立上传卡 |
|---|---|---|---|
| COMEDY_SEG01 | READY_TO_UPLOAD | [COMEDY_SEG01.h3.txt](COMEDY_SEG01.h3.txt) | [COMEDY_SEG01.upload.md](COMEDY_SEG01.upload.md) |
| COMEDY_SEG02 | READY_TO_UPLOAD | [COMEDY_SEG02.h3.txt](COMEDY_SEG02.h3.txt) | [COMEDY_SEG02.upload.md](COMEDY_SEG02.upload.md) |

## 执行顺序与阻塞项

1. 待制作资产先按自己的上传卡上传实际参考图、提交完整资产提示词；生成后登记真实文件、版本、哈希并批准，再重新编译下游。已经批准且未变化的资产直接复用。
2. 打开每个 Segment 的上传卡，只上传该段表内的真实媒体，并在入口核对模式、时长和槽位编号。
3. 打开对应 H3 文件，复制完整正文提交；`CHAT_DELIVERY.md` 不替代 H3 正文文件。
4. 平台上传后另行保存入口回执；本地 `READY_TO_UPLOAD` 不等于平台已上传，`visual_status=UNVERIFIED` 不得升级。

当前阻塞：无机器识别阻塞；仍需实际平台上传回执和生成后人工画面验收。

自动文件模式：长 H3 正文留在独立文件；本页保留创作摘要、资产提示词、分段地图和每段上传助手，不能用总清单链接代替操作卡。

