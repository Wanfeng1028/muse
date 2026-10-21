"""What `semantic_search` should do once the profile that filled the store is gone.

Deactivating or deleting a model profile does not delete the memories that
profile produced, but `semantic_search` gave up as soon as it could not find
an active one. The retrieval it abandoned needs no generation model at all:
the built-in ONNX encoder is what wrote those vectors in the first place.
"""

from pathlib import Path

import pytest

from one_memory.hy_memory_bridge import (
    HY_MEMORY_NAMESPACE,
    GraphWidthMismatch,
    GraphWidthMismatchError,
    builtin_retrieval_snapshot,
)
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_governance import MemoryGovernanceStore
from one_memory.memory_processing import MemoryProcessingSupervisor
from one_memory.memory_tasks import MemoryTaskStore
from one_memory.model_profiles import (
    ModelCapabilities,
    ModelProfileInput,
    ModelProfileStore,
    ProviderKind,
)
from one_memory.secrets import InMemorySecretStore


class RecordingBridge:
    def __init__(self, snapshot, hits: tuple[str, ...] = ()) -> None:
        self.snapshot = snapshot
        self.hits = hits

    async def search_scores(self, query: str, **_: object) -> tuple[object, ...]:
        del query
        return tuple((memory_id, 0.9) for memory_id in self.hits)


def _supervisor(tmp_path, *, hits: tuple[str, ...] = (), built: list | None = None):
    database = tmp_path / "one-memory.sqlite3"
    secrets = InMemorySecretStore()
    profiles = ModelProfileStore(database)

    def factory(snapshot, _secret, data_dir):
        # Building the real client is what creates the store on disk, so the
        # stand-in has to create it too: without that, "no store was built"
        # is a sentence no assertion could ever falsify.
        (data_dir / "hy-memory" / HY_MEMORY_NAMESPACE / "graph").mkdir(
            parents=True,
            exist_ok=True,
        )
        bridge = RecordingBridge(snapshot, hits)
        if built is not None:
            built.append(bridge)
        return bridge

    supervisor = MemoryProcessingSupervisor(
        tasks=MemoryTaskStore(database),
        profiles=profiles,
        secrets=secrets,
        evidence=EvidenceStore(database),
        governance=MemoryGovernanceStore(database),
        data_dir=tmp_path,
        bridge_factory=factory,
    )
    return supervisor, profiles, secrets


def _plant_store(tmp_path: Path) -> None:
    """Give the data directory the graph an earlier extraction would have left."""
    graph = tmp_path / "hy-memory" / HY_MEMORY_NAMESPACE / "graph"
    graph.mkdir(parents=True)
    (graph / "catalog.kz").write_bytes(b"")


def _activate(profiles, secrets):
    created = profiles.create(
        ModelProfileInput(
            name="Local",
            provider_kind=ProviderKind.OLLAMA,
            model="hy-bot-phi4",
            embedding_model="nomic-embed-text",
        ),
        secrets,
    )
    profiles.record_capabilities(
        created.profile_id,
        expected_revision=created.revision,
        capabilities=ModelCapabilities(
            endpoint_reachable=True,
            model_available=True,
            structured_output=True,
            embedding_available=True,
        ),
        secrets=secrets,
    )
    return profiles.activate(created.profile_id, secrets)


@pytest.mark.anyio
async def test_a_library_left_by_a_retired_profile_is_still_searchable(tmp_path) -> None:
    supervisor, _profiles, _secrets = _supervisor(tmp_path, hits=("memory-1",))
    _plant_store(tmp_path)

    found = await supervisor.semantic_search("抽取")

    assert found == (("memory-1", 0.9),)


@pytest.mark.anyio
async def test_no_store_on_disk_is_not_a_reason_to_build_one(tmp_path) -> None:
    """Searching must not leave a 512-wide graph behind for an undecided user.

    Building the client is what creates the store, and the width it creates is
    the built-in encoder's. A user who has not chosen a model yet would then
    meet a width mismatch on their first 768-wide profile: an accident this
    search invented, in the same shape as the one that retired a live graph.
    """
    supervisor, _profiles, _secrets = _supervisor(tmp_path, hits=("memory-1",))

    found = await supervisor.semantic_search("抽取")

    assert found == ()
    assert not (tmp_path / "hy-memory").exists()


@pytest.mark.anyio
async def test_a_store_written_wider_is_left_to_the_width_prompt(tmp_path) -> None:
    supervisor, _profiles, _secrets = _supervisor(tmp_path)
    _plant_store(tmp_path)

    class WiderStore(RecordingBridge):
        async def search_scores(self, query: str, **_: object) -> tuple[object, ...]:
            # Where the real one raises: the client is built lazily, on the
            # first search, and it is building it that reads the stored width.
            del query
            raise GraphWidthMismatchError(
                GraphWidthMismatch(
                    stored_width=768,
                    expected_width=512,
                    graph_path=str(tmp_path / "graph"),
                )
            )

    supervisor.bridge_factory = lambda snapshot, _secret, _data_dir: WiderStore(snapshot)

    assert await supervisor.semantic_search("抽取") == ()


@pytest.mark.anyio
async def test_retrieval_reaches_hy_as_a_local_encoder_needing_no_key(tmp_path) -> None:
    built: list[RecordingBridge] = []
    supervisor, _profiles, _secrets = _supervisor(tmp_path, built=built)
    _plant_store(tmp_path)

    await supervisor.semantic_search("抽取")

    snapshot = built[0].snapshot
    assert snapshot.embedding_provider_kind is ProviderKind.LOCAL_ONNX
    assert snapshot.has_api_key is False
    assert snapshot == builtin_retrieval_snapshot()


@pytest.mark.anyio
async def test_the_retrieval_bridge_does_not_occupy_a_real_profiles_cache_slot(
    tmp_path,
) -> None:
    """Otherwise pasting a key would change nothing the user can see.

    The cache is keyed by profile id and revision. Were the retrieval snapshot
    to collide with a real profile's key, the bridge built with no generation
    model would be handed back after the user configured one, and extraction
    would go on doing nothing with no error anywhere to explain it.
    """
    built: list[RecordingBridge] = []
    supervisor, profiles, secrets = _supervisor(tmp_path, built=built)
    _plant_store(tmp_path)

    await supervisor.semantic_search("抽取")
    active = _activate(profiles, secrets)
    await supervisor._prewarm_write_bridges(("cursor",))  # noqa: SLF001
    await supervisor.semantic_search("抽取")

    assert len(built) == 3
    assert len({id(bridge) for bridge in built}) == 3
    assert built[0].snapshot == builtin_retrieval_snapshot()
    assert {bridge.snapshot.profile_id for bridge in built[1:]} == {active.profile_id}
