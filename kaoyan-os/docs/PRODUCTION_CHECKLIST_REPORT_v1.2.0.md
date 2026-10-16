# v1.2.0 发版对照报告

对照 `PRODUCTION_CHECKLIST.md`，逐条过一遍。版本 v1.2.0，深色模式，日期 2026-10-16。

## 1. 功能与测试

[通过] 深色模式功能完成：后端 `Settings.theme` 字段 + `PUT /api/settings` 校验，前端切换按钮 + `data-theme` + `index.css` 深色 token 覆盖。

[通过] vitest 28/28 全过，本轮新增 6 例：默认 light、PUT dark 持久化、`'blue'` / 数字 `1` / `'Dark'` 三例 400、切回 light。

[通过] 真实冒烟：PUT theme=dark 返回 200 并持久化，PUT theme=blue 返回 400，GET 确认落库值，全部符合预期。

[通过] 交互验收 INTERACT PASS：点切换按钮 → `data-theme=dark` 且服务端 theme 落库为 dark；再点切回 light。

[通过] 视觉验收：14 张真实截图（7 页 × 浅/深）+ 考试记录表 + 错题筛选态，人工看过，无布局 / 文字问题。截图在 `docs/screenshots/`。

## 2. 数据库与迁移

[不适用] 本轮无 DB 迁移。settings 表是 key-value 结构，theme 只是多了一个 key，建表结构没变，不需要迁移脚本。老库直接能跑。

## 3. 备份与恢复

[通过] 沿用 v1.1.0 的全量 JSON 备份 / 恢复机制，本轮没动这部分代码。settings 表本来就在备份范围内，theme 跟着一起走。

## 4. 故障演练

[未通过] 本轮没做故障演练，排期上放到了后面。不阻塞本次发版，但记在这里。

## 5. 可观测性

[通过] 日志 / 指标沿用既有方案（Fastify 默认日志），本轮没引入新的观测需求，也没改动日志配置。

## 6. 安全

[不适用] 鉴权限流不适用：本项目是本地单用户自托管，没有多租户、没有公网暴露面，`PUT /api/settings` 的输入校验（theme 只收 light / dark）已覆盖。

## 7. 文档

[通过] CHANGELOG.md 已更新到 1.2.0，Added / Fixed 都写全了。

[通过] README.md 功能列表加了深色模式一行，路线图标记 v1.2.0 已交付，新增 `## 深色模式` 一节。

## 技术债

无新增。

本轮顺手修的 3 个线上真 bug（`api.updateSettings` 用错 PATCH、`api.listMistakes` 布尔串、真题页 `subject=all` 透传）已计入 Fixed，不算技术债。

## 结论

可发版。
