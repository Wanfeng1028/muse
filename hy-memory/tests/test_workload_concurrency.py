import asyncio

import pytest

import hy_memory.core.workload as workload


@pytest.mark.asyncio
async def test_global_llm_gate_bounds_concurrent_calls(monkeypatch):
    monkeypatch.setenv("MEMORY_LLM_GLOBAL_CONCURRENCY", "4")
    workload._states.clear()
    active = maximum = 0
    lock = asyncio.Lock()

    async def one():
        nonlocal active, maximum
        async with workload.llm_slot():
            async with lock:
                active += 1
                maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            async with lock:
                active -= 1

    await asyncio.gather(*(one() for _ in range(50)))
    assert maximum == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "env_name,context_name,expected,kwargs",
    [
        ("MEMORY_DYNAMIC_EPISODE_CONCURRENCY", "episode_slot", 5, {}),
        ("MEMORY_GRAPH_PROJECTION_CONCURRENCY", "graph_slot", 4, {}),
        ("MEMORY_KUZU_PROJECTION_CONCURRENCY", "graph_slot", 1, {"kuzu": True}),
        ("MEMORY_EMBEDDING_GLOBAL_CONCURRENCY", "embedding_slot", 7, {}),
        ("MEMORY_RECONCILE_RETRIEVAL_CONCURRENCY", "reconcile_retrieval_slot", 6, {}),
        ("MEMORY_RECONCILE_LOCAL_RETRIEVAL_CONCURRENCY", "reconcile_retrieval_slot", 2, {"local": True}),
    ],
)
async def test_resource_gates_bound_tasks(
    monkeypatch, env_name, context_name, expected, kwargs,
):
    monkeypatch.setenv(env_name, str(expected))
    workload._states.clear()
    active = maximum = 0
    lock = asyncio.Lock()
    context = getattr(workload, context_name)

    async def one():
        nonlocal active, maximum
        async with context(**kwargs):
            async with lock:
                active += 1
                maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            async with lock:
                active -= 1

    await asyncio.gather(*(one() for _ in range(30)))
    assert maximum == expected


@pytest.mark.asyncio
async def test_derived_llm_has_its_own_shared_budget(monkeypatch):
    monkeypatch.setenv("MEMORY_LLM_GLOBAL_CONCURRENCY", "20")
    monkeypatch.setenv("MEMORY_DERIVED_LLM_CONCURRENCY", "3")
    workload._states.clear()
    active = maximum = 0

    async def one():
        nonlocal active, maximum
        async with workload.workload_scope("derived"):
            async with workload.llm_slot():
                active += 1
                maximum = max(maximum, active)
                await asyncio.sleep(0.01)
                active -= 1

    await asyncio.gather(*(one() for _ in range(30)))
    assert maximum == 3
