# mini-os

**状态**：v1.3「多用户与权限」（2026-10-16）。`cargo test` 65/65 全过（lib 15、api_test 16、auth_test 8、failure_injection 11、isolation_test 5、metrics_test 4、share_test 6）；`cargo clippy --all-targets -- -D warnings` 零警告；`cargo fmt --check` 通过。真服务冒烟（注册→登录→跨用户 404→分享只读→migrate-legacy→登出）全过；Web UI 四张截图亲眼验收通过。

## 功能模块

1. Web 终端：浏览器内的 POSIX 风格 shell，命令经后端执行。
2. 文件管理器：目录浏览、上传、下载、重命名、删除。
3. 文本编辑器：打开/编辑/保存 VFS 内文件。
4. 任务管理器：查看与终止运行中的进程。
5. 系统监控：CPU/内存/磁盘指标，SSE 推送。
6. 分享：生成只读链接，供未登录访客读取单个文件。
7. 备份/恢复：整库导出与导入。
8. 用户体系与鉴权：注册/登录/注销，Argon2id 密码哈希（PHC 字符串存储），opaque session token（32 字节随机 hex 明文仅走 HttpOnly Cookie，库内只存 SHA-256），`SESSION_TTL_SECS` 默认 7 天。
9. 访客只读分享：`POST /api/shares`（仅文件）签发 token，`GET /api/s/:token` 返回元信息、`/download` 流式下载。

## 里程碑记录

### v1.3 多用户与权限（2026-10-16）

做了什么：

- 端点：`POST /api/auth/register|login|logout|migrate-legacy`、`GET /api/me`、`GET /api/auth/setup-needed`。
- 鉴权中间件：白名单公开（health/readyz/metrics、auth 注册登录、分享只读），其余 `/api/*` 与 `/ws` 未登录一律 401。
- VFS 按用户隔离：`vfs_nodes.user_id`；`settings` 改 `(user_id, key)` 联合主键；跨用户访问返回 404，不泄露存在性。
- 迁移 003：建 `users`/`sessions`/`shares`，重建 `settings` 联合主键，占位用户 `legacy` 承接老数据，幂等可重跑。
- 前端：`login.html` 登录/注册/初始化三态页；桌面门卫未登录跳登录页；任务栏显示当前用户与注销；文件管理器加分享按钮；`share.html` 只读分享页。
- 指标新增 `auth_ops_total`；备份/恢复改为整库覆盖新表；OPERATIONS.md 同步更新。

本轮抓到的真 bug（均已修）：

- B11 补丁误删 `/api/health` 路由（返回 index.html），验收发现后补回。
- dpsk 输出夹带 `---NEW-END---`/`---END-PATCH---`/`---` 标记行污染 src/lib.rs、handlers.rs、main.rs、config.rs、db.rs、api_test.rs，应用后逐文件清除。
- 分享接口返回的 url 是 `/api/s/{token}`，与设计契约 `/share.html?token=` 不符，已按契约修正；另有测试断言与实现语义不一致（POST /api/fs 应为 201、DELETE 应为 204），已按实现修正测试。
- 视觉验收抓到 v1.x 遗留 bug：`<div id="taskbar">` 用 id 而 CSS 用 `.taskbar` 类选择器，任务栏样式自 v1 起从未生效，已补 `class="taskbar"`（保留 id，无 JS 按 id 引用，安全）。

诚实未做：访客角色、目录分享、细粒度 RBAC、密码强度策略（仅最小长度）、2FA、JWT、滑动续期、限流。

## 后续计划

- ~~多用户与权限~~ → 目录分享、RBAC、限流。
- 进程隔离与资源配额。
- 可观测性：结构化日志与追踪。
</｜DSML｜ parameter>
</｜DSML｜ invoke>
</｜DSML｜ calls>
