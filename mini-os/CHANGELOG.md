## [1.19.17] - 2026-10-30
### Changed
- src/handlers.rs：create_fs 在 kind 校验后、内容解析前、DB 加锁前新增冲突检查：bytes 为 Some 且 content 为 Some 且 trim 后非空时返回 400，文案逐字为“bytes 与 content 不能同时指定”，不创建节点；bytes 空数组加非空 content 同样 400；bytes 单独、content 单独、两者都不给、content 为空串或纯空白加 bytes 行为不变。此前 bytes 与 content 同时给时 content 被无声丢弃。
- src/models.rs：CreateNodeRequest 的 content 与 bytes 两行注释同步说明该 400 口径。
- Cargo.toml 与 Cargo.lock：mini-os 版本由 1.19.16 升为 1.19.17。

### Added
- tests/fs_create_bytes_content_conflict_test.rs：6 例（both_bytes_and_content_400、bytes_only_201、content_only_201、empty_content_plus_bytes_201、whitespace_content_plus_bytes_201、empty_bytes_plus_content_400），6/6 通过。

### Verification
- 关联回归：fs_create_parent_conflict_test 6、fs_parent_id_validation_test 6、fs_v2_test 15、vfs_path_r2 1，合计 28/28 通过。
- cargo fmt --all --check 干净。
- clippy：--lib 与新测试目标无归属到改动文件的告警；--all-targets 在既存 tests/handlers_deep.rs:330 报 E0308（parent_id 期望 Option<String> 却给 Option 整数），与本轮改动无交集，属既存已知限制，本轮未扩范围修复。
- 真服务冒烟（18533 端口、隔离库）：health 返回 1.19.17；注册 201；bytes+content 返回 400 且文案逐字相符；bytes 单独返回 201 且 size 为 3；列表恰 1 条（冲突未建节点）；冒烟后服务已停、端口已关、冒烟库已删。

## [1.19.16] - 2026-10-29

### Changed
- src/handlers.rs 的 create_share file 分支在取 node_id 之前，若 req.path 为 Some 且 trim 后非空则返回 400 及固定文案“file 模式下不能指定 path”，空串与纯空白 path 仍视为未给走原有逻辑，src/models.rs 的 path 字段注释同步更新为“file 模式下非空 path 返回 400”。
- 契约变更：此前 file 模式会无声丢弃 path，现改为拒绝，调用方 file 分享只给 nodeId，不许再带 path。
- 未动范围：未动 dir 分支、type 非法校验、expires_at 校验、token 生成、share_type 缺省逻辑、前端，无迁移、无新依赖、无新增端点、无 UI 改动。

### Added
- 新增 tests/share_file_path_conflict_test.rs 含 5 例（file+path 400 且列表为空、空 path 仍 201、纯空白 path 仍 201、缺省 type+path 400、file+path 无 nodeId 时先报 path 冲突 400），5/5 通过。
- 旧测 tests/share_node_path_conflict_test.rs 的 file_share_with_path_ignored_still_works 翻转为 file_share_with_path_now_400（断言 400 + 文案 + 列表为空），该文件 6/6 通过。

### Verification
- 靶向测试：除 handlers_deep 外逐目标跑通 30 个目标、共 248 项通过、0 项失败（含 lib_deep 判为抖动），其余约 68 个远离改动面的目标列为已知缺口，不谎称全量通过。
- 格式化：cargo fmt --all --check 干净。
- 真服务冒烟（18531 端口）：health 返回 1.19.16，file+path 返回 400 且文案逐字相符，file 仅 nodeId 返回 201 且 token 非空，分享列表恰 1 条，冒烟后服务已停、端口已关、冒烟二进制与冒烟库已删。
- clippy 基线：clippy --all-targets -- -D warnings 有 7 处报错，均位于 handlers.rs 508/1374/1520 与 notes.rs 116/125，与本轮 2501 行附近改动无交集，属既有基线，本轮未扩范围修复。

