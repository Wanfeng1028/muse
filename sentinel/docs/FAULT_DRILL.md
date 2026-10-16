./scripts/fault-drill.sh
```

退出码语义：

- `0`：13 项全过
- `1`：任一步骤失败
- `2`：环境缺失

## 4. 演练步骤与预期

### 阶段 0：准备（约 7s）

做什么：启动两个假目标（`python3 http.server`，`127.0.0.1:18901` / `127.0.0.1:18902`）；构建 sentinel。

预期：两个假目标可访问，sentinel 构建完成。

### 阶段 1：启动（约 1s）

做什么：启动 webhook sink（`127.0.0.1:18903`，把每次 POST body 追加写 `hooks.log`）；启动 sentinel（端口 `18200`，`SENTINEL_TICK_SEC=2`，`SENTINEL_CHECK_RETRY_MAX=2`，`SENTINEL_WEBHOOK_URL` 指向 sink）。

预期：`/api/healthz` 就绪。

### 阶段 2：建监控（约 2s）

做什么：`POST /api/monitors` 建 `drill-mon-1`（id=3）、`drill-mon-2`（id=4），`kind=http`、`interval_sec=10`、`timeout_sec=3`。

预期：`/api/overview` 的 up 计数到 2。

### 阶段 3：目标全挂（约 13s）

做什么：kill 两个假目标。

预期：`/api/incidents` 出现 2 条 `ended_at` 为 null 的 open 事件；webhook sink 收到告警 POST 且 body 含监控名（通知链路真实打通）。

### 阶段 4：恢复闭环（约 16s）

做什么：重启两个假目标。

预期：两条事件的 `ended_at` 均变为非 null（事件闭环）；`hooks.log` 新增恢复类通知。

## 5. 实测结果（2026-10-17）

- 总结果：13/13 通过
- 总耗时：39s
- 各阶段耗时：阶段 0 约 7s、阶段 1 约 1s、阶段 2 约 2s、阶段 3 约 13s、阶段 4 约 16s
- 阶段 3：`/api/incidents` 出现 2 条 `ended_at` 为 null 的 open 事件；webhook sink 收到告警 POST，body 含监控名
- 阶段 4：两条事件 `ended_at` 均变为非 null；`hooks.log` 新增恢复类通知

## 6. 未覆盖项

本次演练覆盖的是“探针目标全挂 → 事件 → 通知 → 恢复闭环”。

以下情况没有演练：

- sentinel 进程本身被 `kill -9`
- 磁盘满
- 真实断网

下次演练建议：补上这三项的演练脚本与判定标准。

## 7. 排障

演练失败时，在 trap 清理前先另开一个终端看日志：

```
tail -f .drill-tmp/sentinel.log
