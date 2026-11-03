# Seedance 2.0 视频提示词阶段

当分镜、资产、ShotSpec 和关键帧已确认，需要编译最终 Seedance 2.0 视频提示词执行包时读取本文件。本文件负责路由和装配；模型细节放在独立编译器中。

## 必读路由

- 始终读取 `references/00-visual-contract.md`、`references/40-continuity-and-handoff.md` 和 `references/seedance-2-prompt-compiler.md`。
- 输入包含 `expression_handoff`、`EX-` ID 或表演标注时，读取 `references/performance-adapter.md`。
- 片段包含打斗、追逐、坠落、复杂物体交互、体育/舞蹈或强环境运动时，读取 `references/action-choreography-compiler.md`。
- 最终执行包使用 `templates/seedance-2-prompt-package.md`。

## 目标

把一个已确认的连续生成片段编译成：

1. 生成元数据；
2. 参考素材职责表；
3. storyboard / ShotSpec / EX / 关键帧映射；
4. 首尾相连的动态时间线；
5. 台词、现场声和音乐策略；
6. 连续性、排除项与交付意图。

一次执行包只服务一个 `generation_clip_duration` 片段。作品可由任意数量片段组成，`production_total_duration` 不受单次生成长度限制。

## 生成门禁

编译前确认：

- `production_total_duration` 与上游确认剧本一致；
- 当前 Seedance 2.0 入口实际支持的 `generation_clip_duration`、比例、模式和参考素材类型；
- 本片段的绝对起止时间、相对时间、`shot_id` 列表和分镜原文；
- 每个 ShotSpec、关键帧 ID/路径和关键帧对应的绝对时间；
- 有表演输入时，`expression_handoff.version`、EX→shot 映射、未绑定 ID 和可见性冲突已处理；
- 台词、旁白、现场声、BGM 和字幕策略；
- 当前批次生成数量与宿主工具限制。

缺分镜时返回 storyboard；缺必要资产时返回 assets；缺必要关键帧时返回 frame。不要根据一张图自由脑补新剧情。

## 时长与装箱

- `production_total_duration`：只读上游值，不压缩、不默认、不按模型改写。
- `generation_clip_duration`：单次 Seedance 生成长度，由当前入口能力或用户确认决定。
- storyboard 先建立全局 `shot_id` 和绝对时间，再把连续镜头装入生成片段；改变装箱方式不得重编号镜头。
- 末段可短于标准切片；不能用无内容停顿强行补齐。
- 若一个片段需要超过 3 个强制关键帧或容纳过多独立 EX/动作状态，优先缩短片段，而不是把所有状态压进一条 Prompt。

## 参考素材

按当前宿主实际标签动态编号，例如 `@图片1`、`@视频1`、`@音频1`。逐项记录：

| 字段 | 内容 |
|---|---|
| 资源 | 关键帧/角色/道具/视频/音频的 ID 或路径 |
| 职责 | keyframe / identity / prop / motion / audio |
| 时间锚点 | 对应相对时间与 `shot_id` |
| 必须继承 | 身份、构图、状态、动作或声线中的具体项 |
| 不继承 | 版式、背景、临时表情、错误光色等 |

默认传入当前片段的必要关键帧。角色/道具资产只在关键帧不足以稳定身份或结构时追加；场景资产只有在空间无法由关键帧表达时追加。不要无差别传入全部资产。

关键帧的时间角色来自其实际镜头位置：0 秒可作为开场锚点，中段关键帧保持中段锚点，片段末端可作为收束锚点。不要把非 0 秒关键帧错误声明成首帧。

## 映射表

完整 Prompt 前先输出：

```markdown
| 相对时间 | 绝对时间 | shot_id | 关键帧 | expression_beat_ids | 分镜依据 | 编译状态 |
|---|---|---|---|---|---|---|
| 0.0s-2.5s | 00:00-00:02.5 | EP01-S01-SH001 | KF01 | [] | 推门进入 | compiled |
```

每个时间段必须能追溯到原分镜。EX ID 必须来自已确认映射；没有表演输入时使用 `[]`。

## 编译流程

### 1. 建立全局不变量

只写整段不变的固定画风 DNA、身份、服装、武器、场景地标、世界光向、轴线、损伤/道具状态和声音策略。不要在每个时间段重复。

