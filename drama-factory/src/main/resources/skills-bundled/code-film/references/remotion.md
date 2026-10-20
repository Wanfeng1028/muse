# Remotion 工程：结构、渲染与踩坑

## 1. 原理

Remotion 用 React 描述每一帧画面。渲染时，它用无头浏览器逐帧打开页面、截图，再交给 FFmpeg 编码成视频。所以：
- 任何浏览器能画出来的东西（HTML、CSS、SVG、Canvas、WebGL）都能进视频。
- 每一帧都是独立渲染的，**画面必须完全由帧号决定**。
- 渲染时间 ≈ 帧数 × 每帧的绘制时间 ÷ 并发数。

**授权**：Remotion 对个人和小团队免费，公司商用可能需要购买授权，交付商业项目前提醒用户确认。

## 2. 模板工程结构

用 `python <skill>/scripts/new_project.py <目录>` 创建，结构如下：

```
<project>/
├── package.json             npm 脚本：studio / still / draft / render / typecheck
├── remotion.config.ts       编码参数：H.264、yuv420p、CRF 18、GL 后端
├── tsconfig.json
├── docs/brief.md            策划书
├── public/
│   ├── sfx/                 合成音效和 manifest.json（已自带）
│   ├── music/               配乐
│   ├── vo/                  配音
│   ├── fonts/               字体文件（需自行放入，见 README）
│   └── images/              图片素材
└── src/
    ├── index.ts             入口
    ├── Root.tsx             合成定义，尺寸、帧率、时长都来自 storyboard.json
    ├── Film.tsx             按 storyboard 把镜头排上时间轴，挂上音乐、音效、质感
    ├── storyboard.json      分镜数据
    ├── storyboard.ts        分镜的类型定义
    ├── theme.ts             视觉系统
    ├── lib/
    │   ├── motion.ts        缓动、弹簧、progress、mix、logZoom、stepped
    │   ├── time.ts          时间网格：beats()、sec()
    │   ├── fonts.ts         字体加载（等加载完成才渲染）
    │   └── shot.tsx         useShot()：在场景里拿到当前镜头的时长等信息
    ├── components/
    │   ├── Texture.tsx      颗粒、暗角
    │   ├── Camera.tsx       虚拟摄像机
    │   ├── Ascii.tsx        字符画
    │   ├── SfxTrack.tsx     把 events 放到时间轴上
    │   └── text/            SplitText、Typewriter、Decode
    └── scenes/
        ├── index.ts         场景注册表：storyboard 里的 scene 名字对应这里的组件
        ├── Statement.tsx    一句话 / 大字
        ├── TitleCard.tsx    片名 / 落版
        ├── AsciiSun.tsx     字符画示例
        └── CameraTour.tsx   虚拟摄像机示例
```

**加一个新镜头类型**：在 `src/scenes/` 写一个组件，在 `scenes/index.ts` 注册，然后在 `storyboard.json` 里用它的名字。场景组件里用 `useShot()` 拿到本镜头的 `duration`，用于安排退场。

## 3. 常用命令

```bash
npm install
npm run studio                                      # 浏览器预览，可拖时间轴
npx remotion still Film out/f0120.png --frame=120   # 渲染单帧
npm run draft                                       # 半分辨率快速预演
npm run render                                      # 正式渲染 out/film.mp4
npx remotion render Film out/part.mp4 --frames=300-599   # 只渲染一段
npx remotion render Film out/film.mp4 --concurrency=4    # 调整并发
npm run typecheck                                   # TypeScript 检查
```

## 4. 确定性规则（违反就会闪、会跳、会每次不一样）

- 不用 `Math.random()`，用 `random('种子')`（来自 `remotion`）。
- 不用 `Date.now()`、`new Date()`、`performance.now()`。
- 不用 CSS `transition`、`animation`、`@keyframes`。
- 不用 `setTimeout`、`setInterval`、`requestAnimationFrame` 驱动动画。
- 不用逐帧累加的状态（`useState` 每帧加一）。每一帧的状态都要能直接从帧号算出来。
- 粒子、噪声、抖动这些「随机」效果，都用带种子的函数。

