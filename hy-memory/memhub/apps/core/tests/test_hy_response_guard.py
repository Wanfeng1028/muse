import asyncio
import json
import logging
from types import SimpleNamespace

import pytest

from one_memory.diagnostic_log import configure_diagnostics, reset_diagnostics
from one_memory.hy_response_guard import (
    HyReconcileGuard,
    HyResponseGuard,
    install_hy_write_guards,
)


@pytest.mark.parametrize("invalid", ["empty", "length"])
def test_invalid_response_retries_same_hy_provider_without_changing_prompt(invalid):
    class Provider:
        calls = []

        async def complete(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                content="" if invalid == "empty" and len(self.calls) == 1 else "[]",
                finish_reason="length" if invalid == "length" and len(self.calls) == 1 else "stop",
                tool_calls=None,
            )

    provider = Provider()
    response = asyncio.run(
        HyResponseGuard(provider).complete(prompt="native prompt", max_tokens=2000)
    )
    assert response.content == "[]"
    assert len(provider.calls) == 2
    assert all(call["prompt"] == "native prompt" for call in provider.calls)


def test_repeated_empty_response_fails_instead_of_becoming_no_op():
    class Provider:
        calls = 0

        async def complete_messages(self, **kwargs):
            self.calls += 1
            return SimpleNamespace(content="", finish_reason="stop", tool_calls=None)

    provider = Provider()
    with pytest.raises(ValueError, match="hy_memory_model_empty_response"):
        asyncio.run(HyResponseGuard(provider).complete_messages(messages=[]))
    assert provider.calls == 2


def test_failure_receipt_survives_a_later_successful_model_call():
    class Provider:
        succeed = False

        async def complete_messages(self, **kwargs):
            return SimpleNamespace(
                content="{}" if self.succeed else "", finish_reason="stop", tool_calls=None
            )

    provider = Provider()
    guard = HyResponseGuard(provider)
    with pytest.raises(ValueError, match="hy_memory_model_empty_response"):
        asyncio.run(guard.complete_messages(messages=[]))
    provider.succeed = True
    asyncio.run(guard.complete_messages(messages=[]))
    assert guard.failures == ["hy_memory_model_empty_response"]


def test_provider_exception_is_recorded_even_if_hy_later_swallows_it():
    class Provider:
        async def complete_messages(self, **kwargs):
            raise RuntimeError("provider unavailable")

    guard = HyResponseGuard(Provider())
    with pytest.raises(RuntimeError):
        asyncio.run(guard.complete_messages(messages=[]))
    assert guard.failures == ["hy_memory_model_request_failed"]


def test_payment_error_is_recorded_without_retrying_or_leaking_provider_details():
    class PaymentError(RuntimeError):
        status_code = 402

    class Provider:
        calls = 0

        async def complete_messages(self, **kwargs):
            self.calls += 1
            raise PaymentError("Private provider account details")

    provider = Provider()
    guard = HyResponseGuard(provider)
    with pytest.raises(PaymentError):
        asyncio.run(guard.complete_messages(messages=[]))
    assert provider.calls == 1
    assert guard.failures == ["hy_memory_model_payment_required"]


def observe_provider_failure(error, *, method="complete_messages"):
    class Provider:
        calls = 0

        async def complete(self, *args, **kwargs):
            self.calls += 1
            raise error

        complete_messages = complete

    provider = Provider()
    guard = HyResponseGuard(provider)
    with pytest.raises(type(error)) as raised:
        asyncio.run(getattr(guard, method)("private prompt", api_key="private key"))
    assert raised.value is error
    assert provider.calls == 1
    return guard


