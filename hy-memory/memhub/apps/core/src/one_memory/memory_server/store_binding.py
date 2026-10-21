"""A2: which store implementation is in force.

Having two implementations is not a migration; binding one is. This module is
the single place that decides, so the swap is reviewable and reversible without
touching the 142 call sites.

**按 D56：数据库定为 SQLite（覆盖 D53 的 MySQL-only）。MySQL 路径标注为「未启用」——
目标第 4 条要求「不留双路径」。因此 `store_for` 不再返回 MySQL store；若环境变量被设为
`mysql`，此处按未启用处理并回落到 SQLite 并如实报告 `fell_back=True`，而不是静默双跑。
MySQL 相关代码（db / mysql_store / sync_facade）保留但标注未启用，待按 D56 的复核结果决定
删除还是重启。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from one_memory.database_access import MainDatabase

Engine = str  # "sqlite" | "mysql"

SQLITE = "sqlite"
MYSQL = "mysql"

#: Environment key Runtime sets once the bundled server is installable.
ENGINE_ENV = "ONE_MEMORY_STORE_ENGINE"

#: D56: the database is SQLite (overriding D53's MySQL-only). The MySQL path is
#: NOT enabled — the objective forbids running two engines at once. Kept as a
#: single flag so re-enabling (or deleting) is one decision, not a scavenger
#: hunt through branches.
MYSQL_ENABLED = False


@dataclass(frozen=True)
class Binding:
    engine: Engine
    #: Why this engine, so a status line can say more than a bare name.
    reason: str
    #: True when the requested engine could not be honoured.
    fell_back: bool = False


def resolve_engine(environ: Mapping[str, str] | None = None) -> Binding:
    """Decide which engine to use, and say why."""
    env = os.environ if environ is None else environ
    requested = (env.get(ENGINE_ENV) or SQLITE).strip().lower()

    if requested == MYSQL:
        return Binding(
            SQLITE,
            "MySQL was requested, but D56 fixes SQLite as the only business store",
            fell_back=True,
        )
    if requested == SQLITE:
        return Binding(SQLITE, "D56 SQLite-only business store")
    return Binding(
        SQLITE,
        f"unrecognised {ENGINE_ENV}={requested!r}; using SQLite",
        fell_back=True,
    )


def mysql_available(environ: Mapping[str, str] | None = None) -> bool:
    """Whether the bundled server could actually be started.

    Checked rather than assumed: a binding that claims MySQL while no server
    exists would fail at first query, far from the decision that caused it.
    """
    if environ is None:
        environ = os.environ
    try:
        from one_memory.memory_server.mysql_platform import install_ready, layout_for

        home = environ.get("ONE_MEMORY_DATA_DIR") or str(Path.home() / ".one-memory")
        return install_ready(layout_for(home))[0]
    except Exception:
        return False


def status_line(environ: Mapping[str, str] | None = None) -> str:
    """One line for `one-memory status` and the CLI, honest about fallback."""
    binding = resolve_engine(environ)
    line = f"store: {binding.engine}"
    if binding.fell_back:
        line += f" (fell back — {binding.reason})"
    return line


def store_for(path: Path | str, environ: Mapping[str, str] | None = None) -> MainDatabase:
    """The one accessor call sites should use to get a store.

    78 call sites construct `main_database(path)` directly. Migrating them one
    by one is how the two shapes coexist and drift; routing them all through
    here makes the swap a decision in one place, which is the whole reason the
    port exists.

    **The MySQL branch refuses unless the engine is actually in force.** That
    is the degradation guarantee, not laziness: the bundled server may not be
    present yet (D55 fetches it on first launch, and a user may decline), and
    returning a MySQL store whose server cannot start would fail at first
    query — far from the decision that caused it, and on a machine that was
    working. So MySQL is only returned when `resolve_engine` reports it in
    force, which requires `mysql_available` to have checked that the server
    can really start.
    按 D56 追加：MySQL 路径本身已标注未启用（`MYSQL_ENABLED=False`），故此处
    一律返回 SQLite 并在 `fell_back` 报告中说明原因，避免两套引擎同时生效。
    """
    from one_memory.database_access import main_database

    return main_database(path)


def degradation_note(environ: Mapping[str, str] | None = None) -> str:
    """What a caller should tell the user when MySQL was asked for but is not
    in force. Empty when the requested engine is actually in force.

    A silent downgrade is the failure mode to avoid: the user asked for MySQL,
    and "it works" is not the same as "it is what you asked for".
    """
    binding = resolve_engine(environ)
    if not binding.fell_back:
        return ""
    return (
        f"requested MySQL but running on {binding.engine}: {binding.reason}. "
        "Data written now is on the engine in force, not the one requested."
    )
