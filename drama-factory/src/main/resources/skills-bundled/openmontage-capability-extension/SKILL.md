---
name: openmontage-capability-extension
version: "1.0.0"
description: 当生产需求无现有工具覆盖时，按结构化协议扩展系统能力，涵盖临时脚本、自定义 playbook、新技能文档和工具包装器。适用于遇到能力缺口并需要合规填补的场景。
metadata:
  license: AGPL-3.0
---

# 能力扩展协议

## 何时使用

当遇到现有工具无法覆盖的生产需求时。Agent 可以扩展系统——但有护栏。本协议取代了一刀切的“不要写临时 Python 脚本”规则，改为结构化流程。

## 先评估

在写任何东西之前，先对缺口分类：

| 缺口类型 | 示例 | 行动 |
|----------|---------|--------|
| **一次性转换** | 自定义图像裁剪、色彩调整、格式转换 | 写项目级 Python 脚本 |
| **重复性视觉需求** | 新插画风格、自定义图表类型 | 生成自定义 playbook 或 Remotion 组件 |
| **缺失的 provider** | 用户想要注册表中没有的特定 API | 创建最小工具包装器 |
| **缺失的知识** | Agent 不知道如何提示某个模型 | 用网络搜索学习，然后记录为 Layer 3 技能 |

## 临时脚本规则

脚本仅在以下情况允许：
1. 无现有工具覆盖该需求（通过 preflight 对照注册表验证）
2. 脚本幂等（可安全重跑）
3. 脚本在项目工作区产生文件工件
4. 脚本记入决策日志：`category: "capability_extension"`
5. 用户被告知：“我为 X 写了自定义脚本，因为没有现有工具处理 Y”
6. 脚本未经用户批准不调用外部 API

脚本放在：`projects/<project-name>/scripts/`

### 脚本模板

```python
"""<脚本功能一句话描述>

由能力扩展协议创建，因为：<没有现有工具覆盖的原因>
决策日志条目：<decision_id>
"""
import sys
from pathlib import Path

def main(input_path: str, output_path: str) -> None:
    # 幂等：检查输出是否已存在
    out = Path(output_path)
    if out.exists():
        print(f"Output already exists: {out}")
        return

    # ... 转换逻辑 ...

    print(f"Created: {out}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

## 自定义 Playbook 规则

当现有 playbook 不匹配需求时：
1. 用 `lib/playbook_generator.py` 创建新 playbook
2. 尽可能基于最接近的现有 playbook
3. 对照 `schemas/styles/playbook.schema.json` 验证
4. 保存到 `styles/custom/<project-name>.yaml`
5. 记录决策：`category: "playbook_selection"`、`subject: "custom playbook created"`

## 新技能规则（技术学习）

当 Agent 在网络研究中发现技术知识时：
1. 记录为项目级技能：`projects/<project-name>/skills/<name>.md`
2. 遵循 Layer 3 技能格式：
   - Provider 名称和版本
   - Provider 特定的提示模式
   - 此用例的最佳参数
   - 质量提示和已知失败模式
   - 信息来源 URL
3. 在决策日志中引用
4. 如果普遍有用，建议提升到 `.agents/skills/`

## 工具包装器规则

当用户需要注册表中没有的特定 provider 时：
1. Agent 可以创建最小的 `BaseTool` 子类
2. 保存到 `projects/<project-name>/tools/<name>.py`
3. 必须继承 `BaseTool` 并实现完整合约（input_schema、execute、capabilities 等）
4. 使用前必须注册
5. 记录决策：`category: "capability_extension"`
6. 首次付费 API 调用前需要用户批准

## 仍然禁止的事项

- 绕过管线（所有生产仍通过阶段）
- 在用户不知情的情况下调用外部 API
- 修改 `tools/` 中的现有工具（创建包装器，不要修改原件）
- 跳过决策日志
- 编写超出输出文件副作用的脚本（不发送邮件、不推送远程、不删除项目工作区外的文件）

## 决策日志条目格式

每次扩展必须记录：

```json
{
  "decision_id": "ext-001",
  "stage": "<current stage>",
  "category": "capability_extension",
  "subject": "Created custom <script|playbook|skill|tool> for <purpose>",
  "options_considered": [
    {"option_id": "existing-tool", "label": "<closest existing tool>", "rejected_because": "<why it doesn't work>"},
    {"option_id": "extension", "label": "<what was created>", "reason": "<why this approach>"}
  ],
  "selected": "extension",
  "reason": "<concise justification>",
  "user_visible": true,
  "confidence": 0.8
}
```
