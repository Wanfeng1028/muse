# 表演适配器

当输入包含 `expression_handoff`、`EX-` 节拍、表情标注版剧本，或任务要求把表演编译进关键帧/Seedance 2.0 提示词时读取本文件。

## 目录

1. 职责边界
2. 输入校验
3. EX 到镜头绑定
4. ShotSpec 映射
5. 可见性裁决
6. 静态与动态编译
7. 容量与连续性
8. 输出与门禁

## 1. 职责边界

把 `$annotating-screenplay-expressions` 输出的模型无关表演事实转换为镜头可见、时序明确的下游数据。保留 `expression_handoff.version: "1.0"` 的因果、对象、顺序、强度、连续性和排除项；不要重新诊断人物或润色原剧本。

只让 `internal_state` 参与动作选择。不得把“他意识到真相”“她感到背叛”等心理说明直接写进图像或视频画面。`prompt_ready_zh` 是首选可见动作句，但仍需按镜头、时间和可见性裁剪，不得机械粘贴。

没有 `expression_handoff` 时允许继续普通制作，但必须标记 `performance_input: screenplay_only`；只使用剧本已有可见动作，不生成 `EX-` ID，也不得宣称经过表情专家处理。

## 2. 输入校验

进入绑定前检查：

- `version` 为可识别版本，当前消费 `1.0`；
- `source_locked: true`；
- 每个 beat 的 `id` 全局唯一且以 `EX-` 开头；
- `source_anchor`、`character`、`timing` 足以定位；
- `intensity` 为 0–5 或 `null`；
- `visible_cues`、`visibility`、`exclusions` 类型正确；
- `continuity_in` 与前场残留没有硬冲突。

字段缺失时保留 `null`，不要补写人物事实。版本不识别、ID 重复、来源未锁定时停止消费整个交接包；单个 beat 定位不足时只把该 ID 列入未绑定清单，不阻断其它合法节拍。

## 3. EX 到镜头绑定

先让 `storyboard.md` 为每个镜头建立全局唯一 `shot_id`，再按以下证据顺序绑定：

1. `source_anchor` 的集/场/对白或动作位置；
2. 同一镜头中明确出现的 `character` 与 `target`；
3. `timing` 所指的台词前、台词中、台词后、反应或转场；
4. 镜头绝对时间与相邻动作因果；
5. 已确认的人工映射。

不要仅凭相似情绪词模糊匹配。一个 EX 节拍可以跨多个连续镜头，但每个镜头只领取自己能表现的相位；例如 CU 领取眼睑泄露，后续 MS 领取压回姿态和浅呼吸残留。一个镜头可绑定多个 EX ID，但必须分别保持角色、触发和时序，不能合成“众人同时震惊”。

使用 `templates/expression-shot-map.yaml` 记录：EX ID、来源锚点、角色、`shot_id`、时间段、分配相位、可见性结论和拒绝原因。未绑定项目必须显式输出，不能静默丢失。

## 4. ShotSpec 映射

把交接字段写入 ShotSpec 的 12 项稳定接口：

| ShotSpec | expression_handoff 来源 |
|---|---|
| `expression_beat_ids` | `id` |
| `state_in` | `state_in`，必要时用 `continuity_in` 校验 |
| `displayed_state` | `displayed_state` |
| `leakage` | `leakage` |
| `control_action` | `control_action` |
| `residual` | `residual` |
| `intensity` | `intensity` |
| `timing` | `timing` |
| `visible_cues` | `visible_cues` 四通道 |
| `visibility` | `visibility` |
| `exclusions` | `exclusions` |
| `continuity_out` | `continuity_out` |

把 `version`、`source_anchor`、`prompt_ready_zh`、`confidence` 和关键帧 `selected_phase` 写入 `performance_provenance`。不要把 provenance 当作新增表演内容。

## 5. 可见性裁决

先判断镜头能否看见动作，再决定是否编译：

- ECU/CU：可承载眼睑、嘴角、视线焦点和细小呼吸；
- MCU/MS：优先视线、头颈、呼吸、手部和距离变化；
- FS/WS/EWS：只保留轮廓、重心、步态、手臂、人与人距离及大幅环境反应。

若 `visibility` 要求“中近景以上”而镜头为远景，依次尝试同一 beat 的 `body_hands`、呼吸/声线或站位残留。没有合法替代时标记 `visibility_conflict`，返回 storyboard 调整或把节拍移交相邻可见镜头；禁止静默改景别，也禁止在远景硬写眼睑和嘴角。

## 6. 静态与动态编译

### GPT Image 2 关键帧

每张静态关键帧只选择一个 `selected_phase`：

- `state_in`：触发前的可读准备态；
- `leakage`：瞬时泄露达到最清楚且结构稳定的一刻；
- `control_action`：人物主动掩饰或恢复的可见姿态；
- `residual`：节拍结束后仍需延续的呼吸、泪痕、手势或距离。

优先选择与该 ShotSpec 绝对时间一致、对叙事最有辨识度且适合静止的相位。不得把触发、泄露、控制和残留同时塞进一张图；`prompt_ready_zh` 跨越多个相位时，只截取当前相位所需的可见成分。

### Seedance 2.0 视频

按真实顺序编译：

```text
state_in -> trigger -> leakage -> control_action -> residual/continuity_out
```

把 `prompt_ready_zh` 拆入对应连续时间段，保留人物姓名、对象和先后关系。使用“半拍、随即、开口前、动作落定后”等相对时序；只有分镜已给出精确动作时间时才写数值。镜头时间不足时减少次要通道，不得把多个相位改成同一时刻的五官清单。

## 7. 容量与连续性

同一镜头容量优先级：剧情转折反应 > 改变关系/行动的表演 > 必须延续的残留 > 装饰性微动作。超出容量时把节拍移到相邻合法镜头或列为 `not_compiled_due_to_capacity`，不能删掉后假装完成。

每个镜头结束时把 `continuity_out`、可见残留、泪痕、呼吸、姿态、伤势、手中物和距离写入状态机。下一镜以此作为 `state_in`，但新的明确 EX 节拍拥有更高权威；状态变化必须有触发。

动作戏中表演仍服从受力和生理状态：受击后的呼吸、眩晕、疼痛控制、视线恢复必须承接动作结果，不能与发力链或伤势相冲突。

## 8. 输出与门禁

交付以下三项：

1. EX→shot 映射表；
2. 填充 12 项接口的 ShotSpec；
3. 未绑定、不可见、容量不足或字段冲突清单。

交付前检查：

- 每个已消费 EX ID 都能追溯到原文锚点；
- `internal_state` 没有冒充画面；
- `prompt_ready_zh` 已按相位和时间裁剪；
- 静态帧只有一个表演相位；
- 视频保持触发、泄露、控制、残留顺序；
- `visibility` 与景别相容；
- `exclusions` 已进入目标编译器；
- `continuity_out` 已交给下一镜状态机。
