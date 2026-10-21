# Hermes 一键插入支持

更新日期：2026-10-14

## 结论

Hermes 的“一键插入应用”已开放，但它不是插件安装。它在 Electron 后台静默修改 YAML、写入 Skill、创建 Credential 并授权，所以 macOS 上通常看不到安装窗口或进度。

## 接入方式和产品状态

| 项目 | Hermes 当前实现 |
|---|---|
| 一键插入产品状态 | 开放 |
| Hermes 查询 MemHub | MCP Server |
| 告诉模型何时查询 | `memhub-recall` Skill |
| MemHub 自动向 Prompt 注入记忆 | 没有 |
| Hermes 新会话实时送入 MemHub | 没有 Hook/Plugin；依赖 Core 扫描 |
| 传统插件 | 没有 |

Hermes 对 MemHub 的使用方式是：模型在需要时主动调用 MCP 工具。当前没有 Prompt 前 Prefetch，也没有 memory-provider Hook 自动把记忆塞进上下文。

## 两个开关分别做什么

### 打开“一键插入应用”

写入 `config.yaml` 的 MCP Server、安装 Skill、创建 Credential 并授予 Recall 权限。Hermes 随后可以主动调用 MemHub。

### 关闭“一键插入应用”

先撤销 Hermes Credential，再恢复或删除 MCP 配置、Skill 和 Journal。它不改变 MemHub 是否继续读取 Hermes 对话。

### 打开“同步开关”

Core 校验 `.hermes` Root，创建或恢复 history Job，扫描 Hermes 会话数据库中尚未处理的记录，并通过 Core 的轮询器持续发现新记录。

### 关闭“同步开关”

Core 停止扫描和 claim 未运行 Job；pending Job 冻结，running Job可结束。Hermes 没有 Capture Hook，因此关闭后不会再有另一条实时入库路径。已有 Memory 仍可查询。

### 组合效果

| 一键插入 | 同步 | 结果 |
|---|---|---|
| 关 | 关 | 双向都关闭 |
| 开 | 关 | Hermes 可以查询已有 Memory，但 MemHub 不再读取 Hermes 新会话 |
| 关 | 开 | MemHub 读取 Hermes 会话，但 Hermes 不能调用 MemHub |
| 开 | 开 | 双向接通；Recall 仍由 Hermes 模型主动调用，不是自动 Prefetch |

## 打开时的实际动作

```text
~/.hermes/config.yaml
  └── mcp_servers.one-memory

~/.hermes/skills/memhub-recall/SKILL.md

~/.hermes/.one-memory/recall-install.json

<MemHub dataDir>/host-permissions/...
  └── Hermes Credential、Installation、Grant
```

配置大致为：

```yaml
mcp_servers:
  one-memory:
    command: /Applications/MemHub.app/Contents/MacOS/MemHub
    args:
      - /Applications/MemHub.app/Contents/Resources/mcp.cjs
    env:
      ELECTRON_RUN_AS_NODE: "1"
      ONE_MEMORY_BROKER_DISCOVERY: "..."
      ONE_MEMORY_MANAGED_BY: "one-memory"
      ONE_MEMORY_HOST_CREDENTIAL_FILE: ".../credential"
```

Hermes Layout 定义在 [recall-installer.ts](../../packages/host-bridge/src/recall-installer.ts)，YAML 局部编辑在 [yaml-mcp.ts](../../packages/host-bridge/src/yaml-mcp.ts)。编辑器只维护 `mcp_servers.one-memory`，尽量保留模型、Gateway 和注释。

## Skill、Capture 与权限

- Skill：`~/.hermes/skills/memhub-recall/SKILL.md`。
- Capture：当前不安装。Hermes 使用单一 memory-provider slot，自动占用可能覆盖用户已有 Provider。
- 默认 Tools：`om_recall`、`om_conversations`、`om_diagnostic_trace`。
- 默认 Scopes：`all-apps`、`source:hermes`。

## 重复打开

- 已安装且 `approved`：不重装，只修复 MemHub 命令路径并 Probe。
- 文件存在但权限不完整：重新 Preview、安装、签发新 Credential 并授权。
- 已有非 MemHub 管理的 `one-memory` Server：默认拒绝覆盖。

## 关闭

正常关闭会先撤销 Credential，再：

- 删除或恢复 `mcp_servers.one-memory`；
- 删除或恢复 `memhub-recall/SKILL.md`；
- 删除安装 Journal。

配置或 Skill 被用户修改后，MemHub 不会强删，只会尽量撤权并提示人工检查。

## 生效与重启

Probe 成功只证明 MCP 命令能连接 MemHub，不证明正在运行的 Hermes 已热加载。建议完全退出 Hermes、重新打开并开始新会话。
