from hy_memory.config import MemoryConfig


def test_verbatim_fallback_defaults_disabled(monkeypatch):
    monkeypatch.delenv("MEMORY_CODING_VERBATIM_FALLBACK_ENABLED", raising=False)
    assert MemoryConfig().coding.verbatim_fallback_enabled is False


def test_verbatim_fallback_env_can_enable(monkeypatch):
    monkeypatch.setenv("MEMORY_CODING_VERBATIM_FALLBACK_ENABLED", "true")
    assert MemoryConfig().coding.verbatim_fallback_enabled is True


def test_verbatim_fallback_from_dict_can_enable(monkeypatch):
    monkeypatch.delenv("MEMORY_CODING_VERBATIM_FALLBACK_ENABLED", raising=False)
    config = MemoryConfig.from_dict({
        "coding": {"verbatim_fallback_enabled": True},
    })
    assert config.coding.verbatim_fallback_enabled is True
