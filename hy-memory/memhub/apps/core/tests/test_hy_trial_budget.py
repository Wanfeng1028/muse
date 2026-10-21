"""Offline proofs for the real-model acceptance budget (no network, no Keychain).

`scripts/hy_trial_budget.py` is the acceptance stop-loss: the real lifecycle
spends money and exports memory, so every path that could let spend go unknown
must fail closed. These tests use `httpx.MockTransport` only.
"""

import asyncio
import json
import runpy
import stat
import time
from pathlib import Path

import httpx
import pytest

_MODULE = None


def budget_module():
    """Load once so exception classes keep a stable identity across calls."""
    global _MODULE
    if _MODULE is None:
        script = Path(__file__).resolve().parents[3] / "scripts/hy_trial_budget.py"
        _MODULE = runpy.run_path(str(script))
    return _MODULE


def budget_type():
    return budget_module()["HyTrialBudget"]


def poisoned_error(module):
    return module["HyTrialLedgerPoisonedError"]


def make(path, *, requests=8, seconds=30, tokens=1000, per_request=200):
    return budget_type()(
        path,
        max_requests=requests,
        max_seconds=seconds,
        max_reported_tokens=tokens,
        per_request_max_tokens=per_request,
    )


def usage(total):
    async def handler(request):
        return httpx.Response(200, json={"usage": {"total_tokens": total}})

    return handler


def test_sol1_a_reservation_blocks_a_request_that_would_overshoot_the_ceiling(tmp_path):
    """Sol #1: the ceiling must bind *before* a request, not only after usage."""
    budget = make(tmp_path / "l.jsonl", tokens=500, per_request=200)
    seen = []

    async def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"usage": {"total_tokens": 180}})

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                await client.post("https://api.deepseek.com/chat/completions", json={})
                # 180 settled; the next 200-reservation would reserve 380 <= 500,
                # so it is allowed; a third would exceed and must be refused
                # *before* any send.
                await client.post("https://api.deepseek.com/chat/completions", json={})
                with pytest.raises(RuntimeError, match="hy_trial_token_budget"):
                    await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())
    assert len(seen) == 2


def test_sol1_a_single_reservation_larger_than_the_ceiling_sends_nothing(tmp_path):
    budget = make(tmp_path / "l.jsonl", tokens=100, per_request=200)
    seen = []

    async def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"usage": {"total_tokens": 1}})

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(RuntimeError, match="hy_trial_token_budget"):
                    await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())
    assert seen == []


def test_sol1_reservation_is_persisted_and_settled_in_the_ledger(tmp_path):
    ledger = tmp_path / "l.jsonl"
    budget = make(ledger, tokens=1000, per_request=200)

    async def handler(request):
        return httpx.Response(200, json={"usage": {"total_tokens": 120}})

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())
    kinds = [json.loads(line)["kind"] for line in ledger.read_text().splitlines()]
    assert "reserve" in kinds and "settle" in kinds


@pytest.mark.parametrize(
    "payload",
    [{}, {"usage": {}}, {"usage": {"total_tokens": -5}}, {"usage": {"total_tokens": "12"}}],
)
def test_sol1_missing_or_malformed_usage_poisons_the_ledger(tmp_path, payload):
    ledger = tmp_path / "l.jsonl"
    budget = make(ledger)

    async def handler(request):
        return httpx.Response(200, json=payload)

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(RuntimeError, match="hy_trial_usage"):
                    await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())
    with pytest.raises(poisoned_error(budget_module())):
        make(ledger)


def test_sol1_a_timeout_poisons_the_ledger(tmp_path):
    ledger = tmp_path / "l.jsonl"
    budget = make(ledger, seconds=0.01)

    async def handler(request):
        await asyncio.sleep(0.2)
        return httpx.Response(200, json={"usage": {"total_tokens": 1}})

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(RuntimeError, match="hy_trial_time_budget"):
                    await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())
    with pytest.raises(poisoned_error(budget_module())):
        make(ledger)


def test_sol1_a_transport_failure_poisons_the_ledger(tmp_path):
    ledger = tmp_path / "l.jsonl"
    budget = make(ledger)

    async def handler(request):
        raise httpx.ConnectError("boom", request=request)

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(httpx.ConnectError):
                    await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())
    with pytest.raises(poisoned_error(budget_module())):
        make(ledger)


