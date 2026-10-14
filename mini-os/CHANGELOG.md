
# Changelog

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

