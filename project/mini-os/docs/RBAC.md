# RBAC 角色权限（v1.7）

v1.7 给 mini-os 加上了角色权限。以前只有“是不是管理员”这一条线，现在是三档角色，权限按角色来卡。这篇文档讲清楚每档角色能干啥、被拦下来是什么样、怎么用 CLI 管人、老库升级怎么映射。

## 角色与权限矩阵

三档角色存在 `users.role` 列里，迁移 005 加的，带 CHECK 约束，只允许 `admin`、`editor`、`viewer` 三个值。

| 能力 | admin（管理员） | editor（编辑者） | viewer（只读） |
| --- | --- | --- | --- |
| 文件读取 | ✓ | ✓ | ✓ |
| 文件写入 | ✓ | ✓ | — |
| 创建分享 | ✓ | ✓ | — |
| 管理分享（自己创建的） | ✓ | ✓ | — |
| 管理分享（全部人的） | ✓ | — | — |
| 用户管理（列表、改角色） | ✓ | — | — |
| 便签/日程读取 | ✓ | ✓ | ✓ |
| 便签/日程写入 | ✓ | ✓ | — |

一句话版本：

- 管理员：文件读写 + 分享创建/管理 + 用户管理，全都能干。
- 编辑者：文件读写 + 分享创建 + 管理自己创建的分享。
- 只读：只能读文件，别的都不行。

权限是在 Axum 中间件里按“HTTP 方法 + 路由”强制执行的，不是前端藏个按钮那种假权限。前端怎么改都绕不过去。

个人设置（主题、壁纸）按用户隔离，每个人改自己的，这块不在权限矩阵里，任何角色都能改自己的。

## 403 长什么样

没权限的请求会被中间件拦下来，返回 403，body 是 JSON：

```json
{"error":"权限不足","reason":"需要「X」权限，当前角色为「Y」"}
```

`reason` 里会把需要的权限和当前角色写清楚，方便排查。

举两个例子。

viewer 想写文件，调 `POST /api/fs`：

```
$ curl -i -X POST http://localhost:8080/api/fs \
    -H "Cookie: session=..." \
    -H "Content-Type: application/json" \
    -d '{"path":"/notes/todo.md","content":"hello"}'

HTTP/1.1 403 Forbidden
Content-Type: application/json

{"error":"权限不足","reason":"需要「文件写入」权限，当前角色为「viewer」"}
```

viewer 想建分享，调创建分享的接口：

```
$ curl -i -X POST http://localhost:8080/api/shares \
    -H "Cookie: session=..." \
    -H "Content-Type: application/json" \
    -d '{"path":"/notes/todo.md"}'

HTTP/1.1 403 Forbidden
Content-Type: application/json

{"error":"权限不足","reason":"需要「分享创建」权限，当前角色为「viewer」"}
```

viewer 建分享是直接 403，因为 viewer 压根没有分享创建权限。

顺带说一句：分享链接本身一律只读，这是分享机制本身的设定，跟角色无关。所以“viewer 建的分享只读”这个说法天然成立——其实 viewer 根本建不了分享，而能建分享的人建出来的分享也是只读的。

## 用户管理接口

两个接口，只有 admin 能调，其他角色调会吃 403。

- `GET /api/users`：列出用户。返回用户列表。
- `PUT /api/users/{id}/role`：改某个用户的角色。body 里带新的 role。

改角色有几条安全规则：

- 不能移除最后一个 admin。如果这次改动会让系统里一个 admin 都不剩，直接 403 拒绝。
- 改完角色后，该用户全部 session 会被撤销，必须重新登录才生效。
- 遇到未知的 role 字符串，按 viewer 处理，也就是 fail-closed，宁可给少权限也不给多。

## 分享管理接口

- `GET /api/shares`：列分享。admin 看全部人的分享，editor 只看自己创建的。
- `DELETE /api/shares/{id}`：删分享。admin 能删任何人的，editor 只能删自己的，删别人的会被拦。

viewer 这两个接口都进不来，因为 viewer 没有分享相关权限。

## CLI 管理命令

除了 HTTP 接口，命令行也能管用户。

新增用户：

```
mini-os useradd --username 名 --password 密码 [--role admin|editor|viewer]
```

`--role` 不填的话走默认。注意：系统里第一个用户会自动成为 admin。

改角色：

```
mini-os set-role --username 名 --role 角色
```

`set-role` 同样受“最后一个 admin”保护，改不动最后一个 admin。

两个完整例子：

```
# 加一个编辑者
mini-os useradd --username alice --password s3cret --role editor

# 把 alice 改成只读
mini-os set-role --username alice --role viewer
```

## 老版本升级（迁移 005 的映射规则）

迁移 005 负责把老库里的用户映射到新的三档角色，规则如下：

- `is_admin = 1` 的用户 → `admin`。
- 可登录的普通用户（有密码、能登录的）→ `editor`。
- legacy 占位用户（`password_hash IS NULL`）→ `viewer`。

映射完之后 `users.role` 列带上 CHECK 约束，值只能是三个合法角色之一。

## 已知限制

- `/ws` 终端自 v1.9 起纳入 RBAC：`term_open` 消息要求 FsWrite 权限，
  viewer 角色打开终端会被服务端拒绝（`term_error` "权限不足"）。
  其余终端消息（input/resize/signal/close）在已建立的会话内透传，
  会话本身按 user_id 隔离。
- 分享没有过期时间，也没有撤销接口，这个状态从 v1.6 延续到 v1.7，没变。
- 个人设置（主题、壁纸）不在权限矩阵里，按用户隔离，各改各的。

另外提一句，`/api/me` 会返回当前用户的 role，前端任务栏显示成“用户名（角色名）”，方便一眼看出自己是什么身份。
