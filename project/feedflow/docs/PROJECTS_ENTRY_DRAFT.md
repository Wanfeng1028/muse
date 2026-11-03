
# feedflow

feedflow v1.6「阅读体验」：给阅读器补齐了键盘快捷键（`j`/`k` 上下篇、`o` 打开原文、`r` 标已读、`s` 加星、`?` 帮助浮层），加了按文章记忆的阅读进度（滚动位置存 SQLite，重进接着看），并加固了 OPML 导出（脏数据不崩、补 `dateCreated`）。同时纠正了 README 里"空格标已读"的错误说明。

## 构建与测试

- pytest 129 例全过
- ruff 全洁

## 发版对照报告

- docs/PRODUCTION_CHECKLIST_REPORT_v1.6.md

## 遗留

- `PUT /api/folders/<id>` 调用的 `store.get_folder` / `store.update_folder_position` 在 store.py 里不存在，历史遗留，排期下轮修。
- README"快速开始"节仍是 stub（"安装："后无内容），排期补全。
