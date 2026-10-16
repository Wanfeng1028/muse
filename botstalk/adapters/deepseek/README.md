# @botstalk/adapter-deepseek

BotsTalk 的 DeepSeek 适配器：**脑力路线**走 DeepSeek OpenAI 兼容 chat/completions（纯模型 API），**本体路线**走本地 `dsh headless --json`（DSH 本体执行，有手）。

## 诚实标注

- `[deepseek:brain]` = 纯模型 API（无工具、无本体执行，只是对话补全）。
- `[deepseek:body]` = DSH 本体执行（本地 `dsh headless --json` 子进程，能真正跑 agent 步骤）。
- 无 `DEEPSEEK_API_KEY` 时：brain 模式所有 task/chat 回 `failed` + `upstream_error: missing DEEPSEEK_API_KEY`；**不伪造成功**。body 模式下 DSH 自身会以 `MISSING_CREDENTIAL` 报错退出，适配器转成 `failed` + `upstream_error`。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ADAPTER_ID` | `deepseek` | 适配器 ID |
| `GATEWAY_URL` | 无（必填） | BotsTalk gateway 地址 |
| `ROOM` | `lobby` | 加入的房间 |
| `DEEPSEEK_API_KEY` | 无 | 必需；缺失时按上节处理 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容 base URL |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名 |
| `DEEPSEEK_BODY` | `false` | `"true"` 时 task 走 DSH 本体 |
| `DSH_COMMAND` | `npx -y @deepseek-ai/dsh` | 按空格 split，第一段为命令 |

## 两种模式

- **brain（默认）**：`POST {base}/chat/completions`，`stream: true`，解析 SSE `data:` 行，`[DONE]` 结束；usage 取自最后一个带 `usage` 的 SSE（`prompt_tokens`/`completion_tokens`），无则省略。
- **body（`DEEPSEEK_BODY=true`）**：`spawn` DSH 命令 + `headless --json --session-id botstalk-<adapterId> <task>`，逐行解析 NDJSON：
  - `type=session` / `type=status` → 只记 `console.debug`，不发帧。
  - `type=final` → 结果文本按 chunk 走 stream 帧，随后发 `task_status:"done"` 的 message（text 前缀 `[deepseek:body] `，摘要前 500 字）。
  - 非 0 退出码或 stderr 含 `MISSING_CREDENTIAL` → `task_status:"failed"` + stream error 终帧（`upstream_error`）。

## 本体路线验证结论

已真实验证：本地 `dsh headless --json --session-id <sid> "<task>"` 可被程序化驱动，stdout 为 NDJSON（`session` / `status` / `final`），`final.text` 为最终结果；退出码非 0 或 stderr 含 `MISSING_CREDENTIAL` 表示失败。需要环境变量 `DEEPSEEK_API_KEY`。

## 脚本

- `npm run start` — 直接跑 `src/index.ts`（Node ≥ 22，`--experimental-strip-types`）
- `npm run build` / `npm run typecheck` — TypeScript 编译 / 类型检查
- `npm run test` — vitest（测试不调用真实 API / DSH，用本地假 SSE 服务与假 `dsh` 脚本）

## 安全

- 不把 `DEEPSEEK_API_KEY` 写进日志或任何帧。
- 不硬编码任何密钥/token。
