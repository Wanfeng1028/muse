# code-film 视频工程

由 code-film 技能的 `new_project.py` 创建（也可以直接复制这个模板）。这个工程是《我从未见过太阳》前 14 秒的示例，
包含四种场景组件和完整的音画同步链路。

## 常用命令

```bash
npm install
npm run studio                                 # 浏览器预览，可拖时间轴
npx remotion still Film out/f0240.png --frame=240   # 渲染单帧检查
npm run draft                                  # 半分辨率快速预演
npm run render                                 # 正式渲染 out/film.mp4
npm run typecheck
```

## 改这片子，从哪里下手

1. `src/storyboard.json`：分镜的唯一事实来源。镜头时间、用哪个场景、文字、音效事件全在这里。
2. `src/theme.ts`：视觉系统。颜色、字体、字号、动效参数、质感强度。
3. `src/scenes/`：场景组件。写新组件后在 `scenes/index.ts` 登记。
4. `public/`：字体、音乐、配音、图片素材。

## 目录

```
src/lib/         时间网格、缓动与弹簧、字体加载、useShot
src/components/  Camera（虚拟摄像机）、Ascii（字符画）、Texture（颗粒暗角）、SfxTrack（音效轨）
src/components/text/  SplitText / Typewriter / Decode
public/sfx/      预生成的 13 种合成音效和 manifest.json（含每个音效的时长与峰值）
```

规则：画面上的一切只能是帧号的函数。不要 Math.random()、CSS 动画、setTimeout、Date。
随机效果用 remotion 的 random('种子') 或 @remotion/noise。
