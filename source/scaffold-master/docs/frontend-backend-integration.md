# 前后端接口约定

前端统一通过 `src/api` 请求 `/api`，开发服务器代理到本地 Spring Boot。接口、页面与表的完整定位见根目录 `PROJECT_MAP.md`。

## 响应与分页

普通 JSON 响应为 `code`（结果码）、`message`（提示）、`data`（业务内容）、`traceId`（追踪 ID）；HTTP 与业务码均成功时客户端返回 `data`，错误抛出 `ApiError`。CSV 与 ZIP 使用文件响应。

| 字段 | 中文含义 |
| --- | --- |
| `pageNum` / `pageSize` | 页码 / 每页数量；默认 1 / 10，每页最多 100 |
| `total` / `rows` | 总记录数 / 当前页数据 |
| `id` / `parentId` | 当前记录 ID / 上级记录 ID |
| `username` / `nickname` | 登录账号 / 用户姓名 |
| `deptName` / `postName` / `roleName` | 部门 / 岗位 / 角色显示名称 |
| `status` | 启用或成功为 1，停用或失败为 0 |
| `permission` / `permissions` | 单个操作权限码 / 当前用户权限码列表 |
| `dataScope` | 角色数据范围；写入使用编码，列表可返回中文名称 |
| `createTime` / `updateTime` | 创建 / 更新时间 |
| `menuIds` / `roleIds` / `postIds` | 已选菜单 / 角色 / 岗位 ID 列表 |

## 核心调用

| 页面 / 公共能力 | API 文件 | 后端路径（均带 /api 前缀） |
| --- | --- | --- |
| 登录、当前用户、菜单、密码 | `auth.ts` | `/auth/captcha`、`/auth/login`、`/auth/me`、`/auth/routes`、`/auth/logout`、`/auth/password` |
| 用户、角色、菜单、部门、岗位、字典、参数 | `system.ts` | `/system/users`（可选 `postId` 岗位过滤）、`/roles`、`/menus`、`/depts`、`/posts`、`/dict`、`/configs`（后六项也带 /system） |
| 权限溯源图 | `system.ts` 的 `permissions.graph` | `/system/permissions/graph` |
| 登录热力 | `system.ts` 的 `loginLogs.heatmap` | `/monitor/login-logs/heatmap` |
| 用户引用选项 | `system.ts` 的 `users.options` | `/system/users/options` |
| 业务字典下拉 | `system.ts` 的 `dictData.options` | `/system/dict/options/{dictType}` |
| 两类日志 | `system.ts` | `/monitor/oper-logs`、`/monitor/login-logs` |
| 日志统计与泳道 | `system.ts` 的 `operLogs.stats / timeline`、`loginLogs.stats` | `/monitor/oper-logs/stats`、`/monitor/oper-logs/timeline`、`/monitor/login-logs/stats` |
| 工作台 | `portal.ts` | `/dashboard/summary` |
| 服务健康（登录页） | `portal.ts` 的 `health` | `/health`（匿名） |
| 代码生成 | `portal.ts` | `/tool/generator` 下的表、字段、导入、预览、生成与下载 |

## 登录与权限

登录请求包含 `username`（账号）、`password`（密码）、`captcha`（验证码字符）、`captchaUuid`（验证码标识）。成功返回 `token`（会话凭据）、`expiresIn`（有效秒数）；后续请求附加 Bearer token。

`/auth/me` 返回当前用户、启用角色与权限，`/auth/routes` 返回授权菜单树。前端仅对 `COMPONENT_MAP` 注册的组件生成可见导航和页面路由，无菜单进入 `/no-access`；直接访问未授权页面不加载对应业务页面。

按钮权限与 `@RequiresPermission` 使用同一权限码；数据范围由后端查询 / 导出执行。停用或删除角色不提供权限，前端隐藏操作不能代替后端 403 校验。

退出、401 与新登录共用清理逻辑；旧 token 的 401 不清除新 token，旧菜单 / 用户响应不能写入新会话，初始化中的旧路由会取消。

## 引用选项

用户列表行的 `lastLogin`（最近登录时间）取自 `sys_user.last_login_time`，登录成功时写入；岗位、角色列表的 `userCount`（在岗 / 持有人数）只计未删除用户。

`users/options` 返回 `depts`（部门树）、`roles`（角色选项）、`posts`（岗位选项）、`initPassword`（初始化密码）。只读用户仅得到不含联系人信息的部门结构；编辑选项与密码按用户操作权限返回。

字典业务选项返回 `label`（显示文字）、`value`（存储值）、`tone`（标签语义色）、`def`（默认标记）、`status`（状态），仅包含启用的类型和条目。管理页读取完整字典数据仍要求 `system:dict:list`。

## 工作台与监控统计

以下接口均为只读聚合，时间边界由数据库时钟给出，避免应用与会话时区不一致。

`/dashboard/summary?range=24h|7d|30d` 在原有字段外新增：

