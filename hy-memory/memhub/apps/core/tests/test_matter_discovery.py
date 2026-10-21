import asyncio

import pytest
from pydantic import ValidationError

from one_memory.matters.models import Citation, Claim, MatterDraft, SampleRecord
from one_memory.matters.synthesis import WikiOutline, materialize, synthesize


def source():
    return SampleRecord(
        evidence_id="e1",
        source_id="cursor",
        conversation_id="c1",
        role="user",
        written_by="person",
        created_at=None,
        observed_at="2026-09-11",
        revision=2,
        content_hash="hash",
        project="Atlas",
        workspace=None,
        text="The Atlas release is planned for September 23.",
    )


def source_draft():
    return MatterDraft(
        title="Atlas product",
        purpose="Ship Atlas",
        boundary="Atlas development",
        anchors=["e1"],
        claims=[
            Claim(
                statement="Atlas release is planned for September 23.",
                kind="decision",
                citations=[Citation(evidence_id="e1", quote=source().text)],
            )
        ],
    )


def outline():
    return {
        "synopsis": "Ship Atlas",
        "scope": "Atlas development",
        "entries": [
            {
                "text": "Atlas release is planned for September 23.",
                "kind": "decision",
                "state": "current",
                "scope": "Atlas release",
                "supports": ["K0"],
                "change": "",
            }
        ],
    }


def test_synthesis_materializes_only_known_verbatim_citations():
    result = materialize(WikiOutline.model_validate(outline()), source_draft())
    assert result.claims[0].citations[0].quote == source().text
    invalid = outline()
    invalid["entries"][0]["supports"] = ["K404"]
    with pytest.raises(ValueError, match="unknown_support"):
        materialize(WikiOutline.model_validate(invalid), source_draft())


def test_duplicate_claims_keep_all_governed_refs_and_distinct_states():
    from one_memory.matters.models import MemoryRef
    from one_memory.matters.validation import merge_equivalent_claims

    reference = MemoryRef(
        memory_id="m1",
        revision=1,
        status="confirmed",
        content_hash="hash",
        task_id="t",
        hy_memory_id="h",
        engine_version="test",
        profile_id="p",
        profile_revision=1,
        model="test",
    )
    first = source_draft().claims[0].model_copy(update={"memory_refs": [reference]})
    second = first.model_copy(
        update={
            "memory_refs": [reference.model_copy(update={"memory_id": "m2"})],
            "citations": [Citation(evidence_id="e2", quote="Second source.")],
        }
    )
    historical = first.model_copy(update={"state": "historical"})
    result = merge_equivalent_claims([first, second, historical])
    assert len(result) == 2
    assert {ref.memory_id for ref in result[0].memory_refs} == {"m1", "m2"}
    assert {cite.evidence_id for cite in result[0].citations} == {"e1", "e2"}
    assert result[1].state == "historical"
    assert first.memory_refs == [reference]


def test_synthesis_cannot_echo_the_original_sixty_claim_list():
    with pytest.raises(ValidationError):
        WikiOutline.model_validate(source_draft().model_dump())
    too_many = outline()
    too_many["entries"] *= 17
    with pytest.raises(ValidationError):
        WikiOutline.model_validate(too_many)


def test_wiki_writer_cannot_upgrade_resolved_history_back_to_current():
    from one_memory.matters.models import MemoryRef

    draft = source_draft()
    draft.claims[0].state = "historical"
    draft.claims[0].memory_refs = [
        MemoryRef(
            memory_id="m",
            revision=1,
            status="confirmed",
            content_hash="h",
            task_id="t",
            hy_memory_id="m",
            engine_version="test",
            profile_id="p",
            profile_revision=1,
            model="test",
        )
    ]
    result = materialize(WikiOutline.model_validate(outline()), draft, preserve_state=True)
    assert result.claims[0].state == "historical"
    assert draft.claims[0].state == "historical"


def test_wiki_writer_cannot_upgrade_a_proposal_to_a_decision():
    draft = source_draft()
    draft.claims[0].kind = "proposal"
    result = materialize(WikiOutline.model_validate(outline()), draft, preserve_state=True)
    assert result.claims[0].kind == "proposal"


def test_synthesis_requires_complete_independent_review():
    class FakeModel:
        calls = 0

        async def complete(self, system, data, **kwargs):
            if "recent_human_evidence" in data:
                return {"updates": []}
            self.calls += 1
            return outline() if self.calls == 1 else {"reviews": []}

    with pytest.raises(ValueError, match="review_incomplete"):
        asyncio.run(synthesize(FakeModel(), source_draft(), [source()]))