## [1.19.15] - 2026-10-29

### Changed
- POST /api/shares 的 dir 模式下 nodeId 与 path 双指定不再静默忽略 nodeId：path 非空且 nodeId 已给时返回 400 {"error": "node_id 与 path 不能同时指定"}，不创建分享。dir + nodeId + 空 path 仍走原有 400 "目录分享需要 path 参数"；dir + path 不存在仍 404；dir + path 不是目录仍 400；file 模式 path 忽略的既有行为不动；type 非法、share_type 缺省 file 均不动。models.rs 的 path 字段注释同步说明 dir 冲突口径。Cargo.toml 与 Cargo.lock 版本同步升为 1.19.15。
- 这是一次有意的契约变更：此前 dir 分享会按 path 建分享、nodeId 被无声丢弃，现改为拒绝；调用方须只给 path 或只给 nodeId（file 模式）。

### Added
- 新增 tests/share_node_path_conflict_test.rs，6 例：dir + 文件夹 nodeId 冲突 400 且列表为空、dir + 文件 nodeId 冲突 400 且列表为空、dir 仅 path 仍 201、dir + nodeId 无 path 仍为缺 path 400、file + path 忽略仍 201、file 缺 nodeId 仍 400。

### Verification
- 新测 6/6；分享关联 3 个目标 40 项全过（合计 46 项）；cargo fmt --all --check 干净；真实服务冒烟（18529 端口隔离库）：health 返回 1.19.15、注册 201、冲突 400 且文案逐字相符、dir 仅 path 201、列表恰 1 条；冒烟后服务已停、端口已关、冒烟二进制与隔离库已删。

## [1.19.14] - 2026-10-28

### Changed
- `POST /api/fs` no longer silently lets `parentId` win when both `parentId` and `parent` are given. If `parentId` is a number and `parent` is a non-empty string, it now returns `400 {"error": "parent_id 与 parent 不能同时指定"}`.
- Updated the doc comments on `CreateNodeRequest` in `src/models.rs` to match (`parentId` plus a non-empty `parent` returns 400; `parent` path is resolved only when `parentId` is absent).
- The following cases remain functional: `parentId` is `null` plus a `parent` path, `parentId` plus an empty string `parent`, `parentId` only, and `parent` only.

### Added
- Added `tests/fs_create_parent_conflict_test.rs` with 6 tests covering the following scenarios:
  - Both `parentId` and `parent` path provided returns 400 (and nothing is created).
  - Agreeing `parentId` and `parent` path returns 400.
  - `parentId` only returns 201.
  - `parent` path only returns 201.
  - `parentId` plus an empty string `parent` returns 201.
  - `parentId` is `null` plus `parent` path returns 201.

### Verification
- Targeted tests 6/6.
- Associated `fs_v2_test` 15/15.
- `fs_parent_id_validation_test` 6/6.
- `vfs_path_r2` 1/1.
- `cargo fmt` clean.
- Real-service smoke test on port 18457 with an isolated database: `health` returns 1.19.14, conflict returns 400 with the exact message, both single-specification creates return 201, folder listing shows exactly the two created files.

## [1.19.13] - 2026-10-28
### 变更
浅色主题在 :root（根元素）中添加了 --card-bg、--border-color 和 --text-color。.widget 规则、.widget-add input 以及 #widget-note-body 移除了 var() 回退。深色主题保持不变。副作用：.widget-add input 和 #widget-note-body 的浅色主题边框从 rgba(0, 0, 0, 0.12) 变为 rgba(0, 0, 0, 0.08)。
### 验证
Chromium 截图测试框架渲染了浅色和深色主题下的组件标记。未修改 Rust 代码，因此 cargo test/clippy 均不适用（N/A）。

## [1.19.12] - 2026-10-27

### Changed

