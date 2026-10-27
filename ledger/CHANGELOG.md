# 更新日志

## v2.17.25 - 2026-10-27

### 新增
- `GET /api/budgets/yearly` 的 `year` 参数非法值由 422 收紧为 400，detail 为「year 参数非法」；缺参仍由 FastAPI 必填校验返回 422；yearly 计算口径未动。

### 不变
- yearly 计算、月份端点、创建/更新校验一字未动。

### 测试
- 更新旧测试 2 例（`test_yearly_invalid_year_400`、`test_yearly_non_numeric_year_400`）
- 新增 `tests/test_budgets_yearly_validation.py` 6 例

## v2.17.24 - 2026-10-27

### 新增
- 收紧 /budgets 页面 month 参数校验：非法格式返回 400，detail 为 "month 参数非法"。

### 不变
- /api/budgets 路由、budget_progress、month_range 逻辑不变。
- 页面缺参（None）与空串仍走现有 if not month 默认当月逻辑。

### 测试
- 新增 tests/test_budgets_page_month_validation.py，覆盖 6 例。

## v2.17.23 - 2026-10-27

### 新增
- GET /api/budgets 新增 month 参数校验：非法值返回 400，detail 为“month 参数非法”；此前非法值会直传 month_range：month="bogus" 或空串抛 ValueError 走到 500，month="2026-13" 会算出 ("2026-13-01", "2026-14-01") 这种不存在的区间并静默返回结果，month="2026-1" 会被当成 2026-01 但预算过滤按原串匹配不到。合法格式为严格 YYYY-MM（正则 `^\d{4}-(0[1-9]|1[0-2])$`，实现为 budgets.py 模块级 _MONTH_RE）；缺参时 Query(...) 本来就是必填，行为不变。

### 不变
- yearly 端口的 year 校验（422）、预算创建/更新校验、spent/remaining/pct 计算口径一字未动；页面 /budgets 的 month 未在本轮收紧（仍直传 budget_progress，记为剩余缺口，不谎称全关）。

### 版本同步
- src/ledger/__init__.py、pyproject.toml、tests/test_version_consistency_v21715.py 的版本同步为 2.17.23。

### 测试
- 新增 tests/test_budgets_month_validation.py 6 例全绿（bogus/2026-13/2026-00/2026-1/空串 返回 400 且 detail 为“month 参数非法”、2026-10 返回 200 且响应体为列表）；先红后绿验证通过（撤回代码改动后 5 败 1 过，含日志实锤空串 500；恢复后 6/6）；与 test_budgets.py、test_budgets_yearly.py、test_currencies_budgets_deep2.py 合跑 27 通过；ruff check 与 ruff format 在改动文件上全洁；真实服务冒烟 18278 端口隔离库：month=bogus 返回 400、month=2026-10 返回 200 空列表。

## v2.17.22 - 2026-10-27

### 新增
- `GET /api/transactions` 新增 date_from/date_to 参数校验：非法值返回 400，detail 分别为“date_from 参数非法”与“date_to 参数非法”；此前非法值会静默按字符串比较过滤、返回空列表。合法格式为严格 YYYY-MM-DD（恰好 10 字符、短横线在第 4 与第 7 位、真实日历日期）；None 或空串表示不过滤；其余过滤条件与分页一字未动。

### 不变
- limit/offset 默认值与范围、total 计数口径、条目字段一字未动；不做 date_from 大于 date_to 的顺序校验（超出本轮范围）；创建/更新路径的校验一字未动；前端只发日期输入框的 YYYY-MM-DD，不受影响。

### 版本同步
- `src/ledger/__init__.py`、`pyproject.toml`、`tests/test_version_consistency_v21715.py` 的版本同步为 2.17.22。

### 测试
- 新增 tests/test_transactions_date_validation.py 9 例全绿（date_from bogus 返回 400、date_to bogus 返回 400、月份 13 返回 400、2 月 30 日返回 400、短格式 2024-1-1 返回 400、合法范围过滤为恰好 1 条、空串 date_from 不过滤、缺参不过滤、仅 date_to 合法返回 200）；新测与类型校验测、版本一致性测靶向合跑 15/15；ruff check 与 ruff format 在两处改动文件上全洁。

## v2.17.21 - 2026-10-27

### 新增
- `GET /api/transactions` 新增 type 参数校验：非法值返回 400，detail 为“type 参数非法”；此前非法值会静默按该值过滤、返回空列表。合法值：income、expense、transfer（复用同文件已有的 VALID_TYPES）；None 或空串表示不过滤（行为不变）；其余过滤条件与分页一字未动。

### 不变
- limit/offset 默认值与范围、total 计数口径、条目字段一字未动；创建/更新路径的“非法的交易类型”校验一字未动；前端不受影响。

### 版本同步
- `src/ledger/__init__.py`、`pyproject.toml`、`tests/test_version_consistency_v21715.py` 的版本同步为 2.17.21。

### 测试
- 新增 tests/test_transactions_type_validation.py 5 例全绿（bogus 返回 400、空串不过滤、expense 过滤、income/transfer 返回 200、不带 type 不过滤）；ruff check 与 ruff format 全洁；版本一致性测试通过。

## v2.17.20 - 2026-10-27

### 新增
- `GET /api/statements/{batch_id}/items` 新增 status 参数校验：非法值返回 400，detail 为“status 参数非法”；此前非法值会静默按该值过滤、返回空列表。合法值：preview、pending、auto、claimed、skipped、duplicate；None 或空串表示不过滤（行为不变）；不存在的批次仍先返回 404。

### 不变
- limit/offset 默认值与范围、total 计数口径、条目字段一字未动；前端只发 pending，不受影响。

### 版本同步
- `src/ledger/__init__.py`、`pyproject.toml`、`tests/test_version_consistency_v21715.py` 的版本同步为 2.17.20。

### 测试
- 新增 tests/test_statement_items_status_validation.py 5 例全绿（bogus 返回 400、空串不过滤、preview 过滤、全部合法值返回 200、不存在的批次加 bogus 返回 404）。

## v2.17.19 - 2026-10-26

### 新增
- `src/ledger/routers/workbench.py` 新增 `_ALLOWED_ITEM_STATUSES = {"pending", "claimed", "skipped", "all"}`；`GET /api/workbench/batches/{batch_id}/items` 在批次 404 检查之后、过滤之前校验 `status`，非法值返回 400，detail 为“status 参数非法，应为 pending、claimed、skipped 或 all”；此前非法 `status` 会静默按 `status` 过滤、返回空列表。

### 不变
- `status=all` 时仍不过滤；`page`/`page_size`/`q`/排序逻辑一字未动；其余端点未动。

### 版本同步
- `src/ledger/__init__.py`、`pyproject.toml`、`tests/test_version_consistency_v21715.py` 的 `EXPECTED_VERSION` 同步为 2.17.19。

### 测试
- `tests/test_workbench_api.py` 末尾追加 6 个用例（bogus 返回 400、空串返回 400、all 返回全部、pending 正常、claimed 无数据返回空、不存在的批次加 bogus 返回 404）。
- 新测试 6/6 通过；全量 pytest 1457 通过、1 跳过、0 失败；真实服务冒烟 6/6 通过（8129 端口隔离库）。

## v2.17.18 - 2026-10-26

### 新增
- 新增测试文件 tests/test_dashboard_design_v21718.py，包含一个测试函数 test_dashboard_topbar_single_line。
- 测试断言：
  - GET /static/dashboard.css 返回 200 且 CSS 内容中括号平衡。
  - CSS 包含 .topbar .nav 与 flex-wrap: nowrap、overflow-x: auto、scrollbar-width: none。
  - CSS 包含 .topbar .nav a 与 padding: 7px 8px、font-size: 13px、white-space: nowrap。
  - GET / 返回 200，页面 HTML 中 /static/style.css 出现在 /static/dashboard.css 之前。
