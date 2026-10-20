---
name: prompt-library
description: |
  提示词资产库与结构拆解技能 (Prompt Library Skill by hong hou zi)。
  对用户输入的提示词进行 6 要素结构拆解、8 种技巧识别、5 维度质量评估、适用性分析与智能归档。
metadata:
  trigger-words: [提示词库, 拆解提示词, 提示词资产, prompt-library, 提示词评估]
---

# Prompt Library Skill

提示词收集、拆解、存储、应用的完整技能包

## 功能概述

当用户发送提示词时，自动进行：
1. 结构拆解（6要素分析）
2. 技巧识别（8种常见技巧）
3. 质量评估（5维度评分）
4. 适用性分析（判断是否适合我）
5. 智能应用（自动融入系统设定）

## 触发条件

- 用户直接发送提示词文本
- 用户发送包含提示词的链接
- 用户发送截图/文件中的提示词
- 用户说"看看这个提示词"、"这个不错"等

## 执行流程

### Step 1: 接收确认
```
"收到一个关于[主题]的提示词，让我拆解一下"
```

### Step 2: 结构拆解
按照 `templates/disassembly-template.md` 进行6要素分析：
- 角色定义
- 任务描述
- 知识注入
- 推理框架
- 输出格式
- 约束条件

### Step 3: 技巧识别
按照 `references/techniques.md` 识别使用的技巧

### Step 4: 质量评估
按照 `templates/quality-matrix.md` 进行5维度评分

### Step 5: 适用性分析
判断是否适合融入我的系统：
- 高适用 + A/S级 → 建议应用
- 中适用 + A/S级 → 可考虑
- 低适用 → 仅收录

### Step 6: 存储与应用
- 按格式存储到 `prompt-library/[分类]/` 目录
- 更新README索引
- 若适用，融入SOUL.md/TOOLS.md

## 输出格式

完成拆解后，向用户报告：

```markdown
## 提示词拆解结果

**主题**: [提示词主题]
**来源**: [来源]
**评级**: [S/A/B/C/D] ([分数]/5)

### 核心结构
- 角色: [角色定义摘要]
- 任务: [核心任务]
- 技巧: [使用的技巧]

### 质量评估
| 维度 | 分数 |
|------|------|
| 清晰度 | X/5 |
| 完整性 | X/5 |
| 可执行 | X/5 |
| 鲁棒性 | X/5 |
| 创新性 | X/5 |

### 适用性分析
对我的适用度: [高/中/低]

### 应用建议
[是否应用、如何应用]
```

## 文件结构

```
skills/prompt-library/
├── SKILL.md                      # 本文件
├── scripts/
│   └── update-index.py          # 更新索引脚本
├── templates/
│   ├── disassembly-template.md  # 拆解模板
│   ├── quality-matrix.md        # 质量评估矩阵
│   └── storage-template.md      # 存储文件模板
└── references/
    ├── techniques.md            # 技巧识别参考
    └── quality-criteria.md      # 质量评估标准
```

## 与其他系统集成

### 存储
- 本地: `./prompt-library/`
- 远程: `https://github.com/q2522879285-source/prompt-library`

### 应用位置
| 提示词分类 | 应用位置 |
|-----------|---------|
| agent | SOUL.md |
| workflow | TOOLS.md |
| coding | TOOLS.md |
| video | USER.md 扩展 |
| writing | SOUL.md |
| creative | 灵活应用 |

## 维护

- 每周回顾新收录提示词
- 每月清理低效提示词
- 持续跟踪应用效果

---

创建时间: 2026-04-09
维护者: 索菲娅🦉
