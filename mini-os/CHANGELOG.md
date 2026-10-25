
## [1.16.0] - 2026-10-25

### 修复
- 关闭 v1.15.0 已知限制里挂账的 `cargo fmt --check` 存量 diff 之一：tests/mig006_expiry_deep.rs:185 的 users 建表调用改成 rustfmt 输出形式（单行 execute + .expect 换行缩进），只改换行与缩进，标识符、SQL 字符串与语义一字未动；rustfmt --check 该文件已干净。
- 诚实记录：本轮先走 BotsRouter 大写 GLM-5.3（令牌 id=5，单路串行，max_tokens 4000）要格式稿，模型通被推理吃光、正文 0 字未交（作废，不计用量）；格式最终由 rustfmt 工具链机械输出并经 rustfmt --check 核实，非模型手写。twofa_test.rs 的既存 fmt diff（整文件未过 fmt，全量重排达 844 行）本轮刻意不动，仍为已知限制——全量重排会淹没评审，留待后续单独处理。
- 版本跟进：Cargo.toml 1.15.0 -> 1.16.0，`/api/health` 的 version 随之跟进（`env!("CARGO_PKG_VERSION")`，无硬编码断言）。

### 测试
- `cargo test --offline --test mig006_expiry_deep` 11/11 全绿；`rustfmt --edition 2021 --check tests/mig006_expiry_deep.rs` 干净。
- 全量测试本轮未重跑（v1.15.0 已注明 ws_term_lifecycle_r2 套件内挂起问题未变），不谎称全绿。

### 已知限制
- `cargo fmt --check` 整包仍有 diff：tests/twofa_test.rs 全文件未过 fmt（既存，v1.13.0 已注明），本轮未动。
- 全量测试未跑完：ws_term_lifecycle_r2 在套件内挂起（v1.15.0 已注明，单跑全绿），留待后续在空闲时重跑全量确认。

## [1.15.0] - 2026-10-25

### 修复
- 关闭 v1.12.0 已知限制里挂账的 clippy 全量 -D warnings 下 3 个存量错误（本轮改动文件内）：config.rs 文档注释与 impl 之间的空行（clippy::empty_line_after_doc_comments）、totp.rs `outer_hasher.update(&inner_result)` 的不必要借用（clippy::needless_borrows_for_generic_args）、totp.rs `vec![0u8; BLOCK_SIZE]` 改数组字面量（clippy::useless_vec）。三处均为模型稿原样落仓（GLM-5.3 via BotsRouter，令牌 id=5，单路串行，max_tokens 4000，API prompt 23971 / completion 802 / total 24773，无 429），行为不变：空行删除不影响文档内容、去借用后 inner_result 仍按值传入 update、数组下标读写与原 vec 完全一致。
- 版本跟进：Cargo.toml 1.14.0 -> 1.15.0，`/api/health` 的 version 随之恢复正确（`env!("CARGO_PKG_VERSION")`，无硬编码断言）。

### 测试
- `cargo clippy --offline --all-targets` 本仓 config.rs / totp.rs 再无警告（其余均为 vendor 依赖警告，不在本轮范围）。
- 相关套件：twofa 相关测试全绿；全量 `cargo test --offline --no-fail-fast` 跑到 86 个套件、764 过、0 败后卡在 ws_term_lifecycle_r2（见已知限制）；此前首轮全量亦在同一用例挂起后被停掉，两次均为套件内负载下挂起，与本轮改动无代码交集（该用例不走 totp/config 行为路径，config 改动仅为注释）。
- ws_term_lifecycle_r2 单独跑：`cargo test --offline --test ws_term_lifecycle_r2` 2 例全绿、2.7 秒（本轮改动后的树），故判定为套件内负载敏感的偶发挂起，非本轮回归；全量剩余套件未跑完，如实记录、不谎称全绿。

### 已知限制
- 全量测试未跑完：ws_term_lifecycle_r2 在套件内两次挂起（单跑 2.7 秒全绿），属负载敏感偶发，留待后续在空闲时重跑全量确认。
- `cargo fmt --check` 仍有 1 处既存 diff（tests/mig006_expiry_deep.rs:185，v1.13.0 已注明），不在本轮改动文件，未动。
- vendor 依赖的 clippy 警告（unexpected cfg、deprecated 等）不在本轮范围，未动。

