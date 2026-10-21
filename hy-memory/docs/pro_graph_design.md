# Graph Memory Architecture and Operations

This document describes the Graph features implemented by the current SDK.
It is intended for operators enabling Graph and maintainers working on
`pipelines/_graph`, `reader_base.py`, or a GraphStore backend.

Graph is an optional, fail-open enhancement. Vector retrieval remains the
source of truth: if Graph is unavailable, incomplete, or disabled, normal
memory search must continue to work.

## 1. Enabling Graph

Graph availability depends on the processing mode:

| Mode | Graph behavior |
|---|---|
| `lite` | Disabled |
| `pro` | Controlled by `MEMORY_ENABLE_GRAPH`, default `false` |
| `ultra` | Enabled |

The default backend is embedded Kuzu. Neo4j is available through the `graph`
optional dependency.

```bash
# Embedded, single-process deployment
MEMORY_MODE=pro
MEMORY_ENABLE_GRAPH=true
MEMORY_GRAPH_PROVIDER=kuzu
MEMORY_GRAPH_DB_PATH=/data/hy-memory/kuzu

# Multi-process or remote deployment
MEMORY_GRAPH_PROVIDER=neo4j
NEO4J_URL=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=secret
NEO4J_DATABASE=neo4j
```

Kuzu permits only one process to open a database path. Use Neo4j when several
workers must share the same Graph.

## 2. Write-side projection

When Graph and `MEMORY_GRAPH_WRITE` are enabled, persisted L2 facts are
projected into Graph asynchronously. Projection failures are logged and do not
roll back the VDB write.

### 2.1 Node model

An L2 fact is represented as `Memory(layer="l2_fact")`, not as `VdbRef`.
This allows the node to participate in Topic, Entity, relation, and temporal
edges. `VdbRef` remains the lightweight target used by L6 `DERIVED_FROM`
evidence links.

Graph projection does not replace the VDB. Content, vectors, event time, and
normal retrieval remain VDB-owned.

### 2.2 Edge sources

Current relation sources are:

| Relation | Source | Additional LLM call |
|---|---|---|
| `co_occurs` | L2 facts created in one write batch | No |
| `semantic_neighbor` | Reconcile candidates above `MEMORY_GRAPH_EDGE_MIN_SCORE` | No |
| `causes` | Reconcile `related` output | No additional call |
| `elaborates` | Reconcile `related` output | No additional call |
| `contrasts` | Reconcile `related` output | No additional call |
| `same_series` | Reconcile `related` output | No additional call |
| `TAGGED_WITH` | Memory tags projected to Topic nodes | No new memory LLM call |
| `MENTIONS` | NER entities projected to Entity nodes | No |
| `TEMPORAL_NEXT` | Optional event-time ordering | No |

`co_occurs` is bounded by `MEMORY_GRAPH_CO_OCCURS_MAX_BATCH` to prevent an
O(n²) edge explosion. `semantic_neighbor` is inexpensive but mostly repeats
information already present in vector similarity; typed and co-occurrence
relations usually carry more structural information.

### 2.3 Lifecycle synchronization

Graph state follows memory lifecycle changes:

- ADD projects the new active fact and its edges.
- UPDATE refreshes the projected node.
- SUPERSEDE and SHADOW retire the old projection from active retrieval.
- Search filters inactive or shadowed nodes even if stale edges remain.

Projection code lives in `hy_memory/pipelines/_graph/projector.py` and is
scheduled from `hy_memory/pipelines/writer.py`.

## 3. Read-side Graph usage

`legacy` and `hybrid` readers share the same Graph post-processing. The readers
differ only in candidate recall: `legacy` uses dense vectors; `hybrid` adds the
keyword/BM25 channel.

Enable Graph post-processing with:

```bash
MEMORY_GRAPH_RERANK_ENABLED=true
```

All Graph operations are fail-open. Exceptions return the pre-Graph candidate
order unless a test explicitly requests strict behavior.

### 3.1 A — Support propagation

Support propagation reranks candidates already present in the expanded recall
pool. It never adds a new candidate.

For candidate `v`, the implementation computes bounded support from recalled
neighbors and applies a small score adjustment:

```text
support(v) = sum(edge_prior(u,v) * score(u)) / sqrt(pool_degree(v))
score'(v)  = score(v) + beta * min(support(v), support_cap)
```

Relevant settings:

```bash
MEMORY_GRAPH_PROPAGATE_BETA=0.15
MEMORY_GRAPH_PROPAGATE_ITERS=1
MEMORY_GRAPH_SUPPORT_CAP=1.0
```

### 3.2 B — Bounded relation expansion

Relation expansion may nominate nodes outside the initial pool. Admission is
bounded by all of the following:

- traversal hop limit;
- seed score floor;
- prefilter and expansion limits;
- relation-type quota;
- semantic hard gate `sim(candidate) >= sim(seed) - delta`;
- final multi-channel scoring.

