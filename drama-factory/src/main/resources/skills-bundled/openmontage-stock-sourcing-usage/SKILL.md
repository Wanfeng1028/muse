---
name: openmontage-stock-sourcing-usage
version: "1.0.0"
description: 指导如何在 OpenMontage 中高效使用 Pexels 和 Pixabay 图库工具进行素材搜索与下载，涵盖查询构建、提供商选择、许可证注意事项及资产管道集成，适用于需要免费图片和视频素材的视频制作场景。
metadata:
  license: AGPL-3.0
---

# 图库素材搜索与使用

本技能说明如何在 OpenMontage 中有效使用图库图片和视频工具——查询构建、提供商选择、许可证意识和资产管道集成。

## 可用图库工具

| 工具 | 提供商 | 内容 | 费用 | 速率限制 | 最佳用途 |
|------|--------|------|------|---------|----------|
| `pexels_image` | Pexels | 照片 | 免费 | 200/小时 | 高质量摄影、多样化库 |
| `pixabay_image` | Pixabay | 照片、插画、矢量图 | 免费 | 100/分钟 | 分类筛选、大库（500万+） |
| `pexels_video` | Pexels | 视频片段 | 免费 | 200/小时 | HD/4K 实拍素材 |
| `pixabay_video` | Pixabay | 视频片段 | 免费 | 100/分钟 | 分类筛选视频、动画片段 |

## 提供商选择指南

### 何时选 Pexels

- 需要**高质量摄影**（精选、专业）
- 需要**视频**（视频库比 Pixabay 大）
- 需要**方向筛选**（横屏/竖屏/方形）
- 需要**颜色筛选**（匹配 playbook 调色板）
- 需要**多语言结果**（28 个区域设置）

### 何时选 Pixabay

- 需要**按分类筛选**（自然、商业、科学等）
- 除照片外还需要**插画或矢量图**
- 需要**编辑精选**结果
- 需要**更高速率限制**（100/分钟 vs 200/小时）
- 需要**视频类型筛选**（实拍 vs 动画）

### 决策流程

```
需要图库图片？
├── 需要特定分类（科学、商业等）？→ pixabay_image
├── 需要插画/矢量图？→ pixabay_image
├── 需要颜色匹配？→ pexels_image
└── 通用照片？→ pexels_image（质量筛选更好）

需要图库视频？
├── 需要 4K？→ pexels_video（通过 size="large" 支持 4K）
├── 需要动画片段？→ pixabay_video（video_type="animation"）
├── 需要分类筛选？→ pixabay_video
└── 通用素材？→ pexels_video（HD 质量更好）
```

## 输入参数说明

### pexels_image / pexels_video

```python
{
    "query": "city skyline sunset",      # 必填：搜索词
    "orientation": "landscape",           # 可选：landscape/portrait/square
    "size": "large",                      # 可选：large/medium/small
    "color": "FF6B35",                    # 可选：十六进制色值（不带#）或颜色名
    "per_page": 5,                        # 每页结果数（1-80）
    "download_size": "large2x",           # 图片：original/large2x/large/medium
    "preferred_quality": "hd",            # 视频：hd/sd
    "output_path": "assets/images/s3.jpg" # 保存路径
}
```

### pixabay_image / pixabay_video

```python
{
    "query": "server room",              # 必填：搜索词（最多100字符）
    "image_type": "photo",               # 图片：all/photo/illustration/vector
    "video_type": "film",                # 视频：all/film/animation
    "orientation": "horizontal",          # all/horizontal/vertical
    "category": "computer",              # 20个分类之一
    "colors": "blue,gray",              # 逗号分隔的颜色名
    "editors_choice": true,              # 仅显示精选高质量
    "safesearch": true,                  # 生产环境始终为true
    "output_path": "assets/video/s5.mp4" # 保存路径
}
```

## 注意事项与最佳实践

### 1. Pixabay URL 会过期

Pixabay 下载 URL 内嵌令牌，会过期。搜索后**必须立即下载**。工具会自动处理，但绝不要缓存 Pixabay URL 供后续使用。

### 2. Pixabay 分辨率限制

标准 Pixabay API 用户获取的图片最大宽度为 1280px（`largeImageURL`）。全分辨率需要审批过的 API 权限。对大多数视频制作叠加层来说，1280px 足够。

### 3. Pexels 认证头

Pexels 在 `Authorization` 头中使用裸 API 密钥（不是 `Bearer`）。工具已处理，调试时需注意。

### 4. 搜索结果因区域而异

Pexels 支持 28 个区域设置。搜索文化特定内容时，设置 locale 参数。

### 5. 图库图片是确定性的

与 AI 生成不同，搜索"ocean waves"两次返回相同结果。如果第一个结果不够好，换关键词——不要重复同一查询。

### 6. 视频时长筛选

两个图库视频工具都支持 `min_duration` 和 `max_duration` 参数。用它们避免在只需要 4 秒时下载 30 秒片段——节省带宽和时间。

## 与资产管道集成

图库工具与生成工具的集成方式完全一致。在资产清单中：

```json
{
    "id": "broll-s3",
    "type": "image",
    "subtype": "broll",
    "path": "assets/images/broll-s3.jpg",
    "source_tool": "pexels_image",
    "scene_id": "scene-3",
    "cost_usd": 0.00,
    "metadata": {
        "photographer": "Joey Farina",
        "source_url": "https://www.pexels.com/photo/2014422/",
        "license": "Pexels License (free, no attribution required)"
    }
}
```

剪辑导演和合成导演对图库资产的处理与生成资产完全相同——只是从清单中引用文件路径。

## 许可证摘要

| 提供商 | 商业用途 | 署名 | 限制 |
|--------|---------|------|------|
| Pexels | 可，免费 | 不要求（欢迎） | 不可原样转售；不可暗示背书 |
| Pixabay | 可，免费 | 不要求 | 不可原样转售；不可创建竞争性图库服务 |

两者对所有 OpenMontage 用例均安全。无许可费、无按次版税、无署名义务。
