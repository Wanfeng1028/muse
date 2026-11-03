# 「爆款开场计划」剧本专用skill

由灵蟹创作（SoloEnt）研发，辅助创作者从一个梗到能够写出5分钟短剧剧本的创作 skill。通过逐阶段确认，把创意推进为可拍摄的五分钟短剧剧本，重点控制前 30 秒入戏、首尾承诺兑现和设定一致性。

## 安装

```bash
git clone https://github.com/SoloEnt-AI/5min-drama-contest.git ~/.codex/skills/5min-drama-contest
```

重启 Codex 或开始新会话后即可使用。

## 使用

```text
$5min-drama-contest 帮我从一个想法开始创作五分钟短剧大赛剧本。
```

也可以直接说：

- “帮我写一个五分钟短剧大赛剧本。”
- “按都市赛道写一个五分钟短剧，一开场就入戏。”
- “我有一个脑洞，帮我做成五分钟短剧。”

## 工作流

1. 锁定赛道、故事种子、核心立意、结构原型与视觉形态。
2. 建立世界规则、角色图谱与原型支点。
3. 锁定主叙事重心、前 30 秒开场与结尾兑现。
4. 生成四幕因果推进的五分钟卡点大纲。
5. 分幕完成正式剧本，并按需转换为分镜脚本。

## 目录

```text
.
├── SKILL.md
├── agents/
│   └── openai.yaml
├── assets/
│   └── icon.png
└── references/
    ├── archetypes.md
    ├── beats-5min.md
    ├── centers.md
    ├── format-formal.md
    ├── format-storyboard.md
    └── tracks.md
```