def test_synthesis_uncertain_review_never_becomes_current_fact():
    class FakeModel:
        calls = 0

        async def complete(self, system, data, **kwargs):
            if "recent_human_evidence" in data:
                return {"updates": []}
            self.calls += 1
            return (
                outline()
                if self.calls == 1
                else {"reviews": [{"id": "r0", "verdict": "uncertain"}]}
            )

    with pytest.raises(ValueError, match="no_supported_claims"):
        asyncio.run(synthesize(FakeModel(), source_draft(), [source()]))


def test_outline_schema_failure_gets_one_bounded_repair():
    class FakeModel:
        attempts = 0

        async def complete(self, system, data, **kwargs):
            if "recent_human_evidence" in data:
                return {"updates": []}
            if "claims" in data:
                return {"reviews": [{"id": "r0", "verdict": "supported"}]}
            self.attempts += 1
            result = outline()
            if self.attempts == 1:
                result["synopsis"] = "x" * 181
            else:
                assert "validation_errors" in data
                assert "input" not in str(data["validation_errors"])
            return result

    model = FakeModel()
    result, _ = asyncio.run(synthesize(model, source_draft(), [source()]))
    assert model.attempts == 2
    assert result.purpose == "Ship Atlas"


def test_outline_repeated_schema_failure_is_not_silently_truncated():
    class FakeModel:
        attempts = 0

        async def complete(self, system, data, **kwargs):
            self.attempts += 1
            result = outline()
            result["synopsis"] = "x" * 181
            return result

    model = FakeModel()
    with pytest.raises(ValidationError):
        asyncio.run(synthesize(model, source_draft(), [source()]))
    assert model.attempts == 2


def test_formal_wiki_receives_all_governed_memories_before_compaction():
    from one_memory.matters.models import MemoryRef

    reference = MemoryRef(
        memory_id="m",
        revision=1,
        status="confirmed",
        content_hash="hash",
        task_id="t",
        hy_memory_id="hy-m",
        engine_version="test",
        profile_id="p",
        profile_revision=1,
        model="test",
    )
    draft = source_draft()
    draft.claims = [
        draft.claims[0].model_copy(update={"memory_refs": [reference]}) for _ in range(20)
    ]

    class FakeModel:
        seen = 0

        async def complete(self, system, data, **kwargs):
            if "catalog" in data:
                self.seen += len(data["catalog"])
                assert len(data["catalog"]) <= 12
                assert "最多12条" not in system
                return outline()
            return {"reviews": [{"id": "r0", "verdict": "supported"}]}

    model = FakeModel()
    result, _ = asyncio.run(synthesize(model, draft, [source()]))
    assert model.seen == 20
    assert result.claims[0].memory_refs == [reference]


def test_formal_batches_keep_canonical_matter_metadata_instead_of_rewriting_it():
    from one_memory.matters.models import MemoryRef

    draft = source_draft()
    draft.claims[0].memory_refs = [
        MemoryRef(
            memory_id="m",
            revision=1,
            status="confirmed",
            content_hash="hash",
            task_id="t",
            hy_memory_id="h",
            engine_version="test",
            profile_id="p",
            profile_revision=1,
            model="test",
        )
    ]

    class Model:
        async def complete(self, system, data, **kwargs):
            if "catalog" in data:
                assert "context_catalog" not in data
                assert all("citations" not in item for item in data["catalog"])
                result = outline()
                result["synopsis"] = "Unneeded batch-specific description. " * 100
                result["scope"] = "Unneeded batch-specific boundary. " * 100
                return result
            return {"reviews": [{"id": "r0", "verdict": "supported"}]}

    result, _ = asyncio.run(synthesize(Model(), draft, [source()]))
    assert result.purpose == draft.purpose
    assert result.boundary == draft.boundary
    assert result.claims[0].statement == outline()["entries"][0]["text"]