@pytest.mark.parametrize("method", ["complete", "complete_messages"])
@pytest.mark.parametrize("location", ["direct", "response", "attempts"])
@pytest.mark.parametrize(
    "status,code",
    [
        (401, "hy_memory_model_authentication_failed"),
        (402, "hy_memory_model_payment_required"),
        (403, "hy_memory_model_access_denied"),
        (429, "hy_memory_model_rate_limited"),
        (500, "hy_memory_model_service_unavailable"),
        (599, "hy_memory_model_service_unavailable"),
        (408, "hy_memory_model_timeout"),
        (400, "hy_memory_model_request_incompatible"),
        (404, "hy_memory_model_request_incompatible"),
        (422, "hy_memory_model_request_incompatible"),
    ],
)
def test_provider_status_is_classified_without_retry_or_private_logging(
    status, code, location, method, caplog
):
    from hy_memory.agent.llm_provider import LLMRetryError

    private = "private account key prompt response"
    if location == "attempts":
        error = LLMRetryError(
            private,
            [
                {"status_code": 401, "error": private},
                {"status_code": status, "error_type": private, "response_body": private},
            ],
        )
    else:
        error = RuntimeError(private)
        if location == "direct":
            error.status_code = status
        else:
            error.response = SimpleNamespace(status_code=status, text=private)
    caplog.set_level(logging.WARNING, logger="one_memory.hy_response_guard")
    guard = observe_provider_failure(error, method=method)
    assert guard.failures == [code]
    assert caplog.messages == [f"{code}: status_code={status}"]
    assert "private" not in caplog.text
    assert all(record.exc_info is None and record.stack_info is None for record in caplog.records)


@pytest.mark.parametrize("location", ["direct", "response", "attempts"])
@pytest.mark.parametrize("status", [None, True, False, "402", 402.0, -1, 600, 200, 302, 423])
def test_missing_invalid_or_unmapped_status_is_generic(location, status, caplog):
    from hy_memory.agent.llm_provider import LLMRetryError

    if location == "attempts":
        # A valid earlier failure must not override the final unknown result.
        error = LLMRetryError("private status=402", [{"status_code": 402}, {"status_code": status}])
    else:
        error = RuntimeError("private status=402")
        if location == "direct":
            error.status_code = status
        else:
            error.response = SimpleNamespace(status_code=status)
    caplog.set_level(logging.WARNING, logger="one_memory.hy_response_guard")
    guard = observe_provider_failure(error)
    assert guard.failures == ["hy_memory_model_request_failed"]
    expected_status = status if type(status) is int and 100 <= status <= 599 else "unknown"
    assert caplog.messages == [f"hy_memory_model_request_failed: status_code={expected_status}"]
    assert "private" not in caplog.text


@pytest.mark.parametrize("attempts", [None, [], {}, "402", [None], ["402"], [{"error": "402"}]])
def test_malformed_attempts_do_not_mask_original_exception(attempts, caplog):
    from hy_memory.agent.llm_provider import LLMRetryError

    error = LLMRetryError("private message", attempts)
    caplog.set_level(logging.WARNING, logger="one_memory.hy_response_guard")
    assert observe_provider_failure(error).failures == ["hy_memory_model_request_failed"]
    assert caplog.messages == ["hy_memory_model_request_failed: status_code=unknown"]


@pytest.mark.parametrize(
    "direct,response,expected",
    [
        (401, 429, "authentication_failed"),
        (None, 429, "rate_limited"),
        ("401", "429", "payment_required"),
    ],
)
def test_status_lookup_precedence_is_direct_then_response_then_final_attempt(
    direct, response, expected
):
    from hy_memory.agent.llm_provider import LLMRetryError

    error = LLMRetryError("private message", [{"status_code": 402}])
    error.status_code = direct
    error.response = SimpleNamespace(status_code=response)
    assert observe_provider_failure(error).failures == [f"hy_memory_model_{expected}"]


