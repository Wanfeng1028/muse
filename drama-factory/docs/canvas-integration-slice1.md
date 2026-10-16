# Playhouse 画布接入剧坊主流程 · 切片 1 契约

## 1. 背景与目标

画布成为剧坊的可插拔视图层，主流程是唯一事实源。

工程结构为 Project → Script → Scene → Shot，画布节点与 Shot 一一对应（`node.id = shot.id`）。

## 2. 三轮收敛摘要

### 观点

- 画布是剧坊的"可插拔视图层"，主流程是唯一事实源。
- 工程 Project → 剧本 Script → 场景 Scene → 镜头 Shot，画布节点与 Shot 一一对应（`node.id = shot.id`）。
- proposal 载体选 A：独立 proposal 对象 + approve/reject，带 `base_version`。
- 边加 `type`：`depends`（先后依赖，冲突拒绝 + 要求 rebase，防环）与 `ref`（引用角色/素材，后写覆盖 + 事件记录，不阻塞）。
- `node.status`、`asset_refs` 经 PATCH 白名单直写（`updated_by` 标记），其余字段一律走 proposal。
- 迁移适配器只读不落盘。
- `base_version` 分两层：`GET /canvas` 顶层 `version`（整图版本）同时作为 ETag 返回；SSE 每个事件带 `version`。
- `base_version` 只出现在 proposal 对象和 PATCH 请求里，取自客户端最后见到的 `version`。
- 节点级不加 `base_version`，用 `updated_at` 展示。
- 切片 1 先把字段位和 ETag 预留好，切片 2 直接接 409 回显，不用改契约。

### 依据

- Hark 第 1 轮：节点与 Shot 一一对应，`node.id = shot.id`。
- Hark 第 2 轮：proposal 载体选 A，带 `base_version`；approve 时版本已变返回 409 并回显冲突 ops。
- Hark 第 2 轮：`depends` 边冲突拒绝 + 要求 rebase，防环；`ref` 边后写覆盖 + 事件记录，不阻塞。
- Hark 第 2 轮：PATCH 白名单仅 `status`、`asset_refs`，其余字段走 proposal；迁移适配器只读不落盘。
- Hark 第 3 轮：`base_version` 只出现在 proposal 对象和 PATCH 请求里；节点级用 `updated_at` 展示。
- Hark 第 3 轮：切片 1 预留字段位与 ETag，切片 2 接 409 回显，不改契约。

### 共识

- 切片 1 开工：schema v2 + 迁移适配器 + GET + SSE。
- `depends` 边冲突时一律拒绝并要求 rebase。
- proposal 在切片 1 仅预留，approve/reject 随切片 2。
- `version` = 整图版本 = 乐观并发计数器（旧名 `revision`）。
- 旧 POC JSON（`version:1` + `revision`）在 load 时内存转 v2，绝不回写旧文件；无 `type` 的旧边默认 `depends`。

## 3. schema v2 字段表

### 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | number | 是 | 固定为 `2` |
| `version` | number | 是 | 整图版本，乐观并发计数器（旧名 `revision`） |
| `updated_by` | string | 是 | `editor` \| `agent` \| `job` |
| `updated_at` | string | 是 | ISO8601 |
| `nodes` | array | 是 | 节点列表 |
| `edges` | array | 是 | 边列表 |

### node 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 与 `shot.id` 一一对应 |
| `kind` | string | 是 | `script` \| `storyboard` \| `video` \| `edit` \| `qc` |
| `label` | string | 是 | 展示名 |
| `x` | number | 是 | 画布坐标 |
| `y` | number | 是 | 画布坐标 |
| `shot_ref` | string | 是 | 关联的 Shot 引用 |
| `params` | object | 是 | 节点参数 |
| `status` | string | 是 | `idle` \| `running` \| `done` \| `failed` |
| `asset_refs` | array | 是 | 素材引用列表 |
| `updated_at` | string | 是 | ISO8601，节点级时间展示依据 |
| `updated_by` | string | 是 | `editor` \| `agent` \| `job` |

### edge 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 边标识 |
| `source` | string | 是 | 源节点 id |
| `target` | string | 是 | 目标节点 id |
| `type` | string | 是 | `depends` \| `ref` |

## 4. 端点契约表

| 方法 | 路径 | 请求 | 成功响应 | 错误码触发条件 |
|---|---|---|---|---|
| GET | `/api/canvas` | 可带 `If-None-Match` | 200 v2；ETag: `"N"` | `If-None-Match` 命中 → 304 |
| GET | `/api/canvas/project` | 无 | 200 v2，另带废弃字段 `revision=version`（切片 2 移除） | — |
| PUT | `/api/canvas/project` | body 含 `base_version`（必填） | 200 | `base_version` 过期 → 409 + `current_version`/`updated_by`；`depends` 成环 → 400；`edge.type` 非法 → 400 |
| PATCH | `/api/canvas` | `op=update_node`，`fields` 仅 `status`/`asset_refs`，`If-Match` 头可代替 body `base_version` | 200，`updated_by=agent` | 违规 → 400；node 不存在 → 404；版本过期 → 409 |
| GET | `/api/canvas/events` | 无 | SSE | — |
| POST | `/api/canvas/proposals` | 无 | 202 pending（切片 1 仅预留，approve/reject 随切片 2） | — |
| GET | `/api/canvas/proposals` | 无 | 200 | — |
| POST | `/api/canvas/jobs` | 无 | 202 running，`drama.canvas.job-delay-ms` 后转 done，`node.status=done` 回填，`updated_by=job` | — |
| GET | `/api/canvas/jobs/{id}` | 无 | 200 | 不存在 → 404 |

## 5. SSE 事件表

| 事件 | data 字段 |
|---|---|
| `connected` | 带 `version` |
| `canvas.changed` | 带 `version` |
| `job.status` | 带 `version` |

每个事件的 `data` 均带 `version`。

## 6. 乐观并发规则

`version` 是整图版本，`GET /canvas` 顶层 `version` 同时作为 ETag 返回；`base_version` 只出现在 proposal 对象和 PATCH 请求里，取自客户端最后见到的 `version`；`If-Match` 头可代替 body `base_version`。

## 7. proposal 预留说明

切片 1 只存 pending，`POST /api/canvas/proposals` 返回 202 pending，`GET /api/canvas/proposals` 可读。

切片 2 做 approve/reject + 409 回显，不用改契约。

## 8. 迁移与兼容

迁移适配器只读不落盘。

旧 POC JSON（`version:1` + `revision`）在 load 时内存转 v2，绝不回写旧文件。

无 `type` 的旧边默认 `depends`。

`GET /api/canvas/project` 另带废弃字段 `revision=version`，切片 2 移除。

旧 bundle 不重编即可工作。

## 9. 切片 2 待办清单

- proposal 审批流：approve/reject，approve 时版本已变返回 409 并回显冲突 ops。
- `depends` 冲突拒绝 + rebase：冲突一律拒绝并要求 rebase。
- 存储切换触发条件：后端离开 localhost 或出现第二个写入者。

## 10. 用户拍板记录

- 2026-10-16：切片 1 开工。
- 2026-10-16：`depends` 冲突一律拒绝并要求 rebase。