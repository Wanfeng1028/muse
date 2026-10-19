---
name: openmontage-animated-drawing
version: "1.0.0"
description: 让用户提供的类人简笔画或照片通过真实动捕数据动起来，输出透明 GIF 或 MP4；适用于已有手绘角色、希望其跳舞挥手跳跃的短视频场景，矢量自绘场景请改用 ink-art。
metadata:
  license: AGPL-3.0
---

# 动画绘图（让已有画作真实动起来）

> 命令：`/animated-drawing` · **路线 A（位图）。** 姊妹技能：`/ink-art`（矢量、从零生成）。
> 底层工具：Meta 开源的 **AnimatedDrawings**（github.com/facebookresearch/AnimatedDrawings，代码 MIT，仓库已于 2025 年归档）。

**适用时机：** 用户手里已经有一张**类人**角色画稿或照片，并希望**这张图本身**动起来（跳舞／行走／跳跃／挥手）。产物是原画经形变后生成的位图 **透明 GIF 或 MP4**。若要从零**创作**一个矢量涂鸦并让它自己画出来再动，请改用 **`/ink-art`**。

**它能做什么：** 自动为画稿绑定骨架（预测 16 关节），再把 BVH 动捕片段通过 As-Rigid-As-Possible 网格形变重定向到平面贴图上。它只**移动一张已完成的画**，没有描线／自我绘制式揭示效果（那属于 `/ink-art`）。

## 选择角色来源——必须先询问（严禁静默复用内置角色）

该工具会动画化**你给它的任意图像**，前提是**手绘类人**（头、双臂、双腿，肢体彼此分离，浅色纯底）。开工前**先向用户列出下列选项**并让其选定（用户没有素材时默认走生成）：

1. **用户上传画稿**——本人绘制的类人涂鸦。效果最佳，因为那是他自己的角色。
2. **用户上传照片或其他图像**——先做**涂鸦化**处理（`image_selector` img2img，FLUX/Recraft，提示词大意："把这张图变成儿童蜡笔简笔画，类人，全身，纯白背景"），再绑骨。手绘感来自这一步；直接拿原照片做形变效果很差。
3. **新生成一个角色** ⭐（推荐默认）——用 `image_selector`（FLUX/Imagen），提示词大意："儿童蜡笔风格的类人角色，全身，正面朝向，A 字姿势，四肢分开，纯白背景，无阴影，无文字。"每条视频都能得到不同角色。
4. **取用图库角色**——`pixabay_image` / `pexels_image`，过滤条件为浅底上的手绘类人。命中率不稳定（图库多为照片），优先选第 3 项。

内置示例角色**仅供演示**，不得作为用户成片角色交付。选项 1–4 均依赖下方的自动绑骨 Docker 服务；服务未启动要如实告知用户。

## 两种运行模式

**A · 内置角色 + 预设动作——开箱即用，无需 Docker（已在 Windows 验证）：**
```bash
# 浅克隆官方仓库并进入目录，避免拉取完整历史
git clone --depth 1 https://github.com/facebookresearch/AnimatedDrawings.git && cd AnimatedDrawings
# 仓库锁定 Python 3.8 与旧版 wheel，用 uv 安装该解释器
uv python install 3.8 && uv venv --python 3.8 .venv
# 以可编辑模式安装项目本体
uv pip install --python .venv -e .
# 仓库代码引用了 pkg_resources 却未声明依赖，需手动补 setuptools
uv pip install --python .venv "setuptools<81"
# 跑官方导出 GIF 的示例配置，验证环境可用
.venv/Scripts/python -c "from animated_drawings import render; render.start('./examples/config/mvc/export_gif_example.yaml')"
```
CPU 上约 10–12 秒出片，无需 GPU、Docker 或额外模型下载。

**B · 为新画稿自动绑骨——重载路径（Docker + 约 670 MB 模型，约 16 GB 内存）：**
```bash
# 一条命令完成检测→分割→绑骨→重定向→渲染
python image_to_animation.py drawing.png out_dir
```
依赖仓库自带的 TorchServe 容器（`docker/` 目录），会下载 `drawn_humanoid_detector.mar`（311 MB）与 `drawn_humanoid_pose_estimator.mar`（357 MB）。Windows 上只能通过该容器运行绑骨栈（OpenMMLab 实际仅支持 Linux）。

