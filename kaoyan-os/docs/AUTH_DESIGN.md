# 账号体系设计文档（v1.8.0）

## 1. 背景与目标

README 路线图第 1 项为：「**账号体系**：多用户注册登录、数据按用户隔离，支持多设备同步」。

本轮（v1.8.0）交付范围：

- 多用户**注册**与**登录**。
- 全部业务数据按 `user_id` **隔离**，含老数据迁移。
- 登录态使用服务端 signed opaque session token。

本轮**明确不做**（见第 10 节）：

- 多设备同步（同一账号多端实时/离线同步、冲突解决）。
- OAuth 第三方登录。
- 密码找回。
- 管理员角色。

现状事实（与仓库原文一致）：

- 服务端为 Fastify 单进程（`apps/server/src/app.ts` 中 `Fastify({ logger })`）。
- 数据库为 `node:sqlite` 的 `DatabaseSync`（`apps/server/src/db.ts`），已开启 `PRAGMA foreign_keys = ON`。
- 现有 7 张业务表：`plans`、`focus_sessions`、`mistakes`、`words`、`srs_state`、`exam_records`、`settings`。
- 每个路由文件导出 `registerXxxRoutes(app: FastifyInstance, db: DatabaseSync): void`，请求体校验手写，错误体统一 `{ error: '中文消息' }`。
- 当前依赖：`fastify ^5.2.0`、`@fastify/cors`、`@fastify/static`、`node:sqlite`（Node 24 内置），无密码哈希库，需新增。
- 运行环境为 2 核小内存 Linux VM。

## 2. 密码存储方案

### 2.1 选型：bcryptjs

**选择 `bcryptjs`，不选 `node:crypto` 的 `scrypt`。**

比较项：

| 维度 | bcryptjs | node 内置 scrypt |
| --- | --- | --- |
| 依赖引入成本 | 新增 1 个纯 JS 依赖，无 native 编译，`npm i bcryptjs` 即可 | 0 依赖，`node:crypto` 内置 |
| 内存开销 | 固定约 4KB 级别，cost 只增加 CPU 时间 | 内存开销为 `128 * N * r`，N=2^15、r=8 时约 32MB/次 |
| 2 核小内存 VM 可行性 | 可行：内存占用恒定，只吃 CPU | 可行但风险更高：并发登录时单次 32MB 会叠加，2 核小内存 VM 易触发 OOM |
| 参数表达 | `cost`（对数），语义单一 | `N`、`r`、`p` 三参数，调参面大 |
| 恒定时间比较 | 库内 `compare` 已按恒定时间处理 | 需自行用 `crypto.timingSafeEqual` 处理，易写错 |

**选择理由**：本项目运行在 2 核小内存 VM 上，scrypt 的内存开销随并发线性叠加，是真实 OOM 风险；bcryptjs 是纯 JS、无 native 编译，内存占用恒定，只以 CPU 换强度，适合该环境。且 bcryptjs 的 `compare` 已内置恒定时间比较，减少手写出错面。

### 2.2 参数

- `bcryptjs` 使用 `hash(password, cost)`，`cost = 12`（即 2^12 = 4096 轮）。
- 理由：cost 10 在现代硬件上偏弱；cost 12 在 2 核小内存 VM 上单次哈希约 200–300ms 量级，对注册/登录可接受，对暴力破解构成有效成本；cost 14 会到秒级，影响登录体验，不采用。
- 不使用 `bcryptjs` 的同步 API 于请求路径，使用异步 API（`bcrypt.hash` / `bcrypt.compare`），避免阻塞 Fastify 事件循环。

### 2.3 盐与抗彩虹表

- 盐由 `bcryptjs` 在 `hash` 时自动生成（`bcrypt.genSalt` 等价行为），随机源为该库内部使用的随机源，每个密码一个独立盐。
- 存储格式为 bcrypt 标准字符串 `$2a$12$<salt><hash>`，盐与 cost 内嵌于该字符串，写入 `users.password_hash`。
- 抗彩虹表：每用户独立随机盐 + cost 12，使同一密码在不同用户下哈希不同，预计算表不可复用。

### 2.4 恒定时间比较

- 校验时调用 `bcrypt.compare(plain, storedHash)`，该函数对候选密码做同样 cost 的哈希并做恒定时间比较，不因哈希前缀匹配长度提前返回。
- 代码中禁止手写 `===` 比较密码或哈希。