- 系列收官：v2.17.0–v2.17.14 已覆盖其余 14 页，仪表盘页是最后一页；本轮之后 15 个页面全部有顶栏单行设计层测试锁死，系列收官。

### 说明
- 产品代码未动，dashboard.css 的顶栏单行规则是此前仪表盘美化时已落地的既有规则。
- 设计层测试只断言结构，不依赖任何种子数据。

### 测试
- 新测试 tests/test_dashboard_design_v21718.py 1/1 通过；设计层合跑 19/19 通过（含本轮新测试、其余 14 页设计测试、transactions 两版测试、版本一致性测试）。
- 新文件 ruff check 全洁、ruff format 全洁（模型稿首版 1 处 E501 超长行与 1 处格式缺空行由编排机械修正后全洁）。
- 全量 pytest 1451 通过、1 跳过、0 失败（较 v2.17.17 的 1450 通过恰好 +1，即本轮新测试）。
- 真实服务冒烟（8120 端口，demo.db 复制库）：GET / 200、GET /static/dashboard.css 200、页面含 dashboard.css 引用且在 style.css 之后、css 含 flex-wrap: nowrap；冒烟后服务已停、复制库已删。


## v2.17.17 - 2026-10-26
### 修复
修正两处过期测试断言（实现一字未动，判定依据见下；此前全量 2 失败 wlfl t14/t15 自此清零）：
- t14 历史精确 2 票置信度 70 → 80：实现公式 min(90, 60 + 票数*10) 自 v2.0 起未变；deep2 测试已锁死精确 2 票=80、deep3 锁死 3 票=90、产品文档记“历史(≥80)”；旧断言 70 与上述三处均冲突，属过期期望。
- t15 转账配对容差用例：旧例 50000 与 50101（差 101 分）按“仅绝对容差 100 分”写不配对，但 amount_within 的锁死语义是绝对或相对任一通过即相当（r2 边界测试双锁），默认 pct_tol=1.0 下相对差约 0.2% 应配对；本轮把该例改为 50000 与 51000（同时超绝对 100 分与相对 1%，差 1000 分约 1.96%）断言不配对，并新增 50101 例断言配对、把 OR 语义锁死。
- 模型稿（只走 BotsRouter，大写 GLM-5.3，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，max_tokens 4000，调用器为本轮现写最小新文件 glm53_r20_call.py，令牌经 SSH 现取不落盘、钉死 UserKnownHostsFile、未读任何现成调用脚本）：第 1 通只交了“要先读文件”的元文本而非代码围栏（作废，不计入仓）；收紧提示词（最高指令单围栏、声明无文件访问能力、函数体全文给出照抄）后第 2 通即出可用正文（API prompt 25068（含上游缓存 23744）/ completion 1037 / total 26105，reasoning_tokens 0），两函数原文入仓、零编排修正。
### 测试
- tests/test_ledger_balance_wlfl.py 全文件 18/18 通过；匹配相关套件（deep2/deep3/deep4、amount_within 绝对/相对边界 r2、match_best、suggest_candidates）合跑 146/146 通过。
- ruff：本轮改动行零新增告警；全文件 40 个 check 错误与整文件 format 差异均为既存（import 未排序等，改动行均在其外；不为本轮重排整文件，避免噪声 diff）。
- 全量 pytest：1450 通过、1 跳过、0 失败（此前 1448 通过、2 失败、1 跳过；2 失败即本轮修掉的 t14/t15；耗时 178.9 秒）。


## v2.17.16 - 2026-10-26
### 修复
修复正则守卫的嵌套量词检测漏洞，旧实现第二分支写错导致 `([a-z]+){2,}` 等分组嵌套量词模式被错误放行。
改用线性扫描函数 `_has_nested_quantifier`，正确跟踪分组栈与组内量词标志，并处理各类前缀与量词。
删除旧正则 `_NESTED_QUANTIFIER_RE`，`check_pattern_safety` 其余检查顺序与返回值字符串未动。
### 测试
新增端到端测试，锁死 `match_best` 与预览链对历史脏规则的跳过行为。
新测试文件 13 例全绿，与既有正则测试合跑共 37 例全绿。
两个改动文件的 ruff check 与新区段 ruff format 全洁。
全量 pytest 1448 通过、2 失败（wlfl t14/t15 干净树既存）、1 跳过。
### 文档
同步更新 `docs/OPERATIONS.md §8`，更正历史脏数据灾难正则在调度时即被跳过的事实。
补记本轮 `{m,n}` 嵌套检测已补齐。
版本号三处同步至 2.17.16。

## v2.17.15 - 2026-10-25

### 新增

- 版本同步：将 `src/ledger/__init__.py` 中的 `__version__`（此前停留在 2.17.1）与 `pyproject.toml` 中 `[project]` 的 `version`（此前停留在 2.17.0）统一同步到 2.17.15，关闭此前多轮注明的版本漂移问题。本节不包含任何功能改动。

### 测试

- 新增版本一致性测试 1 例（`tests/test_version_consistency_v21715.py`）：断言 `src/ledger/__init__.py` 的 `__version__`、`pyproject.toml` 的 `[project] version` 与 `CHANGELOG.md` 首个 `## vX.Y.Z` 标题三处一致且均为 2.17.15；按与既有设计层测试合跑的口径纳入测试套件，不单独声称通过数字。

## v2.17.14 - 2026-10-25
### 新增
- 对账工作台页顶栏不换行：新文件 `src/ledger/static/workbench.css`（仅 workbench 页引用，workbench.html 加 extra_css 行，style.css 不动），与账单导入向导页 v2.17.13 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.13 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭对账工作台页一页，其余页仍走原 wrap，不谎称全站关闭。模型稿 3 条规则原文未动，测试文件由模型同通生成。对账工作台页路由实测为 `/workbench`，测试按实测路由写。模型 1 通即出可用正文、无 429。
### 测试
- 新增 `tests/test_workbench_design_v21714.py` 1 例（对账工作台页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.13/v2.17.12/v2.17.11/v2.17.10/v2.17.9/v2.17.8/v2.17.7/v2.17.6/v2.17.5/v2.17.4/v2.17.3/v2.17.2/v2.17.1/v2.17.0 设计层合跑 17/17 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8117 端口，demo.db 复制库）对账工作台页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；截图存 `docs/screenshots/workbench-v21714.png`。本截图为 setContent 内联样式 harness 拍摄，仅作顶栏验收：图中红色“Failed to parse URL from /api/workbench/batches”是 harness 下相对地址在 about:blank 解析失败的已知假象，真实服务上该接口已 curl 实测返回 200 正常 JSON（含 1 条招商银行储蓄卡批次、10 条待处理），不作门面问题。验收后服务已按真实 PID 停掉、复制库已删。

## v2.17.13 - 2026-10-25
### 新增
- 账单导入向导页顶栏不换行：新文件 `src/ledger/static/statement.css`（仅 statement 页引用，statement.html 加 extra_css 行，style.css 不动），与复核页 v2.17.12 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.12 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭账单导入向导页一页，其余页（workbench 等）仍走原 wrap，不谎称全站关闭。模型稿 3 条规则原文未动，测试文件由模型同通生成。账单导入向导页路由实测为 `/statement`，测试按实测路由写。模型 1 通即出可用正文、无 429。
### 测试
- 新增 `tests/test_statement_design_v21713.py` 1 例（账单导入向导页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.12/v2.17.11/v2.17.10/v2.17.9/v2.17.8/v2.17.7/v2.17.6/v2.17.5/v2.17.4/v2.17.3/v2.17.2/v2.17.1/v2.17.0 设计层合跑 16/16 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8116 端口，demo.db 复制库）账单导入向导页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误，账单导入向导内容正常渲染；截图存 `docs/screenshots/statement-v21713.png`。本截图为 setContent 内联样式 harness 拍摄，仅作顶栏验收。验收后服务已按 PID 停掉、复制库已删。