def test_sol1_an_over_reservation_is_refused_before_send(tmp_path):
    budget = make(tmp_path / "l.jsonl", tokens=100, per_request=200)
    seen = []

    async def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"usage": {"total_tokens": 1}})

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(RuntimeError, match="hy_trial_token_budget"):
                    await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())
    assert seen == []


def test_sol3_a_non_authorized_host_is_refused_not_passed_through(tmp_path):
    """Sol #3: no pass-through for unknown hosts; only the exact allowlist."""
    budget = make(tmp_path / "l.jsonl")
    seen = []

    async def handler(request):
        seen.append(request)
        return httpx.Response(200, json={})

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(RuntimeError, match="hy_trial_host_refused"):
                    await client.get("https://example.com/v1/models")
                with pytest.raises(RuntimeError, match="hy_trial_host_refused"):
                    await client.get("https://api.openai.com/v1/models")
                # an explicitly allowed local ASGI host still passes
                await client.get("http://test/api/v1/health")

    asyncio.run(scenario())
    assert [r.url.host for r in seen] == ["test"]
    assert budget.requests == 0


def test_sol2_elapsed_is_not_double_counted_across_requests(tmp_path):
    """Sol #2: two 0.1s requests must leave ~0.2s of budget, not ~0.4s."""
    ledger = tmp_path / "l.jsonl"
    budget = make(ledger, seconds=10.0)

    async def handler(request):
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={"usage": {"total_tokens": 1}})

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                await client.post("https://api.deepseek.com/chat/completions", json={})
                await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    per_request = [e["elapsed_seconds"] for e in events if e["kind"] == "settle"]
    assert per_request and all(0.05 <= e < 0.5 for e in per_request)
    # the next run's remaining budget is derived from the finalized run elapsed,
    # which must be the sum of the two requests (~0.2s), not ~0.4s.
    reopened = make(ledger, seconds=10.0)
    assert 0.1 < reopened.elapsed_seconds < 0.6


def test_sol3_a_redirect_is_refused(tmp_path):
    budget = make(tmp_path / "l.jsonl")

    async def handler(request):
        return httpx.Response(302, headers={"location": "https://evil.example/"})

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(RuntimeError, match="hy_trial_redirect_refused"):
                    await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())
    with pytest.raises(poisoned_error(budget_module())):
        make(tmp_path / "l.jsonl")


def test_sol5_the_ledger_is_created_only_by_the_first_run(tmp_path):
    """Sol #5: no O_EXCL pre-create claim; the first run writes the header."""
    ledger = tmp_path / "l.jsonl"
    assert not ledger.exists()
    budget = make(ledger)

    async def handler(request):
        return httpx.Response(200, json={"usage": {"total_tokens": 1}})

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())
    header = json.loads(ledger.read_text().splitlines()[0])
    assert header["kind"] == "header"
    assert stat.S_IMODE(ledger.stat().st_mode) == 0o600


def test_the_ledger_never_records_bodies_or_keys(tmp_path):
    ledger = tmp_path / "l.jsonl"
    budget = make(ledger)

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "usage": {"total_tokens": 3},
                "choices": [{"message": {"content": "private reply"}}],
            },
        )

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                await client.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={"Authorization": "Bearer private-key"},
                    json={
                        "model": "trial",
                        "messages": [{"role": "user", "content": "private input"}],
                    },
                )

    asyncio.run(scenario())
    text = ledger.read_text()
    assert "private-key" not in text and "private input" not in text and "private reply" not in text


def test_trial_budget_rejects_a_second_live_ledger_owner(tmp_path):
    ledger = tmp_path / "l.jsonl"
    first, second = make(ledger), make(ledger)
    with (
        first.install(),
        pytest.raises(RuntimeError, match="hy_trial_ledger_locked"),
        second.install(),
    ):
        pass


