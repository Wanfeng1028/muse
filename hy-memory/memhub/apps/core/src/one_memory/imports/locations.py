"""Candidate location checks never enumerate or open conversation files."""

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from one_memory.imports.access import (
    SourceAccessError,
    SourceAccessErrorCode,
    source_root_identity,
)


class SourceLocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    state: Literal["found", "not_found", "inaccessible", "invalid"]
    root_id: str | None = None
    reason: str | None = None


#: Sources that are explicitly paused. They stay registered so the catalog is
#: stable and honest ("this source exists"), but nothing may probe or start them:
#: no `stat` of their candidate path, no detection, no import. OpenClaw/Claw is
#: paused pending a product decision; wiring it back means removing it here, not
#: silently letting a directory check run.
PAUSED_SOURCE_IDS = frozenset({"openclaw"})


def inspect_source_location(source_id: str, root: Path) -> SourceLocation:
    if source_id in PAUSED_SOURCE_IDS:
        # Deliberately do not touch the filesystem: "paused" means no probe at all,
        # not "probe and then ignore the answer". `not_found` is the honest
        # existing state for "you cannot use this source"; the reason carries the
        # distinct cause so callers can tell pause from absence if they need to.
        return SourceLocation(source_id=source_id, state="not_found", reason="source_paused")
    try:
        details = root.stat()
        if not root.is_dir():
            return SourceLocation(source_id=source_id, state="invalid", reason="root_not_directory")
        if (
            not details.st_mode & 0o444
            or not details.st_mode & 0o111
            or not os.access(root, os.R_OK | os.X_OK)
        ):
            return SourceLocation(
                source_id=source_id, state="inaccessible", reason="permission_denied"
            )
        return SourceLocation(
            source_id=source_id, state="found", root_id=source_root_identity(root)
        )
    except FileNotFoundError:
        return SourceLocation(source_id=source_id, state="not_found")
    except PermissionError:
        return SourceLocation(source_id=source_id, state="inaccessible", reason="permission_denied")
    except SourceAccessError as error:
        state: Literal["inaccessible", "invalid"] = (
            "invalid" if error.code is SourceAccessErrorCode.ROOT_NOT_DIRECTORY else "inaccessible"
        )
        return SourceLocation(source_id=source_id, state=state, reason=error.code)
    except (OSError, RuntimeError):
        return SourceLocation(
            source_id=source_id, state="inaccessible", reason="location_unavailable"
        )
