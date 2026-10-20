# 连续性与交接协议

## 1. 目的

把 BodySpec、CharacterBible、SceneBible、`expression_handoff` 和 ShotSpec 连接为可生成的连续镜头系统，防止每帧重新设计。本协议服务于资产（`assets.md`）、表演适配（`performance-adapter.md`）、关键帧（`frame.md`）与视频提示词（`prompt.md`）阶段的跨阶段交接。

## 2. 交接对象

### BodySpec → CharacterBible

只传递：

- age_presentation；
- archetype / blend；
- head_count；
- skeleton；
- volume_distribution；
- posture；
- function；
- camera cautions；
- anatomy negatives。

不得把体型模板中的通用服装或职业示例当作角色事实。

### CharacterBible → Scene / Shot

传递：

- canonical identity；
- apparent age；
- face、hair、eyes、skin、species traits；
- BodySpec 摘要；
- costume construction；
- weapon and harness；
- materials；
- unique marks；
- immutable list；
- allowed variations。

不传递资产图摄影棚背景、固定资产灯位、分割线或中性站姿。

### SceneBible → ShotSpec

传递：

- location、culture、era、function；
- spatial axis and map；
- landmark；
- foreground / midground / background；
- scale cues；
- time、weather、atmosphere；
- key-light family；
- palette；
- material state；
- fixed environmental anchors。

### VisualBible → 每个镜头

每帧必须读取并重复最少必要硬锚点：

- 角色身份；
- 服装和武器；
- 场景地标；
- 时间、天气；
- 主光方向与色温；
- 材质和画风；
- 当前损伤与道具状态。

### expression_handoff → ShotSpec

先按 `references/performance-adapter.md` 建立 EX→shot 映射，再传递：

- `expression_beat_ids` 与来源锚点；
- `state_in`、`displayed_state`；
- `leakage`、`control_action`、`residual`；
- `intensity`、`timing`、`visible_cues`、`visibility`；
- `exclusions` 与 `continuity_out`；
- `prompt_ready_zh` 作为下游动作底稿。

`internal_state` 只参与选择，不进入可见提示词。没有结构化表演输入时记录 `performance_input: screenplay_only`，不要伪造 EX ID。

## 3. 镜头状态机

为每帧记录：

```yaml
shot_id:
previous_shot:
next_shot:
character_state:
  position:
  facing:
  pose:
  expression_beat_ids: []
  performance:
    state_in:
    displayed_state:
    active_phase:
    visible_cues:
    residual:
    continuity_out:
  costume_damage:
  held_items:
  injuries:
environment_state:
  destruction:
  wetness:
  smoke:
  fire:
  crowd:
lighting_state:
  key_direction:
  key_elevation:
  dominant_bright_zone:
  practicals:
camera_state:
  position:
  angle:
  focal_length:
  focus_target:
change_from_previous:
locked_from_previous:
```

每个镜头必须使用全局唯一 `shot_id`。上一镜的 `performance.continuity_out` 成为下一镜默认 `state_in`；若下一镜有更新且明确的 EX 节拍，以新节拍为准，并把变化原因写入 `change_from_previous`。

## 4. 可变与不可变

### 不可变

- 脸、年龄、发型、物种；
- 身体基础比例；
- 服装版型、甲片和武器尺寸；
- 地标相对位置和场景文化；
- 时间窗口内的太阳或月亮方向；
- 画风抽象程度；
- 材质基础属性。

### 可变

- 表情、姿势、动作；
- 由 EX 节拍触发的视线、呼吸、声线、手势和距离；
- 镜头位置、焦段和景别；
- 合理的衣发动态；
- 逐步产生的破损、污渍和湿润；
- 烟、尘、雨、雪和火焰的局部形态；
- 剧情导致的建筑破坏。

任何变化必须写入 `change_from_previous`。

## 5. 光位连续性

同一时间和地点：

- 太阳、月亮或主要环境光方向保持固定；
- 摄影机换侧时，画面上的受光侧可能变化，但世界光向不变；
- 轮廓光、投影、材质高光和体积光必须由同一世界光向推导；
- 实景灯可进入或离开画面，但不能无理由改变全局色温；
- 魔法爆发可短暂成为主光，结束后恢复环境主光。

## 6. 180 度轴线

为人物关系和运动路线定义空间轴：

```yaml
axis:
  point_a:
  point_b:
  screen_direction:
  allowed_crossing_method:
```

默认不越轴。需要越轴时，通过以下方式之一完成：

- 摄影机运动明确跨轴；
- 中性正面镜头重置轴线；
- 遮挡转场；
- 高空或俯视建立新空间关系。

## 7. 角色运动连续性

记录：

- 起始位置；
- 路线；
- 速度；
- 朝向；
- 手中武器；
- 伤势；
- 衣服破损；
- 发尾、披风和尾巴的运动趋势。
- 表演残留：浅呼吸、泪痕、嘴角控制、视线对象、手指紧张和说话延迟。

下一帧不能瞬移、左右手交换、武器换边、损伤消失或无触发重置表演残留。

## 8. 场景地图最小表示

```yaml
scene_map:
  north_reference:
  main_landmark:
  entrances:
  exits:
  elevation_changes:
  path:
  cover:
  dangerous_zones:
  light_sources:
```

大场面至少锁定一个主地标、一个路线和一个高差。

## 9. 连续提示词写法

每个新镜头只重复：

1. 必须稳定的身份锚点；
2. 本场景主地标和世界光向；
3. 本镜头新增变化；
4. 镜头参数；
5. 当前动作和接触点；
6. 本镜头消费的 EX ID、可见相位与尾态；
7. 连续性负面约束。

不要把完整上一帧提示词机械复制，避免冲突和 token 浪费。

## 10. 连续性审计

每帧检查：

- 人物是否还是同一人；
- 左右方向和轴线是否成立；
- 武器、服装和损伤是否延续；
- 地标相对位置是否合理；
- 光向和天气是否延续；
- 动作是否能从上一帧到达；
- `expression_beat_ids` 是否可追溯，触发—泄露—控制—残留是否按时序发生；
- `continuity_out` 是否进入下一镜，微表情是否符合当前景别可见性；
- 新增破坏是否有因果；
- 镜头变化是否服务叙事。