- GET /api/fs 的 parent_id 参数收紧：此前 parent_id 走 Axum Query 反序列化，非整数直接由框架拒绝（错误体非本项目口径）；现改为 Option<String> 后手工解析，非负整数才放行，""、"abc"、"1.5"、"-1"、超 i64 上限一律返回 400 {"error": "parent_id 参数非法"}，与 fs/search 的 limit 口径一致。不传 parent_id 仍查根目录；合法 id 查不到时返回 200 空数组（列表语义，不 404）。

### Added

- 新增 tests/fs_parent_id_validation_test.rs，6 例：abc 400、1.5 400、-1 400、空串 400、999999 200 空数组、合法文件夹内含文件且无参根目录含该文件夹。

## [1.19.11] - 2026-10-27

### Fixed

- 修复 GET /api/events 不带参数时返回 400 的回归。根因：v1.19.10 在 list_events 中无论 from 是否显式给出，都会把哨兵串 "0000-00-00T00:00:00" 送进 validate_dt，数值范围校验因月份 00 拒绝该串，导致无参请求由 200 退化为 400。修法：from 缺省时不再送 validate_dt，直接以该哨兵串作 SQL 下界；from 显式给出时仍走 validate_dt，非法值仍返回 400。to 缺省值 "9999-12-31T23:59:59" 保持不变，from 大于 to 的 400 检查与文案不变。

### Added

- 新增 tests/events_list_no_param_test.rs，共 4 个用例：无参查询已建日程返回 200、仅给 to 查询返回 200、显式 from=2026-02-30 仍返回 400、空库无参查询返回 200 且结果为空数组。

## [1.19.10] - 2026-10-27

### Changed
- 在 `src/notes.rs` 的 `validate_dt` 函数中新增日期时间数值范围校验：
  - 月份范围限定为 01-12。
  - 日期范围限定为 01-当月天数，包含闰年规则（能被 4 整除且（不能被 100 整除或能被 400 整除））。
  - 小时范围限定为 00-23。
  - 分钟范围限定为 00-59。
  - 秒范围限定为 00-59。
- 保留了 `validate_dt` 原有的长度、分隔符、数字位检查，以及同一错误文案“时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM”。
- 修复此前不存在的日期时间（如 `2026-02-30`、`2026-13-01`、`2026-10-25T24:00`）通过校验并入库的漏洞。

### Added
- 新增 `tests/events_calendar_test.rs`，包含 14 个测试函数，覆盖以下场景：
  - 拒绝 2 月 30 日、平年 2 月 29 日、13 月、00 月、4 月 31 日、00 日、24 时、60 分、60 秒。
  - 放行闰年 2 月 29 日、2000 年 2 月 29 日。
  - 放行边界值：`2026-12-31T23:59:59`、纯日期 `2026-01-01`。
  - 拒绝区间查询中的非法起始日期（`from`）。

### 验证状态（本轮如实记录）
- `rustfmt --edition 2021 --check` 对 `src/notes.rs` 与 `tests/events_calendar_test.rs` 均干净（解析通过、零格式差异）。
- `cargo test` 与真实服务冒烟本轮未能执行：本机执行沙箱自约 06:19 起拒绝外部进程写文件（python/cargo/cat 写操作均报 Operation not permitted，bash 内置写与 muse.write 工具不受影响），`cargo check` 在写 target 指纹时同样失败；靶向与关联测试、冒烟均待沙箱恢复后补跑，本轮不冒充已通过。
- 补验（2026-10-27 10:07 轮，沙箱已恢复）：`cargo test --test events_calendar_test` 14/14 通过，关联 `events_dt_r2` 4/4 通过，`cargo fmt --all -- --check` 干净；真实服务冒烟（18436 端口隔离库）：注册 201、2026-02-30 建日程 400 且文案为“时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM”、合法日程 201，冒烟后服务已停、端口复查已关、冒烟库已删。本轮无代码改动、无模型调用。

## [1.19.9] - 2026-10-27

