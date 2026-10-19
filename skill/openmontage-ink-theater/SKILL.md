---
name: openmontage-ink-theater
version: "1.0.0"
description: 提供水墨风格"动态艺术"创作方法，通过极简黑白视觉与吉祥物操作荒诞机关来演绎抽象概念，适用于动画管线的创意分镜与隐喻表达。
metadata:
  license: AGPL-3.0
---

# 水墨剧场（Ink Theater）

## 概览

水墨剧场是一套"白纸黑墨"的极简视觉体系：一个面无表情的吉祥物，通过操作一台荒唐的"低科技机关"，把抽象概念**物理性地演出来**。它不是一个固定场景库，而是一套通用方法加一个参数化引擎，运行在 `animation` 管线的 atelier 模式上，本身并不是独立管线。

风格标识：`ink-sketch`；引擎路径：`ink-theater/ink-theater.js`；运行时：HyperFrames（atelier）。

## 通用方法：概念 → 动态场景

隐喻生成分三步，这一步在智能体里完成，不写进代码：

1. **抽象概念 → 一个物理动作**：卡住、渗漏、叠加、分拣、发酵、推动、下沉、解开。
2. **系统 → 一个低科技物件**：压机、漏斗、井、罐子、传送带、梯子、桥、柜子、巨石、闸门、天平。
3. **吉祥物在物件上执行该动作**：摇柄、推、抽、盖章、打捞。**如果你把吉祥物删掉隐喻依然成立，那它只是装饰，必须重做。**

随后把动作编排成节拍，铺在同一张连续白纸上，配以镜头运动（平移、推近）。

## 可用原型（择一，细节自创）

| 原型 | 吉祥物动作 | 运动配方 |
|---|---|---|
| 机关 | 操作机器（摇柄/拉杆/泵） | 投料 → 摇柄 → 机器运转（蒸汽/仪表）→ 产物弹出 |
| 前后载荷转移 | 先被混乱压垮 → 松弛，一个关键动作 | 左侧混乱 → 橙色扫过 → 右侧结构拼装完成 |
| 旅途/陷阱 | 沿路径行走，掉坑或撞节点 | 路径绘出 → 行走 → 陷阱吞噬/节点弹出 → 蓝色回归环 |
| 一源多支 | 把单一来源拆分/切割 | 源头分裂 → 箭头指向 N 个分支 → 各分支各自行动 |
| 推/惯性 | 把巨石推上坡，巨石滚走 | 缓慢吃力上行（power1）→ 越过顶点 → 快速滚落（power2.in） |
| 井/提取 | 桶降入噪音，捞出珍宝 | 桶下降 → 捞取 → 拉上唯一有价值的部分 |

## 颜色语法（严格）

- **黑** = 结构与吉祥物
- **橙** = 仅用于流动与箭头
- **红** = 问题/警告
- **蓝** = 好的终态

纯白纸面，留白不少于 35%，主体占 40%–60%。吉祥物表情木讷（白点眼），绝不卖萌。

## 引擎速查（`InkTheater`）

- 线条：`inkPath(pts)`、`inkRibbon(pts,{width,taper})`（笔刷）。抖动：`boil(turbEl, tl, {duration})`。
- 运动：`ease.{settle,overshoot,bouncy,soft}`（seek 安全的弹簧）——弹出用 overshoot，到位用 settle，落地用 bounce。
- 角色：`mascot({x,y,scale})` → `.reachL/.reachR([x,y])`（FABRIK）。通过 GSAP `onUpdate` 跟随移动目标。
- 机械：`parts.{crank,gauge,hopper,slot,lever,box}`，自由组合。
- 完整 API 与确定性规则见 `ink-theater/README.md`。

## 角色：水墨傀儡与真实动作捕捉（不要手调运动）

需要角色行走、跳舞等时，**不要**手写运动（正弦曲线、逐帧摆姿势）。改用傀儡加**动捕动作库**：

- `InkPuppet.create(mount,{cx,ground,boil})` → `p.drawIn(tl,{start})`（自绘出场）→ `InkPuppet.choreograph(tl, p, [{clip:'walk'},{clip:'dance_spin'},{clip:'wave'}], {start})`。
- **阅读 `ink-theater/mocap/catalog.json`，为每个节拍挑选匹配的动作——要多样化，绝不要循环同一个 clip**（循环正是让视频显得重复的元凶）。目前共 12 个动作（均来自 CMU）：walk、run、climb、march、shuffle、jump、kick、sit、wave、twist、dance_spin、dance_glide。
- **动作不在目录里？** 运行 `node ink-theater/mocap/add-motion.mjs <name> <cmu-id|url|path> <category> "<desc>"`——它会抓取、转换（自动识别 fair1 / CMU / Mixamo 骨架）、重新打包并更新目录。免费 CMU 动捕（`una-dinosauria/cmu-mocap`）有数千条。之后把 `mocap/clips.js` 复制进项目。
- **对话气泡**（角色"说话"）：`InkTheater.balloon(tl, {into, overlay, at, dur, text, mouth:[x,y], center:[x,y], boil})`——用 HTML 文本，这样 webfont 才生效。

## 不可违背的原则

- **手写字体要嵌入完整字体，不要用 Google Fonts 的 subset woff2**（`css2` API 的 subset 缺少 basic-latin，会到处静默回退成衬线体）。使用内置的 `ink-theater/assets/patrickhand.ttf`（`@font-face … format("truetype")`），用在 **HTML 覆盖层 `<div>`** 上做字幕/对话气泡。不要热链 Google（会破坏确定性）。详见 `ink-theater/README.md` 的"font gotcha"。
- 确定性：闭式弹簧、抖动由时间线驱动、禁用 `repeat:-1`、只用带种子的 PRNG。
- 在 `window.__timelines` 上放一个暂停的 `gsap.timeline`。渲染前用 `lint` 加 `snapshot` 校验（并读 contact-sheet）。
- **免管线**：这是 `animation` / `character-animation` 管线上的一种风格加引擎，**不是** Rule-Zero 管线。不要为了找 `.yaml` 清单而卡住。

## 参考实现

- `projects/ink-theater-reel/` —— 能力展示片。
- `projects/ink-theater-momentum/` —— "Momentum"故事（手写字通过 HTML div 实现）。
