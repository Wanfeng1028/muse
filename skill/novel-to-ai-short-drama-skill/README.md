# 导演视角 Skill

一个面向 AI 短剧生产的中文 Codex Skill。它把小说、网文或故事片段改编成具有明确成片时长、分场节拍、表演调度、镜头语言、声音设计和生成连续性的导演分镜台本。

## 核心能力

- 小说叙述、心理活动与背景说明的视听化改写。
- 开场钩子、冲突升级、转折、高潮与尾钩的节拍规划。
- 按目标成片时长建立逐镜时间码，镜头秒数严格闭合。
- 标注景别、机位、角度、运镜起止和叙事动机。
- 将抽象情绪拆成演员可以执行的动作、视线、停顿和道具行为。
- 维护角色、服装、伤势、空间轴线、视线和关键道具连续性。
- 将复杂场面拆成适合 AI 视频生成的原子镜头，并标注后期处理风险。

## 必填输入

使用时至少提供：

1. 小说正文、故事片段或可读取的文件。
2. 单集成片时长，例如 30 秒、60 秒、90 秒或 2 分钟。

若未提供单集时长，Skill 会先追问，不会自行假设。多集改编还需提供总集数或本次改编范围。画幅未指定时默认使用 9:16 竖屏。

## 默认交付内容

1. 改编规格与本集戏剧任务。
2. 必要的保留、压缩、外化和新增说明。
3. 分场节拍与时长账本。
4. 含景别、机位、运镜、表演、对白、声音及 AI 备注的逐镜导演台本。
5. 角色、场景和道具连续性锚点。
6. 时长、原作保真、连续性与 AI 可生成性校验。

## 仓库结构

```text
novel-to-ai-short-drama/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── adaptation-workflow.md
│   ├── deliverable-template.md
│   ├── directing-language.md
│   └── quality-gates.md
├── examples/
│   └── 测试结果.md
├── scripts/
│   └── validate_skill.py
├── .github/
│   └── workflows/
│       └── validate.yml
├── .gitattributes
├── .gitignore
├── LICENSE
└── requirements-dev.txt
```

## 安装

将仓库克隆到 Codex 的个人技能目录：

### Windows PowerShell

```powershell
git clone <你的仓库地址> "$env:USERPROFILE\.codex\skills\novel-to-ai-short-drama"
```

### macOS / Linux

```bash
git clone <你的仓库地址> ~/.codex/skills/novel-to-ai-short-drama
```

重新启动 Codex 或开启新任务后即可使用。

## 使用示例

```text
请使用 $novel-to-ai-short-drama，把下面的小说片段改编成一集 60 秒、9:16 竖屏的 AI 短剧导演分镜台本：

[粘贴小说正文]
```

完整的狼人、霸总、校园对照测试见 [examples/测试结果.md](examples/测试结果.md)。每组都包含同一原文的普通剧本化结果和 Skill 导演化结果。

## 本地校验

```bash
python -m pip install -r requirements-dev.txt
python scripts/validate_skill.py
```

GitHub Actions 会在推送和 Pull Request 时自动执行相同校验。

## 许可证

本项目采用 [MIT License](LICENSE) 开源。
