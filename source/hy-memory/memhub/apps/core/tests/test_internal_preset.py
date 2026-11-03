"""The optional model preset a configured build carries.

A user should not have to apply for a model key before they can find out
whether a memory product is worth using. The preset fills in everything a
teammate cannot be expected to know — endpoint, model name, thinking chain —
and leaves exactly one field for them.

The repository carries no vendor endpoint or model name. A distributor may
provide a generic HTTPS endpoint at build time; a normal build carries none.
"""

import ast
from pathlib import Path

import pytest

from one_memory.model_presets import (
    PRESET_PROFILE_NAME,
    configured_preset,
    seed_preset_profile,
)
from one_memory.model_profiles import ModelProfileStore, ProviderKind
from one_memory.secrets import InMemorySecretStore

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def configured_build(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ONE_MEMORY_MODEL_PRESET_BASE_URL", "https://models.example.com/v1")
    monkeypatch.setenv("ONE_MEMORY_MODEL_PRESET_MODEL", "memory-model")


@pytest.fixture
def open_build(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ONE_MEMORY_MODEL_PRESET_BASE_URL", raising=False)
    monkeypatch.delenv("ONE_MEMORY_MODEL_PRESET_MODEL", raising=False)


def _store(tmp_path):
    return ModelProfileStore(tmp_path / "one-memory.sqlite3"), InMemorySecretStore()


def test_a_fresh_data_dir_gets_a_preset_needing_only_a_key(tmp_path, configured_build) -> None:
    profiles, secrets = _store(tmp_path)

    seeded = seed_preset_profile(profiles, secrets)

    assert seeded is not None
    assert seeded.name == PRESET_PROFILE_NAME
    assert seeded.provider_kind is ProviderKind.OPENAI_COMPATIBLE
    assert seeded.model == "memory-model"
    assert seeded.has_api_key is False
    assert [profile.name for profile in profiles.list(secrets)] == [PRESET_PROFILE_NAME]


def test_the_preset_endpoint_uses_https(tmp_path, configured_build) -> None:
    profiles, secrets = _store(tmp_path)

    seeded = seed_preset_profile(profiles, secrets)

    assert seeded is not None
    assert seeded.base_url is not None
    assert seeded.base_url.startswith("https://")


def test_the_preset_has_the_thinking_chain_off(tmp_path, configured_build) -> None:
    """Measured on the same extraction prompt: 22.5s and 1262 tokens with the
    chain and one item missed, against 1.8s and 39 tokens without it and all
    items found. Twelve times the latency, thirty-two times the tokens, and
    worse output: extraction is a structured-output task, so the chain is pure
    overhead here."""
    profiles, secrets = _store(tmp_path)

    seeded = seed_preset_profile(profiles, secrets)

    assert seeded is not None
    assert seeded.disable_thinking is True


def test_the_preset_is_left_waiting_rather_than_activated(tmp_path, configured_build) -> None:
    """Waiting for a key is not the same state as configured wrongly.

    Activation checks capabilities on purpose, and a profile with no key
    cannot have any. Seeding must not loosen that to make its own profile
    activate; the interface tells the two states apart in wording instead.
    """
    profiles, secrets = _store(tmp_path)

    seeded = seed_preset_profile(profiles, secrets)

    assert seeded is not None
    assert seeded.is_active is False
    assert seeded.capabilities.model_available is False


def test_a_build_without_the_switch_carries_no_preset(tmp_path, open_build) -> None:
    profiles, secrets = _store(tmp_path)

    assert configured_preset() is None
    assert seed_preset_profile(profiles, secrets) is None
    assert profiles.list(secrets) == []


@pytest.mark.parametrize(
    "missing",
    ["ONE_MEMORY_MODEL_PRESET_BASE_URL", "ONE_MEMORY_MODEL_PRESET_MODEL"],
)
def test_an_incomplete_preset_is_ignored(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    monkeypatch.setenv("ONE_MEMORY_MODEL_PRESET_BASE_URL", "https://models.example.com/v1")
    monkeypatch.setenv("ONE_MEMORY_MODEL_PRESET_MODEL", "memory-model")
    monkeypatch.delenv(missing)

    assert configured_preset() is None


def test_a_remote_plain_http_preset_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONE_MEMORY_MODEL_PRESET_BASE_URL", "http://models.example.com/v1")
    monkeypatch.setenv("ONE_MEMORY_MODEL_PRESET_MODEL", "memory-model")

    with pytest.raises(ValueError, match="HTTPS"):
        configured_preset()


def test_the_preset_does_not_come_back_after_the_user_deletes_it(
    tmp_path,
    configured_build,
) -> None:
    """Deleting it has to mean something, including across a restart."""
    profiles, secrets = _store(tmp_path)
    seeded = seed_preset_profile(profiles, secrets)
    assert seeded is not None
    profiles.delete(seeded.profile_id, secrets)

    assert seed_preset_profile(profiles, secrets) is None
    assert profiles.list(secrets) == []


def test_seeding_twice_leaves_one_profile(tmp_path, configured_build) -> None:
    profiles, secrets = _store(tmp_path)

    first = seed_preset_profile(profiles, secrets)
    second = seed_preset_profile(profiles, secrets)

    assert first is not None
    assert second is None
    assert len(profiles.list(secrets)) == 1


def test_preset_configuration_does_not_import_a_generated_module() -> None:
    module_path = REPOSITORY_ROOT / "apps" / "core" / "src" / "one_memory" / "model_presets.py"
    tree = ast.parse(module_path.read_text())

    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "one_memory.model_preset_data" not in imported

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "import_module" not in called
