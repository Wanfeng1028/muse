# OpenAgents 移植第 4 轮（抄清单 8 + 7）

adapter/game 清单规范先行 + 能力匹配派单结构化打分版；LLM 兜底后置（只移植 prompt 构建与响应解析，不调用 LLM）

---

## 1 原版规格（已从 openagents-develop.tar.gz 提取核实）

### 1.1 NormalizedCapability

| 字段 | 说明 |
|---|---|
| `agent_id` | 代理唯一标识 |
| `agent_type` | `"a2a"` 或 `"local"` |
| `skills` | `string[]`，代理可执行的技能 |
| `tags` | `string[]`，分类标签 |
| `input_modes` | 默认 `["text"]` |
| `output_modes` | 默认 `["text"]` |
| `description` | 自由文本描述 |
| `raw_capabilities` | 原始能力字典，保留完整信息 |

### 1.2 normalize_a2a

- 遍历 A2A agent 的 `skills` 数组，对每个 skill 取 `tags` / `input_modes` / `output_modes` 并集
- 并集为空时回落 `["text"]`
- `raw_capabilities` 存原始 A2A 字典

### 1.3 normalize_local

- 结构化 `skills` 取 `id` / `name`，`tools` / `abilities` / `functions` 并入 `skills`
- `tags` / `categories` / `labels` 并入 `tags`
- `input_modes` / `output_modes` 非列表时回落 `["text"]`
- `raw_capabilities` 为原字典

### 1.4 match_structured_capabilities（原版布尔匹配）

ALL 语义：`skills` / `tags` / `input_modes` / `output_modes` 四个维度，每个非空维度的所需集合必须是已声明集合的子集才通过；空维度恒过（不参与拦截）。返回布尔值。

### 1.5 LLM 兜底

- `DEFAULT_MATCHING_PROMPT`：构建 prompt，解析结果中 `matches` 仅当 `confidence >= 0.5` 时为 `true`
- `parse_llm_response`：
  - 剥离 markdown 围栏
  - 缺字段默认 `matches: false` / `confidence: 0.5` / `reason: ""`
  - 解析失败返回 `{ matches: false, confidence: 0.0, reason: "Failed to parse LLM response" }`

### 1.6 mod_manifest.json

| 字段 | 说明 |
|---|---|
| `mod_name` | 模块名 |
| `version` | 语义化版本 |
| `description` | 描述 |
| `authors` | 作者列表 |
| `license` | 许可证 |
| `agent_adapter_class` | 适配器类路径 |
| `network_mod_class` | 网络模块类路径 |
| `capabilities` | 能力声明 |
| `requires_adapter` | 是否需要适配器 |
| `studio_interface` | Studio 接口定义 |
| `dependencies` | 依赖列表 |
| `metadata` | 含 `tools`、`core_features` 子字段 |
| `process_events` | 处理的事件列表 |
| `generate_events` | 生成的事件列表 |

### 1.7 eventdef.yaml

AsyncAPI 3.0 格式；按事件名分 channel，操作分 `send` / `receive`。

### 1.8 许可证口径

- 原版代码：Apache-2.0
- botstalk 代码：沿用 MIT
- 模板文字与格式规范：设计移植，非直接复制

---

## 2 本轮设计决策

### 2.1 结构化打分（botstalk 新增层）

原版只有布尔匹配，没有打分函数。打分是 botstalk 新增层。

**维度权重：**

| 维度 | 权重 |
|---|---|
| skills | 0.5 |
| tags | 0.25 |
| input_modes | 0.125 |
| output_modes | 0.125 |

**计分规则：**

- 只对 `required` 中非空的维度计分；空维度跳过
- 仅使用非空维度的权重做重归一化
- 单维度得分 = 该维度已具备的所需项数 / 该维度所需项总数
- 总分 = Σ（归一化权重 × 单维度得分）

**matched / missing 统计：** 只统计 `skills` + `tags` 两个维度的交集与差集。

### 2.2 pick 规则

1. 最高分胜出
2. 并列时取 `agent_id` 字典序最小者
3. 最高分 ≤ 0 时不选中，走 `unsupported`

### 2.3 @ 指定行为

`mentions` 非空时，打分不起作用——直接将 `mentions` 过滤后的首个候选直派。该行为由测试用例锁定，系测试抓出的真 bug 修复（原版 @ 指定后仍走打分，导致被指定者因能力不匹配而被跳过）。

### 2.4 协议 v1.3 兼容

- `capability_update.capabilities` 新增可选 `skills` / `tags`
- `message` 新增可选 `required_capabilities`
- 均为可选字段，老客户端不携带时不受影响

### 2.5 清单校验规则

| 规则 | 说明 |
|---|---|
| `mod_name` | 小写蛇形（lower_snake_case） |
| `version` | 语义化三段（major.minor.patch） |
| `capabilities` | 非空且技能 ID 唯一 |
| 未知字段 | 忽略，向前兼容 |

### 2.6 deepseek 清单示例

文件位置：`adapters/deepseek/manifest.json`

---

## 3 文件清单

### 3.1 核心实现

| 文件 | 职责 |
|---|---|
| `gateway/src/capability.ts` | NormalizedCapability 类型、normalizeLocalAdapter（对应原版 normalize_local；原版 normalize_a2a 暂无 botstalk 侧 A2A 数据源，未移植）、matchStructured（对应原版 match_structured_capabilities）、结构化打分（原版无此函数，为本轮新增层） |
| `gateway/src/capability-llm.ts` | DEFAULT_MATCHING_PROMPT、parse_llm_response（不调用 LLM） |
| `gateway/src/manifest.ts` | loadManifestFile、loadManifestDir、清单校验 |
| `adapters/deepseek/manifest.json` | deepseek 适配器清单示例 |

### 3.2 协议层

| 文件 | 变更 |
|---|---|
| `packages/protocol/types.ts` | capability_update.capabilities 新增可选 skills/tags；message 新增可选 required_capabilities |
| `packages/protocol/codec.ts` | 编解码适配新可选字段 |

### 3.3 网关接线

| 文件 | 变更 |
|---|---|
| `gateway/src/hub.ts` | Conn 新增 capabilitySkills / capabilityTags；capability_update 时存储 |
| `gateway/src/router.ts` | 打分派单接线 |
| `adapters/base/src/client.ts` | sendCapability 新增可选 skills/tags 参数 |

### 3.4 测试

| 文件 | 覆盖范围 |
|---|---|
| `gateway/test/capability.test.ts` | normalize、match、打分、pick |
| `gateway/test/manifest.test.ts` | 清单校验规则 |
| `packages/protocol/test/codec-capability.test.ts` | 协议编解码新字段 |
| `gateway/test/router-capability.test.ts` | 派单集成（打分、unsupported、@指定覆盖） |
| `scripts/smoke-capability-matching.mjs` | 端到端冒烟 |

---

## 4 已知限制

1. **清单加载函数** `loadManifestFile` / `loadManifestDir` 已实现并经测试，但网关启动时尚未自动加载某个清单目录（待后续轮次接 config）
2. **LLM 兜底函数**已实现但网关派单尚未调用 LLM——结构化打分无候选命中时直接走 `unsupported`，不回退 LLM
3. **registry 描述符**尚未转成清单文件
4. **游戏清单**尚未编写

---

## 5 视觉验收说明

本轮无 Web UI 变更（派单逻辑与清单校验均为后端行为），无截图。
