
# 更新日志

## v1.24.0 — 2026-10-27

### Added
- 标签走进阅读器：阅读器正文区标题下方新增标签 chips 行，点按已有标签即按该标签筛选文章列表，chip 后的 × 可摘除文章与该标签的关联。
- 阅读器正文区 chips 下方新增贴标签编辑器：可下拉选择已有标签，或填写新标签名，下拉优先于新名。
- 文章列表支持标签筛选：点 chip 后进入标签筛选并保留当前 scope，状态栏显示“<scope 文案> · 标签：<名>”，并出现“清除标签筛选”按钮；切换 scope 或点订阅树/分组即清除筛选。
- 后端 POST /api/articles/mark_read 新增 tag_id 参数（非整数报 400“tag_id 非法”）：筛选态下一键已读只标该标签的文章，其余参数语义不动。
- 标签页贴标签表单 select 首项新增空选项“选已有标签”：此前无空项、浏览器默认选中首个已有标签导致新名输入框走不到新建分支；现下拉有值时用下拉、为空时才用新名。
- 标签页该标签文章行的时间由裸 ISO 改为“YYYY-MM-DD HH:MM”显示。
- 新增样式层 design-v119.css（base.html 在 v118 之后引用）：纸面底、墨色字、柿色主色、细线，纯色无渐变、无 !important。

### 测试
- 新增 tests/test_reader_tags_v124.py，共 8 例。
- 新增截图 docs/screenshots/reader-tags-chips-v124.png（chips + 编辑器）与 docs/screenshots/reader-tags-filter-v124.png（筛选态）。

### 已知限制
- 清除标签筛选后 scope 保持不变，不恢复筛选前 scope。
- 正文区 chip 点按后列表不自动滚动定位。

## v1.23.0 — 2026-10-26

### Added

#### 文章标签系统

- **数据库**：迁移 v7 新增 `tags` 与 `article_tags` 两张表及两个索引
- **store 层**：
  - `create_tag`：规范化处理（去空白、折叠连续空白、转小写），重复创建返回已有标签
  - `list_tags`：返回标签列表，含 `article_count` 篇数
  - `list_article_tags`、`add_article_tag`、`remove_article_tag`
  - `list_articles` 新增 `tag_id` 过滤参数
- **API**：
  - `GET /api/tags`、`POST /api/tags`
  - `GET /api/articles/<id>/tags`、`POST /api/articles/<id>/tags`、`DELETE /api/articles/<id>/tags`
  - `GET /api/articles?tag_id=` 按标签过滤文章列表
- **Web**：
  - 新增 `/tags` 页：新建标签、标签列表（含篇数）、选中标签的文章列表、贴标签与取消关联表单
  - 顶栏新增“标签”入口
- **测试**：`tests/test_tags.py`（8 例）与 `tests/test_tags_api.py`（9 例）共 17 例通过，`ruff` 全部通过
- **顶栏翻转点修正（design-v118.css 层，原 v112–v117 层不动）**：新增“标签”入口后实测翻转点后移（已登录 8 链 571px 起单行、未登录 7 链 521px 起单行），v117 旧阈值（521/471）在错位带（已登录 521–570px、未登录 471–520px）把两行顶栏按单行算、阅读区溢出 62px；新层在错位带改回 183px 两行算式，复测错位带 app-shell 恢复 613px、单行带仍 675px；新增 `tests/test_design_v118.py` 3 例；`tests/test_design_v117_loggedin_topbar.py` 导航计数同步为已登录 8 链、未登录 7 链

### 已知限制

- 阅读器正文区暂不显示标签 chips，标签管理请通过 `/tags` 页与 API 完成


## v1.22.0 — 2026-10-26

- **接口行为调整**：收紧 `GET /api/articles` 的 `scope` 参数校验。改动前，当 `scope` 取值非法时，系统会静默回落至 `unread`；改动后，若 `scope` 非法，接口将直接返回 HTTP 400 状态码，且响应体中的错误信息（`error` 字段）为 "scope 非法"。当请求中缺失 `scope` 参数或其值为空字符串时，仍默认按 `unread` 处理。
- **测试同步更新**：`test_api_pagination_search_deep2.py` 中的原有回落测试已重命名为 `test_invalid_scope_returns_400`，断言已相应更新，以校验接口返回 400 状态码且错误信息包含 "scope 非法"。
- **未改动说明**：合法 `scope`（`unread`/`starred`/`all`）以及 `limit`、`offset`、`feed_id`、`folder_id` 的行为一字不动。前端仅发送合法值，不受影响。本次改动无 schema 变更、无 UI 改动；版本号：CHANGELOG 新增 v1.22.0 一节（pyproject 的 0.1.0 为陈旧占位，与本项目 CHANGELOG 版本线无关）。

## v1.21.0 — 2026-10-26

### 改动
- `GET /api/articles` 的 `limit` / `offset` 解析收紧：
  - `limit` 缺参或空串仍默认 50；非整数（如 `abc`、`1.5`、`1x`）或小于 1 返回 400，文案「limit 参数非法」；大于 200 仍钳制为 200。
  - `offset` 缺参或空串仍默认 0；非整数或小于 0 返回 400，文案「offset 参数非法」。
