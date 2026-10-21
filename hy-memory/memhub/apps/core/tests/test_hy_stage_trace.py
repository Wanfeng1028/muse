import asyncio
import json
import runpy
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/hy_stage_trace.py"


def observer():
    return runpy.run_path(str(SCRIPT))["HyStageTrace"]()


def test_observer_returns_native_results_without_editing_or_requesting_models(tmp_path):
    extraction = SimpleNamespace(
        success=True,
        info={"memory": [{"content": "An assistant proposal", "owner": "agent"}]},
        raw_response="must not persist this envelope",
        _actual_prompt="must not persist a model prompt",
    )
    reconciled = SimpleNamespace(
        success=True,
        ops=[SimpleNamespace(op="ADD", content="An assistant proposal", owner=None)],
    )
    calls = []

    class Extractor:
        async def extract(self, **kwargs):
            calls.append(("extract", kwargs))
            return extraction

    class Reconciler:
        async def reconcile(self, **kwargs):
            calls.append(("reconcile", kwargs))
            return reconciled

    original = Extractor.extract
    trace = observer()

    async def scenario():
        with trace.install(Extractor, Reconciler):
            assert await Extractor().extract(content="original") is extraction
            assert await Reconciler().reconcile(new_memories=["original"]) is reconciled

    asyncio.run(scenario())
    assert calls == [
        ("extract", {"content": "original"}),
        ("reconcile", {"new_memories": ["original"]}),
    ]
    assert Extractor.extract is original
    assert [event["stage"] for event in trace.events] == ["extract", "reconcile"]
    assert trace.events[1]["items"][0]["owner"] is None
    path = tmp_path / "trace.json"
    trace.save(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    saved = path.read_text()
    assert "must not persist" not in saved
    assert json.loads(saved)["first_import_acceptance"] is False
    with pytest.raises(FileExistsError):
        trace.save(path)


def test_observer_redacts_content_without_recording_prompts_or_exception_details():
    secret = "sk-" + "x" * 24

    class Extractor:
        async def extract(self):
            return SimpleNamespace(
                success=True,
                info={
                    "memory": [{"content": f"API key: {secret}", "owner": "user"}],
                    "tool_calls": [{"api_key": secret}],
                },
            )

    class Reconciler:
        async def reconcile(self):
            raise RuntimeError(f"private error: {secret}")

    trace = observer()

    async def scenario():
        with trace.install(Extractor, Reconciler):
            await Extractor().extract()
            with pytest.raises(RuntimeError):
                await Reconciler().reconcile()

    asyncio.run(scenario())
    encoded = json.dumps(trace.events)
    assert secret not in encoded
    assert "private error" not in encoded
    assert "tool_calls" not in encoded
    assert "redacted-secret" in encoded
    assert trace.events[-1]["error_type"] == "RuntimeError"
