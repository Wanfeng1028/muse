import asyncio
import json

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)


class _StubAnswerer:
    def __init__(self, events: tuple[dict, ...]) -> None:
        self.events = events
        self.calls: list[tuple[str, str]] = []
        self.last_workspace_path: str | None = None

    async def answer_stream(
        self,
        question: str,
        *,
        scope: str = "all-apps",
        workspace_path: str | None = None,
    ):
        self.calls.append((question, scope))
        self.last_workspace_path = workspace_path
        for event in self.events:
            yield event


def _sse_events(text: str) -> list[dict]:
    return [
        json.loads(frame.strip().removeprefix("data:").strip())
        for frame in text.split("\n\n")
        if frame.strip().startswith("data:")
    ]


def test_ask_stream_endpoint_emits_recall_deltas_and_final(tmp_path) -> None:
    async def scenario() -> None:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer local-token",
                    "Origin": "http://127.0.0.1:5173",
                },
            ) as client,
        ):
            evidence = app.state.evidence_store.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="conversation",
                    message_id="message",
                    correlation_id="message",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim="我要求看板只用真实数据。",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record
            created = await client.post(
                "/api/v1/memories",
                json={
                    "request_id": "create-1",
                    "draft": {
                        "user_id": "local",
                        "kind": "chat",
                        "content": "用户要求看板只用真实数据。",
                        "scopes": ["all-apps"],
                        "evidence_ids": [evidence.evidence_id],
                    },
                },
            )
            memory = app.state.memory_governance_store.get(
                created.json()["memory_id"],
                user_id="local",
            )
            stub = _StubAnswerer(
                (
                    {"type": "recall", "memories": (memory,)},
                    {"type": "delta", "text": "你要求"},
                    {"type": "delta", "text": "真实数据。"},
                    {
                        "type": "final",
                        "answer": "你要求真实数据。",
                        "memories": (memory,),
                        "mode": "generated",
                        "retrieval": {"semantic_state": "failed"},
                    },
                )
            )
            app.state.memory_answerer = stub

            response = await client.post(
                "/api/v1/memories/ask/stream",
                json={"question": "我对数据有什么要求？", "scope": "all-apps"},
            )

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            events = _sse_events(response.text)
            assert [event["type"] for event in events] == [
                "recall",
                "delta",
                "delta",
                "final",
            ]
            assert events[0]["memories"][0]["memory_id"] == memory.memory_id
            assert (
                "".join(event["text"] for event in events if event["type"] == "delta")
                == events[-1]["answer"]
            )
            assert events[-1]["retrieval"] == {"semantic_state": "failed"}
            assert stub.calls == [("我对数据有什么要求？", "all-apps")]

    asyncio.run(scenario())


def test_ask_stream_endpoint_requires_the_local_token(tmp_path) -> None:
    async def scenario() -> None:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://127.0.0.1:5173"},
            ) as client,
        ):
            response = await client.post(
                "/api/v1/memories/ask/stream",
                json={"question": "我是谁？", "scope": "all-apps"},
            )

            assert response.status_code == 401

    asyncio.run(scenario())
