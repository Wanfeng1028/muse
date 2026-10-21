import asyncio
import threading
import time

import httpx
import pytest
from test_memory_qa import _grounded_setup, _ndjson_stream
from test_onboarding_profile import FakeGraph, _app, _client, _setup, _supervisor

from one_memory.memory_qa import MemoryAnswerer
from one_memory.model_probe import ModelProber
from one_memory.secrets import SecretStoreUnavailableError


@pytest.mark.parametrize(
    "operation,args",
    [
        ("digest", ()),
        ("graph_snapshot", ()),
        ("graph_width_mismatch", ()),
        ("semantic_search", ("example",)),
        ("update_hy_memory", ("id", "corrected")),
        ("delete_hy_memory", ("id",)),
        ("decide_graph_width", ("keep_existing",)),
    ],
)
@pytest.mark.parametrize("phase", ["active", "secret"])
def test_credentials_do_not_block_the_event_loop(tmp_path, monkeypatch, operation, args, phase):
    stores = _setup(tmp_path)
    supervisor = _supervisor(tmp_path, stores, FakeGraph(()))
    method = "active_identity" if phase == "active" else "resolve_snapshot_secret"
    original = getattr(supervisor.profiles, method)
    called = threading.Event()

    def waiting(*args, **kwargs):
        called.set()
        time.sleep(0.25)
        return original(*args, **kwargs)

    monkeypatch.setattr(supervisor.profiles, method, waiting)

    async def scenario():
        task = asyncio.create_task(getattr(supervisor, operation)(*args))
        started = time.monotonic()
        await asyncio.sleep(0.04)
        elapsed = time.monotonic() - started
        # Some graph operations have no fake implementation; those exceptions
        # are irrelevant to whether a credential read stops the event loop.
        await asyncio.gather(task, return_exceptions=True)
        assert called.is_set()
        assert elapsed < 0.18, f"Credential wait blocked the loop for {elapsed:.3f}s"

    asyncio.run(scenario())


def test_disabled_automatic_processing_does_not_digest_onboarding(tmp_path):
    async def scenario():
        app = _app(tmp_path)
        async with app.router.lifespan_context(app), _client(app) as client:
            app.state.settings.automatic_memory_processing = False
            calls = []

            async def digest():
                calls.append(True)
                return {}

            app.state.memory_processing_supervisor.digest = digest
            response = await client.post("/api/v1/onboarding/complete")
            assert response.status_code == 200
            assert calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize("stream", [False, True])
def test_answering_reads_credentials_off_loop(tmp_path, monkeypatch, stream):
    governance, profiles, secrets = _grounded_setup(tmp_path)
    owner = threading.get_ident()
    for method in ("active", "resolve_snapshot_secret"):
        original = getattr(profiles, method)

        def checked(*args, _original=original, **kwargs):
            assert threading.get_ident() != owner
            return _original(*args, **kwargs)

        monkeypatch.setattr(profiles, method, checked)
    body = '{"citations":["memory-real-data"],"answer":"使用真实数据"}'
    transport = (
        _ndjson_stream((body,))
        if stream
        else httpx.MockTransport(
            lambda request: httpx.Response(200, json={"message": {"content": body}})
        )
    )
    answerer = MemoryAnswerer(
        governance=governance, profiles=profiles, secrets=secrets, transport=transport
    )

    async def scenario():
        if stream:
            events = [item async for item in answerer.answer_stream("看板真实数据")]
            assert events[-1]["mode"] == "generated"
        else:
            assert (await answerer.answer("看板真实数据")).mode == "generated"

    asyncio.run(scenario())


def test_model_probe_credential_lookup_is_off_loop(tmp_path, monkeypatch):
    _, profiles, secrets = _grounded_setup(tmp_path)
    profile = profiles.active(secrets)
    owner = threading.get_ident()
    for method in ("require", "secret_ref", "record_capabilities"):
        original = getattr(profiles, method)

        def checked(*args, _original=original, **kwargs):
            assert threading.get_ident() != owner
            return _original(*args, **kwargs)

        monkeypatch.setattr(profiles, method, checked)
    prober = ModelProber(
        store=profiles,
        secrets=secrets,
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    asyncio.run(prober.probe(profile.profile_id))


def test_unavailable_credentials_keep_governed_graph_readable(tmp_path, monkeypatch):
    async def scenario():
        app = _app(tmp_path)
        async with app.router.lifespan_context(app), _client(app) as client:

            def denied(*args):
                raise SecretStoreUnavailableError("private-system-error")

            monkeypatch.setattr(app.state.model_profile_store, "active", denied)
            response = await client.get("/api/v1/memories/graph")
            assert response.status_code == 200
            assert response.json()["hy_graph_available"] is False
            assert "private-system-error" not in response.text
            assert (await client.get("/api/v1/health")).status_code == 200

    asyncio.run(scenario())
