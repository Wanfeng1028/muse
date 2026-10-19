# second-brain v0.15 发版对照报告（2026-10-20）

## 变更清单

### 1. 困难卡片标记与 SM-2 联动
- 文件：internal/store/migrate.go（v3 迁移 reviews_is_hard）、internal/store/review.go
  （SetHardMark/GetHardMark/ListHardNotes/HardMarkMap；RecordReview 惩罚逻辑）、
  internal/api/review.go（POST /api/review/{id}/hard、queueItem.hard）。
- 行为：reviews 表加 is_hard 列，迁移 v3 幂等；RecordReview 的 upsert 显式写
  is_hard=0 且 DO UPDATE 不触碰该标记，避免复习时误清困难标记；
  POST /api/review/{id}/hard 请求体 {hard} 返回 {id,hard}，卡片不存在返回 404，
  参数非法返回 400；复习队列项带 hard 字段；SM-2 联动——grade=3 且该卡片已标
  hard 时，下次间隔减半。
- 测试文件：internal/store/review_hard_test.go、review_hard_link_test.go、
  internal/api/review_hard_test.go。

### 2. 复习统计后端与前端
- 文件：internal/api/review.go（GET /api/review/trend、GET /api/review/mastery）、
  web 前端复习视图与新增"复习统计"视图。
- 行为：GET /api/review/trend?days=7 返回 {days, trend[{date,reviewed,added}]}；
  GET /api/review/mastery 返回 {mastery[{tag,total,avgEf,hard,due}]}；前端卡片上
  增加"标记为困难"切换钮（描边/填色两态，无 emoji）；完成态升级为 4 数字面板
  （复习篇数/标记困难/连续天数/近 7 天复习）+ 事实型提示语；新增"复习统计"导航项，
  含近 7 天趋势 canvas 条形图（复习深色柱+新增浅色柱，手绘无图表库）与各科掌握度表
  （EF 条）。

### 3. 推送通道深测与死信 E2E
- 文件：推送相关测试（SMTP/WebPush/死信）。
- 行为：SMTP 失败注入（握手中断/连接被拒/535/完整对话，fake 脚本服务器）；
  WebPush 部分失败（410 清理/500 耗尽/混合）；死信 E2E（双通道耗尽→failed_permanent，
  同日重跑再尝试且死信幂等，次日按天隔离重发；不可重试错误一次即死信）；
  P2-5：WebPush 无到期时也推送空 digest（与 SMTP/Webhook 一致）。

### 4. 图谱力导向布局升级
- 文件：web 图谱视图。
- 行为：力导向布局（斥力+引力+重力+位移钳制，确定性无随机）；孤立节点聚合
  （≥8 聚成簇）；滚轮缩放（0.3~4）、拖拽平移、悬停浮层、标签碰撞避让。

### 5. P1-6/P2-5 偿还
- 文件：internal/store/migrate.go（v4 迁移 notes.client_note_id + 唯一索引）、
  internal/store 笔记创建路径（CreateNoteFor 幂等读）、web/offline-queue.js、
  WebPush 推送路径。
- 行为：P1-6 离线新建笔记客户端幂等键 clientNoteId，迁移 v4 加 notes.client_note_id
  与唯一索引，CreateNoteFor 幂等读，offline-queue.js 入队注入 crypto.randomUUID；
  P2-5 WebPush 无到期时也推送空 digest。
- 另附：scripts/seed-demo 种子脚本，55 篇中文演示笔记、71 双链、20 篇复习历史、
  5 篇困难标记，可重复运行幂等。

## 生产 checklist 关键项自评
- 数据迁移：通过。v3/v4 迁移幂等，可重复执行；RecordReview 的 upsert 显式写
  is_hard=0 且 DO UPDATE 不触碰标记，升级不会误清已有困难标记。
- 兼容性：通过。Note 新增 clientNoteId omitempty，老数据与老客户端不受影响；
  WebPush 空 digest 只增行为，不改变既有到期推送语义。
- 可观测性：通过。复习统计与掌握度提供趋势与标签维度数据；死信 E2E 覆盖双通道
  耗尽、同日幂等、次日隔离与不可重试快速失败。
- 前端可用性：通过。困难切换钮两态清晰；复习统计视图含趋势与掌握度表；图谱支持
  缩放/平移/悬停/标签避让，无随机导致的可复现性问题。

## 已知限制
- 困难标记的 SM-2 惩罚只在 grade=3 时触发，grade≤2 本来就会重置间隔。
- 种子脚本只用于演示/截图验收，不随服务发布。

## 结论
待 go test ./... 全绿 + go vet/gofmt 全洁后可发版。
