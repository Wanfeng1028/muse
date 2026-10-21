import asyncio
from datetime import datetime
import json

from hy_memory.models.memory import (
    MemoryLayer,
    MemoryNode,
    MemoryStatus,
    SourceType,
)
from hy_memory.pipelines.balanced_catalog import (
    CATALOG_SCHEMA_KIND,
    CATALOG_VERSION,
    source_bank_fingerprint,
)
from hy_memory.pipelines.specific_supplement import (
    SUPPLEMENT_MARKER,
    SUPPLEMENT_SCHEMA_KIND,
    SUPPLEMENT_VERSION,
    attach_specific_supplement_to_l0,
    deterministic_claim_candidates,
    get_active_specific_supplement,
    is_internal_profile_chain_custom,
    materialize_specific_supplement,
    normalize_clause_selection,
    normalize_remove_selection,
    run_specific_supplement_generation,
    specific_forget_targets,
    supplement_reject_reason,
)


def run(value):
    return asyncio.run(value)


def fact(node_id, content, *, tags=None):
    return MemoryNode(
        node_id=node_id,
        user_id="u1",
        agent_id="a1",
        layer=MemoryLayer.L2_FACT,
        content=content,
        owner="user",
        status=MemoryStatus.ACTIVE,
        is_latest=True,
        tags=tags or ["tag"],
    )


def balanced_catalog(evidence=None):
    evidence = evidence or ["base"]
    return MemoryNode(
        node_id="catalog_base",
        user_id="u1",
        agent_id="",
        layer=MemoryLayer.L6_SCHEMA,
        content=(
            "System2 verified persona catalog:\n"
            "- [habits_items] The user carries a steel bottle."
        ),
        status=MemoryStatus.ACTIVE,
        source_type=SourceType.COMPOSITE,
        evidence_chain=evidence,
        custom={
            "schema_kind": CATALOG_SCHEMA_KIND,
            "balanced_catalog_version": CATALOG_VERSION,
            "source_bank_fingerprint": "catalog-fp",
            "selected_count": len(evidence),
        },
    )


def supplement_node(content=None):
    return MemoryNode(
        node_id="catalog_supplement_x",
        user_id="u1",
        agent_id="",
        layer=MemoryLayer.L6_SCHEMA,
        content=content or (
            f"{SUPPLEMENT_MARKER}\n"
            "- [health_accessibility] The user has mild myopia."
        ),
        status=MemoryStatus.ACTIVE,
        source_type=SourceType.COMPOSITE,
        custom={
            "schema_kind": SUPPLEMENT_SCHEMA_KIND,
            "specific_supplement_version": SUPPLEMENT_VERSION,
            "source_bank_fingerprint": "supp-fp",
            "selected_count": 1,
        },
    )


class FakeResponse:
    def __init__(self, content):
        self.content = content
        self.prompt_tokens = 10
        self.completion_tokens = 3