## 3. 登录态机制

### 3.1 选型：signed session token（服务端 sessions 表 + opaque 随机 token）

**选择服务端 sessions 表 + opaque 随机 token，不选 JWT。**

理由：

- 需要**登出即失效**。opaque token 在服务端删除对应行即失效；JWT 在过期前无法单点失效，需额外维护黑名单表，等于又引入一张表。
- 需要**防重放、防固定**。opaque token 由服务端签发并落库，可对每行记录签发时间、最后使用时间、绝对过期与空闲过期，JWT 把这些放在自包含声明里，改策略需换密钥或加表。
- 本项目为**单进程、单数据库**，session 查询就是一次 `node:sqlite` 主键查询，开销可忽略，JWT 的「无状态」优势在本场景不成立。

### 3.2 token 生成

- 使用 `crypto.randomBytes(32)` 生成 32 字节（256 位）随机值，编码为 `base64url` 字符串作为 token。
- 256 位熵 + 随机源为 `crypto.randomBytes`，满足防猜测。
- 服务端**只存 token 的哈希**，不存 token 明文：对 token 明文做 `crypto.createHash('sha256').update(token).digest('hex')`，将 hex 写入 `sessions.token_hash`。数据库泄露不直接等于会话可被冒用。

### 3.3 存储方式：Cookie

- 自托管单域名场景，选 **Cookie** 而非 `Authorization` header。
- Cookie 名：`kaoyan_session`。
- 属性：`HttpOnly`、`SameSite=Lax`、`Path=/`、`Secure`（仅当请求经 HTTPS 时由部署层反代设置 `X-Forwarded-Proto`，服务端据此决定是否加 `Secure`；本轮实现按环境变量 `COOKIE_SECURE=1` 开启，默认关闭以兼容本地 HTTP 开发）。
- `SameSite=Lax` 已阻断跨站 POST 携带 cookie；同时本轮所有业务写接口只接受 JSON body 与表单编码，且校验 `Content-Type`，跨站简单表单无法构造 `application/json`。

### 3.4 CSRF 处理

- 依赖 `SameSite=Lax` 作为主防线：跨站请求不会携带 `kaoyan_session`。
- 额外防线：对 `POST`/`PUT`/`PATCH`/`DELETE` 请求，若 `Origin` 头存在，必须与 `Host` 推导出的同源一致，否则返回 `403 { error: '非法来源' }`；若 `Origin` 缺失（同源导航或非浏览器客户端），放行并由 `SameSite=Lax` 覆盖浏览器场景。
- 本轮不引入独立 CSRF token，理由：单域名自托管 + `SameSite=Lax` + `Origin` 校验已覆盖浏览器攻击面，独立 token 需前端配合改造，超出本轮范围。

### 3.5 过期与续期

- `sessions` 表字段：
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `user_id INTEGER NOT NULL`，外键引用 `users(id)`，`ON DELETE CASCADE`
  - `token_hash TEXT NOT NULL UNIQUE`
  - `created_at TEXT NOT NULL DEFAULT (datetime('now'))`
  - `last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))`
  - `expires_at TEXT NOT NULL`
- 绝对过期：`expires_at = datetime('now', '+30 days')`，签发时写入。
- 空闲过期：每次认证成功后，若 `last_seen_at` 距当前超过 24 小时，则更新 `last_seen_at = datetime('now')` 并将 `expires_at` 顺延为 `datetime('now', '+30 days')`；未超过 24 小时不写库，避免每请求一次写。
- 认证中间件流程：取 cookie → 算 `token_hash` → 查 `sessions` → 校验 `expires_at > datetime('now')` → 注入 `request.user` → 按上述规则决定是否续期。
- 过期或查不到：返回 `401 { error: '未登录' }`，并下发清除 cookie 的 `Set-Cookie`。

### 3.6 登出失效

- `POST /api/auth/logout`：取 cookie 中 token，算 `token_hash`，`DELETE FROM sessions WHERE token_hash = ?`，随后下发清除 cookie 的 `Set-Cookie`（`Max-Age=0`）。
- 无论该 token 是否存在，均返回 `204`，不泄露会话是否存在。

## 4. users 表定义

在 `apps/server/src/db.ts` 的 `initSchema` 中新增：

