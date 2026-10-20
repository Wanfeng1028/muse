# 116｜从视觉资料到实际提示词

本库采用 Markdown 决策手册 + JSON 条目 + 原文出处 + 原有真实媒体库。手册负责什么时候看、如何取舍、写到哪里；JSON 是问题/视觉条目的唯一编辑源；按模块生成的 Markdown 是无脚本环境的可读视图。真实图片/视频继续负责视觉参考，不能由文字条目、器材名或条目 ID 替代。

## 首先只解决一个缺口

身份、剧情、ShotSpec 和批准 style_lock 优先。先问当前缺的是表面区分、光源依据、画面层级，还是尚未选定的整体媒介。风格已确认就补局部表达，不能因为查到漂亮条目而换画风。没有缺口时不查库、不答题。未确认新风格时，按原 STYLE MOTHER 流程提出少量可比较方案；库本身不新增审批。

弱模型可以按下面四步执行，不必理解全部摄影术语：

1. **点出对象**：哪一件已存在物品的哪一面看不清？先保留身份、形状、颜色和当前状态。
2. **选对媒介和尺度**：写实看光路/表面响应；赛璐璐看大色块/亮带；水墨看墨色/留白/边缘。先描述整形，再决定近处是否真的看得见织纹、毛孔或划痕。
3. **用现有光作区分**：光从哪里来？这片面相对旁边的面应该更柔、更窄、更哑，还是以边缘软硬区分？只选择当前可见的一项主要差异。
4. **写入并回读**：把“具体物件 + 已有光源/画法 + 可见响应 + 当前状态/尺度”写入原字段和完整自然语言正文。回读实际导出的 .image.txt / .h3.txt；只留下条目编号不算完成。

## 快速查找

在技能根目录运行，Python 3.10+，不联网、不调用生成模型、不修改 production：

    python scripts/director_library.py questions --module shots --case C5
    python scripts/director_library.py questions --question Q06
    python scripts/director_library.py visuals --medium live_action --surface dry_cloth
    python scripts/director_library.py visuals --medium ink --surface silk
    python scripts/director_library.py visuals --medium anime_3d --layer rendering
    python scripts/director_library.py visuals --medium live_action --search Cooke

默认一次返回两张卡，最多四张；不足以解决当前问题才读 remaining_ids。没有具体问题/媒介时只给目录，不倒入全库。搜索不到返回 NO_MATCH，不自动改用另一个媒介。器材、作者或工作室名只是来源检索别名；正式描述使用可见现象，品牌名称不代表任何渲染器已启用。

视觉层包括：optics 光学观感、finish 纹理/高光处理、diffusion 柔化、lighting_palette 光色组织、animation 动画表现、rendering 渲染观感、surface 材质。它们是可选候选，绝不要求每层选一条；多条查询结果是替代方案，不是自动叠加配方。相同 exclusive_group 提示需要取舍，跨组也仍需核对；它不是物理互斥定律。无缺口时保持已有方案。

无脚本能力时，读取本手册、当前 [模块指南](115-directed-decisions.md) 命中的问题节与 [视觉索引](../data/visual-style-materials.json) 的指定条目。只取当前条件下的 description、cel 或 ink，不把其他媒介适配句一并复制。

## 局部路由和原字段落点