## 5. 素材加载

- 所有本地素材放在 `public/`，用 `staticFile('images/a.png')` 引用。不要用网络地址，渲染时可能加载失败或变慢。
- 图片用 Remotion 的 `<Img>`，它会等图片加载完成再截图。
- 视频用 `<OffthreadVideo>`，比 `<Video>` 更稳定、帧更准。
- 音频用 `<Audio>`，放在 `<Sequence from={...}>` 里控制起点，`volume` 可以是帧的函数。
- 字体由 `lib/fonts.ts` 统一加载，在 `theme.ts` 的 `fonts` 数组登记即可。字体文件缺失时会在控制台警告并回退到系统字体，**渲染出的中文可能变成难看的字体甚至方块**，所以交付前一定要确认字体文件在。
- 自己写的异步加载（比如读图片像素做字符画），用 `delayRender()` 拿到句柄，完成后 `continueRender(handle)`。

## 6. Sequence 与时间

- `<Sequence from={30} durationInFrames={60}>` 里面的 `useCurrentFrame()` 从 0 开始计数，是**相对帧**。
- `<Series>` 可以把一串镜头首尾相接，不用手算 `from`。
- `TransitionSeries` 的转场会让相邻镜头重叠，总时长会减少（见 `camera-transitions.md`）。
- 音频、配音的时长，事先用 `media_durations.py` 或 `ffprobe` 读出来，写进 `storyboard.json`，不要在渲染时动态计算。

## 7. 性能

- `filter: blur()`、`backdrop-filter`、大面积的 `box-shadow` 和 `mix-blend-mode` 很耗性能，尤其是作用在大元素或很多元素上时。
- 几百个以上的粒子用 `<canvas>` 画。
- 大图先缩小到需要的尺寸（推镜头最多需要 1.5 到 2 倍）。
- 预演阶段用 `--scale=0.5` 或 `--frames` 只渲染局部。
- 3D 和运动模糊的镜头单独渲染，降低并发。

## 8. 编码与交付

- 默认 H.264、`yuv420p`、CRF 18，兼容性最好（微信、各种手机都能播）。**宽高必须是偶数。**
- 透明背景：`--codec=prores --prores-profile=4444`，或者 `--codec=vp9 --pixel-format=yuva420p` 输出 webm；图片格式要用 png（`--image-format=png`）。
- 交付前跑 `finalize.py`：两遍响度标准化到 -14 LUFS，音频转成 AAC 320k/48kHz，并加 `faststart`（让视频能边下边播）。

## 9. Windows 注意事项

- 工程放在纯英文路径下。
- 3D 用 `--gl=angle`（模板已设置）。
- 命令行里的路径用正斜杠或者加引号。
- 杀毒软件可能拖慢首次渲染（它会扫描下载的浏览器），首次慢是正常的。

## 10. 常见错误

| 现象 | 原因和解决 |
|---|---|
| 渲染卡住后超时 | 某个 `delayRender` 没有 `continueRender`。检查字体、图片、自定义加载逻辑 |
| 画面闪烁、每次渲染不一样 | 用了 `Math.random()`、CSS 动画或者逐帧累加的状态 |
| 中文变成方块或宋体 | 字体文件没放进 `public/fonts/`，或者 `theme.ts` 没登记 |
| 图片在第一帧缺失 | 用了普通 `<img>`，改成 `<Img>` |
| 3D 画面全黑或报 WebGL 错误 | GL 后端不对，Windows 用 `angle`，Linux 试 `angle-egl` 或 `swangle` |
| `preserve-3d` 不生效 | 父元素上有 `overflow: hidden`、`filter` 或 `opacity` |
| 版本不匹配的警告 | 所有 `@remotion/*` 包和 `remotion` 必须是同一个版本，统一改成同一个版本号再装 |
| 视频在微信或手机上黑屏 | 像素格式不是 `yuv420p`，或者宽高是奇数 |
| 音频爆音或太小 | 没做响度标准化，跑 `finalize.py` |
| 找不到场景组件 | `storyboard.json` 里的 `scene` 名字没有在 `scenes/index.ts` 注册 |