```sql
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

字段级定义：

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 用户主键 |
| `username` | TEXT | NOT NULL UNIQUE | 登录名，唯一 |
| `password_hash` | TEXT | NOT NULL | bcryptjs 输出，形如 `$2a$12$...` |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | 创建时间，UTC 文本 |

`username` 规则：

- 长度 3–32 字符。
- 字符集：小写字母、数字、下划线；首字符必须为小写字母。
- 校验正则：`/^[a-z][a-z0-9_]{2,31}$/`。
- 注册时对 `username` 先做上述正则校验，再做 `trim`（不改变大小写），不匹配返回 `400 { error: '用户名格式不合法' }`。

`sessions` 表定义（与第 3 节一致）：

```sql
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

## 5. 数据隔离方案

### 5.1 user_id 列加法

对 7 张业务表逐表新增 `user_id` 列，规则统一：

- 类型：`INTEGER`。
- 迁移期：允许 NULL，以便先加列、再回填、再收紧。
- 迁移完成后：`NOT NULL`，并加外键 `REFERENCES users(id) ON DELETE CASCADE`。
- 说明：SQLite 的 `ALTER TABLE` 不能直接加 `NOT NULL` 无默认值的列，也不能直接加外键约束。因此本轮迁移采用「加列 → 回填 → 重建表」三步，重建表在 `initSchema` 里以「检测到旧结构则重建」的方式落地。

`settings` 表特殊处理见第 8 节；`srs_state` 特殊处理见第 5.4 节。

### 5.2 老数据迁移：local 默认保留用户

- 迁移时创建名为 `local` 的默认保留用户，老数据全部归到该用户。
- **`local` 用户是否可登录：不可登录。**
- **`local` 用户密码怎么处理**：`password_hash` 写入一个不可能与任何 bcrypt 校验匹配的固定串 `'!locked'`。`bcrypt.compare(plain, '!locked')` 恒为 `false`，因此该账号无法通过 `/api/auth/login` 登录。原因：老数据没有密码，不能凭空造一个可登录凭据；保留 `local` 仅为承载老数据，保证迁移后数据可见。
- `local` 用户的 `username = 'local'`，满足第 4 节正则（全小写字母，长度 5）。

### 5.3 迁移 SQL（逐表）

迁移在 `initSchema(db)` 内、`CREATE TABLE` 之后执行，检测 `users` 表是否存在且 7 张业务表是否缺 `user_id` 列；若缺则执行下列步骤。以下 SQL 中 `local` 用户 id 通过 `SELECT id FROM users WHERE username = 'local'` 取得，记为 `:local_id`。

步骤 A：建 `users` 表与 `sessions` 表（幂等，已在第 4 节给出）。

步骤 B：确保 `local` 用户存在：

```sql
INSERT INTO users (username, password_hash)
SELECT 'local', '!locked'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'local');
```

步骤 C：对每张表先加可空列：

```sql
ALTER TABLE plans ADD COLUMN user_id INTEGER;
ALTER TABLE focus_sessions ADD COLUMN user_id INTEGER;
ALTER TABLE mistakes ADD COLUMN user_id INTEGER;
ALTER TABLE exam_records ADD COLUMN user_id INTEGER;
ALTER TABLE words ADD COLUMN user_id INTEGER;
```

（`srs_state` 与 `settings` 不在本步，见 5.4 与第 8 节。）

步骤 D：回填老数据到 `local`：

```sql
UPDATE plans SET user_id = (SELECT id FROM users WHERE username = 'local') WHERE user_id IS NULL;
UPDATE focus_sessions SET user_id = (SELECT id FROM users WHERE username = 'local') WHERE user_id IS NULL;
UPDATE mistakes SET user_id = (SELECT id FROM users WHERE username = 'local') WHERE user_id IS NULL;
UPDATE exam_records SET user_id = (SELECT id FROM users WHERE username = 'local') WHERE user_id IS NULL;
UPDATE words SET user_id = (SELECT id FROM users WHERE username = 'local') WHERE user_id IS NULL;
```

步骤 E：重建表以加上 `NOT NULL` 与外键（以 `plans` 为例，其余表同构）：

