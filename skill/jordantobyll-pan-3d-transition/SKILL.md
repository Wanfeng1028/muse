---
name: jordantobyll-pan-3d-transition
description: Assemble drone/aerial footage and stills into a montage with 3D swivel (pan) transitions using Remotion, plus insert a 3D rotating teaser clip into an existing video. Use when the user wants aerial montages, 3D pan transitions, swivel/flip card effects, or a rotating teaser inserted mid-video.
version: "1.0.0"
author: playhouse
license: MIT
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Pan 3D Transition

## 目标
用 Remotion 生成两类效果：

1. **Montage**：把 `public/montage/` 下的无人机航拍视频与静态照片拼成一段序列，相邻片段之间用 3D 绕 Y 轴翻转（swivel）转场衔接，视觉上像卡片翻面。
2. **Pan3D 插入片段**：从视频后段抽取帧序列，做成一段带 3D 旋转进出场、背景虚化压暗的“teaser”片段，之后与主视频拼接。

## 目录结构
```
scripts/video_effects/
├── src/
│   ├── dynamic-index.ts     # Remotion 入口，registerRoot
│   ├── Root.tsx             # 注册 Pan3D 与 DroneMontage 两个 Composition
│   ├── Montage.tsx          # 航拍序列 + 3D swivel 转场
│   ├── Pan3D.tsx            # 3D 旋转 teaser 片段
│   └── montageConfig.ts     # 时长 / 转场 / 片段清单配置
├── remotion.config.ts
├── package.json
└── tsconfig.json
```

## 素材准备
- 航拍片段放到 `scripts/video_effects/public/montage/`，文件名与 `montageConfig.ts` 中的 `src` 对应。
- Pan3D 使用 `public/frames/frame_0001.jpg` 起的帧序列，以及背景图 `public/frames/bg_image.png`（由外部脚本抽取）。

## 使用方式

### 预览 / 渲染航拍 montage
```bash
cd scripts/video_effects
npm install
npx remotion studio src/dynamic-index.ts
npx remotion render src/dynamic-index.ts DroneMontage out/montage.mp4
```

### 渲染 3D teaser 片段（Pan3D）
Pan3D 通过 `--props` 接收 `frameCount / playbackRate / width / height`，并用 `calculateMetadata` 让输出的尺寸与帧数与源视频对齐（拼接时可用 `-c copy`）：
```bash
npx remotion render src/dynamic-index.ts Pan3D out/teaser.mp4 \
  --props '{"frameCount":300,"playbackRate":1,"width":1920,"height":1080}'
```

### 拼接到原视频
将 teaser 片段按所需位置插入主视频：切出 intro / teaser / main 三段后用 `ffmpeg` 拼接（保留音频），例如：
```bash
ffmpeg -i intro.mp4 -i teaser.mp4 -i main.mp4 \
  -filter_complex "[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1[v][a]" \
  -map "[v]" -map "[a]" output.mp4
```

## 配置说明（montageConfig.ts）
| 字段 | 含义 |
|------|------|
| `FPS` / `WIDTH` / `HEIGHT` | 输出帧率与分辨率 |
| `TRANSITION` | 相邻片段重叠时长（秒），即 3D swivel 转场时长 |
| `SEGMENTS` | 片段数组；`video` 类型支持 `trimStart`，`image` 类型走 Ken Burns 缓慢推拉 |

## 依赖
```bash
cd scripts/video_effects && npm install
```

## 输出
- `DroneMontage`：航拍素材拼成的 montage，片段间为 3D swivel 转场。
- `Pan3D`：可插入到原视频指定位置的 3D 旋转 teaser 片段。

## 来源说明
功能参考 https://github.com/jordantobyll/video-editing-skills，本文与脚本为独立重写。