- `scope`、`feed_id`、`folder_id` 语义一字未动；前端只发 `limit=100`，不受影响。

### 测试
- 新增 `tests/test_articles_pagination_validation.py`，9 例。
- 旧测试同步 4 处（`test_api_deep3_paging_args.py` 2 处、`test_api_pagination_search_deep2.py` 2 处，期望由 200 改 400 并改名）。
- 靶向 pytest 30/30 通过（15.02 秒）；`ruff check` 改动 4 文件全洁（`ruff format` 的文件级差异为既有漂移，本轮未动）。

### 已知限制
- 全量 pytest 未跑，仅跑靶向 3 文件 30 例。
- `scope` 非法仍静默回落 `unread`，`feed_id` / `folder_id` 非法仍视为不过滤；这两处不在本轮范围，留待后续轮次。
- 无 UI 改动，视觉验收不适用。

## v1.20.0 — 2026-10-26

### 新增
- 登录失败锁定持久化：锁定计数写入 SQLite 新表 login_lockouts（迁移 v6），进程重启后计数与锁定状态仍有效；create_app 创建 LoginLockout 时传入 db_path；持久模式默认用墙钟 time.time 做时间源，内存模式默认 time.monotonic 不变；窗口、阈值、429 + Retry-After、成功清零、过期清行语义全部不变。
- 新增 tests/test_auth_lockout_persist.py 6 例：跨实例计数接续、跨实例锁定可见、成功清零、过期锁定不残留、窗口过期重计、迁移建表与 user_version 断言。

### 测试
- 全量 pytest 1005/1005 通过（462.5 秒，0 失败）；ruff 全洁；真实服务冒烟（18421 端口）：3 次错密码后 429 + Retry-After 900，锁定中正确密码仍 429，进程重启后仍 429（Retry-After 899）。

### 已知限制
- 持久时间戳用墙钟：系统时钟大幅回拨会延长锁定、快进会提前解锁；同一库文件的多进程共享同一份计数（SQLite 串行化写，登录低频场景够用）；反代后同 IP 共享计数的问题仍在。

## v1.19.0 — 2026-10-26

### 复核：翻转点 1px 粒度实测，关闭 v1.18.0 断点精度 caveat（不改样式）

- 方法：真实服务两路——18319 带密码门 + curl 登录取会话（已登录 7 链）、18320 不开密码门（未登录 6 链），复制的 feedflow.db 种子库，Chromium setContent 内联 v112–v117 层 + /api 路由回真实服务；扫宽 390/469/470/471/472/473/519/520/521/522/523/768，844 高；24 点零 console 错误、导航全程零横向滚动（scrollWidth == clientWidth）。
- 结果：未登录 470px 仍两行（顶栏 183px、app-shell 613px）、471px 起单行（121px、675px）；已登录 520px 仍两行、521px 起单行；与 v1.18.0 实测的 471/521 逐像素一致，1–2px 容差 caveat 关闭；390px 两行态不变。
- 插曲（据实）：首轮未登录路误用带密码门的服务取首页，只拿到 213 字节登录跳转体，该轮未登录行作废；改走 18320 无密码门服务重扫后 24 点全有效。首轮 /api 401 console 错误是 harness 未转发会话 Cookie 所致，二轮转发后归零，属 harness artifact、非回归。
- 模型稿（只走 BotsRouter，大写 GLM-5.3，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，max_tokens 4000，调用器为本轮现写的最小新文件 glm53_r19_call.py，令牌经 SSH 现取不落盘、未读任何现成调用脚本）：第 1 通正文 0 字作废（API prompt 24327 / completion 520 / total 24847）；缩小目标后第 2 通只问配对测试 1 个函数，正文 663 字但 completion 4000 触顶截断在半句断言（API prompt 24073 / completion 4000 / total 28073），编排按截断处的正则骨架机械补齐尾部 3 行断言，并按 v118 口径另写其余 2 例（本条如实注明哪些行是模型稿、哪些是编排补写）。
- 测试：新增 tests/test_design_v119_flippoints.py 3 例（v117 在 v116 之后引用且 served；521 只配 is-logged-in、471 只配 not-logged-in 且 521 > 471、calc 恰好 2 次；v117 无 !important/gradient/box-shadow）；v112–v119 设计测试合跑 19/19 全绿。
- 截图：docs/screenshots/topbar-flip-521-loggedin-v119.png（7 链单行含退出）、topbar-flip-471-loggedout-v119.png（6 链单行无退出），亲眼核对与实测一致。
- 验收后服务按真实 PID 停干净、端口已关、复制库与服务日志已删；扫宽脚本存 muse-build/shot/ff-v119-sweep.js，扫宽原始输出存 ff-v119-sweep-out.txt。

## v1.18.0 — 2026-10-25

### 修复：移动端单行顶栏下 app-shell 高度多扣 62px

