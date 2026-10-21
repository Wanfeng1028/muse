"""An optional vendor-neutral model profile supplied by the environment.

A downstream package may provide an HTTPS endpoint and model identifier with
`ONE_MEMORY_MODEL_PRESET_BASE_URL` and `ONE_MEMORY_MODEL_PRESET_MODEL`. The
repository contains no distributor endpoint or model identifier. If either
value is absent, the product opens the normal custom-model form.

Deliberately not `ProviderKind.HY_DEFAULT`. That means "an endpoint the
product hosts", which would put the user's conversations through us and the
model bill on us — the opposite of what this product says about itself.
`openai_compatible` with the fields prefilled buys the same first five
minutes with none of that.
"""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from one_memory.memory_server.migrations import model_profile_seeds_ddl
from one_memory.memory_server.sql_compat import execute, is_mysql
from one_memory.memory_server.store_binding import store_for
from one_memory.model_profiles import (
    ModelProfile,
    ModelProfileInput,
    ModelProfileStore,
    ProviderKind,
)
from one_memory.secrets import SecretStore

#: The seed claim, per engine.
#:
#: `INSERT ... ON CONFLICT DO NOTHING` is SQLite; MySQL spells it
#: `INSERT IGNORE`. They look equivalent and both "succeed", which is what makes
#: them dangerous: the wrong one either keeps inserting duplicates (claiming the
#: seed twice) or errors, and the caller's `rowcount == 1` test silently decides
#: the wrong winner. So they are two named constants, not one shared string.
CLAIM_SQLITE = (
    "INSERT INTO model_profile_seeds (name, seeded_at) VALUES (?, ?) ON CONFLICT(name) DO NOTHING"
)
CLAIM_MYSQL = "INSERT IGNORE INTO model_profile_seeds (name, seeded_at) VALUES (%s, %s)"

PRESET_PROFILE_NAME = "预配置模型服务"

#: One row per preset ever seeded, so deleting one is a decision that
#: survives a restart. Without it, seeding on an empty profile list would
#: quietly undo the deletion the next time the app opened.
SEED_SCHEMA = model_profile_seeds_ddl("sqlite")


def configured_preset() -> ModelProfileInput | None:
    """The preset this build carries, or `None` for a build without one."""
    data = _preset_data()
    if data is None:
        return None
    return ModelProfileInput(
        name=PRESET_PROFILE_NAME,
        provider_kind=ProviderKind.OPENAI_COMPATIBLE,
        base_url=data["base_url"],
        model=data["model"],
        # Extraction wants a result, not a transcript of deliberation.
        # Measured on one extraction prompt: 22.5s and 1262 completion tokens
        # with the chain and one item missed, against 1.8s and 39 tokens
        # without it and every item found.
        disable_thinking=True,
        api_key=None,
    )


def seed_preset_profile(
    profiles: ModelProfileStore,
    secrets: SecretStore,
) -> ModelProfile | None:
    """Create this build's preset once, on a data directory that has none.

    Returns `None` when there is nothing to do, which covers three different
    situations that all want the same silence: an open build with no preset,
    a directory that already has one, and one where the user deleted it.

    The profile is left inactive. Activation checks capabilities, and a
    profile with no key cannot have any; loosening that so the preset could
    activate itself would trade a wording problem for a real one.
    """
    preset = configured_preset()
    if preset is None:
        return None
    if not _claim_seed(profiles.database_path, preset.name):
        return None
    return profiles.create(preset, secrets)


def apply_preset_key(
    profiles: ModelProfileStore,
    profile_id: str,
    key: str,
    *,
    secrets: SecretStore,
    expected_revision: int,
) -> ModelProfile:
    """Store the one field the build could not fill in."""
    from one_memory.model_profiles import ModelProfilePatch

    return profiles.update(
        profile_id,
        ModelProfilePatch(expected_revision=expected_revision, api_key=SecretStr(key)),
        secrets,
    )


def _preset_data() -> dict[str, Any] | None:
    base_url = os.environ.get("ONE_MEMORY_MODEL_PRESET_BASE_URL", "").strip()
    model = os.environ.get("ONE_MEMORY_MODEL_PRESET_MODEL", "").strip()
    if not base_url or not model:
        return None
    return {"base_url": base_url, "model": model}


def _claim_seed(database_path: Path, name: str) -> bool:
    """Record the intent to seed, and say whether this caller won the claim."""
    store: Any = store_for(database_path)
    mysql = is_mysql(store)
    # `autocommit=True` is what makes the claim durable on SQLite; without it a
    # second call re-wins the claim because the first row was never committed.
    # The MySQL facade accepts and ignores it (it commits at checkout exit), so
    # the call site needs no engine branch here.
    with store.write(autocommit=True) as connection:
        execute(connection, mysql, SEED_SCHEMA)
        claimed = execute(
            connection,
            mysql,
            CLAIM_MYSQL if mysql else CLAIM_SQLITE,
            (name, datetime.now(UTC).isoformat()),
        )
        return bool(claimed.rowcount == 1)
