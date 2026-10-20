# 90｜统一生产数据与 A/B/C 总线

## 版本与基本类型

生产文件使用 UTF-8 JSON 或 YAML，`version:"2.0"`。秒数可用整数、十进制或有理数字符串，所有时间运算由 Fraction 完成；帧号为整数，不接受 bool、NaN 或重复 JSON/YAML key。区间左闭右开。路径相对 production 文件目录，不相对当前 shell 工作目录。主样例 JSON 是完整、无空槽的参考实例。

根字段：project_id；fps_num/fps_den；production_total_duration；generation_clip_limit；scene_registry；character_registry；shots；segments；ledger。可选 brief、story、asset_cards、unresolved_threads、dispatch_log、base_revision 保存叙事和溯源，不能替代必需字段。

v3技能继续兼容version:"2.0"的镜头存储格式。generation_clip_min默认4，上限不大于15。delivery_scope为prompt_only或full_production；完整生产必须使用story.contract_version:"3.0"、script_scenes、asset_plan和逐镜story_beat_ids/required_assets。局部任务不要求编造上游故事，但不能报告全故事通过。

新合同分别见[11叙事](11-story-architecture.md)、[31表演](31-performance-handoff.md)、[32灵动表演](32-liveliness-performance-framework.md)、[46条件特效](46-effect-families.md)、[61资产依赖](61-asset-dependency-production.md)、[91专业模块](91-module-orchestration.md)。旧A/B/C支路契约继续解释已有资产来源与窄操作，七模块登记负责新的阶段分工；两者不重复赋予同一字段多个最终写入者。

## 场景与角色登记

scene_registry 每项至少 id/name，生产使用时同时写 space、entrances、exits、landmarks、key_light、version。character_registry 每项 id/name/height_m/identity；height_m 是设计值或测量值须在旁注区分，百米以上自动触发尺度审查。角色 ID 和场景 ID 互不复用；道具 ownership 只指向登记对象。

## ShotSpec v2

v2.1交付检查继续读取version:"2.0"数据，但收紧可独立提交条件：角色和场景每项必须新增完整英文`prompt_description`，每镜新增`state_description`描述开场道具／伤势／空间状态。旧数据缺项会报告G8失败；主导演依真值源补全，不从检索ID猜测。可选根字段`prompt_bindings`为显式`{{KEY}}`提供文字展开；字典不是模型输入。详见[交付合同](72-standalone-prompt-delivery.md)。

| 字段 | 合同 |
|---|---|
| id / scene_id | 稳定且已登记的身份 |
| start_frame / end_frame | 全局整数帧，前一镜尾=后一镜头 |
| visual | 英文可见画面、当前场所、身份和动作初态 |
| features | core_emotion/combat/supernatural_vfx/colossal 四个显式布尔值；不能通过关 flag 躲审查 |
| characters | 画内角色数组，每项 id、position[x,y]、facing、gaze、weapon_hand、weapon_direction |
| camera | previs_id 三位字符串，description、movement、path、target、adaptation、sensor_basis、lens_mm、shutter_angle |
| performance | 旧完整五轨或strategy:selective轨道；也可用source_beat_id/source_anchor/events消费完整表演交接；需要灵动/夸张/动作化表演时增加acting_design与段级motion_profile；详见31/32 |
| combat | 战斗时七层 force_source/trajectory/contact/resistance/impact_hold/transfer/recoil，加 chain.attack/response/result/continuation |
| vfx | energy_fluid使用主干/三通道/四相位；其他family使用origin/scope/process/end_state/lighting/continuity/events |
| scale_proofs | 巨构时至少两类证据，每项 type/detail/frame_location/depth_relation |
| dialogues | 无台词用空数组；有则 speaker_id/speaker_name/delivery/language/text/start/end/voiceover |
| audio | foley 数组、low_frequency_hz；有低频写 source/classification，无则 no_low_frequency_reason |
| outcome_events | 本镜造成的账本事件 ID，未变化为空数组 |
| state_in/state_out | 对应初始／事件重放的完整状态快照 |

表演、VFX、对白局部帧相对当前 Shot 开始。相机路径与人物位置是计划目标，不声称来自源片精确测量。提示词 visual 和 cues 用英语，台词保留用户原文；内部中文分析不得混入最终 H3 正文。

## Segment

4.3.6 兼容扩展见[114 绑定合同](114-reference-binding-delivery-v4.3.6.md)：shots.reference_requirements 属 shots；Segment references/subjects 仍属 model，允许 planned 与真实绑定分阶段，新增 asset_id/asset_version/entity_id、shot_ids、preserve/exclude、可选帧窗和 state_guards。正式绑定从 asset_plan 批准版本解析，外部媒体要求哈希与批准证据。派生 manifest 不能成为第二生产真值。