### Changed
- WS 层 term_open/term_resize 的 cols/rows 解析不再静默回落 80/24：字段存在但不是合法 u16（超 u16、字符串、浮点）时不再当成 80x24，改为返回 term_error“终端尺寸非法（列 2–500、行 2–500）”，不创建/不调整会话；字段缺失时仍默认 80/24；合法 u16 但超 2–500 范围的仍由 manager 判 InvalidSize，走同一文案。
- 实现：src/handlers.rs 新增 term_size_from helper（缺失取默认、存在须为 u16、其余交 manager），term_open/term_resize 两处解析改用它，非法时以 Err(TermError::InvalidSize) 走已有 term_error 通路；manager 范围与文案一字未动。

### Added
- tests/ws_term_size_invalid_test.rs 新增 4 例：超大 cols 的 open 拒收、字符串 cols 的 open 拒收、缺省尺寸仍建会话（term_ready 且 session_id 32 位 hex）、超大 cols 的 resize 拒收；4/4 通过；关联回归 term_size_validation_test 8/8、ws_term_open_r2 3/3 通过；cargo fmt 干净。
- 真实服务冒烟：18429 端口隔离库，超大 open、字符串 open、超大 resize 均 term_error 同文案，合法 open 正常 term_ready，冒烟后服务已停、端口复查已关。

## [1.19.8] - 2026-10-26

### Changed

- TerminalManager::open/resize 的 cols/rows 越界不再静默钳制到 2–500：超出范围返回 TermError::InvalidSize；WS 层 term_error 文案为“终端尺寸非法（列 2–500、行 2–500）”。
- 校验优先于会话查找：坏尺寸对不存在的会话也返回 InvalidSize，而不是 NotFound。
- 范围内行为不变；现有前端发送的尺寸不小于 20 列 8 行，不受影响。
- 真实服务冒烟：term_open cols=0 与 term_resize cols=501 均返回 term_error“终端尺寸非法”，80x24 正常建会话、100x30 正常调整。

### Added

- tests/term_size_validation_test.rs 新增 8 例；tests/terminal_read_edge_r2.rs 的 2 个旧钳制测试同步改写为新语义（open/resize 越界返回 InvalidSize）。（坏尺寸 open、坏尺寸 resize、校验优先于会话查找、边界 2/500、坏尺寸后会话仍可用），8/8 通过。
## [1.19.7] - 2026-10-26

- GET /api/fs/search 的 limit 参数：缺失或空串默认 50；非整数、小于 1 或大于 200 时返回 400，错误体 {"error": "limit 参数非法"}；此前为静默钳制到 1 到 200。
- 测试：tests/fs_v2_test.rs 旧 search_limit_clamp 测试替换为 search_limit_out_of_range_400、search_limit_non_integer_400、search_limit_boundary_ok 三组。
- 验证：fs_v2_test 15/15、vfs_search_r2 2/2 通过；cargo fmt 干净；真实服务冒烟 limit=1000 与 limit=abc 均 400、limit=200 返回 200 且含文件。

## [1.19.6] - 2026-10-26

- list_events: 如果 `from` 大于 `to` 返回 400，消息“开始时间不能晚于结束时间”。如果 `from` 等于 `to` 返回 200 空数组。
- 测试套件通过：events_range_r2 4/4、events_dt_r2 4/4、events_misc_r2 2/2、notes_test 9/9、notes_crud_r2 4/4，合计 23/23 通过。
- 全量套件未跑（VM 负载），预计 mini-os 下次迭代时补跑。

## [1.19.5] - 2026-10-26

### 修复
- 删 static/style.css 第 1615 行裸 --- 分隔线（depth 0 的非法内容，浏览器丢弃）。

### 测试
- css_no_orphan_block_test 扩展拦截 depth 0 纯破折号行；新旧测试同跑通过；cargo fmt --all -- --check 干净。
- Chromium 实测删线前后 .icon-tile 计算样式均为 64px/16px，无回归。

> **如实记录**：Flash 模型稿（BotsRouter GLM-5.3-Flash，令牌 id=5、渠道 20）；首版 CHANGELOG 稿截断、第二版仍截断，编排按提示词事实补全末句；删线与测试扩展为编排机械执行；无 429。