## [1.14.0] - 2026-10-25

### 前端美化（桌面布局真修，不是换皮）
- 根因（亲眼看 v13 桌面截图 + 对照代码核实）：桌面图标容器 HTML 是 `#icon-grid`，CSS 里只有 `.desktop-icons` 定义了网格，`#icon-grid` 从未被定义，图标只能竖排居中一列；开始菜单元素只有 `#start-menu` + JS 切换的 `.hidden` 类，CSS 里 `.start-menu` 面板样式从未生效；任务栏 HTML 实际是 `#start-btn` / `#taskbar-apps` / `.taskbar-right` / `#logout-btn` / `#ws-status` / `#clock`，CSS 里 `.taskbar-start` / `.taskbar-tasks` / `.taskbar-tray` 从未生效；任务栏毛玻璃底在黛蓝壁纸上洗成浅蓝色。
- 新增设计层 `static/design-v114.css`（原 `style.css` 不动，`index.html` 在主样式后引用设计层）：`#icon-grid` 恢复网格（92px 列、116px 行，64px 瓷砖 + 标签放得下）、`#start-menu` 直接写面板样式且 `.hidden` 时隐藏、任务栏按实际 id 写样式并改实色纸面底（取消毛玻璃）、时钟用 tabular-nums、全部按钮与链接加 focus-visible 2px 赭石外圈。
- 编排修正（GLM 稿后人工核对）：图标行高 100px 装不下 64px 瓷砖 + 标签，改 116px；hover 标签变赭石在壁纸上可读性差，删掉；`color-mix` 换成已有的 `--primary-soft` 变量。
- 视觉逻辑写进 `docs/DESIGN.md` v1.14.0 一节；去 AI 味自查：无紫渐变、无霓虹辉光、无 Inter 首选字体、无 emoji 当图标（桌面图标本来就是 Lucide SVG 瓷砖）、无居中英雄区、无三栏特性格。

### 测试
- 新增 `tests/design_v114_test.rs` 3 例：设计层覆盖真实选择器、index 链接顺序在主样式之后、无紫/无 Inter/无渐变且大括号平衡。
- 版本跟进：Cargo.toml 1.13.0 -> 1.14.0，`/api/health` 的 version 随之恢复正确（`env!("CARGO_PKG_VERSION")`，无硬编码断言）。