| 字段 | 中文含义 |
| --- | --- |
| `trendPrev` | 上一等长周期的登录次数，用于主卡环比 |
| `dailyOps[].date` / `total` / `failed` | 近 7 天按日：日期 / 操作次数 / 失败次数，缺失日期补 0 |
| `stats` 中 `menus` / `depts` | 统计卡两项：菜单项总数（目录 / 菜单 / 按钮）/ 未删除部门数 |
| `stats[].fresh` | 是否「新增」：上一周期为 0、无法计算环比时为 `true`，前端显示「新增」而非百分比 |
| `roleDist` | 按角色数据范围统计的持有人数，只计未删除用户 |

`/monitor/oper-logs/stats?range=` 与 `/monitor/login-logs/stats?range=`（权限分别为 `monitor:operlog:list`、`monitor:loginlog:list`）：

| 字段 | 中文含义 |
| --- | --- |
| `range` | 实际统计范围；未知取值按 `24h` 处理 |
| `total` / `failed` / `successRate` | 总次数 / 失败次数 / 成功率百分比（无记录时为 100） |
| `avgCost` / `p95Cost` | 操作平均耗时 / 95 分位耗时，单位毫秒（仅操作日志） |
| `activeUsers` | 区间内有操作的账号数（仅操作日志） |
| `users` / `ips` | 区间内登录账号数 / 来源 IP 数（仅登录日志） |
| `series[].bucket` / `total` / `failed` | 时间桶标签（24h 为 `HH:00`，按天为 `MM-dd`）/ 次数 / 失败次数；24h 返回 24 个桶，7d / 30d 返回 7 / 30 个桶 |

`/system/permissions/graph`（权限 `system:role:list`，遵守数据权限）供角色「溯源」视图与菜单星图角色环使用：

| 字段 | 中文含义 |
| --- | --- |
| `users[].id` / `nickname` / `deptName` / `status` | 用户 ID / 昵称 / 部门名 / 状态 |
| `roles[].id` / `name` / `code` / `builtin` / `status` / `dataScope` | 角色 ID / 名称 / 编码 / 内置标记 / 状态 / 数据范围 |
| `menus[].id` / `parentId` / `name` / `type` / `permission` | 菜单 ID / 父级 / 名称 / 类型（目录、菜单、按钮）/ 权限码 |
| `userRoles` / `roleMenus` | 用户-角色、角色-菜单 `[from, to]` 关联对 |

`/monitor/login-logs/heatmap?days=7|30`（权限 `monitor:loginlog:list`）：

| 字段 | 中文含义 |
| --- | --- |
| `cells[].dow` / `hour` / `total` / `failed` | 星期（0–6）/ 小时（0–23）/ 登录次数 / 失败次数，组成 7×24 网格 |
| `anomalies[].kind` / `key` / `failed` / `firstTime` / `lastTime` | 异常类型（`ip` 或 `user`）/ 来源标识 / 失败次数 / 首次 / 最近失败时间；同 IP 或同账号窗口内连续失败达到阈值即聚合，阈值读 `sys_config`，缺省 5 |

用户列表 `GET /system/users` 新增可选 `postId`（岗位 ID，经 `sys_user_post` 关联过滤），分页、统计与导出一致生效，仍受 `@DataScope` 数据范围约束；前端用于岗位阶梯的成员触须。

`/monitor/oper-logs/timeline?date=yyyy-MM-dd`（缺省为数据库当天，格式错误返回 400）：

| 字段 | 中文含义 |
| --- | --- |
| `date` / `nowSec` | 统计日期 / 当前时刻的当日秒数（非当天为 `null`） |
| `lanes[].module` / `count` | 泳道对应的操作模块 / 当日次数，按次数降序 |
| `blocks[].startSec` / `endSec` | 时间块起止的当日秒数；同模块相邻操作间隔不超过 15 分钟即合并 |
| `blocks[].count` / `failed` / `maxCost` | 块内次数 / 失败次数 / 最大耗时毫秒 |
| `blocks[].ids` | 块内日志 ID，最多 50 个，用于定位明细 |

## 代码生成契约与边界

预览返回 `files`（文件列表）、`activeFile`（默认文件名）、`code`（默认文件代码）；每个文件含 `name`（文件名）、`path`（相对路径）、`code`（该文件代码）。前端按完整路径切换，所有文件都可查看。

生成表字段：`tableName`（表名）、`tableComment`（说明）、`className`（实体名）、`module`（模块名）、`businessName`（业务名）、`synced`（配置确认标记）。配置保存当前支持说明与确认标记，字段信息只展示；ZIP 为 7 份开发骨架，业务 CRUD 尚需实现和验证，不自动写入项目。

## 验证入口

后端集成测试通过真实验证码契约登录，覆盖认证、接口权限、数据范围、管理写入、日志、日志统计与泳道、工作台与生成器；前端单测验证统一请求与契约。`scaffold-vue/scripts/session-regression.py` 验证浏览器中的旧请求晚到、慢退出、低权限与无菜单账号。

测试使用独立本地数据库；变更公共能力后补受影响页面的实际操作验证。