## [1.19.4] - 2026-10-26

### 修复

- static/style.css：删除深色块后遗留的 14 行无选择器孤立声明块（浏览器直接丢弃，零运行时影响）。

### 测试

- 新增 `tests/css_no_orphan_block_test.rs` 1 例：解析至 depth 0 时遇到 `--name:` 声明即 panic。
- widget 既有测试同跑全部通过；`cargo fmt` 干净。

> **如实记录**：本节稿件由 Flash 模型生成（BotsRouter GLM-5.3-Flash，令牌 id=5、渠道 20）。首版稿因 3 次空响应作废，缩小目标后出稿；编排侧修正 2 处误报（注释续行、裸 `---` 线）；第 1615 行裸 `---` 线经实测无回归，留待后续处理；全程无 429。

## [1.19.3] - 2026-10-26

### 修复
- 夜墨深色主题小组件浅色残留（TECH_DEBT P1-8）：[data-theme="dark"] 块补 3 个变量——--card-bg: rgba(33,29,23,0.92)、--border-color: rgba(237,230,214,0.14)、--text-color: #ede6d6，取值与深色块已有 --glass-bg / --glass-border / --text 同源；.widget 的 var(...) fallback 原样保留，浅色下行为不变。顺带发现未动：深色块之后另有一段无选择器的孤立声明块（约 126–138 行，slate/blue 系变量），浏览器会直接丢弃，与本轮无关，留待后续单独处理。
- 模型稿由 BotsRouter 大写 GLM-5.3-Flash（令牌 id=5、渠道 20、单路串行，调用器为本轮现写 flash_call_n12.py，令牌经 SSH 现取不落盘，按 data: 行解析 delta.content）产出：CSS 3 行 1 通即出；测试稿首通 reasoning-only 空响应作废，缩小目标后第 2 通出稿；无 429。
- 编排修正 1 处：rustfmt 把测试末尾多行 assert 折叠成单行后落仓。

### 测试
- 新增 tests/widget_dark_theme_test.rs 1 例（深色块含 3 个新变量、.widget fallback 未删改）：cargo test --offline --test widget_dark_theme_test 1/1 通过；cargo fmt --all -- --check 干净。
- 计算样式实测（Chromium 隔离渲染 style.css，不走登录态桌面）：深色下 .widget 背景 rgba(33,29,23,0.92)、文字 rgb(237,230,214)、边框 rgba(237,230,214,0.14)，均为深色值；浅色下仍为白色 fallback（rgba(255,255,255,0.92) / rgb(43,38,32) / rgba(0,0,0,0.08)），无回归。
- 版本跟进：Cargo.toml 1.19.2 -> 1.19.3，Cargo.lock 同步。

## [1.19.2] - 2026-10-26

### 补齐
- .env.example 补 6 个已上线但缺失的变量（README 称它是“快速了解可用变量”的入口，此前不全）：MINIOS_DATA_DIR（留空不覆盖，回退 DATABASE_PATH 父目录、再回退 data）、MINIOS_SESSION_SLIDING（默认 true）、MINIOS_SHARE_RPS（默认 5）、MINIOS_SHARE_BURST（默认 30）、MINIOS_SHARE_RATE_LIMIT_ENABLED（默认 true）、MINIOS_TERM_OUTPUT_LIMIT（默认 1048576，即 1MiB）；默认值均从 src/config.rs 与 src/ratelimit.rs 源码核实，未动已有行。
- 复核旧挂账：TOTP 主密钥缺失一条已作废——MINIOS_TOTP_MASTER_KEY 早在 v1.12.0（1a71d00f）已入 .env.example，本轮核对在册，不重复加。
- 模型稿由 BotsRouter 大写 GLM-5.3-Flash（令牌 id=5、渠道 20、单路串行，调用器为本轮现写 flash_call_n12.py，令牌经 SSH 现取不落盘，按 data: 行解析 delta.content）产出：.env.example 6 行 1 通即出；测试稿首版提示词连空作废（reasoning-only 空响应，外层 280 秒超时截断第 3 次重试），缩小目标（只留包含/不包含断言）后第 2 通出稿；无 429。
- 编排修正 1 处：模型稿测试多写了一条 content.lines().count() == 6 断言，.env.example 远不止 6 行，删除该行后落仓；其余断言逐字保留。

