# BotsTalk v0.3.0 设计说明

存档日期：随 v0.3.0 发布。
本文档描述任务追踪面板、未读计数、一键部署三件事的行为。所有描述以当前实现为准。

## 1. 一句话目标

老板在群里派活，活儿的状态全程可见、可取消，断线不丢事件。

拆开说：
- 群里发一条 intent=task 的消息就是派活。
- 网关把它记进任务台账，选一个 adapter 执行。
- 状态变化（派发、执行中、完成、失败、无 adapter、取消）都以 task_event 广播出去，面板实时看到。
- 断线重连能补到漏掉的 task_event。
- 任务面板里能看未读数，点一下就标已读。

## 2. 任务状态机与 cancel 规则

### 2.1 状态集合

| 状态 | 含义 |
| --- | --- |
| dispatched | 已派发给某个 adapter，等待它开工 |
| running | adapter 回执说在执行中 |
| done | 终态，完成 |
| failed | 终态，失败 |
| unsupported | 终态，没有可用 adapter 接活 |
| cancelled | 终态，owner 主动取消 |

### 2.2 流转图

```
                    routeMessage(intent=task, 无 task_status)
                                   |
                                   v
                            +--------------+
                            |  dispatched  |
                            +--------------+
                              |         |
            回执 running        |         |  回执 failed
                              v         v
                        +---------+   +--------+
                        | running |   | failed |  (终态)
                        +---------+   +--------+
                          |     |
             回执 done     |     |  回执 failed
                          v     v
                     +------+  +--------+
                     | done |  | failed |  (终态)
                     +------+  +--------+

  派发时无可用 adapter：
     (无状态) ----> unsupported (终态)

  owner 取消（从非终态任意状态）：
     dispatched / running ----> cancelled (终态)
```

说明：
- 派发入口只有一条：routeMessage 收到 intent=task 且没有 task_status 的帧。
- 回执入口：intent=task 且 task_status 已设置；若带 task_id 就更新台账状态。
- unsupported 是派发阶段直接落定的，不是回执回来的。
- 终态：done、failed、cancelled、unsupported。进入终态后不再变化。

### 2.3 cancel 规则

- 只有 owner 能发起 cancel。
- 只有非终态（dispatched、running）能被取消，取消后进 cancelled。
- 已经是终态的任务再 cancel 一律拒绝。
- cancel 之后网关做的事：更新台账状态为 cancelled，广播一条 task_event。
- cancel 不向执行任务的 adapter 发任何帧。adapter 不会因为 cancel 收到通知，也就没有"停止执行"这个动作。见第 8 节。

## 3. 为什么用 task_event 新帧而不是复用 message 帧

核心区别是语义：message 帧是聊天内容，task_event 帧是状态通知。

- message 帧进 messages 历史表，是"群里说过的话"。翻聊天记录能看到。
- task_event 帧不进 messages 历史表，是"任务状态变了一下"的通知。它走的是正常广播/补发通道，所以断线重连能补到，但它的身份是事件，不是聊天消息。

带来的好处：
- 面板只订阅 task_event，不翻 messages 历史。打开面板就是订阅事件流，不依赖历史表。
- 聊天和任务状态两条线互不污染。有人在群里聊别的，不会进面板。
- 补发通道复用同一套 gseq 逻辑，不用为事件单独造一套重传机制。

代价：
- task_event 不进历史表，重启后历史事件没了，看面板得走 REST 拉台账。见第 8 节。

task_event 帧结构：
- type = "task_event"
- sender 固定为 "gateway"
- payload = { task_id, status, assignee?, title?, note? }
- 带 gseq
- 走正常广播/补发通道

## 4. 台账表设计与幂等

### 4.1 表：tasks

字段：

| 字段 | 说明 |
| --- | --- |
| task_id | 任务 ID，主键 |
| status | 状态，取值见第 2 节 |
| assignee | 被派发的 adapter；unsupported 时为空 |
| title | 任务标题，来自原帧 |
| note | 备注，比如 unsupported 的原因 |
| created_at | 创建时间 |
| updated_at | 最近更新时间 |