def test_batches_write_resolved_targets_and_review_against_original_global_memory():
    from one_memory.matters.models import MemoryRef

    ref = MemoryRef(
        memory_id="m0",
        revision=1,
        status="confirmed",
        content_hash="hash",
        task_id="t",
        hy_memory_id="h",
        engine_version="test",
        profile_id="p",
        profile_revision=1,
        model="test",
    )
    old = source().model_copy(
        update={"text": "For now, discuss the design only.", "created_at": "2026-09-10T09:00:00Z"}
    )
    later = source().model_copy(
        update={
            "evidence_id": "e2",
            "text": "The design is agreed; start implementing now.",
            "created_at": "2026-09-11T09:00:00Z",
        }
    )
    draft = source_draft()
    draft.claims = [
        Claim(
            statement=old.text,
            kind="constraint",
            basis="human_statement",
            citations=[
                Citation(evidence_id=old.evidence_id, quote=old.text, created_at=old.created_at)
            ],
            memory_refs=[ref.model_copy(update={"memory_id": f"m{i}"})],
        )
        for i in range(12)
    ]
    draft.claims.append(
        Claim(
            statement=later.text,
            kind="decision",
            basis="human_statement",
            citations=[
                Citation(
                    evidence_id=later.evidence_id, quote=later.text, created_at=later.created_at
                )
            ],
            memory_refs=[ref.model_copy(update={"memory_id": "later"})],
        )
    )
    governed = draft.model_copy(deep=True)
    for index in range(12):
        original = draft.claims[index]
        draft.claims[index] = original.model_copy(
            update={
                "state": "superseded",
                "memory_refs": original.memory_refs + draft.claims[-1].memory_refs,
                "citations": original.citations + draft.claims[-1].citations,
            }
        )

    class Model:
        async def complete(self, system, data, **kwargs):
            if "catalog" in data:
                assert "context_catalog" not in data
                assert len(data["catalog"]) <= 12
                assert all("citations" not in item for item in data["catalog"])
                is_old = data["catalog"][0]["evidence_statement"] == old.text
                result = outline()
                result["entries"] = [
                    {
                        **result["entries"][0],
                        "text": item["evidence_statement"],
                        "state": "superseded" if is_old else "current",
                        "supports": [item["key"]],
                        "change": "Implementation was subsequently authorized." if is_old else "",
                    }
                    for item in data["catalog"]
                ]
                return result
            assert len(data["governed_memories"]) == 13
            return {
                "reviews": [{"id": item["id"], "verdict": "supported"} for item in data["claims"]]
            }

    result, _ = asyncio.run(synthesize(Model(), draft, [old, later], context=governed))
    first = result.claims[0]
    assert first.state == "superseded"
    assert {citation.evidence_id for citation in first.citations} == {"e1", "e2"}
    assert {ref.memory_id for ref in first.memory_refs} == {"m0", "later"}


def test_formal_wiki_retains_reviewed_source_when_compression_omits_it():
    from one_memory.matters.models import MemoryRef

    ref = MemoryRef(
        memory_id="primary",
        revision=1,
        status="confirmed",
        content_hash="hash",
        task_id="t",
        hy_memory_id="hy",
        engine_version="test",
        profile_id="p",
        profile_revision=1,
        model="test",
    )
    draft = source_draft()
    draft.claims[0].memory_refs = [ref]
    draft.claims[0].kind = "constraint"
    draft.claims.append(
        draft.claims[0].model_copy(
            update={
                "statement": "A second independent constraint",
                "kind": "constraint",
                "memory_refs": [ref.model_copy(update={"memory_id": "secondary"})],
            }
        )
    )

    class Model:
        async def complete(self, system, data, **kwargs):
            if "claims" in data:
                assert len(data["claims"]) == 2
                assert data["claims"][1]["statement"] == "A second independent constraint"
                return {
                    "reviews": [
                        {"id": item["id"], "verdict": "supported"} for item in data["claims"]
                    ]
                }
            return outline()

    result, _ = asyncio.run(synthesize(Model(), draft, [source()]))
    assert result.claims[1].statement == draft.claims[1].statement
    assert {ref.memory_id for claim in result.claims for ref in claim.memory_refs} == {
        "primary",
        "secondary",
    }


def test_retained_source_still_fails_if_independent_review_rejects_it():
    from one_memory.matters.models import MemoryRef

    draft = source_draft()
    draft.claims[0].memory_refs = [
        MemoryRef(
            memory_id="m",
            revision=1,
            status="confirmed",
            content_hash="hash",
            task_id="t",
            hy_memory_id="hy",
            engine_version="test",
            profile_id="p",
            profile_revision=1,
            model="test",
        )
    ]

    class Model:
        async def complete(self, system, data, **kwargs):
            if "claims" in data:
                return {
                    "reviews": [
                        {"id": item["id"], "verdict": "unsupported"} for item in data["claims"]
                    ]
                }
            return outline()

    with pytest.raises(ValueError, match="no_supported_claims"):
        asyncio.run(synthesize(Model(), draft, [source()]))


