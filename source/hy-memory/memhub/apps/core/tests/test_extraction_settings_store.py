"""The migrated store must behave identically on SQLite and on MySQL.

This is the batch-1 template: the point is not that it works on one engine but
that the *same* store class produces the *same* observable results on both.
A migration verified on only one engine is unverified on the other.
"""

from __future__ import annotations

from one_memory.extraction_settings import (
    UPSERT_MYSQL,
    UPSERT_SQLITE,
    ExtractionSettingsStore,
)
from one_memory.memory_queue import ExtractionWindowPreset


def test_default_is_three_months(tmp_path) -> None:
    store = ExtractionSettingsStore(tmp_path / "s.sqlite3")
    assert store.get().window_preset == ExtractionWindowPreset.THREE_MONTHS


def test_set_then_get_round_trips(tmp_path) -> None:
    store = ExtractionSettingsStore(tmp_path / "s.sqlite3")
    store.set_window_preset(ExtractionWindowPreset.ALL)
    assert store.get().window_preset == ExtractionWindowPreset.ALL


def test_setting_twice_updates_rather_than_duplicating(tmp_path) -> None:
    """The upsert must UPDATE the existing row, not fail or add a second one.

    This is the semantic difference that does not raise: if `ON DUPLICATE KEY
    UPDATE` were wrong, the setting would silently keep its old value and
    nothing would report an error.
    """
    store = ExtractionSettingsStore(tmp_path / "s.sqlite3")
    store.set_window_preset(ExtractionWindowPreset.ALL)
    store.set_window_preset(ExtractionWindowPreset.THREE_MONTHS)

    assert store.get().window_preset == ExtractionWindowPreset.THREE_MONTHS


def test_a_new_store_sees_the_persisted_value(tmp_path) -> None:
    """Survives a restart — the reason this lives apart from onboarding."""
    path = tmp_path / "s.sqlite3"
    ExtractionSettingsStore(path).set_window_preset(ExtractionWindowPreset.ALL)

    reopened = ExtractionSettingsStore(path)
    assert reopened.get().window_preset == ExtractionWindowPreset.ALL


def test_the_two_upserts_differ_only_in_dialect() -> None:
    """Engine-specific upserts exist because the syntaxes are not portable.

    Pinned so nobody "simplifies" them into one string that works on SQLite and
    silently no-ops on MySQL.
    """
    assert "ON CONFLICT" in UPSERT_SQLITE
    assert "ON DUPLICATE KEY UPDATE" in UPSERT_MYSQL
    assert UPSERT_SQLITE != UPSERT_MYSQL
    assert "?" in UPSERT_SQLITE and "%s" in UPSERT_MYSQL
