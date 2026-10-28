# 考研指挥舱 API 文档

> 版本：v1.11.0 ｜ 与代码同步校验：tests/api-docs-sync.test.ts（路由增删必须同步更新本文档，否则 CI 测试失败）
> 认证方式：除标注"免认证"外，所有接口需登录（cookie 会话）。未登录返回 401 { error: '...' }。

## 通用约定

- 基地址：/api；请求/响应均为 JSON（除特别说明）。
- 错误响应统一为 { error: '中文原因' }，状态码见各接口。
- 日期格式：YYYY-MM-DD；时间：ISO 8601。
- subject 取值：math（数学）/ english（英语）/ politics（政治）/ major（专业课821）。
- 会话 Cookie 名：`kaoyan_session`；有效期 30 天，空闲超过 24 小时访问会自动续期。
- 写方法（POST/PUT/PATCH/DELETE）若带 `Origin` 头且与当前 host 不一致，直接返回 403 `{ error: '非法来源' }`。

---

## 1. 认证

### `POST /api/auth/register`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/auth/register | 免认证 |

**请求参数（body，JSON）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | username | string | 是 | 小写字母开头，仅含小写字母/数字/下划线，长度 3~32（正则 `^[a-z][a-z0-9_]{2,31}$`） |
| body | password | string | 是 | 按 UTF-8 字节数计，8~72 字节 |

**成功响应**

状态码：201

```json
{
  "id": 1,
  "username": "alice",
  "created_at": "2025-01-01T00:00:00.000Z"
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "用户名格式不合法" }` | username 不满足 `^[a-z][a-z0-9_]{2,31}$`（含空串、非字符串、长度越界、含大写/非法字符等） |
| 400 | `{ "error": "密码长度需为 8~72 个字符" }` | password 按 UTF-8 字节数小于 8 或大于 72 |
| 409 | `{ "error": "用户名已存在" }` | 用户名已被注册（查询命中或插入时唯一约束冲突） |
| 429 | `{ "error": "请求过于频繁" }` | 同 IP 1 小时内注册请求超过 5 次（测试环境关闭限流） |

---

### `POST /api/auth/login`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/auth/login | 免认证 |

**请求参数（body，JSON）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | username | string | 是 | 注册时的用户名（须完全一致，区分大小写） |
| body | password | string | 是 | 注册时的密码 |

**成功响应**

状态码：200；响应头会下发 `Set-Cookie: kaoyan_session=...; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000`（`COOKIE_SECURE=1` 时附加 `Secure`）。

```json
{
  "id": 1,
  "username": "alice"
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 401 | `{ "error": "用户名或密码错误" }` | 用户名不存在，或密码校验失败（包括 password_hash 非法时的兜底） |
| 429 | `{ "error": "请求过于频繁" }` | 同一归一化用户名（trim + 小写）或同一 IP 在 15 分钟内登录尝试超过 10 次（测试环境关闭限流） |

---

### `POST /api/auth/logout`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/auth/logout | 免认证（携带 Cookie 时清除对应会话） |

**请求参数**

无（可携带 Cookie）。

**成功响应**

状态码：204，无响应体；响应头下发 `Set-Cookie: kaoyan_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0` 清除会话。

**错误码**

无。

---

### `GET /api/auth/me`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/auth/me | 需登录 |

**请求参数**

无。

**成功响应**

状态码：200

```json
{
  "id": 1,
  "username": "alice"
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 401 | `{ "error": "未登录" }` | 未携带 Cookie、会话不存在、会话已过期（过期时会清除会话 Cookie） |

---

## 2. 复习计划

### `GET /api/plans`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/plans | 需登录 |

**请求参数（query）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | date | string | 否 | 按日期过滤，YYYY-MM-DD |
| query | subject | string | 否 | 按科目过滤，取 math/english/politics/major 之一 |

**成功响应**

状态码：200，返回按 `date ASC, id ASC` 排序的计划数组。

```json
[
  {
    "id": 1,
    "date": "2025-01-01",
    "subject": "math",
    "title": "高数第一章",
    "plannedMinutes": 60,
    "done": false,
    "createdAt": "2025-01-01T00:00:00.000Z"
  }
]
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "date 格式非法，应为 YYYY-MM-DD" }` | 传入 date 但不是合法的 YYYY-MM-DD（含不存在的日期，如 2025-02-30） |
| 400 | `{ "error": "subject 非法" }` | 传入 subject 但不是 math/english/politics/major 之一 |

---

### `GET /api/plans/summary`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/plans/summary | 需登录 |

**请求参数（query）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | date | string | 否 | 统计日期，YYYY-MM-DD；缺省为今天 |

**成功响应**

状态码：200

```json
{
  "date": "2025-01-01",
  "total": 2,
  "done": 1,
  "completionRate": 0.5,
  "plans": [
    {
      "id": 1,
      "title": "高数第一章",
      "subject": "math",
      "plannedMinutes": 60,
      "actualMinutes": 45,
      "done": true
    }
  ]
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "date 格式非法，应为 YYYY-MM-DD" }` | 传入 date 但不是合法的 YYYY-MM-DD |

---

### `GET /api/plans/summary/by-subject`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/plans/summary/by-subject | 需登录 |

返回当前用户的计划分科汇总。可选查询参数 days：只统计最近 N 天（含今天，按计划 date 界定），N 按 1~31 钳制；不传时统计全部历史，非法 days 返回 400 错误体 { "error": "days 参数无效" }。

- 仅返回有计划的科目。
- 按 SUBJECTS 顺序排列：math、english、politics、major。
- 若无任何计划（空库），返回 `{ "subjects": [] }`。
- 每科字段：subject、total（计划条数）、done（已完成条数）、completionRate（done/total，保留四位小数）、plannedMinutes（计划分钟之和）、actualMinutes（关联专注分钟之和）。
- 实现用两路聚合（计划聚合与专注分钟聚合分开查再按科目合并），避免 JOIN 扇出导致条数与计划分钟被重复计算。

**成功响应示例：**

```json
{
  "subjects": [
    {
      "subject": "math",
      "total": 2,
      "done": 1,
      "completionRate": 0.5,
      "plannedMinutes": 150,
      "actualMinutes": 40
    },
    {
      "subject": "english",
      "total": 1,
      "done": 1,
      "completionRate": 1,
      "plannedMinutes": 30,
      "actualMinutes": 10
    }
  ]
}
```

### `GET /api/plans/export`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | `/api/plans/export` | 需要（登录用户） |

将学习计划导出为 CSV 文件下载，返回 `text/csv` 而非 JSON，响应头为 `Content-Type: text/csv; charset=utf-8` 与 `Content-Disposition: attachment; filename="kaoyan-plans.csv"`。要点：

- 可选 query 参数 `subject` 用于按科目过滤；非法时返回 400 `{ "error": "subject 非法" }`。
- CSV 表头固定为 `id,date,subject,subject_name,title,planned_minutes,done,created_at`。
- `done` 取值 `1` 或 `0`。
- 记录按 `date` 升序、`id` 升序排列。
- 文件名为 `kaoyan-plans.csv`；带 `subject` 参数时为 `kaoyan-plans-<subject>.csv`。
- 输出带 UTF-8 BOM，行以换行分隔、末尾追加换行；字段含双引号、逗号、回车或换行时用双引号包裹，内部双引号翻倍。

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| subject | query | string | 否 | 按科目过滤计划；非法时返回 400 |

#### 成功响应

状态码 200，返回 CSV 文件：

```csv
id,date,subject,subject_name,title,planned_minutes,done,created_at
1,2024-06-01,math,数学,数学新学1,60,1,2024-05-31 09:00:00
```

#### 错误码

| 状态码 | 响应体 | 说明 |
| --- | --- | --- |
| 400 | `{ "error": "subject 非法" }` | `subject` 参数非法 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `GET /api/plans/overdue`

| GET | /api/plans/overdue | 需登录 |

没参数。返回当天日期 date、逾期未完成总数 count、逾期计划数组 plans。逾期就是计划的 date 小于服务端今天且 done 为 false。plans 按 date 升序排，同一天内按 id 升序排。只返回当前登录用户自己的计划，别人的不碰。没登录返回 401。

```json
{
  "date": "2026-10-25",
  "count": 1,
  "plans": [
    {
      "id": 42,
      "date": "2026-10-20",
      "subject": "math",
      "title": "刷线代第三章习题",
      "plannedMinutes": 90,
      "done": false,
      "createdAt": "2026-10-19T08:30:00Z"
    }
  ]
}
```

### `POST /api/plans`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/plans | 需登录 |

**请求参数（body，JSON）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | title | string | 是 | 计划标题，trim 后不能为空 |
| body | subject | string | 是 | 取 math/english/politics/major 之一 |
| body | plannedMinutes | number | 是 | 计划时长，1~1440（含端点，须为有限数字） |
| body | date | string | 否 | YYYY-MM-DD；缺省为今天 |

**成功响应**

状态码：201

```json
{
  "id": 1,
  "date": "2025-01-01",
  "subject": "math",
  "title": "高数第一章",
  "plannedMinutes": 60,
  "done": false,
  "createdAt": "2025-01-01T00:00:00.000Z"
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "title 不能为空" }` | title 非字符串或 trim 后为空串 |
| 400 | `{ "error": "subject 非法" }` | subject 非字符串或不是 math/english/politics/major 之一 |
| 400 | `{ "error": "plannedMinutes 必须为 1~1440 的数字" }` | plannedMinutes 非数字、非有限数、小于 1 或大于 1440 |
| 400 | `{ "error": "date 格式非法，应为 YYYY-MM-DD" }` | date 显式传入但不是合法的 YYYY-MM-DD |

---

### `PATCH /api/plans/:id`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| PATCH | /api/plans/:id | 需登录 |

**请求参数（path）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | id | number | 是 | 计划 ID，正整数 |

**请求参数（body，JSON，所有字段可选，至少一个才有更新动作）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | date | string | 否 | YYYY-MM-DD |
| body | subject | string | 否 | 取 math/english/politics/major 之一 |
| body | title | string | 否 | trim 后不能为空 |
| body | plannedMinutes | number | 否 | 1~1440 的有限数字 |
| body | done | boolean | 否 | 是否已完成 |

**成功响应**

状态码：200

```json
{
  "id": 1,
  "date": "2025-01-01",
  "subject": "math",
  "title": "高数第一章",
  "plannedMinutes": 60,
  "done": true,
  "createdAt": "2025-01-01T00:00:00.000Z"
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "id 非法" }` | 路径参数 id 不是正整数（非整数、≤0 等） |
| 400 | `{ "error": "date 格式非法，应为 YYYY-MM-DD" }` | body.date 传入但不是合法的 YYYY-MM-DD |
| 400 | `{ "error": "subject 非法" }` | body.subject 传入但不是 math/english/politics/major 之一 |
| 400 | `{ "error": "title 不能为空" }` | body.title 传入但非字符串或 trim 后为空串 |
| 400 | `{ "error": "plannedMinutes 必须为 1~1440 的数字" }` | body.plannedMinutes 传入但非数字、非有限数、<1 或 >1440 |
| 400 | `{ "error": "done 必须为布尔值" }` | body.done 传入但不是布尔类型 |
| 404 | `{ "error": "计划不存在" }` | 计划不存在，或不属于当前登录用户 |

---

### `DELETE /api/plans/:id`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| DELETE | /api/plans/:id | 需登录 |

**请求参数（path）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | id | number | 是 | 计划 ID，正整数 |

**成功响应**

状态码：200

```json
{ "ok": true }
```

> 说明：删除计划不会级联删除专注记录，会把该用户下 `focus_sessions.plan_id` 中引用本计划的字段置为 NULL。

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "id 非法" }` | 路径参数 id 不是正整数（非整数、≤0 等） |
| 404 | `{ "error": "计划不存在" }` | 计划不存在，或不属于当前登录用户 |

---

### `GET /api/plans/auto-schedule/preview`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/plans/auto-schedule/preview | 需登录 |

**请求参数（query）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | subjects | string | 是 | 逗号分隔的科目列表，如 `math,english`，非空 |
| query | dailyMinutes | string | 是 | 单日可用分钟数，30~1440 的整数（query 传字符串，须匹配纯数字正则 /^-?\d+$/，60.0、0x3c、+60、带空格均非法） |
| query | examDate | string | 是 | 考试日期，YYYY-MM-DD |
| query | startDate | string | 否 | 起始日期，YYYY-MM-DD；缺省（undefined/null/空串）为今天 |

**成功响应**

状态码：200

```json
{
  "items": [
    {
      "date": "2025-01-01",
      "subject": "math",
      "title": "智能排期·数学 新学1",
      "plannedMinutes": 60,
      "kind": "new"
    },
    {
      "date": "2025-01-02",
      "subject": "math",
      "title": "智能排期·数学 复习1-1天",
      "plannedMinutes": 30,
      "kind": "review"
    }
  ]
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "subjects 不能为空" }` | subjects 非字符串、trim 后为空，或拆分去空后没有任何有效项 |
| 400 | `{ "error": "subject 非法" }` | subjects 中任一项不是 math/english/politics/major 之一 |
| 400 | `{ "error": "dailyMinutes 非法" }` | dailyMinutes 不是纯数字串，或解析后不是整数，或 <30，或 >1440 |
| 400 | `{ "error": "examDate 非法" }` | examDate 不是合法的 YYYY-MM-DD |
| 400 | `{ "error": "startDate 非法" }` | startDate 显式传入（非空）但不是合法的 YYYY-MM-DD |
| 400 | `{ "error": "examDate 不能早于 startDate" }` | examDate 早于 startDate |

---

### `POST /api/plans/auto-schedule`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/plans/auto-schedule | 需登录 |

**请求参数（body，JSON）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | subjects | string[] | 是 | 科目数组，长度≥1，每项取 math/english/politics/major 之一 |
| body | dailyMinutes | number | 是 | 单日可用分钟数，30~1440 的整数 |
| body | examDate | string | 是 | 考试日期，YYYY-MM-DD |
| body | startDate | string | 否 | 起始日期，YYYY-MM-DD；缺省（undefined/null/空串）为今天 |

**成功响应**

状态码：200

```json
{
  "created": 3,
  "skipped": 1,
  "discarded": 0,
  "items": [
    {
      "id": 10,
      "date": "2025-01-01",
      "subject": "math",
      "title": "智能排期·数学 新学1",
      "plannedMinutes": 60,
      "done": false,
      "createdAt": "2025-01-01T00:00:00.000Z"
    }
  ]
}
```

> 字段含义：`created` 本次实际新建计划数；`skipped` 因 `(user_id, date, subject, title)` 已存在而跳过的条数；`discarded` 排期算法因超出考试日或超限被丢弃的条数；`items` 本次新建的计划列表。

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "subjects 不能为空" }` | subjects 不是数组，或数组长度为 0 |
| 400 | `{ "error": "subject 非法" }` | subjects 数组中任一项不是 math/english/politics/major 之一 |
| 400 | `{ "error": "dailyMinutes 非法" }` | dailyMinutes 非数字、非整数，或 <30，或 >1440 |
| 400 | `{ "error": "examDate 非法" }` | examDate 不是合法的 YYYY-MM-DD |
| 400 | `{ "error": "startDate 非法" }` | startDate 显式传入（非 null/undefined/空串）但不是合法的 YYYY-MM-DD |
| 400 | `{ "error": "examDate 不能早于 startDate" }` | examDate 早于 startDate |