- 根因：v116 层把移动端 app-shell 高度写死为 calc(100vh - 183px - 48px)，对应顶栏两行时的 183px；但导航变单行后顶栏只有 121px，阅读区因此白白矮 62px。实测翻转点（Chromium 真实服务 + 会话登录，逐宽度实测）：已登录 7 链在 521px 起单行（520px 仍两行），未登录 6 链在 471px 起单行（470px 仍两行）；768px 已登录态实测顶栏 121px、导航单行、修复前 app-shell 613px。
- 改动：新增 `feedflow/static/css/design-v117.css`（base.html 在 v116 之后引用，原样式表与 v112–v116 层、JS 不动），两条平铺媒体查询——(max-width: 768px) and (min-width: 521px) 下 body.is-logged-in .app-shell 改 calc(100vh - 121px - 48px)；(max-width: 768px) and (min-width: 471px) 下 body:not(.is-logged-in) .app-shell 同款；base.html 的 <body> 改成按 session.get('feedflow_authed') 条件加 is-logged-in 类（仅此 1 行模板改动，不改导航语义与任何 JS）。
- 模型稿（只走 BotsRouter，大写 GLM-5.3，令牌 id=5，渠道 20，单路串行，SSE 按 data: 行拼 content，prompt 首行禁思考过程，max_tokens 4000，调用器为本轮现写的最小新文件、令牌经 SSH 现取不落盘）：1 通即出可用正文、无 429、无思考泄露（API prompt 24651（含上游缓存 23744）/ completion 3823 / total 28474），CSS 两规则与数值逐字落仓。编排修正 1 处：模型稿 fixture 漏传 db_path（create_app 会直接 KeyError），按 tests/conftest.py 口径补 tmp_path 隔离库，绝不碰仓库 data 库。
- 视觉验收：修复后重起已登录服务实测——768px 下 app-shell 675px（= 844 - 121 - 48，与预期一致）、390px 下仍 613px（两行口径不受影响）、零 console 错误；截图存 `docs/screenshots/topbar-loggedin-768-v118.png`（单行 7 链齐全、阅读器三栏正常渲染）。
- 测试：新增 `tests/test_design_v118_appshell.py` 3 例（v117 层在 v116 之后引用且 served、两条媒体查询与两处 121px 算式；已登录 body 带 is-logged-in 类；未登录 body 无该类）；v112–v118 设计测试同跑，全量 16/16 通过。

### 本轮已知限制（诚实保留，不谎称闭环）

- 翻转点 521px/471px 是按当前导航文案与默认字体实测的；若导航文案增减或字体渲染差异超过 1px，临界宽度附近 1–2px 内可能错行，届时以实测为准重定断点。

## v1.17.0 — 2026-10-25

### 已登录态顶栏复核（关闭 v1.16.0 已知限制，不改样式）

- 关闭 v1.16.0 已知限制“已登录时导航多一条‘退出’，换行行数可能再变、app-shell 重算值届时需复核”：实测结论是**无需改样式**——已登录态（密码门开启、会话登录后）390px 下顶栏仍 183px、导航仍两行（第一行阅读器/今日必读/聚类 Top/订阅管理，第二行统计/OPML/退出）、导航 scrollWidth 与 clientWidth 均为 326px（零横向滚动）、app-shell 仍 613px（= 844 - 183 - 48），v116 的 183px 口径继续成立。复核方法：复制演示库 + 一次性测试密码门（FEEDFLOW_AUTH_PASSWORD_HASH 与 FEEDFLOW_SECRET_KEY 均为测试串，复核后删除），curl 登录取会话，Chromium 390x844 截图实测；截图存 `docs/screenshots/topbar-loggedin-390-v117.png`（第一行品牌加搜索框、导航两行全部可见、零 console 错误）。
- 模型稿（只走 BotsRouter，大写 GLM-5.3，令牌 id=5，渠道 20，单路串行，SSE 按 data: 行拼 content，prompt 首行禁思考过程，max_tokens 4000，调用器为本轮现写的最小新文件、令牌经 SSH 现取不落盘）：1 通出正文但混入思考过程与多围栏迭代（API prompt 24378（含上游缓存 23744）/ completion 4000 触顶 / total 28378），编排只抽最后一围栏完整文件落仓，思考段与中间围栏一字未入仓。编排修正 2 处：其一，模型稿测试 2 复用带密码门的 fixture 会 302 到登录页（登录页无导航），改用不带 auth 配置的应用测未登录 6 链；其二，模型稿部分配置缺 host/port/fetch_interval/user_agent 致配置校验失败，按 tests/conftest.py 的 app fixture 口径补齐。
- 测试：新增 `tests/test_design_v117_loggedin_topbar.py` 2 例（已登录 7 链含退出 + v116 层仍 served 且含 183px 算式；未登录 6 链无退出）；v112–v117 设计测试同跑，全量 13/13 通过。

### 本轮已知限制（诚实保留，不谎称闭环）

- 本轮只复核了 390px 宽度下已登录态；更大移动端宽度（如 768px 临界点）下 7 链换行行数未实测，app-shell 值在该宽度下仍以 v116 的 183px 口径为准，届时需复核。

## v1.16.0 — 2026-10-25

### 前端美化（设计层，不改功能与后端）

