# 红果短剧编剧 · 短剧工业化编剧 Skill

一个给 [Codex](https://github.com/openai/codex) 用的短剧编剧技能：从选题立项、黄金开场、主线与节奏，到分集正文、台词打磨、可拍性与合规自检，全链路由一个剧本引擎串起来。

> 一句创意进，一部带付费墙的爆款剧本出。

---

## 它由两条来源合成

这个技能不是凭空写的，它把两条互补的来源焊在了一起：

| 来源 | 贡献 | 授权 |
|---|---|---|
| [`short-drama-factory` v3.2](https://github.com/lixiaoxiao9888-create/short-drama-factory) | 工业化结构引擎：情绪契约单元链、篇幅三档、60/80/100 与 30/40/50 集结构、三级付费墙、跨集连续性台账、机检脚本 | MIT |
| [红果短剧创作服务平台《短剧编剧第一课》01–10 期](https://github.com/kunhai-88/hongguo-shortdrama-screenwriting-course) | 平台视角的创作标准：选题评估、黄金开场、主线孵化、节奏分区、期待/悬念/钩子、情绪点编排、可拍性与过稿、台词打磨、网文转型 | 见下方「版权」 |

前者懂结构与体量，后者懂选题、情绪和落地。两者几乎不重叠，所以合起来的覆盖面比任何单一来源都宽。

---

## 能力

**三档篇幅**（先定档再动笔）

| 档位 | 时长 | 正文体量（实拍 / 漫剧） | 场景 | 单集拍数 | 全剧集数档 |
|---|---|---|---|---|---|
| 标准档（默认） | 90～120 秒 | 350～500 / 260～400 | ≤2 | 1 拍 | 60 / 80 / 100 |
| 长档 | 165～195 秒（约 3 分钟） | 650～850 / 520～680 | ≤3 | 2 拍 + 中段小钩 | 30 / 40 / 50 |
| 漫剧档 | 60～90 秒 | 260～400 | ≤2 | 1 拍 | 60 / 80 / 100 |

**八个交互模式**

| 上手方式 | 输入 | 产出 |
|---|---|---|
| `/立项大纲` `/策划` | 脑洞、题材或原著概况 | 选题评估五问 + 流派判定 + 档位判定 + 四幕大纲 |
| `/全剧大纲` `/卡点规划` `/长档大纲` | 已确认大纲 | 节奏曲线 + 付费墙卡点 + 情绪契约单元链 |
| `/分集规划 1-10` | 集数区间 | 单集冲突、场景、情绪流变、集尾钩子 + 台账更新 |
| `/写剧本 第N集` `/写长档 第N集` | 集数 + 情节 | 足额单集正文，过机检 |
| `/剧本医生` `/精修` | 草稿 | 台词七维暴改 + 断章打磨 + 复读检测 |
| `/极速短剧` `/直接写` | 小说片段或梗概 | 直出 1～5 集 |
| `/合规审核` `/落地自检` | 剧本正文 | 三类合规雷区 + 经济账与角色配额核查 |
| `/连写 1-10` | 集数区间 | 带台账的逐集批量生产 |

也可以直接用自然语言说「写短剧」「帮我立项：赘婿战神」「这集帮我看看」。

---

## 安装

```bash
git clone https://github.com/zhu5859243-free/hongguo-shortdrama-screenwriting.git
cd hongguo-shortdrama-screenwriting

mkdir -p ~/.codex/skills/hongguo-shortdrama-screenwriting
cp -R SKILL.md LICENSE agents examples references scripts templates \
      ~/.codex/skills/hongguo-shortdrama-screenwriting/
```

装好后直接对话即可，比如「用红果短剧编剧立项：赘婿战神」。

---

## 机检

技能自带两个确定性校验脚本，写完剧本必须过一遍，FAIL 不得裸交：

```bash
python3 scripts/validate_episode.py <单集剧本.md> --format auto|standard|long|manju
python3 scripts/validate_series.py <台账文件> --episodes 30|40|50|60|80|100
python3 scripts/validate_episode.py --self-test
```

单集机检覆盖：正文体量、单句句长、场景数、前 3 秒冲突、开篇废镜头词、断章卡点、长档中段小钩、跨集复读、情绪流变链、合规红线词，以及三项来自课程的检查——**E12 黄金三角**（身份/困境/目标）、**E13 上帝视角与心理描写**、**E14 对白为主**（OS/VO 不得超过对白的 1/3）。

---

## 目录结构

```text
.
├── SKILL.md                      # 技能入口：三道门、执行顺序、12 条红线、出稿双自检
├── SKILL-选型分析.md              # 四个候选技能的评审过程与合成方案
├── README.md
├── LICENSE                       # MIT（继承自 short-drama-factory）
├── agents/openai.yaml            # UI 元数据
├── references/                   # 18 个权威库
├── templates/                    # 立项大纲 / 台账 / 单集排版
├── scripts/                      # 单集与全剧机检
└── examples/                     # 标准档与长档单集示例
```

`references/` 里，`hongguo-course-01-10.md` 是课程总纲，`topic-and-ip-selection.md`、`golden-opening-toolbox.md`、`expectation-suspense-hook.md`、`emotion-point-playbook.md`、`pace-and-dialogue-craft.md`、`shooting-feasibility.md` 是课程各期的专项提炼；其余为结构引擎文件。

---

## 版权与致谢

- 结构引擎部分来自 [`short-drama-factory`](https://github.com/lixiaoxiao9888-create/short-drama-factory)，MIT 授权，许可证随本仓库保留。
- 课程部分来源为微信公众号「红果短剧创作服务平台」《短剧编剧第一课》01–10 期。**原文正文、图片与课程品牌版权归原公众号及相关权利方所有**；本仓库中的课程内容是对公开方法论的学习提炼与二次整理，非原文转载，各文件均标注了来源与原文链接。如需对外分发，请自行核对授权。
- 案例中的剧名、作品名称引用均用于说明方法论，版权归各自权利人。
