# Toonflow deepSeek 语言 Provider 评估并入报告

## 评估对象

Toonflow 内置的 `deepseek` vendor 是一个**语言（文本）provider**：它在 Toonflow 的可编程 Vendor 系统中以单个 TypeScript 文件形态存在，通过 `textRequest` 适配函数对接 OpenAI 兼容的 chat/completions 文本生成接口，供 host 以 `id:modelName` 寻址调用；它**不是视频通道**，与 drama-factory 已落地的 toonflow-apimart / compshare / metaso / tfrouter 等媒体 provider 描述符不属同一类，不可混为一谈。

## 能力事实

以下事实来自 Toonflow-app 的 deepSeek vendor（2026-10-20 经 Keenable 从公开资料核验，非模型记忆），逐条列出：

- Toonflow 具备「可编程 Vendor 系统」：第三方 AI provider 以单个 TypeScript 文件（vendor）形式提供，host 使用 Sucrase 转译 + vm2 沙箱加载，运行时通过 `id:modelName` 寻址调用。
- vendor 契约：导出 `vendor`（元数据 + inputs 凭证 schema + 默认 inputValues + models 列表）+ `textRequest` / `imageRequest` / `videoRequest` / `ttsRequest` 四个适配函数。
- 内置 deepseek vendor（`data/vendor/deepseek.ts`）：其 `textRequest` 走 OpenAI 兼容接口（`createDeepSeek` / `createOpenAICompatible`）。
- 该 vendor 支持 thinking 模式注入：`thinkLevel` 0..3 映射为 `reasoning_effort` 的 `high`/`max`，并附加 `thinking:{type:"enabled"}`。
- `o_vendorConfig` 初始化数据里 deepseek 的 `enable=0`（默认禁用），用户填写自己的 API Key 后启用。
- Toonflow 官方 relay（toonflow vendor）内部也按模型名是否包含 `"deepseek"` 做分支切换。

## 与 drama-factory 现状的对照

| 维度 | Toonflow deepseek vendor | drama-factory LlmScriptService |
| --- | --- | --- |
| 协议 | OpenAI 兼容 chat/completions（经 `createDeepSeek` / `createOpenAICompatible`） | OpenAI 兼容 chat/completions（写死 `CHAT_URL="https://chatapi.weixin.qq.com/openai/v1/chat/completions"`） |
| 鉴权 | vendor inputs 凭证 schema + 用户填自己的 API Key | 写死常量 `CREDENTIAL="custom.weixin-chatapi"` |
| 模型选择 | 通过 `id:modelName` 运行时寻址，models 列表在 vendor 元数据中声明 | 模型固定为 DeepSeek-V4-Flash（编剧用，短剧剧本 4 场 JSON 生成），无运行时寻址 |
| 开关 | `o_vendorConfig` 中 deepseek `enable=0` 默认禁用，填 Key 后启用 | 无独立 enable 开关，服务直接调用 |
| 调用点 | host 经 vm2 沙箱加载 vendor，运行时按 `id:modelName` 调用 `textRequest` | `LlmScriptService`（编剧）、`ChatService`（同源）直接调用固定端点 |
| 媒体通道 | 另有 imageRequest / videoRequest / ttsRequest | 无（媒体侧由 toonflow-{apimart,compshare,metaso,tfrouter} 描述符承担） |

**结论**：两者在「OpenAI 兼容 chat/completions 文本生成」这一能力上重叠。drama-factory 已有的 `LlmScriptService` 本质上就是一条等效的直调通道，因此**不需要**再新增一套 deepseek 直调代码；真正值得并入的是 Toonflow vendor 的**可配置语言 provider 注册表思想**（inputs schema + enable 开关 + `id:modelName` 寻址 + thinking 注入）。

## 价格

deepSeek 官方价格与微信 ChatAPI 额度价格均以官网为准，待官网核验。本报告不做成本测算。

## 并入建议

### 5.1 不做什么