### 2. 建立连续时间线

从 `0.0s` 连续覆盖到 `generation_clip_duration`。把分镜的绝对时间换算为片段内相对时间；普通叙事使用足够清楚的粒度，只有重要接触、泄露、冲击或台词锚点才细到 0.1 秒。

每段只写当前变化：起始状态 → 触发/意图 → 主体动作 → 对象/环境反馈 → 摄影与焦点 → 声音 → 尾态。相邻动作连续时可以合并，但不得删掉因果结果和下一段起始状态。

### 3. 编译表演

有 `expression_handoff` 时：

```text
state_in -> trigger -> leakage -> control_action -> residual -> continuity_out
```

- 使用 ShotSpec 的 12 项表演接口和 `performance_provenance.prompt_ready_zh`；
- 按 `timing`、`visibility` 和可用时长裁剪，不能原样堆叠；
- `internal_state` 不进入画面；
- `exclusions` 进入对应时间段或结尾约束；
- 静态关键帧只锚定 `selected_phase`，视频补齐前后相位的连续过渡；
- 未绑定、不可见或因容量未编译的 EX ID 必须列出，不能静默丢失。

没有结构化表演输入时标记 `performance_input: screenplay_only`，只扩写剧本已有可见动作。

### 4. 编译动作

普通动作写清身体/道具起点、路径、接触/反馈和尾态。复杂动作按 `action-choreography-compiler.md` 使用“一攻一应一果一续”，保留发力链、目标点、防守者起始状态、应对、空间交换、人物/环境结果和下一拍主动权。

运镜绑定一个动作或表演锚点；不要让主体高速动作与无关的环绕、甩镜、变焦同时竞争。摄影机换侧必须交代越轴方法。

### 5. 编译声音

- 台词写人物、对象、语气、时间和口型可见条件；
- 现场声写呼吸、脚步、衣料、道具、碰撞、环境底噪和混响；
- `soundtrack_policy: inherit` 服从上游；
- `no_bgm` 只在用户/上游明确要求时使用；
- `specified_music` 写清进入、退出和与台词/现场声的层级。

## 全局约束

在结尾合并并去重：

- 人脸、年龄、体型、发型、服装、武器和道具结构不漂移；
- 场景地标、轴线、世界光向、时间天气和损伤连续；
- 动作路径、手部、接触点、地面关系和物理反馈清楚；
- 关键帧在声明时间点被经过，但整段保持自然运动；
- 未要求时不生成字幕、文字、Logo、水印；
- 不出现无关角色、无因特效、无因环境破坏或互相冲突的镜头运动；
- 合并 ShotSpec 的 `exclusions`，不重复同义负面词。

## 交付意图

可以记录：

```yaml
delivery_intent:
  target_mastering_resolution: null
  target_delivery_fps: null
  postprocess_required: false
  model_guarantee: false
```

8K 与 120fps 若被用户要求，只是母版/后期目标，不得宣称 Seedance 2.0 原生保证。不要用这些质量词替代内容、动作和摄影描述。

## 输出格式

先交付可审核的执行包，再在用户确认并且工具可用时生成视频：

```markdown
### [项目/集/场/片段 ID] · [绝对时间]

#### Seedance 2.0 执行包
[生成元数据、素材职责、映射表、完整 Prompt、约束与交付意图]

#### 未编译事项
- 未绑定 EX ID：无 / [列表]
- 可见性冲突：无 / [列表]
- 缺失资产或锚点：无 / [列表]
```

视频生成后按主 Skill 的实际宿主交付规则展示结果。

## 质量门禁

- 总时长与单次生成时长分离且数值一致；
- 相对时间无空洞、重叠或超出片段；
- 每段可追溯到 `shot_id`、分镜、关键帧和可选 EX ID；
- `prompt_ready_zh`、`timing`、`visibility`、`exclusions` 和 `continuity_out` 被实际消费；
- 打戏存在发力/应对/结果/续接，文戏不存在夸张动作污染；
- 声音策略来自上游，不把无 BGM 设为通用默认；
- 固定画风、身份、空间、光向和材质合同保持不变；
- 最终执行包只面向 Seedance 2.0，没有其它模型或节点术语。