## v2.17.12 - 2026-10-25
### 新增
- 复核页顶栏不换行：新文件 `src/ledger/static/review.css`（仅 review 页引用，review.html 加 extra_css 行，style.css 不动），与月度报告页 v2.17.11 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.11 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭复核页一页，其余页（statement/workbench 等）仍走原 wrap，不谎称全站关闭。模型稿 3 条规则原文未动。复核页路由实测为 `/bills/review`（非 `/review`），测试按实测路由写。途中插曲：第一通撞 502 Bad Gateway，等 90 秒重发成功；截图脚本 sed 换名把 /static/review.css 带偏成错路径，坏脚本已删、重写干净版后重拍，入提交前已核对文件名与版本一致。
### 测试
- 新增 `tests/test_review_design_v21712.py` 1 例（复核页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.11/v2.17.10/v2.17.9/v2.17.8/v2.17.7/v2.17.6/v2.17.5/v2.17.4/v2.17.3/v2.17.2/v2.17.1/v2.17.0 设计层合跑 15/15 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8115 端口，demo.db 复制库）复核页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误，复核页标题与说明正常渲染；截图存 `docs/screenshots/review-v21712.png`。本截图为 setContent 内联样式 harness 拍摄，仅作顶栏验收。验收后服务已按 PID 停掉、复制库已删。

