# 信流 FeedFlow · 自托管 RSS 阅读器

自托管的 RSS 阅读器。一个进程、一个 SQLite 文件，跑起来就能用。

[![CI](https://img.shields.io/badge/build-passing-brightgreen.svg)](#)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1.3-000.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 截图

阅读器三栏：左边分组和源，中间文章列表，右边正文。

![阅读器三栏](docs/screenshots/reader.png)

订阅管理：新建源、改分组、调抓取间隔都在这一页。

![订阅管理](docs/screenshots/feeds.png)

统计：订阅源、文章、未读一览。

![统计](docs/screenshots/stats.png)

搜索：标题、正文、作者一起搜。

![搜索](docs/screenshots/search.png)

OPML：导入导出订阅清单。

![OPML](docs/screenshots/opml.png)

阅读器里的"为什么排前面"：打开文章自动算出重要性总分，五个分项一条条摆出来，每条理由都是大白话。

![为什么排前面](docs/screenshots/reader-score.png)

设了密码后先过登录页，默认不设密码、行为不变。

![登录页](docs/screenshots/login.png)

## 重要性排序与今日必读

订阅一多，时间线根本刷不完，最后往往变成"收藏夹吃灰"。今日必读每天只挑最重要的 N 篇给你，默认 20 篇，想多看几篇就去兴趣设置里改数字。

每篇文章都会算一个 0~1 的重要性分数，它是下面五个分项的加权和。每个分项都先归一化到 0~1，所以分数可以拆开看，不是黑盒：

| 分项 | 怎么算 | 权重 |
| --- | --- | --- |
| 时效 | 发布时间越近越高，半衰期 48 小时 | 0.30 |
| 事件热度 | 同一事件跟进的文章越多越高 | 0.25 |
| 来源 | 你手动设的权重 × 系统按你的已读/星标学到的权重 | 0.20 |
| 关键词 | 标题或正文命中你设的关键词就加分 | 0.15 |
| 未读 | 没读过的文章有加成 | 0.10 |

今日必读页每篇文章下面都会写清"为什么这篇排前面"，哪一项拉的分、拉了多少，一眼就能看到。


![今日必读](docs/screenshots/digest.png)

今日必读页，每篇下面都标了排序理由。

关键词和来源权重不用记公式，在"今日必读"页右上角点"调我的兴趣"就能改，改完排序立刻生效。

## 聚类 Top：同一事件只看一次

同一件事十个源都在报，时间线刷不动。聚类 Top 把去重后的事件按重要性排成卡片流，一张卡片就是一件事：聚类主题、成员篇数、来源数、来源标题（至多 5 个）、簇重要性分，以及"为什么这件事排前面"（cluster_reasons）。点开卡片能看到每篇成员的排序理由（score_info），"还有 N 篇已折叠"告诉你这件事一共被报了多少次。

![聚类 Top](docs/screenshots/clusters.png)

设计注记：卡片流不用三栏特性格样板；分数必须可解释——用户能看到每一项的来由；无数据时如实提示，不许空状态当门面。


## Fever API（第三方客户端同步）

想在手机或别的阅读器里看？FeedFlow 兼容 Fever 协议，Reeder、Unread 这类支持 Fever 的客户端可以直接连上来同步，
订阅、文章、已读和星标状态两边互通。

三步接上：

1. 生成 api_key：跑 `python -m feedflow fever-key`，按提示输入邮箱和密码（密码不回显），它会吐出一串 md5。
   这个邮箱密码只活在你这条命令里，服务端只认这串 md5。
2. 启动服务时带上环境变量：`FEEDFLOW_FEVER_API_KEY=<那串 md5>`。
3. 在客户端里加 Fever 账号：地址填 `http://你的机器:8300/fever/`，用户名/密码随便填当时输入的那套就行，
   客户端实际提交的是 api_key。

几点如实说明：

| 事项 | 现状 |
| --- | --- |
| 已支持 | 分组/订阅/文章/未读 id/星标 id 读取；单篇标已读、标星标/取消星标；按源/按组标已读（带 before 时间戳）；unread_recently_read |
| 分页 | items 接口支持 since_id/max_id/with_ids，每次最多 50 篇 |
| favicon | 没做抓取，统一返回 1x1 透明占位图 |
| is_spark | 没这个概念，恒为 0 |
| 未分组的源 | 归到 group 0；按组标已读时 id=0 表示全部源 |

安全提醒：Fever 协议本身是明文 api_key，自用走内网或反向代理加 HTTPS；api_key 妥善保管，泄露了重新生成一个换上就行。

## 演示数据

第一次启动时，如果数据库是空的，会自动写入一套演示数据：2 个分组（技术博客、科技资讯）、6 个订阅源、24 篇文章，发布时间错开在最近 7 天内，混合已读/未读/星标状态。源地址是真实站点的 RSS 地址，文章内容是本地生成的示例文本，仅供试用和截图。

演示数据只在空库时写入一次，不会覆盖你自己的数据。想要干净的库，删掉 `data/feedflow.db` 重启即可。

## 监控指标

`GET /metrics` 返回 Prometheus 文本格式，可直接被抓取。

| 指标名 | labels | 含义 |
| --- | --- | --- |
| `feedflow_http_requests_total` | `method`、`route`、`status` | HTTP 请求计数。 |
| `feedflow_fetch_total` | `status` | 抓取总次数。 |
| `feedflow_fetch_errors_total` | `kind` | 抓取错误计数，`kind` 取值 `timeout` / `dns` / `http_4xx` / `http_5xx` / `parse_error` / `unknown`。 |
| `feedflow_articles_stored_total` | 无 | 已入库文章累计数量。 |
| `feedflow_fetch_duration_seconds_total` | 无 | 抓取耗时累计秒数。 |
| `feedflow_feeds_total` | 无 | 订阅源总数。 |
| `feedflow_articles_total` | 无 | 文章总数。 |
| `feedflow_unread_total` | 无 | 未读文章数。 |
| `feedflow_starred_total` | 无 | 加星文章数。 |

## 更新记录

### v1.6 — 2026-10-16

- 键盘快捷键：`j`/`k` 上下篇、`o` 新标签页打开原文、`r` 标已读/未读、`s` 加星/取消星标、`?` 快捷键帮助浮层。
- 阅读进度记忆：滚动位置按文章存进数据库，重进自动恢复。
- OPML 导出加固：脏数据不崩，加 `dateCreated`。
- 测试：pytest 129 例全过、ruff 全洁。

### v1.4 — 2026-10-16


- 新增 Prometheus 指标（`GET /metrics`）。
- 新增失败注入测试。
- 补全运维手册，共 8 章。
- 新增 Fever 运维章节。
- 移动端阅读优化（≤768px：订阅/文章/正文三段式视图切换，顶栏横滑，触控目标 ≥44px）。
- 测试：pytest 102 例全过（新增 18：指标 6 + 失败注入 12）、ruff 全洁。

![移动端阅读器](docs/screenshots/reader-mobile.png)

移动端：三段式视图切换，一次只看一栏。

- v1.1（2026-10-13）：视觉返工。阅读器三栏改为全幅布局（之前被锁在 900px 容器里，右边大片空白）；演示数据换成真实命名的订阅源和文章（之前是"示例博客"这类敷衍命名且有重复）；修了订阅管理页分组列显示"未分组"的加载竞态；修了搜索页模板变量写错导致永远无结果；短于 3 字的搜索词改走 LIKE 匹配（trigram 索引形不成 3 元组）。pytest 35 例全过，ruff 全洁。

## 功能

- 分组和源树，未读数直接标在名字后面。
- 三栏阅读器，键盘操作：`j`/`k` 上下篇、`o` 打开原文、`r` 标已读、`s` 加星、`?` 看全部快捷键；阅读进度按文章记住，重进接着看。

- 未读、收藏、全部三种视图，按源或按分组筛。
- 全文搜索，中文按三元组匹配，正文一起搜。
- 每个源可单独设抓取间隔，也可只手动抓。
- OPML 导入导出，从别的阅读器搬过来不折腾。
- 支持 ETag 和 Last-Modified，源没更新就不重复拉。
- 后台调度器每 60 秒检查一次到期源。
- 可选单用户密码门：默认关闭；设 FEEDFLOW_AUTH_PASSWORD_HASH（推荐）或 FEEDFLOW_AUTH_PASSWORD 即开启，开启时必须同时设 FEEDFLOW_SECRET_KEY；探针与 Fever 不受影响，详见 OPERATIONS.md 第 11 节。

## 快速开始

安装：

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# 或
make install
```

运行：

```bash
make run
# 等价于 .venv/bin/python -m feedflow serve
```

然后浏览器打开 http://127.0.0.1:8300（监听地址与端口可用 FEEDFLOW_HOST / FEEDFLOW_PORT 环境变量修改）。

手动抓一次订阅：

```bash
make fetch
```

跑测试：

```bash
make test
```

Docker 一把梭：

```bash
docker compose up --build
```

容器内监听 8300 并映射到宿主机 8300；数据库与备份落在宿主机 ./data 目录（挂载为 /app/data），重建容器不丢数据。启动后同样打开 http://127.0.0.1:8300。

