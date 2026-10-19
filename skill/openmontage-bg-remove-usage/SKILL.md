---
name: openmontage-bg-remove-usage
version: "1.0.0"
description: 说明 OpenMontage 中 bg_remove 抠图工具的使用方式，涵盖模型选择、alpha matting 取舍、批量帧处理与合成前质检，适用于产品演示、人物合成、缩略图与绿幕替代等资产准备场景。
metadata:
  license: AGPL-3.0
---

# OpenMontage 背景移除使用指南

> 参考来源：rembg 库文档、U2Net 论文（Qin 等，2020）、IS-Net 论文（Qin 等，2022）、OpenMontage `tools/bg_remove.py` 实现。

## 速查卡

```
默认模型：        u2net（通用、快速）
人物场景：        u2net_human_seg（针对人体轮廓优化）
精细边缘：        开启 alpha_matting（头发、毛皮、树叶）
输出：            默认透明 PNG；设置 bg_color 可替换为纯色底
耗时：            CPU 约 1-3 秒/张，GPU（onnxruntime-gpu）低于 0.5 秒
安装：            pip install rembg（CPU） | pip install rembg[gpu]（CUDA）
```

## 何时使用 bg_remove

背景移除属于**资产准备**环节，应在合成阶段之前完成。

- **产品演示／电商视频**——把产品隔离到干净背景上。
- **合成叠加**——把演讲者叠加到生成的背景或图表之上。
- **缩略图制作**——为 YouTube 封面做干净抠像。
- **绿幕替代**——不实际搭绿幕也能得到绿幕效果。
- **B-roll 准备**——把原始照片处理干净用于叠加。

## 模型选择指南

| 模型 | 最适合 | 速度 | 备注 |
|-------|----------|-------|-------|
| `u2net` | 通用物体、产品、场景 | 快 | 默认；综合表现均衡 |
| `u2net_human_seg` | 人物、肖像、演讲者 | 快 | 对人体轮廓的遮罩更准确 |
| `isnet-general-use` | 复杂边缘、头发、毛皮 | 较慢 | 细微边界细节更丰富 |

**决策规则：** 主体是人就用 `u2net_human_seg`；主体边缘复杂（头发、毛皮、植被）且要求最高质量，用 `isnet-general-use`；其余情况用默认的 `u2net`。

## Alpha Matting

Alpha matting 通过计算边界处的软透明来细化边缘遮罩，边缘更自然，但处理耗时约翻倍。

| 主体类型 | 是否开启 | 原因 |
|-------------|---------------|--------|
| 头发、毛皮、羽毛 | 开启 | 半透明细丝需要软边 |
| 树叶、树木、草地 | 开启 | 不规则的有机边界受益于 matting |
| 产品、设备 | 关闭 | 几何边缘干净，matting 无增益 |
| 文字、logo、图形 | 关闭 | 硬边才是正确结果 |

## 常见工作流

### 1. 演讲者抠像用于合成

把演讲者从其背景中提取出来，叠加到图表或幻灯片上。

```
bg_remove(input_path="speaker.png", model="u2net_human_seg")
  --> speaker_nobg.png（透明）
  --> 在合成阶段叠加到图表/幻灯片之上
```

### 2. 产品隔离

隔离产品，可选放到品牌色背景上。

```
bg_remove(input_path="product.jpg", model="u2net")
  --> product_nobg.png（透明）

# 或指定品牌背景色：
bg_remove(input_path="product.jpg", model="u2net", bg_color="#FFFFFF")
  --> product_nobg.png（白色背景）
```

### 3. 缩略图准备

先抠图，再放大，最后在合成阶段叠加文字。

```
bg_remove(input_path="subject.png", model="u2net_human_seg", alpha_matting=True)
  --> subject_nobg.png
  --> 放大 --> 在合成阶段叠加文字
```

### 4. 批量帧处理

为合成序列准备多帧时，应在进入合成阶段前把所有源帧处理完毕。

```
for each source frame:
    bg_remove(input_path=frame, model="u2net_human_seg")
    --> frame_nobg.png
然后：把所有透明帧合成到背景序列之上
```

## 质量检查清单

进入合成阶段前，逐项核对每个 bg_remove 产物：

- [ ] **边缘干净**——主体周围没有光晕伪影。
- [ ] **细节保留**——头发、手指、细窄结构完好。
- [ ] **透明彻底**——透明区域没有残留背景色渗出。
- [ ] **主体完整**——没有误删主体的一部分。
- [ ] **合成测试**——叠加到目标背景上时主体过渡自然。

## 在 OpenMontage 中的落地

在资产准备中使用 `bg_remove` 工具时：

1. **凡含人物的帧一律用 `u2net_human_seg`**——它对人体轮廓的遮罩比通用模型更紧致。
2. **只对复杂边缘主体开启 `alpha_matting`**，如头发、毛皮、植被；边缘干净的主体跳过，节省时间。
3. **合成类工作流输出透明 PNG**（不设 `bg_color`），在合成阶段再叠加，保留最大灵活性。
4. **需要纯色替换时设置 `bg_color`**，与风格手册的背景色 token 保持一致，让产物贴合项目视觉。
5. **源帧必须在合成阶段之前处理完**——bg_remove 属于资产准备，不是合成时的操作。
6. **合成前按原始分辨率检查边缘**——光晕与边缘渗色在成片里会很明显，必须提前发现。
