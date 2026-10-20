# AI 影视流水线 Skill（LingCut + LibTV + ffmpeg）

> 一套被**一部 25 分钟古装片**（180+ 镜头、总成本约 23 元）实战验证过的 AI 影视生产流程。
> 固化成 Claude / DSH 的 Agent Skill，也可以当纯文档读。

---

## 这是什么

用 **LingCut 无限画布**（lingcut.cn）生成分镜图与视频、**LibTV** 生成配音与旁白、
**ffmpeg** 拼接成片，最后交付一个**开箱即用的剪辑工作台**（含新旧版本对照）。

**不是"提示词大全"，是一份踩过坑的施工手册。**

---

## 三个最值钱的知识点

### ① 尾帧接续法 —— 免费模型做付费长镜

LingCut 免费模型时长上限只有 12 秒。但剧本经常需要 20 秒的一镜到底。

**解法**：抽 A 段的**尾帧**当 B 段的**首帧**，两段拼起来。

```
A 段(12s) → ffmpeg 抽尾帧 → 上传成图片节点 → B 段(10s) 引用它 → concat
```

实测：20.29 秒长镜，**接缝肉眼无感**，成本 0 元（付费模型同样效果要 6 元）。

→ `references/04-LONGSHOT.md`

### ② 道具基底引用法 —— 解决"每封信都一样"和"字写不对"

AI 画中文极不可靠，很多人的做法是在提示词里写「字迹虚化不可读」来**躲**。
这是把问题藏起来。

**解法**：先生成一张**干净空白**的道具基底图，再让每个镜头**引用它**单独生成。
基底保证材质一致，单独生成保证内容各异，而且模型有全部注意力去写字。

实测：**12 张信纸全部写对**（含「别让你儿子去修仙」8 字全对），每张内容都不同。

→ `references/05-ASSETS.md`

### ③ 返工循环 —— 占总工时 45%

第一次生成的东西**一定有一堆问题**。预算必须给返工留一大半。

关键是**自动审计**：把分镜表和画布 JSON 逐镜比对，自动找出
①缺台词 ②台词不全 ③没写声音方向 ④缺专用特写图。

实测：186 镜逐字比对，找出 66 处缺陷。

→ `references/01-PIPELINE.md` 第 ⑧ 节

---

## 目录结构

```
.
├── SKILL.md                        主入口（14 条铁律 + 速查）
├── references/
│   ├── 01-PIPELINE.md              12 阶段总纲 ★
│   ├── 02-LINGCUT-PROMPT.md        提示词规范
│   ├── 03-CINEMATIC.md             电影感五条铁律
│   ├── 04-LONGSHOT.md              ★ 尾帧接续法
│   ├── 05-ASSETS.md                ★ 道具基底法
│   ├── 06-CONTENT-POLICY.md        ★ 内容审核规避
│   ├── 07-AUDIO.md                 台词归属 + 声音性别
│   ├── 08-ASSEMBLY.md              拼接 / 混音 / 漏镜检测
│   ├── 09-DELIVERY.md              剪辑工作台 + 抖音发布
│   ├── 10-TROUBLESHOOTING.md       ★ 报错对照表（24 类）
│   ├── 11-LINGCUT-AUTOMATION.md    画布自动化
│   ├── 12-CHARACTER-ASSET.md       角色定板
│   ├── 13-DRAMA-RULES.md           工业化规则
│   └── archive/                    已作废但保留的
├── scripts/                        可复用脚本（24 个 + README）
├── playbook/PLAYBOOK.md            历史经验库
└── prompts/EXAMPLES.md             提示词模板
```

---

## 快速开始

### 1. 装成 Agent Skill

```bash
# 拷到你的 skill 目录
cp -r . ~/.dsh/skills/lingcut-video        # DSH
# 或 ~/.claude/skills/lingcut-video         # Claude Code
```

### 2. 配置（只改一个文件）

```bash
vim scripts/_config.mjs
```

或用环境变量覆盖：

```bash
LINGCUT_PROJECT    你的项目根目录
LINGCUT_TOOLS      tools 目录（ffmpeg / chrome-profile）
LINGCUT_PW         playwright-core 的 index.js 路径
LINGCUT_CHROME     Chromium 可执行文件
LINGCUT_FFMPEG     ffmpeg 可执行文件
LINGCUT_PROJECT_ID 画布项目 ID
```

自检：

```bash
node -e "import('./scripts/_config.mjs').then(m=>console.log(m.PROJ, m.CHROME, m.FFMPEG))"
```

### 3. 典型流程

```bash
node scripts/lingcut-login.mjs           # 登录画布
node scripts/lingcut-make.mjs new        # 建节点
node scripts/lingcut-make.mjs gen        # 生成
node scripts/lingcut-audit.mjs           # ★ 审计（找缺台词/缺声音）
node scripts/lingcut-split.mjs L11 cfg.json   # ★ 长镜拆分
node scripts/lingcut-download-all.mjs    # 下载全部素材
node scripts/rebuild-film.mjs            # ★ 逐章→三卷→全片
node scripts/build-editdesk.mjs          # ★ 生成剪辑工作台
```

---

## 前置条件

- **LingCut 订阅会员** + 账户余额（免费模型不限量，付费模型按秒计费）
- 画布「API 设置」里配置好上游密钥
- 凭据放 `<项目>/.secrets/`（**本仓库不含任何凭据**）
- Node.js + ffmpeg + playwright-core + Chromium

---

## 成本参考（实测一部 25 分钟片）

| 项目 | 单价 |
|---|---|
| 分镜图 | 0.06 元/张 |
| **免费视频** | **0 元**（5/8/10/12 秒）|
| 付费 wan3 | 0.3 元/秒（5–30 秒）|
| 付费 Seedance | 4.2 元/条（15 秒）|

**全片 ≈ 23.5 元**（图 ~15 元 + 1 个付费镜 2.4 元 + 配音约 30 积分；
190+ 个免费视频 = 0 元）

> ⚠️ **任何付费操作前都必须跟用户报备并获批。**

---

## 三条最容易翻车的

1. **限流 ≤5 次/分钟（失败的也算）** → 节流 13 秒，一批跑完再提下一批
2. **改画布数据必须用引擎 `updateNodeData(id, patch, true)`** —— 直接 PUT 会被自动保存覆盖
3. **提示词必须从 UI 的 `contenteditable` 打进去** —— 只改节点数据不生效

---

## 隐私说明

这个仓库发布前经过**脱敏处理**：

- ✅ 无任何 API key / 密码 / 邮箱 / Cookie
- ✅ 无个人文件系统路径
- ✅ 无画布 / 项目 ID
- ✅ 示例中的角色名与地名已泛化

**所有凭据都应该放 `<项目>/.secrets/`，永远不要提交进 Git。**

---

## 许可

MIT —— 见 `LICENSE`。

本项目与 LingCut（lingcut.cn）、MiniMax、LibTV 的开发商均无关联。
「LingCut」等名称与商标归各自所有者。

---

## 致谢

本 skill 里的每一条「实测踩坑」，都是真的烧过钱、返过工之后写下来的。
如果你用它做出了东西，欢迎把新踩的坑补进 `playbook/PLAYBOOK.md` ——
**这是这套文档能持续变强的唯一机制。**
