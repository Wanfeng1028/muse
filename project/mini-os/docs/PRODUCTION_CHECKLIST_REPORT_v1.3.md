# PRODUCTION CHECKLIST REPORT v1.3

## 0. 结论先行
- 发版结论：**有条件通过**。多用户与权限核心链路（注册/登录/登出/legacy 迁移/会话鉴权/数据隔离/只读分享）具备发版条件。
- 已知限制（设计契约内明确未做）：访客角色、目录分享、细粒度 RBAC、密码强度策略（仅最小长度）、2FA、JWT、session 滑动续期、限流。
- 后续排期：目录分享、RBAC、限流（见第 8 节）。

## 1. 版本信息与范围
- 版本：v1.3「多用户与权限」里程碑。
- 范围一句话：在单 SQLite 库上引入 users/sessions/shares 三表与 argon2 密码、opaque session 鉴权、VFS 按 user_id 隔离、只读文件分享，并以迁移 003 将老数据归属 legacy 占位用户。
- 沿用项：JSONL 日志与 request_id、/metrics、健康/就绪、优雅关闭、docker-compose、backup/restore CLI 与脚本。
- Checklist：
  - [通过] 版本范围与设计契约一致，未声明契约外特性。
  - [通过] 老库升级路径由迁移 003 覆盖（vfs_nodes 加 user_id 默认 1、settings 重建联合主键、占位用户 id=1 'legacy'）。

## 2. 可靠性
- 测试金字塔数字（2026-10-16 验收实测）：`cargo test` **65/65 全过**——lib 15（auth 4 + metrics 6 + migrate 2 + log 3 既有）、api_test 16、auth_test 8、failure_injection 11、isolation_test 5、metrics_test 4、share_test 6；`cargo clippy --all-targets -- -D warnings` 零警告；`cargo fmt --check` 通过。
- 失败注入覆盖：伪造 token、过期 session、users 表缺失时返回 500 且不 panic。
- 迁移 003：建 users/sessions/shares，vfs_nodes 加 user_id，settings 重建联合主键，占位用户 'legacy'（password_hash NULL 不可登录），老数据归属 legacy；**幂等**。
- 健康与生命周期：GET /api/health、GET /api/readyz、优雅关闭沿用既有实现。
- Checklist：
  - [通过] cargo test 覆盖 auth/隔离/分享/失败注入新增用例。
  - [通过] cargo clippy --all-targets 零警告。
  - [通过] 失败注入：伪造 token、过期 session 均按契约拒绝。
  - [通过] 失败注入：users 表缺失时 500 且不 panic。
  - [通过] 迁移 003 幂等，老库可升级。
  - [通过] 健康/就绪/优雅关闭沿用。

## 3. 可观测性
- 沿用：JSONL 日志与 request_id 贯穿请求链路。
- 新增：`auth_ops_total{op}`，op ∈ {register, login, logout, migrate_legacy, share_create}。
- 排障：结合 request_id 与 auth_ops_total 定位认证失败、迁移领取、分享创建异常。
- Checklist：
  - [通过] JSONL + request_id 沿用。
  - [通过] /metrics 新增 auth_ops_total 且 op 标签与契约一致。
  - [通过] 排障路径可由 request_id 与 auth_ops_total 联合定位。

## 4. 数据与状态
- 备份/恢复：单 SQLite 文件，现有 backup/restore CLI 与脚本整库备份，覆盖 users/sessions/shares 新表。
- 敏感数据策略：密码仅存 argon2 0.5 Argon2id PHC 字符串；session token 32 字节 OsRng → hex 明文仅交客户端，库里只存 SHA-256 hex；Cookie 名 mini_os_session（HttpOnly, Path=/, SameSite=Lax, Max-Age=ttl）。
- 配置：SESSION_TTL_SECS 启动校验，默认 604800。
- 多用户 tenant 落地：vfs_nodes.user_id、settings (user_id,key) 联合主键，所有查询加 user_id 约束，跨用户 id 返回 404。
- Checklist：
  - [通过] 备份覆盖用户表，整库备份含新表。
  - [通过] 密码只存 argon2 PHC。
  - [通过] token 明文永不落库，仅存 SHA-256。
  - [通过] Cookie HttpOnly/SameSite=Lax/Path=/ 与契约一致。
  - [通过] SESSION_TTL_SECS 启动校验。
  - [通过] 多用户 tenant 隔离落地，跨用户 404。

