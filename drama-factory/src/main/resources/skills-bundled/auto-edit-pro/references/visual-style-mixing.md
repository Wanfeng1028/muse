# 可复现的 71 风格混合

## 选择规则：语义与外观分离

先依据台词选择十种语义结构，再从已登记的风格池分配外观。新 Remotion 全屏舞台方案默认采用 `seeded-shuffle`，完整默认池包含原有 21 项与[扩展目录](react-bits-catalog.md)的新增 50 项，共 71 项，顺序与核心 `VISUAL_STYLE_IDS` 一致。不同风格可在同一视频共存，不为整条视频只选一种。每个完整 shuffle bag 包含池中各项一次；池大于一项时，跨 bag 边界也避免相邻重复。少于池大小的节拍只使用该 bag 的前几项，不额外插入无意义镜头来凑数。

记录全局种子、池与每段已分配的风格。固定 seed、输入和 pool 得到相同顺序；换 seed 可以得到另一组可复现组合。渲染、跳帧、并行导出与再次打开方案都不重新抽签。用户指定子池时只使用该子池；单项池允许重复。已保存的四风格池与旧配色保持不变，不因注册表扩容而扩池。风格变化不改变台词、结构、证据状态、字幕时间码或手势事实。

## 原有 21 种外观与官方参考

这里是根据参考方向创作的**本地原创、逐帧驱动实现**（local original frame-driven interpretations），不是直接复制 React Bits 源码，也不是上游网页组件的逐像素复刻。官方页仅用于确认视觉机制与参考方向；本地实现以持久化 seed 和 frame/fps 求值，不引入上游鼠标、滚动、摄像头、陀螺仪或真实时间驱动。以同一语义内容比较材质、空间和动势，而不是仅改变色号。