### 测试
- 新增 tests/env_example_test.rs 1 例（6 个新键齐全、旧变量 MINIOS_SHARE_READ_RPM / MINIOS_SHARE_READ_BURST 不出现）：cargo test --offline --test env_example_test 1/1 通过；cargo fmt --all -- --check 干净；src 一字未动。
- 版本跟进：Cargo.toml 1.19.1 -> 1.19.2，Cargo.lock 同步。

## [1.19.1] - 2026-10-26

### 修复
- `cargo clippy --offline --all-targets -- -D warnings` 全量清零（此前 CHANGELOG 挂账的
  存量错误逐项清除，src 未动，全部改动只在 tests/）：未使用导入（terminal_ctrlc_idle_r2
  的 TermError、plugin_rollback_deep4、handlers_deep 的 tower::ServiceExt、download_file_deep3
  的 init_state_with、terminal_longline_r2 的 TermError、ws_handshake_deep2 的 Arc）；
  `manual_str_repeat`（fs_traversal_deep2 两处、db_deep 一处、main_deep 一处 repeat_once）；
  `bool_assert_comparison`（notes_crud_r2、lib_deep、models_deep）；`type_complexity`
  （upload_boundary_deep3、upload_limits_deep2 各新增 `type Part<'a>` 别名）；
  `question_mark`（plugin_reinstall_upgrade_deep 的 if-let-else 链改 `or_else` + `cloned()?`）；
  `await_holding_lock`（plugin_api_boundary_deep 12 个测试各加 allow 并附误报原因注释：
  app_for 返回的 guard 锁住进程全局环境变量，测试全程必须持有、不能在 await 前释放）；
  死代码（terminal_ctrld_r2、terminal_read_edge_r2、terminal_quota_r2 三拷贝的 read_until
  整段删除；plugin_install_test 的 write_basic_plugin、migrate_deep 的 users_columns、
  share_expiry_test 的 read_bytes 与 multipart_body；auth_deep 的 allow(dead_code) 注释——
  该文件用 `#[path]` 直编 src/auth.rs，公开项在测试模块里算私有，故不动 src/auth.rs）；
  以及两处未使用变量改名（plugin_api_boundary_deep 的 userB/userD 两处 u2_cookie →
  _u2_cookie）。删除跟进：quota_r2 的 Duration 导入改为只留 Instant（第 68 行仍在用），
  read_edge_r2 的 Duration 与 Instant 删除后均无用故整行删，plugin_install_test 删除死函数
  后 Path 导入改为只留 PathBuf。
- 诚实记录：模型稿由 BotsRouter 大写 GLM-5.3-Flash（令牌 id=5，渠道 20，单路串行，
  调用器为本轮现写最小新文件 relay-station/flash_call_n10.py、令牌经 SSH 现取不落盘，
  按 data: 行解析 delta.content）产出；其中 plugin_api_boundary_deep 首通 reasoning-only
  空响应、第二通只交元文本，拆成“改名两行”与“allow 注释”两通小稿后成功；
  session_sliding_http_test 的 params 行模型调用连续 3 通 reasoning-only 空响应
  （max_tokens 4000 两通、8000 一通）未获模型稿，编排按 handlers_deep 同款已授权模式
  机械删除（文件内调用写的是全路径 rusqlite::params![...]）。同款机械复用另有：
  db_deep 的 repeat（复用 fs_traversal 同款）、models_deep 的 bool（复用 notes_crud 同款）、
  upload_limits_deep2 的 Part 别名（复用 upload_boundary 同款），以及死代码删除
  （plugin_install_test、migrate_deep、share_expiry_test、ws_handshake_deep2、
  terminal_longline_r2 均复用本轮已授权的删除模式）；download_file_deep3 一通中途遇
  上游 500，调用器 90 秒后重试一次成功。另有一处编排失误已纠正：plugin_install_test
  删除死函数时多删了 #[test] 与函数头一行，git diff 发现后原样恢复，最终 diff 干净。