- **不新增 deepseek 直调代码**。drama-factory 已有 `LlmScriptService`，重复实现一套 deepseek 调用会形成双通道、双维护点，明确禁止。
- 不把语言 provider 与已落地的 toonflow-{apimart,compshare,metaso,tfrouter} 媒体 provider 描述符混用同一套目录或同一套 submit/poll 模板。

### 5.2 做什么（真正的并入点）

把 `LlmScriptService` / `ChatService` 中写死的 `CHAT_URL` / `CREDENTIAL` / model 改为**可配置的 language-provider 注册表**，对标 Toonflow vendor 的 inputs schema + enable 开关 + `id:modelName` 寻址。配置键设计：

- `drama.llm.provider`：取值 `deepseek-direct | custom`，默认 `deepseek-direct`（零回归）。
- `drama.llm.model`：模型名，默认保持现状（DeepSeek-V4-Flash），可被覆盖。
- `drama.llm.think-level`：0-3，可选，默认关闭；借鉴 Toonflow 的 `reasoning_effort` 注入思想，仅在开启时向请求注入对应 `reasoning_effort`（0..3 映射 high/max）与 `thinking:{type:"enabled"}`，关闭时不注入任何 thinking 相关字段。

`deepseek-direct` 通道对应现有写死端点与凭证，行为与当前完全一致；`custom` 通道允许指向其它 OpenAI 兼容端点与凭证引用。

### 5.3 描述符模板

拟新增 `data/llm-providers/deepseek.json`，字段草图如下（**字段待实现时与 ProviderDescriptor 对齐**）：

```json
{
  "id": "deepseek-direct",
  "kind": "language",
  "protocol": "openai-compatible",
  "endpoint": "/chat/completions",
  "auth": { "type": "bearer", "keyRef": "env:DEEPSEEK_API_KEY" },
  "model": "DeepSeek-V4-Flash",
  "enable": false,
  "thinkLevel": 0
}
```

说明：`kind` 固定为 `language` 以与媒体 provider 描述符区分；`auth.keyRef` 用 `env:` 前缀指向环境变量，避免凭证入库；`enable` 对标 Toonflow `o_vendorConfig` 的默认禁用语义。

### 5.4 测试清单

- 描述符 schema 校验测试：`data/llm-providers/deepseek.json` 通过 language provider 描述符 schema 校验。
- provider 选择单元测试：默认配置下选中 `deepseek-direct`，端点为现有 chat/completions，**零回归**。
- `LlmScriptService` 现有测试回归：编剧 4 场 JSON 生成行为不变。
- `ChatService` 同源回归。
- think-level 注入测试：关闭时不注入 thinking 字段；开启 0..3 时按映射注入。

## 风险与回滚

- 配置缺失时的默认行为：`drama.llm.provider` 缺省即 `deepseek-direct`，等价于当前写死通道，不改变现有调用。
- 改动面仅限 `LlmScriptService` / `ChatService` 的取配置处（把写死常量替换为配置读取），不动协议、不动业务逻辑。
- 回滚：将 `drama.llm.provider` 置回默认，或删除描述符文件并保留写死常量分支即可恢复原状；think-level 默认关闭，回滚时无需清理请求体。

## DoD 小结

按仓库 PRODUCTION_CHECKLIST 精神逐条：

- 文档完整性：**通过**（本报告章节齐备，事实来源与建议明确）。
- 描述符 schema 校验测试：**不适用（本轮未改代码）**。
- provider 选择单元测试（默认通道零回归）：**不适用（本轮未改代码）**。
- LlmScriptService 现有测试回归：**不适用（本轮未改代码）**。
- ChatService 同源回归：**不适用（本轮未改代码）**。
- think-level 注入测试：**不适用（本轮未改代码）**。
- 新增 deepseek 直调代码：**不适用（本轮未改代码，且本报告明确禁止新增）**。
- 价格核验：**未通过**（待官网核验，本报告不做成本测算）。
- 视频 provider 与语言 provider 混用：**不适用（本轮未改代码，本报告明确区分）**。