## 输入要求（自动绑骨路径）
一张清晰绘制的**类人**，大致 T/A 姿势（肢体分开不重叠），置于**浅色纯底**（分割基于阈值 + 洪水填充），画面中只能有一个人物。

## 由 agent 生成的配置（全部为 YAML）
`char_cfg.yaml`（附带 `texture.png`、`mask.png`，由 `image_to_annotations.py` 自动产出）· **动作**配置（BVH + 帧区间 + 地平面）· **重定向**配置（BVH 关节到骨架关节的映射；骨架一致时复用内置的 `fair1_ppf` / `cmu1_pfp`）· **MVC** 配置（`controller.MODE: video_render`、`OUTPUT_VIDEO_PATH`，可选 `WINDOW_DIMENSIONS` / `CLEAR_COLOR` / `BACKGROUND_IMAGE` / `CAMERA_POS`）。

## 预设动作与重定向配置的对应（必须匹配 BVH 骨架）
每个内置 BVH 属于不同骨架体系，配错重定向配置会直接崩溃（报错形如 `ValueError: 'RightArm' is not in list`）。对应关系如下：

| 动作 | BVH 目录 | 重定向配置 |
|---|---|---|
| `dab`、`wave_hello`、`jumping`、`zombie` | `bvh/fair1/` | `fair1_ppf` |
| `jumping_jacks` | `bvh/cmu1/` | `cmu1_pfp` |
| `jesse_dance` | `bvh/rokoko/` | `mixamo_fff` |

其他 BVH 需自行匹配骨架，或另写重定向配置。长片段务必用 `end_frame_idx` 截断（例如 `wave_hello` 有 839 帧），否则渲染耗时数分钟；含地面接触的动作（`dab`、`wave_hello`）渲染约慢 8 倍。

## 角色多样性——动画化用户自己的画（解决"永远是同一个吉祥物"）
内置角色**仅供演示**。真实使用中角色应来自用户**提供**的素材，每条视频都不同。对于"随便给我做条视频"且没有画稿的请求，应**新生成一个角色**（图像生成，提示词如"儿童蜡笔风格的……"，输出浅底 PNG）并**自动绑骨**（Docker 路线），从而每次角色都不同。**绝不可跨视频复用内置角色**，否则所有成片都像同一个吉祥物。

## 合成进 HyperFrames（后半程，真正出片所必需）
AnimatedDrawings 只输出运动中的角色本身。要形成含背景、气球、配乐的**视频**，需在 HyperFrames 中合成：
- **透明输出：** 在 MVC 配置中设 `view.CLEAR_COLOR: [0,0,0,0]`，得到透明帧。
- **GIF 在确定性 HyperFrames 渲染中会卡死。** 转成带 alpha 的 **VP9 WebM**：`ffmpeg -i char.gif -c:v libvpx-vp9 -pix_fmt yuva420p char.webm`（`ffprobe` 会误报 `yuv420p`，alpha 实际完好）。
- **视频契约（linter 强制，跑 `npm run check`）：** `<video>` 必须是舞台的**直接子元素并带独立 `id`**，不可嵌在带时间轴的 `<div>` 里（嵌套会导致画面冻结）；每个片段需自己的 `data-track-index`；淡出需补一条硬杀 `tl.set(el,{opacity:0})`。
- 文字与**对话气泡**用 HTML 覆盖层 div，字体使用完整的 `ink-theater/assets/patrickhand.ttf`（参见 ink-theater 的字体坑）。
- **流水线豁免：** `/animated-drawing` 与 `/ink-art` 属创意入口，不适用 Rule-Zero 流水线，无需 `.yaml` 清单。

## 输出与诚实的局限
输出透明 GIF 或 MP4（H.264，`avc1`），分辨率取自 `WINDOW_DIMENSIONS`（示例为 500×500）。**仅限位图**（对画稿像素做形变，放大可见拉伸贴图）、**仅限类人**、**无描线揭示**、**背景粗糙**。它是个"让你的涂鸦活过来"的趣味效果；自动绑骨路线背后依赖 Docker 服务。它不是通用矢量引擎——若需要自我绘制式的白墨矢量涂鸦，请用 `/ink-art`。

会话评测样例渲染位于 `.tmp/animated-drawings/out/`（如 `char3_dab.gif`、`char1_zombie.mp4`）。