def test_failure_diagnostics_never_stringify_exception_or_illegal_status(caplog):
    class PrivateError(RuntimeError):
        def __str__(self):
            pytest.fail("Diagnostics must not stringify the provider exception")

    class PrivateStatus:
        def __str__(self):
            pytest.fail("Diagnostics must not stringify an untrusted status")

    error = PrivateError()
    error.status_code = PrivateStatus()
    caplog.set_level(logging.WARNING, logger="one_memory.hy_response_guard")
    assert observe_provider_failure(error).failures == ["hy_memory_model_request_failed"]
    assert caplog.messages == ["hy_memory_model_request_failed: status_code=unknown"]


def test_status_attribute_failure_preserves_original_provider_exception(caplog):
    class BrokenStatusError(RuntimeError):
        @property
        def status_code(self):
            raise ValueError("private attribute failure")

    error = BrokenStatusError("private provider message")
    caplog.set_level(logging.WARNING, logger="one_memory.hy_response_guard")
    assert observe_provider_failure(error).failures == ["hy_memory_model_request_failed"]
    assert caplog.messages == ["hy_memory_model_request_failed: status_code=unknown"]


def test_integer_subclass_is_not_a_strict_http_status(caplog):
    class Status(int):
        pass

    error = RuntimeError("private message")
    error.status_code = Status(402)
    caplog.set_level(logging.WARNING, logger="one_memory.hy_response_guard")
    assert observe_provider_failure(error).failures == ["hy_memory_model_request_failed"]
    assert caplog.messages == ["hy_memory_model_request_failed: status_code=unknown"]


@pytest.mark.parametrize("method", ["complete", "complete_messages"])
def test_terminal_sanitized_client_timeout_is_not_an_invented_http_status(method, caplog):
    from hy_memory.agent.llm_provider import LLMRetryError

    error = LLMRetryError("private error", [{"failure_kind": "timeout", "error": "private"}])
    caplog.set_level(logging.WARNING, logger="one_memory.hy_response_guard")
    assert observe_provider_failure(error, method=method).failures == ["hy_memory_model_timeout"]
    assert caplog.messages == ["hy_memory_model_timeout: status_code=unknown"]
    assert "private" not in caplog.text


@pytest.mark.parametrize("kind", [None, "connection", "unknown", "timeout private", True, {}, []])
def test_only_final_exact_timeout_category_is_used(kind, caplog):
    from hy_memory.agent.llm_provider import LLMRetryError

    error = LLMRetryError("private error", [{"failure_kind": "timeout"}, {"failure_kind": kind}])
    assert observe_provider_failure(error).failures == ["hy_memory_model_request_failed"]
    assert "private" not in caplog.text


def test_real_http_status_takes_precedence_over_client_timeout_kind():
    from hy_memory.agent.llm_provider import LLMRetryError

    error = LLMRetryError("private error", [{"failure_kind": "timeout", "status_code": 402}])
    assert observe_provider_failure(error).failures == ["hy_memory_model_payment_required"]


def test_valid_empty_json_array_is_not_confused_with_a_transport_empty_response():
    class Provider:
        calls = 0

        async def complete(self, **kwargs):
            self.calls += 1
            return SimpleNamespace(content="[]", finish_reason="stop", tool_calls=None)

    provider = Provider()
    assert asyncio.run(HyResponseGuard(provider).complete(prompt="native")).content == "[]"
    assert provider.calls == 1


def test_installation_reaches_ordinary_and_ultra_inner_writers():
    from one_memory.hy_write_verification import HyExtractionGuard

    def native_writer():
        native = SimpleNamespace()
        agent = SimpleNamespace(llm_provider=native, extractor=SimpleNamespace(llm=native))
        reconciler = SimpleNamespace(_get_llm=lambda: native)
        return SimpleNamespace(mem_agent=agent, reconciler=reconciler), agent, reconciler

    ordinary, ordinary_agent, ordinary_reconciler = native_writer()
    ultra_inner, ultra_agent, ultra_reconciler = native_writer()

    class Registry:
        async def get_writer(self):
            return ordinary

        async def get_system2_writer(self):
            return SimpleNamespace(_writer=ultra_inner)

    client = SimpleNamespace(_registry=Registry(), _loop_thread=SimpleNamespace(run=asyncio.run))
    install_hy_write_guards(client)
    for writer, agent, reconciler in (
        (ordinary, ordinary_agent, ordinary_reconciler),
        (ultra_inner, ultra_agent, ultra_reconciler),
    ):
        assert isinstance(agent.extractor.llm, HyResponseGuard)
        assert agent.llm_provider is agent.extractor.llm
        assert isinstance(agent.extractor, HyExtractionGuard)
        assert agent.extractor in client._one_memory_write_guards
        assert isinstance(reconciler._llm, HyResponseGuard)
        assert type(writer._reconciler).__name__ == "HyReconcileGuard"


