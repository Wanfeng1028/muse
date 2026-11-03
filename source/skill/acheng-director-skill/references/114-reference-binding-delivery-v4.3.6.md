# 114｜逐段参考绑定与联合交付

本合同是引用链的唯一新增合同；不替代 H3 指南、创作、资产链或编排器。优先级：用户确认事实 → 字段 owner 的生产真值 → 本合同的绑定与交付状态 → 73/109 的展示载体。加载专业 skill 是读取并执行其合同，不等于启动子代理或调用生成模型。

## 一个真值，两类身份，三个状态

`production.json` 仍是唯一生产真值。复用 `asset_plan`、`asset_cards`、`segments[].references/subjects`；导出的 binding_snapshot 只是带 production revision 的不可变派生快照，不允许反向修改。

- 稳定身份：asset_id / entity_id / asset_version，跨 Segment 可追踪。
- 请求局部标签：Picture/Video/Audio/Subject 和 speaker `(Sx)`。每段独立编号；Subject 不是上传槽位。一个来源可定义多个 Subject，同一 Subject 可来自多个来源。
- PLANNED：只有提示词、没有真实媒体，或版本/批准/用途未完成。拟定标签可以保存在草案和计划中，不是正式引用证明。
- BOUND_LOCAL：实际文件、媒体类型、基础签名、哈希和指定版本一致；生产任务还需要内容批准证据。仅机器读字节不等于看过图/视频或听过音频。
- NOT_UPLOADED：所有本地导出默认如此。平台已上传只能来自另附的入口回执，包含 platform/request_id/confirmed_by、段号、正文与绑定哈希、实际槽位和媒体哈希，以及证据文件的哈希。回执校验只证明记录自洽，不冒充实时登录验证。

正式本地交付状态是 READY_TO_UPLOAD，不叫“平台可直接提交”。缺失输入使用 DRAFT_MISSING_REFERENCES，其他合同失败使用 DRAFT_CONTRACT_FAILED；`accepted=false`，不得出现正式 format PASS。合法且显式选择的 T2VA 才可写无需上传；I2VA/FL2VA/L2VA 同样不能把缺帧当作免参考。

## 前置需求与权属

shots 在 `shots[].reference_requirements` 登记本镜确需引用的 asset_id、asset_version、entity_id、purpose。不是把 required_assets 的每项一律上传：制作所需资产不全等于本段输入。主导演创建对象与批准语义；assets 负责 asset_plan 的真实文件/版本/状态；model 独占 Segment references/subjects；continuity 核对时序、版本和状态污染。

每条 Segment reference 至少提供 label、asset_id/asset_version 或外部 file、role、preserve、exclude、shot_ids。按需要提供全局 start_frame/end_frame、entity_id、state_label、state_guards。独立帧图明确首帧/尾帧/中间关键帧/构图用途；STYLE_MOTHER 不强制成为每段直接输入。同一素材兼作开场帧与后续身份来源时，shot_ids 表示来源可用范围，anchor_shot_ids 限定帧构图约束生效的镜头；后续身份继承由 Subject 表述，不把开场姿态重新施加到每镜。

```json
{
  "label": "<Picture 1>",
  "asset_id": "IDENTITY_APPROVED",
  "asset_version": "v1",
  "source_only": true,
  "role": "character identity",
  "preserve": "the approved face, hair and costume",
  "exclude": "source pose, lighting, background and later damage",
  "shot_ids": ["SHOT_001"]
}
```

asset_plan 已有 approved/file/sha256/version 时不重复维护另一份文件真值。外部独立素材需 file、asset_version、sha256 和 `approval:{status:"approved",sha256:"...",evidence:"批准来源说明"}`；缺证据保持待核验。历史 `legacy_fixture` 仅保留冻结演示数据的兼容性，不允许新项目借它绕过批准或密度门。

Subject 提供 label、entity_id、definition、retention、shot_ids；definition 引用已登记媒体；跨字段和镜头意义不变。source_only 的 Picture 只出现在 Subject 来源中，不机械补独立 definition/retention。实际正文必须完整描述外观、空间、朝向、动作因果、微表演、声音和尾态；标签不取代描述。机器检查结构化身份冲突、范围和哈希；任意自然语言的对象漂移仍要由主导演脱离上下文核读。

`state_guards` 是对已存在账本状态的只读断言，例如 `{"domain":"scenes","target":"SCENE_A","equals":0}` 或 `{"domain":"characters","target":"CHAR_A","field":"trauma_phase","equals":null}`。需要中途状态参考时限定帧窗，不能让未来破坏在开场无条件继承。空间、材质和画面内容没有真实视觉证据时保持未核验。

## 同源编译与交付

