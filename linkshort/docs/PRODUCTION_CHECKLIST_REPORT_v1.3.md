
# 发版对照报告 v1.3

日期：2026-10-15
对照版本：v1.2
结论：**可发版**

## 可靠性

| 项 | 状态 | 理由 |
| --- | --- | --- |
| purge 开关默认关闭行为不变 | 通过 | 默认 `LINKSHORT_BURN_PURGE_AFTER_DESTROY=false`，行为与 v1.2 完全一致 |
| purge 开 302→404 语义 | 通过 | 真实服务 127.0.0.1:18097 验证：建 burn 链 201 → 访问 302 → 再访 404 |
| purge 失败不阻断跳转 | 通过 | 代码走查：purge 出错只记日志，不影响 302 |
| 备份恢复脚本安全门 | 通过 | `--force` 拒绝/放行、`--dry-run` 不动数据、恢复前后 integrity_check 均实测 |
| -race 58 例全过 | 通过 | `go test ./... -race -count=1` 全过，58 例 |

## 可观测性

| 项 | 状态 | 理由 |
| --- | --- | --- |
| 新指标 `linkshort_burn_links_purged_total` | 通过 | purge 开实测计数 1，purge 关为 0 |
| `/api/meta` 暴露开关状态 | 通过 | 新增 `burn_purge_after_destroy` 字段，true/false 均验证 |

## 数据

| 项 | 状态 | 理由 |
| --- | --- | --- |
| purge 级联删除 visits、统计口径变化已文档化 | 通过 | links 表无残留，visits 级联删除；OPERATIONS.md 写明 clicks 从统计消失 |
| 备份恢复自动化演练 | 通过 | v1.2 未通过项已关闭，演练输出见 OPERATIONS.md（2026-10-15） |

## 部署运维

| 项 | 状态 | 理由 |
| --- | --- | --- |
| `make backup` / `make restore` | 通过 | 备份在线成功；停服删库恢复后重启验证通过 |

## 安全

| 项 | 状态 | 理由 |
| --- | --- | --- |
| 沿用 v1.1/v1.2 鉴权限流 | 通过 | 未改动鉴权与限流逻辑 |

## 可维护性

| 项 | 状态 | 理由 |
| --- | --- | --- |
| 新增 6 例测试 | 通过 | store PurgeLink 2、handler 跳转 purge 语义 2 + meta 1、metrics purged 指标 1 |

## 真实服务冒烟

| 项 | 状态 | 理由 |
| --- | --- | --- |
| purge 关 302→410 | 通过 | 真实服务验证 |
| purge 开 302→404 | 通过 | 真实服务验证 |
| max_visits 302×2→410 回归 | 通过 | 真实服务验证 |
| 普通链 302 | 通过 | 真实服务验证 |
| meta 字段 true/false | 通过 | 真实服务验证 |
| metrics purged_total 1 | 通过 | 真实服务验证 |
| 备份在线成功 | 通过 | 真实服务验证 |
| 删库恢复后 readyz 200 + 数据一致 | 通过 | overview {"enabled_links":2,"links":3,"today_clicks":6,"total_clicks":6}，/smk-plain 302，/smk-burn1 410 |

## 已知缺口

1. 高并发 clicks 检查仍未做分布式锁（单连接串行写入缓解，v1.1 起遗留）。
2. restore.sh 目标 DB 不存在时仍会打印"旧 DB 快照: xxx.broken-..."一行（实际跳过了快照），文案小瑕疵，未修。
=== END