- 彻底关闭 v1.15.0 已知限制“390px 下顶栏导航横向溢出”：新增 `feedflow/static/css/design-v116.css`（base.html 在 v115 之后引用；原样式表、v112–v115 层、JS 一字不动），移动端顶栏改两行布局——顶栏高度改 auto、内层允许换行、导航排到最后占满一行宽度且自身换行、取消横向滚动；app-shell 高度由 100vh - 57px - 48px 重算为 100vh - 183px - 48px（390px 实测顶栏 183px：第一行约 60px、导航两行 122px、底线 1px；切换栏 48px 不变）。
- 模型稿（只走 BotsRouter，大写 GLM-5.3，令牌 id=5，渠道 20，单路串行，SSE 按 data: 行拼 content，prompt 首行禁思考过程，max_tokens 4000，调用器为本路现写的最小新文件、令牌经 SSH 现取不落盘）：第 1 通调用器 choices 空数组 bug 致脚本崩溃、未取到正文（不计用量）；第 2 通正文截断在半条规则、不可用（API prompt 24048 / completion 4000 / total 28048，其中首条顶栏 auto 规则已完整输出）；第 3 通缩小目标只问导航 1 条，第 1 次 SSH 取令牌偶发代理失败、第 2 次撞 429（等 90 秒重发成功，不计用量），成功通 API prompt 23869 / completion 650 / total 24519，正文即导航规则原文。编排修正 1 处：导航 overflow-x 由 hidden 改 visible（换行后本无溢出，visible 防裁剪焦点轮廓）；内层换行与 app-shell 重算为编排据实测补。
- 视觉验收：真实服务（18316 端口，应用自带种子库）+ 390px 截图亲眼核对 `docs/screenshots/topbar-mobile-390-v116.png`——第一行品牌加搜索框、第二行起导航 4 + 2 两行全部可见、导航 scrollWidth 与 clientWidth 均为 326px（零横向滚动）、品牌左缘 32px 不动、顶栏高 183px、重算后 app-shell 高 613px（= 844 - 183 - 48）、零 console 错误；冒烟服务与演示库已删，截图脚本在 muse-build/shot/ff-v116-shot.js。
- 测试：`tests/test_design_v116.py` 2 例（设计层引用与 served、四选择器、两行布局关键声明、app-shell 重算值、移动端-only、无横向滚动声明）；v112–v115 设计测试同跑，全量 11/11 通过。
- 视觉逻辑见 `docs/DESIGN.md` v1.16.0 一节。

### 本轮已知限制（诚实保留，不谎称闭环）

- 390px 下导航占两行（4 + 2），顶栏总高 183px，阅读器可视区相应收窄；这是两行布局本身的代价，不是溢出。已登录时导航多一条“退出”，换行行数可能再变，行高以实测为准、app-shell 重算值届时需复核。

## v1.15.0 — 2026-10-25

### 前端美化（设计层，不改功能与后端）

- 改善（未彻底关闭）v1.13.0/v1.14.0 已知限制“390px 下顶栏导航横向溢出”：复现实测 390px 下内栏内容 829px、视口 350px，旧规则整条顶栏滚动、品牌会滚走，聚类 Top 出界、订阅管理/统计/OPML 全在屏外，搜索框占 240px。新增 `feedflow/static/css/design-v115.css`（base.html 在 v114 之后引用；原样式表、v112–v114 层、JS 一字不动），模型稿 3 条规则原样落仓（均包在 768px 媒体查询里）：内栏 overflow-x 改 visible 且 min-width 0（整条不再滚动）；导航条 min-width 0 + flex 1 1 auto + overflow-x auto（只有导航条自己滚动）；搜索框 input 收窄到 120px。
- 视觉验收：真实服务（18315 端口，种子库）+ 390px 截图亲眼核对 `docs/screenshots/topbar-mobile-390.png`——导航条滚到底时 OPML 落在导航可视区右缘、品牌钉在左侧不动、搜索框钉在右侧，计算样式与规则一一对上（内栏 overflow-x visible、导航条 scrollWidth 407px / clientWidth 48px / scrollLeft 可到 359、搜索框 120px）；冒烟服务与演示库已删，截图脚本在 muse-build/shot/ff-v115-shot.js（复现脚本 ff-v115-repro.js）。
- 测试：`tests/test_design_v115.py` 2 例（设计层引用与 served、三选择器、移动端媒体查询、桌面无裸 .topbar 规则）；v112–v114 设计测试同跑，全量 9/9 通过。
- 视觉逻辑见 `docs/DESIGN.md` v1.15.0 一节。

### 本轮已知限制（诚实保留，不谎称闭环）

- 390px 下导航可视窗口仍只有约 48px（品牌约 146px + 搜索框 120px + 间距占去大半视口），链接要靠在导航条内滑动才能逐个看到；彻底解决需顶栏改两行布局（品牌/搜索一行、导航独占一行），同时要重算移动端 app-shell 高度，排期后续版本，本轮不硬凑。

## v1.14.0 — 2026-10-25

### 前端美化（设计层 + 空态导览文案，不改功能与后端）

