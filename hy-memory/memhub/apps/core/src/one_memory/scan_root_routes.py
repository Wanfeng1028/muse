"""A4-01: the scan-root endpoints the CLI's `path` command talks to.

Only the configuration half is exposed: registering and listing directories.
Sweeping them is the daemon's job, and it is deliberately not reachable from
here — an endpoint that scans on demand would let a caller drive I/O the daemon
cannot account for, and the schedule is the daemon's to keep.

Every mutation bumps the revision, because adapters read roots as intent and
cannot otherwise tell a stale view from a current one; a revoked root that kept
being scanned would present as a scanning bug rather than the stale intent it is.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.params import Depends

from one_memory.memory_server.scan_root_store import ScanRootStore, blank, new_root_id
from one_memory.memory_server.scan_roots import ScanRoot, ScanRootConfig, canonical, validate


def scan_root_router(dependencies: Sequence[Depends]) -> APIRouter:
    router = APIRouter(prefix="/api/v1/scan-roots", dependencies=dependencies)

    def _store(request: Request) -> ScanRootStore:
        database = request.app.state.evidence_store.database_path
        return ScanRootStore(database)

    @router.get("")
    async def list_roots(request: Request) -> dict[str, Any]:
        config = await _read(request, _store(request))
        return {
            "schema_version": 1,
            "revision": config.revision,
            "roots": [_root(root) for root in config.roots],
        }

    @router.post("")
    async def add_root(value: dict[str, Any], request: Request) -> dict[str, Any]:
        path = str(value.get("root") or value.get("path") or "")
        if blank(path):
            raise HTTPException(status_code=422, detail="scan_root_path_required")
        source_id = value.get("source")
        source_id = str(source_id) if source_id is not None else None
        recursive = bool(value.get("recursive", True))
        store = _store(request)
        config = await _read(request, store)
        root = ScanRoot(
            root_id=new_root_id(path, source_id),
            path=canonical(path),
            source_id=source_id,
            recursive=recursive,
        )
        from one_memory.memory_server.scan_roots import add_root as _add

        # `add_root` refuses a duplicate by raising, so the refusal is turned
        # into a 409 here; left uncaught it would surface as a 500 and read as a
        # server fault rather than the configuration mistake it is.
        try:
            updated = _add(config, root)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        problems = validate(updated)
        if problems:
            raise HTTPException(status_code=409, detail=problems[0])
        await _write(request, store, updated)
        return {"schema_version": 1, "revision": updated.revision, "root": _root(root)}

    @router.delete("")
    async def remove_root(value: dict[str, Any], request: Request) -> dict[str, Any]:
        path = str(value.get("root") or value.get("path") or "")
        if blank(path):
            raise HTTPException(status_code=422, detail="scan_root_path_required")
        store = _store(request)
        config = await _read(request, store)
        target = canonical(path)
        match = next((root for root in config.roots if root.path == target), None)
        if match is None:
            raise HTTPException(status_code=404, detail="scan_root_not_found")
        from one_memory.memory_server.scan_roots import remove_root as _remove

        await _write(request, store, _remove(config, match.root_id))
        return {"schema_version": 1, "removed": match.root_id}

    return router


def _root(root: ScanRoot) -> dict[str, Any]:
    return {
        "root_id": root.root_id,
        "path": root.path,
        "source_id": root.source_id,
        "recursive": root.recursive,
        "enabled": root.enabled,
    }


def _catalog(request: Request) -> dict[str, Any]:
    return cast(dict[str, Any], request.app.state.source_catalog)


def _authorized_root(request: Request, source_id: str) -> Any:
    from one_memory.imports.grants import SourceGrantStore

    store = request.app.state.source_grant_store
    return (
        store.authorized_root(user_id="local", source_id=source_id)
        if isinstance(store, SourceGrantStore)
        else None
    )


async def _read(request: Request, store: ScanRootStore) -> ScanRootConfig:
    return await asyncio.to_thread(store.get)


async def _write(request: Request, store: ScanRootStore, config: ScanRootConfig) -> None:
    await asyncio.to_thread(store.save, config)


def _problems(config: ScanRootConfig) -> list[str]:
    return validate(config)
