---
name: openmontage-checkpoint-protocol
version: "1.0.0"
description: 管线各阶段的检查点写入与人工审批协议，支持故障恢复、人工监督和审计追踪。适用于阶段完成并通过审查后决定是否检查点及是否请求人工批准的场景。
metadata:
  license: AGPL-3.0
---

# 检查点协议 — 元技能

## 何时使用

在完成阶段工作并通过审查之后。本技能教你何时以及如何检查点，以及何时向人请求批准。它用指令驱动的协议取代了 Python `checkpoint_policy.py`。

检查点是管线的存档点。它们支持故障恢复、人工监督和审计追踪。

## 协议

### 第 1 步：检查清单策略

从管线清单读取当前阶段的配置：

```yaml
- name: idea
  checkpoint_required: true      # 必须检查点吗？
  human_approval_default: true   # 必须问人吗？
```

| `checkpoint_required` | `human_approval_default` | 行动 |
|----------------------|------------------------|--------|
| true | true | 检查点 + 提交人工批准 |
| true | false | 检查点 + 自动继续 |
| false | * | 完全跳过检查点（罕见） |

### 第 2 步：准备检查点数据

收集检查点所需的一切：

1. **阶段名称** — 刚完成哪个阶段
2. **状态** — `"completed"`（或需要批准时 `"awaiting_human"`）
3. **工件** — 本阶段产生的规范工件
4. **元数据** — 审查发现、成本快照、计时信息

### 第 3 步：写检查点

调用检查点工具：

```python
write_checkpoint(
    pipeline_dir,      # 项目工作目录
    project_name,      # 项目标识
    stage_name,        # 例如 "idea"
    status,            # "completed" 或 "awaiting_human"
    artifacts,         # {"brief": {...}} — 阶段输出
)
```

检查点工具会：
- 对照 schema 验证工件
- 强制执行审批门（受门控阶段没有 `human_approved=True` 不能写 `completed`）
- 将任何被取代的检查点归档到 `projects/<id>/history/`（阶段版本和门转换永不销毁）
- 将检查点 JSON 写入磁盘
- 包含时间戳和阶段元数据

规范位置：`projects/<project_id>/checkpoint_<stage>.json` —— 始终把仓库的 `projects/` 目录作为 `pipeline_dir` 传入（或使用 `lib.checkpoint.PROJECTS_DIR`）。始终传入 `pipeline_type` —— 门控执行通过它读取清单。

在管线初始化时（任何阶段之前），调用 `init_project()`：

```python
from lib.checkpoint import init_project
init_project("my-project", title="My Project", pipeline_type="cinematic")
```

这创建规范目录布局并写入 `project.json` —— Backlot 看板在首个检查点之前展示项目所需的标记。然后启动看板：`python -m backlot open my-project`（不可用时不致命 —— 看板是观察者，绝非阻断者）。

### 第 4 步：阶段内检查点（恢复支持 + 活性）

**进入任何阶段时，先写一个 `in_progress` 检查点。** 这是通过 Backlot 看板告诉用户阶段是活跃而非停滞的方式 —— 确定性比速度更重要。

长时间运行的阶段（如 `assets` 或 `compose` 循环）可能因 API 错误、速率限制或会话中断而中途失败。为了能从确切的失败点（例如场景 4）恢复：

1. **写部分进度**：每次成功生成重要项（例如一个场景的资源、一个 clip）时，写一个 `in_progress` 检查点。

   `in_progress` 检查点可以省略阶段的规范工件，但存储在已知工件名下的任何工件仍会通过 schema 验证。如果部分数据还不是有效的规范工件，把它存在 `metadata.partial_progress` 而不是 `artifacts` 下。
   ```python
   write_checkpoint(
       pipeline_dir, project_name,
       stage="assets",
       status="in_progress",
       artifacts={},  # 还没有完整的规范工件
       metadata={
           "partial_progress": {
               "asset_manifest_draft": partial_manifest_dict,
               "completed_scene_ids": completed_scene_ids,
           }
       },
   )
   ```
   如果部分工件已满足其 schema（例如 `asset_manifest` 有 `version: "1.0"` 和有效的 `assets[]` 条目），可以直接存在 `artifacts` 中。
2. **从部分进度恢复**：启动阶段时，始终检查是否存在该阶段的 `in_progress` 检查点。如何处理见第 7 步（恢复协议）。

### 第 5 步：人工批准（如需要）

**清单值是绑定的。** 管线清单中的 `human_approval_default` 是阶段是否门控的唯一真源。本技能绝不覆盖它，你也不能 —— 没有“这个情况特殊”。（`lib/checkpoint.py` 强制执行：对受门控阶段写 `status="completed"` 而无 `human_approved=True` 会抛出 `GATE VIOLATION` 错误。）

当 `human_approval_default: true` 时：

1. **以 `status="awaiting_human"` 写检查点**（不是 `completed`）。

2. **向人展示摘要**：
   ```
   ## Stage Complete: [stage_name] — awaiting your approval

   ### Artifact Summary
   [工件关键细节 — 标题、时长、关键决策]
   [如果 Backlot 看板在运行，指向它：工件在那里渲染]

   ### Review Findings
   [审查者摘要：N 个 critical（全部修复），N 个建议]

   ### Cost So Far
   [已花预算 / 总额，按工具细分]

   ### Action Required
   请审查并批准以继续，或提供修改反馈。
   ```

