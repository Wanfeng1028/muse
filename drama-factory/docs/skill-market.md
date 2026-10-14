# Skill 市场

Agent 技能的发布、安装与管理。Skill = 可复用的 prompt 模板（支持 `{{变量}}`
占位符），可按版本演进；安装后可在剧本 / 分镜生成时选用，其 prompt 模板会
真实注入大模型的 system prompt，Run 时间线会记录用了哪个 Skill 及版本。

## 数据模型（V15）

- `skills`：name / slug（唯一）/ description / author / category
（SCRIPT/BOARD/VIDEO/EDIT/GENERAL）/ tags / icon（Lucide 名）/
official / install_count / rating_sum / rating_count
- `skill_versions`：skill_id / version（语义化三段）/ prompt_template / changelog
- `skill_installs`：skill_id（唯一）/ version（安装时的版本，可升级/降级）
- `skill_ratings`：skill_id / score（1–5）/ comment
- `agent_steps.skill_id`：记录某步骤使用的 Skill

预设 4 个官方 Skill（随 V15 落地）：分镜大师（BOARD）、短剧钩子开头（SCRIPT）、
转场设计（BOARD）、爽点节奏（SCRIPT）。

## REST API（`/api/skills`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/skills` | 发布 Skill（自动建 1.0.0 版）→ 201 |
| GET | `/api/skills?q=&tag=&category=&sort=` | 检索；sort=popular/rating/newest/name |
| GET | `/api/skills/installed` | 已安装列表 |
| GET | `/api/skills/{id}` | 详情（版本列表倒序、最新 5 条评分、已安装版本） |
| POST | `/api/skills/{id}/versions` | 发布新版本 → 201 |
| POST | `/api/skills/{id}/install` | 安装（body.version 为空则装最新版；幂等） |
| DELETE | `/api/skills/{id}/install` | 卸载 → 204（未安装 → 404） |
| POST | `/api/skills/{id}/rate` | 评分 1–5 |
| POST | `/api/skills/{id}/render` | 渲染模板（宽松模式：缺失变量保留占位符） |

非法参数 → 400，不存在 → 404。

## Agent 调用链集成

- `POST /api/episodes/{id}/generate-script?mode=ai&skillId=`：
Skill 必须已安装；其模板用 `{剧集标题, 大纲}` 渲染后追加到剧本大模型
system prompt（`` 段）；响应 `usedSkill` 如 `"短剧钩子开头 v1.0.0"`。
- `POST /api/episodes/{id}/shots/from-script` body `{scriptText, skillId}`：
同理注入分镜大模型 system prompt。
- Run：`POST /api/runs` 支持 `scriptSkillId` / `boardSkillId`，写入对应
AgentStep 的 `skill_id`；执行时透传，Run 时间线追加
`"SCRIPT 使用 Skill: xxx v1.0.0"` / `"BOARD 使用 Skill: xxx v1.0.0"`，
toolCalls 的 input/output JSON 同样记录。
- 前端：分镜板「AI 生成剧本」旁有 Skill 下拉框（已安装列表），生成后
元信息行显示所用 Skill；`skills.html` 为市场浏览/安装管理/发布页。

## 测试

- `SkillServiceTest`（15）：发布校验、版本管理、检索排序、安装幂等、
卸载、评分、宽松渲染、resolveForUse。
- `SkillControllerTest`（5）：DTO 映射与透传。
- `SkillMarketFlowTest`（4，MockMvc）：发布→发版→安装→评分→升级/降级→卸载
全链路；分类筛选；slug 重复 400；非法评分 400。
- `SkillScriptGenerateTest`（2）：Skill prompt 真实透传到
`LlmScriptService.generate` 的第三个参数；不用 Skill 时传 null。
