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

## 演示数据

第一次启动时，如果数据库是空的，会自动写入一套演示数据：2 个分组（技术博客、科技资讯）、6 个订阅源、24 篇文章，发布时间错开在最近 7 天内，混合已读/未读/星标状态。源地址是真实站点的 RSS 地址，文章内容是本地生成的示例文本，仅供试用和截图。

演示数据只在空库时写入一次，不会覆盖你自己的数据。想要干净的库，删掉 `data/feedflow.db` 重启即可。

## 更新记录

- v1.1（2026-10-13）：视觉返工。阅读器三栏改为全幅布局（之前被锁在 900px 容器里，右边大片空白）；演示数据换成真实命名的订阅源和文章（之前是"示例博客"这类敷衍命名且有重复）；修了订阅管理页分组列显示"未分组"的加载竞态；修了搜索页模板变量写错导致永远无结果；短于 3 字的搜索词改走 LIKE 匹配（trigram 索引形不成 3 元组）。pytest 35 例全过，ruff 全洁。

## 功能

- 分组和源树，未读数直接标在名字后面。
- 三栏阅读器，键盘翻上下条，空格标已读。
- 未读、收藏、全部三种视图，按源或按分组筛。
- 全文搜索，中文按三元组匹配，正文一起搜。
- 每个源可单独设抓取间隔，也可只手动抓。
- OPML 导入导出，从别的阅读器搬过来不折腾。
- 支持 ETag 和 Last-Modified，源没更新就不重复拉。
- 后台调度器每 60 秒检查一次到期源。

## 快速开始

安装：

