# 剪辑技术

## 删停顿(`scripts/pause_cuts.py`)

只剪静音、不剪内容。用法:

```bash
python3 scripts/pause_cuts.py detect --words words.json --video clip.mp4 \
  [--protect protect.json] -o cuts.json          # 找切点,写剪点表 JSON
python3 scripts/pause_cuts.py apply cuts.json --video clip.mp4 -o clip.cut.mp4   # 应用切点
```

- `--words` 是本仓库已有的 `timeline/words.py` 词级时间码格式(`{"words":[{"w","s","e"}, ...]}`)。
- `--protect` 是可选的保护区间列表(`[{"start","end","why"?}]`)——分镜里组件自己的入场/出场窗口、SFX 音效窗口都可以从分镜/组件参数里读出来,拼成这份文件传进去;绝不在这些区间内切。
- 默认规则:句中停顿(非结尾)长于 0.25s 的收短到约 0.15s,句末(依上一个词是否以 `。？！.!?` 结尾判断)收短到约 0.22s;每个切点在词起音前后各留 0.07/0.08s 安全带;给了 `--fps`(或 `--video` 自动探测到的帧率)时切点吸附到帧边界。
- 切点必须验证:`detect` 会对候选切点做人声能量(RMS/峰值 dBFS)检查,从响的一侧收缩直到低于 `--silence-db`(默认 -66dBFS)才落定,查不到足够安静的子区间就跳过、记进输出的 `skipped` 里,不会咬字。
- `apply` 用同一组切点同时剪画面和声音(音画对得上):画面在切点硬切(不做画面交叉淡化,会重影),声音在每个切点做等功率交叉淡化(`--crossfade-ms`,默认 12ms,落在 10-15ms 区间)。
- 一条视频生产管线自己的动画窗口表如果比一份手写的 `--protect` 文件更复杂(比如按分镜里每个组件动态算保护区间),参考 `library/_shared/video20-a0-pipeline/` 里更完整的项目专属实现。

## 可选整体提速(`scripts/speed.py`,约 1.1×)

```bash
python3 scripts/speed.py --video clip.cut.mp4 --speed 1.1 -o clip.fast.mp4
python3 scripts/speed.py --video clip.cut.mp4 --speed 1.1 --bgm bed.mp3 --bgm-gain-db -14 -o clip.fast.mp4
```

- 画面:`setpts=PTS/speed` 原始帧率丢帧,不插帧——动作观感不变,只是变快。
- 人声:ffmpeg `rubberband` 滤镜变速(`pitch=1` 保持音高),没有 `rubberband` 时退回 `atempo`(会打印警告,音高保持没有 rubberband 干净)。
- BGM(`--bgm`,可选):按自己的原速铺在提速后的新时长下面,不跟人声一起拉伸——跟着拉伸会和 BGM 自己的卡点对不上。这里只做简单的裁剪/循环+淡入淡出+增益混音,不是响度匹配的母带;要做贴合人声的闪避混音,把这个脚本产出的提速人声传给 `audio/xlaudio`(见 `audio/README.md`)。