---

### `GET /api/plans/range`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/plans/range | 需登录 |

**请求参数（query）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | from | string | 是 | 起始日期（含），YYYY-MM-DD |
| query | to | string | 是 | 结束日期（含），YYYY-MM-DD；与 from 构成闭区间，区间跨度不得超过 62 天 |

**成功响应**

状态码：200，返回按 `date ASC, id ASC` 排序的计划数组。

```json
[
  {
    "id": 1,
    "date": "2025-01-01",
    "subject": "math",
    "title": "高数第一章",
    "plannedMinutes": 60,
    "done": false,
    "createdAt": "2025-01-01T00:00:00.000Z"
  }
]
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "from 格式非法，应为 YYYY-MM-DD" }` | from 缺失或不是合法的 YYYY-MM-DD |
| 400 | `{ "error": "to 格式非法，应为 YYYY-MM-DD" }` | to 缺失或不是合法的 YYYY-MM-DD |
| 400 | `{ "error": "区间不能超过 62 天" }` | to 早于 from，或 from 到 to 的跨度超过 62 天 |

---

### `GET /api/plans/overload`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/plans/overload | 需登录 |

**请求参数（query）**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | weekStart | string | 是 | 本周起始日（含），YYYY-MM-DD；服务端据此计算连续 7 天 |
| query | dailyMinutes | string | 是 | 单日阈值分钟数，30~1440 的整数（query 传字符串，须匹配纯数字正则 /^-?\d+$/） |

**成功响应**

状态码：200，返回本周 7 天负荷与超载日期列表。

```json
{
  "weekStart": "2025-01-06",
  "dailyMinutes": 240,
  "days": [
    { "date": "2025-01-06", "plannedMinutes": 180, "overloaded": false },
    { "date": "2025-01-07", "plannedMinutes": 300, "overloaded": true },
    { "date": "2025-01-08", "plannedMinutes": 0, "overloaded": false },
    { "date": "2025-01-09", "plannedMinutes": 0, "overloaded": false },
    { "date": "2025-01-10", "plannedMinutes": 0, "overloaded": false },
    { "date": "2025-01-11", "plannedMinutes": 0, "overloaded": false },
    { "date": "2025-01-12", "plannedMinutes": 0, "overloaded": false }
  ],
  "overloadedDays": ["2025-01-07"]
}
```