def test_coverage_repair_also_validates_and_repairs_the_outline_schema():
    from one_memory.matters.models import MemoryRef

    ref = MemoryRef(
        memory_id="primary",
        revision=1,
        status="confirmed",
        content_hash="hash",
        task_id="t",
        hy_memory_id="hy",
        engine_version="test",
        profile_id="p",
        profile_revision=1,
        model="test",
    )
    draft = source_draft()
    draft.claims[0].memory_refs = [ref]
    draft.claims.append(
        draft.claims[0].model_copy(
            update={"memory_refs": [ref.model_copy(update={"memory_id": "secondary"})]}
        )
    )

    class Model:
        repaired = False

        async def complete(self, system, data, **kwargs):
            if "claims" in data:
                return {"reviews": [{"id": "r0", "verdict": "supported"}]}
            result = outline()
            if "missing_keys" in data:
                result["entries"] *= 17
            elif "validation_errors" in data:
                self.repaired = True
                result["entries"][0]["supports"] = ["K0", "K1"]
            return result

    model = Model()
    result, _ = asyncio.run(synthesize(model, draft, [source()]))
    assert model.repaired
    assert {ref.memory_id for ref in result.claims[0].memory_refs} == {"primary", "secondary"}


def test_composed_claim_preserves_all_sources_instead_of_truncating_to_eight():
    draft = source_draft()
    draft.claims = [
        draft.claims[0].model_copy(
            update={
                "citations": [
                    Citation(evidence_id=f"e{group}-{i}", quote="original quote") for i in range(8)
                ]
            }
        )
        for group in range(4)
    ]
    output = outline()
    output["entries"][0]["supports"] = ["K0", "K1", "K2", "K3"]
    result = materialize(WikiOutline.model_validate(output), draft)
    assert len(result.claims[0].citations) == 32


def test_unresolved_human_questions_are_not_lost_just_because_they_are_not_decisions():
    from one_memory.matters.models import MemoryRef
    from one_memory.matters.synthesis import required_memory_ids

    claim = (
        source_draft().claims[0].model_copy(update={"kind": "open_question", "state": "unresolved"})
    )
    claim.memory_refs = [
        MemoryRef(
            memory_id="m",
            revision=1,
            status="confirmed",
            content_hash="hash",
            task_id="t",
            hy_memory_id="hy",
            engine_version="test",
            profile_id="p",
            profile_revision=1,
            model="test",
        )
    ]
    assert required_memory_ids([claim]) == {"m"}


def test_large_governed_catalog_is_written_in_bounded_sections_without_losing_memories():
    from one_memory.matters.models import MemoryRef

    draft = source_draft()
    draft.claims = [
        draft.claims[0].model_copy(
            update={
                "memory_refs": [
                    MemoryRef(
                        memory_id=f"m{i}",
                        revision=1,
                        status="confirmed",
                        content_hash="hash",
                        task_id="t",
                        hy_memory_id=f"h{i}",
                        engine_version="test",
                        profile_id="p",
                        profile_revision=1,
                        model="test",
                    )
                ]
            }
        )
        for i in range(48)
    ]

    class Model:
        windows = []

        async def complete(self, system, data, **kwargs):
            if "catalog" in data:
                assert len(data["catalog"]) <= 12
                self.windows.append(data["catalog"])
                result = outline()
                result["entries"] = [
                    {
                        **result["entries"][0],
                        "supports": [item["key"] for item in data["catalog"][i : i + 4]],
                    }
                    for i in range(0, len(data["catalog"]), 4)
                ]
                return result
            return {
                "reviews": [{"id": claim["id"], "verdict": "supported"} for claim in data["claims"]]
            }

    model = Model()
    result, _ = asyncio.run(synthesize(model, draft, [source()]))
    assert len(model.windows) == 4
    assert {ref.memory_id for claim in result.claims for ref in claim.memory_refs} == {
        f"m{i}" for i in range(48)
    }


