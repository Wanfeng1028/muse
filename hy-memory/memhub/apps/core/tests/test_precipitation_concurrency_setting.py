"""Rule 2/9: precipitation concurrency is configurable, not hardcoded to 1.

`api.py` passed `max_concurrent_tasks=1` literally. `a59f4b5` labelled that
"验收包临时" (temporary, for an acceptance package) and the config comment
next to `import_max_concurrent_jobs` says the durable fix is an admission
controller, not a larger constant — but a hardcoded 1 is rule 9's exact
anti-pattern: a small number baked into code that no machine can tune.

The concern behind it was real, so it was measured rather than argued away:
`tests/measure_recall_under_precipitation.py`. With readers actually held,
recall latency at concurrency 1 and 4 is indistinguishable (median 272ms vs
272ms) and only degrades at 8 (522ms). So the pin is replaced by a setting
that defaults to "whatever the profile allows", which is 4.

This file guards the wiring: the setting must reach the supervisor, and
leaving it unset must not silently fall back to 1.
"""

from __future__ import annotations

import ast
from pathlib import Path

from one_memory.config import Settings

API = Path(__file__).resolve().parents[1] / "src" / "one_memory" / "api.py"


def test_the_concurrency_is_not_a_hardcoded_literal() -> None:
    """A literal `max_concurrent_tasks=1` is the thing being removed.

    String-matching the source is deliberately crude: the failure mode being
    guarded against is someone re-pinning the number during an incident, and
    no runtime test would catch a literal that only appears in production.
    """
    tree = ast.parse(API.read_text())
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.keyword)
        and node.arg == "max_concurrent_tasks"
        and isinstance(node.value, ast.Constant)
    ]
    assert literals == [], f"concurrency is pinned to a literal again: {literals}"


def test_the_setting_defaults_to_the_profile_not_to_one() -> None:
    """Unset must mean "profile decides", which is 4 — not a silent 1."""
    settings = Settings(_env_file=None)
    assert settings.precipitation_max_concurrent_tasks is None


def test_the_setting_is_configurable_per_machine() -> None:
    settings = Settings(_env_file=None, precipitation_max_concurrent_tasks=8)
    assert settings.precipitation_max_concurrent_tasks == 8


def test_profile_max_concurrency_is_four() -> None:
    """The number the profile contributes, asserted so it cannot drift.

    If the profile default were ever lowered to 1, unpinned concurrency would
    silently become serial again and nothing above would fail.
    """
    from one_memory.model_profiles import ModelProfileInput

    assert ModelProfileInput.model_fields["max_concurrency"].default == 4
