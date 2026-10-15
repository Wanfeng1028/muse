
# Changelog

## [1.2.0] - 2026-10-16

### 新增
- 版本化数据库迁移：`schema_migrations` 表（001 建表 / 002 增补 `content_blob`/`mime_type` 列），幂等，老库启动自动升级
- 就绪探针 `GET /api/readyz`（DB 真实可查 200，否则 503）；`/api/health` 的 version 改为取 Cargo.toml
- 结构化日志：JSONL 写 stderr（`ts/level/request_id/method/path/status/latency_ms`），`x-request-id` 透传/生成并回写响应头
- 优雅关闭：SIGTERM/Ctrl+C 排空在途请求后退出（exit 0，打 `service_stopped`）；`SHUTDOWN_TIMEOUT_SECS`（默认 30 秒）只约束排空阶段
- CLI 子命令：`mini-os backup --db --out`（在线备份，拒绝覆盖）、`mini-os restore --db --backup [--force]`（完整性校验 + 自动快照 + 原子替换）
- 运维脚本：`scripts/backup.sh`（保留最近 7 个）、`scripts/restore.sh`、`scripts/load_check.py`、`scripts/fault_drill.sh`（kill -9/备份恢复/损坏拒绝/优雅关闭/超时回归，全 PASS）
- `docker-compose.yml` 一键部署（日志轮转 10m×3、资源限制 1 核/512M；本机无 daemon 未实跑）
- `docs/OPERATIONS.md` 运维手册

### 测试
- 28 例全过（单元 4 + API 集成 16 + 失败注入 8：损坏库 open 拒绝、业务表缺失时读写 500 不 panic、readyz 200/503 翻转、request_id 透传/生成、迁移幂等与老库升级）
- 真实负载：300 文件顺序创建 0 失败（avg 74.93ms / max 138.97ms），30 个抽查内容一致
- `cargo clippy --all-targets` 零警告

### 修复
- 修复优雅关闭实现：`SHUTDOWN_TIMEOUT_SECS` 曾被错误地用于整个服务生命周期（服务运行超 N 秒会被掐断），现只约束排空阶段（对照实验：3 秒超时下健康服务 6 秒后仍 READY）

### 已知限制
- 无鉴权、无限流（本地单用户场景）；单实例 SQLite；docker 镜像未在本机实跑验证

## [1.1.0] - 2026-10-15


### 新增
- 文件上传：`POST /api/files/upload?path=<目录>`，multipart/form-data（字段名 `file`），单文件上限默认 50MB（`UPLOAD_MAX_BYTES` 环境变量可配）
- 文件下载：`GET /api/files/download?path=<文件路径>`，64KB 分块流式响应，`Content-Disposition: attachment`，目录请求 400、不存在 404
- 存储：`vfs_nodes` 新增 `content_blob BLOB` / `mime_type TEXT` 列（ALTER TABLE 幂等迁移）；文本文件仍写 `content` 列（编辑器可直接打开），二进制文件只存 blob
- 节点 JSON 新增 `size`（字节数）、`mimeType` 字段；`stats.totalBytes` 改为 blob 与文本双路求和
- 安全：文件名消毒（拒绝 `/` `\` 控制字符与 `..`，超长拒绝）、超限 413、同名 409、路径穿越 400
- 前端文件管理器：工具栏"上传"按钮（多文件、XHR 上传进度条）、拖拽到窗口上传、文件行内"下载"按钮、顶部错误提示条
- 修复：补 `.hidden` 工具类（开始菜单此前无法隐藏）；修复壁纸切换类名 mismatch（`wallpaper-ocean` vs `.wallpaper.ocean`）

### 测试
- 集成测试 8 → 16（新增上传/下载 8 例：文本 roundtrip、二进制 roundtrip、子目录、413、路径穿越、409、目录下载 400、缺失 404）
- `cargo clippy --all-targets -- -D warnings` 零警告；真机冒烟 + 4 张真实截图视觉验收通过

### 已知限制
- 暂无鉴权；不支持断点续传；上传进度仅前端展示

## [1.0.0] - 2026-10-13

- 工程化 v1：Axum + rusqlite 虚拟文件系统、5 应用桌面前端、WebSocket、CI 与多阶段 Dockerfile
- 8 个集成测试、clippy 零警告