- 关闭 v1.13.0 已知限制“阅读器空态仍是功能性提示，未做成导览页”一项：阅读器未选文章时，右栏不再只有一句提示——原提示句留作标题行，下方 1px 细线分隔出三步导览（左边订阅树选源 → 中间列表选篇 → 正文在此打开，可星标、标已读或查看原文），脚注给出去订阅管理 / 今日必读的入口。三步文案逐项对过真实行为：订阅树、文章列表、星标/已读/原文按钮均是既有功能；脚注初版“还没有订阅源？”与种子库已有 6 个源的实况不符，验收时已改成中性说法“要加新源去订阅管理”。
- 新增 `feedflow/static/css/design-v114.css`（base.html 在 v113 之后引用；原样式表、v112/v113 层、app.js、mobile.js 一字不动），模型稿 3 条规则原样落仓（`.reader-guide`、`.reader-guide li`、`.guide-step`）：导览去默认序号、顶线分隔、行距 1.8；步骤 15px 墨色字；数字徽标 13px 柿色字 + 浅柿底 + 2px 柿色左线。脚注行无专属规则，沿用 v112 层 `.reader-empty` 的次要色。
- 视觉逻辑“空态就是报纸的使用说明小卡”见 `docs/DESIGN.md` v1.14.0 一节。
- 测试：`tests/test_design_v114.py` 2 例（设计层引用与 served、三选择器、导览文案、三栏结构无覆盖、报纸 token）；v112/v113 设计测试同跑，全量 7/7 通过。
- 视觉验收：真实服务（18314 端口，应用自带种子库：6 源 33 篇）+ 截图亲眼核对 `docs/screenshots/reader-empty-guide.png`——未选文章的右栏导览、柿色数字徽标、细线分隔均实证可见，计算样式与规则一一对上（导览顶线 1px #E7E2D6、徽标底 #FBEDE6、左线 2px #C2410C）；冒烟服务与演示库已删，截图脚本在 muse-build/shot/ff-v114-shot.js。

### 本轮已知限制

- 390px 下顶栏导航仍横向溢出（v1.13.0 已知限制，延续）。

## v1.13.0 — 2026-10-25

### 前端美化（设计层，不改功能与后端）
- 新增 `feedflow/static/css/design-v113.css`，base.html 在 design-v112.css 之后引用；原样式表、v112 层与 mobile.js 一字不动。关闭 v1.12.0 已知限制“移动端三栏切换样式未动”一项。
  视觉逻辑“切换栏就是报纸的页眉细线”见 `docs/DESIGN.md`：切换栏纸面底（#FAFAF7）加细线分隔（#E7E2D6）；未选中按钮 13px 次要色（#6B655A）、2px 透明下线；选中态照搬顶栏导航激活态——墨色字（#1C1A17）+ 浅柿底（#FBEDE6）+ 2px 柿色下线（#C2410C）。全部规则包在 `@media (max-width: 768px)` 里，桌面三栏不受影响。
- 测试：`tests/test_design_v113.py` 2 例（设计层引用与 served、切换栏三选择器、无渐变、无 !important、无桌面 .app-shell 覆盖、六个报纸 token 齐全）；v112 设计测试 3 例同跑，全量 5/5 通过。
- 视觉验收：真实服务（18312 端口，种子数据）+ Playwright 390px 截图亲眼核对两张——订阅态（订阅钮浅柿底 + 柿色下线、真实订阅树）与文章态（文章钮激活、真实文章列表），计算样式与规则一一对上；README 移动端门面图换成新文章态截图，订阅态另存 `docs/screenshots/reader-mobile-tree.png`。冒烟服务与演示库已删，截图脚本在 muse-build/shot/ff-v113-shot.js。

### 本轮已知限制
- 390px 下顶栏导航仍横向溢出（今日必读/聚类 Top 被截断），属既有问题，本轮只动切换栏，未动顶栏。
- 阅读器空态仍是功能性提示，未做成导览页（v1.12.0 已知限制，留待下轮）。

## v1.12.0 — 2026-10-25

### 新增
- 按簇标记已读：新增 POST /api/clusters/<cluster_id>/read，整簇未读文章一次标已读，返回 {"cluster_id": ..., "updated": ...}；solo 单篇（cluster_id 为 NULL）按自身 id 命中；已全部已读时 updated 为 0 且仍返回 200（幂等）；scope 可选 unread/starred/all，非法 scope 返回 400，不存在的簇返回 404。
- 聚类 Top 页（/digest/clusters）每张卡片新增“本簇标已读”按钮，点后整簇标已读并刷新页面。
- store 层新增 mark_cluster_read 与 cluster_exists（与 mark_all_read 一致，不写 last_read_at）。
- 测试：tests/test_cluster_mark_read.py（store 层 4 例 + API 层 5 例）。

### 已知限制
- 批量标记已读不写 last_read_at，与既有 mark_all_read 行为一致；Fever 的 unread_recently_read 仍以单篇 set_read 记录的时间为准。
- 本版关闭 v1.11.0 已知限制之外的独立缺口，不改动单用户密码门与登录锁定行为。

### 前端美化（设计层，不改功能与后端）
- 新增 `feedflow/static/css/design-v112.css`，base.html 在原 style.css 之后引用；原样式表不动。
  视觉逻辑“编辑室报纸”见 `docs/DESIGN.md`：纸面底、墨色正文、柿色单主色、细线分隔、左对齐、纯色无渐变。
- 顶栏高 60px，品牌前 10px 柿色方块，导航激活态浅柿底加底部 2px 柿色线，搜索框宽 240px、左内边距 32px 避开图标。
- 阅读器：订阅树底栏顶部细线、纸色底、始终可见；原样式表里根本没有 `.list-bar` 规则，本层补置顶白底列表栏；
  文章选中态浅柿底加左侧 3px 柿色线——此前 `openArticle` 只去未读、不加 active，选中态规则实际从未触发，本轮在 app.js 里补了 active 切换。
