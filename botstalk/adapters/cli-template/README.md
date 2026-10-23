# @botstalk/cli-template —— CLI 本体 adapter 模板

## 这是什么

把任意符合 `@botstalk/registry` 描述符的 coding CLI（如 Claude Code、Codex）接成 botstalk adapter 的模板类。

一句话原理：按描述符 `install.binary` + `launch.args`（`{agent_name}` 模板替换）spawn 子进程，prompt 写 stdin，stdout 当任务结果回房间。

## 文件结构

- `src/command.ts`：命令构造，包含 `renderArgs()` / `buildCommand()` / `expandHome()`。
- `src/ready.ts`：`checkReady()` 按 `check_ready` 字段判就绪，支持 `env_vars` / `creds_file` / `status_args` 正则；`probe()` 做存活探测。
- `src/cli-adapter.ts`：`CliAdapter` 基类，包含 `runTask()` / `stopCurrent()` / `handleTaskMessage()`；同一实例同时只跑一个任务。
- `src/adapters/claude.ts` / `src/adapters/codex.ts`：两个开箱即用的具体 adapter。

## 派生自己的 adapter

```ts
import { CliAdapter } from '@botstalk/cli-template';
import { registry } from '@botstalk/registry';

export class DroidAdapter extends CliAdapter {
  constructor() {
    super(registry.getByName('codex'), { agentName: 'droid' });
  }
}

const adapter = new DroidAdapter();
adapter.connect({ gateway: 'ws://127.0.0.1:8765', room: 'lobby' });
## 运行

```bash
npm run build
node dist/adapters/claude.js --gateway ws://127.0.0.1:8765 --room lobby
## 关键语义

- `runTask` 超时会标记为 `timedOut`，并杀掉子进程。
- 杀进程走**进程组**：spawn 时使用 `detached: true`，停止时使用 `process.kill(-pid)`，把 CLI 派生的孙进程一起收掉。否则孙进程可能占住 stdio 管道，导致任务挂起。
- 停止流程：先发 `SIGINT`，等待 `killGraceMs`（默认 `2000ms`）后仍未退出则升级为 `SIGKILL`。
- `stdout` / `stderr` 各自上限 `1MB`，超出部分截断。

## checkReady 语义表

| 检查项 | 不满足时 |
|---|---|
| `env_vars` 缺失 | not ready |
| `creds_file` 不存在 | not ready |
| `status_args` 正则不匹配 | not ready |

## Windows 说明

本实现使用 POSIX 信号语义。Windows 下进程组杀会退化为直接 kill；`taskkill /F /T` 树杀留待后续实现。

## 协议来源

设计对标 `openagents-org/openagents` 的 `ClaudeAdapter`：子进程执行 + 会话保持思想，本仓库为 TypeScript 重实现。registry 描述符 22 个 JSON 原样移植，许可证 `Apache-2.0`，详见 `packages/registry`。