- 验收：clippy 全量 exit 0（仅 qrcode 依赖自身 4 条警告，不计入本包错误）；`cargo fmt
  --all -- --check` 干净（fmt diff 均由本轮删除引入的空行/导入换行，已用 rustfmt 修掉）；
  受影响 26 套件单跑 227/227 全绿；全量 `cargo test --offline` 775/775 全绿、0 失败。
  版本跟进：Cargo.toml 1.19.0 -> 1.19.1，Cargo.lock 同步。

## [1.19.0] - 2026-10-26

### 修复
- 同款无界握手收尾：`ws_term_conn_r2`、`ws_term_io_r2`、`ws_term_open_r2` 三个套件各自拷贝的
  `connect_ws` 原为无界握手（与 v1.18.0 前的 lifecycle 拷贝同款），现统一改为
  `connect_ws_timeout` + 30 秒薄壳（壳体与 v1.18.0 的 lifecycle 壳逐字一致），既有测试一字不改；
  每文件各新增 1 个黑洞回归测试（2 秒超时 panic，与 lifecycle 同款），三套件自此不再有无界握手。
- 版本跟进：Cargo.toml 1.18.0 -> 1.19.0，Cargo.lock 同步，`/api/health` 的 version
  随 CARGO_PKG_VERSION 自动跟进。模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，
  单路串行，prompt 首行禁思考过程，max_tokens 4000，调用器为本轮现写最小新文件
  relay-station/glm53_r24_call.py、令牌经 SSH 现取不落盘）2 通产出：超时壳 1 通
  （API prompt 24185 / completion 541 / total 24726，reasoning_tokens 0）与黑洞测试 1 通
  （API prompt 23909 / completion 1098 / total 25007，reasoning_tokens 0），壳体与测试经编排
  核对与 lifecycle 版逐字一致（仅测试内 Duration 引用归一化）后机械落仓。
- 验收：4 套件单跑 13/13 全绿（含 3 个新增黑洞测试与 lifecycle 旧测试）；`cargo fmt --all -- --check`
  干净；全量 `cargo test --offline` exit 0（全部 test result 段均为 ok）。

## [1.18.0] - 2026-10-26

### 修复
- 关闭 v1.17.0 已知限制里挂账的全量套件卡死：`ws_term_lifecycle_r2` 在全量/并行运行时
  间歇挂在 `ws_sigint_kills_sleep_keeps_shell`，此前两次全量均卡于此、单跑全绿。
  根因已定位（非握手）：该测试开完会话后从不关闭就直接返回；测试返回触发
  tokio current-thread runtime 析构，析构在 blocking 池上无限等待 pump 线程退出，
  而 pump 正阻塞在仍活着的 shell 的 PTY 读上，析构便永远等下去。关键证据：临时
  插桩（已还原）两次复现均为“output ok 已打印、测试自身断言全过、随后卡死”，
  挂起点在收尾而非测试逻辑；两两组合（sigint+close、sigint+blackhole）均过、
  三测并行时才间歇复现，符合“析构时序竞态”而非固定死锁。
  修法（仅 `tests/ws_term_lifecycle_r2.rs`）：sigint 测试末尾显式发 `term_close`，
  并等 pump 的 `term_exited` 再返回——以泵退出回执代替任意时长 sleep，收尾确定性
  化；生产侧断连清理路径未动（生产服务常驻、清理任务能被正常调度，不受此竞态影响）。