- 列表星标：字符 ★ 换成同色 12px SVG 星（app.js 列表渲染处；阅读区按钮文字星标未动）。
- 摘要：序号衬线 20px 柿色，标题 18px，理由 chip 米灰底；统计：卡片顶部内阴影 3px 柿色线。
- 模型稿编排修正（逐项核对后改，未照抄）：删模型稿 `.app-shell` flex 覆盖（原为 grid 三栏，会破坏三栏）、
  品牌字号回 18px、评分卡恢复 3px 柿色左线（border 简写会覆盖它）、摘要容器加 max-width/box-sizing 防窄屏溢出。
- 测试：`tests/test_design_v112.py` 3 例（设计层引用与 served、关键选择器、无渐变、无 app-shell 规则、列表星标为 SVG、打开文章加 active）。
- 视觉验收：真实服务（8312 端口，种子数据）+ Playwright 截图亲眼核对三张——阅读器空态、已打开文章（选中项浅柿底、评分卡柿色条）、
  今日必读（序号柿色衬线）；README 门面 reader.png/digest.png 换成新截图。冒烟服务与演示库已删，截图脚本在 muse-build/shot/feedflow-v112-shot.js。

### 本轮已知限制
- 阅读器空态仍是功能性提示，未做成导览页；移动端三栏切换样式未动。

## v1.11.0 — 2026-10-25

### 新增
- 登录失败锁定：密码门开启后，按客户端 IP 内存计数，默认窗口 15 分钟内连续失败 5 次即锁定 15 分钟；达到阈值的当次失败与锁定期间的提交（含正确密码）回 429 + "尝试次数过多，请稍后再试" + Retry-After 头；成功登录清零该 IP 计数；未达阈值的失败仍回 200 + "密码不正确"。可调环境变量：FEEDFLOW_AUTH_MAX_ATTEMPTS（默认 5）、FEEDFLOW_AUTH_LOCK_MINUTES（默认 15）、FEEDFLOW_AUTH_WINDOW_MINUTES（默认 15），非法值启动 fail-fast。
- 测试：tests/test_auth_lockout.py（锁模块单元 5 例：阈值/成功清零/窗口重置/锁定过期/非法参数；HTTP 集成 4 例：阈值锁定、成功清零、默认阈值 5 次、配置校验 fail-fast）。

### 已知限制
- 锁定计数只存内存，进程重启清零，单进程有效；反代后所有请求同 IP 时共享计数（与 HTTP 限流同款限制）；仍为单用户单密码，无多用户；登出支持 GET；会话 cookie 未设 Secure。
- 本版关闭 v1.10.0 已知限制中的"无登录失败锁定"一项。

## v1.10.0 — 2026-10-24

### 新增
- 可选单用户密码门：默认关闭，不设密码相关环境变量时行为与旧版完全一致；设 `FEEDFLOW_AUTH_PASSWORD_HASH`（推荐，werkzeug 哈希）或 `FEEDFLOW_AUTH_PASSWORD`（启动时当场哈希，不落盘）即开启，开启时必须同时设 `FEEDFLOW_SECRET_KEY`，否则启动 fail-fast 退出。门禁覆盖全部 Web 页与 `/api/*`（登录会话），放行 `/healthz`、`/metrics`、`/login`、`/logout`、`/static/*`、`/fever/*`；Fever 仍用自己的 api_key 鉴权；`feed.xml` 需登录会话，RSS 阅读器请走 Fever。登录失败重渲提示“密码不正确”；next 只接受站内相对路径。
- 登录页（`/login`）与顶栏退出入口（登录后显示）；登出 `/logout`（GET/POST 均可）。
- 测试：`tests/test_auth.py` 8 例（默认关闭行为、门禁 401/302、探针放行、登录登出全流程、next 站外跳转拦截、配置 fail-fast）。

### 已知限制
- 单用户单密码，无多用户、无登录失败锁定（防爆破只靠 HTTP 限流）；登出支持 GET；会话 cookie 未设 Secure。

## v1.9.1 — 2026-10-24

### 技术债清理
- `requirements.txt` 钉版本：`pytest==9.1.1`、`ruff==0.17.0`（2026-10-23 轮记录的"ruff 未钉版本"技术债关闭）。
- ruff 0.17.0 全量问题清零：从 197 处降到 0（`ruff check` 全洁）。143 处走 ruff 安全自动修复（未使用 import/导入排序/PEP585 注解/datetime.timezone.utc 等）；剩余 59 处机械修复：UP031 printf→f-string（28）、ISC004 隐式拼接合并（5）、RUF059 未使用解包变量改 `_` 前缀（9）、F841 未使用局部变量改 `_` 前缀（2）、PERF102 只用值时改 `.values()`（2）、RUF015 单元素切片改 `next()`（2）、FURB192 `sorted()[-1]` 改 `max()`（1）、BLE001 三处确为意图内全捕获加 `noqa` 注释（2 脚本+1 线程错误收集）、PLR0124 `x != x` 改 `math.isnan`（1）、PLW1510 subprocess 显式 `check=False`（1）、RUF012 可变类属性默认值加 `ClassVar` 注解（1）、EXE001 两脚本加执行位（2）。语义零改动，pytest 全量通过。
- `scripts/loadtest.py` / `scripts/loadtest_phase6.py` 加执行位（shebang 与权限对齐）。