| ID / 官方参考 | 材质与构图方向 | 动势与阅读要求 |
|---|---|---|
| `balatro` / [Balatro](https://reactbits.dev/backgrounds/balatro) | 多色旋流、油墨状色带、深浅暖冷对照；文字使用清楚的实色或低干扰阅读层 | 流动只作用于背景表面；旋转/相位由帧计算，正文与证据不跟着扭曲 |
| `crt-warp` / [CRT Warp](https://reactbits.dev/backgrounds/crt-warp) | 复古荧光终端、扫描线、边缘晕影与弧形屏幕暗示；命令类标签可用等宽字体 | 使用低幅逐帧扫描与形变暗示；避免强闪烁，标题、数字和原字幕保持稳定可读 |
| `cubes` / [Cubes](https://reactbits.dev/animations/cubes) | 立体块面、阵列、明确的受光面/阴影面；适合表现模块组装，但块面不替代真实数据 | 块面波动、错相运动或空间起伏均以帧和固定参数计算；前景文字单独承载 |
| `hyperspeed` / [Hyperspeed](https://reactbits.dev/backgrounds/hyperspeed) | 消失点、纵深光轨、暗底高亮的速度空间；能量沿明确方向聚集 | 光轨投影与相位由帧计算；速度感留在表面，不让整屏正文运动，也不伪造性能提升数字 |
| `shape-waves` / [Shape Waves](https://reactbits.dev/backgrounds/shape-waves) | 暖纸色、绿锈与陶土色的方/圆/三角形波阵 | 几何形状在分层波场中错相起伏；正文保留独立阅读层，不由装饰形状拼造新含义 |
| `ripple-distortion` / [Ripple Distortion](https://reactbits.dev/animations/ripple-distortion) | 青蓝水波、折射环纹与波心传播 | 只形变本地程序化背景；证据正文、截图、原字幕和人物不接受波纹形变 |
| `evil-eye` / [Evil Eye](https://reactbits.dev/backgrounds/evil-eye) | 暗紫与黄绿的极坐标火焰虹膜、竖向瞳孔 | 眼形作为装饰而非真实观察或跟踪证据；视向与相位从帧和种子计算 |
| `electric-border` / [Electric Border](https://reactbits.dev/animations/electric-border) | 琥珀电弧轮廓、边缘能量与暖黑底 | 电弧仅在组件边框附近变化；文字区不闪烁，不把边框电弧当成执行状态证明 |
| `lightning` / [Lightning](https://reactbits.dev/backgrounds/lightning) | 冷电蓝、分叉闪电与深靛空间 | 有限幅度的逐帧放电，不采用整屏白闪；光效不覆盖证据和字幕 |
| `grid-motion` / [Grid Motion](https://reactbits.dev/backgrounds/grid-motion) | 青灰与暖橙的倾斜卡片网格、多行反向视差 | 抽象格面按种子与帧移动；无批准素材时不填入产品图、人物照或伪证据 |
| `waves` / [Waves](https://reactbits.dev/backgrounds/waves) | 浅苔纸色、深青竖向曲线与柔和陶土点缀 | 密集曲线由平滑波场推动，不驱动正文浮动；内容密集段保留安静阅读层 |
| `metallic-paint` / [Metallic Paint](https://reactbits.dev/animations/metallic-paint) | 冷灰金属反光、明暗流线与液态涂层 | 仅处理程序化装饰或明确批准的装饰资产；金属形变不扭曲证据正文、商标或原片 |
| `circular-carousel` / [Circular Carousel](https://reactbits.dev/components/circular-carousel) | 暖紫金色的环形卡面、透视缩放与深度排序 | 默认使用抽象几何；有明确批准时才使用真实资产，轮播不是新增产品、案例或事实的许可 |
| `micro-slats` / [Micro Slats](https://reactbits.dev/backgrounds/micro-slats) | 浅紫灰底的密集短栅片、倾斜与细微高光 | 本地确定性波场替代鼠标流体驱动；细节置于正文之后，避免形成干扰阅读的栅格 |
| `ghost-fibers` / [Ghost Fibers](https://reactbits.dev/backgrounds/ghost-fibers) | 墨绿底、多层薄纤维与浅色微光 | 细线层逐帧扭转，减少抢眼密度；不声称是真实数据轨迹 |
| `acid-squares` / [Acid Squares](https://reactbits.dev/backgrounds/acid-squares) | 酸黄绿与粉红方形场、密度节奏和波状深度 | 方格发生局部形变/位移，正文保持稳定；不以高速闪烁代替动势 |
| `light-tunnel` / [Light Tunnel](https://reactbits.dev/backgrounds/light-tunnel) | 暖橙金色线缆隧道、消失点与径向纵深 | 光脉冲沿隧道推进；视觉方向明确，不制造虚假的速度/性能数字 |
| `light-pillar` / [Light Pillar](https://reactbits.dev/backgrounds/light-pillar) | 紫青双色的纵向体积光柱与柔和扭转 | 光柱逐帧流动，主要位于装饰表面；来源、正文和字幕不随光柱旋转 |
| `floating-lines` / [Floating Lines](https://reactbits.dev/backgrounds/floating-lines) | 石墨蓝底、桃色与冰蓝的多束横向漂浮曲线 | 上中下曲线束错相漂移；曲线不冒充因果连线或源数据路径 |
| `grid-scan` / [Grid Scan](https://reactbits.dev/backgrounds/grid-scan) | 森林黑底、浅绿透视网格与扫掠高亮 | 扫描完全由当前帧计算，不访问 webcam/gyro；扫描样式不意味着真实系统检查通过 |
| `prismatic-burst` / [Prismatic Burst](https://reactbits.dev/backgrounds/prismatic-burst) | 紫橙折射棱镜、放射光束与径向折转 | 棱镜光束按帧旋转/扩张；限制装饰覆盖，保持数字与证据文字形状不变 |

新增 50 项的目录与选择命令见 [React Bits 扩展目录](react-bits-catalog.md)。所有 71 项仍可按场景随机混合；组件类使用列表、卡面、导航等抽象装饰与对应材质，不自动更换语义内容为交互网站。

颜色可依组件内容调整；不要求整片蓝色。新增 17 风格的默认背景三色来自各自 palette 的 `accent / line / canvas`，语义文字使用 `foreground / muted` 与阅读表面；原四风格已有颜色与材质保留。`intensity` 同时影响各效果的运动参数与背景纹理不透明度（`0.25 + 0.75 × intensity`），不影响正文不透明度；减小该值仍需结合表面遮罩、对比度与实际帧验证阅读效果。自动规划对证据/数据段使用 `.25`，其他段使用 `.65`。自定义 `colors` 只替换背景三色，不修改文字 palette/material。

优先在组件舞台表面渲染装饰，文字/来源标签在其上；保持源视频背景和连续音轨。允许设计明确的全屏包装，但并非选择某种风格后就自动替换真实背景。`surface: "transparent"` 时遵循透明底面的意图，不重新铺上不透明的特效底。动画/组件类只增加视觉层，不自动添加假素材或改变台词：轮播/格阵默认使用抽象几何，真实资产须有批准；波纹与金属涂层不作用于证据正文、来源截图、字幕或人物原片。

## 故事板合同

```ts
// Canonical IDs are maintained in core/src/visual-styles.ts and catalog-styles.ts.
import type {VisualStyleId} from '../packages/core/src/visual-styles';

// Optional beat field. uint32 means an integer from 0 through 4294967295.
visualStyle?: {
  id: VisualStyleId;
  seed: number;       // uint32, persisted per beat
  intensity: number;  // 0..1
  colors?: [string, string, string]; // backdrop-only hex triple; text palette/material stays tied to its ID
};

// Optional storyboard field. Per-beat assignments are persisted, not inferred on render.
styleMix?: {
  mode: 'seeded-shuffle';
  seed: number;       // uint32
  pool: VisualStyleId[];
};
```

示例（显式保留原四项子池，不是 71 项默认池）：

```json
{
  "styleMix": {
    "mode": "seeded-shuffle",
    "seed": 20260929,
    "pool": ["balatro", "crt-warp", "cubes", "hyperspeed"]
  },
  "visualStyle": {
    "id": "balatro",
    "seed": 42,
    "intensity": 0.6,
    "colors": ["#112237", "#F7784D", "#66DBC7"]
  }
}
```

此例并列展示两个层级字段：`styleMix` 放在 storyboard 根，`visualStyle` 放在各个 beat；不要把整个示例当成完整故事板。旧故事板没有这些字段时保持旧审美，不在加载时补字段或重新套混合风格。

## CLI 与复用

```bash
# Real video: Gate A only; default pool includes all 71 registered styles.
npm run package-video -- --video INPUT.mp4 --srt INPUT.srt --out RUN --renderer remotion --captions burned-in --style-mix seeded-shuffle --style-seed 20260929

# Explicit original four-style subset; style choice is not execution approval.
npm run package-video -- --video INPUT.mp4 --srt INPUT.srt --out RUN --renderer remotion --captions burned-in --style-mix seeded-shuffle --style-seed 20260929 --style-pool balatro,crt-warp,cubes,hyperspeed

# New-style subset for a new Gate A plan.
npm run package-video -- --video INPUT.mp4 --srt INPUT.srt --out RUN_NEW --renderer remotion --captions burned-in --style-seed 20260929 --style-pool waves,metallic-paint,grid-scan

# New plan using original palette/material behavior.
npm run package-video -- --video INPUT.mp4 --srt INPUT.srt --out RUN_LEGACY --renderer remotion --captions burned-in --style-mix legacy

# Explicitly requested synthetic examples only; no source-media input.
npm run demo:styles -- --out DEMO_DIR
```

`--style-mix` 接受 `seeded-shuffle` 或 `legacy`；`--style-seed` 接受 uint32；`--style-pool` 使用逗号分隔的已登记 ID。重新制作另一组随机方案应使用新的 Gate A 输出目录和新 seed；后续 Gate B/C/D 继续已审定故事板，不在后台替换风格分配。HyperFrames 只使用 legacy 布局/风格，混合风格交由 Remotion。

现有组件演示命令生成**覆盖原四风格的三个合成组件 MP4 预览、静帧和画廊**，不是 71 项全览。仅要求升级风格时，不额外交付展示样例；内部逐帧和导出测试只作为实现验收。用户明确要求组件演示时，检查实际 MP4 的探测信息、完整解码与代表帧，画廊只作为查看入口。它不读取用户真实视频，也不代表真实项目完成 Gate C/D；真人视频包装仍执行 Gate A → 获批后的 B/C → 单独获批的 D。

可复用提示词：

```text
用 $auto-edit-pro 包装这条视频。新方案采用 71 项默认风格池，以 seeded-shuffle 混合，seed=20260929；若续做已保存方案，则保留其中的池与逐段分配。语义结构跟随台词，视觉风格独立随机；短片不为凑满风格增添镜头，保留源片、原声、证据与字幕接棒。先生成 Gate A，后续沿用获批分配。
```

## 扩展候选：先研究、再适配、最后入池

2026-09-29 已核对新增 17 项官方页面及 [React Bits 组件源目录](https://github.com/DavidHDev/react-bits/tree/main/src/content)的对应视觉机制；逐项 page/source/mechanism 记录位于本地 renderer 的 `styles/extended-a.tsx` 与 `styles/extended-b.tsx`。该记录说明参考来源，不表示复用了上游实现。

2026-09-29 本次又核对并加入 50 项（20 背景、15 动画、15 组件）；Aurora、Dither、Threads 已从候选转为注册实现。每项官方页、源码路径、视觉机制与本地适配差异见[扩展目录](react-bits-catalog.md)及三个机器可读 JSON 清单。仅作为未来候选、尚未注册的条目仍不得加入随机池。

新增时先重新检查[官方目录](https://github.com/DavidHDev/react-bits/blob/main/src/constants/Categories.js)、官方预览和具体实现条件。决定独立原创实现还是适配上游代码；若采用上游代码，另行核实该文件的许可、归属、依赖与素材，保留必要声明，不把上游许可等同于本仓库许可。移除鼠标/hover 依赖、实时定时器和不确定随机，转换为 seed + frame/fps 的可跳帧实现。验证透明度、文本对比度、同帧重复渲染、不同帧可见变化、源背景连续性与真实 MP4，再把 ID 加入 schema、注册表、shuffle 测试和可选池。仅浏览到一个好看的网页不等于已经支持该风格。

## 验收边界

- 同 seed、输入和 pool 的新规划输出相同风格顺序；以至少 142 项分配检验两个完整默认 bag，每个完整 bag 覆盖 71 项一次；多项池没有相邻重复。
- 短片不插入凑数镜头；旧四项及 21 项 pool 固定 seed 的顺序和保存内容保持不变；50 个本次新增 ID 都能通过真实 Gate A CLI。
- 打乱渲染帧顺序后，同一帧仍相同；同一风格有实际逐帧变化，不是海报替换。
- 修改 style seed 不改变台词、语义结构、原声时间轴或事实归属。
- 旧故事板渲染保持旧外观；HyperFrames 不静默忽略新字段。
- 每种风格都检查装饰/正文/证据/字幕层次。风格丰富度不代替十种结构的语义验收。
