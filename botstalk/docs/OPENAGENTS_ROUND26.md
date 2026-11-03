OpenAgents 第 26 轮：任务列表 limit 非法值返回 400

## 背景与缺口
GET /api/tasks 的 limit 参数此前静默回落：代码为 parseInt 后有限且大于 0 才生效，否则默认 50；1.5 截成 1、10abc 截成 10，abc、0、负数、空串都悄悄回落 50，调用方无从知晓。本轮接第 22 轮配对码 ttl、第 23 轮分享链接 ttl、第 24 轮历史 limit、第 25 轮历史 before_id 的同款收紧系列。事前核查：HTTP 层没有测试锁定旧回落语义（tasks-api、tasks-cursor、tasks 三个测试文件只覆盖房间/状态过滤、游标分页与数据库层上限），数据库层 listTasks 的上限 200 测试本轮未动。

## 改动
只改 botstalk/gateway/src/server.ts 的任务列表分支。limitParam 存在时必须匹配 /^[0-9]+$/ 且解析后大于等于 1，否则返回 400 且 body 严格等于 {"error":"INVALID_TASKS_LIMIT"}，不调用 listTasks；缺省仍默认 50，上限仍为 Math.min(n, 200)；status、room、before_updated_ms/before_task_id 游标分支与 db.ts 一字不动；不升协议版本。

## 测试
新增 botstalk/gateway/test/tasks-limit-validation.test.ts（以 upsertTaskDispatch 种子 7 条任务、startServer 端口 0 起服、fetch 断言的写法，与既有 tasks-api 测试同款）。12 例：无效 7 个（0、-1、abc、1.5、10abc、空串、5.0）各返回 400 且体严格相等；有效 5 个（limit=5 得 5 条、limit=1 得 1 条、limit=1000 得 7 条、缺省得 7 条、limit=200 得 7 条）。靶向 4 文件 41 例全绿。先红验证：临时回退网关改动（git stash）后新测恰好 7 败 5 过，恢复后复绿。网关全量 vitest 84 文件 1083 例全绿（第 25 轮基线 83 文件 1071 例，恰增本轮 1 文件 12 例，零回归）。网关源码 tsc --noEmit 零错；测试 tsc 共 7 处既存错误，均在旧文件内（game-frames、pairing、werewolf-ai-vision、werewolf-r2），本轮新文件零错。

## 冒烟
新增 botstalk/scripts/smoke-tasks-limit.mjs，真实网关端口 18501。种子用两段式：先起服建表后停服、离线向 botstalk.db 的 tasks 表插 7 条任务、再起服测，避开第 25 轮记下的运行中插库 database is locked 教训。8 项全过（limit=5、1、1000、缺省各 200 且条数正确；abc、0、1.5、空串各 400 且体为 INVALID_TASKS_LIMIT），打印 SMOKE_TASKS_LIMIT_PASS，冒烟后端口复查已关。

## 已知保留与下一轮候选
游标 before_updated_ms/before_task_id 只给一半时静默忽略的语义本轮未动；未读数接口 since_id 的静默回落本轮未动，可作后续收紧候选；吊销仍为终态、REST requester 自报身份未动；第 24/25 轮的轮次文档缺口与第 17 轮设备管理 Web UI 缺 CHANGELOG 与轮次文档的缺口仍在；无 Web UI 改动，视觉验收不适用。