## v1.9.0 — 2026-10-23

### 新增
- 阅读器文章详情区新增"为什么排前面"评分卡片：打开文章后按需拉取 `GET /api/articles/<id>/score`（v1.8 端点），展示重要性总分、时效 / 事件热度 / 来源权重 / 关键词 / 未读加成五个因子条、大白话理由列表与发布时间小字；后端请求失败时卡片静默消失，不影响阅读。旧报纸视觉（纸白底、柿色左侧竖线、左对齐），去 AI 味约束延续。
- `tests/test_article_score_api.py`（8 例）：v1.8 评分端点的 HTTP 契约测试——响应形状、五因子 0~1 有界、已读文章未读因子为 0、多成员簇 cluster_size、与 `ranking.score_article` 纯函数一致性、404。

### 文档
- README"快速开始"补全：安装 / 运行 / 手动抓取 / 测试 / Docker 一把梭，含默认监听 127.0.0.1:8300 与./data 持久化说明（2026-10-16 v1.6 发版报告遗留项关闭）。

## v1.8.0 — 2026-10-22

### 新增
- 排序可解释性端点：`GET /api/articles/<id>/score` 返回单篇文章的重要性评分与五个因子的得分明细（`score`/`parts`[heat/keyword/recency/source/unread]/`reasons`/`cluster_size`/`age_hours`），文章不存在返回 404。真实服务冒烟验证通过。

## v1.7.0 — 2026-10-20

### 新增
- 新增“聚类 Top”视图（`/digest/clusters`）：去重聚类后的 Top N 事件卡片流，每卡片展示聚类主题、来源数、来源标题（至多 5 个）、重要性分（可解释，拆出 `cluster_score` 计算依据）、每篇成员的 `score_info`、“还有 N 篇已折叠”。导航栏新增“聚类 Top”入口。
- 新增 `ranking.get_digest_clusters(db_path, n=10, now=None)`：未读文章经 `rank_articles` 排序后按 `cluster_id` 分组（NULL `cluster_id` 各自成 solo 组），返回 `cluster_id`/`topic`/`members`/`sources`/`source_titles`/`unread`/`representative`（含 `score_info`）/`cluster_score`/`cluster_reasons`/`latest_at`。
- 种子数据加 `CLUSTER_DEMO`（3 事件 x 3 来源=9 篇，验证真实聚类 3 簇 x 3 篇）。

### 修复
- 修复阅读器 `app.js` 与 CSS 类名失配（`renderItem` 吐 `art-title`/`art-meta`/裸星号，CSS 写的是 `.title`/`.meta`/`.star`）：改回 `title`/`meta`/`<span class="star">`，未读加粗+红点+星标着色恢复。

### 测试
- 新增 `tests/test_digest_clusters.py`（9 例）、`tests/test_digest_clusters_page.py`（6 例）；本轮 pytest 全绿（3 个 flaky 失败已修：`rank_articles` 签名、`read_at` 列不存在、NULL 分组契约）。


## v1.6.1 — 2026-10-17

### 修复

- 修 PUT /api/folders/<id> 历史 bug（v1.6 遗留）：处理器调用的 store.get_folder 与 store.update_folder_position 根本不存在，导致改分组名/排序直接 500。补上 feedflow/store.py 的 get_folder(db_path, folder_id)（无则 None，返回 {id,name,position,unread}，形状与 list_folders 一致）与 update_folder_position（直接设置 position）；api.py 行为契约未动。
- 回归测试 tests/test_folders_put.py（7 例：改名、调序、404、空名 400、非法 position 400、名+序同改、404 无副作用）；pytest 136/136 全绿。

## v1.6 — 2026-10-16

### 新增

- 阅读器键盘快捷键：`j`/`k` 上下篇、`o` 新标签页打开原文、`r` 标已读/未读、`s` 加星/取消星标、`?` 快捷键帮助浮层（`Esc` 关闭）；`m` 标已读/未读保留兼容。
- 阅读进度记忆：滚动位置按文章持久化到 SQLite（`articles.scroll_pos`，DB 迁移 v4），重进文章自动恢复到上次读到的位置；新增 `POST /api/articles/<id>/progress` 接口。
- OPML 导出加固：标题/网址为 None 的脏数据不再导致导出 500；head 新增 `dateCreated`；分组嵌套与未分组直挂结构保持 OPML 2.0 标准形态。
- tests/test_progress.py（8 例）与 tests/test_opml.py 新增 6 例。

测试：pytest 129 例全过、ruff 全洁。

## v1.5.1 — 2026-10-16


### 变更

- 依赖升级：trafilatura 2.2.0 → 2.3.1。2.3.1 是当前 PyPI 上的最新版本；上游 2.3.0 的发版说明里写了没有破坏性变更，主要是下载和解压部分的代码重构、文档处理逻辑的简化。本地 venv 里换成 2.3.1 后跑了一遍测试，pytest 115/115 全过。

