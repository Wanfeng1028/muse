"""The objective names `recall` and requires BOTH paths: raw and memory.

Verified against a real Core with seeded evidence and one governed memory:
asking for `raw` returns the stored verbatim and leaves `memory` as
`not_requested`; asking for `memory` returns the governed memory and leaves
`raw` as `not_requested`. That the unrequested side is marked, rather than
silently empty, is what proves the filter is actually applied.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings


def _seed(data_dir) -> tuple[str, str]:
    """One evidence row and one governed memory; return their verbatim/content."""
    verbatim = "帮我总结一下 SQLite 的写锁调优方法"
    memory = "用户偏好：数据库调优时优先看写入批处理和读池容量，不要一上来就换引擎。"

    connection = sqlite3.connect(data_dir / "one-memory.sqlite3")
    try:
        cursor = connection.cursor()
        columns = [row[1] for row in cursor.execute("PRAGMA table_info(evidence)")]
        row: dict[str, object] = {}
        for column in columns:
            if column == "evidence_id" or column == "idempotency_key":
                row[column] = str(uuid.uuid4())
            elif column in ("user_id", "source_id"):
                row[column] = "local" if column == "user_id" else "codex"
            elif column in ("conversation_id", "message_id"):
                row[column] = str(uuid.uuid4())
            elif column == "role":
                row[column] = "user"
            elif column == "written_by":
                row[column] = "person"
            elif column == "verbatim":
                row[column] = verbatim
            elif column in ("created_at", "updated_at", "imported_at", "recorded_at"):
                row[column] = "2026-09-26T00:00:00Z"
            elif column == "revision" or column == "source_ordinal":
                row[column] = 1
            elif column.endswith("_hash") or column == "fingerprint":
                row[column] = str(uuid.uuid4())[:32]
        names = ",".join(row)
        markers = ",".join(["?"] * len(row))
        cursor.execute(f"INSERT INTO evidence ({names}) VALUES ({markers})", list(row.values()))

        memory_columns = [r[1] for r in cursor.execute("PRAGMA table_info(governed_memories)")]
        memory_row: dict[str, object] = {}
        for column in memory_columns:
            if column == "memory_id":
                memory_row[column] = str(uuid.uuid4())
            elif column == "user_id":
                memory_row[column] = "local"
            elif column == "kind":
                memory_row[column] = "working"
            elif column == "status":
                memory_row[column] = "confirmed"
            elif column == "content":
                memory_row[column] = memory
            elif column in ("scopes_json", "tags_json"):
                memory_row[column] = "[]"
            elif column == "origin":
                memory_row[column] = "manual"
            elif column == "revision":
                memory_row[column] = 1
            elif column in ("created_at", "updated_at"):
                memory_row[column] = "2026-09-26T00:00:00Z"
        names = ",".join(memory_row)
        markers = ",".join(["?"] * len(memory_row))
        cursor.execute(
            f"INSERT INTO governed_memories ({names}) VALUES ({markers})",
            list(memory_row.values()),
        )
        connection.commit()
    finally:
        connection.close()
    return verbatim, memory


def _client(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=data_dir,
            source_home=tmp_path,
            api_token=SecretStr("test-token"),
        )
    )
    return (
        app,
        data_dir,
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "Authorization": "Bearer test-token",
                "Origin": "http://127.0.0.1:5173",
            },
        ),
    )


@pytest.mark.anyio
async def test_raw_path_returns_verbatim_and_leaves_memory_unrequested(tmp_path) -> None:
    app, data_dir, client = _client(tmp_path)
    async with app.router.lifespan_context(app), client:
        # Seed inside the lifespan: the schema is created on startup, so seeding
        # before it yields no columns and an empty INSERT.
        verbatim, _ = _seed(data_dir)
        response = await client.post(
            "/api/v1/context/search",
            json={
                "query": verbatim,
                "kinds": ["raw"],
                "limit": 5,
                "character_budget": 2000,
                "timeout_ms": 5000,
            },
        )

    assert response.status_code == 200, response.text
    document = response.json()
    assert document["paths"]["raw"]["status"] == "ok"
    assert document["paths"]["memory"]["status"] == "not_requested", "memory must not run"
    texts = [message["text"] for item in document["items"] for message in item.get("messages", [])]
    assert verbatim in texts, "raw path must return the stored verbatim"


@pytest.mark.anyio
async def test_memory_path_returns_governed_memory_and_leaves_raw_unrequested(tmp_path) -> None:
    app, data_dir, client = _client(tmp_path)
    async with app.router.lifespan_context(app), client:
        _, memory = _seed(data_dir)
        response = await client.post(
            "/api/v1/context/search",
            json={
                "query": "数据库调优偏好",
                "kinds": ["memory"],
                "limit": 5,
                "character_budget": 2000,
                "timeout_ms": 5000,
            },
        )

    assert response.status_code == 200, response.text
    document = response.json()
    assert document["paths"]["memory"]["status"] == "ok"
    assert document["paths"]["raw"]["status"] == "not_requested", "raw must not run"
    contents = [item["content"] for item in document["items"]]
    assert memory in contents, "memory path must return the governed memory"