| 缺口 | 先检查 | 原 owner 与字段 | 下游必须消费到哪里 |
|---|---|---|---|
| 人物皮肤、衣料像同一种塑料 | 真实材质、近景可见面、已存在光源 | assets：asset_cards 的七步第4/6步与完整 prompt；经批准的 character_registry.prompt_description | 独立角色图；后续关键帧适用描述和 H3 Subject/逐镜正文 |
| 场景或道具材质没有层级 | 主形/焦点/背景、已有光路和状态 | assets：asset_cards 与 scene_registry.prompt_description；场景支路仅提出建议 | 场景母图、适用视角、关键帧；shots.visual 写当前镜头真正可见的部分 |
| 单帧光泽或损坏与时间冲突 | 当前 Shot 的单一相位、干湿/破损版本 | assets：关键帧卡和 references；continuity 核对既有 ledger | 相应 reference_requirements → model.references/subjects/state范围，不能把尾态提前到首帧 |
| 每镜像换了媒介 | 批准 style_lock 和既有媒介 | model：segments.style；assets 守住锚点用途 | H3 style 与图像七步第2步；镜头只补当前可见事实 |
| 需要动画节拍、拖随或冲击强调 | 当前 motion_profile、效果family、冻结时序 | performance/effects 写各自原字段；model 用既有 motion_profile/animation_term_evidence | 走 [88条动画术语](113-animation-art-terminology-library-v4.3.md)，不另建第二份动画词库 |
| 缺的其实是具体参考图 | 素材是否已生成、批准、版本/哈希正确 | assets 提供素材；model 分配每段真实标签 | 走 [114绑定合同](114-reference-binding-delivery-v4.3.6.md)；资料库 ID 永远不是 Picture 或上传槽 |

七步表和完整 prompt 必须同步；风格行与逐镜正文也必须一致。本库没有新增 production 字段。采用结果写回原 owner；跨 owner 的建议先交主导演按原回包合同合并，不能让检索脚本直接写入生产文件。

## 不同媒介的同一材质

假设已登记的是丝绸，不能因查库把亚麻改成丝绸。光源、颜色与状态也必须从项目取值。

| 已有条件 | 可用的表达方向 | 不带入 |
|---|---|---|
| 写实丝绸、已有侧窗、近景 | 受光褶皱上的克制亮带随面转向，暗面保持既有底色 | 无依据的红变金、汗渍、新纹样 |
| 赛璐璐同一丝绸 | 顺褶皱的少量硬边亮带，与稳定主色相区别 | 全面PBR毛孔或照片噪点 |
| 水墨同一丝绸 | 连续柔滑墨面和顺褶皱的细长留白 | 摄影镜面贴图、强制胶片颗粒 |

这些是条件示例，不是项目事实；明暗方向、色彩、磨损和动作仍由批准输入决定。

## 接入流程和交付的位置

- **设计前**：只选择当前缺口对应的问题，排除已确认答案和不适用媒介。
- **提交 owner 回包前**：检查决定是否已写入它拥有的原字段；在既有 evidence 记录来源条目、采用结果、必要取舍和字段位置即可。不要另存完整答题过程。
- **编译前**：检查库里的字眼有没有偷偷增加物件、灯、风雨、伤势、能力或身份纹样；冲突回原 owner，不能由格式器删掉有效正文。
- **实际文件交付前**：回读物件/材质/光源/时态是否完整、资产与 H3 引用是否同源；机器门仍按原规则检查时间、模式、标签、哈希与缺项。语义观察标成观察，结构 PASS 只引用脚本回执。

检索结果不宣称材质已经被生成，不宣称百分之百保真，不降低原详细度下限。没有真实生成图、视频或音频时，相应视觉/听觉质量继续 UNVERIFIED。

## 原文裁决和维护

[提问索引](../data/director-inquiries.json)保存全部 Q01–Q36 的触发、输入、局部问题、条件分支、原 owner、完成条件和弃用规则；[视觉索引](../data/visual-style-materials.json)保存31个中性视觉条目，其中7个材质条目提供写实、赛璐璐、水墨适配。原始长文完整留在 sources，只作可追溯出处，不能重新执行其强制 scratchpad、固定帧数或品牌模板。

修改问题 JSON 后运行：

    python scripts/director_library.py render-guides
    python scripts/director_library.py validate

生成的七份问题视图不手工维护第二套正文。包验收检查其与 JSON 一致、原文哈希、原 owner 落点、模块路由和88术语引用；这属于工程检查，不是对审美的自动打分。完整纳入/拒绝说明见 [4.3.8优化说明](../UPGRADE-4.3.8.md)。
