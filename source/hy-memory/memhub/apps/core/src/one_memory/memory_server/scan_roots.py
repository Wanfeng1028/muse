"""A4-01: scan root configuration (multi-path, revision, immediate scan).

The architecture calls for multi-path scan roots, an authorization revision, a
five-minute daemon schedule, and an immediate scan. This module is the
configuration half — the part decidable without touching a filesystem.

Two rules carry the weight:

- **Every change needs a revision.** Roots are user intent that adapters read;
  without a revision an adapter cannot tell whether its view is stale, and a
  revoked root could keep being scanned. So each mutation bumps it, and
  `changed_since` lets an adapter ask exactly whether it must re-check.
- **Duplicate paths are refused.** One directory registered twice would be swept
  twice and every file counted twice — which presents as a scanning bug rather
  than the configuration mistake it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class ScanRoot:
    root_id: str
    path: str
    source_id: str | None = None
    recursive: bool = True
    enabled: bool = True


@dataclass(frozen=True)
class ScanRootConfig:
    roots: tuple[ScanRoot, ...] = ()
    revision: int = 0


def canonical(path: str) -> str:
    """One comparable form for one directory.

    Two spellings of the same directory must compare equal, or the same root can
    be registered twice and swept twice.
    """
    text = str(PurePosixPath(path.strip()))
    if len(text) > 1:
        text = text.rstrip("/")
    return text


def is_blank(path: str) -> bool:
    """Whether the path carries no directory at all.

    Checked before canonicalisation on purpose: whitespace canonicalises to ".",
    which looks like a valid directory and would slip through.
    """
    return path.strip() == ""


def validate(config: ScanRootConfig) -> list[str]:
    """Configuration problems, or an empty list when it is usable."""
    problems: list[str] = []
    if config.revision < 0:
        problems.append("revision must not be negative")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for root in config.roots:
        if not root.root_id:
            problems.append("root_id must not be empty")
        if not root.path.strip():
            problems.append(f"{root.root_id}: path must not be empty")
        if root.root_id in seen_ids:
            problems.append(f"duplicate root_id: {root.root_id}")
        key = canonical(root.path)
        if key in seen_paths:
            problems.append(f"duplicate path: {key}")
        seen_ids.add(root.root_id)
        seen_paths.add(key)
    return problems


def _with_roots(config: ScanRootConfig, roots: tuple[ScanRoot, ...]) -> ScanRootConfig:
    return ScanRootConfig(roots=roots, revision=config.revision)


def add_root(config: ScanRootConfig, root: ScanRoot) -> ScanRootConfig:
    """Register a root, refusing a duplicate id or path instead of merging."""
    if is_blank(root.path):
        raise ValueError(f"{root.root_id}: path must not be empty")
    candidate = ScanRoot(
        root_id=root.root_id,
        path=canonical(root.path),
        source_id=root.source_id,
        recursive=root.recursive,
        enabled=root.enabled,
    )
    problems = validate(_with_roots(config, (*config.roots, candidate)))
    if problems:
        raise ValueError("; ".join(problems))
    return ScanRootConfig(roots=(*config.roots, candidate), revision=config.revision + 1)


def remove_root(config: ScanRootConfig, root_id: str) -> ScanRootConfig:
    kept = tuple(root for root in config.roots if root.root_id != root_id)
    if len(kept) == len(config.roots):
        return config
    return ScanRootConfig(roots=kept, revision=config.revision + 1)


def set_enabled(config: ScanRootConfig, root_id: str, enabled: bool) -> ScanRootConfig:
    roots: list[ScanRoot] = []
    changed = False
    for root in config.roots:
        if root.root_id == root_id and root.enabled is not enabled:
            roots.append(ScanRoot(**{**root.__dict__, "enabled": enabled}))
            changed = True
        else:
            roots.append(root)
    if not changed:
        return config
    return ScanRootConfig(roots=tuple(roots), revision=config.revision + 1)


def roots_for_source(config: ScanRootConfig, source_id: str) -> tuple[ScanRoot, ...]:
    return tuple(root for root in config.roots if root.source_id == source_id)


def enabled_roots(config: ScanRootConfig) -> tuple[ScanRoot, ...]:
    return tuple(root for root in config.roots if root.enabled)


def changed_since(config: ScanRootConfig, revision: int) -> bool:
    """Whether an adapter holding `revision` must re-read the roots."""
    return config.revision != revision