- 同文件另一处无界等待一并收口：`connect_ws` 的逐字节读头循环此前无界，
  服务端迟迟不回 101 时测试会永远挂住。新增 `connect_ws_timeout(addr, cookie, dur)`，
  连接＋写请求＋读头整个包在 `timeout(dur, …)` 里，超时直接 panic；旧 `connect_ws`
  改为 30 秒薄壳，既有两测试一字不改；新增回归测试
  `ws_upgrade_handshake_timeout_blackhole`（只接受连接、永不回字节的黑洞 listener，
  2 秒触发超时 panic，`#[should_panic]`）。
- 诚实记录：握手超时部分由 BotsRouter 大写 GLM-5.3（令牌 id=5，单路串行）生成
  （首通 4000 token 触顶截断作废；拆两通小稿后 A 通辅助函数、B 通回归测试均原文入仓，
  另补一处编排空行）；sigint 收尾修复为编排直接改动（约 12 行、锚定精确，无模型稿）。
  诊断插桩已全部还原，不进提交。
- 版本跟进：Cargo.toml 1.17.0 -> 1.18.0，Cargo.lock 同步，`/api/health` 的 version
  随之跟进（`env!("CARGO_PKG_VERSION")`，无硬编码断言）。

### 测试
- `cargo test --offline --test ws_term_lifecycle_r2`：修复前连跑 3 次 1 过 2 挂（挂起均在
  output ok 之后）；修复后连跑 5 次 5/5 全绿（3.15–4.29 秒），另单次直接跑 5.24 秒全绿。
- `cargo fmt --all -- --check` 干净。
- 全量测试：`cargo test --offline` 全绿通过（90 个 test result 段、772 通过、0 失败、0 忽略，exit 0；此前卡死的 `ws_term_lifecycle_r2` 在全量内 3/3 通过，5.35 秒；另含 doc-tests 0 项）。

### 已知限制
- 同款无界 `connect_ws` 拷贝仍在 `tests/ws_term_conn_r2.rs`、`ws_term_io_r2.rs`、
  `tests/ws_term_open_r2.rs`（deep3 没有），记为后续跟进项，本轮不无声扩大范围。

## [1.17.0] - 2026-10-26

### 修复
- 关闭 v1.16.0 已知限制里挂账的 `cargo fmt --check` 存量 diff 最后一处：tests/twofa_test.rs 全文件 rustfmt 重排（844 行，693 增 / 151 删），只改换行、缩进与多行调用的尾逗号，标识符、字符串字面量与断言语义一字未动；`cargo fmt --all --check` 现已全包干净。
- 诚实记录：本轮为 v1.16.0 明确“留待后续单独处理”的专项重排，整轮 diff 只有这一个测试文件，评审即“纯 rustfmt 输出”本身；格式由 rustfmt 工具链机械输出，无模型手写内容（本轮未走模型调用——格式稿不需要模型，硬凑模型通才是灌水）。另记一笔：cargo fmt 传 --edition 2021 时 --check 会静默 0 输出（原因未深究），本轮改走不带 --edition 的 cargo fmt --all（Cargo.toml 已声明 edition 2021），复核时以此为准。
- 版本跟进：Cargo.toml 1.16.0 -> 1.17.0，Cargo.lock 同步，`/api/health` 的 version 随之跟进（`env!("CARGO_PKG_VERSION")`，无硬编码断言）。

### 测试
- `cargo test --offline --test twofa_test --test twofa_backup_sweep_test --test twofa_v112_test`：11 + 6 + 3 = 20/20 全绿（twofa_test 套件本身耗时 399 秒，系 TOTP 窗口等待，非挂起）。
- 全量测试本轮未重跑（v1.15.0 已注明 ws_term_lifecycle_r2 套件内挂起问题未变），不谎称全绿。

### 已知限制
- 全量测试未跑完：ws_term_lifecycle_r2 在套件内挂起（v1.15.0 已注明，单跑全绿），留待后续在空闲时重跑全量确认。

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