## v1.5 — 2026-10-16

### 新增

- 全文 RSS 输出：`GET /feed.xml`，正文优先用抓取时 trafilatura 提取的 content_text，无正文时回落摘要去标签文本；支持 `?feed_id=` / `?folder=` 过滤，最多 50 篇；ETag + If-None-Match 304 缓存。
- HTTP 层 IP 限流：内存令牌桶，默认 60 req/min（`FEEDFLOW_RATE_LIMIT_RPS=1.0` + `FEEDFLOW_RATE_LIMIT_BURST=60`），超限 429 + Retry-After；`/healthz` 与 `/metrics` 免限流；Prometheus 新增 `feedflow_http_rate_limited_total`；开关 `FEEDFLOW_RATE_LIMIT_ENABLED`。
- tests/test_feedxml.py（8 例）与 tests/test_ratelimit.py（5 例）；运维手册新增第 9 节"限流调参"。

## v1.4 — 2026-10-16

### 新增

- Prometheus 指标（`GET /metrics`，9 个指标系列）。
- 失败注入测试。
- 运维手册补全，共 8 章。
- Fever 运维章节。
- 移动端阅读优化。

### 修复

- 纠正 `docs/OPERATIONS.md` 中环境变量默认值错误。

测试：pytest 102 例全过（新增 18：指标 6 + 失败注入 12）、ruff 全洁。

## v1.3 — 2026-10-15

### 新增
- Fever API 兼容：第三方 RSS 客户端（Reeder、Unread 等支持 Fever 协议的）可以直接连 FeedFlow 同步订阅、文章和已读/星标状态。接口挂载在 `/fever/`，鉴权用 POST 提交的 `api_key`（md5(邮箱:密码) 十六进制），用 `feedflow fever-key` 命令生成后写入环境变量 `FEEDFLOW_FEVER_API_KEY` 启用。支持 groups/feeds/favicons/items（since_id/max_id/with_ids 分页，各 50 篇封顶）/unread_item_ids/saved_item_ids 读取，以及单篇标记已读/星标、按源/按组标记已读（需 before 时间戳）、unread_recently_read 写操作。未实现 favicon 抓取，返回 1x1 透明占位图；无 spark 概念，is_spark 恒为 0；未分组的源归入 group 0。
- 正文提取超时收敛：新增环境变量 `FEEDFLOW_EXTRACT_TIMEOUT`（默认 15 秒），单篇卡住的文章页不再拖慢整个源的抓取，超时自动回落用 RSS 摘要。
- 新增 `feedflow fever-key` 命令：交互式输入邮箱和密码（密码不回显），输出可直接用的 api_key。
- 新增 tests/test_fever.py（22 个用例），覆盖鉴权、分组/源/文章读取、分页、已读/星标/分组标记、unread_recently_read 及参数校验。

### 改进
- `store.set_read` 标记已读时同步记录 `last_read_at`（迁移 v3 新增列），供 Fever 的 unread_recently_read 使用。

## v1.2 — 2026-10-13

### 新增
- 新增重要性排序：综合时效衰减（半衰期 48 小时）、事件热度（同簇文章数）、来源权重（手动权重 × 按已读/星标学习）、关键词命中、未读加成五个维度加权算分，让真正重要的文章排前面。
- 新增「今日必读」页（/digest）：直接看当天最值得读的 N 篇，每篇都能展开分数明细，一眼看懂"为什么排前面"。
- 新增兴趣设置页（/settings/interests）：可以增删关键词、手动调来源权重、设置每日篇数 N。
- 数据库迁移到 v2：新增 keywords、feed_weights、settings 三张表。
- 新增环境变量 FEEDFLOW_DIGEST_N，用来控制「今日必读」默认篇数，默认 20。
- 新增 tests/test_ranking.py，共 16 个测试用例覆盖排序逻辑。

### 改进
- 排序分数支持拆解展示，不再是黑盒。

## v1.1 — 2026-10-13

### 新增
- 抓取支持重试和失败分类，网络抖动或源站报错时不再一挂到底。
- 调度状态持久化，重启后不会丢抓取计划。
- 新增结构化日志，排查问题更方便。
- 新增 /healthz 健康检查接口。
- 新增备份恢复 CLI，数据可以备份和还原。
- 新增 SimHash + Jaccard 去重聚类，重复文章折叠显示，不再刷屏。

### 改进
- 视觉返工：改成三栏全幅布局，阅读区更宽敞。
- 演示数据改成真实命名，看起来不再像占位符。
- 搜索页短词改走 LIKE，避免 FTS5 对短词不生效的问题。

### 修复
- 修复阅读管理页分组列的竞态问题。
- 修复搜索页模板变量错误。

## v1.0 — 2026-10-13

### 新增
- 首个可用版本。
- 订阅管理：添加、编辑、删除订阅源。
- APScheduler 定时抓取，自动拉取新文章。
- trafilatura 正文提取，尽量还原干净的文章内容。
- 三栏阅读器，左边订阅、中间列表、右边正文。
- FTS5 全文搜索，快速找到看过的文章。
- OPML 导入导出，方便迁移订阅。
- 统计页，查看订阅和阅读情况。
