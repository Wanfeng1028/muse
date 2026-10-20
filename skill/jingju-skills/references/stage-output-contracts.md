# 阶段输出模板

所有输出先给用户审阅。除非用户明确确认，不进入下一阶段。

## 1. 项目设定

```markdown
# 项目设定

项目名：
故事大体环境：
小说/漫剧类型：
目标剧型：
画风：
集数：
单集时长：
目标受众：
核心爽点：
情绪基调：

## 待确认
请确认以上项目设定是否通过。可选择：通过 / 修改 / 补充 / 重写。
```

## 2. 剧本大纲

```markdown
# 剧本大纲

## 一句话简介

## 背景设定 / 世界观

## 核心冲突

## 人物关系

| 角色 | 关系对象 | 关系 | 冲突/情感 |
|---|---|---|---|

## 三幕结构

### 第一幕：建立世界和冲突
### 第二幕：冲突升级和反转
### 第三幕：爆发、解决和钩子

## 分集大纲

| 集数 | 标题 | 核心事件 | 爽点 | 结尾钩子 |
|---|---|---|---|---|

## 角色出场时间线

## 待确认
这个大纲是否通过？是否需要调整人物关系、爽点、结尾钩子或分集节奏？
```

## 3. 角色卡

```markdown
# 角色卡：{character_name}

## 基础设定
- 角色ID：
- 姓名：
- 年龄：
- 身份：
- 性格：
- 人物弧光：
- 人物关系：

## 外貌设定
- 体型：
- 年龄感：
- 脸型：
- 五官：
- 发型/发色：
- 服饰：
- 服饰细节：
- 配饰：
- 绘画风格：
- 整体气质：

## 角色锁定词
固定描述：

禁止变化：
- 不改变脸型
- 不改变发型/发色
- 不改变服饰和服饰细节
- 不改变体型和年龄感
- 不改变绘画风格

## 角色参考图 image2 提示词
透明背景或纯白背景，干净统一底色，单人角色设定图，不拿道具，无复杂场景。
包含正面特写、正面全身、侧面、背面，多视角角色设定图。

Prompt:
```
{prompt}
```

Negative:
```
different face, different hairstyle, different outfit, props, handheld object, complex background, messy background, extra people
```

## 待确认
请确认角色设定和角色参考图提示词。确认后才可以生成或选择角色参考图。
```

## 4. 分集剧本

```markdown
# 第{episode_number}集：{episode_title}

## 本集目标

## 本集情绪曲线

## 本集爽点

## 本集结尾钩子

## 正文

### 场景 1：{scene_name}
- 地点：
- 时间：
- 氛围：
- 出场角色：

对白/旁白/动作：

## 待确认
请确认本集剧本是否通过。确认后才进入分镜设计。
```

## 5. 分镜脚本

```markdown
# 第{episode_number}集分镜脚本

| shot_id | 时长 | 场景 | 角色 | 剧情目的 | 景别 | 构图 | 动作/表情 | 气泡/字幕/旁白 | 情绪 | 转场 |
|---|---:|---|---|---|---|---|---|---|---|---|

## 动态漫附加项
- 分格布局：
- 气泡位置：
- 漫画特效：
- 拟声词：

## 待确认
请确认分镜数量、镜头顺序、构图和对白。确认后才生成图片提示词。
```

## 6. 图片提示词

```markdown
# 图片提示词：{shot_id}

## 引用资产
- character_id：
- scene_id：
- episode_id：

## 画面说明

## image2 提示词
```
{character_lock}, {scene_description}, {composition}, {emotion}, {action}, {art_style}, high quality illustration
```

## Stable Diffusion 正向
```
{positive_prompt}
```

## Stable Diffusion 负向
```
different face, different hairstyle, different outfit, bad anatomy, blurry, extra fingers, extra people, unwanted props
```

## ComfyUI 参数包
```json
{
  "asset_type": "storyboard_image",
  "episode_id": "{episode_id}",
  "shot_id": "{shot_id}",
  "workflow": "ipadapter_character_consistency",
  "character_id": "{character_id}",
  "scene_id": "{scene_id}",
  "positive_prompt": "{positive_prompt}",
  "negative_prompt": "{negative_prompt}",
  "reference_image": "{reference_image}",
  "seed": 123456,
  "denoise": 0.35,
  "width": 1024,
  "height": 1536
}
```

## 待确认
请确认图片提示词。生成图片后必须选择采用版本，未选择不得进入图生视频。
```

## 7. 图片版本确认

```markdown
# 图片版本确认：{asset_id}

| version | seed | workflow | 说明 | 状态 |
|---|---:|---|---|---|
| v1 |  |  |  | draft |
| v2 |  |  |  | draft |

可选操作：
- 采用这一张
- 重抽同提示词
- 保持构图，微调人物
- 保持人物，微调背景
- 改表情
- 改服饰细节
- 高清修复
- 放弃该版本

请使用 `/select {asset_id} {version}` 选择最终版本。
```

## 8. 图生视频提示词

```markdown
# 图生视频提示词：{shot_id}

## 前置确认
- 源图片版本：
- 源图片是否 selected：
- 图片是否 locked：

## 视频参数
- duration：
- source_image：
- pace：

## 提示词
```
保持原图角色脸部、发型、服饰、体型和画风完全一致。
角色动作：{motion_description}
表情变化：{expression_change}
镜头运动：{camera_movement}
环境动效：{environment_motion}
节奏：{pace}
不要新增人物，不要新增道具，不要改变场景主体。
```

## 负面提示词
```
changed face, changed hairstyle, changed outfit, new character, new props, changed scene, distorted body, flicker, unstable identity
```

## 待确认
请确认图生视频提示词。确认后，如果本地视频模型/API可用，才允许生成成品视频；否则只交付提示词。
```

## 9. 视频版本确认

```markdown
# 视频版本确认：{shot_id}

| version | source_image | prompt_status | 说明 | 状态 |
|---|---|---|---|---|
| v1 |  | approved |  | draft |

请确认采用哪个视频版本。未确认视频版本不得标记镜头完成。
```
