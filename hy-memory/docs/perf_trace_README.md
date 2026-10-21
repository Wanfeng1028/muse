# 性能与 Pipeline 可观测性

Hy Memory 提供三类互补的观测数据：

1. `TRACE_PERF`：写入链路的 INFO 日志，适合快速 grep 单次请求。
2. Pipeline logs：环节级结构化记录，可写 JSONL，并可通过 `MemoryInspector` 查询持久化 trace。
3. System metrics：按时间窗口聚合的进程负载、延迟和存储操作统计。

三者都使用 `request_id` 关联请求，但用途和字段并不相同。

## 1. TRACE_PERF 日志

写入链路会输出以下格式的 INFO 日志：

```text
TRACE_PERF [<request_id>] <STAGE> <key=value ...>
```

当前可能出现的 System 1 stage：

| Stage | 含义 | 主要字段 |
|---|---|---|
| `S1_START` | 开始实际处理写入 | `waiting`, `user` |
| `S1_L1_DONE` | L1_RAW embedding 与持久化阶段完成 | `l1_ms` |
| `S1_EXTRACT_DONE` | Extractor 完成 | `extract_ms`, `summary_ms`, `memory` |
| `S1_RECONCILE_DONE` | Reconcile 决策完成 | `ops`, `candidates`，以及各 op 数量 |
| `S1_UPDATE_BATCH_DONE` | 批量 UPDATE 完成 | `nodes` |
| `S1_ADD_BATCH_DONE` | 批量 ADD 完成 | `nodes` |
| `S1_INTENTION_DONE` | L7 intention 写入完成 | `intentions` |
| `S1_PERSIST_DONE` | 抽取结果持久化完成 | `ops` |
| `S1_WORKFLOW_DONE` | System 1 workflow 完成 | `workflow_ms` |

并非每个请求都会产生全部 stage。例如 lite 模式、空抽取、没有 intention 或没有批量 ADD/UPDATE 时，对应日志不会出现。

按请求查看：

```bash
grep 'TRACE_PERF \[<request_id>\]' app.log
```

`hy_memory/core/workload.py` 也会输出带 `TRACE_PERF` 前缀的 workload 排队日志，但格式不是上述 `[request_id] STAGE` 形式，分析时不要将两者混为一类。

### 写入返回的 timing

chat 写入会在可用时返回 System 1 timing：

```python
result = client.add("User likes coffee", user_id="u1")
print(result.get("timing", {}))
```

字段包括：

```text
sys1_waiting_ms
sys1_l1_process_ms
sys1_workflow_ms
sys1_ops_avg_ms
```

这些是阶段耗时，不是固定服务等级阈值。合理范围取决于 LLM、embedding、向量库、机器资源和并发量。

## 2. Pipeline logs

Pipeline logs 有两种输出，字段契约不同。

JSONL 文件主要字段：

```text
request_id, namespace, user_id, agent_id, session_id,
step, prompt, content, parsed, memory_ids,
tokens, elapsed_ms, timestamp
```

Inspector 读取的持久化 Pipeline Trace 主要字段：

```text
request_id, namespace, user_id, agent_id, session_id,
step, prompt, response, parsed, memory_ids,
elapsed_ms, prompt_tokens, completion_tokens, total_tokens,
event_at_ms, created_at
```

### 两种输出

- JSONL log 默认启用，目录优先级为：`MEMORY_LOG_DIR` → `MEMORY_TRACE_LOG_DIR` → `{MEMORY_DATA_DIR}/logs/pipeline`。
- 持久化 trace 由 `MEMORY_PIPELINE_TRACE_ENABLED` 控制，默认开启，写入 cache backend 供 Inspector 查询。

两种写入都是 best-effort；观测写入失败不应中断主读写流程。

默认 `MEMORY_LOG_LLM_CONTENT=false`，`prompt` 和 LLM 输出（JSONL 的 `content`、持久化
Trace 的 `response`）只保留长度与摘要哈希。只有显式设置为 `true` 才会记录完整输入
输出；生产环境启用前应评估敏感信息风险。

### 常见 step

写入链常见 step：

```text
S1_EMBED
S1_L1_UPSERT
EXTRACT
SEARCH_QUERY
RECONCILE_CANDIDATES
RECONCILE
RECONCILE_APPLY
TOOL_CALLS
WRITE_SUMMARY
S1_AGENT_FAILED
S1_L1_ROLLBACK
```

working/coding 链常见 step：

```text
CODING_JUDGE
CODING_EXTRACT
CODING_RECONCILE
READ_CODING_EMBED
READ_CODING_VDB
READ_CODING_RESULT
```

chat search 的 read-side step 统一以 `READ_` 开头。当前定义包括：

```text
READ_SCENE_JUDGE
READ_REQUEST
READ_EMBED_QUERY
READ_INTENT
READ_RECALL_VEC
READ_HIDDEN_L0_CONTEXT
READ_KEYWORD_EMBED
READ_TAG_MATCH
READ_RECALL_TAG
READ_BM25
READ_RRF
READ_MERGE_SCHEMA
READ_EVOLUTION
READ_INTENTION
READ_GRAPH_RERANK
READ_SUMMARY
```

实际 step 取决于 reader、scene、配置和召回结果，不保证每次搜索都包含完整列表。

### 使用 MemoryInspector

`MemoryInspector` 是公开 API：

```python
from hy_memory import HyMemoryClient, MemoryInspector

client = HyMemoryClient(mode="pro")
inspector = MemoryInspector(client)

write_result = client.add("User likes coffee", user_id="u1")
write_trace = inspector.get_full_trace(write_result["request_id"])

search_result = client.search("What does the user like?", user_ids=["u1"])
read_trace = inspector.get_read_trace(search_result["request_id"])

extract_logs = inspector.get_pipeline_logs(
    request_id=write_result["request_id"],
    step="EXTRACT",
)
```

异步调用对应 `async_get_full_trace()`、`async_get_read_trace()` 和 `async_get_pipeline_logs()`。

## 3. System metrics

进程级 metrics 当前收集：

- System 1 started、completed、failed 和 active 数量，以及各阶段平均耗时。
- 最近 60 秒完成量。
- VDB 与 Graph 操作数和平均耗时。

返回 schema 还保留 `active_sys2`、`queued_sys2`、`sys2_requests` 和 System 2 latency 字段；但当前生产链路没有调用 `sys2_enqueue()`、`sys2_start()`、`sys2_end()`，因此这些值不会自动反映 Ultra 后台任务。不要用它们判断当前 System 2 负载。

公开 SDK：

```python
metrics = client.get_metrics(minutes=10)
metrics = inspector.get_system_metrics(minutes=10)
metrics = await client.async_get_metrics(minutes=10)
```

HTTP Server 入口：

```text
GET /api/v1/metrics?minutes=10
```

主要返回字段：

```text
uptime_seconds
window_minutes
requests
avg_latency_ms
throughput
storage_ops
sys2_requests
since
```

没有样本的平均耗时或存储字段可能为空。指标按分钟聚合；cache backend 支持相关方法时会持久化，后台每分钟 flush，并清理 7 天前的数据。active/queued 与最近 60 秒 throughput 属于当前进程实时状态。

## 4. 定向验证

```bash
python -m pytest -q \
  tests/test_pipeline_observability.py \
  tests/test_op_trace_logs.py \
  tests/coding/test_coding_pipeline_log.py \
  tests/test_shared_runtime.py
```