```sql
CREATE TABLE plans_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  date TEXT NOT NULL,
  subject TEXT NOT NULL,
  title TEXT NOT NULL,
  planned_minutes INTEGER NOT NULL DEFAULT 0,
  done INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
INSERT INTO plans_new (id, user_id, date, subject, title, planned_minutes, done, created_at)
SELECT id, user_id, date, subject, title, planned_minutes, done, created_at FROM plans;
DROP TABLE plans;
ALTER TABLE plans_new RENAME TO plans;
```

`focus_sessions`、`mistakes`、`exam_records`、`words` 按同样方式重建，字段与 `db.ts` 原文一致，仅追加 `user_id` 列与外键。

注意：`words` 表原文中 `word TEXT NOT NULL UNIQUE` 是**全局唯一**。多用户后同一单词可被不同用户各自添加，全局 UNIQUE 会阻止第二个用户添加同一单词。因此重建 `words` 时改为：

```sql
CREATE TABLE words_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  word TEXT NOT NULL,
  phonetic TEXT NOT NULL DEFAULT '',
  meaning TEXT NOT NULL DEFAULT '',
  example TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'manual',
  memory_tip TEXT NOT NULL DEFAULT '',
  UNIQUE (user_id, word),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

即把 `UNIQUE(word)` 改为 `UNIQUE(user_id, word)`。

步骤 F：重建后若存在外键指向被重建的表（`srs_state.word_id` 指向 `words(id)`），需在重建 `words` 后重建 `srs_state`（见 5.4）。

### 5.4 srs_state 的隔离

`srs_state` 不新增 `user_id` 列。理由：`srs_state.word_id` 已是对 `words(id)` 的外键且 `ON DELETE CASCADE`，`words` 已带 `user_id`，因此 `srs_state` 的用户归属完全由 `words.user_id` 决定，再加一列会引入不一致风险。

隔离实现：

- `srs_state` 重建（因 `words` 被重建，外键需重建）：

```sql
CREATE TABLE srs_state_new (
  word_id INTEGER PRIMARY KEY,
  ease REAL NOT NULL DEFAULT 2.5,
  interval_days INTEGER NOT NULL DEFAULT 0,
  repetitions INTEGER NOT NULL DEFAULT 0,
  due_date TEXT NOT NULL,
  FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
);
INSERT INTO srs_state_new (word_id, ease, interval_days, repetitions, due_date)
SELECT word_id, ease, interval_days, repetitions, due_date FROM srs_state;
DROP TABLE srs_state;
ALTER TABLE srs_state_new RENAME TO srs_state;
```

- 所有对 `srs_state` 的查询与更新，SQL 均通过 `JOIN words ON words.id = srs_state.word_id` 并加 `WHERE words.user_id = ?` 条件。
- 例：取某用户今日到期：

```sql
SELECT srs_state.word_id, srs_state.ease, srs_state.interval_days, srs_state.repetitions, srs_state.due_date
FROM srs_state
JOIN words ON words.id = srs_state.word_id
WHERE words.user_id = ? AND srs_state.due_date <= date('now');
```

- 例：更新某用户某词的复习状态：

```sql
UPDATE srs_state
SET ease = ?, interval_days = ?, repetitions = ?, due_date = ?
WHERE word_id = ?
  AND EXISTS (SELECT 1 FROM words WHERE words.id = srs_state.word_id AND words.user_id = ?);