def test_installed_guards_label_model_calls_by_hy_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("ONE_MEMORY_DIAGNOSTICS", "1")

    class Provider:
        async def complete(self, **kwargs):
            return SimpleNamespace(content="[]", finish_reason="stop", tool_calls=None)

    def native_writer():
        native = Provider()
        agent = SimpleNamespace(llm_provider=native, extractor=SimpleNamespace(llm=native))
        reconciler = SimpleNamespace(_get_llm=lambda: native)
        return SimpleNamespace(mem_agent=agent, reconciler=reconciler), agent, reconciler

    ordinary, ordinary_agent, ordinary_reconciler = native_writer()
    ultra_inner, _ultra_agent, _ultra_reconciler = native_writer()

    class Registry:
        async def get_writer(self):
            return ordinary

        async def get_system2_writer(self):
            return SimpleNamespace(_writer=ultra_inner)

    client = SimpleNamespace(_registry=Registry(), _loop_thread=SimpleNamespace(run=asyncio.run))
    install_hy_write_guards(client)
    receipt = configure_diagnostics(tmp_path)
    try:
        asyncio.run(ordinary_agent.llm_provider.complete(prompt="private-extract"))
        asyncio.run(ordinary_reconciler._llm.complete(prompt="private-reconcile"))
    finally:
        reset_diagnostics()
    written = receipt.path.read_text()
    phases = [json.loads(line)["details"]["phase"] for line in written.splitlines()]
    assert phases == ["extract", "reconcile"]
    assert "private-" not in written


def test_model_call_log_records_stage_and_duration_without_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("ONE_MEMORY_DIAGNOSTICS", "1")

    class Provider:
        async def complete(self, *, prompt, **kwargs):
            return SimpleNamespace(content="[]", finish_reason="stop", tool_calls=None)

    receipt = configure_diagnostics(tmp_path)
    try:
        asyncio.run(HyResponseGuard(Provider()).complete(prompt="private-prompt-marker"))
    finally:
        reset_diagnostics()
    written = receipt.path.read_text()
    event = json.loads(written)
    assert event["event"] == "hy.model_call.completed"
    assert event["details"] == {"phase": "extract", "attempt": 1, "call_count": 1}
    assert event["duration_ms"] >= 0
    assert "private-prompt-marker" not in written


def test_reconcile_log_counts_operations_without_content(tmp_path, monkeypatch):
    monkeypatch.setenv("ONE_MEMORY_DIAGNOSTICS", "1")

    class Reconciler:
        async def reconcile(self, **kwargs):
            return SimpleNamespace(
                success=True,
                ops=[
                    SimpleNamespace(op="ADD", owner="user", content="private-a", memory_id=None),
                    SimpleNamespace(op="UPDATE", owner="user", content="private-b", memory_id=None),
                    SimpleNamespace(
                        op="SUPERSEDE", owner="user", content="private-c", memory_id=None
                    ),
                    SimpleNamespace(op="DELETE", owner="user", content="private-d", memory_id=None),
                ],
            )

    receipt = configure_diagnostics(tmp_path)
    try:
        asyncio.run(HyReconcileGuard(Reconciler()).reconcile())
    finally:
        reset_diagnostics()
    written = receipt.path.read_text()
    event = json.loads(written)
    assert event["event"] == "hy.reconcile.completed"
    assert event["details"] == {
        "created_count": 1,
        "updated_count": 1,
        "superseded_count": 1,
        "deleted_count": 1,
        "result_count": 4,
    }
    assert "private-a" not in written