def test_optional_context_selection_never_filters_required_human_memories():
    from one_memory.matters.models import MemoryRef
    from one_memory.matters.synthesis import focus_material

    reference = MemoryRef(
        memory_id="human",
        revision=1,
        status="confirmed",
        content_hash="hash",
        task_id="t",
        hy_memory_id="hy",
        engine_version="test",
        profile_id="p",
        profile_revision=1,
        model="test",
    )
    core = source_draft().claims[0].model_copy(update={"memory_refs": [reference]})
    optional = [
        core.model_copy(
            update={
                "statement": f"Agent proposal {i}",
                "basis": "agent_report",
                "kind": "proposal",
                "memory_refs": [reference.model_copy(update={"memory_id": f"a{i}"})],
            }
        )
        for i in range(20)
    ]

    class Model:
        async def complete(self, system, data, **kwargs):
            assert len(data["supplemental_catalog"]) == 20
            assert all(item["basis"] == "agent_report" for item in data["supplemental_catalog"])
            return {"keys": ["s2"]}

    result = asyncio.run(focus_material(Model(), [core, *optional], profile_id=None))
    assert result == [core, optional[2]]


def test_batch_size_does_not_become_a_total_dossier_storage_limit():
    from one_memory.matters.models import MemoryRef

    draft = source_draft()
    draft.claims = [
        draft.claims[0].model_copy(
            update={
                "memory_refs": [
                    MemoryRef(
                        memory_id=f"m{i}",
                        revision=1,
                        status="confirmed",
                        content_hash="hash",
                        task_id="t",
                        hy_memory_id=f"h{i}",
                        engine_version="test",
                        profile_id="p",
                        profile_revision=1,
                        model="test",
                    )
                ]
            }
        )
        for i in range(72)
    ]

    class Model:
        async def complete(self, system, data, **kwargs):
            if "catalog" in data:
                assert len(data["catalog"]) <= 12
                result = outline()
                result["entries"] = [
                    {**result["entries"][0], "supports": [item["key"]]} for item in data["catalog"]
                ]
                return result
            return {
                "reviews": [{"id": item["id"], "verdict": "supported"} for item in data["claims"]]
            }

    result, _ = asyncio.run(synthesize(Model(), draft, [source()]))
    assert len(result.claims) == 72
    assert {ref.memory_id for claim in result.claims for ref in claim.memory_refs} == {
        f"m{i}" for i in range(72)
    }


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_semantic_outline_repair_preserves_support_and_rechecks(repair_succeeds):
    from one_memory.matters.models import MemoryRef

    draft = source_draft()
    draft.claims[0].memory_refs = [
        MemoryRef(
            memory_id="m",
            revision=1,
            status="confirmed",
            content_hash="hash",
            task_id="t",
            hy_memory_id="h",
            engine_version="test",
            profile_id="p",
            profile_revision=1,
            model="test",
        )
    ]

    class Model:
        checks = 0
        repairs = 0

        async def complete(self, system, data, **kwargs):
            if "claims" in data:
                self.checks += 1
                return {
                    "reviews": [
                        {
                            "id": "r0",
                            "verdict": "supported"
                            if self.checks == 2 and repair_succeeds
                            else "unsupported",
                            "reason": "Scope is broader than the evidence.",
                        }
                    ]
                }
            if "review_notes" in data:
                self.repairs += 1
                assert data["catalog"][0]["evidence_statement"] == draft.claims[0].statement
            return outline()

    model = Model()
    if repair_succeeds:
        result, _ = asyncio.run(synthesize(model, draft, [source()]))
        assert result.claims[0].memory_refs == draft.claims[0].memory_refs
    else:
        with pytest.raises(ValueError, match="no_supported_claims"):
            asyncio.run(synthesize(model, draft, [source()]))
    assert model.checks == 2 and model.repairs == 1


def test_agent_generated_decision_is_still_downgraded_after_synthesis():
    class FakeModel:
        calls = 0

        async def complete(self, system, data, **kwargs):
            if "recent_human_evidence" in data:
                return {"updates": []}
            self.calls += 1
            return (
                outline()
                if self.calls == 1
                else {"reviews": [{"id": "r0", "verdict": "supported"}]}
            )

    record = source().model_copy(update={"written_by": "agent", "role": "assistant"})
    result, rejected = asyncio.run(synthesize(FakeModel(), source_draft(), [record]))
    assert rejected == 0
    assert result.claims[0].kind == "proposal"
    assert result.claims[0].basis == "agent_report"


def test_reconciliation_replaces_old_claim_instead_of_keeping_both():
    from one_memory.matters.synthesis import reconcile_current

    record = source().model_copy(
        update={
            "evidence_id": "e2",
            "text": "Correction: release Atlas on September 25.",
            "created_at": "2026-09-11T00:00:00Z",
        }
    )

    class FakeModel:
        async def complete(self, system, data, **kwargs):
            return {
                "updates": [
                    {
                        "index": 0,
                        "replacement": {
                            "statement": "Release Atlas on September 25.",
                            "kind": "decision",
                            "state": "current",
                            "citations": [{"evidence_id": "e2", "quote": record.text}],
                        },
                    }
                ]
            }

    result = asyncio.run(reconcile_current(FakeModel(), source_draft(), [source(), record]))
    assert len(result.claims) == 1
    assert "25" in result.claims[0].statement
    assert "23" not in result.claims[0].statement