索引：
- 主键 task_id。
- status 上建索引，用于按状态查。
- assignee 上建索引，用于按 adapter 查。

### 4.2 幂等

重复派发同一个 task_id 时，覆盖更新，不报错、不产生重复行。

具体行为：
- 派发路径写台账用 upsert 语义：task_id 已存在就更新 status、assignee、title、note、updated_at，不存在就插入。
- 回执路径按 task_id 更新状态，同样覆盖。
- 因为 task_id 是主键，同一 task_id 反复写只会有一行，最后一次写的状态生效。

这样做的目的：网络重发、客户端重试、adapter 重复回执，都不会在台账里留下多行，也不会因为主键冲突把流程打断。

## 5. 未读语义

### 5.1 since_id 语义

接口：GET /api/rooms/:room/unread?since_id=

- 返回该房间里 id > since_id 的消息数量，以及这些消息里的最大 id。
- since_id 是"我已经看到这里了"的水位线，id 大于它的才算未读。
- 房间不存在或参数缺失按接口既有约定处理。

### 5.2 localStorage key 规则

- Web 把 lastReadId 存在 localStorage。
- key 里包含房间名，也就是每个房间各存一份已读水位，房间之间不互相干扰。
- 进任务面板时，如果收到新消息，显示"N 条新消息"的 pill。
- 点 pill：标已读（更新 lastReadId），并滚到底部。

### 5.3 多标签页竞态的诚实说明

同一个浏览器开多个标签页时，每个标签页各自读写 localStorage 里的 lastReadId。存在竞态：

- 标签页 A 标已读写入水位，标签页 B 手里的水位还是旧的，B 可能仍显示未读 pill，直到它自己重新读一次。
- 两个标签页几乎同时标已读，后写的覆盖先写的。因为都是把水位往后推，最终结果一般不会退步，但中间态可能不一致。
- 没有做跨标签页的锁或广播同步。

结论：多标签页下未读状态可能短暂不一致，刷新或重新进入面板会以 localStorage 当前值为准。这是已知行为，不是 bug 掩盖。

## 6. 部署架构

### 6.1 文本架构图

```
  浏览器 (Web 前端)
       |
       |  HTTP / WebSocket
       v
  +-----------------------------+
  |  网关 (node:22-slim 单镜像)  |
  |  - 直出 Web 静态文件          |
  |    PUBLIC_DIR=/app/public    |
  |  - 广播 / 补发 task_event    |
  |  - REST: /api/rooms/...      |
  +-----------------------------+
       |
       |  读写
       v
  +-----------------------------+
  |  /data  (数据卷)             |
  |  SQLite (WAL 模式)           |
  +-----------------------------+
```

### 6.2 说明

- 单镜像：node:22-slim，网关和 Web 静态文件在同一个镜像里。
- 网关直出 Web 静态文件，PUBLIC_DIR=/app/public。
- 数据落在 /data，SQLite 跑 WAL 模式。
- /data 挂成数据卷，容器重建数据还在。
- compose 一键启动，卷映射到 /data。

## 7. 协议 v1.2 变更与兼容性

### 7.1 变更

- 新增 task_event 帧类型，用于任务状态通知。
- hello 的 protocol_version 升到 "1.2"。

### 7.2 兼容性

- 旧客户端连新网关：会被 4400 拒绝。原因是客户端 protocol_version 不是 "1.2"，网关不接受。
- 新客户端连新网关：正常。
- 升级顺序上，客户端和网关要一起升到 v1.2。

## 8. 已知限制

这一节只写实现里确实没做的，不写计划外的好话。

1. 单房间 lobby。
   当前只支持一个房间 lobby，多房间待 v0.4。

2. cancel 只通知面板，不强制 adapter 停手。
   cancel 做的是：更新台账、广播 task_event。它不向执行任务的 adapter 发任何帧。adapter 收到 cancel 靠自觉——也就是说，当前实现里 adapter 根本收不到 cancel 通知，任务是否真的停下来取决于 adapter 自己的行为。v0.4 再做 cancel 帧。

3. task_event 不进 messages 历史表。
   task_event 走广播/补发通道，但没写进 messages 历史表。重启后事件流没了，看面板要走 REST 拉台账。
