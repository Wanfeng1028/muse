---
name: openmontage-animation-compose-director
version: "1.0.0"
description: 动画管线的渲染合成阶段，强调文字锐利度、时间完整性以及输出节奏的一致性。适用于图像驱动动画的合成 JSON 构建、音乐选取、渲染前校验与渲染后自检。
metadata:
  license: AGPL-3.0
---

# 合成导演 — 动画管线

## 适用场景

本阶段负责把动画渲染出来，重点是文字清晰、时间准确、输出节奏稳定。对于 `image_animation` 方案，还要额外负责构建合成 JSON、挑选音乐、跑渲染前校验以及做渲染后自检。

## 运行时路由（第一步，强制）

动手之前先读 `edit_decisions.render_runtime`。它在提案阶段就被锁定，不允许悄悄更改。本技能余下内容默认 `render_runtime="remotion"`（本管线的默认值）。如果提案锁的是别的运行时：

- **`render_runtime="hyperframes"`**——HTML/CSS/GSAP 渲染。不要套用下面 Remotion 相关的章节（public/ 暂存、Remotion 合成 JSON）。改为：
  1. 读 `skills/core/hyperframes.md` 了解完整路由模型；
  2. 读 `.agents/skills/hyperframes/SKILL.md` 与 `.agents/skills/hyperframes-cli/SKILL.md` 了解编写契约与命令行用法；
  3. 调用 `video_compose` 并传 `edit_decisions.render_runtime="hyperframes"`——它会委托给 `hyperframes_compose`，后者负责在 `projects/<名称>/hyperframes/` 下物化工作区，执行 `hyperframes check → render`，并返回 MP4 路径；
  4. 渲染前 `hyperframes check` 必须通过。它统一了 lint、运行时、布局、动效与 WCAG 对比度检查；迭代阶段可用 `skip_contrast=true` 推迟对比度检查，但最终交付不行。
- **`render_runtime="ffmpeg"`**——只做简单拼接与裁剪，没有合成。直接调用 `video_compose`，它不会自动升级到 Remotion。
- **运行时不可用**——不要悄悄换成别的引擎。按 AGENT_GUIDE.md 的"显式上报阻塞"把问题摆到用户面前，等批准（记入 decision_log 作为 `render_runtime_selection` 决策）后再切。

渲染后自检（final_review）在所有运行时下都一样——同样的 ffprobe 探测、抽帧、音频抽查与承诺保全检查。`final_review.checks.promise_preservation.render_runtime_used` 必须等于实际运行的运行时。

**调用 `video_compose.execute()` 时把 `proposal_packet` 传进去。** 这样工具能直接对比提案锁定的运行时与 `edit_decisions` 中记录的运行时，一旦不一致就置 `runtime_swap_detected=true`。不传的话这项检查会变成 `skipped`，只能靠评审技能跨产物比对来抓偷换。