## 5. 部署与运维
- 沿用：docker-compose 部署方式。
- OPERATIONS.md 更新：SESSION_TTL_SECS、用户表说明、排障新增项。
- Checklist：
  - [通过] docker-compose 沿用，无部署方式变更。
  - [通过] OPERATIONS.md 已更新 SESSION_TTL_SECS、用户表说明、排障新增项。

## 6. 安全与健壮性
- 输入校验：用户名 3-32 字符 [A-Za-z0-9_.-]、禁 'legacy'；密码 ≥8 字符。
- token 不可猜：32 字节 OsRng，分享 token 16 随机字节 hex。
- 防枚举：登录失败统一 401；register 用户名已存在返回 409。
- 跨用户 404：不泄露存在性。
- 分享：POST /api/shares 仅节点属当前用户且 kind=file；GET /api/s/:token 只读元信息；/download 流式下载；不存在 404；访客只读不可写。
- 未做（已知限制）：限流、2FA、密码强度策略（仅最小长度）。
- Checklist：
  - [通过] 用户名/密码规则按契约校验。
  - [通过] token 不可猜（OsRng）。
  - [通过] 防枚举：login 统一 401，register 409。
  - [通过] 跨用户访问 404。
  - [通过] 分享只读，不存在 404。
  - [未通过] 限流未实现 → 已知限制，排期见第 8 节。
  - [未通过] 2FA 未实现 → 已知限制。
  - [未通过] 密码强度策略仅最小长度 → 已知限制。
  - [不适用] 访客角色、目录分享、细粒度 RBAC、JWT、session 滑动续期：契约明确未做。

## 7. 可维护性
- auth.rs 模块边界清晰，承载注册/登录/登出/迁移/会话。
- API 契约表：端点与鉴权中间件公开路径按契约固定。
- CHANGELOG v1.3 记录本里程碑。
- 技术债记录：见已知限制与第 8 节排期。
- Checklist：
  - [通过] auth.rs 模块边界清晰。
  - [通过] API 契约表与中间件公开路径一致。
  - [通过] CHANGELOG v1.3 已记录。
  - [通过] 技术债已记录并关联排期。

## 8. 发版结论
- 结论：**有条件通过**。核心多用户与权限链路满足设计契约，可发版；已知限制需在后续版本收敛。
- 已知限制清单：
  - 访客角色、目录分享、细粒度 RBAC。
  - 密码强度策略（仅最小长度）、2FA、JWT。
  - session 滑动续期、限流。
- 后续排期：
  - 目录分享。
  - RBAC。
  - 限流。
- Checklist：
  - [通过] 结论为有条件通过并附已知限制。
  - [通过] 后续排期明确列出目录分享、RBAC、限流。
  - [通过] 未通过项均有排期或声明为已知限制。

## 9. 视觉验收（2026-10-16，真服务 + Chromium 152 截图，亲眼检查）
- `login.html` 初始化态：ocean 壁纸 + 白卡片，「创建管理员账号」+ 规则说明（用户名 3-32 字符、密码至少 8 位），「创建账号」按钮；去 AI 味（无紫渐变 hero、无渐变标题、无 emoji 图标、表单左对齐）。
- `login.html` 登录态：「登录你的桌面」+「没有账号？去注册」切换链接。
- 桌面登录态：壁纸 + 应用图标列（文件管理器/文本编辑器/终端/设置/关于）+ 底部毛玻璃任务栏（开始/用户名/注销/WS 状态/时钟）。**抓到 v1.x 遗留 bug**：`<div id="taskbar">` 与 CSS `.taskbar` 类选择器不匹配，任务栏样式自 v1 起从未生效，已补 `class="taskbar"` 修复（保留 id，无 JS 按 id 引用）。
- `share.html` 只读分享页：`mini-os · 只读分享` 品牌行 + 文件 SVG 图标 + 文件名/大小/类型 + 蓝色「下载文件」按钮，匿名可读。
- 未登录访问 `/` 自动跳 `login.html`（门卫逻辑已由冒烟测试覆盖：`/api/fs` 未登录 401、`/ws` 未登录 401/带 cookie 101）。
- Checklist：
  - [通过] 登录页双态视觉符合桌面美学且去 AI 味。
  - [通过] 桌面登录态渲染正常，任务栏经修复后位于底部。
  - [通过] 分享页只读展示正常。
  - [通过] 未登录拦截链路（页面跳转 + API 401 + WS 401）冒烟通过。