> 字段含义：`days` 为从 weekStart 起连续 7 天（含 weekStart），每天的 `plannedMinutes` 为该日计划总时长；`overloaded` 表示是否超过 `dailyMinutes`；`overloadedDays` 是超载日期的数组。

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "weekStart 格式非法，应为 YYYY-MM-DD" }` | weekStart 缺失或不是合法的 YYYY-MM-DD |
| 400 | `{ "error": "dailyMinutes 非法" }` | dailyMinutes 不是纯数字串，或解析后不是整数，或 <30，或 >1440 |

---

## 2.1 智能排期算法说明

智能排期按艾宾浩斯遗忘曲线安排复习：每一条新学内容在当天记为「新学」，之后在间隔 `[1, 3, 7, 15, 30]` 天（REVIEW_OFFSETS）各安排一次「复习」；同一科目每 2 天推进一课新学（每课 60 分钟），每条约 30 分钟的复习跟随其新学日期顺延。生成的条目先按日期排序（同日新学优先于复习），再逐条塞进每日时间预算：若某条计划时长已超过单日上限（dailyMinutes）则直接丢弃；否则从它原本的日期开始向后找第一个"当天已排分钟 + 本条 ≤ dailyMinutes"的日子落位，若顺延后已超过考试日（examDate）则丢弃。最终统计丢弃条数（discarded），已存在 `(user_id, date, subject, title)` 完全相同的计划会被跳过（skipped）。


## 3. 专注计时

### `GET /api/focus`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/focus | 需要（登录用户） |

按 started_at 降序返回当前用户的专注记录。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | limit | number | 否 | 返回条数上限，缺省 50；limit 必须为整数字符串（正则 /^-?\d+$/），非整数返回 400 错误体 { "error": "limit 参数无效" }；整数小于等于 0 时回落 50；整数大于 500 时钳制为 500。 |

**成功响应**

状态码 200

```json
[
  {
    "id": 1,
    "subject": "math",
    "minutes": 60,
    "startedAt": "2025-01-01T08:00:00.000Z",
    "note": null,
    "planId": null
  }
]
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "limit 参数无效" }` | limit 不是整数字符串 |
| 401 | （未认证响应） | 未登录或认证失败 |

### `POST /api/focus`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/focus | 需要（登录用户） |

新增一条专注记录。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | subject | SubjectKey | 是 | 必须是合法学科 key，否则返回 400 |
| body | minutes | number | 是 | 必须为整数且在 1~1440 之间 |
| body | startedAt | string | 否 | 提供时必须为字符串；trim 后需以 YYYY-MM-DD 开头、长度 10~40 且 Date.parse 可解析；未提供或为 null 时使用 nowIso() |
| body | note | string | 否 | 提供时必须为字符串且长度 <= 500；未提供或为 null 时存为 null |
| body | planId | number | 否 | 提供时必须为正整数，且为当前用户拥有的计划，否则 400 或 404；未提供时存为 null |

**成功响应**

状态码 201

```json
{
  "id": 1,
  "subject": "math",
  "minutes": 60,
  "startedAt": "2025-01-01T08:00:00.000Z",
  "note": null,
  "planId": null
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "invalid subject" }` | subject 不是合法学科 key |
| 400 | `{ "error": "minutes must be an integer between 1 and 1440" }` | minutes 非数字、非整数或不在 1~1440 |
| 400 | `{ "error": "startedAt must be a valid date string" }` | startedAt 提供时非字符串，或 trim 后不满足 YYYY-MM-DD 开头、长度 10~40、Date.parse 可解析 |
| 400 | `{ "error": "note must be a string up to 500 chars" }` | note 提供时非字符串或长度超过 500 |
| 400 | `{ "error": "planId 非法" }` | planId 提供时非正整数 |
| 404 | `{ "error": "计划不存在" }` | planId 提供但不存在或不属于当前用户 |
| 401 | （未认证响应） | 未登录或认证失败 |

### `GET /api/focus/stats`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/focus/stats | 需要（登录用户） |

返回专注统计。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | days | number | 否 | 统计天数，缺省 7；days 必须为 1~31 的整数字符串（正则 /^-?\d+$/），非整数或越界（小于 1 或大于 31）返回 400 错误体 { "error": "days 参数无效" }。 |

**成功响应**

状态码 200

```json
{
  "days": [
    { "date": "2025-01-01", "minutes": 60 },
    { "date": "2025-01-02", "minutes": 0 }
  ],
  "todayMinutes": 0,
  "weekMinutes": 60,
  "totalMinutes": 120
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "days 参数无效" }` | days 不是整数字符串 |
| 401 | （未认证响应） | 未登录或认证失败 |

### `GET /api/focus/summary/by-subject`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/focus/summary/by-subject | 需要（登录用户） |

按科目返回专注时长汇总：仅返回有专注记录的科目，按数学、英语、政治、专业课 821 的顺序排列。可选查询参数 `days`：只统计最近 N 天（含今天），N 按 1~31 钳制；不传时统计全部历史，非法 days 返回 400 错误体 { "error": "days 参数无效" }。

**成功响应**

状态码 200

```json
{
  "subjects": [
    { "subject": "math", "sessions": 3, "totalMinutes": 125 },
    { "subject": "english", "sessions": 2, "totalMinutes": 45 }
  ]
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "days 参数无效" }` | days 不是整数字符串 |
| 401 | （未认证响应） | 未登录或认证失败 |

### `GET /api/focus/export`

导出专注计时记录为 CSV 文本。

| 项目 | 说明 |
| --- | --- |
| 方法 | `GET` |
| 路径 | `/api/focus/export` |
| 认证 | 需要登录 |

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| subject | string | 否 | 按科目筛选，须为合法 SubjectKey（`math` / `english` / `politics` / `major`）；非法值返回 `400 { error: 'subject 非法' }` |

**成功响应**

返回 CSV 文本，表头依次为 `id,subject,subject_name,minutes,started_at,note,plan_id`，按 `started_at` 升序、`id` 升序排列。`subject_name` 为科目中文名；`note` 或 `plan_id` 为空时输出空串。

导出口径与其他导出一致：UTF-8 BOM、RFC 4180 转义、`Content-Type: text/csv; charset=utf-8`、`Content-Disposition` 附件下载；无筛选时文件名为 `kaoyan-focus.csv`，有筛选时为 `kaoyan-focus-<subject>.csv`。

**错误码**

| 状态码 | 说明 |
| --- | --- |
| 400 | `subject 非法` |
| 401 | 未登录 |

## 4. 错题本

### `GET /api/mistakes/summary`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/mistakes/summary | 需要（登录用户） |

返回错题掌握率，可选 subject 过滤。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | subject | string | 否 | 合法学科 key，用于过滤；提供非法值时返回 400 |

**成功响应**

状态码 200

```json
{
  "subject": null,
  "total": 10,
  "mastered": 4,
  "unmastered": 6,
  "masteredRate": 0.4
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "无效的 subject 参数" }` | subject 提供但不是合法学科 key |
| 401 | （未认证响应） | 未登录或认证失败 |

### `GET /api/mistakes/summary/by-subject`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/mistakes/summary/by-subject | 需要（登录用户） |

按科目返回错题掌握率汇总：仅返回有错题的科目，按数学、英语、政治、专业课 821 的顺序排列；掌握率与单科汇总用同一舍入口径（4 位小数）。

本接口无请求参数。

**成功响应**

状态码 200

```json
{
  "subjects": [
    {
      "subject": "math",
      "total": 3,
      "mastered": 1,
      "unmastered": 2,
      "masteredRate": 0.3333
    },
    {
      "subject": "english",
      "total": 2,
      "mastered": 2,
      "unmastered": 0,
      "masteredRate": 1
    }
  ]
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 401 | （未认证响应） | 未登录或认证失败 |

### `GET /api/mistakes/export`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | `/api/mistakes/export` | 需要（登录用户） |

将错题记录导出为 CSV 文件下载，返回 `text/csv` 而非 JSON，响应头为 `Content-Type: text/csv; charset=utf-8` 与 `Content-Disposition: attachment; filename="kaoyan-mistakes.csv"`。要点：

- 可选 query 参数 `subject` 用于按科目过滤；非法时返回 400 `{ "error": "无效的 subject" }`。
- CSV 表头固定为 `id,subject,subject_name,title,content,analysis,mastered,created_at`。
- `mastered` 取值 `1` 或 `0`。
- 记录按 `created_at` 升序、`id` 升序排列。
- 文件名为 `kaoyan-mistakes.csv`；带 `subject` 参数时为 `kaoyan-mistakes-<subject>.csv`。
- 输出带 UTF-8 BOM，行以换行分隔、末尾追加换行；字段含双引号、逗号、回车或换行时用双引号包裹，内部双引号翻倍。

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| subject | query | string | 否 | 按科目过滤错题；非法时返回 400 |

#### 成功响应

状态码 200，返回 CSV 文件：

```csv
id,subject,subject_name,title,content,analysis,mastered,created_at
1,math,数学,二元一次方程,解题步骤,先移项,1,2024-06-01 08:00:00
```

#### 错误码

| 状态码 | 响应体 | 说明 |
| --- | --- | --- |
| 400 | `{ "error": "无效的 subject" }` | `subject` 参数非法 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `GET /api/mistakes`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/mistakes | 需要（登录用户） |

返回当前用户错题列表，按 id 降序。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | subject | string | 否 | 合法学科 key；空字符串忽略；非法值返回 400 |
| query | mastered | string | 否 | 必须为 "0" 或 "1"；空字符串忽略；其他值返回 400 |
| query | q | string | 否 | 关键词，对 title 与 content 做 LIKE 匹配；空字符串忽略 |

**成功响应**

状态码 200

```json
[
  {
    "id": 1,
    "subject": "math",
    "title": "极限计算",
    "content": "...",
    "analysis": "...",
    "mastered": false,
    "createdAt": "2025-01-01T08:00:00.000Z"
  }
]
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "无效的 subject" }` | subject 提供且非空但不是合法学科 key |
| 400 | `{ "error": "mastered 必须为 0 或 1" }` | mastered 提供且非空但不等于 "0" 或 "1" |
| 401 | （未认证响应） | 未登录或认证失败 |

### `POST /api/mistakes`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/mistakes | 需要（登录用户） |

创建一条错题。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | subject | SubjectKey | 是 | 必须为合法学科 key |
| body | title | string | 是 | trim 后不能为空 |
| body | content | string | 否 | 非字符串时按空字符串 '' 处理 |
| body | analysis | string | 否 | 非字符串时按空字符串 '' 处理 |

**成功响应**

状态码 201

```json
{
  "id": 1,
  "subject": "math",
  "title": "极限计算",
  "content": "",
  "analysis": "",
  "mastered": false,
  "createdAt": "2025-01-01T08:00:00.000Z"
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "请求体无效" }` | body 缺失或非对象 |
| 400 | `{ "error": "subject 非法" }` | subject 不是合法学科 key |
| 400 | `{ "error": "title 不能为空" }` | title 非字符串或 trim 后为空 |
| 401 | （未认证响应） | 未登录或认证失败 |

### `PATCH /api/mistakes/:id`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| PATCH | /api/mistakes/:id | 需要（登录用户） |

逐字段可选更新错题。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | id | number | 是 | 必须为正整数 |
| body | subject | SubjectKey | 否 | 提供时必须为合法学科 key |
| body | title | string | 否 | 提供时 trim 后不能为空 |
| body | content | string | 否 | 提供时必须为字符串 |
| body | analysis | string | 否 | 提供时必须为字符串 |
| body | mastered | boolean | 否 | 提供时必须为布尔值 |

**成功响应**

状态码 200

```json
{
  "id": 1,
  "subject": "math",
  "title": "极限计算",
  "content": "",
  "analysis": "",
  "mastered": true,
  "createdAt": "2025-01-01T08:00:00.000Z"
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "id 非法" }` | id 非正整数 |
| 404 | `{ "error": "错题不存在" }` | 错题不存在或不属于当前用户 |
| 400 | `{ "error": "请求体无效" }` | body 缺失或非对象 |
| 400 | `{ "error": "subject 非法" }` | subject 提供但不是合法学科 key |
| 400 | `{ "error": "title 不能为空" }` | title 提供但非字符串或 trim 后为空 |
| 400 | `{ "error": "content 非法" }` | content 提供但非字符串 |
| 400 | `{ "error": "analysis 非法" }` | analysis 提供但非字符串 |
| 400 | `{ "error": "mastered 非法" }` | mastered 提供但非布尔值 |
| 401 | （未认证响应） | 未登录或认证失败 |

### `DELETE /api/mistakes/:id`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| DELETE | /api/mistakes/:id | 需要（登录用户） |

删除一条错题。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | id | number | 是 | 必须为正整数 |

**成功响应**

状态码 200

```json
{ "ok": true }
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "id 非法" }` | id 非正整数 |
| 404 | `{ "error": "错题不存在" }` | 错题不存在或不属于当前用户 |
| 401 | （未认证响应） | 未登录或认证失败 |

### `GET /api/mistakes/:id/source-exams`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/mistakes/:id/source-exams | 需要（登录用户） |

返回与该错题同科目、且在时间窗口内的考试记录，按 taken_at 降序、id 降序。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | id | number | 是 | 必须为正整数 |
| query | windowDays | number | 否 | 时间窗口天数，缺省 7；提供时必须为 0~90 的整数（纯数字整数串，正则校验，1.0、0x2、+7、带空格、空串均 400） |

**成功响应**

状态码 200

```json
[
  {
    "id": 1,
    "subject": "math",
    "paper": "2025 模拟一",
    "score": 120,
    "totalScore": 150,
    "durationMinutes": 180,
    "takenAt": "2025-01-01"
  }
]
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "id 非法" }` | id 非正整数 |
| 400 | `{ "error": "windowDays 非法" }` | windowDays 提供时非整数或不在 0~90 |
| 404 | `{ "error": "错题不存在" }` | 错题不存在或不属于当前用户 |
| 401 | （未认证响应） | 未登录或认证失败 |

### `POST /api/mistakes/quiz/generate`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/mistakes/quiz/generate | 需要（登录用户） |

按条件组卷。unmasteredOnly 缺省 true 时只组未掌握错题；limit 缺省 20，取值 1~100；返回题目不含 analysis。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | subject | SubjectKey | 否 | 按学科过滤 |
| body | unmasteredOnly | boolean | 否 | 缺省 true；为 true 时仅组未掌握错题 |
| body | limit | number | 否 | 缺省 20；取值 1~100 |

**成功响应**

状态码 200

```json
{
  "items": [
    {
      "id": 1,
      "subject": "math",
      "title": "极限计算",
      "content": "...",
      "mastered": false,
      "createdAt": "2025-01-01T08:00:00.000Z"
    }
  ]
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | （参数校验错误返回体） | subject、unmasteredOnly 或 limit 不合法 |
| 401 | （未认证响应） | 未登录或认证失败 |

### `POST /api/mistakes/quiz/grade`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/mistakes/quiz/grade | 需要（登录用户） |

提交组卷结果并回写掌握状态：correct=true 置为已掌握，correct=false 打回未掌握。updatedIds 为实际发生变化的 id。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | answers | array | 是 | 每项含 id 与 correct |

**成功响应**

状态码 200

```json
{
  "updatedIds": [1, 2]
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | （参数校验错误返回体） | answers 不合法 |
| 401 | （未认证响应） | 未登录或认证失败 |


## 5. 单词 SRS

单词接口用于管理用户词库与 SRS（间隔重复）复习状态。所有接口均需登录认证，且仅作用于当前登录用户的数据。

### `GET /api/words`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/words | 需要（登录用户） |

返回当前用户的全部单词（含 SRS 状态），按 `id` 升序排列。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| - | - | - | - | 无参数 |

**成功响应**

状态码：`200`

```json
[
  {
    "id": 1,
    "word": "abandon",
    "phonetic": "/əˈbændən/",
    "meaning": "v. 放弃；抛弃",
    "example": "He abandoned his car. ｜ 他弃车而去。",
    "source": "core500",
    "memory_tip": "a-band-on：一个乐队解散了，放弃",
    "state": {
      "wordId": 1,
      "ease": 2.5,
      "intervalDays": 0,
      "repetitions": 0,
      "dueDate": "2025-01-01"
    }
  }
]
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `GET /api/words/summary/by-source`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/words/summary/by-source | 需要（登录用户） |

按来源返回单词汇总：每项含 source、total（该来源单词总数）、due（有 SRS 状态且 due_date <= 今天的单词数）、notStarted（无 SRS 状态的单词数）；仅返回有单词的来源，按内置、核心500词库、手动录入、CSV导入的顺序排列。

本接口无请求参数。

### `GET /api/words/export`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | `/api/words/export` | 需要（登录用户） |

将单词导出为 CSV 文件下载，返回 `text/csv` 而非 JSON，响应头为 `Content-Type: text/csv; charset=utf-8` 与 `Content-Disposition: attachment; filename="kaoyan-words.csv"`。要点：

- 可选 query 参数 `source` 用于按来源过滤，取值为 `builtin`、`core500`、`manual`、`csv`；非法时返回 400 `{ "error": "无效的 source 参数" }`。
- CSV 表头固定为 `id,word,phonetic,meaning,example,source,source_name,memory_tip,repetitions,due_date`。
- `source_name` 取 `WORD_SOURCES` 中对应来源的中文名。
- 无 SRS 时 `repetitions` 与 `due_date` 为空。
- 记录按 `id` 升序排列。
- 文件名为 `kaoyan-words.csv`；带 `source` 参数时为 `kaoyan-words-<source>.csv`。
- 输出带 UTF-8 BOM，行以换行分隔、末尾追加换行；字段含双引号、逗号、回车或换行时用双引号包裹，内部双引号翻倍。

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| source | query | string | 否 | 按来源过滤，取值 `builtin`、`core500`、`manual`、`csv`；非法时返回 400 |

#### 成功响应

状态码 200，返回 CSV 文件：

```csv
id,word,phonetic,meaning,example,source,source_name,memory_tip,repetitions,due_date
1,abandon,əˈbændən,放弃,Don't abandon hope.,manual,手动录入,,3,2024-06-10
```

#### 错误码

| 状态码 | 响应体 | 说明 |
| --- | --- | --- |
| 400 | `{ "error": "无效的 source 参数" }` | `source` 参数非法 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `GET /api/words/due`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/words/due | 需要（登录用户） |

返回今天到期的单词（`srs_state.due_date <= 今天`），按 `due_date` 升序、`id` 升序排列。仅返回存在 SRS 状态的单词。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| - | - | - | - | 无参数 |

**成功响应**

状态码：`200`

```json
[
  {
    "id": 1,
    "word": "abandon",
    "phonetic": "/əˈbændən/",
    "meaning": "v. 放弃；抛弃",
    "example": "He abandoned his car. ｜ 他弃车而去。",
    "source": "core500",
    "memory_tip": "a-band-on：一个乐队解散了，放弃",
    "state": {
      "wordId": 1,
      "ease": 2.5,
      "intervalDays": 1,
      "repetitions": 1,
      "dueDate": "2025-01-01"
    }
  }
]
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `POST /api/words`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/words | 需要（登录用户） |

创建单词并初始化 SRS 状态（ease=2.5，interval_days=0，repetitions=0，due_date=今天）。新词来源标记为 `manual`。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | word | string | 是 | 单词，去除首尾空白后不能为空 |
| body | meaning | string | 是 | 释义，去除首尾空白后不能为空 |
| body | phonetic | string | 否 | 音标，缺省为空字符串 |
| body | example | string | 否 | 例句，缺省为空字符串 |

**成功响应**

状态码：`201`

```json
{
  "id": 2,
  "word": "benefit",
  "phonetic": "",
  "meaning": "n. 利益",
  "example": "",
  "source": "manual",
  "memory_tip": "",
  "state": {
    "wordId": 2,
    "ease": 2.5,
    "intervalDays": 0,
    "repetitions": 0,
    "dueDate": "2025-01-01"
  }
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "word 不能为空" }` | `word` 缺失、非字符串或去除空白后为空 |
| 400 | `{ "error": "meaning 不能为空" }` | `meaning` 缺失、非字符串或去除空白后为空 |
| 409 | `{ "error": "单词已存在" }` | 当前用户已存在同名单词 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `POST /api/words/:id/review`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/words/:id/review | 需要（登录用户） |

按 SM-2 简化规则更新单词的 SRS 状态并返回更新后的单词。

**grade 语义**

| grade | 含义 | 处理规则 |
| --- | --- | --- |
| 0 | 忘记 | repetitions 重置为 0；intervalDays 设为 1；ease = max(1.3, ease - 0.2) |
| 1 | 模糊 | intervalDays = repetitions 为 0 时取 1，否则 max(1, round(intervalDays * 1.2))；repetitions 加 1；ease = max(1.3, ease - 0.05) |
| 2 | 记住 | repetitions 为 0 时 intervalDays = 1；为 1 时 intervalDays = 3；否则 intervalDays = round(intervalDays * ease)；repetitions 加 1；ease = min(2.5, ease + 0.05) |

更新后 `due_date = 今天 + intervalDays`。若该词尚无 SRS 状态则按默认 ease=2.5、intervalDays=0、repetitions=0 初始化后再计算。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | id | number | 是 | 单词 id，必须为正整数 |
| body | grade | number | 是 | 复习评分，必须为 0、1 或 2 |

**成功响应**

状态码：`200`

```json
{
  "id": 1,
  "word": "abandon",
  "phonetic": "/əˈbændən/",
  "meaning": "v. 放弃；抛弃",
  "example": "He abandoned his car. ｜ 他弃车而去。",
  "source": "core500",
  "memory_tip": "a-band-on：一个乐队解散了，放弃",
  "state": {
    "wordId": 1,
    "ease": 2.55,
    "intervalDays": 1,
    "repetitions": 1,
    "dueDate": "2025-01-02"
  }
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "id 无效" }` | `id` 不是正整数 |
| 400 | `{ "error": "grade 必须为 0|1|2" }` | `grade` 不是 0、1 或 2 |
| 404 | `{ "error": "单词不存在" }` | 当前用户下不存在该 id 的单词 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `POST /api/words/import`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/words/import | 需要（登录用户） |

批量导入词库。请求体大小上限为 5 MB（bodyLimit = 5 * 1024 * 1024）。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | words | array | 是 | 导入项数组，长度必须为 1..2000 |
| body | source | string | 否 | 词源，必须为 `WORD_SOURCES` 的键之一；缺省或为 null 时取 `core500` |

每个导入项字段：

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| words[i] | word | string | 是 | 单词，去除空白后不能为空 |
| words[i] | meanings_zh | string[] | 是 | 非空数组，且每项去除空白后不能为空 |
| words[i] | pos | string | 否 | 词性，去除空白后拼接在释义前 |
| words[i] | phonetic | string | 否 | 音标 |
| words[i] | example_en | string | 否 | 英文例句 |
| words[i] | example_zh | string | 否 | 中文例句，与英文例句以 ` ｜ ` 拼接 |

**成功响应**

状态码：`200`

```json
{
  "imported": 2,
  "skippedExisting": 1,
  "skippedInvalid": 1,
  "errors": [
    { "index": 3, "message": "meanings_zh 必须为非空数组" }
  ]
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "words 必须为 1..2000 的数组" }` | body 为 null 或非对象；或 `words` 不是数组、长度小于 1 或大于 2000 |
| 400 | `{ "error": "source 无效" }` | `source` 提供了值但不是字符串，或不是 `WORD_SOURCES` 的键之一 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

**逐条跳过规则（不计入错误码，体现在响应的 `errors` 与计数中，errors 最多记录 50 条）**

| 触发条件 | 计数 | errors.message |
| --- | --- | --- |
| 条目为 null 或非对象 | skippedInvalid +1 | 条目必须为对象 |
| `word` 非字符串或去除空白后为空 | skippedInvalid +1 | word 不能为空 |
| `meanings_zh` 不是数组或为空数组 | skippedInvalid +1 | meanings_zh 必须为非空数组 |
| `meanings_zh` 存在空项 | skippedInvalid +1 | meanings_zh 每项必须为非空字符串 |
| 同一请求内 word 重复 | skippedExisting +1 | - |
| 当前用户已存在同名单词 | skippedExisting +1 | - |

### `POST /api/words/seed-vocab`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/words/seed-vocab | 需要（登录用户） |

播种内置词库（`vocab-500-a.json`、`vocab-500-b.json`、`vocab-500-c.json`、`vocab-500-d.json`、`words-05.json`、`words-06.json`、`words-500.json`）。导入词源固定为 `core500`，新词 SRS 初始化为 ease=2.5、interval_days=0、repetitions=0、due_date=今天。

**幂等说明**：按当前用户 + word 去重。已存在的同名单词会被跳过并计入 `skippedExisting`，不会重复插入，因此重复调用不会产生重复数据。整批写入在单个事务中执行，失败时回滚。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| - | - | - | - | 无参数 |

**成功响应**

状态码：`200`

```json
{
  "imported": 1000,
  "skippedExisting": 0,
  "skippedInvalid": 0,
  "errors": []
}
```

`errors` 为校验失败条目明细，每项结构为 `{ "file": "vocab-500-a.json", "index": 0, "message": "..." }`。

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `GET /api/words/vocab-status`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/words/vocab-status | 需要（登录用户） |

返回当前用户内置 500 词库（`source = 'core500'`）的统计。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| - | - | - | - | 无参数 |

**成功响应**

状态码：`200`

```json
{
  "total": 1000,
  "mastered": 120,
  "pending": 880
}
```

`mastered` 为 `srs_state.repetitions > 0` 的词数；`pending = total - mastered`。

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `DELETE /api/words/:id`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| DELETE | /api/words/:id | 需要（登录用户） |

删除指定单词及其 SRS 状态。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | id | number | 是 | 单词 id，必须为正整数 |

**成功响应**

状态码：`200`

```json
{ "ok": true }
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "id 无效" }` | `id` 不是正整数 |
| 404 | `{ "error": "单词不存在" }` | 当前用户下不存在该 id 的单词 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

## 6. 真题统计

真题接口用于管理考试记录并提供趋势、汇总、CSV 导出与相关错题查询。所有接口均需登录认证，且仅作用于当前登录用户的数据。可选查询参数 `subject` 必须为合法科目键，否则返回 400。

### `GET /api/exams`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/exams | 需要（登录用户） |

返回当前用户的考试记录，按 `taken_at` 降序、`id` 降序排列。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | subject | string | 否 | 科目键，提供时必须为合法科目，否则返回 400 |

**成功响应**

状态码：`200`

```json
[
  {
    "id": 1,
    "subject": "math",
    "paper": "2023 真题",
    "score": 120,
    "totalScore": 150,
    "durationMinutes": 180,
    "takenAt": "2025-01-01"
  }
]
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "无效的 subject 参数" }` | 提供了 `subject` 但不是合法科目键 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `GET /api/exams/trend`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/exams/trend | 需要（登录用户） |

返回趋势点，按 `taken_at` 升序、`id` 升序排列。每点包含 `rate = round(score / totalScore * 10000) / 10000`，当 `totalScore <= 0` 时 `rate` 为 0。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | subject | string | 否 | 科目键，提供时必须为合法科目，否则返回 400 |

**成功响应**

状态码：`200`

```json
[
  {
    "takenAt": "2025-01-01",
    "paper": "2023 真题",
    "score": 120,
    "totalScore": 150,
    "rate": 0.8
  }
]
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "无效的 subject 参数" }` | 提供了 `subject` 但不是合法科目键 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `GET /api/exams/summary`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/exams/summary | 需要（登录用户） |

返回真题汇总统计。`avgScore` 为算术平均分（保留一位小数）；`avgRate` 为加权得分率（总分之和 / 满分之和，保留四位小数），与单场 `rate` 含义不同。`bestScore` 并列时取最早一场；`first` 取 `taken_at` 最早（并列取 `id` 最小）；`latest` 取 `taken_at` 最晚（并列取 `id` 最大）；`improvement` 在记录数小于 2 时为 0，否则为 `latest.score - first.score`。无记录时返回全零对象。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | subject | string | 否 | 科目键，提供时必须为合法科目，否则返回 400 |

**成功响应**

状态码：`200`

```json
{
  "subject": "math",
  "count": 2,
  "avgScore": 115,
  "avgRate": 0.7667,
  "bestScore": 120,
  "bestTakenAt": "2025-01-01",
  "latestScore": 110,
  "latestTakenAt": "2025-02-01",
  "firstScore": 120,
  "firstTakenAt": "2025-01-01",
  "improvement": -10
}
```

无记录时：

```json
{
  "subject": null,
  "count": 0,
  "avgScore": 0,
  "avgRate": 0,
  "bestScore": 0,
  "bestTakenAt": "",
  "latestScore": 0,
  "latestTakenAt": "",
  "firstScore": 0,
  "firstTakenAt": "",
  "improvement": 0
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "无效的 subject 参数" }` | 提供了 `subject` 但不是合法科目键 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `GET /api/exams/summary/by-subject`

| 方法 | 路径 | 认证 |
|------|------|------|
| GET | /api/exams/summary/by-subject | 需要登录用户 |

返回当前用户的真题分科汇总。

- 仅返回有记录的科目。
- 按 SUBJECTS 顺序排列：math、english、politics、major。
- 若无任何记录（空库），返回 `{ "subjects": [] }`。
- 计算口径与 `GET /api/exams/summary` 同款：avgScore 保留一位小数；avgRate 为总分之和 / 满分之和保留四位小数；best 并列取最早；first 取 taken_at 最早（并列 id 最小）；latest 取 taken_at 最晚（并列 id 最大）；improvement 在场次小于 2 时为 0，否则为 latest.score - first.score。
- 可选查询参数 days：只统计最近 N 天（含今天，按 taken_at 日期界定），N 按 1~31 钳制；不传时统计全部历史，非法 days 返回 400 错误体 { "error": "days 参数无效" }（与 GET /api/plans/summary/by-subject 的 days 口径一致）。

**成功响应示例：**

```json
{
  "subjects": [
    {
      "subject": "math",
      "count": 3,
      "avgScore": 88.3,
      "avgRate": 0.5889,
      "bestScore": 95,
      "bestTakenAt": "2026-02-01T00:00:00Z",
      "latestScore": 90,
      "latestTakenAt": "2026-03-01T00:00:00Z",
      "firstScore": 80,
      "firstTakenAt": "2026-01-01T00:00:00Z",
      "improvement": 10
    },
    {
      "subject": "english",
      "count": 1,
      "avgScore": 70,
      "avgRate": 0.7,
      "bestScore": 70,
      "bestTakenAt": "2026-04-01T00:00:00Z",
      "latestScore": 70,
      "latestTakenAt": "2026-04-01T00:00:00Z",
      "firstScore": 70,
      "firstTakenAt": "2026-04-01T00:00:00Z",
      "improvement": 0
    }
  ]
}
```

**错误码：**

- `401`：未登录。

### `GET /api/exams/export`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/exams/export | 需要（登录用户） |

导出考试记录为 CSV。**返回 `text/csv` 而非 JSON**。

- 响应头 `Content-Type: text/csv; charset=utf-8`
- 响应头 `Content-Disposition: attachment; filename="kaoyan-exams.csv"`；当提供 `subject` 时文件名为 `kaoyan-exams-<subject>.csv`
- 输出带 UTF-8 BOM（`\ufeff`），行以 `\n` 分隔，末尾追加换行
- 表头列为：`id,subject,subject_name,paper,score,total_score,rate,duration_minutes,taken_at`
- `rate = round(score / totalScore * 10000) / 10000`，当 `totalScore <= 0` 时为 0
- `subject_name` 取科目名称，未匹配到时回退为科目键
- 字段包含 `"`、`,`、`\r`、`\n` 时用双引号包裹，内部 `"` 转义为 `""`
- 数据按 `taken_at` 升序、`id` 升序排列

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| query | subject | string | 否 | 科目键，提供时必须为合法科目，否则返回 400 |

**成功响应**

状态码：`200`

```
id,subject,subject_name,paper,score,total_score,rate,duration_minutes,taken_at
1,math,数学,2023 真题,120,150,0.8,180,2025-01-01
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "无效的 subject 参数" }` | 提供了 `subject` 但不是合法科目键 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `POST /api/exams`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/exams | 需要（登录用户） |

创建考试记录。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| body | subject | string | 是 | 必须为合法科目键 |
| body | paper | string | 是 | 试卷名，去除空白后不能为空 |
| body | score | number | 是 | 得分，必须为有限数且位于 0 到 `totalScore` 之间 |
| body | totalScore | number | 是 | 满分，必须为有限数且大于 0 |
| body | durationMinutes | number | 否 | 时长（分钟），必须为有限数且大于等于 0，落库时向下取整；缺省或为 null 时为 0 |
| body | takenAt | string | 否 | 考试日期，去除空白后不能为空；缺省或为 null 时为今天 |

**成功响应**

状态码：`201`

```json
{
  "id": 1,
  "subject": "math",
  "paper": "2023 真题",
  "score": 120,
  "totalScore": 150,
  "durationMinutes": 180,
  "takenAt": "2025-01-01"
}
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "请求体不能为空" }` | body 缺失、为 null 或非对象 |
| 400 | `{ "error": "无效的 subject" }` | `subject` 不是合法科目键 |
| 400 | `{ "error": "paper 不能为空" }` | `paper` 非字符串或去除空白后为空 |
| 400 | `{ "error": "totalScore 必须大于 0" }` | `totalScore` 非数字、非有限数或小于等于 0 |
| 400 | `{ "error": "score 必须在 0 到 totalScore 之间" }` | `score` 非数字、非有限数、小于 0 或大于 `totalScore` |
| 400 | `{ "error": "durationMinutes 必须大于等于 0" }` | `durationMinutes` 提供了值但非数字、非有限数或小于 0 |
| 400 | `{ "error": "takenAt 无效" }` | `takenAt` 提供了值但非字符串或去除空白后为空 |
| 500 | `{ "error": "创建失败" }` | 插入后按 id 回查不到记录 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `DELETE /api/exams/:id`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| DELETE | /api/exams/:id | 需要（登录用户） |

删除指定考试记录。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | id | number | 是 | 考试记录 id，必须为正整数 |

**成功响应**

状态码：`200`

```json
{ "ok": true }
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "无效的 id" }` | `id` 不是正整数 |
| 404 | `{ "error": "记录不存在" }` | 当前用户下不存在该 id 的考试记录 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |

### `GET /api/exams/:id/related-mistakes`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/exams/:id/related-mistakes | 需要（登录用户） |

返回与该考试记录在时间窗口内相关的错题。以考试 `taken_at` 为基准日，选取同科目错题中 `created_at` 与基准日相差天数不超过 `windowDays` 的记录，按 `created_at` 降序、`id` 降序返回。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | id | number | 是 | 考试记录 id，必须为正整数 |
| query | windowDays | string | 否 | 时间窗口天数，解析为整数后必须位于 0..90；缺省为 7（纯数字整数串，正则校验，1.0、0x2、+7、带空格、空串均 400） |

**成功响应**

状态码：`200`

```json
[
  {
    "id": 1,
    "subject": "math",
    "title": "极限计算",
    "content": "求 lim ...",
    "analysis": "使用洛必达法则",
    "mastered": false,
    "createdAt": "2025-01-02 10:00:00"
  }
]
```

**错误码**

| 状态码 | 返回体 | 触发条件 |
| --- | --- | --- |
| 400 | `{ "error": "无效的 id" }` | `id` 不是正整数 |
| 400 | `{ "error": "windowDays 非法" }` | `windowDays` 提供了值但不是 0..90 的整数 |
| 404 | `{ "error": "记录不存在" }` | 当前用户下不存在该 id 的考试记录 |
| 400 | `{ "error": "takenAt 非法" }` | 该考试记录的 `taken_at` 不匹配 `YYYY-MM-DD` 格式 |
| 401 | `{ "error": "Unauthorized" }` | 未登录（由全局认证钩子返回） |


## 7. 统计

### `GET /api/stats/weekly`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/stats/weekly | 需要（Bearer Token） |

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| Query | start | string | 否 | 周起始日 `YYYY-MM-DD`；缺省为本周一（周一为每周第一天）；不存在的日历日期（如 2024-02-30）返回 400 start 日期无效 |

**成功响应**

状态码：200

```json
{
  "weekStart": "2025-01-06",
  "weekEnd": "2025-01-13",
  "focusMinutes": 320,
  "focusBySubject": { "math": 120, "english": 80, "politics": 60, "major": 60 },
  "focusMinutesByDay": [60, 0, 90, 0, 80, 0, 90],
  "currentStreak": 4,
  "plansTotal": 12,
  "plansDone": 7,
  "wordsTotal": 500,
  "wordsLearned": 210,
  "wordsDue": 35,
  "mistakesNew": 6,
  "mistakesUnmastered": 18,
  "examsTaken": 2
}
```

**错误码**

| 状态码 | 返回体 | 含义 | 触发条件 |
| --- | --- | --- | --- |
| 400 | `{ "error": "start 日期格式无效" }` | start 不符合 `YYYY-MM-DD` | Query start 存在但不匹配 `^\d{4}-\d{2}-\d{2}$` |
| 400 | `{ "error": "start 日期无效" }` | start 是无效日期 | start 匹配格式但 `new Date(start + 'T00:00:00')` 为 NaN |

### `GET /api/stats/heatmap`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/stats/heatmap | 需要（Bearer Token） |

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| Query | months | string | 否 | 回溯月数，纯数字整数 1..6，缺省 3；每月按 31 天计；非纯数字串（`1.0`、`0x2` 等）返回 400 |

**成功响应**

状态码：200

```json
{
  "months": 3,
  "startDate": "2024-10-08",
  "endDate": "2025-01-06",
  "days": [
    {
      "date": "2024-10-08",
      "focusMinutes": 60,
      "plansTotal": 3,
      "plansDone": 2,
      "mistakesNew": 1,
      "examsTaken": 0
    }
  ],
  "currentStreak": 4,
  "bestStreak": 12,
  "activeDays": 40
}
```

**错误码**

| 状态码 | 返回体 | 含义 | 触发条件 |
| --- | --- | --- | --- |
| 400 | `{ "error": "months 参数无效" }` | months 非 1..6 的整数 | Query months 存在但不匹配 `/^-?\d+$/` 或 n<1 或 n>6 |

## 8. 备份与导入

### `GET /api/backup/export`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/backup/export | 需要（Bearer Token） |

**请求参数**

无。

**成功响应**

状态码：200。导出当前用户全部数据，各行均移除 `user_id` 字段。

```json
{
  "format": "kaoyan-backup",
  "version": 1,
  "exportedAt": "2025-01-06T12:00:00.000Z",
  "tables": {
    "plans": [],
    "focus_sessions": [],
    "mistakes": [],
    "words": [],
    "srs_state": [],
    "exam_records": [],
    "settings": []
  }
}
```

**错误码**

无接口级非 2xx 分支（认证失败由全局鉴权中间件处理）。

### `POST /api/backup/import`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/backup/import | 需要（Bearer Token） |

请求体上限：20 MiB（`bodyLimit: 20 * 1024 * 1024`）。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| Body | mode | string | 否 | `replace` 或 `merge`；缺省为 `replace` |
| Body | data | object | 是 | 备份负载 |
| Body.data.format | string | 是 | 必须为 `kaoyan-backup` |
| Body.data.version | number | 是 | 必须为 `1` |
| Body.data.tables | object | 是 | 包含以下键，且每个键必须为数组：`plans`、`focus_sessions`、`mistakes`、`words`、`srs_state`、`exam_records`、`settings` |

各表行级必填字段：

| 表 | 必填字段及校验 |
| --- | --- |
| plans | `date`（非空 string）、`subject`（合法 SubjectKey）、`title`（非空 string） |
| focus_sessions | `subject`（合法 SubjectKey）、`started_at`（非空 string） |
| mistakes | `subject`（合法 SubjectKey）、`title`（非空 string） |
| words | `word`（非空 string）、`meaning`（非空 string） |
| srs_state | `word_id`（有限 number）、`due_date`（非空 string） |
| exam_records | `subject`（合法 SubjectKey）、`paper`（非空 string）、`taken_at`（非空 string） |
| settings | `key`（非空 string）、`value`（string） |

**mode 语义**

| mode | 行为 |
| --- | --- |
| replace | 单事务内先删除当前用户的 `srs_state`、`words`、`plans`、`focus_sessions`、`mistakes`、`exam_records`、`settings`，再按顺序插入备份数据；任一失败则 ROLLBACK 并返回 500。`srs_state` 中 `word_id` 不属于本次导入 words 的行计入 `skipped.srs_state`。 |
| merge | 不删除现有数据。`words` 按 `(user_id, word)` 去重，已存在则计入 `skipped.words`；`srs_state` 仅当 `word_id` 属于当前用户时以 INSERT OR REPLACE 写入，否则计入 `skipped.srs_state`；`plans`、`focus_sessions`、`mistakes`、`exam_records` 插入异常计入对应 `skipped.*`；`settings` 相同 key 且值相同计入 `skipped.settings`，值不同则更新并计入 `imported.settings`，不存在则插入并计入 `imported.settings`。 |

**成功响应**

状态码：200

```json
{
  "mode": "replace",
  "imported": {
    "plans": 0,
    "focus_sessions": 0,
    "mistakes": 0,
    "words": 0,
    "srs_state": 0,
    "exam_records": 0,
    "settings": 0
  },
  "skipped": {
    "plans": 0,
    "focus_sessions": 0,
    "mistakes": 0,
    "words": 0,
    "srs_state": 0,
    "exam_records": 0,
    "settings": 0
  }
}
```

**错误码**

| 状态码 | 返回体 | 含义 | 触发条件 |
| --- | --- | --- | --- |
| 400 | `{ "error": "请求体无效" }` | Body 非普通对象 | Body 不是对象或为数组或为 null |
| 400 | `{ "error": "无效的 mode" }` | mode 取值非法 | mode 存在且不是 `replace` 也不是 `merge` |
| 400 | `{ "error": "data 无效" }` | data 非普通对象 | data 缺失或不是对象或为数组或为 null |
| 400 | `{ "error": "format 无效" }` | format 不匹配 | data.format !== 'kaoyan-backup' |
| 400 | `{ "error": "version 无效" }` | version 不匹配 | data.version !== 1 |
| 400 | `{ "error": "tables 无效" }` | tables 非普通对象 | data.tables 缺失或不是对象或为数组或为 null |
| 400 | `{ "error": "表 <name> 不是数组" }` | 某表不是数组 | tables[name] 不是数组（name 取 `plans`、`focus_sessions`、`mistakes`、`words`、`srs_state`、`exam_records`、`settings`） |
| 400 | `{ "error": "表 <name> 第 <r> 行不是对象" }` | 行非普通对象 | tables[name][r] 不是对象或为数组或为 null |
| 400 | `{ "error": "表 <name> 第 <r> 行：date 缺失或类型不对" }` | plans.date 非法 | plans 行 date 不是非空 string |
| 400 | `{ "error": "表 <name> 第 <r> 行：subject 无效" }` | subject 非法 | plans / focus_sessions / mistakes / exam_records 行 subject 非合法 SubjectKey |
| 400 | `{ "error": "表 <name> 第 <r> 行：title 缺失或类型不对" }` | title 非法 | plans / mistakes 行 title 不是非空 string |
| 400 | `{ "error": "表 <name> 第 <r> 行：started_at 缺失或类型不对" }` | started_at 非法 | focus_sessions 行 started_at 不是非空 string |
| 400 | `{ "error": "表 <name> 第 <r> 行：word 缺失或类型不对" }` | word 非法 | words 行 word 不是非空 string |
| 400 | `{ "error": "表 <name> 第 <r> 行：meaning 缺失或类型不对" }` | meaning 非法 | words 行 meaning 不是非空 string |
| 400 | `{ "error": "表 <name> 第 <r> 行：word_id 缺失或类型不对" }` | word_id 非法 | srs_state 行 word_id 不是有限 number |
| 400 | `{ "error": "表 <name> 第 <r> 行：due_date 缺失或类型不对" }` | due_date 非法 | srs_state 行 due_date 不是非空 string |
| 400 | `{ "error": "表 <name> 第 <r> 行：paper 缺失或类型不对" }` | paper 非法 | exam_records 行 paper 不是非空 string |
| 400 | `{ "error": "表 <name> 第 <r> 行：taken_at 缺失或类型不对" }` | taken_at 非法 | exam_records 行 taken_at 不是非空 string |
| 400 | `{ "error": "表 <name> 第 <r> 行：key 缺失或类型不对" }` | key 非法 | settings 行 key 不是非空 string |
| 400 | `{ "error": "表 <name> 第 <r> 行：value 缺失或类型不对" }` | value 非法 | settings 行 value 不是 string |
| 500 | `{ "error": "导入失败" }` | replace 模式事务失败 | replace 分支中任一数据库操作抛错（已尝试 ROLLBACK） |

说明：错误文案中 `<name>` 为表名，`<r>` 为 1 基行号（源码中为 `r + 1`）。

### `POST /api/import/words`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/import/words | 需要（Bearer Token） |

请求体上限：5 MiB（`bodyLimit: 5 * 1024 * 1024`）。CSV 支持 UTF-8 BOM、双引号转义、`\r\n` / `\n` 换行。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| Body | csv | string | 是 | CSV 文本，非空（trim 后） |

CSV 列：

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| word | 是 | 单词；trim 后为空计入 `skippedEmpty` |
| meaning | 是 | 释义；trim 后为空计入错误行 |
| phonetic | 否 | 音标 |
| example | 否 | 例句 |

表头大小写不敏感（normalizeHeader 转小写并 trim），第一个非空行作为表头。导入后写入 `words`（source 固定为 `csv`）并插入初始 `srs_state`（ease=2.5、interval_days=0、repetitions=0、due_date=今日）。

**成功响应**

状态码：200

```json
{
  "imported": 10,
  "skippedEmpty": 1,
  "skippedExisting": 2,
  "errors": [{ "row": 5, "message": "meaning 不能为空" }],
  "errorRows": 1
}
```

`errors` 最多收集 50 条。

**错误码**

| 状态码 | 返回体 | 含义 | 触发条件 |
| --- | --- | --- | --- |
| 400 | `{ "error": "请求体无效" }` | Body 非普通对象 | Body 不是对象或为数组或为 null |
| 400 | `{ "error": "csv 不能为空" }` | csv 缺失或空白 | csv 不是 string 或 trim 后为空 |
| 400 | `{ "error": "缺少必需列：word / meaning" }` | 无表头或缺少必需列 | 全部行为空白行，或表头中不存在 `word` 或不存在 `meaning` |

### `POST /api/import/mistakes`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/import/mistakes | 需要（Bearer Token） |

请求体上限：5 MiB（`bodyLimit: 5 * 1024 * 1024`）。CSV 解析规则同上。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| Body | csv | string | 是 | CSV 文本，非空（trim 后） |

CSV 列：

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| subject | 是 | 必须为合法 SubjectKey，否则计入错误行 |
| title | 是 | trim 后为空计入错误行 |
| content | 否 | 缺省空字符串 |
| analysis | 否 | 缺省空字符串 |

表头大小写不敏感。导入的错题 `mastered` 固定为 0，`created_at` 使用当前 ISO 时间。

**成功响应**

状态码：200

```json
{
  "imported": 8,
  "errors": [{ "row": 3, "message": "无效的 subject" }],
  "errorRows": 1
}
```

`errors` 最多收集 50 条。

**错误码**

| 状态码 | 返回体 | 含义 | 触发条件 |
| --- | --- | --- | --- |
| 400 | `{ "error": "请求体无效" }` | Body 非普通对象 | Body 不是对象或为数组或为 null |
| 400 | `{ "error": "csv 不能为空" }` | csv 缺失或空白 | csv 不是 string 或 trim 后为空 |
| 400 | `{ "error": "缺少必需列：subject / title" }` | 无表头或缺少必需列 | 全部行为空白行，或表头中不存在 `subject` 或不存在 `title` |

### `POST /api/import/exams`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/import/exams | 需要登录 |

请求体上限：5 MiB（`bodyLimit: 5 * 1024 * 1024`）。CSV 解析规则同上。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| Body | csv | string | 是 | CSV 文本，非空（trim 后） |

CSV 列：

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| subject | 是 | 必须为合法 SubjectKey（math/english/politics/major），否则计入错误行 |
| paper | 是 | trim 后为空计入错误行 |
| score | 是 | 必须为数字，且在 0 到 total_score 之间，否则计入错误行 |
| total_score | 是 | 必须为数字且大于 0，否则计入错误行 |
| duration_minutes | 否 | 缺省 0；非空时必须为大于等于 0 的数字，否则计入错误行，写入时取整 |
| taken_at | 否 | 缺省今天；非空时必须为严格 YYYY-MM-DD 真实日期，否则计入错误行 |

表头大小写不敏感。合法行写入 exam_records，`taken_at` 缺省为今天。

**成功响应**

状态码：200

```json
{
  "imported": 2,
  "errors": [{ "row": 4, "message": "score 不能大于 total_score" }],
  "errorRows": 1
}
```

`errors` 最多收集 50 条，`errorRows` 为错误行总数。

**错误码**

| 状态码 | 返回体 | 含义 | 触发条件 |
| --- | --- | --- | --- |
| 400 | `{ "error": "csv 不能为空" }` | csv 缺失或空白 | csv 不是 string 或 trim 后为空 |
| 400 | `{ "error": "缺少必需列：subject / paper / score / total_score" }` | 无表头或缺少必需列 | 全部行为空白行，或表头中不存在必需列 |
| 401 | 未登录 | 需要登录 | 未携带有效登录凭据 |

### `POST /api/import/plans`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| POST | /api/import/plans | 需要登录 |

请求体上限：5 MiB（`bodyLimit: 5 * 1024 * 1024`）。CSV 解析规则同上。

**请求参数**

| 位置 | 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| Body | csv | string | 是 | CSV 文本，非空（trim 后） |

CSV 列：

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| date | 是 | 必须为严格 YYYY-MM-DD 真实日期，否则计入错误行 |
| subject | 是 | 必须为合法 SubjectKey（math/english/politics/major），否则计入错误行 |
| title | 是 | trim 后为空计入错误行 |
| planned_minutes | 否 | 缺省 60；非空时必须为 1~1440 的数字，否则计入错误行 |
| done | 否 | 缺省 0；非空时只接受 0 或 1，否则计入错误行 |

表头大小写不敏感。合法行写入 plans，`created_at` 使用当前 ISO 时间。

**成功响应**

状态码：200

```json
{
  "imported": 2,
  "errors": [{ "row": 4, "message": "date 须为 YYYY-MM-DD 格式的真实日期" }],
  "errorRows": 1
}
```

`errors` 最多收集 50 条，`errorRows` 为错误行总数。

**错误码**

| 状态码 | 返回体 | 含义 | 触发条件 |
| --- | --- | --- | --- |
| 400 | `{ "error": "csv 不能为空" }` | csv 缺失或空白 | csv 不是 string 或 trim 后为空 |
| 400 | `{ "error": "缺少必需列：date / subject / title" }` | 无表头或缺少必需列 | 全部行为空白行，或表头中不存在必需列 |
| 401 | 未登录 | 需要登录 | 未携带有效登录凭据 |

### `POST /api/import/focus`

从 CSV 文本导入专注计时记录，合法行写入 `focus_sessions`。

| 项目 | 说明 |
| --- | --- |
| 方法 | `POST` |
| 路径 | `/api/import/focus` |
| 认证 | 需要登录 |

请求体上限 5 MiB。

**Body 参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| csv | string | 是 | CSV 文本，trim 后不能为空；解析规则同其他导入（UTF-8 BOM、引号转义、CRLF、表头大小写不敏感） |

**列说明**

| 列 | 必填 | 说明 |
| --- | --- | --- |
| subject | 是 | 须为合法 SubjectKey（`math` / `english` / `politics` / `major`），否则记错 |
| minutes | 是 | 取整后须在 1 到 1440 之间，否则记错 |
| started_at | 是 | 须以 `YYYY-MM-DD` 开头、长度 10 到 40，且可被 `Date.parse` 解析，否则记错 |
| note | 否 | 缺省 `null`；超过 500 字记错 |
| plan_id | 否 | 缺省 `null`；非空时须为正整数且为当前用户的计划，否则记错 |

**成功响应**

## 9. 设置

### `GET /api/settings`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/settings | 需要（Bearer Token） |

**请求参数**

无。

**成功响应**

状态码：200。返回 `Settings`，缺省字段以 `DEFAULT_SETTINGS` 补齐。数据库中非法值（exam_date 格式不符或不存在的日期、theme 非 light/dark、数字非正整数或超过上限）会被忽略并回退默认值。

```json
{
  "examDate": "2025-12-20",
  "dailyGoalMinutes": 240,
  "pomodoroMinutes": 25,
  "breakMinutes": 5,
  "theme": "light"
}
```

**错误码**

无接口级非 2xx 分支（认证失败由全局鉴权中间件处理）。

### `PUT /api/settings`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| PUT | /api/settings | 需要（Bearer Token） |

**请求参数**

Body 为 `Partial<Settings>`，仅处理出现在 Body 中的字段，未提供的字段保持不变。字段与校验：

| 字段 | 类型 | 校验 |
| --- | --- | --- |
| examDate | string | 匹配 YYYY-MM-DD 且为真实存在的日历日期（不存在的日期非法） |
| dailyGoalMinutes | number | 有限、>0、≤1440 的整数（写入时向下取整） |
| pomodoroMinutes | number | 有限、>0、≤180 的整数（写入时向下取整） |
| breakMinutes | number | 有限、>0、≤60 的整数（写入时向下取整） |
| theme | string | 仅允许 `light` 或 `dark` |

**成功响应**

状态码：200。返回更新后的完整 `Settings`。

```json
{
  "examDate": "2025-12-20",
  "dailyGoalMinutes": 240,
  "pomodoroMinutes": 25,
  "breakMinutes": 5,
  "theme": "dark"
}
```

**错误码**

| 状态码 | 返回体 | 含义 | 触发条件 |
| --- | --- | --- | --- |
| 400 | `{ "error": "invalid field: <field>" }` | 字段非法 | 任一提供字段校验失败；`<field>` 为 `examDate` / `dailyGoalMinutes` / `pomodoroMinutes` / `breakMinutes` / `theme` 之一 |

## 10. 健康检查

### `GET /api/health`

| 方法 | 路径 | 认证 |
| --- | --- | --- |
| GET | /api/health | 免认证 |

**请求参数**

无。

**成功响应**

状态码：200

```json
{
  "status": "ok",
  "time": "2025-01-06T12:00:00.000Z"
}
```

**错误码**

无接口级非 2xx 分支。

**与客户端期望的差异**：源码返回 `{ status: 'ok', time }`，而 `api.ts` 的 `health()` 期望 `{ ok: boolean }`。以源码实际返回为准，`ok` 字段并不存在；调用方应读取 `status === 'ok'` 判断健康状态。

## 附录 A：错误码速查

| 状态码 | 返回体 | 含义 | 常见触发接口 |
| --- | --- | --- | --- |
| 400 | `{ "error": "start 日期格式无效" }` | start 不符合 `YYYY-MM-DD` | GET /api/stats/weekly |
| 400 | `{ "error": "start 日期无效" }` | start 是无效日期 | GET /api/stats/weekly |
| 400 | `{ "error": "months 参数无效" }` | months 非 1..6 的整数 | GET /api/stats/heatmap |
| 400 | `{ "error": "请求体无效" }` | Body 非普通对象 | POST /api/backup/import、POST /api/import/words、POST /api/import/mistakes |
| 400 | `{ "error": "无效的 mode" }` | mode 取值非法 | POST /api/backup/import |
| 400 | `{ "error": "data 无效" }` | data 非普通对象 | POST /api/backup/import |
| 400 | `{ "error": "format 无效" }` | format 不匹配 | POST /api/backup/import |
| 400 | `{ "error": "version 无效" }` | version 不匹配 | POST /api/backup/import |
| 400 | `{ "error": "tables 无效" }` | tables 非普通对象 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 不是数组" }` | 某表不是数组 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行不是对象" }` | 行非普通对象 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：date 缺失或类型不对" }` | plans.date 非法 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：subject 无效" }` | subject 非法 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：title 缺失或类型不对" }` | title 非法 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：started_at 缺失或类型不对" }` | started_at 非法 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：word 缺失或类型不对" }` | word 非法 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：meaning 缺失或类型不对" }` | meaning 非法 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：word_id 缺失或类型不对" }` | word_id 非法 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：due_date 缺失或类型不对" }` | due_date 非法 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：paper 缺失或类型不对" }` | paper 非法 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：taken_at 缺失或类型不对" }` | taken_at 非法 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：key 缺失或类型不对" }` | key 非法 | POST /api/backup/import |
| 400 | `{ "error": "表 <name> 第 <r> 行：value 缺失或类型不对" }` | value 非法 | POST /api/backup/import |
| 400 | `{ "error": "csv 不能为空" }` | csv 缺失或空白 | POST /api/import/words、POST /api/import/mistakes |
| 400 | `{ "error": "缺少必需列：word / meaning" }` | 无表头或缺少必需列 | POST /api/import/words |
| 400 | `{ "error": "缺少必需列：subject / title" }` | 无表头或缺少必需列 | POST /api/import/mistakes |
| 400 | `{ "error": "invalid field: <field>" }` | 设置字段非法 | PUT /api/settings |
| 500 | `{ "error": "导入失败" }` | replace 模式事务失败 | POST /api/backup/import |

## 附录 B：文档同步机制

`tests/api-docs-sync.test.ts` 使用 `app.printRoutes()` 枚举应用注册的全部路由，并断言每一个 `METHOD + 路径` 组合都出现在 `docs/API.md` 中。

- 新增接口：必须在本文件中新增对应的 `### \`METHOD /api/xxx\`` 小节，否则测试失败。
- 删除接口：必须同步删除本文件中的对应小节，否则测试失败。
- 修改路径或方法：必须同步更新本文件中的标题，否则测试失败。

换言之，本文件是接口清单的唯一真实来源（single source of truth），任何路由注册的增删改都必须与本文档保持一致。