Admitted items are merged into a seed by default, so they do not consume an
extra top-k slot.

Core settings and current defaults:

```bash
MEMORY_GRAPH_RELAX_GAMMA=0.3
MEMORY_GRAPH_SEED_FLOOR=0.5
MEMORY_GRAPH_MAX_EXPAND=20
MEMORY_GRAPH_EXPAND_HOPS=2
MEMORY_GRAPH_EXPAND_PREFILTER_TOP_N=50
MEMORY_GRAPH_SEED_SIM_DELTA=0.2
MEMORY_GRAPH_EXPAND_MERGE_SEED=true
```

Set `MEMORY_GRAPH_RELAX_GAMMA=0` to disable relation expansion while retaining
support propagation and relation paths.

### 3.3 C — Relation paths

Relation paths preserve connection semantics that would be lost in a flat
memory list. The shared reader stores them independently from normal memories
in its diagnostic `ReadResponse.extra["related_paths"]` field:

```python
read_response.extra["related_paths"]
```

Each path contains the ordered nodes and relation types. Temporal edges also
include direction (`earlier -> later`).

```bash
MEMORY_GRAPH_PATH_ENABLED=true
MEMORY_GRAPH_PATH_HIGH_FLOOR=0.5
```

### 3.4 Relation-type priors

The reader weights an edge by both its stored weight and a relation-type prior.
Current priors are defined in `pipelines/_graph/rerank.py`:

| Relation | Prior |
|---|---:|
| `causes` | 0.90 |
| `elaborates` | 0.90 |
| `same_series` | 0.85 |
| `contrasts` | 0.70 |
| `temporal_next` | 0.70 |
| `co_occurs` | 0.55 |
| `episode` | 0.55 |
| untyped `related` | 0.50 |
| `semantic_neighbor` | 0.35 |

Higher priors are reserved for relations that provide information not already
encoded by vector similarity. The degree normalization and support cap prevent
high-degree nodes from dominating ranking.

## 4. Temporal edges and episodes

`MEMORY_GRAPH_TEMPORAL_SPINE=true` creates directed `TEMPORAL_NEXT` edges using
VDB `memory_at` values. Graph nodes do not own canonical event time; projection
resolves timestamps from VDB before building the spine.

Episodes are separate from Graph. `episode_id` groups memories belonging to one
discussion and can provide bounded candidate support even when Graph is off.

```bash
MEMORY_EPISODE_RECALL_ENABLED=false
MEMORY_EPISODE_RECALL_WEIGHT=0.7
MEMORY_EPISODE_SUMMARY_ENABLED=false
```

Detailed Episode and summary settings are listed in `docs/env_reference.md`.

## 5. Backfill and rebuild

Existing VDB facts can be projected with:

```python
client.build_memory_graph(
    user_id="u1",
    agent_id=None,      # None means all agents for the user
    clear_first=False,
)
```

Backfill can reconstruct:

- L2 Memory nodes;
- Topic and Entity projections;
- `semantic_neighbor` edges from stored vectors;
- optional `TEMPORAL_NEXT` edges.

Backfill cannot reconstruct batch `co_occurs` edges or LLM typed relations,
because the original write-batch and reconcile decisions are not recoverable.

Use `clear_first=True` after changing projection rules. It clears the selected
L2 projection and orphaned Topic/Entity nodes without deleting System 2 L6
schemas.

## 6. Observability

The shared reader records internal diagnostics in:

```python
read_response.extra["graph_rerank"]   # edge, propagation, and admission stats
read_response.extra["related_paths"]  # decorated relation paths
```

`HyMemoryClient.search()` does not currently forward these two internal fields.
For public operational visibility, use pipeline traces: read-side Graph work is
recorded as `READ_GRAPH_RERANK`, while write projection reports `GRAPH_PROJECT`
statistics and errors.

## 7. Implementation map

| Responsibility | Module |
|---|---|
| Projection and lifecycle synchronization | `hy_memory/pipelines/_graph/projector.py` |
| Support, expansion, paths, priors | `hy_memory/pipelines/_graph/rerank.py` |
| Reader integration | `hy_memory/pipelines/reader_base.py` |
| Write scheduling | `hy_memory/pipelines/writer.py` |
| Relation output parsing | `hy_memory/agent/reconciler.py` |
| GraphStore interface | `hy_memory/data/graph_store_base.py` |
| Kuzu backend | `hy_memory/data/graph_store_kuzu.py` |
| Neo4j backend | `hy_memory/data/graph_store_neo4j.py` |
| Graph backfill API | `HyMemoryClient.build_memory_graph()` |

Tests covering these contracts live primarily in `tests/test_memory_graph.py`,
`tests/test_graph_edge_idempotency.py`, and `tests/test_profile_evidence.py`.