## 前置资源

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/render_report.schema.json` | 产物校验 |
| 上游产物 | `edit_decisions`、`asset_manifest` | 时间计划与素材文件 |
| 工具 | `video_compose`、`audio_mixer`、`video_stitch` | 最终组装 |
| 工具 | `composition_validator` | 渲染前校验（强制） |
| 工具 | `audio_probe` | 音乐时长检查 |
| 风格手册 | 当前激活的 playbook | 渲染一致性 |
| 参考 | `remotion-composer/public/demo-props/mori-no-seishin.json` | 合成 JSON 格式范例 |
| 参考 | `skills/core/remotion.md` | Remotion 模式、anime_scene 类型、关键约束 |

## 流程

### 1. 确保素材在 Remotion 公共目录中

**关键：** Remotion 只能通过 `staticFile()` 访问文件，而它解析的根是 `remotion-composer/public/`。生成的图片和音乐必须先复制或软链进这个目录才能渲染。

```
项目结构：
  projects/<名称>/assets/images/*.png     ← 图片生成在这里
  remotion-composer/public/<名称>/*.png   ← Remotion 从这里读

必须做：把图片和音乐都复制或软链到 public/<项目名>/
```

合成 JSON 里的图片路径相对于 `remotion-composer/public/`：
```json
"images": ["deep-ocean/scene1-a.png", "deep-ocean/scene1-b.png"]
"src": "deep-ocean/ambient-music.mp3"
```

**跳过这一步，渲染会因文件缺失报错，或者产出黑帧。**

### 2. 构建合成 JSON（image_animation 方案）

`anime_scene` 合成需要一份 JSON，放在 `remotion-composer/public/demo-props/<名称>.json`。

**必需结构：**

```json
{
  "cuts": [
    {
      "id": "scene-1-name",
      "source": "",
      "in_seconds": 0,
      "out_seconds": 5,
      "type": "anime_scene",
      "images": ["<项目>/<图片a>.png", "<项目>/<图片b>.png"],
      "animation": "<镜头运动>",
      "particles": "<粒子类型>",
      "particleColor": "#HEXCOLOR",
      "particleCount": 20,
      "particleIntensity": 0.5,
      "backgroundColor": "#0A0A1A",
      "vignette": true,
      "lightingFrom": "rgba(r,g,b,a)",
      "lightingTo": "transparent"
    }
  ],
  "overlays": [...],
  "audio": { "music": { "src": "<项目>/music.mp3", "volume": 0.15, "fadeInSeconds": 2, "fadeOutSeconds": 3 } }
}
```

**字段与 AnimeScene prop 对照：**

| JSON 字段 | 类型 | 取值 | 是否必填 |
|-----------|------|------|----------|
| `type` | string | `"anime_scene"` | 是 |
| `images` | string[] | 1–4 个相对 `public/` 的图片路径 | 是 |
| `animation` | string | `zoom-in`、`zoom-out`、`pan-left`、`pan-right`、`ken-burns`、`drift-up`、`drift-down`、`parallax`、`static` | 否（默认 `ken-burns`） |
| `particles` | string | `fireflies`、`petals`、`sparkles`、`mist`、`light-rays` | 否 |
| `particleColor` | string | 十六进制颜色 | 否（默认 `#FFE082`） |
| `particleCount` | number | 1–50 | 否（默认 20） |
| `particleIntensity` | number | 0–1 | 否（默认 0.6） |
| `backgroundColor` | string | 场景背景的十六进制颜色 | 否（默认 `#0A0A1A`） |
| `vignette` | boolean | 电影感暗角叠加 | 否（默认 true） |
| `lightingFrom` | string | 起始渐变颜色（`rgba(...)` 或 `transparent`） | 否 |
| `lightingTo` | string | 结束渐变颜色 | 否 |

**参考：** 完整可跑的例子见 `mori-no-seishin.json`（吉卜力森林）与 `deep-ocean.json`（水下生物荧光）。

### 3. 选音乐并找最佳起点

用 `tools/audio/pixabay_music.py` 找与情绪相符的免版税氛围音乐。

**下载后必须跑音频能量分析：**

```python
from tools.analysis.audio_energy import AudioEnergy
result = AudioEnergy().execute({
    "input_path": "path/to/music.mp3",
    "video_duration_seconds": 30,  # 你的视频时长
})
data = result.data
print(f"推荐起点: {data['recommended_offset_seconds']}s")
print(f"理由: {data['offset_reason']}")
print(f"是否需要循环: {data['needs_loop']}")
```

这个工具会：

1. **找到最佳段落**——逐秒分析响度，找出平均能量最高的 N 秒窗口。氛围音乐常有 10 到 30 秒的安静前奏，主旋律才进来。
2. **建议循环**——如果从起点算起音乐比视频短，就提示你开启循环。

**把起点写进合成 JSON：**

```json
"audio": {
  "music": {
    "src": "project/music.mp3",
    "volume": 0.15,
    "fadeInSeconds": 2,
    "fadeOutSeconds": 3,
    "offsetSeconds": 55,
    "loop": false
  }
}
```

- `offsetSeconds`——从音轨的这个位置开始播放（跳过安静前奏）
- `loop`——剩余音乐短于视频时设为 `true`

**如果工具返回 `needs_loop: true`：** 在合成 JSON 里设 `"loop": true`。Remotion 会无缝循环音频，音量淡入淡出每轮重置。

### 4. 渲染前校验（强制，无例外）

每次渲染前都跑 `composition_validator`：

```python
from tools.analysis.composition_validator import CompositionValidator
result = CompositionValidator().execute({
    "composition_path": "remotion-composer/public/demo-props/<名称>.json",
    "assets_root": "remotion-composer/public",
})
# 继续之前 result.data["valid"] 必须为 True
```

它能抓出：

- 会导致黑帧或渲染报错的缺失图片／音频文件；
- 非法的镜头时间（out ≤ in）；
- 音频长于视频时长。

**校验失败就先修，不要渲染非法合成。**

### 5. 保留运动时间

不要让导出设置或粗心的合成改变停顿、错位、场景过渡的实际观感时长。

### 6. 保护文字与图表锐利度

动画导出常栽在文字发虚、细线糊掉、或移动端取景太挤。

### 7. 渲染

```bash
cd remotion-composer
npx remotion render Explainer \
  --props="public/demo-props/<名称>.json" \
  --output="<输出路径>/final.mp4" \
  --codec=h264 --crf=18
```

**注意：** 合成名是 `Explainer`，不是 `ExplainerVideo`。不要把 `src/index.ts` 指定为入口——Remotion 会自动发现。

### 8. 渲染后自检（强制）

渲染完成后抽中间帧做目视检查：

```bash
# 每个场景中间抽一帧
ffmpeg -y -i final.mp4 \
  -vf "select='eq(n\,75)+eq(n\,225)+eq(n\,375)+eq(n\,525)+eq(n\,675)+eq(n\,825)'" \
  -vsync vfr frames/scene_%02d.png
```

**逐帧检查：**

- [ ] 图片可见（不是黑帧或暗帧）
- [ ] 粒子在渲染（闪光、萤火等可见）
- [ ] 镜头运动明显（取景与静止时有差异）
- [ ] 叠加层在正确时机出现且文字干净
- [ ] 各场景色调一致
- [ ] 暗角营造出电影纵深感

**同时验证输出文件：**
```bash
ffprobe -v quiet -print_format json -show_format -show_streams final.mp4
```
- 时长在目标值 ±5% 以内？
- 分辨率是 1920×1080？
- 音频流存在？

**发现问题时：** 定位原因（图片缺失、时间错误、渲染故障）并修好，再交给用户。

### 9. 用渲染元数据

推荐元数据键：

- `render_fps`
- `sharpness_checks`
- `safe_zone_checks`
- `variant_outputs`

## 常见坑

- **忘了把素材拷到 `remotion-composer/public/`**——渲染失败的头号原因。图片生成到 `projects/<名称>/assets/`，但 Remotion 从 `public/` 读。
- 渲染后文字发虚或有锯齿。
- 压缩参数损伤图表。
- 预览与最终输出的场景节奏不一致。
- **跳过 `composition_validator`**——它能在浪费渲染时间之前抓出文件缺失、时间错误、音频不匹配。
- **不抽帧自检**——没做过目视检查的渲染不算"完成"。黑帧、粒子丢失、图片不可见，光看文件大小往往看不出来。
- **用 `useVideoConfig()` 的 `durationInFrames` 做场景级计时**——它返回的是整个合成的时长，不是该 Sequence 的时长。见 `skills/core/remotion.md` 的关键约束。