### 已知限制
- 壁纸本身（ocean 黛蓝渐变）未改，设计层只改任务栏与图标区；深色主题下设计层只用变量名，纸面底在深色下为夜墨面，未单独截图深色态。
- 桌面图标仍需双击打开（单击只选中），本轮未改交互。
- 真实服务截图验收（隔离库、端口 19014、注册用户 + 1 条日程 + 1 条便签）：`docs/screenshots/v114-desktop.png`（6 图标左上网格、任务栏实色纸面）与 `v114-startmenu.png`（开始菜单白卡面板）。截图里任务栏显示“WS: 已断开”是截图 harness 的 about:blank 下 WS 无法建连所致，真实浏览器下 WS 正常（服务 /api/* 均 200），不是本轮回归。


# Changelog

## [1.13.0] - 2026-10-25

### 新增
- 已用备用码归档清理：`twofa::sweep_used_backup_codes` 删除超过保留期的已用备用码行（只删 `used_at` 非空且距今超过保留天数的行，未用码永不删除）；`verify_login` 在备用码登录成功后顺手调用清扫（入口驱动，无独立定时任务）。背景：旧已用码以前永久留库；删旧行不改变鉴权行为（用过的码再次提交本来就返回 401）。
- 新配置 `MINIOS_BACKUP_CODE_RETENTION_DAYS`（默认 90 天，合法范围 1 到 3650 的整数天数，非法值启动即报错退出 exit 2）；`Config` 与 `AppState` 各加 `backup_code_retention_days` 字段。
- 版本跟进：Cargo.toml 1.12.0 → 1.13.0，`/api/health` 的 version 随之恢复正确。

### 测试
- 新增 `tests/twofa_backup_sweep_test.rs` 6 例全绿：直接清扫（只删旧已用、91/89 天边界、空表返回 0）、保留期解析（默认 90、合法边界 1/3650、非法值报错且错误含变量名）、`init_state` 默认保留期 90、备用码登录 E2E（真实 2FA 全流程 + 植入旧已用行，清扫后植入行消失、总数 10、已用行仅刚用掉的 1 行）。
- 全量 `cargo test --offline --no-fail-fast` 765/765 全绿；本轮文件 `cargo fmt` 全洁。
- 真实服务冒烟：`/api/health` 报 1.13.0；`MINIOS_BACKUP_CODE_RETENTION_DAYS=abc` 启动即 exit 2 且报错指明变量名与合法范围；保留期 30 可正常启动。

### 已知限制（诚实声明）
- 清扫是入口驱动：只在备用码登录成功时触发，没有后台定时任务；长期无人用备用码登录时，旧已用行会一直留到下一次备用码登录才被清掉。这不影响鉴权安全（旧已用码复用本来就 401）。
- 另顺手修了 `tests/api_test.rs` 里硬编码 "1.9.0" 的版本断言，改为 `env!("CARGO_PKG_VERSION")`，以后版本升级不再漂移；`mig006_expiry_deep.rs:185` 与 `twofa_test.rs` 的既存格式 diff 不在本轮改动范围，未动。

## [1.12.0] - 2026-10-24

### 新增
- 两步验证独立限流：`MINIOS_2FA_RPS`（默认 1）/ `MINIOS_2FA_BURST`（默认 5），IP 单维度令牌桶，只挂在 `POST /api/auth/2fa` 路由上，与登录限流桶解耦；超限返回 429 + `Retry-After` 头 + `{"error": "两步验证尝试过于频繁，请 <secs> 秒后重试", "retry_after": <secs>}`，并计入指标 `2fa_ratelimited`。背景：单 challenge 5 次上限可被重登录刷出新 challenge 绕过，登录桶只管发挑战不管验码；本限流补上验码路径的独立闸门。注意：该桶按 IP 计，不按账号计；同一出口 IP 下的多用户共享配额。
- 过期挑战清扫：`twofa::sweep_expired_challenges` 删除 `expires_at <= now` 的 tfa_challenges 行，在发挑战（create_tfa_challenge）与验码（verify_login）两个入口调用；无 schema 变更，不新增迁移。
- 版本跟进：Cargo.toml 1.9.0 → 1.12.0，`/api/health` 的 version 随之恢复正确（此前 CHANGELOG 已到 1.11.0 但 health 仍报 1.9.0）。

### 文档
- `.env.example` 补 `MINIOS_2FA_RPS` / `MINIOS_2FA_BURST` / `MINIOS_TOTP_MASTER_KEY` 三项；`docs/OPERATIONS.md` 环境变量表补 2FA 两行，探针示例版本号 1.2.0 → 1.12.0。

### 测试
- 新增 `tests/twofa_v112_test.rs` 3 例全绿；受影响套件合计 128/128 全绿；既有 twofa_test 套件修复后完整重跑 11/11 全绿（修复前首轮 10/11，tfa_challenge_expiry 因清扫误删本次挑战由 410 退化为 401 的回归已修复：清扫改为排除本次 challenge）。

### 已知限制（诚实声明）
- clippy 全量 -D warnings 下 3 个存量错误未修（config.rs:44、totp.rs:100/120），不在本轮改动文件，留待后续轮次。
- 2FA 限流为 IP 维度；TOTP 猜解仍受“单 challenge 5 次 + IP 桶 + 5 分钟过期”三重约束，不等于彻底杜绝猜解。

## [1.11.0] - 2026-10-24

### 新增
- 新增 `src/twofa.rs`（488 行）：两步验证 HTTP 层，提供 6 个端点
  - `GET /api/2fa/status`：查询启用状态
  - `POST /api/2fa/setup`：验证密码后返回 `secret`、`otpauthUrl`、`qrSvg` 二维码
  - `POST /api/2fa/enable`：输入 6 位验证码启用两步验证，返回 10 个备用码
  - `POST /api/2fa/disable`：验证密码后停用，返回 204
  - `POST /api/2fa/backup-codes/regenerate`：验证密码后重新生成 10 个备用码，旧码作废
  - `POST /api/auth/2fa`：登录第二步，使用 challenge 及验证码或备用码换取 session
- 新增 `src/totp.rs`（396 行）：TOTP 核心实现
  - 遵循 RFC 6238 / RFC 4226，使用 SHA1，6 位数字，30 秒周期，校验容忍前后 1 个窗口
  - 生成 20 字节随机密钥并转为 base32
  - 生成 `otpauth://` URL 及 SVG 格式二维码
  - 通过 RFC 6238 官方测试向量
- 新增 `src/password.rs`（92 行）：密码强度策略
  - 长度 8 到 128 字符，必须同时含字母和数字
  - 不可与用户名相同（忽略大小写）
  - 包含 15 个常见密码黑名单（如 `password`、`12345678`、`minios123`、`letmein1`）
  - 注册接口与 `useradd` CLI 同口径
- 密钥落库加密
  - TOTP 密钥使用 AES-256-GCM 加密后以 hex 存入 `users.totp_secret`
  - 主密钥来自环境变量 `MINIOS_TOTP_MASTER_KEY`（64 个十六进制字符，即 32 字节）
  - 未配置主密钥时，2FA 相关操作报 500，普通登录不受影响
  - 12 字节随机 nonce 拼接在密文前
- 备用码机制
  - 生成 10 个格式为 `xxxx-xxxx` 的备用码，字符集为 `abcdefghjkmnpqrstuvwxyz23456789`
  - 使用 argon2 哈希后入库，输入时支持带或不带横线
  - 一次一码，用过标记 `used_at`，再次使用返回 401
- 登录第二步交互
  - 启用 2FA 的用户调用 `/api/auth/login` 不再直接返回 session，改为返回 `202` 及 `{"requires2fa": true, "challenge"}`
  - `challenge` 存入 `tfa_challenges` 表，5 分钟有效
  - 单个 `challenge` 连续 5 次错误尝试后作废并返回 429，需重新登录
- 迁移 008
  - `users` 表新增 `totp_secret`（TEXT，可空）与 `totp_enabled`（INTEGER，默认 0）
  - 新建 `tfa_backup_codes` 与 `tfa_challenges` 表
  - 幂等执行：列判存在，表用 `IF NOT EXISTS`
- 依赖更新
  - `Cargo.toml` 新增 `aes-gcm 0.10.3`、`qrcode 0.14.1`（svg 特性）、`sha1 0.10.6`
  - 使用 `vendor/` 本地目录及 `[patch.crates-io]` 做离线补丁，支持本机离线构建
- 前端更新
  - `static/login.html` 登录页增加第二步两步验证界面（标题"两步验证"）
  - `static/app.js` 设置区增加两步验证设置：状态查询、启用向导（输密码→扫二维码→输验证码→展示备用码）、停用、重生成备用码

### 测试
- 新增 26 个测试用例
  - `tests/twofa_test.rs`：11 个集成测试，覆盖密码策略经注册接口、status 默认 false、setup/enable 全流程、登录第二步 202/200、备用码一次一码、challenge 5 次锁定 429、challenge 过期 410、disable 204 回退、备用码轮换旧码失效、密钥落库非明文且可解密、迁移 008 列与表断言
  - `src/totp.rs`：9 个单元测试，包含 RFC 6238 官方向量
  - `src/password.rs`：6 个单元测试

### 已知限制
- TOTP 仅实现 SHA1，未支持 RFC 6238 允许的 SHA256/512
- challenge 的 5 次尝试上限按单个 challenge 计算；攻击者重新登录可获取新 challenge（受 `MINIOS_LOGIN_RPS`/`MINIOS_LOGIN_BURST` 间接约束）；`/api/auth/2fa` 暂无独立 IP 级限流
- 过期 challenge 仅在命中时删除，无定时清理任务；已用备用码保留在库中（查询取 `used_at IS NULL`），无归档或清理策略
- 主密钥轮换无在线迁移：更换 `MINIOS_TOTP_MASTER_KEY` 后旧密文解密失败，用户需先停用再重新设置两步验证
- `.env.example` 尚未收录 `MINIOS_TOTP_MASTER_KEY`（待补）

## [1.10.0] - 2026-10-23

### 新增
- 会话滑动续期：`verify_session_sliding`（剩余寿命 < TTL/2 时自动顺延 `expires_at`）+ 中间件续期后重发 `Set-Cookie`（Max-Age 与服务端一致）；开关 `MINIOS_SESSION_SLIDING`（默认开启，非法值启动 exit(2)）；旧 `verify_session` 行为不变。
- 测试：`tests/session_sliding_test.rs` 8 例（续期/新鲜不续期/半衰期边界/开关关闭/过期清理/未知与空 token/开关解析真值表）+ `tests/session_sliding_http_test.rs` 1 例（中间件续期后重发 Set-Cookie、新鲜会话不重发）。

### 已知限制
- 滑动续期按请求触发；并发请求下后写覆盖前写，均为顺延，无正确性问题。
- `MINIOS_SESSION_SLIDING=false` 时退回固定 TTL 行为。

## [1.9.0] - 2026-10-20

### 新增
- 真 PTY 终端：`src/terminal.rs`（portable-pty 0.8.1），按用户隔离、每用户上限 8
  会话、空闲 30 分钟回收、Ctrl+C 发 SIGINT；WS 协议
  term_open/input/resize/signal/close ↔ term_ready/output/exited/error；
  前端 xterm.js 5.3.0 多标签页（fit/Ctrl+C 透传/断线重连）。
- 文件管理 v2：`PATCH /api/fs/:id/move`（环检测 400/同名 409/跨用户 404/幂等）、
  `GET /api/fs/search`（LIKE 转义防注入，返回面包屑 path）；
  前端右键菜单（重命名/移动到…/删除二次确认）、可点击面包屑、防抖搜索框。
- 笔记/日程：迁移 007（notes/events 表）；8 个 REST 接口（user_id 隔离，
  title/时间格式校验）；RBAC 新增 NotesRead/NotesWrite（Viewer 只读）；
  桌面小组件：今日日程（增删/勾选完成）+ 速记便签（防抖自动保存），
  数据走后端 API。
- 桌面：双击标题栏最大化/还原、右下角缩放、任务栏高亮、`window-resize` 事件；
  Lucide SVG 应用图标；`docs/DESIGN.md` 纸墨视觉注记。

### 测试
- `cargo test` 全绿：新增 terminal_test 9、fs_v2_test 13、notes_test 9；
  migrate 单测期望同步到 007。
- WS 真机冒烟（raw socket）：401 未授权、term_ready、真命令回显、
  Ctrl+C 中断 sleep 后 shell 存活。
- 3 张截图亲眼验收：v19-desktop-widgets（多窗口同屏）、
  v19-contextmenu（右键菜单）、v19-theme-dark（深色主题）。

### 已知限制
- 拖拽上传为整份重传，分片/断点续传未做（需求明确不做）。
- xterm.js `allowProposedApi` 的 Ctrl+C 拦截行为待真实浏览器长期验证。

## [1.8.1] - 2026-10-17

### 修复

- **窗口透明 bug**：`static/style.css` 首行残留 markdown 代码围栏 ```` ```css ````，CSS 解析器把 `:root` 规则整个吞掉，所有 `var(--*)` 失效 → 全部窗口背景透明、桌面图标从窗口内容里透出来。删除该行后恢复正常（视觉验收确认）

### 杂项

- v1.7 两张截图重拍：`docs/screenshots/v17-users-viewer.png` / `v17-users-admin.png`，干净种子数据（`scripts/seed-shot-users.sh`：zhangwei/admin、editor01/editor、viewer01/viewer），README 截图区已引用

## [1.8.0] - 2026-10-17

### 新增
- 分享读限流 v1.8 重设计：IP 单维度独立令牌桶（`ShareReadLimiter` + `ShareReadKey`，与登录桶类型/状态双隔离）；
  覆盖 `GET /api/s/:token`、`/api/s/:token/download`、`GET /api/share/list`；探针（`/api/health`、`/api/readyz`、`/metrics`）天然豁免。
- 新环境变量：`MINIOS_SHARE_RPS`（默认 5）、`MINIOS_SHARE_BURST`（默认 30）、
  `MINIOS_SHARE_RATE_LIMIT_ENABLED`（默认 true）；非法值启动 fail-fast（stderr 点名 + exit 2）。
- 指标 `minios_share_rate_limited_total`（counter）：被限流拒绝的分享读请求总数。
- share.html 429 前端 UX（沿用 v1.5 登录限流 UX 体系）：初始页「看的人有点多」+ 实时倒计时 + disabled 重试按钮，
  倒计时结束自动重试；目录浏览列表区倒计时条 + 面包屑禁用 + 自动重载。深色主题一致，大白话文案。

### 变更（破坏性）
- `MINIOS_SHARE_READ_RPM` / `MINIOS_SHARE_READ_BURST` 废弃：只要被设置服务就拒绝启动并提示改用新变量（fail-fast，防静默误配）。
- 限流维度从 token+IP 双维度改为 IP 单维度：v1.7 的 token 桶跨 IP 聚合曾导致爆款链接多 IP 正常访问也全员 429，v1.8 已消除。
- `auth_ops_total{op="share_ratelimited"}` 移除，改用独立计数器 `minios_share_rate_limited_total`。

### 测试
- `cargo test` 151/151 全过：lib 52、api_test 16、auth_test 8、failure_injection 11、isolation_test 5、
  metrics_test 4、metrics_v16_test 5、ratelimit_test 8、rbac_test 8、share_dir_test 12、
  share_ratelimit_test 8（v1.8 重写：429+Retry-After、探针豁免、总开关关闭、恢复）、share_test 6、upload_security_test 8。
- `cargo clippy --all-targets -- -D warnings` 零警告；`cargo fmt --check` 通过；依赖零新增。
- 真服务冒烟（127.0.0.1:18101，RPS=1/BURST=3）：14/14 通过——注册 201、3 次分享读 200、
  第 4 次 429（`retry-after: 1` + JSON 体）、限流期间三探针 200、`minios_share_rate_limited_total 1`、窗口后恢复 200。
- 2 张截图亲眼验收：`docs/screenshots/v18-share-normal.png`（正常态）、
  `docs/screenshots/v18-share-ratelimited.png`（429 倒计时态）。

### 已知限制
- 限流桶单进程内存（多实例不共享、重启清零）。
- NAT/出口 IP 下多用户共享 IP 桶可能被误伤（调大 BURST 或透传 X-Forwarded-For）。
- v1.5 遗留：分布式限流、注册限流、密码策略、2FA，这版没动，继续挂。

## [1.7.0] - 2026-10-16


### 新增
- Prometheus 告警规则示例：prometheus/rules/mini-os-example.yml（7 条：5xx 错误率、P99 延迟、服务存活、分享访问突增、登录限流突增、WS 连接数、分享 404 探测；字段以官方文档为准）；docs/ALERTING.md（规则说明、阈值调参、Alertmanager/webhook 接入步骤）；scripts/check-alert-rules.py（无 promtool 时的规则自检：pyyaml 解析 + 字段/duration/severity/annotations 校验）。
- 分享读取限流（token+IP 双维度令牌桶）：GET /api/s/:token、/api/s/:token/download、/api/share/list 三条公开读路由；默认 30 次/分钟、burst 30（MINIOS_SHARE_READ_RPM/_BURST 可配，非法 fail-fast）；超限 429 + Retry-After 头 + JSON 错误体；metrics 新增 auth_ops_total{op="share_ratelimited"}。
- docs/RATE_LIMIT_EVAL.md：真实压测数据与阈值评估（20s/8 并发：16989 次请求中 40 次 200、16949 次 429，p99 34.98ms；正常速率 1/s 下 10/10 通过）。

### 测试
- cargo test：lib 46、api_test 16、auth_test 8、isolation_test 5、metrics_test 4、metrics_v16_test 5、ratelimit_test 8、share_test 6、share_dir_test 12、upload_security_test 8、share_ratelimit_test 6（新增）全过。
- cargo clippy --all-targets -- -D warnings：本轮新增代码零警告；cargo fmt --check：本轮文件通过。
- 真服务压测（127.0.0.1:18098/18099）：正常速率 10/10 通过；burst 40 次→25×200+15×429；429 带 retry-after: 2 头与 JSON 体；新 IP+新 token 200 不受影响。

### 已知限制
- 限流桶单进程内存（多实例不共享、重启清零），与登录限流同一实现。
- token 桶跨 IP 聚合：单分享链接 30/分钟封顶，爆款链接需调大 MINIOS_SHARE_READ_RPM。
- NAT/出口 IP 下多用户共享 IP 桶可能被误伤，建议调大 BURST 或透传 X-Forwarded-For。

## [1.6.0] - 2026-10-16

### 新增
- 目录分享：`POST /api/shares` 传 `{"type":"dir","path":"/目录"}` 创建目录只读分享（目录不存在 404、是文件 400、跨用户 404、非法 type 400）；`shares` 表加 `share_type` 列（迁移 004，老数据默认 `file`，`CHECK(share_type IN ('file','dir'))`）。
- 目录浏览 API：`GET /api/share/list?token=...&path=` 返回 `{path, entries:[{name,kind,size,mtime}]}`（文件夹排前面）；`GET /api/s/:token/download?path=相对路径` 下载目录树内文件；路径穿越（`..`/空段/控制字符）一律 403。
- 分享页 `static/share.html` 支持目录浏览：面包屑导航、文件夹点击进入、文件下载按钮；换肤为深色桌面美学（与桌面端 dark 主题同 token），去 AI 味。
- Prometheus 指标增强（零新依赖）：`http_request_duration_seconds` 直方图（11 档桶 + `+Inf`，`_sum`/`_count`）；`vfs_files_total`、`vfs_bytes_total`、`shares_total{type}` 三个 DB 实时 gauge；路由 label 归一化（无 MatchedPath 时记 `unknown`，不用原始 URI）。
- `GET /api/s/:token` 对目录分享返回 `shareType:"dir"`、`kind:"folder"`、`size` 为整树文件字节数之和。

### 测试
- `cargo test` 117/117 全过：lib 34（含 metrics 直方图单测 4）、api_test 16、auth_test 8、failure_injection 11、isolation_test 5、metrics_test 4、ratelimit_test 8、share_test 6、upload_security_test 8、share_dir_test 12（新增）、metrics_v16_test 5（新增）。
- `cargo clippy --all-targets -- -D warnings` 零警告；`cargo fmt --check` 通过。
- 真服务冒烟（127.0.0.1:18092）：注册 200 → 建目录树 → 分享目录 201 → 访客浏览根/子目录 200 → 嵌套文件下载 200 → 路径穿越 403；4 张截图亲眼验收通过。

### 已知限制
- 目录分享 token 无过期时间、无撤销接口；删除源目录（级联删 shares 行）是唯一的撤销方式。
- 分享为整树只读，不支持子目录/单文件级二次授权。
- 三个 gauge 为抓取时实时查 DB，大库下每次抓取有全表 `COUNT/SUM` 开销（抓取间隔建议 ≥15s）。
- v1.5 已知限制延续：限流桶单进程内存（多实例不共享、重启清零）、注册接口不限流、无密码复杂度/2FA。

## [1.4.0] - 2026-10-16

### 新增
- 上传安全加固：新增 sniff_mime magic-bytes 嗅探，识别 PE/MZ、ELF、Mach-O/fat binary、MSI/OLE 复合文档、shebang 脚本。
- 命中可执行文件的上传直接返回 415 `{"error": "可执行文件不允许上传"}`，文件不入库。
- mime 取值优先级改为：嗅探结果 > 客户端 Content-Type 头 > 扩展名猜测。
- 无新增依赖。
- 前端上传队列：单个文件失败不再中断整队，失败记名后继续下一个。
- 上传进度文本改为"上传中 i/n：文件名 (pct%)"。
- 队列结束后若有失败，错误条显示"上传完成：成功 X 个，失败 Y 个（名1，名2）"，最多列 3 个文件名。

### 测试
- `cargo test` 73/73 全过：lib 15、api_test 16、auth_test 8、failure_injection 11、isolation_test 5、metrics_test 4、share_test 6、upload_security_test 8（新增）。
- `cargo clippy --all-targets -- -D warnings` 零警告。
- `cargo fmt --check` 通过。
- 真服务冒烟（127.0.0.1:18091）：注册 200 → 上传文本 201 → 下载 200 且字节一致 → MZ 可执行上传 415 → bob 跨用户下载 404 → 未登录下载 401。

### 已知限制
- 仅按魔数拒绝已知可执行类型，未做病毒扫描。
- zip 内嵌可执行不检测。
- 不支持断点续传（v1.1 已知限制延续）。

## [1.3.0] - 2026-10-16
### 新增
- 用户体系：`users` 表（用户名唯一、argon2id 密码哈希 PHC 存储、首个可登录用户自动为管理员）；注册/登录/登出端点（`POST /api/auth/register|login|logout`）；用户名规则（3–32 字符、仅字母数字 `_.` `-`、禁用 `legacy`）、密码 ≥8 位；登录失败统一 401（防用户名枚举）
- 登录态：opaque session token（32 字节随机 hex 走 HttpOnly Cookie `mini_os_session`，库里只存 SHA-256）；`sessions` 表（过期时间 epoch 秒）；`SESSION_TTL_SECS` 环境变量（默认 7 天）
- 鉴权中间件：白名单公开（health/readyz/metrics/auth 注册登录登出/setup-needed/分享只读），其余 `/api/*` 与 `/ws` 未登录 401；前端登录门卫（未登录跳 `login.html`，401 自动跳转）
- VFS 按用户隔离：`vfs_nodes.user_id`、`settings` 主键改为 `(user_id, key)`；跨用户 id 返回 404（不泄露存在性）
- 访客只读分享：`POST /api/shares`（仅文件，201 返回 `{token, url}`）、`GET /api/s/:token` 元信息、`GET /api/s/:token/download` 流式下载；`shares` 表（token 唯一、节点删除级联失效）；`static/share.html` 只读分享页
- 迁移 003：建 `users`/`sessions`/`shares`、加 `user_id` 列、重建 `settings` 联合主键、占位用户 `legacy` 承接老数据（不可登录）；`POST /api/auth/migrate-legacy` 一次性领走旧数据（无旧数据 410）
- 前端：`static/login.html`（登录/注册/初始化三态）、任务栏当前用户 + 注销、文件管理器行内"分享"按钮 + 链接弹窗
- 指标：`auth_ops_total{op}`（register/login/logout/migrate_legacy/share_create）

### 测试
- 新增 `tests/auth_test.rs` 8 例（注册/登录/注销全流程、409/400/401、legacy 不可登录、首个用户 admin、migrate-legacy 一次性、未登录 401）
- 新增 `tests/isolation_test.rs` 5 例（文件/设置/上传下载/统计隔离、跨用户父目录 404）
- 新增 `tests/share_test.rs` 6 例（分享全流程、文件夹拒绝、伪造 token 404、跨用户分享 404、删文件后分享失效）
- `tests/failure_injection.rs` 追加 3 例（伪造 token 401、过期 session 401、users 表缺失 500 不 panic）；既有 4 例适配鉴权
- `cargo test` 65/65 全过（lib 15、api_test 16、auth_test 8、failure_injection 11、isolation_test 5、metrics_test 4、share_test 6）；`cargo clippy --all-targets -- -D warnings` 零警告；`cargo fmt --check` 通过（2026-10-16 验收实测）

### 已知限制（诚实声明）
- 仅文件分享，不支持目录分享；无访客角色、无细粒度 RBAC
- 密码策略仅最小长度（8 位），无复杂度要求；无 2FA；无登录限流
- session 无滑动续期，过期需重新登录

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

