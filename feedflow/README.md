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