3. **结束你的回合。** 在同一响应中执行任何进一步的管线工作都是门控违规。“展示并继续”不是等待 —— 回合必须以问题结束，下一个管线动作必须由用户回复引起。

4. **对用户回复的处理：**
   - **批准** → 以 `status="completed"`、`human_approved=True` 重写检查点，然后进入下一阶段
   - **要求修改** → 带着人类反馈回到阶段导演技能，产生修订工件，重新审查，重新检查点（被取代的检查点自动保存在 `history/` 中）
   - **中止** → 停止管线

5. **批准是逐门的。** 之前的批准，无论多么宽泛（“看起来很好，继续做整个东西”），绝不覆盖后续的门。如果用户明确预授权整个运行，在他们说的时候记入 `decision_log`（`category: "approval_policy"`）—— 没有该条目，每个门都停。

6. **资源门审查故事板 —— 在任何草稿渲染之前。** `assets` 现在在每条管线中门控：逐场景展示生成的资源（Backlot 看板的胶片条是自然审查面），包括迄今花费和预计 compose 成本。在这里发现坏资源能省一次完整重渲染。

   **不要为了获得此审查而渲染草稿/完整合成。** 审查面是用逐场景资源填充的胶片条 —— 现成选择、生成静帧、旁白波形 —— *不是*渲染的视频。对于“资源”是工坊/定制合成（无可缩略图文件）的场景，Agent 写一张**逐场景审查静帧**到 `projects/<id>/snapshots/<scene_id>.png`（在代表帧的 `remotion still` —— 见 `skills/meta/bespoke-composition.md`）；看板在胶片条上展示它们。静帧落盘时刷新 `metadata.partial_progress`，然后在门处停下。草稿/最终渲染是 **compose** 阶段 —— 仅在资源门批准后运行。在资源阶段内渲染完整草稿跳过了用户本该持有的门。

### 第 6 步：确定下一阶段

检查点写入并批准（如需要）后：

```python
next_stage = get_next_stage(pipeline_dir, project_name)
```

读取所有现有检查点，返回下一个需要运行的阶段，或管线完成时返回 `None`。

### 第 7 步：恢复协议

在任何管线运行的 START（不仅是阶段之后），始终检查现有进度：

```python
next_stage = get_next_stage(pipeline_dir, project_name)
```

如果 `next_stage` 不是第一阶段：
1. 告知人类：“发现现有进度。从阶段恢复：[next_stage]”
2. **检查部分进度**：读取 `next_stage` 的检查点：
   ```python
   current_cp = read_checkpoint(pipeline_dir, project_name, next_stage)
   ```
   如果 `current_cp` 存在且状态为 `"in_progress"`，告知人类你正从阶段中间恢复。
3. **加载工件**：从检查点加载先前工件作为上下文。如果从 `"in_progress"` 恢复，先从 `current_cp["artifacts"]` 加载任何 schema 有效的部分工件。如果部分数据存在 `current_cp["metadata"]["partial_progress"]`，用该草稿数据及其完成标记（如 `completed_scene_ids`）跳过已完成的子任务。
4. **继续**：从下一个成功步骤继续生成，追加到部分工件。

如果存在状态为 `"awaiting_human"` 的检查点：
1. 告知人类：“阶段 [name] 正在等待你的批准”
2. 展示检查点数据供审查
3. 等待批准后再继续

### 样本检查点（参考驱动制作）

当制作是参考驱动时（存在 VideoAnalysisBrief），在提案批准和完整制作之间有一个额外检查点：

| 阶段 | checkpoint_required | human_approval_default | 备注 |
|-------|--------------------|-----------------------|-------|
| `sample` | true | true | 始终需要人工批准 |

样本检查点：
1. 展示：渲染的样本片段（10-15 秒）
2. 成本：样本成本 vs 预计完整视频成本
3. 行动：批准（→ 进入脚本）、修改（→ 重新生成样本）、中止

样本检查点不是管线阶段 —— 它是提案阶段内的子检查点。它不产生规范工件。它产生渲染的预览片段，存储在 `projects/<name>/assets/sample/sample_v{N}.mp4`。

**展示格式：**
```
## Sample Preview Ready

**Sample clip:** [path to sample_v1.mp4]
- Duration: [X] seconds (hook + 1 middle scene)
- Voice: [TTS provider + voice name]
- Visuals: [description — AI images, Remotion animations, etc.]
- Music: [source]

**Sample cost:** $[X.XX]
**Projected full video cost:** $[X.XX]

Does this feel right? I can adjust: voice, visual style, pacing, music, colors.
```

## 关键原则

1. **始终为完成的工作写检查点。** 即使 `checkpoint_required: false`，如果阶段耗时或花费显著，也考虑写检查点。丢失工作比磁盘上多一个文件更糟。

2. **创意阶段绝不跳过人工批准。** `idea` 和 `script` 塑造一切。为了省时间冲过它们会产生没人想要的视频。

3. **包含成本快照。** 人类在批准昂贵的下游阶段（assets、compose）之前应该知道已花多少、还剩多少。

4. **检查点支持恢复。** 如果管线在 `compose` 崩溃，人类可以重启并从 `compose` 继续 —— 不是从 `idea`。这是重点。

5. **批准请求要透明。** 不要只展示工件 —— 展示审查发现、成本和任何疑虑。帮助人类做知情决策。
