# OpenAgents 移植第 1 轮：registry 描述符 + CLI 本体 adapter 模板（2026-10-24）

## 原版行为实测（openagents-org/openagents，tarball 解包实测）

- registry：22 个 agent 描述符（非 23，实测计数）。字段全集包含：`name` / `label` / `description` / `homepage` / `tags` / `featured` / `order` / `builtin` / `logo` / `support` / `install` / `uninstall` / `adapter` / `launch` / `check_ready` / `probe` / `env_config` / `models` / `vendor` / `tagline` / `catalog` / `workspace_model` / `protocol` / `resolve_env` / `provider_locked`。
- `Registry` 类语义：featured 优先按 `order` 排序，其余按 `(label || name)` 字母序；缺 `support` 或空对象时补 `DEFAULT_SUPPORT = { install: true, workspace: false, collaboration: false }`。`cursor` / `opencode` 的 `support` 实测为 `{}`。
- 上游真实形态：6 个描述符 `launch` 为 `null`，例如 `openclaw` / `opencode` / `codearts`；3 个描述符 `adapter` 为 `null`，例如 `hermes` / `mini-swe-agent` / `nanoclaw`。校验器与 `CliAdapter` 必须容忍这些空值，不许当错误。
- `ClaudeAdapter` 子进程语义：按 `install.binary` 找二进制，`launch.args` 拼参数。`claude` 包含 `--append-system-prompt "Your agent name is '{agent_name}'."` 模板；`codex` 的 `args` 实测为 `[null]`。停止时 `SIGINT` → 宽限 → `SIGKILL`；Windows 使用 `taskkill /F /T` 杀树。就绪判定覆盖 `check_ready` 四项；`probe` 使用 `probe.args` + `timeout_s`。

## 移植决策

- 描述符 JSON 原样移植，作为纯数据搬运；`Apache-2.0` 归属在 `packages/registry/src/index.ts` 注释声明。
- `Registry` 类用 TypeScript 重实现，排序与默认补齐行为与原版逐项对照，并用测试锁定。
- `CliAdapter` 拆三个文件：
  - `command.ts`：纯函数，负责参数渲染与命令构造。
  - `ready.ts`：负责就绪判定与探测。
  - `cli-adapter.ts`：基类，继承 `AdapterClient`；`onTask` 默认接到 `handleTaskMessage()` → `runTask()` → 回房间 `task done` / `task failed`。
- 进程组杀是本轮实测逼出的设计：失败注入测出 shell 脚本孙进程（`sleep`）继承管道，导致 `close` 事件 30s 才到。修复为 `detached: true` + `process.kill(-pid)` 杀整组，并用 `exit` 事件 2s 宽限兜底。

## 测试（三类）

- 行为对照：
  - `registry.test.ts`：6 例，覆盖 22 个描述符全合法、排序前 7 与 label 序、`check_ready` 关键字段。
  - `cli-adapter.test.ts`：A 组 4 例，覆盖 `buildCommand` 的 `claude` / `codex` / `openclaw-null` / `expandHome`。
- E2E：`fake-cli.sh` 替身，覆盖 `auth status` / `--print` / `--slow` / `--ignore-sigint` / `--boom` / `--big` / `stdin` 回显，共 4 例。
- 失败注入：6 例，覆盖二进制不存在、timeout 无僵尸、`SIGINT` 升级 `SIGKILL`、并发拒绝、`1MB` 截断、非零退出。其中 2 例在首轮实测中抓出真 bug：`close` 事件挂起；修复后全绿。
- 网关：`GET /api/registry/agents` 返回 22 条白名单字段，`verified` 不泄露 `check_ready`；`GET /api/registry/agents/:name` 正常；不存在时 404。真实网关冒烟通过；网关全量 `826/826` 零回归。

## 本轮交付

- `packages/registry`：`@botstalk/registry@0.1.0`
- `adapters/cli-template`：`@botstalk/cli-template@0.1.0`，包含 `claude` / `codex` 两个具体 adapter
- 网关 `registry-routes.ts`

=== PATCH: botstalk/packages/registry/src/index.ts ===
diff --git a/botstalk/packages/registry/src/index.ts b/botstalk/packages/registry/src/index.ts
--- a/botstalk/packages/registry/src/index.ts
+++ b/botstalk/packages/registry/src/index.ts
@@ -1,3 +1,9 @@
+// SPDX-License-Identifier: Apache-2.0
+// 本包内 22 个 agent 描述符 JSON 原样移植自 openagents-org/openagents（Apache-2.0）。
+// 上游版权与许可归 openagents-org/openagents 所有；此处仅做 TypeScript 封装，
+// 不改变上游描述符数据语义。完整 Apache-2.0 许可见仓库根 LICENSE / NOTICE。
+
 import descriptors from './descriptors.json';
 import { AgentDescriptor } from './types';
 
 export const AGENTS = descriptors as AgentDescriptor[];
