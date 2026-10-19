---
name: openmontage-image-provider-usage
version: "1.0.0"
description: 图像生成与图库提供商的选择与使用指南，涵盖各提供商特性对比、按场景类型的路由策略、成本分级方案及混合来源一致性处理，适用于需要为视频项目选择最优图像来源的场景。
metadata:
  license: AGPL-3.0
---

# 图像提供商使用指南

> 如何在图像生成和图库提供商之间选择，以及如何高效使用每一个。补充 `image-gen-usage.md`（深入覆盖 FLUX 提示词）。

## 提供商全景

### 生成提供商（AI 创建图像）

| 工具 | 提供商 | 费用 | 速度 | 最适合 |
|------|--------|------|------|--------|
| `flux_image` | FLUX 2 Pro via fal.ai | ~$0.03-0.05 | ~5-10s | 照片写实、通用、主力工具 |
| `grok_image` | Grok Imagine Image (xAI) | $0.02/输出 + $0.002/输入编辑图 | ~5-15s | 图像编辑、风格迁移、多图合成 |
| `openai_image` | GPT Image 2 (OpenAI) | ~$0.01-0.21 | ~5-15s | 复杂指令、图中文字、多元素 |
| `recraft_image` | Recraft V4 via fal.ai | ~$0.04-0.25 | ~5-10s | Logo、SVG 矢量、品牌资产、文字渲染（见下方注意事项） |
| `local_diffusion` | Stable Diffusion（本地） | 免费 | ~30s+ | 离线、隐私、免费 |
| `image_gen` | 多提供商（旧版，已弃用） | 不定 | 不定 | **已弃用**——请使用 `image_selector` 或各提供商工具 |

### 图库提供商（搜索并下载现有图像）

| 工具 | 提供商 | 费用 | 速度 | 最适合 |
|------|--------|------|------|--------|
| `pexels_image` | Pexels | 免费 | ~2-5s | 高质量摄影、色彩过滤 |
| `pixabay_image` | Pixabay | 免费 | ~2-5s | 大库、分类过滤、插画 |

### 选择器

| 工具 | 用途 |
|------|------|
| `image_selector` | 根据偏好和可用性路由到最佳提供商 |

## 按场景类型选择提供商

| 场景类型 | 首选提供商 | 原因 | 备选 |
|----------|------------|------|------|
| **真实照片**（城市、自然、人物） | `pexels_image` | 真实照片优于 AI 写实 | `pixabay_image` → `flux_image` |
| **技术图表** | `diagram_gen` | 结构化、可编辑 | `flux_image` 配合图表提示词 |
| **抽象/概念插画** | `flux_image` | AI 擅长自定义概念 | `openai_image` |
| **风格迁移/重绘现有图像** | `grok_image` | 原生编辑流程、强提示变换 | `openai_image` |
| **多图合并/合成** | `grok_image` | 可将多张源图合并为一个场景 | `openai_image` |
| **Logo 或品牌资产** | `recraft_image` | 支持 SVG、文字精确 | `openai_image` |
| **含文字/标注的图像** | `openai_image` | 最佳文字渲染（GPT Image 2） | `recraft_image` |
| **复杂多元素构图** | `openai_image` | 最佳指令遵循 | `flux_image` |
| **主视觉图（关键画面）** | `flux_image` | 最高视觉质量 | `openai_image` |
| **缩略图** | `flux_image` 或 `recraft_image` | 需要足够吸睛 | — |
| **预算/免费项目** | `pexels_image` 或 `pixabay_image` | 免费、即时 | `local_diffusion` |
| **离线/隔离网络** | `local_diffusion` | 无需网络 | — |

## 提供商特定注意事项

### Recraft V4 via fal.ai
- **`style` 参数导致 422 错误**（截至 2026-04）。fal.ai 的 Recraft V4 端点拒绝 `style` 枚举值（`digital_illustration`、`realistic_image` 等）。**解决方案：** 将风格方向编码到提示词文本中（如写"牙齿横截面的数字插画"而非 `style="digital_illustration"`）。`image_size` 和 `colors` 参数正常可用。
- **精确商业名称的文字渲染不可靠。** Recraft（与所有 AI 图像模型一样）可能幻觉出错误文字。对于文字必须逐字准确的场景（CTA 画面、商业名称、电话号码），使用 Remotion `text_card` 而非生成含文字的图像。

## 成本-质量权衡

```
制作路径：高级
├── 主视觉图：flux_image ($0.05/张)
├── 辅助视觉：flux_image ($0.03/张)
├── 文字叠加：openai_image ($0.05/张 中等)
├── B-roll 静帧：pexels_image ($0.00)
└── 10 张图总计：约 $0.35

制作路径：标准
├── 全部生成：flux_image ($0.03/张)
├── B-roll 静帧：pexels_image ($0.00)
└── 10 张图总计：约 $0.25

制作路径：预算
├── 全部图库：pexels_image + pixabay_image ($0.00)
├── 图表：diagram_gen ($0.00)
└── 总计：$0.00

制作路径：离线
├── 全部生成：local_diffusion ($0.00)
├── 图表：diagram_gen ($0.00)
└── 总计：$0.00（但更慢、质量更低）
```

当任务从现有图像出发、且应仅路由到支持编辑的提供商时，使用 `generation_mode="edit"`。

## 使用图像选择器

多数情况下使用 `image_selector` 并让其路由：

```python
# 选择器自动寻找最佳可用提供商
result = image_selector.execute({
    "prompt": "现代数据中心的鸟瞰图",
    "preferred_provider": "auto",  # 或 "flux"、"pexels" 等
    "output_path": "assets/images/scene-3.png"
})
```

当你明确知道哪种提供商最适合该场景类型时，用 `preferred_provider` 覆盖。
用 `allowed_providers` 限制为免费或本地选项：

```python
# 预算模式：仅使用免费提供商
result = image_selector.execute({
    "prompt": "服务器机房内景",
    "allowed_providers": ["pexels", "pixabay", "local_diffusion"],
    "output_path": "assets/images/scene-3.jpg"
})
```

## 混合来源的一致性处理

在同一视频中混用图库和生成图像时，视觉一致性是挑战。

### 策略：统一调色
在合成阶段将剧本的调色 LUT 同时应用于图库和生成图像。这统一了观感。`color_grade` 增强工具负责处理。

### 策略：匹配视觉身份，而非复制前缀
生成图像时，将剧本的情绪、色调、质感和媒介适配为简短的场景专属锚点。搜索图库时，按相同的情感和视觉品质过滤：色彩、光照、环境、构图、年代和质感。将剧本作为一致性来源，而非逐字粘贴的脚本。

### 策略：避免场景内混用风格
不要在同一场景中一个元素用图库照片、另一个用 AI 插画。保持每个场景内部一致——要么全图库，要么全生成。
