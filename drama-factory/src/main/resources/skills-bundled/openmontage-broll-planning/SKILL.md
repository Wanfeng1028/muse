---
name: openmontage-broll-planning
version: "1.0.0"
description: 从脚本中梳理B-roll需求、判断实拍素材与AI生成的取舍、构造检索关键词并评估素材质量，适用于为视频规划补充镜头的场景。
metadata:
  license: AGPL-3.0
---

# B-roll 素材规划

为视频规划辅助画面（B-roll）时，先确定每段内容需要什么视觉，再决定用素材库还是 AI 生成，最后按统一标准筛选。

## 何时使用

- 视频已有旁白脚本，需要补充画面来铺陈背景、提供语境或增加视觉变化。
- 不确定某段场景该用素材库还是 AI 生成。
- 需要一套可复用的检索、评估、降级流程。

## 实拍素材 vs AI 生成：取舍表

| 场景需求 | 优先素材库 | 优先生成 |
|---------|-----------|---------|
| 真实世界的环境镜头（城市、办公室、自然） | 是，素材库最擅长 | 仅在找不到合适素材时 |
| 真人置于真实场景 | 是，生成人物容易失真 | 仅在高质量模型下考虑 |
| 抽象概念可视化 | 否 | 是，AI 可创造不存在之物 |
| 自定义图表/信息图 | 否 | 是，用 `diagram_gen` 或 `image_selector` |
| 品牌化/风格化图像 | 否 | 是，AI 可对齐 playbook 风格 |
| 历史/档案影像 | 是，素材库有档案资源 | 否 |
| 具体技术设备 | 是，真实照片更可信 | 仅在设备不存在时 |
| 运动/动作片段（海浪、车流、云） | 是，素材库视频很合适 | AI 视频正在追赶 |
| 隐喻性画面（成长、连接） | 两者皆可 | 是，创作控制力更强 |

**判断准则：** 需要“看起来真实”就用素材库；需要“贴合你的概念”就生成。

## 从脚本提取 B-roll 需求

逐段过脚本，每段回答以下问题：

1. 旁白在讲什么？主题暗示了画面。
2. 是否有增强标记？脚本作者可能埋了 `[B-ROLL: ...]` 提示。
3. 是否提到具体事物？例如“数据中心的服务器”对应服务器素材。
4. 是否在解释抽象概念？例如“算法权衡各因素”对应生成图表。
5. 这段多长？决定所需片段时长。

### 产出：B-roll 简报

每条需求记录如下字段：

```
Scene: s3 (15s-22s)
Need: 现代数据中心的环境镜头
Source: stock
Keywords: ["data center", "server room", "rack servers blue light"]
Duration: 4-6 秒
Orientation: landscape
Mood: 冷调、科技感、干净
Fallback: AI 生成服务器机架图像
```

## 构造有效的素材检索词

### 检索词构造规则

1. 具体但不过度具体。“aerial city skyline sunset”可行；“drone shot above the financial district towers at exactly 6:47pm, golden backlight”这种精确到分钟的长句几乎无结果。
2. 用 2-4 个关键词。素材检索基于关键词而非语义，词越多结果越少。
3. 主语放前面。“ocean waves”优于“beautiful calm serene ocean waves at dawn”。
4. 带上所需视觉特征：
   - 俯拍加 “aerial” 或 “drone”
   - 细节加 “close-up” 或 “macro”
   - 延时加 “timelapse”
   - 慢动作加 “slow motion”
5. 失败时换同义词。如“programmer coding”效果差，试 “developer laptop” 或 “software engineer workspace”。

### 按场景类型的检索模板

每条检索都加一个 **POV 关键词**。素材库（Pexels、Pixabay、Storyblocks、Artgrid）会索引 POV 术语——drone、aerial、OTS（过肩）、macro、top-down、dashcam、FPV、handheld、locked-off——加上 POV 往往比反复调整主语更容易命中。CMU/Harvard CHAI 分类法同样把 POV 视为一级场景维度，因为它决定了你检索的是哪个货架。

| 场景类型 | 模板 | 带 POV 的示例 |
|---------|------|--------------|
| 环境镜头 | `[地点] [时段] [POV]` | "tokyo skyline night drone" |
| 活动 | `[人物] [动作] [POV]` | "scientist microscope OTS" |
| 物体 | `[物体] [风格] [POV]` | "circuit board macro top-down" |
| 自然 | `[元素] [质感] [POV]` | "ocean waves aerial drone" |
| 抽象运动 | `[运动] [风格] [POV]` | "light trails timelapse locked-off" |
| 职场 | `[环境] [活动] [POV]` | "modern office meeting handheld" |

若场景描述本身没暗示 POV，应向脚本/场景导演确认，不要默认“无 POV”。POV 错误的素材（需要航拍却拿到手持）比调色错误更难补救。

## 评估素材库片段质量

拿到结果后逐条评估再使用。

### 图像标准
- 分辨率：达到目标（视频帧至少 1080p）。
- 相关性：画面确实对应场景需求，而非仅关键词命中。
- 风格兼容：与 playbook 视觉风格不冲突。
- 无水印：Pexels/Pixabay 免授权，但仍需核实。
- 构图：主体取景合理，未被尴尬裁切。
- POV 匹配：素材实际 POV 是否符合场景需求？POV 错误比调色错误代价更高，直接弃用重检，不要靠裁切硬救。

### 视频标准（包含以上图像标准）
- 时长：至少满足场景所需（可裁短，不能拉长）。
- 运动：平稳，无突兀镜头运动（除非刻意为之）。
- 帧率：匹配目标输出（24/30fps 为常见值）。
- 音频：素材库视频音频通常丢弃，不纳入考量。

### 评分启发式

每条结果 1-5 分：
- 5：完全匹配，直接用。
- 4：匹配良好，需轻微裁切或修剪。
- 3：可接受，建议调色以贴合 playbook。
- 2：勉强，先换关键词试试。
- 1：错误，完全不匹配场景。

**阈值：** 使用 3 分及以上的结果。低于 3 分则调整检索词或改用生成。

## 失败降级链

素材检索失败（无结果或全部低于 3 分）时依次尝试：

1. 换关键词——同义词、更宽泛的词、不同角度。
2. 换素材平台——Pexels 与 Pixabay 库不同。
3. 切 AI 生成——用 `flux_image` 或 `openai_image` 配合场景描述。
4. 上报用户——“[场景] 未找到合适素材，以下是最优选项：[展示结果]。或我可以用生成图像替代。你倾向哪种？”

仅当素材检索与生成两条路都会产生次优结果时才询问用户。多数情况下降级链可静默处理。

## 归属信息记录

Pexels 与 Pixabay 均可商用且无需强制署名，但最佳实践是在素材清单中记录来源：

```json
{
  "id": "broll-scene-3",
  "type": "image",
  "source_tool": "pexels_image",
  "provider": "pexels",
  "attribution": {
    "photographer": "Joey Farina",
    "source_url": "https://www.pexels.com/photo/...",
    "license": "Pexels License"
  }
}
```

这些字段在工具响应中可得（`photographer`、`pexels_url` / `page_url`），纳入素材清单以保持透明。
