# PRODUCTION_CHECKLIST_REPORT_v0.9

项目：second-brain「第二大脑」；版本：v0.9（按用户推送）；对照标准：仓库统一生产标准（6 大类）；性质：增量里程碑报告，v0.8.0 既有结论不变。本轮做的事是把"回顾推送"从只能推给一个人，改成能按用户分别推：push_log 表加了 user_id 列，推送调度改成按用户循环，API 多了 GET /api/digest，前端在 digest 模式下会跟着当前使用者切换内容，并且修了一个并发加载的竞态。下面按 6 大类逐条对照，只写 v0.9 动了什么，没动的沿用历史版本结论。

1. 可靠性：部分通过。测试金字塔方面，本轮新增 13 例测试，internal/store/push_user_test.go 8 例（空库/单用户/多用户排序/大小写归一化/未来到期排除/按用户推送隔离/老接口 local 兼容/历史按用户过滤），internal/api/digest_user_test.go 5 例真实 HTTP（X-User 隔离/?user= 参数/默认 local 回退/头优先于参数/推送历史按用户过滤）；`go test ./...` 全绿，旧测试（TestRunPushIdempotent 等）全部通过，`go vet ./...` 零警告，`gofmt -l` 零输出。错误处理沿用历史版本。DB 迁移版本化方面，push_log 加 user_id 列（默认 'local'），唯一索引从 (date, channel) 改为 (date, channel, user_id)，新增幂等迁移 migratePushLogUser（internal/store/push_migrate.go），老库（无 user_id 列）与新库双路径实测通过，老数据 user_id 回填 'local'。健康检查与优雅关闭沿用历史版本。

2. 可观测性：部分通过。结构化日志沿用历史版本；v0.9 顺手修了 tick 日志里 %q 误用于 error 的小 bug，报错定位因此更准一点。关键指标、基础告警沿用历史版本，本轮没有新增指标。

3. 数据与状态：部分通过。备份恢复沿用历史版本。多用户设计是本轮重点：store 层新增 ListUsersWithDueReviews(today)（返回有到期回顾的去重用户，带排序）、HasPushedFor/RecordPushFor（按日期+通道+用户去重）、ListPushLogFor（支持 ?user= 过滤）；PushRecord 加 user 字段；旧 HasPushed/RecordPush/ListPushLog 保留为默认 local 的兼容 wrapper，老调用方不用改。API 层新增 GET /api/digest，身份语义沿用 CurrentUser：X-User 头 > ?user= 查询参数 > 默认 local；响应是 {"user","date","notes"}，notes 元素含 id/title/snippet/tags/dueDate。GET /api/push/history 支持 ?user= 过滤。敏感数据、配置密钥分离沿用历史版本。

4. 部署运维：部分通过。Docker Compose、滚动更新、资源限制与日志轮转、运维手册沿用历史版本。本轮推送调度（internal/push/scheduler.go）新增 RunPushForUser（单用户独立 digest 推送）；RunPush 改为分发器——按 ListUsersWithDueReviews 循环每个用户，没有到期用户时回退默认用户单次推送（保持空库行为与旧测试兼容）；Scheduler.tick 按用户循环，HasPushedFor 按（日期，通道，用户）去重；PushResult 加 User 字段。这些改动没有引入新的部署步骤，老库升级由 migratePushLogUser 自动处理。

5. 安全与健壮性：部分通过。输入校验、防注入、鉴权沿用历史版本；v0.9 在身份识别上复用了 CurrentUser 的既有优先级（X-User 头 > ?user= 查询参数 > 默认 local），并有 5 例真实 HTTP 测试覆盖隔离、参数、默认回退、头优先于参数这几条路径，避免串号。依赖更新沿用历史版本。限流、超时、熔断沿用历史版本，本轮未动。前端（internal/web/static/review.js）加了 loadSeq 序列号 guard，修掉 loadDigest 与 __sbStartReview 并发时的混合态竞态，这个问题是视觉验收时发现并修的，属于健壮性上的实打实改进。

6. 可维护性：部分通过。模块边界与 API 契约方面，本轮新增 GET /api/digest，GET /api/push/history 扩了 ?user= 过滤，旧 store 接口保留为兼容 wrapper，边界清楚，老代码不会被强改。前端把 digest 加载抽成 loadDigest() 并记录 digestUser，digest 模式下进度行显示"1 / 5 · alice 的回顾"，__sbOnUserChange 在 digest 模式下按新使用者重载回顾（队列模式下重载队列），逻辑分叉写明了。CHANGELOG、技术债沿用历史版本，本轮没补。文档与代码同步沿用历史版本，已知限制那几条在下文单独列了。视觉验收方面，用真实服务加播种数据（2 用户各 3 篇到期笔记）跑了 3 张截图：alice digest（标题"今日回顾 · alice的笔记1"、进度"1 / 5 · alice 的回顾"）、bob digest（同理）、alice 队列（"1 / 3" 无混合态）；布局撑满视口、徽标数字正确、无 AI 味问题。

v0.9 新增风险与已知限制 4 项：

1. DigestNotes 的"补足"逻辑仍是全局笔记池（按该用户的复习历史排序补足），非到期补足部分可能出现其他用户创建的笔记——沿用既有语义，本轮未改。
2. 推送通道配置仍是全局的（SMTP/Webhook 收件人未按用户区分）：v0.9 做到"每个用户独立 digest 内容、独立去重"，但发往同一通道/收件人；按用户配置收件人为后续工作。
3. 端到端与失败注入沿用历史版本结论（未补齐）。
4. 离线队列评分回放仍按 local 归属（v0.6 已知限制，文档已声明）。

结论：v0.9 增量通过——按用户推送的内容隔离、去重、API 与前端切换都有测试和视觉验收兜底，老库迁移走幂等路径不需要人工介入；上面 4 项已知限制不阻塞本轮上线，其中按用户配置推送收件人留到后续版本处理。
