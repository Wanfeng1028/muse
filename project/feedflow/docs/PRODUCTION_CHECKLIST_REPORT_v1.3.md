# FeedFlow v1.3 发版对照报告

本轮 v1.3 做了两件事：一是加 Fever API 兼容，第三方 RSS 客户端能直连同步；二是把正文提取的超时收敛住，超时就回落 RSS 摘要。下面按 7 个节逐条对照，每条给结论。

## 一、可靠性

- pytest 单元 + API 集成：通过：84/84 全过（含新增 tests/test_fever.py 22 例）
- Fever 写操作参数校验 400/404 齐全：通过。mark=item / mark=feed / mark=group 这些写法里，参数缺、类型不对、目标不存在的情况都有对应返回码。
- 正文提取超时有界：通过。FEEDFLOW_EXTRACT_TIMEOUT 默认 15 秒，在 config.py 的 load 和 validate 里过一遍，trafilatura.fetch_url 走 config 的 DOWNLOAD_TIMEOUT，超时回落 RSS 摘要，不会一直卡着。
- DB 迁移 v3 版本化、老库自动 ALTER：通过。用 PRAGMA user_version 判断版本，老库自动补 articles.last_read_at 列。
- 健康检查 /healthz 沿用 v1.1：通过。这轮没动它。
- 失败注入测试本轮未新增：未通过，排期 v1.4。

## 二、可观测性

- 结构化日志 request_id 全链路沿用 v1.1，Fever 请求走同一套 before_request：通过。fever 蓝图挂在同一个 app 上，日志和 request_id 是同一套。
- 未新增 Prometheus 指标：未通过，排期 v1.4。

## 三、数据与状态

- 备份恢复 CLI 沿用 v1.1：通过。这轮没动它。
- last_read_at 为普通时间戳列、无敏感数据：通过。就是标已读时 store.set_read 记一下时间。
- FEEDFLOW_FEVER_API_KEY 走环境变量、不落库、fever-key 只在终端输出一次：通过。key 只从环境变量读，生成命令只在终端打印一次。

## 四、部署运维

- docker-compose 一键部署沿用 v1.1：通过。这轮没动它。
- 新增的两个环境变量已进 .env.example：通过。FEEDFLOW_FEVER_API_KEY 和 FEEDFLOW_EXTRACT_TIMEOUT 都写进去了。
- docs/OPERATIONS.md 未补 Fever 章节：未通过，排期 v1.4。

## 五、安全与健壮

- hmac.compare_digest 常量时间比较：通过。api_key 和环境变量里的 FEEDFLOW_FEVER_API_KEY 比较用常量时间，避免时序侧信道。
- 未配置 key 时接口整体关闭：通过。没配 FEEDFLOW_FEVER_API_KEY 就返回 auth:0，接口不干活。
- SQL 全参数绑定：通过。没有拼字符串的地方。
- items 分页 50 封顶：通过。since_id / max_id / with_ids 每条路径都封顶 50。
- unread_item_ids 全量返回、大库下可能偏大：通过，但列为已知限制。这个接口按 Fever 协议就是返回全量未读 id，库大了响应体会偏大，先记着。

## 六、可维护性

- fever.py 为独立协议适配层，读走 db.query_*、写复用 store 写锁语义：通过。读路径直接查，写路径复用 store 的写锁，不自己另搞一套。
- CHANGELOG / README / .env.example 已同步：通过。
- 技术债：OPERATIONS.md 补 Fever 章节、Prometheus 指标、失败注入测试（均排期 v1.4）。

## 七、发版结论

可发版（v1.3）。遗留三项排期 v1.4：OPERATIONS.md 补 Fever 章节、Prometheus 指标、失败注入测试。

## 实测记录

- 通过：84/84 全过（含新增 tests/test_fever.py 22 例）：pytest 单元 + API 集成，由编排者实测回填。
- 通过：ruff check 全洁（本轮新增的 I001/UP012/RUF059/F841 已修复；ruff format 非仓库强制项，基线已有 22 文件未格式化）：ruff 检查结果，由编排者实测回填。
- 通过：真实服务冒烟 9 项全过——错误 key 鉴权拒绝、groups/feeds/items/unread_ids 读取、单篇标已读/星标/取消、按源标已读、unread_recently_read 恢复、400/404 参数校验、既有页面（//digest//stats//api/stats）回归 200；extract_timeout 配置缓存验证通过：冒烟结论，由编排者实测回填。
