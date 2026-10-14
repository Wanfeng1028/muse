
# 更新日志

本文件记录 linkshort 的所有重要变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [v1.1.0] - 2026-10-14

### 新增

- **限次访问**：链接可设置最多可访问次数 N，前 N 次返回 302，第 N+1 次返回 410"链接已达访问上限"。
- **阅后即焚**：一次性链接，首次访问返回 302，之后返回 410"链接已阅销毁"。销毁检查在禁用检查之前。
- **remaining 字段**：API 响应新增 `max_visits`、`burn`、`remaining`（剩余次数，null=不限）。
- **数据库版本化迁移**：`db.go` 使用 `PRAGMA user_version` 做版本化迁移，v1→v2 自动为老库 `ALTER` 加列，实测老数据保留。
- **Web UI**：
  - 新建页加"限次访问"输入框 + "阅后即焚"复选框（互斥联动）。
  - 列表页加"限制"列徽标（阅后即焚 / 已销毁 / 限 N 次·剩 M 次 / 不限）。
  - 详情页加"访问限制"行，支持编辑保存与清除。
- **测试**：新增 10 例。store 4 例（迁移版本与列、CreateLinkEx、MarkBurned、UpdateLinkEx）；handler 6 例（创建限次/阅后即焚、非法限次 400、限次达限 410、阅后即焚 410、已阅销毁优先于禁用 404、PATCH 限次更新/清除）。

### 变更

- `linkJSON` 新增三个字段：`max_visits`、`burn`、`remaining`。
- `POST /api/links` 接受 `max_visits`（正整数，1~1000000）、`burn`（bool）；非法组合返回 400（burn 与 max_visits≠1、max_visits≤0）。
- `PATCH /api/links` 支持 `max_visits`（数字 / null 清除）、`burn`。

### 已知缺口

- CSV 导入导出未带新字段（排期 v1.2）。
- 高并发下两次访问可能都通过 clicks 检查（单连接串行写入缓解，未做分布式锁）。
- burn 链接"销毁"后数据仍保留在库中（可查统计，彻底删除需手动删）。

## [v1.0.0] - 2026-10-13

工程化 v1：短链 CRUD/跳转/统计/二维码/导入导出/Web UI 四页。