def test_budget_exhaustion_has_actionable_code_without_echoing_provider_details(tmp_path):
    import httpx
    from pydantic import SecretStr

    from one_memory.matters.model import MatterModel
    from one_memory.model_profiles import ModelProfileInput, ModelProfileStore, ProviderKind
    from one_memory.secrets import InMemorySecretStore

    profiles = ModelProfileStore(tmp_path / "db.sqlite3")
    secrets = InMemorySecretStore()
    profile = profiles.create(
        ModelProfileInput(
            name="test",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://models.example.test/v1",
            model="test-model",
            api_key=SecretStr("fake-key"),
        ),
        secrets,
    )
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            401,
            json={
                "error": {
                    "type": "UserBudgetExhausted",
                    "code": "2005",
                    "message": "private provider details",
                }
            },
        )
    )
    model = MatterModel(profiles, secrets, transport=transport)
    with pytest.raises(ValueError, match="^matter_model_budget_exhausted$"):
        asyncio.run(model.complete("system", {}, profile_id=profile.profile_id))


def test_cached_output_still_checks_revocation_before_returning(tmp_path):
    import httpx

    from one_memory.matters.model import MatterModel
    from one_memory.model_profiles import ModelProfileInput, ModelProfileStore, ProviderKind
    from one_memory.secrets import InMemorySecretStore

    profiles = ModelProfileStore(tmp_path / "db.sqlite3")
    secrets = InMemorySecretStore()
    profile = profiles.create(
        ModelProfileInput(name="test", provider_kind=ProviderKind.OLLAMA, model="test-model"),
        secrets,
    )
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"message": {"content": '{"ok":true}'}})

    model = MatterModel(profiles, secrets, transport=httpx.MockTransport(respond))
    assert asyncio.run(model.complete("system", {}, profile_id=profile.profile_id)) == {"ok": True}

    def revoked():
        raise ValueError("matter_sources_changed_during_generation")

    model.evidence_guard = revoked
    with pytest.raises(ValueError, match="sources_changed"):
        asyncio.run(model.complete("system", {}, profile_id=profile.profile_id))
    assert len(requests) == 1


def test_direct_deepseek_thinking_toggle_does_not_change_other_gateways():
    from types import SimpleNamespace

    from one_memory.model_profiles import ProviderKind, attach_disable_thinking

    direct = SimpleNamespace(
        provider_kind=ProviderKind.OPENAI_COMPATIBLE,
        disable_thinking=True,
        base_url="https://api.deepseek.com/v1",
    )
    assert attach_disable_thinking(direct, {}) == {"thinking": {"type": "disabled"}}
    direct.base_url = "https://gateway.example.test/v1"
    assert attach_disable_thinking(direct, {}) == {"reasoning_effort": "none"}


def test_thinking_request_has_bounded_effort_and_does_not_cache_reasoning(tmp_path):
    import json
    import sqlite3

    import httpx
    from pydantic import SecretStr

    from one_memory.matters.model import MatterModel
    from one_memory.model_profiles import ModelProfileInput, ModelProfileStore, ProviderKind
    from one_memory.secrets import InMemorySecretStore

    profiles = ModelProfileStore(tmp_path / "db.sqlite3")
    secrets = InMemorySecretStore()
    profile = profiles.create(
        ModelProfileInput(
            name="thinking",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            api_key=SecretStr("test-only"),
            disable_thinking=False,
        ),
        secrets,
    )
    requests = []

    def response(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"ok":true}',
                            "reasoning_content": "private-internal-reasoning",
                        },
                    }
                ]
            },
        )

    model = MatterModel(profiles, secrets, transport=httpx.MockTransport(response))
    assert asyncio.run(model.complete("system", {}, profile_id=profile.profile_id)) == {"ok": True}
    assert requests[0]["reasoning_effort"] == "low"
    assert requests[0]["max_tokens"] == 32768
    assert requests[0]["thinking"] == {"type": "enabled"}
    with sqlite3.connect(profiles.database_path) as db:
        assert (
            "private-internal-reasoning"
            not in db.execute("SELECT body FROM matter_model_cache").fetchone()[0]
        )