```

- 删除：`srs_state` 行随 `words` 行级联删除；用户删除 `words` 行时由其自身 `user_id` 条件限定，`srs_state` 自动级联。

## 6. 路由隔离策略

### 6.1 认证中间件

新增 `apps/server/src/auth.ts`，导出：

- `registerAuthRoutes(app: FastifyInstance, db: DatabaseSync): void`：注册 `/api/auth/register`、`/api/auth/login`、`/api/auth/logout`、`/api/auth/me`。
- `authHook(app: FastifyInstance, db: DatabaseSync): void`：注册 `onRequest` 钩子。

钩子行为：

- 白名单路径直接放行：`/api/health`、`/api/auth/register`、`/api/auth/login`、`/api/auth/logout`、`/api/auth/me`。
- 其余 `/api/*` 路径：从 cookie `kaoyan_session` 取 token → 算 `token_hash` → 查 `sessions` → 校验 `expires_at > datetime('now')` → 查 `users` → 将 `request.user = { id, username }` 注入。
- 失败统一返回 `401 { error: '未登录' }`，并下发清除 cookie 的 `Set-Cookie`。
- `request.user` 类型通过 Fastify 的 `declare module 'fastify'` 扩展 `FastifyRequest`，字段为 `user?: { id: number; username: string }`。

在 `buildApp` 中，`authHook(app, db)` 在注册业务路由之前调用，`registerAuthRoutes(app, db)` 在 `registerPlansRoutes` 之前调用。

### 6.2 逐路由 user_id 取值与条件

所有业务路由统一规则：**`user_id` 一律从 `request.user.id` 取，绝不从请求体、查询串或路径参数取。**

| 路由文件 | 现有路由（`/api/...`） | 读取 `user_id` | 查询条件 |
| --- | --- | --- | --- |
| `routes/plans.ts` | `GET /api/plans` | `request.user.id` | `WHERE user_id = ?` |
| `routes/plans.ts` | `POST /api/plans` | `request.user.id` | `INSERT ... user_id = ?` |
| `routes/plans.ts` | `PATCH /api/plans/:id` | `request.user.id` | `UPDATE ... WHERE id = ? AND user_id = ?` |
| `routes/plans.ts` | `DELETE /api/plans/:id` | `request.user.id` | `DELETE FROM plans WHERE id = ? AND user_id = ?` |
| `routes/focus.ts` | `GET /api/focus` | `request.user.id` | `WHERE user_id = ?` |
| `routes/focus.ts` | `POST /api/focus` | `request.user.id` | `INSERT ... user_id = ?` |
| `routes/focus.ts` | `DELETE /api/focus/:id` | `request.user.id` | `DELETE ... WHERE id = ? AND user_id = ?` |
| `routes/mistakes.ts` | `GET /api/mistakes` | `request.user.id` | `WHERE user_id = ?` |
| `routes/mistakes.ts` | `POST /api/mistakes` | `request.user.id` | `INSERT ... user_id = ?` |
| `routes/mistakes.ts` | `PATCH /api/mistakes/:id` | `request.user.id` | `UPDATE ... WHERE id = ? AND user_id = ?` |
| `routes/mistakes.ts` | `DELETE /api/mistakes/:id` | `request.user.id` | `DELETE ... WHERE id = ? AND user_id = ?` |
| `routes/words.ts` | `GET /api/words` | `request.user.id` | `WHERE user_id = ?` |
| `routes/words.ts` | `POST /api/words` | `request.user.id` | `INSERT ... user_id = ?`；唯一冲突按 `UNIQUE(user_id, word)` 判断 |
| `routes/words.ts` | `PATCH /api/words/:id` | `request.user.id` | `UPDATE ... WHERE id = ? AND user_id = ?` |
| `routes/words.ts` | `DELETE /api/words/:id` | `request.user.id` | `DELETE ... WHERE id = ? AND user_id = ?` |
| `routes/words.ts` | `GET /api/words/srs/due` | `request.user.id` | `JOIN words ON words.id = srs_state.word_id WHERE words.user_id = ?` |
| `routes/words.ts` | `POST /api/words/:id/srs` | `request.user.id` | `UPDATE srs_state ... WHERE word_id = ? AND EXISTS (SELECT 1 FROM words WHERE words.id = srs_state.word_id AND words.user_id = ?)` |
| `routes/exams.ts` | `GET /api/exams` | `request.user.id` | `WHERE user_id = ?` |
| `routes/exams.ts` | `POST /api/exams` | `request.user.id` | `INSERT ... user_id = ?` |
| `routes/exams.ts` | `DELETE /api/exams/:id` | `request.user.id` | `DELETE ... WHERE id = ? AND user_id = ?` |
| `routes/settings.ts` | `GET /api/settings` | `request.user.id` | 见第 8 节 |
| `routes/settings.ts` | `PUT /api/settings/:key` | `request.user.id` | 见第 8 节 |
| `routes/stats.ts` | `GET /api/stats/*` | `request.user.id` | 各聚合查询加 `WHERE user_id = ?` |
| `routes/backup.ts` | `GET /api/backup/export` | `request.user.id` | 见第 9 节 |
| `routes/backup.ts` | `POST /api/backup/import` | `request.user.id` | 导入行一律写入 `request.user.id`，忽略导入文件中的 `user_id` |

上表中路由路径以现有实现为准；若现有实现中某路径与上表不完全一致，以代码中 `app.get/post/patch/put/delete('/api/...')` 实际注册路径为准，改动仅限「加 `user_id` 条件」这一件事，不新增业务路由。

### 6.3 UPDATE/DELETE 跨用户访问返回 404

**统一返回 `404 { error: '未找到' }`，不返回 403。**

理由：

- 403 会向攻击者确认「该 id 存在但属于别人」，泄露资源存在性；404 不区分「不存在」与「属于别人」，不泄露。
- 一致性规则：所有「按 id 操作的单行读写」接口，只要 `WHERE id = ? AND user_id = ?` 影响行数为 0，一律返回 `404`。包含 `GET /api/xxx/:id`（若存在）、`PATCH`、`DELETE`。
- 唯一例外是未登录：未登录由认证钩子拦截，返回 `401`，不进入业务路由。

### 6.4 未登录统一 401

未登录访问任意业务接口，响应：

```
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{ "error": "未登录" }
```

## 7. API 契约

所有请求与响应均为 `application/json; charset=utf-8`。错误体统一 `{ error: string }`，`error` 为中文消息。成功体不使用 `{ error }` 结构。

### 7.1 POST /api/auth/register

请求体：

```json
{ "username": "alice", "password": "s3cret-pw" }
```

校验：

- `username`：满足 `/^[a-z][a-z0-9_]{2,31}$/`。
- `password`：长度 8–72（bcrypt 输入上限 72 字节，按 UTF-8 字节数计）。

成功：`201`

```json
{ "id": 2, "username": "alice", "created_at": "2025-01-01 00:00:00" }
```

失败：

- `400 { "error": "用户名格式不合法" }`：`username` 不满足正则。
- `400 { "error": "密码长度不合法" }`：`password` 长度不在 8–72。
- `409 { "error": "用户名已存在" }`：`username` 唯一冲突。
- `429 { "error": "请求过于频繁" }`：触发注册限流。

注册成功后不自动登录，不返回 session。

### 7.2 POST /api/auth/login

请求体：

```json
{ "username": "alice", "password": "s3cret-pw" }
```

成功：`200`，并下发 `Set-Cookie: kaoyan_session=<token>; HttpOnly; SameSite=Lax; Path=/`（HTTPS 环境追加 `Secure`）。

```json
{ "id": 2, "username": "alice" }
```

失败：`401 { "error": "用户名或密码错误" }`，且不区分「用户名不存在」与「密码错误」。

- `429 { "error": "请求过于频繁" }`：触发登录限流。

### 7.3 POST /api/auth/logout

请求体：无。

行为：删除 cookie 对应 session 行，下发清除 cookie 的 `Set-Cookie`（`Max-Age=0`）。

成功：`204`，无响应体。未登录时同样返回 `204`。

### 7.4 GET /api/auth/me

请求体：无。

成功：`200`

```json
{ "id": 2, "username": "alice" }
```

失败：`401 { "error": "未登录" }`。

## 8. settings 表隔离

`settings` 原为全局 key-value：

```sql
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

### 8.1 选择：加 user_id 列，不改 key 前缀

**选择加 `user_id` 列，不选择给 key 加前缀。**

理由：

- key 加前缀（如 `u2:theme`）把用户身份编码进字符串，查询必须做字符串拼接，无法用外键约束，删除用户时无法级联清理。
- 加 `user_id` 列后，主键变为 `(user_id, key)`，可用外键 `ON DELETE CASCADE` 随用户删除自动清理，查询条件统一为 `WHERE user_id = ? AND key = ?`。

### 8.2 迁移

```sql
CREATE TABLE settings_new (
  user_id INTEGER NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (user_id, key),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
INSERT INTO settings_new (user_id, key, value)
SELECT (SELECT id FROM users WHERE username = 'local'), key, value FROM settings;
DROP TABLE settings;
ALTER TABLE settings_new RENAME TO settings;
```

老设置全部归到 `local` 用户。`seedIfEmpty` 的判定逻辑相应改为按用户判定：`settings` 中不存在该 `user_id` 的行时，为该用户写入默认设置。

### 8.3 路由行为

- `GET /api/settings`：`SELECT key, value FROM settings WHERE user_id = ?`，返回对象或数组，与现有实现结构一致，仅加 `user_id` 条件。
- `PUT /api/settings/:key`：`INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value`。
- 主题偏好等所有 key 自动按用户隔离。

## 9. 安全清单逐项回应

### 9.1 SQL 注入

- 本项目使用 `node:sqlite` 的 `DatabaseSync`，所有新代码延续现有约定：一律用 `db.prepare(...)` 加占位符 `?` 传参，禁止字符串拼接 SQL。
- 新代码中不允许出现模板字符串拼 SQL 值。`user_id`、`username`、`key`、`value` 全部走占位符。
- `PRAGMA foreign_keys = ON` 已在 `createDb` 中开启，迁移与运行期均生效。

### 9.2 暴力破解

本项目为 Fastify 单进程，使用**内存计数器**，不引入 Redis 等外部依赖。

登录限流（`POST /api/auth/login`）：

- 维度一：按 `username` 计数。键 `login:user:<username>`。
- 维度二：按客户端 IP 计数。键 `login:ip:<ip>`，IP 取 `request.ip`。
- 阈值：任一维度在 15 分钟滑动窗口内失败次数达到 10 次，返回 `429 { error: '请求过于频繁' }`。
- 成功登录后清零该 `username` 与 `ip` 的计数。
- 实现：`Map<string, { count: number; resetAt: number }>`，每次访问时若 `Date.now() > resetAt` 则重置；每 10 分钟用 `setInterval` 清理过期键，`unref()` 以免阻止进程退出。

注册限流（`POST /api/auth/register`）：

- 维度：按客户端 IP。键 `register:ip:<ip>`。
- 阈值：1 小时滑动窗口内 5 次，超出返回 `429 { error: '请求过于频繁' }`。

认证失败限流：

- 未登录访问业务接口由认证钩子直接 `401`，不计入登录计数器，避免正常过期会话触发封禁。

### 9.3 敏感数据

- `password_hash` 只写不读：任何 API 响应体、日志、错误消息中都不包含 `password_hash`。`/api/auth/me` 与 `/api/auth/register` 的成功体只含 `id`、`username`、`created_at`。
- 备份导出（`GET /api/backup/export`）**不包含 `users` 表，也不包含 `sessions` 表**。导出仅含当前 `user_id` 的 7 张业务表中属于该用户的行（`srs_state` 通过 `words` 关联过滤），且导出内容中省略 `user_id` 字段。
- 备份导入（`POST /api/backup/import`）忽略导入文件中的 `user_id`，所有行强制写入 `request.user.id`。
- 删除策略：删除用户时 `users` 行删除，`sessions`、7 张业务表（含 `settings`）通过 `ON DELETE CASCADE` 级联删除。本轮不提供删除用户 API，删除通过运维直接对数据库执行 `DELETE FROM users WHERE id = ?` 完成，级联由外键保证。

### 9.4 密钥分离

- 本轮 session token 为 opaque 随机值，不涉及签名密钥，因此**不需要 session 签名密钥**。token 的安全性来自 `crypto.randomBytes(32)` 的熵与服务端哈希存储，不依赖密钥。
- 现有环境变量 `DATABASE_PATH` 继续用于数据库路径（`app.ts` 原文）。
- 启动校验：`buildApp` 在创建 app 后、注册路由前，校验 `DATABASE_PATH`（若设置）指向的目录可写；不可写时抛错并终止启动。本轮不新增必填环境变量，避免与现有部署冲突。
- 若后续引入签名密钥，必须从环境变量读取并在启动时校验非空，本条为约束，不在本轮实现。

## 10. 已知缺口与非目标

以下内容**本轮不做**，明确列为已知缺口：

- **多设备同步**：同一账号在多设备间的实时同步、离线修改合并、冲突解决，本轮不做。本轮只保证同一账号在任一设备登录后看到同一份服务端数据。
- **OAuth 第三方登录**：不接入任何第三方身份提供方。
- **密码找回**：不提供邮箱/手机找回、重置密码流程。忘记密码只能由运维直接改库。
- **管理员角色**：不引入 `role` 字段、不引入管理端接口、不引入用户管理页面。

已知缺口带来的可接受后果：

- `local` 用户不可登录，老数据只能通过注册新用户后手工在数据库层面改 `user_id` 归属，本轮不提供该操作界面。
- 无密码找回意味着用户忘记密码即失去账号访问，本轮接受。