def test_no_progress_review_a_non_2xx_with_usage_poisons_the_ledger(tmp_path):
    """Adversarial-review #1: a real 429/500 spend must not be booked as clean.

    A non-2xx can still carry `usage.total_tokens`; those tokens were spent but
    the request failed, so letting it settle as `returned` would let a later
    same-ledger attempt continue from a clean state. Any non-2xx is fail-closed.
    """
    ledger = tmp_path / "l.jsonl"
    budget = make(ledger, tokens=1000, per_request=200)

    async def handler(request):
        return httpx.Response(429, json={"usage": {"total_tokens": 150}})

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(RuntimeError, match="hy_trial_status:429"):
                    await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())
    with pytest.raises(poisoned_error(budget_module())):
        make(ledger, tokens=1000, per_request=200)
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert any(
        e.get("kind") == "poison" and e.get("reason") == "hy_trial_status:429" for e in events
    )


def test_no_progress_review_a_precreated_empty_ledger_is_refused(tmp_path):
    """Adversarial-review #2: an empty file must not become a header-less ledger."""
    ledger = tmp_path / "l.jsonl"
    ledger.write_text("", encoding="utf-8")
    budget = make(ledger)
    with pytest.raises(RuntimeError, match="hy_trial_ledger_header_required"), budget.install():
        pass


def test_no_progress_review_a_redirect_following_client_is_refused(tmp_path):
    """Adversarial-review #4: follow_redirects would hide the 3xx from the hook."""
    budget = make(tmp_path / "l.jsonl")

    async def handler(request):
        return httpx.Response(200, json={"usage": {"total_tokens": 1}})

    async def scenario():
        with budget.install():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler), follow_redirects=True
            ) as client:
                with pytest.raises(RuntimeError, match="hy_trial_redirects_enabled"):
                    await client.post("https://api.deepseek.com/chat/completions", json={})

    asyncio.run(scenario())


def test_no_progress_review_the_whole_run_elapsed_is_shared_across_owners(tmp_path):
    """Adversarial-review #3: local-stage wall clock must not be re-spent by C8.

    A run that spends its whole window inside import/worker/digest/restart must
    leave the next owner with ~0 seconds, not a fresh full window.
    """
    ledger = tmp_path / "l.jsonl"
    first = make(ledger, seconds=10.0, requests=8, tokens=1000)
    with first.install():
        pass
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert any(e.get("kind") == "run" for e in events)
    reopened = make(ledger, seconds=10.0, requests=8, tokens=1000)
    assert reopened.elapsed_seconds >= first.elapsed_seconds
    # A second owner whose install does real local work must inherit the first
    # owner's wall clock and add its own on top.
    time.sleep(0.02)
    second_start = reopened.elapsed_seconds
    with reopened.install():
        time.sleep(0.05)
    after = make(ledger, seconds=10.0, requests=8, tokens=1000)
    assert after.elapsed_seconds > second_start


def test_no_progress_review_a_forged_header_without_caps_is_refused(tmp_path):
    """Re-review #2: a header that anchors no caps must not be accepted."""
    ledger = tmp_path / "l.jsonl"
    ledger.write_text(json.dumps({"kind": "header"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        make(ledger)


def test_no_progress_review_a_failed_local_stage_still_records_elapsed(tmp_path):
    """Re-review #3: an exception before any request must still persist elapsed."""
    ledger = tmp_path / "l.jsonl"
    budget = make(ledger, seconds=30.0, requests=8, tokens=1000)
    with pytest.raises(RuntimeError, match="boom"), budget.install():
        time.sleep(0.02)
        raise RuntimeError("boom")
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert any(e.get("kind") == "run" for e in events)
    reopened = make(ledger, seconds=30.0, requests=8, tokens=1000)
    assert reopened.elapsed_seconds > 0.0


@pytest.mark.parametrize(
    "field", ["max_requests", "max_seconds", "max_reported_tokens", "per_request_max_tokens"]
)
def test_no_progress_review_a_non_finite_header_cap_is_refused(tmp_path, field):
    """Re-review #2b: JSON NaN/Infinity must not anchor or bypass the caps."""
    ledger = tmp_path / "l.jsonl"
    header = {
        "kind": "header",
        "schema": 3,
        "max_requests": 8,
        "max_seconds": 30,
        "max_reported_tokens": 1000,
        "per_request_max_tokens": 200,
    }
    header[field] = float("nan") if field == "max_seconds" else float("inf")
    ledger.write_text(json.dumps(header) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        make(ledger)