class SequenceProvider:
    responses = []
    calls = []

    def __init__(self, config):
        pass

    async def complete_messages(self, messages, max_tokens, temperature=None):
        type(self).calls.append({
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        return FakeResponse(type(self).responses.pop(0))


class FakeVectorStore:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    async def list_by_user(self, **kwargs):
        self.calls.append(kwargs)
        return self.facts

    async def get_by_id(self, node_id):
        return next((node for node in self.facts if node.node_id == node_id), None)


class FakeGraphStore:
    def __init__(self, nodes=None):
        self.nodes = {node.node_id: node for node in (nodes or [])}
        self.upserts = []
        self.links = []
        self.updates = []

    async def get_all_nodes(self, isolation_key, layer=None, status=None, limit=100):
        return [
            node for node in self.nodes.values()
            if (layer is None or node.layer == layer)
            and (status is None or node.status == status)
        ][:limit]

    async def get_nodes_by_user(self, user_id, layer=None, status=None, limit=100):
        return [
            node for node in self.nodes.values()
            if node.user_id == user_id
            and (layer is None or node.layer == layer)
            and (status is None or node.status == status)
        ][:limit]

    async def get_node(self, node_id):
        return self.nodes.get(node_id)

    async def upsert_memory_node(self, node):
        self.nodes[node.node_id] = node
        self.upserts.append(node.node_id)
        return node.node_id

    async def ensure_vdbref(self, node_id, layer):
        return None

    async def add_derived_from(self, memory_node_id, vdbref_node_id):
        self.links.append((memory_node_id, vdbref_node_id))
        return True

    async def update_node(self, node_id, updates):
        self.updates.append((node_id, updates))
        node = self.nodes[node_id]
        if "status" in updates:
            node.status = MemoryStatus(updates["status"])
        if "is_latest" in updates:
            node.is_latest = updates["is_latest"]
        return True

    async def delete_node(self, node_id):
        self.nodes.pop(node_id, None)
        return True


def test_internal_profile_chain_recognizes_catalog_and_supplement():
    assert is_internal_profile_chain_custom(balanced_catalog().custom)
    assert is_internal_profile_chain_custom(supplement_node().custom)
    assert not is_internal_profile_chain_custom({"schema_kind": "behavior_pattern"})


def test_question_shaped_claim_candidates_are_exact_and_conservative():
    source = (
        "The user asked the assistant to explain why breezy days in late April "
        "make their head feel heavier and their nose more blocked than calm days."
    )
    candidates = deterministic_claim_candidates(source)
    expected = (
        "breezy days in late April make their head feel heavier and their nose "
        "more blocked than calm days."
    )
    assert expected in candidates
    assert all(candidate in source for candidate in candidates)
    assert all("The user asked" not in candidate for candidate in candidates)
    assert deterministic_claim_candidates(
        "The user asked for tips on watching a 3D movie without getting a headache."
    ) == []


def test_clause_and_remove_normalizers_are_bounded():
    parents = [{"node_id": "p1", "candidates": ["a", "b"]}]
    assert normalize_clause_selection(
        {"selected": [{"parent": 1, "candidates": [2, 1]}]}, parents
    ) == {"p1": 2}
    assert normalize_remove_selection({"remove": [3, 1, 1, 99]}, 3) == [1, 3]
    assert specific_forget_targets(["the fact", "they enjoy iced coffee"]) == [
        "they enjoy iced coffee"
    ]


def test_supplement_verifier_keeps_generic_for_salvage_only():
    assert supplement_reject_reason(
        "The user asked why breezy days make their nose blocked."
    ) == "generic_question"
    assert supplement_reject_reason(
        "The assistant recommended taking a walk."
    ) == "assistant_advice"
    assert supplement_reject_reason(
        "The user has mild myopia."
    ) == ""


def test_residual_fact_order_is_clone_stable_by_content_and_tags():
    from hy_memory.pipelines.specific_supplement import eligible_supplement_facts

    left = [
        fact("random-z", "The user has mild myopia.", tags=["vision", "health"]),
        fact("random-a", "The user collects European design books.", tags=["books"]),
    ]
    right = [
        fact("other-a", "The user has mild myopia.", tags=["vision", "health"]),
        fact("other-z", "The user collects European design books.", tags=["books"]),
    ]
    assert [node.content for node in eligible_supplement_facts(left)] == [
        node.content for node in eligible_supplement_facts(right)
    ] == [
        "The user collects European design books.",
        "The user has mild myopia.",
    ]


def test_attach_specific_supplement_changes_only_suffix_metadata():
    l0 = [{
        "node_id": "l0",
        "content": "The user's name is Alice.",
        "layer": MemoryLayer.L0_BASIC_INFO.value,
        "score": 1.0,
    }]
    updated, info = attach_specific_supplement_to_l0(l0, supplement_node())
    assert info["attached"] is True
    assert updated[0]["content"] == l0[0]["content"]
    assert updated[0]["_specific_supplement_suffix"].startswith(SUPPLEMENT_MARKER)
    assert attach_specific_supplement_to_l0([], supplement_node())[1][
        "attached"
    ] is False


def test_generation_uses_residual_exact_facts_and_semantic_forget(monkeypatch):
    facts = [
        fact("base", "The user carries a steel bottle."),
        fact("health", "The user has mild myopia.", tags=["health", "vision"]),
        fact("keep", "The user collects European design books."),
        fact("drop", "The user enjoys iced coffee."),
        fact(
            "marker",
            "The user asked the assistant to forget that they enjoy iced coffee.",
        ),
    ]
    graph = FakeGraphStore([balanced_catalog(["base"])])
    # Residual prompt order is clone-stable by normalized content:
    # marker, keep, drop, health.
    SequenceProvider.responses = [
        json.dumps({
            "domains": {
                "health_accessibility": [4],
                "preferences_collections": [2, 3],
            }
        }),
        json.dumps({"remove": []}),
    ]
    SequenceProvider.calls = []
    monkeypatch.setenv("MEMORY_EVOLING_BALANCED_CATALOG_ENABLED", "true")
    monkeypatch.setenv("MEMORY_HYBRID_V2_BALANCED_CATALOG_L0_ENABLED", "true")
    monkeypatch.setenv("MEMORY_EVOLING_SPECIFIC_SUPPLEMENT_ENABLED", "true")
    monkeypatch.setattr(
        "hy_memory.pipelines.specific_supplement.LLMProvider",
        SequenceProvider,
    )
    result = run(run_specific_supplement_generation(
        user_id="u1",
        vector_store=FakeVectorStore(facts), graph_store=graph, config=object(),
    ))
    assert result["success"] is True
    assert result["selected_count"] == 2
    assert result["suppressed_forget_target_entries"] == [{
        "node_id": "drop", "domain": "preferences_collections",
    }]
    node = graph.nodes[result["supplement_node_id"]]
    assert node.agent_id == ""
    assert node.custom["schema_kind"] == SUPPLEMENT_SCHEMA_KIND
    assert node.custom["specific_supplement_version"] == SUPPLEMENT_VERSION
    assert node.embedding is None
    assert "mild myopia" in node.content
    assert "European design books" in node.content
    assert "iced coffee" not in node.content
    assert [edge[1] for edge in graph.links] == ["health", "keep"]
    assert len(SequenceProvider.calls) == 2


def test_generation_uses_cross_agent_user_fact_bank(monkeypatch):
    base = fact("base", "The user carries a steel bottle.")
    health = fact("health", "The user has mild myopia.")
    base.agent_id = "agent-a"
    health.agent_id = "agent-b"
    store = FakeVectorStore([base, health])
    graph = FakeGraphStore([balanced_catalog(["base"])])
    SequenceProvider.responses = [json.dumps({
        "domains": {"health_accessibility": [1]},
    })]
    SequenceProvider.calls = []
    monkeypatch.setenv("MEMORY_EVOLING_SPECIFIC_SUPPLEMENT_ENABLED", "true")
    monkeypatch.setenv("MEMORY_USER_PROFILE_BALANCED_CATALOG_ENABLED", "true")
    monkeypatch.setattr(
        "hy_memory.pipelines.specific_supplement.LLMProvider", SequenceProvider,
    )

    result = run(run_specific_supplement_generation(
        user_id="u1", vector_store=store, graph_store=graph, config=object(),
    ))

    assert result["success"] is True
    node = graph.nodes[result["supplement_node_id"]]
    assert node.agent_id == ""
    assert node.evidence_chain == ["health"]
    assert "agent_id" not in store.calls[0]


def test_generation_salvages_question_composite_in_place(monkeypatch):
    facts = [
        fact("base", "The user carries a steel bottle."),
        fact(
            "composite",
            "The user asked the assistant to explain why breezy days in late "
            "April make their head feel heavier and their nose more blocked "
            "than calm days.",
        ),
        fact("ordinary", "The user collects European design books."),
    ]
    graph = FakeGraphStore([balanced_catalog(["base"])])
    # residual order: composite, ordinary
    SequenceProvider.responses = [
        json.dumps({
            "domains": {
                "health_accessibility": [1],
                "preferences_collections": [2],
            }
        }),
        json.dumps({
            "selected": [{"parent": 1, "candidates": [1]}]
        }),
    ]
    SequenceProvider.calls = []
    monkeypatch.setenv("MEMORY_EVOLING_BALANCED_CATALOG_ENABLED", "true")
    monkeypatch.setenv("MEMORY_HYBRID_V2_BALANCED_CATALOG_L0_ENABLED", "true")
    monkeypatch.setenv("MEMORY_EVOLING_SPECIFIC_SUPPLEMENT_ENABLED", "true")
    monkeypatch.setattr(
        "hy_memory.pipelines.specific_supplement.LLMProvider",
        SequenceProvider,
    )
    result = run(run_specific_supplement_generation(
        user_id="u1",
        vector_store=FakeVectorStore(facts), graph_store=graph, config=object(),
    ))
    assert result["success"] is True
    node = graph.nodes[result["supplement_node_id"]]
    lines = node.content.splitlines()
    assert "breezy days in late April" in lines[1]
    assert "European design books" in lines[2]
    assert "The user asked" not in node.content
    assert node.custom["clause_salvage_count"] == 1


def test_same_source_supplement_is_zero_llm_zero_write(monkeypatch):
    facts = [
        fact("base", "The user carries a steel bottle."),
        fact("health", "The user has mild myopia."),
    ]
    catalog = balanced_catalog(["base"])
    residual_fingerprint = source_bank_fingerprint([facts[1]])
    combined = __import__("hashlib").sha256(
        f"{catalog.node_id}:{residual_fingerprint}".encode("utf-8")
    ).hexdigest()
    current = supplement_node()
    current.custom["source_bank_fingerprint"] = combined
    graph = FakeGraphStore([catalog, current])

    class FailProvider:
        def __init__(self, config):
            raise AssertionError("LLM must not be constructed")

    monkeypatch.setenv("MEMORY_EVOLING_BALANCED_CATALOG_ENABLED", "true")
    monkeypatch.setenv("MEMORY_HYBRID_V2_BALANCED_CATALOG_L0_ENABLED", "true")
    monkeypatch.setenv("MEMORY_EVOLING_SPECIFIC_SUPPLEMENT_ENABLED", "true")
    monkeypatch.setattr(
        "hy_memory.pipelines.specific_supplement.LLMProvider", FailProvider
    )
    result = run(run_specific_supplement_generation(
        user_id="u1",
        vector_store=FakeVectorStore(facts), graph_store=graph, config=object(),
    ))
    assert result["reason"] == "current_specific_supplement_exists"
    assert result["prompt_tokens"] == 0
    assert graph.upserts == []
    assert graph.links == []
    assert graph.updates == []


def test_cloned_supplement_is_adopted_with_remapped_exact_evidence(monkeypatch):
    facts = [
        fact("base", "The user carries a steel bottle."),
        fact("new-health", "The user has mild myopia."),
        fact(
            "new-mentor",
            "The user asked for help editing a post. The user learned patience "
            "from a longtime mentor and still follows that advice.",
        ),
    ]
    old = supplement_node(
        f"{SUPPLEMENT_MARKER}\n"
        "- [health_accessibility] The user has mild myopia.\n"
        "- [values_coping] The user learned patience from a longtime mentor "
        "and still follows that advice."
    )
    old.node_id = "cloned-old-supplement"
    old.evidence_chain = ["new-health", "new-mentor"]
    old.custom.update({
        "source_bank_fingerprint": "source-namespace-fingerprint",
        "selected_count": 2,
        "domains": {
            "health_accessibility": ["old-health"],
            "values_coping": ["old-mentor"],
        },
    })
    graph = FakeGraphStore([balanced_catalog(["base"]), old])

    class FailProvider:
        def __init__(self, config):
            raise AssertionError("clone adoption must not construct the LLM")

    monkeypatch.setenv("MEMORY_EVOLING_BALANCED_CATALOG_ENABLED", "true")
    monkeypatch.setenv("MEMORY_HYBRID_V2_BALANCED_CATALOG_L0_ENABLED", "true")
    monkeypatch.setenv("MEMORY_EVOLING_SPECIFIC_SUPPLEMENT_ENABLED", "true")
    monkeypatch.setattr(
        "hy_memory.pipelines.specific_supplement.LLMProvider", FailProvider
    )
    result = run(run_specific_supplement_generation(
        user_id="u1",
        vector_store=FakeVectorStore(facts), graph_store=graph, config=object(),
    ))
    assert result["success"] is True
    assert result["reason"] == "cloned_specific_supplement_adopted"
    assert result["selected_count"] == 2
    assert result["prompt_tokens"] == 0
    adopted = graph.nodes[result["supplement_node_id"]]
    assert adopted.agent_id == ""
    assert adopted.content == old.content
    assert adopted.evidence_chain == ["new-health", "new-mentor"]
    assert adopted.custom["clone_adoption_version"] == "exact-evidence-remap-v1"
    assert adopted.custom["domains"]["health_accessibility"] == ["new-health"]
    assert adopted.custom["domains"]["values_coping"] == ["new-mentor"]
    assert graph.nodes["cloned-old-supplement"].status == MemoryStatus.SUPERSEDED


def test_agent_scoped_supplement_migrates_to_user_scope_without_llm(monkeypatch):
    facts = [
        fact("base", "The user carries a steel bottle."),
        fact("health", "The user has mild myopia."),
    ]
    old = supplement_node()
    old.node_id = "agent-scoped-supplement"
    old.agent_id = "agent-b"
    old.evidence_chain = ["health"]
    catalog = balanced_catalog(["base"])
    residual_fingerprint = source_bank_fingerprint([facts[1]])
    old.custom.update({
        "source_bank_fingerprint": __import__("hashlib").sha256(
            f"{catalog.node_id}:{residual_fingerprint}".encode("utf-8")
        ).hexdigest(),
        "base_catalog_node_id": catalog.node_id,
        "selected_count": 1,
        "domains": {"health_accessibility": ["health"]},
    })
    graph = FakeGraphStore([catalog, old])
    monkeypatch.setenv("MEMORY_EVOLING_SPECIFIC_SUPPLEMENT_ENABLED", "true")
    monkeypatch.setenv("MEMORY_USER_PROFILE_BALANCED_CATALOG_ENABLED", "true")

    class FailProvider:
        def __init__(self, config):
            raise AssertionError("agent-scope migration must not call the LLM")

    monkeypatch.setattr(
        "hy_memory.pipelines.specific_supplement.LLMProvider", FailProvider,
    )
    result = run(run_specific_supplement_generation(
        user_id="u1", vector_store=FakeVectorStore(facts),
        graph_store=graph, config=object(),
    ))

    assert result["reason"] == "cloned_specific_supplement_adopted"
    migrated = graph.nodes[result["supplement_node_id"]]
    assert migrated.agent_id == ""
    assert migrated.custom["profile_scope"] == "user"
    assert graph.nodes["agent-scoped-supplement"].status == MemoryStatus.SUPERSEDED


def test_supplement_with_any_still_valid_custom_id_is_not_clone_adopted(monkeypatch):
    facts = [
        fact("base", "The user carries a steel bottle."),
        fact("health", "The user has mild myopia."),
    ]
    old = supplement_node()
    old.node_id = "same-namespace-old"
    old.evidence_chain = ["health"]
    old.custom.update({
        "source_bank_fingerprint": "old-bank",
        "selected_count": 1,
        "domains": {"health_accessibility": ["health"]},
    })
    graph = FakeGraphStore([balanced_catalog(["base"]), old])
    SequenceProvider.responses = [json.dumps({
        "domains": {"health_accessibility": [1]},
    })]
    SequenceProvider.calls = []
    monkeypatch.setenv("MEMORY_EVOLING_BALANCED_CATALOG_ENABLED", "true")
    monkeypatch.setenv("MEMORY_HYBRID_V2_BALANCED_CATALOG_L0_ENABLED", "true")
    monkeypatch.setenv("MEMORY_EVOLING_SPECIFIC_SUPPLEMENT_ENABLED", "true")
    monkeypatch.setattr(
        "hy_memory.pipelines.specific_supplement.LLMProvider", SequenceProvider
    )
    result = run(run_specific_supplement_generation(
        user_id="u1",
        vector_store=FakeVectorStore(facts), graph_store=graph, config=object(),
    ))
    assert result["success"] is True
    assert result.get("reason") != "cloned_specific_supplement_adopted"
    assert len(SequenceProvider.calls) == 1


def test_cloned_supplement_with_unmatched_visible_line_falls_back(monkeypatch):
    facts = [
        fact("base", "The user carries a steel bottle."),
        fact("health", "The user has mild myopia."),
    ]
    old = supplement_node(
        f"{SUPPLEMENT_MARKER}\n"
        "- [health_accessibility] The user has severe hyperopia."
    )
    old.node_id = "invalid-cloned-old"
    old.evidence_chain = ["health"]
    old.custom.update({
        "source_bank_fingerprint": "source-namespace-fingerprint",
        "selected_count": 1,
        "domains": {"health_accessibility": ["old-health"]},
    })
    graph = FakeGraphStore([balanced_catalog(["base"]), old])
    SequenceProvider.responses = [json.dumps({
        "domains": {"health_accessibility": [1]},
    })]
    SequenceProvider.calls = []
    monkeypatch.setenv("MEMORY_EVOLING_BALANCED_CATALOG_ENABLED", "true")
    monkeypatch.setenv("MEMORY_HYBRID_V2_BALANCED_CATALOG_L0_ENABLED", "true")
    monkeypatch.setenv("MEMORY_EVOLING_SPECIFIC_SUPPLEMENT_ENABLED", "true")
    monkeypatch.setattr(
        "hy_memory.pipelines.specific_supplement.LLMProvider", SequenceProvider
    )
    result = run(run_specific_supplement_generation(
        user_id="u1",
        vector_store=FakeVectorStore(facts), graph_store=graph, config=object(),
    ))
    assert result["success"] is True
    assert result.get("reason") != "cloned_specific_supplement_adopted"
    assert len(SequenceProvider.calls) == 1
    assert "mild myopia" in graph.nodes[result["supplement_node_id"]].content


def test_materialize_exact_artifact_replaces_current_without_llm(monkeypatch):
    facts = [
        fact("base", "The user carries a steel bottle."),
        fact("health", "The user has mild myopia."),
        fact(
            "mentor",
            "The user asked for help editing a post. The user learned patience "
            "from a longtime mentor and still follows that advice.",
        ),
    ]
    current = supplement_node()
    graph = FakeGraphStore([balanced_catalog(["base"]), current])
    monkeypatch.setenv("MEMORY_HYBRID_V2_BALANCED_CATALOG_L0_ENABLED", "true")
    result = run(materialize_specific_supplement(
        user_id="u1",
        entries=[
            {
                "domain": "health_accessibility",
                "parent_node_id": "health",
                "content": "The user has mild myopia.",
            },
            {
                "domain": "values_coping",
                "parent_node_id": "mentor",
                "content": (
                    "The user learned patience from a longtime mentor and "
                    "still follows that advice."
                ),
            },
        ],
        vector_store=FakeVectorStore(facts), graph_store=graph,
        materialization_source="frozen-system2-artifact",
    ))
    assert result["success"] is True
    assert result["reason"] == "specific_supplement_artifact_materialized"
    assert result["selected_count"] == 2
    assert result["prompt_tokens"] == result["completion_tokens"] == 0
    node = graph.nodes[result["supplement_node_id"]]
    assert node.agent_id == ""
    assert node.evidence_chain == ["health", "mentor"]
    assert node.custom["materialization_version"] == "exact-evidence-artifact-v1"
    assert node.custom["materialization_source"] == "frozen-system2-artifact"
    assert node.custom["clause_salvage_count"] == 1
    assert "The user asked" not in node.content
    assert graph.nodes[current.node_id].status == MemoryStatus.SUPERSEDED


def test_materialize_empty_artifact_is_persistent_but_search_invisible(monkeypatch):
    facts = [fact("base", "The user carries a steel bottle.")]
    graph = FakeGraphStore([balanced_catalog(["base"]), supplement_node()])
    monkeypatch.setenv("MEMORY_HYBRID_V2_BALANCED_CATALOG_L0_ENABLED", "true")
    monkeypatch.setenv("MEMORY_HYBRID_V2_SPECIFIC_SUPPLEMENT_L0_ENABLED", "true")
    result = run(materialize_specific_supplement(
        user_id="u1", entries=[],
        vector_store=FakeVectorStore(facts), graph_store=graph,
        materialization_source="empty-frozen-artifact",
    ))
    assert result["success"] is True
    assert result["selected_count"] == 0
    node = graph.nodes[result["supplement_node_id"]]
    assert node.custom["artifact_empty"] is True
    assert node.evidence_chain == []
    assert run(get_active_specific_supplement(
        graph, user_id="u1",
    )) is None


def test_materialize_invalid_artifact_fails_closed_without_retirement(monkeypatch):
    facts = [
        fact("base", "The user carries a steel bottle."),
        fact("health", "The user has mild myopia."),
    ]
    current = supplement_node()
    graph = FakeGraphStore([balanced_catalog(["base"]), current])
    monkeypatch.setenv("MEMORY_HYBRID_V2_BALANCED_CATALOG_L0_ENABLED", "true")
    result = run(materialize_specific_supplement(
        user_id="u1",
        entries=[{
            "domain": "health_accessibility",
            "parent_node_id": "health",
            "content": "The user has severe hyperopia.",
        }],
        vector_store=FakeVectorStore(facts), graph_store=graph,
        materialization_source="invalid-artifact",
    ))
    assert result["success"] is False
    assert "not exact parent evidence" in result["error"]
    assert graph.nodes[current.node_id].status == MemoryStatus.ACTIVE
    assert graph.upserts == []
    assert graph.links == []
    assert graph.updates == []
