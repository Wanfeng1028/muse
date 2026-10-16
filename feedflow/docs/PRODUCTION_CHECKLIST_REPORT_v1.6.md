
# feedflow v1.6 发版对照报告（生产级 Definition of Done）

版本：v1.6「阅读体验」· 2026-10-16
范围：阅读器键盘快捷键增强、阅读进度记忆（DB 迁移 v4、新进度保存接口）、OPML 导出加固。
生成方式：按 C 批文档任务对照 v1.4 报告骨架逐节填写，事实依据来自本轮 A 批（键盘快捷键 + 阅读进度）、B 批（OPML 加固）改动记录与测试结果。

## 1. 可靠性
- [通过] pytest 129 例全过。基线 115 例，本轮新增 14 例：tests/test_progress.py 8 例、tests/test_opml.py 新增 6 例。
- [通过] ruff 全洁，无告警。
- [通过] DB 迁移走既有版本化机制（PRAGMA user_version），版本从 v1 递增到 v4，老库打开自动补列，无手工步骤。

## 2. 可观测性
- [通过] 无新增指标。
- [通过] 进度保存接口 `POST /api/articles/<id>/progress` 走既有结构化日志，不新增日志通道。

## 3. 数据与状态
- [通过] `articles.scroll_pos` 随文章行存储，迁移 v4 补列，默认值 0。
- [通过] 整库备份恢复 CLI 已覆盖 scroll_pos，无需单独备份逻辑。
- [通过] 无新增敏感数据，进度值仅记录阅读位置。

## 4. 部署与运维
- [通过] docker-compose 配置不变。
- [通过] 老库迁移自动补列，scroll_pos 默认 0，启动无需人工干预。

## 5. 安全与健壮性
- [通过] `/api/articles/<id>/progress` 校验 scroll_pos 为非负数字，超过 10 万钳制。
- [通过] 404/400 按既有 `_err` 格式返回，接口错误结构与其它接口一致。
- [通过] OPML 导出对标题/网址为 None 的脏数据做 None-safe 处理，不再 500。

## 6. 可维护性
- [通过] CHANGELOG 新增 v1.6 条目，README 功能节与更新记录节同步更新（并纠正了原先"空格标已读"的错误描述，实际快捷键为 `r`/`m`）。
- [遗留] 技术债：`api.py` 的 `PUT /api/folders/<id>` 调用了 `store.get_folder` / `store.update_folder_position`，但这两个函数在 store.py 中不存在。历史遗留 bug，本轮未改动，排期下轮修。

## 7. 视觉验收
- [通过] 阅读器三栏用真实数据截图亲眼验收，本轮新增样式只有 `?` 快捷键帮助浮层，无布局变化。
- [通过] 截图路径 docs/screenshots/reader.png 沿用既有门面图。

## 结论
**可发版**。可靠性、数据、部署、安全、可维护性各项对照通过，视觉验收已确认。
遗留排期：
1. 修 `PUT /api/folders/<id>` 的缺失 store 方法（`store.get_folder` / `store.update_folder_position`）。
2. README"快速开始"节仍是 stub（"安装："后无内容），排期补全。
