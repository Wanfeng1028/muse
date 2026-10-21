# CLI 体验流程（用户可以照着走一遍）

本文件只写**真机验证过**的步骤。凡标注「拒绝」的，是当前刻意未接线、会明确报错而非假装成功。

## 0. 准备

发行目录（九项齐全）：`dist-runtime6`（用 `node scripts/build_runtime_distribution.cjs dist-runtime6 darwin arm64 0.0.0 产出）。

体验时建议用**隔离数据目录**，不动你日常的 `~/.one-memory`：

```bash
export ONE_MEMORY_DATA_DIR=/tmp/my_try
```

CLI 可用两种方式：

```bash
# 方式 A：用仓库里的构建产物
node apps/cli/dist/one-memory.cjs <命令>

# 方式 B：npm tarball 安装（已在隔离目录验证）
npm install /path/to/one-memory-cli-0.0.0.tgz
npx one-memory <命令>
```

## 1. 启动与体检

```bash
node apps/cli/dist/one-memory.cjs status
node apps/cli/dist/one-memory.cjs doctor
```

`status` 显示 Runtime 是否运行；`doctor` 按诊断口径做只读检查（默认不修复）。

## 2. 首次接入（init）—— 没有独立的「授权」步骤

```bash
# 先看本机有哪些宿主可接入
node apps/cli/dist/one-memory.cjs init

# 指定来源，生成接入计划（默认只出计划）
node apps/cli/dist/one-memory.cjs init --source codex

# 接入并同时导入历史
node apps/cli/dist/one-memory.cjs init --source codex --import

# 只看会做什么，不真的做
node apps/cli/dist/one-memory.cjs init --source codex --import --dry-run
```

**接入即授权**：没有单独的 authorize 步骤。

## 3. 导入历史与看进度

```bash
node apps/cli/dist/one-memory.cjs setup plan --source codex      # 生成导入计划
node apps/cli/dist/one-memory.cjs sources import --plan-file <计划文件> --confirm
node apps/cli/dist/one-memory.cjs progress                        # 看导入进度
```

真机观察：授权 codex 后任务运行中并持续落库（stored 从 14,437 涨到 62,634）。

## 4. 扫描（两阶段）

```bash
node apps/cli/dist/one-memory.cjs scan            # 预览
node apps/cli/dist/one-memory.cjs scan --yes --source codex   # 执行（必须带 --source）
```

不带 `--yes` 只出计划；执行时给裸路径会明确拒绝（Runtime 按来源寻址）。

## 5. 登记扫描目录（path）

```bash
mkdir -p /tmp/scanme
node apps/cli/dist/one-memory.cjs path list
node apps/cli/dist/one-memory.cjs path add --root /tmp/scanme --source codex --yes
node apps/cli/dist/one-memory.cjs path list          # 显示刚登记的，revision 0→1
node apps/cli/dist/one-memory.cjs path remove --root /tmp/scanme --yes
```

行为已验证：重复登记返回 **409**；删除不存在的返回 **404**。

## 6. 看宿主适配器（adapter）

```bash
node apps/cli/dist/one-memory.cjs adapter list
```

输出每个 harness 的 available / authorized / live_sync / recall 能力。

`adapter probe` **目前会拒绝**（Runtime 未提供探测端点），不是参数问题。

## 7. 写入记忆与查任务（write → task）

```bash
node apps/cli/dist/one-memory.cjs write --session <会话ID> --from 1 --to 2 --evidence <证据ID> --json
# 返回 request_id（state=accepted）

node apps/cli/dist/one-memory.cjs task --id <request_id> --json
```

写入异步完成；`unknown` 表示结果待定，**不可据此重发**。

## 8. 召回（recall）

`recall` 两条路径（raw / memory）此前已真机验证，命令可继续使用。

## 9. 备份

```bash
node apps/cli/dist/one-memory.cjs backup create --target <data目录内的路径> --yes --json
```

目标必须在数据目录内（否则拒绝）；产物已验证 540,672 字节、权限 owner-only。

## 10. 宿主接入（host）

```bash
node apps/cli/dist/one-memory.cjs host list
node apps/cli/dist/one-memory.cjs host status --host codex
node apps/cli/dist/one-memory.cjs host install --host codex          # 预览
node apps/cli/dist/one-memory.cjs host install --host codex --approve <fingerprint>   # 执行
node apps/cli/dist/one-memory.cjs host uninstall --host codex --approve <fingerprint>
```

两阶段确认：不加 `--approve` 只预览。

## 11. 持续同步控制

```bash
node apps/cli/dist/one-memory.cjs sync status --host codex
node apps/cli/dist/one-memory.cjs sync pause --host codex
node apps/cli/dist/one-memory.cjs sync resume --host codex
```

## 12. 卸载（保留数据）

```bash
node apps/cli/dist/one-memory.cjs uninstall --install-root <root> --home <home> --yes
```

已验证：删除 current 链接、版本目录、CLI 链接；**数据目录原样保留**。

## 已知会明确拒绝的（不是 bug）

- `adapter probe`：Runtime 无探测端点。
- `service-install/service-uninstall --yes`（在隔离环境）：需真实用户域（launchctl），失败时会正确回滚、不留半成品。
- 某些命令不接受 `--json`（如 `start`、`install`、`uninstall`）——契约里该命令没有这个选项，带了会退 2。

## 与桌面 App 的关系

- 只读/控制类命令在 CLI-only 场景已验证：两个独立 CLI 进程连同一 daemon（同一 instance_id）、读同一份数据；`start` 不会重复启动。
- 涉及 App 的那半（App 与 CLI 共用同一 daemon 的真机验收）依赖桌面 App 运行，App 当前未运行，未验证。
- 注意：`~/.one-memory/runtime.json` 存在过期 receipt（记录的 pid/port 已不存在），会让 CLI 显示 stopped——receipt 维护在 App 侧，本轮未改。