## v2.17.11 - 2026-10-25
### 新增
- 月度报告页顶栏不换行：新文件 `src/ledger/static/report.css`（仅 report 页引用，report.html 加 extra_css 行，style.css 不动），与周期账单页 v2.17.10 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.10 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭月度报告页一页，其余页仍走原 wrap，不谎称全站关闭。模型稿 3 条规则原文未动。
### 测试
- 新增 `tests/test_report_design_v21711.py` 1 例（月度报告页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.10/v2.17.9/v2.17.8/v2.17.7/v2.17.6/v2.17.5/v2.17.4/v2.17.3/v2.17.2/v2.17.1/v2.17.0 设计层合跑 14/14 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8114 端口，demo.db 复制库）月度报告页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；截图存 `docs/screenshots/report-v21711.png`。本截图为 setContent 内联样式 harness 拍摄，仅作顶栏验收：图中两条红色“加载失败”是 harness 下相对地址 /api/reports/* 在 about:blank 解析失败的已知假象，真实服务上两接口均已 curl 实测返回正常 JSON（月度汇总与口径方案），不作门面问题。验收后服务已按 PID 停掉、复制库已删。

## v2.17.10 - 2026-10-25
### 新增
- 周期账单页顶栏不换行：新文件 `src/ledger/static/recurring.css`（仅 recurring 页引用，recurring.html 加 extra_css 行，style.css 不动），与导入导出页 v2.17.9 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.9 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭周期账单页一页，其余页仍走原 wrap，不谎称全站关闭。模型稿 3 条规则原文未动（仅文件头注释展开为多行）；首通撞 429，按口径等 90 秒重发成功。
### 测试
- 新增 `tests/test_recurring_design_v21710.py` 1 例（周期账单页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.9/v2.17.8/v2.17.7/v2.17.6/v2.17.5/v2.17.4/v2.17.3/v2.17.2/v2.17.1/v2.17.0 设计层合跑 13/13 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8113 端口，demo.db 复制库）周期账单页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；周期账单内容正常渲染（即将到来暂无、全部暂无记录、新增表单与招商银行储蓄卡下拉）；截图存 `docs/screenshots/recurring-v21710.png`。本截图为路由代理 harness 拍摄，仅作顶栏与页面静态渲染验收。


## v2.17.9 - 2026-10-25
### 新增
- 导入导出页顶栏不换行：新文件 `src/ledger/static/import.css`（仅 import 页引用，import.html 加 extra_css 行，style.css 不动），与侦探队列页 v2.17.8 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.8 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭导入导出页一页，其余页仍走原 wrap，不谎称全站关闭。模型稿 3 条规则原文未动（仅文件头注释展开为多行）。
### 测试
- 新增 `tests/test_import_design_v2179.py` 1 例（导入导出页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.8/v2.17.7/v2.17.6/v2.17.5/v2.17.4/v2.17.3/v2.17.2/v2.17.1/v2.17.0 设计层合跑 12/12 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8112 端口，demo.db 复制库）导入导出页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；导入导出内容正常渲染（CSV 导入/导出区）；截图存 `docs/screenshots/import-v2179.png`。本截图为路由代理 harness 拍摄，仅作顶栏与页面静态渲染验收。


## v2.17.8 - 2026-10-25
### 新增
- 侦探队列页顶栏不换行：新文件 `src/ledger/static/detective.css`（仅 detective 页引用，detective.html 加 extra_css 行，style.css 不动），与汇率页 v2.17.7 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.7 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭侦探队列页一页，其余页仍走原 wrap，不谎称全站关闭。模型稿 3 条规则原文未动（仅补文件头注释）。
### 测试
- 新增 `tests/test_detective_design_v2178.py` 1 例（侦探队列页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.7/v2.17.6/v2.17.5/v2.17.4/v2.17.3/v2.17.2/v2.17.1/v2.17.0 设计层合跑 11/11 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8111 端口，demo.db 复制库）侦探队列页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；侦探队列真实数据亦正常渲染（待认领 10 条，美团外卖 32.8、滴滴出行 21.5）；截图存 `docs/screenshots/detective-v2178.png`。本截图为路由代理 harness 拍摄，仅作顶栏与页面静态渲染验收。


## v2.17.7 - 2026-10-25
### 新增
- 汇率页顶栏不换行：新文件 `src/ledger/static/currencies.css`（仅 currencies 页引用，currencies.html 加 extra_css 行，style.css 不动），与分类页 v2.17.6 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.6 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭汇率页一页，其余页仍走原 wrap，不谎称全站关闭。模型稿 3 条规则原文未动（仅去围栏、补文件头注释）。
### 测试
- 新增 `tests/test_currencies_design_v2177.py` 1 例（汇率页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.6/v2.17.5/v2.17.4/v2.17.3/v2.17.2/v2.17.1/v2.17.0 设计层合跑 10/10 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8110 端口，demo.db 复制库）汇率页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；汇率真实数据亦正常渲染（本位币 CNY 汇率 1）；截图存 `docs/screenshots/currencies-v2177.png`。本截图为路由代理 harness 拍摄，仅作顶栏与页面静态渲染验收。


## v2.17.6 - 2026-10-25
### 新增
- 分类页顶栏不换行：新文件 `src/ledger/static/categories.css`（仅 categories 页引用，categories.html 加 extra_css 行，style.css 不动），与预算页 v2.17.5 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.5 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭分类页一页，其余页仍走原 wrap，不谎称全站关闭。编排修正 1 处：模型稿头注释误写“仅 budgets 页引用”，落盘时改回 categories，3 条规则原文未动。
### 测试
- 新增 `tests/test_categories_design_v2176.py` 1 例（分类页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.5/v2.17.4/v2.17.3/v2.17.2/v2.17.1/v2.17.0 设计层合跑 9/9 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8109 端口，demo.db 复制库）分类页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；分类真实数据亦正常渲染（支出 12 类、收入 6 类）；截图存 `docs/screenshots/categories-v2176.png`。本截图为 setContent 内联样式 harness 拍摄，仅作顶栏与页面静态渲染验收。

## v2.17.5 - 2026-10-25
### 新增
- 预算页顶栏不换行：新文件 `src/ledger/static/budgets.css`（仅 budgets 页引用，budgets.html 加 extra_css 行，style.css 不动），与账户页 v2.17.4 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.4 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭预算页一页，其余页仍走原 wrap，不谎称全站关闭。
### 测试
- 新增 `tests/test_budgets_design_v2175.py` 1 例（预算页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.4/v2.17.3/v2.17.2/v2.17.1/v2.17.0 设计层合跑 8/8 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8108 端口，demo.db 复制库）预算页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；截图存 `docs/screenshots/budgets-v2175.png`。本截图为 setContent 内联样式 harness 拍摄，仅作顶栏与页面静态渲染验收。

## v2.17.4 - 2026-10-25
### 新增
- 账户页顶栏不换行：新文件 `src/ledger/static/accounts.css`（仅 accounts 页引用，accounts.html 加 extra_css 行，style.css 不动），与拍照记账页 v2.17.3 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.3 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭账户页一页，其余页仍走原 wrap，不谎称全站关闭。
### 测试
- 新增 `tests/test_accounts_design_v2174.py` 1 例（账户页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.3/v2.17.2/v2.17.1/v2.17.0 设计层合跑 7/7 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8107 端口，demo.db 复制库）账户页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；账户真实数据亦正常渲染（招商银行储蓄卡 823.9 CNY、信用卡 0 CNY）；截图存 `docs/screenshots/accounts-v2174.png`。本截图为 setContent 内联样式 harness 拍摄，仅作顶栏与页面静态渲染验收。

## v2.17.3 - 2026-10-25
### 新增
- 拍照记账页顶栏不换行：新文件 `src/ledger/static/bills.css`（仅 bills 页引用，bills.html 加 extra_css 行，style.css 不动），与规则页 v2.17.2 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.2 所记“其余页仍走原 `.nav` wrap”缺口在本轮只关闭拍照记账页一页，其余页仍走原 wrap，不谎称全站关闭。
### 测试
- 新增 `tests/test_bills_design_v2173.py` 1 例（拍照记账页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.2/v2.17.1/v2.17.0 设计层合跑 6/6 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8106 端口，demo.db 复制库）拍照记账页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；截图存 `docs/screenshots/bills-v2173.png`。本截图为 setContent 内联样式 harness 拍摄，仅作顶栏验收（app.js 未加载，不验 OCR 交互）。

## v2.17.2 - 2026-10-25
### 新增
- 规则页顶栏不换行：新文件 `src/ledger/static/rules.css`（仅规则页引用，rules.html 加 extra_css 行，style.css 不动），与交易页 v2.17.1 已验证的顶栏口径一致（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行）；由此 v2.17.1 所记“其他未做设计层的页不受影响”缺口在本轮只关闭规则页一页，其余页仍走原 `.nav` wrap，不谎称全站关闭。
- 编排修正 2 处（模型稿按仓库实测核对后改动，如实记录）：模型稿选择器 `.topbar-nav` 在 base.html 里根本不存在，真实结构是 header.topbar 下的 nav.nav，改回 `.topbar .nav`；模型稿第 1 条漏写 `flex-wrap: nowrap`（v2.17.1 已实证 flex 容器换行由 flex-wrap 控制），补回。
### 测试
- 新增 `tests/test_rules_design_v2172.py` 1 例（规则页引用顺序、顶栏单行规则齐全、括号平衡）；与 v2.17.1/v2.17.0 设计层 4 例合跑 5/5 全绿；ruff 新测文件全洁。
### 视觉验收
- 真实服务（8105 端口，demo.db 复制库）规则页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；截图存 `docs/screenshots/rules-v2172.png`。本截图规则表为空是 setContent 截图 harness 下相对地址 /api/match-rules 拉取失败所致（真实服务 /rules 本身 200），仅作顶栏验收，不作门面。

## v2.17.1 - 2026-10-25
### 新增
- 交易页顶栏不换行：`transactions.css` 补顶栏 3 条规则（导航 `flex-wrap: nowrap` + 横向滚动 + 隐藏滚动条、链接 7px 8px/13px 不换行），与仪表盘 v2.16.0 已验证的顶栏口径一致；此前 v2.17.0 已知限制所记“顶栏换行是原样式老问题”至此在交易页关闭（style.css 原 `.nav` 仍为 wrap，其他未做设计层的页不受影响）。编排修正 1 处：模型稿第 1 条只写 `white-space: nowrap`，flex 容器换行由 `flex-wrap` 控制，故补 `flex-wrap: nowrap`。
### 测试
- 新增 `tests/test_transactions_design_v2171.py` 1 例（顶栏单行规则齐全、括号平衡）；与 v2.17.0 设计层 3 例合跑 4/4 全绿；ruff（仅 py 文件）全洁。
### 视觉验收
- 真实服务（8103 端口）交易页截图亲眼核对：1440 宽下顶栏单行、15 链全可见（仪表盘至月度报告），实测顶栏高 60px、导航 `flex-wrap: nowrap`、滚动宽与可见宽均为 953px（无截断、无溢出）、零 console 错误；截图存 `docs/screenshots/transactions-v2171.png`。本截图交易表为空（演示库默认月无数据，见 v2.16.0 同款记录），仅作顶栏验收，不作门面。

## v2.17.0 - 2026-10-25
### 新增
- 交易页前端美化（新文件 src/ledger/static/transactions.css，仅交易页引用，transactions.html 加 extra_css 行，style.css 不动）：视觉逻辑为“流水台账”，承接仪表盘 v2.16.0 的账本式横向阅读——纸面白、墨色文字、细线分隔、左对齐；表头 2px 墨线、行间发丝线、金额等宽数字右对齐、日期等宽次要色；筛选与记一笔控件 44px、焦点 2px 墨环；提交与查询按钮改墨底白字；层级靠字号、字重、线宽三档。
- 去 AI 味自查：无紫渐变、无 Inter 独占、无一切居中、无三栏特性格、无 emoji 图标、无 Unleash/Empower/Seamless/Next-generation 类文案、无编号段落+衬线大标题 Specimen 风；设计逻辑写在 transactions.css 文件头注释。
- 编排修正 1 处：原 .pagination 自带 align-items:center，模型稿漏写会致按钮纵向拉伸，补回；其余规则逐字保留。
### 视觉验收
- 真实服务 + 真实数据：demo.db 复制库起 8102 端口，交易页截图亲眼核对（见下）；金额正负色为 app.js 行内色（收入绿/支出红/转账蓝），本层只定对齐与字重，未改颜色口径。
- 仅交易页改动，其他页仍走原 style.css；仪表盘设计层未动。
### 测试
- 新增 tests/test_transactions_design_v217.py 3 例（页面引用顺序、设计层可取与括号平衡与关键选择器、规则体禁令串），全绿；ruff 改动文件全洁。
### 模型
- 5 段由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行）微批输出，每段 3 条规则；第 4 通撞 429 一次，等 90 秒重发成功，不计用量；API 合计 prompt 119899 / completion 1970 / total 121869。

## v2.16.0 - 2026-10-25
### 新增
- 仪表盘前端美化（新文件 src/ledger/static/dashboard.css，仅仪表盘页引用，base.html 增 extra_css 块、dashboard.html 引用）：视觉逻辑为“账本式横向阅读”——纸面暖白、墨色文字、细线分隔、左对齐、金额等宽数字、层级靠字号/字重/线宽三档；总览改成同一账目条（上粗下细、列间竖线，收入绿/支出红/结余墨色）；图表为白底细边框无阴影面板；快捷入口改成一行文字链接、竖线分隔；顶栏 15 个链接单行不换行（原样式 flex-wrap: wrap 导致换行，截图实证后补 nowrap 并收紧内边距至 8px/字号 13px，1440 宽下 15 链全可见）；短页页脚贴视口底（body 纵向 flex、main 撑满）。
- 去 AI 味自查：无紫渐变、无 Inter 独占、无居中英雄区、无三栏特性格、无 emoji 图标、无 Unleash/Empower/Seamless/Next-generation 类文案、无编号段落+衬线大标题 Specimen 风；总览条是财务报表行，不是特性介绍格；设计逻辑写在 dashboard.css 文件头注释。
### 视觉验收
- 真实服务 + 真实数据：demo.db 复制库（2026-09 共 23 笔）起 8101 端口，仪表盘 ?month=2026-09 截图三轮亲眼核对：第一轮发现顶栏换行，第二轮单行滚动但末 2 链被截断，第三轮 15 链全可见、无重叠；总览 5000/3530.1/1469.9 与 23 笔、图表、快捷行均真实渲染，非空状态/loading 门面。注意：默认当月（2026-10）demo 库无数据会显示 0 笔，验收用 2026-09 月份参数，属实记录。
- 仅仪表盘页改动，其他页仍走原 style.css；图表 SVG 本体未改（其柱条颜色是数据可视化，非 hero 渐变）。

## v2.15.0 - 2026-10-25
### 新增
- match_best 模糊分支返回结果追加 detail 字段（复用 fuzzy_match_detail，与 v2.14 预览链条 detail 同口径：matched / distance / window / threshold）；其他分支键不变，_pick_best_fuzzy 返回形状不变。预览接口的 hit 即带 detail，无需另改路由。
- 新增 tests/test_match_best_fuzzy_detail_v215.py（3 例：子串命中 detail、1 字之差 detail、非模糊分支不带 detail）。

## v2.14.0 - 2026-10-25
### 新增
- matching.py 新增 fuzzy_match_detail(pattern, haystack)，返回 matched / distance / window / threshold 四键解释（子串命中 distance 0；否则滑动窗口最小编辑距离与首次最小窗口；threshold 按词长取 1 或 2）。
- POST /api/match-rules/preview 的 fuzzy 链条目追加 detail 字段（仅 fuzzy 分支，其他分支键不变）。
- 新增 tests/test_fuzzy_detail_v214.py（12 例）与 tests/test_preview_chain_deep.py 的 fuzzy 链 detail 断言（1 例，另断言 keyword 条目不带 detail）。
### 修复
- fuzzy_rule_matches 改为复用 fuzzy_match_detail，阈值与窗口逻辑与 v2.13 完全一致（2 字词 1 字之差仍不命中）。
- 关闭版本号漂移：src/ledger/__init__.py 的 __version__ 定为 2.14.0 作为单一来源，/api/health 与 pyproject.toml 同步至 2.14.0（此前 CHANGELOG 已到 2.13.0，但 health 与 pyproject 仍为 2.11.0、__init__ 为 0.1.0）；health 版本测试改为跟随 __version__ 断言。
### 测试
- pytest 全量 1414 通过、2 失败、1 跳过；2 失败为干净树既存 wlfl_t14/t15（git stash 对照验证，零新增回归）。
- ruff check 在本轮改动文件上全洁（test_preview_chain_deep.py 第 89 行既存 I001/F401 未动）；ruff format 的整文件漂移为既存风格（单空行分隔顶层函数），干净树同样存在，未扩面重排。
- 真实服务冒烟（uvicorn 真进程）：/api/health version=2.14.0、/api/ready true；建 fuzzy 规则“星巴克”后预览“星巴客咖啡”命中 92 rule_fuzzy，链条 detail 为 {matched: true, distance: 1, window: "星巴", threshold: 1}。

## v2.13.0 - 2026-10-24
### 新增
- match_best 调度新增模糊规则层级（别名 > 正则 > 关键词 > 模糊 > 历史 > 候选 > 无匹配）。
- 模糊命中 source=rule_fuzzy、置信度 92。
- fuzzy 匹配算法为归一化后子串命中或滑动窗口编辑距离（长度 < 5 允许距离 1、长度 >= 5 允许距离 2，且距离*2 < 词长，2 字词 1 字之差不命中）。
- API 创建规则的 pattern_type 白名单补上 fuzzy（更新接口白名单此前已含 fuzzy）。
- 规则预览链路 fuzzy 分支按同一算法判定、置信度 92。
- 规则管理页下拉框与类型/来源文案补“模糊”/“模糊规则”。
### 测试
- 新增 tests/test_match_best_fuzzy_v213.py 12 例；改写 tests/test_match_best_fuzzy_deep.py 3 例；合计 15 例通过。

本项目更新日志遵循 Keep a Changelog 风格。

## v2.12.0 - 2026-10-24

### 新增

- 真实负载验证：新增 scripts/load_test.py——确定性仿真账单生成器（24 个月、约 110 笔/月，商户池覆盖餐饮/购物/交通/日用/医疗/工资/转账，种子 20261024 可复现，BOM+UTF-8 仿真真实导出）+ 真实 HTTP 全链路压测 harness（子进程起 uvicorn，逐月上传→确认计时、自动匹配率、去重探针、并发探针、内存与库大小、阈值判定、JSON 报告）。关闭 v2.11.1 对照报告"真实负载验证：待执行"项。
- 新增 tests/test_load_statement.py（CI 版）：两月上传确认、重传去重、建规则后自动匹配率≥0.5、命中正确性抽查、确认耗时 <60s 共 5 例。
- 新增 docs/LOAD_TEST.md 方法论文档；make load-test / make load-test-quick 快捷目标。

### 测试

- pytest 全量 1393 通过、1 跳过（2 失败为干净树既存 wlfl_t14/t15，非本轮引入）；新增 tests/test_load_statement.py 4 例全过；ruff check + format 全洁。
- 真实负载实测结论见 docs/LOAD_TEST_REPORT.md：24 个月 2664 笔走真实 HTTP，上传 5.14s / 确认 15.14s，自动匹配率 85.5%，去重精确命中，3 路并发上传零 5xx，阈值判定通过。

## v2.11.1 - 2026-10-24


### 新增

- 新增回滚脚本 scripts/rollback_v6_to_v5.py（v6→v5）：默认 dry-run 只打印计划；--yes 真实执行（自动备份 backups/ledger-<时间戳>.pre-rollback.sqlite3）；冲突检测（report_schemes 非空、规则列偏离默认值、suggested_rule_id 非空、(keyword, direction) 重复组）命中时写.rollback_conflicts.json 并 exit 3、中止且不写入；退出码 0 成功 / 1 执行失败 / 2 前置或参数失败 / 3 发现冲突。关闭 v2.11 发版报告"迁移回滚路径：未通过"项。
- POST /api/workbench/batches/{batch_id}/resolve-batch 新增 dry_run 入参：True 时逐条只做与真实处理相同的前置校验、不写库，返回 {"dry_run": true, "ok": [...], "failed": [...]}。关闭 v2.11 发版报告"批量对账失败明细：未通过"项的预检部分。
- 新增 POST /api/workbench/batches/{batch_id}/failures-export：批量预检并导出失败明细 CSV（BOM + 表头 id,occurred_on,counterparty,summary,amount_yuan,direction,reason），只做校验不写库。

### 测试

- 新增 tests/test_rollback_v6_to_v5.py 11 例：dry-run 默认/显式、flag 互斥、非 v6 拒绝、文件缺失、4 类冲突检测、--db 优先于 LEDGER_DB、真实回滚 happy path（schema 精确回到 v5、数据保留、备份落盘）。
- 新增 tests/test_workbench_dryrun_export.py 6 例：dry-run 不写库、失败上报、方向不匹配、非法动作 422、CSV 导出形状与金额格式、无失败时仅表头、批次 404。

### 说明

- v2.11 已知限制第 6-9 条标注的"（v2.11.1 关闭本项）"至此全部有名有实：正则防护（v2.11.0 已合入 matching.py）、批量预检与失败明细 CSV 导出（本轮）、preview 跳过原因（v2.11.0 已合入）、v6→v5 回滚脚本（本轮）。

## v2.11 - 2026-10-20

### 新增

- 侦探规则引擎 v2：MatchRule 新增 pattern_type（keyword/regex）、is_enabled、hit_count 三列。
- StatementItem 新增 suggested_rule_id，用于记录命中的建议规则。
- matching.py 新增 match_best 统一调度：别名记忆 85 > 正则规则 97 > 关键词规则 95 > 历史 > 候选。
- 同级命中按 priority、长度、id 依次决胜；非法正则跳过不抛异常。
- 新增 PUT /api/match-rules/{id}，用于更新规则字段。
- 新增 POST /api/match-rules/preview，返回 chain 解释链。
- 新增 POST /api/match-rules/{id}/touch，用于累计命中次数。
- 前端新增 /rules 规则管理页，包含表格、启用开关、测试命中区。
- 新增对账差异工作台 router workbench.py。
- 新增 GET /api/workbench/batches，列出对账批次。
- 新增 GET /api/workbench/batches/{id}/items，支持分页与 q 搜索。
- 新增 POST /api/workbench/items/{id}/resolve，动作含 confirm/ignore/learn/transfer。
- 新增 POST /api/workbench/batches/{id}/resolve-batch，采用部分成功语义。
- 前端新增 /workbench 页，支持逐条确认/忽略/记成规则/转账与批量操作和进度。
- 新增月度收支报告 router reports.py。
- 新增 GET /api/reports/monthly，含分类汇总、环比、Top 商户、口径分桶。
- 新增 GET+PUT /api/reports/category-scheme，默认“9月口径”。
- 默认口径分桶为考研投入、一次性大项、饮食、日用、话费、交通。
- 前端新增 /report 页，含年月选择、条形图、环比表、Top 商户、导出自包含 HTML。
- 新增演示数据脚本 scripts/seed_workbench_demo.py。
- 新增样例文件 docs/samples/cmb-statement-sample.csv。
- 数据库迁移 v5 到 v6：match_rules 补 3 列，statement_items 补 suggested_rule_id，新建 report_schemes 表。

### 测试

- 新增 tests/test_import_boundary_deep2.py，覆盖 GBK 与 UTF-8-SIG 解码。
- 覆盖金额千分位、括号负数、¥ 符号、全角逗号解析。
- 覆盖中文日期解析与重复导入幂等。
- pytest 全量待本轮实测后填。

### 冒烟

- 本轮冒烟范围：/rules、/workbench、/report 三页可打开，接口返回结构符合预期。
- 冒烟未覆盖真实银行流水大批量场景，相关验证待后续执行。

### 已知限制

- 规则预览的解释链仅展示命中路径，不展示被跳过规则的跳过原因。
- 批量对账为部分成功语义，前端仅汇总失败条数，未提供逐条失败明细导出。
- 月度报告导出的 HTML 为自包含单文件，未做移动端适配。
- 非法正则在调度中直接跳过，未在规则管理页给出显式告警。
- 演示数据脚本仅生成示例数据，不校验与真实账套的字段兼容性。

## v2.10 - 2026-10-17


### 新增

- 旧端点 POST /api/bills/ocr 补齐全路径 Prometheus 埋点（v2.9 对照报告已知限制"本轮范围外"，本轮关闭）：新指标集 ledger_bills_ocr_requests_total{result="ok"|"error"} / ledger_bills_ocr_failures_total{reason="unavailable"|"unsupported"|"invalid"|"oversize"|"internal"} / ledger_bills_ocr_duration_seconds / ledger_bills_ocr_confidence_avg，与 statements 端点的 ledger_ocr_* 实例计数完全隔离；reason 映射：unsupported=非图片（422）、oversize=超 5MB（422）、invalid=文件名/内容空或提供商配置非法（422/500）、unavailable=OCR 提供商未配置或未实现（422/501）、internal=其他。
- src/ledger/ocr_metrics.py 重构为 _OcrMetrics(prefix) 类：模块级旧函数名与 ledger_ocr_* 指标名/HELP 文本逐字不变（v2.9 向后兼容），bills 用独立实例。
- pip 依赖定期扫描本地脚本版：scripts/deps_scan.py（只用标准库：从 pyproject 读依赖、pip list --outdated 查过期、OSV API 查已知 CVE；exit 0 无问题 / 1 有漏洞或大版本过期 / 2 扫描失败）+ docs/DEPENDENCY_SCAN.md + make deps-scan + .github/workflows/deps-scan.yml（每周一 03:00 UTC，continue-on-error）。
- 版本号统一 bump：pyproject.toml、src/ledger/routers/health.py（/api/health）、tests/test_metrics.py 断言、docs/OPERATIONS.md 两处示例，2.1.0 → 2.10.0。

### 测试

- pytest 全量 290 通过、1 跳过（跳过的是既有用例：环境无 tesseract）。
- 新增 tests/test_bills_ocr_metrics.py（至少 10 例：指标名前缀/HELP、两实例隔离、ok 路径、各失败分类、埋点故障隔离、/metrics 文本解析）。
- ruff check 与 ruff format 全洁。

### 冒烟

- 真实服务冒烟（uvicorn 真实进程，mock provider，LEDGER_DB 独立）：建账户 201 → 记一笔 200 → POST /api/bills/ocr 有效 PNG → 200（review_id=1 入审核队列）→ 非图片 .txt → 422 → GET /api/metrics 验证 ledger_bills_ocr_requests_total{result="ok"}=1/{result="error"}=1、ledger_bills_ocr_failures_total{reason="unsupported"}=1、直方图 count=2 → POST /api/statements/ocr → 200（旧端点不受影响，ledger_ocr_* 照常渲染）→ /api/health version=2.10.0 → 备份 → 删库 → 恢复 → 账户/交易/review 数据一致。

### 已知限制

- tesseract 真实安装实测：2026-10-17 实测：`apt-get update` 执行 10 分钟无任何输出（apt 源不可达，与已知 apt 源损坏一致），已终止；`which tesseract` 无 binary；全盘仅找到冒烟垫片 ~/workspace/muse-build/w2b/shim/tesseract（POSIX shell 脚本，输出固定 CSV，非真实识别）。结论：环境仍无真实 tesseract，ledger_ocr_confidence_avg / ledger_bills_ocr_confidence_avg 继续诚实为 0；OCR 识别率真实语料验证暂无法执行，仍为已知限制。
- 指标为进程内计数，重启清零（既有行为）。
- pyproject 版本号历史漂移（v2.2 起未 bump）已在本轮统一为 2.10.0。

## v2.9 - 2026-10-17

### 新增

- 新增 `ledger_ocr_requests_total{result="ok"|"empty"|"error"}` counter：POST /api/statements/ocr 全路径计数（每次请求都记，含 400/413/415 前置校验拒绝）。
- 新增 `ledger_ocr_failures_total{reason="unavailable"|"unsupported"|"invalid"|"oversize"|"internal"}` counter：unavailable=tesseract 不可用（503）；unsupported=非图片类型（415）；invalid=请求非法（400）；oversize=超 5MB（413）；internal=其他。
- 新增 `ledger_ocr_duration_seconds` histogram：全路径请求耗时，buckets (0.05,0.1,0.25,0.5,1,2.5,5,10,+Inf)。
- 新增 `ledger_ocr_confidence_avg` gauge：tesseract TSV 词级置信度均值（0~1），运行平均；无样本时为 0。
- 改名说明：排期名 `ledger_ocr_requests_total{provider,status}` 当时为占位名，v2.8.1 实际交付的是 `ocr_requests_total`/`ocr_duration_seconds`；v2.9 交付真正的 `ledger_`-前缀全路径指标集。
- 新增 OcrEmptyError(OcrFailedError)；TesseractOcrProvider 新增 `_word_confidence_avg`（TSV 解析，best-effort 永不抛错）与 `last_confidence` 属性。
- 埋点语义：src/ledger/routers/statements.py 原函数改名 `_ocr_statement_preview_impl`，新 `ocr_statement_preview` 包装做全路径埋点（OcrEmptyError→422/result empty；HTTPException 按状态码分类；埋点异常只 warning）。

### 测试

- pytest 全量 279 通过、1 跳过（跳过的是既有用例：环境无 tesseract）。
- 新增 tests/test_ocr_metrics_v29.py（14 例：指标名/HELP、归一化、置信度校验、直方图桶、全路径 e2e 各分类、故障隔离）。
- 删除被取代的 tests/test_ocr_metrics.py（v2.8.1 旧指标名已移除）。
- ruff check 与 ruff format 全洁（11 个历史未格式化文件与本轮无关）。

### 冒烟

- 真实冒烟（uvicorn 真实进程，mock provider）：POST /api/statements/ocr 有效 PNG→200；.txt→415；魔数非法→400；超 5MB→413；/metrics 验证 ledger_ocr_requests_total{result="ok"} 1、{result="error"} 3，failures unsupported/invalid/oversize 各 1，直方图 count 4。

### 已知限制

- tesseract 未安装时 confidence_avg 恒为 0（无样本，诚实）。
- 旧端点 POST /api/bills/ocr 未埋点（本轮范围外）。
- 指标为进程内计数，重启清零（既有行为）。

## v2.8.1 - 2026-10-17

### 新增

- `ocr_requests_total{result="ok"|"unavailable"|"error"}`：OCR 请求计数（counter）。`ok`=OCR 成功；`unavailable`=OCR provider 不可用（503）；`error`=识别失败（422）/其他异常。只统计走到 OCR provider 调用的请求。
- `ocr_duration_seconds`：OCR 延迟分布（histogram，buckets：0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, +Inf），用于 OCR 延迟分布/告警。
- 指标输出 `GET /api/metrics`（手写 Prometheus exposition，零新依赖）；进程内计数，服务重启清零。
- 埋点只统计走到 OCR provider 调用的请求；埋点异常只记 warning，永不影响主流程。

### 测试

- 新增 `tests/test_ocr_metrics.py` 覆盖埋点语义。
- `GET /api/metrics` 真实冒烟验证指标名与标签。

## v2.8 - 2026-10-17

### 新增

- `POST /api/statements/ocr`：multipart 上传图片，做 magic bytes 校验，得到 OCR 文本行，复用 statement 解析预览流。坏图 400、超 5MB 413、非图片 415、识别出空文本 422；缺 binary、执行失败、超时返回 503，detail 原样带安装指引（OcrUnavailableError）。
- 图片只在内存里识别，不写盘、不存库。
- `src/ledger/ocr.py`：新增 `OcrUnavailableError` 与 `ocr_lines` 方法（Mock/Tesseract）。
- `ParsePreviewOut` 新增 `ocr_text` 字段。
- `statement.html` 新增「图片 OCR 录入」卡片：拖拽区、进度条、识别预览后进第 2 步核对。
- 侦探队列集成：OCR → 上传 → 确认 → 认领 → 记住为规则，全复用既有接口。

### 测试

- pytest 全量 265 通过、1 跳过（跳过的是环境无 tesseract 的既有用例）。
- ruff check 与 ruff format 全洁。
- 真实服务冒烟（mock provider）7 步：建账户 201 → OCR 预览 200 → 确认上传 200 → 确认批次 200 → 侦探队列 4 条 pending → 认领 200 → 记住为规则 1 条。
- 2 张截图亲眼验收通过。

## v2.7 - 2026-10-17

### 新增

- 商户别名管理 API（v2.4 遗留缺口：别名学错了改不掉）：GET /api/merchant-aliases（列表，含 category_name）、PATCH /api/merchant-aliases/{id}（改别名文本/改映射分类；404 别名不存在/分类不存在、400 无更新字段或别名为空、409 别名冲突）、DELETE /api/merchant-aliases/{id}（404/ok）；schemas 新增 MerchantAliasOut、MerchantAliasUpdate。
- 侦探页新增「记住的商户别名」管理区：每行别名可改名、分类可重选，保存/删除即时生效；空状态有引导文案。
- 回归测试 tests/test_merchant_aliases.py（8 例：列表、改名、改分类、404、400、409、删除）；pytest 全量 250 通过、1 跳过（既有 tesseract 缺失跳过）。

## v2.6 - 2026-10-16

### 新增

- 真实 OCR 提供商：`TesseractOcrProvider`（src/ledger/ocr.py，调本地 tesseract CLI 的 stdin/stdout）。超时默认 30 秒（`LEDGER_OCR_TIMEOUT`）、语言默认 `chi_sim+eng`（`LEDGER_OCR_LANG`）；缺二进制时报错并给出 apt/brew 安装命令；识别失败或超时抛 `OcrFailedError`。金额提取先遮掉日期片段再取最大值（修过日期干扰金额的 bug）。
- OCR 审核队列：`POST /api/bills/ocr` 返回 `review_id` 并把识别结果写入待审核队列（`ocr_reviews` 表，status=pending）；新增 `GET /api/bills/review`（待审核列表）、`GET /api/bills/review/{id}/image`（原图）、`POST /api/bills/review/{id}/confirm`（确认入账，重复确认返回 409）、`POST /api/bills/review/{id}/reject`（驳回）。
- 新页面 `/bills/review`「OCR 审核」：原图缩略 + 识别字段可编辑 + 置信度低于 70% 的字段标红；确认后调记账 API 入账。
- `OcrResult` 新增 `field_confidence`（各字段置信度：merchant/amount_cents/occurred_on）。
- DB 迁移 v4→v5：新建 `ocr_reviews` 表（`CURRENT_VERSION=5`）。

### 测试

- 新增 `tests/test_ocr_tesseract.py`（18 例通过、1 例因环境无 tesseract 跳过）、`tests/test_bills_review.py`（15 例）；全量 242 例通过。
- 3 处旧的硬编码版本号断言更新为 `CURRENT_VERSION`。

## v2.4 - 2026-10-16

### 新增

- 模糊匹配升级（`matching.py` 纯函数）：金额容差（绝对差 ≤x 分或相对差 ≤x%，整数运算无浮点误差）、日期窗口（±N 天）、商户别名匹配（归一化精确相等，置信度 85）。
- 商户别名学习：手工认领一次即记住（归一化对方名 → 分类），存 `merchant_aliases` 表；纠正认领时更新映射；下次同类自动入账（match_source="alias"）。
- 匹配优先级：关键词规则(95) > 别名(85) > 历史习惯(≥80 自动)。
- 转账配对：同批次一出一入、金额容差内（±100 分或 ±1%）、日期窗口内（±3 天）、且对方名为自有账户时，双方标记 `match_source="transfer-pair"`（置信度 90），侦探页显示"转账配对成功"。
- 侦探页批量处理：卡片多选 + 批量工具条（全选/批量认领/批量忽略）；跨方向勾选时批量认领置灰并提示；部分成功语义（`{processed, failed:[{item_id,error}]}`），失败逐条给原因。
- API（前缀 `/api`）：`POST /api/statements/items/batch-claim`、`POST /api/statements/items/batch-skip`。
- DB 迁移 v3→v4：新建 `merchant_aliases` 表。

### 修复

- 修测试隔离：`tests/conftest.py` 清表列表补 `merchant_aliases`（别名泄漏曾导致全量跑时 `test_claim_errors` 失败）。
- 修 `test_currencies.py` 硬编码版本号断言（3→4）。

### 测试

- pytest 增至 173 例全过（新增 29 例：容差边界/日期窗口/别名/配对/批量/学习闭环/规则优先）；ruff 全洁。

### 已知限制

- 转账配对只覆盖同批次内条目；配对参数为模块常量（`TRANSFER_PAIR_*`），暂无管理界面。
- 批量认领要求勾选同方向，跨方向需分批处理或用批量忽略。

## v2.3 - 2026-10-16

### 新增

- 全站移动端适配：`@media (max-width: 768px)` 断点；顶栏导航横向滑动；触控目标 ≥44px。
- 交易列表、侦探队列规则表在移动端转卡片流（`data-label` 列名，`table:has()` 精确命中）。
- 仪表盘 / 预算页移动端布局：汇总卡单列、图表上下排、快捷入口两列、预算行换行。
- 品牌 logo 从 emoji 换成内联 SVG 硬币线稿 mark。
- `tests/test_mobile.py`：10 页 200 + viewport 标记 + 断点 CSS 存在性冒烟测试。

### 修复

- 修导航高亮选择器 `.nav a.active` 缺圆点导致永不生效。
- 补齐模板存在但 CSS 从未定义的类（`.filters`、`.pagination`、`.summary-cards`、`.charts`、`.quick-link-grid`、`.budget-row`、`.toolbar` 等）的桌面样式。

## v2.2 - 2026-10-16

### 新增

- 多币种：账户与交易支持 `currency` 字段（ISO 4217 三字母大写，默认 CNY，非法值 422）。
- 汇率管理：`GET /api/currencies` 列表、`PUT /api/currencies/{code}` 新增/更新汇率；汇率页 `/currencies` 可视化设置。
- 本位币折算：月度汇总与净资产按 `LEDGER_BASE_CURRENCY`（默认 CNY）折算；缺汇率的交易/账户不计入并计入 `unknown_count`。
- DB 迁移 v2→v3：新增 `currencies` 表，`transactions` 表加 `currency` 列（老数据默认 CNY）。
- 交易页记一笔表单加币种下拉；仪表盘标注本位币。

### 限制

- 跨币种转账不做实时换算，按转出币种金额记录（后续版本再议）。

## v2.1 - 2026-10-15

### 新增

- DB 迁移版本化：`PRAGMA user_version`（当前版本 2），v1 老库启动自动补 4 张 v2 表，损坏库启动报 `MigrationError`。
- 结构化日志：stderr JSON Lines（ts/level/logger/msg/request_id），`RequestIdMiddleware` 全链路 request_id 并回写 `X-Request-Id` 响应头；`LEDGER_LOG_LEVEL` 环境变量，非法值启动 fail-fast。
- `GET /api/metrics`：Prometheus 文本格式，6 个指标（账单批次/条目按状态/侦探待认领/自动匹配率/交易总数/账户总数）。
- 备份恢复 CLI：`python -m ledger backup [--keep N]`（默认保留 7 个，备份前 integrity_check）、`python -m ledger restore FILE`（恢复前自动安全快照，坏备份拒绝恢复）；`make backup [KEEP=N]` / `make restore FILE=`。
- 就绪探针 `GET /api/ready`（DB 通 200 / 不通 503）；优雅关闭（lifespan dispose engine）。
- `docker-compose.yml` 一键部署（healthcheck / 资源限制 1 核 512M / 日志轮转 / named volume）与 `docs/OPERATIONS.md` 运维手册。
- 失败注入测试 4 例：DB 锁定→500 带 request_id、坏 CSV→200 不崩服务、磁盘满→BackupError 无残留、metrics DB 故障→500。
- 未处理异常统一 500 `{"detail":"服务器内部错误","request_id":"..."}`（由 RequestIdMiddleware 兜底；FastAPI 0.143 的 Exception 处理器会被转给 ServerErrorMiddleware 并 re-raise，故不用）。

### 修复

- 修 `python -m ledger serve` 启动崩溃（`args.dir` 在 serve 子命令不存在）。
- 修坏 CSV（随机二进制）的 `csv.Error` 抛 500：改为 errors 行收集返回 200。
- 修备份 `integrity_check` 对损坏文件抛裸 `sqlite3.DatabaseError`：改为 `BackupError`。
- 修备份写入失败（磁盘满）抛裸 `OSError` 且留半成品：改为 `BackupError` 并清理。

### 测试

- pytest 97 → 119 例全过；ruff 全洁；真实服务冒烟（建账→交易→metrics→备份→删库→恢复→数据一致）全链路通过。

## v2.0 - 2026-10-15

### 新增

- 银行账单侦探：导入银行 / 支付宝 / 微信账单，自动匹配分类，对不上的进侦探队列。
- 账单导入向导 `/statement`：上传 → 解析预览（自动识别模板 / 编码 / 表头前导行）→ 列映射可调（date / counterparty / summary / amount / direction，存为自定义模板复用）→ 确认。
- 预置 4 个模板：支付宝、微信支付、招商银行、工商银行。
- 三路匹配引擎 `matching.py`：关键词规则（priority）> 历史习惯（同商户多数票）> 候选建议（Top3 + 置信度）。
- 侦探队列 `/detective`：待认领卡片流，一键认领 / 换分类 / 记住为规则 / 跳过。
- 认领即学习：claim 时 `save_rule=true` 存关键词规则，下次同类自动入账。
- 转账识别：对方为自己账户名时建议转账。
- 指纹去重：`sha256(日期|金额|方向|对方|摘要)`，重复导入自动跳过。
- 账单解析 `statement_parser.py`：GBK / 表头探测 / 列映射。
- API（前缀 `/api`）：`statement-templates`（GET/POST/DELETE）、`statements/parse-preview`（POST multipart）、`statements/upload`（POST multipart）、`statements/batches`（GET）、`statements/{id}`（GET/DELETE）、`statements/{id}/confirm`（POST）、`statements/{id}/items`（GET）、`statements/items/{id}/claim`、`claim-transfer`、`skip`（POST）、`match-rules`（GET/POST/DELETE）。
- 测试增至 97 例。

### 修复

- 修 `style.css` 首行 css 围栏导致全站 CSS 变量失效。
- 修 `base.html` 顶栏类名与 CSS 设计体系脱节导致顶栏无样式。
- 修 `style.css` 尾部 `.chart-toolbar` 规则截断。

## v1 - 2026-10-13

### 新增

- 多账户、交易、分类、预算、统计。
- CSV 导入导出。
- 周期账单。
- 7 页 Web UI。
- pytest 34 例。
6. 正则防护：创建/更新时拒绝嵌套量词、回溯引用、超长（>200 字符）正则并 400 明示；匹配侧 haystack>500 字符熔断跳过（v2.11.1 关闭本项）。
7. 批量对账支持执行前预检（dry-run）与失败明细 CSV 导出（v2.11.1 关闭"失败明细未通过"项）。
8. preview 解释链展示被跳过规则的原因（停用/方向不匹配/非法正则/未命中）（v2.11.1 关闭本项）。
9. 提供 v6→v5 回滚脚本 scripts/rollback_v6_to_v5.py 与 docs/MIGRATION_RUNBOOK.md（v2.11.1 关闭"回滚未通过"项）。
10. 并发创建相同规则存在理论竞态（先查后插），已捕获转 409（或记录为已知限制，以实际合入为准）。