1. resolve_bindings 从上述字段生成一次快照；缺引用仍保留需求、资产版本、用途和缺项。H3-only 只报告缺依赖，不开启资产生成或 STYLE_MOTHER。
2. compile_h3 用该快照的同一组 references/subjects 写正文、检查合同、index 和独立 `SEG.upload.md`。引用仅在指定 Shot/帧窗生效；不把所有标签塞到每镜。
3. 每份正式 H3 附 `.check.json`、`.acceptance.json`、`.delivery.json` 和上传卡。草案为 `.h3.draft.txt`，保留完整创作内容与拟定映射，明确不能提交；不能靠改扩展名取得通过。
4. h3_delivery 联合回读：生产 revision、媒体字节/哈希、正文、卡片、manifest、总上传视图与聊天视图一致。正文或卡片改动后旧回执失效；新目录重编。
5. 新版 model 节点 complete 提交必须通过联合门；提交器连同素材与 sidecar 保存独立 bundle。partial 仍走原游标机制，不伪装 accepted。最终人工影像/听音验收独立，visual_status 不提升。

```bash
python scripts/compile_h3.py production.json --out output/revision-01
python scripts/compile_h3.py production.json --draft --out output/draft-01
python scripts/compile_h3.py production.json --execution-mode interactive_segment --segment SEG_01 --out output/segment-01
python scripts/h3_delivery.py output/revision-01 --production production.json
python scripts/h3_delivery.py output/revision-01 --upload-receipt platform-upload.json
```

CLI 返回码：0=本地正式包通过；2=草案已保存但不可提交；1=执行/合同失败。不将 2 当成功提交。

## 4.3.7｜附带资产提示词也必须带真实输入映射

资产生成请求与 H3 视频请求使用独立的编号域。compile_assets 和 compile_h3 附带资产分支共用 asset_delivery：逐项复制真实参考图片，验证文件类型／基础签名／已有批准哈希，保留 image 编号、来源路径、版本、role、subject、preserve 与 exclude。资产所需的参考尚未就绪时，提示词状态为 PLANNED／draft-missing-references，缺失项列在 missing_reference_details；不能只留 reference_count。PROMPT_READY 只表示生成指令及其输入已就绪，不表示资产已生成。

新导出包标记 asset_reference_contract=1.0。每项资产附 prompt_sha256、resolved_card_sha256、input_revision、上传卡及其哈希；导出后从文件回读核对，不由模型手写 PASS。H3 包的 ASSET_ID.asset-upload.md 是制作该资产的输入卡，SEG.upload.md 才是该视频段的输入卡。二者可以共享同一媒体副本，但不能混用槽位。身份图、风格图、关键帧和实际生成视频仍按批准用途分别消费。

独立资产包可用 asset_delivery.py PACKAGE --production production.json 回读；H3 包由 h3_delivery.py 联合核验并单列 asset_prompt_delivery 状态。附带草案不自动阻塞已经使用批准媒体的 H3 段，但该草案本身绝不可提交。当前包的八个演示会重新编译并检查新契约；旧交付包维持历史兼容，不自动获得新的资产引用验收。

## 展示优先级

自动文件模式：聊天直接呈现 `CHAT_DELIVERY.md` 的逐段简洁操作卡，保留真实素材链接、用途、版本、对象、范围、保留/排除、缺项与下一步；长正文留独立文件，不重复贴全文。总 UPLOAD 链接只能辅助，不能替代逐段卡。

交互模式：只展示当前一个 Segment 的卡和完整正文；未完成时保留 partial 游标，下轮继续当前段。首次 1/2 选择题保留，推荐 1 不等于未答即自动生产。制作模式选择不适用于开发这个 skill 本身。

相邻自检不是平行写真值：shots↔assets 核对对象/状态需求，assets↔model 核对版本/来源，model↔continuity 核对范围/尾态，主导演最终接受。反馈给出字段、证据、影响与修复 owner；不得扩成所有模块互相无限审阅。

## 4.3.8｜源卡到最终正文的再核对

带 production 参数的联合验收会从当前源卡及同一绑定重新编译正式正文并逐字比较。只重写正文、重算哈希、同步上传卡，仍不能伪造“引用已经进入正文”。不带 production 的检查只证明包内自洽；最终工程验收必须提供生产源文件。

资产附带导出也执行原七步/事务/路由/覆盖合同。正文合同失败则保留完整草案、render_error 和不可提交状态，不能因媒体槽位齐全就叫 PROMPT_READY。H3已经使用批准媒体时，附带资产草案仍单列，不把两种任务的完成状态混为一谈。

视觉 Subject 只能从 Picture/Video 定义，Audio负责声音；音色引用通过真实发声者和对应 Audio 定义/保留关系绑定，不能用声音文件证明脸部身份。引用已批准资产时，重复填写的哈希、状态版本、实体集合必须与该资产一致。图片、视频、音频的分类标签分别编号，上传顺序由本段操作卡明确列出，不能把总上传序号当成分类编号。

媒体校验范围是扩展类型、基础容器签名、非空和SHA-256；WAVE与AVI的RIFF子类型不能混用。它不是完整解码器，也不证明MP4一定包含所需轨道、音频时长适配、视频画面内容正确。真实入口的轨道、时长、数量限制和生成后视听表现仍需媒体检查/平台能力确认。

编译器同时消费原有sensor_basis、shutter_angle、人物位置/朝向/视线/持物、表演可见性与承接、VFX来源、尺度证据位置、声源与低频值，以及账本事件/道具持有人。屏幕归一化坐标以左→右、上→下解释；道具ID在生产源的 prompt_bindings 中提供明确可读名称，不猜译内部ID。账本摘要不替代逐镜动作与尾态正文。