id 为安全文件名；start_frame/end_frame；shot_ids 严格按时间顺序、无重复、无漏镜；generation_clip_duration 与帧区间一致；mode 五选一；`mode_lock`、`mode_selection_reason`、`prompt_detail_policy`；style、overall_soundscape、non_diegetic_music；references 数组；Ref2VA 还需 summary。新 Ref2VA 任务的 `detailed_description` 按时长与复杂度动态计算最低词数（默认 10 秒段为 2,000）和目标词数（默认约 2,400） 个英文词，极限值 2900 词硬性封顶（处于 2200-2900 词区间，剔除无上限输出）；历史夹具必须显式声明 `prompt_detail_policy.profile:"legacy_fixture"`。

每个参考项 label/file/role。Ref2VA 项增加 definition/retention；后两者必须使用同一标签，标签在全段唯一。首尾帧模式 Picture 标签按指南固定。panels 仅在接触表参考时出现，完整1–16编号，每项 panel/shot_id/frame/phase/description。格号按阅读顺序，frame 不得逆序或落到所属镜头外。

Ref2VA可另有`subjects`数组，每项label/definition/retention，label为`<Subject N>`，definition必须引用真实素材的Picture/Video等标签。Subject表示可复用内容，不额外上传一张名叫Subject的图片。若Picture/Video只给Subject提供来源，references项可设source_only:true，仍保留真实file/role，但不重复生成独立definition/retention；必须被Subject定义实际引用。

实际首尾帧应在 shot.visual 中写初始锚定与最终收敛路径，不能仅靠首行声明。工具负责语法和结构检查，人负责看图核对角色与路径。

## 账本事件

initial/final 都包含 characters{id:{ammo,trauma_phase}}、scenes{id:damage_level}、props{prop_id:owner_id}。完整制作可给每个角色另附 wounds 明细，trauma_phase 作为本切片主要功能限制的汇总；多伤不能被汇总字段清除。

events 每项 id/frame/shot_id/domain/target/before/after/reason。domain 为 ammo/trauma/damage/prop；ammo 必须含 delta，增加时附 action:reload/resupply 与 resource_source；trauma 向稳定或恢复推进时附 action:treat/recover 与 story_time_evidence；damage 降级必须 action:repair。事件顺序按 frame 稳定排序，同帧多个事件按数组顺序重放。

## A/B/C 标准消息外壳

所有支路请求都用以下字段：contract、version、request_id、caller、target、input_revision、scope、allowed_write_paths、payload。回包用同 request_id、input_revision、status、patch、evidence、unresolved。总导演拒绝版本不符、作用域之外字段、未知 shot_id 或无法复核的“已验证”。每个请求最多一次生成及一次有明确失败原因的修正；还有冲突时交回主导演，不让两个支路互相调用形成循环。

契约 A target=cinematic-vfx-prompt-engine，只返回 vfx 表现槽。OPTIMIZE 冻结 origin、collision_type、collision 和 phases，防止在槽内偷改接触结果或时间。

契约 B target=h3-prompt-writing，只返回 selected_mode、alignment_line、ordered_sections、reference_map、execution_gate；不改剧情和总时长。当前脚本是该已读指南的确定性文本编译实现，不是远程 Skill RPC。

契约 C target=im2-clean-image，仓库别名 im2-image-skills。返回 image_transaction、seven_steps、recipe、structure_lock、prompt、avoid、actual_generation_settings、acceptance。未生成时 actual_generation_settings 为计划或 null，acceptance.visual=unverified。

可运行资产卡使用`asset_cards`数组：id、target_skill、source_repository、recipe、mode、transaction、seven_steps、prompt、reference_policy、references、generation_status、actual_settings；重场景另有structure_lock。reference_policy为none/required，references每项为image/file/role/subject/preserve/exclude。`prompt`是完整可提交正文，不能省略；可选prompt_bindings只用于导出前显式展开。compile_assets与post_hooks共用相同规则。早期资产模板是[asset-stage.json](../templates/asset-stage.json)，含完整实例。

## 确定性钩子与失效传播

script 后运行 `post_hooks.py script` 检查 scene_id 与正文表头；assets 后运行 `post_hooks.py assets` 检查七步、事务、参考和结构锁。这两个钩子不要求虚构下游镜头。其他模块在完整工作生产包上运行 audit：storyboard 对应G1/G2；performance 对应G4；action 对应G5；vfx 对应G6与冻结差异；compiler 对应G8/G9；continuity 对应G10。尚未产出的下游字段会报告未就绪，不能称整个包通过。最终统一跑十项。场景地图改动使该场相机、资产和关键帧失效；台词改变只使相关表演、声音和编译失效；vfx材质改变不触发剧本重写。

核验报告应区分描述存在与生成画面实测。禁止把上游文件里“通过”字符串当验收证据。机器分数必须来自当前 production 内容 SHA，与实际交付版本一致。
