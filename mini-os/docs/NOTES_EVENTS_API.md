# 便签与日程接口文档

## 1. 概述

本文档描述便签（notes）和日程（events）两组接口。两者都要求登录 cookie，都按 `user_id` 做数据隔离。请求其他用户的资源 id，一律返回 404，不区分"不存在"和"无权限"。

数据库迁移编号 007。

## 2. 数据模型

### notes

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | INTEGER | PRIMARY KEY | 主键 |
| user_id | INTEGER | NOT NULL | 所属用户 |
| title | TEXT | NOT NULL DEFAULT '' | 标题 |
| body | TEXT | NOT NULL DEFAULT '' | 正文 |
| pinned | INTEGER | NOT NULL DEFAULT 0 | 是否置顶，0/1 |
| updated_at | TEXT | NOT NULL | 更新时间 |

### events

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | INTEGER | PRIMARY KEY | 主键 |
| user_id | INTEGER | NOT NULL | 所属用户 |
| title | TEXT | NOT NULL | 标题 |
| starts_at | TEXT | NOT NULL | 开始时间 |
| ends_at | TEXT | NULL | 结束时间 |
| all_day | INTEGER | NOT NULL DEFAULT 0 | 是否全天，0/1 |
| done | INTEGER | NOT NULL DEFAULT 0 | 是否完成，0/1 |
| created_at | TEXT | NOT NULL | 创建时间 |

## 3. 接口表

所有接口都需要登录 cookie。

| 方法 | 路径 | 权限 | 请求 | 响应 | 状态码 |
| --- | --- | --- | --- | --- | --- |
| GET | /api/notes | NotesRead | 无 | 便签数组，按 `pinned DESC, updated_at DESC` | 200 |
| POST | /api/notes | NotesWrite | `{title?, body?}` | 新建的便签 | 201 |
| PUT | /api/notes/:id | NotesWrite | `{title?, body?, pinned?}` | 更新后的便签 | 200 |
| DELETE | /api/notes/:id | NotesWrite | 无 | 无 | 204 |
| GET | /api/events?from=&to= | NotesRead | 查询参数 `from`、`to`，ISO 字符串 | 日程数组，按 `starts_at ASC` | 200 |
| POST | /api/events | NotesWrite | `{title, startsAt, endsAt?, allDay?}` | 新建的日程 | 201 |
| PUT | /api/events/:id | NotesWrite | `{title?, startsAt?, endsAt?, allDay?, done?}` | 更新后的日程 | 200 |
| DELETE | /api/events/:id | NotesWrite | 无 | 无 | 204 |

说明：

- POST /api/notes 不传 `title` 时，标题为 `"未命名便签"`。
- PUT 类接口只更新请求里提供的字段，没提供的保持原值。
- GET /api/events 的 `from`/`to` 都不传时返回全部；`to` 是开区间。

字段一律 camelCase：`userId`、`startsAt`、`endsAt`、`allDay`、`createdAt`、`updatedAt`。

## 4. 校验规则

- `title`：trim 后为空返回 400，消息 `"标题不能为空"`；超过 200 字符返回 400。
- `startsAt` / `endsAt`：格式非法返回 400。接受 `YYYY-MM-DD` 或 `YYYY-MM-DDTHH:MM`，存储时统一规范化为 `YYYY-MM-DDTHH:MM:SS`。
- `endsAt` 早于 `startsAt` 返回 400。

## 5. 时间格式说明

- 存储格式统一为 `YYYY-MM-DDTHH:MM:SS`。
- 写入时接受 `YYYY-MM-DD` 和 `YYYY-MM-DDTHH:MM` 两种写法，服务端补全为秒。
- 查询参数 `from`、`to` 用 ISO 字符串，形如 `YYYY-MM-DDTHH:MM:SS`。
- `to` 为开区间。查某一天的日程，传 `from=当天00:00:00&to=次日00:00:00`。

## 6. RBAC

权限点：

- `Permission::NotesRead`：GET 类接口。
- `Permission::NotesWrite`：POST / PUT / DELETE。

角色：

- Admin：读写。
- Editor：读写。
- Viewer：只读。任何写操作返回 403。

跨用户 id 一律 404。

## 7. 前端小组件行为

### 今日日程

- 拉取当天范围：`GET /api/events?from=当天00:00:00&to=次日00:00:00`。
- 新增支持快捷写法，例如输入 `10:00 开会`，解析出时间与标题后走 `POST /api/events`。
- 勾选完成：`PUT /api/events/:id`，带 `done`。
- 删除需要二次确认。

### 速记便签

- 首次渲染自动绑定第一条 pinned 便签；没有则新建 `"桌面速记"` 并置顶。
- textarea 输入防抖 800ms，然后 `PUT /api/notes/:id` 更新 `body`。
- 数据走后端 API，不用 localStorage 做唯一存储。

## 8. 示例 curl

列出便签：

```
curl -b cookies.txt http://localhost:3000/api/notes
```

新建便签：

```
curl -b cookies.txt -X POST http://localhost:3000/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"title":"购物清单","body":"牛奶"}'
```

更新便签（只改 pinned）：

```
curl -b cookies.txt -X PUT http://localhost:3000/api/notes/12 \
  -H 'Content-Type: application/json' \
  -d '{"pinned":1}'
```

删除便签：

```
curl -b cookies.txt -X DELETE http://localhost:3000/api/notes/12
```

查某天日程：

```
curl -b cookies.txt 'http://localhost:3000/api/events?from=2025-03-01T00:00:00&to=2025-03-02T00:00:00'
```

新建日程：

```
curl -b cookies.txt -X POST http://localhost:3000/api/events \
  -H 'Content-Type: application/json' \
  -d '{"title":"开会","startsAt":"2025-03-01T10:00","endsAt":"2025-03-01T11:00"}'
```

标记日程完成：

```
curl -b cookies.txt -X PUT http://localhost:3000/api/events/7 \
  -H 'Content-Type: application/json' \
  -d '{"done":1}'
```

删除日程：

```
curl -b cookies.txt -X DELETE http://localhost:3000/api/events/7