def test_native_no_candidate_reconcile_retains_extractor_owner(tmp_path, monkeypatch):
    from hy_memory.agent.reconciler import MemoryReconciler
    from hy_memory.config import MemoryConfig
    from hy_memory.pipelines._retrieval.reconcile_retrieval import ReconcileHybridRetriever

    from one_memory.hy_response_guard import HyReconcileGuard

    class Embeddings:
        async def embed_batch(self, texts):
            return [[1.0, 0.0] for _ in texts]

    class Store:
        async def get_embeddings(self, identifiers):
            return {}

    async def no_candidates(*args, **kwargs):
        return []

    monkeypatch.setattr(ReconcileHybridRetriever, "search_candidates", no_candidates)
    native = MemoryReconciler(MemoryConfig())
    native._enable_search_query = False
    arguments = {
        "new_memories": ["Agent建议启用备份，用户尚未确认。"],
        "user_id": "test",
        "agent_id": "test",
        "embed_service": Embeddings(),
        "vector_store": Store(),
        "new_memories_with_meta": [
            {"content": "Agent建议启用备份，用户尚未确认。", "owner": "agent"}
        ],
    }
    result = asyncio.run(HyReconcileGuard(native).reconcile(**arguments))
    assert result.success and len(result.ops) == 1
    assert result.ops[0].owner == "agent"
    assert result.ops[0].content == arguments["new_memories"][0]


def test_report_binding_rejects_a_reconciler_input_not_in_the_supplied_file():
    from one_memory.hy_response_guard import HyReconcileGuard

    guard = HyReconcileGuard(None)
    guard.imported_contents = frozenset({"supplied"})
    with pytest.raises(ValueError, match="import_input_mismatch"):
        asyncio.run(
            guard.reconcile(
                new_memories=["unbound"], new_memories_with_meta=[{"content": "unbound"}]
            )
        )


@pytest.mark.parametrize(
    "target_state", ["valid", "missing", "other-user", "other-agent", "read-error"]
)
def test_update_verification_reads_the_real_hy_store_interface_and_checks_identity(target_state):
    from hy_memory.agent.reconciler import ReconcileOp, ReconcileResult

    from one_memory.hy_response_guard import HyReconcileGuard

    node = SimpleNamespace(user_id="local", agent_id="atlas", owner="user", content="Keep history.")
    if target_state == "other-user":
        node.user_id = "another-user"
    if target_state == "other-agent":
        node.agent_id = "another-agent"

    class Store:
        calls = []

        async def get_by_id(self, key):
            self.calls.append(key)
            if target_state == "read-error":
                raise OSError("private storage details must not reach the receipt")
            return None if target_state == "missing" else node

    class Native:
        async def reconcile(self, **kwargs):
            return ReconcileResult(
                ops=[
                    ReconcileOp(op="UPDATE", memory_id="prior", owner="user", content=node.content)
                ]
            )

        def _get_llm(self):
            pytest.fail("An unchanged, identity-checked source needs no new model call")

    store = Store()
    guard = HyReconcileGuard(Native())
    arguments = {"user_id": "local", "agent_id": "atlas", "vector_store": store}
    if target_state == "valid":
        assert asyncio.run(guard.reconcile(**arguments)).success
        assert guard.failures == []
    else:
        code = (
            "hy_memory_write_verification_failed"
            if target_state == "read-error"
            else "hy_memory_write_verification_target_invalid"
        )
        with pytest.raises(ValueError, match=code):
            asyncio.run(guard.reconcile(**arguments))
        assert guard.failures == [code]
    assert store.calls == ["prior"]
